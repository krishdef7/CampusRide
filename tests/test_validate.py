from datetime import datetime

import pytest

from campusride.agent.schema import Action
from campusride.agent.validate import Repair, to_action
from campusride.config import IST

NOW = datetime(2026, 10, 5, 14, 0, tzinfo=IST)


def book(**kw):
    args = {"pickup": "RB", "dropoff": "LHC", "when": {"type": "asap"}, "passengers": 1, "vehicle_type": "any"} | kw
    return to_action("book_ride", args, NOW)


def test_happy_path_resolves_everything():
    a = book(when={"type": "at", "day_offset": 1, "time_24h": "18:30"}, passengers=3, vehicle_type="cab")
    assert a == Action("book_ride", pickup="rajendra", dropoff="lhc", pickup_at=datetime(2026, 10, 6, 18, 30, tzinfo=IST),
                       passengers=3, vehicle_type="cab")
    assert a.as_label()["pickup_at"] == "2026-10-06T18:30"


def test_relative_time():
    assert book(when={"type": "in", "minutes": 20}).pickup_at == datetime(2026, 10, 5, 14, 20, tzinfo=IST)


@pytest.mark.parametrize("when", [{"type": "at", "time_24h": "6pm"}, {"type": "at"}, {"type": "in", "minutes": 0},
                                  {"type": "at", "day_offset": -1, "time_24h": "10:00"}])
def test_malformed_time_goes_back_to_llm(when):
    r = book(when=when)
    assert isinstance(r, Repair) and r.reason == "bad_time"


def test_schema_error_is_repair():
    r = to_action("book_ride", {"pickup": "RB"}, NOW)
    assert isinstance(r, Repair) and r.reason == "schema" and "dropoff" in r.message


def test_unknown_tool_is_repair():
    assert isinstance(to_action("fly_drone", {}, NOW), Repair)


@pytest.mark.parametrize("kw,reason", [
    ({"passengers": 9}, "capacity"),
    ({"passengers": 4, "vehicle_type": "auto"}, "capacity"),
    ({"dropoff": "Rajendra Bhawan"}, "same_place"),
    ({"dropoff": "Delhi airport"}, "out_of_area"),
    ({"when": {"type": "at", "day_offset": 0, "time_24h": "09:00"}}, "past_time"),
    ({"when": {"type": "in", "minutes": 60 * 24 * 9}}, "too_far_ahead"),
])
def test_business_rules_decline_deterministically(kw, reason):
    a = book(**kw)
    assert isinstance(a, Action) and a.name == "decline" and a.decline_reason == reason


def test_ambiguous_place_asks_instead_of_guessing():
    a = book(pickup="my hostel")
    assert a.name == "clarify" and a.missing == ("pickup",) and len(a.candidates) > 2


def test_unknown_place_asks():
    a = book(dropoff="narnia")
    assert a.name == "clarify" and a.missing == ("dropoff",)


def test_quote_ignores_time_and_keeps_constraints():
    a = to_action("get_quote", {"pickup": "SAC", "dropoff": "station", "passengers": 2, "vehicle_type": "auto"}, NOW)
    assert a == Action("get_quote", pickup="sac", dropoff="railway_station", passengers=2, vehicle_type="auto")


def test_clarify_and_decline_passthrough():
    a = to_action("ask_clarification", {"missing": ["pickup", "dropoff"], "question": "Where from and to?"}, NOW)
    assert a.name == "clarify" and a.missing == ("dropoff", "pickup")
    assert to_action("decline", {"reason": "weather"}, NOW).decline_reason == "out_of_scope"
