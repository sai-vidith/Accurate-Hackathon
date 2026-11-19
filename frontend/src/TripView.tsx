import { useEffect, useState } from "react";
import { api } from "./api";
import Chat from "./Chat";
import CompareTable, { baselineRows } from "./Compare";
import ItemEditor from "./ItemEditor";
import MapView from "./MapView";
import Recovery from "./Recovery";
import Tasks from "./Tasks";
import type { Item, PlanDraft, Prefs, Trip } from "./types";
import { BookingChip, Btn, Card, Cover, FeasBadge, Icon, Notice, Pill, Segmented, Stat, TypeIcon, day, hm, inputCls, money, toast } from "./ui";

const INTERESTS = ["sightseeing", "culture", "food", "shopping", "nature", "rest"];

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-[1000] grid place-items-center bg-slate-900/40 p-4 backdrop-blur-[2px]" onClick={onClose}>
      <div role="dialog" aria-label={title} className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><Icon name="x" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

function PrefsModal({ trip, onClose, onTrip }: { trip: Trip; onClose: () => void; onTrip: (t: Trip) => void }) {
  const [p, setP] = useState<Prefs>({ ...trip.preferences });
  const toggle = (i: string) => setP({ ...p, interests: p.interests.includes(i) ? p.interests.filter((x) => x !== i) : [...p.interests, i] });
  const lab = "mb-1 block text-sm font-medium text-slate-700";
  return (
    <Modal title="Travel preferences" onClose={onClose}>
      <div className={lab}>Interests <span className="font-normal text-slate-500">(first = most important)</span></div>
      <div className="mb-5 flex flex-wrap gap-2">
        {INTERESTS.map((i) => (
          <button key={i} onClick={() => toggle(i)} aria-pressed={p.interests.includes(i)}
            className={`rounded-full px-3 py-1 text-sm capitalize transition ${p.interests.includes(i) ? "bg-teal-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>{i}</button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-4 text-sm">
        <label><span className={lab}>Extra budget for changes</span>
          <input type="number" min={0} step={100} value={p.extra_budget} onChange={(e) => setP({ ...p, extra_budget: Number(e.target.value) })} className={inputCls} /></label>
        <label><span className={lab}>Currency</span>
          <input value={p.currency} onChange={(e) => setP({ ...p, currency: e.target.value.toUpperCase().slice(0, 3) })} className={inputCls} /></label>
        <label><span className={lab}>Pace</span>
          <select value={p.pace} onChange={(e) => setP({ ...p, pace: e.target.value })} className={inputCls}>
            <option value="relaxed">Relaxed</option><option value="moderate">Moderate</option><option value="packed">Packed</option></select></label>
        <label><span className={lab}>Travelling as</span>
          <select value={p.group} onChange={(e) => setP({ ...p, group: e.target.value })} className={inputCls}>
            <option value="solo">Solo</option><option value="couple">Couple</option><option value="friends">Friends</option><option value="family">Family</option></select></label>
        <label><span className={lab}>Travelers</span>
          <input type="number" min={1} value={p.travelers} onChange={(e) => setP({ ...p, travelers: Number(e.target.value) })} className={inputCls} /></label>
        <label className="flex items-end gap-2 pb-3 text-slate-700"><input type="checkbox" checked={p.accessibility} onChange={(e) => setP({ ...p, accessibility: e.target.checked })} className="h-4 w-4 accent-teal-600" /> Step-free access</label>
      </div>
      <div className="mt-6 flex justify-end gap-2">
        <Btn kind="ghost" onClick={onClose}>Cancel</Btn>
        <Btn onClick={async () => { onTrip(await api.patchTrip(trip.id, { preferences: p })); onClose(); }}>Save</Btn>
      </div>
    </Modal>
  );
}

function DelayBox({ trip, item, onTrip, onClose }: { trip: Trip; item: Item; onTrip: (t: Trip) => void; onClose: () => void }) {
  const transport = item.type === "transport";
  const stay = item.type === "stay";
  const [minutes, setMinutes] = useState(45);
  const [mode, setMode] = useState(transport ? "arrives_late" : stay ? "late_start" : "overrun");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setBusy(true);
    setErr(null);
    try {
      onTrip(await api.reportDelay(trip.id, item.id, minutes, mode));
      toast(`Delay of ${minutes} min recorded`, "amber", "Every later stop was rechecked. See the impact below.");
      onClose();
      setTimeout(() => { document.getElementById("recovery")?.scrollIntoView({ behavior: "smooth", block: "start" }); }, 50);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50/70 p-4 text-sm">
      <div className="mb-3 flex items-center gap-2 font-semibold text-amber-900"><Icon name="clock" /> Report a delay at “{item.title}”</div>
      <div className="flex flex-wrap items-center gap-2">
        {[15, 30, 45, 60, 90].map((m) => (
          <button key={m} onClick={() => setMinutes(m)} aria-pressed={minutes === m}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${minutes === m ? "bg-amber-500 text-white" : "bg-white text-amber-800 ring-1 ring-amber-200 hover:ring-amber-300"}`}>{m} min</button>
        ))}
        <label className="flex items-center gap-1.5 text-xs text-amber-900">or
          <input type="number" min={1} max={1440} value={minutes} onChange={(e) => setMinutes(Math.max(1, Number(e.target.value)))} aria-label="Delay in minutes"
            className="w-20 rounded-lg border border-amber-200 bg-white px-2 py-1 text-xs" /> min</label>
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-amber-900">
        {transport ? <span>Arrives {minutes} min late</span> : stay ? <span>Check in {minutes} min later</span> : (
          <>
            <label className="flex items-center gap-1.5"><input type="radio" className="accent-amber-600" checked={mode === "overrun"} onChange={() => setMode("overrun")} /> Runs over (ends {minutes} min later)</label>
            <label className="flex items-center gap-1.5"><input type="radio" className="accent-amber-600" checked={mode === "late_start"} onChange={() => setMode("late_start")} /> Starts late (begins {minutes} min later)</label>
          </>
        )}
      </div>
      {err && <div className="mt-2 text-xs text-red-700">{err}</div>}
      <div className="mt-4 flex gap-2">
        <Btn onClick={go} disabled={busy} className="!py-1.5 text-xs">{busy ? "Checking…" : "Recalculate my day"}</Btn>
        <Btn kind="ghost" onClick={onClose} className="!py-1.5 text-xs">Cancel</Btn>
      </div>
    </div>
  );
}

function DoneToggle({ trip, item, onTrip }: { trip: Trip; item: Item; onTrip: (t: Trip) => void }) {
  const [busy, setBusy] = useState(false);
  const set = async (done: boolean, at?: string) => {
    setBusy(true);
    try {
      const before = new Set(trip.items.filter((i) => i.completed).map((i) => i.id));
      const t = await api.markDone(trip.id, item.id, done, at);
      onTrip(t);
      const after = new Set(t.items.filter((i) => i.completed).map((i) => i.id));
      const others = done ? [...after].filter((x) => !before.has(x) && x !== item.id).length : [...before].filter((x) => !after.has(x) && x !== item.id).length;
      if (at) toast(`Finish time updated to ${at.slice(11, 16)}`);
      else if (done) toast(`Done: ${item.title}`, "green", others ? `${others} earlier stop${others > 1 ? "s" : ""} also marked done` : "Locked: it won't be rescheduled");
      else toast(`Not done: ${item.title}`, "sky", others ? `${others} later stop${others > 1 ? "s" : ""} also unticked` : undefined);
    } catch (e: any) { toast(e.message, "red"); } finally { setBusy(false); }
  };
  const toggle = (
    <label className="flex cursor-pointer select-none items-center gap-1.5"
      title={item.completed ? "Mark as not done (later stops become not done too)" : "Mark as done (earlier stops count as done too)"}>
      <input type="checkbox" checked={!!item.completed} disabled={busy} onChange={(e) => set(e.target.checked)} className="peer sr-only" />
      <span className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors duration-200 peer-focus-visible:ring-2 peer-focus-visible:ring-teal-500 peer-focus-visible:ring-offset-1 ${item.completed ? "bg-emerald-500" : "bg-slate-200 hover:bg-slate-300"} ${busy ? "opacity-60" : ""}`}>
        <span className={`absolute top-0.5 grid h-5 w-5 place-items-center rounded-full bg-white shadow transition-all duration-200 ${item.completed ? "left-[22px]" : "left-0.5"}`}>
          {item.completed && <Icon name="check" className="h-3 w-3 text-emerald-600" />}
        </span>
      </span>
      <span className={`whitespace-nowrap text-xs font-semibold ${item.completed ? "text-emerald-700" : "text-slate-500"}`}>{item.completed ? "Done" : "Not done"}</span>
    </label>
  );
  // The finish-time box sits outside the toggle so clicking it never flips the switch.
  return item.completed ? (
    <span className="flex items-center gap-1.5">
      {toggle}
      <input type="time" key={item.completed_at ?? ""} defaultValue={hm(item.completed_at)} disabled={busy} title="Actual finish time"
        onBlur={(e) => { const v = e.target.value; if (v && v !== hm(item.completed_at)) set(true, `${(item.completed_at ?? item.start).slice(0, 10)}T${v}`); }}
        className="rounded-md border border-emerald-200 bg-white px-1 py-0.5 text-[11px] text-emerald-800" />
    </span>
  ) : toggle;
}

const WARN = ["affected", "at_risk", "shifted", "skipped", "tight", "conflict"];

function Stop({ trip, i, r, here, onTrip, onEdit, delayOpen, setDelay, last }: {
  trip: Trip; i: Item; r?: Trip["view"]["results"][string]; here: boolean; onTrip: (t: Trip) => void; onEdit: (i: Item) => void;
  delayOpen: boolean; setDelay: (b: boolean) => void; last: boolean;
}) {
  const off = i.status === "cancelled";
  const done = !!i.completed;
  const warn = !off && !done && r && WARN.includes(r.status);
  const bad = warn && !["skipped", "tight", "shifted"].includes(r!.status);
  const rail = done ? "bg-emerald-300" : "bg-slate-200";
  return (
    <li className={`group relative flex gap-3 sm:gap-4 ${off ? "opacity-50" : ""}`}>
      {/* time + rail */}
      <div className="hidden w-[92px] shrink-0 pt-3 text-right sm:block">
        <div className={`text-sm font-semibold tabular-nums ${done ? "text-emerald-700" : "text-slate-900"}`}>{hm(i.start)}</div>
        {i.end && i.type !== "stay" && <div className="text-xs tabular-nums text-slate-400">{hm(i.end)}</div>}
        {i.previous_start && <div className="text-[11px] tabular-nums text-slate-400 line-through">{hm(i.previous_start)}</div>}
      </div>
      <div className="relative flex flex-col items-center">
        <span className={`relative z-[1] mt-2 ${here ? "rounded-full ring-4 ring-sky-100" : ""}`}><TypeIcon type={i.type} done={done} /></span>
        {!last && <span className={`w-0.5 flex-1 ${rail}`} />}
      </div>
      {/* card */}
      <div className={`mb-3 min-w-0 flex-1 rounded-2xl border p-3.5 transition duration-200 ${
        here ? "border-sky-300 bg-sky-50/40 shadow-md shadow-sky-100" :
        done ? "border-emerald-100 bg-emerald-50/40" :
        bad ? "border-red-200 bg-white" : warn ? "border-amber-200 bg-white" : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm"}`}>
        {here && (
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-sky-700">
            <span className="relative flex h-2.5 w-2.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400 opacity-75" /><span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-sky-600" /></span>
            You are here: next up
          </div>
        )}
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
          <div className="min-w-0 flex-1">
            <div className="mb-0.5 text-xs font-semibold tabular-nums text-slate-500 sm:hidden">{hm(i.start)}{i.end && i.type !== "stay" ? ` – ${hm(i.end)}` : ""}</div>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className={`font-semibold ${off ? "line-through" : done ? "text-emerald-900" : "text-slate-900"}`}>{i.title}</span>
              {i.priority === "must" && <Pill tone="slate">Must</Pill>}
              {i.source === "recovery" && <Pill tone="violet" icon="sparkle">Added by recovery</Pill>}
            </div>
            <div className="mt-1 flex min-w-0 items-center gap-1 text-xs text-slate-500">
              <Icon name="pin" className="h-3 w-3 text-slate-400" />
              <span className="truncate">
                {i.type === "transport" && i.origin ? `${i.origin.name} → ` : ""}{i.location?.name ?? "No place set"}
                {i.location && i.location.lat == null && <span className="text-amber-600"> · not on map: edit to fix</span>}
                {i.booking.reference ? ` · ref ${i.booking.reference}` : ""}
              </span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {!off && !done && <FeasBadge r={r} />}
            <BookingChip status={i.booking.status} />
          </div>
        </div>

        {done && <div className="mt-2 flex items-center gap-1 text-xs font-medium text-emerald-700"><Icon name="lock" className="h-3 w-3" /> Finished {hm(i.completed_at)}. Locked: never rescheduled.</div>}
        {off && i.cancel_reason && <div className="mt-2 text-xs text-slate-500">{i.cancel_reason}</div>}
        {!off && !done && i.change_note && <div className="mt-2 text-xs text-violet-700">{i.change_note}</div>}
        {warn && <div className={`mt-2 flex items-start gap-1.5 rounded-lg px-2.5 py-1.5 text-xs ${bad ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-800"}`}><Icon name="alert" className="mt-px h-3.5 w-3.5" />{r!.reason}</div>}
        {!off && i.location?.approximate && <div className="mt-1.5 text-xs text-amber-700">{i.location.address}</div>}
        {i.notes && <div className="mt-1 text-xs text-slate-400">{i.notes}</div>}

        {!off && (
          <div className="mt-3 flex flex-wrap items-center gap-1 border-t border-slate-100 pt-2.5">
            <DoneToggle trip={trip} item={i} onTrip={onTrip} />
            <span className="flex-1" />
            {!done && (
              <button onClick={() => setDelay(!delayOpen)} aria-label={`Report a delay at ${i.title}`} aria-expanded={delayOpen}
                className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold transition ${delayOpen ? "bg-amber-100 text-amber-800" : "text-amber-700 hover:bg-amber-50"}`}>
                <Icon name="clock" className="h-3.5 w-3.5" /> Delay
              </button>
            )}
            <button onClick={() => onEdit(i)} aria-label={`Edit ${i.title}`} title="Edit"
              className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"><Icon name="pencil" className="h-3.5 w-3.5" /></button>
            <button onClick={() => api.deleteItem(trip.id, i.id).then((t) => { onTrip(t); toast(`Removed ${i.title}`, "red"); })} aria-label={`Remove ${i.title}`} title="Remove"
              className="rounded-lg p-1.5 text-slate-400 transition hover:bg-red-50 hover:text-red-600"><Icon name="trash" className="h-3.5 w-3.5" /></button>
          </div>
        )}
        {delayOpen && <DelayBox trip={trip} item={i} onTrip={onTrip} onClose={() => setDelay(false)} />}
      </div>
    </li>
  );
}

function Itinerary({ trip, onTrip, results, onEdit }: { trip: Trip; onTrip: (t: Trip) => void; results: Trip["view"]["results"]; onEdit: (i: Item | null) => void }) {
  const [delayFor, setDelayFor] = useState<string | null>(null);
  const [compare, setCompare] = useState(false);
  const days = [...new Set(trip.items.map((i) => i.start.slice(0, 10)))].sort();
  const live = trip.items.filter((i) => i.status !== "cancelled");
  const lastDoneIdx = live.reduce((acc, it, n) => (it.completed ? n : acc), -1);
  const hereId = lastDoneIdx >= 0 ? live[lastDoneIdx + 1]?.id ?? "__end" : null;
  const hereDay = live.find((i) => i.id === hereId)?.start.slice(0, 10);
  const jump = (d: string) => document.getElementById(`day-${d}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  return (
    <Card title="Itinerary" icon="calendar"
      sub={trip.items.length ? "Ticking a stop also completes every stop before it. Finished stops are locked and never changed." : undefined}
      right={
        <div className="flex gap-2">
          {trip.baseline && <Btn kind="secondary" onClick={() => setCompare((c) => !c)}>{compare ? "Hide comparison" : "Compare with original"}</Btn>}
          <Btn icon="plus" onClick={() => onEdit(null)}>Add</Btn>
        </div>
      }>
      {days.length > 1 && (
        <div className="-mx-1 mb-5 flex gap-2 overflow-x-auto px-1 pb-1" role="navigation" aria-label="Jump to day">
          {days.map((d, n) => {
            const list = live.filter((i) => i.start.startsWith(d));
            const dn = list.filter((i) => i.completed).length;
            const full = list.length > 0 && dn === list.length;
            return (
              <button key={d} onClick={() => jump(d)}
                className={`flex shrink-0 flex-col items-start rounded-xl border px-3.5 py-2 text-left transition hover:-translate-y-0.5 hover:shadow-sm ${hereDay === d ? "border-sky-300 bg-sky-50" : full ? "border-emerald-200 bg-emerald-50/60" : "border-slate-200 bg-white"}`}>
                <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Day {n + 1}</span>
                <span className="text-sm font-semibold text-slate-900">{day(d)}</span>
                <span className={`mt-0.5 text-[11px] ${full ? "text-emerald-700" : "text-slate-500"}`}>{full ? "All done" : `${dn}/${list.length} done`}</span>
              </button>
            );
          })}
        </div>
      )}
      {compare && trip.baseline && (
        <div className="mb-5 animate-fade-up">
          <CompareTable heads={["Originally planned", "Now"]} rows={baselineRows(trip)}
            caption={`Original saved ${trip.baseline.taken_at.replace("T", " ").slice(0, 16)}, before the first change. Done stops are locked.`} />
        </div>
      )}
      {trip.items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 px-6 py-12 text-center text-sm text-slate-500">
          <span className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-teal-50 text-teal-600"><Icon name="calendar" className="h-6 w-6" /></span>
          <p className="font-semibold text-slate-900">Your itinerary is empty</p>
          <p className="mt-1">Start with how you arrive (a train or flight), then your hotel and plans.<br />Or ask the assistant: <i>“Add a train from Bengaluru at 07:00 arriving Mysuru 09:30 on 20 Nov”</i>.</p>
          <Btn icon="plus" className="mt-4" onClick={() => onEdit(null)}>Add your first stop</Btn>
        </div>
      ) : days.map((d, n) => {
        const list = trip.items.filter((i) => i.start.startsWith(d));
        return (
          <div key={d} id={`day-${d}`} className="mb-4 scroll-mt-20 last:mb-0">
            <div className="sticky top-16 z-10 -mx-2 mb-2 flex items-center gap-3 bg-white/95 px-2 py-2 backdrop-blur">
              <span className="rounded-lg bg-slate-900 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-white">Day {n + 1}</span>
              <span className="text-sm font-semibold text-slate-900">{day(d)}</span>
              <span className="h-px flex-1 bg-slate-100" />
              <span className="text-xs text-slate-400">{list.filter((i) => i.completed).length}/{list.length} done</span>
            </div>
            <ol>
              {list.map((i, k) => (
                <Stop key={i.id} trip={trip} i={i} r={results[i.id]} here={hereId === i.id} onTrip={onTrip} onEdit={onEdit} last={k === list.length - 1}
                  delayOpen={delayFor === i.id} setDelay={(b) => setDelayFor(b ? i.id : null)} />
              ))}
            </ol>
          </div>
        );
      })}
      {hereId === "__end" && <Notice tone="green" icon="check" className="mt-3">Everything is done. Enjoy the rest of your trip!</Notice>}
    </Card>
  );
}

function DraftPanel({ d }: { d: PlanDraft }) {
  const link = (url?: string) => url && /^https?:\/\//.test(url)
    ? <a href={url} target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center text-teal-700 hover:underline"><Icon name="external" className="h-3.5 w-3.5" /></a> : null;
  return (
    <Card title="Drafted from your idea" icon="sparkle"
      sub={d.live_search ? "Researched with live web search, then checked by the timing engine. Nothing is booked yet." : "Web search wasn't available, so this uses the AI's general knowledge. Check details before booking."}>
      <p className="mb-4 rounded-xl bg-slate-50 px-3.5 py-2.5 text-sm italic text-slate-600">“{d.idea}”</p>
      {d.assumptions.length > 0 && (
        <div className="mb-4"><h3 className="mb-1 text-sm font-semibold text-slate-900">What I assumed</h3>
          <ul className="list-disc space-y-0.5 pl-5 text-sm text-slate-600">{d.assumptions.map((a, n) => <li key={n}>{a}</li>)}</ul></div>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {d.stays.length > 0 && (
          <div><h3 className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold text-slate-900"><Icon name="bed" className="h-4 w-4 text-teal-600" /> Where to stay</h3>
            <ul className="space-y-2 text-sm">{d.stays.slice(0, 4).map((s, n) => (
              <li key={n}><b className="text-slate-800">{s.name}</b>{s.town && <span className="text-slate-500">, {s.town}</span>}{link(s.url)}
                <span className="block text-xs text-slate-500">{[s.price, s.why].filter(Boolean).join(" · ")}</span></li>))}</ul></div>
        )}
        {d.getting_there.length > 0 && (
          <div><h3 className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold text-slate-900"><Icon name="route" className="h-4 w-4 text-teal-600" /> Getting there and around</h3>
            <ul className="space-y-2 text-sm">{d.getting_there.slice(0, 4).map((g, n) => (
              <li key={n}><b className="text-slate-800">{[g.from, g.to].filter(Boolean).join(" → ")}</b>{link(g.url)}
                <span className="block text-xs text-slate-500">{[g.mode, g.option, g.duration, g.price].filter(Boolean).join(" · ")}</span></li>))}</ul></div>
        )}
      </div>
      {d.tips.length > 0 && (
        <div className="mt-4"><h3 className="mb-1 text-sm font-semibold text-slate-900">Good to know</h3>
          <ul className="list-disc space-y-0.5 pl-5 text-sm text-slate-600">{d.tips.slice(0, 5).map((t, n) => <li key={n}>{t}</li>)}</ul></div>
      )}
      {d.sources.length > 0 && (
        <details className="mt-4 text-sm"><summary className="cursor-pointer font-medium text-slate-700">Sources ({d.sources.length})</summary>
          <ul className="mt-2 space-y-1">{d.sources.map((s, n) => (
            <li key={n}><a href={s.url} target="_blank" rel="noreferrer" className="text-teal-700 hover:underline">{s.title || s.url}</a></li>))}</ul></details>
      )}
      <p className="mt-4 text-xs text-slate-500">Stays and journeys are on your booking checklist under <b>Bookings to sort out</b>. Mark each one confirmed with its reference once you've booked it.</p>
    </Card>
  );
}

export default function TripView({ id, back }: { id: string; back: () => void }) {
  const [trip, setTrip] = useState<Trip | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<Item | null | undefined>(undefined);
  const [prefs, setPrefs] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const [rain, setRain] = useState<{ day: string; max_chance?: number; outdoor_at_risk: string[]; rainy_hours?: number[] }[]>([]);
  const [side, setSide] = useState<"map" | "chat">("map");

  useEffect(() => { api.trip(id).then(setTrip).catch((e) => setErr(e.message)); }, [id]);
  useEffect(() => { if (trip?.items.length) api.weather(id).then((w) => setRain(w.days.filter((d) => d.outdoor_at_risk.length))).catch(() => undefined); }, [id, trip?.items.length]);

  if (err) return (
    <div className="mx-auto max-w-xl p-10">
      <Notice tone="red" icon="alert">{err} <button className="ml-1 font-semibold underline" onClick={back}>Back to my trips</button></Notice>
    </div>
  );
  if (!trip) return (
    <div className="mx-auto max-w-[1400px] space-y-4 px-4 py-6 sm:px-6">
      <div className="h-44 animate-pulse rounded-3xl bg-slate-200/70" />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.85fr)_minmax(340px,1fr)]"><div className="h-96 animate-pulse rounded-2xl bg-slate-200/60" /><div className="h-96 animate-pulse rounded-2xl bg-slate-200/60" /></div>
    </div>
  );

  const open = [...trip.disruptions].reverse().find((d) => ["analyzed", "planned", "no_plan"].includes(d.status)) ?? null;
  const results = open ? open.impact.results : trip.view.results;
  const plan = open?.plans.find((p) => p.id === focus) ?? null;
  const attention = trip.actions.filter((a) => a.status === "needs_attention").length;
  const pending = trip.actions.filter((a) => a.status === "pending").length;
  const live = trip.items.filter((i) => i.status !== "cancelled");
  const confirmed = live.filter((i) => i.booking.status === "confirmed").length;
  const doneN = live.filter((i) => i.completed).length;
  const warnings = live.filter((i) => !i.completed && WARN.includes(results[i.id]?.status ?? "")).length;
  const days = new Set(trip.items.map((i) => i.start.slice(0, 10))).size;
  const pct = live.length ? Math.round((100 * doneN) / live.length) : 0;
  const p = trip.preferences;

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-14 pt-5 sm:px-6">
      <button onClick={back} className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 text-sm text-slate-500 transition hover:text-slate-900"><Icon name="back" /> All trips</button>

      {/* cover header */}
      <section className="relative mb-6 animate-fade-up overflow-hidden rounded-3xl shadow-lg shadow-slate-900/5">
        <Cover seed={trip.title + trip.id} animated className="absolute inset-0 h-full w-full" />
        <div className="absolute inset-0 bg-gradient-to-r from-slate-900/50 via-slate-900/20 to-transparent" />
        <div className="relative flex flex-wrap items-end justify-between gap-5 px-6 py-7 text-white sm:px-8">
          <div className="min-w-0 max-w-3xl">
            <div className="mb-2 flex flex-wrap gap-2 text-xs font-medium">
              <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2.5 py-1 ring-1 ring-white/20 backdrop-blur"><Icon name="pin" className="h-3.5 w-3.5" />{trip.destination || "No destination"}</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2.5 py-1 ring-1 ring-white/20 backdrop-blur"><Icon name="users" className="h-3.5 w-3.5" />{p.travelers} traveler{p.travelers > 1 ? "s" : ""} · {p.group}</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2.5 py-1 capitalize ring-1 ring-white/20 backdrop-blur">{p.interests.slice(0, 3).join(", ")} · {p.pace}</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight drop-shadow-sm sm:text-3xl">{trip.title}</h1>
            <p className="mt-1 text-sm text-white/85">Extra budget for changes {money(p.extra_budget, p.currency)}</p>
          </div>
          <div className="flex flex-col items-start gap-3 sm:items-end">
            <button onClick={() => setPrefs(true)} className="inline-flex items-center gap-1.5 rounded-xl bg-white px-3.5 py-2 text-sm font-semibold text-slate-900 shadow-sm transition hover:bg-teal-50">
              <Icon name="sliders" /> Edit preferences
            </button>
            <div className="w-56">
              <div className="mb-1 flex justify-between text-xs text-white/90"><span>Trip progress</span><span className="font-semibold">{pct}%</span></div>
              <div className="h-2 overflow-hidden rounded-full bg-white/25" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Trip progress">
                <div className="h-full rounded-full bg-white transition-all duration-700" style={{ width: `${pct}%` }} />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* at a glance */}
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-5" aria-label="Trip at a glance">
        <Stat icon="check" tone="green" label={`of ${live.length} stops done`} value={doneN} />
        <Stat icon="calendar" tone="teal" label="days" value={days} />
        <Stat icon="file" tone="sky" label={`bookings confirmed${pending ? ` · ${pending} pending` : ""}`} value={confirmed} />
        <Stat icon="alert" tone={warnings ? "amber" : "slate"} label={warnings ? "timing warnings" : "no timing warnings"} value={warnings} />
        <Stat icon="clock" tone={attention ? "red" : "slate"} label="need your attention" value={attention} />
      </div>

      {rain.length > 0 && !open && (
        <Notice tone="sky" icon="rain" className="mb-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>Rain forecast ({rain[0].max_chance}% chance) on {day(rain[0].day)} while you're outdoors: <b>{rain[0].outdoor_at_risk.join(", ")}</b>.</span>
            <Btn onClick={async () => setTrip(await api.reportChange(trip.id, `Rain is forecast on ${rain[0].day} around ${rain[0].rainy_hours?.[0] ?? 14}:00 to ${(rain[0].rainy_hours?.slice(-1)[0] ?? 18) + 1}:00`))}>Plan around the rain</Btn>
          </div>
        </Notice>
      )}

      {open && (
        <button onClick={() => document.getElementById("recovery")?.scrollIntoView({ behavior: "smooth", block: "start" })}
          className="mb-5 flex w-full animate-fade-up items-center gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-left text-sm text-red-900 transition hover:bg-red-100/70">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-white text-red-600 ring-1 ring-red-200"><Icon name="alert" /></span>
          <span className="min-w-0 flex-1"><b>Disruption in progress:</b> {open.summary}</span>
          <span className="shrink-0 font-semibold">{open.status === "planned" ? "Review plans" : "See impact"} ↓</span>
        </button>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.85fr)_minmax(340px,1fr)]">
        <div className="min-w-0 space-y-6">
          {trip.plan_draft && <DraftPanel d={trip.plan_draft} />}
          <Itinerary trip={trip} onTrip={setTrip} results={results} onEdit={(i) => setEditing(i)} />
          <div id="recovery" className="scroll-mt-20 space-y-6">
            <Recovery trip={trip} d={open} onTrip={setTrip} focus={focus} setFocus={(f) => { setFocus(f); if (f) setSide("map"); }} />
            <Tasks trip={trip} onTrip={setTrip} />
          </div>
          <details className="group rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm">
            <summary className="flex cursor-pointer list-none items-center justify-between font-medium text-slate-700">
              <span className="flex items-center gap-2"><Icon name="file" className="h-4 w-4 text-slate-400" /> Trip history</span>
              <span className="text-xs text-slate-400 group-open:hidden">Show</span><span className="hidden text-xs text-slate-400 group-open:inline">Hide</span>
            </summary>
            <ol className="mt-3 max-h-64 space-y-1.5 overflow-y-auto text-xs text-slate-600">
              {[...trip.log].reverse().map((l, n) => <li key={n} className="flex gap-3"><span className="shrink-0 tabular-nums text-slate-400">{l.at.slice(5, 16).replace("T", " ")}</span><span>{l.text}</span></li>)}
            </ol>
          </details>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Segmented value={side} onChange={setSide} className="lg:hidden" options={[["map", "Map", "map"], ["chat", "Assistant", "sparkle"]] as const} />
          <div className={`${side === "map" ? "block" : "hidden"} h-[46vh] lg:block lg:h-[40vh]`}>
            <MapView tripId={trip.id} items={trip.items} results={results} plan={plan} dis={open} center={trip.center} />
          </div>
          <div className={`${side === "chat" ? "block" : "hidden"} h-[56vh] lg:block lg:h-[calc(60vh-7rem)] lg:min-h-[360px]`}>
            <Chat trip={trip} onTrip={setTrip} />
          </div>
        </aside>
      </div>

      {editing !== undefined && <ItemEditor trip={trip} item={editing} onClose={() => setEditing(undefined)} onSaved={(t) => { setTrip(t); setEditing(undefined); toast(editing ? "Stop updated" : "Stop added"); }} />}
      {prefs && <PrefsModal trip={trip} onClose={() => setPrefs(false)} onTrip={(t) => { setTrip(t); toast("Preferences saved"); }} />}
    </div>
  );
}
