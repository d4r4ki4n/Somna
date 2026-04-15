"""Somna Control Panel — Widget Drawing Primitives.

Pure draw functions that accept a DrawList, cursor position, and theme tokens.
Each returns the vertical height consumed so the caller can advance the cursor.

All positions are SCREEN-SPACE (from imgui.get_cursor_screen_pos()), and every
function accounts for scroll offset internally via the DrawList coordinate
system — no raw pixel arithmetic or dummy() hacks needed.

Per ImGui Visual Design Reference §4–6. Adapted from Reese's design for
imgui-bundle API (ChildFlags_.borders, module-relative imports).
"""
from __future__ import annotations

import math
import time
from collections import deque

from imgui_bundle import imgui

from ui.panel_theme import (
    hex_to_u32, hex_to_rgba, token_u32, token_rgba,
    BADGE_CONDUCTOR_PHASE, BADGE_SESSION_PHASE, BADGE_SLEEP_STAGE,
    BADGE_SLEEP_PHASE, BADGE_GENUS_PHASE, BADGE_MAPS, FONTS,
)


# ── Sizing constants (§4) ───────────────────────────────────────────────────
BADGE_H_PAD    = 6.0
BADGE_HEIGHT   = 22.0
BADGE_CORNER_R = 3.0
SPARKLINE_W    = 80.0
SPARKLINE_H    = 20.0
GAUGE_STROKE   = 8.0
GATE_DOT_R     = 5.0
GATE_DOT_GAP   = 6.0
PHASE_RING_R   = 12.0
PROGRESS_H     = 16.0
ALERT_PULSE_SEC = 1.0  # full cycle period


# ── Badge ────────────────────────────────────────────────────────────────────

def draw_badge(
    dl: imgui.ImDrawList,
    pos: imgui.ImVec2,
    text: str,
    bg_hex: str,
    *,
    text_hex: str = "#e0e0e0",
    scale: float = 1.0,
) -> float:
    """Rounded rectangle badge with centered text. Returns consumed height."""
    font = FONTS.get("badge_bold") or FONTS.get("badge")
    if font:
        imgui.push_font(font, 0.0)
    tw = imgui.calc_text_size(text).x
    if font:
        imgui.pop_font()

    w = tw + BADGE_H_PAD * 2 * scale
    h = BADGE_HEIGHT * scale
    r = BADGE_CORNER_R * scale

    dl.add_rect_filled(
        imgui.ImVec2(pos.x, pos.y),
        imgui.ImVec2(pos.x + w, pos.y + h),
        hex_to_u32(bg_hex), r,
    )
    tx = pos.x + (w - tw) * 0.5
    ty = pos.y + (h - imgui.get_text_line_height()) * 0.5
    dl.add_text(imgui.ImVec2(tx, ty), hex_to_u32(text_hex), text)
    return h


def _resolve_badge_color(key: str, value: str) -> tuple[str, str]:
    """Return (bg_hex, text_hex) for a badge value from its config key."""
    for prefix, cmap in BADGE_MAPS.items():
        if prefix in key:
            entry = cmap.get(value)
            if entry is None:
                return ("#888888", "#e0e0e0")
            if isinstance(entry, tuple):
                return entry  # (bg, text) — e.g. sleep_stage
            return (entry, "#e0e0e0")
    return ("#888888", "#e0e0e0")


def badge_for_conductor_phase(dl, pos, value: str, **kw) -> float:
    bg = BADGE_CONDUCTOR_PHASE.get(value, "#888888")
    return draw_badge(dl, pos, value, bg, **kw)

def badge_for_session_phase(dl, pos, value: str, **kw) -> float:
    bg = BADGE_SESSION_PHASE.get(value, "#888888")
    return draw_badge(dl, pos, value, bg, **kw)

def badge_for_sleep_stage(dl, pos, value: str, **kw) -> float:
    entry = BADGE_SLEEP_STAGE.get(value, ("#888888", "#e0e0e0"))
    return draw_badge(dl, pos, value, entry[0], text_hex=entry[1], **kw)

def badge_for_sleep_phase(dl, pos, value: str, **kw) -> float:
    bg = BADGE_SLEEP_PHASE.get(value, "#888888")
    return draw_badge(dl, pos, value, bg, **kw)

def badge_for_genus_phase(dl, pos, value: str, **kw) -> float:
    bg = BADGE_GENUS_PHASE.get(value, "#888888")
    return draw_badge(dl, pos, value, bg, **kw)


# ── Gauge (semi-circle arc) ─────────────────────────────────────────────────

def draw_gauge(
    dl: imgui.ImDrawList,
    pos: imgui.ImVec2,
    value: float,       # 0.0–1.0
    radius: float = 40.0,
    stroke: float = GAUGE_STROKE,
    scale: float = 1.0,
) -> float:
    """180° bottom-arc speedometer gauge with 3-stop gradient.

    value < 0.3 → red (gauge_low)
    0.3–0.6     → amber (gauge_mid)
    > 0.6       → green (gauge_high)

    Returns total height consumed (radius + padding).
    """
    r  = radius * scale
    sw = stroke * scale
    cx = pos.x + r + sw
    cy = pos.y + r + sw

    value = max(0.0, min(1.0, value))
    seg   = 64

    # Track (full arc background)
    dl.path_arc_to(imgui.ImVec2(cx, cy), r, math.pi, 2.0 * math.pi, seg)
    dl.path_stroke(token_u32("gauge_track"), 0, sw)

    # Filled arc
    if value > 0.001:
        end_angle = math.pi + value * math.pi
        if value < 0.3:
            fill = token_u32("gauge_low")
        elif value < 0.6:
            fill = token_u32("gauge_mid")
        else:
            fill = token_u32("gauge_high")
        dl.path_arc_to(imgui.ImVec2(cx, cy), r, math.pi, end_angle, seg)
        dl.path_stroke(fill, 0, sw)

    # Center percentage text
    pct_text = f"{int(value * 100)}%"
    tw = imgui.calc_text_size(pct_text).x
    dl.add_text(
        imgui.ImVec2(cx - tw * 0.5, cy - imgui.get_text_line_height() - 2 * scale),
        token_u32("text_value"), pct_text,
    )
    return r + sw + 4.0 * scale


# ── Inline Gauge (single-row bar + %) ───────────────────────────────────────

def draw_inline_gauge(
    dl: imgui.ImDrawList,
    pos: imgui.ImVec2,
    value: float,       # 0.0–1.0
    width: float,       # total available width
    bar_h: float = 8.0,
) -> float:
    """Single-line gauge: thin bar left, % text right-aligned.

    Total height = one text line. Fits cleanly in a table control column.
    """
    value = max(0.0, min(1.0, value))
    if value < 0.3:
        fill_col = token_u32("gauge_low")
    elif value < 0.6:
        fill_col = token_u32("gauge_mid")
    else:
        fill_col = token_u32("gauge_high")

    pct_text = f"{int(value * 100)}%"
    tw  = imgui.calc_text_size(pct_text).x
    lh  = imgui.get_text_line_height()

    bar_w = max(20.0, width - tw - 8.0)
    bar_y = pos.y + (lh - bar_h) * 0.5

    dl.add_rect_filled(
        imgui.ImVec2(pos.x, bar_y),
        imgui.ImVec2(pos.x + bar_w, bar_y + bar_h),
        token_u32("gauge_track"), 2.0,
    )
    if value > 0.001:
        dl.add_rect_filled(
            imgui.ImVec2(pos.x, bar_y),
            imgui.ImVec2(pos.x + bar_w * value, bar_y + bar_h),
            fill_col, 2.0,
        )
    dl.add_text(
        imgui.ImVec2(pos.x + bar_w + 6.0, pos.y),
        token_u32("text_value"), pct_text,
    )
    return lh


# ── Sparkline ────────────────────────────────────────────────────────────────

def draw_sparkline(
    dl: imgui.ImDrawList,
    pos: imgui.ImVec2,
    buf: deque,
    w: float = SPARKLINE_W,
    h: float = SPARKLINE_H,
    color_hex: str = "#eb6f92",
    scale: float = 1.0,
) -> float:
    """Polyline mini-chart. *buf* is a deque of floats."""
    sw  = w * scale
    sh  = h * scale
    col = hex_to_u32(color_hex)

    if len(buf) < 2:
        dl.add_rect(
            imgui.ImVec2(pos.x, pos.y),
            imgui.ImVec2(pos.x + sw, pos.y + sh),
            token_u32("widget_frame_bg"), 0,
        )
        return sh

    lo  = min(buf)
    hi  = max(buf)
    rng = hi - lo if hi != lo else 1.0
    n   = len(buf)
    step = sw / max(n - 1, 1)

    points = []
    for i, v in enumerate(buf):
        px = pos.x + i * step
        py = pos.y + sh - ((v - lo) / rng) * sh
        points.append(imgui.ImVec2(px, py))

    dl.add_polyline(points, col, 0, 1.0 * scale)
    return sh


# ── Gate Indicator (4-dot R A C S) ──────────────────────────────────────────

_GATE_LABELS = ("R", "A", "C", "S")

def draw_gate_indicator(
    dl: imgui.ImDrawList,
    pos: imgui.ImVec2,
    gates: dict[str, bool],
    scale: float = 1.0,
) -> float:
    """Four colored dots for Respiratory, Alpha, Cardiac, Stillness gates."""
    r     = GATE_DOT_R * scale
    gap   = GATE_DOT_GAP * scale
    green = token_u32("success_green")
    red   = token_u32("alert_red")
    muted = token_u32("text_muted")

    keys = ("respiratory", "alpha", "cardiac", "stillness")
    x    = pos.x
    for k, lbl in zip(keys, _GATE_LABELS):
        cx = x + r
        cy = pos.y + r
        on = gates.get(k, False)
        dl.add_circle_filled(imgui.ImVec2(cx, cy), r, green if on else red)
        lw = imgui.calc_text_size(lbl).x
        dl.add_text(
            imgui.ImVec2(cx - lw * 0.5, cy + r + 2 * scale),
            muted, lbl,
        )
        x += r * 2 + gap

    return r * 2 + imgui.get_text_line_height() + 4 * scale


# ── Phase Ring ───────────────────────────────────────────────────────────────

def draw_phase_ring(
    dl: imgui.ImDrawList,
    pos: imgui.ImVec2,
    phase: float,       # 0.0–1.0 (breath cycle fraction)
    radius: float = PHASE_RING_R,
    scale: float = 1.0,
) -> float:
    """24×24 circular arc from 12-o'clock, filling clockwise."""
    r  = radius * scale
    cx = pos.x + r
    cy = pos.y + r
    seg = 48

    dl.add_circle(imgui.ImVec2(cx, cy), r, token_u32("widget_frame_bg"), seg, 2.0 * scale)

    if phase > 0.001:
        start = -math.pi * 0.5
        end   = start + phase * 2.0 * math.pi
        dl.path_arc_to(imgui.ImVec2(cx, cy), r, start, end, seg)
        dl.path_stroke(hex_to_u32("#eb6f92"), 0, 3.0 * scale)

    return r * 2


# ── Alert Badge (pulsing) ───────────────────────────────────────────────────

def draw_alert_badge(
    dl: imgui.ImDrawList,
    pos: imgui.ImVec2,
    text: str,
    scale: float = 1.0,
) -> float:
    """Badge with sinusoidal alpha pulsing (0.6 → 1.0 over 1 s)."""
    t     = time.monotonic()
    alpha = 0.8 + 0.2 * math.sin(t * 2.0 * math.pi / ALERT_PULSE_SEC)
    return draw_badge(
        dl, pos, text,
        bg_hex="#3d1a25",
        text_hex="#e94560",
        scale=scale,
    )


# ── Composite Gate Badge ────────────────────────────────────────────────────

def draw_composite_gate_badge(
    dl: imgui.ImDrawList,
    pos: imgui.ImVec2,
    all_clear: bool,
    scale: float = 1.0,
) -> float:
    if all_clear:
        return draw_badge(dl, pos, "ALL CLEAR", "#2a273f", text_hex="#9ccfd8", scale=scale)
    return draw_badge(dl, pos, "BLOCKED", "#3d1a25", text_hex="#e94560", scale=scale)


# ── Dot Indicator ────────────────────────────────────────────────────────────

def draw_dot_indicator(
    dl: imgui.ImDrawList,
    pos: imgui.ImVec2,
    is_on: bool,
    label: str,
    scale: float = 1.0,
) -> float:
    """Small colored dot + label text."""
    r  = 4.0 * scale
    cy = pos.y + imgui.get_text_line_height() * 0.5
    col = token_u32("success_green") if is_on else token_u32("text_disabled")
    dl.add_circle_filled(imgui.ImVec2(pos.x + r, cy), r, col)
    dl.add_text(
        imgui.ImVec2(pos.x + r * 2 + 6 * scale, pos.y),
        token_u32("text_label"), label,
    )
    return imgui.get_text_line_height() + 2 * scale


# ── Lock Icon ────────────────────────────────────────────────────────────────

def draw_lock_icon(
    dl: imgui.ImDrawList,
    pos: imgui.ImVec2,
    scale: float = 1.0,
) -> float:
    """Small padlock glyph in user_lock amber, 12×14 px."""
    col = token_u32("source_user_lock")
    s   = scale
    x, y = pos.x, pos.y
    # Body rectangle
    dl.add_rect_filled(
        imgui.ImVec2(x, y + 6 * s),
        imgui.ImVec2(x + 10 * s, y + 14 * s),
        col, 1.5 * s,
    )
    # Shackle arc
    dl.path_arc_to(imgui.ImVec2(x + 5 * s, y + 6 * s), 4 * s, math.pi, 0, 12)
    dl.path_stroke(col, 0, 2.0 * s)
    return 14.0 * s


# ── Progress Bar ─────────────────────────────────────────────────────────────

def draw_progress_bar(
    pos: imgui.ImVec2,
    value: float,       # 0.0–1.0
    width: float = 296.0,
    height: float = PROGRESS_H,
    scale: float = 1.0,
) -> float:
    """Full-width progress bar with centered percentage. Uses imgui directly."""
    w = width * scale
    h = height * scale
    imgui.push_style_color(
        imgui.Col_.plot_histogram,
        imgui.ImVec4(*token_rgba("progress_bar_fill")),
    )
    imgui.progress_bar(max(0.0, min(1.0, value)), imgui.ImVec2(w, h), f"{int(value * 100)}%")
    imgui.pop_style_color()
    return h + 4 * scale


# ── Source Icon ──────────────────────────────────────────────────────────────

def draw_source_icon(
    dl: imgui.ImDrawList,
    pos: imgui.ImVec2,
    source: str,        # "agent", "director", "user"
    scale: float = 1.0,
) -> float:
    """Tiny source-attribution dot, 4px left of the value text."""
    token = {
        "agent":    "source_agent",
        "director": "source_director",
        "user":     "source_user_lock",
    }.get(source, "source_director")
    r  = 3.0 * scale
    cy = pos.y + imgui.get_text_line_height() * 0.5
    dl.add_circle_filled(imgui.ImVec2(pos.x + r, cy), r, token_u32(token))
    return imgui.get_text_line_height()


# ── Text Layout Helpers ──────────────────────────────────────────────────────

def labeled_value_row(
    label: str,
    value: str,
    content_width: float = 296.0,
    label_color: str = "text_label",
    value_color: str = "text_value",
) -> float:
    """Label on the left, value right-aligned. Returns line height consumed."""
    imgui.text_colored(imgui.ImVec4(*token_rgba(label_color)), label)
    imgui.same_line(content_width - imgui.calc_text_size(value).x)
    imgui.text_colored(imgui.ImVec4(*token_rgba(value_color)), value)
    return imgui.get_text_line_height_with_spacing()


def right_aligned_text(
    text: str,
    color: str = "text_value",
    content_width: float = 296.0,
) -> None:
    """Emit text right-aligned within the content area."""
    tw = imgui.calc_text_size(text).x
    imgui.same_line(content_width - tw)
    imgui.text_colored(imgui.ImVec4(*token_rgba(color)), text)


def section_summary_text(
    text: str,
    content_width: float = 296.0,
) -> None:
    """Right-aligned summary in section_summary color (for collapsed headers)."""
    right_aligned_text(text, "text_section_summary", content_width)
