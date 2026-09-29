"""Turn a raw LLM tool call into a resolved `Action`, or explain precisely why it can't be.

Three outcomes:
* `Action` - resolved; may itself be a deterministic clarify/decline (unknown place, 9 passengers, ...)
* `Repair` - the arguments are malformed (bad schema, '6pm' instead of '18:00', ...). The error goes back
  to the LLM as a ToolMessage so it can fix its own call. Bounded by `llm_max_repairs`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import ValidationError

from campusride import campus
from campusride.agent.schema import TOOLS_BY_NAME, Action, When

_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


@dataclass(frozen=True)
class Repair:
    reason: str  # metric label
    message: str  # shown to the LLM


def resolve_when(when: When, now: datetime) -> datetime | None | Repair:
    if when.type == "asap":
        return None
    if when.type == "in":
        if when.minutes is None or when.minutes <= 0:
            return Repair("bad_time", "when.type='in' needs a positive integer 'minutes'.")
        return (now + timedelta(minutes=when.minutes)).replace(second=0, microsecond=0)
    if when.time_24h is None or not _HHMM.match(when.time_24h.strip()):
        return Repair("bad_time", f"when.time_24h must be 24-hour 'HH:MM' (got {when.time_24h!r}).")
    if when.day_offset < 0:
        return Repair("bad_time", "when.day_offset can't be negative.")
    h, m = (int(x) for x in when.time_24h.strip().split(":"))
    day = (now + timedelta(days=when.day_offset)).date()
    return datetime(day.year, day.month, day.day, h, m, tzinfo=now.tzinfo)


def _place(mention: str, field: str) -> str | Action:
    r = campus.resolve_place(mention)
    if r.ok:
        return r.place_id
    if r.status == "out_of_area":
        return Action("decline", decline_reason="out_of_area",
                      message=f"Sorry, {mention} is outside our service area. We only run rides on and around the IIT Roorkee campus.")
    if r.status == "ambiguous":
        names = ", ".join(campus.PLACES[c].name for c in r.candidates[:4])
        return Action("clarify", missing=(field,), candidates=r.candidates,
                      message=f"Which {field} did you mean by '{mention}'? For example: {names}.")
    return Action("clarify", missing=(field,), message=f"I couldn't find '{mention}' on campus. Where exactly is your {field}?")


def to_action(tool_name: str, args: dict, now: datetime) -> Action | Repair:
    model = TOOLS_BY_NAME.get(tool_name)
    if model is None:
        return Repair("unknown_tool", f"Unknown tool {tool_name!r}. Use one of: {', '.join(TOOLS_BY_NAME)}.")
    try:
        parsed = model.model_validate(args)
    except ValidationError as e:
        errs = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        return Repair("schema", f"Invalid arguments for {tool_name}: {errs}")

    if tool_name == "decline":
        return Action("decline", decline_reason="out_of_scope", message=parsed.reason)
    if tool_name == "ask_clarification":
        return Action("clarify", missing=tuple(sorted(set(parsed.missing))), message=parsed.question)
    if tool_name in ("cancel_ride", "get_ride_status"):
        return Action(tool_name, ride_id=parsed.ride_id)

    # book_ride / get_quote
    if not parsed.pickup.strip() or not parsed.dropoff.strip():
        return Repair("schema", "pickup and dropoff must be non-empty; call ask_clarification if the user didn't say.")
    pickup = _place(parsed.pickup, "pickup")
    dropoff = _place(parsed.dropoff, "dropoff")
    for resolved in (pickup, dropoff):
        if isinstance(resolved, Action) and resolved.name == "decline":
            return resolved
    if isinstance(pickup, Action) and isinstance(dropoff, Action):
        return Action("clarify", missing=("dropoff", "pickup"), message=f"{pickup.message} {dropoff.message}")
    for resolved in (pickup, dropoff):
        if isinstance(resolved, Action):
            return resolved
    if pickup == dropoff:
        return Action("decline", decline_reason="same_place", message="Pickup and destination are the same place.")

    if parsed.passengers < 1:
        return Repair("schema", "passengers must be at least 1 (the user counts).")
    vehicle = None if parsed.vehicle_type == "any" else parsed.vehicle_type
    if parsed.passengers > campus.MAX_PASSENGERS:
        return Action("decline", decline_reason="capacity",
                      message=f"Our largest vehicle seats {campus.MAX_PASSENGERS}. Please split into two rides.")
    if vehicle and parsed.passengers > campus.CAPACITY[vehicle]:
        return Action("decline", decline_reason="capacity",
                      message=f"A {vehicle.replace('_', '-')} seats at most {campus.CAPACITY[vehicle]}. Try a cab or split the group.")

    if tool_name == "get_quote":
        return Action("get_quote", pickup=pickup, dropoff=dropoff, passengers=parsed.passengers, vehicle_type=vehicle)

    pickup_at = resolve_when(parsed.when, now)
    if isinstance(pickup_at, Repair):
        return pickup_at
    if pickup_at is not None:
        if pickup_at < now - timedelta(minutes=1):
            return Action("decline", decline_reason="past_time", message="That time has already passed. When should we pick you up?")
        if pickup_at > now + timedelta(days=7):
            return Action("decline", decline_reason="too_far_ahead", message="Rides can be booked at most 7 days ahead.")
    return Action("book_ride", pickup=pickup, dropoff=dropoff, pickup_at=pickup_at,
                  passengers=parsed.passengers, vehicle_type=vehicle)
