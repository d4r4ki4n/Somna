"""
Somna Progress Panel

Shows user-visible progress:
  - Total sessions, total time, avg/max depth
  - Recent session history with depth metrics
  - Most-played sessions
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from imgui_bundle import imgui

from ui.panel_theme import token_rgba


def _v4(r: int, g: int, b: int, a: float = 1.0) -> imgui.ImVec4:
    return imgui.ImVec4(r / 255, g / 255, b / 255, a)


_TEXT = _v4(224, 222, 244, 1.0)
_SUBTLE = _v4(144, 140, 170, 1.0)
_MUTED = _v4(110, 106, 134, 1.0)
_LOVE = _v4(235, 111, 146, 1.0)
_PINE = _v4(62, 143, 176, 1.0)
_FOAM = _v4(156, 207, 216, 1.0)
_GOLD = _v4(246, 193, 119, 1.0)
_IRIS = _v4(196, 167, 231, 1.0)
_HL_LOW = _v4(42, 40, 62, 1.0)
_HL_MED = _v4(68, 65, 90, 1.0)
_SURFACE = _v4(42, 39, 63, 0.97)


def _fmt_duration(s: float) -> str:
    if not s or s <= 0:
        return "—"
    m = int(s) // 60
    h = m // 60
    if h > 0:
        return f"{h}h {m % 60}m"
    return f"{m}m"


def _fmt_depth(d: float) -> str:
    if not d or d <= 0:
        return "—"
    if d < 1:
        return f"{d:.2f}"
    return f"{d:.1f}"


class ProgressPanel:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._cache: Optional[dict] = None
        self._cache_frame: int = -999
        self._refresh_interval: int = 300

    def _load_data(self) -> dict:
        conn = sqlite3.connect(str(self._db_path))
        c = conn.cursor()

        profile = {
            "sessions": 0,
            "total_time_s": 0,
            "avg_peak_depth": 0.0,
            "max_depth": 0.0,
        }
        try:
            c.execute(
                "SELECT sessions_completed, total_session_time_s, "
                "avg_peak_depth, max_achieved_depth FROM director_profile"
            )
            row = c.fetchone()
            if row:
                profile = {
                    "sessions": row[0] or 0,
                    "total_time_s": row[1] or 0,
                    "avg_peak_depth": row[2] or 0.0,
                    "max_depth": row[3] or 0.0,
                }
        except Exception:
            pass

        recent = []
        try:
            c.execute(
                "SELECT session_id, session_date, duration_sec, "
                "depth_min_sef95, composite_score "
                "FROM session_metrics ORDER BY session_date DESC LIMIT 15"
            )
            for r in c.fetchall():
                recent.append(
                    {
                        "name": r[0] or "—",
                        "date": (r[1] or "")[:10],
                        "duration": r[2] or 0,
                        "depth": r[3] or 0.0,
                        "score": r[4] or 0.0,
                    }
                )
        except Exception:
            pass

        played = []
        try:
            c.execute(
                "SELECT name, play_count, last_played, is_favorite "
                "FROM sessions WHERE play_count > 0 "
                "ORDER BY play_count DESC LIMIT 8"
            )
            for r in c.fetchall():
                played.append(
                    {
                        "name": r[0] or "—",
                        "plays": r[1] or 0,
                        "last": (r[2] or "")[:10],
                        "fav": bool(r[3]),
                    }
                )
        except Exception:
            pass

        conn.close()
        return {"profile": profile, "recent": recent, "played": played}

    def render(self) -> None:
        frame = imgui.get_frame_count()
        if self._cache is None or frame - self._cache_frame > self._refresh_interval:
            self._cache = self._load_data()
            self._cache_frame = frame

        data = self._cache
        p = data["profile"]

        w = imgui.get_content_region_avail().x

        self._draw_header(w, p)
        imgui.spacing()
        self._draw_stats_row(w, p)
        imgui.spacing()
        imgui.separator()
        imgui.spacing()
        self._draw_recent(w, data["recent"])
        imgui.spacing()
        imgui.separator()
        imgui.spacing()
        self._draw_played(w, data["played"])

    def _draw_header(self, w: float, p: dict) -> None:
        imgui.text_colored(_SUBTLE, "PROGRESS")
        imgui.spacing()

    def _draw_stats_row(self, w: float, p: dict) -> None:
        col_w = w / 4.0

        stats = [
            ("Sessions", str(p["sessions"]), _FOAM),
            ("Total Time", _fmt_duration(p["total_time_s"]), _GOLD),
            ("Avg Depth", _fmt_depth(p["avg_peak_depth"]), _IRIS),
            ("Max Depth", _fmt_depth(p["max_depth"]), _LOVE),
        ]

        for i, (label, val, col) in enumerate(stats):
            if i > 0:
                imgui.same_line(col_w * i + 4)
            imgui.begin_child(f"##stat_{i}", imgui.ImVec2(col_w - 6, 48))
            imgui.set_cursor_pos(imgui.ImVec2(6, 4))
            imgui.text_colored(_MUTED, label)
            imgui.set_cursor_pos(imgui.ImVec2(6, 22))
            imgui.text_colored(col, val)
            imgui.end_child()

    def _draw_recent(self, w: float, recent: list) -> None:
        imgui.text_colored(_SUBTLE, "Recent Sessions")
        imgui.spacing()

        if not recent:
            imgui.text_colored(_MUTED, "  No EEG session data yet.")
            return

        imgui.push_style_color(imgui.Col_.child_bg, _HL_LOW)
        imgui.begin_child("##recent_list", imgui.ImVec2(w, 0))

        dl = imgui.get_window_draw_list()
        sub_u32 = imgui.color_convert_float4_to_u32(_MUTED)
        txt_u32 = imgui.color_convert_float4_to_u32(_SUBTLE)
        foam_u32 = imgui.color_convert_float4_to_u32(_FOAM)
        gold_u32 = imgui.color_convert_float4_to_u32(_GOLD)

        for s in recent:
            p = imgui.get_cursor_screen_pos()
            row_h = 20

            name = s["name"]
            date = s["date"]
            dur = _fmt_duration(s["duration"])
            depth = _fmt_depth(s["depth"])

            dl.add_text(imgui.ImVec2(p.x + 4, p.y + 3), foam_u32, name)
            dl.add_text(
                imgui.ImVec2(p.x + w * 0.45, p.y + 3), sub_u32, date
            )
            dl.add_text(
                imgui.ImVec2(p.x + w * 0.62, p.y + 3), txt_u32, dur
            )
            dl.add_text(
                imgui.ImVec2(p.x + w * 0.78, p.y + 3), gold_u32, depth
            )

            imgui.dummy(imgui.ImVec2(w - 8, row_h))

        imgui.end_child()
        imgui.pop_style_color()

    def _draw_played(self, w: float, played: list) -> None:
        imgui.text_colored(_SUBTLE, "Most Played")
        imgui.spacing()

        if not played:
            imgui.text_colored(_MUTED, "  No sessions played yet.")
            return

        imgui.push_style_color(imgui.Col_.child_bg, _HL_LOW)
        imgui.begin_child("##played_list", imgui.ImVec2(w, 0))

        dl = imgui.get_window_draw_list()
        sub_u32 = imgui.color_convert_float4_to_u32(_MUTED)
        txt_u32 = imgui.color_convert_float4_to_u32(_SUBTLE)
        foam_u32 = imgui.color_convert_float4_to_u32(_FOAM)
        love_u32 = imgui.color_convert_float4_to_u32(_LOVE)

        for s in played:
            p = imgui.get_cursor_screen_pos()
            row_h = 20

            star = "\u2605 " if s["fav"] else "  "
            name = star + s["name"]
            plays = f"{s['plays']}x"
            last = s["last"]

            dl.add_text(imgui.ImVec2(p.x + 4, p.y + 3), foam_u32, name)
            dl.add_text(
                imgui.ImVec2(p.x + w * 0.55, p.y + 3), love_u32, plays
            )
            dl.add_text(
                imgui.ImVec2(p.x + w * 0.72, p.y + 3), sub_u32, last
            )

            imgui.dummy(imgui.ImVec2(w - 8, row_h))

        imgui.end_child()
        imgui.pop_style_color()