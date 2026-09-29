"""Hand-written hard cases with hand-assigned labels: slang, context, implicit counts, indirect phrasing.

`now` indexes build_dataset.NOWS: 0 Mon 14:00 · 1 Wed 08:15 · 2 Fri 21:40 · 3 Sat 11:05 · 4 Sun 18:30
"""

from datetime import timedelta


def at(days: int, h: int, m: int = 0):
    return lambda now: (now + timedelta(days=days)).replace(hour=h, minute=m, second=0, microsecond=0)


def rel(minutes: int):
    return lambda now: (now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)


def book(p, d, t="asap", pax=1, veh=None):
    return {"action": "book_ride", "pickup": p, "dropoff": d, "passengers": pax, "vehicle_type": veh, "pickup_at": t}


def quote(p, d, pax=1, veh=None):
    return {"action": "get_quote", "pickup": p, "dropoff": d, "passengers": pax, "vehicle_type": veh}


def clarify(*missing):
    return {"action": "clarify", "missing": sorted(missing)}


def decline(reason):
    return {"action": "decline", "reason": reason}


T, D = "test", "dev"
HANDWRITTEN = [
    # ------------------------------------------------------------------ test (45)
    dict(split=T, turns=["yo, me n 2 of my wingies need to get from RKB to LHC asap"], expected=book("radhakrishnan", "lhc", pax=3), tags=["slang", "passenger_arithmetic"]),
    dict(split=T, turns=["Can I get a ride to the main gate? I'm outside the library."], expected=book("mgcl", "main_gate"), tags=["implicit_pickup"]),
    dict(split=T, turns=["My train is at 7:30pm, need to go to the station from Govind Bhawan at 6:45 pm"], expected=book("govind", "railway_station", at(0, 18, 45)), tags=["distractor_time"]),
    dict(split=T, turns=["cab chahiye RB se station ke liye, kal subah 5:30 baje, 2 log"], expected=book("rajendra", "railway_station", at(1, 5, 30), 2, "cab"), tags=["hinglish"]),
    dict(split=T, turns=["I'm at the hospital, can someone take me back to Kasturba? I'm not feeling well"], expected=book("hospital", "kasturba"), tags=["implicit_pickup"]),
    dict(split=T, turns=["How much would it be for an auto from civil lines to Rajendra Bhawan for 3 of us?"], expected=quote("civil_lines", "rajendra", 3, "auto")),
    dict(split=T, turns=["Actually, never mind, cancel that"], needs_ride=True, expected={"action": "cancel_ride", "ride_id": None}, tags=["indirect"]),
    dict(split=T, turns=["is my e-rickshaw on its way?"], needs_ride=True, expected={"action": "get_ride_status", "ride_id": None}, tags=["vehicle_distractor"]),
    dict(split=T, turns=["What is the capital of France?"], expected=decline("out_of_scope")),
    dict(split=T, turns=["Can you book me a flight to Bangalore?"], expected=decline("out_of_scope"), tags=["booking_distractor"]),
    dict(split=T, turns=["take me to sac"], expected=clarify("pickup")),
    dict(split=T, turns=["I have an interview at the main building at 10 tomorrow, pick me up from Jawahar at 9:30"], expected=book("jawahar", "main_building", at(1, 9, 30)), tags=["distractor_time"]),
    dict(split=T, turns=["from mac to sarojini, three people, in 10 min"], expected=book("mac", "sarojini", rel(10), 3), tags=["terse"]),
    dict(split=T, turns=["need a toto from swimming pool to Himalaya Bhawan"], expected=book("swimming_pool", "himalaya", veh="e_rickshaw"), tags=["vehicle_slang"]),
    dict(split=T, turns=["Book a ride from Ravindra to Ravindra Bhawan"], expected=decline("same_place")),
    dict(split=T, turns=["We're a group of 10 going from SAC to the bus stand"], expected=decline("capacity")),
    dict(split=T, turns=["Book ride from convo hall to KB at quarter past 5 in the evening"], expected=book("convocation_hall", "kasturba", at(0, 17, 15)), tags=["verbal_time"]),
    dict(split=T, turns=["i'll be at the stadium after practice, need a ride back to Rajiv Bhawan at 8"], expected=book("sports_complex", "rajiv", at(0, 20, 0)), tags=["bare_hour", "implicit_pickup"]),
    dict(split=T, turns=["ride from bus stand to IITR hospital, it's urgent"], expected=book("bus_stand", "hospital")),
    dict(split=T, turns=["how long will it take for a ride from the ECE department to Azad?"], expected=quote("ece_dept", "azad")),
    dict(split=T, turns=["Please cancel ride 29500"], needs_ride=True, ride_id=29500, expected={"action": "cancel_ride", "ride_id": 29500}),
    dict(split=T, turns=["whats the status of booking #29501"], needs_ride=True, ride_id=29501, expected={"action": "get_ride_status", "ride_id": 29501}),
    dict(split=T, turns=["book a cab from Khosla International House to the railway station on Thursday at 6 am"], expected=book("khosla", "railway_station", at(3, 6, 0), veh="cab"), tags=["weekday"]),
    dict(split=T, turns=["Need a ride"], expected=clarify("pickup", "dropoff")),
    dict(split=T, turns=["from the faculty quarters to CSE at 9:45 am tomorrow, for me and my kid"], expected=book("faculty_residences", "cse_dept", at(1, 9, 45), 2), tags=["passenger_arithmetic"]),
    dict(split=T, turns=["gimme a ride from lhc to rb in half an hr"], expected=book("lhc", "rajendra", rel(30)), tags=["slang", "relative_time"]),
    dict(split=T, turns=["Is there any cab available near Jawahar Bhawan to go to civil lines"], expected=quote("jawahar", "civil_lines", veh="cab")),
    dict(split=T, turns=["Tell me the mess timings"], expected=decline("out_of_scope")),
    dict(split=T, turns=["ok book it"], expected=clarify("pickup", "dropoff"), tags=["no_context"]),
    dict(split=T, turns=["Book a ride from SB to Delhi"], expected=decline("out_of_area")),
    dict(split=T, turns=["subah 8 baje LHC jaana hai Ganga Bhawan se, kal"], expected=book("ganga", "lhc", at(1, 8, 0)), tags=["hinglish", "word_order"]),
    dict(split=T, turns=["I need a cab for 4 people tomorrow at 7pm", "from Rajendra to the bus stand"], expected=book("rajendra", "bus_stand", at(1, 19, 0), 4, "cab"), tags=["multiturn"]),
    dict(split=T, turns=["book a ride from azad", "main building"], expected=book("azad", "main_building"), tags=["multiturn"]),
    dict(split=T, turns=["can you take me to the station?", "Govind bhawan"], expected=book("govind", "railway_station"), tags=["multiturn"]),
    dict(split=T, now=2, turns=["need to get back to Cautley from civil lines"], expected=book("civil_lines", "cautley")),
    dict(split=T, now=2, turns=["book an auto from the market to RB at 11"], expected=book("civil_lines", "rajendra", at(0, 23, 0), veh="auto"), tags=["bare_hour"]),
    dict(split=T, now=2, turns=["ride to the railway station tomorrow morning at 6 from Himalaya"], expected=book("himalaya", "railway_station", at(1, 6, 0)), tags=["word_order"]),
    dict(split=T, now=3, turns=["on Monday at 9 am from Sarojini to LHC"], expected=book("sarojini", "lhc", at(2, 9, 0)), tags=["weekday"]),
    dict(split=T, now=3, turns=["what would it cost to go from the pool to the bus stand?"], expected=quote("swimming_pool", "bus_stand")),
    dict(split=T, now=4, turns=["tonight at 10 from SAC to Rav, 2 people"], expected=book("sac", "ravindra", at(0, 22, 0), 2), tags=["verbal_time"]),
    dict(split=T, now=4, turns=["I can't see my ride, where is it?"], needs_ride=True, expected={"action": "get_ride_status", "ride_id": None}),
    dict(split=T, now=1, turns=["running late for my 9am class at LHC!! pick me up from Jawahar now"], expected=book("jawahar", "lhc"), tags=["distractor_time"]),
    dict(split=T, now=1, turns=["can you book me a ride for noon from main building to the hospital"], expected=book("main_building", "hospital", at(0, 12, 0)), tags=["verbal_time"]),
    dict(split=T, now=1, turns=["Need an e-rickshaw for 5 from mgcl to kasturba"], expected=decline("capacity")),
    dict(split=T, turns=["Book a ride from Raj bhawan to the lecture hall"], expected=clarify("pickup"), tags=["ambiguous_place"]),
    # ------------------------------------------------------------------ dev (10)
    dict(split=D, turns=["rb to lhc"], expected=book("rajendra", "lhc"), tags=["terse"]),
    dict(split=D, turns=["Me and 3 friends want to go to Civil Lines from Ganga at 7 pm"], expected=book("ganga", "civil_lines", at(0, 19, 0), 4)),
    dict(split=D, turns=["How much is a cab from main gate to the station"], expected=quote("main_gate", "railway_station", veh="cab")),
    dict(split=D, turns=["cancel"], needs_ride=True, expected={"action": "cancel_ride", "ride_id": None}),
    dict(split=D, turns=["who won the match yesterday"], expected=decline("out_of_scope")),
    dict(split=D, turns=["drop me at the hospital"], expected=clarify("pickup")),
    dict(split=D, turns=["need a ride to MGCL", "from Azad"], expected=book("azad", "mgcl"), tags=["multiturn"]),
    dict(split=D, now=2, turns=["tomorrow at 9 from KB to main building"], expected=book("kasturba", "main_building", at(1, 9, 0))),
    dict(split=D, turns=["book 3 seats in an auto from sac to mac in 15 minutes"], expected=book("sac", "mac", rel(15), 3, "auto")),
    dict(split=D, turns=["where's my driver"], needs_ride=True, expected={"action": "get_ride_status", "ride_id": None}),
]
