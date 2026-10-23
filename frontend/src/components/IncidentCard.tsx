import { useState } from "react";
import { CATEGORY_LABELS, timeAgo, type Incident } from "../api";
import { CatIcon } from "../icons";

export function SeverityLabel({ severity }: { severity: Incident["severity"] }) {
  const text = { info: "Info", caution: "Caution", warning: "Warning", urgent: "Urgent" }[severity];
  return (
    <span className={`row sev-text ${severity}`} style={{ gap: 5, fontWeight: 650 }}>
      <i className={`sev ${severity}`} />
      {text}
    </span>
  );
}

export default function IncidentCard({
  incident, distance, onOpen, expandable = true, startOpen = false,
}: {
  incident: Incident;
  distance?: number;
  onOpen?: () => void;
  expandable?: boolean;
  startOpen?: boolean;
}) {
  const [open, setOpen] = useState(startOpen);
  const reports = incident.reports ?? [];
  return (
    <div className={`card click incident-card ${incident.severity}`} id={`incident-${incident.id}`} onClick={() => (onOpen ? onOpen() : expandable && setOpen(!open))}>
      <div className="incident">
        <div className="ico"><CatIcon category={incident.category} /></div>
        <div className="grow">
          <div className="title">{incident.title}</div>
          <div className="meta">
            <SeverityLabel severity={incident.severity} />
            <span>·</span>
            <span>{timeAgo(incident.last_reported)}</span>
            {distance !== undefined && (<><span>·</span><span>{distance < 1000 ? `${Math.round(distance / 10) * 10} m` : `${(distance / 1000).toFixed(1)} km`} away</span></>)}
          </div>
          <div className="row wrap" style={{ gap: 6, marginTop: 7 }}>
            <span className="chip">{CATEGORY_LABELS[incident.category] ?? incident.category}</span>
            <span className={`chip ${incident.report_count > 1 ? "shield" : ""}`}>
              {incident.report_count > 1 ? `${incident.report_count} separate reports` : "1 report"}
            </span>
            {(incident.confirmations ?? 0) > 0 && (
              <span className="chip shield">{incident.confirmations} confirmed</span>
            )}
            {incident.demo && <span className="chip demo">Demo report (fictional)</span>}
          </div>
          {(open || !expandable) && (
            <>
              <div className="summary">{incident.summary}</div>
              {incident.advice && (
                <div className="advice"><span><b>What to do:</b> {incident.advice}</span></div>
              )}
              {open && reports.length > 0 && (
                <div className="reports">
                  {reports.map((r) => (
                    <div className="r" key={r.id}>
                      <div className="t">Community report · {timeAgo(r.created_at)}</div>
                      {r.text}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
