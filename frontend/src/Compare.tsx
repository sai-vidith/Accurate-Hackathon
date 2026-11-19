import type { Disruption, Plan, Trip } from "./types";
import { TypeIcon, hm } from "./ui";

export type Slot = { start?: string | null; end?: string | null; travel?: number | null; label?: string; tone?: string };
export type CmpRow = {
  id: string;
  title: string;
  type: string;
  done?: boolean;
  cols: (Slot | null)[];
  why?: string;
  tags?: string[];
};

const mins = (a?: string | null, b?: string | null) => {
  if (!a || !b) return null;
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60000);
};
const delta = (m: number | null) => (m == null || m === 0 ? null : `${m > 0 ? "+" : "−"}${Math.abs(m) >= 60 ? `${Math.floor(Math.abs(m) / 60)}h${Math.abs(m) % 60 ? ` ${Math.abs(m) % 60}m` : ""}` : `${Math.abs(m)}m`}`);
const dur = (s?: string | null, e?: string | null) => mins(s, e);

const TONE: Record<string, string> = {
  affected: "bg-red-50 text-red-700", at_risk: "bg-amber-50 text-amber-900", shifted: "bg-sky-50 text-sky-900",
  disrupted: "bg-orange-50 text-orange-900", completed: "bg-emerald-50 text-emerald-800", skipped: "bg-slate-100 text-slate-500",
  dropped: "bg-red-50 text-red-700", new: "bg-violet-50 text-violet-800", shortened: "bg-amber-50 text-amber-900",
  reordered: "bg-indigo-50 text-indigo-800", postponed: "bg-teal-50 text-teal-800", moved: "bg-sky-50 text-sky-900",
  updated: "bg-orange-50 text-orange-900", added: "bg-violet-50 text-violet-800", cancelled: "bg-slate-100 text-slate-500",
};

function Cell({ s, ref0 }: { s: Slot | null; ref0: Slot | null }) {
  if (!s) return <td className="px-3 py-2 text-slate-300">—</td>;
  if (!s.start) return <td className="px-3 py-2"><span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${TONE[s.tone ?? ""] ?? "bg-slate-100 text-slate-600"}`}>{s.label}</span></td>;
  const ds = ref0 && ref0 !== s ? mins(ref0.start, s.start) : null;
  const dd = ref0 && ref0 !== s && ref0.end && s.end ? (dur(s.start, s.end) ?? 0) - (dur(ref0.start, ref0.end) ?? 0) : null;
  return (
    <td className="px-3 py-2 align-top">
      <div className="whitespace-nowrap text-[13px] font-semibold tabular-nums text-slate-900">
        {hm(s.start)}{s.end ? `–${hm(s.end)}` : ""}
        {delta(ds) && <span className={`ml-1.5 rounded px-1 font-sans text-[10px] font-bold ${ds! > 0 ? "bg-orange-100 text-orange-800" : "bg-emerald-100 text-emerald-800"}`}>{delta(ds)}</span>}
      </div>
      <div className="mt-0.5 flex flex-wrap gap-1 text-[10px] text-slate-500">
        {s.travel != null && s.travel > 0 && <span>{s.travel} min travel</span>}
        {dd != null && dd !== 0 && <span className={dd < 0 ? "font-semibold text-amber-700" : "font-semibold text-sky-700"}>{dd < 0 ? `${-dd} min shorter` : `${dd} min longer`}</span>}
        {s.label && <span className={`rounded px-1 font-semibold ${TONE[s.tone ?? ""] ?? ""}`}>{s.label}</span>}
      </div>
    </td>
  );
}

export default function CompareTable({ heads, rows, caption }: { heads: string[]; rows: CmpRow[]; caption?: string }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Stop</th>
            {heads.map((h) => <th key={h} className="px-3 py-2">{h}</th>)}
            <th className="px-3 py-2">Why</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.id} className={r.done ? "bg-emerald-50/40" : ""}>
              <td className="px-3 py-2 align-top">
                <div className="flex items-center gap-2 font-medium text-slate-900"><TypeIcon type={r.type} done={r.done} size="sm" /> {r.title}</div>
                {r.done && <div className="text-[10px] font-semibold uppercase text-emerald-700">done · locked</div>}
              </td>
              {r.cols.map((c, n) => <Cell key={n} s={c} ref0={r.cols[0]} />)}
              <td className="max-w-[320px] px-3 py-2 align-top text-xs text-slate-600">{r.why}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {caption && <div className="border-t border-slate-100 px-3 py-2 text-[11px] text-slate-500">{caption}</div>}
    </div>
  );
}

const STATUS_LABEL: Record<string, string> = {
  affected: "Needs a change", at_risk: "At risk", shifted: "Shifts later", disrupted: "Delay here", completed: "Done",
  skipped: "Not marked done", in_progress: "Now", unaffected: "",
};

/** Original (as booked) vs. after the delay if nothing else changes [vs. a plan]. */
export function disruptionRows(trip: Trip, d: Disruption, plan?: Plan | null): CmpRow[] {
  const base = d.impact.base ?? {};
  const res = d.impact.results;
  const items = Object.fromEntries(trip.items.map((i) => [i.id, i]));
  const sched = Object.fromEntries((plan?.schedule ?? []).map((r) => [r.id, r]));
  const removed = new Set((plan?.removed ?? []).map((r) => r.id));
  const ids = Object.keys(res).filter((id) => items[id]);
  ids.sort((a, b) => (base[a]?.start ?? items[a].start).localeCompare(base[b]?.start ?? items[b].start));
  const rows: CmpRow[] = ids.map((id) => {
    const it = items[id];
    const r = res[id];
    const b = base[id];
    const done = r.status === "completed" && r.manual;
    const after: Slot = r.status === "affected"
      ? { label: "Can't happen", tone: "affected" }
      : { start: r.start, end: it.type === "stay" ? null : r.end, travel: r.travel_min ?? null, label: STATUS_LABEL[r.status], tone: r.status };
    const cols: (Slot | null)[] = [{ start: b?.start ?? it.start, end: it.type === "stay" ? null : b?.end ?? it.end, travel: b?.travel_min ?? null }, after];
    let why = r.why || r.reason;
    let tags: string[] = [];
    if (plan) {
      const p = sched[id];
      if (p) {
        cols.push({ start: p.start, end: it.type === "stay" ? null : p.end, travel: p.travel_min, label: p.tag === "kept" || p.tag === "done" ? undefined : p.tag, tone: p.tag });
        why = p.why || why;
        tags = p.flags;
      } else if (removed.has(id)) {
        cols.push({ label: "Dropped", tone: "dropped" });
        why = (plan.removed.find((x) => x.id === id)?.why ?? why);
      } else cols.push(null);
    }
    return { id, title: it.title, type: it.type, done, cols, why, tags };
  });
  if (plan) {
    for (const p of plan.schedule.filter((x) => x.tag === "new")) {
      rows.push({ id: p.id, title: p.title, type: p.type, cols: [null, null, { start: p.start, end: p.end, travel: p.travel_min, label: "new", tone: "new" }], why: p.why });
    }
    rows.sort((a, b) => ((a.cols[2]?.start ?? a.cols[0]?.start ?? "") as string).localeCompare((b.cols[2]?.start ?? b.cols[0]?.start ?? "") as string));
  }
  return rows;
}

/** The itinerary as first planned vs. now. */
export function baselineRows(trip: Trip): CmpRow[] {
  const before = Object.fromEntries((trip.baseline?.items ?? []).map((i) => [i.id, i]));
  const ids = [...new Set([...Object.keys(before), ...trip.items.map((i) => i.id)])];
  const now = Object.fromEntries(trip.items.map((i) => [i.id, i]));
  const rows = ids.map((id) => {
    const o = before[id];
    const c = now[id];
    const it = c ?? o;
    const cur: Slot | null = !c ? null : c.status === "cancelled" ? { label: "Dropped", tone: "cancelled" }
      : { start: c.start, end: c.type === "stay" ? null : c.end, label: !o ? "added" : c.completed ? `done ${hm(c.completed_at)}` : undefined, tone: !o ? "added" : c.completed ? "completed" : undefined };
    return {
      id, title: it.title, type: it.type, done: !!c?.completed,
      cols: [o ? { start: o.start, end: o.type === "stay" ? null : o.end } : null, cur],
      why: c?.cancel_reason || c?.change_note || (c && o && c.start !== o.start ? "Changed by an approved recovery plan." : ""),
    } as CmpRow;
  });
  rows.sort((a, b) => ((a.cols[0]?.start ?? a.cols[1]?.start ?? "") as string).localeCompare((b.cols[0]?.start ?? b.cols[1]?.start ?? "") as string));
  return rows;
}

/** The changes at a glance: only the stops whose time or status changes, as "before → after". */
export function ImpactList({ rows }: { rows: CmpRow[] }) {
  const changed = rows.filter((r) => {
    const [a, b] = r.cols;
    if (r.done || !a || !b) return false;
    return b.label === "Can't happen" || (b.start && a.start && b.start !== a.start) || ["affected", "at_risk", "disrupted"].includes(b.tone ?? "");
  });
  const lost = changed.filter((r) => r.cols[1]?.label === "Can't happen").length;
  const unchanged = rows.filter((r) => !r.done).length - changed.length;
  if (!changed.length) {
    return <div className="flex items-center gap-2 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800"><span className="grid h-6 w-6 place-items-center rounded-full bg-emerald-500 text-white">✓</span>No stop moves: every time still works.</div>;
  }
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2 text-xs font-semibold">
        <span className="rounded-full bg-sky-50 px-2.5 py-1 text-sky-700 ring-1 ring-inset ring-sky-200">{changed.length - lost} stop{changed.length - lost === 1 ? "" : "s"} move</span>
        {lost > 0 && <span className="rounded-full bg-red-50 px-2.5 py-1 text-red-700 ring-1 ring-inset ring-red-200">{lost} can't happen as planned</span>}
        <span className="rounded-full bg-slate-50 px-2.5 py-1 text-slate-600 ring-1 ring-inset ring-slate-200">{unchanged} unchanged</span>
      </div>
      <ol className="space-y-2">
        {changed.map((r, n) => {
          const [a, b] = r.cols as [Slot, Slot];
          const lostRow = b.label === "Can't happen";
          const ds = mins(a.start, b.start);
          return (
            <li key={r.id} style={{ animationDelay: `${n * 40}ms` }}
              className={`flex animate-fade-up flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border px-3.5 py-2.5 ${lostRow ? "border-red-200 bg-red-50/50" : "border-slate-200 bg-white"}`}>
              <div className="flex min-w-0 flex-1 items-center gap-2.5">
                <TypeIcon type={r.type} size="sm" />
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-slate-900">{r.title}</div>
                  {r.why && <div className="line-clamp-1 text-[11px] text-slate-500" title={r.why}>{r.why}</div>}
                </div>
              </div>
              <div className="flex items-center gap-2 text-sm tabular-nums">
                <span className="text-slate-400 line-through">{hm(a.start)}</span>
                <span className="text-slate-300">→</span>
                {lostRow ? <span className="font-semibold text-red-700">Can't happen</span> : <span className="font-semibold text-slate-900">{hm(b.start)}</span>}
                {!lostRow && delta(ds) && <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${ds! > 0 ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>{delta(ds)}</span>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
