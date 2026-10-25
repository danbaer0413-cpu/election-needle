"""
Read VoteHub's early-vote posts from Bluesky and turn them into rows.

    python votehub.py                 # fetch recent posts from @votehub.com, write data/votehub_latest.csv
    python votehub.py --text post.txt # parse one post saved as text (for testing)

Uses Bluesky's public read API (no login). Each post is parsed with plain patterns; a post that does
not match is written to data/votehub_unparsed.txt instead of being guessed at. Their modeled vote
ranges and ratings are stored for display only; nothing here feeds the model's numbers.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re

FIELDS = ["state", "as_of", "kind", "total", "delta", "pct_of_final", "implied_final", "candidates", "rating", "day"]
STATES = ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida",
          "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
          "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska",
          "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
          "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee",
          "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming"]
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _num(s):
    return int(s.replace(",", ""))


def parse_post(text: str) -> dict | None:
    """One row, or None if the post is not an early-vote total post."""
    t = text.replace("–", "-").replace("—", "-")
    m_total = re.search(r"Total\s+(early\s+|mail\s+)?votes:\s*([\d,]+)\s*(?:\(\s*([+-][\d,]+)\s*\))?", t, re.I)
    m_asof = re.search(r"As of\s+([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2}),\s*(\d{4})", t)
    if not (m_total and m_asof):
        return None
    state = next((s for s in sorted(STATES, key=len, reverse=True) if re.search(rf"\b{s}\b", t)), "")
    kind = (m_total.group(1) or "").strip().lower() or "total"
    total = _num(m_total.group(2))
    pct = re.search(r"([\d.]+)%\s+of projected final turnout", t, re.I)
    pct = float(pct.group(1)) if pct else None
    day = re.search(r"Day\s+(\d+)", t)
    rating = re.search(r"rate[s]?\s+(?:this\s+)?(?:the\s+)?race\s+as\s+([A-Za-z ]+?)\.", t)
    cands = re.findall(r"([A-Z][A-Za-z.' -]+?):\s*([\d.]+)%?\s*-\s*([\d.]+)%", t)
    mo = MONTHS.get(m_asof.group(1)[:3])
    as_of = dt.date(int(m_asof.group(3)), mo, int(m_asof.group(2))).isoformat() if mo else ""
    return {"state": state, "as_of": as_of, "kind": kind, "total": total,
            "delta": _num(m_total.group(3)) if m_total.group(3) else "",
            "pct_of_final": pct, "implied_final": round(total / (pct / 100)) if pct else "",
            "candidates": "; ".join(f"{n.strip()} {a}-{b}" for n, a, b in cands),
            "rating": rating.group(1).strip() if rating else "", "day": day.group(1) if day else ""}


API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"


def _record(i) -> dict:
    p = i["post"]; emb = p.get("embed") or {}
    imgs = emb.get("images") or (emb.get("media") or {}).get("images") or []
    return {"uri": p.get("uri", ""), "created": p["record"].get("createdAt", ""), "text": p["record"].get("text", ""),
            "alt": " | ".join(x.get("alt", "") for x in imgs if x.get("alt")),
            "link": ((emb.get("external") or {}).get("title", ""))}


def fetch_records(actor="votehub.com", pages=1, limit=100, timeout=30) -> list[dict]:
    """Posts with date, image alt text (results are often posted as pictures) and link title. pages > 1 walks back in time."""
    import requests
    out, cursor = [], None
    for _ in range(pages):
        params = {"actor": actor, "limit": limit, "filter": "posts_no_replies"}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(API, params=params, timeout=timeout)
        r.raise_for_status()
        j = r.json()
        out += [_record(i) for i in j.get("feed", [])]
        cursor = j.get("cursor")
        if not cursor:
            break
    return out


def fetch_posts(actor="votehub.com", limit=100, timeout=30) -> list[str]:
    return [r["text"] for r in fetch_records(actor, 1, limit, timeout)]


def archive(records, path="data/votehub_raw.jsonl", keep=3000):
    """Append every new post (any topic) so election-night posts are kept even if the parser does not understand them yet."""
    import json
    seen, rows = set(), []
    if os.path.exists(path):
        for line in open(path):
            try:
                r = json.loads(line); rows.append(r); seen.add(r["uri"])
            except Exception:
                pass
    new = [r for r in records if r["uri"] and r["uri"] not in seen]
    rows = (rows + new)[-keep:]
    with open(path, "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""))
    return len(new)


def run(out="data/votehub_latest.csv", unparsed="data/votehub_unparsed.txt", texts=None):
    if texts is None:
        recs = fetch_records()
        try:
            archive(recs)
        except Exception as ex:
            print("could not archive posts:", ex)
        texts = [r["text"] + (("\n" + r["alt"]) if r["alt"] and r["alt"] not in r["text"] else "") for r in recs]
    rows, bad = [], []
    for t in texts:
        r = parse_post(t)
        if r:
            rows.append(r)
        elif re.search(r"early|mail", t, re.I):
            bad.append(t)
    # keep the newest post per state and vote kind
    best = {}
    for r in sorted(rows, key=lambda r: r["as_of"]):
        best[(r["state"], r["kind"])] = r
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(best.values())
    # running history (one row per state, kind and date) so later days can be added up
    hist_path = out.replace("latest", "history")
    try:
        import pandas as pd
        old = pd.read_csv(hist_path) if os.path.exists(hist_path) else pd.DataFrame(columns=FIELDS)
        new = pd.concat([old, pd.DataFrame(rows, columns=FIELDS)], ignore_index=True)
        new.drop_duplicates(["state", "kind", "as_of"], keep="last").sort_values(["state", "kind", "as_of"]).to_csv(hist_path, index=False)
    except Exception as ex:  # history is a convenience; never break the run
        print("could not update history:", ex)
    with open(unparsed, "w") as f:
        f.write("\n\n-----\n\n".join(bad))
    return list(best.values()), bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    a = ap.parse_args()
    rows, bad = run(texts=[open(a.text).read()] if a.text else None)
    for r in rows:
        print(r)
    print(f"{len(rows)} parsed, {len(bad)} early/mail posts not understood")
