#!/usr/bin/env python3
"""Refresh a contribution-only GitHub-profile card from public GitHub data.

Uses the Python standard library and GitHub's public contribution calendar.
No API credentials, personal access token, or third-party service is needed.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
COLORS = {
    "bg": "#111914", "ink": "#ebe6d5", "muted": "#94a28e",
    "line": "#344235", "accent": "#b5ca95", "red": "#cc795e",
}
LEVELS = ["#263128", "#45583c", "#6c8753", "#98b374", "#c7dca5"]


class ContributionParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.days = {}
        self.headline = []
        self.in_headline = False

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "h2" and attr.get("id") == "js-contribution-activity-description":
            self.in_headline = True
        if tag in ("td", "rect") and "data-date" in attr and "data-level" in attr:
            when = date.fromisoformat(attr["data-date"])
            level = int(attr["data-level"])
            if not 0 <= level <= 4:
                raise ValueError("Unexpected contribution intensity")
            self.days[when.isoformat()] = level

    def handle_endtag(self, tag):
        if tag == "h2":
            self.in_headline = False

    def handle_data(self, data):
        if self.in_headline:
            self.headline.append(data)

    def result(self):
        text = " ".join(" ".join(self.headline).split())
        match = re.search(r"([\d,]+)\s+contributions?\s+in\s+the\s+last\s+year", text, re.I)
        if not match or len(self.days) < 300:
            raise RuntimeError("GitHub contribution markup changed; preserving the existing card.")
        return int(match.group(1).replace(",", "")), [
            {"date": when, "level": level} for when, level in sorted(self.days.items())
        ]


def collect(username, fixture_dir=None):
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username):
        raise ValueError("Invalid GitHub username")
    if fixture_dir is not None:
        contribution_html = (fixture_dir / "contributions.html").read_text()
    else:
        encoded = urllib.parse.quote(username, safe="")
        request = urllib.request.Request(
            f"https://github.com/users/{encoded}/contributions",
            headers={"User-Agent": "CIA-developer-profile/public-contributions"},
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            contribution_html = response.read().decode("utf-8")
    parser = ContributionParser()
    parser.feed(contribution_html)
    count, days = parser.result()
    # This publicly visible total can include anonymized private contributions
    # if the user has chosen to display them. No private details are fetched.
    return {
        "username": username,
        "updated_on": datetime.now(timezone.utc).date().isoformat(),
        "contributions_past_year": count,
        "contribution_days": days,
    }


def render(data, mobile=False):
    c = COLORS
    width, height = (600, 335) if mobile else (960, 250)
    username = escape(data["username"])
    count = f"{data['contributions_past_year']:,}"
    chunks = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="stats-title stats-description">
<title id="stats-title">{username}'s GitHub contributions</title>
<desc id="stats-description">Snapshot {escape(data['updated_on'])}: {data['contributions_past_year']} contributions in the past year. The heatmap uses GitHub's public contribution intensity levels. This card shows only the contribution total, with no repository, follower, or star counters.</desc>
<style>.mono{{font-family:'SFMono-Regular',Consolas,'Liberation Mono',monospace}} .value{{font-family:Arial,Helvetica,sans-serif;font-weight:600;letter-spacing:-2px}} .ink{{fill:{c['ink']}}} .muted{{fill:{c['muted']}}}</style>
<rect x=".75" y=".75" width="{width-1.5}" height="{height-1.5}" rx="9" fill="{c['bg']}" stroke="{c['line']}" stroke-width="1.5"/>
<rect x=".75" y="18" width="3" height="24" fill="{c['red']}"/>
<text x="32" y="34" class="mono ink" font-size="12" letter-spacing="1.8">OPERATIONS LOG</text>
<text x="{width-32}" y="34" text-anchor="end" class="mono muted" font-size="10">@{username}</text>
<path d="M32 53 H{width-32}" stroke="{c['line']}"/>
<text x="32" y="137" class="value ink" font-size="74">{count}</text>
<text x="34" y="161" class="mono muted" font-size="10" letter-spacing=".45">CONTRIBUTIONS / PAST YEAR</text>
''']
    if mobile:
        chunks.append('<text x="375" y="108" class="mono muted" font-size="12" letter-spacing="1">SIGNALS,</text>')
        chunks.append('<text x="375" y="130" class="mono ink" font-size="12" letter-spacing="1">NOT SCORES.</text>')
        chunks.append(f'<path d="M32 182 H568" stroke="{c["line"]}"/>')
        chunks.append('<text x="36" y="207" class="mono muted" font-size="10" letter-spacing=".6">PAST-YEAR ACTIVITY</text>')
    else:
        chunks.append(f'<path d="M280 81 V177" stroke="{c["line"]}"/>')
        chunks.append('<text x="316" y="86" class="mono muted" font-size="10" letter-spacing=".8">PAST-YEAR CONTRIBUTION SIGNAL</text>')
    first = date.fromisoformat(data["contribution_days"][0]["date"])
    columns = (date.fromisoformat(data["contribution_days"][-1]["date"]) - first).days // 7 + 1
    cell, gap = (8, 2) if mobile else (8, 3)
    if mobile and columns > 53:
        cell, gap = 7, 2
    gx, gy = (36, 221) if mobile else (316, 104)
    for item in data["contribution_days"]:
        offset = (date.fromisoformat(item["date"]) - first).days
        x = gx + (offset // 7) * (cell + gap)
        y = gy + (offset % 7) * (cell + gap)
        label = escape(f"{item['date']}: GitHub activity level {item['level']} of 4")
        chunks.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="1.5" fill="{LEVELS[item["level"]]}"><title>{label}</title></rect>')
    if not mobile:
        chunks.append('<text x="316" y="199" class="mono muted" font-size="10">Signals, not scores.</text>')
        chunks.append('<text x="748" y="199" class="mono muted" font-size="9">less</text>')
        for index, color in enumerate(LEVELS):
            chunks.append(f'<rect x="{780+index*13}" y="191" width="8" height="8" rx="1.5" fill="{color}"/>')
        chunks.append('<text x="853" y="199" class="mono muted" font-size="9">more</text>')
        chunks.append(f'<path d="M32 215 H928" stroke="{c["line"]}"/>')
    footer_y = 315 if mobile else 237
    chunks.append(f'<text x="32" y="{footer_y}" class="mono muted" font-size="9">GITHUB PUBLIC CONTRIBUTIONS</text>')
    chunks.append(f'<text x="{width-32}" y="{footer_y}" class="mono muted" text-anchor="end" font-size="9">PUBLIC RECORD / DAILY SNAPSHOT</text>')
    chunks.append('</svg>\n')
    return '\n'.join(chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', default=os.environ.get('PROFILE_USERNAME', 'Azrael-opm'))
    parser.add_argument('--fixture-dir', type=Path, help='Optional public-data fixtures for testing')
    args = parser.parse_args()
    data = collect(args.username, args.fixture_dir)
    # Complete the fetch and both renders before changing the last snapshot.
    desktop, mobile = render(data), render(data, mobile=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / 'operations-stats.svg').write_text(desktop, encoding='utf-8')
    (ASSETS / 'operations-stats-mobile.svg').write_text(mobile, encoding='utf-8')
    (ASSETS / 'stats.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(f"Updated {data['username']}: {data['contributions_past_year']} contributions. {data['updated_on']}")


if __name__ == '__main__':
    main()
