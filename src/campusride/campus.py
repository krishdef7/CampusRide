"""Campus gazetteer: named places, zones and deterministic place-name resolution.

The LLM never invents coordinates or place IDs. It passes the user's words through
(e.g. "RB", "rajendra bhavan", "the library") and `resolve_place` maps them onto the
gazetteer, or reports that the mention is unknown, ambiguous or outside the service area.

Coordinates are approximate, hand-placed positions on the IIT Roorkee campus.
`scripts/geocode_places.py` can refine them with the Google Geocoding API.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Literal

from rapidfuzz import fuzz, process


@dataclass(frozen=True)
class Zone:
    id: str
    name: str


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    lat: float
    lon: float
    zone: str
    kind: str
    aliases: tuple[str, ...] = field(default=())


ZONES: dict[str, Zone] = {
    z.id: z
    for z in [
        Zone("acad", "Academic core"),
        Zone("activity", "SAC / sports"),
        Zone("hostels_w", "West hostels"),
        Zone("hostels_e", "East hostels"),
        Zone("hostels_g", "Girls' hostels"),
        Zone("hospital", "Hospital & residences"),
        Zone("gate", "Main gate"),
        Zone("station", "Railway station"),
        Zone("town", "Civil Lines / bus stand"),
    ]
}

PLACES: dict[str, Place] = {
    p.id: p
    for p in [
        # Academic core
        Place("main_building", "Main Building", 29.8649, 77.8966, "acad", "academic", ("mb", "main bldg", "admin building")),
        Place("lhc", "Lecture Hall Complex", 29.8661, 77.8941, "acad", "academic", ("lhc", "lecture hall", "lecture halls", "lecture hall complex")),
        Place("mgcl", "Mahatma Gandhi Central Library", 29.8656, 77.8953, "acad", "academic", ("library", "central library", "mgcl", "lib")),
        Place("cse_dept", "Computer Science Department", 29.8641, 77.8948, "acad", "academic", ("cse", "cse department", "cs dept", "computer science")),
        Place("ece_dept", "Electronics Department", 29.8637, 77.8958, "acad", "academic", ("ece", "ece department", "electronics dept")),
        Place("convocation_hall", "Convocation Hall", 29.8644, 77.8984, "acad", "academic", ("convo hall", "convocation", "convo")),
        # Activity / sports
        Place("sac", "Student Activity Centre", 29.8629, 77.8976, "activity", "activity", ("sac", "student activity center", "activity centre")),
        Place("mac", "Multi Activity Centre", 29.8616, 77.8990, "activity", "activity", ("mac", "multi activity center")),
        Place("sports_complex", "Sports Complex", 29.8624, 77.8929, "activity", "sports", ("stadium", "sports ground", "sports complex", "ground")),
        Place("swimming_pool", "Swimming Pool", 29.8617, 77.8942, "activity", "sports", ("pool", "swimming pool")),
        # West hostels
        Place("rajendra", "Rajendra Bhawan", 29.8698, 77.8948, "hostels_w", "hostel", ("rb", "rjb", "rajendra", "rajendra bhawan")),
        Place("govind", "Govind Bhawan", 29.8690, 77.8921, "hostels_w", "hostel", ("gb", "govind", "govind bhawan")),
        Place("cautley", "Cautley Bhawan", 29.8714, 77.8934, "hostels_w", "hostel", ("cautley", "cautley bhawan")),
        Place("jawahar", "Jawahar Bhawan", 29.8678, 77.8914, "hostels_w", "hostel", ("jb", "jawahar", "jawahar bhawan")),
        # East hostels
        Place("ravindra", "Ravindra Bhawan", 29.8705, 77.8971, "hostels_e", "hostel", ("rav", "ravindra", "ravindra bhawan")),
        Place("radhakrishnan", "Radhakrishnan Bhawan", 29.8700, 77.8991, "hostels_e", "hostel", ("rkb", "radhakrishnan", "radhakrishnan bhawan")),
        Place("azad", "Azad Bhawan", 29.8686, 77.9010, "hostels_e", "hostel", ("azad", "azad bhawan")),
        Place("ganga", "Ganga Bhawan", 29.8725, 77.8960, "hostels_e", "hostel", ("ganga", "ganga bhawan")),
        Place("rajiv", "Rajiv Bhawan", 29.8729, 77.8986, "hostels_e", "hostel", ("rajiv", "rajiv bhawan")),
        Place("khosla", "Khosla International House", 29.8712, 77.9004, "hostels_e", "hostel", ("khosla", "khosla house", "international house")),
        # Girls' hostels
        Place("kasturba", "Kasturba Bhawan", 29.8620, 77.9011, "hostels_g", "hostel", ("kb", "kasturba", "kasturba bhawan")),
        Place("sarojini", "Sarojini Bhawan", 29.8609, 77.9025, "hostels_g", "hostel", ("sb", "sarojini", "sarojini bhawan")),
        Place("himalaya", "Himalaya Bhawan", 29.8599, 77.9001, "hostels_g", "hostel", ("hb", "himalaya", "himalaya bhawan")),
        # Hospital & residences
        Place("hospital", "IITR Hospital", 29.8680, 77.8996, "hospital", "medical", ("hospital", "iitr hospital", "health centre", "health center", "medical centre")),
        Place("faculty_residences", "Faculty Residences", 29.8668, 77.9024, "hospital", "residential", ("faculty quarters", "faculty residences", "residences")),
        # Gate
        Place("main_gate", "Main Gate", 29.8634, 77.8903, "gate", "gate", ("main gate", "gate", "front gate", "iitr gate")),
        # Off campus
        Place("railway_station", "Roorkee Railway Station", 29.8722, 77.8856, "station", "transit", ("railway station", "station", "rly station", "roorkee station", "train station")),
        Place("bus_stand", "Roorkee Bus Stand", 29.8611, 77.8858, "town", "transit", ("bus stand", "bus station", "bus stop", "isbt", "roorkee bus stand")),
        Place("civil_lines", "Civil Lines Market", 29.8662, 77.8866, "town", "market", ("civil lines", "market", "civil lines market")),
    ]
}

# Generic words that name a *class* of places. On their own they are ambiguous.
AMBIGUOUS_TERMS: dict[str, tuple[str, ...]] = {
    "hostel": tuple(p.id for p in PLACES.values() if p.kind == "hostel"),
    "bhawan": tuple(p.id for p in PLACES.values() if p.kind == "hostel"),
    "my hostel": tuple(p.id for p in PLACES.values() if p.kind == "hostel"),
    "girls hostel": tuple(p.id for p in PLACES.values() if p.zone == "hostels_g"),
    "department": ("cse_dept", "ece_dept"),
    "dept": ("cse_dept", "ece_dept"),
    "activity center": ("sac", "mac"),
}

# Destinations people ask for that we deliberately don't serve.
OUT_OF_AREA = {
    "delhi", "new delhi", "dehradun", "haridwar", "rishikesh", "saharanpur", "meerut", "muzaffarnagar",
    "airport", "delhi airport", "jolly grant", "jolly grant airport", "chandigarh", "noida", "gurgaon",
    "mussoorie", "igi airport",
}

_FILLER = re.compile(
    r"\b(the|near|outside|opposite|in front of|front of|infront of|behind|at|from|to|se|tak|ke paas|wala|wali|please|pls)\b"
)
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    t = text.lower().strip()
    t = t.replace("bhavan", "bhawan").replace("centre", "center").replace("'", "")
    t = re.sub(r"[^\w\s]", " ", t)
    t = _FILLER.sub(" ", t)
    return _SPACES.sub(" ", t).strip()


def _build_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for p in PLACES.values():
        for a in (p.name, p.id.replace("_", " "), *p.aliases):
            key = normalize(a)
            if key in index and index[key] != p.id:
                raise ValueError(f"alias {a!r} maps to both {index[key]} and {p.id}")
            index[key] = p.id
    return index


ALIASES: dict[str, str] = _build_alias_index()
_FUZZY_KEYS = [k for k in ALIASES if len(k) >= 4]  # fuzzy-matching 2-letter codes causes false hits


@dataclass(frozen=True)
class Resolution:
    status: Literal["ok", "ambiguous", "unknown", "out_of_area"]
    place_id: str | None = None
    candidates: tuple[str, ...] = ()
    query: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def resolve_place(mention: str) -> Resolution:
    q = normalize(mention)
    if not q:
        return Resolution("unknown", query=mention)
    # Strip a trailing/leading "hostel"/"bhawan" when the rest is a hostel name, e.g. "rajendra hostel".
    candidates_q = [q, re.sub(r"\b(hostel|bhawan)\b", "", q).strip(), q.removesuffix(" hostel") + " bhawan"]
    for cq in candidates_q:
        if cq in ALIASES:
            return Resolution("ok", ALIASES[cq], query=mention)
    if q in OUT_OF_AREA or any(q.endswith(" " + o) or q.startswith(o + " ") for o in OUT_OF_AREA):
        return Resolution("out_of_area", query=mention)
    if q in AMBIGUOUS_TERMS:
        return Resolution("ambiguous", candidates=AMBIGUOUS_TERMS[q], query=mention)

    # A truncated name that prefixes several places ("raj bhawan": Rajendra or Rajiv?) is ambiguous.
    head = q.split()[0]
    if len(head) >= 3:
        prefixed = tuple(dict.fromkeys(
            p.id for p in PLACES.values() for tok in [normalize(p.name).split()[0]] if tok != head and tok.startswith(head)
        ))
        if len(prefixed) >= 2:
            return Resolution("ambiguous", candidates=prefixed, query=mention)

    # Plain edit-distance similarity: tolerates a typo or two without partial-substring false hits.
    matches = process.extract(q, _FUZZY_KEYS, scorer=fuzz.ratio, limit=5, score_cutoff=85)
    if not matches:
        return Resolution("unknown", query=mention)
    best_score = matches[0][1]
    top_ids = list(dict.fromkeys(ALIASES[m[0]] for m in matches if m[1] >= best_score - 3))
    if len(top_ids) == 1:
        return Resolution("ok", top_ids[0], query=mention)
    return Resolution("ambiguous", candidates=tuple(top_ids), query=mention)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def place_distance_m(a: str, b: str) -> float:
    pa, pb = PLACES[a], PLACES[b]
    return haversine_m(pa.lat, pa.lon, pb.lat, pb.lon)


# Road distance is longer than the straight line; 1.3 is a common urban detour factor.
DETOUR_FACTOR = 1.3
SPEED_MPS = {"e_rickshaw": 15 / 3.6, "auto": 20 / 3.6, "cab": 22 / 3.6}
CAPACITY = {"e_rickshaw": 4, "auto": 3, "cab": 6}
MAX_PASSENGERS = max(CAPACITY.values())
BASE_FARE = {"e_rickshaw": 20.0, "auto": 30.0, "cab": 60.0}
PER_KM = {"e_rickshaw": 10.0, "auto": 14.0, "cab": 22.0}


def eta_seconds(distance_m: float, vehicle_type: str = "e_rickshaw") -> float:
    return distance_m * DETOUR_FACTOR / SPEED_MPS[vehicle_type]


def fare_inr(distance_m: float, vehicle_type: str) -> float:
    return round(BASE_FARE[vehicle_type] + PER_KM[vehicle_type] * distance_m * DETOUR_FACTOR / 1000, 0)


def zone_of(place_id: str) -> str:
    return PLACES[place_id].zone


def zone_centroid(zone_id: str) -> tuple[float, float]:
    ps = [p for p in PLACES.values() if p.zone == zone_id]
    return sum(p.lat for p in ps) / len(ps), sum(p.lon for p in ps) / len(ps)
