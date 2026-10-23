import { useEffect, useState } from "react";
import { api, clock, timeAgo, type Sos, type Walk } from "../api";
import BeaconMap from "../components/BeaconMap";
import { IconPin } from "../icons";
import { useApp } from "../state";

type Board = {
  sos: Sos[];
  walks: Walk[];
  escorts: { id: number; from_name: string; to_name: string; user_name: string; created_at: string; status: string }[];
};

const UNIT_LABELS: Record<string, string> = {
  yale_pd: "Yale PD", ems: "EMS", fire: "Fire", yale_security: "Yale Security", mental_health_clinician: "Mental health clinician",
};

function SosCard({ s, onAction }: { s: Sos; onAction: (id: number, a: "ack" | "resolve") => void }) {
  const open = s.status === "open" || s.status === "acknowledged";
  return (
    <div className="card" style={{ borderColor: open ? "var(--red-line)" : undefined, borderLeft: open ? "4px solid var(--sos)" : undefined }}>
      <div className="row between">
        <div className="row" style={{ gap: 8 }}>
          <span className={`chip ${open ? "red" : "off"}`}>{s.status.toUpperCase()}</span>
          <b>{s.caller?.name ?? "Caller"}</b>
        </div>
        <span className="tiny faint">{clock(s.created_at)} · {timeAgo(s.created_at)}</span>
      </div>
      <div className="small muted" style={{ marginTop: 4 }}>{s.caller?.affiliation} · {s.caller?.unit} · NetID {s.caller?.netid}</div>
      <div className="small row" style={{ marginTop: 6, gap: 4 }}><IconPin size={14} /> <b>{s.place_label}</b> ({s.lat.toFixed(5)}, {s.lng.toFixed(5)})</div>
      <div style={{ marginTop: 10 }}><BeaconMap me={{ lat: s.lat, lng: s.lng, label: s.place_label }} /></div>
      {s.note && <div className="small" style={{ marginTop: 10 }}><span className="muted">Caller's note:</span> “{s.note}”</div>}
      {s.brief ? (
        <div className="brief">
          <span className="chip shield">AI draft · verify with caller</span>
          <div style={{ fontWeight: 700, fontSize: 15, marginTop: 7 }}>{s.brief.headline}</div>
          <dl>
            <dt>Nature</dt><dd>{s.brief.nature.replace(/_/g, " ")}</dd>
            <dt>Threat now</dt><dd className={s.brief.threat_present === "yes" ? "sev-text urgent" : ""}>{s.brief.threat_present}</dd>
            <dt>Injuries</dt><dd>{s.brief.injuries}</dd>
            <dt>Send</dt><dd>{s.brief.recommended_units.map((u) => UNIT_LABELS[u] ?? u).join(", ")}</dd>
            <dt>Caller</dt><dd>{s.brief.caller}</dd>
          </dl>
          <div className="small muted" style={{ marginTop: 8 }}>Facts stated</div>
          <ul>{s.brief.key_facts.map((f, i) => <li key={i}>{f}</li>)}</ul>
          <div className="small muted" style={{ marginTop: 8 }}>Ask first</div>
          <ul>{s.brief.ask_caller.map((f, i) => <li key={i}>{f}</li>)}</ul>
        </div>
      ) : (
        <div className="tiny faint" style={{ marginTop: 8 }}>
          {s.brief_status === "waiting_for_note" && "No note from the caller yet: location and identity above are what we know."}
          {s.brief_status === "pending" && "Responder Brief agent is summarising the caller's note…"}
          {s.brief_status === "failed" && "AI brief unavailable; use the caller's note as written."}
        </div>
      )}
      <div className="timeline" style={{ marginTop: 10 }}>
        {s.timeline.map((e, i) => <div className="ev" key={i}><span className="t">{clock(e.t)}</span><span className="dot" /><span>{e.event}</span></div>)}
      </div>
      {open && (
        <div className="row" style={{ gap: 8, marginTop: 12 }}>
          {s.status === "open" && <button className="btn blue grow" onClick={() => onAction(s.id, "ack")}>Acknowledge</button>}
          <button className="btn grow" onClick={() => onAction(s.id, "resolve")}>Resolve</button>
        </div>
      )}
    </div>
  );
}

export default function Dispatch() {
  const { toast } = useApp();
  const [board, setBoard] = useState<Board | null>(null);

  const load = () => api<Board>("/api/dispatch").then(setBoard).catch(() => {});
  useEffect(() => {
    load();
    const t = window.setInterval(load, 3000);
    return () => window.clearInterval(t);
  }, []);

  async function action(id: number, a: "ack" | "resolve") {
    await api(`/api/dispatch/sos/${id}/${a}`, { method: "POST", body: {} });
    load();
  }

  async function resetDemo() {
    if (!window.confirm("Re-seed the demo data? Fresh demo reports are created, and every account (including ones made in the app) is reset. AI usage logs are kept.")) return;
    await api("/api/admin/reset-demo", { method: "POST", body: {} });
    toast("Demo data reset. Sign in again.");
    window.setTimeout(() => window.location.reload(), 1200);
  }

  if (!board) return <div className="empty">Loading…</div>;
  const live = board.sos.filter((s) => s.status === "open" || s.status === "acknowledged");
  const past = board.sos.filter((s) => !(s.status === "open" || s.status === "acknowledged"));
  const flagged = board.walks.filter((w) => w.status === "overdue" || w.status === "escalated");

  return (
    <div>
      <div className="h1">Dispatch console</div>
      <div className="small muted">Simulated Yale PD view. In a real rollout this would feed the department's existing dispatch system.</div>

      <div className="section-title"><span>Live SOS ({live.length})</span></div>
      {live.length === 0 ? <div className="card empty">No open SOS calls.</div> : <div className="stack">{live.map((s) => <SosCard key={s.id} s={s} onAction={action} />)}</div>}

      <div className="section-title"><span>Missed walk check-ins ({flagged.length})</span></div>
      {flagged.length === 0 ? <div className="card empty">Everyone on a walk has checked in.</div> : (
        <div className="stack">
          {flagged.map((w) => (
            <div key={w.id} className="card">
              <div className="row between"><b>{w.walker?.name}</b><span className={`chip ${w.status === "escalated" ? "red" : "demo"}`}>{w.status}</span></div>
              <div className="small muted" style={{ marginTop: 3 }}>{w.origin?.name} → {w.dest?.name} · due {clock(w.eta)}</div>
              {w.origin && w.dest && <div style={{ marginTop: 8 }}><BeaconMap route={[w.origin, w.dest]} /></div>}
            </div>
          ))}
        </div>
      )}

      <div className="section-title"><span>Escort requests (24 h)</span></div>
      {board.escorts.length === 0 ? <div className="card empty">None.</div> : (
        <div className="card tight">
          {board.escorts.map((e) => (
            <div key={e.id} className="row between small" style={{ padding: "6px 0" }}>
              <span><b>{e.user_name}</b> · {e.from_name} → {e.to_name}</span><span className="faint">{timeAgo(e.created_at)}</span>
            </div>
          ))}
        </div>
      )}

      {past.length > 0 && (
        <>
          <div className="section-title"><span>Closed today ({past.length})</span></div>
          <div className="stack">{past.slice(0, 5).map((s) => <SosCard key={s.id} s={s} onAction={action} />)}</div>
        </>
      )}

      <div className="section-title"><span>Demo controls</span></div>
      <button className="btn block" onClick={resetDemo}>Reset demo data (fresh fictional reports)</button>
    </div>
  );
}
