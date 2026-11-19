import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { Disruption, Item, Plan, SimResult } from "./types";
import { hm } from "./ui";

type Pt = { lat: number; lng: number; label: string; title: string; time: string; color: string; ring?: string };

const COLORS: Record<string, string> = {
  affected: "#e11d48", at_risk: "#d97706", shifted: "#0284c7", disrupted: "#ea580c", completed: "#94a3b8",
  new: "#7c3aed", moved: "#0284c7", default: "#0f172a",
};

function pin(p: Pt) {
  return L.divIcon({
    className: "",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html: `<div style="width:28px;height:28px;border-radius:9999px;background:${p.color};color:white;font:600 12px Inter,sans-serif;display:grid;place-items:center;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,.35)${p.ring ? `;outline:3px solid ${p.ring}` : ""}">${p.label}</div>`,
  });
}

function Fit({ pts }: { pts: [number, number][] }) {
  const map = useMap();
  const key = pts.map((p) => p.join(",")).join("|");
  useEffect(() => {
    if (pts.length === 1) map.setView(pts[0], 14);
    else if (pts.length > 1) map.fitBounds(L.latLngBounds(pts), { padding: [36, 36], maxZoom: 15 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return null;
}

export default function MapView({ tripId, items, results, plan, dis, center }: {
  tripId: string; items: Item[]; results: Record<string, SimResult>; plan: Plan | null; dis: Disruption | null; center?: { lat: number; lng: number } | null;
}) {
  // Real road geometry between stops from openrouteservice (falls back to straight lines).
  const [roads, setRoads] = useState<{ road: boolean; points: [number, number][] }[]>([]);
  const routeKey = (plan?.id ?? "") + items.map((i) => `${i.id}:${i.status}:${i.location?.lat}`).join("|");
  useEffect(() => {
    let live = true;
    setRoads([]);
    api.routes(tripId, plan?.id).then((r) => live && setRoads(r.segments)).catch(() => undefined);
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId, routeKey]);
  const pts: Pt[] = useMemo(() => {
    if (plan) {
      return plan.schedule.filter((r) => r.location?.lat != null).map((r, i) => ({
        lat: r.location!.lat!, lng: r.location!.lng!, label: String(i + 1), title: r.title, time: hm(r.start),
        color: COLORS[r.tag] ?? COLORS.default,
      }));
    }
    return items.filter((i) => i.status !== "cancelled" && i.location?.lat != null).map((i, n) => ({
      lat: i.location!.lat!, lng: i.location!.lng!, label: String(n + 1), title: i.title, time: hm(i.start),
      color: COLORS[results[i.id]?.status ?? "default"] ?? COLORS.default,
    }));
  }, [items, results, plan]);

  const cands = plan ? [] : dis?.options?.candidates ?? [];
  const removed = plan ? items.filter((i) => plan.removed.some((r) => r.id === i.id) && i.location?.lat != null) : [];
  const line = pts.map((p) => [p.lat, p.lng] as [number, number]);
  const fitPts = line.length ? line : center ? [[center.lat, center.lng] as [number, number]] : [];

  return (
    <div className="relative h-full min-h-[300px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <MapContainer center={fitPts[0] ?? [20.59, 78.96]} zoom={fitPts.length ? 13 : 4} className="h-full w-full" scrollWheelZoom>
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Fit pts={fitPts} />
        {roads.length > 0
          ? roads.map((sg, n) => (
              <Polyline key={n} positions={sg.points} pathOptions={{ color: plan ? "#7c3aed" : "#0f172a", weight: 4, opacity: 0.7, dashArray: sg.road ? undefined : "6 8" }} />
            ))
          : line.length > 1 && <Polyline positions={line} pathOptions={{ color: plan ? "#7c3aed" : "#0f172a", weight: 2, opacity: 0.35, dashArray: "4 6" }} />}
        {removed.map((i) => (
          <CircleMarker key={i.id} center={[i.location!.lat!, i.location!.lng!]} radius={9} pathOptions={{ color: "#e11d48", dashArray: "3 3", fillOpacity: 0.1 }}>
            <Tooltip>Dropped: {i.title}</Tooltip>
          </CircleMarker>
        ))}
        {cands.map((c) => (
          <CircleMarker key={c.cid} center={[c.lat, c.lng]} radius={6} pathOptions={{ color: "#7c3aed", fillColor: "#ddd6fe", fillOpacity: 0.9, weight: 1.5 }}>
            <Tooltip>{c.name}{c.indoor ? " · indoor" : ""}{c.rating ? ` · ★${c.rating}` : ""}</Tooltip>
          </CircleMarker>
        ))}
        {pts.map((p, i) => (
          <Marker key={`${p.lat}-${p.lng}-${i}`} position={[p.lat, p.lng]} icon={pin(p)}>
            <Popup><b>{p.time}</b> {p.title}</Popup>
          </Marker>
        ))}
      </MapContainer>
      <a href={api.mapUrl(tripId, plan?.id)} target="_blank" rel="noreferrer"
        className="absolute right-3 top-3 z-[500] rounded-lg border border-slate-200 bg-white/95 px-2.5 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-white hover:text-teal-700">
        Open full map ↗
      </a>
      <div className="pointer-events-none absolute bottom-3 left-3 z-[500] rounded-lg border border-slate-200 bg-white/95 px-2.5 py-1 text-[11px] text-slate-600 shadow-sm">
        {plan ? <>Previewing <b>{plan.name}</b> · <span className="text-violet-700">● new</span> <span className="text-sky-700">● moved</span> <span className="text-rose-600">◌ dropped</span></>
          : cands.length ? <>Your stops · <span className="text-violet-700">● nearby options found</span></> : "Your stops in order"}
      </div>
    </div>
  );
}
