import { SERVICE_BOUNDS } from "./api";

export type Fix = { lat: number; lng: number; accuracy: number };
export type Located =
  | { kind: "gps"; fix: Fix }                       // the phone's location, inside Beacon's area
  | { kind: "outside"; fix: Fix }                   // a real location, but not in New Haven (e.g. a grader's laptop)
  | { kind: "unavailable"; reason: string };        // no permission, no GPS, or it timed out

export function inServiceArea(lat: number, lng: number): boolean {
  return lat >= SERVICE_BOUNDS[0] && lat <= SERVICE_BOUNDS[2] && lng >= SERVICE_BOUNDS[1] && lng <= SERVICE_BOUNDS[3];
}

/** Ask the browser for the current location once. Never throws. */
export function locate(timeoutMs = 9000): Promise<Located> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve({ kind: "unavailable", reason: "This browser can't share its location." });
    navigator.geolocation.getCurrentPosition(
      (p) => {
        const fix = { lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy };
        resolve(inServiceArea(fix.lat, fix.lng) ? { kind: "gps", fix } : { kind: "outside", fix });
      },
      (e) => resolve({ kind: "unavailable", reason: e.code === e.PERMISSION_DENIED ? "Location permission is off." : "Your location isn't available right now." }),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 30000 },
    );
  });
}

export function walkMinutes(meters: number): number {
  return Math.max(1, Math.round((meters * 1.3) / 80));
}
