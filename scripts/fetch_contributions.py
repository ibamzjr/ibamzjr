#!/usr/bin/env python3
"""Fetch GitHub's public contribution calendar without an API token."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


COUNT_PATTERN = re.compile(r"([\d,]+)\s+contributions?", re.IGNORECASE)
TOTAL_PATTERN = re.compile(
    r"([\d,]+)\s+contributions?\s+in\s+the\s+last\s+year",
    re.IGNORECASE,
)
CELL_ID_PATTERN = re.compile(r"contribution-day-component-(\d+)-(\d+)$")


@dataclass(frozen=True)
class RawCell:
    date_text: str
    level: int
    week: int
    weekday: int
    element_id: str
    count_text: str | None


class ContributionCalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: list[RawCell] = []
        self.tooltips: dict[str, str] = {}
        self.months: list[tuple[str, int]] = []
        self._tooltip_for: str | None = None
        self._tooltip_parts: list[str] = []
        self._month_span: int | None = None
        self._month_text_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        classes = set(values.get("class", "").split())
        if tag == "td" and values.get("data-date"):
            match = CELL_ID_PATTERN.fullmatch(values.get("id", ""))
            if match is None:
                raise ValueError("Contribution cell has an unexpected id")
            weekday = int(match.group(1))
            week_from_id = int(match.group(2))
            try:
                week = int(values["data-ix"])
                level = int(values["data-level"])
            except (KeyError, ValueError) as error:
                raise ValueError("Contribution cell metadata is invalid") from error
            if week != week_from_id:
                raise ValueError("Contribution cell id and data-ix disagree")
            self.cells.append(
                RawCell(
                    date_text=values["data-date"],
                    level=level,
                    week=week,
                    weekday=weekday,
                    element_id=values["id"],
                    count_text=values.get("data-count") or None,
                )
            )
        elif (
            tag == "td"
            and "ContributionCalendar-label" in classes
            and values.get("colspan")
        ):
            self._month_span = int(values["colspan"])
        elif (
            tag == "span"
            and self._month_span is not None
            and values.get("aria-hidden") == "true"
        ):
            self._month_text_parts = []
        elif tag == "tool-tip" and values.get("for"):
            self._tooltip_for = values["for"]
            self._tooltip_parts = []

    def handle_data(self, data: str) -> None:
        if self._tooltip_for is not None:
            self._tooltip_parts.append(data)
        if self._month_text_parts is not None:
            self._month_text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._month_text_parts is not None:
            label = " ".join(self._month_text_parts).strip()
            if label:
                self.months.append((label, int(self._month_span)))
            self._month_text_parts = None
        elif tag == "td" and self._month_span is not None:
            self._month_span = None
        elif tag == "tool-tip" and self._tooltip_for is not None:
            self.tooltips[self._tooltip_for] = " ".join(
                self._tooltip_parts
            ).strip()
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
    parser.add_argument(
        "--input-html",
        type=Path,
        help="Optional saved GitHub contribution fragment for offline validation",
    )
    return parser.parse_args()


def download_calendar(username: str) -> str:
    url = f"https://github.com/users/{username}/contributions"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html",
            "User-Agent": f"{username}-profile-calendar/2.0",
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
    raise RuntimeError(f"Could not determine contribution count for {cell.date_text}")


def build_payload(username: str, source_html: str) -> dict[str, object]:
    parser = ContributionCalendarParser()
    parser.feed(source_html)
    if not 350 <= len(parser.cells) <= 371:
        raise RuntimeError(
            f"Expected 350-371 dated contribution cells, received {len(parser.cells)}"
        )
    if len(parser.tooltips) != len(parser.cells):
        raise RuntimeError("Every contribution cell must have one official tooltip")
    if len(parser.months) != 13 or sum(span for _, span in parser.months) != 53:
        raise RuntimeError("Official month headers must span exactly 53 weeks")

    days: list[dict[str, object]] = []
    for cell in parser.cells:
        cell_date = date.fromisoformat(cell.date_text)
        expected_weekday = (cell_date.weekday() + 1) % 7
        if cell.weekday != expected_weekday:
            raise RuntimeError(f"Official weekday mismatch for {cell.date_text}")
        tooltip = parser.tooltips[cell.element_id]
        days.append(
            {
                "date": cell.date_text,
                "count": parse_count(cell, tooltip),
                "level": cell.level,
                "week": cell.week,
                "weekday": cell.weekday,
                "tooltip": tooltip,
            }
        )

    days.sort(key=lambda day: str(day["date"]))
    dates = [date.fromisoformat(str(day["date"])) for day in days]
    if any((right - left).days != 1 for left, right in zip(dates, dates[1:])):
        raise RuntimeError("Contribution dates are not consecutive")
    if min(int(day["week"]) for day in days) != 0 or max(
        int(day["week"]) for day in days
    ) != 52:
        raise RuntimeError("Official contribution cells must use weeks 0 through 52")
    if any(int(day["level"]) not in range(5) for day in days):
        raise RuntimeError("Official contribution levels must be between 0 and 4")

    total_match = TOTAL_PATTERN.search(source_html)
    if total_match is None:
        raise RuntimeError("Official contribution total was not found")
    official_total = int(total_match.group(1).replace(",", ""))
    calculated_total = sum(int(day["count"]) for day in days)
    if official_total != calculated_total:
        raise RuntimeError(
            f"Official total {official_total} does not match tooltip sum {calculated_total}"
        )

    latest_age = datetime.now(timezone.utc).date() - dates[-1]
    if latest_age.days > 8:
        raise RuntimeError(f"Contribution data is stale; latest date is {dates[-1]}")

    start_week = 0
    months: list[dict[str, object]] = []
    for label, span in parser.months:
        months.append({"label": label, "start_week": start_week, "span": span})
        start_week += span

    return {
        "schema_version": 2,
        "username": username,
        "source": f"https://github.com/users/{username}/contributions",
        "range": {"from": days[0]["date"], "to": days[-1]["date"]},
        "total_contributions": official_total,
        "months": months,
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
    source_html = (
        args.input_html.read_text(encoding="utf-8")
        if args.input_html is not None
        else download_calendar(args.username)
    )
    payload = build_payload(args.username, source_html)
    write_json_atomic(args.output, payload)
    print(
        f"Wrote {args.output}: {len(payload['days'])} official cells, "
        f"{payload['total_contributions']} contributions"
    )


if __name__ == "__main__":
    main()
