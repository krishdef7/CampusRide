"""Build the labeled agent eval set: 100 dev cases (for prompt iteration) and 500 held-out test cases.

Labels are correct by construction. Each generated case is assembled from slots (place, time, passengers,
vehicle, phrasing template), and the label is computed from the slots, not from any model. On top of
that, hand-written hard cases (tests/…/handwritten.py) cover phrasings that templates can't.

The phrasing templates, place surface forms and the policy (e.g. "no time given = ASAP") are fixed
in advance and mirror docs/labeling_policy.md. The test split is never used to tune the prompt.

    python evals/build_dataset.py        # writes evals/data/agent_eval_{dev,test}.jsonl
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from handwritten import HANDWRITTEN  # noqa: E402
from natural import NATURAL  # noqa: E402
from safety import SAFETY  # noqa: E402

from campusride.campus import CAPACITY, PLACES  # noqa: E402
from campusride.config import IST  # noqa: E402

OUT = Path(__file__).resolve().parent / "data"

NOWS = [
    datetime(2026, 10, 5, 14, 0, tzinfo=IST),   # Monday afternoon
    datetime(2026, 10, 7, 8, 15, tzinfo=IST),   # Wednesday morning
    datetime(2026, 10, 9, 21, 40, tzinfo=IST),  # Friday night
    datetime(2026, 10, 10, 11, 5, tzinfo=IST),  # Saturday late morning
    datetime(2026, 10, 11, 18, 30, tzinfo=IST),  # Sunday evening
]
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# ----------------------------------------------------------------- surface forms


def place_surface(rng: random.Random, pid: str) -> tuple[str, list[str]]:
    p = PLACES[pid]
    forms = [p.name, p.name.lower(), *p.aliases]
    s = rng.choice(forms)
    tags = []
    if s in p.aliases and len(s) <= 4:
        s = s.upper() if rng.random() < 0.6 else s
        tags.append("abbrev")
    if len(s) > 7 and rng.random() < 0.08:  # a human-obvious typo: drop one interior character
        i = rng.randrange(2, len(s) - 2)
        s = s[:i] + s[i + 1:]
        tags.append("typo")
    if s.lower() in ("library", "hospital", "stadium", "market", "station", "pool", "gate", "ground") and rng.random() < 0.7:
        s = "the " + s
    return s, tags


def fmt_label(dt: datetime | None) -> str:
    return "asap" if dt is None else dt.strftime("%Y-%m-%dT%H:%M")


def _h12(h: int) -> tuple[int, str]:
    return (h % 12 or 12), ("am" if h < 12 else "pm")


def _clock(rng: random.Random, h: int, m: int) -> str:
    h12, ap = _h12(h)
    options = [f"{h12}{ap}", f"{h12} {ap}", f"{h12}:{m:02d} {ap}", f"{h:02d}:{m:02d}"]
    if m == 0:
        part = "in the morning" if h < 12 else "in the afternoon" if h < 17 else "in the evening" if h < 21 else "at night"
        options += [f"{h12} {ap.upper()}", f"{h12} o'clock {part}"]
    else:
        options += [f"{h12}.{m:02d} {ap}"]
        options = [o for o in options if ":" in o or "." in o]
    return rng.choice(options)


def time_phrase(rng: random.Random, now: datetime) -> tuple[str, str, list[str]]:
    """(surface, label, tags). All generated times are in the future relative to `now`."""
    kind = rng.choices(
        ["asap", "in", "today", "tomorrow", "weekday", "dayafter", "hinglish", "bare"],
        weights=[28, 14, 18, 16, 8, 4, 8, 4],
    )[0]
    today = now.replace(second=0, microsecond=0)
    if kind == "asap":
        return rng.choice(["", "", "now", "right now", "asap", "immediately", "right away", "abhi"]), "asap", []
    if kind == "in":
        m = rng.choice([10, 15, 20, 30, 45, 60, 90, 120])
        special = {30: ["in half an hour", "after half an hour"], 60: ["in an hour", "in 1 hour"],
                   90: ["in an hour and a half"], 120: ["in 2 hours", "after two hours"]}
        s = rng.choice(special.get(m, []) + [f"in {m} minutes", f"in {m} mins", f"after {m} min", f"{m} min baad"])
        return s, fmt_label(today + timedelta(minutes=m)), ["relative_time"]
    if kind in ("today", "bare", "hinglish") and now.hour <= 21:
        h = rng.randint(now.hour + 1, 22)
        m = rng.choice([0, 0, 15, 30, 45])
        dt = today.replace(hour=h, minute=m)
        if kind == "bare" and 1 <= h - 12 <= 11 and m == 0 and now.hour >= h - 12:
            return f"at {h - 12}", fmt_label(dt), ["bare_hour"]
        if kind == "hinglish" and 16 <= h <= 22:
            word = "shaam" if h <= 19 else "raat"
            return f"aaj {word} {h - 12} baje" if m == 0 else f"aaj {word} {h - 12}:{m:02d} baje", fmt_label(dt), ["hinglish"]
        return rng.choice(["at ", "at ", "today at ", ""]) + _clock(rng, h, m), fmt_label(dt), []
    if kind in ("tomorrow", "today", "bare", "hinglish"):
        h, m = rng.randint(6, 22), rng.choice([0, 0, 15, 30, 45])
        dt = (today + timedelta(days=1)).replace(hour=h, minute=m)
        if kind == "hinglish" and 6 <= h <= 11:
            return f"kal subah {h} baje" if m == 0 else f"kal subah {h}:{m:02d} baje", fmt_label(dt), ["hinglish"]
        lead = rng.choice(["tomorrow at ", "tomorrow ", "tmrw at ", "tomorrow at "])
        if h < 12 and rng.random() < 0.3:
            return f"tomorrow morning at {h}" + (f":{m:02d}" if m else ""), fmt_label(dt), []
        return lead + _clock(rng, h, m), fmt_label(dt), []
    if kind == "dayafter":
        h, m = rng.randint(7, 20), rng.choice([0, 30])
        dt = (today + timedelta(days=2)).replace(hour=h, minute=m)
        return "day after tomorrow at " + _clock(rng, h, m), fmt_label(dt), ["day_offset"]
    # weekday: never today or tomorrow, so the offset is unambiguous
    off = rng.randint(2, 6)
    target = today + timedelta(days=off)
    h, m = rng.randint(7, 21), rng.choice([0, 0, 30])
    dt = target.replace(hour=h, minute=m)
    wd = WEEKDAYS[target.weekday()]
    return rng.choice([f"on {wd} at ", f"this {wd} ", f"{wd.capitalize()} "]) + _clock(rng, h, m), fmt_label(dt), ["weekday"]


PAX = {
    1: ["", "", "", "just me", "for one person", "for 1"],
    2: ["for 2", "for two people", "me and a friend", "me and my roommate", "2 of us", "for 2 people"],
    3: ["for 3 people", "me and 2 friends", "the three of us", "hum 3 log", "for 3", "3 passengers"],
    4: ["for 4", "four of us", "me and 3 friends", "we are 4", "4 people"],
    5: ["for 5 people", "five of us", "me + 4 friends", "we are 5"],
    6: ["for 6 people", "six of us", "we are 6", "me and 5 friends"],
}
VEH = {
    None: [""],
    "e_rickshaw": ["an e-rickshaw", "a toto", "an e-rick", "e rickshaw"],
    "auto": ["an auto", "auto", "an auto-rickshaw"],
    "cab": ["a cab", "a car", "a taxi"],
}


def pax_vehicle(rng: random.Random) -> tuple[int, str | None, str, str, list[str]]:
    pax = rng.choices([1, 2, 3, 4, 5, 6], weights=[45, 22, 15, 10, 5, 3])[0]
    vehicle = rng.choices([None, "e_rickshaw", "auto", "cab"], weights=[65, 12, 12, 11])[0]
    if vehicle and CAPACITY[vehicle] < pax:
        vehicle = "cab"
    tags = []
    ps = rng.choice(PAX[pax])
    if pax > 1 and any(w in ps for w in ("friend", "roommate", "+")):
        tags.append("passenger_arithmetic")
    return pax, vehicle, ps, rng.choice(VEH[vehicle]), tags


def two_places(rng: random.Random) -> tuple[str, str]:
    ids = list(PLACES)
    a = rng.choice(ids)
    b = rng.choice([i for i in ids if i != a])
    return a, b


def tidy(s: str) -> str:
    s = " ".join(s.split())
    s = s.replace(" ,", ",").replace(" ?", "?").replace(" .", ".").replace(",,", ",").strip(" ,")
    if s and random.random() < 0.3:
        s = s.lower()
    return s


BOOK_TEMPLATES = [
    "Book {veh} from {p} to {d} {t} {pax}",
    "I need a ride from {p} to {d} {t} {pax}",
    "{p} to {d} {t} {pax}",
    "Can you get me {veh} to {d} from {p} {t}? {pax}",
    "pick me up at {p} and drop me at {d} {t}",
    "mujhe {p} se {d} jana hai {t} {pax}",
    "{t} {p} se {d} tak {veh} chahiye {pax}",
    "need to reach {d} from {p} {t}, {pax}",
    "hey, could you book {veh} to {d}? I'm at {p}. {t} {pax}",
    "going to {d} from {p} {t}, please book {pax}",
    "book a ride {p} -> {d} {t} {pax}",
    "Please arrange {veh} from {p} to {d} {t} {pax}",
    "I want to go from {p} to {d} {t} {pax}",
    "ride from {p} to {d} {t} {pax} pls",
    "get me to {d} from {p} {t} {pax}",
    "bhai {p} se {d} ke liye {veh} book kar do {t} {pax}",
]
QUOTE_TEMPLATES = [
    "How much would a ride from {p} to {d} cost? {pax}",
    "what's the fare from {p} to {d} {pax}",
    "{p} se {d} kitna lagega?",
    "how long would it take to get {veh} from {p} to {d}?",
    "is there a ride available from {p} to {d} right now? just checking, don't book",
    "any {vehp} free near {p}? thinking of going to {d}, what's the price",
    "check price {p} to {d} {pax}",
    "how much for {veh} from {p} to {d}?",
]
CANCEL_TEMPLATES = ["cancel my ride", "please cancel the booking", "I don't need the ride anymore, cancel it",
                    "cancel it", "ride cancel kar do", "plans changed, cancel my cab", "cancel ride #{id}",
                    "cancel booking {id}", "please cancel ride {id}", "i want to cancel ride number {id}"]
STATUS_TEMPLATES = ["where is my ride?", "status of my ride", "how far is my driver", "is my driver coming?",
                    "mera ride kahan hai?", "has a driver been assigned yet?", "status of ride #{id}",
                    "where's ride {id}?", "any update on booking {id}?", "track ride {id}"]
MISSING_PICKUP = ["take me to {d}", "I need to go to {d} {t}", "book {veh} to {d}", "{d} jana hai", "drop me at {d} {t}",
                  "need a ride to {d} {pax}"]
MISSING_DROPOFF = ["pick me up from {p}", "I'm at {p}, need a ride", "book {veh} from {p} {t}", "{p} se ride chahiye",
                   "send a ride to {p} {t}"]
MISSING_BOTH = ["book a ride", "I need a cab", "can I get a ride {t}?", "ride chahiye", "book an auto please",
                "need a ride for 3 people"]
AMBIGUOUS = [("from my hostel to {d}", "pickup"), ("from {p} to the hostel", "dropoff"), ("{p} to the department {t}", "dropoff"),
             ("take me from the bhawan to {d}", "pickup")]
OUT_OF_SCOPE = ["what's the weather tomorrow?", "who is the director of IIT Roorkee?", "order me a pizza",
                "write my DSA assignment", "tell me a joke", "what's in the mess menu today?",
                "how do I reset my ERP password?", "recommend a good movie", "what time does the library close?",
                "book a table at the canteen", "translate 'good morning' to French", "what's 234 * 19?",
                "how do I get a hostel room change?", "send a message to my friend", "play some music"]
OUT_OF_AREA = ["book a cab from {p} to Delhi airport {t}", "ride from {p} to Dehradun {t}", "{p} se Haridwar jana hai {t}",
               "I need to get to Jolly Grant airport from {p} {t}", "cab to Rishikesh from {p}", "{p} to Saharanpur {t} please"]
CAPACITY_TEMPLATES = [("book a ride for {n} people from {p} to {d}", None), ("we are {n}, need a ride from {p} to {d}", None),
                      ("{veh} for {n} people from {p} to {d}", "auto"), ("{veh} from {p} to {d} for {n} of us", "e_rickshaw")]


def gen(rng: random.Random, split: str, counts: dict[str, int], start_ride_id: int, seen: set) -> list[dict]:
    """Generate cases per category. Phrasings are unique across dev+test (`seen`), so no test case
    is a verbatim copy of a dev case or of another test case."""
    ride_counter = [start_ride_id]

    def next_ride_id():
        ride_counter[0] += 1
        return ride_counter[0]

    def book():
        now = rng.choice(NOWS)
        p, d = two_places(rng)
        ps, ptags = place_surface(rng, p)
        ds, dtags = place_surface(rng, d)
        t, tl, ttags = time_phrase(rng, now)
        pax, veh, paxs, vehs, xtags = pax_vehicle(rng)
        tpl = rng.choice(BOOK_TEMPLATES)
        if "{veh}" not in tpl and veh is not None:
            veh = None
        if "{veh}" in tpl and veh is None:
            vehs = "a ride"
        if "{pax}" not in tpl:
            pax, paxs, xtags = 1, "", []
        text = tpl.format(p=ps, d=ds, t=t, pax=paxs, veh=vehs)
        tags = ptags + dtags + ttags + xtags + (["hinglish"] if any(w in tpl for w in (" se ", "jana", "bhai", "chahiye")) else [])
        return "book", [text], now, {"action": "book_ride", "pickup": p, "dropoff": d, "passengers": pax,
                                      "vehicle_type": veh, "pickup_at": tl}, tags, None

    def quote():
        now = rng.choice(NOWS)
        p, d = two_places(rng)
        ps, ptags = place_surface(rng, p)
        ds, dtags = place_surface(rng, d)
        pax, veh, paxs, vehs, xtags = pax_vehicle(rng)
        tpl = rng.choice(QUOTE_TEMPLATES)
        vehp = {None: "rides", "e_rickshaw": "e-rickshaws", "auto": "autos", "cab": "cabs"}[veh]
        if "{veh" not in tpl:
            veh = None
        if "{veh}" in tpl and veh is None:
            vehs = "a ride"
        if "{pax}" not in tpl:
            pax, paxs, xtags = 1, "", []
        text = tpl.format(p=ps, d=ds, pax=paxs, veh=vehs, vehp=vehp)
        return "quote", [text], now, {"action": "get_quote", "pickup": p, "dropoff": d, "passengers": pax,
                                       "vehicle_type": veh}, ptags + dtags + xtags, None

    def ride_op(kind, templates):
        def build():
            now = rng.choice(NOWS)
            rid = next_ride_id()
            tpl = rng.choice(templates)
            with_id = "{id}" in tpl
            p, d = two_places(rng)
            setup = {"rides": [{"id": rid, "pickup": p, "dropoff": d, "status": "scheduled"}]}
            return kind, [tpl.format(id=rid)], now, {
                "action": "cancel_ride" if kind == "cancel" else "get_ride_status",
                "ride_id": rid if with_id else None}, ["explicit_id"] if with_id else [], setup
        return build

    def clarify():
        now = rng.choice(NOWS)
        p, d = two_places(rng)
        ps, _ = place_surface(rng, p)
        ds, _ = place_surface(rng, d)
        t, _, _ = time_phrase(rng, now)
        _, _, paxs, vehs, _ = pax_vehicle(rng)
        vehs = vehs or "a ride"
        r = rng.random()
        if r < 0.35:
            text, missing = rng.choice(MISSING_PICKUP).format(d=ds, t=t, veh=vehs, pax=paxs), ["pickup"]
        elif r < 0.65:
            text, missing = rng.choice(MISSING_DROPOFF).format(p=ps, t=t, veh=vehs), ["dropoff"]
        elif r < 0.8:
            text, missing = rng.choice(MISSING_BOTH).format(t=t), ["dropoff", "pickup"]
        else:
            tpl, field = rng.choice(AMBIGUOUS)
            text, missing = tpl.format(p=ps, d=ds, t=t), [field]
        return "clarify", [text], now, {"action": "clarify", "missing": sorted(missing)}, \
            ["ambiguous_place"] if r >= 0.8 else [], None

    def decline():
        now = rng.choice(NOWS)
        p, d = two_places(rng)
        ps, _ = place_surface(rng, p)
        ds, _ = place_surface(rng, d)
        t, _, _ = time_phrase(rng, now)
        r = rng.random()
        if r < 0.3:
            text, reason = rng.choice(OUT_OF_SCOPE), "out_of_scope"
        elif r < 0.6:
            text, reason = rng.choice(OUT_OF_AREA).format(p=ps, t=t), "out_of_area"
        elif r < 0.85:
            tpl, veh = rng.choice(CAPACITY_TEMPLATES)
            n_people = rng.randint(7, 12) if veh is None else CAPACITY[veh] + rng.randint(1, 2)
            text, reason = tpl.format(n=n_people, p=ps, d=ds, veh=rng.choice(VEH[veh]) if veh else ""), "capacity"
        else:
            alt = [a for a in (PLACES[p].name, *PLACES[p].aliases) if a.lower() != ps.lower()] or [PLACES[p].name]
            text, reason = f"book a ride from {ps} to {rng.choice(alt)}", "same_place"
        return "decline", [text], now, {"action": "decline", "reason": reason}, [reason], None

    def multiturn():
        now = rng.choice(NOWS)
        p, d = two_places(rng)
        ps, _ = place_surface(rng, p)
        ds, _ = place_surface(rng, d)
        t, tl, _ = time_phrase(rng, now)
        if rng.random() < 0.5:
            turns = [f"I need a ride from {ps} {t}", rng.choice([f"to {ds}", f"{ds}", f"going to {ds}", f"{ds} jana hai"])]
        else:
            turns = [f"book a ride to {ds} {t}", rng.choice([f"I'm at {ps}", f"from {ps}", f"{ps}", f"pick me up at {ps}"])]
        return "multiturn", turns, now, {"action": "book_ride", "pickup": p, "dropoff": d, "passengers": 1,
                                          "vehicle_type": None, "pickup_at": tl}, ["multiturn"], None

    builders = {"book": book, "quote": quote, "cancel": ride_op("cancel", CANCEL_TEMPLATES),
                "status": ride_op("status", STATUS_TEMPLATES), "clarify": clarify, "decline": decline,
                "multiturn": multiturn}
    out = []
    for cat, n_cases in counts.items():
        for _ in range(n_cases):
            for _attempt in range(500):
                category, turns, now, expected, tags, setup = builders[cat]()
                turns = [tidy(t) for t in turns]
                key = tuple(t.lower() for t in turns)
                if key not in seen:
                    seen.add(key)
                    break
            else:
                raise RuntimeError(f"could not generate a unique {cat} case")
            out.append({"id": f"{split}-{len(out) + 1:04d}", "split": split, "category": category,
                        "tags": sorted(set(tags)), "now": now.isoformat(), "turns": turns,
                        "setup": setup or {}, "expected": expected})
    return out


def _resolve_label(label: dict, now: datetime) -> dict:
    exp = dict(label)
    if "pickup_at" in exp and callable(exp["pickup_at"]):
        exp["pickup_at"] = fmt_label(exp["pickup_at"](now))
    return exp


def handwritten(split: str, start_ride_id: int, items: list[dict] = HANDWRITTEN, category: str = "handwritten",
                prefix: str = "hw") -> list[dict]:
    """Materialize hand-labeled cases. `foreign_ride` seeds a ride owned by another rider (safety slice)."""
    out = []
    items = [h for h in items if h["split"] == split]
    rid = start_ride_id
    for i, h in enumerate(items, 1):
        setup = {}
        if h.get("needs_ride"):
            rid += 1
            setup["rides"] = [{"id": h.get("ride_id", rid), "pickup": "rajendra", "dropoff": "lhc", "status": "scheduled"}]
        if h.get("foreign_ride"):
            setup["foreign_rides"] = [{"id": h["foreign_ride"], "pickup": "khosla", "dropoff": "bus_stand", "status": "scheduled"}]
        now = NOWS[h.get("now", 0)]
        case = {"id": f"{split}-{prefix}{i:03d}", "split": split, "category": category, "tags": h.get("tags", []),
                "now": now.isoformat(), "turns": h["turns"], "setup": setup, "expected": _resolve_label(h["expected"], now)}
        if h.get("also_ok"):
            case["also_ok"] = [_resolve_label(a, now) for a in h["also_ok"]]
        out.append(case)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    test_counts = {"book": 200, "quote": 45, "cancel": 35, "status": 35, "clarify": 55, "decline": 55, "multiturn": 30}
    dev_counts = {"book": 38, "quote": 9, "cancel": 7, "status": 7, "clarify": 11, "decline": 11, "multiturn": 7}
    random.seed(0)
    seen: set = set()
    dev = gen(random.Random(101), "dev", dev_counts, 10_000, seen) + handwritten("dev", 19_000)
    test = gen(random.Random(202), "test", test_counts, 20_000, seen) + handwritten("test", 29_000)
    assert len(test) == 500, len(test)
    # Separate slices, frozen before any model was run on them (see natural.py / safety.py).
    natural_dev = handwritten("dev", 18_500, NATURAL, "natural", "nat")
    natural_test = handwritten("test", 30_500, NATURAL, "natural", "nat")
    safety_dev = handwritten("dev", 18_800, SAFETY, "safety", "sec")
    safety_test = handwritten("test", 31_100, SAFETY, "safety", "sec")
    assert (len(natural_test), len(natural_dev), len(safety_test), len(safety_dev)) == (120, 30, 40, 8)
    for name, rows in (("dev", dev), ("test", test), ("natural_dev", natural_dev), ("natural_test", natural_test),
                       ("safety_dev", safety_dev), ("safety_test", safety_test)):
        with open(OUT / f"agent_eval_{name}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        cats = {}
        for r in rows:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
        print(f"{name}: {len(rows)} cases {cats}")


if __name__ == "__main__":
    main()
