"""First-run data: real Yale places and resources, demo accounts, and demo reports.

- Places: geocoded from OpenStreetMap by scripts/geocode_places.py.
- Resources: phone numbers and hours copied from Yale web pages on 2026-10-22
  (source_url on every row). Yale pages sometimes disagree; the row keeps the
  number from the page cited.
- Demo reports are FICTIONAL. They are marked demo=1 and the app labels them
  "Demo report" everywhere, so nobody mistakes them for real incidents.
"""

import json
import sqlite3
from pathlib import Path

from auth import hash_password
from db import ago_iso, dumps, init_schema, now_iso

SEED_DIR = Path(__file__).resolve().parent / "data_seed"
VERIFIED = "2026-10-22"

RESOURCES = [
    # name, category, phone, display, hours, who, description, source
    ("Emergency: 911", "emergency", "911", "911", "24/7", "Anyone",
     "Immediate danger, fire, or a medical emergency. Yale College says to call 911 or Yale Police.",
     "https://college.yale.edu/life-at-yale/safety"),
    ("Yale Police Department", "emergency", "2034324400", "(203) 432-4400", "24/7", "Anyone on or near campus",
     "Yale's own police. Call for immediate danger on campus or for non-emergency police matters.",
     "https://college.yale.edu/life-at-yale/safety"),
    ("Yale Security walking escort", "escort", "2037855555", "(203) 785-5555", "24/7", "Yale students, faculty, and staff",
     "A Yale Security officer walks with you between points within the Yale footprint.",
     "https://oiss.yale.edu/node/5101"),
    ("Nighttime Safe Ride", "ride", "2034326330", "(203) 432-6330", "6 pm to 6 am, 7 days", "Yale students, faculty, and staff",
     "Door-to-door ride within campus borders at night.",
     "https://oiss.yale.edu/node/5101"),
    ("Blue emergency phones", "emergency", None, "Red button on any blue-light phone", "24/7", "Anyone",
     "More than 500 campus phones with red buttons that connect straight to police, fire, or medical help.",
     "https://college.yale.edu/life-at-yale/safety"),
    ("Yale Mental Health & Counseling", "mental_health", "2034320290", "(203) 432-0290", "Mon-Fri, 8:30 am to 5 pm", "Yale students",
     "Counseling and mental health care at Yale Health.",
     "https://college.yale.edu/life-at-yale/safety"),
    ("On-call mental health clinician", "mental_health", "2034320123", "(203) 432-0123", "After hours, weekends, and holidays", "Yale students",
     "A clinician on call when Mental Health & Counseling is closed.",
     "https://college.yale.edu/life-at-yale/safety"),
    ("988 Suicide & Crisis Lifeline", "mental_health", "988", "988 (call or text)", "24/7", "Anyone",
     "Free, confidential support for anyone in distress or crisis.",
     "https://988lifeline.org/"),
    ("Walden Peer Counseling", "mental_health", "2034328255", "(203) 432-TALK (8255)", "8 pm to 8 am on nights school is in session", "Yale undergraduates",
     "Anonymous, confidential student peer-support hotline.",
     "https://yalewell.yale.edu/walden-peer-counseling"),
    ("SHARE Center", "sexual_misconduct", "2034322000", "(203) 432-2000", "24/7 hotline", "Yale community",
     "Sexual Harassment and Assault Response & Education: confidential counselors any time, day or night.",
     "https://sharecenter.yale.edu/"),
    ("Yale Shuttle", "ride", None, "Live map in the Yale Shuttle app", "Until 1 am on weekdays", "Yale community",
     "Free campus shuttle routes.",
     "https://oiss.yale.edu/node/5101"),
    ("LiveSafe (Yale's current safety app)", "app", None, "App Store / Google Play", "24/7", "Yale community",
     "Yale's official safety app: tips to Yale PD, escort requests, and location sharing.",
     "https://your.yale.edu/campus-essentials/community-safety/campus-safety-support/livesafe-app"),
]

DEMO_USERS = [
    # netid, password, name, affiliation, unit, role, contacts, medical note
    ("hd2026", "Bulldog#2026", "Handsome Dan (demo)", "student", "Yale School of Management", "member",
     [{"name": "Roommate (demo)", "phone": "555-0101"}], ""),
    ("ycci01", "NightShift#2026", "Jordan Lee (demo)", "staff", "Yale Center for Clinical Investigation", "member",
     [{"name": "Partner (demo)", "phone": "555-0102"}, {"name": "Sister (demo)", "phone": "555-0103"}],
     "Mild asthma; carries an inhaler."),
    ("ypd001", "Dispatch#2026", "Dispatcher (demo)", "staff", "Yale Police Department (simulated console)", "dispatcher",
     [], ""),
    ("ar2027", "Elm#City2027", "Alex Rivera (demo)", "student", "Yale College", "member",
     [{"name": "Mom (demo)", "phone": "555-0104"}], ""),
]
DEMO_AUTHORS = ["hd2026", "ycci01", "ar2027"]  # demo reports rotate between these fictional members

# FICTIONAL "good news" posts: community-feed only (no map pin). (place, minutes ago, author, title, text)
DEMO_GOOD_NEWS = [
    ("Sterling Memorial Library", 70, "ycci01", "Thank you to the Yale Security officer at Sterling",
     "Huge thanks to the Yale Security officer who walked me from Sterling to my car at 1am. Took five minutes and made my week."),
    ("Payne Whitney Gym", 210, "ar2027", "Lost wallet returned at Payne Whitney",
     "Someone turned in my lost wallet at the Payne Whitney front desk with everything still inside. Thank you, whoever you are!"),
]

# FICTIONAL comments and reactions on the demo reports. (incident title starts with, author, minutes ago, text)
DEMO_COMMENTS = [
    ("Car break-ins, Temple Street", "ycci01", 120, "Saw glass on level 4 too around 8. I parked on level 2 tonight."),
    ("Car break-ins, Temple Street", "ar2027", 95, "Thanks for posting. I reported mine to Yale PD as well."),
    ("Someone trying car door handles", "hd2026", 40, "Saw someone doing the same thing near Prospect and Trumbull about ten minutes later."),
    ("Yale Security officer at the Air Rights", "ycci01", 15, "So reassuring on night shifts. Thank you!"),
    ("Peaceful march on College Street", "ar2027", 12, "Very calm, lots of signs and music. Traffic is moving slowly."),
    ("Thank you to the Yale Security officer", "hd2026", 50, "Love this. The walking escort is underrated."),
]
DEMO_REACTIONS = [  # (title starts with, netid, kind)
    ("Car break-ins, Temple Street", "ar2027", "confirm"), ("Car break-ins, Temple Street", "hd2026", "like"),
    ("Someone trying car door handles", "ycci01", "confirm"), ("Dark sidewalk near YCCI", "ar2027", "confirm"),
    ("Man following and shouting", "ycci01", "confirm"), ("Yale Security officer at the Air Rights", "hd2026", "like"),
    ("Yale Security officer at the Air Rights", "ar2027", "like"), ("Thank you to the Yale Security officer", "ar2027", "like"),
    ("Lost wallet returned", "hd2026", "like"), ("Lost wallet returned", "ycci01", "like"),
]

# FICTIONAL demo incidents. Each has its reports: (minutes ago, text).
DEMO_INCIDENTS = [
    dict(place="Temple Street Garage", category="vehicle_break_in", severity="warning",
         title="Car break-ins, Temple Street Garage (upper levels)",
         summary="Two separate reports of smashed car windows on the upper levels in the last few hours. No one was hurt and no suspect was seen.",
         advice="Keep bags and electronics out of sight. Walking to a car there at night? A Yale Security walking escort is free.",
         reports=[(185, "Car window smashed on the upper level of Temple Street Garage. Glass everywhere, didn't see anyone. Reported it to Yale PD."),
                  (140, "Second car with a broken window near the Temple St garage stairwell, upper levels. Check your car if you parked up there.")]),
    dict(place="Yale Health Center", category="suspicious_activity", severity="caution",
         title="Someone trying car door handles on Lock Street",
         summary="One report of a person trying car door handles along Lock Street, last seen heading toward Prospect Street. Gray hoodie, dark backpack.",
         advice="Lock your car and keep valuables hidden. Don't confront anyone; call Yale PD at (203) 432-4400 if you see it happening.",
         reports=[(52, "Person going car to car on Lock Street pulling on door handles, gray hoodie and dark backpack, walked off toward Prospect.")]),
    dict(place="Yale Center for Clinical Investigation (YCCI)", category="hazard", severity="info",
         title="Dark sidewalk near YCCI on Church Street South",
         summary="Two streetlights are out on the sidewalk between the parking area and the YCCI entrance.",
         advice="After dark, walk with someone or request a Yale Security walking escort.",
         reports=[(95, "Two streetlights out on Church Street South between the lot and the YCCI entrance. Really dark after 7.")]),
    dict(place="Union Station", category="police_activity", severity="caution",
         title="Police activity at the Union Station entrance",
         summary="Several police cars at the main entrance with part of the sidewalk taped off. Cause unknown.",
         advice="Use another entrance or allow extra time, and follow officers' directions.",
         reports=[(35, "Lots of police cars at the Union Station front entrance, part of the sidewalk taped off.")]),
    dict(place="New Haven Green", category="harassment", severity="warning",
         title="Man following and shouting at students near the Green bus stops",
         summary="A man followed students near the bus stops on the Green and shouted at them around 7 pm.",
         advice="Stay where other people are, and call Yale PD if someone follows you.",
         reports=[(120, "A man followed me and my friend from the bus stop on the Green yelling at us. We went into a store and he left.")]),
    dict(place="Kline Biology Tower", category="hazard", severity="info",
         title="Streetlight out on the path from Kline Tower to Ingalls Rink",
         summary="The path between Kline Biology Tower and Ingalls Rink is very dark after sunset.",
         advice="Use Prospect Street instead after dark.",
         reports=[(300, "Streetlight out on the walkway from KBT down toward Ingalls, super dark.")]),
    dict(place="Sterling Memorial Library", category="theft", severity="caution",
         title="Bike stolen outside Sterling Memorial Library",
         summary="A bike was stolen from the rack outside Sterling between 2 and 4 pm; the cable lock was cut.",
         advice="A U-lock through the frame is much harder to cut than a cable lock.",
         reports=[(360, "My bike was stolen from the rack outside Sterling between 2 and 4. Cable lock cut.")]),
    dict(place="Air Rights Garage", category="safety_update", severity="info",
         title="Yale Security officer at the Air Rights Garage stairwell",
         summary="A Yale Security officer is posted by the main stairwell tonight.",
         advice="If you're parking there late, the officer can help you get to your car.",
         reports=[(25, "There's a Yale Security officer by the Air Rights Garage stairwell tonight, nice to see.")]),
    dict(place="Old Campus (Phelps Gate)", category="gathering", severity="info",
         title="Peaceful march on College Street toward the Green",
         summary="A peaceful student march is moving along College Street toward the Green. Police are directing traffic; nothing unsafe reported.",
         advice="Expect slow traffic on College Street for about an hour.",
         reports=[(20, "Peaceful march heading down College St toward the Green, lots of people, police directing traffic. Totally calm.")]),
]


def seed(conn: sqlite3.Connection, *, reset: bool = False) -> None:
    init_schema(conn)
    if reset:
        for table in ["safety_events", "ai_runs", "chat_messages", "escort_requests", "sos_events", "walks",
                      "comments", "post_reactions", "posts", "incidents", "resources", "places", "sessions", "users"]:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    # Places are reference data: keep them in sync with places.json on every start.
    places = json.loads((SEED_DIR / "places.json").read_text(encoding="utf-8"))
    for p in places:
        conn.execute("INSERT OR REPLACE INTO places (id, name, kind, aliases_json, address, lat, lng) VALUES (?,?,?,?,?,?,?)",
                     (p["id"], p["name"], p["kind"], dumps(p["aliases"]), p["address"], p["lat"], p["lng"]))
    conn.commit()
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return  # already seeded
    by_name = {p["name"]: p for p in places}

    for r in RESOURCES:
        conn.execute("INSERT INTO resources (name, category, phone, phone_display, hours, who, description, source_url, verified_on) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", (*r[:7], r[7], VERIFIED))

    for netid, pw, name, aff, unit, role, contacts, med in DEMO_USERS:
        conn.execute("INSERT INTO users (netid, name, affiliation, unit, role, password_hash, contacts_json, medical_note, demo, created_at) "
                     "VALUES (?,?,?,?,?,?,?,?,1,?)", (netid, name, aff, unit, role, hash_password(pw), dumps(contacts), med, now_iso()))
    uid = {r[0]: r[1] for r in conn.execute("SELECT netid, id FROM users")}
    post_of: dict[str, int] = {}  # title -> first post id, for demo comments and reactions
    n = 0

    def add_post(author: str, minutes: float, category: str, text: str, place: dict, title: str, advice: str,
                 severity: str, incident_id: int | None) -> int:
        cur = conn.execute(
            "INSERT INTO posts (user_id, created_at, category, raw_text, text, place_id, lat, lng, status, "
            "moderation_json, incident_id, demo) VALUES (?,?,?,?,?,?,?,?,'published',?,?,1)",
            (uid[author], ago_iso(minutes=minutes), category, text, text, place["id"], place["lat"], place["lng"],
             dumps({"decision": "publish", "title": title, "advice": advice, "severity": severity,
                    "note": "Seeded demo report (fictional)"}), incident_id))
        post_of.setdefault(title, int(cur.lastrowid or 0))
        return int(cur.lastrowid or 0)

    for inc in DEMO_INCIDENTS:
        place = by_name[inc["place"]]
        times = [m for m, _ in inc["reports"]]
        cur = conn.execute(
            "INSERT INTO incidents (title, summary, advice, category, severity, place_id, lat, lng, report_count, "
            "first_reported, last_reported, demo) VALUES (?,?,?,?,?,?,?,?,?,?,?,1)",
            (inc["title"], inc["summary"], inc["advice"], inc["category"], inc["severity"], place["id"],
             place["lat"], place["lng"], len(times), ago_iso(minutes=max(times)), ago_iso(minutes=min(times))))
        for minutes, text in inc["reports"]:
            add_post(DEMO_AUTHORS[n % len(DEMO_AUTHORS)], minutes, inc["category"], text, place, inc["title"],
                     inc["advice"], inc["severity"], cur.lastrowid)
            n += 1
    for place_name, minutes, author, title, text in DEMO_GOOD_NEWS:
        add_post(author, minutes, "good_news", text, by_name[place_name], title, "", "info", None)

    def post_for(prefix: str) -> int:
        return next(pid for title, pid in post_of.items() if title.startswith(prefix))

    for prefix, author, minutes, text in DEMO_COMMENTS:
        conn.execute("INSERT INTO comments (post_id, user_id, created_at, raw_text, text, status, moderation_json, demo) "
                     "VALUES (?,?,?,?,?,'published',?,1)",
                     (post_for(prefix), uid[author], ago_iso(minutes=minutes), text, text,
                      dumps({"decision": "publish", "note": "Seeded demo comment (fictional)"})))
    for prefix, author, kind in DEMO_REACTIONS:
        conn.execute("INSERT OR IGNORE INTO post_reactions (post_id, user_id, kind, created_at) VALUES (?,?,?,?)",
                     (post_for(prefix), uid[author], kind, now_iso()))
    conn.commit()
