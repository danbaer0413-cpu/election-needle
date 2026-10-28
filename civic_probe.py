"""Finds out whether civicAPI's early-vote pages have a data endpoint we can read.
Run once from GitHub Actions (civic-probe workflow). Writes data/civic_probe.json and prints a summary.
Steps: 1) read the page HTML + its script files and list any /api/ or fetch( URLs, 2) try likely endpoints for a few states."""
import json, re, sys, requests

BASE = "https://civicapi.org"
H = {"User-Agent": "election-needle-probe/1.0 (personal project; attribution: civicapi.org)"}
out = {"pages": {}, "found": [], "tries": []}


def get(u):
    try:
        r = requests.get(u, headers=H, timeout=25)
        return r.status_code, r.headers.get("content-type", ""), r.text
    except Exception as ex:
        return 0, "", str(ex)[:200]


pat = re.compile(r"""["'`]((?:https?://civicapi\.org)?/(?:api|v2)[^"'`\s<>)]{2,120})["'`]""")
for page in ("/early-vote", "/early-vote/me", "/early-vote/ne", "/early-vote/wi"):
    code, ct, html = get(BASE + page)
    info = {"status": code, "bytes": len(html)}
    urls = set(pat.findall(html))
    for s in set(re.findall(r'src=["\']([^"\']+\.js[^"\']*)', html)):
        su = s if s.startswith("http") else BASE + (s if s.startswith("/") else "/" + s)
        c2, _, js = get(su)
        if c2 == 200:
            urls |= set(pat.findall(js))
            urls |= {m for m in re.findall(r"""["'`](/[A-Za-z0-9_\-/\.]*early[A-Za-z0-9_\-/\.\?=\$\{\}]*)["'`]""", js)}
    info["urls"] = sorted(urls)[:60]
    out["pages"][page] = info
    print(page, code, len(html), "candidate urls:", len(urls))
    for u in sorted(urls)[:25]:
        print("   ", u)

cands = []
for st in ("me", "ne", "wi"):
    for p in (f"/api/v2/early-vote/{st}", f"/api/v2/early-vote?state={st}", f"/api/v2/earlyvote/{st}", f"/api/early-vote/{st}",
              f"/api/early-vote?state={st}", f"/api/v2/early/{st}", f"/api/v2/early-vote/{st}/counties"):
        cands.append(p)
cands += ["/api/v2/early-vote", "/api/early-vote", "/api/v2/status"]
for u in out["pages"].values():
    for x in u["urls"]:
        if "early" in x.lower() and x not in cands:
            cands.append(x)
for p in cands:
    u = p if p.startswith("http") else BASE + p
    code, ct, body = get(u)
    ok = code == 200 and "json" in ct.lower()
    out["tries"].append({"url": u, "status": code, "json": ok, "head": body[:300] if ok else ""})
    print(("OK  " if ok else "no  ") + str(code), u)
    if ok:
        out["found"].append(u)
json.dump(out, open("data/civic_probe.json", "w"), indent=1)
print("JSON endpoints found:", out["found"] or "none")
