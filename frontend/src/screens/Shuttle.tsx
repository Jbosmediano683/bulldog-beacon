import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, distanceM, type ShuttleBus, type ShuttleEta, type ShuttleOption, type ShuttlePlan, type ShuttleSystem } from "../api";
import { createBaseMap, mapColors, mePin } from "../components/mapBase";
import { locate, walkMinutes, type Located } from "../geo";
import { IconChevron, IconWalk } from "../icons";
import { useApp } from "../state";

const LIVE_EVERY_MS = 10000;

function clockIn(minutes: number): string {
  return new Date(Date.now() + minutes * 60000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function TripSteps({ o, dest }: { o: ShuttleOption; dest: string }) {
  return (
    <ol className="trip-steps">
      <li><IconWalk size={14} /> Walk {o.board.walk_min} min to <b>{o.board.name}</b></li>
      <li>
        <span className="swatch" style={{ background: o.color }} /><b>{o.route}</b>
        {o.bus ? ` bus ${o.bus}` : ""} comes in <b>{o.bus_in_min} min</b>
        <span className="tiny faint"> ({o.bus_timing === "live" ? "live" : "estimated: you'd miss the next one"})</span>
      </li>
      <li>
        Ride {o.ride_min} min, {o.stops_on_ride} {o.stops_on_ride === 1 ? "stop" : "stops"} ({o.ride_km} km)
        <span className="tiny faint"> ({o.ride_timing === "live" ? "live" : o.ride_timing === "measured" ? "from current bus speeds" : "typical speed"})</span>
        {o.long_way_around && <span className="chip warn" style={{ marginLeft: 6 }}>goes the long way around</span>}
      </li>
      <li>Get off at <b>{o.alight.name}</b>, walk {o.alight.walk_min} min to {dest}</li>
    </ol>
  );
}

export default function ShuttleScreen() {
  const { here, go, places } = useApp();
  const [sys, setSys] = useState<ShuttleSystem | null>(null);
  const [buses, setBuses] = useState<ShuttleBus[]>([]);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [shown, setShown] = useState<Set<number> | null>(null);
  const [stopId, setStopId] = useState<number | null>(null);
  const [etas, setEtas] = useState<ShuttleEta[] | null>(null);
  const [loc, setLoc] = useState<Located | null>(null);
  const [dest, setDest] = useState<number | "">("");
  const [plan, setPlan] = useState<ShuttlePlan | null>(null);
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [pick, setPick] = useState(0);
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layers = useRef<{ routes: L.LayerGroup; stops: L.LayerGroup; buses: L.LayerGroup; me: L.LayerGroup; trip: L.LayerGroup } | null>(null);

  useEffect(() => {
    api<ShuttleSystem>("/api/shuttle").then((s) => {
      setSys(s);
      setShown(new Set(s.routes.filter((r) => r.running_now).map((r) => r.id)));
    }).catch(() => setSys({ routes: [], stops: [], announcements: [], hours: "", source: "", error: "Couldn't load the shuttle map." }));
    locate().then(setLoc);
  }, []);

  useEffect(() => {
    const load = () => api<{ buses: ShuttleBus[]; error: string | null }>("/api/shuttle/live")
      .then((r) => { setBuses(r.buses); setLiveError(r.error); }).catch(() => setLiveError("Live bus positions aren't available right now."));
    load();
    const t = window.setInterval(load, LIVE_EVERY_MS);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (stopId === null) return;
    setEtas(null);
    const load = () => api<ShuttleEta[]>(`/api/shuttle/eta?stop=${stopId}`).then(setEtas).catch(() => setEtas([]));
    load();
    const t = window.setInterval(load, 20000);
    return () => window.clearInterval(t);
  }, [stopId]);

  // Plan a trip: from the phone's location in New Haven, otherwise from the location set at the top of the app.
  const gps = loc?.kind === "gps" ? loc.fix : null;
  useEffect(() => {
    if (dest === "" || !here) { setPlan(null); return; }
    let live = true;
    setPlanning(true);
    setPlanError(null);
    setStopId(null);
    const q = new URLSearchParams({ dest_place_id: String(dest), place_id: String(here.id) });
    if (gps) { q.set("lat", String(gps.lat)); q.set("lng", String(gps.lng)); }
    api<ShuttlePlan>(`/api/shuttle/plan?${q}`)
      .then((p) => { if (live) { setPlan(p); setPick(0); } })
      .catch((e) => { if (live) setPlanError(e instanceof Error ? e.message : "Couldn't plan that trip."); })
      .finally(() => { if (live) setPlanning(false); });
    return () => { live = false; };
  }, [dest, here?.id, gps?.lat, gps?.lng]); // eslint-disable-line react-hooks/exhaustive-deps

  const trip = plan && plan.options.length ? plan.options[Math.min(pick, plan.options.length - 1)] : null;
  const routeById = useMemo(() => new Map((sys?.routes ?? []).map((r) => [r.id, r])), [sys]);
  const stopById = useMemo(() => new Map((sys?.stops ?? []).map((s) => [s.id, s])), [sys]);
  // While a trip is shown, the map shows only that route.
  const visibleRoutes = useMemo(() => new Set(trip ? [trip.route_id] : [...(shown ?? [])]), [trip, shown]);
  const visibleStops = useMemo(() => {
    const ids = new Set<number>();
    for (const r of sys?.routes ?? []) if (visibleRoutes.has(r.id)) r.stops.forEach((s) => ids.add(s));
    return ids;
  }, [sys, visibleRoutes]);
  const me = gps ? { lat: gps.lat, lng: gps.lng, label: "You" } : here ? { lat: here.lat, lng: here.lng, label: here.name } : null;
  const nearestStop = useMemo(() => {
    if (!me || !sys) return null;
    let best: { id: number; m: number } | null = null;
    for (const id of visibleStops.size ? visibleStops : new Set(sys.stops.map((s) => s.id))) {
      const s = stopById.get(id);
      if (!s) continue;
      const m = distanceM(me, s);
      if (!best || m < best.m) best = { id, m };
    }
    return best;
  }, [me?.lat, me?.lng, sys, visibleStops, stopById]); // eslint-disable-line react-hooks/exhaustive-deps

  // Build the map once the system is loaded.
  useEffect(() => {
    if (!el.current || map.current || !sys) return;
    const m = createBaseMap(el.current);
    layers.current = {
      routes: L.layerGroup().addTo(m), stops: L.layerGroup().addTo(m), trip: L.layerGroup().addTo(m),
      buses: L.layerGroup().addTo(m), me: L.layerGroup().addTo(m),
    };
    map.current = m;
    return () => { map.current?.remove(); map.current = null; };
  }, [sys]);

  function frame(pts: L.LatLngExpression[], maxZoom: number) {
    const m = map.current;
    if (!m || !pts.length) return;
    const box = L.latLngBounds(pts).pad(0.08);
    // After the map has its real size (setTimeout, not requestAnimationFrame: rAF doesn't fire in hidden tabs).
    window.setTimeout(() => { if (map.current) { m.invalidateSize(); m.fitBounds(box, { maxZoom, animate: false }); } }, 150);
  }

  // Routes and stops.
  useEffect(() => {
    const g = layers.current;
    if (!g || !sys || !shown) return;
    g.routes.clearLayers();
    g.stops.clearLayers();
    const pts: L.LatLngExpression[] = [];
    for (const r of sys.routes) {
      if (!visibleRoutes.has(r.id) || r.path.length < 2) continue;
      L.polyline(r.path as [number, number][], { color: r.color, weight: trip ? 3 : 4, opacity: trip ? 0.3 : 0.85 })
        .bindTooltip(r.name, { sticky: true }).addTo(g.routes);
      pts.push(...(r.path as [number, number][]));
    }
    for (const id of visibleStops) {
      const s = stopById.get(id);
      if (!s) continue;
      L.circleMarker([s.lat, s.lng], { radius: id === stopId ? 8 : 5, color: mapColors().ink, weight: 2, fillColor: id === stopId ? "#ffd166" : mapColors().stopFill, fillOpacity: 1 })
        .bindTooltip(s.name, { direction: "top" }).on("click", () => setStopId(id)).addTo(g.stops);
    }
    if (!trip && pts.length && stopId === null) frame(pts, 15);
  }, [sys, shown, visibleRoutes, visibleStops, stopById, stopId, trip]); // eslint-disable-line react-hooks/exhaustive-deps

  // The planned trip: walk to the stop, the ride itself, walk to the destination.
  useEffect(() => {
    const g = layers.current;
    if (!g) return;
    g.trip.clearLayers();
    if (!plan) return;
    const d: [number, number] = [plan.dest.lat, plan.dest.lng], o: [number, number] = [plan.origin.lat, plan.origin.lng];
    L.marker(d, { icon: L.divIcon({ className: "", html: '<div class="pin info" style="background:#00356b"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }) })
      .bindTooltip(plan.dest.name, { direction: "top", permanent: true, className: "dest-label" }).addTo(g.trip);
    if (!trip) {
      L.polyline([o, d], { color: mapColors().edge, weight: 4, dashArray: "8 8" }).addTo(g.trip);
      frame([o, d], 17);
      return;
    }
    const b: [number, number] = [trip.board.lat, trip.board.lng], a: [number, number] = [trip.alight.lat, trip.alight.lng];
    L.polyline([o, b], { color: mapColors().walk, weight: 3, dashArray: "4 6" }).addTo(g.trip);
    L.polyline([a, d], { color: mapColors().walk, weight: 3, dashArray: "4 6" }).addTo(g.trip);
    if (trip.path.length > 1) L.polyline(trip.path as [number, number][], { color: trip.color, weight: 7, opacity: 0.95 }).addTo(g.trip);
    for (const [p, label] of [[b, `Board: ${trip.board.name}`], [a, `Get off: ${trip.alight.name}`]] as const) {
      L.circleMarker(p, { radius: 9, color: trip.color, weight: 4, fillColor: mapColors().stopFill, fillOpacity: 1 }).bindTooltip(label, { direction: "top" }).addTo(g.trip);
    }
    frame([o, d, b, a, ...(trip.path as [number, number][])], 16);
  }, [plan, trip]); // eslint-disable-line react-hooks/exhaustive-deps

  // Live buses.
  useEffect(() => {
    const g = layers.current;
    if (!g) return;
    g.buses.clearLayers();
    for (const b of buses) {
      const r = routeById.get(b.route ?? -1);
      if (r && !visibleRoutes.has(r.id)) continue;
      const color = r?.color ?? "#00356b";
      L.marker([b.lat, b.lng], {
        icon: L.divIcon({ className: "", iconSize: [26, 26], iconAnchor: [13, 13],
          html: `<div class="bus-pin" style="background:${color}"><span style="transform:rotate(${b.heading}deg)">&#9650;</span></div>` }),
        zIndexOffset: 400,
      }).bindTooltip(`${r?.name ?? "Shuttle"} · bus ${b.name}`, { direction: "top" }).addTo(g.buses);
    }
  }, [buses, routeById, visibleRoutes, sys]);

  useEffect(() => {
    const g = layers.current;
    if (!g || !me) return;
    g.me.clearLayers();
    L.marker([me.lat, me.lng], { icon: mePin(), zIndexOffset: 500 }).bindTooltip(me.label, { direction: "top" }).addTo(g.me);
  }, [me?.lat, me?.lng, sys]); // eslint-disable-line react-hooks/exhaustive-deps

  function pickStop(id: number) {
    setStopId(id);
    const s = stopById.get(id);
    if (s) map.current?.setView([s.lat, s.lng], 17);
  }

  function toggle(id: number) {
    setShown((cur) => {
      const next = new Set(cur ?? []);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  if (!sys) return <div className="empty">Loading the shuttle map…</div>;
  const stop = stopId !== null ? stopById.get(stopId) : null;
  const routesAtStop = stop ? sys.routes.filter((r) => r.stops.includes(stop.id)) : [];
  const running = sys.routes.filter((r) => r.running_now);
  const sorted = [...running, ...sys.routes.filter((r) => !r.running_now)];
  const fromLabel = gps ? "your location" : here ? `${here.name} (set at the top of the app)` : "your location";
  const best = plan?.options[0];

  return (
    <div>
      <button className="back-link" onClick={() => go("resources")}><IconChevron size={14} /> Resources</button>
      <div className="h1">Yale Shuttle</div>
      <p className="small muted" style={{ marginTop: 2 }}>
        Free for the Yale community. {running.length} of {sys.routes.length} routes running now, {buses.length} buses on the road.
        Bus positions update every 10 seconds.
      </p>
      {sys.error && <div className="verdict blocked small">{sys.error} Beacon will show the map again as soon as it can reach it.</div>}
      {sys.announcements.map((a, i) => (
        <div key={i} className="notice small"><b>{a.title}:</b> {a.message}</div>
      ))}

      <div className="card planner">
        <div className="h2" style={{ fontSize: 15, margin: 0 }}>Where are you going?</div>
        <select className="select" style={{ marginTop: 8 }} value={dest} onChange={(e) => setDest(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Choose a destination</option>
          {places.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <div className="tiny faint" style={{ marginTop: 5 }}>
          From {fromLabel}. Beacon compares every running route, in the direction the bus actually drives, with just walking.
        </div>

        {planning && <div className="small muted" style={{ marginTop: 10 }}>Finding the fastest way…</div>}
        {planError && <div className="verdict blocked small" style={{ marginTop: 10 }}>{planError}</div>}
        {plan && !planning && (
          <div style={{ marginTop: 10 }}>
            {plan.error ? (
              <div className="verdict blocked small">{plan.error}</div>
            ) : plan.recommend === "shuttle" && best ? (
              <div className="plan-best">
                <div className="plan-headline">
                  Take the <span className="swatch" style={{ background: best.color }} /><b>{best.route}</b>: arrive about {best.arrive_at}
                  <span className="muted"> ({best.total_min} min)</span>
                </div>
                <div className="tiny faint">Walking would take about {plan.walk_only_min} min.</div>
              </div>
            ) : plan.recommend === "walk" ? (
              <div className="plan-best walk">
                <div className="plan-headline"><IconWalk size={16} /> Walking is fastest: about {plan.walk_only_min} min</div>
                <div className="tiny faint">
                  {best ? `The quickest shuttle would take ${best.total_min} min (${best.route}).` : "No shuttle ride beats walking from here."}
                </div>
                <button className="btn primary sm" style={{ marginTop: 8 }} onClick={() => go("walk", { walkDraft: { dest_place_id: plan.dest.id } })}>
                  Walk With Me to {plan.dest.name}
                </button>
              </div>
            ) : (
              <div className="plan-best none">
                <div className="plan-headline">No single Yale Shuttle ride gets you there right now</div>
                <div className="tiny faint">
                  Walking takes about {plan.walk_only_min} min.
                  {plan.not_running_now?.length ? ` Later: ${plan.not_running_now.map((r) => `${r.route} (${r.hours})`).join(", ")}.` : ""}
                  {" "}After 6 pm, Nighttime Safe Ride is (203) 432-6330.
                </div>
              </div>
            )}

            {trip && <TripSteps o={trip} dest={plan.dest.name} />}

            {plan.options.length > 1 && (
              <div className="plan-alts">
                <div className="tiny faint">Compare routes (tap one to see it)</div>
                {plan.options.map((o, i) => (
                  <button key={o.route_id} className={`plan-alt ${i === pick ? "on" : ""}`} onClick={() => setPick(i)}>
                    <span><span className="swatch" style={{ background: o.color }} />{o.route}</span>
                    <span>{o.total_min} min{o.long_way_around ? " · long way around" : ""}</span>
                  </button>
                ))}
              </div>
            )}
            <button className="linkish tiny" style={{ marginTop: 8 }} onClick={() => setDest("")}>Clear trip and show all routes</button>
          </div>
        )}
      </div>

      {!plan && nearestStop && me && (
        <button className="card nearest-card as-button" onClick={() => pickStop(nearestStop.id)}>
          <div className="tiny faint">NEAREST STOP {gps ? "TO YOU" : `TO ${here?.name.toUpperCase()}`}</div>
          <div className="row between" style={{ alignItems: "baseline", marginTop: 2 }}>
            <b style={{ fontSize: 16 }}>{stopById.get(nearestStop.id)?.name}</b>
            <span className="small muted">{Math.round(nearestStop.m)} m · {walkMinutes(nearestStop.m)} min walk</span>
          </div>
          <div className="tiny" style={{ color: "var(--link)", marginTop: 3 }}>Show next arrivals</div>
        </button>
      )}

      {!plan && (
        <div className="route-chips">
          {sorted.map((r) => (
            <button key={r.id} className={`route-chip ${shown?.has(r.id) ? "on" : ""} ${r.running_now ? "" : "idle"}`} onClick={() => toggle(r.id)}
                    title={r.hours}>
              <span className="swatch" style={{ background: r.color }} />{r.name}
              <span className="tiny faint">{r.running_now ? "running" : r.hours}</span>
            </button>
          ))}
        </div>
      )}

      <div ref={el} className="map tall" style={{ marginTop: 10 }} />
      {liveError && <div className="tiny faint" style={{ marginTop: 6 }}>{liveError}</div>}

      {stop && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="row between">
            <b>{stop.name}</b>
            <button className="linkish" onClick={() => setStopId(null)}>Close</button>
          </div>
          <div className="row" style={{ gap: 6, flexWrap: "wrap", marginTop: 6 }}>
            {routesAtStop.map((r) => (
              <span key={r.id} className="chip"><span className="swatch" style={{ background: r.color }} />{r.name}</span>
            ))}
          </div>
          <div className="section-title" style={{ marginTop: 10 }}><span>Next arrivals</span></div>
          {etas === null ? <div className="small muted">Checking…</div>
            : etas.length === 0 ? <div className="small muted">No buses are on their way to this stop right now. Routes here: {routesAtStop.map((r) => `${r.name} (${r.hours})`).join(", ") || "none"}.</div>
            : (
              <div className="stack" style={{ gap: 6 }}>
                {etas.slice(0, 6).map((e, i) => {
                  const r = routeById.get(e.route ?? -1);
                  return (
                    <div key={i} className="row between small">
                      <span><span className="swatch" style={{ background: r?.color ?? "#999" }} />{r?.name ?? "Shuttle"} · bus {e.bus}</span>
                      <b>{e.minutes > 0 ? `${e.minutes} min · ${clockIn(e.minutes)}` : "Arriving"}</b>
                    </div>
                  );
                })}
              </div>
            )}
        </div>
      )}

      <div className="tiny faint" style={{ marginTop: 10 }}>
        {sys.hours}. Live from {sys.source}. Trip times use live arrivals where Yale's system has them, otherwise each route's
        current speed. Tap a stop on the map for its next arrivals.
      </div>
    </div>
  );
}
