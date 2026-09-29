"""Reply rendering, the llm_resolves ablation, provider quirks and eval scoring: no network, no database."""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from campusride.agent.ablation import to_action_direct
from campusride.agent.graph import render_reply
from campusride.agent.llm import LLMClient, _RateLimiter, _signature_preserving_chat_openai
from campusride.agent.schema import TOOLS, Action
from campusride.config import IST, Settings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))
from run_agent_eval import score  # noqa: E402

NOW = datetime(2026, 10, 5, 14, 0, tzinfo=IST)


def test_scheduled_reply_is_rendered_in_ist_not_utc():
    # asyncpg returns timestamptz in UTC; 03:30 UTC is 09:00 IST.
    utc = datetime(2026, 10, 6, 3, 30, tzinfo=UTC).isoformat()
    action = Action("book_ride", pickup="govind", dropoff="hospital", passengers=1)
    reply = render_reply(action, "executed", {"id": 3, "status": "scheduled", "pickup_place_id": "govind",
                                              "dropoff_place_id": "hospital", "passengers": 1, "pickup_at": utc}, None)
    assert "09:00" in reply and "03:30" not in reply


def test_direct_resolution_accepts_ids_and_absolute_times():
    a = to_action_direct("book_ride", {"pickup": "rajendra", "dropoff": "lhc", "pickup_at": "2026-10-05T18:30",
                                       "passengers": 2}, NOW)
    assert (a.name, a.pickup, a.dropoff, a.passengers) == ("book_ride", "rajendra", "lhc", 2)
    assert a.pickup_at == datetime(2026, 10, 5, 18, 30, tzinfo=IST)


def test_direct_resolution_does_not_resolve_aliases_for_the_llm():
    a = to_action_direct("book_ride", {"pickup": "RB", "dropoff": "lhc"}, NOW)
    assert a.name == "clarify" and a.missing == ("pickup",)


def test_direct_resolution_keeps_business_rules_and_out_of_area():
    assert to_action_direct("book_ride", {"pickup": "rajendra", "dropoff": "Dehradun"}, NOW).decline_reason == "out_of_area"
    assert to_action_direct("book_ride", {"pickup": "sac", "dropoff": "lhc", "passengers": 9}, NOW).decline_reason == "capacity"
    assert to_action_direct("book_ride", {"pickup": "sac", "dropoff": "lhc", "pickup_at": "6pm"}, NOW).reason == "bad_time"


def test_thought_signatures_round_trip_on_openai_compatible_endpoints():
    """Gemini 3 rejects a follow-up request whose earlier tool calls lack their thought_signature."""
    cls = _signature_preserving_chat_openai()
    model = cls(model="gemini-x", api_key="k", base_url="http://localhost:1/v1")
    raw = {"id": "r", "object": "chat.completion", "created": 0, "model": "gemini-x",
           "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
               "role": "assistant", "content": None,
               "tool_calls": [{"id": "c1", "type": "function", "extra_content": {"google": {"thought_signature": "SIG"}},
                               "function": {"name": "book_ride", "arguments": "{\"pickup\": \"RB\"}"}}]}}]}
    msg = model._create_chat_result(raw).generations[0].message
    assert msg.additional_kwargs["tool_call_extra_content"] == {"c1": {"google": {"thought_signature": "SIG"}}}

    payload = model._get_request_payload([HumanMessage("hi"), msg, ToolMessage("ERROR: fix it", tool_call_id="c1")])
    sent = payload["messages"][1]
    assert sent["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "SIG"}}
    assert "tool_call_extra_content" not in sent


async def test_rate_limit_errors_are_retried_and_excluded_from_latency(monkeypatch):
    class Flaky:
        def __init__(self):
            self.n = 0

        async def ainvoke(self, messages):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("Error code: 429 - RESOURCE_EXHAUSTED, retry in 0.01s")
            return AIMessage("", tool_calls=[{"name": "decline", "args": {"reason": "x"}, "id": "c"}],
                             usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})

    async def fast_sleep(_):
        return None

    monkeypatch.setattr("campusride.agent.llm.asyncio.sleep", fast_sleep)
    flaky = Flaky()
    client = LLMClient(Settings(llm_provider="fake"), TOOLS, model=flaky)
    res = await client.ainvoke([HumanMessage("hi")])
    assert flaky.n == 2 and res.message.tool_calls[0]["name"] == "decline"
    assert res.wait_s >= 0 and res.latency_s < 1


async def test_non_retryable_errors_fail_fast():
    class Broken:
        async def ainvoke(self, messages):
            raise ValueError("invalid schema")

    client = LLMClient(Settings(llm_provider="fake"), TOOLS, model=Broken())
    with pytest.raises(ValueError):
        await client.ainvoke([HumanMessage("hi")])


async def test_rate_limiter_spaces_requests(monkeypatch):
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr("campusride.agent.llm.asyncio.sleep", fake_sleep)
    lim = _RateLimiter(rpm=60)  # one request per second
    for _ in range(3):
        await lim.wait()
    assert len(slept) == 2 and all(0.9 < s <= 2.0 for s in slept)


def test_also_ok_labels_count_as_exact_only_for_listed_alternatives():
    case = {"expected": {"action": "book_ride", "pickup": "rajendra", "dropoff": "lhc", "passengers": 1,
                         "vehicle_type": None, "pickup_at": "asap"},
            "also_ok": [{"action": "clarify", "missing": ["dropoff"]}]}
    assert score(case, {"action": "clarify", "missing": ["dropoff"]})["exact"]
    assert not score(case, {"action": "clarify", "missing": ["pickup"]})["exact"]
    assert not score(case, {"action": "decline", "reason": "out_of_scope"})["exact"]
