#!/usr/bin/env python3
"""Generate the animated IBAM ASCII wordmark and profile card."""

from __future__ import annotations

import argparse
import html
from pathlib import Path


SVG_WIDTH = 980
SVG_HEIGHT = 760

LETTER_PATTERNS = {
    "I": (
        "11111",
        "00100",
        "00100",
        "00100",
        "00100",
        "00100",
        "11111",
    ),
    "B": (
        "11110",
        "10001",
        "10001",
        "11110",
        "10001",
        "10001",
        "11110",
    ),
    "A": (
        "01110",
        "10001",
        "10001",
        "11111",
        "10001",
        "10001",
        "10001",
    ),
    "M": (
        "10001",
        "11011",
        "10101",
        "10101",
        "10001",
        "10001",
        "10001",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/ibam-wordmark.svg"),
        help="Destination SVG",
    )
    parser.add_argument(
        "--static",
        action="store_true",
        help="Render the final frame without animation",
    )
    return parser.parse_args()


def build_wordmark_rows(word: str = "IBAM") -> list[str]:
    rows: list[str] = []
    for row_index in range(7):
        letter_rows: list[str] = []
        for letter in word:
            pattern = LETTER_PATTERNS[letter][row_index]
            letter_rows.append("".join("@" if value == "1" else " " for value in pattern))
        rows.append("  ".join(letter_rows))
    return rows


def render_svg(static: bool) -> str:
    wordmark_rows = build_wordmark_rows()
    shadow_far: list[str] = []
    shadow_near: list[str] = []
    foreground: list[str] = []
    for index, row in enumerate(wordmark_rows):
        y = 196 + (index * 39)
        escaped = html.escape(row)
        common = 'textLength="600" lengthAdjust="spacingAndGlyphs"'
        shadow_far.append(
            f'<text class="mark mark-shadow-far" x="204" y="{y + 12}" {common}>{escaped}</text>'
        )
        shadow_near.append(
            f'<text class="mark mark-shadow-near" x="197" y="{y + 6}" {common}>{escaped}</text>'
        )
        foreground.append(
            f'<text class="mark mark-front" x="190" y="{y}" {common}>{escaped}</text>'
        )

    initial_width = 760 if static else 0
    wipe_animation = ""
    if not static:
        wipe_animation = (
            '<animate attributeName="width" from="0" to="760" '
            'begin="0.2s" dur="1.25s" fill="freeze" />'
        )

    info_state = (
        "opacity: 1; transform: none; animation: none;"
        if static
        else "opacity: 0; transform: translateX(-12px); animation: info-enter 0.45s ease-out forwards;"
    )
    shell_animation = "none" if static else "wordmark-rock 5.2s ease-in-out 1.8s infinite"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" role="img" aria-labelledby="wordmark-title wordmark-desc">
  <title id="wordmark-title">IBAM animated ASCII wordmark</title>
  <desc id="wordmark-desc">A dimensional IBAM wordmark followed by Ilham Romadhon's developer profile.</desc>
  <defs>
    <clipPath id="wordmark-wipe">
      <rect class="wordmark-wipe" x="120" y="120" width="{initial_width}" height="360">{wipe_animation}</rect>
    </clipPath>
    <linearGradient id="info-rule" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#58A6FF" />
      <stop offset="0.52" stop-color="#F2CC60" />
      <stop offset="1" stop-color="#FF7B72" />
    </linearGradient>
  </defs>
  <style>
    .terminal-text {{
      fill: #8B949E;
      font: 16px 'Cascadia Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
    }}
    .mark {{
      font: 34px 'Cascadia Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
      white-space: pre;
    }}
    .mark-shadow-far {{ fill: #8C6D1F; opacity: 0.42; }}
    .mark-shadow-near {{ fill: #1F6FEB; opacity: 0.7; }}
    .mark-front {{ fill: #E6EDF3; }}
    .wordmark-shell {{
      transform-box: fill-box;
      transform-origin: center;
      animation: {shell_animation};
    }}
    .identity {{
      fill: #E6EDF3;
      font: 700 22px 'Cascadia Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
      letter-spacing: 0;
    }}
    .info-line {{
      {info_state}
    }}
    .delay-1 {{ animation-delay: 1.65s; }}
    .delay-2 {{ animation-delay: 1.82s; }}
    .delay-3 {{ animation-delay: 1.99s; }}
    .delay-4 {{ animation-delay: 2.16s; }}
    .delay-5 {{ animation-delay: 2.33s; }}
    .info-key {{
      fill: #58A6FF;
      font: 16px 'Cascadia Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
    }}
    .info-value {{
      fill: #C9D1D9;
      font: 16px 'Cascadia Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
    }}
    @keyframes info-enter {{ to {{ opacity: 1; transform: translateX(0); }} }}
    @keyframes wordmark-rock {{
      0%, 100% {{ transform: translateX(0) skewY(0deg); }}
      25% {{ transform: translateX(4px) skewY(-0.7deg); }}
      75% {{ transform: translateX(-4px) skewY(0.7deg); }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .wordmark-wipe {{ width: 760px !important; }}
      .wordmark-shell, .info-line {{ animation: none !important; opacity: 1; transform: none; }}
    }}
  </style>
  <rect x="1" y="1" width="978" height="758" rx="16" fill="#0D1117" stroke="#30363D" stroke-width="2" />
  <path d="M1 64 H979" stroke="#30363D" />
  <circle cx="28" cy="32" r="10" fill="#FF7B72" />
  <circle cx="58" cy="32" r="10" fill="#F2CC60" />
  <circle cx="88" cy="32" r="10" fill="#3FB950" />
  <text class="terminal-text" x="318" y="39">ibam@github: ~ $ ./wordmark.sh --3d</text>
  <g class="wordmark-shell" clip-path="url(#wordmark-wipe)">
    {''.join(shadow_far)}
    {''.join(shadow_near)}
    {''.join(foreground)}
  </g>
  <rect x="90" y="488" width="800" height="2" fill="url(#info-rule)" opacity="0.8" />
  <text class="identity" x="90" y="532">ILHAM ROMADHON</text>
  <g class="info-line delay-1"><text class="info-key" x="90" y="574">role</text><text class="info-value" x="230" y="574">Web Developer</text></g>
  <g class="info-line delay-2"><text class="info-key" x="90" y="610">base</text><text class="info-value" x="230" y="610">Malang, Indonesia</text></g>
  <g class="info-line delay-3"><text class="info-key" x="90" y="646">stack</text><text class="info-value" x="230" y="646">Laravel / React / Inertia.js</text></g>
  <g class="info-line delay-4"><text class="info-key" x="90" y="682">build</text><text class="info-value" x="230" y="682">RoyalVilla</text></g>
  <g class="info-line delay-5"><text class="info-key" x="90" y="718">study</text><text class="info-value" x="230" y="718">BINUS University</text></g>
</svg>
'''


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_svg(args.static), encoding="utf-8", newline="\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
