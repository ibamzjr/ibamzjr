#!/usr/bin/env python3
"""Render IBAM as a projected 3D ASCII flipbook inside a terminal panel."""

from __future__ import annotations

import argparse
import html
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


CANVAS_WIDTH = 486
CANVAS_HEIGHT = 387
GRID_COLUMNS = 64
GRID_ROWS = 28
CELL_WIDTH = 7.0
CELL_HEIGHT = 12.0
ART_X = 19
ART_Y = 35
TITLEBAR_HEIGHT = 28
WORD = "IBAM"
RAMP = " .`:-=+*csS#%@"
LIGHT = np.array([-0.18, -0.42, -1.0], dtype=np.float32)
LIGHT /= np.linalg.norm(LIGHT)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/ibam-wordmark.svg"),
        help="Destination SVG",
    )
    parser.add_argument(
        "--font",
        type=Path,
        help="Optional bold geometric TTF font",
    )
    parser.add_argument(
        "--static",
        action="store_true",
        help="Render the rest frame without animation",
    )
    return parser.parse_args()


def resolve_font(explicit: Path | None) -> Path:
    candidates = [
        explicit,
        Path("C:/Windows/Fonts/ARIALNB.TTF"),
        Path("C:/Windows/Fonts/bahnschrift.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise RuntimeError("No suitable bold geometric font was found")


def rasterize_word(font_path: Path) -> np.ndarray:
    font_size = 260
    font = ImageFont.truetype(str(font_path), font_size)
    tracking = round(font_size * 0.08)
    bounds = [font.getbbox(letter) for letter in WORD]
    widths = [font.getlength(letter) for letter in WORD]
    top = min(box[1] for box in bounds)
    bottom = max(box[3] for box in bounds)
    width = round(sum(widths) + tracking * (len(WORD) - 1) + 20)
    height = bottom - top + 20
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    pen = 10.0
    baseline = 10 - top
    for letter, advance in zip(WORD, widths):
        draw.text((pen, baseline), letter, font=font, fill=255)
        pen += advance + tracking

    mask = np.asarray(image) >= 112
    occupied_y, occupied_x = np.nonzero(mask)
    if len(occupied_x) == 0:
        raise RuntimeError("Wordmark font produced an empty mask")
    return mask[
        occupied_y.min() : occupied_y.max() + 1,
        occupied_x.min() : occupied_x.max() + 1,
    ]


def surface_shell(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    height, width = mask.shape
    extrusion = max(6, round(height * 0.29))
    y, x = np.nonzero(mask)

    points: list[np.ndarray] = []
    normals: list[np.ndarray] = []
    front = np.column_stack((x, y, np.full(len(x), -0.7)))
    points.append(front)
    normals.append(np.tile((0.0, 0.0, -1.0), (len(front), 1)))
    back = np.column_stack((x, y, np.full(len(x), extrusion)))
    points.append(back)
    normals.append(np.tile((0.0, 0.0, 1.0), (len(back), 1)))

    padded = np.pad(mask, 1)
    empty_right = ~padded[1:-1, 2:]
    empty_left = ~padded[1:-1, :-2]
    empty_down = ~padded[2:, 1:-1]
    empty_up = ~padded[:-2, 1:-1]
    boundary = mask & (empty_right | empty_left | empty_down | empty_up)
    edge_y, edge_x = np.nonzero(boundary)
    normal_x = empty_right[edge_y, edge_x].astype(float) - empty_left[
        edge_y, edge_x
    ].astype(float)
    normal_y = empty_down[edge_y, edge_x].astype(float) - empty_up[
        edge_y, edge_x
    ].astype(float)
    length = np.hypot(normal_x, normal_y)
    length[length == 0] = 1.0
    normal_x /= length
    normal_y /= length

    depth_steps = np.linspace(0, extrusion, max(7, extrusion // 4))
    for depth in depth_steps:
        points.append(
            np.column_stack((edge_x, edge_y, np.full(len(edge_x), depth)))
        )
        normals.append(
            np.column_stack((normal_x, normal_y, np.zeros(len(normal_x))))
        )

    cloud = np.concatenate(points).astype(np.float32)
    surface_normals = np.concatenate(normals).astype(np.float32)
    cloud[:, 0] -= width / 2
    cloud[:, 1] -= height / 2
    cloud[:, 2] -= extrusion / 2
    cloud /= float(width)
    return cloud, surface_normals


def rotation_x(angle: float) -> np.ndarray:
    cosine, sine = math.cos(angle), math.sin(angle)
    return np.array(
        [[1, 0, 0], [0, cosine, -sine], [0, sine, cosine]],
        dtype=np.float32,
    )


def rotation_y(angle: float) -> np.ndarray:
    cosine, sine = math.cos(angle), math.sin(angle)
    return np.array(
        [[cosine, 0, sine], [0, 1, 0], [-sine, 0, cosine]],
        dtype=np.float32,
    )


def project(
    points: np.ndarray,
    normals: np.ndarray,
    yaw: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rotation = rotation_x(math.radians(3.5)) @ rotation_y(yaw)
    rotated_points = points @ rotation.T
    rotated_normals = normals @ rotation.T
    visible = rotated_normals[:, 2] < -0.015
    rotated_points = rotated_points[visible]
    rotated_normals = rotated_normals[visible]

    camera_depth = rotated_points[:, 2] + 5.8
    perspective = 4.05 / camera_depth
    intensity = 0.19 + 0.81 * np.clip(rotated_normals @ LIGHT, 0, 1)
    fog = np.clip((camera_depth - 5.45) / 0.8, 0, 1)
    intensity *= 1.0 - 0.28 * fog
    ramp_index = np.clip(
        np.rint(intensity * (len(RAMP) - 1)).astype(int),
        1,
        len(RAMP) - 1,
    )
    return (
        rotated_points[:, 0] * perspective,
        rotated_points[:, 1] * perspective,
        camera_depth,
        ramp_index,
    )


def fit_frames(
    projected: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
) -> tuple[float, float, float]:
    all_x = np.concatenate([frame[0] for frame in projected])
    all_y = np.concatenate([frame[1] for frame in projected])
    x_min, x_max = float(all_x.min()), float(all_x.max())
    y_min, y_max = float(all_y.min()), float(all_y.max())
    aspect = CELL_WIDTH / CELL_HEIGHT
    horizontal = 0.92 * (GRID_COLUMNS - 1) / (x_max - x_min)
    vertical = 0.62 * (GRID_ROWS - 1) / ((y_max - y_min) * aspect)
    scale = min(horizontal, vertical)
    center_x = (GRID_COLUMNS - 1) / 2 - (x_min + x_max) * scale / 2
    center_y = (GRID_ROWS - 1) / 2 - (y_min + y_max) * scale * aspect / 2
    return scale, center_x, center_y


def to_ascii(
    frame: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    scale: float,
    center_x: float,
    center_y: float,
) -> list[str]:
    x, y, depth, ramp_index = frame
    columns = np.rint(center_x + x * scale).astype(int)
    rows = np.rint(
        center_y + y * scale * (CELL_WIDTH / CELL_HEIGHT)
    ).astype(int)
    valid = (
        (columns >= 0)
        & (columns < GRID_COLUMNS)
        & (rows >= 0)
        & (rows < GRID_ROWS)
    )
    columns = columns[valid]
    rows = rows[valid]
    depth = depth[valid]
    ramp_index = ramp_index[valid]

    grid = np.zeros((GRID_ROWS, GRID_COLUMNS), dtype=np.int8)
    far_to_near = np.argsort(-depth)
    grid[rows[far_to_near], columns[far_to_near]] = ramp_index[far_to_near]
    return ["".join(RAMP[index] for index in row) for row in grid]


def frame_markup(rows: list[str], extra: str = "") -> str:
    text_rows: list[str] = []
    for row_index, row in enumerate(rows):
        trimmed = row.rstrip()
        if not trimmed.strip():
            continue
        leading = len(trimmed) - len(trimmed.lstrip())
        body = trimmed[leading:]
        x = ART_X + leading * CELL_WIDTH
        y = ART_Y + row_index * CELL_HEIGHT + CELL_HEIGHT * 0.78
        text_rows.append(
            f'<text xml:space="preserve" x="{x:.1f}" y="{y:.1f}" '
            f'font-size="11.0" textLength="{len(body) * CELL_WIDTH:.1f}" '
            f'lengthAdjust="spacing">{html.escape(body)}</text>'
        )
    return f'<g fill="#C9D1D9"{extra}>{"".join(text_rows)}</g>'


def render_svg(frames: list[list[str]], static: bool) -> str:
    common_start = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" viewBox="0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}" role="img" aria-labelledby="wordmark-title wordmark-desc" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">
  <title id="wordmark-title">Animated 3D IBAM ASCII wordmark</title>
  <desc id="wordmark-desc">IBAM rendered as a monochrome, dimensional ASCII wordmark in a terminal window.</desc>
  <defs>
    <linearGradient id="wordmark-bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#111722" />
      <stop offset="1" stop-color="#0D1117" />
    </linearGradient>
  </defs>
  <style>
    .wordmark-fallback {{ display: none; }}
    @media (prefers-reduced-motion: reduce) {{
      .wordmark-motion {{ display: none; }}
      .wordmark-fallback {{ display: inline; }}
    }}
  </style>
  <rect width="486" height="387" rx="12" fill="url(#wordmark-bg)" />
  <rect x="0.5" y="0.5" width="485" height="386" rx="12" fill="none" stroke="#30363D" />
  <line x1="0" y1="28" x2="486" y2="28" stroke="#30363D" />
  <circle cx="19" cy="14" r="4.5" fill="#FF5F56" />
  <circle cx="34" cy="14" r="4.5" fill="#FFBD2E" />
  <circle cx="49" cy="14" r="4.5" fill="#27C93F" />
  <text x="243" y="18" fill="#7D8590" font-size="11.5" text-anchor="middle">ibam@github: ~$ ./wordmark.sh --3d</text>
'''
    if static:
        return common_start + frame_markup(frames[0]) + "</svg>\n"

    reveal_duration = 1.6
    loop_duration = 5.0
    art_width = GRID_COLUMNS * CELL_WIDTH
    art_height = GRID_ROWS * CELL_HEIGHT
    motion: list[str] = [
        '<g class="wordmark-motion">',
        f'<clipPath id="wordmark-wipe"><rect x="{ART_X}" y="{ART_Y}" '
        f'width="0" height="{art_height}"><animate attributeName="width" '
        f'from="0" to="{art_width}" begin="0s" dur="{reveal_duration}s" '
        f'fill="freeze" /></rect></clipPath>',
        f'<g clip-path="url(#wordmark-wipe)">{frame_markup(frames[0])}'
        f'<set attributeName="opacity" to="0" begin="{reveal_duration}s" /></g>',
    ]
    frame_count = len(frames)
    for index, rows in enumerate(frames):
        if index == 0:
            values = "1;0"
            key_times = f"0;{1 / frame_count:.5f}"
        else:
            values = "0;1;0"
            key_times = (
                f"0;{index / frame_count:.5f};{(index + 1) / frame_count:.5f}"
            )
        animation = (
            f'<animate attributeName="opacity" calcMode="discrete" '
            f'values="{values}" keyTimes="{key_times}" dur="{loop_duration}s" '
            f'begin="{reveal_duration}s" repeatCount="indefinite" />'
        )
        motion.append(
            frame_markup(rows, ' opacity="0"').replace("</g>", animation + "</g>")
        )
    motion.append("</g>")
    fallback = f'<g class="wordmark-fallback">{frame_markup(frames[0])}</g>'
    return common_start + "".join(motion) + fallback + "</svg>\n"


def main() -> None:
    args = parse_args()
    font_path = resolve_font(args.font)
    points, normals = surface_shell(rasterize_word(font_path))
    rest_yaw = math.radians(-12)
    frame_count = 22
    amplitude = math.radians(9.5)
    yaws = [
        rest_yaw + amplitude * math.sin(2 * math.pi * index / frame_count)
        for index in range(frame_count)
    ]
    projected = [project(points, normals, yaw) for yaw in yaws]
    scale, center_x, center_y = fit_frames(projected)
    frames = [to_ascii(frame, scale, center_x, center_y) for frame in projected]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_svg(frames, args.static), encoding="utf-8", newline="\n")
    print(
        f"Wrote {args.output}: {CANVAS_WIDTH}x{CANVAS_HEIGHT}, "
        f"{frame_count} frames, font={font_path.name}"
    )


if __name__ == "__main__":
    main()
