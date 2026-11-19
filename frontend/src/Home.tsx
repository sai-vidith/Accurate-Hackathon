import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { User } from "./auth";
import type { Status, TripSummary } from "./types";
import { Btn, Cover, Icon, Notice, Pill, Spinner, day, inputCls, toast, type IconName } from "./ui";

const EXAMPLE = `20 Nov 2026, Mysuru.
Train 12007 Shatabdi from Chennai Central 06:00, arrives Mysuru Junction 10:00 (PNR 4521).
Hotel Roopa, Mysuru, check-in 14:00.
Mysore Palace guided tour 12:30–15:30, booked with Heritage Walks (ref HW-55).
Walk around Devaraja Market 16:00–17:00.
Dinner at Hotel RRR 19:00, table reserved.`;

const IDEA_EXAMPLE = `Kerala in late December with my parents and two kids (6 of us).
We'd like cool weather, tea gardens, an easy trek and some time by the backwaters.
Starting from Thiruvananthapuram, about 4 days, mid-range hotels.`;

type Mode = "idea" | "upload" | "describe" | "build";
const MODES: { key: Mode; icon: IconName; title: string; sub: string }[] = [
  { key: "idea", icon: "sparkle", title: "Plan from an idea", sub: "No plan yet? Tell us roughly what you want" },
  { key: "upload", icon: "upload", title: "Upload itinerary", sub: "PDF, Word, text or a photo" },
  { key: "describe", icon: "pencil", title: "Describe your trip", sub: "Write or paste it in your own words" },
  { key: "build", icon: "compass", title: "Build step by step", sub: "Add stops one at a time" },
];

const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };

function TripCard({ t, test, open, refresh, i }: { t: TripSummary; test: boolean; open: (id: string) => void; refresh: () => void; i: number }) {
  const [menu, setMenu] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setMenu(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [menu]);
  const pct = t.items ? Math.round((100 * (t.done ?? 0)) / t.items) : 0;
  const dates = t.from ? `${day(t.from)}${t.to && t.to !== t.from ? ` – ${day(t.to)}` : ""}` : "No dates yet";

  if (test) {
    return (
      <div ref={box} className={`group relative flex items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-white/70 px-3 py-2.5 transition hover:border-slate-400 hover:bg-white ${menu ? "z-20" : ""}`}>
        <button className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={() => open(t.id)}>
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-500"><Icon name="layers" /></span>
          <span className="min-w-0"><span className="block truncate text-sm font-medium text-slate-800">{t.title}</span>
            <span className="block text-xs text-slate-500">{t.items} items · {dates}</span></span>
        </button>
        <Menu t={t} test menu={menu} setMenu={setMenu} refresh={refresh} />
      </div>
    );
  }
  return (
    <div ref={box} style={{ animationDelay: `${i * 50}ms` }}
      className={`group relative animate-fade-up overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition duration-200 hover:-translate-y-1 hover:shadow-xl hover:shadow-slate-200/80 ${menu ? "z-20 overflow-visible" : ""}`}>
      <button className="block w-full text-left" onClick={() => open(t.id)}>
        <div className="relative h-24 overflow-hidden rounded-t-2xl">
          <Cover seed={t.title + t.id} className="h-full w-full transition duration-500 group-hover:scale-105" />
          <span className="absolute bottom-2.5 left-3 inline-flex items-center gap-1 rounded-full bg-white/90 px-2 py-0.5 text-[11px] font-semibold text-slate-700 backdrop-blur">
            <Icon name="pin" className="h-3 w-3 text-teal-600" />{t.destination || "No destination"}
          </span>
        </div>
        <div className="p-4">
          <div className="truncate pr-6 font-semibold text-slate-900">{t.title}</div>
          <div className="mt-1 flex items-center gap-1.5 text-xs text-slate-500"><Icon name="calendar" className="h-3.5 w-3.5" />{dates}</div>
          <div className="mt-3.5">
            <div className="mb-1 flex justify-between text-[11px] text-slate-500"><span>{t.done ?? 0} of {t.items} stops done</span><span>{pct}%</span></div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-gradient-to-r from-teal-500 to-emerald-500" style={{ width: `${pct}%` }} /></div>
          </div>
          {t.open_actions > 0 && <div className="mt-3"><Pill tone="amber" icon="alert">{t.open_actions} booking task{t.open_actions > 1 ? "s" : ""} open</Pill></div>}
        </div>
      </button>
      <Menu t={t} test={false} menu={menu} setMenu={setMenu} refresh={refresh} />
    </div>
  );
}

function Menu({ t, test, menu, setMenu, refresh }: { t: TripSummary; test: boolean; menu: boolean; setMenu: (b: boolean) => void; refresh: () => void }) {
  return (
    <>
      <button aria-label={`Options for ${t.title}`} aria-expanded={menu} onClick={() => setMenu(!menu)}
        className={`rounded-lg p-1.5 transition ${test ? "text-slate-400 hover:bg-slate-100 hover:text-slate-700" : "absolute right-2.5 top-2.5 bg-white/20 text-white backdrop-blur hover:bg-white/40"}`}>
        <Icon name="more" />
      </button>
      {menu && (
        <div role="menu" className={`absolute right-2.5 z-30 w-48 animate-fade-up overflow-hidden rounded-xl border border-slate-200 bg-white py-1 text-sm shadow-xl ${test ? "top-11" : "top-11"}`}>
          <button onClick={() => { setMenu(false); api.patchTrip(t.id, { kind: test ? "manual" : "test" }).then(() => { refresh(); toast(`Moved to ${test ? "my trips" : "test trips"}`); }); }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-slate-700 hover:bg-slate-50">
            <Icon name="layers" /> Move to {test ? "my trips" : "test trips"}
          </button>
          <button onClick={() => { setMenu(false); api.deleteTrip(t.id).then(() => { refresh(); toast(`Deleted “${t.title}”`, "red"); }); }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-red-600 hover:bg-red-50">
            <Icon name="trash" /> Delete
          </button>
        </div>
      )}
    </>
  );
}

export default function Home({ user, open, status }: { user: User; open: (id: string) => void; status: Status | null }) {
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [mode, setMode] = useState<Mode>("idea");
  const [idea, setIdea] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [dest, setDest] = useState("");
  const [drag, setDrag] = useState(false);
  const [showTests, setShowTests] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = () => api.trips().then((r) => setTrips(r.trips)).catch(() => setTrips([]));
  useEffect(() => { refresh(); }, []);

  const go = async (label: string, fn: () => Promise<{ id: string; title?: string; items?: unknown[] }>) => {
    setBusy(label);
    setError(null);
    try {
      const t = await fn();
      toast(`Trip ready: ${t.title ?? "your trip"}`, "green", t.items ? `${t.items.length} stops added` : undefined);
      open(t.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  };

  const upload = (f: File | undefined) => f && go(`Reading ${f.name}… this can take a minute for long itineraries`, () => api.importFile(f));
  const noAi = status && status.ai.providers.length === 0;
  const mine = (trips ?? []).filter((t) => (t.kind ?? "manual") === "manual");
  const tests = (trips ?? []).filter((t) => t.kind === "test");
  const stops = mine.reduce((a, t) => a + t.items, 0);
  const done = mine.reduce((a, t) => a + (t.done ?? 0), 0);
  const tasks = mine.reduce((a, t) => a + t.open_actions, 0);

  return (
    <div className="mx-auto max-w-6xl px-4 pb-14 pt-6 sm:px-6">
      {/* hero */}
      <section className="relative mb-8 animate-fade-up overflow-hidden rounded-3xl bg-gradient-to-br from-teal-700 via-teal-600 to-sky-700 px-6 py-8 text-white shadow-lg shadow-teal-900/10 sm:px-10 sm:py-10">
        <svg viewBox="0 0 800 260" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full" aria-hidden="true">
          <circle cx="690" cy="60" r="44" fill="white" opacity=".1" />
          <path d="M0 210 C 150 170, 280 220, 420 185 S 680 140, 800 175 L800 260 L0 260Z" fill="white" opacity=".07" />
          <path d="M0 240 C 180 215, 340 250, 500 225 S 700 210, 800 222 L800 260 L0 260Z" fill="white" opacity=".09" />
          <path d="M470 200 Q 560 90, 640 140 T 770 70" fill="none" stroke="white" strokeWidth="2.5" strokeDasharray="2 10" strokeLinecap="round" opacity=".6" className="animate-dash" />
        </svg>
        <div className="relative flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-xl">
            <p className="text-sm font-medium text-teal-100">{greeting()}, {user.username}</p>
            <h1 className="mt-1 text-3xl font-bold leading-tight tracking-tight sm:text-4xl">When plans break, recover in minutes.</h1>
            <p className="mt-2 text-teal-50/90">Add your itinerary, tell Copilot what changed, and choose from checked recovery plans. Bookings that still work stay as they are.</p>
          </div>
          <dl className="grid grid-cols-3 gap-2 sm:gap-3">
            {[["Trips", mine.length], ["Stops done", `${done}/${stops}`], ["Open tasks", tasks]].map(([l, v]) => (
              <div key={l as string} className="rounded-2xl bg-white/10 px-4 py-3 ring-1 ring-white/15 backdrop-blur">
                <dd className="text-2xl font-bold tabular-nums">{trips ? v : "–"}</dd><dt className="text-xs text-teal-100">{l}</dt>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* create */}
      <section className="mb-10 animate-fade-up rounded-3xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] sm:p-6" style={{ animationDelay: "80ms" }}>
        <h2 className="text-lg font-semibold text-slate-900">Create a trip</h2>
        <p className="mb-5 text-sm text-slate-500">Pick whichever is easiest. You can edit everything afterwards.</p>
        <div role="tablist" className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {MODES.map((m) => {
            const on = mode === m.key;
            return (
              <button key={m.key} role="tab" aria-selected={on} onClick={() => setMode(m.key)}
                className={`group flex items-center gap-3 rounded-2xl border-2 p-4 text-left transition ${on ? "border-teal-500 bg-teal-50/60 shadow-sm" : "border-slate-200 hover:border-teal-200 hover:bg-slate-50"}`}>
                <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl transition ${on ? "bg-teal-600 text-white shadow-md shadow-teal-600/30" : "bg-slate-100 text-slate-500 group-hover:bg-teal-50 group-hover:text-teal-600"}`}>
                  <Icon name={m.icon} className="h-5 w-5" />
                </span>
                <span className="min-w-0"><span className={`block font-semibold ${on ? "text-teal-900" : "text-slate-900"}`}>{m.title}</span><span className="block text-xs text-slate-500">{m.sub}</span></span>
                <span className={`ml-auto h-4 w-4 shrink-0 rounded-full border-2 transition ${on ? "border-[5px] border-teal-600" : "border-slate-300"}`} />
              </button>
            );
          })}
        </div>

        <div key={mode} className="animate-fade-up">
          {mode === "idea" && (
            <div>
              <label htmlFor="idea" className="mb-1.5 block text-sm font-medium text-slate-700">Where would you like to go, roughly when, and who's coming?</label>
              <textarea id="idea" value={idea} onChange={(e) => setIdea(e.target.value)} rows={5} placeholder={IDEA_EXAMPLE} className={`${inputCls} leading-relaxed`} />
              <p className="mt-2 text-xs text-slate-500">Copilot searches the web for current places, opening days, stays and ways to get there, drafts a day-by-day plan, and checks every timing. Stays and journeys become a booking checklist. Takes up to a minute.</p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Btn icon="sparkle" disabled={!!busy || idea.trim().length < 8 || !!noAi} onClick={() => go("Searching the web, drafting your plan and placing it on the map… up to a minute", () => api.planIdea(idea))}>Draft my plan</Btn>
                <Btn kind="secondary" onClick={() => setIdea(IDEA_EXAMPLE)}>Use an example</Btn>
              </div>
            </div>
          )}

          {mode === "upload" && (
            <div
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]); }}
              className={`grid place-items-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${drag ? "scale-[1.01] border-teal-500 bg-teal-50" : "border-slate-200 bg-slate-50/60"}`}>
              <span className={`grid h-14 w-14 place-items-center rounded-2xl bg-white text-teal-600 shadow-sm ring-1 ring-slate-200 transition ${drag ? "-translate-y-1" : ""}`}><Icon name="upload" className="h-7 w-7" /></span>
              <p className="mt-4 font-medium text-slate-900">{drag ? "Drop it here" : "Drop your booking confirmations or itinerary here"}</p>
              <p className="mt-1 text-sm text-slate-500">PDF, Word (.docx), text, or an image (PNG, JPG)</p>
              <div className="mt-3 flex flex-wrap justify-center gap-1.5">
                {["PDF", "DOCX", "TXT", "PNG", "JPG"].map((f) => <span key={f} className="rounded-md bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-500 ring-1 ring-slate-200">{f}</span>)}
              </div>
              <input ref={fileRef} type="file" className="hidden" accept=".pdf,.docx,.txt,.md,.eml,image/*" onChange={(e) => upload(e.target.files?.[0])} />
              <Btn className="mt-5" icon="file" disabled={!!busy || !!noAi} onClick={() => fileRef.current?.click()}>Choose a file</Btn>
              {status && status.ai.vision.length === 0 && <p className="mt-3 text-xs text-slate-400">Photos need a Gemini key; PDFs and documents work with Groq.</p>}
            </div>
          )}

          {mode === "describe" && (
            <div>
              <label htmlFor="describe" className="mb-1.5 block text-sm font-medium text-slate-700">Your trip in your own words</label>
              <textarea id="describe" value={text} onChange={(e) => setText(e.target.value)} rows={7} placeholder={EXAMPLE} className={`${inputCls} leading-relaxed`} />
              <p className="mt-2 text-xs text-slate-500">Paste booking emails or write it out: dates, times, places, booking references.</p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Btn icon="sparkle" disabled={!!busy || !text.trim() || !!noAi} onClick={() => go("Understanding your trip…", () => api.importText(text))}>Create my trip</Btn>
                <Btn kind="secondary" onClick={() => setText(EXAMPLE)}>Use an example</Btn>
              </div>
            </div>
          )}

          {mode === "build" && (
            <form className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); go("Creating…", () => api.createTrip(title || "My trip", dest)); }}>
              <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Trip name</span>
                <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Mysuru weekend" className={inputCls} /></label>
              <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">Main city</span>
                <input value={dest} onChange={(e) => setDest(e.target.value)} placeholder="e.g. Mysuru" className={inputCls} /></label>
              <Btn type="submit" icon="plus" disabled={!!busy} className="py-2.5">Start building</Btn>
              <p className="text-xs text-slate-500 sm:col-span-3">You'll add trains, hotels, activities and meals one by one, with real places from the map.</p>
            </form>
          )}
        </div>

        {busy && (
          <div className="mt-5 flex items-center gap-3 rounded-xl bg-teal-50 px-4 py-3 text-sm text-teal-900">
            <Spinner /> <span>{busy}</span>
          </div>
        )}
        {error && <Notice tone="red" icon="alert" className="mt-4">{error}
          {mode === "describe" && /dated items/.test(error) && (
            <button className="ml-2 font-semibold underline underline-offset-2" onClick={() => { setIdea(text); setMode("idea"); setError(null); }}>Draft a plan from this instead</button>
          )}</Notice>}
        {noAi && <Notice tone="amber" icon="alert" className="mt-4">No AI key found in <code>.env</code>, so upload and description import are off. You can still build a trip step by step.</Notice>}
      </section>

      {/* my trips */}
      <section className="mb-10">
        <div className="mb-4 flex items-end justify-between gap-3">
          <div><h2 className="text-xl font-semibold text-slate-900">My trips</h2><p className="text-sm text-slate-500">Open a trip to follow it, report a change, or review plans.</p></div>
          {trips && <span className="text-sm text-slate-400">{mine.length} trip{mine.length === 1 ? "" : "s"}</span>}
        </div>
        {trips === null ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((n) => <div key={n} className="h-56 animate-pulse rounded-2xl bg-slate-200/60" />)}</div>
        ) : mine.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
            <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-teal-50 text-teal-600"><Icon name="route" className="h-7 w-7" /></span>
            <p className="mt-4 font-semibold text-slate-900">No trips yet</p>
            <p className="mt-1 text-sm text-slate-500">Upload an itinerary, describe your trip, or build one step by step above.</p>
          </div>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {mine.map((t, i) => <TripCard key={t.id} t={t} i={i} test={false} open={open} refresh={refresh} />)}
          </div>
        )}
      </section>

      {tests.length > 0 && (
        <section className="mb-10 rounded-3xl border border-slate-200 bg-slate-100/60 p-5">
          <button onClick={() => setShowTests(!showTests)} aria-expanded={showTests} className="flex w-full items-center justify-between gap-3 text-left">
            <span><span className="font-semibold text-slate-700">Automated test trips</span> <span className="text-sm text-slate-400">({tests.length})</span>
              <span className="block text-xs text-slate-500">Created by the automated test runs; kept separate from your trips</span></span>
            <span className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-slate-600 hover:bg-white">{showTests ? "Hide" : "Show"}<Icon name="back" className={`h-3.5 w-3.5 transition ${showTests ? "rotate-90" : "-rotate-90"}`} /></span>
          </button>
          {showTests && (
            <div className="mt-4 grid animate-fade-up gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {tests.map((t, i) => <TripCard key={t.id} t={t} i={i} test open={open} refresh={refresh} />)}
            </div>
          )}
        </section>
      )}

    </div>
  );
}
