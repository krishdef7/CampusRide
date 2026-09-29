"""Rule-based (regex + gazetteer) parser. Same output type as the agent, so evals can measure what the LLM
actually adds over a strong non-LLM baseline instead of assuming it."""

from __future__ import annotations

import re
from datetime import datetime

from campusride import campus
from campusride.agent.schema import Action
from campusride.agent.validate import to_action

_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "chhe": 6}
_NUM = r"(\d+|" + "|".join(_WORDNUM) + r")"
_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _num(s: str) -> int:
    return int(s) if s.isdigit() else _WORDNUM[s]


def _norm(text: str) -> str:
    return " " + re.sub(r"[^\w\s#]", " ", text.lower().replace("bhavan", "bhawan").replace("centre", "center")) + " "


def _find_places(t: str) -> list[tuple[int, str, str]]:
    """(position, place_id or 'OUT', surface) for every gazetteer alias in normalized text `t`, longest first."""
    found: list[tuple[int, str, str]] = []
    taken = [False] * len(t)
    keys = sorted(set(campus.ALIASES) | campus.OUT_OF_AREA, key=len, reverse=True)
    for k in keys:
        for m in re.finditer(r"(?<=\s)" + re.escape(k) + r"(?=\s)", t):
            if any(taken[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            found.append((m.start(), campus.ALIASES.get(k, "OUT"), k))
    return sorted(found)


def _when(text: str, now: datetime) -> dict:
    t = text.lower()
    if m := re.search(r"\b(?:in|after)\s+" + _NUM + r"\s*(min|mins|minutes|minute|hour|hours|hr|hrs)\b", t) or \
            re.search(_NUM + r"\s*(min|mins|minutes|ghante|ghanta)\s*(?:baad|mein|me)\b", t):
        n = _num(m.group(1))
        return {"type": "in", "minutes": n * (60 if m.group(2).startswith(("h", "g")) else 1)}
    if re.search(r"\b(?:in|after)\s+(?:half an hour|30 min)", t):
        return {"type": "in", "minutes": 30}
    if re.search(r"\bin an hour\b", t):
        return {"type": "in", "minutes": 60}
    day = 0
    if re.search(r"day after tomorrow|parso", t):
        day = 2
    elif re.search(r"\btomorrow\b|\bkal\b|\btmrw\b|\btmr\b", t):
        day = 1
    else:
        for i, d in enumerate(_DAYS):
            if re.search(rf"\b{d}\b", t):
                day = (i - now.weekday()) % 7 or 7
    m = re.search(r"\b(\d{1,2})(?::|\.)(\d{2})\s*(am|pm)?\b", t) or re.search(r"\b(\d{1,2})()\s*(am|pm|baje|o'?clock)\b", t) \
        or re.search(r"\bat\s+(\d{1,2})()()\b", t)
    if not m:
        if "noon" in t:
            return {"type": "at", "day_offset": day, "time_24h": "12:00"}
        return {"type": "asap"}
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3) or ""
    evening = re.search(r"evening|night|tonight|shaam|raat", t)
    morning = re.search(r"morning|subah", t)
    if ap == "pm" and h < 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    elif ap not in ("am", "pm") and h < 12:
        if evening:
            h += 12
        elif not morning and day == 0 and (h, mi) <= (now.hour, now.minute):
            h += 12
    if day == 0 and (h, mi) <= (now.hour, now.minute):
        day = 1
    return {"type": "at", "day_offset": day, "time_24h": f"{h:02d}:{mi:02d}"}


def _passengers(text: str) -> int:
    t = text.lower()
    if m := re.search(r"\b(?:me|myself)\s+(?:and|&|\+|aur)\s+" + _NUM + r"\s+(?:friends?|others?|more|people|log|dost)", t):
        return _num(m.group(1)) + 1
    if re.search(r"\b(?:me|myself)\s+(?:and|&|aur)\s+(?:my\s+)?(?:friend|roommate|brother|sister|mom|dad|wife|husband)\b", t):
        return 2
    if m := re.search(_NUM + r"\s+(?:of us|people|persons|passengers|pax|log|seats|students|friends)\b", t) or \
            re.search(r"\bfor\s+" + _NUM + r"\b", t) or re.search(r"\bwe(?:'re| are)\s+" + _NUM + r"\b", t):
        return _num(m.group(1))
    return 1


def _vehicle(text: str) -> str:
    t = text.lower()
    if re.search(r"e-?rick|e rickshaw|e-rickshaw|toto", t):
        return "e_rickshaw"
    if re.search(r"\bauto\b", t):
        return "auto"
    if re.search(r"\b(cab|car|taxi)\b", t):
        return "cab"
    return "any"


def parse(turns: list[str], now: datetime) -> Action:
    text = " ".join(turns)
    t = _norm(text)
    ride_no = re.search(r"(?:#|(?:ride|booking)\s*(?:no\.?|number)?\s*#?)(\d{2,})", t)
    rid = int(ride_no.group(1)) if ride_no else None
    if re.search(r"\bcancel\b|\bcancell?ed\b|don'?t need|nahi chahiye", t):
        return Action("cancel_ride", ride_id=rid)
    places = _find_places(t)
    if re.search(r"\bstatus\b|where is my|where s (?:my|ride)|kaha(?:n)? hai|how far is my|track|driver (?:coming|kab)|update on|been assigned", t) and not places:
        return Action("get_ride_status", ride_id=rid)
    ride_words = re.search(r"ride|cab|auto|rick|toto|drop|pick|book|go|jana|chalna|reach|take me|get me|need|want|taxi|car", t)
    if not places and not ride_words:
        return Action("decline", decline_reason="out_of_scope")

    pickup = dropoff = None
    for pos, _pid, surface in places:
        before = t[max(0, pos - 12):pos]
        after = t[pos + len(surface):pos + len(surface) + 8]
        if re.search(r"\bfrom\s*$|\bat\s*$|\bpick(?:up)? (?:me )?(?:from|at)?\s*$", before) or re.match(r"\s*se\b", after):
            pickup = pickup or surface
        elif re.search(r"\bto\s*$|\btill\s*$|\buntil\s*$", before) or re.match(r"\s*(?:tak|jana|jaana|chalo)\b", after):
            dropoff = dropoff or surface
    rest = [s for _, _, s in places if s not in (pickup, dropoff)]
    if pickup is None and dropoff is None and len(rest) >= 2:
        pickup, dropoff = rest[0], rest[1]
    elif pickup is None and dropoff is not None and rest:
        pickup = rest[0]
    elif dropoff is None and pickup is not None and rest:
        dropoff = rest[0]
    elif pickup is None and dropoff is None and len(rest) == 1:
        dropoff = rest[0]

    missing = tuple(f for f, v in (("pickup", pickup), ("dropoff", dropoff)) if v is None)
    if missing:
        if any(pid == "OUT" for _, pid, _ in places):
            return Action("decline", decline_reason="out_of_area")
        return Action("clarify", missing=missing)
    is_quote = re.search(r"how much|fare|price|cost|kitna|kitne|how long|eta|any .*(?:free|available)|available", t) and \
        (not re.search(r"\bbook\b", t) or re.search(r"don t book|dont book|not book", t))
    args = {"pickup": pickup, "dropoff": dropoff, "passengers": _passengers(text), "vehicle_type": _vehicle(text)}
    if is_quote:
        res = to_action("get_quote", args, now)
    else:
        res = to_action("book_ride", {**args, "when": _when(text, now)}, now)
    return res if isinstance(res, Action) else Action("clarify", missing=())
