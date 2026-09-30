"""Prompt / tool-schema versions, selectable so a candidate can be evaluated before it becomes the default.

v3 (default, frozen before the first test run): agent.schema + agent.prompts.
v4 (candidate): found by error analysis of Gemma 4 on natural_test, so it must be validated on dev splits;
    its test-split numbers are post-hoc. The v3 `ask_clarification.missing` accepted "time" / "passengers" /
    "ride_id" although none of them is ever required (defaults: now, 1, latest ride). Gemma asked for a time in
    12 of its 29 natural_test misses, including fully specified bookings. v4 allows only pickup / dropoff in
    `missing` (anything else goes back to the LLM through the self-repair loop) and says so in the prompt.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from campusride.agent import schema
from campusride.agent.prompts import system_prompt
from campusride.agent.schema import Action
from campusride.agent.validate import Repair, to_action


class ask_clarification(BaseModel):
    """Ask where the ride should start or end when the user didn't say (or said something ambiguous).
    Time, passengers, vehicle and ride number are never required: don't ask for them."""

    missing: list[Literal["pickup", "dropoff"]] = Field(description="Which of pickup / dropoff is missing or ambiguous")
    question: str = Field(description="One short, friendly question to the user")


TOOLS_V4 = [schema.book_ride, schema.get_quote, schema.cancel_ride, schema.get_ride_status, ask_clarification,
            schema.decline]

_V4_RULE = """10. Only a missing or ambiguous pickup or destination is a reason to ask. Everything else has a default:
    no time = as soon as possible, no count = 1 passenger, no vehicle = any, no ride number = the latest ride.
    If pickup and destination are known, book (or quote) directly.
"""


def system_prompt_v4(now: datetime) -> str:
    return system_prompt(now) + _V4_RULE


def to_action_v4(tool_name: str, args: dict, now: datetime) -> Action | Repair:
    if tool_name == "ask_clarification":
        try:
            parsed = ask_clarification.model_validate(args)
        except ValidationError:
            return Repair("schema", "ask_clarification.missing may only contain 'pickup' and/or 'dropoff'. "
                                    "Time, passengers, vehicle and ride number have defaults: don't ask for them; "
                                    "call the right tool instead.")
        if not parsed.missing:
            return Repair("schema", "ask_clarification needs at least one of 'pickup' / 'dropoff'. If both are known, "
                                    "call book_ride or get_quote.")
    return to_action(tool_name, args, now)


VARIANTS = {"v4": (TOOLS_V4, {"prompt_fn": system_prompt_v4, "to_action_fn": to_action_v4})}
