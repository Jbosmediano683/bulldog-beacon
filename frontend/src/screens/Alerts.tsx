import { useEffect, useState } from "react";
import { api, distanceM, type Incident, type YaleEvent } from "../api";
import BeaconMap from "../components/BeaconMap";
import Composer from "../components/Composer";
import EventCard, { EventSheet } from "../components/EventCard";
import IncidentCard from "../components/IncidentCard";
import { IconPlus } from "../icons";
import { useApp, type MapLayer } from "../state";

const RANGES = [
  { h: 6, label: "6 h" },
  { h: 24, label: "24 h" },
  { h: 72, label: "3 days" },
  { h: 168, label: "7 days" },
];

type EventFeed = { events: YaleEvent[]; error: string | null; source: string };

export default function Alerts() {
  const { here, focusIncidentId, clearFocus, focusEventId, clearFocusEvent, user, mapLayer, setMapLayer } = useApp();
  const [hours, setHours] = useState(24);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [feed, setFeed] = useState<EventFeed | null>(null);
  const [focus, setFocus] = useState<number | null>(focusIncidentId);
  const [focusEvent, setFocusEvent] = useState<number | null>(null);
  const [composing, setComposing] = useState(false);
  const [openEvent, setOpenEvent] = useState<YaleEvent | null>(null);
  const layer: MapLayer = mapLayer;
  const showSafety = layer !== "events";
  const showEvents = layer !== "safety";

  const load = () => api<Incident[]>(`/api/incidents?hours=${hours}`).then(setIncidents).catch(() => {});
  useEffect(() => {
    load();
    const t = window.setInterval(load, 15000);
    return () => window.clearInterval(t);
  }, [hours]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const loadEvents = () => api<EventFeed>("/api/events?hours=12").then(setFeed).catch(() => {});
    loadEvents();
    const t = window.setInterval(loadEvents, 5 * 60000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (focusIncidentId) {
      setFocus(focusIncidentId);
      clearFocus();
      window.setTimeout(() => document.getElementById(`incident-${focusIncidentId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 350);
    }
  }, [focusIncidentId, clearFocus]);

  useEffect(() => {
    if (focusEventId) {
      setFocusEvent(focusEventId);
      setFocus(null);
      clearFocusEvent();
    }
  }, [focusEventId, clearFocusEvent]);

  const sorted = [...incidents].sort((a, b) => Date.parse(b.last_reported) - Date.parse(a.last_reported));
  const events = feed?.events ?? [];
  const eventsShown = layer === "events" ? events : events.slice(0, 4);

  function selectEvent(id: number) {
    setFocusEvent(id);
    setFocus(null);
    const ev = events.find((e) => e.id === id);
    if (ev) setOpenEvent(ev);
  }

  function showOnMap(ev: YaleEvent) {
    setOpenEvent(null);
    setFocusEvent(ev.id);
    setFocus(null);
    document.querySelector(".app-scroll")?.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div>
      <div className="h1">Campus map</div>
      <div className="small muted">Safety alerts from the Yale community, and what's happening at Yale today.</div>

      <div className="layer-toggle" role="tablist">
        {([["all", "Everything"], ["safety", "Safety"], ["events", "Events"]] as const).map(([id, label]) => (
          <button key={id} className={layer === id ? "on" : ""} onClick={() => { setMapLayer(id); setFocusEvent(null); }}>{label}</button>
        ))}
      </div>
      {showSafety && (
        <div className="filters">
          {RANGES.map((r) => (
            <button key={r.h} className={hours === r.h ? "on" : ""} onClick={() => setHours(r.h)}>{r.label}</button>
          ))}
        </div>
      )}
      <div style={{ marginTop: showSafety ? 0 : 12 }}>
        <BeaconMap incidents={showSafety ? incidents : []} events={showEvents ? events : []}
                   me={here ? { lat: here.lat, lng: here.lng, label: `You: ${here.name}` } : undefined}
                   focusId={focus} focusEventId={focusEvent}
                   onSelect={(id) => { setFocus(id); setFocusEvent(null); document.getElementById(`incident-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); }}
                   onSelectEvent={selectEvent} view={`${layer}-${events.length > 0}`} tall />
      </div>
      <div className="row wrap small muted" style={{ gap: 12, margin: "10px 2px 0" }}>
        {showSafety && (
          <>
            <span className="row" style={{ gap: 5 }}><i className="sev info" />Info</span>
            <span className="row" style={{ gap: 5 }}><i className="sev caution" />Caution</span>
            <span className="row" style={{ gap: 5 }}><i className="sev warning" />Warning</span>
            <span className="row" style={{ gap: 5 }}><i className="sev urgent" />Urgent</span>
          </>
        )}
        {showEvents && <span className="row" style={{ gap: 5 }}><i className="sev" style={{ background: "var(--event)", borderRadius: 3 }} />Yale event</span>}
      </div>

      {showEvents && (
        <>
          <div className="section-title">
            <span>Happening at Yale{events.length ? ` · ${events.length}` : ""}</span>
            {layer === "all" && events.length > eventsShown.length && <button onClick={() => setMapLayer("events")}>See all</button>}
          </div>
          {feed?.error && events.length === 0 ? (
            <div className="card empty small">{feed.error}. Events will show here when the calendar is reachable.</div>
          ) : events.length === 0 ? (
            <div className="card empty small">{feed ? "Nothing else on Yale's calendar today." : "Checking Yale's calendar…"}</div>
          ) : (
            <div className="stack">
              {eventsShown.map((e) => (
                <EventCard key={e.id} event={e} onOpen={() => setOpenEvent(e)} />
              ))}
              <div className="tiny faint" style={{ textAlign: "center" }}>Live from Yale's public calendar, events.yale.edu</div>
            </div>
          )}
        </>
      )}

      {showSafety && (
        <>
          <div className="section-title"><span>Safety · {sorted.length} incident{sorted.length === 1 ? "" : "s"} · newest first</span></div>
          {sorted.length === 0 ? (
            <div className="card empty">No reports in this window. That's good news.</div>
          ) : (
            <div className="stack">
              {sorted.map((i) => (
                <IncidentCard key={`${i.id}-${i.id === focus}`} incident={i} startOpen={i.id === focus}
                              distance={here ? distanceM(here, i) : undefined} />
              ))}
            </div>
          )}
        </>
      )}
      <div style={{ height: 70 }} />
      {user.role !== "dispatcher" && (
        <button className="fab" onClick={() => setComposing(true)}><IconPlus size={18} /> Post alert</button>
      )}
      {openEvent && <EventSheet event={openEvent} onClose={() => setOpenEvent(null)} onShowOnMap={() => showOnMap(openEvent)} />}
      {composing && <Composer onClose={() => setComposing(false)} onPublished={() => { window.setTimeout(load, 2500); window.setTimeout(load, 9000); }} />}
    </div>
  );
}
