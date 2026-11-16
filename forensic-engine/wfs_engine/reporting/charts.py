"""SVG chart primitives used by the HTML report renderer (no JavaScript)."""
from __future__ import annotations

from typing import Iterable
from xml.sax.saxutils import escape

PALETTE = {
    "cyan": "#22d3ee",
    "teal": "#2dd4bf",
    "amber": "#f59e0b",
    "red": "#ef4444",
    "slate": "#94a3b8",
}


def _fmt(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return f"{value:.0f}" if float(value).is_integer() else f"{value:.1f}"


def bar_chart(labels: list[str], values: list[float], width: int = 760,
              height: int = 240, color: str = PALETTE["cyan"]) -> str:
    if not labels:
        return _empty(width, height)
    pad_l, pad_b, pad_t = 44, 42, 12
    plot_w = width - pad_l - 12
    plot_h = height - pad_b - pad_t
    maximum = max(values) or 1
    bar_w = plot_w / len(values)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'xmlns="http://www.w3.org/2000/svg" class="chart">']
    for i in range(4):
        y = pad_t + plot_h * i / 4
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - 12}" y2="{y:.1f}" '
                     f'stroke="#233043" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end" '
                     f'font-size="10" fill="#7c8ba1">{_fmt(maximum * (4 - i) / 4)}</text>')
    for idx, (label, value) in enumerate(zip(labels, values)):
        h = (value / maximum) * plot_h
        x = pad_l + idx * bar_w + bar_w * 0.12
        y = pad_t + plot_h - h
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w * 0.76:.1f}" '
                     f'height="{max(h, 0.6):.1f}" fill="{color}" opacity="0.85" rx="2"/>')
        if len(labels) <= 16:
            parts.append(f'<text x="{x + bar_w * 0.38:.1f}" y="{height - pad_b + 14}" '
                         f'text-anchor="middle" font-size="9" fill="#7c8ba1">'
                         f'{escape(str(label)[:12])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def line_chart(labels: list[str], values: list[float], width: int = 760,
               height: int = 240, color: str = PALETTE["teal"]) -> str:
    if not labels:
        return _empty(width, height)
    pad_l, pad_b, pad_t = 44, 34, 12
    plot_w = width - pad_l - 12
    plot_h = height - pad_b - pad_t
    maximum = max(values) or 1
    step = plot_w / max(1, len(values) - 1)
    points = [(pad_l + i * step, pad_t + plot_h - (v / maximum) * plot_h)
              for i, v in enumerate(values)]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}"
                    for i, (x, y) in enumerate(points))
    area = (f"{path} L{points[-1][0]:.1f},{pad_t + plot_h:.1f} "
            f"L{points[0][0]:.1f},{pad_t + plot_h:.1f} Z")
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'xmlns="http://www.w3.org/2000/svg" class="chart">',
             f'<path d="{area}" fill="{color}" opacity="0.14"/>',
             f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2"/>']
    for i in range(4):
        y = pad_t + plot_h * i / 4
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - 12}" y2="{y:.1f}" '
                     f'stroke="#233043" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end" '
                     f'font-size="10" fill="#7c8ba1">{_fmt(maximum * (4 - i) / 4)}</text>')
    for idx in range(0, len(labels), max(1, len(labels) // 8)):
        x = pad_l + idx * step
        parts.append(f'<text x="{x:.1f}" y="{height - pad_b + 16}" text-anchor="middle" '
                     f'font-size="9" fill="#7c8ba1">{escape(str(labels[idx])[:12])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def heatmap_chart(grid: list[list[int]], labels: list[str], width: int = 760,
                  height: int = 240) -> str:
    if not grid:
        return _empty(width, height)
    pad_l, pad_t = 74, 12
    cell_w = (width - pad_l - 12) / 24
    cell_h = (height - pad_t - 20) / 7
    maximum = max((max(row) for row in grid), default=0) or 1
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'xmlns="http://www.w3.org/2000/svg" class="chart">']
    for row_idx, row in enumerate(grid):
        parts.append(f'<text x="{pad_l - 8}" y="{pad_t + row_idx * cell_h + cell_h * 0.7:.1f}"'
                     f' text-anchor="end" font-size="9" fill="#7c8ba1">'
                     f'{escape(labels[row_idx][:3])}</text>')
        for hour, value in enumerate(row):
            alpha = 0.06 + 0.9 * (value / maximum)
            parts.append(
                f'<rect x="{pad_l + hour * cell_w:.1f}" y="{pad_t + row_idx * cell_h:.1f}"'
                f' width="{cell_w - 1.5:.1f}" height="{cell_h - 1.5:.1f}" rx="2"'
                f' fill="{PALETTE["cyan"]}" opacity="{alpha:.2f}"/>')
    for hour in range(0, 24, 3):
        parts.append(f'<text x="{pad_l + hour * cell_w + cell_w / 2:.1f}" '
                     f'y="{height - 6}" text-anchor="middle" font-size="9" fill="#7c8ba1">'
                     f'{hour:02d}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _empty(width: int, height: int) -> str:
    return (f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
            f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" font-size="12" '
            f'fill="#7c8ba1">No data</text></svg>')
