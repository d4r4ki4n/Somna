"""ui/session_editor_imgui.py — ImGui Session Editor Modal.

Opens over the control panel as a popup modal.  Two-panel layout:
  left  — keyframe list + transport buttons
  right — selected keyframe detail (time / label / ease / parameters)

Key feature: ⊕ Capture Live snapshots the current live_control.json state into
a new keyframe at session_time, letting users author sessions by dialling in
each phase live rather than typing values by hand.

Per Bible Ch.4 §4.1 (Session Architecture) and Bible Ch.9 §9.1 (Control Panel).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from imgui_bundle import imgui

from ui.panel_theme import token_rgba, RP, hex_to_u32

# ── Helpers ───────────────────────────────────────────────────────────────────


def _v4(name: str, a: float | None = None) -> imgui.ImVec4:
    return imgui.ImVec4(*token_rgba(name, a))


# ── Known-param typing ────────────────────────────────────────────────────────

_BOOL_PARAMS: set[str] = {
    "audio_muted",
    "center_flash_sync_to_beat",
    "tts_enabled",
    "tts_subliminal",
    "window_always_on_top",
    "window_click_through",
    "spiral_show_text",
    "beat_sync_master",
    "start_fullscreen",
}

_STR_PARAMS: dict[str, list[str]] = {
    "spiral_style": [
        "tunnel_dream",
        "galaxy",
        "archimedean",
        "kaleidoscope",
        "interference",
        "electric",
        "vortex",
        "dna",
        "fibonacci",
        "rose",
        "moire",
        "spirograph",
        "fermat",
        "superformula",
        "liminal",
        "resonant",
        "nebula",
        "bifurcate",
        "cobwebs",
        "strange_attractor",
        "flow_field",
        "sacred_geometry",
        "recursive_fractal",
        "potter_tunnel",
        "fractal_scale",
        "neuro_vortex",
    ],
    "veil_mode": ["scroll", "rain", "drift", "converge", "strobe", "tunnel", "null"],
    "bg_mode": ["slideshow", "none"],
    "beat_type": ["binaural", "isochronic", "both"],
    "font_switch_mode": ["intelligent", "rapid"],
    "spiral_color_mode": ["rainbow", "solid"],
    "noise_color": ["white", "pink", "brown", "blue", "violet", "grey", "off"],
}

_EASE_OPTIONS = ["linear", "ease_in", "ease_out", "ease_in_out", "instant"]
_CATEGORY_OPTIONS = [
    "general",
    "focus",
    "sleep",
    "entrainment",
    "genus",
    "edison",
    "ssild",
    "custom",
]

# Keys never useful as session-yaml params
_SKIP_CAPTURE: set[str] = {
    "session_time",
    "session_duration",
    "session_name",
    "session_folder",
    "timeline_label",
    "timeline_paused",
    "timeline_locked_params",
    "playlist_index",
    "playlist",
    "playlist_mode",
    "_timeline_cmd",
    "seek_time",
    "agent_message",
    "user_response",
    "response_timestamp",
    "user_console_input",
    "user_console_ts",
    "agent_console_response",
    "agent_mode",
    # legacy
    "llm_prompt",
    "llm_prompt_written_at",
    "llm_prompt_style",
    "llm_prompt_timeout_s",
    "tts_prompt",
}


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class _KF:
    t: float
    label: str = ""
    ease: str = "linear"
    params: dict[str, Any] = field(default_factory=dict)


# ── Main class ────────────────────────────────────────────────────────────────


class SessionEditorModal:
    """Stateful ImGui session editor modal.  Call open() then render() every frame."""

    def __init__(self, root: Path) -> None:
        self._root = root

        # window visibility
        self._window_open = False
        self._session_path: Optional[Path] = None

        # session data
        self._keyframes: list[_KF] = []
        self._defaults: dict[str, Any] = {}

        # metadata buffers
        self._name_buf: str = ""
        self._desc_buf: str = ""
        self._dur_buf: str = ""
        self._cat_idx: int = 0

        # keyframe edit state
        self._sel_kf: int = -1
        self._kf_t_buf: str = "0"
        self._kf_label_buf: str = ""
        self._kf_ease_idx: int = 0

        # param add
        self._add_param_buf: str = ""

        # timeline drag state
        self._drag_idx: int = -1

        # capture options
        self._capture_diff: bool = True  # only capture params that differ from defaults

        # misc
        self._dirty: bool = False
        self._status_msg: str = ""
        self._status_ts: float = 0.0

    # ── Open ─────────────────────────────────────────────────────────────────

    def open(
        self, session_path: Optional[Path], live_state: dict | None = None
    ) -> None:
        """Load the session at *session_path* (or create a blank one) and open the modal."""
        self._session_path = session_path
        self._keyframes = []
        self._defaults = {}
        self._dirty = False
        self._sel_kf = -1
        self._status_msg = ""

        if session_path and (session_path / "session.yaml").exists():
            self._load_yaml(session_path / "session.yaml")
        else:
            self._name_buf = session_path.name if session_path else "new_session"
            self._desc_buf = ""
            self._dur_buf = "1800"
            self._cat_idx = 0
            self._keyframes = [_KF(t=0, label="start", ease="linear")]

        self._window_open = True

    # ── Load / save ───────────────────────────────────────────────────────────

    def _load_yaml(self, path: Path) -> None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            self._name_buf = str(data.get("name") or path.parent.name)
            self._desc_buf = str(data.get("description") or "")
            self._dur_buf = str(data.get("duration") or 1800)
            cat = data.get("category") or "general"
            self._cat_idx = (
                _CATEGORY_OPTIONS.index(cat) if cat in _CATEGORY_OPTIONS else 0
            )
            self._defaults = dict(data.get("defaults") or {})
            for kf in data.get("timeline") or []:
                self._keyframes.append(
                    _KF(
                        t=float(kf.get("t", 0)),
                        label=str(kf.get("label") or ""),
                        ease=str(kf.get("ease") or "linear"),
                        params=dict(kf.get("params") or {}),
                    )
                )
            self._keyframes.sort(key=lambda k: k.t)
        except Exception as exc:
            self._set_status(f"Load error: {exc}", error=True)

    def _save(self) -> None:
        if not self._session_path:
            return
        try:
            self._session_path.mkdir(parents=True, exist_ok=True)
            out: dict[str, Any] = {
                "name": self._name_buf.strip() or self._session_path.name,
                "description": self._desc_buf.strip(),
                "category": _CATEGORY_OPTIONS[self._cat_idx],
                "duration": int(self._dur_buf) if self._dur_buf.isdigit() else 1800,
                "defaults": self._defaults,
                "timeline": [
                    {
                        "t": round(kf.t, 2),
                        "label": kf.label,
                        "ease": kf.ease,
                        "params": kf.params,
                    }
                    for kf in sorted(self._keyframes, key=lambda k: k.t)
                ],
            }
            yaml_text = yaml.dump(
                out,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
            (self._session_path / "session.yaml").write_text(
                yaml_text, encoding="utf-8"
            )
            self._dirty = False
            self._set_status("Saved")
        except Exception as exc:
            self._set_status(f"Save failed: {exc}", error=True)

    # ── Capture ───────────────────────────────────────────────────────────────

    def _capture(self, live: dict) -> None:
        """Snapshot current live_control.json into a new keyframe at session_time."""
        t = float(live.get("session_time") or 0.0)
        params: dict[str, Any] = {}
        for k, v in live.items():
            if k in _SKIP_CAPTURE:
                continue
            if (
                k.startswith("_")
                or k.startswith("eeg_")
                or k.startswith("ppg_")
                or k.startswith("imu_")
                or k.startswith("sleep_")
                or k.startswith("tmr_")
                or k.startswith("tts_playing")
                or k.startswith("conductor_")
            ):
                continue
            if v is None:
                continue
            if self._capture_diff and self._defaults.get(k) == v:
                continue
            params[k] = v

        kf = _KF(t=t, label="captured", ease="linear", params=params)
        self._keyframes.append(kf)
        self._keyframes.sort(key=lambda k: k.t)
        self._sel_kf = self._keyframes.index(kf)
        self._sync_kf_bufs()
        self._dirty = True
        self._set_status(f"Captured {len(params)} params @ {t:.0f}s")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg: str, error: bool = False) -> None:
        self._status_msg = ("⚠ " if error else "✓ ") + msg
        self._status_ts = time.time()

    def _sync_kf_bufs(self) -> None:
        """Populate per-keyframe text buffers from the selected keyframe."""
        if 0 <= self._sel_kf < len(self._keyframes):
            kf = self._keyframes[self._sel_kf]
            self._kf_t_buf = str(round(kf.t, 2))
            self._kf_label_buf = kf.label
            ease = kf.ease
            self._kf_ease_idx = (
                _EASE_OPTIONS.index(ease) if ease in _EASE_OPTIONS else 0
            )

    def _param_widget(self, key: str, val: Any, uid: int) -> tuple[bool, Any]:
        """Render the value input for a single param row.  Returns (changed, new_val)."""
        imgui.set_next_item_width(-30)
        if key in _BOOL_PARAMS or isinstance(val, bool):
            chg, nv = imgui.checkbox(f"##pv{uid}", bool(val))
            return chg, nv
        if key in _STR_PARAMS:
            opts = _STR_PARAMS[key]
            cur = str(val) if val is not None else opts[0]
            cur_idx = opts.index(cur) if cur in opts else 0
            chg, ni = imgui.combo(f"##pv{uid}", cur_idx, opts)
            return chg, opts[ni]
        # Numeric or free string
        raw = str(val) if val is not None else ""
        chg, new_str = imgui.input_text(f"##pv{uid}", raw)
        if chg:
            try:
                if new_str.lower() in ("true", "false"):
                    return True, new_str.lower() == "true"
                return True, float(new_str) if "." in new_str else int(new_str)
            except ValueError:
                return True, new_str
        return False, val

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self, live: dict) -> None:
        """Call every frame.  Renders the editor window when visible."""
        if not self._window_open:
            return

        centre = imgui.get_main_viewport().get_center()
        imgui.set_next_window_pos(centre, imgui.Cond_.appearing, imgui.ImVec2(0.5, 0.5))
        imgui.set_next_window_size(imgui.ImVec2(760, 560), imgui.Cond_.appearing)

        expanded, self._window_open = imgui.begin(
            "Session Editor##seded",
            self._window_open,
        )
        if expanded:
            avail_w = imgui.get_content_region_avail().x
            self._render_metadata(avail_w)
            imgui.separator()
            self._render_toolbar(live)
            imgui.spacing()
            self._render_timeline(avail_w, live)
            imgui.spacing()
            self._render_body(avail_w)
            imgui.separator()
            self._render_footer(avail_w)
        imgui.end()

    # ── Timeline canvas ───────────────────────────────────────────────────────

    def _render_timeline(self, avail_w: float, live: dict) -> None:
        TL_H = 72  # total height of timeline strip
        PAD = 44  # left/right margin before axis starts
        AXIS_Y = 46  # y offset of axis line from strip top
        R = 7  # diamond half-size

        # Colors
        C_BG = imgui.IM_COL32(42, 39, 63, 255)  # surface
        C_AXIS = imgui.IM_COL32(57, 53, 82, 255)  # overlay
        C_TICK = imgui.IM_COL32(110, 106, 134, 160)  # muted
        C_KF = imgui.IM_COL32(156, 207, 216, 220)  # foam
        C_SEL = imgui.IM_COL32(235, 111, 146, 255)  # love
        C_LABEL = imgui.IM_COL32(224, 222, 244, 200)  # text
        C_PLAY = imgui.IM_COL32(246, 193, 119, 230)  # gold
        C_END = imgui.IM_COL32(110, 106, 134, 70)  # muted dim (session end)

        imgui.begin_child(
            "##tl",
            imgui.ImVec2(avail_w, TL_H),
            child_flags=imgui.ChildFlags_.none,
            window_flags=(
                imgui.WindowFlags_.no_scroll_with_mouse
                | imgui.WindowFlags_.no_scrollbar
            ),
        )

        pos = imgui.get_cursor_screen_pos()
        w = imgui.get_content_region_avail().x
        dl = imgui.get_window_draw_list()

        # Session duration for t↔x mapping
        try:
            dur = max(1.0, float(self._dur_buf)) if self._dur_buf else 1800.0
        except ValueError:
            dur = (
                max(60.0, (self._keyframes[-1].t * 1.15 + 15))
                if self._keyframes
                else 1800.0
            )

        usable = max(1.0, w - PAD * 2)

        def t_to_x(t: float) -> float:
            return pos.x + PAD + (t / dur) * usable

        def x_to_t(x: float) -> float:
            return max(0.0, min(dur, (x - pos.x - PAD) / usable * dur))

        axis_sy = pos.y + AXIS_Y

        # Background fill
        dl.add_rect_filled(pos, imgui.ImVec2(pos.x + w, pos.y + TL_H), C_BG)

        # Axis line
        dl.add_line(
            imgui.ImVec2(pos.x + PAD, axis_sy),
            imgui.ImVec2(pos.x + w - PAD, axis_sy),
            C_AXIS,
            2.0,
        )

        # Tick marks — aim for ~8 ticks regardless of duration
        _TICKS = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600)
        tick_s = next((ti for ti in _TICKS if dur / ti <= 10), 3600)

        t = 0.0
        while t <= dur + 0.01:
            tx = t_to_x(t)
            dl.add_line(
                imgui.ImVec2(tx, axis_sy - 4),
                imgui.ImVec2(tx, axis_sy + 4),
                C_TICK,
                1.0,
            )
            m, s = divmod(int(round(t)), 60)
            lbl = f"{m}:{s:02d}" if m else f"{int(round(t))}s"
            lw = imgui.calc_text_size(lbl).x
            dl.add_text(imgui.ImVec2(tx - lw * 0.5, axis_sy + 7), C_TICK, lbl)
            t += tick_s

        # Session end marker
        xe = t_to_x(dur)
        dl.add_line(
            imgui.ImVec2(xe, axis_sy - 8), imgui.ImVec2(xe, axis_sy + 8), C_END, 2.0
        )

        # Playhead (gold triangle + vertical line)
        ph_t = float(live.get("session_time") or 0.0)
        ph_x = t_to_x(ph_t)
        dl.add_line(
            imgui.ImVec2(ph_x, pos.y + 4), imgui.ImVec2(ph_x, axis_sy - 1), C_PLAY, 2.0
        )
        dl.add_triangle_filled(
            imgui.ImVec2(ph_x - 5, pos.y + 4),
            imgui.ImVec2(ph_x + 5, pos.y + 4),
            imgui.ImVec2(ph_x, pos.y + 12),
            C_PLAY,
        )

        # ── Mouse interaction ─────────────────────────────────────────────────
        hovered = imgui.is_window_hovered()
        mouse = imgui.get_mouse_pos()

        if hovered and imgui.is_mouse_clicked(imgui.MouseButton_.left):
            # Diamond hit test using L1 distance (natural for rotated square)
            best_i, best_d = -1, R * 2.8
            for i, kf in enumerate(self._keyframes):
                d = abs(mouse.x - t_to_x(kf.t)) + abs(mouse.y - axis_sy)
                if d < best_d:
                    best_i, best_d = i, d
            if best_i >= 0:
                self._sel_kf = best_i
                self._drag_idx = best_i
                self._sync_kf_bufs()

        if self._drag_idx >= 0:
            if imgui.is_mouse_down(imgui.MouseButton_.left):
                new_t = round(x_to_t(mouse.x), 1)
                self._keyframes[self._drag_idx].t = new_t
                self._kf_t_buf = str(new_t)
                self._dirty = True
            else:
                # Drag released — re-sort and locate the dragged keyframe
                dragged = self._keyframes[self._drag_idx]
                self._keyframes.sort(key=lambda k: k.t)
                self._sel_kf = self._keyframes.index(dragged)
                self._drag_idx = -1
                self._sync_kf_bufs()

        # ── Draw keyframe diamonds ────────────────────────────────────────────
        for i, kf in enumerate(self._keyframes):
            kx = t_to_x(kf.t)
            sel = i == self._sel_kf
            col = C_SEL if sel else C_KF

            dl.add_quad_filled(
                imgui.ImVec2(kx, axis_sy - R),
                imgui.ImVec2(kx + R, axis_sy),
                imgui.ImVec2(kx, axis_sy + R),
                imgui.ImVec2(kx - R, axis_sy),
                col,
            )
            if sel:
                # White outline on selected diamond
                pts = [
                    (kx, axis_sy - R),
                    (kx + R, axis_sy),
                    (kx, axis_sy + R),
                    (kx - R, axis_sy),
                ]
                for j in range(4):
                    x0, y0 = pts[j]
                    x1, y1 = pts[(j + 1) % 4]
                    dl.add_line(
                        imgui.ImVec2(x0, y0),
                        imgui.ImVec2(x1, y1),
                        imgui.IM_COL32(255, 255, 255, 160),
                        1.5,
                    )

            # Label above diamond
            lbl = kf.label or f"{kf.t:.0f}s"
            lw = imgui.calc_text_size(lbl).x
            c_lbl = C_SEL if sel else (C_LABEL if kf.label else C_TICK)
            dl.add_text(imgui.ImVec2(kx - lw * 0.5, axis_sy - R - 15), c_lbl, lbl)

        imgui.end_child()

    # ── Metadata row ──────────────────────────────────────────────────────────

    def _render_metadata(self, avail_w: float) -> None:
        dirty = False

        imgui.text_disabled("Name")
        imgui.same_line(spacing=4)
        imgui.set_next_item_width(200)
        chg, self._name_buf = imgui.input_text("##sname", self._name_buf)
        dirty |= chg

        imgui.same_line(spacing=12)
        imgui.text_disabled("Cat")
        imgui.same_line(spacing=4)
        imgui.set_next_item_width(130)
        chg, self._cat_idx = imgui.combo("##scat", self._cat_idx, _CATEGORY_OPTIONS)
        dirty |= chg

        imgui.same_line(spacing=12)
        imgui.text_disabled("Duration")
        imgui.same_line(spacing=4)
        imgui.set_next_item_width(70)
        chg, self._dur_buf = imgui.input_text("s##sdur", self._dur_buf)
        dirty |= chg

        imgui.set_next_item_width(avail_w)
        chg, self._desc_buf = imgui.input_text("##sdesc", self._desc_buf)
        dirty |= chg

        if dirty:
            self._dirty = True

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _render_toolbar(self, live: dict) -> None:
        if imgui.button("+ Keyframe"):
            t = (self._keyframes[-1].t + 60) if self._keyframes else 0.0
            self._keyframes.append(_KF(t=t, label="", ease="linear"))
            self._sel_kf = len(self._keyframes) - 1
            self._sync_kf_bufs()
            self._dirty = True
        imgui.same_line(spacing=4)

        imgui.begin_disabled(self._sel_kf < 0)
        if imgui.button("Delete##kfdel"):
            if 0 <= self._sel_kf < len(self._keyframes):
                self._keyframes.pop(self._sel_kf)
                self._sel_kf = min(self._sel_kf, len(self._keyframes) - 1)
                self._sync_kf_bufs()
                self._dirty = True
        imgui.end_disabled()

        imgui.same_line(spacing=16)

        # Prominent Capture button in pine color
        imgui.push_style_color(imgui.Col_.button, _v4("source_agent", 0.35))
        imgui.push_style_color(imgui.Col_.button_hovered, _v4("source_agent", 0.55))
        imgui.push_style_color(imgui.Col_.button_active, _v4("source_agent", 0.75))
        if imgui.button("⊕  Capture Live"):
            self._capture(live)
        imgui.pop_style_color(3)

        if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
            imgui.set_tooltip(
                "Snapshot the current control panel state into a new keyframe\n"
                "positioned at the current session time.\n\n"
                "Workflow: run the 'live' freeform session, dial in each phase\n"
                "via the sliders, then Capture it here — no manual typing needed."
            )

        imgui.same_line(spacing=8)
        _, self._capture_diff = imgui.checkbox("Diff only##capd", self._capture_diff)
        if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
            imgui.set_tooltip("Only capture params that differ from session defaults.")

    # ── Two-column body ───────────────────────────────────────────────────────

    def _render_body(self, avail_w: float) -> None:
        left_w = 220.0
        right_w = avail_w - left_w - imgui.get_style().item_spacing.x
        body_h = 320.0

        # Left: keyframe list
        imgui.begin_child(
            "##kflist",
            imgui.ImVec2(left_w, body_h),
            child_flags=imgui.ChildFlags_.borders,
        )
        for i, kf in enumerate(self._keyframes):
            t_str = f"{kf.t:.0f}s"
            lbl = kf.label or "—"
            n_str = f"  ·{len(kf.params)}" if kf.params else ""
            display = f"{lbl}  {t_str}{n_str}"
            sel, _ = imgui.selectable(
                f"{display}##kf{i}",
                self._sel_kf == i,
                imgui.SelectableFlags_.none,
                imgui.ImVec2(0, 0),
            )
            if sel and self._sel_kf != i:
                self._sel_kf = i
                self._sync_kf_bufs()
        imgui.end_child()

        imgui.same_line()

        # Right: keyframe detail
        imgui.begin_child(
            "##kfdetail",
            imgui.ImVec2(right_w, body_h),
            child_flags=imgui.ChildFlags_.borders,
        )
        if 0 <= self._sel_kf < len(self._keyframes):
            self._render_kf_detail(right_w)
        else:
            imgui.text_disabled("Select a keyframe to edit")
        imgui.end_child()

    def _render_kf_detail(self, panel_w: float) -> None:
        kf = self._keyframes[self._sel_kf]
        dirty = False

        # Time + label + ease row
        imgui.text_disabled("t (s)")
        imgui.same_line(spacing=4)
        imgui.set_next_item_width(70)
        chg, self._kf_t_buf = imgui.input_text("##kft", self._kf_t_buf)
        if chg:
            try:
                kf.t = float(self._kf_t_buf)
                self._keyframes.sort(key=lambda k: k.t)
                self._sel_kf = self._keyframes.index(kf)
                dirty = True
            except ValueError:
                pass

        imgui.same_line(spacing=10)
        imgui.text_disabled("Label")
        imgui.same_line(spacing=4)
        imgui.set_next_item_width(140)
        chg, self._kf_label_buf = imgui.input_text("##kflbl", self._kf_label_buf)
        if chg:
            kf.label = self._kf_label_buf
            dirty = True

        imgui.same_line(spacing=10)
        imgui.text_disabled("Ease")
        imgui.same_line(spacing=4)
        imgui.set_next_item_width(110)
        chg, self._kf_ease_idx = imgui.combo(
            "##kfease", self._kf_ease_idx, _EASE_OPTIONS
        )
        if chg:
            kf.ease = _EASE_OPTIONS[self._kf_ease_idx]
            dirty = True

        imgui.separator()

        # Parameter table header
        n_params = len(kf.params)
        imgui.text_disabled(f"Parameters  ({n_params})")

        # Param rows — collect deletions to avoid mutating during iteration
        to_delete: list[str] = []
        uid = self._sel_kf * 10000
        param_items = list(kf.params.items())
        for pkey, pval in param_items:
            imgui.push_style_color(imgui.Col_.text, _v4("text_value"))
            imgui.text(pkey)
            imgui.pop_style_color()
            imgui.same_line(spacing=8)
            chg, new_val = self._param_widget(pkey, pval, uid)
            if chg:
                kf.params[pkey] = new_val
                dirty = True
            uid += 1
            imgui.same_line(spacing=4)
            imgui.push_style_color(imgui.Col_.text, _v4("alert_red", 0.7))
            if imgui.small_button(f"✕##pdel{uid}"):
                to_delete.append(pkey)
                dirty = True
            imgui.pop_style_color()

        for k in to_delete:
            del kf.params[k]

        imgui.separator()

        # Add parameter
        imgui.set_next_item_width(panel_w - 90)
        _, self._add_param_buf = imgui.input_text("##addpkey", self._add_param_buf)
        imgui.same_line(spacing=4)
        if imgui.small_button("Add param"):
            pname = self._add_param_buf.strip()
            if pname and pname not in kf.params:
                kf.params[pname] = 0
                self._add_param_buf = ""
                dirty = True

        if dirty:
            self._dirty = True

    # ── Footer ────────────────────────────────────────────────────────────────

    def _render_footer(self, avail_w: float) -> None:
        # Status message with timeout
        if self._status_msg and time.time() - self._status_ts < 5.0:
            is_err = self._status_msg.startswith("⚠")
            color = _v4("alert_red") if is_err else _v4("success_green")
            imgui.push_style_color(imgui.Col_.text, color)
            imgui.text(self._status_msg)
            imgui.pop_style_color()
        else:
            if self._dirty:
                imgui.push_style_color(imgui.Col_.text, _v4("warning_amber", 0.8))
                imgui.text("Unsaved changes")
                imgui.pop_style_color()
            else:
                imgui.text_disabled(
                    str(self._session_path) if self._session_path else "new session"
                )

        # Right-align Save + Close by measuring button widths and using set_cursor_pos_x
        style = imgui.get_style()
        fp = style.frame_padding.x
        sp = style.item_spacing.x
        save_w = imgui.calc_text_size("Save").x + fp * 2
        close_w = imgui.calc_text_size("Close").x + fp * 2
        total_w = save_w + close_w + sp
        imgui.same_line()
        imgui.set_cursor_pos_x(max(imgui.get_cursor_pos_x() + 8, avail_w - total_w))

        imgui.push_style_color(imgui.Col_.button, _v4("source_agent", 0.4))
        imgui.push_style_color(imgui.Col_.button_hovered, _v4("source_agent", 0.6))
        imgui.push_style_color(imgui.Col_.button_active, _v4("source_agent", 0.8))
        if imgui.button("Save##sedsave"):
            self._save()
        imgui.pop_style_color(3)

        imgui.same_line(spacing=sp)
        if imgui.button("Close##sedclose"):
            self._window_open = False
