"""
Pull VoteHub's posts for a date range and save the ones that look like RESULTS (not early-vote totals), so we can see their format.

    python votehub_samples.py --since 2026-08-01 --until 2026-08-15 [--pages 40]

Run on GitHub: Actions -> votehub-samples -> Run workflow (enter dates). Saves data/votehub_samples.txt: for each post its date,
text, image alt text (results are often posted as pictures) and link title. Send me that file.
"""
import argparse
import re
from votehub import fetch_records, parse_post

RESULT = re.compile(r"report|counted|\bin\b.*%|leads?|wins?|won|called|projected|results|vote count|precincts|%\s*-\s*%|\d+\.\d%", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-01"); ap.add_argument("--until", default="2099-01-01")
    ap.add_argument("--pages", type=int, default=40); ap.add_argument("--out", default="data/votehub_samples.txt")
    a = ap.parse_args()
    recs = fetch_records(pages=a.pages)
    print(f"fetched {len(recs)} posts, oldest {min((r['created'] for r in recs), default='n/a')}")
    keep = []
    for r in recs:
        day = r["created"][:10]
        full = r["text"] + " " + r["alt"]
        if not (a.since <= day <= a.until) or parse_post(r["text"]):
            continue
        if RESULT.search(full):
            keep.append(r)
    with open(a.out, "w") as f:
        f.write(f"{len(keep)} possible results posts {a.since} to {a.until}\n\n")
        for r in keep:
            f.write(f"[{r['created']}] {r['uri']}\nTEXT: {r['text']}\nIMAGE ALT: {r['alt'] or '-'}\nLINK: {r['link'] or '-'}\n\n-----\n\n")
    print(f"saved {len(keep)} posts to {a.out}")


if __name__ == "__main__":
    main()
