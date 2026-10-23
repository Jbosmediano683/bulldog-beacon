import { useEffect, useState } from "react";
import { api, telHref, type Resource, type ServiceStatus } from "../api";
import { IconChevron, IconInfo, IconMap, IconPhone } from "../icons";
import { useApp, type Tab } from "../state";

// These resources open a map inside Beacon instead of sending people to another site or app.
const MAPS: Record<string, { tab: Tab; cta: string }> = {
  "Blue emergency phones": { tab: "bluephones", cta: "See every blue phone on the map" },
  "Yale Shuttle": { tab: "shuttle", cta: "Open the live shuttle map" },
};

const GROUPS: { id: string; title: string; note?: string }[] = [
  { id: "emergency", title: "Emergency" },
  { id: "escort", title: "Get there safely" },
  { id: "ride", title: "" },
  { id: "mental_health", title: "Talk to someone", note: "Feeling shaken, anxious, or not okay is a normal reaction. These people are there for it." },
  { id: "sexual_misconduct", title: "Sexual harassment and assault" },
];

export default function Resources() {
  const { go } = useApp();
  const [data, setData] = useState<{ resources: Resource[]; status: ServiceStatus } | null>(null);
  useEffect(() => { api<{ resources: Resource[]; status: ServiceStatus }>("/api/resources").then(setData).catch(() => {}); }, []);
  if (!data) return <div className="empty">Loading…</div>;
  const open = (name: string) => data.status.services.find((s) => s.name === name)?.open_now;

  return (
    <div>
      <div className="h1">Resources</div>
      <p className="small muted" style={{ marginTop: 2 }}>
        Every number here was copied from a Yale web page (source linked) and checked in October 2026. Beacon's AI is only
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
                const opensMap = MAPS[r.name];
                return (
                  <div className={`card res ${opensMap ? "opens" : ""}`} key={r.id}
                       role={opensMap ? "button" : undefined} tabIndex={opensMap ? 0 : undefined}
                       onClick={opensMap ? () => go(opensMap.tab) : undefined}
                       onKeyDown={opensMap ? (e) => { if (e.key === "Enter") go(opensMap.tab); } : undefined}>
                    {opensMap ? (
                      <span className="call map"><IconMap size={18} /></span>
                    ) : r.phone ? (
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
                      {opensMap && <div className="map-cta">{opensMap.cta} <IconChevron size={13} /></div>}
                      <div className="tiny faint" style={{ marginTop: 6 }}>
                        {r.hours} · {r.who} · <a href={r.source_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>source</a>
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
