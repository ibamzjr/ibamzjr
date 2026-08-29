#!/usr/bin/env python3
"""Stage a contribution snapshot without regressing cached GitHub data."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import date
from pathlib import Path


SUMMARY_PATTERN = re.compile(r"([\d,]+) contributions in the last year")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fresh_json", type=Path)
    parser.add_argument("fresh_svg", type=Path)
    parser.add_argument("published_json", type=Path)
    parser.add_argument("published_svg", type=Path)
    return parser.parse_args()


def load_snapshot(path: Path) -> tuple[date, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2:
        raise RuntimeError(f"Unsupported contribution schema in {path}")
    range_end = date.fromisoformat(str(payload["range"]["to"]))
    total = int(payload["total_contributions"])
    calculated = sum(int(day["count"]) for day in payload["days"])
    if total != calculated:
        raise RuntimeError(f"Contribution total is inconsistent in {path}")
    return range_end, total


def validate_svg(path: Path, expected_total: int) -> None:
    match = SUMMARY_PATTERN.search(path.read_text(encoding="utf-8"))
    if match is None or int(match.group(1).replace(",", "")) != expected_total:
        raise RuntimeError(f"Contribution SVG is inconsistent with its data: {path}")


def main() -> None:
    args = parse_args()
    fresh_end, fresh_total = load_snapshot(args.fresh_json)
    published_end, published_total = load_snapshot(args.published_json)
    validate_svg(args.fresh_svg, fresh_total)

    stale = fresh_end < published_end or (
        fresh_end == published_end and fresh_total < published_total
    )
    if stale:
        print(
            "Skipped cached contribution data: "
            f"fresh={fresh_end}/{fresh_total}, "
            f"published={published_end}/{published_total}"
        )
        return

    shutil.copyfile(args.fresh_json, args.published_json)
    shutil.copyfile(args.fresh_svg, args.published_svg)
    print(f"Staged contribution snapshot: {fresh_end}/{fresh_total}")


if __name__ == "__main__":
    main()
