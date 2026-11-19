# Deploying: Netlify (website) + Render (API) + Neon (database)

```
 browser ──► Netlify: the website (React build)
    │
    └─────► Render: the API (FastAPI, Docker) ──► Neon: Postgres (trips, accounts, activity log)
                     └──► Groq / Gemini / openrouteservice / OpenStreetMap
```

The website calls the Render API directly. A Netlify proxy would be simpler, but Netlify proxies time out after
26 seconds, and drafting a plan from an idea (or waking a sleeping free Render service) can take longer.

## 1. Database: Neon (free, no expiry)

1. Sign up at https://neon.tech and create a project (region: Singapore or Mumbai if offered, close to Render's region).
2. Copy the **connection string** (`postgresql://...neon.tech/neondb?sslmode=require`). That's your `DATABASE_URL`.

The app creates its tables on first start. Each trip and account is stored as one JSON document (JSONB), the same
shape the app already uses, so nothing else in the code changed. Without `DATABASE_URL` the app keeps using JSON
files, which is how it runs on your laptop.

Why not Render's own Postgres: the free one is deleted 30 days after you create it.

## 2. API: Render

1. Push this folder to a **new** GitHub repository (not your submitted one). `.env` is git-ignored, so keys stay local.
2. Render: **New > Blueprint**, pick the repo. It reads `render.yaml` and builds the `Dockerfile`.
3. Fill in when asked:
   - `GROQ_API_KEY`, `GEMINI_API_KEY`, `ORS_API_KEY`
   - `DATABASE_URL`: the Neon string from step 1
   - `ALLOWED_ORIGINS`: leave as `https://example.netlify.app` for now; you'll fix it in step 4
4. First build takes 5-10 minutes. Then open `https://<your-service>.onrender.com/api/health`: it should say `"ok": true`.

With `SEED_DEMO=1` the four demo stories are loaded **once**, when the database has no accounts. Later restarts
keep everything. To reset the demo: in Render's **Shell** tab run `python seed_demo.py --reset`.

## 3. Website: Netlify

1. Netlify: **Add new site > Import an existing project**, pick the same repo. It reads `netlify.toml`
   (builds `frontend/`, publishes `dist`).
2. **Site configuration > Environment variables**: add `VITE_API_URL` = `https://<your-service>.onrender.com`
   (no trailing slash). Then **Deploys > Trigger deploy**, because the address is built into the site.

## 4. Connect them

In Render, set `ALLOWED_ORIGINS` to your Netlify address, e.g. `https://disruption-copilot.netlify.app`. To also allow
Netlify deploy previews, add a pattern: `https://disruption-copilot.netlify.app,https://*--disruption-copilot.netlify.app`.
Render restarts by itself. Open the Netlify site and log in as `arjun` / `demo1234`.

If the site says it can't reach the server, the API is asleep (free plan): wait a minute and try again. Open the
site 2 minutes before you present.

## Settings (Render)

| Variable | Needed | What it does |
|---|---|---|
| `GROQ_API_KEY` | yes | Main AI, and the web search behind *Plan from an idea* |
| `GEMINI_API_KEY` | recommended | Backup AI, and reading photos of itineraries |
| `ORS_API_KEY` | recommended | Real road times, road routes on the map, nearby places for recovery plans |
| `DATABASE_URL` | yes on Render | Neon Postgres. Without it, data is lost whenever the free service restarts |
| `ALLOWED_ORIGINS` | yes with Netlify | The website's address(es); `*` allowed inside a pattern |
| `JWT_SECRET` | generated | Signs logins (if unset, one is created and kept in the database) |
| `SEED_DEMO` | optional | `1` = load the demo stories when the database has no accounts |
| `IDEA_LIMIT_PER_HOUR` | optional | Drafts per user per hour (default 10), so a public link can't run up your AI bill |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | optional | Create an admin account on start |

Netlify needs only `VITE_API_URL`.

## Other ways to run it

- **One server, no Netlify:** the Render service also serves the website itself at its own address, so the Render
  URL alone is a complete app.
- **Any Docker host:** `docker compose up --build -d` (reads `.env`; add `DATABASE_URL` there or keep the file storage
  in the `copilot-data` volume).

## Before you share the link

- The demo accounts use a public password (`demo1234`). Fine for judges; for real users set `SEED_DEMO=0` and reset.
- **Regenerate your API keys** if they were ever pasted anywhere (chat, screenshots, commits), then update them in Render.
- One API process on purpose (in-memory caches and locks). It is safe with the database, but for several API servers,
  move the per-user rate limit and caches to shared storage first.
- OpenStreetMap's free place lookup allows about one request per second: fine for a demo, not for heavy traffic.

## Tested before handing over

- File storage and Postgres (PostgreSQL 16): 55 tests, including one that runs the whole store against Postgres
  (set `TEST_DATABASE_URL` to run it).
- Production start script with Postgres: demo loads once, an approved plan survives a restart, no files are written.
- Website and API on different addresses: login, recovery plans, page refresh; CORS allows only the listed sites.
- Not tested here: the actual Render, Netlify and Neon accounts (no access from this workspace). Check the first
  Render build log and `/api/health`.
