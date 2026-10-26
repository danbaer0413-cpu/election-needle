"""Read-only: do the state's downloadable result FILES exist, and what do they look like?  Saves data/portal_files.txt.
Past-election files are shown so we can see the layout before election night. Never touches anything behind a bot check."""
import io, re, zipfile
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
URLS = [
    ("NC 2024 precinct results zip", "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2024_11_05/results_pct_20241105.zip"),
    ("NC 2026 folder (general)", "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2026_11_03/results_pct_20261103.zip"),
    ("NC file index", "https://dl.ncsbe.gov/?prefix=ENRS/2026_11_03/"),
    ("FL 2024 election-night file", "https://flelectionfiles.floridados.gov/enightfilespublic/20241105_ElecResultsFL.txt"),
    ("FL 2026 election-night file", "https://flelectionfiles.floridados.gov/enightfilespublic/20261103_ElecResultsFL.txt"),
    ("MN media results page", "https://electionresults.sos.mn.gov/Results/MediaSupport"),
    ("MI results data page", "https://www.michigan.gov/sos/elections/election-results-and-data"),
    ("MI election results site", "https://mielections.us/election/results/"),
    ("KS results page", "https://sos.ks.gov/elections/election-results.html"),
    ("NH results page", "https://www.sos.nh.gov/2026-general-election-results"),
    ("ME results data page", "https://www.maine.gov/sos/elections-voting/election-results-data"),
    ("MS results page", "https://www.sos.ms.gov/elections-voting/election-results"),
    ("WI results (WEC)", "https://elections.wi.gov/elections-voting/results"),
    ("NE results", "https://electionresults.nebraska.gov/"),
]
out = []
for label, url in URLS:
    out.append(f"\n== {label}: {url}")
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
        ct = r.headers.get("content-type", "")
        out.append(f"   status {r.status_code}, {len(r.content):,} bytes, {ct}")
        if r.status_code == 200:
            if url.endswith(".zip"):
                z = zipfile.ZipFile(io.BytesIO(r.content))
                out.append(f"   zip members: {z.namelist()[:5]}")
                head = z.open(z.namelist()[0]).read(1500).decode("latin-1")
                out.append("   first lines: " + head.replace("\n", " | ")[:700])
            elif "html" in ct:
                t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
                out.append("   text: " + t[:300])
                links = re.findall(r'href=["\']([^"\']+\.(?:zip|csv|txt|xlsx?|xml|json))', r.text, re.I)
                out.append(f"   data links: {list(dict.fromkeys(links))[:15]}")
            else:
                out.append("   first lines: " + r.text[:700].replace("\n", " | "))
    except Exception as ex:
        out.append(f"   failed: {str(ex)[:160]}")
txt = "\n".join(out)
open("data/portal_files.txt", "w").write(txt + "\n")
print(txt)
