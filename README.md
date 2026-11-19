# Disruption Copilot

> **Demo:** double-click `start_demo.bat` (Windows) and see [DEMO.md](DEMO.md) for the five stories, Plan from an idea, and `check_setup.bat`. **Deploy:** see [DEPLOY.md](DEPLOY.md) (Netlify + Render + Neon Postgres).

**When plans break, recover in minutes.** An AI travel assistant for *Problem Statement 2: Smarter Travel, Better Experience*.

Add your itinerary by uploading it, describing it, or building it step by step. When something changes, tell Copilot in plain words: a delayed train, a cancelled flight, rain, a closed place, or a new commitment. It works out which stops are really affected and finds real alternatives on the map. Then it shows 2–3 recovery plans that code has checked. **Nothing changes until you approve a plan.** Bookings that still work stay as they are, and every booking change is tracked as **confirmed**, **pending** or **needs your attention**.

**Demo video (9 min):** [`Disruption_Copilot_Demo.mp4`](Disruption_Copilot_Demo.mp4). Project report: [`Disruption_Copilot_Project_Report.pdf`](Disruption_Copilot_Project_Report.pdf).

The original problem statement is in [`FINAL_PROBLEM_STATEMENT.md`](FINAL_PROBLEM_STATEMENT.md). An itinerary to try it with is in [`Gokarna_Dandeli_Trip_Itinerary.PDF`](Gokarna_Dandeli_Trip_Itinerary.PDF).

---

## Contents

1. [Quick start](#1-quick-start)
2. [Setup in detail](#2-setup-in-detail)
3. [Using the app](#3-using-the-app)
4. [Admin: activity monitor](#4-admin-activity-monitor)
5. [Running the tests](#5-running-the-tests)
6. [Troubleshooting](#6-troubleshooting)
7. [How it works](#7-how-it-works)
8. [Project structure](#8-project-structure)
9. [Data, privacy and limits](#9-data-privacy-and-limits)
10. [Team](#team)

---

## 1. Quick start

You need **Python 3.11+** and **Node.js 20+** (check with `python3 --version` and `node --version`).

```bash
cd ACCURATE_HACK
cp .env.example .env        # then open .env and paste your API keys (section 2.2)
./start.sh                  # first run installs everything; later runs start in seconds
```

Open **http://localhost:5173**, choose **Create account**, and sign in.
The **first account you create becomes the admin** unless you set an admin in `.env` (section 2.3).

Stop the app with **Ctrl+C** in the terminal; this stops both servers.

---

## 2. Setup in detail

### 2.1 What `start.sh` does

1. Checks that ports **8000** (backend) and **5173** (frontend) are free.
2. On the first run, creates a Python virtual environment in `.venv/` and installs `backend/requirements.txt`.
3. On the first run, installs the frontend packages in `frontend/node_modules/`.
4. Starts the backend at http://localhost:8000 (API docs at http://localhost:8000/docs).
5. Starts the frontend at **http://localhost:5173**.

### 2.2 API keys (`.env`)

All the services below have free tiers. Copy `.env.example` to `.env` and fill in:

| Variable | What it's for | Where to get it | If it's missing |
|---|---|---|---|
| `GROQ_API_KEY` | Main AI: reading itineraries, understanding changes, planning, chat | https://console.groq.com/keys | Gemini is used instead |
| `GEMINI_API_KEY` | Backup AI, and reading **photos/screenshots** | https://aistudio.google.com/apikey | Photo uploads are turned off |
| `ORS_API_KEY` | Nearby places, real travel times, road routes on the map | https://openrouteservice.org/dev/#/signup | Travel times are estimated from distance |

Optional settings:

| Variable | Default | Meaning |
|---|---|---|
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model to use |
| `GEMINI_MODEL` | `gemini-flash-lite-latest` | Gemini model to use |
| `LLM_PROVIDER_ORDER` | `groq,gemini` | Which AI to try first |
| `JWT_SECRET` | created automatically | Secret that signs login tokens; stored in `backend/data/.jwt_secret` if left empty |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | empty | Creates (or resets) this admin account at startup |

With **no AI key at all**, you can still build trips step by step, and changes and plans use the built-in rules. Upload and "Describe it" need an AI key.

**Restart the app after editing `.env`.** Never commit `.env`: it is already listed in `.gitignore`.

### 2.3 Accounts and the admin

- Every user signs in, and each user sees **only their own trips**.
- **Admin:** set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env` before starting. If you leave them empty, the first account created becomes the admin. The admin can open the **Activity monitor**.
- Trips created before logins existed are given to the admin, so nothing disappears.
- A login lasts 24 hours. Passwords are stored only as salted hashes, never in plain text.

### 2.4 Manual start (instead of `start.sh`)

```bash
# one time
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

# terminal 1: backend
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000

# terminal 2: frontend
cd frontend && npm run dev
```

---

## 3. Using the app

### 3.1 Create a trip

On the home page, under **Create a trip**, pick one of three options:

| Option | How to use it | Good for |
|---|---|---|
| **Upload itinerary** | Drag a file onto the box or press **Choose a file**. Accepts PDF, Word (.docx), text, PNG and JPG. | Booking confirmations and travel-agent itineraries (try the Gokarna PDF) |
| **Describe your trip** | Write or paste the trip in your own words with dates, times, places and booking references. Press **Use an example** to see the format, then **Create my trip**. | Quick tests and booking emails |
| **Build step by step** | Enter a trip name and main city, press **Start building**, then **+ Add** each stop with live place search. | Full control |

Long, multi-day PDFs are read one day at a time and can take a minute or two. Each place is located on the map. If a place can't be found exactly, it's placed at its town centre and marked **approximate**. Edit the stop to fix it.

### 3.2 Your trips

- **My trips** shows a card per trip with dates, stops and progress. Click a card to open the trip.
- The **⋯** menu on a card lets you **move** a trip between *My trips* and *Automated test trips*, or **delete** it.
- **Automated test trips** (created by test runs) are kept in a separate, collapsible section at the bottom.

### 3.3 Inside a trip

| Part | What you see and do |
|---|---|
| **Header** | Destination, travelers, interests and pace. **Edit preferences** sets interests, pace, group, travelers, step-free access and the *extra budget for changes*. |
| **At a glance** | Stops done, days, bookings confirmed, timing warnings, and tasks that need your attention. |
| **Day picker** | Jump to any day. Each day shows how many of its stops are done. |
| **Timeline** | Each stop shows its time, place, and booking status (**Confirmed / Pending / Needs attention**). Schedule warnings such as **Tight** or **Plan conflict** come with the reason. The stop you're at next is highlighted **"You are here"**. |
| **Done switch** | Tick a stop when you've done it. **Ticking a stop also marks every earlier stop done**, and unticking one also unticks the later ones. You can correct the actual finish time. Finished stops are **locked** and never rescheduled. |
| **Delay** | On any unfinished stop, press **Delay**, pick 15–90 min (or type a number), choose *runs over* or *starts late*, and press **Recalculate my day**. |
| **Edit / remove** | The pencil and bin icons on each stop. |
| **Compare with original** | Appears after a change is approved: the original plan next to the current one. |
| **Map** | All stops in order with road routes. **Open full map** opens a full-screen map in a new tab. |
| **Copilot assistant** | Chat about your trip: *"What's near my hotel?"*, *"My train is 2 hours late"*, *"Add lunch at 13:30"*. It can report changes and add stops, but approving plans is always your decision. |
| **Trip history** | A log of everything that happened to the trip. |

### 3.4 When something changes

1. Report the change in either of two ways:
   - press **Delay** on a stop (section 3.3);
   - or, under **Something changed?**, pick a category (*Train/flight delayed, Cancelled, Rain, Place closed, Running late, New commitment*) or type in your own words, then press **Check my trip**.

   You can set an **As of** time; otherwise Copilot works it out.
2. **Impact on your trip** lists only the stops that change, as *old time → new time* with the difference, plus anything that **can't happen**. Open **Detailed comparison** to see every stop with the reason.
   - Stops before the one you reported are treated as done for planning, even if you haven't ticked them.
   - Problems that already existed in your own plan are labelled *"not caused by this change"*.
3. Press **Find recovery plans**. Copilot gathers real nearby places, opening hours and travel times, then shows the plans that **passed every check**: reachable in time, open, within your budget, keeping must-dos and working bookings.
   - Each plan (**A, B, …**) shows what moves, what's shortened, added or dropped and why, with its pros and cons.
   - **Map** previews the plan on the map, and **Compare** shows *original / if nothing is done / with this plan* side by side.
   - Plans that failed a check are listed with the reason.
4. Press **Approve this plan**. Your itinerary updates, and bookings that still work stay unchanged. You can also **Dismiss** the change to keep everything as it was.
5. Under **Bookings to sort out**, follow any booking changes the plan needs:
   - **I've requested it** → **It's confirmed** (add the reference);
   - or **Couldn't do it** → **Find another plan**.

If a change is reported for a stop that's already ticked done, nothing is changed and you're told why.

### 3.5 A 5-minute demo

1. Sign in → **Describe your trip** → **Use an example** → **Create my trip**.
2. Tick **Hotel Roopa** done. The stops before it are ticked too, and a message confirms it.
3. Press **Delay** on *Mysore Palace guided tour* → **45 min** → **Recalculate my day**. Read the impact list.
4. Press **Find recovery plans** → open **Compare** on a plan → **Approve this plan**.
5. Press **Compare with original** above the timeline.
6. Ask the assistant: *"What indoor places are near my hotel?"*
7. As admin, open **Activity monitor** to see every request you just made.

For a multi-day example, upload `Gokarna_Dandeli_Trip_Itinerary.PDF` and press **Delay** on *Explore Vibhuti Falls* (day 3).

---

## 4. Admin: activity monitor

Admins see **Activity monitor** in the top bar. It refreshes live every 5 seconds (turn **Live** off to pause) and has a time window of 1 hour, 24 hours or 7 days.

| Section | Shows |
|---|---|
| **Summary tiles** | Requests, active users, error rate, server errors, response time (typical and 95th percentile), failed logins |
| **Requests over time** | Requests per hour (per day for 7 days); hover a bar for its count |
| **Request log** | Every API request: time, user, endpoint, feature, result code, time taken, and the outside services it called (AI and map services). Click a row for the full path, the error message and details such as how many stops an import produced. Filter by user, outcome (succeeded / refused / server error / slow), feature, or free-text search. |
| **Endpoints & services** | Busiest endpoints with average and worst-case time; call counts, timings and failures for Groq, Gemini, Nominatim, Photon, openrouteservice, osmnx and Open-Meteo; requests by feature and by user |
| **Users** | Each account's role, trips, requests, failures, join date, last login and last activity. Click a user to filter the log. |

The log is stored in `backend/data/activity.jsonl` (the most recent 20,000 requests).

---

## 5. Running the tests

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

The 52 tests run **offline**: no AI, no map services, and they use temporary data folders, so your trips are never touched. They cover:

- timing and impact;
- plan checking and approval;
- keeping unaffected bookings;
- booking task flow;
- rain, closures and cancellations;
- the done-cascade rules, and ignored delays on finished stops;
- delays reported mid-trip;
- itinerary import, including rejecting same-name places in the wrong town or country;
- logins, per-user trips, expired or forged tokens, and the admin monitor.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `Port 8000 (or 5173) is already in use` | An earlier run is still going. Open http://localhost:5173, or stop it: `lsof -ti tcp:8000 \| xargs kill` (same for 5173). |
| `no such file or directory: ../.venv/bin/uvicorn` | Run `./start.sh` once from the project folder, or do the "one time" steps in 2.4. |
| "Can't reach the backend" | The backend isn't running or crashed; check the terminal running `./start.sh`. |
| Sent back to the login page | Your 24-hour login expired, or the account was removed. Sign in again. |
| Upload or "Describe it" is disabled | No AI key in `.env`. Add `GROQ_API_KEY` or `GEMINI_API_KEY` and restart. |
| Photo upload doesn't work | Photos need `GEMINI_API_KEY`. |
| Upload is slow | Long itineraries are read day by day, and each place is looked up on OpenStreetMap (1 lookup per second, its usage rule). Free AI tiers may also briefly rate-limit; the app waits and retries. The Activity monitor shows where the time goes. |
| A stop is in the wrong place or "approximate" | Edit the stop (pencil icon) and pick the right place in the search box. |
| Travel times look rough | Without `ORS_API_KEY`, times are estimated from distance. Add the key for real road times. |
| I forgot the admin password | Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env` and restart: that account is reset to admin with the new password. |
| `SSL: CERTIFICATE_VERIFY_FAILED` on macOS | Already handled by the app (it uses `certifi`). If it persists, run `/Applications/Python*/Install\ Certificates.command`. |

---

## 7. How it works

**The AI suggests; the code decides.** The AI reads documents and messages and proposes plans. Deterministic code checks every plan, and facts come from OpenStreetMap-based open services, never from the AI. The checks cover:

- reachability, using real travel times plus buffers (10 min, 20 min at stations and airports);
- fixed versus flexible times and opening hours;
- hotel check-in windows;
- your budget and must-do stops;
- rain;
- never touching finished stops.

| Service / library | Used for |
|---|---|
| Groq, then Gemini (OpenAI-compatible API) | Reading itineraries, understanding changes, proposing plans, chat |
| geopy + OpenStreetMap **Nominatim** | Locating every imported place (town-anchored, rejects same-name places elsewhere) |
| **openrouteservice** | Nearby places with opening hours, travel times, road routes, road alternatives |
| **osmnx** | Extra opening hours from OpenStreetMap |
| **Photon** | Search-as-you-type place picker |
| **folium** / Leaflet | Full-screen map / in-app map |
| **Open-Meteo** | Rain forecast for outdoor stops |
| FastAPI + PyJWT | Backend API and logins |
| React + Vite + Tailwind | Frontend |

No Google services are used.

---

## 8. Project structure

```
ACCURATE_HACK/
├── start.sh                    start both servers (installs on first run)
├── .env.example                template for your API keys → copy to .env
├── README.md                   this file
├── FINAL_PROBLEM_STATEMENT.md  problem statement and workflow
├── Gokarna_Dandeli_Trip_Itinerary.PDF   example itinerary to upload
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py         API routes, login check and request logging
│   │   ├── auth.py         accounts, password hashing, JWT
│   │   ├── activity.py     activity log and admin statistics
│   │   ├── extract.py      upload/description → trip (AI) + locating places
│   │   ├── engine.py       timing simulation, impact, plan checks
│   │   ├── planner.py      change → impact → options → plans → approve → tasks
│   │   ├── maps.py         Nominatim, Photon, openrouteservice, osmnx, Open-Meteo
│   │   ├── mapping.py      road routes and the full-screen map
│   │   ├── assistant.py    Copilot chat with tools
│   │   ├── llm.py          Groq → Gemini
│   │   ├── store.py        saving trips
│   │   └── config.py, timeutil.py
│   ├── tests/              automated tests (pytest)
│   └── data/               your data (created automatically, not in git)
│       ├── trips/          one JSON file per trip
│       ├── users.json      accounts (hashed passwords)
│       └── activity.jsonl  request log
└── frontend/
    └── src/
        ├── App.tsx         top bar and page switching
        ├── Login.tsx       sign in / create account
        ├── Home.tsx        dashboard, create a trip, trip cards
        ├── TripView.tsx    trip page: header, timeline, done switches, delays
        ├── Recovery.tsx    disruption reporting, impact, plans, approval
        ├── Compare.tsx     before/after views
        ├── Tasks.tsx       booking tasks
        ├── MapView.tsx     map
        ├── Chat.tsx        Copilot assistant
        ├── Admin.tsx       activity monitor
        └── ui.tsx          shared design components and icons
```

---

## 9. Data, privacy and limits

- **Everything is stored locally** in `backend/data/`. Nothing is sent anywhere except the AI and map requests needed to answer you.
- `.env`, `backend/data/` (trips, accounts, activity log, login secret), `.venv/` and `node_modules/` are excluded from git.
- To share the project as a zip, leave out `.env`, `.venv/` and `frontend/node_modules/`. They are recreated by `cp .env.example .env` and `./start.sh`.
- **Limits of open data:**
  - There are no train or bus timetables, so a cancelled leg gets a computed road alternative, and Copilot asks for your replacement's times.
  - Opening hours are known only where OpenStreetMap has them; otherwise the app says "confirm before going".
  - The openrouteservice free tier allows about 2,000 route and 500 place requests a day, and results are cached.
- Place and map data © OpenStreetMap contributors. Weather by Open-Meteo. No Accurate Background data is used.

---

## Team

| # | Name | Roll number | Branch |
|---|---|---|---|
| 1 | Sai Sri Meghana Bondili | 23071A6709 | DS |
| 2 | Koneti Bhaskar Charan Tej | 23071A0591 | CSE |
| 3 | T. Harshavardhan | 23071A67K0 | DS |
| 4 | Sai Vidith | 23071A67F0 | DS |
| 5 | Kotaru Kshitej | 23071A1226 | IT |
| 6 | Jonnavaram Naga Bharadwaj Reddy | 23071A0584 | CSE |
| 7 | Krishna Pramoditha Kathari | 23071A05G7 | CSE |
| 8 | Mohammed Rehan Khan | 23071A6932 | IoT |
