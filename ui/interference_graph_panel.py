"""Somna Interference Graph — ImGui Panel Renderer.

The Neural Chord Interface: a visual instrument for composing cross-modal
interference patterns. Not a mixing desk — a loom.

Slots into the control panel via set_section_extra():

    graph    = InterferenceGraph()
    ig_panel = InterferenceGraphPanel(graph, patch_fn=patch_live)
    panel_manager.set_section_extra("SomaticPalette", ig_panel.render)

Visual layout:
  ┌─────────────────────────────────────────────────────────────┐
  │  VNS     ──●────────────────────── 38Hz Alpha              │
  │  Haptic  ──────●────────────────── 42Hz Gamma              │
  │  Audio   ──────────●────────────── 40Hz Gamma              │
  │  Visual  ───────────────●────────── 44Hz Gamma              │
  │  Δ Delta ▐ Theta ▐ Alpha ▐ Beta ▐▐ Gamma                  │
  └─────────────────────────────────────────────────────────────┘
  [Spread: 0.0 Hz]  [GENUS] [Somna Deep] [Theta Weaver] ...

Unavailable channels (Haptic, VNS — no hardware yet) are rendered at
reduced opacity and cannot be dragged. Their nodes are tracked for future
hardware integration without any changes to the data model.
"""

from __future__ import annotations

import math
import time
from typing import Callable

from imgui_bundle import imgui

from ui.panel_theme import hex_to_u32, hex_to_rgba, token_u32, token_rgba, FONTS
from ui.interference_graph import (
    InterferenceGraph,
    Channel,
    ChordNode,
    Tether,
    CHANNEL_ORDER,
    CHANNEL_COLORS,
    CHANNEL_AVAILABLE,
    BAND_RANGES,
    FREQ_MIN,
    FREQ_MAX,
    band_label_for_freq,
    PRESETS,
)


# ── Layout constants ──────────────────────────────────────────────────────────

LANE_HEIGHT = 38.0
LANE_PAD_Y = 6.0
NODE_RADIUS = 9.0
NODE_RADIUS_HOV = 11.0
TETHER_WIDTH = 2.5
BAND_STRIP_H = 18.0
GRAPH_PAD_X = 68.0  # must fit longest label ("Haptic") right-aligned with 8px gap
GRAPH_PAD_RIGHT = 12.0
SPREAD_KNOB_W = 140.0
MIN_GRAPH_W = 260.0

# Unavailable channel alpha multiplier
_UNAVAIL_ALPHA = 0.35


# ── Color helpers ─────────────────────────────────────────────────────────────


def _channel_u32(ch: Channel, alpha: float = 1.0) -> int:
    if not CHANNEL_AVAILABLE[ch]:
        alpha *= _UNAVAIL_ALPHA
    return hex_to_u32(CHANNEL_COLORS[ch], alpha)


def _channel_rgba(ch: Channel, alpha: float = 1.0) -> tuple[float, float, float, float]:
    if not CHANNEL_AVAILABLE[ch]:
        alpha *= _UNAVAIL_ALPHA
    return hex_to_rgba(CHANNEL_COLORS[ch], alpha)


_BAND_BG_COLORS: dict[str, int] = {
    "Delta": hex_to_u32("#1a1a2e", 0.15),
    "Theta": hex_to_u32("#2a1a3e", 0.12),
    "Alpha": hex_to_u32("#1a2a3e", 0.10),
    "Beta": hex_to_u32("#1a3a2e", 0.08),
    "Gamma": hex_to_u32("#3a1a2e", 0.12),
}

_BAND_LABEL_COLORS: dict[str, int] = {
    "Delta": hex_to_u32("#6e6a86", 0.7),
    "Theta": hex_to_u32("#908caa", 0.7),
    "Alpha": hex_to_u32("#9ccfd8", 0.6),
    "Beta": hex_to_u32("#c4a7e7", 0.6),
    "Gamma": hex_to_u32("#eb6f92", 0.7),
}


# ── Tether glow pulse ─────────────────────────────────────────────────────────


def _tether_glow_alpha(tether: Tether, palette_active: bool = False) -> float:
    """Steady glow when idle; pulses at the tether's average frequency when a palette is active."""
    if palette_active:
        avg_hz = (tether.node_a.frequency_hz + tether.node_b.frequency_hz) * 0.5
        phase = math.sin(2.0 * math.pi * avg_hz * time.time())
        norm = (phase + 1.0) * 0.5
        return tether.intensity * (0.30 + norm * 0.40)
    return tether.intensity * 0.50


# ── Main panel class ──────────────────────────────────────────────────────────


class InterferenceGraphPanel:
    """ImGui renderer for the Interference Graph.

    One instance per graph. Drag state is tracked as instance variables —
    no module-level globals — so multiple instances (e.g., in tests) are
    fully independent.
    """

    def __init__(
        self,
        graph: InterferenceGraph,
        patch_fn: Callable[[dict], None] | None = None,
    ) -> None:
        self.graph = graph
        self._patch_fn = patch_fn
        # Drag state — instance-level, no module global
        self._dragging_channel: Channel | None = None

    def render(self, content_width: float, palette_active: bool = False) -> None:
        """Main entry point — called every frame by the panel manager."""
        self._palette_active = palette_active
        dl = imgui.get_window_draw_list()
        pos = imgui.get_cursor_screen_pos()

        n_lanes = len(CHANNEL_ORDER)
        graph_h = n_lanes * (LANE_HEIGHT + LANE_PAD_Y) + BAND_STRIP_H + LANE_PAD_Y
        graph_w = max(MIN_GRAPH_W, content_width)

        imgui.dummy(imgui.ImVec2(graph_w, graph_h))

        gx0 = pos.x + GRAPH_PAD_X
        gx1 = pos.x + graph_w - GRAPH_PAD_RIGHT
        gy0 = pos.y

        # Band background tints
        lane_total_h = n_lanes * (LANE_HEIGHT + LANE_PAD_Y)
        for band_name, band_lo, band_hi in BAND_RANGES:
            x0 = InterferenceGraph.freq_to_x(band_lo, gx0, gx1)
            x1 = InterferenceGraph.freq_to_x(band_hi, gx0, gx1)
            dl.add_rect_filled(
                imgui.ImVec2(x0, gy0),
                imgui.ImVec2(x1, gy0 + lane_total_h),
                _BAND_BG_COLORS.get(band_name, 0),
            )

        # Band boundary lines
        for _, band_lo, _ in BAND_RANGES:
            x = InterferenceGraph.freq_to_x(band_lo, gx0, gx1)
            dl.add_line(
                imgui.ImVec2(x, gy0),
                imgui.ImVec2(x, gy0 + lane_total_h),
                token_u32("separator", 0.3),
                1.0,
            )

        tethers = self.graph.compute_tethers()

        # Tethers drawn before nodes so nodes always render on top
        self._render_tethers(dl, tethers, gx0, gx1, gy0)

        # Swim lanes + node positions
        node_positions: dict[Channel, imgui.ImVec2] = {}
        for i, ch in enumerate(CHANNEL_ORDER):
            node = self.graph.nodes[ch]
            lane_y = gy0 + i * (LANE_HEIGHT + LANE_PAD_Y)
            cy = lane_y + LANE_HEIGHT / 2.0
            avail = CHANNEL_AVAILABLE[ch]

            lane_bg = hex_to_u32("#232136", 0.35 if avail else 0.18)
            dl.add_rect_filled(
                imgui.ImVec2(gx0, lane_y),
                imgui.ImVec2(gx1, lane_y + LANE_HEIGHT),
                lane_bg,
                2.0,
            )
            dl.add_line(
                imgui.ImVec2(gx0, cy),
                imgui.ImVec2(gx1, cy),
                token_u32("separator", 0.2 if avail else 0.08),
                1.0,
            )

            # Channel label — right-aligned to the left of the graph
            label = ch.value
            label_col = _channel_u32(ch, 0.9 if avail else 0.45)
            lw = imgui.calc_text_size(label).x
            dl.add_text(
                imgui.ImVec2(
                    pos.x + GRAPH_PAD_X - lw - 8, cy - imgui.get_text_line_height() / 2
                ),
                label_col,
                label,
            )

            nx = InterferenceGraph.freq_to_x(node.frequency_hz, gx0, gx1)
            node_pos = imgui.ImVec2(nx, cy)
            node_positions[ch] = node_pos

            if avail:
                freq_text = (
                    f"{node.frequency_hz:.1f} {band_label_for_freq(node.frequency_hz)}"
                )
                tw = imgui.calc_text_size(freq_text).x
                lh = imgui.get_text_line_height()
                # Flip label to left of node when it would overflow the right edge
                if nx + NODE_RADIUS + 6 + tw <= gx1:
                    lx = nx + NODE_RADIUS + 6
                else:
                    lx = nx - NODE_RADIUS - 6 - tw
                dl.add_text(
                    imgui.ImVec2(lx, cy - lh / 2),
                    _channel_u32(ch, 0.7),
                    freq_text,
                )

        # Nodes on top of tethers
        for ch in CHANNEL_ORDER:
            node = self.graph.nodes[ch]
            npos = node_positions[ch]
            avail = CHANNEL_AVAILABLE[ch]
            hovered = avail and self._is_node_hovered(npos)
            dragging = self._dragging_channel == ch
            r = NODE_RADIUS_HOV if (hovered or dragging) else NODE_RADIUS

            # Outer glow first, then solid circle — glow stays underneath
            glow_a = 0.40 if hovered else 0.22
            dl.add_circle_filled(npos, r + 4, _channel_u32(ch, glow_a), 24)
            dl.add_circle_filled(npos, r, _channel_u32(ch, 1.0 if avail else 0.4), 24)
            # Inner highlight
            hl_a = 0.5 if hovered else 0.3
            dl.add_circle_filled(
                npos,
                r * 0.45,
                hex_to_u32("#ffffff", hl_a * (1.0 if avail else 0.4)),
                16,
            )

            if avail:
                src_colors = {
                    "user": token_u32("source_user_lock"),
                    "agent": token_u32("source_agent"),
                    "conductor": token_u32("source_director"),
                    "preset": token_u32("source_user_lock"),
                }
                dl.add_circle_filled(
                    imgui.ImVec2(npos.x, npos.y + r * 0.6),
                    2.5,
                    src_colors.get(node.source, token_u32("source_director")),
                    8,
                )
            else:
                dl.add_circle(npos, r, _channel_u32(ch, 0.3), 24, 1.0)
                # Tooltip for planned channels — triggered via invisible button
                imgui.set_cursor_screen_pos(
                    imgui.ImVec2(npos.x - NODE_RADIUS_HOV, npos.y - NODE_RADIUS_HOV)
                )
                imgui.invisible_button(
                    f"##tip_{ch.value}",
                    imgui.ImVec2(NODE_RADIUS_HOV * 2, NODE_RADIUS_HOV * 2),
                )
                if imgui.is_item_hovered():
                    imgui.set_tooltip(f"{ch.value}: planned hardware — not yet active")

        self._handle_node_drag(node_positions, gx0, gx1)

        strip_y = gy0 + lane_total_h + LANE_PAD_Y
        self._render_band_strip(dl, gx0, gx1, strip_y)

        imgui.set_cursor_screen_pos(imgui.ImVec2(pos.x, strip_y + BAND_STRIP_H + 8))
        self._render_controls(graph_w)

        writes = self.graph.pending_writes()
        if writes and self._patch_fn:
            self._patch_fn(writes)

    # ── Tether rendering ──────────────────────────────────────────────────

    def _render_tethers(
        self,
        dl: imgui.ImDrawList,
        tethers: list[Tether],
        gx0: float,
        gx1: float,
        gy0: float,
    ) -> None:
        # Pre-determine which single tether gets a badge (the strongest one)
        badge_tether = max(tethers, key=lambda t: t.intensity) if tethers else None

        for tether in tethers:
            a = tether.node_a
            b = tether.node_b

            a_idx = CHANNEL_ORDER.index(a.channel)
            b_idx = CHANNEL_ORDER.index(b.channel)
            a_y = gy0 + a_idx * (LANE_HEIGHT + LANE_PAD_Y) + LANE_HEIGHT / 2
            b_y = gy0 + b_idx * (LANE_HEIGHT + LANE_PAD_Y) + LANE_HEIGHT / 2
            a_x = InterferenceGraph.freq_to_x(a.frequency_hz, gx0, gx1)
            b_x = InterferenceGraph.freq_to_x(b.frequency_hz, gx0, gx1)

            glow = _tether_glow_alpha(tether, getattr(self, "_palette_active", False))

            # Blend both channel colors for the tether
            ra, ga_c, ba_c, _ = hex_to_rgba(CHANNEL_COLORS[a.channel], 1.0)
            rb, gb_c, bb_c, _ = hex_to_rgba(CHANNEL_COLORS[b.channel], 1.0)
            r = (ra + rb) / 2.0
            g = (ga_c + gb_c) / 2.0
            b_c = (ba_c + bb_c) / 2.0

            # Curved bezier: bow the control point perpendicular to the
            # a→b direction so the strand is visibly elastic, not a ruler line.
            dx = b_x - a_x
            dy = b_y - a_y
            ln = math.sqrt(dx * dx + dy * dy) or 1.0
            # Perpendicular unit vector (rotated 90° right of a→b)
            px, py = dy / ln, -dx / ln
            bow = min(28.0, 10.0 + abs(b_idx - a_idx) * 9.0)
            cx = (a_x + b_x) / 2.0 + px * bow
            cy_cp = (a_y + b_y) / 2.0 + py * bow

            # Quadratic bezier polyline (12 segments)
            pts = []
            for s in range(13):
                t = s / 12.0
                qx = (1 - t) ** 2 * a_x + 2 * (1 - t) * t * cx + t**2 * b_x
                qy = (1 - t) ** 2 * a_y + 2 * (1 - t) * t * cy_cp + t**2 * b_y
                pts.append(imgui.ImVec2(qx, qy))

            # Draw glow (wide, dim) FIRST so the sharp line sits on top
            glow_col = imgui.IM_COL32(
                int(r * 255), int(g * 255), int(b_c * 255), int(glow * 75)
            )
            dl.add_polyline(
                pts, glow_col, 0, TETHER_WIDTH * 3.5 * tether.intensity + 1.0
            )

            # Sharp core line on top of glow
            core_col = imgui.IM_COL32(
                int(r * 255), int(g * 255), int(b_c * 255), int(glow * 255)
            )
            dl.add_polyline(pts, core_col, 0, TETHER_WIDTH * tether.intensity + 0.5)

            # Badge at arc midpoint — only for the single strongest tether
            if tether is badge_tether and tether.intensity > 0.3:
                t_mid = 0.5
                bx_m = (
                    (1 - t_mid) ** 2 * a_x
                    + 2 * (1 - t_mid) * t_mid * cx
                    + t_mid**2 * b_x
                )
                by_m = (
                    (1 - t_mid) ** 2 * a_y
                    + 2 * (1 - t_mid) * t_mid * cy_cp
                    + t_mid**2 * b_y
                )

                badge = tether.badge_text
                tw_b = imgui.calc_text_size(badge).x
                bw = tw_b + 10
                bh = imgui.get_text_line_height() + 4
                bg_col = imgui.IM_COL32(
                    int(r * 100), int(g * 100), int(b_c * 100), int(glow * 180)
                )
                dl.add_rect_filled(
                    imgui.ImVec2(bx_m - bw / 2, by_m - bh / 2),
                    imgui.ImVec2(bx_m + bw / 2, by_m + bh / 2),
                    bg_col,
                    3.0,
                )
                txt_col = imgui.IM_COL32(
                    int(min(255, r * 255 + 80)),
                    int(min(255, g * 255 + 80)),
                    int(min(255, b_c * 255 + 80)),
                    int(glow * 240),
                )
                dl.add_text(
                    imgui.ImVec2(
                        bx_m - tw_b / 2, by_m - imgui.get_text_line_height() / 2
                    ),
                    txt_col,
                    badge,
                )

    # ── Band spectrum strip ───────────────────────────────────────────────

    # Greek-letter abbreviations — always single-char, never overflow a narrow band
    _BAND_SHORT: dict[str, str] = {
        "Delta": "δ",
        "Theta": "θ",
        "Alpha": "α",
        "Beta": "β",
        "Gamma": "γ",
    }

    def _render_band_strip(
        self,
        dl: imgui.ImDrawList,
        gx0: float,
        gx1: float,
        strip_y: float,
    ) -> None:
        lh = imgui.get_text_line_height()
        for band_name, band_lo, band_hi in BAND_RANGES:
            x0 = InterferenceGraph.freq_to_x(band_lo, gx0, gx1)
            x1 = InterferenceGraph.freq_to_x(band_hi, gx0, gx1)
            cx = (x0 + x1) / 2.0
            col = _BAND_LABEL_COLORS.get(band_name, token_u32("text_muted", 0.5))

            dl.add_rect_filled(
                imgui.ImVec2(x0, strip_y),
                imgui.ImVec2(x1, strip_y + BAND_STRIP_H),
                _BAND_BG_COLORS.get(band_name, 0),
                1.0,
            )

            sym = self._BAND_SHORT.get(band_name, band_name[0])
            sw = imgui.calc_text_size(sym).x
            dl.add_text(
                imgui.ImVec2(cx - sw / 2, strip_y + (BAND_STRIP_H - lh) / 2),
                col,
                sym,
            )

    # ── Node interaction ──────────────────────────────────────────────────

    def _is_node_hovered(self, npos: imgui.ImVec2) -> bool:
        io = imgui.get_io()
        dx = io.mouse_pos.x - npos.x
        dy = io.mouse_pos.y - npos.y
        return (dx * dx + dy * dy) <= (NODE_RADIUS_HOV + 4) ** 2

    def _handle_node_drag(
        self,
        node_positions: dict[Channel, imgui.ImVec2],
        gx0: float,
        gx1: float,
    ) -> None:
        io = imgui.get_io()

        if imgui.is_mouse_clicked(0) and not io.want_text_input:
            for ch, npos in node_positions.items():
                if CHANNEL_AVAILABLE[ch] and self._is_node_hovered(npos):
                    self._dragging_channel = ch
                    break

        if self._dragging_channel is not None:
            if imgui.is_mouse_down(0):
                hz = InterferenceGraph.x_to_freq(io.mouse_pos.x, gx0, gx1)
                hz = round(max(FREQ_MIN, min(FREQ_MAX, hz)) * 2.0) / 2.0
                self.graph.set_channel_frequency(
                    self._dragging_channel, hz, source="user"
                )
            else:
                self._dragging_channel = None

    # ── Controls row ──────────────────────────────────────────────────────

    def _render_controls(self, graph_w: float) -> None:
        # ── Spread row ────────────────────────────────────────────────────
        imgui.text_colored(imgui.ImVec4(*token_rgba("text_label")), "Spread")
        imgui.same_line(spacing=6)

        slider_w = min(SPREAD_KNOB_W, graph_w * 0.40)
        imgui.set_next_item_width(slider_w)
        changed, new_spread = imgui.slider_float(
            "##spread_knob",
            self.graph.spread_hz,
            0.0,
            10.0,
            "%.1f Hz",
            imgui.SliderFlags_.none,
        )
        if changed:
            self.graph.apply_spread(new_spread)

        # Chord summary and dominant interference on the same line only when
        # there is enough horizontal room; otherwise drop to a new line.
        summary = self.graph.chord_summary()
        dominant = self.graph.dominant_interference()
        info_text = f"{summary}  {dominant}" if dominant else summary
        info_w = imgui.calc_text_size(info_text).x
        # "Spread" label ≈ 45px, slider, 12px gap
        used = 45 + 6 + slider_w + 12
        if used + info_w <= graph_w:
            imgui.same_line(spacing=12)
        else:
            imgui.dummy(imgui.ImVec2(0, 0))  # new line without extra spacing

        imgui.text_colored(imgui.ImVec4(*token_rgba("text_muted")), summary)
        if dominant:
            imgui.same_line(spacing=8)
            imgui.text_colored(
                imgui.ImVec4(*token_rgba("source_user_lock")),
                dominant,
            )

        # IAF indicator
        if self.graph.iaf_hz is not None:
            imgui.same_line(spacing=12)
            imgui.text_colored(
                imgui.ImVec4(*token_rgba("gauge_mid")),
                f"IAF {self.graph.iaf_hz:.1f} Hz",
            )

        # Preset stamp buttons
        imgui.dummy(imgui.ImVec2(0, 2))
        for preset_name, preset in PRESETS.items():
            short = preset_name[:3]
            clicked = imgui.small_button(f"{short}##preset_{preset_name}")
            if imgui.is_item_hovered():
                imgui.set_tooltip(preset.description)
            if clicked:
                self.graph.apply_preset(preset_name)
            imgui.same_line(spacing=4)

        imgui.dummy(imgui.ImVec2(0, 0))
