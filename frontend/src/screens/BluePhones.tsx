import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, distanceM, type BluePhones } from "../api";
import { createBaseMap, mapColors, mePin } from "../components/mapBase";
import { locate, walkMinutes, type Located } from "../geo";
import { IconChevron } from "../icons";
import { useApp } from "../state";

const COMPASS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"];

function direction(from: { lat: number; lng: number }, to: { lat: number; lng: number }): string {
  const dy = to.lat - from.lat, dx = (to.lng - from.lng) * Math.cos((from.lat * Math.PI) / 180);
  const deg = (Math.atan2(dx, dy) * 180) / Math.PI;
  return COMPASS[Math.round(((deg + 360) % 360) / 45) % 8];
}

export default function BluePhonesScreen() {
  const { here, go } = useApp();
  const [data, setData] = useState<BluePhones | null>(null);
  const [failed, setFailed] = useState(false);
  const [loc, setLoc] = useState<Located | null>(null);
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const phones = useRef<L.LayerGroup | null>(null);
  const near = useRef<L.LayerGroup | null>(null);

  useEffect(() => { api<BluePhones>("/api/blue-phones").then(setData).catch(() => setFailed(true)); }, []);
  useEffect(() => { locate().then(setLoc); }, []);

  // Where "you" are: the phone's location in New Haven, otherwise the location set at the top of the app.
  const me = loc?.kind === "gps" ? { lat: loc.fix.lat, lng: loc.fix.lng, label: "You (phone location)" }
    : here ? { lat: here.lat, lng: here.lng, label: `You (${here.name})` } : null;
  const nearest = useMemo(() => {
    if (!data || !me) return [];
    return data.phones.map((p) => ({ ...p, m: distanceM(me, p) })).sort((x, y) => x.m - y.m).slice(0, 3);
  }, [data, me?.lat, me?.lng]); // eslint-disable-line react-hooks/exhaustive-deps

  // The map draws right away; the phones are added as soon as they load.
  useEffect(() => {
    if (!el.current || map.current) return;
    const m = createBaseMap(el.current);
    phones.current = L.layerGroup().addTo(m);
    near.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => { map.current?.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const g = phones.current;
    if (!g || !data) return;
    g.clearLayers();
    for (const p of data.phones) {
      L.circleMarker([p.lat, p.lng], { radius: 5, color: "#ffffff", weight: 1.5, fillColor: mapColors().phone, fillOpacity: 0.95 })
        .bindTooltip("Blue emergency phone", { direction: "top" }).addTo(g);
    }
  }, [data]);

  useEffect(() => {
    const m = map.current, g = near.current;
    if (!m || !g || !me) return;
    g.clearLayers();
    L.marker([me.lat, me.lng], { icon: mePin(), zIndexOffset: 500 }).bindTooltip(me.label, { direction: "top" }).addTo(g);
    nearest.forEach((p, i) => {
      L.circleMarker([p.lat, p.lng], { radius: i === 0 ? 13 : 10, color: mapColors().ring, weight: 2.5, fill: false }).addTo(g);
    });
    if (nearest[0]) {
      L.polyline([[me.lat, me.lng], [nearest[0].lat, nearest[0].lng]], { color: mapColors().ring, weight: 3, dashArray: "6 6" }).addTo(g);
      const box = L.latLngBounds([[me.lat, me.lng], ...nearest.map((p) => [p.lat, p.lng] as [number, number])]).pad(0.6);
      // Frame after the map has its real size (setTimeout, not requestAnimationFrame: rAF doesn't fire in hidden tabs).
      window.setTimeout(() => { if (map.current) { m.invalidateSize(); m.fitBounds(box, { maxZoom: 18, animate: false }); } }, 150);
    }
  }, [nearest, data]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <button className="back-link" onClick={() => go("resources")}><IconChevron size={14} /> Resources</button>
      <div className="h1">Blue emergency phones</div>
      <p className="small muted" style={{ marginTop: 2 }}>
        {data ? `${data.count} phones` : "About 500 phones"} across campus, each under a blue light. Press the red button and you're
        connected straight to Yale Police for police, fire, or medical help. No phone or app needed.
      </p>

      {failed && (
        <div className="verdict blocked small" style={{ marginTop: 12 }}>
          Beacon couldn't load the blue-phone locations just now. Every blue phone is under a blue light, and the red button
          connects you to Yale Police. In an emergency, call 911.
        </div>
      )}

      {nearest[0] && me && (
        <div className="card nearest-card">
          <div className="tiny faint">NEAREST BLUE PHONE {loc?.kind === "gps" ? "TO YOU" : `TO ${here?.name.toUpperCase()}`}</div>
          <div className="row between" style={{ alignItems: "baseline", marginTop: 2 }}>
            <b style={{ fontSize: 22, color: "var(--ink)" }}>{Math.round(nearest[0].m)} m</b>
            <span className="small muted">about {walkMinutes(nearest[0].m)} min walk, to the {direction(me, nearest[0])}</span>
          </div>
          <div className="tiny faint" style={{ marginTop: 4 }}>
            Next closest: {nearest.slice(1).map((p) => `${Math.round(p.m)} m ${direction(me, p)}`).join(" · ")}
            {loc && loc.kind !== "gps" && <> · Measured from the location set at the top of the app.</>}
          </div>
        </div>
      )}

      <div ref={el} className="map tall" style={{ marginTop: 12 }} />

      <div className="tiny faint" style={{ marginTop: 8 }}>
        Positions traced from Yale's blue phone map (your.yale.edu, retrieved Oct 23, 2026): within a few meters on central campus
        and about 10 m at the athletic fields. In an emergency you can always call 911.
      </div>
    </div>
  );
}
