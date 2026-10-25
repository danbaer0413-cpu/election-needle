"""
Read poll posts from a Bluesky account (default usapolling.bsky.social) through Bluesky's public read API
(no login) and turn them into poll rows for our races.

A post counts for a race only when it names BOTH of that race's candidates (config/candidates.csv) with a percent
next to each, e.g. "Talarico 48% Paxton 46%". The poll date is the post date (conservative: a poll is never
dated earlier than its field end date). Everything seen is saved to data/bsky_raw.json and every post that
looked like a poll but could not be matched is listed in data/bsky_unmatched.txt, so the parser can be tuned.
Not tested against the live account (the sandbox cannot reach Bluesky): check data/bsky_raw.json after run 1.
"""
from __future__ import annotations
import csv, json, os, re, sys, time
import requests

API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
PCT = re.compile(r"([A-Z][A-Za-z'’\-\.]+(?:\s[A-Z][A-Za-z'’\-]+)?)\s*[:\-–—(]?\s*(\d{1,2}(?:\.\d)?)\s*%")
SAMPLE = re.compile(r"(?:n\s*=\s*|N\s*=\s*|sample[:\s]+)([\d,]{3,6})|([\d,]{3,6})\s*(?:LV|RV|likely voters|registered voters|respondents)", re.I)


PSTER = re.compile(r"Emerson|Quinnipiac|Marist|Siena|New York Times|NYT|Fox News|CNN|SSRS|Monmouth|Marquette|UNH|Univ(?:ersity)? of New Hampshire|"
                   r"Morning Consult|Washington Post|Ipsos|YouGov|AARP|Beacon|Shaw|Selzer|Mason-Dixon|Susquehanna|Cygnal|Trafalgar|"
                   r"Data for Progress|co/efficient|Change Research|Public Policy Polling|PPP|Echelon|Redfield|AtlasIntel|"
                   r"Suffolk|Muhlenberg|Franklin & Marshall|Cook Political|Pew|Gallup|Mitchell|EPIC-MRA|Glengariff|Civiqs|"
                   r"UT Tyler|UT/Texas Politics|Texas Politics Project|UMass|Saint Anselm|St\. Anselm|Winthrop|Roanoke|Elon|High Point|Meredith|"
                   r"Emerson College|Bowling Green|Ohio Northern|Baldwin Wallace|Ohio State|Fabrizio|Impact Research|Noble Predictive|Remington|"
                   r"co/efficient|OnMessage|Tarrance|Hart Research|GQR|Global Strategy|Navigator|Harvard|Harris|Echelon Insights", re.I)


def load_candidates(path="config/candidates.csv"):
    with open(path) as f:
        return list(csv.DictReader(f))


def fetch_posts(actor="usapolling.bsky.social", pages=4):
    posts, cursor = [], None
    for _ in range(pages):
        p = {"actor": actor, "limit": 100, "filter": "posts_no_replies"}
        if cursor:
            p["cursor"] = cursor
        r = requests.get(API, params=p, timeout=30, headers={"User-Agent": "election-needle (personal, non-commercial)"})
        r.raise_for_status()
        j = r.json()
        for it in j.get("feed", []):
            po = it.get("post", {})
            rec = po.get("record", {})
            if it.get("reason"):                       # reposts are other people's posts; skip
                continue
            posts.append(dict(uri=po.get("uri"), created=rec.get("createdAt", "")[:10], text=rec.get("text", "")))
        cursor = j.get("cursor")
        if not cursor:
            break
        time.sleep(0.5)
    return posts


def _pct_for(text, surname):
    s = re.escape(surname)
    m = re.search(rf"{s}[^\d%\n]{{0,12}}?(\d{{1,2}}(?:\.\d)?)\s*%", text, re.I) or \
        re.search(rf"(\d{{1,2}}(?:\.\d)?)\s*%[^\d%\n]{{0,12}}?{s}", text, re.I)
    return float(m.group(1)) if m else None


MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DATE_LINE = re.compile(r"^(.*?)\s+/\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", re.I | re.M)
SKIP = re.compile(r"internal|generic ballot|approval|mayor|lt\.? gov|\d(?:st|nd|rd|th)\s+house|house polling|district|hypothetical", re.I)


def source_and_date(text, fallback):
    """'Poll Vault / Oct 22, 2026' or 'House Polling - PPP / Oct 22, 2026 - (Democratic Pollster)' -> (pollster, 'YYYY-MM-DD')."""
    m = DATE_LINE.search(text)
    if not m:
        return None, fallback
    name = re.split(r"\s[-–—]\s|:\s", m.group(1).strip())[-1].strip(" -–—")
    name = re.sub(r"\bPolling\b", "", name).strip()
    return (name or None), f"{int(m.group(4)):04d}-{MONTHS[m.group(2).lower()[:3]]:02d}-{int(m.group(3)):02d}"


def parse_post(post, cands):
    """-> list of dict(id,pollster,end,n,d,r,uri) for races this post reports.
    Seen in real posts: 'Nebraska - Senate Polling:\n⚪️ Osborn: 46%\n🔴 Ricketts: 45%*\n\nGBAO / Oct 22, 2026\n\n(Osborn Internal)'.
    Skips internals (sponsor's own poll), district-level House posts (their Senate/Governor lines are district samples),
    generic ballots, approval and hypotheticals. Pollster and field date come from the 'Pollster / Mon D, YYYY' line."""
    t = post["text"]
    if SKIP.search(t):
        return []
    pollster, end = source_and_date(t, post["created"])
    out = []
    for c in cands:
        if c["dem"].lower() not in t.lower() or c["rep"].lower() not in t.lower():
            continue
        abbr = c["id"].split("-")[0]
        if not (re.search(re.escape(c["state_names"]), t, re.I) or re.search(rf"\b{abbr}\b", t)):
            continue        # candidate surnames repeat across states (two Collinses, two Jacksons): require the state
        d, r = _pct_for(t, c["dem"]), _pct_for(t, c["rep"])
        if d is None or r is None or not (5 <= d <= 90 and 5 <= r <= 90) or d + r > 100:
            continue
        if c["id"] == "AK-governor" and d + r < 90:
            continue        # first-round numbers (several Republicans) are not a head-to-head: only final-round / two-way posts
        m = SAMPLE.search(t)
        n = float((m.group(1) or m.group(2)).replace(",", "")) if m else 600.0
        if not pollster:
            pm = PSTER.search(t)
            pollster = pm.group(0) if pm else None
        out.append(dict(id=c["id"], pollster=pollster or f"unknown-{post['uri']}", end=end, n=n, d=d, r=r, uri=post["uri"]))
    return out


def run(actor="usapolling.bsky.social", raw="data/bsky_raw.json", unmatched="data/bsky_unmatched.txt"):
    cands = load_candidates()
    posts = fetch_posts(actor)
    os.makedirs("data", exist_ok=True)
    json.dump(posts, open(raw, "w"))
    polls, miss = [], []
    for p in posts:
        got = parse_post(p, cands)
        polls += got
        if not got and re.search(r"\d\s*%", p["text"]) and re.search(r"senate|governor|poll", p["text"], re.I):
            miss.append(p["text"].replace("\n", " ")[:300])
    open(unmatched, "w").write("\n".join(miss))
    print(f"bluesky: {len(posts)} posts, {len(polls)} matched polls, {len(miss)} poll-like posts not matched")
    return polls


if __name__ == "__main__":
    try:
        run(*(sys.argv[1:2] or []))
    except Exception as ex:
        print("bsky_polls failed:", ex)
