import { useEffect, useState, type ReactNode } from "react";
import type { BookingStatus, Item, SimResult } from "./types";

/* Design tokens (Tailwind classes):
   background slate-50 #F8FAFC · cards white · text slate-900 #0F172A · primary teal-600 #0D9488 · accent sky-600 #0284C7
   borders slate-200 #E2E8F0 · muted slate-500 #64748B · success emerald · warning amber · danger red */

export const hm = (s?: string | null) => (s ? s.slice(11, 16) : "—");
export const day = (s: string) =>
  new Date(s.slice(0, 10) + "T00:00").toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
export const money = (n: number | null | undefined, cur = "INR") =>
  n == null ? "—" : `${cur === "INR" ? "₹" : cur + " "}${Math.round(n).toLocaleString("en-IN")}`;

// Kept for the map pins and plain-text spots.
export const TYPE_ICON: Record<Item["type"], string> = { transport: "🚆", stay: "🏨", activity: "📍", meal: "🍽️", other: "•" };

/* ------------------------------------------------------------------ icons (outline, 24px grid) */

const P = (d: string) => <path d={d} />;
const ICONS: Record<string, ReactNode> = {
  plane: P("M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"),
  train: <>{P("M8 3.1V7a4 4 0 0 0 8 0V3.1")}{P("m9 15-1-1")}{P("m15 15 1-1")}{P("M9 19c-2.8 0-5-2.2-5-5v-4a8 8 0 0 1 16 0v4c0 2.8-2.2 5-5 5Z")}{P("m8 19-2 3")}{P("m16 19 2 3")}</>,
  bed: <>{P("M2 4v16")}{P("M2 8h18a2 2 0 0 1 2 2v10")}{P("M2 17h20")}{P("M6 8v9")}</>,
  pin: <>{P("M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z")}<circle cx="12" cy="10" r="3" /></>,
  meal: <>{P("M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2")}{P("M7 2v20")}{P("M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7")}</>,
  dot: <circle cx="12" cy="12" r="3" />,
  upload: <>{P("M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2")}{P("M12 12v9")}{P("m16 16-4-4-4 4")}</>,
  pencil: <>{P("M12 20h9")}{P("M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z")}</>,
  compass: <><circle cx="12" cy="12" r="10" />{P("m16.2 7.8-2.1 6.3-6.3 2.1 2.1-6.3 6.3-2.1z")}</>,
  map: <>{P("M14.1 5.6a2 2 0 0 0 1.8 0l3.7-1.9A1 1 0 0 1 21 4.6v12.8a1 1 0 0 1-.6.9l-4.5 2.3a2 2 0 0 1-1.8 0l-4.2-2.1a2 2 0 0 0-1.8 0l-3.7 1.8A1 1 0 0 1 3 19.4V6.6a1 1 0 0 1 .6-.9l4.5-2.3a2 2 0 0 1 1.8 0z")}{P("M15 5.8v15")}{P("M9 3.2v15")}</>,
  sparkle: P("M9.9 15.5A2 2 0 0 0 8.5 14l-6.1-1.6a.5.5 0 0 1 0-1L8.5 10A2 2 0 0 0 9.9 8.5l1.6-6.1a.5.5 0 0 1 1 0L14 8.5A2 2 0 0 0 15.5 10l6.1 1.6a.5.5 0 0 1 0 1L15.5 14a2 2 0 0 0-1.4 1.4l-1.6 6.1a.5.5 0 0 1-1 0z"),
  check: P("M20 6 9 17l-5-5"),
  clock: <><circle cx="12" cy="12" r="10" />{P("M12 6v6l4 2")}</>,
  alert: <>{P("m21.7 18-8-14a2 2 0 0 0-3.5 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3")}{P("M12 9v4")}{P("M12 17h.01")}</>,
  rain: <>{P("M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2")}{P("M16 14v6")}{P("M8 14v6")}{P("M12 16v6")}</>,
  x: <>{P("M18 6 6 18")}{P("m6 6 12 12")}</>,
  lock: <><rect x="3" y="11" width="18" height="11" rx="2" />{P("M7 11V7a5 5 0 0 1 10 0v4")}</>,
  calendar: <><rect x="3" y="4" width="18" height="18" rx="2" />{P("M16 2v4")}{P("M8 2v4")}{P("M3 10h18")}</>,
  logout: <>{P("M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4")}{P("m16 17 5-5-5-5")}{P("M21 12H9")}</>,
  activity: P("M22 12h-4l-3 9L9 3l-3 9H2"),
  send: <>{P("m22 2-7 20-4-9-9-4Z")}{P("M22 2 11 13")}</>,
  back: <>{P("m12 19-7-7 7-7")}{P("M19 12H5")}</>,
  more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
  ban: <><circle cx="12" cy="12" r="10" />{P("m4.9 4.9 14.2 14.2")}</>,
  refresh: <>{P("M3 12a9 9 0 0 1 9-9 9.8 9.8 0 0 1 6.7 2.7L21 8")}{P("M21 3v5h-5")}{P("M21 12a9 9 0 0 1-9 9 9.8 9.8 0 0 1-6.7-2.7L3 16")}{P("M8 16H3v5")}</>,
  file: <>{P("M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z")}{P("M14 2v4a2 2 0 0 0 2 2h4")}{P("M16 13H8")}{P("M16 17H8")}</>,
  sliders: <>{P("M4 21v-7")}{P("M4 10V3")}{P("M12 21v-9")}{P("M12 8V3")}{P("M20 21v-5")}{P("M20 12V3")}{P("M2 14h4")}{P("M10 8h4")}{P("M18 16h4")}</>,
  plus: <>{P("M5 12h14")}{P("M12 5v14")}</>,
  users: <>{P("M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2")}<circle cx="9" cy="7" r="4" />{P("M22 21v-2a4 4 0 0 0-3-3.9")}{P("M16 3.1a4 4 0 0 1 0 7.8")}</>,
  trash: <>{P("M3 6h18")}{P("M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6")}{P("M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2")}</>,
  route: <><circle cx="6" cy="19" r="3" />{P("M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15")}<circle cx="18" cy="5" r="3" /></>,
  external: <>{P("M15 3h6v6")}{P("M10 14 21 3")}{P("M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6")}</>,
  layers: <>{P("m12 2 10 5-10 5L2 7Z")}{P("m2 17 10 5 10-5")}{P("m2 12 10 5 10-5")}</>,
};
export type IconName = keyof typeof ICONS;

export function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
      className={`shrink-0 ${/\bh-\d/.test(className) ? "" : "h-4 w-4 "}${className}`} aria-hidden="true">
      {ICONS[name]}
    </svg>
  );
}

export function Logo({ size = "md" }: { size?: "md" | "lg" }) {
  return (
    <span className="flex items-center gap-2.5">
      <span className={`grid place-items-center rounded-xl bg-teal-600 text-white shadow-sm ${size === "lg" ? "h-10 w-10" : "h-9 w-9"}`}>
        <Icon name="plane" className="h-5 w-5" />
      </span>
      <span className={`font-bold tracking-tight text-slate-900 ${size === "lg" ? "text-xl" : "text-lg"}`}>Disruption Copilot</span>
    </span>
  );
}

const TYPE_STYLE: Record<Item["type"], [IconName, string]> = {
  transport: ["train", "bg-sky-50 text-sky-700"],
  stay: ["bed", "bg-teal-50 text-teal-700"],
  activity: ["pin", "bg-violet-50 text-violet-700"],
  meal: ["meal", "bg-orange-50 text-orange-700"],
  other: ["dot", "bg-slate-100 text-slate-600"],
};

export function TypeIcon({ type, done, size = "md" }: { type: string; done?: boolean; size?: "sm" | "md" }) {
  const [name, cls] = TYPE_STYLE[type as Item["type"]] ?? TYPE_STYLE.other;
  const box = size === "sm" ? "h-6 w-6" : "h-8 w-8";
  return (
    <span className={`grid ${box} shrink-0 place-items-center rounded-full ${done ? "bg-emerald-500 text-white" : cls}`}>
      <Icon name={done ? "check" : name} className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} />
    </span>
  );
}

/* ------------------------------------------------------------------ pills */

export type Tone = "green" | "sky" | "amber" | "red" | "slate" | "violet" | "teal";
const TONES: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  sky: "bg-sky-50 text-sky-700 ring-sky-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  slate: "bg-slate-50 text-slate-600 ring-slate-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
  teal: "bg-teal-50 text-teal-700 ring-teal-200",
};

export function Pill({ tone = "slate", icon, children, title }: { tone?: Tone; icon?: IconName; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${TONES[tone]}`}>
      {icon && <Icon name={icon} className="h-3 w-3" />}
      {children}
    </span>
  );
}

const BOOKING: Record<BookingStatus, { label: string; tone: Tone; icon: IconName } | null> = {
  confirmed: { label: "Confirmed", tone: "green", icon: "check" },
  pending: { label: "Pending", tone: "sky", icon: "clock" },
  needs_attention: { label: "Needs attention", tone: "amber", icon: "alert" },
  cancelled: { label: "Cancelled", tone: "slate", icon: "ban" },
  none: null,
};

export function BookingChip({ status }: { status: BookingStatus }) {
  const b = BOOKING[status];
  if (!b) return null;
  return <Pill tone={b.tone} icon={b.icon} title="Booking status">{b.label}</Pill>;
}

const FEAS: Record<SimResult["status"], { label: string; tone: Tone } | null> = {
  completed: { label: "Done", tone: "slate" },
  in_progress: { label: "Now", tone: "sky" },
  unaffected: null,
  disrupted: { label: "Changed", tone: "amber" },
  shifted: { label: "Shifts later", tone: "sky" },
  at_risk: { label: "At risk", tone: "amber" },
  affected: { label: "Affected", tone: "red" },
  skipped: { label: "Not marked done", tone: "amber" },
  tight: { label: "Tight", tone: "amber" },
  conflict: { label: "Plan conflict", tone: "red" },
};

export function FeasBadge({ r }: { r?: SimResult }) {
  if (!r) return null;
  const f = r.status === "completed" && r.assumed ? { label: "Past", tone: "slate" as Tone } : FEAS[r.status];
  if (!f) return null;
  return <Pill tone={f.tone} icon={f.tone === "red" || f.tone === "amber" ? "alert" : undefined} title="Schedule check">{f.label}</Pill>;
}

export const IMPACT_STYLE: Record<string, string> = {
  affected: "border-red-200 bg-red-50",
  at_risk: "border-amber-200 bg-amber-50",
  shifted: "border-sky-200 bg-sky-50",
  disrupted: "border-orange-200 bg-orange-50",
  unaffected: "border-emerald-200 bg-emerald-50",
  completed: "border-slate-200 bg-slate-50",
  skipped: "border-amber-200 bg-amber-50",
  tight: "border-amber-200 bg-amber-50",
  conflict: "border-red-200 bg-red-50",
  in_progress: "border-sky-200 bg-sky-50",
};

/* ------------------------------------------------------------------ layout + controls */

export function Card({ title, sub, right, icon, children, className = "", id }: {
  title?: ReactNode; sub?: ReactNode; right?: ReactNode; icon?: IconName; children: ReactNode; className?: string; id?: string;
}) {
  return (
    <section id={id} className={`rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${className}`}>
      {(title || right) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            {icon && <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-teal-50 text-teal-700"><Icon name={icon} /></span>}
            <div className="min-w-0">
              {title && <h2 className="text-base font-semibold text-slate-900">{title}</h2>}
              {sub && <p className="mt-0.5 text-sm text-slate-500">{sub}</p>}
            </div>
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Btn({ children, onClick, kind = "primary", disabled, className = "", type = "button", title, icon }: {
  children: ReactNode; onClick?: () => void; kind?: "primary" | "secondary" | "ghost" | "danger" | "dark"; disabled?: boolean; className?: string;
  type?: "button" | "submit"; title?: string; icon?: IconName;
}) {
  const k = {
    primary: "bg-teal-600 text-white shadow-sm hover:bg-teal-700",
    dark: "bg-slate-900 text-white hover:bg-slate-700",
    secondary: "border border-slate-200 bg-white text-slate-800 hover:border-slate-300 hover:bg-slate-50",
    ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
    danger: "text-red-700 hover:bg-red-50",
  }[kind];
  return (
    <button type={type} title={title} disabled={disabled} onClick={onClick}
      className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${k} ${className}`}>
      {icon && <Icon name={icon} />}
      {children}
    </button>
  );
}

/** Segmented tabs (as in the trip-creation card). */
export function Segmented<K extends string>({ value, onChange, options, className = "" }: {
  value: K; onChange: (k: K) => void; options: readonly (readonly [K, string, IconName?])[]; className?: string;
}) {
  return (
    <div role="tablist" className={`grid gap-1 rounded-xl bg-slate-100 p-1 text-sm font-medium ${className}`} style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>
      {options.map(([k, label, icon]) => (
        <button key={k} type="button" role="tab" aria-selected={value === k} onClick={() => onChange(k)}
          className={`flex items-center justify-center gap-2 rounded-lg px-2 py-2 transition ${value === k ? "bg-white text-teal-700 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}>
          {icon && <Icon name={icon} />}<span className="truncate">{label}</span>
        </button>
      ))}
    </div>
  );
}

/** Underlined tabs (as in the admin monitor). */
export function Tabs<K extends string>({ value, onChange, options }: { value: K; onChange: (k: K) => void; options: readonly (readonly [K, string])[] }) {
  return (
    <div role="tablist" className="flex gap-6 border-b border-slate-200 text-sm font-medium">
      {options.map(([k, label]) => (
        <button key={k} role="tab" aria-selected={value === k} onClick={() => onChange(k)}
          className={`-mb-px border-b-2 pb-2.5 pt-1 transition ${value === k ? "border-teal-600 text-teal-700" : "border-transparent text-slate-500 hover:text-slate-900"}`}>
          {label}
        </button>
      ))}
    </div>
  );
}

export const inputCls = "w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 transition focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100";

export function Spinner({ label, light }: { label?: string; light?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-2 text-sm ${light ? "text-white" : "text-slate-500"}`} role="status">
      <span className={`h-4 w-4 animate-spin rounded-full border-2 ${light ? "border-white/40 border-t-white" : "border-slate-200 border-t-teal-600"}`} />
      {label}
    </span>
  );
}

export function Notice({ tone = "slate", icon, children, className = "" }: { tone?: Tone; icon?: IconName; children: ReactNode; className?: string }) {
  const cls: Record<Tone, string> = {
    green: "border-emerald-200 bg-emerald-50 text-emerald-900", sky: "border-sky-200 bg-sky-50 text-sky-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900", red: "border-red-200 bg-red-50 text-red-800",
    slate: "border-slate-200 bg-slate-50 text-slate-700", violet: "border-violet-200 bg-violet-50 text-violet-900",
    teal: "border-teal-200 bg-teal-50 text-teal-900",
  };
  return (
    <div role={tone === "red" ? "alert" : undefined} className={`flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm ${cls[tone]} ${className}`}>
      {icon && <Icon name={icon} className="mt-0.5 h-4 w-4" />}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ toasts (feedback after an action) */

type ToastMsg = { id: number; text: ReactNode; tone: "green" | "red" | "sky" | "amber"; sub?: ReactNode };
let toastId = 0;
export function toast(text: ReactNode, tone: ToastMsg["tone"] = "green", sub?: ReactNode) {
  window.dispatchEvent(new CustomEvent("copilot:toast", { detail: { id: ++toastId, text, tone, sub } }));
}

export function Toaster() {
  const [list, setList] = useState<ToastMsg[]>([]);
  useEffect(() => {
    const on = (e: Event) => {
      const t = (e as CustomEvent<ToastMsg>).detail;
      setList((l) => [...l.slice(-2), t]);
      setTimeout(() => setList((l) => l.filter((x) => x.id !== t.id)), 4200);
    };
    window.addEventListener("copilot:toast", on);
    return () => window.removeEventListener("copilot:toast", on);
  }, []);
  const icon: Record<ToastMsg["tone"], [IconName, string]> = {
    green: ["check", "bg-emerald-500"], red: ["alert", "bg-red-500"], sky: ["sparkle", "bg-sky-500"], amber: ["clock", "bg-amber-500"],
  };
  return (
    <div className="pointer-events-none fixed bottom-5 left-1/2 z-[2000] flex w-[min(92vw,420px)] -translate-x-1/2 flex-col gap-2" aria-live="polite">
      {list.map((t) => (
        <div key={t.id} className="pointer-events-auto flex animate-toast-in items-start gap-3 rounded-2xl bg-slate-900 px-4 py-3 text-sm text-white shadow-2xl shadow-slate-900/30">
          <span className={`mt-0.5 grid h-6 w-6 shrink-0 animate-pop place-items-center rounded-full ${icon[t.tone][1]}`}><Icon name={icon[t.tone][0]} className="h-3.5 w-3.5" /></span>
          <div className="min-w-0"><div className="font-medium">{t.text}</div>{t.sub && <div className="mt-0.5 text-xs text-slate-300">{t.sub}</div>}</div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ trip covers */

const COVERS = [
  ["#0D9488", "#0284C7"], ["#0F766E", "#14B8A6"], ["#0369A1", "#38BDF8"], ["#115E59", "#0284C7"], ["#0E7490", "#2DD4BF"], ["#1E3A8A", "#0D9488"],
];
export const coverOf = (key: string) => {
  let h = 0;
  for (const c of key) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return COVERS[h % COVERS.length];
};

/** A calm generated "travel" cover: gradient, hills and a dotted route with pins. Same trip, same cover. */
export function Cover({ seed, className = "", animated }: { seed: string; className?: string; animated?: boolean }) {
  const [a, b] = coverOf(seed);
  const id = `g${seed.replace(/[^a-z0-9]/gi, "").slice(0, 12)}`;
  let h = 0;
  for (const c of seed) h = (h * 17 + c.charCodeAt(0)) >>> 0;
  const y1 = 40 + (h % 25), y2 = 25 + ((h >> 3) % 30), y3 = 45 + ((h >> 6) % 20);
  return (
    <svg viewBox="0 0 400 140" preserveAspectRatio="xMidYMid slice" className={className} aria-hidden="true">
      <defs><linearGradient id={id} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor={a} /><stop offset="1" stopColor={b} /></linearGradient></defs>
      <rect width="400" height="140" fill={`url(#${id})`} />
      <circle cx={320 - (h % 60)} cy="34" r="16" fill="white" opacity=".18" />
      <path d={`M0 ${100 + (h % 10)} C 80 ${78 + (h % 14)}, 150 ${96}, 230 ${80 + ((h >> 2) % 12)} S 360 70, 400 86 L400 140 L0 140Z`} fill="white" opacity=".12" />
      <path d={`M0 ${118} C 100 ${102 + (h % 8)}, 200 ${124}, 300 ${106} S 380 104, 400 110 L400 140 L0 140Z`} fill="white" opacity=".14" />
      <path d={`M40 ${y1 + 50} Q 130 ${y2}, 200 ${y3 + 20} T 360 ${y2 + 10}`} fill="none" stroke="white" strokeWidth="2.5" strokeDasharray="2 9" strokeLinecap="round" opacity=".85"
        vectorEffect="non-scaling-stroke" className={animated ? "animate-dash" : ""} />
      {[[40, y1 + 50], [200, y3 + 20], [360, y2 + 10]].map(([x, y], n) => (
        <g key={n} transform={`translate(${x} ${y})`}><circle r={animated ? 3.5 : 7} fill="white" opacity=".25" /><circle r={animated ? 1.8 : 3.5} fill="white" /></g>
      ))}
    </svg>
  );
}

export function Stat({ icon, label, value, tone = "slate" }: { icon: IconName; label: string; value: ReactNode; tone?: "slate" | "green" | "amber" | "red" | "sky" | "teal" }) {
  const t = { slate: "bg-slate-100 text-slate-600", green: "bg-emerald-50 text-emerald-600", amber: "bg-amber-50 text-amber-600",
    red: "bg-red-50 text-red-600", sky: "bg-sky-50 text-sky-600", teal: "bg-teal-50 text-teal-600" }[tone];
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3">
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${t}`}><Icon name={icon} className="h-5 w-5" /></span>
      <div className="min-w-0"><div className="text-xl font-bold leading-tight tabular-nums text-slate-900">{value}</div><div className="truncate text-xs text-slate-500">{label}</div></div>
    </div>
  );
}
