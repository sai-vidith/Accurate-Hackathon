# Demo guide: five stories

This is the team's submitted version with three small additions: **Plan from an idea**, four ready-made demo
stories, and a setup check. Everything else works exactly as before.

## Run it (Windows)

You need **Python 3.11+** and **Node.js 20+**.

1. Put your keys in `.env` (copy `.env.example` if it isn't there): `GROQ_API_KEY`, `GEMINI_API_KEY`, `ORS_API_KEY`.
2. Double-click **`start_demo.bat`**. The first run installs everything (a few minutes). It builds fresh demo data
   each time, because the stories are dated relative to today. `start_demo.bat keep` starts on the data as you left it.
3. Once it has run once, double-click **`check_setup.bat`**. It checks your keys, that Groq answers and can search
   the web, and places seven landmarks with the app's own map lookup, comparing each pin with a hand-checked
   position (pass if within 2 km). Fix anything marked FAIL before you present.
4. The browser opens http://localhost:5173. All demo passwords are `demo1234`.

The demo uses its own data folder (`backend/data_demo`), so your own accounts and trips in `backend/data` are untouched.
macOS/Linux: `cd backend && COPILOT_DATA_DIR=$PWD/data_demo python seed_demo.py --reset`, then `./start.sh` with the same
`COPILOT_DATA_DIR`.

## The five stories

Each account opens on a trip where something has **just gone wrong**. Open the trip, read the red banner and the
impact list, press **Find recovery plans**, approve one, and show the booking tasks.

| Log in as | Who | What just happened | What to point out |
|---|---|---|---|
| **meera** | Family of 5 in Mysuru: grandparents, two kids, step-free access, relaxed pace | Heavy rain forecast 3 pm to 8 pm on day 1; the evening fountain show at Brindavan Gardens is outdoors | Rain is checked per stop (indoor/outdoor). With internet, plans suggest nearby indoor places instead. |
| **arjun** | Solo, first big trip: Dandeli then Gokarna | His overnight train arrives 2½ hours late, so the 08:30 cab and the day after it shift | The must-do rafting is protected: the plan skips the flexible stops to keep it. |
| **vikram** | Experienced business traveller in Goa, bigger budget, packed pace | His client workshop runs 2 hours over | Opening hours matter: the Basilica closes at 17:00, so the plans move or drop what can't happen. |
| **rohit** | Four friends in Hampi | Vittala Temple (the stone chariot) is closed all day | A closed place is dropped and the rest of the day is re-timed; with internet, plans offer nearby alternatives. |
| **anyone** | Someone with no plan yet, only an idea | n/a | **Plan from an idea**: see below. |

### Plan from an idea (live, needs internet)

On the home page the first option is **Plan from an idea**. Type something vague, or press **Use an example**:

> Kerala in late December with my parents and two kids (6 of us). We'd like cool weather, tea gardens, an easy
> trek and some time by the backwaters. Starting from Thiruvananthapuram, about 4 days, mid-range hotels.

Press **Draft my plan** (up to a minute). Groq's `openai/gpt-oss-120b` searches the web for current places, opening
days, stays and ways to get there, then drafts a day-by-day plan in the same format an uploaded itinerary uses. The
timing engine checks it like any other trip. The trip page shows **Drafted from your idea**: what it assumed, where
to stay, how to get there, tips, and the pages it used. Every stay and journey becomes a task under **Bookings to sort
out**. Nothing is ever marked booked until you confirm it.

If a description has no dates (for example "Kerala, trekking, family"), the **Describe your trip** box now explains
that it reads existing plans and offers **Draft a plan from this instead**.

If web search isn't available, the draft is made from the AI's general knowledge and the page says so.

## Maps

- Demo stories use **hand-checked coordinates** (Google Maps, Wikipedia and OpenStreetMap, November 2026) and real
  opening hours, so their pins and "open when you arrive" checks don't depend on a live lookup.
- Uploaded itineraries and drafted plans are placed by the app's own lookup (OpenStreetMap), which rejects a place in
  the wrong country or one too far to reach in the time available, and marks town-centre fallbacks as *approximate*.
  `check_setup.bat` shows whether that lookup works on your machine today.
- Without `ORS_API_KEY`, travel times are estimated and the map draws straight lines between stops.

## What changed from the submitted version

| File | Change |
|---|---|
| `backend/app/ideas.py` (new) | Plan from an idea: Groq web search, then a drafted itinerary, then booking tasks |
| `backend/app/main.py` | `POST /api/trips/plan-idea` (10 per user per hour); clearer message when a description has no dates; `/api/health`; serves the built website in production |
| `backend/seed_demo.py` (new) | The four demo stories |
| `backend/check_setup.py` (new), `check_setup.bat`, `start_demo.bat` | Setup check and Windows launchers |
| `Dockerfile`, `deploy/start.sh`, `render.yaml`, `netlify.toml`, `docker-compose.yml`, `DEPLOY.md` (new) | Deployment: Netlify (website) + Render (API) + Neon (database); see DEPLOY.md |
| `backend/app/db.py` (new), `store.py`, `auth.py`, `activity.py` | Optional Postgres storage when `DATABASE_URL` is set; JSON files otherwise |
| `frontend/src/api.ts` | `VITE_API_URL` for a separately hosted API, and a clear message when the server is asleep |
| `backend/tests/test_ideas.py` (new) | Two offline tests (54 tests in total pass) |
| `frontend/src/Home.tsx`, `TripView.tsx`, `api.ts`, `types.ts` | The new tab and the "Drafted from your idea" panel |
