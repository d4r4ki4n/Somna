"""Somna Control Panel — Config-Driven ImGui Manager.

Loads widget definitions from panel_config.json and renders the panel
based on session mode, disclosure layer, and authority classification.

Replaces the hardcoded per-mode rendering with a data-driven dispatch loop.
Per Bible Ch.9 §9.1 (Control Panel Architecture) §§5–14.

Adapted from Reese's design for imgui-bundle API:
  - imgui.begin(name, p_open, flags)  [positional, returns tuple]
  - imgui.begin_child uses ChildFlags_.borders (not .border)
  - style.set_color_() used in panel_theme.py (not style.colors[])
  - imgui.Key enum used directly (no imgui.Key_ alias)

Usage:
    panel = ControlPanelManager("panel_config.json")
    # Inside your hello_imgui render callback:
    panel.update(live_state_dict)
    panel.render()
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from imgui_bundle import imgui

from ui.panel_theme import (
    apply_somna_theme,
    load_somna_fonts,
    hex_to_u32,
    hex_to_rgba,
    token_u32,
    token_rgba,
    FONTS,
    BADGE_MAPS,
)
from ui.panel_widgets import (
    draw_badge,
    draw_gauge,
    draw_inline_gauge,
    draw_sparkline,
    draw_gate_indicator,
    draw_phase_ring,
    draw_alert_badge,
    draw_composite_gate_badge,
    draw_dot_indicator,
    draw_lock_icon,
    draw_progress_bar,
    draw_source_icon,
    labeled_value_row,
    right_aligned_text,
    section_summary_text,
    _resolve_badge_color,
)
from ipc import patch_live


# ── Constants ────────────────────────────────────────────────────────────────

PANEL_W = 420
PANEL_W_CUE = 240
CONTENT_PAD = 12
COLLAPSED_W = 40
COLLAPSE_ANIM_SEC = 0.2
TRANSITION_SEC = 2.0  # mode crossfade total duration
SPARKLINE_W = 80.0
SPARKLINE_H = 20.0
SPARKLINE_BUF_LEN = 120  # ~2 s at 60 fps
DEBUG_JSON_H = 200.0
DEBUG_LOG_H = 150.0
DEBUG_GATE_H = 40.0

_LAYER_ORDER = ("Essential", "Advanced", "Debug")


# ── Data Structures ─────────────────────────────────────────────────────────


@dataclass
class WidgetDef:
    """Single widget entry parsed from panel_config.json."""

    key: str
    widget: str
    classification: str  # USER_CONTROL | AGENT_TUNABLE | TELEMETRY | INTERNAL
    layer: str  # Essential | Advanced | Debug
    label: str
    section: str
    modes: list[str]
    tooltip: str = ""
    range: list[float] | None = None
    enum: list[str] | None = None
    badge_colors: dict | None = None
    inline: bool = False  # render on same row as previous widget
    password: bool = False  # mask text input (for API keys)


def _parse_widget(raw: dict) -> WidgetDef:
    return WidgetDef(
        key=raw["key"],
        widget=raw["widget"],
        classification=raw["classification"],
        layer=raw["layer"],
        label=raw["label"],
        section=raw["section"],
        modes=raw.get("modes", []),
        tooltip=raw.get("tooltip", ""),
        range=raw.get("range"),
        enum=raw.get("enum"),
        badge_colors=raw.get("badge_colors"),
        inline=bool(raw.get("inline", False)),
        password=bool(raw.get("password", False)),
    )


# ── Section Summary Generators ───────────────────────────────────────────────

_SECTION_SUMMARIES: dict[str, Callable] = {}


def _reg_summary(section: str):
    def decorator(fn):
        _SECTION_SUMMARIES[section] = fn
        return fn

    return decorator


@_reg_summary("Conditioning")
def _summary_conditioning(live: dict) -> str:
    vr = live.get("conditioning_vr_schedule", "?")
    para = live.get("conditioning_paradigm", "?")
    pool = live.get("conditioning_active_pool", "?")
    return f"{vr} · {para} · Pool: {pool}"


@_reg_summary("Habituation")
def _summary_habituation(live: dict) -> str:
    nov = live.get("habituation_novelty_score", 0)
    lc = live.get("stimulus_lifecycle_stage", "?")
    return f"novelty {nov:.2f} · {lc}"


@_reg_summary("Induction")
def _summary_induction(live: dict) -> str:
    tech = live.get("induction_technique", "?")
    d = live.get("trance_score", 0)
    eff = live.get("induction_efficiency", 0)
    return f"{tech} · {int(d * 100)}% · eff {eff:.2f}"


@_reg_summary("DeliveryGate")
def _summary_delivery_gate(live: dict) -> str:
    gc = live.get("gate_all_clear", False)
    st = "ALL" if gc else "partial"
    rl = live.get("relaxation_level", "?")
    return f"{st} gates · relax {rl}"


@_reg_summary("TMR")
def _summary_tmr(live: dict) -> str:
    en = "enabled" if live.get("tmr_enabled") else "disabled"
    cnt = live.get("tmr_cue_count", 0)
    return f"{en} · {cnt} cues · spindle-gated"


@_reg_summary("HTW")
def _summary_htw(live: dict) -> str:
    el = "eligible" if live.get("htw_eligible") else "ineligible"
    ct = live.get("htw_wake_count", 0)
    mx = live.get("htw_max_wakes", 3)
    return f"{el} · count {ct}/{mx}"


@_reg_summary("Visual/Audio")
def _summary_visual_audio(live: dict) -> str:
    temp = live.get("shader_color_temperature", "?")
    pan = "ON" if live.get("audio_panning_enabled") else "OFF"
    return f"temp {temp}K · panning {pan}"


@_reg_summary("GENUS")
def _summary_genus(live: dict) -> str:
    freq = live.get("genus_frequency", 40)
    ver = "verified" if live.get("genus_gamma_verified") else "unverified"
    mins = live.get("genus_session_minutes", 0)
    m, s = divmod(int((mins or 0) * 60), 60)
    return f"{freq}Hz · {ver} · {m}:{s:02d}"


@_reg_summary("OpenXR")
def _summary_openxr(live: dict) -> str:
    if live.get("vr_safety_kill"):
        return "safety kill"
    if live.get("vr_headset_active"):
        mode = live.get("vr_render_mode", "?")
        return f"active · {mode}"
    return "inactive"


@_reg_summary("Haptic")
def _summary_haptic(live: dict) -> str:
    conn = live.get("haptic_connected", False)
    if not conn:
        return "disconnected"
    pat = live.get("haptic_pattern", "continuous")
    act = live.get("haptic_actual_intensity", 0)
    return f"{pat} · {act:.0f}%"


@_reg_summary("taVNS")
def _summary_tavns(live: dict) -> str:
    conn = live.get("tavns_connected", False)
    if not conn:
        return "disconnected"
    imp = "OK" if live.get("tavns_impedance_ok") else "HIGH"
    cur = live.get("tavns_actual_current_ua", 0)
    return f"{cur:.0f}uA · imp {imp}"


# ── Main Manager ─────────────────────────────────────────────────────────────


class ControlPanelManager:
    """Config-driven ImGui control panel for Somna.

    Args:
        config_path:   Path to panel_config.json.
        transport_fn:  Optional callable(cw: float) rendered after the header
                       separator. Use for session start/stop/load buttons.
    """

    def __init__(
        self,
        config_path: str | Path = "panel_config.json",
        transport_fn: Callable[[float], None] | None = None,
    ) -> None:
        raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self._widgets: list[WidgetDef] = [_parse_widget(w) for w in raw["widgets"]]
        self._by_key: dict[str, WidgetDef] = {w.key: w for w in self._widgets}

        self._transport_fn = transport_fn

        # Optional layout extensions
        self._sidebar_fn: "Callable[[float, float], None] | None" = None
        self._sidebar_width: float = 260.0
        self._console_bar_fn: "Callable[[float, float], None] | None" = None
        self._console_bar_height: float = 180.0
        # Optional extra content rendered after Essential widgets (noise buttons, presets…)
        self._essential_extra_fn: "Callable[[float], None] | None" = None
        # Per-section extra content rendered at the top of a named section, before widgets
        self._section_extra_fns: "dict[str, Callable[[float], None]]" = {}

        # Runtime state
        self._live: dict = {}
        self._live_lock = threading.Lock()
        self._debug_mode: bool = False
        self._mode: str = "TRANCE"
        self._prev_mode: str | None = None
        self._transition_t: float | None = None

        # Collapse
        self._collapsed: bool = False
        self._collapse_t: float | None = None
        self._panel_width_cur: float = PANEL_W

        # Sparkline buffers: key → deque
        self._sparklines: dict[str, deque] = {}

        # Locked params (user-set via panel or from timeline_locked_params)
        self._locked_params: set[str] = set()

        # Sections already rendered in the left column spill (cleared each frame)
        self._left_spill_done: set[str] = set()

        # Section order (drag-to-reorder) and expanded state
        self._section_order: list[str] = []  # populated on first render
        self._section_expanded: dict[str, bool] = {}  # True = open in right columns
        self._drag_section: str | None = None  # section being dragged (grip held)
        self._drag_confirmed: bool = False  # True once mouse actually moved
        self._drag_hover_target: str | None = (
            None  # section header hovered as drop target
        )

        # Debug decision log ring buffer
        self._decision_log: deque[dict] = deque(maxlen=50)

        # Debug gate timing ring buffer (30 s @ 60 fps ≈ 1800 samples)
        self._gate_history: deque[dict] = deque(maxlen=1800)

        # Previous live snapshot for change-highlight in debug JSON
        self._prev_live: dict = {}
        self._change_flash: dict[str, float] = {}  # key → flash_start_time

    # ── Public API ───────────────────────────────────────────────────────

    def set_sidebar(
        self,
        fn: "Callable[[float, float], None]",
        width: float = 260.0,
    ) -> None:
        """Register the session player for the top-left column of the header zone.
        fn(col_w, col_h) is called each frame."""
        self._sidebar_fn = fn
        self._sidebar_width = width

    def set_essential_extra(self, fn: "Callable[[float], None]") -> None:
        """Register a callback rendered after the Essential widgets.
        fn(content_width) is called each frame in the Essential section."""
        self._essential_extra_fn = fn

    def set_section_extra(
        self, section_name: str, fn: "Callable[[float], None]"
    ) -> None:
        """Register a callback rendered at the top of a named Advanced section.
        fn(content_width) is called each frame when that section is expanded."""
        self._section_extra_fns[section_name] = fn

    def set_console_bar(
        self,
        fn: "Callable[[float, float], None]",
        height: float = 180.0,
    ) -> None:
        """Register the console for the top-right column of the header zone.
        fn(col_w, col_h, active_layer) is called each frame.
        height sets the header zone height shared with the session player."""
        self._console_bar_fn = fn
        self._console_bar_height = height  # = top_zone height

    def update(self, live: dict) -> None:
        """Thread-safe state update. Called from your state-polling thread."""
        with self._live_lock:
            for k, v in live.items():
                if k in self._prev_live and self._prev_live[k] != v:
                    self._change_flash[k] = time.monotonic()
            self._prev_live = dict(self._live)
            self._live = dict(live)

            # Feed sparkline buffers
            for w in self._widgets:
                if "Sparkline" in w.widget:
                    buf = self._sparklines.setdefault(
                        w.key, deque(maxlen=SPARKLINE_BUF_LEN)
                    )
                    val = live.get(w.key)
                    if val is not None:
                        try:
                            buf.append(float(val))
                        except (TypeError, ValueError):
                            pass

            # Decision log
            dec = live.get("_last_director_decision")
            if dec and (not self._decision_log or self._decision_log[-1] != dec):
                self._decision_log.append(dec)

            # Gate timing
            self._gate_history.append(
                {
                    "t": time.monotonic(),
                    "R": live.get("gate_respiratory", False),
                    "A": live.get("gate_alpha", False),
                    "C": live.get("gate_cardiac", False),
                    "S": live.get("gate_stillness", False),
                }
            )

            # Locked params from timeline
            locked = live.get("timeline_locked_params")
            if isinstance(locked, list):
                self._locked_params = set(locked)

    # ── Dockable-window support ────────────────────────────────────────────

    def section_names(self) -> list[str]:
        """Return ordered list of all Advanced section names."""
        with self._live_lock:
            live = dict(self._live)
        mode = self._mode
        visible = self._visible_widgets(mode)
        depth = [
            w
            for w in visible
            if w.layer == "Advanced" or (w.layer == "Debug" and self._debug_mode)
        ]
        sections = self._group_by_section(depth)
        for _sec in self._section_extra_fns:
            sections.setdefault(_sec, [])
        known = set(sections.keys())
        self._section_order = [s for s in self._section_order if s in known]
        for s in sections:
            if s not in self._section_order:
                self._section_order.append(s)
        return [n for n in self._section_order if n in sections]

    def render_section(self, name: str) -> None:
        """Render a single section (header + extra + widgets) for dockable window use."""
        self._handle_keyboard()
        self._detect_mode()

        with self._live_lock:
            live = dict(self._live)
        mode = self._mode
        visible = self._visible_widgets(mode)
        depth = [
            w
            for w in visible
            if w.layer == "Advanced" or (w.layer == "Debug" and self._debug_mode)
        ]
        sections = self._group_by_section(depth)
        for _sec in self._section_extra_fns:
            sections.setdefault(_sec, [])

        widgets = sections.get(name, [])
        if self._render_section_header(name, live):
            if name in self._section_extra_fns:
                self._section_extra_fns[name](self._content_width())
            self._render_widget_list(widgets, live)

    def render_section_docked(self, name: str) -> None:
        """Render section content only (no drag header) for dockable window use."""
        self._handle_keyboard()
        self._detect_mode()

        with self._live_lock:
            live = dict(self._live)
        mode = self._mode
        visible = self._visible_widgets(mode)
        depth = [
            w
            for w in visible
            if w.layer == "Advanced" or (w.layer == "Debug" and self._debug_mode)
        ]
        sections = self._group_by_section(depth)
        for _sec in self._section_extra_fns:
            sections.setdefault(_sec, [])

        widgets = sections.get(name, [])
        if name in self._section_extra_fns:
            self._section_extra_fns[name](self._content_width())
        self._render_widget_list(widgets, live)

    def render_essential(self) -> None:
        """Render Essential-layer controls + badges + extras."""
        self._handle_keyboard()
        self._detect_mode()

        with self._live_lock:
            live = dict(self._live)
        mode = self._mode
        visible = self._visible_widgets(mode)
        cw = self._content_width()

        ess_controls = [
            w
            for w in visible
            if w.layer == "Essential" and w.widget in ("Slider", "Toggle", "Dropdown")
        ]
        ess_badges = [
            w
            for w in visible
            if w.layer == "Essential"
            and w.widget not in ("Slider", "Toggle", "Dropdown")
        ]

        self._render_widget_list(ess_controls, live)

        if ess_badges:
            self._render_essential_badge_row(ess_badges, live)

        if self._essential_extra_fn is not None:
            imgui.spacing()
            self._essential_extra_fn(cw)

    def render_status_strip(self) -> None:
        """Public wrapper for the status strip."""
        self._render_status_strip()

    def render(self) -> None:
        """Main render entry point. Call every frame."""
        self._handle_keyboard()
        self._detect_mode()

        # Collapse animation
        if self._collapsed:
            self._animate_collapse(target=COLLAPSED_W)
            if self._panel_width_cur <= COLLAPSED_W + 1:
                self._render_collapsed_tab()
                return
        else:
            self._animate_collapse(target=self._base_panel_width())

        vp = imgui.get_main_viewport()
        imgui.set_next_window_pos(vp.work_pos, imgui.Cond_.always)
        imgui.set_next_window_size(vp.work_size, imgui.Cond_.always)

        flags = (
            imgui.WindowFlags_.no_title_bar
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_collapse
            | imgui.WindowFlags_.no_saved_settings
            | imgui.WindowFlags_.no_scrollbar
            | imgui.WindowFlags_.no_scroll_with_mouse
        )
        imgui.begin("##somna_panel", None, flags)

        avail = imgui.get_content_region_avail()
        has_sidebar = self._sidebar_fn is not None
        has_console = self._console_bar_fn is not None

        _SPLIT_W = 5
        _C_HOV = imgui.IM_COL32(86, 82, 110, 140)
        _NO_SCROLL = (
            imgui.WindowFlags_.no_scrollbar | imgui.WindowFlags_.no_scroll_with_mouse
        )

        # ── Left column: session player — independent full-height, grows freely ─
        if has_sidebar:
            imgui.begin_child(
                "##left_col",
                imgui.ImVec2(self._sidebar_width, avail.y),
                child_flags=imgui.ChildFlags_.borders,
            )
            self._sidebar_fn(self._sidebar_width, 0)

            # Spill: fill any remaining vertical space with Advanced sections.
            # get_content_region_avail().y gives us exactly the unused pixels below
            # the session player (and queue) at the current cursor position.
            left_rem = imgui.get_content_region_avail()
            if left_rem.y > 100:
                imgui.begin_child(
                    "##left_spill",
                    imgui.ImVec2(0, left_rem.y),
                    child_flags=imgui.ChildFlags_.none,
                )
                self._left_spill_done = self._render_spill_sections()
                imgui.end_child()
            else:
                self._left_spill_done = set()

            imgui.end_child()

            # Horizontal drag handle (session │ right column)
            imgui.same_line(spacing=0)
            imgui.invisible_button("##hsplit", imgui.ImVec2(_SPLIT_W, avail.y))
            if imgui.is_item_hovered() or imgui.is_item_active():
                imgui.set_mouse_cursor(imgui.MouseCursor_.resize_ew)
                imgui.get_window_draw_list().add_rect_filled(
                    imgui.get_item_rect_min(), imgui.get_item_rect_max(), _C_HOV
                )
            if imgui.is_item_active():
                self._sidebar_width = max(
                    200.0,
                    min(
                        avail.x * 0.65,
                        self._sidebar_width + imgui.get_io().mouse_delta.x,
                    ),
                )
            imgui.same_line(spacing=0)

        # ── Right column: console (top, draggable) + sections (below) ──────────
        right_w = imgui.get_content_region_avail().x
        imgui.begin_child(
            "##right_col",
            imgui.ImVec2(right_w, avail.y),
            child_flags=imgui.ChildFlags_.none,
            window_flags=_NO_SCROLL,
        )
        right_avail = imgui.get_content_region_avail()

        # When there's no sidebar, the SOMNA header lives at the top of the right col
        if not has_sidebar:
            self._render_header()
            imgui.separator()

        if has_console:
            con_h = self._console_bar_height
            imgui.begin_child(
                "##con_col",
                imgui.ImVec2(0, con_h),
                child_flags=imgui.ChildFlags_.borders,
                window_flags=_NO_SCROLL,
            )
            self._console_bar_fn(
                right_w, con_h, self._debug_mode if has_sidebar else None
            )
            imgui.end_child()

            # Vertical drag handle (console │ sections)
            imgui.invisible_button("##vsplit", imgui.ImVec2(right_avail.x, _SPLIT_W))
            if imgui.is_item_hovered() or imgui.is_item_active():
                imgui.set_mouse_cursor(imgui.MouseCursor_.resize_ns)
                imgui.get_window_draw_list().add_rect_filled(
                    imgui.get_item_rect_min(), imgui.get_item_rect_max(), _C_HOV
                )
            if imgui.is_item_active():
                self._console_bar_height = max(
                    120.0,
                    min(
                        right_avail.y - 100.0,
                        self._console_bar_height + imgui.get_io().mouse_delta.y,
                    ),
                )

        # Transport strip (seek bar / pause-restart)
        if self._transport_fn is not None:
            self._transport_fn(imgui.get_content_region_avail().x)
            imgui.separator()

        # Scrollable sections pane fills whatever height remains in the right column
        imgui.begin_child(
            "##sections",
            imgui.ImVec2(0, imgui.get_content_region_avail().y),
            child_flags=imgui.ChildFlags_.none,
        )

        # Compact status strip — always visible regardless of layer
        self._render_status_strip()
        imgui.separator()
        imgui.spacing()

        alpha = self._transition_alpha()
        if alpha is not None:
            imgui.push_style_var(imgui.StyleVar_.alpha, alpha)

        if self._debug_mode:
            self._render_debug_banner()

        self._render_current_layer(skip_sections=self._left_spill_done)

        if self._debug_mode:
            self._render_debug_panels()

        if alpha is not None:
            imgui.pop_style_var()

        imgui.end_child()  # ##sections
        imgui.end_child()  # ##right_col
        imgui.end()

    # ── Mode Detection ───────────────────────────────────────────────────

    def _detect_mode(self) -> None:
        with self._live_lock:
            live = dict(self._live)

        old = self._mode

        if live.get("cue_test_mode"):
            new = "CUE_TEST"
        elif live.get("session_type") == "sleep" or "SLEEP" in str(
            live.get("session_arc", "")
        ):
            new = "SLEEP"
        elif live.get("genus_active") or live.get("conductor_phase") == "GENUS_BLOCK":
            new = "GENUS"
        else:
            new = "TRANCE"

        if new != old:
            self._prev_mode = old
            self._mode = new
            self._transition_t = time.monotonic()

    def _base_panel_width(self) -> float:
        return PANEL_W_CUE if self._mode == "CUE_TEST" else PANEL_W

    # ── Keyboard ─────────────────────────────────────────────────────────

    def _handle_keyboard(self) -> None:
        io = imgui.get_io()
        # Tab → collapse toggle
        if imgui.is_key_pressed(imgui.Key.tab) and not io.want_text_input:
            self._collapsed = not self._collapsed
            self._collapse_t = time.monotonic()
        # Ctrl+Shift+D → debug mode toggle
        if (
            io.key_ctrl
            and io.key_shift
            and imgui.is_key_pressed(imgui.Key.d)
            and not io.want_text_input
        ):
            self._debug_mode = not self._debug_mode

    # ── Essential Status Strip ───────────────────────────────────────────

    def _render_status_strip(self) -> None:
        """Compact always-visible telemetry row: phase · score · HR · EEG · timer."""
        with self._live_lock:
            live = dict(self._live)

        dl = imgui.get_window_draw_list()
        cw = self._content_width()
        pos = imgui.get_cursor_screen_pos()
        h = 26.0

        # Background tint
        dl.add_rect_filled(
            pos,
            imgui.ImVec2(pos.x + cw, pos.y + h),
            token_u32("status_strip_bg"),
            3.0,
        )

        # Draw items left-to-right with same_line spacing
        imgui.dummy(imgui.ImVec2(0, h))  # reserve height before drawing over it
        imgui.set_cursor_screen_pos(imgui.ImVec2(pos.x + 6, pos.y + 5))

        def _item(label: str, value: str, col_token: str = "text_value") -> None:
            imgui.text_colored(imgui.ImVec4(*token_rgba("text_muted")), label)
            imgui.same_line(spacing=3)
            imgui.text_colored(imgui.ImVec4(*token_rgba(col_token)), value)
            imgui.same_line(spacing=10)

        # Trance score as percent
        score = live.get("trance_score")
        if score is not None:
            _item(
                "depth",
                f"{int(float(score) * 100)}%",
                "source_user_lock" if float(score) > 0.7 else "text_value",
            )

        # Heart rate
        hr = live.get("heart_rate_bpm")
        if hr is not None:
            _item("HR", f"{int(float(hr))} bpm")

        # EEG quality dot
        eeg_q = live.get("eeg_signal_quality")
        eeg_lost = live.get("eeg_signal_lost", False)
        if eeg_lost:
            imgui.text_colored(imgui.ImVec4(*token_rgba("alert_red")), "\u25cf lost")
            imgui.same_line(spacing=10)
        elif eeg_q is not None:
            q = float(eeg_q)
            col = (
                token_rgba("success_green")
                if q > 0.7
                else token_rgba("source_user_lock")
                if q > 0.4
                else token_rgba("alert_red")
            )
            imgui.text_colored(imgui.ImVec4(*col), f"\u25cf {int(q * 100)}%")
            imgui.same_line(spacing=10)

        # Session timer (right-aligned)
        elapsed = live.get("session_time") or live.get("session_elapsed")
        if elapsed is not None:
            secs = int(float(elapsed))
            t_str = f"{secs // 60}:{secs % 60:02d}"
            tw = imgui.calc_text_size(t_str).x
            imgui.set_cursor_screen_pos(imgui.ImVec2(pos.x + cw - tw - 8, pos.y + 5))
            imgui.text_colored(imgui.ImVec4(*token_rgba("text_muted")), t_str)

        imgui.set_cursor_screen_pos(imgui.ImVec2(pos.x, pos.y + h + 2))
        imgui.dummy(imgui.ImVec2(0, 0))

    # ── Essential badge row ──────────────────────────────────────────────

    def _render_essential_badge_row(
        self, widgets: "list[WidgetDef]", live: dict
    ) -> None:
        """Render status badges inline — pure same_line flow, no manual cursor math."""
        muted_col = imgui.ImVec4(*token_rgba("text_muted"))
        val_col = imgui.ImVec4(*token_rgba("text_value"))
        alert_col = imgui.ImVec4(*token_rgba("alert_red"))

        first_rendered = True
        for w in widgets:
            value = live.get(w.key)

            if w.widget == "Alert Badge":
                if not value:
                    continue
                if not first_rendered:
                    imgui.same_line(spacing=14)
                imgui.text_colored(alert_col, f"\u26a0 {w.label}")
                first_rendered = False

            elif w.widget in ("Badge", "Indicator", "Value", "Counter", "Timer"):
                v = str(value) if value is not None else "\u2014"
                if not first_rendered:
                    imgui.same_line(spacing=14)
                imgui.text_colored(muted_col, f"{w.label}:")
                imgui.same_line(spacing=3)
                if w.widget == "Badge" and value is not None:
                    _, txt_hex = _resolve_badge_color(w.key, v)
                    r, g, b, a = hex_to_rgba(txt_hex, 1.0)
                    imgui.text_colored(imgui.ImVec4(r, g, b, a), v)
                else:
                    imgui.text_colored(val_col, v)
                first_rendered = False

    # ── Header ───────────────────────────────────────────────────────────

    def _render_header(self) -> None:
        cw = self._content_width()
        f = FONTS.get("panel_title_bold")
        if f:
            imgui.push_font(f, 0.0)
        imgui.text("SOMNA")
        if f:
            imgui.pop_font()

        # Debug mode toggle
        imgui.same_line(cw - 60)
        if self._debug_mode:
            imgui.push_style_color(
                imgui.Col_.button,
                imgui.ImVec4(*token_rgba("button_bg_active")),
            )
        if imgui.button("Debug", imgui.ImVec2(54, 22)):
            self._debug_mode = not self._debug_mode
        if self._debug_mode:
            imgui.pop_style_color()
        imgui.new_line()

        # Lock count indicator
        if self._locked_params:
            imgui.text_colored(
                imgui.ImVec4(*token_rgba("source_user_lock")),
                f"{len(self._locked_params)} locked",
            )

    # ── Widget Layer Rendering ───────────────────────────────────────────

    def _render_current_layer(self, skip_sections: "set[str] | None" = None) -> None:
        mode = self._mode
        with self._live_lock:
            live = dict(self._live)

        visible = self._visible_widgets(mode)
        cw = self._content_width()

        # Essential: split into interactive controls (full-width rows) and
        # status badges (rendered as a compact horizontal strip).
        ess_controls = [
            w
            for w in visible
            if w.layer == "Essential" and w.widget in ("Slider", "Toggle", "Dropdown")
        ]
        ess_badges = [
            w
            for w in visible
            if w.layer == "Essential"
            and w.widget not in ("Slider", "Toggle", "Dropdown")
        ]

        self._render_widget_list(ess_controls, live)

        if ess_badges:
            self._render_essential_badge_row(ess_badges, live)

        if self._essential_extra_fn is not None:
            imgui.spacing()
            self._essential_extra_fn(cw)

        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        depth = [
            w
            for w in visible
            if w.layer == "Advanced" or (w.layer == "Debug" and self._debug_mode)
        ]
        sections = self._group_by_section(depth)
        # Sections that have an extra renderer but no widgets still deserve a header
        for _sec in self._section_extra_fns:
            sections.setdefault(_sec, [])
        # Sync section order from current sections if not yet initialised
        known = set(sections.keys())
        self._section_order = [s for s in self._section_order if s in known]
        for s in sections:
            if s not in self._section_order:
                self._section_order.append(s)

        has_sidebar = self._sidebar_fn is not None
        # When no sidebar, all sections are expanded by default (no left-column state)
        sec_items = [
            (n, sections[n])
            for n in self._section_order
            if n in sections
            and (not has_sidebar or self._section_expanded.get(n, False))
            and (not skip_sections or n not in skip_sections)
        ]

        # Responsive column count: 1 column narrow, 2 at ≥520, 3 at ≥860
        n_cols = 1
        if cw >= 860:
            n_cols = 3
        elif cw >= 520:
            n_cols = 2

        if n_cols == 1:
            for sec_name, widgets in sec_items:
                if self._render_section_header(sec_name, live):
                    if sec_name in self._section_extra_fns:
                        self._section_extra_fns[sec_name](self._content_width())
                    self._render_widget_list(widgets, live)
            self._finish_section_drag()
            return

        # Masonry columns: distribute sections round-robin, render each column
        # as an independent child window so collapsing in one column never
        # adds dead space in another.
        col_secs: list[list] = [[] for _ in range(n_cols)]
        for i, item in enumerate(sec_items):
            col_secs[i % n_cols].append(item)

        spc = imgui.get_style().item_spacing.x
        col_w = (cw - spc * (n_cols - 1)) / n_cols
        avail_h = imgui.get_content_region_avail().y

        for ci, csecs in enumerate(col_secs):
            if ci > 0:
                imgui.same_line(spacing=spc)
            imgui.begin_child(
                f"##seccol{ci}",
                imgui.ImVec2(col_w, avail_h),
                child_flags=imgui.ChildFlags_.none,
            )
            inner_w = imgui.get_content_region_avail().x
            for sec_name, widgets in csecs:
                if self._render_section_header(sec_name, live):
                    if sec_name in self._section_extra_fns:
                        self._section_extra_fns[sec_name](inner_w)
                    self._render_widget_list(widgets, live)
            imgui.end_child()

        self._finish_section_drag()

    def _render_spill_sections(self) -> "set[str]":
        """Left-column section panel.

        Collapsed sections live here as compact draggable rows — clicking one
        expands it (moves it to the right columns).  Expanded sections show
        only their header here (as a 'send back' affordance).

        Returns the set of section names rendered so the right column can skip
        any that are collapsed (they don't need to appear there at all).
        """
        with self._live_lock:
            live = dict(self._live)

        mode = self._mode
        visible = self._visible_widgets(mode)
        depth = [
            w
            for w in visible
            if w.layer == "Advanced" or (w.layer == "Debug" and self._debug_mode)
        ]
        sections = self._group_by_section(depth)
        for _sec in self._section_extra_fns:
            sections.setdefault(_sec, [])

        # Initialise / update section order list (add new, remove stale)
        known = set(sections.keys())
        self._section_order = [s for s in self._section_order if s in known]
        for s in sections:
            if s not in self._section_order:
                self._section_order.append(s)
        for s in sections:
            self._section_expanded.setdefault(s, False)

        rendered_in_left: set[str] = set()
        _C_HOV = imgui.IM_COL32(86, 82, 110, 120)
        _C_DRAG_LINE = imgui.IM_COL32(196, 167, 231, 200)

        drop_target_idx: int | None = None

        for idx, sec_name in enumerate(self._section_order):
            expanded = self._section_expanded.get(sec_name, False)

            # ── Drag-drop source: invisible button over the header text area ──
            p0 = imgui.get_cursor_screen_pos()
            row_h = 22.0
            dl = imgui.get_window_draw_list()

            # Background highlight for hovered row
            imgui.invisible_button(f"##drag_{sec_name}", imgui.ImVec2(-1, row_h))
            is_hov = imgui.is_item_hovered()
            is_act = imgui.is_item_active()
            if is_hov:
                dl.add_rect_filled(
                    p0,
                    imgui.ImVec2(
                        p0.x + imgui.get_content_region_avail().x + 999, p0.y + row_h
                    ),
                    _C_HOV,
                )

            # Draw the header text on top of the invisible button
            arrow = "\u25be " if expanded else "\u25b8 "
            label_col = token_u32("text_label") if expanded else token_u32("text_muted")
            imgui.set_cursor_screen_pos(
                imgui.ImVec2(
                    p0.x + 4, p0.y + (row_h - imgui.get_text_line_height()) * 0.5
                )
            )
            dl.add_text(
                imgui.ImVec2(
                    p0.x + 4, p0.y + (row_h - imgui.get_text_line_height()) * 0.5
                ),
                label_col,
                arrow + sec_name,
            )
            imgui.set_cursor_screen_pos(imgui.ImVec2(p0.x, p0.y + row_h))

            # Click on the row toggles expand/collapse
            if is_hov and imgui.is_mouse_released(0) and not imgui.is_mouse_dragging(0):
                self._section_expanded[sec_name] = not expanded

            # Collapsed sections are "owned" by the left column
            if not expanded:
                rendered_in_left.add(sec_name)

        return rendered_in_left

    def _visible_widgets(self, mode: str) -> list[WidgetDef]:
        result = []
        for w in self._widgets:
            if mode not in w.modes:
                continue
            if w.classification == "INTERNAL" and not self._debug_mode:
                continue
            result.append(w)
        return result

    def _group_by_section(self, widgets: list[WidgetDef]) -> dict[str, list[WidgetDef]]:
        groups: dict[str, list[WidgetDef]] = {}
        for w in widgets:
            groups.setdefault(w.section, []).append(w)
        return groups

    # ── Section Header with Summary ──────────────────────────────────────

    def _finish_section_drag(self) -> None:
        """Complete or cancel a section drag when the mouse button is released."""
        if self._drag_section and not imgui.is_mouse_down(0):
            if self._drag_confirmed and self._drag_hover_target:
                dragged = self._drag_section
                target = self._drag_hover_target
                if (
                    dragged in self._section_order
                    and target in self._section_order
                    and dragged != target
                ):
                    self._section_order.remove(dragged)
                    new_idx = self._section_order.index(target)
                    self._section_order.insert(new_idx, dragged)
            self._drag_section = None
            self._drag_confirmed = False
            self._drag_hover_target = None

    def _render_section_header(self, name: str, live: dict) -> bool:
        """Render collapsing header with drag grip. Returns True when expanded."""
        summary_fn = _SECTION_SUMMARIES.get(name)
        summary = summary_fn(live) if summary_fn else ""

        # ── Drag grip: six-dot handle at the left of the header ──────────────
        _GRIP_W = 16.0
        p0 = imgui.get_cursor_screen_pos()
        fh = imgui.get_frame_height()
        imgui.invisible_button(f"##grip_{name}", imgui.ImVec2(_GRIP_W, fh))
        is_grip_active = imgui.is_item_active()
        is_grip_hovered = imgui.is_item_hovered()

        # Draw two columns of three dots (⠿ style)
        dl = imgui.get_window_draw_list()
        dot_col = (
            token_u32("text_muted")
            if not is_grip_hovered
            else token_u32("text_primary")
        )
        mid_y = p0.y + fh * 0.5
        for col_dx in (4.0, 8.0):
            for row_dy in (-4.0, 0.0, 4.0):
                dl.add_circle_filled(
                    imgui.ImVec2(p0.x + col_dx, mid_y + row_dy), 1.5, dot_col
                )

        # Latch drag state while grip is held
        if is_grip_active:
            self._drag_section = name
        if self._drag_section == name and imgui.is_mouse_dragging(0):
            self._drag_confirmed = True
            imgui.set_tooltip(f"\u2261  {name}")

        imgui.same_line(spacing=2)

        # ── Collapsing header ─────────────────────────────────────────────────
        imgui.set_next_item_open(True, imgui.Cond_.first_use_ever)
        expanded = imgui.collapsing_header(f"{name}##sec_{name}")

        # ── Drop target: use rect-hit-test so it works while a button is active ──
        if self._drag_section and self._drag_section != name:
            r_min = imgui.get_item_rect_min()
            r_max = imgui.get_item_rect_max()
            if imgui.is_mouse_hovering_rect(r_min, r_max):
                self._drag_hover_target = name
                dl.add_line(
                    imgui.ImVec2(r_min.x, r_min.y),
                    imgui.ImVec2(r_max.x, r_min.y),
                    imgui.IM_COL32(196, 167, 231, 220),
                    2.0,
                )

        if summary and not expanded:
            imgui.same_line(self._content_width() - imgui.calc_text_size(summary).x - 8)
            imgui.text_colored(
                imgui.ImVec4(*token_rgba("text_section_summary")), summary
            )

        return bool(expanded)

    def _section_is_active(self, name: str, live: dict) -> bool:
        checks = {
            "TMR": lambda: live.get("tmr_enabled"),
            "HTW": lambda: live.get("htw_eligible"),
            "GENUS": lambda: live.get("genus_active"),
            "Conditioning": lambda: live.get("conditioning_active"),
        }
        fn = checks.get(name)
        return bool(fn and fn())

    # ── Widget List Rendering (with inline grouping) ─────────────────────

    def _render_widget_list(self, widgets: list, live: dict) -> None:
        """Render a list of widgets, collapsing consecutive inline-flagged ones onto one row."""
        i = 0
        while i < len(widgets):
            w = widgets[i]
            group = [w]
            while (i + len(group)) < len(widgets) and widgets[i + len(group)].inline:
                group.append(widgets[i + len(group)])
            if len(group) > 1:
                self._render_inline_row(group, live)
            else:
                self._render_widget(w, live)
            i += len(group)

    def _render_inline_row(self, group: list, live: dict) -> None:
        """Render a group of Toggle/Dropdown widgets compactly on one row."""
        for j, w in enumerate(group):
            if j > 0:
                imgui.same_line(spacing=4)
            self._render_widget_compact(w, live)

    def _render_widget_compact(self, w: WidgetDef, live: dict) -> None:
        """Compact (no 2-col table) rendering for Toggle and Dropdown widgets."""
        value = live.get(w.key)
        read_only = (
            w.classification == "AGENT_TUNABLE" and not self._debug_mode
        ) or w.classification in ("TELEMETRY", "INTERNAL")
        disabled = self._is_disabled(w, live)

        if disabled:
            imgui.push_style_var(imgui.StyleVar_.alpha, 0.5)

        is_locked = w.key in self._locked_params
        lbl_col = imgui.ImVec4(
            *token_rgba("source_user_lock" if is_locked else "text_label")
        )

        wtype = w.widget
        if wtype == "Toggle":
            v = bool(value) if value is not None else False
            if read_only:
                imgui.push_style_color(
                    imgui.Col_.text, imgui.ImVec4(*token_rgba("text_muted"))
                )
                imgui.text(f"{'✓' if v else '✗'} {w.label}")
                imgui.pop_style_color()
            else:
                imgui.push_style_color(imgui.Col_.text, lbl_col)
                changed, nv = imgui.checkbox(f"{w.label}##{w.key}_inl", v)
                imgui.pop_style_color()
                if changed:
                    self._commit(w.key, nv)

        elif wtype == "Dropdown":
            enum = w.enum or []
            cur = str(value) if value is not None else (enum[0] if enum else "")
            idx = enum.index(cur) if cur in enum else 0
            imgui.push_style_color(imgui.Col_.text, lbl_col)
            imgui.text(w.label)
            imgui.pop_style_color()
            imgui.same_line(spacing=4)
            imgui.set_next_item_width(110)
            if read_only:
                imgui.text_disabled(cur)
            else:
                changed, ni = imgui.combo(f"##{w.key}_inl", idx, enum)
                if changed:
                    self._commit(w.key, enum[ni])

        if w.tooltip and imgui.is_item_hovered():
            imgui.set_tooltip(w.tooltip)
        if disabled:
            imgui.pop_style_var()

    # ── Single Widget Dispatch ───────────────────────────────────────────

    # Widget types that render as one full-width block (label on top, viz below)
    _FULL_WIDTH_TYPES = frozenset(
        {
            "Gauge+Sparkline",
            "Value+Sparkline",
            "Gate Indicator",
            "Progress Bar",
            "Text",
        }
    )

    def _render_widget(self, w: WidgetDef, live: dict) -> None:
        key = w.key
        value = live.get(key)
        dl = imgui.get_window_draw_list()
        cw = self._content_width()
        is_locked = key in self._locked_params
        classification = w.classification

        disabled = self._is_disabled(w, live)
        if disabled:
            imgui.push_style_var(imgui.StyleVar_.alpha, 0.5)

        read_only = (
            classification == "AGENT_TUNABLE" and not self._debug_mode
        ) or classification in ("TELEMETRY", "INTERNAL")

        wtype = w.widget

        if wtype in self._FULL_WIDTH_TYPES:
            # Full-width visualisations: label on its own line, then content
            pos = imgui.get_cursor_screen_pos()
            if is_locked:
                draw_lock_icon(dl, pos)
                imgui.dummy(imgui.ImVec2(14, 0))
                imgui.same_line()
            if wtype == "Gauge":
                self._w_gauge(w, value, dl, cw)
            elif wtype == "Gauge+Sparkline":
                self._w_gauge_sparkline(w, value, dl, cw)
            elif wtype == "Value+Sparkline":
                self._w_value_sparkline(w, value, dl, cw)
            elif wtype == "Gate Indicator":
                self._w_gate_indicator(w, live, dl, cw)
            elif wtype == "Progress Bar":
                self._w_progress_bar(w, value, cw)
            elif wtype == "Text":
                self._w_text(w, value)
        else:
            # Inline widgets: [label col | control col] on one row
            label_w = max(70.0, min(140.0, cw * 0.40))
            TF = (
                imgui.TableFlags_.sizing_fixed_fit
                | imgui.TableFlags_.no_borders_in_body
            )
            if imgui.begin_table(f"##wt{key}", 2, TF, imgui.ImVec2(cw, 0)):
                imgui.table_setup_column(
                    "##l", imgui.TableColumnFlags_.width_fixed, label_w
                )
                imgui.table_setup_column("##c", imgui.TableColumnFlags_.width_stretch)
                imgui.table_next_row()

                # Label column
                imgui.table_set_column_index(0)
                pos = imgui.get_cursor_screen_pos()
                if is_locked:
                    draw_lock_icon(dl, pos)
                    imgui.set_cursor_screen_pos(imgui.ImVec2(pos.x + 16, pos.y))
                lbl_color = imgui.ImVec4(
                    *token_rgba("source_user_lock" if is_locked else "text_label")
                )
                imgui.text_colored(lbl_color, w.label)

                # Control column
                imgui.table_set_column_index(1)
                imgui.set_next_item_width(-1)
                if wtype == "Slider":
                    self._w_slider(w, value, read_only)
                elif wtype == "Toggle":
                    self._w_toggle(w, value, read_only)
                elif wtype == "Dropdown":
                    self._w_dropdown(w, value, read_only)
                elif wtype == "Badge":
                    self._w_badge(w, value, dl)
                elif wtype == "Indicator":
                    self._w_indicator(w, value, read_only)
                elif wtype == "Alert Badge":
                    self._w_alert_badge(w, value, dl)
                elif wtype == "Gauge":
                    self._w_gauge(w, value, dl)
                elif wtype == "Phase Ring":
                    self._w_phase_ring(w, value, dl)
                elif wtype == "Timer":
                    self._w_timer(w, value)
                elif wtype == "Counter":
                    self._w_counter(w, value)
                elif wtype == "Value":
                    self._w_value(w, value)
                elif wtype == "ColorPicker":
                    self._w_color_picker(w, value, read_only)
                elif wtype == "Input":
                    self._w_input(w, value, read_only)

                imgui.end_table()

        if w.tooltip and imgui.is_item_hovered():
            imgui.set_tooltip(w.tooltip)

        if disabled:
            imgui.pop_style_var()

    # ── Widget Type Implementations ──────────────────────────────────────

    def _w_slider(self, w: WidgetDef, value, read_only: bool) -> None:
        rng = w.range or [0.0, 1.0]
        v = float(value) if value is not None else rng[0]
        if read_only:
            imgui.text_colored(imgui.ImVec4(*token_rgba("text_muted")), f"{v:.2f}")
            return

        changed, new_v = imgui.slider_float(f"##{w.key}", v, rng[0], rng[1], "%.2f")

        # Filled-bar overlay: draw a tinted rect over the left portion of the trough
        if changed:
            self._commit(w.key, new_v)
            v = new_v
        rmin = imgui.get_item_rect_min()
        rmax = imgui.get_item_rect_max()
        lo, hi = float(rng[0]), float(rng[1])
        frac = (v - lo) / (hi - lo) if hi != lo else 0.0
        frac = max(0.0, min(1.0, frac))
        fill_x = rmin.x + frac * (rmax.x - rmin.x)
        # Pine/foam teal at 35% alpha — subtle fill behind the handle
        dl = imgui.get_window_draw_list()
        dl.add_rect_filled(
            imgui.ImVec2(rmin.x, rmin.y + 1),
            imgui.ImVec2(fill_x, rmax.y - 1),
            imgui.IM_COL32(62, 143, 176, 70),  # Pine #3e8fb0 @ 28%
            2.0,
        )

    def _w_toggle(self, w: WidgetDef, value, read_only: bool) -> None:
        v = bool(value) if value is not None else False
        if read_only:
            imgui.text_colored(
                imgui.ImVec4(*token_rgba("text_muted")),
                "ON" if v else "OFF",
            )
        else:
            changed, new_v = imgui.checkbox(f"##{w.key}", v)
            if changed:
                self._commit(w.key, new_v)

    def _w_dropdown(self, w: WidgetDef, value, read_only: bool) -> None:
        options = w.enum or []
        current = str(value) if value is not None else (options[0] if options else "")
        idx = options.index(current) if current in options else 0
        if read_only:
            imgui.text_colored(imgui.ImVec4(*token_rgba("text_muted")), current)
        else:
            changed, new_idx = imgui.combo(f"##{w.key}", idx, options)
            if changed and 0 <= new_idx < len(options):
                self._commit(w.key, options[new_idx])

    def _w_badge(self, w: WidgetDef, value, dl) -> None:
        v = str(value) if value is not None else "—"
        pos = imgui.get_cursor_screen_pos()
        bg_hex, txt_hex = _resolve_badge_color(w.key, v)
        h = draw_badge(dl, pos, v, bg_hex, text_hex=txt_hex)
        imgui.dummy(imgui.ImVec2(0, h))

    def _w_gauge(self, w: WidgetDef, value, dl) -> None:
        v = float(value) if value is not None else 0.0
        cw = imgui.get_content_region_avail().x
        pos = imgui.get_cursor_screen_pos()
        h = draw_inline_gauge(dl, pos, v, cw)
        imgui.dummy(imgui.ImVec2(cw, h))

    def _w_gauge_sparkline(self, w: WidgetDef, value, dl, cw: float) -> None:
        v = float(value) if value is not None else 0.0
        cw = cw or self._content_width()
        imgui.text_colored(imgui.ImVec4(*token_rgba("text_label")), w.label)
        pos = imgui.get_cursor_screen_pos()
        gh = draw_inline_gauge(dl, pos, v, cw)
        imgui.dummy(imgui.ImVec2(cw, gh))
        # Compact sparkline below (15 px tall)
        sp_pos = imgui.get_cursor_screen_pos()
        buf = self._sparklines.get(w.key, deque())
        draw_sparkline(dl, sp_pos, buf, cw, 15.0)
        imgui.dummy(imgui.ImVec2(cw, 15.0))

    def _w_value_sparkline(self, w: WidgetDef, value, dl, cw: float) -> None:
        v = str(value) if value is not None else "—"
        cw = cw or self._content_width()
        imgui.text_colored(imgui.ImVec4(*token_rgba("text_label")), f"{w.label}  {v}")
        pos = imgui.get_cursor_screen_pos()
        buf = self._sparklines.get(w.key, deque())
        draw_sparkline(dl, pos, buf, cw, SPARKLINE_H)
        imgui.dummy(imgui.ImVec2(cw, SPARKLINE_H))

    def _w_indicator(self, w: WidgetDef, value, read_only: bool) -> None:
        v = str(value) if value is not None else "—"
        col = token_rgba("text_muted" if read_only else "text_value")
        imgui.text_colored(imgui.ImVec4(*col), v)

    def _w_alert_badge(self, w: WidgetDef, value, dl) -> None:
        if not value:
            return
        pos = imgui.get_cursor_screen_pos()
        h = draw_alert_badge(dl, pos, w.label)
        imgui.dummy(imgui.ImVec2(0, h))

    def _w_gate_indicator(self, w: WidgetDef, live: dict, dl, cw: float) -> None:
        gates = {
            "respiratory": live.get("gate_respiratory", False),
            "alpha": live.get("gate_alpha", False),
            "cardiac": live.get("gate_cardiac", False),
            "stillness": live.get("gate_stillness", False),
        }
        imgui.text_colored(imgui.ImVec4(*token_rgba("text_label")), w.label)
        pos = imgui.get_cursor_screen_pos()
        h = draw_gate_indicator(dl, pos, gates)
        imgui.dummy(imgui.ImVec2(0, h))

    def _w_phase_ring(self, w: WidgetDef, value, dl) -> None:
        v = float(value) if value is not None else 0.0
        pos = imgui.get_cursor_screen_pos()
        h = draw_phase_ring(dl, pos, v)
        imgui.dummy(imgui.ImVec2(24, h))

    def _w_timer(self, w: WidgetDef, value) -> None:
        secs = int(value) if value is not None else 0
        if secs >= 3600:
            txt = f"{secs // 3600}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
        else:
            txt = f"{secs // 60}:{secs % 60:02d}"
        imgui.text_colored(imgui.ImVec4(*token_rgba("text_value")), txt)

    def _w_counter(self, w: WidgetDef, value) -> None:
        imgui.text_colored(
            imgui.ImVec4(*token_rgba("text_value")),
            str(value if value is not None else 0),
        )

    def _w_progress_bar(self, w: WidgetDef, value, cw: float) -> None:
        v = float(value) if value is not None else 0.0
        imgui.text_colored(imgui.ImVec4(*token_rgba("text_label")), w.label)
        draw_progress_bar(imgui.get_cursor_screen_pos(), v, cw)

    def _w_value(self, w: WidgetDef, value) -> None:
        imgui.text_colored(
            imgui.ImVec4(*token_rgba("text_value")),
            str(value if value is not None else "—"),
        )

    def _w_text(self, w: WidgetDef, value) -> None:
        imgui.text_wrapped(str(value) if value is not None else "")

    def _w_color_picker(self, w: WidgetDef, value, read_only: bool) -> None:
        """Inline color swatch that opens a popup picker. Value is [r, g, b] 0-255."""
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            r, g, b = int(value[0]), int(value[1]), int(value[2])
        else:
            r, g, b = 255, 105, 180  # default pink

        # Show a small color swatch button; clicking opens the picker popup
        swatch_col = imgui.ImVec4(r / 255, g / 255, b / 255, 1.0)
        imgui.push_style_color(imgui.Col_.button, swatch_col)
        imgui.push_style_color(imgui.Col_.button_hovered, swatch_col)
        imgui.push_style_color(imgui.Col_.button_active, swatch_col)
        imgui.button(
            f"##{w.key}_sw", imgui.ImVec2(imgui.get_content_region_avail().x, 0)
        )
        imgui.pop_style_color(3)

        if not read_only and imgui.begin_popup_context_item(
            f"##{w.key}_ctx", imgui.PopupFlags_.mouse_button_left
        ):
            changed, new_rgb = imgui.color_picker3(
                f"##{w.key}_pick",
                (r / 255, g / 255, b / 255),
                imgui.ColorEditFlags_.no_alpha | imgui.ColorEditFlags_.picker_hue_wheel,
            )
            if changed:
                self._commit(
                    w.key,
                    [
                        int(new_rgb[0] * 255),
                        int(new_rgb[1] * 255),
                        int(new_rgb[2] * 255),
                    ],
                )
            imgui.end_popup()

    def _w_input(self, w: WidgetDef, value, read_only: bool) -> None:
        """Single-line text input field, optionally password-masked."""
        buf = str(value) if value is not None else ""
        if read_only:
            imgui.text_disabled(buf or "—")
            return
        flags = imgui.InputTextFlags_.none
        if w.password:
            flags |= imgui.InputTextFlags_.password
        imgui.set_next_item_width(-1)
        changed, new_val = imgui.input_text(f"##{w.key}_inp", buf, flags=flags)
        if changed:
            self._commit(w.key, new_val)

    # ── Authority / Lock ─────────────────────────────────────────────────

    def _commit(self, key: str, value) -> None:
        """Write a parameter with user source tag. Adds to locked set."""
        patch_live({key: value, f"{key}_source": "user"})
        self._locked_params.add(key)

    def _is_disabled(self, w: WidgetDef, live: dict) -> bool:
        """Check if widget should be rendered at 50% alpha (system-disabled)."""
        if live.get("genus_active") and w.section == "Induction":
            if any(k in w.key for k in ("alpha", "theta")):
                return True
        return False

    def _gauge_radius(self) -> float:
        if self._mode == "CUE_TEST":
            return 30.0
        if not self._debug_mode:
            return 60.0
        return 40.0

    # ── Mode Transition Animation ────────────────────────────────────────

    def _transition_alpha(self) -> float | None:
        if self._transition_t is None:
            return None
        elapsed = time.monotonic() - self._transition_t
        if elapsed >= TRANSITION_SEC:
            self._transition_t = None
            return None
        # Phase 1: 0–1.0 s → fade out (1 → 0)
        # Phase 2: 1.0–1.5 s → hold black
        # Phase 3: 1.5–2.0 s → fade in (0 → 1)
        if elapsed < 1.0:
            return max(0.0, 1.0 - elapsed)
        if elapsed < 1.5:
            return 0.0
        return min(1.0, (elapsed - 1.5) / 0.5)

    # ── Collapse Animation ───────────────────────────────────────────────

    def _animate_collapse(self, target: float) -> None:
        dt = imgui.get_io().delta_time
        speed = (PANEL_W - COLLAPSED_W) / COLLAPSE_ANIM_SEC
        if self._panel_width_cur < target:
            self._panel_width_cur = min(target, self._panel_width_cur + speed * dt)
        elif self._panel_width_cur > target:
            self._panel_width_cur = max(target, self._panel_width_cur - speed * dt)

    def _render_collapsed_tab(self) -> None:
        """40px vertical tab with 'SOMNA' stacked letters."""
        vp = imgui.get_main_viewport()
        x = vp.work_pos.x + vp.work_size.x - COLLAPSED_W
        imgui.set_next_window_pos(imgui.ImVec2(x, vp.work_pos.y))
        imgui.set_next_window_size(imgui.ImVec2(COLLAPSED_W, vp.work_size.y))
        flags = (
            imgui.WindowFlags_.no_title_bar
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_scrollbar
            | imgui.WindowFlags_.no_saved_settings
        )
        imgui.push_style_var(imgui.StyleVar_.alpha, 0.6)
        imgui.begin("##somna_tab", None, flags)
        for ch in "SOMNA":
            cw = imgui.calc_text_size(ch).x
            imgui.set_cursor_pos_x((COLLAPSED_W - cw) * 0.5)
            imgui.text_colored(imgui.ImVec4(*token_rgba("text_muted")), ch)
        imgui.end()
        imgui.pop_style_var()

    # ── Debug Layer ──────────────────────────────────────────────────────

    def _render_debug_banner(self) -> None:
        cw = self._content_width()
        dl = imgui.get_window_draw_list()
        pos = imgui.get_cursor_screen_pos()
        h = 32.0
        dl.add_rect_filled(
            pos,
            imgui.ImVec2(pos.x + cw, pos.y + h),
            token_u32("debug_banner_bg"),
            0,
        )
        warn = "\u26a0 Debug mode active \u2014 manual changes may conflict with automated systems."
        f = FONTS.get("alert_bold")
        if f:
            imgui.push_font(f, 0.0)
        dl.add_text(
            imgui.ImVec2(pos.x + 8, pos.y + 8), token_u32("debug_banner_text"), warn
        )
        if f:
            imgui.pop_font()
        imgui.dummy(imgui.ImVec2(cw, h + 4))

    def _render_debug_panels(self) -> None:
        cw = self._content_width()
        imgui.spacing()
        imgui.separator()

        if imgui.collapsing_header("Raw State JSON##dbg_json"):
            self._render_debug_json(cw)

        if imgui.collapsing_header("Director Decision Log##dbg_log"):
            self._render_debug_decision_log(cw)

        if imgui.collapsing_header("Gate Timing##dbg_gate"):
            self._render_debug_gate_timing(cw)

    def _render_debug_json(self, cw: float) -> None:
        now = time.monotonic()
        with self._live_lock:
            live = dict(self._live)
        f = FONTS.get("debug")
        if f:
            imgui.push_font(f, 0.0)
        imgui.begin_child(
            "##json_view",
            imgui.ImVec2(cw, DEBUG_JSON_H),
            child_flags=imgui.ChildFlags_.borders,
        )
        for k in sorted(live.keys()):
            v = live[k]
            flash_t = self._change_flash.get(k)
            if flash_t and (now - flash_t) < 1.0:
                alpha = 1.0 - (now - flash_t)
                dl = imgui.get_window_draw_list()
                p = imgui.get_cursor_screen_pos()
                dl.add_rect_filled(
                    p,
                    imgui.ImVec2(p.x + cw, p.y + imgui.get_text_line_height()),
                    hex_to_u32("#2a3a5c", alpha),
                )
            imgui.text_colored(imgui.ImVec4(*token_rgba("text_muted")), f"{k}:")
            imgui.same_line()
            imgui.text(str(v))
        imgui.end_child()
        if f:
            imgui.pop_font()

    def _render_debug_decision_log(self, cw: float) -> None:
        f = FONTS.get("debug")
        if f:
            imgui.push_font(f, 0.0)
        imgui.begin_child(
            "##dec_log",
            imgui.ImVec2(cw, DEBUG_LOG_H),
            child_flags=imgui.ChildFlags_.borders,
        )
        for entry in reversed(self._decision_log):
            ts = entry.get("timestamp", "")
            dec = entry.get("decision", str(entry))
            imgui.text_colored(imgui.ImVec4(*token_rgba("text_muted")), ts)
            imgui.same_line()
            imgui.text(dec)
            imgui.separator()
        imgui.end_child()
        if f:
            imgui.pop_font()

    def _render_debug_gate_timing(self, cw: float) -> None:
        """Last 30 s, 4 rows (R/A/C/S), green ticks = on, red = off."""
        dl = imgui.get_window_draw_list()
        pos = imgui.get_cursor_screen_pos()
        h = DEBUG_GATE_H
        row_h = h / 4.0
        now = time.monotonic()
        window = 30.0

        labels = ("R", "A", "C", "S")
        for row, lbl in enumerate(labels):
            ry = pos.y + row * row_h
            dl.add_text(imgui.ImVec2(pos.x, ry), token_u32("text_muted"), lbl)
            for sample in self._gate_history:
                age = now - sample["t"]
                if age > window:
                    continue
                sx = pos.x + 16 + (1.0 - age / window) * (cw - 20)
                on = sample.get(lbl, False)
                col = token_u32("success_green") if on else token_u32("alert_red")
                dl.add_line(
                    imgui.ImVec2(sx, ry + 2),
                    imgui.ImVec2(sx, ry + row_h - 2),
                    col,
                    1.0,
                )
        imgui.dummy(imgui.ImVec2(cw, h))

    # ── Utilities ────────────────────────────────────────────────────────

    def _content_width(self) -> float:
        return imgui.get_content_region_avail().x
