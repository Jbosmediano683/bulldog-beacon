"""One-off: geocode the Yale places Beacon knows about with OpenStreetMap Nominatim.

Writes backend/data_seed/places.json (committed), so the app itself never calls a
geocoder. Nominatim's policy is 1 request per second with a real User-Agent.
Map data (c) OpenStreetMap contributors, ODbL.

Run from the repo root:  python scripts/geocode_places.py
"""

import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "backend" / "data_seed" / "places.json"

# (name, kind, aliases, query)
PLACES = [
    ("Evans Hall (Yale SOM)", "building", ["evans", "som", "school of management"], "165 Whitney Avenue, New Haven, CT"),
    ("Sterling Memorial Library", "building", ["sterling", "sml", "library"], "120 High Street, New Haven, CT"),
    ("Old Campus (Phelps Gate)", "building", ["old campus", "phelps gate"], "344 College Street, New Haven, CT"),
    ("Schwarzman Center", "building", ["schwarzman", "commons"], "168 Grove Street, New Haven, CT"),
    ("Yale Center for Clinical Investigation (YCCI)", "building", ["ycci", "clinical investigation", "church street south"], "2 Church Street South, New Haven, CT"),
    ("Yale New Haven Hospital", "medical", ["ynhh", "hospital", "york street hospital"], "20 York Street, New Haven, CT"),
    ("Sterling Hall of Medicine", "building", ["shm", "medical school", "school of medicine", "cedar street"], "333 Cedar Street, New Haven, CT"),
    ("Yale Health Center", "medical", ["yale health", "lock street", "health center"], "55 Lock Street, New Haven, CT"),
    ("Yale Police Department", "safety", ["ypd", "yale police", "ashmun"], "101 Ashmun Street, New Haven, CT"),
    ("Union Station", "transit", ["train station", "union station", "metro-north", "amtrak"], "50 Union Avenue, New Haven, CT"),
    ("Air Rights Garage", "parking", ["air rights", "york street garage"], "Air Rights Garage, New Haven, CT"),
    ("Temple Street Garage", "parking", ["temple garage", "temple street"], "Temple Street Garage, New Haven, CT"),
    ("Crown Street Garage", "parking", ["crown garage", "crown street"], "Crown Street Garage, New Haven, CT"),
    ("Pierson-Sage Garage", "parking", ["pierson sage", "science hill garage"], "Pierson-Sage Garage, New Haven, CT"),
    ("Payne Whitney Gym", "building", ["pwg", "gym", "payne whitney"], "70 Tower Parkway, New Haven, CT"),
    ("Kline Biology Tower", "building", ["kbt", "kline", "science hill"], "219 Prospect Street, New Haven, CT"),
    ("Yale Law School", "building", ["law school", "sterling law", "wall street"], "127 Wall Street, New Haven, CT"),
    ("Hall of Graduate Studies", "building", ["hgs", "graduate school"], "320 York Street, New Haven, CT"),
    ("Yale University Art Gallery", "building", ["art gallery", "yuag", "chapel street gallery"], "1111 Chapel Street, New Haven, CT"),
    ("Yale Bookstore (Broadway)", "building", ["broadway", "bookstore", "barnes and noble"], "77 Broadway, New Haven, CT"),
    ("Ingalls Rink", "building", ["ingalls", "the whale", "hockey rink"], "73 Sachem Street, New Haven, CT"),
    ("Grove Street Cemetery", "landmark", ["grove street", "cemetery"], "227 Grove Street, New Haven, CT"),
    ("New Haven Green", "landmark", ["the green", "green", "church street"], "New Haven Green, New Haven, CT"),
    ("Shubert Theatre", "landmark", ["shubert", "college street theatre"], "247 College Street, New Haven, CT"),
    ("Yale Divinity School", "building", ["divinity", "yds", "prospect street"], "409 Prospect Street, New Haven, CT"),
    ("Chapel St & York St", "intersection", ["chapel and york", "chapel york"], "Chapel Street & York Street, New Haven, CT"),
]

# Rough box around New Haven; anything outside it is a bad match.
LAT, LNG = (41.28, 41.34), (-72.96, -72.89)


def main() -> None:
    out, missing = [], []
    with httpx.Client(headers={"User-Agent": "BulldogBeacon-class-project/1.0 (Yale MGT 409)"}, timeout=20) as client:
        for i, (name, kind, aliases, query) in enumerate(PLACES, start=1):
            resp = client.get("https://nominatim.openstreetmap.org/search",
                              params={"q": query, "format": "json", "limit": 1})
            hits = resp.json() if resp.status_code == 200 else []
            time.sleep(1.1)
            if not hits:
                missing.append(name)
                continue
            lat, lng = float(hits[0]["lat"]), float(hits[0]["lon"])
            if not (LAT[0] <= lat <= LAT[1] and LNG[0] <= lng <= LNG[1]):
                missing.append(f"{name} (outside New Haven: {lat}, {lng})")
                continue
            out.append({"id": i, "name": name, "kind": kind, "aliases": aliases, "address": query,
                        "lat": round(lat, 6), "lng": round(lng, 6), "osm_match": hits[0]["display_name"]})
            print(f"ok  {name:48s} {lat:.5f}, {lng:.5f}  <- {hits[0]['display_name'][:70]}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwrote {len(out)} places to {OUT}")
    for m in missing:
        print("MISSING:", m)


if __name__ == "__main__":
    main()
