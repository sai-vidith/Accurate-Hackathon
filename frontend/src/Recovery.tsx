import { useState } from "react";
import { api } from "./api";
import CompareTable, { ImpactList, disruptionRows } from "./Compare";
import type { Disruption, Plan, Trip } from "./types";
import { Btn, Card, Icon, Notice, Pill, Spinner, day, hm, inputCls, money, toast, type IconName } from "./ui";

const QUICK: [IconName, string, string][] = [
  ["train", "Train/flight delayed", "My train is delayed by 2 hours"],
  ["ban", "Cancelled", "My flight was cancelled"],
  ["rain", "Rain", "It's going to rain this afternoon"],
  ["lock", "Place closed", "The museum is closed today"],
  ["clock", "Running late", "I'm running about an hour late"],
  ["calendar", "New commitment", "I have a work call from 15:00 to 16:00"],
];

function ReportBox({ trip, onTrip }: { trip: Trip; onTrip: (t: Trip) => void }) {
  const [msg, setMsg] = useState("");
  const [asOf, setAsOf] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const send = async () => {
    setBusy(true);
    setErr(null);
    try {
      onTrip(await api.reportChange(trip.id, msg, asOf || undefined));
      toast("Change understood", "amber", "Every later stop was rechecked. See the impact below.");
      setMsg("");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="Something changed?" icon="alert" sub="Tell Copilot in your own words. It works out what's affected before suggesting anything.">
      <ol className="mb-4 grid gap-2 text-xs text-slate-500 sm:grid-cols-3">
        {["Describe what changed", "See the impact on every stop", "Pick a plan and approve it"].map((t, n) => (
          <li key={t} className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2">
            <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-teal-600 text-[10px] font-bold text-white">{n + 1}</span>{t}
          </li>
        ))}
      </ol>
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {QUICK.map(([icon, l, t]) => (
          <button key={l} onClick={() => setMsg(t)} aria-pressed={msg === t}
            className={`group flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left text-sm font-medium transition ${msg === t ? "border-teal-500 bg-teal-50 text-teal-900 shadow-sm" : "border-slate-200 text-slate-700 hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-sm"}`}>
            <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg transition ${msg === t ? "bg-teal-600 text-white" : "bg-slate-100 text-slate-500 group-hover:bg-teal-50 group-hover:text-teal-600"}`}><Icon name={icon} /></span>
            {l}
          </button>
        ))}
      </div>
      <label htmlFor="change-msg" className="sr-only">What changed</label>
      <textarea id="change-msg" value={msg} onChange={(e) => setMsg(e.target.value)} rows={2} placeholder="e.g. My train is running 3 hours late" className={inputCls} />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Btn icon="route" onClick={send} disabled={busy || !msg.trim() || !trip.items.length}>{busy ? "Analysing…" : "Check my trip"}</Btn>
        <label className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          As of
          <input type="datetime-local" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-1 text-xs" />
          <span>(optional: leave empty and Copilot works it out)</span>
        </label>
        {busy && <Spinner />}
      </div>
      {!trip.items.length && <p className="mt-2 text-xs text-slate-500">Add some items to your trip first.</p>}
      {err && <Notice tone="red" icon="alert" className="mt-3">{err}</Notice>}
    </Card>
  );
}

function PlanCard({ p, n, cur, focused, onFocus, onApprove, onCompare, busy }: { p: Plan; n: number; cur: string; focused: boolean; onFocus: () => void; onApprove: () => void; onCompare: () => void; busy: boolean }) {
  const [all, setAll] = useState(false);
  const tagCls: Record<string, string> = {
    new: "bg-violet-100 text-violet-800", moved: "bg-sky-100 text-sky-800", updated: "bg-orange-100 text-orange-800",
    shortened: "bg-amber-100 text-amber-900", reordered: "bg-indigo-100 text-indigo-800", postponed: "bg-teal-100 text-teal-800",
    kept: "text-slate-400", done: "bg-emerald-100 text-emerald-800", skipped: "bg-slate-100 text-slate-500", busy: "bg-slate-100 text-slate-600",
  };
  const failed = p.checks.filter((c) => !c.ok);
  return (
    <div className={`flex flex-col rounded-2xl border bg-white p-4 transition ${focused ? "border-teal-500 shadow-lg ring-2 ring-teal-100" : p.recommended ? "border-teal-300 shadow-sm" : "border-slate-200"}`}>
      <div className="mb-2 flex items-start gap-3">
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl text-sm font-bold ${p.recommended ? "bg-teal-600 text-white shadow-md shadow-teal-600/30" : "bg-slate-100 text-slate-600"}`}>{String.fromCharCode(65 + n)}</span>
        <div className="min-w-0 flex-1">
          {p.recommended && <div className="mb-1"><Pill tone="green" icon="check">Recommended</Pill></div>}
          <h3 className="text-base font-semibold leading-snug text-slate-900">{p.name}</h3>
        </div>
      </div>
      <p className="mb-3 text-sm text-slate-600">{p.summary}</p>
      <dl className="mb-3 grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded-xl bg-slate-50 p-2"><dt className="text-slate-500">Extra cost</dt><dd className="text-sm font-semibold">{p.extra_cost ? money(p.extra_cost, cur) : "None known"}</dd></div>
        <div className="rounded-xl bg-slate-50 p-2"><dt className="text-slate-500">Travel</dt><dd className="text-sm font-semibold">{p.travel_min} min</dd></div>
        <div className="rounded-xl bg-slate-50 p-2"><dt className="text-slate-500">Day ends</dt><dd className="text-sm font-semibold">{p.day_ends}</dd></div>
      </dl>
      <ol className="mb-3 space-y-1.5 text-sm">
        {p.schedule.filter((r) => r.tag !== "done" && r.tag !== "skipped" && (all || r.tag !== "kept")).map((r) => (
          <li key={r.id} className="flex items-start gap-2">
            <span className="w-[78px] shrink-0 text-xs font-semibold leading-5 tabular-nums text-slate-700">{hm(r.start)}{r.end && r.type !== "stay" ? `–${hm(r.end)}` : ""}</span>
            <span className="min-w-0 flex-1">
              <span className="font-medium text-slate-800">{r.title}</span>
              {r.was && <span className="ml-1 text-[11px] tabular-nums text-slate-400 line-through">{hm(r.was)}{r.was_end && r.type !== "stay" ? `–${hm(r.was_end)}` : ""}</span>}
              {r.tag !== "kept" && r.why && <span className="block text-[11px] text-slate-500">{r.why}</span>}
              {r.travel_min > 0 && <span className="block text-[11px] text-slate-400">{r.travel_min} min {r.travel_mode === "walk" ? "walk" : "by road"} before</span>}
            </span>
            <span className="flex shrink-0 flex-col items-end gap-0.5">
              {(r.flags?.length ? r.flags.filter((f) => f !== "moved" || r.flags.length === 1) : r.tag !== "kept" ? [r.tag] : []).map((f) => (
                <span key={f} className={`rounded px-1.5 text-[10px] font-semibold uppercase ${tagCls[f] ?? "bg-slate-100"}`}>{f}</span>
              ))}
            </span>
          </li>
        ))}
        {p.removed.map((r) => (
          <li key={r.id} className="flex items-start gap-2 text-slate-400">
            <span className="w-[78px] shrink-0 text-xs leading-5 tabular-nums line-through">{hm(r.start)}</span>
            <span className="flex-1"><span className="line-through">{r.title}</span>{r.why && <span className="block text-[11px] text-slate-400">{r.why}</span>}</span>
            <span className="shrink-0 rounded bg-red-100 px-1.5 text-[10px] font-semibold uppercase text-red-700">dropped</span>
          </li>
        ))}
      </ol>
      {p.schedule.some((r) => r.tag === "kept") && (
        <button onClick={() => setAll(!all)} className="mb-3 self-start text-xs font-medium text-sky-700 hover:underline">
          {all ? "Show only what changes" : `Show all stops (${p.schedule.filter((r) => r.tag === "kept").length} unchanged)`}
        </button>
      )}
      <div className="mb-3 space-y-1 border-t border-slate-100 pt-3 text-xs">
        {p.checks.map((c) => <div key={c.text} className={`flex items-start gap-1.5 ${c.ok ? "text-emerald-700" : "text-red-700"}`}><Icon name={c.ok ? "check" : "x"} className="mt-px h-3.5 w-3.5" />{c.text}</div>)}
        {p.dropped.map((x) => <div key={x.title} className="text-slate-500">↷ Left out {x.title}: {x.why}</div>)}
      </div>
      <div className="mb-3 grid grid-cols-2 gap-3 text-xs">
        <div><div className="mb-1 font-semibold text-emerald-800">Advantages</div>
          <ul className="space-y-0.5 text-slate-600">{(p.pros ?? []).map((t) => <li key={t}>+ {t}</li>)}</ul></div>
        <div><div className="mb-1 font-semibold text-red-800">Disadvantages</div>
          <ul className="space-y-0.5 text-slate-600">{(p.cons ?? []).map((t) => <li key={t}>− {t}</li>)}</ul></div>
      </div>
      {p.source !== "rules" && (
        <div className="mb-4 text-xs text-slate-500">
          <span className="font-semibold">AI notes</span> (the checks and lists above are calculated): {p.tradeoffs.join(" · ")}
        </div>
      )}
      {failed.length === 0 && (
        <div className="mt-auto grid grid-cols-[auto_auto_1fr] gap-2">
          <Btn kind="secondary" icon="map" onClick={onFocus}>{focused ? "Hide map" : "Map"}</Btn>
          <Btn kind="secondary" onClick={onCompare}>Compare</Btn>
          <Btn onClick={onApprove} disabled={busy}>Approve this plan</Btn>
        </div>
      )}
      <p className="mt-1.5 text-center text-[11px] text-slate-400">Unchanged bookings stay as they are. Changes to bookings become tasks for you.</p>
    </div>
  );
}

export default function Recovery({ trip, d, onTrip, focus, setFocus }: { trip: Trip; d: Disruption | null; onTrip: (t: Trip) => void; focus: string | null; setFocus: (id: string | null) => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [asOf, setAsOf] = useState("");
  const [cmp, setCmp] = useState<string | null>(null);
  const run = async (label: string, fn: () => Promise<Trip>) => {
    setBusy(label);
    setErr(null);
    try { onTrip(await fn()); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  if (!d) {
    const last = trip.disruptions[trip.disruptions.length - 1];
    return (
      <>
        {last?.status === "dismissed" && last.dismiss_reason && (
          <Notice tone="green" icon="lock" className="mb-4">
            <b>No changes made.</b> {last.dismiss_reason}
            {(last.ignored ?? []).map((x) => <div key={x} className="mt-1 text-xs text-emerald-800">{x}</div>)}
          </Notice>
        )}
        <ReportBox trip={trip} onTrip={onTrip} />
      </>
    );
  }

  const items = Object.fromEntries(trip.items.map((i) => [i.id, i]));
  const res = d.impact.results;
  const cur = trip.preferences.currency;

  return (
    <div className="space-y-5">
      <Card title="Handle disruption" icon="alert" sub={<>Understood by {d.understood_by}</>}
        right={<Btn kind="ghost" icon="x" onClick={() => run("…", () => api.dismiss(trip.id, d.id))}>Dismiss</Btn>}>
        <div className="flex items-start gap-3 rounded-xl border border-red-100 bg-red-50 px-4 py-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white text-red-600 ring-1 ring-red-100"><Icon name="alert" /></span>
          <div className="min-w-0">
            <p className="font-medium text-slate-900">“{d.message}”</p>
            <p className="mt-0.5 text-sm text-red-800">{d.summary}</p>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {d.changes.map((c) => c.delay_min != null ? (
            <span key={c.item_id} className="flex flex-wrap items-center gap-1.5 rounded-lg bg-amber-50 px-2.5 py-1.5 text-amber-900 ring-1 ring-amber-200">
              <Icon name="clock" className="h-3.5 w-3.5" /> {items[c.item_id]?.title}: <b>{c.delay_mode === "overrun" ? "runs over" : c.delay_mode === "late_start" ? "starts late" : "arrives late"}</b>
              {[-15, -5].map((n) => <button key={n} disabled={!!busy || c.delay_min! + n < 1} onClick={() => run("Recalculating…", () => api.resizeDelay(trip.id, d.id, c.delay_min! + n))} className="rounded bg-white px-1.5 font-semibold ring-1 ring-orange-200 disabled:opacity-40">{n}</button>)}
              <b className="min-w-[52px] text-center">{c.delay_min} min</b>
              {[5, 15].map((n) => <button key={n} disabled={!!busy} onClick={() => run("Recalculating…", () => api.resizeDelay(trip.id, d.id, c.delay_min! + n))} className="rounded bg-white px-1.5 font-semibold ring-1 ring-orange-200 disabled:opacity-40">+{n}</button>)}
              <span className="text-orange-700">({c.note})</span>
            </span>
          ) : (
            <span key={c.item_id} className="rounded-lg bg-amber-50 px-2.5 py-1.5 text-amber-900 ring-1 ring-amber-200">
              {items[c.item_id]?.title ?? c.item_id}: <b>{c.kind}</b>{c.new_start ? ` · departs ${hm(c.new_start)}` : ""}{c.new_end ? ` · arrives ${hm(c.new_end)}` : ""}
            </span>
          ))}
          {d.rain && (
            <span className="rounded-lg bg-sky-50 px-2 py-1 text-sky-900 ring-1 ring-sky-200">
              Rain {hm(d.rain.start)}–{hm(d.rain.end)} <button className="ml-1 text-sky-600 hover:underline" onClick={() => run("…", () => api.editChange(trip.id, d.id, { clear_rain: true }))}>remove</button>
            </span>
          )}
          {d.busy.map((b) => <span key={b.start} className="rounded-lg bg-slate-100 px-2.5 py-1.5">{b.title} {hm(b.start)}–{hm(b.end)}</span>)}
        </div>
        {(d.ignored ?? []).length > 0 && <Notice tone="green" icon="lock" className="mt-3">{d.ignored!.map((q) => <div key={q}>{q}</div>)}</Notice>}
        {d.questions.length > 0 && <Notice tone="amber" icon="alert" className="mt-3">{d.questions.map((q) => <div key={q}>{q}</div>)}</Notice>}
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          Checked as of <b className="text-slate-700">{day(d.as_of)} {hm(d.as_of)}</b> ({d.impact.position}).
          <input type="datetime-local" value={asOf || d.as_of} onChange={(e) => setAsOf(e.target.value)} className="rounded-lg border border-slate-200 px-2 py-1" />
          {asOf && asOf !== d.as_of && <Btn kind="secondary" className="!py-1 text-xs" onClick={() => run("…", () => api.editChange(trip.id, d.id, { as_of: asOf }))}>Recheck</Btn>}
        </div>
      </Card>

      <Card title="Impact on your trip" icon="route" sub="Before and after: every later stop is rechecked against travel times, buffers, opening hours and fixed booking times.">
        <ImpactList rows={disruptionRows(trip, d)} />
        <details className="group mt-4 rounded-xl border border-slate-200">
          <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
            Detailed comparison: every stop, with the reason
            <Icon name="back" className="h-4 w-4 -rotate-90 text-slate-400 transition group-open:rotate-90" />
          </summary>
          <div className="border-t border-slate-200 p-3">
            <CompareTable heads={["Original", "After this change (nothing else done)"]} rows={disruptionRows(trip, d)}
              caption="Times are recalculated stop by stop from real travel times, buffers, fixed booking times and opening hours, not by adding the delay to everything. Done stops are locked." />
          </div>
        </details>
        {d.status === "analyzed" && (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            {d.impact.needs_change ? (
              <Btn icon="sparkle" onClick={() => run("Finding real alternatives: nearby places, opening hours, routes…", () => api.makePlans(trip.id, d.id))} disabled={!!busy}>Find recovery plans</Btn>
            ) : (
              <>
                <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-700"><Icon name="check" /> Nothing needs to change: your plan still works.</span>
                <Btn kind="secondary" onClick={() => run("…", () => api.dismiss(trip.id, d.id))}>Got it</Btn>
                <Btn kind="ghost" onClick={() => run("Finding alternatives…", () => api.makePlans(trip.id, d.id))}>Show options anyway</Btn>
              </>
            )}
          </div>
        )}
        {busy && <div className="mt-4 flex items-center gap-3 rounded-xl bg-teal-50 px-4 py-3 text-sm text-teal-900"><Spinner /><span>{busy}</span></div>}
        {err && <Notice tone="red" icon="alert" className="mt-3">{err}</Notice>}
      </Card>

      {d.status === "planned" && (
        <Card title="Choose a recovery plan" icon="check" sub={`${d.plans.length} plan(s) passed every check. Planned by ${d.options?.planned_by}; ${d.options?.candidates.length ?? 0} nearby places and ${d.options?.transits.length ?? 0} alternative transport option(s) considered.`}>
          <div className="grid gap-4 md:grid-cols-2">
            {d.plans.map((p, n) => (
              <PlanCard key={p.id} p={p} n={n} cur={cur} busy={!!busy} focused={focus === p.id}
                onFocus={() => setFocus(focus === p.id ? null : p.id)} onCompare={() => setCmp(p.id)}
                onApprove={() => run("Updating your itinerary…", () => api.approve(trip.id, d.id, p.id).then((t) => { setFocus(null); toast(`Plan approved: ${p.name}`, "green", "Your itinerary is updated. Unchanged bookings stay as they are."); return t; }))} />
            ))}
          </div>
          {d.excluded.length > 0 && (
            <details className="mt-4 text-sm text-slate-600">
              <summary className="cursor-pointer">Rejected by the checks ({d.excluded.length})</summary>
              <ul className="mt-2 space-y-1">{d.excluded.map((p) => <li key={p.id}><b>{p.name}</b>: {p.checks.filter((c) => !c.ok).map((c) => c.text).join("; ")}</li>)}</ul>
            </details>
          )}
        </Card>
      )}

      {cmp && d.plans.find((x) => x.id === cmp) && (() => {
        const p = d.plans.find((x) => x.id === cmp)!;
        return (
          <div className="fixed inset-0 z-[1000] grid place-items-center bg-slate-900/40 p-4 backdrop-blur-[2px]" onClick={() => setCmp(null)}>
            <div className="max-h-[90vh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
              <div className="mb-1 flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold">Compare: {p.name}</h2>
                  <p className="text-sm text-slate-500">{p.summary}</p>
                </div>
                <button onClick={() => setCmp(null)} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Close comparison"><Icon name="x" /></button>
              </div>
              <div className="my-4">
                <CompareTable heads={["Original", "If nothing is done", `With “${p.name}”`]} rows={disruptionRows(trip, d, p)}
                  caption="Each change shows the time difference against the original and why it was made. Nothing is applied until you approve." />
              </div>
              <div className="flex flex-wrap justify-end gap-2">
                <Btn kind="ghost" onClick={() => setCmp(null)}>Close</Btn>
                <Btn icon="check" onClick={() => { setCmp(null); run("Updating your itinerary…", () => api.approve(trip.id, d.id, p.id).then((t) => { toast(`Plan approved: ${p.name}`, "green", "Your itinerary is updated."); return t; })); }} disabled={!!busy}>Approve this plan</Btn>
              </div>
            </div>
          </div>
        );
      })()}

      {d.status === "no_plan" && (
        <Card title="No plan meets all your limits" icon="alert" sub="Copilot won't offer a plan that breaks a hard limit. Here's what got in the way:">
          <ul className="mb-3 space-y-1 text-sm text-slate-700">
            {d.excluded.map((p) => <li key={p.id}><b>{p.name}</b>: {p.checks.filter((c) => !c.ok).map((c) => c.text).join("; ")}</li>)}
          </ul>
          <p className="text-sm text-slate-600">Try raising the extra budget, changing a <b>must-do</b> to high priority (edit the item), or giving a later "as of" time. Then press <b>Find recovery plans</b> again.</p>
          <Btn className="mt-3" onClick={() => run("Trying again…", () => api.makePlans(trip.id, d.id))}>Try again</Btn>
        </Card>
      )}
    </div>
  );
}
