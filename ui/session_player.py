"""
Somna Session Player

Full-featured session browser matching the legacy Tkinter SESSION panel:
  - Category + sort filters (dropdown row)
  - Scrollable session list with Name / Dur / Category columns
  - Queue row
  - + New / ≡ Edit buttons
  - Three-button transport: Start Agent | ▶ Start Session | ▶ Start Beats

Wire callbacks after instantiation:
    player.on_start_session   = lambda entry: ...
    player.on_stop_session    = lambda: ...
    player.on_start_agent     = lambda: ...
    player.on_toggle_beats    = lambda: ...      # start/stop audio
    player.on_new_session     = lambda: ...
    player.on_edit_session    = lambda entry: ...
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

from imgui_bundle import imgui


class SessionState(Enum):
    IDLE = auto()
    RUNNING = auto()
    STOPPING = auto()


@dataclass
class SessionEntry:
    name: str
    duration: str  # e.g. "35m"
    category: str  # e.g. "General", "Sleep", "GENUS"
    description: str = ""
    file_path: str = ""

    @property
    def detail(self) -> str:
        parts = []
        if self.duration:
            parts.append(self.duration)
        if self.category and self.category != "General":
            parts.append(self.category)
        return "  ·  ".join(parts) if parts else ""


# ── Rosé Pine Moon palette ────────────────────────────────────────────────────
def _v4(r: int, g: int, b: int, a: float = 1.0) -> imgui.ImVec4:
    return imgui.ImVec4(r / 255, g / 255, b / 255, a)


_BASE = _v4(35, 33, 54, 0.97)  # #232136
_SURFACE = _v4(42, 39, 63, 0.97)  # #2a273f
_OVERLAY = _v4(57, 53, 82, 0.97)  # #393552
_HL_LOW = _v4(42, 40, 62, 1.0)  # #2a283e
_HL_MED = _v4(68, 65, 90, 1.0)  # #44415a
_HL_HIGH = _v4(86, 82, 110, 1.0)  # #56526e
_TEXT = _v4(224, 222, 244, 1.0)  # #e0def4
_SUBTLE = _v4(144, 140, 170, 1.0)  # #908caa
_MUTED = _v4(110, 106, 134, 1.0)  # #6e6a86
_LOVE = _v4(235, 111, 146, 1.0)  # #eb6f92
_LOVE_DIM = _v4(235, 111, 146, 0.35)
_LOVE_HOV = _v4(235, 111, 146, 0.70)
_PINE = _v4(62, 143, 176, 1.0)  # #3e8fb0
_PINE_DIM = _v4(62, 143, 176, 0.40)
_PINE_HOV = _v4(62, 143, 176, 0.75)
_FOAM = _v4(156, 207, 216, 1.0)  # #9ccfd8
_IRIS = _v4(196, 167, 231, 1.0)  # #c4a7e7
_IRIS_DIM = _v4(196, 167, 231, 0.30)
_GOLD = _v4(246, 193, 119, 1.0)  # #f6c177

_ROW_H = 20  # px per session row
# Horizontal gap between buttons in action / transport rows (full width = sum(btn) + gaps)
_BTN_GAP = 4


class SessionPlayer:
    def __init__(self):
        self._sessions: list[SessionEntry] = []
        self._selected: int = -1
        self._playing: int = -1
        self._state = SessionState.IDLE
        self._search: str = ""
        self._filter_cat: str = "All"
        self._sort_mode: str = "Name"
        self._beats_on: bool = False
        self._queue: list[SessionEntry] = []
        self.agent_running: bool = False
        self._seek_value: float = 0.0
        self._seeking: bool = False
        self._seek_live: Optional[Callable[[], dict]] = None

        self._footer_h_cache: float = 0.0  # measured last frame; 0 = first frame

        self.on_start_session: Optional[Callable[[SessionEntry], None]] = None
        self.on_stop_session: Optional[Callable[[], None]] = None
        self.on_start_agent: Optional[Callable[[], None]] = None
        self.on_toggle_beats: Optional[Callable[[], None]] = None
        self.on_new_session: Optional[Callable[[], None]] = None
        self.on_edit_session: Optional[Callable[[Optional[SessionEntry]], None]] = None
        self.on_queue_change: Optional[Callable[[list[str]], None]] = None
        self.on_timeline_cmd: Optional[Callable[[str], None]] = None
        self.on_seek: Optional[Callable[[float], None]] = None

    def _notify_queue_change(self) -> None:
        if self.on_queue_change:
            self.on_queue_change([s.name for s in self._queue])

    # ── Public API ─────────────────────────────────────────────────────────────

    def load_sessions(self, sessions: list[SessionEntry]) -> None:
        self._sessions = sessions
        if sessions and self._selected < 0:
            self._selected = 0

    def mark_playing(self, name: str) -> None:
        for i, s in enumerate(self._sessions):
            if s.name == name:
                self._playing = i
                self._state = SessionState.RUNNING
                return

    @property
    def selected(self) -> Optional[SessionEntry]:
        return (
            self._sessions[self._selected]
            if 0 <= self._selected < len(self._sessions)
            else None
        )

    @property
    def playing(self) -> Optional[SessionEntry]:
        return (
            self._sessions[self._playing]
            if 0 <= self._playing < len(self._sessions)
            else None
        )

    @property
    def state(self) -> SessionState:
        return self._state

    @state.setter
    def state(self, v: SessionState) -> None:
        self._state = v

    def set_live_fn(self, fn: Callable[[], dict]) -> None:
        self._seek_live = fn

    # ── Rendering — called by sidebar fn each frame ───────────────────────────

    def render(self, width: float = -1, height: float = -1) -> None:
        w = imgui.get_content_region_avail().x
        avail_h = imgui.get_content_region_avail().y

        imgui.begin_child(
            "##session_panel",
            imgui.ImVec2(w, avail_h),
            child_flags=imgui.ChildFlags_.none,
        )
        w = imgui.get_content_region_avail().x

        self._draw_header(w)
        self._draw_filter_sort(w)
        self._draw_col_headers(w)

        header_end_y = imgui.get_cursor_pos().y

        desc_h = self._calc_description_height(w)
        actions_h = 22.0 + 8.0
        transport_h = 28.0 + 8.0
        seek_h = 0.0
        if self._state == SessionState.RUNNING:
            seek_h = 65.0
        queue_h = 0.0
        if self._queue:
            queue_h = 22.0 + len(self._queue) * 20.0 + 16.0

        max_desc_share = max(0.0, (avail_h - header_end_y) * 0.35)
        if desc_h > max_desc_share:
            desc_h = max_desc_share

        remaining = max(
            0.0,
            avail_h
            - header_end_y
            - desc_h
            - actions_h
            - transport_h
            - seek_h
            - queue_h,
        )
        playlist_h = max(20.0, remaining)

        self._draw_playlist_h(w, playlist_h)
        self._draw_description(w, max_h=desc_h)
        self._draw_actions(w)
        self._draw_transport(w)
        self._draw_seek_bar(w)

        if self._queue:
            imgui.spacing()
            imgui.separator()
            imgui.spacing()
            self._draw_queue(w)

        imgui.end_child()

    # ── Header ─────────────────────────────────────────────────────────────────

    def _draw_header(self, w: float) -> None:
        h = 34
        dl = imgui.get_window_draw_list()
        p = imgui.get_cursor_screen_pos()
        dl.add_rect_filled(
            p, imgui.ImVec2(p.x + w, p.y + h), imgui.IM_COL32(35, 33, 54, 255), 3.0
        )

        if self._state == SessionState.RUNNING and self.playing:
            foam = imgui.color_convert_float4_to_u32(_FOAM)
            text = imgui.color_convert_float4_to_u32(_TEXT)
            sub = imgui.color_convert_float4_to_u32(_SUBTLE)
            dl.add_text(imgui.ImVec2(p.x + 8, p.y + 4), foam, "\u25b6 NOW PLAYING")
            name_str = self.playing.name
            dl.add_text(imgui.ImVec2(p.x + 8, p.y + 19), text, name_str)
            dur_str = self.playing.duration
            if dur_str:
                dl.add_text(
                    imgui.ImVec2(
                        p.x + w - imgui.calc_text_size(dur_str).x - 8, p.y + 19
                    ),
                    sub,
                    dur_str,
                )
        else:
            sub = imgui.color_convert_float4_to_u32(_SUBTLE)
            n = len(self._sessions)
            lbl = f"SESSION  ·  {n}" if n else "SESSION"
            dl.add_text(imgui.ImVec2(p.x + 8, p.y + 10), sub, lbl)

        imgui.dummy(imgui.ImVec2(w, h))
        imgui.spacing()

    # ── Filter / Sort row ──────────────────────────────────────────────────────

    def _draw_filter_sort(self, w: float) -> None:
        half = (w - 12) / 2

        imgui.push_style_color(imgui.Col_.frame_bg, _OVERLAY)
        imgui.push_style_color(imgui.Col_.popup_bg, _SURFACE)
        imgui.push_style_color(imgui.Col_.text, _SUBTLE)

        imgui.set_next_item_width(half)
        cats = ["All"] + self._unique_categories()
        cat_idx = cats.index(self._filter_cat) if self._filter_cat in cats else 0
        ch, new_idx = imgui.combo("##filt_cat", cat_idx, cats)
        if ch and 0 <= new_idx < len(cats):
            self._filter_cat = cats[new_idx]

        imgui.same_line(spacing=6)
        sort_opts = ["Name", "Duration", "Recent"]
        sort_idx = (
            sort_opts.index(self._sort_mode) if self._sort_mode in sort_opts else 0
        )
        imgui.set_next_item_width(half)
        ch2, new_si = imgui.combo("##sort_mode", sort_idx, sort_opts)
        if ch2 and 0 <= new_si < len(sort_opts):
            self._sort_mode = sort_opts[new_si]

        imgui.pop_style_color(3)
        imgui.spacing()

    # ── Column headers ─────────────────────────────────────────────────────────

    def _draw_col_headers(self, w: float) -> None:
        dl = imgui.get_window_draw_list()
        p = imgui.get_cursor_screen_pos()
        h = 16
        sub = imgui.color_convert_float4_to_u32(_MUTED)
        dl.add_text(imgui.ImVec2(p.x + 6, p.y), sub, "Name")
        dl.add_text(
            imgui.ImVec2(p.x + w - imgui.calc_text_size("Dur").x - 90, p.y), sub, "Dur"
        )
        dl.add_text(
            imgui.ImVec2(p.x + w - imgui.calc_text_size("Category").x - 6, p.y),
            sub,
            "Category",
        )
        imgui.dummy(imgui.ImVec2(w, h))

    # ── Session list ───────────────────────────────────────────────────────────

    def _draw_playlist_h(self, w: float, h: float) -> None:
        filtered = self._filtered_sorted()

        imgui.push_style_color(imgui.Col_.child_bg, _SURFACE)
        imgui.begin_child("##playlist", imgui.ImVec2(w, h))
        dl = imgui.get_window_draw_list()
        sub_u32 = imgui.color_convert_float4_to_u32(_MUTED)

        for orig_i, s in filtered:
            is_sel = orig_i == self._selected
            is_play = orig_i == self._playing and self._state == SessionState.RUNNING

            bg = _HL_HIGH if (is_play or is_sel) else imgui.ImVec4(0, 0, 0, 0)
            imgui.push_style_color(imgui.Col_.header, bg)
            imgui.push_style_color(imgui.Col_.header_hovered, _HL_MED)

            clicked = imgui.selectable(
                f"##s{orig_i}",
                is_sel,
                imgui.SelectableFlags_.none,
                imgui.ImVec2(w - 4, _ROW_H),
            )
            if isinstance(clicked, tuple):
                clicked = clicked[0]
            if clicked:
                self._selected = orig_i
            if imgui.is_item_hovered() and imgui.is_mouse_double_clicked(0):
                self._start(orig_i)
            if imgui.is_item_hovered() and imgui.is_mouse_clicked(1):
                imgui.open_popup(f"##ctx_{orig_i}")

            rmin = imgui.get_item_rect_min()
            rmax = imgui.get_item_rect_max()
            ty = rmin.y + (_ROW_H - imgui.get_text_line_height()) * 0.5

            name_col = _FOAM if is_play else (_LOVE if is_sel else _TEXT)
            name_u32 = imgui.color_convert_float4_to_u32(name_col)

            # Category column (right, fixed ~80px)
            cat_str = s.category or ""
            cat_w = imgui.calc_text_size(cat_str).x
            cat_x = rmax.x - cat_w - 6
            if cat_str:
                dl.add_text(imgui.ImVec2(cat_x, ty), sub_u32, cat_str)

            # Duration column (~40px before category)
            dur_str = s.duration or ""
            dur_w = imgui.calc_text_size(dur_str).x
            dur_x = cat_x - dur_w - 14
            if dur_str:
                dl.add_text(imgui.ImVec2(dur_x, ty), sub_u32, dur_str)

            # Name column — clip to remaining space
            prefix = "\u25b6 " if is_play else "  "
            name = prefix + s.name
            name_maxw = dur_x - rmin.x - 10
            if name_maxw > 0:
                nw = imgui.calc_text_size(name).x
                if nw <= name_maxw:
                    dl.add_text(imgui.ImVec2(rmin.x + 4, ty), name_u32, name)
                else:
                    ew = imgui.calc_text_size("…").x
                    while name and imgui.calc_text_size(name).x > name_maxw - ew:
                        name = name[:-1]
                    dl.add_text(imgui.ImVec2(rmin.x + 4, ty), name_u32, name + "…")

            # Right-click context menu
            if imgui.begin_popup(f"##ctx_{orig_i}"):
                if imgui.menu_item_simple("\u25b6  Start Session"):
                    self._start(orig_i)
                if imgui.menu_item_simple("\u2295  Add to Queue"):
                    if s not in self._queue:
                        self._queue.append(s)
                        self._notify_queue_change()
                if imgui.menu_item_simple("\u270e  Edit"):
                    if self.on_edit_session:
                        self.on_edit_session(s)
                imgui.end_popup()

            imgui.pop_style_color(2)

        imgui.end_child()
        imgui.pop_style_color()
        imgui.spacing()

    # ── Description ────────────────────────────────────────────────────────────

    def _calc_description_height(self, w: float) -> float:
        desc = ""
        if self.selected:
            desc = self.selected.description or self.selected.detail
        if not desc:
            return 0.0
        pad = 10.0
        text_sz = imgui.calc_text_size(desc, wrap_width=w - pad * 2)
        return text_sz.y + pad * 2

    def _draw_description(self, w: float, max_h: float = 0.0) -> None:
        desc = ""
        if self.selected:
            desc = self.selected.description or self.selected.detail
        if not desc:
            return

        pad = 10.0
        text_sz = imgui.calc_text_size(desc, wrap_width=w - pad * 2)
        box_h = text_sz.y + pad * 2
        if max_h > 0.0 and box_h > max_h:
            box_h = max_h

        imgui.push_style_color(imgui.Col_.child_bg, _HL_LOW)
        imgui.push_style_color(imgui.Col_.text, _SUBTLE)
        flags = (
            imgui.WindowFlags_.none
            if box_h >= text_sz.y + pad * 2
            else imgui.WindowFlags_.none
        )
        imgui.begin_child(
            "##sess_desc",
            imgui.ImVec2(w, box_h),
            child_flags=imgui.ChildFlags_.none,
            window_flags=flags,
        )
        imgui.set_cursor_pos(imgui.ImVec2(pad, pad))
        imgui.push_text_wrap_pos(w - pad)
        imgui.text_wrapped(desc)
        imgui.pop_text_wrap_pos()
        imgui.end_child()
        imgui.pop_style_color(2)
        imgui.spacing()

    # ── Queue ──────────────────────────────────────────────────────────────────

    def _draw_queue(self, w: float) -> None:
        dl = imgui.get_window_draw_list()
        sub_u32 = imgui.color_convert_float4_to_u32(_MUTED)
        txt_u32 = imgui.color_convert_float4_to_u32(_SUBTLE)

        # Header row
        p = imgui.get_cursor_screen_pos()
        dl.add_rect_filled(
            p, imgui.ImVec2(p.x + w, p.y + 22), imgui.IM_COL32(35, 33, 54, 220), 3.0
        )
        dl.add_text(
            imgui.ImVec2(p.x + 6, p.y + 4),
            sub_u32,
            f"\u2631  Queue  \u2014  {len(self._queue)} session{'s' if len(self._queue) != 1 else ''}",
        )

        clr_w = imgui.calc_text_size("clear").x + 10
        imgui.dummy(imgui.ImVec2(w - clr_w - 6, 22))
        imgui.same_line()
        imgui.push_style_color(imgui.Col_.button, _HL_LOW)
        imgui.push_style_color(imgui.Col_.button_hovered, _HL_MED)
        imgui.push_style_color(imgui.Col_.text, _MUTED)
        if imgui.small_button("clear##q"):
            self._queue.clear()
            self._notify_queue_change()
        imgui.pop_style_color(3)
        imgui.spacing()

        # Queue rows — each one plays on double-click, removes on right-click
        to_remove = -1
        for qi, qs in enumerate(self._queue):
            is_next = qi == 0
            bg = imgui.color_convert_float4_to_u32(
                _HL_LOW if is_next else imgui.ImVec4(0, 0, 0, 0)
            )
            imgui.push_style_color(imgui.Col_.header, _HL_LOW)
            imgui.push_style_color(imgui.Col_.header_hovered, _HL_MED)
            clicked = imgui.selectable(
                f"##q{qi}",
                is_next,
                imgui.SelectableFlags_.none,
                imgui.ImVec2(w - 4, _ROW_H),
            )
            if isinstance(clicked, tuple):
                clicked = clicked[0]
            rmin = imgui.get_item_rect_min()
            rmax = imgui.get_item_rect_max()
            ty = rmin.y + (_ROW_H - imgui.get_text_line_height()) * 0.5

            # Remove button far right — left-click on × to remove
            rm_lbl = "\u00d7"
            rm_w = imgui.calc_text_size(rm_lbl).x + 8
            rm_x = rmax.x - rm_w - 2
            dl.add_text(imgui.ImVec2(rm_x + 2, ty), sub_u32, rm_lbl)
            rm_min = imgui.ImVec2(rm_x, rmin.y)
            rm_max = imgui.ImVec2(rm_x + rm_w, rmax.y)
            if imgui.is_mouse_hovering_rect(rm_min, rm_max) and imgui.is_mouse_clicked(
                0
            ):
                to_remove = qi

            # Name + detail
            name_col = imgui.color_convert_float4_to_u32(_FOAM if is_next else _SUBTLE)
            prefix = "\u25b6 " if is_next else f"{qi + 1}. "
            row_txt = prefix + qs.name
            if qs.duration:
                row_txt += f"  {qs.duration}"
            available_w = rm_x - rmin.x - 8
            nw = imgui.calc_text_size(row_txt).x
            if nw > available_w:
                while (
                    row_txt
                    and imgui.calc_text_size(row_txt).x
                    > available_w - imgui.calc_text_size("…").x
                ):
                    row_txt = row_txt[:-1]
                row_txt += "…"
            dl.add_text(imgui.ImVec2(rmin.x + 4, ty), name_col, row_txt)

            if clicked and imgui.is_mouse_double_clicked(0):
                idx = next(
                    (i for i, s in enumerate(self._sessions) if s.name == qs.name), -1
                )
                if idx >= 0:
                    self._start(idx)
                    self._queue.pop(qi)
                    self._notify_queue_change()

            imgui.pop_style_color(2)

        if to_remove >= 0:
            self._queue.pop(to_remove)
            self._notify_queue_change()
        imgui.spacing()

    # ── + New / ≡ Edit ─────────────────────────────────────────────────────────

    def _draw_actions(self, w: float) -> None:
        bw = (w - _BTN_GAP) / 2
        imgui.push_style_color(imgui.Col_.button, _HL_MED)
        imgui.push_style_color(imgui.Col_.button_hovered, _HL_HIGH)
        imgui.push_style_color(imgui.Col_.text, _SUBTLE)

        if imgui.button("\u2295 New##new_sess", imgui.ImVec2(bw, 22)):
            if self.on_new_session:
                self.on_new_session()
        imgui.same_line(spacing=_BTN_GAP)
        if imgui.button("\u2261 Edit##edit_sess", imgui.ImVec2(bw, 22)):
            if self.on_edit_session:
                self.on_edit_session(self.selected)

        imgui.pop_style_color(3)
        imgui.spacing()

    # ── Transport ──────────────────────────────────────────────────────────────

    def _draw_transport(self, w: float) -> None:
        bw = (w - 2 * _BTN_GAP) / 3
        btn_h = 28

        # ◈ Agent — color shifts to love/active when running
        if self.agent_running:
            imgui.push_style_color(imgui.Col_.button, _v4(235, 111, 146, 0.55))
            imgui.push_style_color(imgui.Col_.button_hovered, _v4(235, 111, 146, 0.75))
            imgui.push_style_color(imgui.Col_.text, _v4(235, 111, 146))
            agent_lbl = "\u25c8 Agent \u25cf##sa"  # filled dot = running indicator
        else:
            imgui.push_style_color(imgui.Col_.button, _IRIS_DIM)
            imgui.push_style_color(imgui.Col_.button_hovered, _HL_MED)
            imgui.push_style_color(imgui.Col_.text, _IRIS)
            agent_lbl = "\u25c8 Agent##sa"
        if imgui.button(agent_lbl, imgui.ImVec2(bw, btn_h)):
            if self.on_start_agent:
                self.on_start_agent()
        imgui.pop_style_color(3)
        imgui.same_line(spacing=_BTN_GAP)

        # ▶ Start / ■ Stop Session
        if self._state == SessionState.RUNNING:
            imgui.push_style_color(imgui.Col_.button, _LOVE_DIM)
            imgui.push_style_color(imgui.Col_.button_hovered, _LOVE_HOV)
            imgui.push_style_color(imgui.Col_.text, _LOVE)
            if imgui.button("\u25a0 Stop##ss", imgui.ImVec2(bw, btn_h)):
                self._stop()
            imgui.pop_style_color(3)
        else:
            imgui.push_style_color(imgui.Col_.button, _PINE_DIM)
            imgui.push_style_color(imgui.Col_.button_hovered, _PINE_HOV)
            imgui.push_style_color(imgui.Col_.text, _PINE)
            if imgui.button("\u25b6 Session##ss", imgui.ImVec2(bw, btn_h)):
                if self._selected >= 0:
                    self._start(self._selected)
            imgui.pop_style_color(3)

        imgui.same_line(spacing=_BTN_GAP)

        # ▶ Start Beats / ■ Stop Beats
        if self._beats_on:
            imgui.push_style_color(imgui.Col_.button, _HL_MED)
            imgui.push_style_color(imgui.Col_.button_hovered, _HL_HIGH)
            imgui.push_style_color(imgui.Col_.text, _SUBTLE)
            lbl = "\u25a0 Beats##sb"
        else:
            imgui.push_style_color(imgui.Col_.button, _GOLD)
            imgui.push_style_color(imgui.Col_.button_hovered, _FOAM)
            imgui.push_style_color(imgui.Col_.text, _BASE)
            lbl = "\u25b6 Beats##sb"
        if imgui.button(lbl, imgui.ImVec2(bw, btn_h)):
            self._beats_on = not self._beats_on
            if self.on_toggle_beats:
                self.on_toggle_beats()
        imgui.pop_style_color(3)

    def _draw_seek_bar(self, w: float) -> None:
        if self._state != SessionState.RUNNING:
            return
        if self._seek_live is None:
            return

        live = self._seek_live()
        t = float(live.get("session_time", 0) or 0)
        dur = float(live.get("session_duration", 0) or 0)
        lbl = live.get("timeline_label", "")
        paused = bool(live.get("timeline_paused", False))

        imgui.spacing()

        bw = (w - _BTN_GAP) / 2
        btn_h = 22

        imgui.push_style_color(imgui.Col_.button, _HL_MED)
        imgui.push_style_color(imgui.Col_.button_hovered, _HL_HIGH)
        imgui.push_style_color(imgui.Col_.text, _TEXT)
        if imgui.button("Resume" if paused else "Pause", imgui.ImVec2(bw, btn_h)):
            if self.on_timeline_cmd:
                self.on_timeline_cmd("resume" if paused else "pause")
        imgui.same_line(spacing=_BTN_GAP)
        if imgui.button("Next##pl", imgui.ImVec2(bw, btn_h)):
            if self.on_timeline_cmd:
                self.on_timeline_cmd("playlist_next")
        imgui.pop_style_color(3)

        if dur > 0:
            if not self._seeking:
                self._seek_value = t / dur
            imgui.set_next_item_width(w)
            imgui.push_style_color(imgui.Col_.frame_bg, _OVERLAY)
            _, self._seek_value = imgui.slider_float(
                "##seek", self._seek_value, 0.0, 1.0, ""
            )
            imgui.pop_style_color()
            if imgui.is_item_active():
                self._seeking = True
            if self._seeking and imgui.is_item_deactivated_after_edit():
                self._seeking = False
                if self.on_seek:
                    self.on_seek(self._seek_value * dur)
            mins, secs = int(t) // 60, int(t) % 60
            tot_m, tot_s = int(dur) // 60, int(dur) % 60
            imgui.text_colored(
                _SUBTLE, f"{mins}:{secs:02d} / {tot_m}:{tot_s:02d}  {lbl}"
            )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _unique_categories(self) -> list[str]:
        seen, out = set(), []
        for s in self._sessions:
            c = s.category or "General"
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def _filtered_sorted(self) -> list[tuple[int, SessionEntry]]:
        query = self._search.lower().strip()
        result = []
        for i, s in enumerate(self._sessions):
            if self._filter_cat not in ("All", "") and s.category != self._filter_cat:
                continue
            if (
                query
                and query not in s.name.lower()
                and query not in s.category.lower()
            ):
                continue
            result.append((i, s))

        if self._sort_mode == "Name":
            result.sort(key=lambda x: x[1].name.lower())
        elif self._sort_mode == "Duration":

            def _dur_key(x):
                try:
                    return int(x[1].duration.replace("m", "") or 0)
                except (ValueError, AttributeError):
                    return 0

            result.sort(key=_dur_key, reverse=True)
        # "Recent" = insertion order (no sort)
        return result

    def _start(self, idx: int) -> None:
        if 0 <= idx < len(self._sessions):
            self._playing = idx
            self._state = SessionState.RUNNING
            if self.on_start_session:
                self.on_start_session(self._sessions[idx])

    def _stop(self) -> None:
        self._state = SessionState.IDLE
        self._playing = -1
        self._beats_on = False
        if self.on_stop_session:
            self.on_stop_session()
