"""
Find the machine-readable feeds behind the state results portals (run on GitHub: Actions -> probe-portals -> Run workflow).

    python probe_portals.py [--portals config/results_portals.csv] [--out data/portal_probe.txt]

For each portal URL it reports the HTTP status, content type, and every data-looking link it can find in the page and in the
JavaScript files the page loads (.json .csv .xml .xlsx .zip, '/api/', 'download', and known results platforms). A single-page app
that builds its tables in the browser will show few or no links; for those use the browser Network tab method in ELECTION_NIGHT.md.
Nothing here changes any setting. Send me data/portal_probe.txt and I will fill in config/feeds.csv.
"""
from __future__ import annotations
import argparse, csv, re, sys
from urllib.parse import urljoin, urlparse
import requests

UA = {"User-Agent": "Mozilla/5.0 (election-needle portal probe)"}
DATA = re.compile(r"""["'(]((?:https?:)?//[^"'()\s<>]+|/[^"'()\s<>]+)["')]""")
KEEP = re.compile(r"\.(json|csv|xml|xlsx|zip)(\?|$)|/api/|download|export|clarity|scytl|enhancedvoting|electionstats|results?/|detail\.|summary\.|county|reportingunit|ElectionEvent", re.I)
SKIP = re.compile(r"\.(png|jpe?g|gif|svg|woff2?|ttf|ico|css)(\?|$)|google|facebook|twitter|gstatic|cloudflare|jquery|bootstrap|fonts\.", re.I)


BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}


def get(url, timeout=25, cap=3_000_000):
    """Try the plain request; retry with browser-like headers on 403/202, and without certificate checks on a certificate
    error (read-only probe of public pages; the report says when this was needed)."""
    try:
        r = requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
        if r.status_code in (403, 202, 406):
            r2 = requests.get(url, headers=BROWSER, timeout=timeout, allow_redirects=True)
            if r2.status_code < 400 and r2.status_code != 202:
                r = r2
    except requests.exceptions.SSLError:
        requests.packages.urllib3.disable_warnings()
        r = requests.get(url, headers=BROWSER, timeout=timeout, allow_redirects=True, verify=False)
    return r.status_code, r.headers.get("content-type", ""), r.url, r.text[:cap] if "text" in r.headers.get("content-type", "") or "json" in r.headers.get("content-type", "") or "javascript" in r.headers.get("content-type", "") else ""


def find_links(base, text):
    out = []
    for m in DATA.finditer(text):
        u = urljoin(base, m.group(1))
        if KEEP.search(u) and not SKIP.search(u) and u not in out:
            out.append(u)
    return out


def probe(url, js_limit=8):
    lines = []
    try:
        code, ctype, final, html = get(url)
    except Exception as ex:
        return [f"  FAILED: {type(ex).__name__}: {str(ex)[:150]}"]
    lines.append(f"  status {code} | {ctype.split(';')[0]} | final url {final} | {len(html):,} chars")
    if code >= 400 or not html:
        return lines
    scripts = re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, re.I)
    text_len = len(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", html)).split())
    lines.append(f"  visible words {text_len} | external scripts {len(scripts)}"
                 + ("  -> looks like a single-page app (data loads in the browser)" if text_len < 150 and scripts else ""))
    links = find_links(final, html)
    same = [urljoin(final, s) for s in scripts if urlparse(urljoin(final, s)).netloc == urlparse(final).netloc and not SKIP.search(s)]
    for js in same[:js_limit]:
        try:
            c2, t2, f2, body = get(js, cap=4_000_000)
            if c2 < 400:
                links += [u for u in find_links(f2, body) if u not in links]
        except Exception:
            pass
    if links:
        lines.append(f"  {len(links)} data-looking links (first 80):")
        lines += [f"    {u}" for u in links[:80]]
    else:
        lines.append("  no data-looking links found in the page or its scripts")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portals", default="config/results_portals.csv")
    ap.add_argument("--out", default="data/portal_probe.txt")
    a = ap.parse_args()
    seen, report = set(), []
    for row in csv.DictReader(open(a.portals)):
        for kind in ("senate_url", "governor_url"):
            u = (row.get(kind) or "").strip()
            if not u or u in seen:
                continue
            seen.add(u)
            report.append(f"{row['state']} {kind.split('_')[0]}: {u}")
            report += probe(u)
    txt = "\n".join(report) + "\n"
    open(a.out, "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
