import { useRef, useState } from "react";
import { api, type Sos } from "../api";
import { useApp } from "../state";

const HOLD_MS = 1500;

/** Press and hold for 1.5 s. The hold prevents pocket-dials; releasing early cancels. */
export default function SosButton() {
  const { here, setSosId, log } = useApp();
  const [progress, setProgress] = useState(0);
  const [sending, setSending] = useState(false);
  const raf = useRef<number | null>(null);
  const start = useRef(0);

  function cancel() {
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = null;
    setProgress(0);
  }

  async function fire() {
    cancel();
    setSending(true);
    let coords: { lat?: number; lng?: number } = {};
    try {
      coords = await new Promise((resolve) => {
        if (!navigator.geolocation) return resolve({});
        navigator.geolocation.getCurrentPosition(
          (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
          () => resolve({}),
          { timeout: 1200, maximumAge: 60000 },
        );
      });
    } catch { /* GPS is optional */ }
    try {
      const sos = await api<Sos>("/api/sos", { body: { place_id: here?.id, ...coords } });
      setSosId(sos.id);
      log({ agent: "rule", title: "SOS sent instantly (no AI in the path)", detail: `Location: ${sos.place_label}`, tone: "warn" });
    } finally {
      setSending(false);
    }
  }

  function tick() {
    const p = Math.min(1, (performance.now() - start.current) / HOLD_MS);
    setProgress(p);
    if (p >= 1) {
      fire();
      return;
    }
    raf.current = requestAnimationFrame(tick);
  }

  function down(e: React.PointerEvent) {
    e.preventDefault();
    if (sending) return;
    start.current = performance.now();
    raf.current = requestAnimationFrame(tick);
  }

  const r = 108, c = 2 * Math.PI * r;
  return (
    <div className="sos-wrap">
      <button
        className={`sos-btn ${progress > 0 ? "holding" : ""}`}
        onPointerDown={down}
        onPointerUp={cancel}
        onPointerLeave={cancel}
        onPointerCancel={cancel}
        onContextMenu={(e) => e.preventDefault()}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (!raf.current) { start.current = performance.now(); raf.current = requestAnimationFrame(tick); } } }}
        onKeyUp={cancel}
        aria-label="SOS: press and hold to alert Yale Police dispatch"
      >
        {progress === 0 && <span className="pulse" />}
        <svg className="ring" viewBox="0 0 240 240">
          <circle cx="120" cy="120" r={r} stroke="rgba(200,16,46,0.12)" strokeWidth="6" fill="none" />
          <circle cx="120" cy="120" r={r} stroke="#a20c25" strokeWidth="6" fill="none" strokeLinecap="round"
                  strokeDasharray={c} strokeDashoffset={c * (1 - progress)} />
        </svg>
        <div>
          <div className="label">{sending ? "…" : "SOS"}</div>
          <div className="hint">{progress > 0 ? "Keep holding" : "Press and hold"}</div>
        </div>
      </button>
      <div className="sos-caption">
        Sends your location to Yale Police dispatch and your trusted contacts. <b>Demo:</b> nothing leaves this app; for a real
        emergency call <a href="tel:911">911</a>.
      </div>
    </div>
  );
}
