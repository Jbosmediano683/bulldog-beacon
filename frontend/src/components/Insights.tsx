import { useEffect, useState, type ReactNode } from "react";
import { api, fmtCost, fmtTokens, timeAgo, type SafetyEvent, type TraceStep, type UsageReport } from "../api";
import { IconShield } from "../icons";
import { useApp } from "../state";

type Run = UsageReport["my_runs"][number];

const AGENTS = [
  { id: "moderator", name: "Moderator", job: "Screens every post & comment" },
  { id: "corroborator", name: "Corroborator", job: "Merges matching reports" },
  { id: "concierge", name: "Concierge", job: "Chat · 6 read-only tools" },
  { id: "responder", name: "Responder Brief", job: "SOS summary for dispatch" },
];

const SAFETY_LABELS: Record<string, string> = {
  injection_blocked: "Prompt injection blocked",
  injection_attempt: "Injection attempt noticed",
  profiling_caught: "Profiling caught",
  pii_removed: "Personal info removed",
  rumor_caught: "Rumor caught",
  emergency_redirect: "Sent to 911 instead",
  crisis_support_shown: "Crisis support shown",
  harassment_blocked: "Harassment blocked",
  output_guard: "Output guard fixed the AI",
  invalid_reference: "Bad reference caught",
  rate_limited: "Rate limit",
  user_budget_reached: "Daily AI budget reached",
  global_budget_reached: "App AI budget reached",
};

function RunItem({ run }: { run: Run }) {
  const [trace, setTrace] = useState<TraceStep[] | null>(null);
  const [open, setOpen] = useState(false);
  async function toggle() {
    setOpen(!open);
    if (!trace) {
      const r = await api<{ trace: TraceStep[] }>(`/api/runs/${run.id}`);
      setTrace(r.trace);
    }
  }
  return (
    <div className="act" onClick={toggle} style={{ cursor: "pointer" }}>
      <div className="top">
        <i className={`dot ${run.agent}`} />
        <b style={{ textTransform: "capitalize" }}>{run.agent}</b>
        <span className="faint tiny">{run.ref}</span>
        {run.status !== "ok" && <span className="chip red">{run.status}</span>}
        <span className="when">{timeAgo(run.created_at)}</span>
      </div>
      <div className="nums">
        <div><small>Input</small><span>{fmtTokens(run.input_tokens)}</span></div>
        <div><small>Cached</small><span>{fmtTokens(run.cached_tokens)}</span></div>
        <div><small>Output</small><span>{fmtTokens(run.output_tokens)}</span></div>
        <div><small>Cost</small><span>{fmtCost(run.cost_usd)}</span></div>
      </div>
      <div className="tiny faint" style={{ marginTop: 6 }}>
        {run.requests} model call{run.requests === 1 ? "" : "s"} · {run.tool_calls} tool call{run.tool_calls === 1 ? "" : "s"} ·{" "}
        {(run.latency_ms / 1000).toFixed(1)} s{run.gateway_cache_hits ? ` · ${run.gateway_cache_hits} gateway cache hit` : ""}
        {run.tool_calls > 0 && !open && " · click for trace"}
      </div>
      {open && trace && trace.length > 0 && (
        <div className="trace">
          {trace.map((s, i) => (
            <div key={i} className={`step ${s.type === "tool_call" ? "call" : "res"}`} title={s.preview ?? JSON.stringify(s.args)}>
              {s.type === "tool_call" ? `→ ${s.tool}(${Object.entries(s.args ?? {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})` : `← ${s.tool}: ${s.preview}`}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Insights() {
  const { activity, user } = useApp();
  const [usage, setUsage] = useState<UsageReport | null>(null);
  const [events, setEvents] = useState<SafetyEvent[]>([]);

  useEffect(() => {
    let alive = true;
    const load = () => {
      api<UsageReport>("/api/usage").then((u) => alive && setUsage(u)).catch(() => {});
      api<SafetyEvent[]>("/api/safety/events").then((e) => alive && setEvents(e)).catch(() => {});
    };
    load();
    const t = window.setInterval(load, 4000);
    return () => { alive = false; window.clearInterval(t); };
  }, []);

  const runs = usage?.my_runs ?? [];
  const latest = runs[0];
  const liveAgent = latest && Date.now() - Date.parse(latest.created_at) < 12000 ? latest.agent : null;

  type Item = { at: number; node: ReactNode };
  const items: Item[] = [
    ...runs.map((r) => ({ at: Date.parse(r.created_at), node: <RunItem key={`r${r.id}`} run={r} /> })),
    ...events.map((e) => ({
      at: Date.parse(e.created_at),
      node: (
        <div className="act" key={`s${e.id}`}>
          <div className="top">
            <IconShield size={15} />
            <b>{SAFETY_LABELS[e.kind] ?? e.kind}</b>
            <span className={`chip ${e.layer === "agent" ? "" : "shield"}`} style={{ padding: "2px 7px" }}>{e.layer}</span>
            <span className="when">{timeAgo(e.created_at)}</span>
          </div>
          <div className="small muted" style={{ marginTop: 5 }}>{e.detail}</div>
        </div>
      ),
    })),
    ...activity.map((a) => ({
      at: a.at,
      node: (
        <div className="act" key={a.id}>
          <div className="top"><i className="dot rule" /><b>{a.title}</b><span className="when">{timeAgo(new Date(a.at).toISOString())}</span></div>
          {a.detail && <div className="small muted" style={{ marginTop: 5 }}>{a.detail}</div>}
        </div>
      ),
    })),
  ].sort((a, b) => b.at - a.at).slice(0, 40);

  const capPct = usage ? Math.min(100, (usage.my_tokens_today / usage.my_daily_cap) * 100) : 0;

  return (
    <aside className="insights">
      <div className="panel">
        <h3>How Beacon's AI works</h3>
        <div className="small muted">
          Four {usage?.model ?? "gpt-6-luna"} agents, each with one job. Code decides who runs when, and checks
          every answer before you see it.
        </div>
        <div className="agents-diagram">
          {AGENTS.map((a) => (
            <div key={a.id} className={`agent-tile ${liveAgent === a.id ? "live" : ""}`}>
              <b><i className={`dot ${a.id}`} />{a.name}</b>
              <small>{a.job}</small>
            </div>
          ))}
        </div>
      </div>

      <div className="panel feed">
        <h3>Live activity {user.role === "dispatcher" ? "(all safety events)" : "(you)"}</h3>
        {items.length === 0 ? (
          <div className="empty small">Post an alert or ask Beacon something: each AI run shows up here with its tokens, cost,
            and tool calls, and every safety catch shows up too.</div>
        ) : items.map((i) => i.node)}
      </div>

      {usage && (
        <div className="panel">
          <div className="row between small"><b>Your AI use today</b><span className="muted">{fmtTokens(usage.my_tokens_today)} / {fmtTokens(usage.my_daily_cap)} tokens</span></div>
          <div className="meter" style={{ marginTop: 8 }}><i style={{ width: `${capPct}%` }} /></div>
          <div className="tiny faint" style={{ marginTop: 6 }}>Daily cap per NetID stops runaway spending. All-time app cost: {fmtCost(usage.totals.cost)} over {usage.totals.runs} runs.</div>
        </div>
      )}
      <div className="disclaimer" style={{ padding: "0 4px" }}>Bulldog Beacon is an independent student project (MGT 409, Yale School of Management). It is not an official Yale University service and is not affiliated with or endorsed by Yale University. In an emergency, call 911.</div>
    </aside>
  );
}
