"""LangGraph ride-booking agent.

    START -> agent --(tool call)--> validate --(Action)--> execute -> respond -> END
                ^                       |
                +------ (Repair) -------+     bounded self-repair loop

* agent: one LLM call with forced tool choice. On the happy path this is the ONLY LLM call.
* validate: deterministic resolution (gazetteer, calendar, business rules). Malformed arguments go
  back to the LLM with the exact error. Semantic problems (unknown place, 9 passengers) become
  deterministic clarify/decline actions with no extra LLM call.
* execute: the side effect, against the real backend (idempotency key per turn).
* respond: the user-facing reply is rendered from the tool result by a template, so ride facts
  (driver, ETA, ride number) can't be hallucinated.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from campusride import campus
from campusride.agent.backend import RideBackend
from campusride.agent.llm import LLMClient
from campusride.agent.prompts import system_prompt
from campusride.agent.schema import Action
from campusride.agent.validate import Repair, to_action
from campusride.config import IST, Settings, now_ist
from campusride.observability import AGENT_LATENCY, AGENT_REPAIRS, AGENT_TOOL_CALLS, current_trace_id, span
from campusride.services import DomainError


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    rider_id: int
    session_id: str
    now: str
    turn: int
    # per-turn scratch (reset at the start of each turn)
    repairs: int
    repair_reasons: list[str]
    llm_calls: int
    input_tokens: int
    output_tokens: int
    llm_latency_s: float
    cost_usd: float
    cached: bool
    action: dict | None
    tool_call_id: str | None
    result: dict | None
    error: dict | None
    outcome: str
    reply: str


@dataclass
class TurnResult:
    action: Action
    reply: str
    outcome: str  # executed | tool_error | clarify | decline | repair_exhausted
    result: dict | None
    error: dict | None
    repairs: int
    repair_reasons: list[str]
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    llm_latency_s: float
    latency_s: float
    cached: bool
    trace_id: str | None = None
    raw_tool_calls: list[dict] = field(default_factory=list)


def _action_to_state(a: Action) -> dict:
    d = a.__dict__.copy()
    d["pickup_at"] = a.pickup_at.isoformat() if a.pickup_at else None
    d["missing"] = list(a.missing)
    d["candidates"] = list(a.candidates)
    return d


def _action_from_state(d: dict) -> Action:
    d = dict(d)
    d["pickup_at"] = datetime.fromisoformat(d["pickup_at"]) if d.get("pickup_at") else None
    d["missing"] = tuple(d.get("missing", ()))
    d["candidates"] = tuple(d.get("candidates", ()))
    return Action(**d)


class RideAgent:
    def __init__(self, llm: LLMClient, backend: RideBackend, settings: Settings, checkpointer=None, recorder=None):
        self.llm = llm
        self.backend = backend
        self.settings = settings
        self.recorder = recorder  # async callable(session_id, rider_id, message, TurnResult)
        self.graph = self._build().compile(checkpointer=checkpointer or InMemorySaver())

    # ------------------------------------------------------------------ nodes

    async def _agent(self, state: AgentState) -> dict:
        now = datetime.fromisoformat(state["now"])
        msgs = [SystemMessage(system_prompt(now)), *state["messages"]]
        with span("agent.llm_decide"):
            res = await self.llm.ainvoke(msgs)
        return {
            "messages": [res.message],
            "llm_calls": state.get("llm_calls", 0) + 1,
            "input_tokens": state.get("input_tokens", 0) + res.input_tokens,
            "output_tokens": state.get("output_tokens", 0) + res.output_tokens,
            "llm_latency_s": state.get("llm_latency_s", 0.0) + res.latency_s,
            "cost_usd": state.get("cost_usd", 0.0) + res.cost_usd,
            "cached": res.cached and state.get("cached", True),
        }

    async def _validate(self, state: AgentState) -> dict:
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None) or []
        now = datetime.fromisoformat(state["now"])
        with span("agent.validate") as s:
            if not calls:
                verdict = Repair("no_tool_call", "You must call exactly one tool.")
                call_id = None
            else:
                call = calls[0]
                call_id = call["id"]
                verdict = to_action(call["name"], call["args"], now)
                s.set_attribute("agent.tool", call["name"])
            # Extra parallel calls are ignored, but each needs a ToolMessage to keep the history valid.
            extra = [ToolMessage("Ignored: only one tool call per turn.", tool_call_id=c["id"]) for c in calls[1:]]

            if isinstance(verdict, Repair):
                AGENT_REPAIRS.labels(verdict.reason).inc()
                s.set_attribute("agent.repair", verdict.reason)
                reasons = [*state.get("repair_reasons", []), verdict.reason]
                if state.get("repairs", 0) >= self.settings.llm_max_repairs:
                    fallback = Action("clarify", message="Sorry, I didn't quite get that. Could you rephrase your request?")
                    return {"action": _action_to_state(fallback), "tool_call_id": call_id, "outcome": "repair_exhausted",
                            "repair_reasons": reasons, "messages": extra}
                feedback = f"ERROR: {verdict.message} Call the tool again with corrected arguments."
                if call_id is None:
                    return {"repairs": state.get("repairs", 0) + 1, "repair_reasons": reasons,
                            "messages": [HumanMessage(f"[system] {feedback}")]}
                return {"repairs": state.get("repairs", 0) + 1, "repair_reasons": reasons,
                        "messages": [ToolMessage(feedback, tool_call_id=call_id), *extra]}
            return {"action": _action_to_state(verdict), "tool_call_id": call_id, "messages": extra}

    def _after_validate(self, state: AgentState) -> str:
        return "execute" if state.get("action") else "agent"

    async def _execute(self, state: AgentState) -> dict:
        action = _action_from_state(state["action"])
        if state.get("outcome") == "repair_exhausted":
            return {}
        if action.name in ("clarify", "decline"):
            return {"outcome": action.name}
        rider_id = state["rider_id"]
        now = datetime.fromisoformat(state["now"])
        with span("agent.tool", **{"agent.tool": action.name}) as s:
            try:
                if action.name == "book_ride":
                    key = f"{state['session_id']}:{state.get('turn', 0)}"
                    result = await self.backend.book(rider_id, action, key, now)
                elif action.name == "get_quote":
                    result = await self.backend.quote(action)
                elif action.name == "cancel_ride":
                    result = await self.backend.cancel(rider_id, action.ride_id)
                else:
                    result = await self.backend.status(rider_id, action.ride_id)
            except DomainError as e:
                AGENT_TOOL_CALLS.labels(action.name, "domain_error").inc()
                s.set_attribute("agent.tool_error", e.code)
                return {"outcome": "tool_error", "error": {"code": e.code, "message": e.message}}
            except Exception as e:  # infrastructure failure: surface it, don't crash the turn
                AGENT_TOOL_CALLS.labels(action.name, "exception").inc()
                s.record_exception(e)
                return {"outcome": "tool_error", "error": {"code": "internal", "message": "Something went wrong on our side. Please try again."}}
        AGENT_TOOL_CALLS.labels(action.name, "ok").inc()
        return {"outcome": "executed", "result": result}

    async def _respond(self, state: AgentState) -> dict:
        action = _action_from_state(state["action"])
        reply = render_reply(action, state.get("outcome", ""), state.get("result"), state.get("error"))
        msgs: list[BaseMessage] = []
        if state.get("tool_call_id"):
            payload = state.get("result") or state.get("error") or {"action": action.name, "message": action.message}
            msgs.append(ToolMessage(json.dumps(_compact(payload), default=str), tool_call_id=state["tool_call_id"]))
        msgs.append(AIMessage(reply))
        return {"reply": reply, "messages": msgs}

    def _build(self) -> StateGraph:
        g = StateGraph(AgentState)
        g.add_node("agent", self._agent)
        g.add_node("validate", self._validate)
        g.add_node("execute", self._execute)
        g.add_node("respond", self._respond)
        g.add_edge(START, "agent")
        g.add_edge("agent", "validate")
        g.add_conditional_edges("validate", self._after_validate, {"execute": "execute", "agent": "agent"})
        g.add_edge("execute", "respond")
        g.add_edge("respond", END)
        return g

    # ------------------------------------------------------------------ entrypoint

    async def run_turn(self, session_id: str, rider_id: int, message: str, now: datetime | None = None) -> TurnResult:
        now = now or now_ist()
        config = {"configurable": {"thread_id": session_id}}
        t0 = time.perf_counter()
        with span("agent.turn", **{"session.id": session_id, "rider.id": rider_id}):
            prev = await self.graph.aget_state(config)
            turn = (prev.values.get("turn", 0) + 1) if prev and prev.values else 1
            final = await self.graph.ainvoke(
                {
                    "messages": [HumanMessage(message)], "rider_id": rider_id, "session_id": session_id,
                    "now": now.isoformat(), "turn": turn, "repairs": 0, "repair_reasons": [], "llm_calls": 0,
                    "input_tokens": 0, "output_tokens": 0, "llm_latency_s": 0.0, "cost_usd": 0.0, "cached": True,
                    "action": None, "tool_call_id": None, "result": None, "error": None, "outcome": "", "reply": "",
                },
                config,
            )
            trace_id = current_trace_id()
        latency = time.perf_counter() - t0
        action = _action_from_state(final["action"])
        AGENT_LATENCY.labels(action.name).observe(latency)
        raw_calls = [
            {"name": c["name"], "args": c["args"]}
            for m in final["messages"] if isinstance(m, AIMessage) for c in (m.tool_calls or [])
        ]
        res = TurnResult(
            action=action, reply=final["reply"], outcome=final["outcome"], result=final.get("result"),
            error=final.get("error"), repairs=final.get("repairs", 0), repair_reasons=final.get("repair_reasons", []),
            llm_calls=final["llm_calls"], input_tokens=final["input_tokens"], output_tokens=final["output_tokens"],
            cost_usd=final["cost_usd"], llm_latency_s=final["llm_latency_s"], latency_s=latency,
            cached=final.get("cached", False), trace_id=trace_id, raw_tool_calls=raw_calls,
        )
        if self.recorder:
            await self.recorder(session_id, rider_id, message, res)
        return res


def _compact(d: Any) -> Any:
    if isinstance(d, dict):
        keep = ("id", "status", "driver_name", "driver_vehicle_type", "pickup_place_id", "dropoff_place_id",
                "pickup_at", "passengers", "options", "code", "message", "action")
        return {k: v for k, v in d.items() if k in keep and v is not None}
    return d


def _ist(ts: str | datetime) -> datetime:
    """DB timestamps come back in UTC; riders read IST."""
    dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(ts)
    return dt.astimezone(IST) if dt.tzinfo else dt


def _pname(pid: str | None) -> str:
    return campus.PLACES[pid].name if pid in campus.PLACES else "your pickup point"


def render_reply(action: Action, outcome: str, result: dict | None, error: dict | None) -> str:
    if outcome in ("clarify", "decline", "repair_exhausted"):
        if action.name == "clarify" and not action.message:
            return f"Could you tell me the {' and '.join(action.missing) or 'details'}?"
        return action.message or "Sorry, I can only help with campus rides."
    if outcome == "tool_error":
        return (error or {}).get("message", "Something went wrong.")
    r = result or {}
    if action.name == "book_ride":
        route = f"{_pname(r.get('pickup_place_id'))} → {_pname(r.get('dropoff_place_id'))}"
        pax = r.get("passengers", 1)
        who = f"{pax} passenger{'s' if pax != 1 else ''}"
        if r.get("status") == "assigned":
            eta = ""
            if r.get("driver_lat") is not None:
                d = campus.haversine_m(r["driver_lat"], r["driver_lon"], r["pickup_lat"], r["pickup_lon"])
                eta = f", about {max(1, round(campus.eta_seconds(d, r['driver_vehicle_type']) / 60))} min away"
            vt = (r.get("driver_vehicle_type") or "").replace("_", "-")
            return f"Booked ride #{r['id']} ({route}, {who}). Driver: {r['driver_name']} ({vt}){eta}."
        if r.get("status") == "scheduled":
            when = _ist(r["pickup_at"]).strftime("%a %d %b, %H:%M")
            return f"Scheduled ride #{r['id']} ({route}, {who}) for {when}. A driver will be assigned a few minutes before pickup."
        return f"Requested ride #{r['id']} ({route}, {who}). No driver is free right now, so I'm still looking and will update you here."
    if action.name == "get_quote":
        opts = r.get("options", [])
        if not opts:
            return f"No drivers are free near {_pname(action.pickup)} right now. You can still book and I'll keep looking."
        parts = [f"{o['vehicle_type'].replace('_', '-')}: {o['available_drivers']} free, pickup in ~{o['pickup_eta_min']} min, "
                 f"~₹{o['fare_inr']:.0f}" for o in opts]
        return f"{_pname(action.pickup)} → {_pname(action.dropoff)}: " + "; ".join(parts) + ". Want me to book one?"
    if action.name == "cancel_ride":
        return f"Cancelled ride #{r['id']}."
    if action.name == "get_ride_status":
        s = r.get("status")
        if s == "assigned":
            return f"Ride #{r['id']}: {r['driver_name']} is on the way to {_pname(r.get('pickup_place_id'))}."
        if s == "scheduled":
            return f"Ride #{r['id']} is scheduled for {_ist(r['pickup_at']).strftime('%a %d %b, %H:%M')}."
        return f"Ride #{r['id']} is {s.replace('_', ' ')}."
    return "Done."
