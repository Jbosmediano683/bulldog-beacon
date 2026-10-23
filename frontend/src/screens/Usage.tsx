import { useEffect, useState } from "react";
import { api, fmtCost, fmtTokens, timeAgo, type SafetyEvent, type UsageReport } from "../api";

const AGENT_NAMES: Record<string, string> = {
  moderator: "Moderator", corroborator: "Corroborator", concierge: "Concierge", responder: "Responder Brief",
};

export default function Usage() {
  const [u, setU] = useState<UsageReport | null>(null);
  const [events, setEvents] = useState<SafetyEvent[]>([]);
  useEffect(() => {
    api<UsageReport>("/api/usage").then(setU).catch(() => {});
    api<SafetyEvent[]>("/api/safety/events").then(setEvents).catch(() => {});
  }, []);
  if (!u) return <div className="empty">Loading…</div>;
  const cachedShare = u.totals.input ? (u.totals.cached / u.totals.input) * 100 : 0;

  return (
    <div>
      <div className="h1">AI usage and safety</div>
      <p className="small muted" style={{ marginTop: 2 }}>
        Every model call is measured: tokens in, tokens served from the prompt cache, tokens out, time, and cost. Model:{" "}
        <b>{u.model}</b>.
      </p>

      <div className="quick-grid" style={{ marginTop: 12 }}>
        <div className="card tight"><div className="tiny faint">AI runs (all users)</div><div className="h1">{u.totals.runs}</div></div>
        <div className="card tight"><div className="tiny faint">Total cost</div><div className="h1">{fmtCost(u.totals.cost)}</div></div>
        <div className="card tight"><div className="tiny faint">Input served from cache</div><div className="h1">{cachedShare.toFixed(0)}%</div></div>
        <div className="card tight"><div className="tiny faint">App tokens today</div><div className="h1">{fmtTokens(u.app_tokens_today)}</div>
          <div className="tiny faint">cap {fmtTokens(u.app_daily_cap)}</div></div>
      </div>

      <div className="section-title"><span>Average run, by agent</span></div>
      <div className="card tight" style={{ overflowX: "auto" }}>
        <table className="data">
          <thead><tr><th>Agent</th><th className="n">Runs</th><th className="n">In</th><th className="n">Cached</th><th className="n">Out</th><th className="n">Sec</th><th className="n">Cost</th></tr></thead>
          <tbody>
            {u.by_agent.map((a) => (
              <tr key={a.agent}>
                <td><i className={`dot ${a.agent}`} /> {AGENT_NAMES[a.agent] ?? a.agent}</td>
                <td className="n">{a.runs}</td>
                <td className="n">{fmtTokens(a.avg_input)}</td>
                <td className="n">{fmtTokens(a.avg_cached)}</td>
                <td className="n">{fmtTokens(a.avg_output)}</td>
                <td className="n">{(a.avg_latency_ms / 1000).toFixed(1)}</td>
                <td className="n">{fmtCost(a.avg_cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="tiny faint" style={{ marginTop: 8 }}>
          Prices per million tokens: ${u.prices_per_million.input} input, ${u.prices_per_million.cached_input} cached, $
          {u.prices_per_million.output} output. Source: {u.price_source}.
        </div>
      </div>

      <div className="section-title"><span>Your recent runs</span></div>
      <div className="card tight" style={{ overflowX: "auto" }}>
        <table className="data">
          <thead><tr><th>When</th><th>Agent</th><th className="n">In</th><th className="n">Cached</th><th className="n">Out</th><th className="n">Cost</th></tr></thead>
          <tbody>
            {u.my_runs.map((r) => (
              <tr key={r.id}>
                <td className="faint">{timeAgo(r.created_at)}</td>
                <td>{AGENT_NAMES[r.agent] ?? r.agent}{r.status !== "ok" && <span className="chip red" style={{ marginLeft: 5 }}>{r.status}</span>}</td>
                <td className="n">{fmtTokens(r.input_tokens)}</td>
                <td className="n">{fmtTokens(r.cached_tokens)}</td>
                <td className="n">{fmtTokens(r.output_tokens)}</td>
                <td className="n">{fmtCost(r.cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {u.my_runs.length === 0 && <div className="empty small">No AI runs yet.</div>}
      </div>

      <div className="section-title"><span>Safety log</span></div>
      <div className="stack">
        {events.length === 0 && <div className="card empty small">No safety events yet.</div>}
        {events.slice(0, 25).map((e) => (
          <div className="card tight" key={e.id}>
            <div className="row between small"><b style={{ textTransform: "capitalize" }}>{e.kind.replace(/_/g, " ")}</b><span className="faint">{e.layer} · {timeAgo(e.created_at)}</span></div>
            <div className="small muted" style={{ marginTop: 4 }}>{e.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
