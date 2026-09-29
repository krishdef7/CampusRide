"""Tool schemas the LLM sees, and the normalized `Action` that everything downstream works with.

The LLM chooses a tool and fills in *surface* arguments: place mentions as the user said them,
and times as small structured fields rather than timestamps. Deterministic code then resolves them
(gazetteer lookup, calendar arithmetic, business rules) into an `Action`. So the LLM handles
language, and code handles facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

VehicleArg = Literal["any", "e_rickshaw", "auto", "cab"]
Field_ = Literal["pickup", "dropoff", "time", "passengers", "ride_id"]


class When(BaseModel):
    """When the pickup should happen."""

    type: Literal["asap", "at", "in"] = Field(
        description="'asap' = now / right away / no time given; 'at' = a clock time; 'in' = relative, e.g. 'in 20 minutes'"
    )
    day_offset: int = Field(0, description="For type='at': 0 = today, 1 = tomorrow, ... up to 6. Use the calendar provided.")
    time_24h: str | None = Field(None, description="For type='at': 24-hour clock time 'HH:MM', e.g. '18:30'.")
    minutes: int | None = Field(None, description="For type='in': minutes from now. '1 hour' = 60, 'half an hour' = 30.")


class book_ride(BaseModel):
    """Book a ride between two campus places, now or at a future time."""

    pickup: str = Field(description="Pickup place exactly as the user named it (abbreviation, nickname or full name)")
    dropoff: str = Field(description="Destination place exactly as the user named it")
    when: When = Field(default_factory=lambda: When(type="asap"))
    passengers: int = Field(1, description="Total people riding, including the user. 'me and 2 friends' = 3")
    vehicle_type: VehicleArg = Field("any", description="Only if the user asks for a specific vehicle")


class get_quote(BaseModel):
    """Check availability, pickup ETA and fare between two places WITHOUT booking. Use for 'how much',
    'how long', 'are any autos free', 'is there a ride available'."""

    pickup: str
    dropoff: str
    passengers: int = 1
    vehicle_type: VehicleArg = "any"


class cancel_ride(BaseModel):
    """Cancel one of the user's rides."""

    ride_id: int | None = Field(None, description="Only if the user gives a ride number; otherwise null = their latest active ride")


class get_ride_status(BaseModel):
    """Status / driver / ETA of one of the user's rides."""

    ride_id: int | None = Field(None, description="Only if the user gives a ride number; otherwise null = their latest ride")


class ask_clarification(BaseModel):
    """Ask the user for information that is required but missing. Never guess a missing pickup or destination."""

    missing: list[Field_] = Field(description="Which required fields are missing")
    question: str = Field(description="One short, friendly question to the user")


class decline(BaseModel):
    """The request is not about campus rides (weather, food, homework, flights, ...)."""

    reason: str


TOOLS = [book_ride, get_quote, cancel_ride, get_ride_status, ask_clarification, decline]
TOOLS_BY_NAME = {t.__name__: t for t in TOOLS}

ActionName = Literal["book_ride", "get_quote", "cancel_ride", "get_ride_status", "clarify", "decline"]
DeclineReason = Literal[
    "out_of_scope", "out_of_area", "capacity", "past_time", "too_far_ahead", "same_place", "no_active_ride"
]


@dataclass(frozen=True)
class Action:
    """Normalized, fully-resolved decision. This is what evals compare against labels."""

    name: ActionName
    pickup: str | None = None  # place id
    dropoff: str | None = None
    pickup_at: datetime | None = None  # None = ASAP
    passengers: int | None = None
    vehicle_type: str | None = None  # None = any
    ride_id: int | None = None
    missing: tuple[str, ...] = ()
    decline_reason: str | None = None
    message: str | None = None  # clarification question / decline explanation
    candidates: tuple[str, ...] = field(default=(), compare=False)

    def as_label(self) -> dict:
        """Canonical JSON form shared with the eval dataset."""
        d: dict = {"action": self.name}
        if self.name in ("book_ride", "get_quote"):
            d |= {"pickup": self.pickup, "dropoff": self.dropoff, "passengers": self.passengers,
                  "vehicle_type": self.vehicle_type}
        if self.name == "book_ride":
            d["pickup_at"] = self.pickup_at.strftime("%Y-%m-%dT%H:%M") if self.pickup_at else "asap"
        if self.name in ("cancel_ride", "get_ride_status"):
            d["ride_id"] = self.ride_id
        if self.name == "clarify":
            d["missing"] = sorted(set(self.missing))
        if self.name == "decline":
            d["reason"] = self.decline_reason
        return d
