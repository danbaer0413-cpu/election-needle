"""
Build the county outlines used by the map (run once on GitHub: Actions -> build-geo -> Run workflow).

    python build_geo.py [--src URL_OR_PATH] [--out data/geo]

Downloads a public US county GeoJSON (feature id = 5-digit FIPS), keeps the counties of our states, rounds the coordinates to
keep the file small, and writes data/geo/counties.json plus data/geo/county_fips.csv (state, fips, name, norm).
Alaska is skipped: our Alaska baseline uses election districts, not boroughs, so it appears on the state map only.
Prints any baseline county names that did not match an outline so they can be fixed.
"""
from __future__ import annotations
import argparse, glob, json, os
import pandas as pd

SRC = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
FIPS = {"FL": "12", "GA": "13", "IA": "19", "KS": "20", "ME": "23", "MI": "26", "MN": "27", "MS": "28", "NC": "37", "NE": "31",
        "NH": "33", "NV": "32", "OH": "39", "SC": "45", "TX": "48", "WI": "55"}


def _round(c, nd=3):
    return [_round(x, nd) for x in c] if isinstance(c, list) and c and isinstance(c[0], list) else [round(v, nd) for v in c]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--src", default=SRC); ap.add_argument("--out", default="data/geo")
    a = ap.parse_args()
    if a.src.startswith("http"):
        import requests
        r = requests.get(a.src, timeout=120); r.raise_for_status(); gj = r.json()
    else:
        gj = json.load(open(a.src))
    from model import norm_name
    inv = {v: k for k, v in FIPS.items()}
    feats, rows = [], []
    for f in gj["features"]:
        st = str(f["properties"].get("STATE") or str(f.get("id", ""))[:2]).zfill(2)
        if st not in inv:
            continue
        fid = str(f.get("id") or (st + str(f["properties"]["COUNTY"]).zfill(3))).zfill(5)
        name = f["properties"].get("NAME", "")
        g = f["geometry"]; g = {"type": g["type"], "coordinates": _round(g["coordinates"])}
        feats.append({"type": "Feature", "id": fid, "properties": {"name": name, "state": inv[st]}, "geometry": g})
        rows.append({"state": inv[st], "fips": fid, "name": name, "norm": norm_name(name)})
    os.makedirs(a.out, exist_ok=True)
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(a.out, "counties.json"), "w"), separators=(",", ":"))
    fx = pd.DataFrame(rows); fx.to_csv(os.path.join(a.out, "county_fips.csv"), index=False)
    print(f"{len(feats)} counties, {os.path.getsize(os.path.join(a.out, 'counties.json')) / 1e6:.1f} MB")
    # which of our baseline units have no outline
    miss = []
    for p in glob.glob("data/*/*/counties.csv"):
        st = p.split("/")[1]
        if st not in FIPS:
            continue
        have = set(fx[fx.state == st].norm)
        for c in pd.read_csv(p)["county"]:
            if norm_name(c) not in have:
                miss.append(f"{st}/{c}")
    miss = sorted(set(miss))
    print(f"baseline units without an outline: {len(miss)}", miss[:40] if miss else "")


if __name__ == "__main__":
    main()
