import { useEffect, useState } from "react";
import { api, distanceM, type Incident, type ServiceStatus, type Walk, type YaleEvent } from "../api";
import EventCard, { EventSheet } from "../components/EventCard";
import EscortSheet from "../components/EscortSheet";
import IncidentCard from "../components/IncidentCard";
import SosButton from "../components/SosButton";
import WalkMini from "../components/WalkMini";
import { IconCalendar, IconCar, IconChat, IconHeart, IconMoon, IconPhone, IconShield, IconWalk } from "../icons";
import { useApp } from "../state";

function greeting(): string {
  const h = Number(new Date().toLocaleString("en-US", { hour: "numeric", hour12: false, timeZone: "America/New_York" }));
  if (h < 5) return "Late night";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function Home() {
  const { user, here, go } = useApp();
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [status, setStatus] = useState<ServiceStatus | null>(null);
  const [walk, setWalk] = useState<Walk | null>(null);
  const [escort, setEscort] = useState(false);
  const [events, setEvents] = useState<YaleEvent[] | null>(null);
  const [openEvent, setOpenEvent] = useState<YaleEvent | null>(null);

  useEffect(() => {
    api<Incident[]>("/api/incidents?hours=24").then(setIncidents).catch(() => {});
    api<{ status: ServiceStatus }>("/api/resources").then((r) => setStatus(r.status)).catch(() => {});
    api<{ events: YaleEvent[] }>("/api/events?hours=12").then((r) => setEvents(r.events)).catch(() => setEvents([]));
    const loadWalk = () => api<Walk | null>("/api/walks/active").then(setWalk).catch(() => {});
    loadWalk();
    const t = window.setInterval(loadWalk, 5000);
    return () => window.clearInterval(t);
  }, []);

  const first = user.name.replace(/\(.*\)/, "").trim().split(" ")[0];
  const near = here
    ? incidents
        .map((i) => ({ i, d: distanceM(here, i) }))
        .filter((x) => x.d < 900)
        .sort((a, b) => a.d - b.d)
        .slice(0, 3)
    : [];
  const svc = (name: string) => status?.services.find((s) => s.name === name);
  const ride = svc("Nighttime Safe Ride");

  return (
    <div>
      <div className="greet">
        <div className="small muted">{status?.new_haven_time ?? ""} · New Haven</div>
        <div className="h1">{greeting()}, <span>{first}</span></div>
      </div>
      <div className="status-strip">
        <span className="chip ok">Walking escort open 24/7</span>
        {ride && <span className={`chip ${ride.open_now ? "ok" : "off"}`}>{ride.open_now ? "Safe Ride running" : "Safe Ride starts 6 pm"}</span>}
        {status?.after_dark_approx && <span className="chip"><IconMoon size={13} /> After dark</span>}
      </div>

      <SosButton />

      {walk && <WalkMini walk={walk} onOpen={() => go("walk")} />}

      <div className="section-title"><span>Quick help</span></div>
      <div className="quick-grid">
        <a className="quick" href="tel:2034324400">
          <span className="ic"><IconPhone size={18} /></span>
          <b>Call Yale PD</b>
          <small>(203) 432-4400 · 24/7</small>
        </a>
        <button className="quick" onClick={() => setEscort(true)}>
          <span className="ic"><IconShield size={18} /></span>
          <b>Walking escort</b>
          <small>Yale Security walks with you</small>
        </button>
        <button className="quick" onClick={() => go("walk")}>
          <span className="ic"><IconWalk size={18} /></span>
          <b>Walk With Me</b>
          <small>Contacts alerted if you don't check in</small>
        </button>
        <a className="quick" href="tel:2034326330">
          <span className="ic"><IconCar size={18} /></span>
          <b>Safe Ride</b>
          <small>(203) 432-6330 · 6 pm to 6 am</small>
        </a>
      </div>

      <div className="section-title">
        <span><IconCalendar size={14} /> Happening at Yale</span>
        <button onClick={() => go("alerts", { mapLayer: "events" })}>See all</button>
      </div>
      {events === null ? (
        <div className="card empty small">Checking Yale's calendar…</div>
      ) : events.length === 0 ? (
        <div className="card empty small">Nothing else on Yale's calendar in the next few hours.</div>
      ) : (
        <div className="stack">
          {events.filter((e) => e.status !== "all_day").concat(events.filter((e) => e.status === "all_day")).slice(0, 3).map((e) => (
            <EventCard key={e.id} event={e} onOpen={() => setOpenEvent(e)} />
          ))}
        </div>
      )}

      <div className="section-title">
        <span>Near you · last 24 h</span>
        <button onClick={() => go("alerts")}>Open map</button>
      </div>
      {near.length === 0 ? (
        <div className="card empty">Nothing reported within 900 m in the last 24 hours.</div>
      ) : (
        <div className="stack">
          {near.map(({ i, d }) => (
            <IncidentCard key={i.id} incident={i} distance={d} onOpen={() => go("alerts", { incidentId: i.id })} />
          ))}
        </div>
      )}

      <div className="section-title"><span>Ask Beacon</span></div>
      <button className="card click row" style={{ width: "100%", textAlign: "left" }}
              onClick={() => go("ask", { chatPrompt: `Is it OK to walk from ${here?.name ?? "here"} to my car right now?` })}>
        <span className="quick ic" style={{ border: 0, padding: 0, background: "var(--sky-soft)", width: 38, height: 38, display: "grid", placeItems: "center", borderRadius: 12 }}><IconChat size={18} /></span>
        <div className="grow">
          <b style={{ fontSize: 14 }}>“Is it OK to walk to my car right now?”</b>
          <div className="small muted">Beacon checks recent reports on your route and what's open.</div>
        </div>
      </button>

      <div className="section-title"><span>Your well-being</span></div>
      <div className="well-card">
        <div className="row" style={{ alignItems: "flex-start" }}>
          <span style={{ color: "var(--ink)", marginTop: 2 }}><IconHeart size={20} /></span>
          <div className="grow">
            <b>Shaken by something you saw or heard?</b>
            <div className="small muted" style={{ marginTop: 3 }}>
              Feeling unsafe takes a toll. Talking to someone helps, any time of day.
            </div>
            <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
              <button className="btn sm" onClick={() => go("resources")}>Talk to someone</button>
              <a className="btn sm ghost" href="tel:988">Call or text 988</a>
            </div>
          </div>
        </div>
      </div>

      {escort && <EscortSheet onClose={() => setEscort(false)} />}
      {openEvent && (
        <EventSheet event={openEvent} onClose={() => setOpenEvent(null)}
                    onShowOnMap={() => go("alerts", { mapLayer: "events", eventId: openEvent.id })} />
      )}
    </div>
  );
}
