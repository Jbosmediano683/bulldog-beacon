import { useEffect, useState } from "react";
import { api, telHref, type Resource, type ServiceStatus } from "../api";
import { IconInfo, IconPhone } from "../icons";

const GROUPS: { id: string; title: string; note?: string }[] = [
  { id: "emergency", title: "Emergency" },
  { id: "escort", title: "Get there safely" },
  { id: "ride", title: "" },
  { id: "mental_health", title: "Talk to someone", note: "Feeling shaken, anxious, or not okay is a normal reaction. These people are there for it." },
  { id: "sexual_misconduct", title: "Sexual harassment and assault" },
  { id: "app", title: "Other Yale tools" },
];

export default function Resources() {
  const [data, setData] = useState<{ resources: Resource[]; status: ServiceStatus } | null>(null);
  useEffect(() => { api<{ resources: Resource[]; status: ServiceStatus }>("/api/resources").then(setData).catch(() => {}); }, []);
  if (!data) return <div className="empty">Loading…</div>;
  const open = (name: string) => data.status.services.find((s) => s.name === name)?.open_now;

  return (
    <div>
      <div className="h1">Resources</div>
      <p className="small muted" style={{ marginTop: 2 }}>
        Every number here was copied from a Yale web page (source linked) and checked on Oct 22, 2026. Beacon's AI is only
        allowed to give out these numbers.
      </p>
      {GROUPS.map((g) => {
        const items = data.resources.filter((r) => r.category === g.id);
        if (!items.length) return null;
        return (
          <div key={g.id}>
            {g.title && <div className="section-title"><span>{g.title}</span></div>}
            {g.note && <div className="small muted" style={{ margin: "-4px 2px 10px" }}>{g.note}</div>}
            <div className="stack">
              {items.map((r) => {
                const o = open(r.name);
                return (
                  <div className="card res" key={r.id}>
                    {r.phone ? (
                      <a className={`call ${r.category === "emergency" ? "red" : ""}`} href={telHref(r.phone)} aria-label={`Call ${r.name}`}><IconPhone size={18} /></a>
                    ) : (
                      <span className="call none"><IconInfo size={18} /></span>
                    )}
                    <div className="grow">
                      <div className="row between" style={{ alignItems: "flex-start" }}>
                        <b style={{ fontSize: 14.5 }}>{r.name}</b>
                        {o !== undefined && o !== null && <span className={`chip ${o ? "ok" : "off"}`}>{o ? "Open now" : "Closed now"}</span>}
                      </div>
                      <div className="num">{r.phone_display}</div>
                      <div className="small muted" style={{ marginTop: 4 }}>{r.description}</div>
                      <div className="tiny faint" style={{ marginTop: 6 }}>
                        {r.hours} · {r.who} · <a href={r.source_url} target="_blank" rel="noreferrer">source</a>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
