import { useState } from "react";
import { api } from "../api";
import { useApp } from "../state";
import Sheet from "./Sheet";

export default function EscortSheet({ onClose, fromId, toId }: { onClose: () => void; fromId?: number | null; toId?: number | null }) {
  const { places, here, log } = useApp();
  const [from, setFrom] = useState<number>(fromId ?? here?.id ?? places[0]?.id);
  const [to, setTo] = useState<number | "">(toId ?? "");
  const [done, setDone] = useState<string | null>(null);

  async function request() {
    const r = await api<{ note: string }>("/api/escorts", { body: { from_place_id: from, to_place_id: to } });
    setDone(r.note);
    log({ agent: "rule", title: "Escort request logged", detail: r.note });
  }

  return (
    <Sheet onClose={onClose}>
      <div className="h2">Yale Security walking escort</div>
      <p className="small muted" style={{ margin: "4px 0 14px" }}>
        A Yale Security officer walks with you, 24/7, within the Yale footprint. Free for students, faculty, and staff.
      </p>
      {!done ? (
        <div className="stack">
          <div className="field">
            <label>From</label>
            <select className="select" value={from} onChange={(e) => setFrom(Number(e.target.value))}>
              {places.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>To</label>
            <select className="select" value={to} onChange={(e) => setTo(Number(e.target.value))}>
              <option value="">Choose destination</option>
              {places.filter((p) => p.id !== from).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <button className="btn primary block" disabled={!to} onClick={request}>Request escort</button>
          <a className="btn block" href="tel:2037855555">Or call Yale Security: (203) 785-5555</a>
        </div>
      ) : (
        <div className="stack">
          <div className="verdict revised small"><b>Request saved.</b> {done}</div>
          <a className="btn primary block" href="tel:2037855555">Call (203) 785-5555</a>
          <button className="btn block" onClick={onClose}>Done</button>
        </div>
      )}
    </Sheet>
  );
}
