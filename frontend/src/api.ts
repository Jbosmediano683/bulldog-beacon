// Small fetch wrapper plus the shapes the API returns.

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(path, {
    method: init?.method ?? (init?.body !== undefined ? "POST" : "GET"),
    headers: init?.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: unknown }).detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : `Request failed (${res.status})`);
  }
  return data as T;
}

export type Contact = { name: string; phone: string };

// Beacon's service area (south, west, north, east); keep in sync with backend/config.py.
// Yale's campuses including West Campus, plus East Rock, Wooster Square, Dixwell,
// Prospect Hill, Westville, the Hill and downtown.
export const SERVICE_BOUNDS = [41.245, -73.005, 41.338, -72.885] as const;

export type YaleEvent = {
  id: number;
  title: string;
  start: string;
  end: string | null;
  all_day: boolean;
  status: "now" | "soon" | "later" | "all_day";
  venue: string;
  room: string;
  lat: number | null;
  lng: number | null;
  free: boolean;
  types: string[];
  kind: string;
  url: string;
  photo_url: string | null;
  photo_large: string | null;
  open_hours: boolean;
  description: string;
  address: string;
  ics_url: string | null;
  ticket_cost: string;
  ticket_url: string | null;
};

export type User = {
  id: number;
  netid: string;
  name: string;
  affiliation: string;
  unit: string;
  role: "member" | "dispatcher";
  contacts: Contact[];
  medical_note: string;
  demo: boolean;
};

export type Place = {
  id: number;
  name: string;
  kind: string;
  aliases: string[];
  address: string;
  lat: number;
  lng: number;
};

export type Severity = "info" | "caution" | "warning" | "urgent";

export type Report = {
  id: number;
  created_at: string;
  category: string;
  text: string;
  status: string;
  demo: boolean;
};

export type Incident = {
  id: number;
  title: string;
  summary: string;
  advice: string;
  category: string;
  severity: Severity;
  place_id: number | null;
  place_name?: string;
  lat: number;
  lng: number;
  report_count: number;
  confirmations?: number;
  first_reported: string;
  last_reported: string;
  demo: boolean;
  reports?: Report[];
};

export type RunUsage = {
  run_id: number;
  status: string;
  requests: number;
  tool_calls: number;
  input_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  gateway_cache_hits: number;
  latency_ms: number;
  cost_usd: number;
  trace: TraceStep[];
};

export type TraceStep = { type: "tool_call" | "tool_result"; tool: string; args?: Record<string, unknown>; preview?: string };

export type Moderation = {
  decision: "publish" | "revise" | "block" | "redirect_911" | "held";
  issues?: string[];
  category?: string;
  severity?: Severity;
  published_text?: string;
  title?: string;
  advice?: string;
  note_to_author?: string;
  layer?: "rule" | "agent";
  guards?: string[];
  support?: boolean;
};

export type PostResult = {
  post: Report & { raw_text: string; moderation: Moderation; incident_id: number | null };
  moderation: Moderation;
  run: RunUsage | null;
  published: boolean;
};

export type Action = {
  kind: "start_walk" | "call" | "request_escort" | "open_map" | "open_resources";
  label: string;
  origin_place_id?: number | null;
  dest_place_id?: number | null;
  minutes?: number | null;
  phone?: string | null;
  incident_id?: number | null;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  actions?: Action[];
  incidents?: Incident[];
  guards?: string[];
  run?: RunUsage | null;
  pending?: boolean;
};

export type Resource = {
  id: number;
  name: string;
  category: string;
  phone: string | null;
  phone_display: string;
  hours: string;
  who: string;
  description: string;
  source_url: string;
  verified_on: string;
};

export type ServiceStatus = {
  new_haven_time: string;
  after_dark_approx: boolean;
  services: { name: string; phone: string | null; phone_display: string; hours: string; open_now: boolean | null }[];
};

export type TimelineItem = { t: string; event: string };

export type Brief = {
  headline: string;
  nature: string;
  threat_present: string;
  injuries: string;
  caller: string;
  location: string;
  recommended_units: string[];
  key_facts: string[];
  ask_caller: string[];
};

export type Sos = {
  id: number;
  user_id: number;
  created_at: string;
  lat: number;
  lng: number;
  place_label: string;
  note: string;
  status: string;
  brief_status: string;
  brief: Brief | null;
  contacts_notified: Contact[];
  timeline: TimelineItem[];
  caller?: { name: string; netid: string; affiliation: string; unit: string };
};

export type Walk = {
  id: number;
  user_id: number;
  started_at: string;
  eta: string;
  status: "active" | "overdue" | "escalated" | "arrived" | "cancelled";
  ended_at: string | null;
  origin: { id: number; name: string; lat: number; lng: number } | null;
  dest: { id: number; name: string; lat: number; lng: number } | null;
  contacts: Contact[];
  events: TimelineItem[];
  walker?: { name: string; netid: string };
};

export type CommunityPost = {
  id: number;
  created_at: string;
  category: string;
  text: string;
  title: string;
  severity: Severity;
  place_id: number | null;
  place_name: string | null;
  incident_id: number | null;
  author: string;
  mine: boolean;
  demo: boolean;
  likes: number;
  confirms: number;
  liked: boolean;
  confirmed: boolean;
  comments: number;
};

export type CommunityComment = {
  id: number;
  post_id: number;
  created_at: string;
  status: string;
  text: string;
  author: string;
  mine: boolean;
  demo: boolean;
  raw_text?: string;
  note?: string;
  support?: boolean;
};

export type SafetyEvent = { id: number; created_at: string; kind: string; layer: string; detail: string; ref: string };

export type UsageReport = {
  model: string;
  prices_per_million: { input: number; cached_input: number; output: number };
  price_source: string;
  my_tokens_today: number;
  my_daily_cap: number;
  app_tokens_today: number;
  app_daily_cap: number;
  by_agent: {
    agent: string; runs: number; avg_requests: number; avg_tool_calls: number; avg_input: number; avg_cached: number;
    avg_output: number; avg_reasoning: number; avg_latency_ms: number; avg_cost: number; total_cost: number;
    gateway_hits: number;
  }[];
  my_runs: (Omit<RunUsage, "trace" | "run_id"> & { id: number; created_at: string; agent: string; ref: string })[];
  totals: { runs: number; cost: number; input: number; cached: number; output: number };
};

// ------------------------------------------------------------- formatting

export function timeAgo(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.floor(mins / 60);
  if (h < 24) return `${h} h ${mins % 60 ? `${mins % 60} min ` : ""}ago`;
  return `${Math.floor(h / 24)} d ago`;
}

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" });
}

export function fmtTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${Math.round(n)}`;
}

export function fmtCost(usd: number): string {
  if (usd === 0) return "$0";
  if (usd < 0.01) return `$${usd.toFixed(5)}`;
  return `$${usd.toFixed(3)}`;
}

export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, "")}`;
}

export const CATEGORY_LABELS: Record<string, string> = {
  suspicious_activity: "Suspicious activity",
  vehicle_break_in: "Car break-in",
  theft: "Theft",
  harassment: "Harassment",
  assault: "Assault",
  police_activity: "Police activity",
  hazard: "Hazard",
  medical: "Medical",
  fire: "Fire",
  gathering: "March / gathering",
  good_news: "Good news",
  safety_update: "Safety update",
  other: "Other",
};

export function distanceM(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const r = 6371000;
  const p1 = (a.lat * Math.PI) / 180, p2 = (b.lat * Math.PI) / 180;
  const dp = p2 - p1, dl = ((b.lng - a.lng) * Math.PI) / 180;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(h));
}
