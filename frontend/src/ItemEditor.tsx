import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Item, Place, Trip } from "./types";
import { Btn } from "./ui";

function PlaceSearch({ label, value, onChange, near }: { label: string; value: Place | null; onChange: (p: Place | null) => void; near?: { lat: number; lng: number } | null }) {
  const [q, setQ] = useState(value?.name ?? "");
  const [res, setRes] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const timer = useRef<number>();
  useEffect(() => { setQ(value?.name ?? ""); }, [value?.name]);
  const search = (text: string) => {
    setQ(text);
    window.clearTimeout(timer.current);
    if (text.trim().length < 3) return setRes([]);
    timer.current = window.setTimeout(() => api.places(text, near).then((r) => { setRes(r.results); setOpen(true); }).catch(() => setRes([])), 350);
  };
  return (
    <label className="relative block text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <input value={q} onChange={(e) => search(e.target.value)} onFocus={() => res.length && setOpen(true)} placeholder="Search a place, station, hotel…"
        className="mt-1 w-full rounded-xl border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100 px-3 py-2" />
      {value?.lat != null && <span className="absolute right-2 top-8 text-xs text-emerald-600">✓ on map</span>}
      {value && value.lat == null && <span className="absolute right-2 top-8 text-xs text-amber-600">not located</span>}
      {open && res.length > 0 && (
        <ul className="absolute z-30 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg">
          {res.map((p) => (
            <li key={p.place_id ?? p.name}>
              <button type="button" onClick={() => { onChange(p); setQ(p.name); setOpen(false); }} className="w-full px-3 py-2 text-left hover:bg-slate-50">
                <div className="font-medium text-slate-800">{p.name}</div>
                <div className="text-xs text-slate-500">{p.address}</div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </label>
  );
}

type Draft = Omit<Item, "id" | "status"> & { id?: string };

const blank = (date: string): Draft => ({
  type: "activity", title: "", start: `${date}T10:00`, end: `${date}T11:30`, location: null, origin: null, fixed: false,
  priority: "normal", indoor: null, notes: "", booking: { status: "none", provider: "", reference: "", cost: null },
});

export default function ItemEditor({ trip, item, onClose, onSaved }: { trip: Trip; item: Item | null; onClose: () => void; onSaved: (t: Trip) => void }) {
  const lastDate = trip.items.length ? trip.items[trip.items.length - 1].start.slice(0, 10) : new Date().toISOString().slice(0, 10);
  const [d, setD] = useState<Draft>(item ? { ...item, booking: { ...item.booking } } : blank(lastDate));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (patch: Partial<Draft>) => setD((x) => ({ ...x, ...patch }));
  const near = trip.center ?? null;

  const save = async () => {
    if (!d.title.trim()) return setErr("Give it a name.");
    setBusy(true);
    setErr(null);
    const booking = { ...d.booking, status: d.booking.reference || d.booking.provider ? (d.booking.status === "none" ? "confirmed" : d.booking.status) : "none" };
    const body: Record<string, unknown> = { ...d, booking, end: d.end || "", location: d.location ?? {}, origin: d.type === "transport" ? d.origin ?? {} : {} };
    delete body.id;
    try {
      onSaved(item ? await api.editItem(trip.id, item.id, body) : await api.addItem(trip.id, body));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[1000] grid place-items-center bg-slate-900/40 p-4 backdrop-blur-[2px]" onClick={onClose}>
      <div className="max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-4 text-lg font-semibold">{item ? "Edit item" : "Add to your trip"}</h2>
        <div className="mb-4 grid grid-cols-5 gap-1 rounded-xl bg-slate-100 p-1 text-xs font-medium">
          {(["transport", "stay", "activity", "meal", "other"] as const).map((t) => (
            <button key={t} onClick={() => set({ type: t, fixed: t === "transport" ? true : d.fixed })}
              className={`rounded-lg py-1.5 capitalize ${d.type === t ? "bg-white text-teal-700 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}>{t}</button>
          ))}
        </div>
        <div className="grid gap-3">
          <label className="text-sm"><span className="font-medium text-slate-700">Name</span>
            <input value={d.title} onChange={(e) => set({ title: e.target.value })} className="mt-1 w-full rounded-xl border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100 px-3 py-2"
              placeholder={d.type === "transport" ? "Train 12007 Chennai → Mysuru" : d.type === "stay" ? "Hotel check-in" : "Mysore Palace tour"} />
          </label>
          {d.type === "transport" && <PlaceSearch label="From" value={d.origin} onChange={(p) => set({ origin: p })} near={near} />}
          <PlaceSearch label={d.type === "transport" ? "To" : "Where"} value={d.location} onChange={(p) => set({ location: p, indoor: p?.indoor ?? d.indoor })} near={near} />
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm"><span className="font-medium text-slate-700">{d.type === "transport" ? "Departs" : d.type === "stay" ? "Check-in from" : "Starts"}</span>
              <input type="datetime-local" value={d.start} onChange={(e) => set({ start: e.target.value })} className="mt-1 w-full rounded-xl border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100 px-2 py-2" />
            </label>
            <label className="text-sm"><span className="font-medium text-slate-700">{d.type === "transport" ? "Arrives" : d.type === "stay" ? "Check-out" : "Ends"}</span>
              <input type="datetime-local" value={d.end ?? ""} onChange={(e) => set({ end: e.target.value })} className="mt-1 w-full rounded-xl border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100 px-2 py-2" />
            </label>
          </div>
          {d.type !== "transport" && d.type !== "stay" && (
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" checked={d.fixed} onChange={(e) => set({ fixed: e.target.checked })} className="h-4 w-4 accent-teal-600" /> Fixed time slot (booked)</label>
              <label className="flex items-center gap-2">
                <span className="font-medium text-slate-700">Indoor?</span>
                <select value={d.indoor == null ? "" : d.indoor ? "yes" : "no"} onChange={(e) => set({ indoor: e.target.value === "" ? null : e.target.value === "yes" })} className="rounded-xl border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100 px-2 py-1">
                  <option value="">Unknown</option><option value="yes">Indoor</option><option value="no">Outdoor</option>
                </select>
              </label>
            </div>
          )}
          <label className="text-sm"><span className="font-medium text-slate-700">How important?</span>
            <select value={d.priority} onChange={(e) => set({ priority: e.target.value as Draft["priority"] })} className="mt-1 w-full rounded-xl border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100 px-3 py-2">
              <option value="must">Must do: never drop it</option><option value="high">High priority</option>
              <option value="normal">Normal</option><option value="optional">Optional: drop first</option>
            </select>
          </label>
          <details className="rounded-lg border border-slate-200 p-3 text-sm" open={!!(d.booking.provider || d.booking.reference)}>
            <summary className="cursor-pointer font-medium text-slate-700">Booking details (optional)</summary>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <input value={d.booking.provider ?? ""} onChange={(e) => set({ booking: { ...d.booking, provider: e.target.value } })} placeholder="Provider (e.g. IRCTC)" className="rounded-xl border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100 px-3 py-2" />
              <input value={d.booking.reference ?? ""} onChange={(e) => set({ booking: { ...d.booking, reference: e.target.value } })} placeholder="Reference / PNR" className="rounded-xl border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100 px-3 py-2" />
              <input type="number" value={d.booking.cost ?? ""} onChange={(e) => set({ booking: { ...d.booking, cost: e.target.value ? Number(e.target.value) : null } })} placeholder="Cost" className="rounded-xl border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100 px-3 py-2" />
            </div>
          </details>
          <textarea value={d.notes} onChange={(e) => set({ notes: e.target.value })} rows={2} placeholder="Notes" className="rounded-xl border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100 px-3 py-2 text-sm" />
        </div>
        {err && <p className="mt-3 text-sm text-red-700">{err}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Btn kind="ghost" onClick={onClose}>Cancel</Btn>
          <Btn onClick={save} disabled={busy}>{busy ? "Saving…" : item ? "Save changes" : "Add item"}</Btn>
        </div>
      </div>
    </div>
  );
}
