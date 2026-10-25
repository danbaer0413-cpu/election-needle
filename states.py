"""
State / level / race registry.

Statewide contests are modelled on counties. House, legislative and local contests use
whatever reporting units sit inside the race's footprint (counties, towns, wards or
precincts) - you supply that unit list in counties.csv, so one model covers every level.

Senate and governor lists: Green Papers (Senate, incl. specials) and Wikipedia
(governors), fetched 2026-10-24. Re-check before Election Night.

`party_reg` marks states that record party registration (so early/mail files may carry
party). Check your state's ballot-return file; the app falls back to the
early-vote geography signal when party data is missing.
"""
from __future__ import annotations

import re

# abbr: (name, party_reg)
STATES = {
    "AL": ("Alabama", False), "AK": ("Alaska", True), "AZ": ("Arizona", True), "AR": ("Arkansas", False),
    "CA": ("California", True), "CO": ("Colorado", True), "CT": ("Connecticut", True), "DE": ("Delaware", True),
    "DC": ("District of Columbia", True), "FL": ("Florida", True), "GA": ("Georgia", False),
    "HI": ("Hawaii", False), "ID": ("Idaho", True), "IL": ("Illinois", False), "IN": ("Indiana", False),
    "IA": ("Iowa", True), "KS": ("Kansas", True), "KY": ("Kentucky", True), "LA": ("Louisiana", True),
    "ME": ("Maine", True), "MD": ("Maryland", True), "MA": ("Massachusetts", True), "MI": ("Michigan", False),
    "MN": ("Minnesota", False), "MS": ("Mississippi", False), "MO": ("Missouri", False), "MT": ("Montana", False),
    "NE": ("Nebraska", True), "NV": ("Nevada", True), "NH": ("New Hampshire", True), "NJ": ("New Jersey", True),
    "NM": ("New Mexico", True), "NY": ("New York", True), "NC": ("North Carolina", True),
    "ND": ("North Dakota", False), "OH": ("Ohio", False), "OK": ("Oklahoma", True), "OR": ("Oregon", True),
    "PA": ("Pennsylvania", True), "RI": ("Rhode Island", True), "SC": ("South Carolina", False),
    "SD": ("South Dakota", True), "TN": ("Tennessee", False), "TX": ("Texas", False), "UT": ("Utah", True),
    "VT": ("Vermont", False), "VA": ("Virginia", False), "WA": ("Washington", False),
    "WV": ("West Virginia", True), "WI": ("Wisconsin", False), "WY": ("Wyoming", True),
}

SENATE_2026 = {"AL", "AK", "AR", "CO", "DE", "FL", "GA", "ID", "IL", "IA", "KS", "KY", "LA", "ME", "MA",
               "MI", "MN", "MS", "MT", "NE", "NH", "NJ", "NM", "NC", "OH", "OK", "OR", "RI", "SC", "SD",
               "TN", "TX", "VA", "WV", "WY"}
SENATE_SPECIAL = {"FL", "OH"}
GOVERNOR_2026 = {"AL", "AK", "AZ", "AR", "CA", "CO", "CT", "FL", "GA", "HI", "ID", "IL", "IA", "KS", "ME",
                 "MD", "MA", "MI", "MN", "NE", "NV", "NH", "NM", "NY", "OH", "OK", "OR", "PA", "RI", "SC",
                 "SD", "TN", "TX", "VT", "WI", "WY"}

LEVELS = ["Federal", "State", "Local"]

# Ballot rules by state for the statewide general elections. These are starting points:
# third_share (share of first-round ballots for candidates other than D and R) is a
# placeholder to set from polls or past results, not a measured value.
RULES = {
    "GA": dict(runoff_rule=True, third_share=0.025),   # majority required, else runoff
    "ME": dict(rcv=True, third_share=0.05),            # ranked-choice general for Senate, governor
    "AK": dict(rcv=True, third_share=0.04),            # ranked-choice general; counts by election district
}

# Model settings that make sense by kind of race. Smaller races = noisier units, thinner polling.
PRESETS = {
    "statewide": dict(use_poll=True, sd_poll=3.0, tau_county=2.5, tau_region=2.0, sigma_nonrep=12.0,
                      units="County"),
    "district": dict(use_poll=True, sd_poll=4.0, tau_county=3.0, tau_region=2.5, sigma_nonrep=13.0,
                     units="County / town / precinct group"),
    "local": dict(use_poll=False, sd_poll=6.0, tau_county=4.0, tau_region=3.0, sigma_nonrep=15.0,
                  units="Precinct / ward / town"),
}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def races_for(abbr: str, level: str) -> list[dict]:
    """Races offered for a state and level. Each: name, kind (preset key), scope text."""
    name = STATES[abbr][0]
    out: list[dict] = []
    if level == "Federal":
        if abbr in SENATE_2026:
            tag = " (special)" if abbr in SENATE_SPECIAL else ""
            out.append(dict(name=f"U.S. Senate{tag}", kind="statewide",
                            scope=f"All of {name}, reported by county"))
        out.append(dict(name="U.S. House - one district", kind="district",
                        scope="Units inside the district. Re-aggregate your baseline to the current lines."))
    elif level == "State":
        if abbr in GOVERNOR_2026:
            out.append(dict(name="Governor", kind="statewide", scope=f"All of {name}, reported by county"))
        out.append(dict(name="Other statewide office or ballot measure", kind="statewide",
                        scope="Baseline from a comparable past contest or measure"))
        out.append(dict(name="State legislature - one district", kind="district",
                        scope="Units inside the district"))
    else:
        out.append(dict(name="Mayor / county / school board / local measure", kind="local",
                        scope="Precincts, wards or towns inside the jurisdiction"))
    return out


def race_dir(abbr: str, race_name: str) -> str:
    return f"data/{abbr}/{slug(race_name)}"
