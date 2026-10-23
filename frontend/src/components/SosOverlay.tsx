import { useEffect, useState } from "react";
import { api, clock, type Sos } from "../api";
import { IconPin } from "../icons";
import { useApp } from "../state";

export default function SosOverlay() {
  const { sosId, setSosId, toast } = useApp();
  const [sos, setSos] = useState<Sos | null>(null);
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (sosId === null) return;
    let alive = true;
    const load = () => api<Sos>(`/api/sos/${sosId}`).then((s) => alive && setSos(s)).catch(() => {});
    load();
    const t = window.setInterval(load, 2500);
    return () => { alive = false; window.clearInterval(t); };
  }, [sosId]);

  async function sendNote() {
    if (!note.trim() || sosId === null) return;
    setSos(await api<Sos>(`/api/sos/${sosId}/note`, { body: { note } }));
    setSent(true);
  }

  async function safe() {
    if (sosId === null) return;
    await api(`/api/sos/${sosId}/safe`, { method: "POST", body: {} });
    setSosId(null);
    toast("Glad you're safe. Dispatch and your contacts were told (simulated).");
  }

  return (
    <div className="sos-overlay">
      <div className="sos-banner">
        <div className="beacon-ring">SOS</div>
        <div className="h1">Help is being alerted</div>
        <div className="small row" style={{ justifyContent: "center", gap: 5, opacity: 0.95 }}>
          {sos ? <><IconPin size={15} /> {sos.place_label} · sent {clock(sos.created_at)}</> : "Sending…"}
        </div>
        <div className="chip demo" style={{ marginTop: 10 }}>Demo: simulated dispatch, nobody is actually contacted</div>
      </div>

      <div className="sos-inner">
        <div className="row" style={{ gap: 10, marginTop: 16 }}>
          <a className="btn danger block" href="tel:911" style={{ padding: "14px 10px", fontSize: 17 }}>Call 911</a>
          <a className="btn block" href="tel:2034324400" style={{ padding: "14px 10px" }}>Call Yale PD</a>
        </div>

        <div className="card" style={{ marginTop: 14 }}>
          <div className="h2">Tell responders what's happening</div>
          <div className="small muted" style={{ margin: "3px 0 10px" }}>Optional. Your alert already went out; a short note helps them.</div>
          {!sent ? (
            <>
              <textarea className="textarea" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500}
                        placeholder="e.g. Someone is following me from the garage, I'm by the YCCI door" />
              <button className="btn primary block" style={{ marginTop: 10 }} onClick={sendNote} disabled={!note.trim()}>
                Send to dispatch
              </button>
            </>
          ) : (
            <div className="small">
              <div><b>Note sent:</b> “{sos?.note}”</div>
              <div className="muted" style={{ marginTop: 6 }}>
                {sos?.brief_status === "ready"
                  ? <>Beacon summarized it for the dispatcher: <b style={{ color: "var(--text)" }}>{sos.brief?.headline}</b></>
                  : sos?.brief_status === "failed"
                    ? "Dispatch has your note as written (AI summary unavailable)."
                    : "Beacon is writing a short summary for the dispatcher…"}
              </div>
            </div>
          )}
        </div>

        <div className="card" style={{ marginTop: 12 }}>
          <div className="h2" style={{ marginBottom: 6 }}>What happened</div>
          <div className="timeline">
            {(sos?.timeline ?? []).map((e, i) => (
              <div className="ev" key={i}><span className="t">{clock(e.t)}</span><span className="dot" style={{ background: "var(--sos)" }} /><span>{e.event}</span></div>
            ))}
          </div>
        </div>

        <button className="btn block" style={{ marginTop: 14 }} onClick={safe}>I'm safe, cancel SOS</button>
      </div>
    </div>
  );
}
