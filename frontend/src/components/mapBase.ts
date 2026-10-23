import L from "leaflet";
import { SERVICE_BOUNDS } from "../api";

export const AREA = L.latLngBounds([SERVICE_BOUNDS[0], SERVICE_BOUNDS[1]], [SERVICE_BOUNDS[2], SERVICE_BOUNDS[3]]);

/** True when the phone (or computer) is set to dark appearance. */
export function isDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

/** Colors for map lines and markers that must stay visible on the light or the dark basemap. */
export function mapColors() {
  return isDark()
    ? { ink: "#a9cbf3", walk: "#a6b0bd", stopFill: "#151c26", mask: "#0c1118", edge: "#7fb4f2", phone: "#4d8ef0", ring: "#7fb4f2" }
    : { ink: "#00356b", walk: "#545b63", stopFill: "#ffffff", mask: "#f2f1ed", edge: "#00356b", phone: "#1f5bd8", ring: "#1f5bd8" };
}

/** A Leaflet map with Beacon's basemap, locked to the service area: Yale's campuses (including West Campus) and the
 *  neighborhoods where students and staff live. Shared by the alert map, the blue-phone map, and the shuttle map. */
export function createBaseMap(el: HTMLElement, opts: L.MapOptions = {}): L.Map {
  const m = L.map(el, {
    zoomControl: true, attributionControl: true,
    maxBounds: AREA.pad(0.04), maxBoundsViscosity: 1.0, minZoom: 12, ...opts,
  }).setView([41.3083, -72.9279], 15);
  // Esri's Light Gray or Dark Gray Canvas basemap (no API key needed), matching the phone's appearance,
  // plus its street-name layer.
  const esri = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas";
  const tiles = (layer: "Base" | "Reference") => `${esri}/World_${isDark() ? "Dark" : "Light"}_Gray_${layer}/MapServer/tile/{z}/{y}/{x}`;
  const c = mapColors();
  const base = L.tileLayer(tiles("Base"), {
    maxZoom: 19, maxNativeZoom: 16, bounds: AREA.pad(0.3),
    attribution: "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
  }).addTo(m);
  const labels = L.tileLayer(tiles("Reference"), { maxZoom: 19, maxNativeZoom: 16, bounds: AREA.pad(0.3) }).addTo(m);
  // Dim everything outside the service area and outline its edge.
  const world: L.LatLngExpression[] = [[-85, -180], [-85, 180], [85, 180], [85, -180]];
  const hole: L.LatLngExpression[] = [AREA.getSouthWest(), AREA.getNorthWest(), AREA.getNorthEast(), AREA.getSouthEast()];
  const mask = L.polygon([world, hole], { stroke: false, fillColor: c.mask, fillOpacity: 0.7, interactive: false }).addTo(m);
  const edge = L.rectangle(AREA, { color: c.edge, weight: 1, opacity: 0.4, dashArray: "4 6", fill: false, interactive: false }).addTo(m);
  // Phones can switch to dark automatically at sunset: swap the basemap without a reload.
  const scheme = window.matchMedia?.("(prefers-color-scheme: dark)");
  const restyle = () => {
    base.setUrl(tiles("Base"));
    labels.setUrl(tiles("Reference"));
    mask.setStyle({ fillColor: mapColors().mask });
    edge.setStyle({ color: mapColors().edge });
  };
  scheme?.addEventListener?.("change", restyle);
  m.on("unload", () => scheme?.removeEventListener?.("change", restyle));
  window.setTimeout(() => {
    m.invalidateSize();
    m.setMinZoom(Math.max(11, m.getBoundsZoom(AREA, false)));  // zoom out to the whole area, no further
  }, 80);
  return m;
}

export function mePin(): L.DivIcon {
  return L.divIcon({ className: "", html: '<div class="me-pin"></div>', iconSize: [16, 16], iconAnchor: [8, 8] });
}
