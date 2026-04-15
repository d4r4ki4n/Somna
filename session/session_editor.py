"""
session_editor.py
Somna — Visual Session Editor

A Tkinter Toplevel window for creating and editing session.yaml files.
Launched via the "Edit" button in the control panel's Session section.

Layout
------
  ┌─ Top bar ─────────────────────────────────────────────────┐
  │ Name  Desc  Duration (s)            [ 💾 Save ]           │
  ├─ Timeline canvas ──────────────────────────────────────────┤
  │  0s   30s   60s … ◆──label──◆──────────◆   [+ Add KF]    │
  ├─ Detail panel ────────────────────────────────────────────┤
  │  ┌ Left: KF meta ┐  ┌ Right: parameter rows (scrollable) ┐│
  │  │  Time / Label │  │  param ▼  value  ✕                 ││
  │  │  Ease ▼       │  │  …                                  ││
  │  │  [Delete KF]  │  │  [ + Add param ]                    ││
  │  └───────────────┘  └────────────────────────────────────┘│
  └───────────────────────────────────────────────────────────┘
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Any, Optional

import yaml

# Import parameter sets so the dropdown has autocomplete knowledge
from session.timeline_runner import INTERPOLATABLE, INSTANT_ONLY
from ipc import patch_live

# ── Rosé Pine palette (mirrors control_panel.py) ──────────────────────────────
RP = {
    "base":     "#232136",
    "surface":  "#2a273f",
    "overlay":  "#393552",
    "muted":    "#6e6a86",
    "subtle":   "#908caa",
    "text":     "#e0def4",
    "love":     "#eb6f92",
    "gold":     "#f6c177",
    "rose":     "#ea9a97",
    "pine":     "#3e8fb0",
    "foam":     "#9ccfd8",
    "iris":     "#c4a7e7",
    "hl_low":   "#2a283e",
    "hl_med":   "#44415a",
    "hl_high":  "#56526e",
}

FONT_LABEL  = ("Segoe UI", 9)
FONT_SMALL  = ("Segoe UI", 8)
FONT_HEADER = ("Segoe UI", 9, "bold")
FONT_MONO   = ("Consolas", 9)

EASING_OPTIONS = ["linear", "ease_in", "ease_out", "ease_in_out", "instant"]

_MAX_UNDO = 20

# Params ordered by authoring priority: most-changed params first,
# grouped by subsystem, alphabetical within group only as a fallback.
_PARAM_ORDER = [
    # ── most common top-level controls ───────────────────────────────
    "beat_frequency", "carrier_frequency", "volume",
    "phrases",
    # ── spirals ──────────────────────────────────────────────────────
    "spiral_style", "spiral_opacity", "spiral_speed_multiplier",
    "spiral_count", "spiral_tightness", "spiral_thickness",
    "spiral_chaos", "spiral_color_mode", "spiral_show_text",
    # ── veil ─────────────────────────────────────────────────────────
    "veil_opacity", "veil_mode",
    # ── center text / subliminal ──────────────────────────────────────
    "center_flash_on_time", "center_flash_off_time",
    "center_flash_sync_to_beat",
    "font_switch_mode",
    # ── shadows ──────────────────────────────────────────────────────
    "shadow_opacity", "shadow_flash_on_time", "shadow_flash_off_time",
    # ── background ───────────────────────────────────────────────────
    "bg_mode", "slideshow_interval",
    # ── audio flags ──────────────────────────────────────────────────
    "audio_muted", "beat_type",
]
# Any params from the runner sets not listed above are appended alphabetically
_known = set(_PARAM_ORDER)
ALL_PARAMS = _PARAM_ORDER + sorted(
    (p for p in (INTERPOLATABLE | INSTANT_ONLY) if p not in _known)
)


# ── Data model ────────────────────────────────────────────────────────────────

class _Keyframe:
    """Mutable keyframe used by the editor (not the runner's dict-based model)."""
    __slots__ = ("t", "label", "ease", "params")

    def __init__(self, t: float, label: str = "",
                 ease: str = "linear", params: dict | None = None):
        self.t      = float(t)
        self.label  = label
        self.ease   = ease
        self.params: dict[str, Any] = dict(params or {})

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "t":      round(self.t, 2),
            "ease":   self.ease,
            "params": dict(self.params),
        }
        if self.label:
            d["label"] = self.label
        return d


# ── Session editor window ─────────────────────────────────────────────────────

class SessionEditor(tk.Toplevel):
    """Visual editor for a session.yaml file."""

    # Timeline canvas geometry
    TL_H      = 96    # canvas height in pixels
    TL_PAD    = 48    # left/right horizontal padding
    KF_R      = 7     # half-size of keyframe diamond

    # Colours
    C_PLAY    = "#f6c177"   # gold  — playhead
    C_AXIS    = "#393552"   # overlay
    C_TICK    = "#6e6a86"   # muted
    C_KF      = "#9ccfd8"   # foam  — normal keyframe
    C_KF_SEL  = "#eb6f92"   # love  — selected keyframe
    C_LABEL   = "#e0def4"   # text

    def __init__(self, parent: tk.Tk, session_path: Path, live_path: Path):
        super().__init__(parent)
        self.session_path  = session_path
        self.yaml_path     = session_path / "session.yaml"
        self.live_path     = live_path

        self.title(f"Session Editor  ·  {session_path.name}")
        self.configure(bg=RP["base"])
        self.resizable(True, True)

        # ── Editor state ───────────────────────────────────────────────────
        self._name_var  = tk.StringVar()
        self._desc_var  = tk.StringVar()
        self._dur_var   = tk.StringVar()
        self._status_var = tk.StringVar()

        self._keyframes: list[_Keyframe] = []
        self._defaults:  dict[str, Any]  = {}
        self._selected:  Optional[int]   = None   # index into _keyframes
        self._drag_idx:  Optional[int]   = None
        self._drag_snapshot: Optional[dict] = None
        self._param_rows: list[tuple]    = []     # (param_var, val_var, frame)

        # Undo stack and dirty flag
        self._undo_stack: list[dict] = []
        self._dirty      = False
        self._restoring  = False  # suppresses dirty traces during restore

        # Playhead from live_control.json (read-only, 500 ms poll)
        self._playhead_t = 0.0

        # ── Build UI then load data ────────────────────────────────────────
        self._build_ui()
        self._load()

        # Dirty traces added AFTER _load so initial values don't mark dirty
        for _v in (self._name_var, self._desc_var, self._dur_var):
            _v.trace_add("write", self._on_field_changed)
        self.bind("<Control-z>", self._undo)

        # Start playhead poll
        self._poll_playhead()

        # Size and position relative to parent
        self.update_idletasks()
        W, H = 980, 680
        px = parent.winfo_x() + max(0, (parent.winfo_width()  - W) // 2)
        py = parent.winfo_y() + max(0, (parent.winfo_height() - H) // 2)
        self.geometry(f"{W}x{H}+{px}+{py}")
        self.lift()
        self.focus_force()

    # ── I / O ─────────────────────────────────────────────────────────────────

    def _load(self):
        """Read session.yaml into the editor state."""
        raw: dict = {}
        if self.yaml_path.exists():
            with open(self.yaml_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}

        self._name_var.set(raw.get("name", self.session_path.name))
        self._desc_var.set(raw.get("description", ""))
        dur = raw.get("duration")
        self._dur_var.set(str(int(dur)) if dur is not None else "")
        self._defaults = dict(raw.get("defaults", {}))

        self._keyframes = []
        for entry in raw.get("timeline", []):
            self._keyframes.append(_Keyframe(
                t      = float(entry.get("t", 0)),
                label  = entry.get("label", ""),
                ease   = entry.get("ease", "linear"),
                params = entry.get("params", {}),
            ))
        self._keyframes.sort(key=lambda k: k.t)

        self._select_keyframe(None)
        self._draw_timeline()
        self._undo_stack.clear()
        self._set_dirty(False)

    def _save(self):
        """Write editor state back to session.yaml and trigger a live reload."""
        dur_str = self._dur_var.get().strip()
        duration: Optional[float] = None
        if dur_str:
            try:
                duration = float(dur_str)
            except ValueError:
                messagebox.showerror("Bad value",
                    f"Duration must be a number (got '{dur_str}').", parent=self)
                return

        # Flush any unsaved param row edits
        self._flush_param_rows()

        data: dict[str, Any] = {
            "name": self._name_var.get().strip() or self.session_path.name,
        }
        desc = self._desc_var.get().strip()
        if desc:
            data["description"] = desc
        if duration is not None:
            data["duration"] = duration
        if self._defaults:
            data["defaults"] = self._defaults
        if self._keyframes:
            data["timeline"] = [
                kf.to_dict()
                for kf in sorted(self._keyframes, key=lambda k: k.t)
            ]

        with open(self.yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False,
                      allow_unicode=True, sort_keys=False)

        # Hot-reload: set session_folder to THIS session before sending the
        # load command so the runner reloads the file we just wrote, not
        # whatever session happened to be loaded before we opened the editor.
        try:
            patch_live({"session_folder": self.session_path.name, "_timeline_cmd": "load"})
        except Exception:
            pass
        self._undo_stack.clear()
        self._set_dirty(False)
        self._status("Saved  ✓")

    def _read_live(self) -> dict:
        try:
            return json.loads(self.live_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _status(self, msg: str):
        self._status_var.set(msg)
        self.after(3000, lambda: self._status_var.set(""))

    # ── Undo / dirty ──────────────────────────────────────────────────────────

    def _set_dirty(self, dirty: bool):
        if dirty == self._dirty:
            return
        self._dirty = dirty
        base = f"Session Editor  ·  {self.session_path.name}"
        self.title(f"*  {base}" if dirty else base)

    def _on_field_changed(self, *_):
        if not self._restoring:
            self._set_dirty(True)

    def _snapshot(self) -> dict:
        return {
            "name":      self._name_var.get(),
            "desc":      self._desc_var.get(),
            "dur":       self._dur_var.get(),
            "defaults":  dict(self._defaults),
            "keyframes": [{"t": kf.t, "label": kf.label, "ease": kf.ease,
                           "params": dict(kf.params)}
                          for kf in self._keyframes],
            "selected":  self._selected,
        }

    def _restore_snapshot(self, state: dict):
        self._restoring = True
        try:
            self._name_var.set(state["name"])
            self._desc_var.set(state["desc"])
            self._dur_var.set(state["dur"])
        finally:
            self._restoring = False
        self._defaults   = dict(state["defaults"])
        self._keyframes  = [
            _Keyframe(t=kf["t"], label=kf["label"], ease=kf["ease"],
                      params=dict(kf["params"]))
            for kf in state["keyframes"]
        ]
        self._select_keyframe(state["selected"])

    def _push_undo(self):
        """Flush param rows, snapshot current state, push to undo stack."""
        self._flush_param_rows()
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > _MAX_UNDO:
            self._undo_stack.pop(0)
        self._set_dirty(True)

    def _undo(self, _event=None):
        if not self._undo_stack:
            self._status("Nothing to undo")
            return
        self._restore_snapshot(self._undo_stack.pop())
        self._set_dirty(True)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ────────────────────────────────────────────────────────
        top = tk.Frame(self, bg=RP["surface"], padx=12, pady=8)
        top.pack(fill="x")

        fields = [
            ("Name",        self._name_var,  28),
            ("Description", self._desc_var,  32),
            ("Duration (s)", self._dur_var,   7),
        ]
        for col, (lbl, var, w) in enumerate(fields):
            tk.Label(top, text=lbl + ":", bg=RP["surface"], fg=RP["muted"],
                     font=FONT_LABEL).grid(row=0, column=col * 2,
                                           sticky="e", padx=(8 if col else 0, 4))
            tk.Entry(top, textvariable=var, bg=RP["overlay"], fg=RP["text"],
                     insertbackground=RP["text"], font=FONT_LABEL,
                     relief="flat", width=w
                     ).grid(row=0, column=col * 2 + 1, sticky="w", padx=(0, 10))

        tk.Button(top, text="💾  Save",
                  font=FONT_HEADER,
                  bg=RP["pine"], fg=RP["base"],
                  activebackground=RP["foam"], activeforeground=RP["base"],
                  relief="flat", bd=0, padx=14, pady=5,
                  cursor="hand2", command=self._save,
                  ).grid(row=0, column=7, padx=(6, 0))

        tk.Label(top, textvariable=self._status_var, bg=RP["surface"],
                 fg=RP["gold"], font=FONT_SMALL
                 ).grid(row=0, column=8, sticky="w", padx=(10, 0))

        # ── Timeline section ───────────────────────────────────────────────
        tl_outer = tk.Frame(self, bg=RP["overlay"])
        tl_outer.pack(fill="x")

        tl_bar = tk.Frame(tl_outer, bg=RP["overlay"], padx=12, pady=5)
        tl_bar.pack(fill="x")
        tk.Label(tl_bar, text="TIMELINE", bg=RP["overlay"],
                 fg=RP["iris"], font=FONT_HEADER).pack(side="left")
        tk.Button(tl_bar, text="+  Add Keyframe",
                  font=FONT_SMALL, bg=RP["hl_high"], fg=RP["text"],
                  activebackground=RP["iris"], activeforeground=RP["base"],
                  relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
                  command=self._add_keyframe,
                  ).pack(side="left", padx=(12, 0))
        tk.Label(tl_bar, text="at t =", bg=RP["overlay"],
                 fg=RP["muted"], font=FONT_SMALL).pack(side="left", padx=(8, 2))
        self._add_t_var = tk.StringVar()
        tk.Entry(tl_bar, textvariable=self._add_t_var,
                 bg=RP["overlay"], fg=RP["foam"],
                 insertbackground=RP["text"],
                 font=FONT_MONO, relief="flat", width=7,
                 ).pack(side="left")
        tk.Label(tl_bar, text="(blank = playhead)",
                 bg=RP["overlay"], fg=RP["muted"], font=FONT_SMALL,
                 ).pack(side="left", padx=(4, 0))
        tk.Label(tl_bar,
                 text="· drag markers · click to select · Del to remove",
                 bg=RP["overlay"], fg=RP["muted"], font=FONT_SMALL,
                 ).pack(side="left", padx=(14, 0))

        self._canvas = tk.Canvas(tl_outer, height=self.TL_H,
                                 bg=RP["surface"], highlightthickness=0)
        self._canvas.pack(fill="x")
        self._canvas.bind("<ButtonPress-1>",  self._on_press)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Configure>",       lambda _e: self._draw_timeline())
        self.bind("<Delete>",                  self._on_delete_key)

        # ── Detail area (left: meta, right: params) ────────────────────────
        detail = tk.Frame(self, bg=RP["base"])
        detail.pack(fill="both", expand=True)

        # Left — keyframe meta
        meta = tk.Frame(detail, bg=RP["surface"], padx=12, pady=10, width=230)
        meta.pack(side="left", fill="y")
        meta.pack_propagate(False)

        tk.Label(meta, text="KEYFRAME", bg=RP["surface"],
                 fg=RP["iris"], font=FONT_HEADER).pack(anchor="w", pady=(0, 6))

        self._kf_t_var     = tk.StringVar(value="—")
        self._kf_label_var = tk.StringVar()
        self._kf_ease_var  = tk.StringVar(value="linear")

        for lbl, var, is_mono in [
            ("Time (s)",  self._kf_t_var,     True),
            ("Label",     self._kf_label_var,  False),
        ]:
            row = tk.Frame(meta, bg=RP["surface"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=lbl, bg=RP["surface"], fg=RP["muted"],
                     font=FONT_LABEL, width=11, anchor="e").pack(side="left")
            font = FONT_MONO if is_mono else FONT_LABEL
            color = RP["foam"] if is_mono else RP["text"]
            tk.Entry(row, textvariable=var, bg=RP["overlay"], fg=color,
                     insertbackground=RP["text"],
                     font=font, relief="flat", width=14,
                     ).pack(side="left", padx=(6, 0))

        ease_row = tk.Frame(meta, bg=RP["surface"])
        ease_row.pack(fill="x", pady=2)
        tk.Label(ease_row, text="Ease", bg=RP["surface"], fg=RP["muted"],
                 font=FONT_LABEL, width=11, anchor="e").pack(side="left")
        self._ease_combo = ttk.Combobox(ease_row, textvariable=self._kf_ease_var,
                                        values=EASING_OPTIONS, state="readonly",
                                        width=13)
        self._ease_combo.pack(side="left", padx=(6, 0))
        self._ease_combo.bind("<<ComboboxSelected>>", self._on_meta_change)

        self._kf_t_var.trace_add("write",     self._on_time_edit)
        self._kf_label_var.trace_add("write", self._on_meta_change)

        kf_btn_row = tk.Frame(meta, bg=RP["surface"])
        kf_btn_row.pack(anchor="w", pady=(14, 0))

        tk.Button(kf_btn_row, text="⧉  Duplicate",
                  font=FONT_SMALL,
                  bg=RP["hl_high"], fg=RP["text"],
                  activebackground=RP["iris"], activeforeground=RP["base"],
                  relief="flat", bd=0, padx=8, pady=4,
                  cursor="hand2", command=self._duplicate_selected,
                  ).pack(side="left", padx=(0, 6))

        tk.Button(kf_btn_row, text="✕  Delete",
                  font=FONT_SMALL,
                  bg=RP["love"], fg=RP["base"],
                  activebackground="#c55070", activeforeground=RP["base"],
                  relief="flat", bd=0, padx=8, pady=4,
                  cursor="hand2", command=self._delete_selected,
                  ).pack(side="left")

        # Right — parameter rows
        prm_outer = tk.Frame(detail, bg=RP["base"])
        prm_outer.pack(side="left", fill="both", expand=True)

        prm_bar = tk.Frame(prm_outer, bg=RP["surface"], padx=12, pady=6)
        prm_bar.pack(fill="x")
        tk.Label(prm_bar, text="PARAMETERS", bg=RP["surface"],
                 fg=RP["iris"], font=FONT_HEADER).pack(side="left")
        tk.Button(prm_bar, text="+  Add",
                  font=FONT_SMALL, bg=RP["hl_high"], fg=RP["text"],
                  activebackground=RP["iris"], activeforeground=RP["base"],
                  relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
                  command=self._add_param_row,
                  ).pack(side="left", padx=(10, 0))

        # Scrollable param canvas
        scroll_outer = tk.Frame(prm_outer, bg=RP["base"])
        scroll_outer.pack(fill="both", expand=True)

        prm_canvas = tk.Canvas(scroll_outer, bg=RP["base"], highlightthickness=0)
        prm_sb = ttk.Scrollbar(scroll_outer, orient="vertical",
                               command=prm_canvas.yview)
        prm_canvas.configure(yscrollcommand=prm_sb.set)
        prm_sb.pack(side="right", fill="y")
        prm_canvas.pack(side="left", fill="both", expand=True)
        prm_canvas.bind("<MouseWheel>",
            lambda e: prm_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._prm_frame = tk.Frame(prm_canvas, bg=RP["base"])
        self._prm_frame.bind("<Configure>",
            lambda _e: prm_canvas.configure(
                scrollregion=prm_canvas.bbox("all")))
        prm_canvas.create_window((0, 0), window=self._prm_frame, anchor="nw")

        self._hint_label = tk.Label(self._prm_frame,
            text="← select a keyframe to edit its parameters",
            bg=RP["base"], fg=RP["muted"], font=FONT_LABEL)
        self._hint_label.pack(pady=20, padx=16, anchor="w")

    # ── Timeline drawing ──────────────────────────────────────────────────────

    def _view_dur(self) -> float:
        dur_str = self._dur_var.get().strip()
        if dur_str:
            try:
                return max(1.0, float(dur_str))
            except ValueError:
                pass
        if self._keyframes:
            return max(60.0, self._keyframes[-1].t * 1.15 + 15)
        return 120.0

    def _t_to_x(self, t: float) -> float:
        w   = max(1, self._canvas.winfo_width())
        dur = self._view_dur()
        return self.TL_PAD + (t / dur) * (w - self.TL_PAD * 2)

    def _x_to_t(self, x: float) -> float:
        w   = max(1, self._canvas.winfo_width())
        dur = self._view_dur()
        t   = (x - self.TL_PAD) / (w - self.TL_PAD * 2) * dur
        return max(0.0, min(dur, t))

    def _draw_timeline(self):
        c   = self._canvas
        c.delete("all")
        w   = max(1, c.winfo_width())
        dur = self._view_dur()

        AXIS_Y = 58

        # Axis line
        c.create_line(self.TL_PAD, AXIS_Y, w - self.TL_PAD, AXIS_Y,
                      fill=self.C_AXIS, width=2)

        # Tick interval — aim for 8-10 visible ticks regardless of duration.
        # Table covers 10 s sessions up to multi-hour; math backstop handles anything beyond.
        _TICK_TABLE = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200)
        tick_s = _TICK_TABLE[-1]
        for ti in _TICK_TABLE:
            if dur / ti <= 10:
                tick_s = ti
                break
        else:
            # Beyond the table: pick the nearest power-of-10-multiple that gives ~8 ticks
            import math as _math
            raw = dur / 8
            mag = 10 ** int(_math.floor(_math.log10(raw)))
            tick_s = mag * round(raw / mag)

        t = 0.0
        while t <= dur + 0.01:
            x = self._t_to_x(t)
            c.create_line(x, AXIS_Y - 5, x, AXIS_Y + 5,
                          fill=self.C_TICK, width=1)
            m, s = divmod(int(round(t)), 60)
            lbl  = f"{m}:{s:02d}" if m else f"{int(round(t))}s"
            c.create_text(x, AXIS_Y + 9, text=lbl,
                          fill=self.C_TICK, font=FONT_SMALL, anchor="n")
            t += tick_s

        # Playhead
        ph = self._t_to_x(self._playhead_t)
        c.create_line(ph, 2, ph, AXIS_Y, fill=self.C_PLAY, width=2)
        c.create_polygon(ph - 5, 2, ph + 5, 2, ph, 9,
                         fill=self.C_PLAY, outline="")

        # Keyframe markers
        R = self.KF_R
        for i, kf in enumerate(self._keyframes):
            x   = self._t_to_x(kf.t)
            sel = (i == self._selected)
            col = self.C_KF_SEL if sel else self.C_KF
            c.create_polygon(x, AXIS_Y - R, x + R, AXIS_Y,
                             x, AXIS_Y + R, x - R, AXIS_Y,
                             fill=col, outline=RP["text"] if sel else col,
                             width=2 if sel else 1, tags=f"kf{i}")
            text = kf.label or f"{kf.t:.0f}s"
            c.create_text(x, AXIS_Y - R - 7, text=text,
                          fill=self.C_LABEL if kf.label else self.C_TICK,
                          font=FONT_SMALL, anchor="s", tags=f"kf{i}")

    # ── Canvas events ─────────────────────────────────────────────────────────

    def _nearest_kf(self, x: float) -> Optional[int]:
        best_i, best_d = None, self.KF_R * 2.5
        for i, kf in enumerate(self._keyframes):
            d = abs(x - self._t_to_x(kf.t))
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    def _on_press(self, event):
        i = self._nearest_kf(event.x)
        self._select_keyframe(i)   # flushes param rows first
        self._drag_idx = i
        self._canvas.focus_set()
        # Snapshot the post-flush state as the pre-drag baseline for undo
        self._drag_snapshot = self._snapshot() if i is not None else None

    def _on_drag(self, event):
        if self._drag_idx is None:
            return
        new_t = round(self._x_to_t(event.x), 1)
        self._keyframes[self._drag_idx].t = new_t
        # Prevent the StringVar trace from re-selecting while dragging
        self._kf_t_var.set(str(new_t))
        self._draw_timeline()

    def _on_release(self, _event):
        if self._drag_idx is not None:
            dragged = self._keyframes[self._drag_idx]
            # Push pre-drag snapshot to undo only if the position actually changed
            if (self._drag_snapshot is not None
                    and abs(dragged.t
                            - self._drag_snapshot["keyframes"][self._drag_idx]["t"])
                    > 0.05):
                self._undo_stack.append(self._drag_snapshot)
                if len(self._undo_stack) > _MAX_UNDO:
                    self._undo_stack.pop(0)
                self._set_dirty(True)
            self._drag_snapshot = None
            self._keyframes.sort(key=lambda k: k.t)
            self._selected = self._keyframes.index(dragged)
            self._drag_idx = None
            self._draw_timeline()

    def _on_delete_key(self, _event):
        # Allow Delete to remove a keyframe unless the user is typing in an
        # Entry or Combobox — in those cases the widget handles the keypress itself.
        focused = self.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Combobox, tk.Text)):
            return
        self._delete_selected()

    # ── Keyframe management ───────────────────────────────────────────────────

    def _select_keyframe(self, idx: Optional[int]):
        self._flush_param_rows()
        self._selected = idx
        if idx is None or idx >= len(self._keyframes):
            self._kf_t_var.set("—")
            self._kf_label_var.set("")
            self._kf_ease_var.set("linear")
            self._clear_param_rows()
            self._hint_label.pack(pady=20, padx=16, anchor="w")
        else:
            kf = self._keyframes[idx]
            self._kf_t_var.set(str(round(kf.t, 2)))
            self._kf_label_var.set(kf.label)
            self._kf_ease_var.set(kf.ease)
            self._rebuild_param_rows(kf.params)
        self._draw_timeline()

    def _add_keyframe(self):
        """Add a blank keyframe at the typed time, or at playhead if blank."""
        raw = self._add_t_var.get().strip()
        if raw:
            try:
                t = round(float(raw), 1)
            except ValueError:
                self._status("Bad time — enter a number (seconds)")
                return
        else:
            t = round(self._playhead_t, 1)
        # Nudge to avoid exact collision
        existing = {kf.t for kf in self._keyframes}
        while t in existing:
            t = round(t + 0.5, 1)
        self._push_undo()
        new_kf = _Keyframe(t=t)
        self._keyframes.append(new_kf)
        self._keyframes.sort(key=lambda k: k.t)
        self._selected = self._keyframes.index(new_kf)
        self._select_keyframe(self._selected)

    def _duplicate_selected(self):
        """Copy the selected keyframe's params into a new keyframe 30 s later."""
        if self._selected is None:
            return
        self._push_undo()   # flushes param rows and snapshots
        src = self._keyframes[self._selected]
        t   = round(src.t + 30.0, 1)
        existing = {kf.t for kf in self._keyframes}
        while t in existing:
            t = round(t + 0.5, 1)
        new_kf = _Keyframe(t=t, label=src.label, ease=src.ease,
                           params=dict(src.params))
        self._keyframes.append(new_kf)
        self._keyframes.sort(key=lambda k: k.t)
        self._selected = self._keyframes.index(new_kf)
        # Pre-fill the time field so user can immediately adjust it
        self._add_t_var.set(str(t))
        self._select_keyframe(self._selected)

    def _delete_selected(self):
        if self._selected is None:
            return
        self._push_undo()   # flushes params to current keyframe, then snapshots
        idx = self._selected
        self._selected = None   # clear BEFORE pop so the deselect flush is a no-op
        self._keyframes.pop(idx)
        self._select_keyframe(None)

    def _on_time_edit(self, *_):
        if self._selected is None or self._drag_idx is not None:
            return
        try:
            t = float(self._kf_t_var.get())
        except ValueError:
            return
        kf = self._keyframes[self._selected]
        kf.t = t
        # Re-sort so _selected stays valid after the time change.
        self._keyframes.sort(key=lambda k: k.t)
        self._selected = self._keyframes.index(kf)
        self._draw_timeline()

    def _on_meta_change(self, *_):
        if self._selected is None:
            return
        kf = self._keyframes[self._selected]
        kf.label = self._kf_label_var.get()
        kf.ease  = self._kf_ease_var.get()
        self._draw_timeline()

    # ── Parameter rows ────────────────────────────────────────────────────────

    def _clear_param_rows(self):
        for _, _, frame in self._param_rows:
            frame.destroy()
        self._param_rows.clear()

    def _rebuild_param_rows(self, params: dict):
        self._clear_param_rows()
        self._hint_label.pack_forget()
        for key, val in params.items():
            self._add_param_row(key=str(key), value=str(val))

    def _flush_param_rows(self):
        """Write current param row values back into the selected keyframe."""
        if self._selected is None or self._selected >= len(self._keyframes):
            return
        kf = self._keyframes[self._selected]
        kf.params = {}
        for param_var, val_var, _ in self._param_rows:
            key     = param_var.get().strip()
            val_str = val_var.get().strip()
            if not key:
                continue
            kf.params[key] = _cast(val_str)

    def _add_param_row(self, key: str = "", value: str = ""):
        """Append one editable parameter row to the params panel."""
        frame = tk.Frame(self._prm_frame, bg=RP["surface"], pady=2)
        frame.pack(fill="x", padx=4, pady=1)

        param_var = tk.StringVar(value=key)
        val_var   = tk.StringVar(value=value)

        cb = ttk.Combobox(frame, textvariable=param_var,
                          values=ALL_PARAMS, width=26, font=FONT_MONO)
        cb.pack(side="left", padx=(4, 0))

        tk.Entry(frame, textvariable=val_var,
                 bg=RP["overlay"], fg=RP["foam"],
                 insertbackground=RP["text"],
                 font=FONT_MONO, relief="flat", width=20,
                 ).pack(side="left", padx=(6, 0))

        row = (param_var, val_var, frame)

        def _del(r=row):
            if r in self._param_rows:
                self._param_rows.remove(r)
            r[2].destroy()

        tk.Button(frame, text="✕",
                  font=FONT_SMALL, bg=RP["surface"], fg=RP["love"],
                  activebackground=RP["overlay"], relief="flat",
                  bd=0, padx=6, pady=2, cursor="hand2",
                  command=_del,
                  ).pack(side="left", padx=(4, 0))

        self._param_rows.append(row)

    # ── Playhead polling ──────────────────────────────────────────────────────

    def _poll_playhead(self):
        if not self.winfo_exists():
            return
        try:
            data = self._read_live()
            self._playhead_t = float(data.get("session_time", 0))
            self._draw_timeline()
        except Exception:
            pass
        self.after(500, self._poll_playhead)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cast(s: str) -> Any:
    """Coerce a string value to the most appropriate Python type for YAML output.
    Order: null → bool → int → float → str."""
    sl = s.strip().lower()
    if sl in ("null", "none", "~"): return None
    if sl == "true":                return True
    if sl == "false":               return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


if __name__ == "__main__":
    import sys
    root_dir = Path(__file__).parent.parent

    root_tk = tk.Tk()
    root_tk.withdraw()

    if len(sys.argv) > 1:
        session_path = Path(sys.argv[1])
    else:
        session_path = root_dir / "sessions" / "default"

    session_path.mkdir(parents=True, exist_ok=True)
    live_path = root_dir / "live_control.json"

    editor = SessionEditor(root_tk, session_path, live_path)
    editor.protocol("WM_DELETE_WINDOW", root_tk.quit)
    root_tk.mainloop()
