#!/usr/bin/env python3
"""Scrape current U.S. government officials from official .gov websites.

Produces gov_data.json at the repository root. Every value is pulled live
from a government page at run time — nothing is hardcoded. If ANY source
fails to scrape or validate, the script exits non-zero WITHOUT writing the
file, so the previously published data stays in place until a human fixes
the scraper.

Sources (all official government sites):
  senate.gov        -> U.S. senators by state          (Q23)
  house.gov         -> representatives by state        (Q29)
  house.gov         -> Speaker of the House            (Q30)
  whitehouse.gov    -> President and Vice President    (Q38, Q39)
  supremecourt.gov  -> Chief Justice                   (Q57)
  usa.gov           -> governor of each state          (Q61)

Standard library only — no pip installs required.

Usage:
  python3 scraper/scrape.py             # normal (CI)
  python3 scraper/scrape.py --insecure  # skip TLS verification (local dev
                                        # machines with broken cert stores)
"""

import json
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "gov_data.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
]

_ssl_context = None  # set in main()


def fetch(url, retries=2):
    """Download a page and return its text. Retries once on failure."""
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30, context=_ssl_context) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001 — we re-raise after retries
            last_err = e
            time.sleep(2)
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def flip_name(last_first):
    """'Padilla, Alex' -> 'Alex Padilla'; 'Marshall, Roger, M.D.' keeps suffix."""
    parts = [p.strip() for p in last_first.split(",")]
    if len(parts) < 2:
        return last_first.strip()
    name = f"{parts[1]} {parts[0]}"
    if len(parts) > 2:  # honorific / generational suffix
        name += ", " + ", ".join(parts[2:])
    return name


def looks_like_name(s):
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z.'\- ]{2,60}(, (Jr|Sr|II|III|IV|M\.D)\.?)?", s.strip()))


def scrape_senators():
    html = fetch("https://www.senate.gov/senators/index.htm")
    rows = re.findall(
        r'<td>\s*<a href="[^"]*\.senate\.gov[^"]*">\s*([^<]+?)\s*</a>\s*</td>'
        r'\s*<td>\s*([^<]+?)\s*</td>',
        html,
    )
    senators = {}
    for raw_name, state in rows:
        if state not in STATES:
            continue
        senators.setdefault(state, []).append(flip_name(raw_name))

    missing = [s for s in STATES if s not in senators]
    total = sum(len(v) for v in senators.values())
    if missing or total < 96:  # allow a few vacancies, never a parse failure
        raise RuntimeError(
            f"Senator scrape failed validation: {total} senators, missing states: {missing}"
        )
    return senators


def scrape_representatives():
    html = fetch("https://www.house.gov/representatives")
    # Page is a series of per-state tables: <caption id="state-california">...
    chunks = re.split(r'<caption id="state-([a-z\-]+)">', html)
    reps = {}
    for i in range(1, len(chunks), 2):
        slug, body = chunks[i], chunks[i + 1]
        state = " ".join(w.capitalize() for w in slug.split("-"))
        state = state.replace(" Of ", " of ")
        if state not in STATES and state != "District of Columbia":
            continue
        for row in body.split("<tr>")[1:]:
            district_m = re.search(
                r'views-field-value-2[^>]*>\s*([^<]+?)\s*</td>', row
            )
            name_m = re.search(
                r'views-field-value-4[^>]*>\s*<a href="[^"]*">\s*([^<]+?)\s*</a>', row
            )
            if district_m and name_m:
                reps.setdefault(state, []).append(
                    {"district": district_m.group(1), "name": flip_name(name_m.group(1))}
                )

    missing = [s for s in STATES if s not in reps]
    total = sum(len(v) for v in reps.values())
    if missing or not (400 <= total <= 445):  # 435 seats +/- vacancies & delegates
        raise RuntimeError(
            f"Representative scrape failed validation: {total} reps, missing states: {missing}"
        )
    return reps


def scrape_speaker():
    html = fetch("https://www.house.gov/leadership")
    m = re.search(
        r'Speaker of the House</a></h2>.*?<h3>(?:Rep\.\s*)?([^<]+?)\s*</h3>',
        html,
        re.DOTALL,
    )
    if not m or not looks_like_name(m.group(1)):
        raise RuntimeError("Speaker scrape failed: pattern not found on house.gov/leadership")
    return m.group(1).strip()


def scrape_president_vp():
    html = fetch("https://www.whitehouse.gov/administration/")
    desc_m = re.search(r'<meta name="description" content="([^"]+)"', html)
    if not desc_m:
        raise RuntimeError("White House scrape failed: no description meta tag")
    desc = desc_m.group(1)
    pres_m = re.search(r"President\s+([A-Z][^,]+),", desc)
    vp_m = re.search(r"Vice President\s+([A-Z][^,]+),", desc)
    if not pres_m or not vp_m:
        raise RuntimeError(f"White House scrape failed: could not parse '{desc}'")
    president, vp = pres_m.group(1).strip(), vp_m.group(1).strip()
    if not looks_like_name(president) or not looks_like_name(vp):
        raise RuntimeError(f"White House scrape failed validation: '{president}' / '{vp}'")
    return president, vp


def scrape_chief_justice():
    html = fetch("https://www.supremecourt.gov/about/justices.aspx")
    m = re.search(
        r"The Honorable\s+(.+?),\s+is\s+the\s+\d+(?:st|nd|rd|th)\s+"
        r"Chief Justice of the United States",
        html,
    )
    if not m:
        raise RuntimeError("Chief Justice scrape failed: pattern not found on supremecourt.gov")
    return m.group(1).strip()


def scrape_governors():
    governors = {}
    failures = []
    for state in STATES + ["District of Columbia"]:
        slug = state.lower().replace(" ", "-")
        try:
            html = fetch(f"https://www.usa.gov/states/{slug}")
            m = re.search(
                r'field--name-field-governor\b[^>]*>\s*<a [^>]*>'
                r"(?:Contact\s+)?(?:Governor|Gov\.|Mayor)\s+([^<]+?)\s*</a>",
                html,
            )
            if m and looks_like_name(m.group(1)):
                governors[state] = m.group(1).strip()
            elif state != "District of Columbia":  # D.C. has a mayor, not a governor
                failures.append(state)
        except RuntimeError:
            failures.append(state)
        time.sleep(0.3)  # be polite to usa.gov

    if failures:
        raise RuntimeError(f"Governor scrape failed for: {failures}")
    return governors


def main():
    global _ssl_context
    if "--insecure" in sys.argv:
        _ssl_context = ssl._create_unverified_context()
        print("WARNING: TLS verification disabled (--insecure)", file=sys.stderr)

    print("Scraping senate.gov ...")
    senators = scrape_senators()
    print(f"  {sum(len(v) for v in senators.values())} senators across {len(senators)} states")

    print("Scraping house.gov/representatives ...")
    representatives = scrape_representatives()
    print(f"  {sum(len(v) for v in representatives.values())} representatives")

    print("Scraping house.gov/leadership ...")
    speaker = scrape_speaker()
    print(f"  Speaker: {speaker}")

    print("Scraping whitehouse.gov ...")
    president, vice_president = scrape_president_vp()
    print(f"  President: {president} / VP: {vice_president}")

    print("Scraping supremecourt.gov ...")
    chief_justice = scrape_chief_justice()
    print(f"  Chief Justice: {chief_justice}")

    print("Scraping usa.gov state pages (51 pages, ~30s) ...")
    governors = scrape_governors()
    print(f"  {len(governors)} governors/mayors")

    data = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "senators": "https://www.senate.gov/senators/index.htm",
            "representatives": "https://www.house.gov/representatives",
            "speaker": "https://www.house.gov/leadership",
            "president": "https://www.whitehouse.gov/administration/",
            "chiefJustice": "https://www.supremecourt.gov/about/justices.aspx",
            "governors": "https://www.usa.gov/states/",
        },
        "president": president,
        "vicePresident": vice_president,
        "speaker": speaker,
        "chiefJustice": chief_justice,
        "senators": senators,
        "representatives": representatives,
        "governors": governors,
    }

    OUTPUT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
