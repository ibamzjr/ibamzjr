#!/usr/bin/env python3
"""Generate a self-contained animated ASCII portrait SVG."""

from __future__ import annotations

import argparse
import html
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


SVG_WIDTH = 740
SVG_HEIGHT = 760
GRID_COLUMNS = 92
GRID_ROWS = 56
TEXT_X = 65
TEXT_Y = 96
TEXT_WIDTH = 610
LINE_HEIGHT = 10.45
PROMPT_X = 28
PROMPT_WIDTH = 290
RAMP = " .,:;irsXA253hMHGS#9B@"


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


def subject_alpha(x_ratio: float, y_ratio: float) -> float:
    """Return a soft, portrait-shaped mask tuned for the supplied photo."""
    center = 0.51
    if y_ratio < 0.48:
        half_width = 0.245
    else:
        progress = min(1.0, (y_ratio - 0.48) / 0.52)
        half_width = 0.245 + (0.275 * progress)

    distance = abs(x_ratio - center)
    feather = 0.065
    if distance <= half_width:
        alpha = 1.0
    elif distance >= half_width + feather:
        alpha = 0.0
    else:
        alpha = 1.0 - ((distance - half_width) / feather)

    if y_ratio < 0.015:
        alpha *= y_ratio / 0.015
    return max(0.0, min(1.0, alpha))


def image_to_ascii(source: Path) -> list[str]:
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")

    width, height = image.size
    crop = (
        int(width * 0.08),
        0,
        int(width * 0.92),
        int(height * 0.98),
    )
    image = image.crop(crop)
    image = ImageOps.fit(
        image,
        (GRID_COLUMNS, GRID_ROWS),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.48),
    )
    image = ImageOps.grayscale(image)
    image = ImageOps.autocontrast(image, cutoff=2)
    image = ImageEnhance.Contrast(image).enhance(1.7)
    image = ImageEnhance.Sharpness(image).enhance(1.45)
    image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=135, threshold=3))

    pixels = image.load()
    rows: list[str] = []
    for y in range(GRID_ROWS):
        characters: list[str] = []
        y_ratio = y / max(1, GRID_ROWS - 1)
        for x in range(GRID_COLUMNS):
            x_ratio = x / max(1, GRID_COLUMNS - 1)
            alpha = subject_alpha(x_ratio, y_ratio)
            value = int(pixels[x, y])
            value = int((value * alpha) + (255 * (1.0 - alpha)))
            density = 1.0 - (value / 255)
            ramp_index = min(len(RAMP) - 1, round(density * (len(RAMP) - 1)))
            characters.append(RAMP[ramp_index])
        rows.append("".join(characters))
    return rows


def render_svg(rows: list[str], static: bool) -> str:
    clip_paths: list[str] = []
    text_rows: list[str] = []
    for index, row in enumerate(rows):
        y = TEXT_Y + (index * LINE_HEIGHT)
        clip_id = f"portrait-row-{index}"
        initial_width = TEXT_WIDTH if static else 0
        animation = ""
        if not static:
            begin = 0.15 + (index * 0.043)
            animation = (
                f'<animate attributeName="width" from="0" to="{TEXT_WIDTH}" '
                f'begin="{begin:.3f}s" dur="0.42s" fill="freeze" />'
            )
        clip_paths.append(
            f'<clipPath id="{clip_id}">'
            f'<rect class="wipe" x="{TEXT_X}" y="{y - 9:.2f}" '
            f'width="{initial_width}" height="11.5">{animation}</rect>'
            f'</clipPath>'
        )
        text_rows.append(
            f'<text class="portrait-row" x="{TEXT_X}" y="{y:.2f}" '
            f'textLength="{TEXT_WIDTH}" lengthAdjust="spacingAndGlyphs" '
            f'clip-path="url(#{clip_id})">{html.escape(row)}</text>'
        )

    cursor_x = PROMPT_X + PROMPT_WIDTH + 6
    cursor = (
        ""
        if static
        else f'<rect class="cursor" x="{cursor_x}" y="718" width="8" height="13" rx="1" />'
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" role="img" aria-labelledby="portrait-title portrait-desc">
  <title id="portrait-title">Ilham Romadhon ASCII portrait</title>
  <desc id="portrait-desc">An animated monochrome ASCII portrait generated from Ilham Romadhon's photograph.</desc>
  <defs>
    {''.join(clip_paths)}
    <linearGradient id="portrait-accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#58A6FF" />
      <stop offset="0.52" stop-color="#E6EDF3" />
      <stop offset="1" stop-color="#F2CC60" />
    </linearGradient>
  </defs>
  <style>
    .portrait-row {{
      fill: #C9D1D9;
      font: 9.5px 'Cascadia Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
      white-space: pre;
    }}
    .terminal-text {{
      fill: #8B949E;
      font: 12px 'Cascadia Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
    }}
    .prompt {{
      fill: url(#portrait-accent);
      font: 13px 'Cascadia Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
    }}
    .cursor {{ fill: #58A6FF; animation: cursor-blink 1s steps(1) infinite; }}
    @keyframes cursor-blink {{ 0%, 48% {{ opacity: 1; }} 49%, 100% {{ opacity: 0; }} }}
    @media (prefers-reduced-motion: reduce) {{
      .wipe {{ width: {TEXT_WIDTH}px !important; }}
      .cursor {{ display: none; }}
    }}
  </style>
  <rect x="1" y="1" width="738" height="758" rx="16" fill="#0D1117" stroke="#30363D" stroke-width="2" />
  <path d="M1 52 H739" stroke="#30363D" />
  <circle cx="24" cy="26" r="7" fill="#FF7B72" />
  <circle cx="46" cy="26" r="7" fill="#F2CC60" />
  <circle cx="68" cy="26" r="7" fill="#3FB950" />
  <text class="terminal-text" x="190" y="31">ibam@github: ~ $ ./portrait.sh</text>
  {''.join(text_rows)}
  <path d="M24 697 H716" stroke="#21262D" />
  <text class="prompt" x="{PROMPT_X}" y="730" textLength="{PROMPT_WIDTH}" lengthAdjust="spacingAndGlyphs">ibam@github:~$ whoami  Ilham Romadhon</text>
  {cursor}
</svg>
'''


def main() -> None:
    args = parse_args()
    if not args.source.is_file():
        raise SystemExit(f"Portrait source not found: {args.source}")
    rows = image_to_ascii(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_svg(rows, args.static), encoding="utf-8", newline="\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
