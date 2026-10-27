"""Build the Alaska election-district outlines for the map (run once on GitHub: Actions -> build-ak-geo -> Run workflow).

    python build_ak_geo.py [--src URL_OR_ZIP] [--out data/geo]

Downloads the Census cartographic-boundary file for Alaska state House districts (the districts our Alaska baseline uses),
turns it into GeoJSON with ids like "District 01", simplifies it, shifts the Aleutian islands that sit east of the 180th meridian
so Alaska is one continuous piece, and writes data/geo/ak_districts.json. Prints the districts it found and any of our baseline
districts that have no outline.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import zipfile

SRC = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_02_sldl_500k.zip"


def dp(points, tol):
    """Douglas-Peucker simplification of a list of [x, y] (iterative, keeps the first and last point)."""
    if len(points) < 5:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = points[a], points[b]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
        far, idx = -1.0, None
        for i in range(a + 1, b):
            px, py = points[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / norm
            if d > far:
                far, idx = d, i
        if idx is not None and far > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(points, keep) if k]


def shift(lon: float) -> float:
    """Aleutians east of the antimeridian show up as +172..+180; make them -188..-180 so the state is one piece."""
    return lon - 360.0 if lon > 0 else lon


def dp_ring(pts, tol):
    """Simplify a CLOSED ring (first point == last point): split it at the point farthest from the start so each half is a real line."""
    if len(pts) < 8:
        return pts
    x0, y0 = pts[0]
    k = max(range(1, len(pts) - 1), key=lambda i: (pts[i][0] - x0) ** 2 + (pts[i][1] - y0) ** 2)
    return dp(pts[:k + 1], tol)[:-1] + dp(pts[k:], tol)


def ring(r, tol):
    pts = [[shift(x), y] for x, y in r]
    pts = dp_ring(pts, tol) if pts and pts[0] == pts[-1] else dp(pts, tol)
    if len(pts) < 4:
        return None
    return [[round(x, 3), round(y, 3)] for x, y in pts]


def rings_to_geometry(shape_parts, points, tol):
    """Split a shapefile record into polygon rings. Outer rings are clockwise in shapefiles; holes are counter-clockwise."""
    rings = []
    bounds = list(shape_parts) + [len(points)]
    for i in range(len(shape_parts)):
        seg = points[bounds[i]:bounds[i + 1]]
        s = ring(seg, tol)
        if s:
            area = sum((s[j][0] * s[(j + 1) % len(s)][1] - s[(j + 1) % len(s)][0] * s[j][1]) for j in range(len(s)))
            rings.append((area, s))
    outers = [r for a, r in rings if a <= 0]          # clockwise (negative signed area) = outer
    holes = [r for a, r in rings if a > 0]
    if not outers:
        outers, holes = [r for a, r in rings], []
    polys = [[o] for o in outers]
    for h in holes:                                   # attach each hole to the outer ring whose box holds it
        hx, hy = h[0]
        for p in polys:
            xs = [q[0] for q in p[0]]; ys = [q[1] for q in p[0]]
            if min(xs) <= hx <= max(xs) and min(ys) <= hy <= max(ys):
                p.append(h)
                break
    return {"type": "MultiPolygon", "coordinates": polys}


def district_label(rec: dict) -> str | None:
    for k in ("SLDLST", "NAME", "NAMELSAD", "GEOID"):
        v = str(rec.get(k, ""))
        m = re.search(r"(\d+)\s*$", v) if k != "NAME" and k != "NAMELSAD" else re.search(r"(\d+)", v)
        if m and "ZZ" not in v.upper():
            return f"District {int(m.group(1)):02d}"
    return None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--src", default=SRC); ap.add_argument("--out", default="data/geo")
    ap.add_argument("--tol", type=float, default=0.004)
    a = ap.parse_args()
    import shapefile                                   # pyshp
    if a.src.startswith("http"):
        import requests
        r = requests.get(a.src, timeout=180); r.raise_for_status(); raw = r.content
    else:
        raw = open(a.src, "rb").read()
    zf = zipfile.ZipFile(io.BytesIO(raw))
    base = next(n[:-4] for n in zf.namelist() if n.endswith(".shp"))
    rd = shapefile.Reader(shp=io.BytesIO(zf.read(base + ".shp")), dbf=io.BytesIO(zf.read(base + ".dbf")))
    fields = [f[0] for f in rd.fields[1:]]
    print("fields:", fields)
    feats = []
    for sr in rd.shapeRecords():
        rec = dict(zip(fields, sr.record))
        lab = district_label(rec)
        if not lab:
            print("skipped (no district number):", rec)
            continue
        geom = rings_to_geometry(sr.shape.parts, sr.shape.points, a.tol)
        feats.append({"type": "Feature", "id": lab, "properties": {"name": lab}, "geometry": geom})
    feats.sort(key=lambda f: f["id"])
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "ak_districts.json")
    with open(path, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh, separators=(",", ":"))
    print(f"wrote {path}: {len(feats)} districts, {os.path.getsize(path) / 1024:.0f} KB")
    try:
        import pandas as pd
        ours = set(pd.read_csv("data/AK/u-s-senate/counties.csv")["county"])
        have = {f["id"] for f in feats}
        print("our districts with no outline:", sorted(ours - have) or "none")
        print("outlines we do not use:", sorted(have - ours) or "none")
    except Exception as ex:
        print("could not compare with our baseline:", ex)


if __name__ == "__main__":
    main()
