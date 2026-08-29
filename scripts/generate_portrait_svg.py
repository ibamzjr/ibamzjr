#!/usr/bin/env python3
"""Generate a clean, animated ASCII portrait from the supplied photograph."""

from __future__ import annotations

import argparse
import html
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps


SVG_WIDTH = 840
SVG_HEIGHT = 875
GRID_COLUMNS = 100
GRID_ROWS = 53
CELL_WIDTH = 8
CELL_HEIGHT = 15
PADDING = 20
TITLEBAR_HEIGHT = 30
ART_WIDTH = GRID_COLUMNS * CELL_WIDTH
ART_TOP = TITLEBAR_HEIGHT + 7
RAMP = " .`:-=+*cs#%@"
WHITE_FLOOR = 0.80


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Source portrait image")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/ibam-ascii.svg"),
        help="Destination SVG",
    )
    parser.add_argument(
        "--static",
        action="store_true",
        help="Render the final frame without animation",
    )
    return parser.parse_args()


def normalized_points(width: int, height: int, points: list[tuple[float, float]]) -> np.ndarray:
    return np.array(
        [[round(x * width), round(y * height)] for x, y in points],
        dtype=np.int32,
    )


def isolate_subject(rgb: np.ndarray) -> np.ndarray:
    """Extract the centered person with a seeded GrabCut segmentation."""
    height, width = rgb.shape[:2]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    mask = np.full((height, width), cv2.GC_BGD, dtype=np.uint8)

    probable_subject = normalized_points(
        width,
        height,
        [
            (0.25, 0.01),
            (0.66, 0.01),
            (0.74, 0.34),
            (0.93, 0.47),
            (1.00, 0.62),
            (1.00, 1.00),
            (0.00, 1.00),
            (0.03, 0.64),
            (0.12, 0.48),
            (0.27, 0.37),
            (0.20, 0.19),
        ],
    )
    cv2.fillPoly(mask, [probable_subject], cv2.GC_PR_FGD)

    cv2.ellipse(
        mask,
        (round(width * 0.49), round(height * 0.25)),
        (round(width * 0.12), round(height * 0.18)),
        0,
        0,
        360,
        cv2.GC_FGD,
        -1,
    )
    certain_torso = normalized_points(
        width,
        height,
        [(0.30, 0.48), (0.68, 0.48), (0.78, 0.96), (0.20, 0.96)],
    )
    cv2.fillPoly(mask, [certain_torso], cv2.GC_FGD)

    border = max(3, round(min(width, height) * 0.012))
    mask[:border, :] = cv2.GC_BGD
    mask[:, :border] = cv2.GC_BGD
    mask[:, -border:] = cv2.GC_BGD
    mask[-border:, : round(width * 0.08)] = cv2.GC_BGD
    mask[-border:, round(width * 0.92) :] = cv2.GC_BGD

    background_model = np.zeros((1, 65), dtype=np.float64)
    foreground_model = np.zeros((1, 65), dtype=np.float64)
    cv2.grabCut(
        bgr,
        mask,
        None,
        background_model,
        foreground_model,
        8,
        cv2.GC_INIT_WITH_MASK,
    )
    alpha = np.where(
        (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD),
        255,
        0,
    ).astype(np.uint8)

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(alpha, 8)
    if component_count > 1:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        alpha = np.where(labels == largest, 255, 0).astype(np.uint8)

    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, close_kernel, iterations=2)
    return cv2.GaussianBlur(alpha, (0, 0), 2.0)


def compose_portrait(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Reframe the cutout with deliberate headroom and balanced shoulders."""
    height, width = alpha.shape
    ys, xs = np.nonzero(alpha > 24)
    if len(xs) == 0:
        raise RuntimeError("Portrait segmentation produced an empty subject")

    left, right = xs.min(), xs.max() + 1
    top, bottom = ys.min(), ys.max() + 1
    subject_rgb = rgb[top:bottom, left:right]
    subject_alpha = alpha[top:bottom, left:right]

    target_width = round(width * 0.80)
    target_height = round(height * 0.91)
    resized_rgb = cv2.resize(
        subject_rgb,
        (target_width, target_height),
        interpolation=cv2.INTER_LANCZOS4,
    )
    resized_alpha = cv2.resize(
        subject_alpha,
        (target_width, target_height),
        interpolation=cv2.INTER_LANCZOS4,
    )

    canvas_rgb = np.full((height, width, 3), 255, dtype=np.uint8)
    canvas_alpha = np.zeros((height, width), dtype=np.uint8)
    x = (width - target_width) // 2
    y = round(height * 0.025)
    canvas_rgb[y : y + target_height, x : x + target_width] = resized_rgb
    canvas_alpha[y : y + target_height, x : x + target_width] = resized_alpha

    gray = cv2.cvtColor(canvas_rgb, cv2.COLOR_RGB2GRAY)
    detailed = cv2.createCLAHE(clipLimit=2.6, tileGridSize=(8, 8)).apply(gray)
    detailed = cv2.convertScaleAbs(detailed, alpha=1.04, beta=15)
    edges = cv2.GaussianBlur(cv2.Canny(detailed, 54, 132), (0, 0), 0.65)
    detailed = np.minimum(detailed, 255 - edges.astype(np.float32) * 0.34).astype(
        np.uint8
    )

    normalized_alpha = canvas_alpha.astype(np.float32) / 255.0
    composite = (
        detailed.astype(np.float32) * normalized_alpha
        + 255.0 * (1.0 - normalized_alpha)
    )
    return np.clip(composite, 0, 255).astype(np.uint8)


def image_to_ascii(source: Path) -> list[str]:
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    rgb = np.asarray(image)
    prepared = compose_portrait(rgb, isolate_subject(rgb))
    sampled = Image.fromarray(prepared, mode="L").resize(
        (GRID_COLUMNS, GRID_ROWS),
        Image.Resampling.LANCZOS,
    )
    sampled = ImageEnhance.Contrast(sampled).enhance(1.05)
    pixels = np.asarray(sampled, dtype=np.float32) / 255.0

    rows: list[str] = []
    for values in pixels:
        characters: list[str] = []
        for luminance in values:
            adjusted = float(luminance) ** 1.18
            if adjusted >= WHITE_FLOOR:
                characters.append(" ")
                continue
            index = round((1.0 - adjusted) * (len(RAMP) - 1))
            characters.append(RAMP[max(0, min(len(RAMP) - 1, index))])
        rows.append("".join(characters))
    return rows


def render_svg(rows: list[str], static: bool) -> str:
    definitions: list[str] = []
    artwork: list[str] = []
    row_duration = 0.11
    for row_index, row in enumerate(rows):
        row_top = ART_TOP + row_index * CELL_HEIGHT
        baseline = row_top + CELL_HEIGHT * 0.76
        text = (
            f'<text xml:space="preserve" x="{PADDING}" y="{baseline:.1f}" '
            f'fill="#C9D1D9" font-size="12.9" textLength="{ART_WIDTH}" '
            f'lengthAdjust="spacing">{html.escape(row)}</text>'
        )
        if static:
            artwork.append(text)
            continue

        delay = row_index * row_duration
        definitions.append(
            f'<clipPath id="portrait-row-{row_index}">'
            f'<rect class="reveal-rect" x="{PADDING}" y="{row_top:.1f}" '
            f'width="0" height="{CELL_HEIGHT}">'
            f'<animate attributeName="width" from="0" to="{ART_WIDTH}" '
            f'begin="{delay:.2f}s" dur="{row_duration:.2f}s" fill="freeze" />'
            f'</rect></clipPath>'
        )
        artwork.append(f'<g clip-path="url(#portrait-row-{row_index})">{text}</g>')
        artwork.append(
            f'<rect class="print-cursor" y="{row_top + 1:.1f}" width="{CELL_WIDTH}" '
            f'height="{CELL_HEIGHT - 2}" fill="#C9D1D9" opacity="0">'
            f'<animate attributeName="x" from="{PADDING}" to="{PADDING + ART_WIDTH}" '
            f'begin="{delay:.2f}s" dur="{row_duration:.2f}s" fill="freeze" />'
            f'<set attributeName="opacity" to="0.82" begin="{delay:.2f}s" />'
            f'<set attributeName="opacity" to="0" begin="{delay + row_duration:.2f}s" />'
            f'</rect>'
        )

    prompt = "ibam@github:~$ whoami Ilham Romadhon"
    prompt_width = 282
    blink_cursor = ""
    if not static:
        blink_cursor = (
            f'<rect class="blink-cursor" x="{PADDING + prompt_width + 6}" y="847" '
            f'width="8" height="14" fill="#C9D1D9">'
            f'<animate attributeName="opacity" values="1;1;0;0" '
            f'keyTimes="0;0.5;0.51;1" dur="1s" repeatCount="indefinite" />'
            f'</rect>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" role="img" aria-labelledby="portrait-title portrait-desc" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">
  <title id="portrait-title">Ilham Romadhon ASCII portrait</title>
  <desc id="portrait-desc">A clean animated ASCII portrait of Ilham Romadhon in a terminal window.</desc>
  <defs>
    <linearGradient id="portrait-bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#111722" />
      <stop offset="1" stop-color="#0D1117" />
    </linearGradient>
    {''.join(definitions)}
  </defs>
  <style>
    @media (prefers-reduced-motion: reduce) {{
      .reveal-rect {{ width: {ART_WIDTH}px !important; }}
      .print-cursor, .blink-cursor {{ display: none; }}
    }}
  </style>
  <rect width="840" height="875" rx="12" fill="url(#portrait-bg)" />
  <rect x="0.5" y="0.5" width="839" height="874" rx="12" fill="none" stroke="#30363D" />
  <line x1="0" y1="30" x2="840" y2="30" stroke="#30363D" />
  <circle cx="20" cy="15" r="5" fill="#FF5F56" />
  <circle cx="36" cy="15" r="5" fill="#FFBD2E" />
  <circle cx="52" cy="15" r="5" fill="#27C93F" />
  <text x="420" y="19" fill="#7D8590" font-size="12" text-anchor="middle">ibam@github: ~$ ./portrait.sh</text>
  {''.join(artwork)}
  <line x1="0" y1="832" x2="840" y2="832" stroke="#30363D" />
  <text x="{PADDING}" y="859" fill="#7D8590" font-size="13" textLength="{prompt_width}" lengthAdjust="spacing">{prompt}</text>
  {blink_cursor}
</svg>
'''


def main() -> None:
    args = parse_args()
    if not args.source.is_file():
        raise SystemExit(f"Portrait source not found: {args.source}")
    rows = image_to_ascii(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_svg(rows, args.static), encoding="utf-8", newline="\n")
    ink = sum(character != " " for row in rows for character in row)
    print(
        f"Wrote {args.output}: {ink}/{GRID_COLUMNS * GRID_ROWS} ink cells "
        f"({ink / (GRID_COLUMNS * GRID_ROWS):.1%})"
    )


if __name__ == "__main__":
    main()
