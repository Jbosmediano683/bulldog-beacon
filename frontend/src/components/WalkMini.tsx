import { useEffect, useState } from "react";
import type { Walk } from "../api";

export function useCountdown(eta: string): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  return Math.round((Date.parse(eta) - now) / 1000);
}

export function mmss(sec: number): string {
  const s = Math.abs(sec);
  return `${sec < 0 ? "+" : ""}${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function WalkMini({ walk, onOpen }: { walk: Walk; onOpen: () => void }) {
  const left = useCountdown(walk.eta);
  return (
    <button className={`walk-card ${walk.status}`} style={{ width: "100%", textAlign: "left", marginTop: 14 }} onClick={onOpen}>
      <div className="row between">
        <div>
          <div className="tiny" style={{ textTransform: "uppercase", letterSpacing: 1, opacity: 0.85 }}>
            {walk.status === "active" ? "Walk With Me is on" : walk.status === "overdue" ? "Check-in missed" : "Contacts alerted"}
          </div>
          <div style={{ fontWeight: 700, marginTop: 3 }}>{walk.origin?.name.replace(/\s*\(.*\)/, "")} → {walk.dest?.name.replace(/\s*\(.*\)/, "")}</div>
        </div>
        <div style={{ fontSize: 26, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{mmss(left)}</div>
      </div>
      <div className="small" style={{ opacity: 0.85, marginTop: 6 }}>
        {walk.status === "active" ? "Tap to check in when you arrive." : "Tap to tell your contacts you're OK."}
      </div>
    </button>
  );
}
