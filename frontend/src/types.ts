export type Place = {
  name: string;
  address?: string;
  lat: number | null;
  lng: number | null;
  place_id?: string;
  types?: string[];
  indoor?: boolean | null;
  hours?: Record<string, number[][]> | null;
  est_cost?: number | null;
  rating?: number | null;
  maps_url?: string;
  source?: string;
  approximate?: boolean;
};

export type BookingStatus = "confirmed" | "pending" | "needs_attention" | "cancelled" | "none";

export type Item = {
  id: string;
  type: "transport" | "stay" | "activity" | "meal" | "other";
  title: string;
  start: string;
  end: string | null;
  location: Place | null;
  origin: Place | null;
  fixed: boolean;
  priority: "must" | "high" | "normal" | "optional";
  indoor: boolean | null;
  notes: string;
  status: "planned" | "cancelled";
  completed?: boolean;
  completed_at?: string | null;
  source?: string;
  previous_start?: string;
  previous_end?: string | null;
  change_note?: string;
  cancel_reason?: string;
  booking: { status: BookingStatus; provider?: string | null; reference?: string | null; cost?: number | null };
};

export type SimResult = {
  status: "completed" | "in_progress" | "unaffected" | "shifted" | "at_risk" | "affected" | "disrupted" | "skipped" | "tight" | "conflict";
  reason: string;
  why?: string;
  manual?: boolean;
  assumed?: boolean;
  buffer?: number;
  earliest?: string;
  start?: string;
  end?: string;
  travel_min?: number;
  travel_mode?: string;
  travel_source?: string;
};

export type PlanRow = {
  id: string;
  title: string;
  type: string;
  start: string;
  end: string | null;
  was: string | null;
  tag: "kept" | "moved" | "new" | "updated" | "done" | "busy" | "skipped" | "shortened" | "reordered" | "postponed";
  flags: string[];
  why: string;
  was_end?: string | null;
  duration?: number | null;
  travel_min: number;
  travel_mode?: string;
  location: Place | null;
  est_cost?: number | null;
};

export type Plan = {
  id: string;
  name: string;
  summary: string;
  tradeoffs: string[];
  facts: string[];
  source: string;
  schedule: PlanRow[];
  removed: { id: string; title: string; start: string; booked: boolean; why?: string }[];
  pros: string[];
  cons: string[];
  score: number;
  kind: string;
  checks: { ok: boolean; text: string }[];
  dropped: { title: string; why: string }[];
  valid: boolean;
  extra_cost: number;
  travel_min: number;
  day_ends: string;
  counts: { kept: number; moved: number; new: number; removed: number; shortened: number; reordered: number; postponed: number };
  recommended?: boolean;
};

export type Change = {
  item_id: string;
  kind: "delay" | "cancel" | "closed" | "reschedule" | "skip";
  new_start?: string | null;
  new_end?: string | null;
  note?: string;
  delay_min?: number;
  delay_mode?: "late_start" | "overrun" | "arrives_late";
  base_start?: string;
  base_end?: string;
};

export type Disruption = {
  id: string;
  message: string;
  summary: string;
  as_of: string;
  changes: Change[];
  rain: { start: string; end: string } | null;
  busy: { start: string; end: string; title?: string }[];
  questions: string[];
  understood_by: string;
  status: "analyzed" | "planned" | "no_plan" | "resolved" | "dismissed";
  ignored?: string[];
  dismiss_reason?: string;
  impact: {
    results: Record<string, SimResult>;
    position: string;
    needs_change: boolean;
    counts: Record<string, number>;
    base?: Record<string, { start: string; end: string | null; travel_min: number; travel_mode?: string }>;
  };
  plans: Plan[];
  excluded: Plan[];
  chosen?: { id: string; name: string };
  options?: {
    candidates: { cid: string; name: string; lat: number; lng: number; indoor: boolean | null; rating?: number; maps_url?: string; source?: string }[];
    transits: { tid: string; depart: string; arrive: string; lines: string[] }[];
    planned_by: string;
  };
};

export type Action = {
  id: string;
  item_id: string | null;
  kind: "change" | "cancel" | "book";
  title: string;
  detail: string;
  provider: string | null;
  status: "needs_attention" | "pending" | "confirmed" | "failed";
  reference: string | null;
};

export type Prefs = {
  interests: string[];
  pace: string;
  extra_budget: number;
  currency: string;
  travelers: number;
  group: string;
  accessibility: boolean;
};

export type Trip = {
  id: string;
  title: string;
  destination: string;
  timezone_offset: string;
  center?: { lat: number; lng: number } | null;
  preferences: Prefs;
  items: Item[];
  disruptions: Disruption[];
  actions: Action[];
  baseline?: { taken_at: string; items: Item[] } | null;
  plan_draft?: PlanDraft | null;
  log: { at: string; kind: string; text: string }[];
  view: { as_of: string; results: Record<string, SimResult>; position: string };
};

export type TripSummary = { id: string; title: string; destination: string; kind: "manual" | "test"; items: number; done?: number; from: string | null; to: string | null; open_actions: number };

export type Status = {
  ai: { providers: string[]; vision: string[] };
  maps: { places: string; routes: string; transit: boolean; road_alternatives: boolean; overpass: string };
};

export type ActivityRow = {
  at: string; user: string | null; role: string | null; method: string; path: string; route: string; area: string;
  status: number; ms: number; trip: string | null; ip: string | null; error: string | null;
  calls: Record<string, { n: number; ms: number; errors: number }>; notes: Record<string, unknown>;
};

export type AdminStats = {
  hours: number; requests: number; users_active: number; errors: number; server_errors: number; avg_ms: number; p95_ms: number;
  failed_logins: number;
  endpoints: { endpoint: string; count: number; avg_ms: number; p95_ms: number; errors: number }[];
  services: { service: string; n: number; ms: number; errors: number; avg_ms: number }[];
  areas: [string, number][]; per_hour: [string, number][]; per_user: [string, number][];
};

export type AdminUser = {
  id: string; username: string; role: "user" | "admin"; created_at: string; last_login: string | null;
  trips: number; requests: number; errors: number; last_seen: string | null;
};

export type PlanDraft = {
  idea: string; made_with: string; live_search: boolean; assumptions: string[];
  stays: { name: string; town?: string; price?: string; why?: string; url?: string }[];
  getting_there: { mode?: string; from?: string; to?: string; option?: string; duration?: string; price?: string; url?: string }[];
  tips: string[]; sources: { title?: string; url: string }[];
};
