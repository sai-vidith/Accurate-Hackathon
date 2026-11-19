"""Four demo stories, each with a problem that has just happened, so the demo starts from "here's what breaks".

    python seed_demo.py --reset        (uses backend/data_demo; your own data in backend/data is not touched)

Accounts (password demo1234):
    meera   family of 5 (grandparents, two kids) in Mysuru, step-free access. Heavy rain is forecast for the
            afternoon and evening of day 1: the evening fountain show at Brindavan Gardens is outdoors.
    arjun   solo, first big trip: Dandeli then Gokarna. His overnight train is running 2 1/2 hours late, so his
            booked cab to Dandeli leaves without him.
    vikram  experienced business traveller in Goa. His client workshop runs 2 hours over, squeezing the
            Basilica of Bom Jesus (closes 17:00) and the Fort Aguada sunset.
    rohit   four friends in Hampi. Vittala Temple (the stone chariot) is closed for the day.
A fifth story is live: log in as anyone and use "Plan from an idea" (see DEMO.md).

Every person, booking and business name is made up. Places and their map positions are real: coordinates were
checked against Google Maps, Wikipedia and OpenStreetMap in November 2026, and opening hours against official pages.
"""
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("COPILOT_DATA_DIR", str(Path(__file__).parent / "data_demo"))
os.environ.setdefault("COPILOT_OFFLINE", "1")   # building the demo needs no AI and no map lookups
sys.path.insert(0, str(Path(__file__).parent))
from app import db  # noqa: E402

# --reset      wipe the demo store first (data_demo folder, or the database tables if DATABASE_URL is set)
# --if-empty   do nothing when accounts already exist (used on every server start, so restarts keep real data)
data_dir = Path(os.environ["COPILOT_DATA_DIR"]).resolve()
if "--if-empty" in sys.argv:
    from app import auth as _auth
    if _auth._load():
        sys.exit("Accounts already exist: leaving the data as it is.")
elif db.enabled():
    if "--reset" not in sys.argv:
        sys.exit("DATABASE_URL is set. Run again with --reset to replace everything in that database with the demo.")
    db.q("truncate trips, users, activity")
elif data_dir.exists():
    if "--reset" not in sys.argv:
        sys.exit(f"{data_dir} already exists. Run again with --reset to rebuild it.")
    shutil.rmtree(data_dir)
(data_dir / "trips").mkdir(parents=True, exist_ok=True)

from app import auth, engine, maps, planner, store  # noqa: E402


def place(name, lat, lng, hours=None, indoor=None):
    p = {"name": name, "lat": lat, "lng": lng, "source": "demo (checked)"}
    if hours:
        p["hours_text"], p["hours"] = hours, maps._osm_hours(hours)
    if indoor is not None:
        p["indoor"] = indoor
    return p


P = {
    # Mysuru
    "mys_jn": place("Mysuru Junction", 12.3163, 76.6454),
    "mys_hotel": place("Heritage Courtyard Hotel, Mysuru", 12.3081, 76.6530),
    "palace": place("Mysore Palace", 12.3039, 76.6544, "10:00-17:30", True),
    "brindavan": place("Brindavan Gardens, KRS", 12.4261, 76.5761, "Mo-Fr 06:30-20:00; Sa,Su 06:30-21:00", False),
    "zoo": place("Mysuru Zoo", 12.3025, 76.6638, "Mo 08:30-17:30; Tu off; We-Su 08:30-17:30", False),
    "philomena": place("St. Philomena's Cathedral, Mysuru", 12.3209, 76.6584, "08:00-20:00", True),
    "chamundi": place("Chamundeshwari Temple, Chamundi Hills", 12.2725, 76.6706, "07:30-14:00,15:00-18:00,19:30-21:00", True),
    # Dandeli and Gokarna
    "sec": place("Secunderabad Junction", 17.4337, 78.5016),
    "hub": place("Hubballi Junction", 15.3496, 75.1505),
    "camp": place("Jungle Nest Camp, Dandeli", 15.2410, 74.6290),
    "kali": place("Kali river jetty, Dandeli", 15.2526, 74.6206, "08:00-17:30", indoor=False),   # water sports stop before dark
    "raft": place("Ganeshgudi rafting start point", 15.2746, 74.5398, indoor=False),
    "huts": place("Sea Breeze Huts, Kudle Beach, Gokarna", 14.5275, 74.3155),
    "om": place("Om Beach, Gokarna", 14.5196, 74.3238, indoor=False),
    # Goa
    "gox": place("Manohar International Airport, Mopa", 15.7377, 73.8694),
    "hyd_air": place("Rajiv Gandhi International Airport, Hyderabad", 17.2403, 78.4294),
    "panaji_office": place("Client office, Panaji", 15.4989, 73.8278, indoor=True),
    "panaji_hotel": place("Riverside Business Hotel, Panaji", 15.4970, 73.8290),
    "bom_jesus": place("Basilica of Bom Jesus, Old Goa", 15.5009, 73.9116, "Mo-Sa 09:00-17:00; Su 11:00-17:00", True),
    "aguada": place("Fort Aguada, Candolim", 15.4922, 73.7742, "09:30-18:00", False),
    # Hampi
    "blr": place("Bengaluru (Majestic bus stand)", 12.9777, 77.5713),
    "hospet": place("Hosapete Junction", 15.2873, 76.3856),
    "hampi_stay": place("Tungabhadra Guesthouse, Hampi Bazaar", 15.3357, 76.4620),
    "virupaksha": place("Virupaksha Temple, Hampi", 15.3352, 76.4587, "06:00-13:00,17:00-21:00", True),
    "vittala": place("Vittala Temple, Hampi", 15.3423, 76.4755, "08:30-17:30", False),
    "lotus": place("Lotus Mahal, Hampi", 15.3203, 76.4713, "08:00-18:00", False),
    "hemakuta": place("Hemakuta Hill (sunset point), Hampi", 15.3314, 76.4599, indoor=False),
}

today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
D = today + timedelta(days=2)            # every story happens the day after tomorrow, so it is never in the past
at = lambda n, hm: (D + timedelta(days=n)).strftime("%Y-%m-%d") + "T" + hm


def user(name):
    u = auth.create_user(name, "demo1234", role="admin" if name == "arjun" else "user")
    auth.REQUEST.set({"user": auth.public_user(u)})
    return u


def trip(title, dest, center, prefs, rows):
    t = store.blank_trip(title, dest)
    t["center"] = {"lat": center[0], "lng": center[1]}
    t["preferences"].update(prefs)
    t["items"] = sorted((engine.normalize_item(r) for r in rows), key=lambda i: i["start"])
    store.log(t, f"Demo trip with {len(rows)} stops.", "import")
    return store.save(t)


def item(t, title):
    return next(i for i in t["items"] if i["title"] == title)


# ---- 1. meera: family of 5 in Mysuru, rain on day 1 -----------------------------------------------------------
user("meera")
t = trip("Mysuru with grandparents and kids", "Mysuru", (12.30, 76.65),
         {"travelers": 5, "group": "family", "accessibility": True, "pace": "relaxed", "interests": ["culture", "nature", "food", "rest"]}, [
    {"type": "transport", "title": "Train Bengaluru to Mysuru", "start": at(0, "08:00"), "end": at(0, "10:15"),
     "origin": place("KSR Bengaluru City Junction", 12.9781, 77.5695), "location": P["mys_jn"],
     "booking": {"provider": "Indian Railways", "reference": "PNR 4417263"}},
    {"type": "stay", "title": "Check in at Heritage Courtyard Hotel", "start": at(0, "11:00"), "location": P["mys_hotel"],
     "booking": {"provider": "Heritage Courtyard Hotel", "reference": "HC-2291"}},
    {"type": "activity", "title": "Mysore Palace", "start": at(0, "11:45"), "end": at(0, "13:30"), "location": P["palace"], "priority": "must", "fixed": False},
    {"type": "meal", "title": "Lunch near the palace", "start": at(0, "13:45"), "end": at(0, "14:45"), "location": P["mys_hotel"], "fixed": False},
    {"type": "activity", "title": "Rest at the hotel", "start": at(0, "15:00"), "end": at(0, "16:30"), "location": P["mys_hotel"], "priority": "optional", "fixed": False},
    {"type": "activity", "title": "Brindavan Gardens musical fountain", "start": at(0, "18:00"), "end": at(0, "20:00"), "location": P["brindavan"],
     "priority": "high", "fixed": False, "indoor": False},
    {"type": "activity", "title": "Mysuru Zoo", "start": at(1, "09:00"), "end": at(1, "11:30"), "location": P["zoo"], "priority": "high", "fixed": False, "indoor": False},
    {"type": "activity", "title": "St. Philomena's Cathedral", "start": at(1, "12:00"), "end": at(1, "12:45"), "location": P["philomena"], "fixed": False},
    {"type": "meal", "title": "Lunch", "start": at(1, "13:00"), "end": at(1, "14:00"), "location": P["mys_hotel"], "fixed": False},
    {"type": "activity", "title": "Chamundeshwari Temple", "start": at(1, "15:00"), "end": at(1, "16:30"), "location": P["chamundi"], "fixed": False},
    {"type": "transport", "title": "Train Mysuru to Bengaluru", "start": at(1, "18:30"), "end": at(1, "21:00"), "origin": P["mys_jn"],
     "location": place("KSR Bengaluru City Junction", 12.9781, 77.5695), "booking": {"provider": "Indian Railways", "reference": "PNR 4417264"}},
])
d = planner.structured(t, f"Heavy rain forecast for Mysuru on {D:%A}, 3 pm to 8 pm", [], datetime.now().strftime("%Y-%m-%dT%H:%M"))
d["rain"] = {"start": at(0, "15:00"), "end": at(0, "20:00")}
planner.recompute_impact(t, d)
store.save(t)

# ---- 2. arjun: solo, Dandeli then Gokarna, train 2 1/2 hours late ------------------------------------------------
user("arjun")
t = trip("Dandeli and Gokarna on my own", "Dandeli", (15.24, 74.62),
         {"travelers": 1, "group": "solo", "pace": "moderate", "interests": ["nature", "food", "sightseeing"]}, [
    {"type": "transport", "title": "Train Secunderabad to Hubballi", "start": at(-1, "21:30"), "end": at(0, "07:30"),
     "origin": P["sec"], "location": P["hub"], "booking": {"provider": "Indian Railways", "reference": "PNR 8124531"}},
    {"type": "transport", "title": "Cab to Dandeli", "start": at(0, "08:30"), "end": at(0, "11:00"), "origin": P["hub"], "location": P["camp"],
     "booking": {"provider": "Coastal Cabs", "reference": "CC-7731"}, "fixed": False},   # a booked cab can be moved, at a cost
    {"type": "stay", "title": "Check in at Jungle Nest Camp", "start": at(0, "11:15"), "location": P["camp"],
     "booking": {"provider": "Jungle Nest Camp", "reference": "JN-1182"}},
    {"type": "activity", "title": "Kayaking on the Kali", "start": at(0, "12:00"), "end": at(0, "13:30"), "location": P["kali"], "fixed": False},
    {"type": "meal", "title": "Lunch at the camp", "start": at(0, "13:45"), "end": at(0, "14:45"), "location": P["camp"], "fixed": False},
    {"type": "activity", "title": "River rafting at Ganeshgudi", "start": at(0, "16:00"), "end": at(0, "17:30"), "location": P["raft"],
     "priority": "must", "booking": {"provider": "Ganeshgudi Rafting", "reference": "GR-405"}},
    {"type": "transport", "title": "Cab to Gokarna", "start": at(1, "08:00"), "end": at(1, "12:30"), "origin": P["camp"], "location": P["huts"],
     "booking": {"provider": "Coastal Cabs", "reference": "CC-7732"}},
    {"type": "stay", "title": "Check in at Sea Breeze Huts", "start": at(1, "13:00"), "location": P["huts"], "booking": {"provider": "Sea Breeze Huts", "reference": "SB-310"}},
    {"type": "activity", "title": "Sunset at Om Beach", "start": at(1, "17:00"), "end": at(1, "18:45"), "location": P["om"], "fixed": False, "indoor": False},
])
planner.report_delay(t, item(t, "Train Secunderabad to Hubballi")["id"], 150)
store.save(t)

# ---- 3. vikram: experienced, Goa work trip, workshop runs 2 hours over -------------------------------------------
user("vikram")
t = trip("Goa: client workshop and an evening off", "Panaji", (15.50, 73.83),
         {"travelers": 1, "group": "solo", "pace": "packed", "extra_budget": 8000, "interests": ["culture", "sightseeing", "food"]}, [
    {"type": "transport", "title": "Flight Hyderabad to Goa", "start": at(0, "06:30"), "end": at(0, "07:45"), "origin": P["hyd_air"], "location": P["gox"],
     "booking": {"provider": "SkyLark Air", "reference": "SKL4X9"}},
    {"type": "transport", "title": "Cab to Panaji", "start": at(0, "08:15"), "end": at(0, "09:30"), "origin": P["gox"], "location": P["panaji_office"],
     "booking": {"provider": "Goa Airport Taxi", "reference": "GT-118"}},
    {"type": "other", "title": "Client workshop", "start": at(0, "10:00"), "end": at(0, "13:00"), "location": P["panaji_office"], "priority": "must",
     "booking": {"provider": "Client", "reference": "Meeting"}},
    {"type": "meal", "title": "Lunch in Panaji", "start": at(0, "13:15"), "end": at(0, "14:15"), "location": P["panaji_office"], "fixed": False},
    {"type": "activity", "title": "Basilica of Bom Jesus", "start": at(0, "15:00"), "end": at(0, "16:00"), "location": P["bom_jesus"], "priority": "high", "fixed": False},
    {"type": "activity", "title": "Fort Aguada", "start": at(0, "17:15"), "end": at(0, "18:30"), "location": P["aguada"], "fixed": False, "indoor": False},
    {"type": "stay", "title": "Check in at Riverside Business Hotel", "start": at(0, "19:15"), "location": P["panaji_hotel"],
     "booking": {"provider": "Riverside Business Hotel", "reference": "RB-5520"}},
    {"type": "other", "title": "Client workshop, day 2", "start": at(1, "10:00"), "end": at(1, "13:00"), "location": P["panaji_office"], "priority": "must",
     "booking": {"provider": "Client", "reference": "Meeting"}},
    {"type": "transport", "title": "Flight Goa to Hyderabad", "start": at(1, "18:55"), "end": at(1, "20:15"), "origin": P["gox"], "location": P["hyd_air"],
     "booking": {"provider": "SkyLark Air", "reference": "SKL4Y2"}},
])
planner.report_delay(t, item(t, "Client workshop")["id"], 120, mode="overrun")
store.save(t)

# ---- 4. rohit: four friends in Hampi, Vittala Temple closed -----------------------------------------------------
user("rohit")
t = trip("Hampi with the gang", "Hampi", (15.33, 76.46),
         {"travelers": 4, "group": "friends", "pace": "packed", "interests": ["culture", "sightseeing", "nature", "food"]}, [
    {"type": "transport", "title": "Overnight bus Bengaluru to Hosapete", "start": at(-1, "22:30"), "end": at(0, "06:30"),
     "origin": P["blr"], "location": P["hospet"], "booking": {"provider": "KSRTC Airavat", "reference": "KS-99120"}},
    {"type": "transport", "title": "Auto to Hampi Bazaar", "start": at(0, "06:45"), "end": at(0, "07:15"), "origin": P["hospet"], "location": P["hampi_stay"],
     "fixed": False},
    {"type": "stay", "title": "Check in at Tungabhadra Guesthouse", "start": at(0, "07:30"), "location": P["hampi_stay"],
     "booking": {"provider": "Tungabhadra Guesthouse", "reference": "TG-77"}},
    {"type": "activity", "title": "Virupaksha Temple", "start": at(0, "08:00"), "end": at(0, "09:15"), "location": P["virupaksha"], "fixed": False},
    {"type": "meal", "title": "Breakfast in Hampi Bazaar", "start": at(0, "09:30"), "end": at(0, "10:15"), "location": P["hampi_stay"], "fixed": False},
    {"type": "activity", "title": "Vittala Temple and the stone chariot", "start": at(0, "10:45"), "end": at(0, "13:00"), "location": P["vittala"],
     "priority": "high", "fixed": False},
    {"type": "meal", "title": "Lunch by the river", "start": at(0, "13:30"), "end": at(0, "14:30"), "location": P["hampi_stay"], "fixed": False},
    {"type": "activity", "title": "Lotus Mahal and the Elephant Stables", "start": at(0, "15:30"), "end": at(0, "17:00"), "location": P["lotus"], "fixed": False},
    {"type": "activity", "title": "Sunset on Hemakuta Hill", "start": at(0, "17:45"), "end": at(0, "18:45"), "location": P["hemakuta"], "fixed": False, "indoor": False},
    {"type": "transport", "title": "Overnight bus Hosapete to Bengaluru", "start": at(1, "21:30"), "end": at(2, "05:30"), "origin": P["hospet"], "location": P["blr"],
     "booking": {"provider": "KSRTC Airavat", "reference": "KS-99121"}},
])
v = item(t, "Vittala Temple and the stone chariot")
planner.structured(t, "Vittala Temple is closed to visitors all day (a VIP visit)",
                   [{"item_id": v["id"], "kind": "closed", "note": "Closed all day for a VIP visit"}], datetime.now().strftime("%Y-%m-%dT%H:%M"))
store.save(t)

print("Demo data written to " + ("the database" if db.enabled() else str(data_dir)))
print("Accounts (password demo1234): meera (family), arjun (solo, admin), vikram (experienced), rohit (friends)")
