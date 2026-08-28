#!/usr/bin/env python3
"""Fetch the public GitHub contribution calendar without an API token."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path


COUNT_PATTERN = re.compile(r"([\d,]+)\s+contributions?", re.IGNORECASE)


@dataclass
class RawCell:
    date_text: str
    level: int
    element_id: str
    count_text: str | None


class ContributionCalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: list[RawCell] = []
        self.tooltips: dict[str, str] = {}
        self._tooltip_for: str | None = None
        self._tooltip_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "td" and values.get("data-date"):
            try:
                level = int(values.get("data-level", "0"))
            except ValueError as error:
                raise ValueError("Contribution cell has an invalid data-level") from error
            self.cells.append(
                RawCell(
                    date_text=values["data-date"],
                    level=level,
                    element_id=values.get("id", ""),
                    count_text=values.get("data-count") or None,
                )
            )
        elif tag == "tool-tip" and values.get("for"):
            self._tooltip_for = values["for"]
            self._tooltip_parts = []

    def handle_data(self, data: str) -> None:
        if self._tooltip_for is not None:
            self._tooltip_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "tool-tip" and self._tooltip_for is not None:
            self.tooltips[self._tooltip_for] = " ".join(self._tooltip_parts).strip()
            self._tooltip_for = None
            self._tooltip_parts = []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="ibamzjr")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/contributions.json"),
    )
    return parser.parse_args()


def download_calendar(username: str) -> str:
    url = f"https://github.com/users/{username}/contributions"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html",
            "User-Agent": f"{username}-profile-readme/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise RuntimeError(f"GitHub returned HTTP {response.status}")
            return response.read().decode("utf-8")
    except urllib.error.URLError as error:
        raise RuntimeError(f"Unable to fetch {url}: {error}") from error


def parse_count(cell: RawCell, tooltip: str) -> int:
    if cell.count_text is not None:
        try:
            return int(cell.count_text.replace(",", ""))
        except ValueError:
            pass

    if "no contributions" in tooltip.lower():
        return 0
    match = COUNT_PATTERN.search(tooltip)
    if match:
        return int(match.group(1).replace(",", ""))
    if cell.level == 0:
        return 0
    raise RuntimeError(f"Could not determine contribution count for {cell.date_text}")


def calculate_streaks(days: list[dict[str, object]]) -> tuple[int, int]:
    active_dates = {
        date.fromisoformat(str(day["date"]))
        for day in days
        if int(day["count"]) > 0
    }
    longest = 0
    running = 0
    previous: date | None = None
    for active_date in sorted(active_dates):
        if previous is not None and active_date == previous + timedelta(days=1):
            running += 1
        else:
            running = 1
        longest = max(longest, running)
        previous = active_date

    today = datetime.now(timezone.utc).date()
    cursor = min(today, max(date.fromisoformat(str(day["date"])) for day in days))
    if cursor not in active_dates:
        cursor -= timedelta(days=1)
    current = 0
    while cursor in active_dates:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def build_payload(username: str, source_html: str) -> dict[str, object]:
    parser = ContributionCalendarParser()
    parser.feed(source_html)
    if len(parser.cells) < 350:
        raise RuntimeError(
            f"Expected at least 350 contribution cells, received {len(parser.cells)}"
        )

    by_date: dict[date, dict[str, object]] = {}
    for cell in parser.cells:
        cell_date = date.fromisoformat(cell.date_text)
        tooltip = parser.tooltips.get(cell.element_id, "")
        by_date[cell_date] = {
            "date": cell.date_text,
            "count": parse_count(cell, tooltip),
            "level": max(0, min(4, cell.level)),
        }

    ordered_dates = sorted(by_date)
    latest_date = ordered_dates[-1]
    age = datetime.now(timezone.utc).date() - latest_date
    if age.days > 8:
        raise RuntimeError(f"Contribution data is stale; latest date is {latest_date}")

    grid_start = ordered_dates[0] - timedelta(
        days=(ordered_dates[0].weekday() + 1) % 7
    )
    days: list[dict[str, object]] = []
    for day_date in ordered_dates:
        item = by_date[day_date]
        item["week"] = (day_date - grid_start).days // 7
        item["weekday"] = (day_date.weekday() + 1) % 7
        days.append(item)

    current_streak, longest_streak = calculate_streaks(days)
    best_day = max(days, key=lambda day: int(day["count"]))
    stats = {
        "total": sum(int(day["count"]) for day in days),
        "active_days": sum(1 for day in days if int(day["count"]) > 0),
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "best_day": best_day["date"],
        "best_day_count": int(best_day["count"]),
    }
    return {
        "schema_version": 1,
        "username": username,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": f"https://github.com/users/{username}/contributions",
        "range": {"from": days[0]["date"], "to": days[-1]["date"]},
        "stats": stats,
        "days": days,
    }


def write_json_atomic(output: Path, payload: dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=output.parent,
        delete=False,
    ) as handle:
        handle.write(rendered)
        temporary = Path(handle.name)
    temporary.replace(output)


def main() -> None:
    args = parse_args()
    payload = build_payload(args.username, download_calendar(args.username))
    write_json_atomic(args.output, payload)
    stats = payload["stats"]
    print(
        f"Wrote {args.output}: {stats['total']} contributions, "
        f"{stats['active_days']} active days"
    )


if __name__ == "__main__":
    main()
