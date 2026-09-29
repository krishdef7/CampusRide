"""Collect REAL user phrasings with labels that are correct by construction.

Each scenario is generated from slots (who, from, to, when, how many, vehicle, intent) and the label is
computed from the slots. Participants only see a plain-language description of the situation and type
the message they would send to a ride bot. Their wording is the data; the scenario is the label.

    python evals/collect/make_form.py            # writes scenarios.json + create_form.gs
    # 1. open https://script.google.com -> New project -> paste create_form.gs -> Run -> copy the logged URL
    # 2. share the form (hostel / class WhatsApp groups); each person answers ~10 scenarios
    # 3. Form responses -> Link to Sheets -> File > Download > CSV
    python evals/collect/import_responses.py responses.csv   # -> evals/data/agent_eval_real_test.jsonl
    python evals/run_agent_eval.py --split real_test

The descriptions deliberately avoid the gazetteer's abbreviations and the eval templates' wording, so
participants use their own words.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from campusride.campus import CAPACITY, PLACES  # noqa: E402
from campusride.config import IST  # noqa: E402

HERE = Path(__file__).resolve().parent
NOW = datetime(2026, 10, 5, 14, 0, tzinfo=IST)  # "It's Monday, 2 pm" in every scenario
HOSTELS = ["rajendra", "govind", "cautley", "jawahar", "ravindra", "radhakrishnan", "azad", "ganga", "rajiv",
           "kasturba", "sarojini", "himalaya"]
DESTS = ["lhc", "mgcl", "main_building", "sac", "mac", "sports_complex", "hospital", "main_gate", "railway_station",
         "bus_stand", "civil_lines", "cse_dept", "convocation_hall"]
VEH_WORDS = {"e_rickshaw": "an e-rickshaw", "auto": "an auto", "cab": "a cab"}
WHO = {1: "alone", 2: "with one friend", 3: "with two friends", 4: "with three friends", 5: "with four friends"}


def _time(rng: random.Random) -> tuple[str, str]:
    kind = rng.choice(["asap", "asap", "today", "tomorrow", "relative"])
    if kind == "asap":
        return "as soon as possible", "asap"
    if kind == "relative":
        m = rng.choice([10, 15, 20, 30, 45, 60])
        return f"in {m} minutes", (NOW + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M")
    day = 0 if kind == "today" else 1
    h, m = rng.choice([(17, 30), (18, 0), (19, 15), (20, 0), (21, 30)] if day == 0 else [(7, 0), (8, 30), (9, 0), (18, 0)])
    at = (NOW + timedelta(days=day)).replace(hour=h, minute=m)
    return f"{'today' if day == 0 else 'tomorrow'} at {at.strftime('%I:%M %p').lstrip('0')}", at.strftime("%Y-%m-%dT%H:%M")


def scenarios(n: int = 60, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        kind = rng.choices(["book", "quote", "status", "cancel", "out_of_area", "capacity"], [60, 12, 7, 7, 7, 7])[0]
        p, d = rng.sample(HOSTELS, 1)[0], rng.choice(DESTS)
        if rng.random() < 0.3:
            p, d = d, p  # heading back to the hostel
        pax = rng.choice([1, 1, 1, 2, 3, 4])
        veh = rng.choice([None, None, None, "e_rickshaw", "auto", "cab"])
        if veh and pax > CAPACITY[veh]:
            veh = "cab"
        sid = f"S{i + 1:03d}"
        if kind in ("book", "quote"):
            when_txt, when_label = _time(rng)
            vtxt = f" You specifically want {VEH_WORDS[veh]}." if veh else " Any vehicle is fine."
            if kind == "book":
                desc = (f"You are at {PLACES[p].name} and want to go to {PLACES[d].name}, {WHO[pax]}, {when_txt}.{vtxt} "
                        "Ask the bot to book it.")
                label = {"action": "book_ride", "pickup": p, "dropoff": d, "passengers": pax, "vehicle_type": veh,
                         "pickup_at": when_label}
            else:
                desc = (f"You are at {PLACES[p].name} and thinking of going to {PLACES[d].name}, {WHO[pax]}.{vtxt} "
                        "You are NOT booking yet: ask how much it would cost or how long the pickup would take.")
                label = {"action": "get_quote", "pickup": p, "dropoff": d, "passengers": pax, "vehicle_type": veh}
            out.append({"id": sid, "description": desc, "expected": label})
        elif kind in ("status", "cancel"):
            with_id = rng.random() < 0.4
            rid = 40_000 + i
            ref = f" Your booking number is {rid}." if with_id else ""
            desc = (f"You booked a ride earlier.{ref} " +
                    ("Ask the bot where your ride is." if kind == "status" else "Your plans changed: ask the bot to cancel it."))
            action = "get_ride_status" if kind == "status" else "cancel_ride"
            out.append({"id": sid, "description": desc, "needs_ride": True, "ride_id": rid,
                        "expected": {"action": action, "ride_id": rid if with_id else None}})
        elif kind == "out_of_area":
            city = rng.choice(["Dehradun", "Haridwar", "Rishikesh", "Delhi airport"])
            desc = f"You are at {PLACES[p].name} and want a ride to {city}. Ask the bot."
            out.append({"id": sid, "description": desc, "expected": {"action": "decline", "reason": "out_of_area"}})
        else:
            big = rng.choice([7, 8, 10])
            desc = f"You and {big - 1} friends (all {big} of you) want one vehicle from {PLACES[p].name} to {PLACES[d].name}. Ask the bot."
            out.append({"id": sid, "description": desc, "expected": {"action": "decline", "reason": "capacity"}})
    return out


GS = """// Generated by evals/collect/make_form.py. Paste into https://script.google.com and press Run.
function createForm() {
  var scenarios = %s;
  var form = FormApp.create('CampusRide: how would you ask a ride bot?');
  form.setDescription('It is Monday, 2 pm, on the IIT Roorkee campus. For each situation, type the message you would ' +
    'send to a campus ride-booking chatbot, exactly as you would really type it (short forms, Hinglish, typos: all fine). ' +
    'Skip any you like. No personal data is collected.');
  form.setCollectEmail(false);
  scenarios.forEach(function (s) {
    form.addParagraphTextItem().setTitle('[' + s.id + '] ' + s.description).setRequired(false);
  });
  Logger.log('Share this link: ' + form.getPublishedUrl());
  Logger.log('Edit link: ' + form.getEditUrl());
}
"""


def main() -> None:
    sc = scenarios()
    (HERE / "scenarios.json").write_text(json.dumps(sc, indent=1, ensure_ascii=False), encoding="utf-8")
    public = [{"id": s["id"], "description": s["description"]} for s in sc]
    (HERE / "create_form.gs").write_text(GS % json.dumps(public, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(sc)} scenarios -> {HERE / 'scenarios.json'} and {HERE / 'create_form.gs'}")


if __name__ == "__main__":
    main()
