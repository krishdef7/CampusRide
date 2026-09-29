"""Graph behaviour with a scripted fake LLM and an in-memory backend: no network, no database."""

from datetime import datetime

from langchain_core.messages import AIMessage

from campusride.agent.graph import RideAgent
from campusride.agent.llm import LLMClient
from campusride.agent.schema import TOOLS
from campusride.config import IST, Settings
from campusride.services import DomainError

NOW = datetime(2026, 10, 5, 14, 0, tzinfo=IST)


class ScriptedModel:
    """Returns pre-written tool calls in order and records what it was shown."""

    def __init__(self, calls):
        self.calls = list(calls)
        self.seen = []

    async def ainvoke(self, messages):
        self.seen.append(messages)
        name, args = self.calls.pop(0)
        return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"call_{len(self.seen)}"}],
                         usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})


class FakeBackend:
    def __init__(self):
        self.booked = []
        self.cancelled = []

    async def book(self, rider_id, action, key, now):
        self.booked.append((rider_id, action, key))
        return {"id": 42, "status": "scheduled" if action.pickup_at else "searching", "pickup_place_id": action.pickup,
                "dropoff_place_id": action.dropoff, "passengers": action.passengers,
                "pickup_at": (action.pickup_at or now).isoformat()}

    async def quote(self, action):
        return {"pickup_place_id": action.pickup, "dropoff_place_id": action.dropoff, "options": []}

    async def cancel(self, rider_id, ride_id):
        if ride_id == 999:
            raise DomainError("forbidden", "Ride #999 isn't one of your rides.")
        self.cancelled.append(ride_id)
        return {"id": ride_id or 7, "status": "cancelled"}

    async def status(self, rider_id, ride_id):
        return {"id": ride_id or 7, "status": "scheduled", "pickup_at": NOW.isoformat()}


def make(calls):
    settings = Settings(llm_provider="fake", llm_model="gpt-4.1-mini")
    model = ScriptedModel(calls)
    backend = FakeBackend()
    return RideAgent(LLMClient(settings, TOOLS, model=model), backend, settings), model, backend


BOOK = {"pickup": "RB", "dropoff": "LHC", "when": {"type": "at", "day_offset": 0, "time_24h": "18:00"}, "passengers": 2}


async def test_happy_path_single_llm_call():
    agent, model, backend = make([("book_ride", BOOK)])
    res = await agent.run_turn("s1", 1, "RB to LHC at 6pm for 2", now=NOW)
    assert res.outcome == "executed" and res.llm_calls == 1 and res.repairs == 0
    assert backend.booked[0][1].pickup == "rajendra" and backend.booked[0][1].passengers == 2
    assert "ride #42" in res.reply.lower()
    assert res.input_tokens == 100 and res.cost_usd > 0


async def test_self_repair_on_malformed_args():
    bad = {**BOOK, "when": {"type": "at", "time_24h": "6pm"}}
    agent, model, backend = make([("book_ride", bad), ("book_ride", BOOK)])
    res = await agent.run_turn("s2", 1, "RB to LHC at 6pm for 2", now=NOW)
    assert res.repairs == 1 and res.repair_reasons == ["bad_time"] and res.llm_calls == 2
    assert res.outcome == "executed"
    # the validator's error message was shown to the model on the retry
    assert "HH:MM" in model.seen[1][-1].content


async def test_repair_budget_is_bounded():
    bad = {**BOOK, "when": {"type": "at", "time_24h": "six"}}
    agent, _, backend = make([("book_ride", bad)] * 3)
    res = await agent.run_turn("s3", 1, "...", now=NOW)
    assert res.outcome == "repair_exhausted" and res.llm_calls == 3 and not backend.booked


async def test_semantic_errors_do_not_cost_extra_llm_calls():
    agent, _, backend = make([("book_ride", {**BOOK, "passengers": 12})])
    res = await agent.run_turn("s4", 1, "12 of us", now=NOW)
    assert res.action.name == "decline" and res.action.decline_reason == "capacity" and res.llm_calls == 1
    assert not backend.booked


async def test_multiturn_memory_and_idempotency_key():
    agent, model, backend = make([
        ("ask_clarification", {"missing": ["dropoff"], "question": "Where to?"}),
        ("book_ride", BOOK),
    ])
    r1 = await agent.run_turn("s5", 1, "pick me up from RB at 6pm", now=NOW)
    assert r1.action.name == "clarify" and r1.reply == "Where to?"
    r2 = await agent.run_turn("s5", 1, "LHC", now=NOW)
    assert r2.outcome == "executed"
    # second LLM call saw the whole conversation, including the first tool call's result
    assert len(model.seen[1]) > 3
    assert backend.booked[0][2] == "s5:2"  # idempotency key is per session turn


async def test_tool_domain_error_surfaces_as_reply():
    agent, _, _ = make([("cancel_ride", {"ride_id": 999})])
    res = await agent.run_turn("s6", 1, "cancel ride 999", now=NOW)
    assert res.outcome == "tool_error" and "isn't one of your rides" in res.reply


async def test_parallel_tool_calls_only_first_executes():
    class Double(ScriptedModel):
        async def ainvoke(self, messages):
            self.seen.append(messages)
            return AIMessage("", tool_calls=[
                {"name": "book_ride", "args": BOOK, "id": "a"}, {"name": "book_ride", "args": BOOK, "id": "b"}])

    settings = Settings(llm_provider="fake")
    backend = FakeBackend()
    agent = RideAgent(LLMClient(settings, TOOLS, model=Double([])), backend, settings)
    res = await agent.run_turn("s7", 1, "book twice", now=NOW)
    assert res.outcome == "executed" and len(backend.booked) == 1
