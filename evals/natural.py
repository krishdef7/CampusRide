"""The "natural" slice: realistic chat messages, written scenario-first by hand.

How these were made, and what they are NOT:
* Each case started from a scenario (who, from where, to where, when, how many), so the label was fixed
  before the message was written. Labels follow docs/labeling_policy.md.
* The messages are deliberately messier than the templates: requests buried in context, self-corrections
  ("RB to LHC, no wait, to the library"), chat-speak and emoji, free-form Hinglish, word-level typos,
  indirect requests, third-party rides, quote-then-book conversations.
* They were written by the developer with AI assistance. They are NOT collected from real users.
  `evals/collect/` has a scenario form for collecting real student phrasings.
* The slice was frozen before any prompt iteration and before any model was run on it. The rule-based
  baseline was not changed after this slice was written.

`now` indexes build_dataset.NOWS: 0 Mon 14:00 · 1 Wed 08:15 · 2 Fri 21:40 · 3 Sat 11:05 · 4 Sun 18:30
"""

from handwritten import at, book, clarify, decline, quote, rel

T, D = "test", "dev"


def cancel(rid=None):
    return {"action": "cancel_ride", "ride_id": rid}


def status(rid=None):
    return {"action": "get_ride_status", "ride_id": rid}


NATURAL = [
    # ------------------------------------------------------------------ test (120)
    # request buried in context
    dict(split=T, now=0, turns=["hey!! so my parents are visiting this weekend and i need to pick them up… actually first i need to get myself to the railway station from Cautley, can you book something for 5:30 pm today"], expected=book("cautley", "railway_station", at(0, 17, 30)), tags=["long_context"]),
    dict(split=T, now=1, turns=["Good morning. I have a lab viva at 10 in the ECE department and I'm still at Ravindra Bhawan. Could you please arrange a ride right now?"], expected=book("ravindra", "ece_dept"), tags=["long_context", "distractor_time"]),
    dict(split=T, now=3, turns=["ok so the plan is: me, my roommate and two of his friends are heading to civil lines for dinner tonight around 8. we'll leave from Azad. book it pls"], expected=book("azad", "civil_lines", at(0, 20, 0), 4), tags=["long_context", "passenger_arithmetic"]),
    dict(split=T, now=4, turns=["I just got off the bus at the bus stand after a 6 hour journey 😩 please send an auto to take me to Sarojini"], expected=book("bus_stand", "sarojini", veh="auto"), tags=["emoji", "implicit_pickup", "distractor_number"]),
    dict(split=T, now=0, turns=["Hi, I'm a visiting faculty member staying at Khosla International House. I need to reach the Main Building by 3:30 pm for a meeting, so please book a cab for 3:10 pm."], expected=book("khosla", "main_building", at(0, 15, 10), veh="cab"), tags=["long_context", "distractor_time"]),
    dict(split=T, now=2, turns=["it's pretty late and my cycle got a puncture near the sports complex, can someone drop me to Himalaya Bhawan"], expected=book("sports_complex", "himalaya"), tags=["long_context", "implicit_pickup"]),
    dict(split=T, now=1, turns=["Our club is doing a photoshoot at the convocation hall at 11. Three of us need to get there from Kasturba around 10:40 am."], expected=book("kasturba", "convocation_hall", at(0, 10, 40), 3), tags=["distractor_time", "passenger_arithmetic"]),
    dict(split=T, now=3, turns=["My friend is coming from Delhi and will reach the Roorkee bus stand around 4 pm. Can you book a cab from the bus stand to Govind Bhawan at 4:15 pm for 2 people?"], expected=book("bus_stand", "govind", at(0, 16, 15), 2, "cab"), tags=["distractor_place", "distractor_time"]),
    dict(split=T, now=0, turns=["so the thing is I twisted my ankle in the gym at the sports complex and can't walk properly. need to get to the hospital asap"], expected=book("sports_complex", "hospital"), tags=["long_context", "implicit_pickup"]),
    dict(split=T, now=4, turns=["Tomorrow is my end sem. I want to reach LHC by 9:30 am so book an e-rickshaw from Rajiv Bhawan at 9 am tomorrow"], expected=book("rajiv", "lhc", at(1, 9, 0), veh="e_rickshaw"), tags=["distractor_time"]),
    # self-corrections
    dict(split=T, now=0, turns=["book a ride from RB to LHC, no wait, to the library"], expected=book("rajendra", "mgcl"), tags=["correction"]),
    dict(split=T, now=1, turns=["cab from Ganga to the station at 6 pm... sorry, 6:30 pm"], expected=book("ganga", "railway_station", at(0, 18, 30), veh="cab"), tags=["correction"]),
    dict(split=T, now=3, turns=["ride from SAC to Jawahar for 2, actually make that 3 people"], expected=book("sac", "jawahar", pax=3), tags=["correction"]),
    dict(split=T, now=4, turns=["from kasturba to main gate — oops I meant sarojini to main gate"], expected=book("sarojini", "main_gate"), tags=["correction"]),
    dict(split=T, now=0, turns=["auto from MAC to Cautley at 5pm. hmm scratch the auto, any vehicle is fine"], expected=book("mac", "cautley", at(0, 17, 0)), tags=["correction"]),
    dict(split=T, now=2, turns=["tomorrow at 7 am from Azad to the bus stand. wait no, day after tomorrow"], expected=book("azad", "bus_stand", at(2, 7, 0)), tags=["correction"]),
    dict(split=T, now=1, turns=["Please book an e-rickshaw from CSE to Rajendra Bhawan in 15 minutes, actually make it 30"], expected=book("cse_dept", "rajendra", rel(30), veh="e_rickshaw"), tags=["correction", "relative_time"]),
    dict(split=T, now=3, turns=["from lhc to gb... no sorry jb"], expected=book("lhc", "jawahar"), tags=["correction", "abbrev"]),
    # chat-speak and emoji
    dict(split=T, now=0, turns=["rb ➡️ lhc asap 🙏"], expected=book("rajendra", "lhc"), tags=["emoji", "terse"]),
    dict(split=T, now=1, turns=["yo can u get me frm jawahar to mgcl rn"], expected=book("jawahar", "mgcl"), tags=["chat_speak"]),
    dict(split=T, now=4, turns=["plsss book cab gb to station 8pm 2ppl"], expected=book("govind", "railway_station", at(0, 20, 0), 2, "cab"), tags=["chat_speak", "terse"]),
    dict(split=T, now=0, turns=["ride pls. sac -> rkb. 4 ppl"], expected=book("sac", "radhakrishnan", pax=4), tags=["chat_speak", "terse"]),
    dict(split=T, now=2, turns=["bro i'm at the main gate, drop me to cautley 🙏🙏"], expected=book("main_gate", "cautley"), tags=["emoji", "implicit_pickup"]),
    dict(split=T, now=1, turns=["need 2 go 2 the hospital from sb. its urgent!!!"], expected=book("sarojini", "hospital"), tags=["chat_speak"]),
    dict(split=T, now=3, turns=["wanna go to civil lines frm rajiv at 5ish"], expected=book("rajiv", "civil_lines", at(0, 17, 0)), tags=["chat_speak", "bare_hour"]),
    dict(split=T, now=4, turns=["lhc se rb, abhi 🚨"], expected=book("lhc", "rajendra"), tags=["emoji", "hinglish", "terse"]),
    # free-form Hinglish
    dict(split=T, now=0, turns=["bhaiya Govind Bhawan se station jaana hai 6 baje, 2 log hain"], expected=book("govind", "railway_station", at(0, 18, 0), 2), tags=["hinglish", "bare_hour"]),
    dict(split=T, now=1, turns=["kal subah 7 baje bus stand pahunchna hai Azad se, cab kar do"], expected=book("azad", "bus_stand", at(1, 7, 0), veh="cab"), tags=["hinglish"]),
    dict(split=T, now=3, turns=["yaar LHC se mess tak... nahi nahi, LHC se Rajendra Bhawan tak ek auto chahiye"], expected=book("lhc", "rajendra", veh="auto"), tags=["hinglish", "correction"]),
    dict(split=T, now=4, turns=["hum 5 log hain, SAC se civil lines jaana hai, gaadi bhej do"], expected=book("sac", "civil_lines", pax=5), tags=["hinglish", "passenger_arithmetic"]),
    dict(split=T, now=2, turns=["raat ko 11 baje jawahar se main gate chhod doge?"], expected=book("jawahar", "main_gate", at(0, 23, 0)), tags=["hinglish"]),
    dict(split=T, now=0, turns=["Kasturba se library, aadhe ghante baad"], expected=book("kasturba", "mgcl", rel(30)), tags=["hinglish", "relative_time"]),
    dict(split=T, now=1, turns=["mujhe aur mere dost ko MAC se Ganga Bhawan jaana hai"], expected=book("mac", "ganga", pax=2), tags=["hinglish", "passenger_arithmetic"]),
    dict(split=T, now=3, turns=["parso shaam 6 baje RKB se bus stand, toto chahiye"], expected=book("radhakrishnan", "bus_stand", at(2, 18, 0), veh="e_rickshaw"), tags=["hinglish"]),
    dict(split=T, now=4, turns=["kitna lagega auto ka SB se station tak?"], expected=quote("sarojini", "railway_station", veh="auto"), tags=["hinglish"]),
    dict(split=T, now=0, turns=["abhi koi cab free hai kya main gate pe? LHC jaana hai"], expected=quote("main_gate", "lhc", veh="cab"), tags=["hinglish"]),
    dict(split=T, now=2, turns=["mera ride kahan hai?"], needs_ride=True, expected=status(), tags=["hinglish"]),
    dict(split=T, now=1, turns=["ride cancel kar do yaar, plan change ho gaya"], needs_ride=True, expected=cancel(), tags=["hinglish"]),
    dict(split=T, now=3, turns=["Cautley se Sports Complex, 20 min mein"], expected=book("cautley", "sports_complex", rel(20)), tags=["hinglish", "relative_time"]),
    # word-level typos
    dict(split=T, now=0, turns=["cna you boook a rdie from Ravindra Bhawan to the Main Buidling"], expected=book("ravindra", "main_building"), tags=["typo"]),
    dict(split=T, now=1, turns=["i ned a auto frm Himalya Bhawan to LHC"], expected=book("himalaya", "lhc", veh="auto"), tags=["typo"]),
    dict(split=T, now=3, turns=["pls book a ride to the raliway station from Govind Bhawan at 4 pm"], expected=book("govind", "railway_station", at(0, 16, 0)), tags=["typo"]),
    dict(split=T, now=4, turns=["tommorow mornig 8am from Ganga to CSE"], expected=book("ganga", "cse_dept", at(1, 8, 0)), tags=["typo"]),
    dict(split=T, now=0, turns=["canel my ride"], needs_ride=True, expected=cancel(), tags=["typo"]),
    dict(split=T, now=2, turns=["Whre is my cab??"], needs_ride=True, expected=status(), tags=["typo", "vehicle_distractor"]),
    dict(split=T, now=1, turns=["boook an e-riksha from Jawahar Bhawan to the libary"], expected=book("jawahar", "mgcl", veh="e_rickshaw"), tags=["typo"]),
    # indirect requests / third parties
    dict(split=T, now=1, turns=["I'm going to miss my 9 am class at LHC unless I leave Rajendra Bhawan right now"], expected=book("rajendra", "lhc"), tags=["indirect", "distractor_time"]),
    dict(split=T, now=2, turns=["Could someone come get me at Civil Lines and take me back to Rajendra Bhawan?"], expected=book("civil_lines", "rajendra"), tags=["indirect"]),
    dict(split=T, now=3, turns=["My mom is at the main gate and needs to get to Kasturba Bhawan. Can you send a ride for her?"], expected=book("main_gate", "kasturba"), tags=["indirect", "third_party"]),
    dict(split=T, now=4, turns=["Getting a ride to the bus stand from Ravindra would really help me out right now"], expected=book("ravindra", "bus_stand"), tags=["indirect"]),
    dict(split=T, now=0, turns=["I'd really rather not walk from LHC to Jawahar in this heat, can you sort something out"], expected=book("lhc", "jawahar"), tags=["indirect"]),
    # passenger arithmetic
    dict(split=T, now=0, turns=["me, my roommate and his girlfriend from Govind Bhawan to civil lines"], expected=book("govind", "civil_lines", pax=3), tags=["passenger_arithmetic"]),
    dict(split=T, now=1, turns=["the whole wing is going — it's 6 of us — from RB to the stadium"], expected=book("rajendra", "sports_complex", pax=6), tags=["passenger_arithmetic"]),
    dict(split=T, now=3, turns=["a cab for my parents and me from Khosla to the railway station at 2 pm"], expected=book("khosla", "railway_station", at(0, 14, 0), 3, "cab"), tags=["passenger_arithmetic"]),
    dict(split=T, now=4, turns=["two friends and I want an auto from SAC to Ravindra"], expected=book("sac", "ravindra", pax=3, veh="auto"), tags=["passenger_arithmetic"]),
    dict(split=T, now=2, turns=["just me, from MAC to KB"], expected=book("mac", "kasturba"), tags=["terse"]),
    dict(split=T, now=0, turns=["me + 3 juniors, ECE department to Jawahar Bhawan in 10 mins"], expected=book("ece_dept", "jawahar", rel(10), 4), tags=["passenger_arithmetic", "relative_time"]),
    dict(split=T, now=1, turns=["a couple of us (me and one friend) need to go from Sarojini to the MAC"], expected=book("sarojini", "mac", pax=2), tags=["passenger_arithmetic"]),
    # quotes
    dict(split=T, now=0, turns=["roughly what does an auto from the bus stand to Cautley cost these days?"], expected=quote("bus_stand", "cautley", veh="auto")),
    dict(split=T, now=1, turns=["how soon could a cab get me from Ganga Bhawan to the station? not booking yet"], expected=quote("ganga", "railway_station", veh="cab")),
    dict(split=T, now=3, turns=["any e-rickshaws free near the library? want to go to Rajiv"], expected=quote("mgcl", "rajiv", veh="e_rickshaw")),
    dict(split=T, now=4, turns=["fare check: RKB to civil lines, 4 people"], expected=quote("radhakrishnan", "civil_lines", 4), tags=["terse"]),
    dict(split=T, now=2, turns=["How long would it take to get from the main gate to Himalaya Bhawan right now?"], expected=quote("main_gate", "himalaya")),
    dict(split=T, now=0, turns=["before I book — what's the price from Jawahar to LHC for 2?"], expected=quote("jawahar", "lhc", 2)),
    # clarification needed
    dict(split=T, now=0, turns=["I need to go to the station"], expected=clarify("pickup")),
    dict(split=T, now=1, turns=["pick me up from Azad"], expected=clarify("dropoff")),
    dict(split=T, now=3, turns=["take me back to my hostel from LHC"], expected=clarify("dropoff"), tags=["ambiguous_place"]),
    dict(split=T, now=4, turns=["ride from the department to Ganga"], expected=clarify("pickup"), tags=["ambiguous_place"]),
    dict(split=T, now=2, turns=["can you book a ride for tomorrow morning at 8?"], expected=clarify("pickup", "dropoff")),
    dict(split=T, now=0, turns=["from girls hostel to LHC"], expected=clarify("pickup"), tags=["ambiguous_place"]),
    dict(split=T, now=1, turns=["book an auto for 3 people"], expected=clarify("pickup", "dropoff")),
    dict(split=T, now=3, turns=["I want to go to Rajendra"], expected=clarify("pickup")),
    dict(split=T, now=4, turns=["need a ride from the hostel to the lecture hall"], expected=clarify("pickup"), tags=["ambiguous_place"]),
    dict(split=T, now=2, turns=["going to the market"], expected=clarify("pickup")),
    # declines
    dict(split=T, now=0, turns=["can you book me a cab to Dehradun from Rajendra Bhawan tomorrow?"], expected=decline("out_of_area")),
    dict(split=T, now=1, turns=["Haridwar jaana hai Main Gate se, cab mil jayegi?"], expected=decline("out_of_area"), tags=["hinglish"]),
    dict(split=T, now=3, turns=["we're 8 people going from SAC to civil lines, one vehicle please"], expected=decline("capacity")),
    dict(split=T, now=4, turns=["an auto for 5 of us from LHC to Azad"], expected=decline("capacity")),
    dict(split=T, now=2, turns=["e-rick for me and 4 friends from Jawahar to main gate"], expected=decline("capacity"), tags=["passenger_arithmetic"]),
    dict(split=T, now=0, turns=["what time does the library close today?"], expected=decline("out_of_scope"), tags=["distractor_place"]),
    dict(split=T, now=1, turns=["can you order me a pizza to Rajendra Bhawan"], expected=decline("out_of_scope"), tags=["booking_distractor"]),
    dict(split=T, now=3, turns=["book me a train ticket from Roorkee station to Delhi"], expected=decline("out_of_scope"), tags=["booking_distractor"]),
    dict(split=T, now=4, turns=["from Kasturba to Kasturba Bhawan please"], expected=decline("same_place")),
    dict(split=T, now=0, turns=["help me write an email to my professor asking for an extension"], expected=decline("out_of_scope")),
    dict(split=T, now=2, turns=["who is the director of IIT Roorkee?"], expected=decline("out_of_scope")),
    dict(split=T, now=1, turns=["ride from Main Building to Rishikesh at 5 pm"], expected=decline("out_of_area")),
    # multi-turn
    dict(split=T, now=0, turns=["need a cab to the station", "from Cautley, at 7 pm"], expected=book("cautley", "railway_station", at(0, 19, 0), veh="cab"), tags=["multiturn"]),
    dict(split=T, now=1, turns=["hey can u book me a ride", "from sb to lhc"], expected=book("sarojini", "lhc"), tags=["multiturn", "chat_speak"]),
    dict(split=T, now=3, turns=["going to civil lines with 2 friends", "we're at Azad"], expected=book("azad", "civil_lines", pax=3), tags=["multiturn", "passenger_arithmetic"]),
    dict(split=T, now=4, turns=["book an auto from Jawahar", "to MGCL, in 15 min"], expected=book("jawahar", "mgcl", rel(15), veh="auto"), tags=["multiturn"]),
    dict(split=T, now=2, turns=["take me home", "Rajiv Bhawan, I'm at the SAC"], expected=book("sac", "rajiv"), tags=["multiturn", "implicit_pickup"]),
    dict(split=T, now=0, turns=["kal subah station jaana hai", "Ganga se, 6 baje"], expected=book("ganga", "railway_station", at(1, 6, 0)), tags=["multiturn", "hinglish"]),
    dict(split=T, now=1, turns=["how much for a cab from RB to the bus stand", "ok book it"], expected=book("rajendra", "bus_stand", veh="cab"), tags=["multiturn", "quote_then_book"]),
    dict(split=T, now=3, turns=["ride from LHC for 3 people", "to Govind Bhawan"], expected=book("lhc", "govind", pax=3), tags=["multiturn"]),
    # cancel / status
    dict(split=T, now=0, turns=["I don't need the ride anymore, please call it off"], needs_ride=True, expected=cancel(), tags=["indirect"]),
    dict(split=T, now=1, turns=["hey is the driver close? been waiting 10 min"], needs_ride=True, expected=status(), tags=["distractor_number"]),
    dict(split=T, now=3, turns=["cancel booking 30412 pls"], needs_ride=True, ride_id=30412, expected=cancel(30412), tags=["explicit_id"]),
    dict(split=T, now=4, turns=["any update on ride #30413?"], needs_ride=True, ride_id=30413, expected=status(30413), tags=["explicit_id"]),
    dict(split=T, now=2, turns=["my plans changed, scrap the ride I booked"], needs_ride=True, expected=cancel(), tags=["indirect"]),
    dict(split=T, now=0, turns=["how far away is my auto"], needs_ride=True, expected=status(), tags=["vehicle_distractor"]),
    dict(split=T, now=1, turns=["ride 30414 - where is it?"], needs_ride=True, ride_id=30414, expected=status(30414), tags=["explicit_id"]),
    dict(split=T, now=3, turns=["Nevermind, don't send anyone"], needs_ride=True, expected=cancel(), tags=["indirect"]),
    # bookings with natural time expressions
    dict(split=T, now=0, turns=["book a ride from Rajendra Bhawan to the LHC at quarter to 5 in the evening"], expected=book("rajendra", "lhc", at(0, 16, 45)), tags=["verbal_time"]),
    dict(split=T, now=1, turns=["at noon tomorrow, cab from Main Building to the railway station"], expected=book("main_building", "railway_station", at(1, 12, 0), veh="cab"), tags=["verbal_time", "word_order"]),
    dict(split=T, now=3, turns=["on Monday at 8:30 am I need to go from Himalaya to LHC"], expected=book("himalaya", "lhc", at(2, 8, 30)), tags=["weekday"]),
    dict(split=T, now=4, turns=["Wednesday evening 6 pm, Azad to civil lines, 3 people"], expected=book("azad", "civil_lines", at(3, 18, 0), 3), tags=["weekday", "terse"]),
    dict(split=T, now=0, turns=["in an hour from MGCL to Cautley"], expected=book("mgcl", "cautley", rel(60)), tags=["relative_time"]),
    dict(split=T, now=2, turns=["10:15 pm from SAC to KB"], expected=book("sac", "kasturba", at(0, 22, 15)), tags=["terse"]),
    dict(split=T, now=1, turns=["after lunch, around 2 pm, from CSE to the swimming pool"], expected=book("cse_dept", "swimming_pool", at(0, 14, 0))),
    dict(split=T, now=3, turns=["this evening at 7:45, Govind Bhawan to the bus stand"], expected=book("govind", "bus_stand", at(0, 19, 45)), tags=["verbal_time"]),
    dict(split=T, now=4, turns=["I need to be picked up at Sarojini at 7 sharp to go to the SAC"], expected=book("sarojini", "sac", at(0, 19, 0)), tags=["bare_hour"]),
    dict(split=T, now=0, turns=["Friday 5:30 pm, cab, Khosla to bus stand, 2 people"], expected=book("khosla", "bus_stand", at(4, 17, 30), 2, "cab"), tags=["weekday", "terse"]),
    dict(split=T, now=1, turns=["tonight at 9, ride from Jawahar to Main Gate"], expected=book("jawahar", "main_gate", at(0, 21, 0)), tags=["verbal_time"]),
    dict(split=T, now=2, turns=["tomorrow at 10:30 am pick me up from Rajiv and drop at the hospital"], expected=book("rajiv", "hospital", at(1, 10, 30))),
    dict(split=T, now=3, turns=["in 45 mins from civil lines to Ravindra"], expected=book("civil_lines", "ravindra", rel(45)), tags=["relative_time"]),
    dict(split=T, now=0, turns=["book an e-rick for 6:15 pm from Radhakrishnan to the main gate"], expected=book("radhakrishnan", "main_gate", at(0, 18, 15), veh="e_rickshaw")),
    dict(split=T, now=4, turns=["right away please, from the sports complex to Rajendra Bhawan, I have a lot of bags"], expected=book("sports_complex", "rajendra")),
    dict(split=T, now=1, turns=["at 12:30 pm from LHC to Govind Bhawan for lunch"], expected=book("lhc", "govind", at(0, 12, 30))),
    dict(split=T, now=3, turns=["can you get me a cab to the station at 3 pm from Kasturba? my train is at 4"], expected=book("kasturba", "railway_station", at(0, 15, 0), veh="cab"), tags=["distractor_time"]),
    dict(split=T, now=2, turns=["from Cautley to MAC, me and 2 others, in 5 minutes"], expected=book("cautley", "mac", rel(5), 3), tags=["passenger_arithmetic", "relative_time"]),
    # ------------------------------------------------------------------ dev (30)
    dict(split=D, now=0, turns=["hi! could you pls get me from Ganga Bhawan to the SAC, it's raining 😅"], expected=book("ganga", "sac"), tags=["emoji"]),
    dict(split=D, now=1, turns=["RB to library, no wait, to LHC"], expected=book("rajendra", "lhc"), tags=["correction"]),
    dict(split=D, now=3, turns=["bhai 3 log hain, KB se civil lines, shaam 7 baje"], expected=book("kasturba", "civil_lines", at(0, 19, 0), 3), tags=["hinglish"]),
    dict(split=D, now=4, turns=["cab from the station to Rajiv Bhawan, 2 bags and just me"], expected=book("railway_station", "rajiv", veh="cab"), tags=["distractor_number"]),
    dict(split=D, now=0, turns=["how much for an auto from Jawahar to the bus stand?"], expected=quote("jawahar", "bus_stand", veh="auto")),
    dict(split=D, now=2, turns=["cancel it, my friend is giving me a lift"], needs_ride=True, expected=cancel(), tags=["indirect"]),
    dict(split=D, now=1, turns=["is my ride coming or not??"], needs_ride=True, expected=status()),
    dict(split=D, now=3, turns=["I want to go to the hospital"], expected=clarify("pickup")),
    dict(split=D, now=4, turns=["10 of us from SAC to LHC"], expected=decline("capacity")),
    dict(split=D, now=0, turns=["book me an uber to delhi airport"], expected=decline("out_of_area")),
    dict(split=D, now=2, turns=["need a ride to Cautley", "I'm at civil lines"], expected=book("civil_lines", "cautley"), tags=["multiturn"]),
    dict(split=D, now=1, turns=["tomorrow 6:30 am, Himalaya to the railway station, cab"], expected=book("himalaya", "railway_station", at(1, 6, 30), veh="cab"), tags=["terse"]),
    dict(split=D, now=3, turns=["me and my 2 roommates from RKB to the stadium in 20 min"], expected=book("radhakrishnan", "sports_complex", rel(20), 3), tags=["passenger_arithmetic"]),
    dict(split=D, now=4, turns=["Tuesday 9 am from Azad to Main Building"], expected=book("azad", "main_building", at(2, 9, 0)), tags=["weekday"]),
    dict(split=D, now=0, turns=["whats the best biryani place in roorkee"], expected=decline("out_of_scope")),
    dict(split=D, now=1, turns=["ride from SB to the gate, actually make it an auto"], expected=book("sarojini", "main_gate", veh="auto"), tags=["correction"]),
    dict(split=D, now=2, turns=["raat 11 baje Jawahar se main gate"], expected=book("jawahar", "main_gate", at(0, 23, 0)), tags=["hinglish"]),
    dict(split=D, now=3, turns=["from my hostel to LHC"], expected=clarify("pickup"), tags=["ambiguous_place"]),
    dict(split=D, now=0, turns=["can someone pick me and my friend up at MAC and take us to Rajendra Bhawan"], expected=book("mac", "rajendra", pax=2), tags=["indirect"]),
    dict(split=D, now=4, turns=["8 pm tonight, cab from Govind to civil lines for 5"], expected=book("govind", "civil_lines", at(0, 20, 0), 5, "cab")),
    dict(split=D, now=1, turns=["any autos around the main gate right now? heading to Ravindra"], expected=quote("main_gate", "ravindra", veh="auto")),
    dict(split=D, now=3, turns=["canel booking 18601"], needs_ride=True, ride_id=18601, expected=cancel(18601), tags=["typo", "explicit_id"]),
    dict(split=D, now=2, turns=["from the pool to Kasturba, abhi"], expected=book("swimming_pool", "kasturba"), tags=["hinglish"]),
    dict(split=D, now=0, turns=["ride from convo hall to Sarojini at half past 5 in the evening"], expected=book("convocation_hall", "sarojini", at(0, 17, 30)), tags=["verbal_time"]),
    dict(split=D, now=1, turns=["4 of us + luggage, cab from Khosla to bus stand at 11 am"], expected=book("khosla", "bus_stand", at(0, 11, 0), 4, "cab"), tags=["passenger_arithmetic"]),
    dict(split=D, now=3, turns=["book a ride for 2 at 4 pm", "from Rajendra to civil lines"], expected=book("rajendra", "civil_lines", at(0, 16, 0), 2), tags=["multiturn"]),
    dict(split=D, now=4, turns=["from Ravindra to LHC... sorry, from Ravindra to MGCL"], expected=book("ravindra", "mgcl"), tags=["correction"]),
    dict(split=D, now=2, turns=["where's ride 18602?"], needs_ride=True, ride_id=18602, expected=status(18602), tags=["explicit_id"]),
    dict(split=D, now=0, turns=["send a toto to Cautley, going to the ECE department"], expected=book("cautley", "ece_dept", veh="e_rickshaw"), tags=["implicit_pickup"]),
    dict(split=D, now=1, turns=["kya aap mere liye movie ticket book kar sakte ho"], expected=decline("out_of_scope"), tags=["hinglish", "booking_distractor"]),
]
