import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { ActivityRow, AdminStats, AdminUser } from "./types";
import { Btn, Card, Icon, Notice, Spinner, Tabs, type IconName } from "./ui";

const AREAS = ["login", "trips", "import", "itinerary", "disruptions", "recovery plans", "bookings", "assistant", "map", "weather", "places", "admin", "status"];

const when = (s?: string | null) => (s ? s.replace("T", " ").slice(5, 16) : "—");
const ms = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)} s` : `${n} ms`);

function StatusPill({ code }: { code: number }) {
  const c = code >= 500 ? "bg-red-50 text-red-700 ring-red-200" : code >= 400 ? "bg-amber-50 text-amber-800 ring-amber-200" : "bg-emerald-50 text-emerald-700 ring-emerald-200";
  return <span className={`inline-block min-w-[42px] rounded-full px-2 py-0.5 text-center text-xs font-semibold tabular-nums ring-1 ring-inset ${c}`}>{code}</span>;
}

function Tile({ label, value, sub, tone = "", icon }: { label: string; value: string | number; sub?: string; tone?: string; icon: IconName }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex items-center justify-between text-xs font-medium text-slate-500">{label}<Icon name={icon} className="h-4 w-4 text-slate-300" /></div>
      <div className={`mt-2 text-2xl font-bold tabular-nums ${tone || "text-slate-900"}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

const callSummary = (calls: ActivityRow["calls"]) =>
  Object.entries(calls)
    .filter(([k]) => !k.startsWith("cache:"))
    .map(([k, c]) => `${k.split(":")[1]} ×${c.n}${c.errors ? ` (${c.errors} failed)` : ""}`)
    .join(" · ");

/** Requests over time: one series, so one hue and no legend (the title names it). Hover a bar for its value. */
function Traffic({ perHour, hours }: { perHour: [string, number][]; hours: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const byDay = hours > 24;
  const map = new Map<string, number>();
  for (const [k, v] of perHour) { const key = byDay ? k.slice(0, 10) : k; map.set(key, (map.get(key) ?? 0) + v); }
  const now = new Date();
  const n = byDay ? Math.ceil(hours / 24) : hours;
  const pad = (x: number) => String(x).padStart(2, "0");
  const keyOf = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` + (byDay ? "" : `T${pad(d.getHours())}`);
  const buckets = Array.from({ length: n }, (_, i) => {
    const d = new Date(now.getTime() - (n - 1 - i) * (byDay ? 864e5 : 36e5));
    return { key: keyOf(d), label: byDay ? d.toLocaleDateString(undefined, { weekday: "short", day: "numeric" }) : `${pad(d.getHours())}:00`, v: map.get(keyOf(d)) ?? 0 };
  });
  const max = Math.max(1, ...buckets.map((b) => b.v));
  const W = 100 / n;
  return (
    <Card title="Requests over time" sub={byDay ? "Per day" : "Per hour"} className="mb-6">
      <div className="relative">
        <svg viewBox={`0 0 100 40`} preserveAspectRatio="none" className="h-36 w-full" role="img" aria-label="Requests per time period">
          <line x1="0" x2="100" y1="39.8" y2="39.8" stroke="#E2E8F0" strokeWidth=".4" vectorEffect="non-scaling-stroke" />
          {buckets.map((b, i) => {
            const h = (b.v / max) * 36;
            return (
              <g key={b.key} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                <rect x={i * W} y="0" width={W} height="40" fill="transparent" />
                {b.v > 0 && <rect x={i * W + W * 0.15} y={40 - h} width={W * 0.7} height={h} rx={Math.min(1.2, W * 0.3)}
                  fill={hover === i ? "#0F766E" : "#0D9488"} />}
              </g>
            );
          })}
        </svg>
        {hover != null && (
          <div className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs text-white shadow-lg"
            style={{ left: `${(hover + 0.5) * W}%` }}>
            <div className="font-semibold tabular-nums">{buckets[hover].v} request{buckets[hover].v === 1 ? "" : "s"}</div>
            <div className="text-slate-300">{buckets[hover].label}</div>
          </div>
        )}
        <div className="mt-1.5 flex justify-between text-[11px] tabular-nums text-slate-400">
          <span>{buckets[0].label}</span><span>{buckets[Math.floor(n / 2)].label}</span><span>{byDay ? "Today" : "Now"}</span>
        </div>
      </div>
    </Card>
  );
}

export default function Admin() {
  const [tab, setTab] = useState<"activity" | "performance" | "users">("activity");
  const [hours, setHours] = useState(24);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [rows, setRows] = useState<ActivityRow[] | null>(null);
  const [filter, setFilter] = useState({ user: "", outcome: "", area: "", q: "" });
  const [live, setLive] = useState(true);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updated, setUpdated] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, u, a] = await Promise.all([api.adminStats(hours), api.adminUsers(), api.adminActivity({ ...filter, limit: 300 })]);
      setStats(s); setUsers(u.users); setRows(a.rows); setError(null); setUpdated(new Date());
    } catch (e: any) {
      setError(e.message);
    }
  }, [hours, filter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!live) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [live, load]);

  const errRate = stats && stats.requests ? Math.round((100 * stats.errors) / stats.requests) : 0;
  const sel = "rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100";

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-8 sm:px-6">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Activity monitor</h1>
          <p className="text-sm text-slate-500">Every request to the backend: who made it, what it did, how long it took, and which AI / map services it used.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Time window" className={sel} value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            <option value={1}>Last hour</option><option value={24}>Last 24 hours</option><option value={168}>Last 7 days</option>
          </select>
          <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
            <input type="checkbox" className="accent-teal-600" checked={live} onChange={(e) => setLive(e.target.checked)} />
            Live {live && <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />}
          </label>
          <Btn kind="secondary" icon="refresh" onClick={load}>Refresh</Btn>
        </div>
      </div>
      {error && <Notice tone="red" icon="alert" className="mb-4">{error}</Notice>}

      {!stats ? <Spinner label="Loading activity…" /> : (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <Tile icon="activity" label="Requests" value={stats.requests} sub={`last ${hours === 168 ? "7 days" : `${hours} h`}`} />
          <Tile icon="users" label="Active users" value={stats.users_active} sub={`${users.length} accounts`} />
          <Tile icon="alert" label="Error rate" value={`${errRate}%`} sub={`${stats.errors} failed requests`} tone={errRate >= 10 ? "text-red-600" : ""} />
          <Tile icon="ban" label="Server errors" value={stats.server_errors} sub="status 500+" tone={stats.server_errors ? "text-red-600" : ""} />
          <Tile icon="clock" label="Response time" value={ms(stats.avg_ms)} sub={`95% under ${ms(stats.p95_ms)}`} />
          <Tile icon="lock" label="Failed logins" value={stats.failed_logins} sub="wrong username or password" tone={stats.failed_logins >= 5 ? "text-amber-600" : ""} />
        </div>
      )}

      {stats && <Traffic perHour={stats.per_hour} hours={hours} />}

      <div className="mb-5">
        <Tabs value={tab} onChange={setTab} options={[["activity", "Request log"], ["performance", "Endpoints & services"], ["users", "Users"]] as const} />
      </div>

      {tab === "activity" && (
        <Card title="Request log" sub={updated ? `Newest first · updated ${updated.toLocaleTimeString()}` : undefined}>
          <div className="mb-4 flex flex-wrap gap-2">
            <select aria-label="User" className={sel} value={filter.user} onChange={(e) => setFilter({ ...filter, user: e.target.value })}>
              <option value="">All users</option>
              {users.map((u) => <option key={u.id} value={u.username}>{u.username}</option>)}
            </select>
            <select aria-label="Outcome" className={sel} value={filter.outcome} onChange={(e) => setFilter({ ...filter, outcome: e.target.value })}>
              <option value="">All outcomes</option><option value="ok">Succeeded</option><option value="client_error">Refused (4xx)</option>
              <option value="server_error">Server errors (5xx)</option><option value="slow">Slow (3 s+)</option>
            </select>
            <select aria-label="Area" className={sel} value={filter.area} onChange={(e) => setFilter({ ...filter, area: e.target.value })}>
              <option value="">All features</option>
              {AREAS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <input aria-label="Search" type="search" className={`${sel} min-w-[200px] flex-1`} placeholder="Search path, trip id, error…" value={filter.q}
              onChange={(e) => setFilter({ ...filter, q: e.target.value })} />
          </div>
          {!rows ? <Spinner /> : rows.length === 0 ? <p className="py-6 text-center text-sm text-slate-500">No requests match.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  <tr className="border-b border-slate-200">
                    <th className="py-2 pr-3">Time</th><th className="pr-3">User</th><th className="pr-3">Request</th><th className="pr-3">Feature</th>
                    <th className="pr-3">Result</th><th className="pr-3 text-right">Took</th><th>Outside calls</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <Fragment key={i}>
                      <tr onClick={() => setOpen(open === i ? null : i)}
                        className={`cursor-pointer border-b border-slate-100 hover:bg-slate-50 ${r.status >= 500 ? "bg-red-50/50" : r.status >= 400 ? "bg-amber-50/40" : ""}`}>
                        <td className="whitespace-nowrap py-2 pr-3 tabular-nums text-slate-500">{when(r.at)}</td>
                        <td className="pr-3">{r.user ?? <span className="text-slate-400">anonymous</span>}{r.role === "admin" && <span className="ml-1.5 rounded bg-sky-50 px-1 text-[10px] font-semibold text-sky-700">admin</span>}</td>
                        <td className="pr-3 font-mono text-xs"><span className="font-semibold">{r.method}</span> {r.route}</td>
                        <td className="pr-3 text-slate-600">{r.area}</td>
                        <td className="pr-3"><StatusPill code={r.status} /></td>
                        <td className={`whitespace-nowrap pr-3 text-right tabular-nums ${r.ms >= 3000 ? "font-semibold text-amber-700" : ""}`}>{ms(r.ms)}</td>
                        <td className="max-w-[320px] truncate text-xs text-slate-500">{callSummary(r.calls) || "—"}</td>
                      </tr>
                      {open === i && (
                        <tr className="border-b border-slate-200 bg-slate-50">
                          <td colSpan={7} className="px-3 py-3 text-xs">
                            <div className="grid gap-3 md:grid-cols-3">
                              <div>
                                <div className="font-semibold text-slate-700">Request</div>
                                <div className="mt-1 break-all font-mono">{r.method} {r.path}</div>
                                <div className="mt-1 text-slate-500">{r.at.replace("T", " ")} · from {r.ip ?? "?"}{r.trip && <> · trip <code>{r.trip}</code></>}</div>
                                {r.error && <div className="mt-2 rounded-lg bg-red-50 p-2 text-red-800"><b>Error:</b> {r.error}</div>}
                              </div>
                              <div>
                                <div className="font-semibold text-slate-700">Outside services used</div>
                                {Object.keys(r.calls).length === 0 ? <div className="mt-1 text-slate-500">None</div> : (
                                  <ul className="mt-1 space-y-0.5">
                                    {Object.entries(r.calls).map(([k, c]) => (
                                      <li key={k}><span className="text-slate-500">{k.split(":")[0] === "cache" ? "cache hit" : k.split(":")[0]}</span> {k.split(":")[1]}: {c.n} call{c.n > 1 ? "s" : ""}
                                        {k.startsWith("cache:") ? "" : `, ${ms(c.ms)}`}{c.errors ? <span className="text-red-600"> · {c.errors} failed</span> : null}</li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                              <div>
                                <div className="font-semibold text-slate-700">Result details</div>
                                {Object.keys(r.notes).length === 0 ? <div className="mt-1 text-slate-500">—</div> : (
                                  <ul className="mt-1 space-y-0.5">{Object.entries(r.notes).map(([k, v]) => <li key={k}><span className="text-slate-500">{k.replace(/_/g, " ")}:</span> {Array.isArray(v) ? v.join(", ") || "—" : String(v)}</li>)}</ul>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "performance" && stats && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Busiest endpoints" sub="Count, typical and worst-case (95th percentile) time, failures">
            <table className="w-full text-left text-sm">
              <thead className="text-[11px] font-semibold uppercase tracking-wide text-slate-500"><tr className="border-b border-slate-200">
                <th className="py-2">Endpoint</th><th className="text-right">Calls</th><th className="text-right">Avg</th><th className="text-right">p95</th><th className="text-right">Failed</th></tr></thead>
              <tbody>{stats.endpoints.map((e) => (
                <tr key={e.endpoint} className="border-b border-slate-100">
                  <td className="py-1.5 pr-2 font-mono text-xs">{e.endpoint}</td><td className="text-right tabular-nums">{e.count}</td>
                  <td className="text-right tabular-nums">{ms(e.avg_ms)}</td><td className={`text-right tabular-nums ${e.p95_ms >= 3000 ? "text-amber-700" : ""}`}>{ms(e.p95_ms)}</td>
                  <td className={`text-right tabular-nums ${e.errors ? "text-red-600" : "text-slate-400"}`}>{e.errors}</td>
                </tr>))}</tbody>
            </table>
          </Card>
          <Card title="Outside services" sub="AI providers and map services called while handling requests">
            {stats.services.length === 0 ? <p className="text-sm text-slate-500">No outside calls yet.</p> : (
              <table className="w-full text-left text-sm">
                <thead className="text-[11px] font-semibold uppercase tracking-wide text-slate-500"><tr className="border-b border-slate-200">
                  <th className="py-2">Service</th><th className="text-right">Calls</th><th className="text-right">Avg time</th><th className="text-right">Failed</th></tr></thead>
                <tbody>{stats.services.map((s) => (
                  <tr key={s.service} className="border-b border-slate-100">
                    <td className="py-1.5"><span className="text-slate-500">{s.service.startsWith("cache:") ? "cache hit" : s.service.split(":")[0]}</span> {s.service.split(":")[1]}</td>
                    <td className="text-right tabular-nums">{s.n}</td><td className="text-right tabular-nums">{s.service.startsWith("cache:") ? "—" : ms(s.avg_ms)}</td>
                    <td className={`text-right tabular-nums ${s.errors ? "text-red-600" : "text-slate-400"}`}>{s.errors}</td>
                  </tr>))}</tbody>
              </table>
            )}
          </Card>
          <Card title="By feature">
            <ul className="space-y-1 text-sm">{stats.areas.map(([a, n]) => (
              <li key={a} className="flex justify-between border-b border-slate-100 py-1"><span>{a}</span><span className="tabular-nums text-slate-600">{n}</span></li>))}</ul>
          </Card>
          <Card title="Most active users">
            <ul className="space-y-1 text-sm">{stats.per_user.map(([u, n]) => (
              <li key={u} className="flex justify-between border-b border-slate-100 py-1"><span>{u}</span><span className="tabular-nums text-slate-600">{n} requests</span></li>))}</ul>
          </Card>
        </div>
      )}

      {tab === "users" && (
        <Card title="Accounts" sub="Click a user to see their requests">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[11px] font-semibold uppercase tracking-wide text-slate-500"><tr className="border-b border-slate-200">
                <th className="py-2 pr-3">User</th><th className="pr-3">Role</th><th className="pr-3 text-right">Trips</th><th className="pr-3 text-right">Requests</th>
                <th className="pr-3 text-right">Failed</th><th className="pr-3">Joined</th><th className="pr-3">Last login</th><th>Last active</th></tr></thead>
              <tbody>{users.map((u) => (
                <tr key={u.id} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50"
                  onClick={() => { setFilter({ ...filter, user: u.username }); setTab("activity"); }}>
                  <td className="py-2 pr-3 font-medium">{u.username}</td>
                  <td className="pr-3">{u.role === "admin" ? <span className="rounded-md bg-sky-100 px-1.5 py-0.5 text-xs font-semibold text-sky-800">admin</span> : "user"}</td>
                  <td className="pr-3 text-right tabular-nums">{u.trips}</td><td className="pr-3 text-right tabular-nums">{u.requests}</td>
                  <td className={`pr-3 text-right tabular-nums ${u.errors ? "text-red-600" : "text-slate-400"}`}>{u.errors}</td>
                  <td className="pr-3 tabular-nums text-slate-600">{when(u.created_at)}</td><td className="pr-3 tabular-nums text-slate-600">{when(u.last_login)}</td>
                  <td className="tabular-nums text-slate-600">{when(u.last_seen)}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
