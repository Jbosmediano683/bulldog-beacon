import L from "leaflet";
import { useEffect, useRef } from "react";
import { type Incident, type YaleEvent } from "../api";
import { createBaseMap, mapColors } from "./mapBase";

type Pt = { lat: number; lng: number };

const CAL_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><rect x="4" y="5.5" width="16" height="14.5" rx="2"/><path d="M4 10.5h16M8.5 3.5v4M15.5 3.5v4"/></svg>';

export default function BeaconMap({
  incidents = [], events = [], me, focusId, focusEventId, onSelect, onSelectEvent, route, tall = false, view = "",
}: {
  incidents?: Incident[];
  events?: YaleEvent[];
  me?: Pt & { label?: string };
  focusId?: number | null;
  focusEventId?: number | null;
  onSelect?: (id: number) => void;
  onSelectEvent?: (id: number) => void;
  route?: [Pt, Pt];
  tall?: boolean;
  view?: string;  // changing this re-frames the map (e.g. switching layers)
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const framed = useRef<string>("");

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = createBaseMap(el.current);
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => { map.current?.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const m = map.current, g = layer.current;
    if (!m || !g) return;
    g.clearLayers();
    const pts: L.LatLngExpression[] = [];
    if (route) {
      L.polyline(route.map((p) => [p.lat, p.lng] as [number, number]), { color: mapColors().edge, weight: 5, opacity: 0.9, dashArray: "8 8" }).addTo(g);
      route.forEach((p) => pts.push([p.lat, p.lng]));
      L.marker([route[1].lat, route[1].lng], {
        icon: L.divIcon({ className: "", html: '<div class="pin info" style="background:#00356b"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }),
      }).addTo(g);
    }
    if (me) {
      L.marker([me.lat, me.lng], {
        icon: L.divIcon({ className: "", html: '<div class="me-pin"></div>', iconSize: [16, 16], iconAnchor: [8, 8] }),
        zIndexOffset: 500,
      }).bindTooltip(me.label ?? "You", { direction: "top" }).addTo(g);
      pts.push([me.lat, me.lng]);
    }
    for (const ev of events) {
      if (ev.lat === null || ev.lng === null) continue;
      const mk = L.marker([ev.lat, ev.lng], {
        icon: L.divIcon({
          className: "",
          html: `<div class="event-pin ${ev.status === "now" ? "now" : ""} ${ev.id === focusEventId ? "focus" : ""}">${CAL_SVG}</div>`,
          iconSize: [22, 22], iconAnchor: [11, 11],
        }),
        zIndexOffset: ev.id === focusEventId ? 1000 : 200,
      }).addTo(g);
      mk.bindTooltip(`${ev.title}${ev.status === "now" ? " · happening now" : ""}`, { direction: "top" });
      if (onSelectEvent) mk.on("click", () => onSelectEvent(ev.id));
      pts.push([ev.lat, ev.lng]);
    }
    for (const inc of incidents) {
      const mk = L.marker([inc.lat, inc.lng], {
        icon: L.divIcon({
          className: "",
          html: `<div class="pin ${inc.severity} ${inc.id === focusId ? "focus" : ""}"></div>`,
          iconSize: [18, 18], iconAnchor: [9, 9],
        }),
        zIndexOffset: inc.id === focusId ? 1000 : 0,
      }).addTo(g);
      mk.bindTooltip(inc.title + (inc.demo ? " (demo)" : ""), { direction: "top" });
      if (onSelect) mk.on("click", () => onSelect(inc.id));
      pts.push([inc.lat, inc.lng]);
    }
    // Frame the map once (or when the focus changes); later refreshes keep the user's pan and zoom.
    const focus = incidents.find((i) => i.id === focusId) ?? events.find((e) => e.id === focusEventId && e.lat !== null);
    const frameKey = `${view}|${focusId ?? ""}|${focusEventId ?? ""}|${route ? route.map((p) => p.lat).join() : ""}|${pts.length > 1}`;
    if (frameKey === framed.current) return;
    framed.current = frameKey;
    // Wait a moment so the container has its final size (sheets and tabs animate in).
    window.setTimeout(() => {
      if (!map.current) return;
      m.invalidateSize();
      if (focus && focus.lat !== null && focus.lng !== null) m.setView([focus.lat, focus.lng], 17, { animate: true });
      else if (pts.length > 1) m.fitBounds(L.latLngBounds(pts), { padding: [28, 28], maxZoom: route ? 17 : 16 });
      else if (me) m.setView([me.lat, me.lng], 16);
    }, 100);
  }, [incidents, events, me?.lat, me?.lng, focusId, focusEventId, route?.[0].lat, route?.[1].lat, view]); // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={el} className={`map ${tall ? "tall" : ""}`} />;
}
