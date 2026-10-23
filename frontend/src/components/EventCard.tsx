import type { YaleEvent } from "../api";
import { IconCalendar, IconChevron, IconPin, IconTicket } from "../icons";
import Sheet from "./Sheet";

const KIND_LABELS: Record<string, string> = {
  performance: "Performance", exhibition: "Exhibition", sports: "Sports", social: "Social", tour: "Tour",
  talk: "Talk", seminar: "Seminar", event: "Event",
};

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" });
}

function day(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", timeZone: "America/New_York" });
}

export function eventWhen(e: YaleEvent): string {
  if (e.status === "all_day") {
    if (!e.end || e.all_day) return "Open today";
    return Date.parse(e.start) <= Date.now() ? `Open now · until ${time(e.end)}` : `Opens ${time(e.start)} · until ${time(e.end)}`;
  }
  if (e.status === "now") return e.end ? `Happening now · until ${time(e.end)}` : "Happening now";
  const mins = Math.round((Date.parse(e.start) - Date.now()) / 60000);
  if (e.status === "soon") return `Starts ${time(e.start)} · in ${Math.max(mins, 1)} min`;
  const d = new Date(e.start).toLocaleDateString("en-US", { weekday: "short", timeZone: "America/New_York" });
  const today = new Date().toLocaleDateString("en-US", { weekday: "short", timeZone: "America/New_York" });
  return `${d === today ? "Today" : d} ${time(e.start)}${e.end ? `–${time(e.end)}` : ""}`;
}

function StatusChips({ event }: { event: YaleEvent }) {
  return (
    <div className="row wrap" style={{ gap: 6 }}>
      <span className={`chip ${event.status === "now" ? "ok" : event.status === "soon" ? "shield" : ""}`}>
        {eventWhen(event)}
      </span>
      {event.free && <span className="chip">Free</span>}
      {event.ticket_cost && !event.free && <span className="chip">{event.ticket_cost}</span>}
    </div>
  );
}

export default function EventCard({ event, onOpen }: { event: YaleEvent; onOpen: () => void }) {
  return (
    <div className="card event-card click" id={`event-${event.id}`} onClick={onOpen} role="button">
      {event.photo_url ? (
        <img className="event-photo" src={event.photo_url} alt="" />
      ) : (
        <div className="event-photo blank"><IconCalendar size={22} /></div>
      )}
      <div className="grow">
        <StatusChips event={event} />
        <div className="event-title">{event.title}</div>
        <div className="tiny muted" style={{ marginTop: 3 }}>
          {event.venue || "Location in event details"} · {KIND_LABELS[event.kind] ?? "Event"}
        </div>
        <div className="more-link row" style={{ gap: 2 }}>About this event <IconChevron size={14} /></div>
      </div>
    </div>
  );
}

/** "About this event": the calendar's details, shown inside Beacon. */
export function EventSheet({ event, onClose, onShowOnMap }: { event: YaleEvent; onClose: () => void; onShowOnMap?: () => void }) {
  const when = event.all_day || !event.end
    ? `${day(event.start)}${event.all_day ? "" : ` · ${time(event.start)}`}`
    : `${day(event.start)} · ${time(event.start)}–${time(event.end)}`;
  return (
    <Sheet onClose={onClose}>
      {(event.photo_large || event.photo_url) && (
        <img className="event-banner" src={event.photo_large ?? event.photo_url ?? ""} alt="" />
      )}
      <StatusChips event={event} />
      <div className="h2" style={{ fontSize: 19, marginTop: 8, lineHeight: 1.25 }}>{event.title}</div>
      <div className="small muted" style={{ marginTop: 4 }}>{when} · {KIND_LABELS[event.kind] ?? "Event"}</div>

      <div className="about-label">About this event</div>
      <div className="about-venue">
        <div className="grow">
          <div style={{ fontWeight: 700 }}>{event.venue || "See the event listing"}{event.room ? `, ${event.room}` : ""}</div>
          {event.address && <div className="small muted" style={{ marginTop: 2 }}>{event.address}</div>}
        </div>
      </div>
      <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
        {onShowOnMap && event.lat !== null && (
          <button className="btn sm" onClick={onShowOnMap}><IconPin size={15} /> View on map</button>
        )}
        {event.ics_url && <a className="btn sm" href={event.ics_url}><IconCalendar size={15} /> Add to calendar</a>}
        {event.ticket_url && <a className="btn sm" href={event.ticket_url} target="_blank" rel="noreferrer"><IconTicket size={15} /> Tickets</a>}
      </div>

      {event.description ? (
        <div className="about-text">{event.description}</div>
      ) : (
        <div className="small muted" style={{ marginTop: 14 }}>The calendar listing has no description.</div>
      )}

      <div className="tiny faint" style={{ marginTop: 16 }}>
        From Yale's public calendar · <a href={event.url} target="_blank" rel="noreferrer">original listing on events.yale.edu ↗</a>
      </div>
      <button className="btn block" style={{ marginTop: 14 }} onClick={onClose}>Close</button>
    </Sheet>
  );
}
