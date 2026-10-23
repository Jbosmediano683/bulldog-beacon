import { useEffect, useState } from "react";
import { api, clock, distanceM, type Walk } from "../api";
import BeaconMap from "../components/BeaconMap";
import { mmss, useCountdown } from "../components/WalkMini";
import { locate, type Located } from "../geo";
import { useApp } from "../state";

function estimateMinutes(a?: { lat: number; lng: number }, b?: { lat: number; lng: number }): number {
  if (!a || !b) return 10;
  return Math.max(2, Math.round((distanceM(a, b) * 1.3) / 80) + 3);
}

function ActiveWalk({ walk, onChange }: { walk: Walk; onChange: (w: Walk | null) => void }) {
  const { setSosId, here, toast } = useApp();
  const left = useCountdown(walk.eta);
  const total = Math.max(1, (Date.parse(walk.eta) - Date.parse(walk.started_at)) / 1000);
  const frac = Math.max(0, Math.min(1, left / total));
  const r = 84, c = 2 * Math.PI * r;
  const color = walk.status === "active" ? "var(--yale-2)" : walk.status === "overdue" ? "var(--sev-caution)" : "var(--sos)";

  async function arrived() {
    onChange(await api<Walk>(`/api/walks/${walk.id}/arrived`, { method: "POST", body: {} }));
    toast("Checked in. Your contacts know you made it.");
  }
  async function cancel() {
    await api(`/api/walks/${walk.id}/cancel`, { method: "POST", body: {} });
    onChange(null);
  }
  async function help() {
    const s = await api<{ id: number }>("/api/sos", { body: { place_id: here?.id ?? walk.origin?.id } });
    setSosId(s.id);
  }

  return (
    <div>
      <div className="h1">{walk.status === "active" ? "Walk With Me is on" : walk.status === "overdue" ? "Are you OK?" : "Your contacts were alerted"}</div>
      <div className="small muted">{walk.origin?.name} → {walk.dest?.name}</div>
      <div className="countdown">
        <svg viewBox="0 0 190 190">
          <circle cx="95" cy="95" r={r} stroke="var(--surface-3)" strokeWidth="10" fill="none" />
          <circle cx="95" cy="95" r={r} stroke={color} strokeWidth="10" fill="none" strokeLinecap="round"
                  strokeDasharray={c} strokeDashoffset={c * (1 - frac)} style={{ transition: "stroke-dashoffset 1s linear" }} />
        </svg>
        <div>
          <div className="num" style={{ color: left < 0 ? color : "var(--text)" }}>{mmss(left)}</div>
          <div className="lbl">{left >= 0 ? `check in by ${clock(walk.eta)}` : "past check-in time"}</div>
        </div>
      </div>
      {walk.status !== "active" && (
        <div className={`verdict ${walk.status === "overdue" ? "blocked" : "redirect_911"} small`} style={{ marginBottom: 12 }}>
          {walk.status === "overdue"
            ? "You didn't check in on time. If you don't respond in about 2 minutes, Beacon alerts your contacts and the Yale PD console with your route."
            : "We alerted your trusted contacts and the dispatch console with your route (simulated). Tap below to let them know you're OK."}
        </div>
      )}
      <div className="stack">
        <button className="btn primary block" style={{ padding: 15, fontSize: 16 }} onClick={arrived}>I'm here safely</button>
        {walk.status !== "active" && <button className="btn danger block" onClick={help}>I need help (SOS)</button>}
        <button className="btn ghost block" onClick={cancel}>Cancel walk</button>
      </div>
      {walk.origin && walk.dest && (
        <div style={{ marginTop: 16 }}><BeaconMap route={[walk.origin, walk.dest]} /></div>
      )}
      <div className="card" style={{ marginTop: 14 }}>
        <div className="h2" style={{ fontSize: 14, marginBottom: 6 }}>Timeline</div>
        <div className="timeline">
          {walk.events.map((e, i) => (
            <div className="ev" key={i}><span className="t">{clock(e.t)}</span><span className="dot" /><span>{e.event}</span></div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function WalkScreen() {
  const { places, here, placeById, walkDraft, clearWalkDraft, user, log } = useApp();
  const [walk, setWalk] = useState<Walk | null | undefined>(undefined);
  const [from, setFrom] = useState<number | "gps">("gps");   // "gps" = Current location
  const [loc, setLoc] = useState<Located | "locating" | null>(null);
  const [locTry, setLocTry] = useState(0);
  const [to, setTo] = useState<number | "">("");
  const [minutes, setMinutes] = useState(10);
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (from !== "gps") return;
    let live = true;
    setLoc("locating");
    locate().then((r) => { if (live) setLoc(r); });
    return () => { live = false; };
  }, [from, locTry]);

  useEffect(() => {
    const load = () => api<Walk | null>("/api/walks/active").then(setWalk).catch(() => {});
    load();
    const t = window.setInterval(load, 4000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (walkDraft) {
      if (walkDraft.origin_place_id) setFrom(walkDraft.origin_place_id);
      if (walkDraft.dest_place_id) setTo(walkDraft.dest_place_id);
      if (walkDraft.minutes) { setMinutes(walkDraft.minutes); setTouched(true); }
      clearWalkDraft();
    }
  }, [walkDraft, clearWalkDraft]);

  // The start point: the phone's location when it's in New Haven, otherwise the location set at the top of the app.
  const gpsFix = from === "gps" && loc && loc !== "locating" && loc.kind === "gps" ? loc.fix : null;
  const a = from === "gps" ? (gpsFix ? { lat: gpsFix.lat, lng: gpsFix.lng } : here) : placeById(from);
  const b = placeById(Number(to));

  useEffect(() => {
    if (!touched && a && b) setMinutes(estimateMinutes(a, b));
  }, [a?.lat, a?.lng, b?.id, touched]); // eslint-disable-line react-hooks/exhaustive-deps

  async function start() {
    setError(null);
    const origin = from === "gps"
      ? { origin_lat: gpsFix?.lat ?? null, origin_lng: gpsFix?.lng ?? null, origin_place_id: here?.id ?? null }
      : { origin_place_id: from };
    try {
      const w = await api<Walk>("/api/walks", { body: { ...origin, dest_place_id: to, minutes } });
      setWalk(w);
      log({ agent: "rule", title: "Walk With Me started", detail: `From ${w.origin?.name}. Timer: ${minutes} min. Missed check-ins escalate by code, not AI.` });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start the walk.");
    }
  }

  if (walk === undefined) return <div className="empty">Loading…</div>;
  if (walk && ["active", "overdue", "escalated"].includes(walk.status)) return <ActiveWalk walk={walk} onChange={setWalk} />;

  const fallback = here ? `the location set at the top of the app (${here.name})` : "a place from the list";
  const locNote = from !== "gps" ? null
    : loc === "locating" || loc === null ? "Finding your location…"
    : loc.kind === "gps" ? `Using your phone's location (accurate to about ${Math.max(5, Math.round(loc.fix.accuracy))} m).`
    : loc.kind === "outside" ? `You're not in New Haven right now, so Beacon will start from ${fallback}.`
    : `${loc.reason} Beacon will start from ${fallback}, or pick a place from the list.`;
  return (
    <div>
      <div className="h1">Walk With Me</div>
      <p className="small muted" style={{ marginTop: 2 }}>
        Set where you're going. If you don't check in by the time you should arrive, Beacon asks if you're OK, then alerts your
        trusted contacts with your route.
      </p>
      {walk?.status === "arrived" && <div className="verdict published small" style={{ marginBottom: 12 }}>Last walk: you checked in at {walk.dest?.name}.</div>}
      <div className="stack">
        <div className="field">
          <label>From</label>
          <select className="select" value={from} onChange={(e) => setFrom(e.target.value === "gps" ? "gps" : Number(e.target.value))}>
            <option value="gps">Current location</option>
            <optgroup label="Yale places">
              {places.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </optgroup>
          </select>
          {locNote && (
            <div className={`loc-note ${loc && loc !== "locating" && loc.kind === "gps" ? "ok" : ""}`}>
              {locNote}
              {loc && loc !== "locating" && loc.kind === "unavailable" && (
                <button className="linkish" onClick={() => setLocTry((n) => n + 1)}>Try again</button>
              )}
            </div>
          )}
        </div>
        <div className="field">
          <label>To</label>
          <select className="select" value={to} onChange={(e) => setTo(Number(e.target.value))}>
            <option value="">Choose destination</option>
            {places.filter((p) => from === "gps" || p.id !== from).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Check in within</label>
          <div className="row">
            <input className="input" type="range" min={1} max={45} value={minutes} style={{ padding: 0, border: 0, background: "none" }}
                   onChange={(e) => { setMinutes(Number(e.target.value)); setTouched(true); }} />
            <b style={{ minWidth: 64, textAlign: "right" }}>{minutes} min</b>
          </div>
          {a && b && <div className="tiny faint">About {Math.round((distanceM(a, b) * 1.3) / 80)} min on foot ({Math.round(distanceM(a, b) * 1.3)} m), plus a few minutes of slack.</div>}
        </div>
        {a && b && <BeaconMap route={[a, b]} />}
        <div className="card tight small">
          <b>Trusted contacts</b>
          <div className="muted" style={{ marginTop: 3 }}>
            {user.contacts.length ? user.contacts.map((c) => c.name).join(", ") : "None yet. Add them from your profile (top right)."}
          </div>
        </div>
        {error && <div className="verdict blocked small">{error}</div>}
        <button className="btn primary block" style={{ padding: 14 }} disabled={!to || loc === "locating" && from === "gps"} onClick={start}>Start walk</button>
        <div className="tiny faint" style={{ textAlign: "center" }}>Demo tip: set 1 minute to see the missed check-in flow.</div>
      </div>
    </div>
  );
}
