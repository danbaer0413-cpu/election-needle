"""Post-election archive. Run by .github/workflows/shutdown.yml (or by hand: python shutdown.py).

Copies everything that records what the model saw and said into data/archive/midterms_2026/, with a MANIFEST.csv
(path, bytes, sha256) and a README.md saying what is there and when it was taken. Nothing is deleted or changed.
Skips raw voter files (never committed) and zip files.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import os
import shutil

OUT = "data/archive/midterms_2026"
SKIP_DIRS = {"raw", "voterfile", "archive", "__pycache__"}
SKIP_NAMES = ("voter",)

# whole folders / single files that make up the record
TREES = ["data", "config"]
EXTRA_FILES = ["README.md", "FUNDAMENTALS.md", "INDEPENDENTS.md", "HOUSE.md", "SHEET.md"]


def _skip(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    if any(p in SKIP_DIRS for p in parts[:-1]):
        return True
    name = parts[-1].lower()
    return name.endswith(".zip") or name.endswith(".pyc") or any(s in name for s in SKIP_NAMES)


def collect() -> list[str]:
    files = []
    for t in TREES:
        for root, dirs, names in os.walk(t):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for n in names:
                p = os.path.join(root, n)
                if not _skip(p):
                    files.append(p)
    files += [f for f in EXTRA_FILES if os.path.exists(f)]
    return sorted(set(files))


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(out: str = OUT) -> int:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    rows = []
    for p in collect():
        dst = os.path.join(out, p)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(p, dst)
        rows.append((p, os.path.getsize(p), sha(p)))
    with open(os.path.join(out, "MANIFEST.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "bytes", "sha256"])
        w.writerows(rows)
    with open(os.path.join(out, "README.md"), "w") as f:
        f.write(f"""# 2026 midterm needle: archive

Taken {stamp}. Copy of the data and config as they stood when the live schedule was shut down.

- `data/latest.json`: the last published projection for every race.
- `data/needle_log.csv`: every update's median, p10, p90 and win probability, by race and time.
- `data/votehub_*`, `data/poll_*`, `data/polls_all.csv`, `data/bsky_*`: polls and VoteHub posts as collected.
- `data/election_night.csv`, `data/night/`, `data/<state>/<race>/results.csv, early.csv, statewide.csv, reporting.csv`: what was loaded on election night.
- `config/`: the model settings, race list, switches and fundamentals in force.
- `MANIFEST.csv`: every file with its size and SHA-256, so a later change is detectable.

Use for the post-mortem: compare `needle_log.csv` and `latest.json` with certified results.
Raw voter files and zip files are not included.
""")
    print(f"archived {len(rows)} files to {out}")
    return len(rows)


if __name__ == "__main__":
    run()
