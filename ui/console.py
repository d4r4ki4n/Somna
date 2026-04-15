"""
Somna Console — Beat Envelope Visualizer

Scrolling log console with a beat envelope background.
The binaural beat only exists in the interference between L and R channels.
This extracts that envelope (LP-filter abs(L+R) at 20 Hz) and renders it
as a breathing band of pink light — the slow amplitude pulse the brain
actually entrains to.

No FFT. No spectrogram. No carrier. Just the beat.
"""

from __future__ import annotations

import math
import time
import collections
import numpy as np
from dataclasses import dataclass
from enum import Enum, auto

from imgui_bundle import imgui


class LogLevel(Enum):
    INFO    = auto()
    WARNING = auto()
    ERROR   = auto()
    AGENT   = auto()
    SYSTEM  = auto()
    DEBUG   = auto()


@dataclass
class LogEntry:
    timestamp: float
    level:     LogLevel
    message:   str
    source:    str = ""


# RGBA 0–255 — same values tint log lines in _draw_log_text and the control-panel
# filter row (legend + visibility toggles).
LOG_COLORS = {
    LogLevel.INFO:    (255, 255, 255, 216),
    LogLevel.WARNING: (255, 235,  59, 230),
    LogLevel.ERROR:   (255, 105, 180, 242),
    LogLevel.AGENT:   (  0, 209, 196, 230),
    LogLevel.SYSTEM:  (173, 130, 222, 216),
    LogLevel.DEBUG:   (128, 128, 128, 153),
}


def log_level_rgba_f(level: LogLevel) -> tuple[float, float, float, float]:
    """RGBA floats 0–1 for ImGui styling (filter legend, etc.)."""
    r, g, b, a = LOG_COLORS.get(level, (255, 255, 255, 200))
    return (r / 255.0, g / 255.0, b / 255.0, a / 255.0)


def _rgba_tuple_to_f(rgba: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    r, g, b, a = rgba
    return (r / 255.0, g / 255.0, b / 255.0, a / 255.0)


# INFO-level lines use `LogEntry.source`: "you" vs anything else (system-style).
# Colors are the old INFO vs DEBUG pair swapped so user-typed lines read brighter.
LOG_COLORS_INFO_USER = (255, 255, 255, 216)
LOG_COLORS_INFO_SYSTEM = (128, 128, 128, 153)


def log_info_user_rgba_f() -> tuple[float, float, float, float]:
    return _rgba_tuple_to_f(LOG_COLORS_INFO_USER)


def log_info_system_rgba_f() -> tuple[float, float, float, float]:
    return _rgba_tuple_to_f(LOG_COLORS_INFO_SYSTEM)

LOG_PREFIX = {
    LogLevel.INFO:    "",
    LogLevel.WARNING: "\u26a0 ",
    LogLevel.ERROR:   "\u2716 ",
    LogLevel.AGENT:   "\u25c8 ",
    LogLevel.SYSTEM:  "\u27d0 ",
    LogLevel.DEBUG:   "\u00b7 ",
}

_CLEAR = imgui.IM_COL32(0, 0, 0, 0)


def _col(r: float, g: float, b: float, a: float) -> int:
    return imgui.IM_COL32(
        min(255, max(0, int(r * 255))),
        min(255, max(0, int(g * 255))),
        min(255, max(0, int(b * 255))),
        min(255, max(0, int(a * 255))),
    )


class SpectrogramConsole:
    """Beat envelope console with glowing band background.

    Class name kept for backward compat.
    """

    def __init__(
        self,
        max_entries:      int   = 500,
        sample_rate:      int   = 16384,
        display_seconds:  float = 2.5,
        line_height:      float = 15.0,
        # Legacy params — accepted, ignored
        fft_bins=None,
        history_frames=None,
        waveform_size=None,
    ):
        self._log:     collections.deque = collections.deque(maxlen=max_entries)
        self._filters: dict              = {l: True for l in LogLevel}
        # INFO rows are split by `source` (see `_entry_visible` / `_draw_log_text`).
        self._show_info_user:   bool = True   # level INFO + source "you"
        self._show_info_system: bool = True   # level INFO + other sources

        # Envelope follower: LP abs(L+R) at 20 Hz, kills carrier, passes beat
        cutoff       = 20.0
        self._alpha  = min(1.0, (2.0 * math.pi * cutoff) / sample_rate)
        self._env    = 0.0
        self._ds     = 8                             # downsample 8:1
        self._ds_cnt = 0
        buf_len      = int(sample_rate * display_seconds / self._ds) + 1
        self._buf:   collections.deque = collections.deque(maxlen=buf_len)
        self._has_data = False

        self._line_h    = line_height
        self._breath_hz = 0.25   # updated from live state by poll

    # ── Logging API ───────────────────────────────────────────

    def log(self, msg: str, level: LogLevel = LogLevel.INFO, src: str = "") -> None:
        self._log.append(LogEntry(time.time(), level, msg, src))

    def info(self,   msg, src=""): self.log(msg, LogLevel.INFO,    src)
    def warn(self,   msg, src=""): self.log(msg, LogLevel.WARNING, src)
    def error(self,  msg, src=""): self.log(msg, LogLevel.ERROR,   src)
    def agent(self,  msg, src=""): self.log(msg, LogLevel.AGENT,   src)
    def system(self, msg, src=""): self.log(msg, LogLevel.SYSTEM,  src)
    def debug(self,  msg, src=""): self.log(msg, LogLevel.DEBUG,   src)
    def clear(self):               self._log.clear()

    # ── Legacy stubs ──────────────────────────────────────────

    def push_fft_frame(self, magnitudes):     pass
    def push_fft_from_audio(self, audio):     pass
    def push_beat_visualization(self, **kw):  pass
    def push_waveform(self, samples):         pass

    # ── Audio API ─────────────────────────────────────────────

    def push_audio(self, left: np.ndarray, right: np.ndarray) -> None:
        """Feed L/R channel chunks. Extracts and stores the beat envelope."""
        a    = self._alpha
        ds   = self._ds
        env  = self._env
        cnt  = self._ds_cnt
        buf  = self._buf
        n    = min(len(left), len(right))

        for i in range(n):
            val  = abs(float(left[i]) + float(right[i]))
            env += a * (val - env)
            cnt += 1
            if cnt >= ds:
                buf.append(env)
                cnt = 0

        self._env      = env
        self._ds_cnt   = cnt
        self._has_data = True

    def reset_waveform(self) -> None:
        """Return to idle animation (call on session stop)."""
        self._buf.clear()
        self._env      = 0.0
        self._ds_cnt   = 0
        self._has_data = False

    def _entry_visible(self, e: LogEntry) -> bool:
        if not self._filters.get(e.level, True):
            return False
        if e.level == LogLevel.INFO:
            if (e.source or "").lower() == "you":
                return self._show_info_user
            return self._show_info_system
        return True

    # ── Render ────────────────────────────────────────────────

    def render(self, width: float = -1, height: float = -1) -> None:
        avail = imgui.get_content_region_avail()
        w     = width  if width  > 0 else avail.x
        h     = height if height > 0 else avail.y

        imgui.begin_child(
            "##env_console_body",
            imgui.ImVec2(w, h),
            child_flags  = imgui.ChildFlags_.none,
            window_flags = imgui.WindowFlags_.no_scrollbar,
        )
        dl  = imgui.get_window_draw_list()
        pos = imgui.get_cursor_screen_pos()
        sz  = imgui.get_content_region_avail()
        self._draw_envelope(dl, pos.x, pos.y, sz.x, sz.y)
        self._draw_log_text(dl, pos, sz)
        imgui.end_child()

    # ── Envelope renderer ─────────────────────────────────────

    def _draw_envelope(self, dl, x: float, y: float, w: float, h: float) -> None:
        IV = imgui.ImVec2

        dl.add_rect_filled(IV(x, y), IV(x + w, y + h), imgui.IM_COL32(12, 4, 22, 240))

        t  = time.time()
        cy = y + h * 0.5

        buf = list(self._buf)
        n   = len(buf)

        if n < 4:
            # Idle: slow ambient breath, no data yet
            breath = 0.5 + 0.5 * math.sin(t * 0.5)
            e      = h * 0.04 * breath
            c      = _col(0.55, 0.10, 0.35, 0.12 * breath)
            dl.add_rect_filled(IV(x, cy - e), IV(x + w, cy + e), c)
            dl.add_line(IV(x, cy), IV(x + w, cy), _col(1.0, 0.65, 0.88, 0.06 * breath), 1.0)
            return

        cols  = max(int(w) // 3, 4)
        col_w = w / cols

        env = [buf[int(c * (n - 1) / (cols - 1))] for c in range(cols)]

        peak = max(env)
        if peak < 1e-8:
            return
        scale = (h * 0.35) / peak

        breath = 0.7 + 0.3 * math.sin(2.0 * math.pi * self._breath_hz * t)
        beat   = env[-1] / peak
        glow   = 0.5 + 0.5 * beat   # brightness follows the beat envelope directly

        def mag(a):   return _col(0.75, 0.18, 0.52, a * glow)
        def pink(a):  return _col(0.95, 0.40, 0.70, a * glow)
        def hot(a):   return _col(1.00, 0.65, 0.88, a * glow)
        def white(a): return _col(1.00, 0.85, 0.95, a * glow)

        # Layer 0 — full-panel breath glow
        dl.add_rect_filled(IV(x, y), IV(x + w, y + h),
                           _col(0.50, 0.08, 0.30, 0.04 * breath))

        # Layer 1 — outer aura (2.2×)
        for c in range(cols):
            e   = env[c] * scale * 2.2
            cx0 = x + c * col_w
            cx1 = cx0 + col_w
            mc  = mag(0.05)
            dl.add_rect_filled_multi_color(IV(cx0, cy - e), IV(cx1, cy),
                                           _CLEAR, _CLEAR, mc, mc)
            dl.add_rect_filled_multi_color(IV(cx0, cy), IV(cx1, cy + e),
                                           mc, mc, _CLEAR, _CLEAR)

        # Layer 2 — mid glow (1.5×)
        for c in range(cols):
            e   = env[c] * scale * 1.5
            cx0 = x + c * col_w
            cx1 = cx0 + col_w
            mc  = pink(0.09)
            dl.add_rect_filled_multi_color(IV(cx0, cy - e), IV(cx1, cy),
                                           _CLEAR, _CLEAR, mc, mc)
            dl.add_rect_filled_multi_color(IV(cx0, cy), IV(cx1, cy + e),
                                           mc, mc, _CLEAR, _CLEAR)

        # Layer 3 — core fill (1×, gradient)
        for c in range(cols):
            e   = env[c] * scale
            cx0 = x + c * col_w
            cx1 = cx0 + col_w
            dl.add_rect_filled_multi_color(IV(cx0, cy - e), IV(cx1, cy),
                                           pink(0.03), pink(0.03), hot(0.28), hot(0.28))
            dl.add_rect_filled_multi_color(IV(cx0, cy), IV(cx1, cy + e),
                                           hot(0.28), hot(0.28), pink(0.03), pink(0.03))

        # Layer 4 — edge lines with glow + bright core
        glow_col   = pink(0.18)
        bright_col = hot(0.55)
        top_pts    = [IV(x + c * col_w + col_w * 0.5, cy - env[c] * scale) for c in range(cols)]
        bot_pts    = [IV(x + c * col_w + col_w * 0.5, cy + env[c] * scale) for c in range(cols)]
        dl.add_polyline(top_pts, glow_col,   imgui.ImDrawFlags_.none, 5.0)
        dl.add_polyline(bot_pts, glow_col,   imgui.ImDrawFlags_.none, 5.0)
        dl.add_polyline(top_pts, bright_col, imgui.ImDrawFlags_.none, 1.5)
        dl.add_polyline(bot_pts, bright_col, imgui.ImDrawFlags_.none, 1.5)

        # Layer 5 — center pulse line
        dl.add_line(IV(x, cy), IV(x + w, cy), white(0.05 * beat), 1.0)

    # ── Log text overlay ──────────────────────────────────────

    def _draw_log_text(self, dl, pos, sz) -> None:
        visible_n = int(sz.y / self._line_h)
        entries   = [e for e in self._log if self._entry_visible(e)]
        start     = max(0, len(entries) - visible_n)
        shadow    = imgui.IM_COL32(0, 0, 0, 160)
        for i, entry in enumerate(entries[start : start + visible_n]):
            x    = pos.x + 6
            y    = pos.y + i * self._line_h + 2
            line = ""
            ts    = time.strftime("%H%M", time.localtime(entry.timestamp))
            line += f"[{ts}] "
            line += LOG_PREFIX.get(entry.level, "") + entry.message
            if entry.level == LogLevel.INFO:
                if (entry.source or "").lower() == "you":
                    r, g, b, a = LOG_COLORS_INFO_USER
                else:
                    r, g, b, a = LOG_COLORS_INFO_SYSTEM
            else:
                r, g, b, a = LOG_COLORS.get(entry.level, (255, 255, 255, 200))
            dl.add_text(imgui.ImVec2(x + 1, y + 1), shadow, line)
            dl.add_text(imgui.ImVec2(x,     y),     imgui.IM_COL32(r, g, b, a), line)

