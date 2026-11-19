import { saveSession, token, type User } from "./auth";
import type { ActivityRow, AdminStats, AdminUser, Place, Status, Trip, TripSummary } from "./types";

// Where the backend lives. Empty = same site (local development, or one server for both).
// On Netlify, set VITE_API_URL to the Render address, e.g. https://disruption-copilot.onrender.com
export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

async function req<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  const headers: Record<string, string> = form ? {} : { "Content-Type": "application/json" };
  const tk = token();
  if (tk) headers.Authorization = `Bearer ${tk}`;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api${path}`, {
      method,
      headers,
      body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
    });
  } catch {
    throw new Error("Can't reach the server. If it was asleep, it takes about a minute to wake up: please try again.");
  }
  const data = await res.json().catch(() => ({}));
  // an expired or invalid login sends you back to the login page
  if (res.status === 401 && tk && !path.startsWith("/auth/")) saveSession(null);
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`);
  return data as T;
}

type Session = { token: string; user: User };

const T = (id: string) => `/trips/${encodeURIComponent(id)}`;

export const api = {
  login: (username: string, password: string) => req<Session>("POST", "/auth/login", { username, password }),
  register: (username: string, password: string) => req<Session>("POST", "/auth/register", { username, password }),
  me: () => req<{ user: User }>("GET", "/auth/me"),
  adminStats: (hours = 24) => req<AdminStats>("GET", `/admin/stats?hours=${hours}`),
  adminUsers: () => req<{ users: AdminUser[] }>("GET", "/admin/users"),
  adminActivity: (f: { user?: string; outcome?: string; area?: string; q?: string; limit?: number }) => {
    const p = new URLSearchParams(Object.entries(f).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]));
    return req<{ rows: ActivityRow[] }>("GET", `/admin/activity?${p}`);
  },
  status: () => req<Status>("GET", "/status"),
  trips: () => req<{ trips: TripSummary[] }>("GET", "/trips"),
  createTrip: (title: string, destination: string) => req<Trip>("POST", "/trips", { title, destination }),
  importFile: (file: File) => {
    const f = new FormData();
    f.append("file", file);
    return req<Trip>("POST", "/trips/import", undefined, f);
  },
  importText: (text: string) => req<Trip>("POST", "/trips/import-text", { text }),
  planIdea: (text: string) => req<Trip>("POST", "/trips/plan-idea", { text }),
  trip: (id: string) => req<Trip>("GET", T(id)),
  patchTrip: (id: string, body: Record<string, unknown>) => req<Trip>("PATCH", T(id), body),
  deleteTrip: (id: string) => req<{ deleted: boolean }>("DELETE", T(id)),
  addItem: (id: string, item: Record<string, unknown>) => req<Trip>("POST", `${T(id)}/items`, item),
  editItem: (id: string, itemId: string, item: Record<string, unknown>) => req<Trip>("PUT", `${T(id)}/items/${itemId}`, item),
  deleteItem: (id: string, itemId: string) => req<Trip>("DELETE", `${T(id)}/items/${itemId}`),
  markDone: (id: string, itemId: string, done: boolean, at?: string) => req<Trip>("POST", `${T(id)}/items/${itemId}/done`, { done, at }),
  reportDelay: (id: string, itemId: string, minutes: number, mode: string) =>
    req<Trip>("POST", `${T(id)}/changes/delay`, { item_id: itemId, minutes, mode }),
  resizeDelay: (id: string, did: string, minutes: number) => req<Trip>("PUT", `${T(id)}/changes/${did}/delay`, { minutes }),
  places: (q: string, near?: { lat: number; lng: number } | null) =>
    req<{ results: Place[]; source: string }>("GET", `/places/search?q=${encodeURIComponent(q)}${near ? `&lat=${near.lat}&lng=${near.lng}` : ""}`),
  routes: (id: string, plan?: string | null) =>
    req<{ segments: { from: string; to: string; road: boolean; points: [number, number][] }[] }>("GET", `${T(id)}/routes${plan ? `?plan=${plan}` : ""}`),
  // opens in a new tab (no headers), so the login token travels in the URL
  mapUrl: (id: string, plan?: string | null) =>
    `${API_BASE}/api${T(id)}/map.html?token=${encodeURIComponent(token() ?? "")}${plan ? `&plan=${plan}` : ""}`,
  weather: (id: string) =>
    req<{ days: { day: string; available: boolean; max_chance?: number; rainy_hours?: number[]; outdoor_at_risk: string[] }[] }>("GET", `${T(id)}/weather`),
  reportChange: (id: string, message: string, as_of?: string) => req<Trip>("POST", `${T(id)}/changes`, { message, as_of }),
  editChange: (id: string, did: string, body: Record<string, unknown>) => req<Trip>("PUT", `${T(id)}/changes/${did}`, body),
  makePlans: (id: string, did: string) => req<Trip>("POST", `${T(id)}/changes/${did}/plans`),
  approve: (id: string, did: string, pid: string) => req<Trip>("POST", `${T(id)}/changes/${did}/plans/${pid}/approve`),
  dismiss: (id: string, did: string) => req<Trip>("POST", `${T(id)}/changes/${did}/dismiss`),
  action: (id: string, aid: string, status: string, reference?: string) => req<Trip>("POST", `${T(id)}/actions/${aid}`, { status, reference }),
  replan: (id: string, aid: string) => req<Trip>("POST", `${T(id)}/actions/${aid}/replan`),
  chat: (id: string, message: string, history: { role: string; content: string }[]) =>
    req<{ reply: string; provider: string | null; tools: string[]; trip: Trip }>("POST", `${T(id)}/chat`, { message, history }),
};
