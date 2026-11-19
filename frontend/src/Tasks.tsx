import { useState } from "react";
import { api } from "./api";
import type { Action, Trip } from "./types";
import { Btn, Card } from "./ui";

const GROUPS: [Action["status"], string, string][] = [
  ["needs_attention", "Needs your attention", "border-amber-200 bg-amber-50/60"],
  ["failed", "Couldn't be done", "border-red-200 bg-red-50/60"],
  ["pending", "Pending: waiting for the provider", "border-sky-200 bg-sky-50/60"],
  ["confirmed", "Confirmed", "border-emerald-200 bg-emerald-50/60"],
];

function Task({ a, trip, onTrip }: { a: Action; trip: Trip; onTrip: (t: Trip) => void }) {
  const [ref, setRef] = useState("");
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = async (status: string, reference?: string) => {
    setBusy(true);
    try { onTrip(await api.action(trip.id, a.id, status, reference)); } finally { setBusy(false); setAsking(false); }
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="font-medium text-slate-900">{a.title}</div>
      <div className="text-xs text-slate-600">{a.detail}</div>
      {a.reference && <div className="mt-1 text-xs text-emerald-700">Ref {a.reference}</div>}
      {asking ? (
        <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); set("confirmed", ref || undefined); }}>
          <input autoFocus value={ref} onChange={(e) => setRef(e.target.value)} placeholder="Confirmation / reference (optional)" className="min-w-0 flex-1 rounded-lg border border-slate-200 px-2 py-1 text-xs focus:border-teal-500 focus:outline-none" />
          <Btn type="submit" className="!px-2 !py-1 text-xs" disabled={busy}>Save</Btn>
        </form>
      ) : (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {a.status === "needs_attention" && <Btn kind="secondary" className="!px-2 !py-1 text-xs" disabled={busy} onClick={() => set("pending")}>I've requested it</Btn>}
          {(a.status === "needs_attention" || a.status === "pending") && <Btn className="!px-2 !py-1 text-xs" disabled={busy} onClick={() => setAsking(true)}>It's confirmed</Btn>}
          {(a.status === "needs_attention" || a.status === "pending") && <Btn kind="danger" className="!px-2 !py-1 text-xs" disabled={busy} onClick={() => set("failed")}>Couldn't do it</Btn>}
          {a.status === "failed" && a.kind !== "cancel" && <Btn className="!px-2 !py-1 text-xs" disabled={busy} onClick={async () => { setBusy(true); try { onTrip(await api.replan(trip.id, a.id)); } finally { setBusy(false); } }}>Find another plan</Btn>}
          {a.status === "failed" && <Btn kind="ghost" className="!px-2 !py-1 text-xs" disabled={busy} onClick={() => set("needs_attention")}>Try again</Btn>}
        </div>
      )}
    </div>
  );
}

export default function Tasks({ trip, onTrip }: { trip: Trip; onTrip: (t: Trip) => void }) {
  if (!trip.actions.length) return null;
  return (
    <Card title="Bookings to sort out" icon="file" sub="Approving a plan updates your itinerary. Booking changes count only once you confirm them here.">
      <div className="grid gap-3 md:grid-cols-2">
        {GROUPS.map(([st, label, cls]) => {
          const list = trip.actions.filter((a) => a.status === st);
          if (!list.length) return null;
          return (
            <div key={st} className={`rounded-2xl border p-3 ${cls}`}>
              <div className="mb-2 text-sm font-semibold text-slate-800">{label} <span className="text-slate-500">({list.length})</span></div>
              <div className="space-y-2">{list.map((a) => <Task key={a.id} a={a} trip={trip} onTrip={onTrip} />)}</div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
