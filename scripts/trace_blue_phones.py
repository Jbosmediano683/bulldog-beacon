"""Trace Yale's blue emergency phones from Yale's own PDF map into backend/data_seed/blue_phones.json.

Yale publishes the phone locations only as a drawing (a PDF with ~500 blue dots and no coordinates):
https://your.yale.edu/campus-essentials/community-safety/campus-safety-support/blue-phone-locations-on-campus
This script turns the drawing into map coordinates so Beacon can show the phones on a real, interactive map.

1. Render the PDF at 3x and find every blue dot (connected blue pixels; touching dots are split by size).
2. Place the drawing on the map with a similarity transform (scale, rotation, offset) fitted to street
   intersections. Their pixel positions were read by hand from the 3x render; their coordinates are where the
   OpenStreetMap centerlines cross (from Nominatim). The fit is within 3.6 m at every control point.
3. The athletic-fields inset at the bottom of the PDF uses the same scale and rotation, offset to the
   Derby Ave & Yale Ave intersection (checked against the Yale Bowl: about 10 m).

Developer-only dependencies (not needed to run the app):
    python -m pip install pypdfium2 pillow numpy scipy httpx
    python scripts/trace_blue_phones.py
"""

import io
import json
import math
from pathlib import Path

import httpx
import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
PDF_URL = "https://your.yale.edu/media/3125/download?inline"
OUT = ROOT / "backend" / "data_seed" / "blue_phones.json"
SCALE = 3
INSET_TOP_PX = 8243   # the athletic-fields inset starts below this line in the 3x render

# (lat, lng) where OpenStreetMap centerlines cross  <->  (x, y) in the 3x render, read by hand
MAIN_CONTROL = [
    ((41.309481, -72.927059), (3020, 5025)),   # Elm St & College St
    ((41.310175, -72.928727), (2642, 5025)),   # Elm St & High St
    ((41.309804, -72.921006), (4010, 4367)),   # Grove St & Orange St
    ((41.303835, -72.927436), (3678, 6336)),   # Church St & George St
    ((41.308471, -72.931642), (2363, 5690)),   # Chapel St & York St
    ((41.301366, -72.935290), (2636, 7666)),   # Congress Ave & Howard Ave
    ((41.325581, -72.922839), (1685, 950)),    # Canner St & Prospect St
]
INSET_ANCHOR = ((41.310409, -72.957893), (2708, 9215))   # Derby Ave & Yale Ave

LAT0, LON0 = 41.31, -72.93
KX, KY = math.cos(math.radians(LAT0)) * 111320.0, 110540.0


def to_z(lat: float, lng: float) -> complex:
    """Local meters as a complex number, y flipped to match image rows."""
    return complex((lng - LON0) * KX, -(lat - LAT0) * KY)


def from_z(z: complex) -> tuple[float, float]:
    return LAT0 - z.imag / KY, LON0 + z.real / KX


def detect_dots(img: np.ndarray) -> list[tuple[float, float]]:
    r, g, b = (img[..., i].astype(np.int16) for i in range(3))
    mask = (b > 200) & (r < 90) & (g > 30) & (g < 120)        # the map's dot blue, (3, 65, 255)
    lab, n = ndimage.label(mask)
    areas = ndimage.sum(mask, lab, np.arange(1, n + 1))
    single = float(np.median(areas[areas > 300]))             # one dot is about 790 px at 3x
    dots = []
    for k, sl in enumerate(ndimage.find_objects(lab)):
        if areas[k] < 0.45 * single:
            continue
        ys, xs = np.nonzero(lab[sl] == k + 1)
        pts = np.stack([xs + sl[1].start, ys + sl[0].start], 1).astype(float)
        m = max(1, int(round(areas[k] / single)))
        if m == 1:
            dots.append(tuple(pts.mean(0)))
            continue
        cent = pts[np.random.default_rng(0).choice(len(pts), m, replace=False)]   # split touching dots
        for _ in range(30):
            assign = ((pts[:, None, :] - cent[None]) ** 2).sum(-1).argmin(1)
            cent = np.array([pts[assign == j].mean(0) if (assign == j).any() else cent[j] for j in range(m)])
        dots += [tuple(c) for c in cent]
    return dots


def main() -> None:
    pdf_bytes = httpx.get(PDF_URL, timeout=60, follow_redirects=True).content
    page = pdfium.PdfDocument(io.BytesIO(pdf_bytes))[0]
    img = np.asarray(page.render(scale=SCALE).to_pil().convert("RGB"))
    dots = detect_dots(img)

    Z = np.array([to_z(*ll) for ll, _ in MAIN_CONTROL])
    P = np.array([complex(*px) for _, px in MAIN_CONTROL])
    (a, b), *_ = np.linalg.lstsq(np.stack([Z, np.ones_like(Z)], 1), P, rcond=None)
    worst = max(abs(p - (a * z + b)) for z, p in zip(Z, P)) / abs(a)
    b_inset = complex(*INSET_ANCHOR[1]) - a * to_z(*INSET_ANCHOR[0])

    phones = []
    for x, y in dots:
        inset = y >= INSET_TOP_PX
        lat, lng = from_z((complex(x, y) - (b_inset if inset else b)) / a)
        phones.append((round(lat, 6), round(lng, 6), "athletics" if inset else "main"))
    phones.sort(key=lambda p: (-p[0], p[1]))
    OUT.write_text(json.dumps({
        "source": "Yale's campus blue phone map (PDF), your.yale.edu/media/3125, linked from "
                  "https://your.yale.edu/campus-essentials/community-safety/campus-safety-support/blue-phone-locations-on-campus",
        "retrieved": "2026-10-23",
        "method": "Each blue dot was detected in the PDF and placed on the map with a similarity transform fitted to 7 street "
                  f"intersections (OpenStreetMap). Fit error: {worst:.1f} m or less on the main campus map; about 10 m on the "
                  "athletic-fields inset.",
        "count": len(phones),
        "phones": [{"id": i + 1, "lat": lat, "lng": lng, "area": area} for i, (lat, lng, area) in enumerate(phones)],
    }, separators=(",", ":")), encoding="utf-8")
    print(f"{len(phones)} phones -> {OUT.relative_to(ROOT)} (worst control-point error {worst:.1f} m)")


if __name__ == "__main__":
    main()
