"""Automated race calls, written ONLY when two independent sources agree.

Sources
  civicapi : a race's candidate carries winner=true and the race is not flagged test_data (civicapi.org, credit them).
  bluesky  : a post by a trusted account (config/call_accounts.json) saying a named candidate wins / is projected to win.
Rules
  * A call needs `min_sources` (default 2) different sources naming the SAME winner; any disagreement = no call, logged as a conflict.
  * One source alone is "pending" (data/calls_pending.csv) and changes nothing on screen.
  * Posts before `not_before`, reposts, quotes, questions and conditionals ("if", "would", "could") are ignored.
  * Rewritten from scratch every run, so a call a source later retracts disappears. Typed calls (data/senate_called.csv,
    data/house/called.csv) always win over automated ones.
Output: data/auto_calls.csv (kind,race,winner,sources) and appends data/auto_calls_log.csv.
Not tested against the live sources (the sandbox cannot reach them): check data/auto_calls_log.csv after the first election-night run."""
from __future__ import annotations
import csv, datetime as dt, json, os, re, time
import requests

CFG = "config/call_accounts.json"
CIVIC = "https://civicapi.org/api/v2"
BSKY = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
UA = {"User-Agent": "election-needle (personal, non-commercial; attribution civicapi.org)"}
WIN = r"(?:wins?|won|projected to win|projected winner|is projected|has been projected|elected|re-?elected|declared (?:the )?winner|victory|defeats?|defeated|holds?|flips?)"
BAD = re.compile(r"\?|\bif\b|\bwould\b|\bcould\b|\bmay\b|\bmight\b|\bneeds? to\b|\bprimary\b|\brunoff\b|\bpoll\b|\bpolls\b|\bforecast\b|\bchance\b|\bodds\b", re.I)


def load_cfg() -> dict:
    d = {"accounts": [], "min_sources": 2, "not_before": "2026-11-03T21:00:00Z", "civic": True, "max_age_hours": 96}
    if os.path.exists(CFG):
        d.update(json.load(open(CFG)))
    return d


def _get(url, params=None):
    try:
        r = requests.get(url, params=params, headers=UA, timeout=40)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def senate_races(path="config/candidates.csv") -> dict:
    out = {}
    for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
        if r["id"].endswith("-senate"):
            out[r["id"]] = {"D": r["dem"].strip(), "R": r["rep"].strip(), "state": r["id"].split("-")[0]}
    return out


def house_seats(path="data/house/ratings_2026.csv") -> set:
    return {(r["state"].strip().upper(), str(int(r["district"]))) for r in csv.DictReader(open(path, newline="")) if str(r.get("district", "")).strip().isdigit()}


# ---------------------------------------------------------------- civicAPI
def civic_calls(senate: dict, house: set, get=_get) -> dict:
    """{('senate', race_id) | ('house', 'ST-N'): 'D'|'R'}"""
    out, states = {}, sorted({v["state"] for v in senate.values()} | {s for s, _ in house})
    for st in states:
        off = 0
        while off < 600:
            js = get(f"{CIVIC}/race/search", {"country": "US", "province": st, "date": "2026-11-03", "offset": off})
            races = (js or {}).get("races") or []
            if not races:
                break
            for r in races:
                name = str(r.get("election_name") or "")
                if "Primary" in name or "State" in name:
                    continue
                key = None
                if "Senate" in name:
                    key = ("senate", f"{st}-senate")
                else:
                    m = re.search(r"(?:U\.?S\.?|United States)\s+House.*?(?:District\s+)?(\d+)\b|Congressional District\s+(\d+)", name)
                    if m:
                        n = str(int(m.group(1) or m.group(2)))
                        if (st, n) in house:
                            key = ("house", f"{st}-{n}")
                if not key or (key[0] == "senate" and key[1] not in senate):
                    continue
                d = get(f"{CIVIC}/race/{r['id']}", {"data": "json"}) or {}
                if d.get("test_data"):
                    continue
                for c in d.get("candidates") or []:
                    if c.get("winner"):
                        p = str(c.get("party") or "")
                        side = "D" if p.startswith("Democ") else "R" if p.startswith("Republ") else None
                        if key[0] == "senate" and not side:          # independents (e.g. Nebraska): match by surname
                            nm = str(c.get("name") or "")
                            side = "D" if senate[key[1]]["D"].lower() in nm.lower() else "R" if senate[key[1]]["R"].lower() in nm.lower() else None
                        if side:
                            out[key] = side
            off += 20
    return out


# ---------------------------------------------------------------- Bluesky
def feed(handle: str, limit: int = 60, get=_get) -> list:
    js = get(BSKY, {"actor": handle, "limit": limit, "filter": "posts_no_replies"}) or {}
    posts = []
    for it in js.get("feed", []):
        if it.get("reason"):                                  # repost
            continue
        po = it.get("post", {})
        rec = po.get("record", {})
        emb = (rec.get("embed") or {}).get("$type", "")
        if "record" in emb and "media" not in emb and "external" not in emb and "images" not in emb:     # pure quote
            continue
        posts.append({"uri": po.get("uri"), "created": rec.get("createdAt", ""), "text": rec.get("text", "")})
    return posts


def _after(created: str, not_before: str, max_age_h: float, now=None) -> bool:
    try:
        t = dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
        nb = dt.datetime.fromisoformat(not_before.replace("Z", "+00:00"))
        now = now or dt.datetime.now(dt.timezone.utc)
        return t >= nb and (now - t).total_seconds() <= max_age_h * 3600
    except Exception:
        return False


def parse_post(text: str, senate: dict, house: set) -> list:
    """[(key, 'D'|'R')] named by one post. Strict: one winner, a win verb right next to the name, no hedging words."""
    if BAD.search(text):
        return []
    out = []
    low = text
    for rid, c in senate.items():
        if "senate" not in low.lower():
            continue
        wins = []
        for side in ("D", "R"):
            nm = re.escape(c[side])
            if re.search(rf"\b{nm}\b[^.\n]{{0,40}}?\b{WIN}\b", low, re.I) or re.search(rf"\b(?:projects?|calls?|declares?)\b[^.\n]{{0,40}}?\b{nm}\b", low, re.I):
                wins.append(side)
        if len(wins) == 1:
            out.append((("senate", rid), wins[0]))
    for st, n in house:
        for m in re.finditer(rf"\b{st}[-\s]0?{n}\b", text):
            seg = text[max(0, m.start() - 80): m.end() + 120]
            sides = set()
            if re.search(rf"\b(?:Democrat\w*|\(D\))\b[^.\n]{{0,40}}?\b{WIN}\b|\b{WIN}\b[^.\n]{{0,25}}?\b(?:Democrat\w*|\(D\))", seg, re.I):
                sides.add("D")
            if re.search(rf"\b(?:Republican\w*|\(R\))\b[^.\n]{{0,40}}?\b{WIN}\b|\b{WIN}\b[^.\n]{{0,25}}?\b(?:Republican\w*|\(R\))", seg, re.I):
                sides.add("R")
            if len(sides) == 1:
                out.append((("house", f"{st}-{n}"), sides.pop()))
    return out


def bluesky_calls(cfg: dict, senate: dict, house: set, fetch=feed, now=None) -> dict:
    """{key: {handle: side}} - one vote per account."""
    votes = {}
    for h in cfg.get("accounts", []):
        for p in fetch(h):
            if not _after(p["created"], cfg["not_before"], cfg["max_age_hours"], now):
                continue
            for key, side in parse_post(p["text"], senate, house):
                votes.setdefault(key, {}).setdefault(h, set()).add(side)
        time.sleep(0.3)
    out = {}
    for key, per in votes.items():
        out[key] = {h: (next(iter(s)) if len(s) == 1 else "?") for h, s in per.items()}      # an account that says both = conflict
    return out


# ---------------------------------------------------------------- combine
def combine(civic: dict, bsky: dict, min_sources: int = 2):
    """-> (calls {key: side}, sources {key: [names]}, pending {key: (side, [names])}, conflicts [key])"""
    calls, srcs, pending, conflicts = {}, {}, {}, []
    keys = set(civic) | set(bsky)
    for key in keys:
        votes = {}
        if key in civic:
            votes["civicapi"] = civic[key]
        for h, side in (bsky.get(key) or {}).items():
            votes[f"bluesky:{h}"] = side
        sides = set(votes.values())
        if len(sides) != 1 or "?" in sides:
            conflicts.append(key)
            continue
        side = sides.pop()
        # independent sources: civicapi counts as one, all Bluesky accounts together count as one only if they are different accounts
        n = (1 if "civicapi" in votes else 0) + len([v for v in votes if v.startswith("bluesky")])
        if n >= min_sources:
            calls[key], srcs[key] = side, sorted(votes)
        else:
            pending[key] = (side, sorted(votes))
    return calls, srcs, pending, conflicts


def main(civic_fn=civic_calls, bsky_fn=bluesky_calls, now=None):
    cfg = load_cfg()
    senate, house = senate_races(), house_seats()
    civic = civic_fn(senate, house) if cfg.get("civic", True) else {}
    bsky = bsky_fn(cfg, senate, house, now=now) if cfg.get("accounts") else {}
    calls, srcs, pending, conflicts = combine(civic, bsky, int(cfg.get("min_sources", 2)))
    os.makedirs("data", exist_ok=True)
    with open("data/auto_calls.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["kind", "race", "winner", "sources"])
        for (k, r), side in sorted(calls.items()):
            w.writerow([k, r, side, "+".join(srcs[(k, r)])])
    with open("data/calls_pending.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["kind", "race", "winner", "sources"])
        for (k, r), (side, s) in sorted(pending.items()):
            w.writerow([k, r, side, "+".join(s)])
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    new = not os.path.exists("data/auto_calls_log.csv")
    with open("data/auto_calls_log.csv", "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["time", "event", "kind", "race", "winner", "sources"])
        for (k, r), side in sorted(calls.items()):
            w.writerow([stamp, "call", k, r, side, "+".join(srcs[(k, r)])])
        for (k, r), (side, s) in sorted(pending.items()):
            w.writerow([stamp, "pending", k, r, side, "+".join(s)])
        for k, r in sorted(conflicts):
            w.writerow([stamp, "CONFLICT", k, r, "", ""])
    print(f"auto calls: {len(calls)} called, {len(pending)} pending (one source), {len(conflicts)} conflicts")
    for (k, r), side in sorted(calls.items()):
        print(f"  CALL {k} {r}: {side} ({'+'.join(srcs[(k, r)])})")
    return calls


if __name__ == "__main__":
    main()
