"""
Somna Control Panel
Styled with Rosé Pine Moon (https://rosepinetheme.com/palette/ingredients)
Entry point for the entire app. Manages the visual display subprocess.
"""
import tkinter as tk
from tkinter import ttk
import json
import subprocess
import sys
import time
import threading
from pathlib import Path
import traceback
import tkinter.colorchooser as colorchooser
from ipc import StateServer, patch_live

# ── Rosé Pine Moon palette ────────────────────────────────────────────────────
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
FONT_TITLE  = ("Segoe UI", 11, "bold")
FONT_LAUNCH = ("Segoe UI", 11, "bold")

# Baseline parameter values applied when loading a session while the display
# is not running.  Ensures sliders reset to neutral defaults instead of
# inheriting stale values from the previously loaded session.
_LIVE_DEFAULTS = {
    "carrier_frequency":        200,
    "beat_frequency":           10,
    "volume":                   80,
    "veil_opacity":             45,
    "veil_mode":                None,
    "slideshow_interval":       2.0,
    "font_switch_mode":         "intelligent",
    "center_flash_sync_to_beat": True,
    "flash_duty_cycle":         0.38,
    "flash_variance":           0.22,
    "center_flash_on_time":     120,
    "center_flash_off_time":    80,
    "shadow_opacity":           12,
    "shadow_flash_on_time":     40,
    "shadow_flash_off_time":    180,
    "spiral_style":             "tunnel_dream",
    "spiral_count":             4,
    "spiral_tightness":         5.5,
    "spiral_thickness":         14,
    "spiral_speed_multiplier":  1.0,
    "spiral_chaos":             0.12,
    "spiral_opacity":           88,
    "spiral_color_mode":        "rainbow",
    "tts_enabled":              False,
    "tts_subliminal":           False,
    "bg_mode":                  None,
    "bg_ganzfeld_gain":         0.55,
    "bg_ganzfeld_cct_k":        3200,
    "bg_ganzfeld_breath_hz":    0.05,
    "noise_color":              "pink",
    "noise_volume":             30,
}


# ── Session management constants ─────────────────────────────────────────────

_SESSION_CATEGORIES = [
    'general', 'focus', 'sleep', 'entrainment',
    'genus', 'edison', 'ssild', 'custom',
]

# Mode strip definitions — one entry per protocol quick-launch button.
# 'session' must match a folder name under sessions/.
# 'auto_start' launches the display automatically after loading.
_MODE_STRIP = [
    {
        "label":       "🧠 GENUS",
        "session":     "genus_default",
        "overrides":   {"beat_frequency": 40.0, "beat_type": "isochronic",
                        "genus_active": True},
        "auto_start":  True,
        "tooltip":     "40 Hz GENUS protocol — 1 hour",
    },
    {
        "label":       "💡 Edison",
        "session":     "edison_default",
        "overrides":   {"beat_frequency": 6.0, "beat_type": "binaural"},
        "auto_start":  True,
        "tooltip":     "Hypnagogic creativity capture",
    },
    {
        "label":       "🌙 SSILD",
        "session":     "ssild_default",
        "overrides":   {"beat_frequency": 4.0, "beat_type": "binaural"},
        "auto_start":  True,
        "tooltip":     "SSILD lucid dreaming protocol",
    },
    {
        "label":       "😴 Sleep",
        "session":     "sleep_default",
        "overrides":   {"beat_frequency": 2.0, "beat_type": "binaural"},
        "auto_start":  False,
        "tooltip":     "Sleep onset session",
    },
    {
        "label":       "🌀 Frac",
        "session":     "fractionation_30min",
        "overrides":   {"beat_frequency": 7.0, "beat_type": "binaural"},
        "auto_start":  True,
        "tooltip":     "Vogt fractionation — 30 min progressive deepening",
    },
    {
        "label":       "🎛 Free",
        "session":     "live",
        "overrides":   {},
        "auto_start":  False,
        "tooltip":     "Freeform — agent-driven or manual",
    },
]

# ── Voice input helpers ───────────────────────────────────────────────────────

class _VoiceRecorder:
    """VAD-aware microphone capture using sounddevice.

    Starts recording immediately.  Automatically stops after
    ``silence_s`` seconds of audio below ``silence_threshold`` RMS,
    then calls ``on_done(wav_bytes)`` from a background thread.

    Manual stop: call stop() at any time.
    """

    _SILENCE_THRESHOLD  = 400    # int16 RMS below this = silence
    _SILENCE_SECONDS    = 2.5    # stop after this many silent seconds (post-speech)
    _MIN_SPEECH_CHUNKS  = 5      # require ~0.5 s of speech before auto-stop is armed
    _MAX_SECONDS        = 30.0   # hard cap to avoid runaway recording

    def __init__(self, on_done, sample_rate: int = 16000):
        self._sr       = sample_rate
        self._on_done  = on_done
        self._chunks   = []
        self._stream   = None
        self._stopped  = threading.Event()

    def start(self):
        import sounddevice as sd  # noqa: PLC0415
        import numpy as np        # noqa: PLC0415
        self._chunks  = []
        self._stopped.clear()
        self._stream  = sd.InputStream(
            samplerate=self._sr, channels=1, dtype="int16",
            callback=self._cb)
        self._stream.start()
        # VAD watchdog runs in a background thread
        threading.Thread(target=self._vad_watchdog, daemon=True).start()

    def _cb(self, indata, frames, time_info, status):
        self._chunks.append(indata.copy())

    def _vad_watchdog(self):
        import numpy as np  # noqa: PLC0415
        silence_frames  = 0
        total_frames    = 0
        chunk_dur       = 0.1   # each chunk is ~100 ms
        silence_needed  = int(self._SILENCE_SECONDS / chunk_dur)
        max_chunks      = int(self._MAX_SECONDS      / chunk_dur)

        speech_detected = 0  # chunks above threshold seen so far
        prev_len = 0
        while not self._stopped.is_set():
            time.sleep(chunk_dur)
            cur_len = len(self._chunks)
            if cur_len == prev_len:
                continue
            new_chunks = self._chunks[prev_len:cur_len]
            prev_len = cur_len
            total_frames += len(new_chunks)
            for chunk in new_chunks:
                rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                if rms < self._SILENCE_THRESHOLD:
                    silence_frames += 1
                else:
                    silence_frames = 0
                    speech_detected += 1
            # Only allow auto-stop once the user has actually started speaking.
            # This prevents killing the recording during the initial ambient
            # silence before they open their mouth.
            speech_armed = speech_detected >= self._MIN_SPEECH_CHUNKS
            if (speech_armed and silence_frames >= silence_needed) \
                    or total_frames >= max_chunks:
                break
        if not self._stopped.is_set():
            self._finish()

    def _finish(self):
        if self._stopped.is_set():
            return
        self._stopped.set()
        wav = self._raw_to_wav()
        try:
            self._on_done(wav)
        except Exception as e:
            print(f"[Voice] on_done error: {e}")

    def stop(self) -> bytes:
        self._stopped.set()
        return self._raw_to_wav()

    def _raw_to_wav(self) -> bytes:
        import io, wave, numpy as np  # noqa: PLC0415
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if not self._chunks:
            return b""
        audio = np.concatenate(self._chunks, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sr)
            wf.writeframes(audio.tobytes())
        return buf.getvalue()


def _transcribe_wav(wav_bytes: bytes, base_url: str, model: str = "whisper-1",
                    language: str = "en") -> str:
    """POST wav_bytes to KoboldCpp's Whisper transcription endpoint."""
    import urllib.request, json as _json  # noqa: PLC0415

    boundary = b"somna_whisper_boundary"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n"
        + wav_bytes + b"\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="model"\r\n\r\n'
        + model.encode() + b"\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="language"\r\n\r\n'
        + language.encode() + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url = url.rstrip("/") + "/v1"
    url += "/audio/transcriptions"

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return _json.loads(resp.read()).get("text", "").strip()


def _load_whisper_cfg() -> dict:
    """Read whisper config from agent_config.yaml; returns defaults if absent."""
    try:
        import yaml  # noqa: PLC0415
        cfg_path = Path(__file__).parent / "agent_config.yaml"
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        w = data.get("whisper") or {}
        return {
            "enabled":   bool(w.get("enabled", True)),
            "model":     str(w.get("model", "whisper-1")),
            "language":  str(w.get("language", "en")),
            "base_url":  str(data.get("base_url", "http://localhost:5001")),
        }
    except Exception:
        return {"enabled": False, "model": "whisper-1", "language": "en",
                "base_url": "http://localhost:5001"}


def _load_eeg_cfg() -> dict:
    """Read EEG config from agent_config.yaml; returns safe defaults if absent."""
    try:
        import yaml  # noqa: PLC0415
        cfg_path = Path(__file__).parent / "agent_config.yaml"
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        e = data.get("eeg") or {}
        return {
            "enabled":       bool(e.get("enabled",      False)),
            "eeg_synthetic": bool(e.get("synthetic",    True)),
            "eeg_board_id":  int(e.get("board_id",      39)),
            "auto_connect":  bool(e.get("auto_connect", False)),
        }
    except Exception:
        return {"enabled": False, "eeg_synthetic": True, "eeg_board_id": 39,
                "auto_connect": False}


_USER_SETTINGS_KEYS = {
    "window_always_on_top", "window_click_through", "window_opacity",
    "tts_voice", "tts_backend", "tts_api_url", "tts_key", "window_geometry",
}


class ControlPanel:
    def __init__(self):
        try:
            self.root      = Path(__file__).parent
            self.live_file = self.root / "live_control.json"
            self._settings_file = self.root / "user_settings.json"
            self._display_proc  = None
            self._agent_proc    = None
            # Start the single-writer server before any component touches live_control.json
            self._state_server = StateServer(self.live_file).start()
            self._bin_presets   = self._load_binaural_presets()
            self._visual_presets = self._load_visual_presets()

            self.root_tk = tk.Tk()
            self.root_tk.title("Somna")
            self.root_tk.configure(bg=RP["base"])
            self.root_tk.resizable(True, True)
            self.root_tk.protocol("WM_DELETE_WINDOW", self._on_close)

            self.sync_var         = tk.BooleanVar(value=True)
            self.noise_color_var  = tk.StringVar(value="pink")
            self._noise_btns: dict = {}   # color → tk.Button for highlight updates
            self._tl_paused  = False  # local mirror of timeline paused state
            self._param_labels: dict = {}  # param_key → tk.Label (for lock gold)
            self._llm_prompt_dialog = None    # open LLM prompt popup, if any
            self._llm_prompt_timer  = None    # countdown after() id

            self._last_ui_snapshot = {}
            self._ui_syncing = False     # guard: True while syncing from JSON → sliders
            self._beats_muted = True     # cached audio_muted; updated by mute btn & refresh
            self._last_user_interaction = 0.0  # timestamp of last slider touch
            self._agent_msg_ts: float = 0.0    # ts of last agent_message handled
            self._seek_dragging = False  # True while user is dragging the seek bar
            self._vr_mode           = False   # True → pass --vr to display subprocess (SteamVR)
            self._vr_headset_proc   = None    # subprocess for vr_display_runner.py
            self._eeg_engine        = None
            self._calibrating_iaf: bool   = False   # True while IAF calibration is running
            self._cal_remaining_s: int    = 0        # local countdown (updated from live)
            self._eeg_poll_gen: int       = 0        # incremented on each new connect; cancels stale polls
            self._display_was_running: bool  = False   # for stop-transition detection
            self._display_session_start: float = 0.0   # wall time of current session start
            self._eeg_stop_thread = None   # background thread running engine.stop()
            self._eeg_cfg       = _load_eeg_cfg()
            self._apply_ttk_theme()
            self._build_ui()
            self._load_current_values()
            self._last_ui_snapshot = self._get_all_widget_values()

            # Clear any orphaned agent_message or session_time left over from a
            # previous crashed/force-killed session so the UI starts clean.
            _live = self._read_live()
            _dirty = False
            if _live.get("agent_message"):
                _live["agent_message"] = None
                _dirty = True
            if float(_live.get("session_time", 0) or 0) > 0:
                _live["session_time"] = 0
                _dirty = True
            if _dirty:
                self._atomic_save(_live)

            # ── Audio engine (binaural + noise + TTS, always on in this process) ──
            # The display subprocess uses SDL_AUDIODRIVER=dummy so it never
            # touches the audio device.  One mixer, one process — no clipping.
            self._audio_on     = False
            self._audio_engine = None
            self._tts_engine   = None
            self._audio_cfg    = None
            self._start_audio()

            self._poll_display_status()
            self._poll_agent_status()
            self._poll_session_state()
            # Stagger the remaining polls so they don't all read live_control.json
            # on the same event-loop tick — avoids a visible 500 ms hitch in the
            # waveform canvas caused by simultaneous file reads.
            self.root_tk.after(125, self._poll_playlist_state)
            self.root_tk.after(250, self._poll_ui_sync)
            self.root_tk.after(375, self._poll_audio)

            # Restore saved geometry or fall back to centered default
            self.root_tk.update_idletasks()
            saved_geo = self._read_settings().get("window_geometry")
            if saved_geo:
                self.root_tk.geometry(saved_geo)
            else:
                w, h = 1200, 1050
                sw = self.root_tk.winfo_screenwidth()
                sh = self.root_tk.winfo_screenheight()
                self.root_tk.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

            # Debounced geometry save — fires 500 ms after the last resize/move
            self._geo_save_job = None
            def _on_configure(event):
                if event.widget is not self.root_tk:
                    return
                if self._geo_save_job:
                    self.root_tk.after_cancel(self._geo_save_job)
                self._geo_save_job = self.root_tk.after(
                    500, lambda: self._save_settings(
                        {"window_geometry": self.root_tk.geometry()}
                    )
                )
            self.root_tk.bind("<Configure>", _on_configure)

            self.root_tk.mainloop()
        except Exception:
            traceback.print_exc()
            input("Press Enter to exit...")

    # ── TTK theme ─────────────────────────────────────────────────────────────

    def _apply_ttk_theme(self):
        s = ttk.Style()
        s.theme_use("clam")

        s.configure(".",
            background=RP["base"],
            foreground=RP["text"],
            font=FONT_LABEL,
            borderwidth=0,
            focuscolor=RP["iris"],
        )
        s.configure("TFrame",    background=RP["base"])
        s.configure("TLabel",    background=RP["base"], foreground=RP["text"], font=FONT_LABEL)
        s.configure("TCheckbutton",
            background=RP["base"], foreground=RP["subtle"],
            font=FONT_LABEL, indicatorcolor=RP["overlay"],
        )
        s.map("TCheckbutton",
            foreground=[("active", RP["text"]), ("selected", RP["iris"])],
            indicatorcolor=[("selected", RP["iris"])],
        )
        s.configure("TCombobox",
            fieldbackground=RP["overlay"],
            background=RP["overlay"],
            foreground=RP["text"],
            arrowcolor=RP["subtle"],
            bordercolor=RP["hl_high"],
            lightcolor=RP["overlay"],
            darkcolor=RP["overlay"],
            font=FONT_LABEL,
        )
        s.map("TCombobox",
            fieldbackground=[("readonly", RP["overlay"])],
            foreground=[("readonly", RP["text"])],
        )
        s.configure("TScrollbar",
            background=RP["overlay"],
            troughcolor=RP["surface"],
            arrowcolor=RP["subtle"],
            bordercolor=RP["surface"],
        )

    # ── Helpers for building styled widgets ───────────────────────────────────

    def _section(self, parent, title, accent=None):
        """A styled section block with a coloured title bar.
        Packed directly into its parent column frame.
        """
        accent = accent or RP["iris"]
        outer = tk.Frame(parent, bg=RP["surface"], bd=0)
        outer.pack(fill="x", pady=(0, 5))

        header = tk.Frame(outer, bg=accent, height=1)
        header.pack(fill="x")

        title_row = tk.Frame(outer, bg=RP["surface"])
        title_row.pack(fill="x", padx=10, pady=(4, 1))
        tk.Label(title_row, text=title.upper(),
                 bg=RP["surface"], fg=accent,
                 font=FONT_HEADER).pack(side="left")

        body = tk.Frame(outer, bg=RP["surface"], padx=10, pady=5)
        body.pack(fill="x")
        body.columnconfigure(1, weight=1)
        return body

    def _label(self, parent, text, row, col=0, fg=None):
        tk.Label(parent, text=text, bg=RP["surface"],
                 fg=fg or RP["subtle"], font=FONT_LABEL,
                 anchor="w").grid(row=row, column=col, sticky="w", pady=2)

    def _plabel(self, parent, text, row, param: str, col=0):
        """Like _label but registers the widget so it can turn gold when locked."""
        lbl = tk.Label(parent, text=text, bg=RP["surface"],
                       fg=RP["subtle"], font=FONT_LABEL, anchor="w")
        lbl.grid(row=row, column=col, sticky="w", pady=2)
        self._param_labels[param] = lbl

    def _slider(self, parent, row, lo, hi, res=1, default=None):
        s = tk.Scale(
            parent,
            from_=lo, to=hi, resolution=res,
            orient="horizontal",
            bg=RP["surface"],
            fg=RP["text"],
            troughcolor=RP["overlay"],
            activebackground=RP["iris"],
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            sliderlength=14,
            width=6,
            font=FONT_SMALL,
        )
        s.grid(row=row, column=1, sticky="ew", pady=2, padx=(8, 0))
        if default is not None:
            s.set(default)
        return s

    def _combobox(self, parent, values, row):
        cb = ttk.Combobox(parent, values=values, state="readonly", width=18)
        cb.grid(row=row, column=1, sticky="w", pady=3, padx=(8, 0))
        return cb

    # ── Tooltip helpers ───────────────────────────────────────────────────────
    _tip_window: object = None

    def _show_tip(self, widget, text: str):
        self._hide_tip()
        try:
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() - 24
            tw = tk.Toplevel(widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            tk.Label(tw, text=text, bg=RP["overlay"], fg=RP["text"],
                     font=FONT_SMALL, relief="flat", bd=0, padx=6, pady=3
                     ).pack()
            self._tip_window = tw
        except Exception:
            pass

    def _hide_tip(self):
        if self._tip_window:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None

    def _value_label(self, parent, var, row, fmt=None):
        """A small live readout to the right of each slider."""
        lbl = tk.Label(parent, textvariable=var,
                       bg=RP["surface"], fg=RP["muted"], font=FONT_SMALL, width=6)
        lbl.grid(row=row, column=2, sticky="w", padx=4)
        return lbl

    # ── Full UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = self.root_tk

        # Outer horizontal split: session sidebar (fixed height) | scrollable content
        outer_hbox = tk.Frame(root, bg=RP["base"])
        outer_hbox.pack(fill="both", expand=True)

        # Session column — sibling of the scrollable area so it is always anchored
        # to the window height and never stretches with scrollable content.
        # Fixed width via pack_propagate(False) prevents the unconstrained expand=True
        # inside _build_session_col from feeding back into a geometry loop.
        _col_sessions = tk.Frame(outer_hbox, bg=RP["base"], width=350)
        _col_sessions.pack(side="left", fill="y", padx=(6, 3), pady=(4, 2))
        _col_sessions.pack_propagate(False)

        # Scrollable content area (console + left/right control columns)
        content_area = tk.Frame(outer_hbox, bg=RP["base"])
        content_area.pack(side="left", fill="both", expand=True)

        self._main_canvas = tk.Canvas(content_area, bg=RP["base"], highlightthickness=0)
        self._main_canvas.pack(fill="both", expand=True)

        self._scroll_frame = tk.Frame(self._main_canvas, bg=RP["base"])
        self._scroll_frame.bind("<Configure>",
            lambda e: self._main_canvas.configure(
                scrollregion=self._main_canvas.bbox("all")))
        self._canvas_win = self._main_canvas.create_window(
            (0, 0), window=self._scroll_frame, anchor="nw")
        self._main_canvas.bind("<MouseWheel>",
            lambda e: self._main_canvas.yview_scroll(
                int(-1*(e.delta/120)), "units"))
        self._main_canvas.bind("<Configure>",
            lambda e: self._main_canvas.itemconfigure(
                self._canvas_win, width=e.width))

        # Two-column control grid: left controls | right controls
        col_outer = tk.Frame(self._scroll_frame, bg=RP["base"])
        col_outer.pack(fill="both", expand=True)
        col_outer.columnconfigure(0, weight=1, uniform="ctrl_cols")
        col_outer.columnconfigure(1, weight=1, uniform="ctrl_cols")
        col_outer.rowconfigure(0, weight=0)  # console row
        col_outer.rowconfigure(1, weight=1)  # controls row

        _col_left = tk.Frame(col_outer, bg=RP["base"])
        _col_left.grid(row=1, column=0, sticky="nsew", padx=(0, 3), pady=(2, 4))
        _col_right = tk.Frame(col_outer, bg=RP["base"])
        _col_right.grid(row=1, column=1, sticky="nsew", padx=(0, 6), pady=(2, 4))

        self._build_session_col(_col_sessions)
        self._build_console_panel(col_outer)
        self._build_left_col(_col_left)
        self._build_right_col(_col_right)
        self._build_wave_panel(col_outer)

        self._bind_controls()

    # Binaural presets: (label, carrier_hz, beat_hz, description)
    _PRESETS = [
        ("δ  Delta",  150, 2.0,  "Deep sleep / healing"),
        ("θ  Theta",  180, 6.0,  "Meditation / dreaming"),
        ("α  Alpha",  200, 10.0, "Calm focus / relaxation"),
        ("β  Beta",   220, 20.0, "Alert / problem-solving"),
        ("γ  Gamma",  300, 40.0, "Peak cognition / clarity"),
    ]

    def _apply_preset(self, carrier: float, beat: float):
        self.carrier.set(carrier)
        self.beat.set(beat)
        self._update()

    # ── Binaural preset flyout ────────────────────────────────────────────────

    def _load_binaural_presets(self) -> dict:
        """Load binaural_presets.json and group entries by brainwave band."""
        path = Path(__file__).parent / "binaural_presets.json"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            return {}
        bands: dict[str, list] = {"δ": [], "θ": [], "α": [], "β": [], "γ": []}
        for name, data in raw.items():
            beat = float(data.get("beat", 0))
            if beat <= 4.0:
                bands["δ"].append((name, data))
            elif beat <= 8.0:
                bands["θ"].append((name, data))
            elif beat <= 13.0:
                bands["α"].append((name, data))
            elif beat <= 30.0:
                bands["β"].append((name, data))
            else:
                bands["γ"].append((name, data))
        for k in bands:
            bands[k].sort(key=lambda x: float(x[1].get("beat", 0)))
        return bands

    def _make_binaural_band_btn(self, parent, label: str,
                                carrier: float, beat: float,
                                band_presets: list) -> tk.Button:
        """Band button: click = apply default, hover = flyout of named sub-presets."""
        btn = tk.Button(
            parent,
            text=label,
            font=("Segoe UI", 8, "bold"),
            bg=RP["overlay"], fg=RP["foam"],
            activebackground=RP["hl_high"], activeforeground=RP["text"],
            relief="flat", bd=0, padx=7, pady=4,
            cursor="hand2",
            command=lambda: self._apply_preset(carrier, beat),
        )
        if not band_presets:
            return btn

        state: dict = {"popup": None, "after_id": None}

        def _cancel():
            if state["after_id"]:
                btn.after_cancel(state["after_id"])
                state["after_id"] = None

        def _schedule_close():
            _cancel()
            state["after_id"] = btn.after(250, _close)

        def _close():
            _cancel()
            p = state["popup"]
            if p:
                try:
                    p.destroy()
                except Exception:
                    pass
            state["popup"] = None

        def _show():
            _cancel()
            if state["popup"] and state["popup"].winfo_exists():
                return

            top = tk.Toplevel(self.root_tk)
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            top.configure(bg=RP["pine"])   # thin 1px border effect
            state["popup"] = top

            inner = tk.Frame(top, bg=RP["overlay"], padx=1, pady=1)
            inner.pack(fill="both", expand=True)

            for pname, pdata in band_presets:
                c    = float(pdata.get("carrier", carrier))
                b    = float(pdata.get("beat", beat))
                desc = (pdata.get("desc", "") or "")[:34]

                row = tk.Frame(inner, bg=RP["overlay"], cursor="hand2")
                row.pack(fill="x")

                name_lbl = tk.Label(
                    row, text=pname,
                    bg=RP["overlay"], fg=RP["text"],
                    font=FONT_SMALL, anchor="w",
                    padx=8, pady=3, width=22, cursor="hand2",
                )
                name_lbl.pack(side="left")

                beat_lbl = tk.Label(
                    row, text=f"{b:.1f}Hz",
                    bg=RP["overlay"], fg=RP["foam"],
                    font=("Segoe UI", 7, "bold"), anchor="e",
                    padx=6, pady=3, width=7, cursor="hand2",
                )
                beat_lbl.pack(side="left")

                desc_lbl = tk.Label(
                    row, text=desc,
                    bg=RP["overlay"], fg=RP["muted"],
                    font=("Segoe UI", 7), anchor="w",
                    padx=4, pady=3, width=28, cursor="hand2",
                )
                desc_lbl.pack(side="left")

                def _row_click(e, _c=c, _b=b):
                    self._apply_preset(_c, _b)
                    _close()

                def _row_enter(e, _row=row):
                    _cancel()
                    _row.config(bg=RP["hl_low"])
                    for w in _row.winfo_children():
                        try:
                            w.config(bg=RP["hl_low"])
                        except Exception:
                            pass

                def _row_leave(e, _row=row):
                    _row.config(bg=RP["overlay"])
                    for w in _row.winfo_children():
                        try:
                            w.config(bg=RP["overlay"])
                        except Exception:
                            pass

                for widget in (row, name_lbl, beat_lbl, desc_lbl):
                    widget.bind("<Button-1>", _row_click)
                    widget.bind("<Enter>",    _row_enter)
                    widget.bind("<Leave>",    _row_leave)

            # Position popup below the button; flip above if near screen bottom
            btn.update_idletasks()
            bx = btn.winfo_rootx()
            by = btn.winfo_rooty() + btn.winfo_height() + 2
            top.update_idletasks()
            ph = top.winfo_reqheight()
            if by + ph > self.root_tk.winfo_screenheight() - 20:
                by = btn.winfo_rooty() - ph - 2
            top.geometry(f"+{bx}+{by}")

            top.bind("<Enter>", lambda e: _cancel())
            top.bind("<Leave>", lambda e: _schedule_close())

        btn.bind("<Enter>", lambda e: (btn.config(fg=RP["text"]), _show()))
        btn.bind("<Leave>", lambda e: (btn.config(fg=RP["foam"]), _schedule_close()))
        return btn

    # ── Visual presets ────────────────────────────────────────────────────────

    def _load_visual_presets(self) -> list:
        """Load visual_presets.yaml from the project root."""
        path = Path(__file__).parent / "visual_presets.yaml"
        if not path.exists():
            return []
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return data.get("presets", [])
        except Exception:
            return []

    def _apply_visual_preset(self, preset: dict):
        """Apply a visual preset: update all relevant widgets then write live."""
        if "spiral_style" in preset:
            self.spiral_style.set(preset["spiral_style"])
        if "veil_mode" in preset:
            vm = preset.get("veil_mode") or "auto"
            self.veil_mode.set(vm)
        if "beat_frequency" in preset:
            self.beat.set(float(preset["beat_frequency"]))
        if "carrier_frequency" in preset:
            self.carrier.set(float(preset["carrier_frequency"]))
        if "spiral_opacity" in preset:
            self.spiral_opac.set(float(preset["spiral_opacity"]))
        if "veil_opacity" in preset:
            self.veil_opac.set(float(preset["veil_opacity"]))
        if "shadow_opacity" in preset:
            self.shadow_opac.set(float(preset["shadow_opacity"]))
        if "spiral_color_mode" in preset:
            self.spiral_color_mode.set(preset["spiral_color_mode"])
        if "spiral_speed_multiplier" in preset:
            self.spiral_speed.set(float(preset["spiral_speed_multiplier"]))
        if "spiral_chaos" in preset:
            self.spiral_chaos.set(float(preset["spiral_chaos"]))
        if "bg_mode" in preset:
            _pm = preset.get("bg_mode") or "slideshow"
            self.bg_mode_var.set("none (transparent)" if _pm == "none" else _pm)
        if "text_color" in preset:
            tc  = preset["text_color"]
            hex_col = f"#{int(tc[0]):02x}{int(tc[1]):02x}{int(tc[2]):02x}"
            self.text_color_swatch.config(bg=hex_col)
            # Patch live_control.json directly — swatch has no tk Variable
            data = self._read_live()
            data["text_color"] = [int(tc[0]), int(tc[1]), int(tc[2])]
            self._atomic_save(data)
        self._update()

    # ── Session helpers ───────────────────────────────────────────────────────

    def _get_sessions(self) -> list[str]:
        d = self.root / "sessions"
        if not d.exists():
            return ["default"]
        return sorted(s.name for s in d.iterdir() if s.is_dir()) or ["default"]

    @staticmethod
    def _fmt_time(seconds: float, duration: float | None = None) -> str:
        t   = int(seconds)
        m, s = divmod(t, 60)
        ts  = f"{m}:{s:02d}"
        if duration:
            dm, ds = divmod(int(duration), 60)
            ts += f" / {dm}:{ds:02d}"
        return ts

    def _send_timeline_cmd(self, cmd: str):
        data = self._read_live()
        data["_timeline_cmd"] = cmd
        self._atomic_save(data)

    def _poll_session_state(self):
        """Read live state every 500 ms and refresh the session section."""
        data    = self._read_live()
        if not data:
            self.root_tk.after(500, self._poll_session_state)
            return
        t       = float(data.get("session_time",    0))
        dur     = data.get("session_duration")
        label   = data.get("timeline_label",   "")
        paused  = bool(data.get("timeline_paused",  False))
        running = self._is_running()

        # Detect display start and stop transitions for EEG session scoring.
        if running and not self._display_was_running:
            self._display_session_start = time.time()
        elif not running and self._display_was_running:
            # Display just stopped — trigger EEG session scoring asynchronously
            session_folder = data.get("session_folder", "unknown")
            duration_s     = time.time() - self._display_session_start
            if duration_s >= 60.0 and self._eeg_engine is not None:
                import threading as _threading
                _threading.Thread(
                    target=self._trigger_eeg_scoring,
                    args=(session_folder, duration_s),
                    daemon=True,
                    name="EEGScoring",
                ).start()
        self._display_was_running = running

        # Detect session-folder changes and record a play event in the DB.
        # Only count when the display is actually running — loading a session
        # without launching the display (e.g. browsing) should not count as a play.
        cur_folder = data.get("session_folder", "")
        if cur_folder and cur_folder != getattr(self, "_last_session_folder", ""):
            self._last_session_folder = cur_folder
            if running:
                try:
                    from content_tools.somna_db import record_session_played
                    record_session_played(cur_folder)
                except Exception:
                    pass

        # Dynamic divider doubles as running status indicator
        if running:
            self._queue_status_var.set("— now playing —")
            self._queue_status_lbl.config(fg=RP["foam"])
        else:
            self._queue_status_var.set("— queue —")
            self._queue_status_lbl.config(fg=RP["subtle"])

        self._sess_time_var.set(self._fmt_time(t, dur) if running else "—")
        self._sess_label_var.set(label if running else "")

        # Update seek bar position when not being dragged
        if running and dur and not self._seek_dragging:
            self._seek_bar.set(int(t / float(dur) * 1000))
        elif not running:
            self._seek_bar.set(0)

        self._refresh_mute_btn()

        # Keep local paused state in sync
        self._tl_paused = paused

        # Gold labels for user-locked parameters
        locked = set(data.get("timeline_locked_params", []))
        for param, lbl in self._param_labels.items():
            lbl.config(fg=RP["gold"] if param in locked else RP["subtle"])

        # Agent-requested display launch — agent writes this flag when it wants a
        # session started so the control panel owns the subprocess.
        if data.get("_agent_launch_display"):
            self._write_live({"_agent_launch_display": None})
            self._launch_display()

        # Agent-requested display stop — e.g. nudge session timed out with no response.
        if data.get("_agent_stop_display"):
            self._write_live({"_agent_stop_display": None})
            if self._display_proc is not None:
                self._stop_display()

        # ── Agent message channel ─────────────────────────────────────────────
        agent_msg = data.get("agent_message") or {}
        if isinstance(agent_msg, dict) and agent_msg.get("text"):
            msg_ts = float(agent_msg.get("ts", 0) or 0)
            if msg_ts > self._agent_msg_ts:
                self._agent_msg_ts = msg_ts
                msg_text      = agent_msg["text"]
                via           = agent_msg.get("via", [])
                msg_style     = agent_msg.get("style") or {}
                msg_timeout   = agent_msg.get("timeout_s")
                msg_needs_resp = bool(agent_msg.get("needs_response", False))

                # Always append to console log when "console" in via
                if "console" in via:
                    # Infer tag from message prefix / style
                    _vm = msg_style.get("voice_mode", "")
                    if msg_text.startswith("[EEG"):
                        _con_tag = "eeg"
                    elif _vm == "silent" and any(
                            w in msg_text.lower()
                            for w in ("headband", "adjust", "sqi", "signal", "quality")):
                        _con_tag = "warn"
                    else:
                        _con_tag = "agent"
                    self._console_append(f"Agent: {msg_text}", tag=_con_tag)

                # Open input dialog when needs_response (regardless of via —
                # if the overlay isn't running, the dialog is the only input path)
                if msg_needs_resp and self._llm_prompt_dialog is None:
                    self._show_llm_prompt_dialog(msg_text, msg_timeout)

        # Agent session suggestion slot
        if hasattr(self, "_suggest_frame"):
            self._poll_suggestion(data)

        self.root_tk.after(500, self._poll_session_state)

    # ── LLM prompt popup ──────────────────────────────────────────────────────

    def _show_llm_prompt_dialog(self, prompt_text: str, timeout_s=None):
        """Minimal, borderless floating input bar that appears above the display.

        Anchored to the bottom-centre of the screen so the zoomed prompt text
        in the display window is still visible above it.

        On submit  → writes user_response + response_timestamp, clears agent_message.
        On skip    → writes user_response: null, clears agent_message.
        On timeout → same as skip.
        """
        if self._llm_prompt_dialog is not None:
            return

        # Use a fresh Toplevel — overrideredirect removes the OS titlebar so
        # it looks like a pure floating panel rather than a system dialog.
        dlg = tk.Toplevel(self.root_tk)
        dlg.overrideredirect(True)
        dlg.configure(bg=RP["overlay"])
        dlg.attributes("-topmost", True)
        self._llm_prompt_dialog = dlg

        # Tell the display to yield TOPMOST while this dialog is open.
        try:
            _d = self._read_live(); _d["llm_dialog_active"] = True
            self._atomic_save(_d)
        except Exception:
            pass

        def _destroy_dialog():
            if self._llm_prompt_timer:
                self.root_tk.after_cancel(self._llm_prompt_timer)
                self._llm_prompt_timer = None
            # Cancel the keep-topmost loop before destroying
            if _topmost_id[0] is not None:
                try:
                    dlg.after_cancel(_topmost_id[0])
                except Exception:
                    pass
                _topmost_id[0] = None
            self._llm_prompt_dialog = None
            # Release the display's TOPMOST hold.
            try:
                _d2 = self._read_live(); _d2["llm_dialog_active"] = False
                self._atomic_save(_d2)
            except Exception:
                pass
            try:
                dlg.destroy()
            except Exception:
                pass

        def _submit(skip: bool = False):
            response = None if skip else entry.get("1.0", "end-1c").strip() or None
            data = self._read_live()
            data["user_response"]      = response
            data["response_timestamp"] = __import__("time").time()
            data["llm_prompt"]         = None
            data["agent_message"]      = None
            self._atomic_save(data)
            if response:
                self._console_append(f"You: {response}", tag="user")
            elif skip:
                self._console_append("You: (skipped)", tag="system")
            _destroy_dialog()

        # ── Thin iris accent bar at top ────────────────────────────────────
        tk.Frame(dlg, bg=RP["iris"], height=2).pack(fill="x")

        # ── Prompt text (italic, muted — not competing with display) ───────
        question_lbl = tk.Label(
            dlg, text=prompt_text,
            bg=RP["overlay"], fg=RP["subtle"],
            font=("Segoe UI", 10, "italic"),
            wraplength=680, justify="left", anchor="w",
            padx=14, pady=6,
        )
        question_lbl.pack(fill="x")

        # ── Input row ──────────────────────────────────────────────────────
        input_row = tk.Frame(dlg, bg=RP["hl_med"], padx=10, pady=8)
        input_row.pack(fill="x")

        entry = tk.Text(input_row, height=2, width=60,
                        bg=RP["base"], fg=RP["text"],
                        insertbackground=RP["iris"],
                        font=("Segoe UI", 11), relief="flat", wrap="word",
                        padx=10, pady=6)
        entry.pack(side="left", fill="x", expand=True)
        entry.focus_set()
        entry.bind("<Return>",         lambda _: _submit())
        entry.bind("<Control-Return>", lambda _: _submit())
        entry.bind("<Escape>",         lambda _: _submit(skip=True))

        btn_col = tk.Frame(input_row, bg=RP["hl_med"])
        btn_col.pack(side="left", padx=(8, 0))

        self._countdown_var = tk.StringVar(value="")
        tk.Label(btn_col, textvariable=self._countdown_var,
                 bg=RP["hl_med"], fg=RP["muted"],
                 font=FONT_SMALL).pack()

        tk.Button(btn_col, text="↵ Send",
                  font=FONT_SMALL,
                  bg=RP["iris"], fg=RP["base"],
                  activebackground=RP["foam"], activeforeground=RP["base"],
                  relief="flat", bd=0, padx=10, pady=4,
                  cursor="hand2",
                  command=lambda: _submit(skip=False),
                  ).pack(fill="x")
        tk.Button(btn_col, text="Skip",
                  font=FONT_SMALL,
                  bg=RP["overlay"], fg=RP["muted"],
                  activebackground=RP["hl_high"], activeforeground=RP["text"],
                  relief="flat", bd=0, padx=10, pady=2,
                  cursor="hand2",
                  command=lambda: _submit(skip=True),
                  ).pack(fill="x", pady=(4, 0))

        # ── Voice input (mic button — VAD auto-stop) ───────────────────────
        _wcfg = _load_whisper_cfg()
        if _wcfg["enabled"]:
            _rec     = [None]
            _mactive = [False]
            _mbtn    = [None]

            def _fill_entry(text: str):
                entry.delete("1.0", "end")
                entry.insert("1.0", text)
                entry.focus_set()

            def _on_audio_ready(wav: bytes):
                """Called by _VoiceRecorder from its watchdog thread."""
                _mactive[0] = False
                _rec[0]     = None
                dlg.after(0, lambda: _mbtn[0].config(
                    text="…", bg=RP["muted"], fg=RP["base"]))
                try:
                    tx = _transcribe_wav(
                        wav,
                        _wcfg["base_url"],
                        _wcfg["model"],
                        _wcfg["language"],
                    )
                    if tx:
                        dlg.after(0, lambda: _fill_entry(tx))
                except Exception as e:
                    print(f"[Voice] Transcription error: {e}")
                finally:
                    dlg.after(0, lambda: _mbtn[0].config(
                        text="🎤 Voice",
                        bg=RP["overlay"], fg=RP["muted"]))

            def _toggle_mic():
                if not _mactive[0]:
                    try:
                        r = _VoiceRecorder(on_done=_on_audio_ready)
                        r.start()
                        _rec[0]     = r
                        _mactive[0] = True
                        _mbtn[0].config(text="● Listening…",
                                        bg=RP["love"], fg=RP["base"])
                    except Exception as e:
                        print(f"[Voice] Record start error: {e}")
                else:
                    # Manual early stop
                    _mbtn[0].config(text="…", bg=RP["muted"], fg=RP["base"])
                    try:
                        wav = _rec[0].stop()
                        _mactive[0] = False
                        _rec[0]     = None
                        threading.Thread(
                            target=lambda: _on_audio_ready(wav),
                            daemon=True).start()
                    except Exception as e:
                        print(f"[Voice] Manual stop error: {e}")
                        _mactive[0] = False

            _mbtn[0] = tk.Button(
                btn_col, text="🎤 Voice",
                font=FONT_SMALL,
                bg=RP["overlay"], fg=RP["muted"],
                activebackground=RP["hl_high"], activeforeground=RP["text"],
                relief="flat", bd=0, padx=10, pady=2,
                cursor="hand2",
                command=_toggle_mic,
            )
            _mbtn[0].pack(fill="x", pady=(4, 0))

        # ── Position: bottom-centre, 80 px above the taskbar ──────────────
        dlg.update_idletasks()
        dw = dlg.winfo_reqwidth()
        dh = dlg.winfo_reqheight()
        sw = self.root_tk.winfo_screenwidth()
        sh = self.root_tk.winfo_screenheight()
        x  = (sw - dw) // 2
        y  = sh - dh - 80
        dlg.geometry(f"{dw}x{dh}+{x}+{y}")

        # ── Continuously re-assert HWND_TOPMOST ───────────────────────────
        # The pygame display window calls _apply_window_flags every ~200 ms,
        # which re-asserts its own TOPMOST and wins the z-order race.
        # We fight back with a periodic after() loop that keeps re-promoting
        # this dialog above the display until it is destroyed.
        _topmost_id = [None]

        def _keep_topmost():
            try:
                import ctypes
                if not dlg.winfo_exists():
                    return
                HWND_TOPMOST = -1
                SWP_FLAGS    = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
                # Use winfo_id() directly — GetParent on an overrideredirect WS_POPUP
                # returns the owner (control panel root), not 0, so the old
                # "GetParent(...) or winfo_id()" fallback promoted the wrong window.
                hwnd = dlg.winfo_id()
                ctypes.windll.user32.SetWindowPos(
                    hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)
                _topmost_id[0] = dlg.after(150, _keep_topmost)
            except Exception:
                pass

        try:
            import ctypes
            HWND_TOPMOST = -1
            SWP_FLAGS    = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
            hwnd = dlg.winfo_id()
            ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            _topmost_id[0] = dlg.after(150, _keep_topmost)
        except Exception:
            pass

        # ── Optional countdown ─────────────────────────────────────────────
        if timeout_s:
            remaining = [int(timeout_s)]

            def _tick():
                remaining[0] -= 1
                if remaining[0] <= 0:
                    _submit(skip=True)
                    return
                self._countdown_var.set(f"{remaining[0]}s")
                self._llm_prompt_timer = self.root_tk.after(1000, _tick)

            self._countdown_var.set(f"{remaining[0]}s")
            self._llm_prompt_timer = self.root_tk.after(1000, _tick)

    def _toggle_pause(self):
        if not self._is_running():
            return
        cmd = "resume" if self._tl_paused else "pause"
        self._send_timeline_cmd(cmd)

    def _restart_session(self):
        if not self._is_running():
            return
        self._send_timeline_cmd("restart")

    def _on_seek_release(self, _event=None):
        self._seek_dragging = False
        if not self._is_running():
            return
        data = self._read_live()
        dur  = data.get("session_duration")
        try:
            dur = float(dur)
        except (TypeError, ValueError):
            dur = 0.0
        if dur <= 0:
            return
        seek_time = float(self._seek_bar.get()) / 1000.0 * dur
        data["_timeline_cmd"] = "seek"
        data["seek_time"]     = round(seek_time, 2)
        self._atomic_save(data)

    def _get_selected_session(self) -> str:
        """Return folder name of the currently selected Treeview row."""
        sel = self._session_tv.selection()
        return sel[0] if sel else ""  # iid IS the raw session name

    def _load_session(self):
        sel = self._get_selected_session()
        if not sel:
            return
        data = self._read_live()
        data["session_folder"] = sel

        if self._is_running():
            # Display is live — send a timeline load command; it handles defaults.
            data["_timeline_cmd"] = "load"
        else:
            # Display not running — reset all visual/audio params to neutral
            # defaults, then overlay this session's YAML defaults on top.
            # This prevents stale values from the previous session persisting.
            data.update(_LIVE_DEFAULTS)
            try:
                import yaml
                yaml_path = self.root / "sessions" / sel / "session.yaml"
                if yaml_path.exists():
                    raw_yaml = yaml.safe_load(
                        yaml_path.read_text(encoding="utf-8")) or {}
                    defaults = raw_yaml.get("defaults", {})
                    if defaults:
                        # Never let a session YAML clobber user-global prefs
                        # or write metadata-only keys into live_control.json.
                        _EXCLUDED = {
                            "window_always_on_top",
                            "window_click_through",
                            "window_opacity",
                            "category",
                            "description",
                        }
                        data.update(
                            {k: v for k, v in defaults.items()
                             if k not in _EXCLUDED}
                        )
            except Exception:
                pass

        self._atomic_save(data)
        if not self._is_running():
            # Sync all sliders to match the newly written values.
            # Also refresh the snapshot so _update() won't see these as dirty.
            self._load_current_values()
            self._last_ui_snapshot = self._get_all_widget_values()
        # Refresh session panel so active-row highlight updates immediately
        if hasattr(self, "_refresh_sessions"):
            self._refresh_sessions()

    def _check_genus_safety(self, visual_enabled: bool = True) -> bool:
        """
        Show photosensitive epilepsy safety modal before the first GENUS visual session.

        Returns True if the user may proceed (either acknowledged or audio-only),
        False if they cancelled.  Stores acknowledgement in director_profile so
        the dialog only appears once per visual-enable toggle.

        genus_protocol.md §5.5 — must be shown before visual flicker is user-facing.
        """
        if not visual_enabled:
            return True   # audio-only mode is safe without the warning

        # Check stored acknowledgement
        try:
            from content_tools.somna_db import get_director_profile, _conn
            import sqlite3 as _sq
            with _conn() as c:
                row = c.execute(
                    "SELECT genus_epilepsy_ack FROM director_profile "
                    "WHERE user_id='default' LIMIT 1"
                ).fetchone()
            if row and row[0]:
                return True  # already acknowledged
        except Exception:
            pass

        # Show warning dialog
        import tkinter.messagebox as mb
        result = mb.askokcancel(
            "GENUS Safety Warning",
            "GENUS visual mode uses stroboscopic 40 Hz light flicker.\n\n"
            "⚠  WARNING: Stroboscopic visual stimulation at 40 Hz may trigger "
            "seizures in individuals with photosensitive epilepsy.\n\n"
            "If you have epilepsy, a seizure history, or photosensitive conditions, "
            "click CANCEL to use audio-only mode instead.\n\n"
            "Click OK to acknowledge that you are not photosensitive and proceed "
            "with visual flicker enabled.\n\n"
            "This warning will not be shown again once acknowledged.",
            icon="warning",
        )
        if result:
            # Store acknowledgement
            try:
                import sqlite3 as _sq2
                from content_tools.somna_db import _DB_PATH
                with _sq2.connect(str(_DB_PATH)) as c2:
                    c2.execute(
                        "UPDATE director_profile SET genus_epilepsy_ack=1 "
                        "WHERE user_id='default'"
                    )
                    if c2.rowcount == 0:
                        c2.execute(
                            "INSERT INTO director_profile (user_id, genus_epilepsy_ack) "
                            "VALUES ('default', 1)"
                        )
            except Exception:
                pass
            return True
        else:
            # User chose audio-only
            data = self._read_live()
            data["genus_visual_enabled"] = False
            self._atomic_save(data)
            return True   # still proceed, but visual disabled

    def _launch_mode(self, mode: dict):
        """Load the protocol session, or visually dismiss the button if already active."""
        session_name = mode["session"]

        # GENUS safety check: show epilepsy warning before visual flicker
        if mode.get("overrides", {}).get("genus_active"):
            live = self._read_live()
            visual_enabled = bool(live.get("genus_visual_enabled", True))
            if not self._check_genus_safety(visual_enabled):
                return

        # Toggle: clicking an already-highlighted button dismisses it without reloading.
        active = self._read_live().get("session_folder", "")
        if active == session_name and not getattr(self, "_dismissed_mode", False):
            self._dismissed_mode = True
            self._session_tv.selection_remove(self._session_tv.selection())
            # Force-dim this button immediately; highlight will stay off until
            # a new session is loaded (which clears _dismissed_mode).
            self._refresh_sessions()
            return
        self._dismissed_mode = False

        session_path = self.root / "sessions" / session_name
        if not session_path.exists():
            print(f"[Panel] Mode session not found: {session_name!r} — create the folder first.")
            return
        # Select and load (iid == session name)
        if self._session_tv.exists(session_name):
            self._session_tv.selection_set(session_name)
        self._load_session()
        # Apply protocol overrides on top of YAML defaults
        if mode.get("overrides"):
            data = self._read_live()
            data.update(mode["overrides"])
            self._atomic_save(data)
        # Auto-launch display if not already running
        if mode.get("auto_start") and not self._is_running():
            self._launch_display()

    # ── Playlist helpers ──────────────────────────────────────────────────────

    def _pl_items(self) -> list:
        return list(self._playlist_lb.get(0, "end"))

    def _pl_push_live(self):
        """Write current playlist and mode to live_control.json."""
        data = self._read_live()
        data["playlist"]       = self._pl_items()
        data["playlist_mode"]  = self._pl_mode_var.get()
        data["playlist_index"] = max(0, min(
            int(data.get("playlist_index", 0)), len(self._pl_items()) - 1))
        self._atomic_save(data)

    def _pl_add(self):
        sel = self._get_selected_session()
        if sel and sel not in self._pl_items():
            self._playlist_lb.insert("end", sel)
            self._pl_push_live()
            # Auto-expand queue section when an item is added
            if hasattr(self, "_queue_expanded") and not self._queue_expanded:
                self._queue_expanded = True
                if hasattr(self, "_queue_frame"):
                    self._queue_frame.grid()
            self._update_queue_toggle_label()

    def _pl_remove(self):
        sel = self._playlist_lb.curselection()
        if sel:
            self._playlist_lb.delete(sel[0])
            self._pl_push_live()

    def _pl_move_up(self):
        sel = self._playlist_lb.curselection()
        if not sel or sel[0] == 0:
            return
        idx = sel[0]
        item = self._playlist_lb.get(idx)
        self._playlist_lb.delete(idx)
        self._playlist_lb.insert(idx - 1, item)
        self._playlist_lb.selection_set(idx - 1)
        self._pl_push_live()

    def _pl_move_down(self):
        sel = self._playlist_lb.curselection()
        if not sel or sel[0] >= self._playlist_lb.size() - 1:
            return
        idx = sel[0]
        item = self._playlist_lb.get(idx)
        self._playlist_lb.delete(idx)
        self._playlist_lb.insert(idx + 1, item)
        self._playlist_lb.selection_set(idx + 1)
        self._pl_push_live()

    def _cycle_loop(self):
        states = ["off", "loop", "loop_one"]
        self._loop_state = states[(states.index(self._loop_state) + 1) % 3]
        self._shuffle_on = False
        self._apply_playlist_mode()

    def _toggle_shuffle(self):
        self._shuffle_on = not self._shuffle_on
        if self._shuffle_on:
            self._loop_state = "off"
        self._apply_playlist_mode()

    def _apply_playlist_mode(self):
        if self._shuffle_on:
            mode = "shuffle"
        elif self._loop_state == "loop":
            mode = "loop"
        elif self._loop_state == "loop_one":
            mode = "loop_one"
        else:
            mode = "sequential"
        self._pl_mode_var.set(mode)
        self._pl_push_live()
        self._refresh_loop_shuffle_buttons()

    def _refresh_loop_shuffle_buttons(self):
        if self._loop_state == "off":
            self._loop_btn.config(text="🔁", bg=RP["overlay"], fg=RP["muted"])
        elif self._loop_state == "loop":
            self._loop_btn.config(text="🔁", bg=RP["iris"],    fg=RP["base"])
        else:
            self._loop_btn.config(text="🔂", bg=RP["iris"],    fg=RP["base"])
        if self._shuffle_on:
            self._shuffle_btn.config(bg=RP["iris"], fg=RP["base"])
        else:
            self._shuffle_btn.config(bg=RP["overlay"], fg=RP["subtle"])

    def _sync_playlist_mode_from_live(self, mode: str):
        """Restore _loop_state / _shuffle_on from a live playlist_mode string."""
        if mode == "shuffle":
            self._shuffle_on = True
            self._loop_state = "off"
        elif mode == "loop":
            self._shuffle_on = False
            self._loop_state = "loop"
        elif mode == "loop_one":
            self._shuffle_on = False
            self._loop_state = "loop_one"
        else:
            self._shuffle_on = False
            self._loop_state = "off"
        self._refresh_loop_shuffle_buttons()

    def _toggle_audio_mute(self):
        new_val = not self._beats_muted
        self._beats_muted = new_val
        self._write_live({"audio_muted": new_val})
        self._refresh_mute_btn()

    def _refresh_mute_btn(self):
        try:
            if self._beats_muted:
                self._mute_btn.config(
                    text="\u25b6  Start Beats",
                    bg=RP["foam"], fg=RP["base"],
                    activebackground=RP["pine"],
                )
            else:
                self._mute_btn.config(
                    text="\u25a0  Stop Beats ",
                    bg=RP["overlay"], fg=RP["text"],
                    activebackground=RP["hl_high"],
                )
        except Exception:
            pass

    def _pl_next(self):
        if self._is_running():
            self._send_timeline_cmd("playlist_next")

    def _pl_prev(self):
        if self._is_running():
            self._send_timeline_cmd("playlist_prev")


    def _refresh_sessions(self, *_):
        """Repopulate the Treeview with session data from the DB."""
        try:
            from content_tools.sessions import list_sessions_with_meta
            sessions = list_sessions_with_meta()
            self._session_meta_cache = {s["name"]: s for s in sessions}
        except Exception:
            # Fallback to plain folder scan if DB is unavailable
            names   = self._get_sessions()
            sessions = [{"name": n, "description": "", "category": "general",
                         "has_timeline": True, "duration_s": 0,
                         "is_favorite": False, "last_played": None, "play_count": 0}
                        for n in names]
            self._session_meta_cache = {s["name"]: s for s in sessions}


        cat_filter = getattr(self, "_cat_filter_var", None)
        cat = cat_filter.get() if cat_filter else "All"
        sort = getattr(self, "_sort_var", None)
        sort_key = sort.get() if sort else "Recent"

        # Filter
        if cat == "Favorites":
            sessions = [s for s in sessions if s.get("is_favorite")]
        elif cat != "All":
            sessions = [s for s in sessions if s.get("category", "general") == cat]

        # Sort
        if sort_key == "Recent":
            sessions.sort(key=lambda s: s.get("last_played") or "", reverse=True)
        elif sort_key == "Most Played":
            sessions.sort(key=lambda s: s.get("play_count", 0), reverse=True)
        elif sort_key == "Duration":
            sessions.sort(key=lambda s: s.get("duration_s") or 0, reverse=True)
        elif sort_key == "Newest":
            sessions.sort(key=lambda s: s.get("created_at") or "", reverse=True)
        else:  # Name
            sessions.sort(key=lambda s: s["name"].lower())

        active = self._read_live().get("session_folder", "")
        # Detect when the active session actually changes so we can auto-scroll
        # to it exactly once.  On subsequent ticks we preserve the user's
        # current Treeview selection so they can browse without interference.
        active_changed = active != getattr(self, "_last_refresh_active", None)
        if active_changed:
            self._last_refresh_active = active

        # Remember what the user had selected before we rebuild the rows
        prev_sel = set(self._session_tv.selection())

        # Rebuild Treeview
        tv = self._session_tv
        tv.delete(*tv.get_children())
        for s in sessions:
            name  = s["name"]
            dur   = s.get("duration_s") or 0
            dur_s = f"{int(dur // 60)}m" if dur >= 60 else ("—" if dur == 0 else f"{int(dur)}s")
            cat_s = (s.get("category") or "general").title()

            # Build display name with markers
            if s.get("is_favorite"):
                disp = f"★ {name}"
                tag  = "favorite"
            elif not s.get("has_timeline", True):
                disp = f"~ {name}"
                tag  = "freeform"
            else:
                disp = name
                tag  = ""

            if name == active:
                disp = f"▸ {disp.lstrip('~ ')}"
                tag  = "active"

            # Use raw session name as iid so lookups never depend on the
            # decorated display string stored in values[0].
            tv.insert("", "end", iid=name, values=(disp, dur_s, cat_s),
                      tags=(tag,) if tag else ())

        # Auto-scroll to the newly active session only when the active
        # session just changed.  Otherwise restore the user's prior selection
        # so browsing the list is not interrupted by poll ticks.
        if active_changed and active and tv.exists(active):
            tv.selection_set(active)
            tv.see(active)
        else:
            for iid in prev_sel:
                if tv.exists(iid):
                    tv.selection_set(iid)
                    break

        # Highlight the mode strip button whose session is currently active.
        # _dismissed_mode suppresses the highlight when user clicked the active
        # button to un-select it; it clears as soon as the active session changes.
        dismissed = getattr(self, "_dismissed_mode", False)
        if active_changed and dismissed:
            # New session loaded — dismiss flag is now stale, clear it
            self._dismissed_mode = False
            dismissed = False
        for btn, sess_name in getattr(self, "_mode_btns", []):
            is_active = (active == sess_name) and not dismissed
            btn.config(
                bg=RP["pine"] if is_active else RP["overlay"],
                fg=RP["base"] if is_active else RP["text"],
            )

    def _sort_sessions_by(self, key: str):
        if hasattr(self, "_sort_var"):
            self._sort_var.set(key)

    def _on_session_double_click(self, event=None):
        """Load the selected session and start the display if it isn't already running."""
        self._load_session()
        if not self._is_running():
            self._launch_display()

    def _on_session_select(self, event=None):
        """Update info bar on single-click without loading the session."""
        sel = self._session_tv.selection()
        if not sel:
            return
        name = sel[0]  # iid is the raw session name
        meta = self._session_meta_cache.get(name, {})
        # Duration
        dur = meta.get("duration_s") or 0
        dur_s = f"{int(dur // 60)}m" if dur >= 60 else ("—" if dur == 0 else f"{int(dur)}s")
        # Last played
        last = meta.get("last_played")
        if last:
            try:
                import datetime
                dt    = datetime.datetime.fromisoformat(last)
                delta = datetime.datetime.now() - dt
                if delta.days == 0:
                    ago = "today"
                elif delta.days == 1:
                    ago = "yesterday"
                else:
                    ago = f"{delta.days}d ago"
            except Exception:
                ago = "—"
        else:
            ago = "never"
        cat   = (meta.get("category") or "general").title()
        plays = meta.get("play_count", 0)
        self._info_meta_lbl.config(
            text=f"{name}  ·  {dur_s}  ·  {cat}  ·  {ago}  ·  {plays}×"
        )
        desc = meta.get("description", "")
        self._info_desc_lbl.config(text=desc if desc else "(no description)")

    def _on_session_right_click(self, event):
        iid = self._session_tv.identify_row(event.y)
        if iid:
            self._session_tv.selection_set(iid)
        try:
            self._session_ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._session_ctx_menu.grab_release()

    def _poll_suggestion(self, data: dict):
        """Show or hide the agent suggestion slot based on live state."""
        suggestion = data.get("session_suggestion")
        if not isinstance(suggestion, dict) or not suggestion.get("text"):
            self._suggest_frame.grid_remove()
            return
        ts = float(suggestion.get("ts", 0) or 0)
        if ts != self._last_suggest_ts:
            self._last_suggest_ts = ts
            self._suggest_lbl.config(text=f"💭 {suggestion['text']}")
        self._suggest_frame.grid()

    def _accept_suggestion(self):
        data = self._read_live()
        suggestion = data.get("session_suggestion")
        if suggestion and suggestion.get("session"):
            target = suggestion["session"]
            if self._session_tv.exists(target):
                self._session_tv.selection_set(target)
            self._load_session()
        # Clear the suggestion
        data["session_suggestion"] = None
        self._atomic_save(data)
        self._suggest_frame.grid_remove()

    def _toggle_session_favorite(self):
        name = self._get_selected_session()
        if not name:
            return
        try:
            from content_tools.somna_db import toggle_favorite
            toggle_favorite(name)
            self._refresh_sessions()
        except Exception:
            pass

    def _toggle_queue_section(self):
        self._queue_expanded = not self._queue_expanded
        body = self._queue_frame.master   # session body frame (f)
        if self._queue_expanded:
            self._queue_frame.grid()
            # Give the queue row equal weight so it claims the bottom half
            body.rowconfigure(7, weight=1)
        else:
            self._queue_frame.grid_remove()
            # Release the queue row weight — treeview reclaims the full height
            body.rowconfigure(7, weight=0)
        self._update_queue_toggle_label()

    def _update_queue_toggle_label(self):
        items = self._pl_items()
        n = len(items)
        arrow = "▾" if self._queue_expanded else "▸"
        if n == 0:
            label = f"{arrow} Queue (empty)"
            fg = RP["subtle"]
        else:
            label = f"{arrow} Queue ({n} item{'s' if n != 1 else ''})"
            fg = RP["foam"]
        if hasattr(self, "_queue_toggle_btn"):
            self._queue_toggle_btn.config(text=label, fg=fg)

    def _poll_playlist_state(self):
        """Highlight the currently playing queue entry and refresh session panel."""
        data    = self._read_live()
        if not data:
            self.root_tk.after(1000, self._poll_playlist_state)
            return
        idx     = int(data.get("playlist_index", 0))
        running = self._is_running()

        # Queue highlight
        lb = self._playlist_lb
        for i in range(lb.size()):
            lb.itemconfig(i, fg=RP["gold"] if i == idx and running else RP["text"])

        # Refresh Treeview row highlights to track active session changes
        self._refresh_sessions()
        self._update_queue_toggle_label()

        self.root_tk.after(1000, self._poll_playlist_state)

    def _open_session_editor(self):
        sel = self._get_selected_session() or "default"
        session_path = self.root / "sessions" / sel
        if not session_path.exists():
            return
        from session.session_editor import SessionEditor
        SessionEditor(self.root_tk, session_path, self.live_file)

    def _new_session(self):
        import tkinter.simpledialog as sd
        raw = sd.askstring("New Session", "Session folder name:",
                           parent=self.root_tk)
        if not raw:
            return
        # Sanitise: keep alphanumeric, spaces, hyphens, underscores
        name = "".join(c for c in raw.strip() if c.isalnum() or c in " _-").strip()
        if not name:
            return
        session_path = self.root / "sessions" / name
        session_path.mkdir(parents=True, exist_ok=True)
        (session_path / "images").mkdir(exist_ok=True)
        (session_path / "fonts").mkdir(exist_ok=True)
        yaml_file = session_path / "session.yaml"
        if not yaml_file.exists():
            yaml_file.write_text(
                f'name: "{name}"\n'
                f'description: ""\n'
                f'duration: 300\n'
                f'\n'
                f'defaults:\n'
                f'  beat_frequency: 10.0\n'
                f'  carrier_frequency: 200.0\n'
                f'  volume: 80.0\n'
                f'  spiral_style: "tunnel_dream"\n'
                f'  spiral_opacity: 85\n'
                f'  veil_opacity: 40\n'
                f'\n'
                f'timeline:\n'
                f'  - t: 0\n'
                f'    label: "start"\n'
                f'    ease: "linear"\n'
                f'    params: {{}}\n',
                encoding="utf-8",
            )
        aff_file = session_path / "affirmations.txt"
        if not aff_file.exists():
            aff_file.write_text("# Add your affirmations here, one per line.\n",
                                encoding="utf-8")
        # Refresh session panel and select the new session
        self._refresh_sessions()
        for iid in self._session_tv.get_children():
            if self._session_tv.item(iid, "values")[0] == name:
                self._session_tv.selection_set(iid)
                self._session_tv.see(iid)
                break
        # Open editor immediately
        from session.session_editor import SessionEditor
        SessionEditor(self.root_tk, session_path, self.live_file)

    # ── Full-width console panel ─────────────────────────────────────────────

    # Tag definitions: (fg_color, bold)
    _CONSOLE_TAGS = {
        "agent":  (RP["iris"],   False),  # Agent speech / questions
        "eeg":    (RP["foam"],   False),  # EEG scoring / ASSR / SQI alerts
        "warn":   (RP["gold"],   False),  # Warnings, degraded signal
        "system": (RP["muted"],  False),  # Session load/stop, startup messages
        "user":   (RP["text"],   True),   # User typed input (bold)
    }

    def _build_console_panel(self, parent: tk.Frame) -> None:
        """Build the console panel that spans the two control columns at the top."""
        outer = tk.Frame(parent, bg=RP["surface"], bd=0)
        outer.grid(row=0, column=0, columnspan=2, sticky="ew",
                   padx=(0, 6), pady=(4, 2))
        outer.columnconfigure(0, weight=1)

        # 1 px accent bar — matches _section() visual language
        tk.Frame(outer, bg=RP["iris"], height=1).grid(row=0, column=0, sticky="ew")

        # ── Header bar: title + filter toggles + Memory button ───────────────
        hdr = tk.Frame(outer, bg=RP["surface"])
        hdr.grid(row=1, column=0, sticky="ew", padx=6, pady=(6, 2))
        hdr.columnconfigure(1, weight=1)
        hdr.columnconfigure(2, weight=0)
        hdr.columnconfigure(3, weight=0)

        tk.Label(hdr, text="CONSOLE", bg=RP["surface"],
                 fg=RP["iris"], font=FONT_HEADER,
                 ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        # Filter toggle buttons — one per tag type
        filter_frame = tk.Frame(hdr, bg=RP["surface"])
        filter_frame.grid(row=0, column=1, sticky="w")

        self._console_filter_vars: dict[str, tk.BooleanVar] = {}
        tag_labels = {
            "agent":  "Agent",
            "eeg":    "EEG",
            "warn":   "Warn",
            "system": "System",
            "user":   "You",
        }
        for tag, label in tag_labels.items():
            color, _ = self._CONSOLE_TAGS[tag]
            var = tk.BooleanVar(value=True)
            self._console_filter_vars[tag] = var
            tk.Checkbutton(
                filter_frame, text=label, variable=var,
                bg=RP["surface"], fg=color, selectcolor=RP["overlay"],
                activebackground=RP["surface"], activeforeground=color,
                font=FONT_SMALL, bd=0, highlightthickness=0, padx=4,
                command=lambda t=tag, v=var: self._toggle_console_tag(t, v.get()),
            ).pack(side="left")

        # Conductor FSM status — to the left of Memory button
        self._conductor_status_lbl = tk.Label(
            hdr, text="phase: —  |  frac —  |  IAF —  |  trance —",
            font=FONT_SMALL, bg=RP["surface"], fg=RP["muted"], anchor="e",
        )
        self._conductor_status_lbl.grid(row=0, column=2, sticky="e", padx=(12, 0))

        tk.Button(
            hdr, text="Memory", font=FONT_SMALL,
            bg=RP["overlay"], fg=RP["subtle"],
            activebackground=RP["hl_high"], activeforeground=RP["text"],
            relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
            command=self._show_memory_dialog,
        ).grid(row=0, column=3, sticky="e", padx=(8, 0))

        # ── Log text widget ───────────────────────────────────────────────────
        log_outer = tk.Frame(outer, bg=RP["overlay"], bd=0)
        log_outer.grid(row=2, column=0, sticky="ew", padx=6)
        log_outer.columnconfigure(0, weight=1)

        self._console_log = tk.Text(
            log_outer, height=10, state="disabled", wrap="word",
            bg=RP["overlay"], fg=RP["text"], font=FONT_SMALL,
            relief="flat", bd=0, highlightthickness=0,
            insertbackground=RP["text"], padx=6, pady=4,
        )
        _scroll = tk.Scrollbar(log_outer, orient="vertical",
                               command=self._console_log.yview,
                               bg=RP["overlay"], troughcolor=RP["surface"])
        _scroll.pack(side="right", fill="y")
        self._console_log.pack(side="left", fill="both", expand=True)
        self._console_log.config(yscrollcommand=_scroll.set)

        # Configure text tags for each category
        for tag, (color, bold) in self._CONSOLE_TAGS.items():
            font = (FONT_SMALL[0], FONT_SMALL[1], "bold") if bold else FONT_SMALL
            self._console_log.tag_configure(tag, foreground=color, font=font)
        # Timestamp tag — muted, always visible
        self._console_log.tag_configure(
            "ts", foreground=RP["muted"], font=FONT_SMALL)

        # ── Input bar ────────────────────────────────────────────────────────
        input_row = tk.Frame(outer, bg=RP["surface"])
        input_row.grid(row=3, column=0, sticky="ew", padx=6, pady=(4, 6))
        input_row.columnconfigure(0, weight=1)

        self._console_entry = tk.Entry(
            input_row, bg=RP["overlay"], fg=RP["text"],
            insertbackground=RP["text"],
            relief="flat", bd=0, font=FONT_SMALL,
        )
        self._console_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=4)
        self._console_entry.bind("<Return>", lambda _: self._send_console_input())

        tk.Button(
            input_row, text="Send", font=FONT_SMALL,
            bg=RP["iris"], fg=RP["base"],
            activebackground=RP["foam"], activeforeground=RP["base"],
            relief="flat", bd=0, padx=12, pady=3,
            cursor="hand2", command=self._send_console_input,
        ).grid(row=0, column=1)

    def _toggle_console_tag(self, tag: str, visible: bool) -> None:
        """Show or hide a message category in the console log."""
        self._console_log.config(state="normal")
        self._console_log.tag_configure(tag, elide=not visible)
        # The timestamp line for each hidden tag should also elide
        self._console_log.tag_configure(f"ts_{tag}", elide=not visible)
        self._console_log.config(state="disabled")

    # ── Left column: Session · Binaural · TTS ────────────────────────────────
    # Session and Playlist are merged into a single compact panel.

    def _build_session_col(self, parent):
        # ── Session panel ─────────────────────────────────────────────────
        f = self._section(parent, "Session", RP["iris"])
        # Make the section body and its outer frame fill the full column height
        f.master.pack_configure(fill="both", expand=True)
        f.pack_configure(fill="both", expand=True)

        # ── Tier 1: Mode strip ────────────────────────────────────────────
        mode_row = tk.Frame(f, bg=RP["surface"])
        mode_row.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        mode_row.columnconfigure(tuple(range(len(_MODE_STRIP))), weight=1)
        self._mode_btns: list = []
        for col, mode in enumerate(_MODE_STRIP):
            btn = tk.Button(
                mode_row, text=mode["label"], font=FONT_SMALL,
                bg=RP["overlay"], fg=RP["text"],
                activebackground=RP["hl_high"], activeforeground=RP["text"],
                relief="flat", bd=0, pady=3, cursor="hand2",
                command=lambda m=mode: self._launch_mode(m),
            )
            btn.grid(row=0, column=col, sticky="ew",
                     padx=(0, 2) if col < len(_MODE_STRIP) - 1 else 0)
            self._mode_btns.append((btn, mode["session"]))
            # Tooltip on hover
            _tip_text = mode.get("tooltip", mode.get("label", ""))
            btn.bind("<Enter>", lambda e, b=btn, t=_tip_text: self._show_tip(b, t))
            btn.bind("<Leave>", lambda e: self._hide_tip())

        # ── Tier 2: Filter / sort bar ─────────────────────────────────────
        filter_row = tk.Frame(f, bg=RP["surface"])
        filter_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 3))
        filter_row.columnconfigure(1, weight=1)
        filter_row.columnconfigure(3, weight=1)

        tk.Label(filter_row, text="Filter:", bg=RP["surface"], fg=RP["subtle"],
                 font=FONT_SMALL).grid(row=0, column=0, padx=(0, 3))
        self._cat_filter_var = tk.StringVar(value="All")
        self._cat_filter_cb = ttk.Combobox(
            filter_row, textvariable=self._cat_filter_var,
            values=["All", "Favorites"] + _SESSION_CATEGORIES,
            state="readonly", font=FONT_SMALL, width=10,
        )
        self._cat_filter_cb.grid(row=0, column=1, sticky="ew")

        tk.Label(filter_row, text="Sort:", bg=RP["surface"], fg=RP["subtle"],
                 font=FONT_SMALL).grid(row=0, column=2, padx=(6, 3))
        self._sort_var = tk.StringVar(value="Recent")
        self._sort_cb = ttk.Combobox(
            filter_row, textvariable=self._sort_var,
            values=["Recent", "Most Played", "Name", "Duration", "Newest"],
            state="readonly", font=FONT_SMALL, width=10,
        )
        self._sort_cb.grid(row=0, column=3, sticky="ew")

        # ── Tier 2: Treeview library ──────────────────────────────────────
        # Row 2 is the elastic "sessions" half — it expands to fill available height.
        # Row 7 (queue frame) gets weight=1 only when the queue is open, giving a
        # 50/50 split between treeview and queue.
        f.rowconfigure(2, weight=1)

        tv_outer = tk.Frame(f, bg=RP["surface"])
        tv_outer.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(0, 3))
        tv_outer.columnconfigure(0, weight=1)
        tv_outer.rowconfigure(0, weight=1)

        # Style Treeview to match Rosé Pine dark theme (done once at panel build)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Session.Treeview",
                         background=RP["overlay"], foreground=RP["text"],
                         fieldbackground=RP["overlay"],
                         rowheight=18, font=FONT_SMALL,
                         bordercolor=RP["hl_med"], borderwidth=0)
        style.configure("Session.Treeview.Heading",
                         background=RP["hl_med"], foreground=RP["subtle"],
                         font=FONT_SMALL, relief="flat", borderwidth=0)
        style.map("Session.Treeview",
                  background=[("selected", RP["iris"])],
                  foreground=[("selected", RP["base"])])

        self._session_tv = ttk.Treeview(
            tv_outer, style="Session.Treeview",
            columns=("name", "dur", "cat"),
            show="headings", height=7, selectmode="browse",
        )
        self._session_tv.heading("name", text="Name",
                                 command=lambda: self._sort_sessions_by("Name"))
        self._session_tv.heading("dur",  text="Dur",
                                 command=lambda: self._sort_sessions_by("Duration"))
        self._session_tv.heading("cat",  text="Category",
                                 command=lambda: self._sort_sessions_by("Name"))
        self._session_tv.column("name", width=140, stretch=True,  anchor="w")
        self._session_tv.column("dur",  width=32,  stretch=False, anchor="e")
        self._session_tv.column("cat",  width=70,  stretch=False, anchor="w")
        self._session_tv.grid(row=0, column=0, sticky="nsew")
        # No visible scrollbar — mouse wheel and keyboard work fine.
        # A native ttk scrollbar on Windows renders with OS chrome that doesn't
        # match the dark theme, and the era of always-visible scrollbars has passed.

        # Row tags for state colouring
        self._session_tv.tag_configure("active",   foreground=RP["pine"])
        self._session_tv.tag_configure("favorite", foreground=RP["gold"])
        self._session_tv.tag_configure("freeform", foreground=RP["subtle"])

        # Right-click context menu
        self._session_ctx_menu = tk.Menu(self.root_tk, tearoff=0,
                                         bg=RP["overlay"], fg=RP["text"],
                                         activebackground=RP["hl_high"],
                                         activeforeground=RP["text"],
                                         relief="flat", bd=1)
        self._session_ctx_menu.add_command(label="Toggle ★ Favorite",
                                            command=self._toggle_session_favorite)
        self._session_ctx_menu.add_command(label="Add to Queue",
                                            command=self._pl_add)
        self._session_ctx_menu.add_command(label="✏ Edit",
                                            command=self._open_session_editor)

        # ── Info bar ──────────────────────────────────────────────────────
        self._info_meta_lbl = tk.Label(
            f, text="", bg=RP["surface"], fg=RP["subtle"],
            font=FONT_SMALL, anchor="w",
        )
        self._info_meta_lbl.grid(row=3, column=0, columnspan=3,
                                  sticky="ew", pady=(0, 1))
        self._info_desc_lbl = tk.Label(
            f, text="", bg=RP["surface"], fg=RP["muted"],
            font=FONT_SMALL, anchor="nw", justify="left",
        )
        self._info_desc_lbl.grid(row=4, column=0, columnspan=3, sticky="ew")
        # Bind width changes so wraplength tracks the column width
        self._info_desc_lbl.bind(
            "<Configure>",
            lambda e: self._info_desc_lbl.config(wraplength=e.width - 4),
        )

        # Action buttons row: + New, ✏ Edit — evenly split across full width
        action_row = tk.Frame(f, bg=RP["surface"])
        action_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=1)
        tk.Button(action_row, text="+ New", font=FONT_SMALL,
                  bg=RP["pine"], fg=RP["base"],
                  activebackground=RP["foam"], activeforeground=RP["base"],
                  relief="flat", bd=0, pady=3,
                  cursor="hand2", command=self._new_session,
                  ).grid(row=0, column=0, sticky="ew", padx=(0, 2))
        tk.Button(action_row, text="✏ Edit", font=FONT_SMALL,
                  bg=RP["overlay"], fg=RP["subtle"],
                  activebackground=RP["hl_high"], activeforeground=RP["text"],
                  relief="flat", bd=0, pady=3,
                  cursor="hand2", command=self._open_session_editor,
                  ).grid(row=0, column=1, sticky="ew")

        # Bind Treeview events
        self._session_tv.bind("<<TreeviewSelect>>", self._on_session_select)
        self._session_tv.bind("<Double-Button-1>",  self._on_session_double_click)
        self._session_tv.bind("<Return>",            lambda _: self._load_session())
        self._session_tv.bind("<Button-3>",          self._on_session_right_click)
        self._cat_filter_var.trace_add("write", lambda *_: self._refresh_sessions())
        self._sort_var.trace_add("write",       lambda *_: self._refresh_sessions())

        # Store session meta cache for info bar lookups
        self._session_meta_cache: dict = {}

        # Populate on startup
        self._refresh_sessions()

        # ── Tier 3: Collapsible queue ─────────────────────────────────────
        self._queue_expanded = False
        queue_toggle_row = tk.Frame(f, bg=RP["surface"])
        queue_toggle_row.grid(row=6, column=0, columnspan=3, sticky="ew",
                               pady=(4, 0))
        self._queue_toggle_btn = tk.Button(
            queue_toggle_row, text="▸ Queue (empty)", font=FONT_SMALL,
            bg=RP["surface"], fg=RP["subtle"],
            activebackground=RP["hl_low"], activeforeground=RP["text"],
            relief="flat", bd=0, anchor="w", cursor="hand2",
            command=self._toggle_queue_section,
        )
        self._queue_toggle_btn.pack(side="left", fill="x", expand=True)

        self._queue_frame = tk.Frame(f, bg=RP["surface"])
        self._queue_frame.grid(row=7, column=0, columnspan=3, sticky="nsew")
        self._queue_frame.grid_remove()  # hidden by default

        queue_inner = tk.Frame(self._queue_frame, bg=RP["overlay"])
        queue_inner.pack(fill="both", expand=True)
        queue_inner.columnconfigure(0, weight=1)

        self._playlist_lb = tk.Listbox(
            queue_inner, height=4,
            bg=RP["overlay"], fg=RP["text"],
            selectbackground=RP["pine"], selectforeground=RP["base"],
            font=FONT_SMALL, relief="flat", bd=0,
            activestyle="none",
        )
        self._playlist_lb.pack(side="left", fill="both", expand=True)

        _pl_scroll = tk.Scrollbar(queue_inner, orient="vertical",
                                  command=self._playlist_lb.yview,
                                  bg=RP["overlay"], troughcolor=RP["surface"])
        _pl_scroll.pack(side="left", fill="y")
        self._playlist_lb.config(yscrollcommand=_pl_scroll.set)

        queue_btns = tk.Frame(self._queue_frame, bg=RP["surface"])
        queue_btns.pack(fill="x", pady=(2, 0))
        for sym, cmd in [("▲", self._pl_move_up), ("▼", self._pl_move_down),
                          ("🗑", self._pl_remove), ("+ Add", self._pl_add)]:
            tk.Button(queue_btns, text=sym, font=FONT_SMALL,
                      bg=RP["overlay"], fg=RP["text"],
                      activebackground=RP["hl_high"], activeforeground=RP["text"],
                      relief="flat", bd=0, padx=6, pady=2, cursor="hand2",
                      command=cmd).pack(side="left", padx=(0, 2))
        # Shuffle lives here now — only relevant when there's a queue
        self._shuffle_btn = tk.Button(
            queue_btns, text="🔀", font=FONT_SMALL,
            bg=RP["overlay"], fg=RP["subtle"],
            activebackground=RP["hl_high"], activeforeground=RP["text"],
            relief="flat", bd=0, padx=6, pady=2, cursor="hand2",
            command=self._toggle_shuffle,
        )
        self._shuffle_btn.pack(side="right")

        # ── Agent suggestion slot ─────────────────────────────────────────
        self._suggest_frame = tk.Frame(f, bg=RP["hl_low"])
        self._suggest_frame.grid(row=8, column=0, columnspan=3, sticky="ew",
                                  pady=(4, 0))
        self._suggest_frame.grid_remove()  # hidden until agent writes a suggestion

        self._suggest_lbl = tk.Label(
            self._suggest_frame, text="", bg=RP["hl_low"], fg=RP["iris"],
            font=FONT_SMALL, anchor="w", wraplength=230,
        )
        self._suggest_lbl.pack(side="left", fill="x", expand=True, padx=(6, 0),
                                pady=4)
        tk.Button(
            self._suggest_frame, text="Go", font=FONT_SMALL,
            bg=RP["iris"], fg=RP["base"],
            activebackground=RP["foam"], activeforeground=RP["base"],
            relief="flat", bd=0, padx=8, pady=3, cursor="hand2",
            command=self._accept_suggestion,
        ).pack(side="right", padx=(0, 4), pady=4)

        # ── Compat shims for code that still references old vars ──────────
        # _queue_status_var / _queue_status_lbl kept as no-op stubs so that
        # _poll_session_state's existing references compile without error.
        self._queue_status_var = tk.StringVar(value="")
        self._queue_status_lbl = tk.Label(f, textvariable=self._queue_status_var,
                                           bg=RP["surface"], fg=RP["subtle"],
                                           font=("Segoe UI", 7))
        self._sess_time_var  = tk.StringVar(value="—")
        self._sess_label_var = tk.StringVar(value="")
        self._last_suggest_ts = 0.0

        # ── Launch buttons — one horizontal row ──────────────────────────
        btns_row = tk.Frame(f, bg=RP["surface"])
        btns_row.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        btns_row.columnconfigure((0, 1, 2), weight=1, uniform="btns")

        self.agent_btn = tk.Button(
            btns_row,
            text="✦  Start Agent",
            font=FONT_LAUNCH,
            bg=RP["gold"], fg=RP["base"],
            activebackground=RP["rose"], activeforeground=RP["base"],
            relief="flat", bd=0, pady=6,
            cursor="hand2", command=self._toggle_agent,
        )
        self.agent_btn.grid(row=0, column=0, sticky="ew", padx=(0, 1))

        self.launch_btn = tk.Button(
            btns_row,
            text="▶  Start Session",
            font=FONT_LAUNCH,
            bg=RP["pine"], fg=RP["base"],
            activebackground=RP["foam"], activeforeground=RP["base"],
            relief="flat", bd=0, pady=6,
            cursor="hand2", command=self._toggle_display,
        )
        self.launch_btn.grid(row=0, column=1, sticky="ew", padx=(1, 1))

        self._mute_btn = tk.Button(
            btns_row,
            text="▶  Start Beats",
            font=FONT_LAUNCH,
            bg=RP["foam"], fg=RP["base"],
            activebackground=RP["pine"], activeforeground=RP["base"],
            relief="flat", bd=0, pady=6,
            cursor="hand2", command=self._toggle_audio_mute,
        )
        self._mute_btn.grid(row=0, column=2, sticky="ew", padx=(1, 0))

        # Playlist mode state
        self._pl_mode_var = tk.StringVar(value="sequential")
        self._loop_state  = "off"   # "off" / "loop" / "loop_one"
        self._shuffle_on  = False

        # ── Transport bar: [seek──────────] timer 🔁 🥽 ──────────────────
        def _tbtn(parent, text, command, **kw):
            opts = {
                "bg": RP["overlay"], "fg": RP["text"],
                "activebackground": RP["hl_high"], "activeforeground": RP["text"],
                "relief": "flat", "bd": 0, "width": 3, "pady": 2,
                "cursor": "hand2", "command": command,
            }
            opts.update(kw)
            return tk.Button(parent, text=text, font=FONT_SMALL, **opts)

        transport_bar = tk.Frame(f, bg=RP["surface"])
        transport_bar.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(2, 4))

        # Right-side: timer · 🔁 · 🥽
        _tpad = (1, 0)

        self._vr_btn = _tbtn(transport_bar, "🥽", self._toggle_vr_mode,
                             fg=RP["muted"])
        self._vr_btn.pack(side="right", padx=_tpad)

        self._loop_btn = _tbtn(transport_bar, "🔁", self._cycle_loop,
                               fg=RP["muted"])
        self._loop_btn.pack(side="right", padx=_tpad)

        tk.Label(
            transport_bar, textvariable=self._sess_time_var,
            bg=RP["surface"], fg=RP["foam"],
            font=("Segoe UI", 9, "bold"),
        ).pack(side="right", padx=_tpad)

        # Seek bar — same style as every other slider in the panel
        self._seek_bar = tk.Scale(
            transport_bar,
            orient="horizontal", from_=0, to=1000, resolution=1,
            showvalue=False, takefocus=False,
            bg=RP["surface"], fg=RP["text"],
            troughcolor=RP["overlay"],
            activebackground=RP["iris"],
            highlightthickness=0, bd=0,
            sliderrelief="flat", sliderlength=14, width=6,
            font=FONT_SMALL,
        )
        self._seek_bar.pack(side="left", fill="x", expand=True, padx=(2, 0))
        self._seek_bar.bind("<ButtonPress-1>",
                            lambda e: setattr(self, "_seek_dragging", True))
        self._seek_bar.bind("<ButtonRelease-1>", self._on_seek_release)

    def _build_left_col(self, parent):
        # ── Binaural Beats ────────────────────────────────────────────────
        f = self._section(parent, "Binaural Beats", RP["foam"])

        preset_row = tk.Frame(f, bg=RP["surface"])
        preset_row.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        for label, carrier, beat, _tip in self._PRESETS:
            band_sym = label[0]
            btn = self._make_binaural_band_btn(
                preset_row, label, carrier, beat,
                self._bin_presets.get(band_sym, []),
            )
            btn.pack(side="left", padx=(0, 4))

        self._plabel(f, "Carrier (Hz)", 1, "carrier_frequency")
        self.carrier = self._slider(f, 1, 80, 400)
        self._plabel(f, "Beat Δ (Hz)", 2, "beat_frequency")
        self.beat = self._slider(f, 2, 0.5, 40, res=0.1)
        self._plabel(f, "Volume", 3, "volume")
        self.volume = self._slider(f, 3, 0, 100)

        self._plabel(f, "Beat Type", 4, "beat_type")
        self.beat_type = self._combobox(
            f, ["binaural", "isochronic", "both"], 4,
        )
        self.beat_type.set("binaural")
        self._plabel(f, "AM Depth", 5, "am_depth")
        self.am_depth = self._slider(f, 5, 0.0, 1.0, res=0.01)
        self._plabel(f, "Spectral Tilt", 6, "noise_spectral_tilt")
        self.noise_spectral_tilt = self._slider(f, 6, 0.5, 3.0, res=0.05)
        self._plabel(f, "Bin. Blend", 7, "binaural_blend")
        self.binaural_blend = self._slider(f, 7, 0.0, 1.0, res=0.01)

        # ── Colored noise ─────────────────────────────────────────────────
        self._label(f, "Noise Color", 8)
        noise_btn_row = tk.Frame(f, bg=RP["surface"])
        noise_btn_row.grid(row=8, column=1, columnspan=2, sticky="w",
                           padx=(4, 0), pady=(4, 2))

        # Color meta: (key, display label, hex bg when active)
        _noise_meta = [
            ("off",    "Off",    RP["muted"]),
            ("white",  "White",  "#e4e0e6"),
            ("pink",   "Pink",   "#eb6f92"),
            ("brown",  "Brown",  "#c4845a"),
            ("blue",   "Blue",   "#569fba"),
            ("violet", "Violet", "#c4a7e7"),
            ("grey",   "Grey",   "#9893a5"),
        ]
        for key, lbl, active_bg in _noise_meta:
            btn = tk.Button(
                noise_btn_row, text=lbl, font=FONT_SMALL,
                bg=RP["overlay"], fg=RP["subtle"],
                activebackground=active_bg, activeforeground=RP["base"],
                relief="flat", bd=0, padx=6, pady=2,
                command=lambda k=key, ab=active_bg: self._set_noise_color(k, ab),
            )
            btn.pack(side="left", padx=(0, 3))
            self._noise_btns[key] = (btn, active_bg)

        self._plabel(f, "Noise Vol", 9, "noise_volume")
        self.noise_vol = self._slider(f, 9, 0, 100)

        # ── Breath coupling (respiratory entrainment) ──────────────────────
        self._label(f, "Breath Coupling", 10)
        breath_row = tk.Frame(f, bg=RP["surface"])
        breath_row.grid(row=10, column=1, columnspan=2, sticky="w", padx=(4, 0))
        self._breath_mod_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            breath_row, text="enabled", variable=self._breath_mod_var,
            bg=RP["surface"], fg=RP["subtle"], selectcolor=RP["overlay"],
            activebackground=RP["surface"], activeforeground=RP["text"],
            font=FONT_SMALL, bd=0, highlightthickness=0,
            command=self._update,
        ).pack(side="left")

        self._plabel(f, "Breath Rate (Hz)", 11, "breath_rate")
        self.breath_rate = self._slider(f, 11, 0.04, 0.20, res=0.01)
        self._plabel(f, "Breath Depth", 12, "breath_depth")
        self.breath_depth = self._slider(f, 12, 0.0, 0.50, res=0.01)

        # Highlight current selection on startup
        self._refresh_noise_btn_highlights(self.noise_color_var.get())

        # ── TTS ───────────────────────────────────────────────────────────
        f = self._section(parent, "Voice", RP["rose"])

        # Row 0: TTS on + SSB subliminal (inline) + ••• server settings toggle
        tts_en_row = tk.Frame(f, bg=RP["surface"])
        tts_en_row.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.tts_enabled = tk.BooleanVar(value=False)
        tk.Checkbutton(tts_en_row, text="TTS on", variable=self.tts_enabled,
                       bg=RP["surface"], fg=RP["text"],
                       activebackground=RP["surface"], activeforeground=RP["text"],
                       selectcolor=RP["overlay"], font=FONT_LABEL,
                       command=self._update).pack(side="left")
        self.tts_subliminal = tk.BooleanVar(value=False)
        tk.Checkbutton(tts_en_row, text="SSB subliminal", variable=self.tts_subliminal,
                       bg=RP["surface"], fg=RP["text"],
                       activebackground=RP["surface"], activeforeground=RP["text"],
                       selectcolor=RP["overlay"], font=FONT_LABEL,
                       command=self._update).pack(side="left", padx=(12, 0))
        self._tts_adv_visible = False
        self._tts_adv_btn = tk.Button(
            tts_en_row, text="•••", font=FONT_SMALL,
            bg=RP["surface"], fg=RP["muted"],
            activebackground=RP["hl_high"], activeforeground=RP["text"],
            relief="flat", bd=0, padx=6, pady=1, cursor="hand2",
            command=self._toggle_tts_adv,
        )
        self._tts_adv_btn.pack(side="right")

        # Backend selector — hidden by default (in ••• panel)
        self._tts_backend_lbl = tk.Label(f, text="Backend", bg=RP["surface"],
                                         fg=RP["subtle"], font=FONT_LABEL, anchor="w")
        self._tts_backend_lbl.grid(row=1, column=0, sticky="w", pady=2)
        self.tts_backend = tk.StringVar(value="edge")
        self._tts_backend_row = tk.Frame(f, bg=RP["surface"])
        self._tts_backend_row.grid(row=1, column=1, columnspan=2, sticky="w", padx=(8, 0))
        for val, lbl in [("edge", "Edge (free)"), ("openai", "OpenAI"), ("local", "Local API")]:
            tk.Radiobutton(self._tts_backend_row, text=lbl, variable=self.tts_backend, value=val,
                           bg=RP["surface"], fg=RP["subtle"],
                           activebackground=RP["surface"], activeforeground=RP["text"],
                           selectcolor=RP["overlay"], font=FONT_SMALL,
                           command=self._on_tts_backend_change).pack(side="left", padx=(0, 8))
        self._tts_backend_lbl.grid_remove()
        self._tts_backend_row.grid_remove()

        # Voice — hidden by default (in ••• panel, row 2)
        self._tts_voice_lbl = tk.Label(f, text="Voice", bg=RP["surface"],
                                       fg=RP["subtle"], font=FONT_LABEL, anchor="w")
        self._tts_voice_lbl.grid(row=2, column=0, sticky="w", pady=2)
        self.tts_voice = tk.StringVar(value="en-US-JennyNeural")
        self._tts_voice_entry = tk.Entry(f, textvariable=self.tts_voice,
                                         bg=RP["overlay"], fg=RP["text"],
                                         insertbackground=RP["text"],
                                         font=FONT_LABEL, relief="flat", width=22)
        self._tts_voice_entry.grid(row=2, column=1, columnspan=2, sticky="ew",
                                   padx=(8, 0), pady=2)
        self._tts_voice_entry.bind("<Return>",   self._update)
        self._tts_voice_entry.bind("<FocusOut>", self._update)
        self._tts_voice_lbl.grid_remove()
        self._tts_voice_entry.grid_remove()

        # API URL — hidden by default (in ••• panel)
        self._tts_url_lbl = tk.Label(f, text="API URL", bg=RP["surface"],
                                     fg=RP["subtle"], font=FONT_LABEL, anchor="w")
        self._tts_url_lbl.grid(row=3, column=0, sticky="w", pady=2)
        self.tts_api_url = tk.StringVar(value="http://localhost:8020")
        self._tts_url_entry = tk.Entry(f, textvariable=self.tts_api_url,
                                       bg=RP["overlay"], fg=RP["muted"],
                                       insertbackground=RP["text"],
                                       font=FONT_LABEL, relief="flat", width=24)
        self._tts_url_entry.grid(row=3, column=1, columnspan=2, sticky="ew",
                                 padx=(8, 0), pady=2)
        self._tts_url_lbl.grid_remove()
        self._tts_url_entry.grid_remove()

        # API Key — hidden by default (in ••• panel)
        self._tts_key_lbl = tk.Label(f, text="API Key", bg=RP["surface"],
                                     fg=RP["subtle"], font=FONT_LABEL, anchor="w")
        self._tts_key_lbl.grid(row=4, column=0, sticky="w", pady=2)
        self.tts_api_key = tk.StringVar(value="none")
        self._tts_key_entry = tk.Entry(f, textvariable=self.tts_api_key,
                                       bg=RP["overlay"], fg=RP["muted"],
                                       insertbackground=RP["text"],
                                       font=FONT_LABEL, relief="flat", width=24,
                                       show="•")
        self._tts_key_entry.grid(row=4, column=1, columnspan=2, sticky="ew",
                                 padx=(8, 0), pady=2)
        self._tts_key_lbl.grid_remove()
        self._tts_key_entry.grid_remove()

        # Volume (row 5)
        self._label(f, "Volume", 5)
        self.tts_volume = tk.DoubleVar(value=65.0)
        tk.Scale(f, variable=self.tts_volume, from_=0, to=100,
                 orient="horizontal", resolution=1,
                 bg=RP["surface"], fg=RP["text"], troughcolor=RP["overlay"],
                 activebackground=RP["iris"], highlightthickness=0,
                 bd=0, sliderrelief="flat", sliderlength=14, width=6,
                 font=FONT_SMALL, command=lambda _: self._update(),
                 ).grid(row=5, column=1, sticky="ew", padx=(8, 0), pady=2)

        # Subliminal volume + carrier (rows 6–7)
        self._label(f, "S. volume", 6)
        self.tts_subli_vol = tk.DoubleVar(value=20.0)
        tk.Scale(f, variable=self.tts_subli_vol, from_=0, to=100,
                 orient="horizontal", resolution=1,
                 bg=RP["surface"], fg=RP["text"], troughcolor=RP["overlay"],
                 activebackground=RP["iris"], highlightthickness=0,
                 bd=0, sliderrelief="flat", sliderlength=14, width=6,
                 font=FONT_SMALL, command=lambda _: self._update(),
                 ).grid(row=6, column=1, sticky="ew", padx=(8, 0), pady=2)

        self._label(f, "Carrier Hz", 7)
        self.tts_subli_hz = tk.DoubleVar(value=16000.0)
        tk.Scale(f, variable=self.tts_subli_hz, from_=14000, to=20000,
                 orient="horizontal", resolution=100,
                 bg=RP["surface"], fg=RP["text"], troughcolor=RP["overlay"],
                 activebackground=RP["iris"], highlightthickness=0,
                 bd=0, sliderrelief="flat", sliderlength=14, width=6,
                 font=FONT_SMALL, command=lambda _: self._update(),
                 ).grid(row=7, column=1, sticky="ew", padx=(8, 0), pady=2)

        self._on_tts_backend_change()   # set initial entry states

        # ── EEG / Biofeedback ─────────────────────────────────────────────
        f = self._section(parent, "Brainwave Monitor", RP["pine"])

        # Connect / Disconnect row
        eeg_top = tk.Frame(f, bg=RP["surface"])
        eeg_top.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))

        self._eeg_connect_btn = tk.Button(
            eeg_top, text="Connect EEG",
            font=FONT_SMALL,
            bg=RP["overlay"], fg=RP["foam"],
            activebackground=RP["hl_high"], activeforeground=RP["text"],
            relief="flat", bd=0, padx=10, pady=3,
            cursor="hand2", command=self._toggle_eeg,
        )
        self._eeg_connect_btn.pack(side="left")

        self._eeg_status_lbl = tk.Label(
            eeg_top, text="disconnected",
            font=FONT_SMALL, bg=RP["surface"], fg=RP["muted"],
        )
        self._eeg_status_lbl.pack(side="left", padx=(10, 0))

        # Band power bars — 5 narrow Canvas widgets
        _band_colors = {
            "delta": RP["love"],
            "theta": RP["iris"],
            "alpha": RP["foam"],
            "beta":  RP["gold"],
            "gamma": RP["rose"],
        }
        self._eeg_bars    = {}
        self._eeg_bar_lbls = {}
        _BAR_W, _BAR_H = 80, 8
        for row_idx, (band, color) in enumerate(_band_colors.items(), start=1):
            self._label(f, band.capitalize(), row_idx)
            bar_frame = tk.Frame(f, bg=RP["surface"])
            bar_frame.grid(row=row_idx, column=1, sticky="w",
                           padx=(8, 0), pady=(2, 0))
            bg_canvas = tk.Canvas(
                bar_frame, width=_BAR_W, height=_BAR_H,
                bg=RP["overlay"], highlightthickness=0, relief="flat",
            )
            bg_canvas.pack(side="left")
            bg_canvas.create_rectangle(0, 0, 0, _BAR_H, fill=color, tags="bar",
                                        outline="")
            self._eeg_bars[band] = (bg_canvas, _BAR_W, color)
            val_lbl = tk.Label(
                bar_frame, text="0.00",
                font=FONT_SMALL, bg=RP["surface"], fg=RP["muted"], width=5,
            )
            val_lbl.pack(side="left", padx=(6, 0))
            self._eeg_bar_lbls[band] = val_lbl

        # ── Derived metrics column — sits in column 2 alongside the band bars ──
        f.columnconfigure(2, weight=1)
        derived_col = tk.Frame(f, bg=RP["surface"])
        derived_col.grid(row=1, column=2, rowspan=5, sticky="nsew", padx=(10, 0))

        def _dlabel(text, fg=RP["muted"]):
            lbl = tk.Label(derived_col, text=text, font=FONT_SMALL,
                           bg=RP["surface"], fg=fg, anchor="w")
            lbl.pack(anchor="w", fill="x", pady=(0, 2))
            return lbl

        self._eeg_trance_lbl      = _dlabel("Trance  —")
        self._eeg_sef95_lbl       = _dlabel("SEF95   —")
        self._eeg_faa_lbl         = _dlabel("FAA     —")
        self._eeg_assr_lbl        = _dlabel("ASSR    —")
        self._conductor_phase_lbl = _dlabel("Phase   —")
        self._freq_lead_lbl       = _dlabel("Lead    —")

        # Quality + state + IAF row
        info_row = tk.Frame(f, bg=RP["surface"])
        info_row.grid(row=6, column=0, columnspan=3, sticky="ew",
                      pady=(6, 0), padx=(0, 8))
        self._eeg_state_lbl = tk.Label(
            info_row, text="state: —",
            font=FONT_SMALL, bg=RP["surface"], fg=RP["muted"],
        )
        self._eeg_state_lbl.pack(side="left")
        self._eeg_iaf_lbl = tk.Label(
            info_row, text="IAF: —",
            font=FONT_SMALL, bg=RP["surface"], fg=RP["muted"],
        )
        self._eeg_iaf_lbl.pack(side="left", padx=(10, 0))

        # Calibrate IAF button
        cal_row = tk.Frame(f, bg=RP["surface"])
        cal_row.grid(row=7, column=0, columnspan=3, sticky="ew",
                     pady=(4, 0), padx=(0, 8))
        self._eeg_cal_btn = tk.Button(
            cal_row, text="Calibrate IAF (30 s)",
            font=FONT_SMALL,
            bg=RP["overlay"], fg=RP["subtle"],
            activebackground=RP["hl_high"], activeforeground=RP["text"],
            relief="flat", bd=0, padx=10, pady=3,
            cursor="hand2", command=self._start_iaf_calibration,
        )
        self._eeg_cal_btn.pack(side="left")
        self._eeg_cal_lbl = tk.Label(
            cal_row, text="",
            font=FONT_SMALL, bg=RP["surface"], fg=RP["muted"],
        )
        self._eeg_cal_lbl.pack(side="left", padx=(8, 0))

        # Hint row — shown during calibration only
        hint_row = tk.Frame(f, bg=RP["surface"])
        hint_row.grid(row=8, column=0, columnspan=3, sticky="ew",
                      pady=(2, 4), padx=(0, 8))
        self._eeg_cal_hint_lbl = tk.Label(
            hint_row, text="",
            font=FONT_SMALL, bg=RP["surface"], fg=RP["gold"],
            wraplength=260, justify="left",
        )
        self._eeg_cal_hint_lbl.pack(side="left")

        # ── OpenXR headset (native flicker; not SteamVR desktop mirror) ────────
        fv = self._section(parent, "OpenXR Headset", RP["iris"])
        self._vr_headset_proc = None

        vr_hint = tk.Label(
            fv,
            text=(
                "Native OpenXR field (ganzfeld / photic / rivalry). "
                "For the full Somna window in VR, use the transport bar "
                "🥽 toggle (SteamVR overlay), not this block."
            ),
            font=FONT_SMALL, bg=RP["surface"], fg=RP["subtle"],
            wraplength=320, justify="left",
        )
        vr_hint.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        # Row 1: launch button + status + safety indicator
        vr_top = tk.Frame(fv, bg=RP["surface"])
        vr_top.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 4))

        self._vr_headset_btn = tk.Button(
            vr_top, text="Launch OpenXR",
            font=FONT_SMALL,
            bg=RP["overlay"], fg=RP["iris"],
            activebackground=RP["hl_high"], activeforeground=RP["text"],
            relief="flat", bd=0, padx=10, pady=3,
            cursor="hand2", command=self._toggle_vr_headset,
        )
        self._vr_headset_btn.pack(side="left")

        self._vr_headset_status_lbl = tk.Label(
            vr_top, text="inactive",
            font=FONT_SMALL, bg=RP["surface"], fg=RP["muted"],
        )
        self._vr_headset_status_lbl.pack(side="left", padx=(8, 0))

        self._vr_safety_lbl = tk.Label(
            vr_top, text="",
            font=FONT_SMALL, bg=RP["surface"], fg=RP["muted"],
        )
        self._vr_safety_lbl.pack(side="right", padx=(0, 4))

        # Row 2: render mode
        self._label(fv, "Render Mode", 2)
        self.vr_render_mode = ttk.Combobox(
            fv,
            values=["ganzfeld", "photic", "rivalry", "dichoptic_ssvep"],
            state="readonly", width=14,
        )
        self.vr_render_mode.set("ganzfeld")
        self.vr_render_mode.grid(row=2, column=1, columnspan=2, sticky="ew",
                                 padx=(8, 0), pady=2)
        self.vr_render_mode.bind("<<ComboboxSelected>>", self._on_vr_mode_change)

        # Row 3: left-eye Hz (shared: rivalry L / ssvep L / photic)
        self._label(fv, "L-Eye Hz", 3)
        self.vr_left_hz = self._slider(fv, 3, 5.0, 30.0, res=0.5)
        self.vr_left_hz.set(7.5)

        # Row 4: right-eye Hz (rivalry R / ssvep R; ignored in photic/ganzfeld mode)
        self._label(fv, "R-Eye Hz", 4)
        self.vr_right_hz = self._slider(fv, 4, 5.0, 30.0, res=0.5)
        self.vr_right_hz.set(12.0)

        # Row 5: modulation depth
        self._label(fv, "Depth", 5)
        self.vr_depth = self._slider(fv, 5, 0.0, 0.40, res=0.01)
        self.vr_depth.set(0.20)

        # Row 6: Ganzfeld background luminance
        self._label(fv, "BG Lum", 6)
        self.vr_bg_lum = self._slider(fv, 6, 0.20, 0.80, res=0.01)
        self.vr_bg_lum.set(0.50)

        # Row 7: vection toggle + speed
        vect_row = tk.Frame(fv, bg=RP["surface"])
        vect_row.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 2))
        self._vr_vection_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            vect_row, text="Vection (optic flow)",
            variable=self._vr_vection_var,
            bg=RP["surface"], fg=RP["text"],
            activebackground=RP["surface"], activeforeground=RP["text"],
            selectcolor=RP["overlay"], font=FONT_LABEL,
            command=self._write_vr_params,
        ).pack(side="left")

        self._label(fv, "Vect Speed", 8)
        self.vr_vection_speed = self._slider(fv, 8, 0.0, 1.0, res=0.05)
        self.vr_vection_speed.set(0.5)

        # Row 9: live SSVEP readout
        self._vr_ssvep_lbl = tk.Label(
            fv, text="binocular —   switch —",
            font=FONT_SMALL, bg=RP["surface"], fg=RP["muted"],
        )
        self._vr_ssvep_lbl.grid(row=9, column=0, columnspan=3, sticky="w", pady=(4, 2))

        # Wire slider changes to write directly to live_control.json
        for w in [self.vr_left_hz, self.vr_right_hz, self.vr_depth, self.vr_bg_lum,
                  self.vr_vection_speed]:
            w.config(command=self._write_vr_params)

    # ── Right column: Veil · Affirmation (+ Shadows) · Spirals · EEG ─────────

    def _build_right_col(self, parent):
        # ── Veil & Background ─────────────────────────────────────────────
        f = self._section(parent, "Veil & Background", RP["subtle"])
        self._plabel(f, "Veil Opacity", 0, "veil_opacity")
        self.veil_opac = self._slider(f, 0, 0, 100)
        self._plabel(f, "BG Speed (ms)", 1, "slideshow_interval")
        self.bg_speed = self._slider(f, 1, 1, 5000)
        # Veil Mode + BG Mode on one row
        self._label(f, "Veil Mode", 2)
        veil_mode_row = tk.Frame(f, bg=RP["surface"])
        veil_mode_row.grid(row=2, column=1, columnspan=2, sticky="ew",
                           padx=(8, 0), pady=2)
        self.veil_mode = ttk.Combobox(
            veil_mode_row,
            values=["auto", "scroll", "rain", "drift", "converge", "strobe", "tunnel"],
            state="readonly", width=10)
        self.veil_mode.pack(side="left")
        # BG Mode: three mutually exclusive options
        self._label(f, "BG Mode", 3)
        self.bg_mode_var = tk.StringVar(value="slideshow")
        self.bg_mode_combo = ttk.Combobox(
            f, textvariable=self.bg_mode_var,
            values=["slideshow", "ganzfeld", "none (transparent)"],
            state="readonly", width=18)
        self.bg_mode_combo.grid(row=3, column=1, columnspan=2, sticky="ew",
                                padx=(8, 0), pady=2)
        # Ganzfeld controls (always visible; only meaningful in ganzfeld mode)
        self._plabel(f, "Ganzfeld Gain", 4, "bg_ganzfeld_gain")
        self.ganzfeld_gain = self._slider(f, 4, 0.0, 1.0, res=0.01)
        self._plabel(f, "CCT (K)", 5, "bg_ganzfeld_cct_k")
        self.ganzfeld_cct = self._slider(f, 5, 2700, 6500, res=100)
        self._plabel(f, "Breath Hz", 6, "bg_ganzfeld_breath_hz")
        self.ganzfeld_breath = self._slider(f, 6, 0.01, 0.20, res=0.01)

        # ── Post-Processing ───────────────────────────────────────────────
        f = self._section(parent, "Post-Processing", RP["overlay"])
        self._plabel(f, "Chrom. Aberr.", 0, "pp_ca_strength")
        self.pp_ca = self._slider(f, 0, 0.0, 1.0, res=0.01)
        self._plabel(f, "Bloom", 1, "pp_bloom_intensity")
        self.pp_bloom = self._slider(f, 1, 0.0, 1.0, res=0.01)
        self._plabel(f, "Bloom Thresh.", 2, "pp_bloom_threshold")
        self.pp_bloom_thresh = self._slider(f, 2, 0.0, 1.0, res=0.01)
        self._plabel(f, "Vignette", 3, "pp_vignette_intensity")
        self.pp_vignette = self._slider(f, 3, 0.0, 1.0, res=0.01)
        self._plabel(f, "Vignette Size", 4, "pp_vignette_sigma")
        self.pp_vignette_sigma = self._slider(f, 4, 0.1, 1.0, res=0.01)

        # ── Affirmation Engine ────────────────────────────────────────────
        f = self._section(parent, "Affirmation Engine", RP["rose"])

        # Row 0: Font Mode (dropdown) + Text Color (swatch + pick) on one line
        self._label(f, "Font Mode", 0)
        affm_row0 = tk.Frame(f, bg=RP["surface"])
        affm_row0.grid(row=0, column=1, columnspan=2, sticky="ew",
                       padx=(8, 0), pady=2)
        self.font_mode = ttk.Combobox(affm_row0, values=["intelligent", "rapid"],
                                      state="readonly", width=10)
        self.font_mode.pack(side="left")
        tk.Label(affm_row0, text="Color", bg=RP["surface"], fg=RP["subtle"],
                 font=FONT_LABEL).pack(side="left", padx=(14, 4))
        self.text_color_swatch = tk.Label(affm_row0, width=3, bg="#ff69b4",
                                          relief="flat", bd=0)
        self.text_color_swatch.pack(side="left")
        tk.Button(affm_row0, text="pick", font=FONT_SMALL,
                  bg=RP["overlay"], fg=RP["subtle"],
                  activebackground=RP["hl_high"], activeforeground=RP["text"],
                  relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
                  command=self._pick_text_color).pack(side="left", padx=(4, 0))

        self._label(f, "Sync to Beat", 1)
        cb = tk.Checkbutton(f, text="enabled", variable=self.sync_var,
                            command=self._update,
                            bg=RP["surface"], fg=RP["text"],
                            activebackground=RP["surface"], activeforeground=RP["text"],
                            selectcolor=RP["overlay"], font=FONT_LABEL)
        cb.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=2)
        self._plabel(f, "Duty Cycle", 2, "flash_duty_cycle")
        self.duty = self._slider(f, 2, 0.1, 0.9, res=0.01)
        self._plabel(f, "Variance %", 3, "flash_variance")
        self.variance = self._slider(f, 3, 0, 50)

        # Flash On + Flash Off side by side on one row
        flash_lbl_row = tk.Frame(f, bg=RP["surface"])
        flash_lbl_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        flash_lbl_row.columnconfigure((0, 1), weight=1)
        self._param_labels["center_flash_on_time"] = tk.Label(
            flash_lbl_row, text="Flash On (ms)", bg=RP["surface"],
            fg=RP["subtle"], font=FONT_LABEL, anchor="w")
        self._param_labels["center_flash_on_time"].grid(row=0, column=0, sticky="w")
        self._param_labels["center_flash_off_time"] = tk.Label(
            flash_lbl_row, text="Flash Off (ms)", bg=RP["surface"],
            fg=RP["subtle"], font=FONT_LABEL, anchor="w")
        self._param_labels["center_flash_off_time"].grid(row=0, column=1, sticky="w", padx=(8, 0))

        flash_slider_row = tk.Frame(f, bg=RP["surface"])
        flash_slider_row.grid(row=5, column=0, columnspan=3, sticky="ew")
        flash_slider_row.columnconfigure((0, 1), weight=1)
        self.center_on = tk.Scale(
            flash_slider_row, from_=5, to=3000, resolution=1,
            orient="horizontal", bg=RP["surface"], fg=RP["text"],
            troughcolor=RP["overlay"], activebackground=RP["iris"],
            highlightthickness=0, bd=0, sliderrelief="flat", sliderlength=14,
            width=6, font=FONT_SMALL)
        self.center_on.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self.center_off = tk.Scale(
            flash_slider_row, from_=5, to=3000, resolution=1,
            orient="horizontal", bg=RP["surface"], fg=RP["text"],
            troughcolor=RP["overlay"], activebackground=RP["iris"],
            highlightthickness=0, bd=0, sliderrelief="flat", sliderlength=14,
            width=6, font=FONT_SMALL)
        self.center_off.grid(row=0, column=1, sticky="ew", padx=(2, 0))

        # Live rate readout
        self._flash_rate_var = tk.StringVar(value="")
        tk.Label(f, textvariable=self._flash_rate_var,
                 bg=RP["surface"], fg=RP["muted"], font=("Segoe UI", 8),
                 anchor="w").grid(row=6, column=1, sticky="w", padx=(8, 0), pady=(0, 4))

        # ── Subliminal Shadows — collapsible subsection ───────────────────
        self._shadows_expanded = False
        shadows_toggle_row = tk.Frame(f, bg=RP["surface"])
        shadows_toggle_row.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        self._shadows_toggle_btn = tk.Button(
            shadows_toggle_row, text="▸ Subliminal Affirmations", font=FONT_SMALL,
            bg=RP["surface"], fg=RP["subtle"],
            activebackground=RP["hl_low"], activeforeground=RP["text"],
            relief="flat", bd=0, anchor="w", cursor="hand2",
            command=self._toggle_shadows_section,
        )
        self._shadows_toggle_btn.pack(side="left", fill="x", expand=True)

        self._shadows_frame = tk.Frame(f, bg=RP["surface"])
        self._shadows_frame.grid(row=8, column=0, columnspan=3, sticky="ew")
        self._shadows_frame.grid_remove()
        self._shadows_frame.columnconfigure(1, weight=1)

        self._plabel(self._shadows_frame, "Opacity", 0, "shadow_opacity")
        self.shadow_opac = self._slider(self._shadows_frame, 0, 0, 100)
        self._plabel(self._shadows_frame, "ON (ms)", 1, "shadow_flash_on_time")
        self.shadow_on = self._slider(self._shadows_frame, 1, 10, 500)
        self._plabel(self._shadows_frame, "OFF (ms)", 2, "shadow_flash_off_time")
        self.shadow_off = self._slider(self._shadows_frame, 2, 10, 1000)
        self._plabel(self._shadows_frame, "Intensity", 3, "subliminal_intensity")
        self.subliminal_intensity = self._slider(self._shadows_frame, 3, 0.0, 1.0, res=0.01)
        self._plabel(self._shadows_frame, "Count", 4, "shadow_count_target")
        self.shadow_count = self._slider(self._shadows_frame, 4, 4, 10)
        self._plabel(self._shadows_frame, "Exclusion Zone", 5, "shadow_exclusion_pct")
        self.shadow_exclusion = self._slider(self._shadows_frame, 5, 0.15, 0.40, res=0.01)
        self._plabel(self._shadows_frame, "SR Noise", 6, "sr_noise_level")
        self.sr_noise = self._slider(self._shadows_frame, 6, 0.0, 2.0, res=0.05)

        # ── Spirals ───────────────────────────────────────────────────────
        f = self._section(parent, "Spirals", RP["gold"])

        # Style + Color Mode on one row
        self._label(f, "Style", 0)
        spiral_row0 = tk.Frame(f, bg=RP["surface"])
        spiral_row0.grid(row=0, column=1, columnspan=2, sticky="ew",
                         padx=(8, 0), pady=2)
        self.spiral_style = ttk.Combobox(spiral_row0, values=[
            "tunnel_dream", "galaxy", "archimedean", "kaleidoscope",
            "interference", "electric", "vortex", "dna", "fibonacci",
            "rose", "moire", "spirograph", "fermat", "superformula", "liminal",
            "resonant", "nebula", "bifurcate",
        ], state="readonly", width=13)
        self.spiral_style.pack(side="left")
        tk.Label(spiral_row0, text="Mode", bg=RP["surface"], fg=RP["subtle"],
                 font=FONT_LABEL).pack(side="left", padx=(10, 4))
        self.spiral_color_mode = ttk.Combobox(spiral_row0, values=["rainbow", "solid"],
                                              state="readonly", width=7)
        self.spiral_color_mode.pack(side="left")

        self._label(f, "Spiral Color", 1)
        color_row = tk.Frame(f, bg=RP["surface"])
        color_row.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=2)
        self.color_swatch = tk.Label(color_row, width=3, bg="#eb6f92",
                                     relief="flat", bd=0)
        self.color_swatch.pack(side="left")
        tk.Button(color_row, text="pick",
                  font=FONT_SMALL,
                  bg=RP["overlay"], fg=RP["subtle"],
                  activebackground=RP["hl_high"], activeforeground=RP["text"],
                  relief="flat", bd=0, padx=8, pady=2,
                  cursor="hand2",
                  command=self._pick_spiral_color).pack(side="left", padx=(6, 0))

        self._plabel(f, "Count", 2, "spiral_count")
        self.spiral_count = self._slider(f, 2, 1, 8)
        self._plabel(f, "Tightness", 3, "spiral_tightness")
        self.spiral_tight = self._slider(f, 3, 2.0, 12.0, res=0.1)
        self._plabel(f, "Thickness", 4, "spiral_thickness")
        self.spiral_thick = self._slider(f, 4, 4, 40)
        self._plabel(f, "Speed", 5, "spiral_speed_multiplier")
        self.spiral_speed = self._slider(f, 5, 0.1, 3.0, res=0.05)
        self._plabel(f, "Chaos", 6, "spiral_chaos")
        self.spiral_chaos = self._slider(f, 6, 0.0, 0.8, res=0.01)
        self._plabel(f, "Opacity %", 7, "spiral_opacity")
        self.spiral_opac = self._slider(f, 7, 10, 100)
        self._plabel(f, "Trail Decay %", 8, "trail_decay")
        self.trail_decay = self._slider(f, 8, 0, 99, res=1)

        # ── Overlay ───────────────────────────────────────────────────────
        f = self._section(parent, "Overlay", RP["muted"])

        # Single-row inline layout: [Always on Top ✓] [Click-through ✓] [Opacity ────]
        overlay_row = tk.Frame(f, bg=RP["surface"])
        overlay_row.grid(row=0, column=0, columnspan=3, sticky="ew", pady=2)
        overlay_row.columnconfigure(4, weight=1)

        self.win_topmost = tk.BooleanVar(value=False)
        tk.Checkbutton(overlay_row, text="Always on Top", variable=self.win_topmost,
                       bg=RP["surface"], fg=RP["text"],
                       activebackground=RP["surface"], activeforeground=RP["text"],
                       selectcolor=RP["overlay"], font=FONT_LABEL,
                       command=self._update).grid(row=0, column=0, sticky="w")

        self.win_clickthrough = tk.BooleanVar(value=False)
        tk.Checkbutton(overlay_row, text="Click-through", variable=self.win_clickthrough,
                       bg=RP["surface"], fg=RP["text"],
                       activebackground=RP["surface"], activeforeground=RP["text"],
                       selectcolor=RP["overlay"], font=FONT_LABEL,
                       command=self._update).grid(row=0, column=1, sticky="w", padx=(12, 0))

        tk.Label(overlay_row, text="Opacity", bg=RP["surface"], fg=RP["subtle"],
                 font=FONT_LABEL).grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.win_opacity = tk.DoubleVar(value=100.0)
        tk.Scale(overlay_row, variable=self.win_opacity, from_=10, to=100,
                 orient="horizontal", resolution=1,
                 bg=RP["surface"], fg=RP["text"], troughcolor=RP["overlay"],
                 activebackground=RP["iris"], highlightthickness=0,
                 bd=0, sliderrelief="flat", sliderlength=14, width=6,
                 font=FONT_SMALL, command=lambda _: self._update(),
                 ).grid(row=0, column=4, sticky="ew", padx=(4, 0))

        # ── GENUS ─────────────────────────────────────────────────────────
        fg = self._section(parent, "GENUS (40 Hz)", RP["gold"])
        genus_en_row = tk.Frame(fg, bg=RP["surface"])
        genus_en_row.grid(row=0, column=0, columnspan=3, sticky="ew")
        self._genus_active_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            genus_en_row, text="active", variable=self._genus_active_var,
            bg=RP["surface"], fg=RP["text"], selectcolor=RP["overlay"],
            activebackground=RP["surface"], activeforeground=RP["text"],
            font=FONT_LABEL, bd=0, highlightthickness=0,
            command=self._update,
        ).pack(side="left")
        self._genus_visual_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            genus_en_row, text="visual flicker", variable=self._genus_visual_var,
            bg=RP["surface"], fg=RP["subtle"], selectcolor=RP["overlay"],
            activebackground=RP["surface"], activeforeground=RP["text"],
            font=FONT_SMALL, bd=0, highlightthickness=0,
            command=self._update,
        ).pack(side="left", padx=(12, 0))
        self._plabel(fg, "Mod. Depth", 1, "genus_modulation_depth")
        self.genus_depth = self._slider(fg, 1, 0.0, 1.0, res=0.01)
        self._plabel(fg, "Duration (min)", 2, "genus_session_duration_min")
        self.genus_duration = self._slider(fg, 2, 5, 120, res=1)
        self._genus_status_lbl = tk.Label(
            fg, text="display: —", font=FONT_SMALL,
            bg=RP["surface"], fg=RP["muted"],
        )
        self._genus_status_lbl.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 2))

    # ── Waveform panel ────────────────────────────────────────────────────────

    def _build_wave_panel(self, col_outer: tk.Frame) -> None:
        """Full-width binaural beat waveform visualization below the control
        columns.  No Win32 tricks — a pure Tkinter canvas in its own panel,
        spanning both control columns and matching the console panel height.
        """
        outer = tk.Frame(col_outer, bg=RP["surface"], bd=0)
        outer.grid(row=2, column=0, columnspan=2, sticky="ew",
                   padx=(0, 6), pady=(0, 6))
        outer.columnconfigure(0, weight=1)

        tk.Frame(outer, bg=RP["foam"], height=1).grid(row=0, column=0, sticky="ew")

        hdr = tk.Frame(outer, bg=RP["surface"])
        hdr.grid(row=1, column=0, sticky="ew", padx=6, pady=(4, 2))
        hdr.columnconfigure(1, weight=1)
        tk.Label(hdr, text="BINAURAL WAVEFORM", bg=RP["surface"],
                 fg=RP["foam"], font=FONT_HEADER).grid(row=0, column=0, sticky="w")
        self._wave_info_var = tk.StringVar(value="")
        tk.Label(hdr, textvariable=self._wave_info_var, bg=RP["surface"],
                 fg=RP["muted"], font=FONT_SMALL).grid(row=0, column=1, sticky="e")

        self._wave_canvas = tk.Canvas(
            outer, height=120, bg=RP["surface"],
            highlightthickness=0, bd=0,
        )
        self._wave_canvas.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 6))

        self._wave_hist_L: list[float] = [0.0] * 120
        self._wave_hist_R: list[float] = [0.0] * 120
        self._wave_photo   = None   # strong ref so Tk never touches a dead image
        self._wave_img_id  = None   # canvas item id; updated in-place each frame
        self._poll_wave_panel()

    def _poll_wave_panel(self) -> None:
        import math, time as _t
        interval = 40
        try:
            audio_muted = not getattr(self, "_audio_on", False) \
                          or getattr(self, "_beats_muted", False)
            if audio_muted:
                self._wave_canvas.delete("all")
                self._wave_img_id = None  # item was deleted; force re-create on resume
                self._wave_info_var.set("audio inactive")
                interval = 200
            else:
                beat = float(self.beat.get())
                vol  = float(self.volume.get()) / 100.0
                if not (math.isfinite(beat) and math.isfinite(vol)):
                    raise ValueError
                beat = max(0.01, beat)
                vol  = max(0.0, min(1.0, vol))
                t    = _t.monotonic()

                L = math.sin(2 * math.pi * beat * t) * vol
                R = math.cos(2 * math.pi * beat * t) * vol

                self._wave_hist_L.append(L)
                self._wave_hist_R.append(R)
                if len(self._wave_hist_L) > 120:
                    self._wave_hist_L.pop(0)
                    self._wave_hist_R.pop(0)

                carrier = float(self.carrier.get())
                self._wave_info_var.set(
                    f"L  {carrier:.0f} Hz     R  {carrier + beat:.0f} Hz     "
                    f"Δ  {beat:.2f} Hz     vol  {vol * 100:.0f}%"
                )
                self._draw_wave_panel()
        except BaseException:
            pass
        finally:
            try:
                self.root_tk.after(interval, self._poll_wave_panel)
            except BaseException:
                pass

    def _draw_wave_panel(self) -> None:
        import math
        from PIL import Image, ImageDraw, ImageFilter, ImageTk

        c  = self._wave_canvas
        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 4 or ch < 4:
            return
        n = len(self._wave_hist_L)
        if n < 2:
            return

        def _rgb(h: str) -> tuple:
            return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))

        mid   = ch / 2.0
        mid_i = int(mid)
        step  = (cw - 2) / (n - 1)
        amp   = mid * 0.82

        def _pt(i: int, v: float) -> tuple:
            x = max(0, min(cw - 1, int(i * step)))
            y = max(0, min(ch - 1, int(mid - (v if math.isfinite(v) else 0.0) * amp)))
            return (x, y)

        pts_L = [_pt(i, v) for i, v in enumerate(self._wave_hist_L)]
        pts_R = [_pt(i, v) for i, v in enumerate(self._wave_hist_R)]

        # Base background
        img = Image.new("RGB", (cw, ch), _rgb(RP["surface"]))

        # Glow layer — both channels in one RGBA image, single blur pass
        glow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        gd   = ImageDraw.Draw(glow)
        gd.line(pts_R, fill=(*_rgb(RP["iris"]), 155), width=8)
        gd.line(pts_L, fill=(*_rgb(RP["foam"]), 155), width=8)
        glow = glow.filter(ImageFilter.GaussianBlur(radius=11))

        # Translucent fill areas under each wave
        fill = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        fd   = ImageDraw.Draw(fill)
        fd.polygon([(0, mid_i)] + pts_R + [(pts_R[-1][0], mid_i)],
                   fill=(*_rgb(RP["iris"]), 38))
        fd.polygon([(0, mid_i)] + pts_L + [(pts_L[-1][0], mid_i)],
                   fill=(*_rgb(RP["foam"]), 38))

        # Composite fill → bloom onto the base
        base = img.convert("RGBA")
        base.alpha_composite(fill)
        base.alpha_composite(glow)

        # Sharp crest lines drawn last so they sit above the bloom
        cd = ImageDraw.Draw(base)
        cd.line(pts_R, fill=(*_rgb("#ede8ff"), 235), width=2)
        cd.line(pts_L, fill=(*_rgb("#daf5f8"), 235), width=2)

        # Dashed center axis
        for x in range(0, cw, 10):
            cd.line([(x, mid_i), (min(x + 4, cw - 1), mid_i)],
                    fill=(*_rgb(RP["muted"]), 110), width=1)

        photo = ImageTk.PhotoImage(base.convert("RGB"))
        self._wave_photo = photo  # keep strong ref before handing to Tk
        if self._wave_img_id is None:
            self._wave_img_id = c.create_image(0, 0, anchor="nw", image=photo)
        else:
            c.itemconfig(self._wave_img_id, image=photo)

    def _bind_controls(self):
        """Attach live-update callbacks to all sliders and comboboxes."""
        for w in [
            self.carrier, self.beat, self.volume,
            self.am_depth, self.noise_spectral_tilt, self.binaural_blend,
            self.noise_vol,
            self.breath_rate, self.breath_depth,
            self.veil_opac, self.bg_speed,
            self.ganzfeld_gain, self.ganzfeld_cct, self.ganzfeld_breath,
            self.pp_ca, self.pp_bloom, self.pp_bloom_thresh,
            self.pp_vignette, self.pp_vignette_sigma,
            self.duty, self.variance, self.center_on, self.center_off,
            self.shadow_opac, self.shadow_on, self.shadow_off,
            self.subliminal_intensity, self.shadow_count,
            self.shadow_exclusion, self.sr_noise,
            self.spiral_count, self.spiral_tight, self.spiral_thick,
            self.spiral_speed, self.spiral_chaos, self.spiral_opac,
            self.trail_decay,
            self.genus_depth, self.genus_duration,
        ]:
            w.config(command=self._update)
        self._update_flash_rate_readout()
        self.font_mode.bind("<<ComboboxSelected>>", self._update)
        self.spiral_style.bind("<<ComboboxSelected>>", self._update)
        self.veil_mode.bind("<<ComboboxSelected>>", self._update)
        self.bg_mode_combo.bind("<<ComboboxSelected>>", self._update)
        self.spiral_color_mode.bind("<<ComboboxSelected>>", self._update)
        self.beat_type.bind("<<ComboboxSelected>>", self._update)
        self._breath_mod_var.trace_add(
            "write", lambda *_: self.root_tk.after_idle(self._update)
        )
        self._genus_active_var.trace_add(
            "write", lambda *_: self.root_tk.after_idle(self._update)
        )
        self._genus_visual_var.trace_add(
            "write", lambda *_: self.root_tk.after_idle(self._update)
        )
        # tts_voice is saved via <Return>/<FocusOut> on _tts_voice_entry — no trace needed.
        self.tts_backend.trace_add(
            "write", lambda *_: self.root_tk.after_idle(self._update)
        )

    # ── Agent console ─────────────────────────────────────────────────────────

    def _send_console_input(self):
        text = self._console_entry.get().strip()
        if not text:
            return
        self._console_entry.delete(0, "end")
        # Echo the user's message to the log
        self._console_append(f"You: {text}", tag="user")
        # Write to live_control.json for the agent to pick up
        data = self._read_live()
        data["user_console_input"] = text
        data["user_console_ts"]    = time.monotonic()
        self._atomic_save(data)

    def _console_append(self, text: str, tag: str = "system") -> None:
        """Append a timestamped, tagged line to the console log.

        tag must be one of: "agent", "eeg", "warn", "system", "user".
        The line's visibility is controlled by the filter checkboxes.
        """
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M")
        ts_tag = f"ts_{tag}"   # per-category timestamp tag for coordinated elide

        self._console_log.config(state="normal")
        # Timestamp in muted color, then message in category color — same line
        self._console_log.insert("end", f"[{ts}] ", (ts_tag, "ts"))
        self._console_log.insert("end", text + "\n", (tag,))
        self._console_log.see("end")
        self._console_log.config(state="disabled")

        # Sync elide state for newly-added ts_tag in case filter is off
        var = self._console_filter_vars.get(tag)
        if var is not None and not var.get():
            self._console_log.config(state="normal")
            self._console_log.tag_configure(ts_tag, elide=True)
            self._console_log.config(state="disabled")

    # ── Colored noise helpers ─────────────────────────────────────────────────

    def _refresh_noise_btn_highlights(self, selected: str):
        for key, (btn, active_bg) in self._noise_btns.items():
            if key == selected:
                btn.config(bg=active_bg, fg=RP["base"], relief="solid")
            else:
                btn.config(bg=RP["overlay"], fg=RP["subtle"], relief="flat")

    def _set_noise_color(self, color: str, active_bg: str):
        self.noise_color_var.set(color)
        self._refresh_noise_btn_highlights(color)
        self._update()

    # ── VR headset management ─────────────────────────────────────────────────

    def _toggle_vr_headset(self):
        """Launch or stop the vr_display_runner.py subprocess."""
        if self._vr_headset_proc and self._vr_headset_proc.poll() is None:
            self._stop_vr_headset()
        else:
            self._start_vr_headset()

    def _start_vr_headset(self):
        if self._vr_headset_proc and self._vr_headset_proc.poll() is None:
            return
        try:
            d = self._read_live()
            d["vr_headset_enabled"] = True
            self._atomic_save(d)
        except Exception:
            pass
        self._write_vr_params()
        self._vr_headset_proc = subprocess.Popen(
            [sys.executable, str(self.root / "vr" / "vr_display_runner.py")]
        )
        self._vr_headset_btn.config(text="Stop OpenXR", fg=RP["love"])
        self._vr_headset_status_lbl.config(text="starting…", fg=RP["gold"])
        self.root_tk.after(1500, self._poll_vr_headset)

    def _stop_vr_headset(self):
        try:
            d = self._read_live()
            d["vr_headset_enabled"] = False
            self._atomic_save(d)
        except Exception:
            pass
        if self._vr_headset_proc:
            self.root_tk.after(2000, self._force_kill_vr_headset)
        self._vr_headset_btn.config(text="Launch OpenXR", fg=RP["iris"])
        self._vr_headset_status_lbl.config(text="stopping…", fg=RP["muted"])

    def _force_kill_vr_headset(self):
        if self._vr_headset_proc and self._vr_headset_proc.poll() is None:
            self._vr_headset_proc.terminate()
        self._vr_headset_proc = None
        self._vr_headset_status_lbl.config(text="inactive", fg=RP["muted"])
        self._vr_safety_lbl.config(text="", fg=RP["muted"])

    def _poll_vr_headset(self):
        """Check whether the VR subprocess is still alive and update status."""
        if self._vr_headset_proc is None:
            return
        if self._vr_headset_proc.poll() is not None:
            self._vr_headset_proc = None
            self._vr_headset_btn.config(text="Launch OpenXR", fg=RP["iris"])
            self._vr_headset_status_lbl.config(text="inactive", fg=RP["muted"])
            self._vr_safety_lbl.config(text="", fg=RP["muted"])
            return
        try:
            d = self._read_live()
            active = d.get("vr_headset_active", False)
            kill   = d.get("vr_safety_kill", False)
            frames = d.get("vr_frame_count", 0)
            if kill:
                self._vr_headset_status_lbl.config(text="SAFETY KILL", fg=RP["love"])
                self._vr_safety_lbl.config(text="paroxysmal — stopped", fg=RP["love"])
            elif active:
                self._vr_headset_status_lbl.config(text=f"active ({frames} fr)", fg=RP["foam"])
                self._vr_safety_lbl.config(text="OK", fg=RP["pine"])
            else:
                self._vr_headset_status_lbl.config(text="starting…", fg=RP["gold"])
        except Exception:
            pass
        self.root_tk.after(2000, self._poll_vr_headset)

    def _write_vr_params(self, *_):
        """Write current VR slider values to live_control.json."""
        mode = self.vr_render_mode.get()
        try:
            d = self._read_live()
            d["vr_render_mode"]       = mode
            d["vr_background_lum"]    = float(self.vr_bg_lum.get())
            d["vr_rivalry_left_hz"]   = float(self.vr_left_hz.get())
            d["vr_rivalry_right_hz"]  = float(self.vr_right_hz.get())
            d["vr_ssvep_left_hz"]     = float(self.vr_left_hz.get())
            d["vr_ssvep_right_hz"]    = float(self.vr_right_hz.get())
            d["vr_rivalry_depth"]     = float(self.vr_depth.get())
            d["vr_ssvep_depth"]       = float(self.vr_depth.get())
            d["vr_photic_hz"]         = float(self.vr_left_hz.get())
            d["vr_photic_depth"]      = float(self.vr_depth.get())
            d["vr_vection_enabled"]   = bool(self._vr_vection_var.get())
            d["vr_vection_speed"]     = float(self.vr_vection_speed.get())
            self._atomic_save(d)
        except Exception:
            pass

    def _on_vr_mode_change(self, *_):
        self._write_vr_params()
        mode = self.vr_render_mode.get()
        # In ganzfeld/photic mode the right-eye Hz has no meaning — grey it out
        r_state = "normal" if mode in ("rivalry", "dichoptic_ssvep") else "disabled"
        self.vr_right_hz.config(state=r_state)

    # ── Display process management ────────────────────────────────────────────

    def _toggle_vr_mode(self):
        self._vr_mode = not self._vr_mode
        self._vr_btn.config(
            fg=RP["iris"] if self._vr_mode else RP["muted"],
            activeforeground=RP["foam"] if self._vr_mode else RP["text"],
        )

    def _launch_display(self):
        if self._is_display_active():
            return
        # Zero out stale session_time and unmute beats.  Also re-push window
        # prefs and the selected session so the new subprocess reads them
        # correctly on its very first frame — avoids stale bg_mode/click-through.
        try:
            sel = self._get_selected_session()
            if not sel:
                # Nothing selected in treeview — use whatever is already live
                # so we don't accidentally leave a stale "default" session.
                sel = self._read_live().get("session_folder", "")
            patch: dict = {"session_time": 0, "audio_muted": False}
            if sel:
                patch["session_folder"] = sel
            saved = self._read_settings()
            for k in ("window_always_on_top", "window_click_through", "window_opacity"):
                if k in saved:
                    patch[k] = saved[k]
                else:
                    patch["window_always_on_top"] = bool(self.win_topmost.get())
                    patch["window_click_through"] = bool(self.win_clickthrough.get())
                    patch["window_opacity"]        = int(self.win_opacity.get())
                    break
            self._write_live(patch)
        except Exception:
            pass
        self._beats_muted = False
        self._refresh_mute_btn()
        args = [sys.executable, str(self.root / "visual_display_runner.py")]
        if self._vr_mode:
            args.append("--vr")
        self._display_proc = subprocess.Popen(args)

    def _stop_display(self):
        if self._display_proc and self._display_proc.poll() is None:
            self._display_proc.terminate()
        self._display_proc = None
        # terminate() on Windows skips the finally block in visual_display_runner.py,
        # so session_time never gets zeroed there.  Clear it here so the next
        # _launch_display() call is not blocked by a stale non-zero value.
        # Also mute beats so the user isn't left with audio running after the visual stops.
        try:
            self._write_live({"session_time": 0, "audio_muted": True})
        except Exception:
            pass
        self._beats_muted = True
        self._refresh_mute_btn()

    def _is_running(self):
        """True only if THIS control panel owns a running display subprocess."""
        return self._display_proc is not None and self._display_proc.poll() is None

    def _is_display_active(self) -> bool:
        """True if ANY display is running — including agent-launched ones.

        Uses session_time > 0 as a proxy since visual_display_runner.py now
        zeroes session_time on clean exit.  Falls back to subprocess ownership.
        """
        if self._is_running():
            return True
        try:
            d = self._read_live()
            return float(d.get("session_time", 0) or 0) > 0
        except Exception:
            return False

    def _toggle_display(self):
        if self._is_running():
            self._stop_display()
        else:
            self._launch_display()

    def _poll_display_status(self):
        if self._is_running():
            self.launch_btn.config(
                text="■  Stop Session ",
                bg=RP["love"], activebackground=RP["rose"],
            )
        else:
            self.launch_btn.config(
                text="▶  Start Session",
                bg=RP["pine"], activebackground=RP["foam"],
            )
        self.root_tk.after(500, self._poll_display_status)

    # ── Agent process management ──────────────────────────────────────────────

    def _is_agent_running(self):
        return self._agent_proc is not None and self._agent_proc.poll() is None

    def _launch_agent(self):
        if self._is_agent_running():
            return
        agent_script = self.root / "agent" / "somna_agent.py"
        if not agent_script.exists():
            return
        self._agent_proc = subprocess.Popen(
            [sys.executable, "-m", "agent.somna_agent"],
            cwd=str(self.root),
        )
        # Give the user immediate feedback in the console panel
        try:
            import yaml as _yaml
            cfg_path = self.root / "agent_config.yaml"
            with open(cfg_path, encoding="utf-8") as _f:
                _cfg = _yaml.safe_load(_f)
            model   = _cfg.get("model", "?")
            mode    = _cfg.get("mode",  "interactive")
            profile = self._load_user_profile_snippet()
            self._console_append(
                f"[Agent] Starting — model={model}  mode={mode}\n{profile}",
                tag="system")
        except Exception:
            self._console_append("[Agent] Starting…", tag="system")

    def _stop_agent(self):
        if self._agent_proc and self._agent_proc.poll() is None:
            self._agent_proc.terminate()
        self._agent_proc = None
        # If the agent launched a display session, close it too.
        # The agent-launched display has its own subprocess that the control panel
        # doesn't own, so we send a stop command via live_control.json.
        if self._is_display_active() and not self._is_running():
            try:
                d = self._read_live()
                d["_timeline_cmd"] = "stop"
                self._atomic_save(d)
            except Exception:
                pass

    def _toggle_agent(self):
        if self._is_agent_running():
            self._stop_agent()
        else:
            self._launch_agent()

    def _poll_agent_status(self):
        if self._is_agent_running():
            self.agent_btn.config(
                text="✦  Stop Agent ",
                bg=RP["love"], activebackground=RP["rose"],
            )
        else:
            self.agent_btn.config(
                text="✦  Start Agent",
                bg=RP["gold"], activebackground=RP["rose"],
            )
        self.root_tk.after(500, self._poll_agent_status)


    def _toggle_shadows_section(self):
        """Expand or collapse the Subliminal Shadows sub-panel."""
        self._shadows_expanded = not self._shadows_expanded
        if self._shadows_expanded:
            self._shadows_frame.grid()
            self._shadows_toggle_btn.config(text="▾ Subliminal Shadows",
                                            fg=RP["text"])
        else:
            self._shadows_frame.grid_remove()
            self._shadows_toggle_btn.config(text="▸ Subliminal Shadows",
                                            fg=RP["subtle"])

    def _toggle_tts_adv(self):
        """Show or hide the TTS server settings (backend, voice, URL, API key)."""
        self._tts_adv_visible = not self._tts_adv_visible
        for w in (self._tts_backend_lbl, self._tts_backend_row,
                  self._tts_voice_lbl, self._tts_voice_entry,
                  self._tts_url_lbl, self._tts_url_entry,
                  self._tts_key_lbl, self._tts_key_entry):
            if self._tts_adv_visible:
                w.grid()
            else:
                w.grid_remove()
        self._tts_adv_btn.config(
            fg=RP["text"] if self._tts_adv_visible else RP["muted"])

    def _on_tts_backend_change(self, *_):
        """Toggle API URL / key field accessibility based on selected backend.
        Does NOT call _update() — safe to call during __init__ before all
        widgets exist."""
        b = self.tts_backend.get()
        if b == "edge":
            self._tts_url_entry.config(state="disabled", fg=RP["muted"])
            self._tts_key_entry.config(state="disabled", fg=RP["muted"])
            self.tts_voice.set("en-US-JennyNeural")
        elif b == "local":
            self._tts_url_entry.config(state="normal",   fg=RP["text"])
            self._tts_key_entry.config(state="disabled", fg=RP["muted"])
            self.tts_voice.set("af_bella")
        else:  # openai
            self._tts_url_entry.config(state="disabled", fg=RP["muted"])
            self._tts_key_entry.config(state="normal",   fg=RP["text"])
            self.tts_voice.set("nova")

    # ── Audio engine lifecycle ─────────────────────────────────────────────────

    def _start_audio(self):
        """Initialise pygame.mixer and start BinauralAudioEngine + TTSEngine.
        Binaural always starts muted (audio_muted=True) so the app is silent
        until the user explicitly presses the play button in the Binaural panel."""
        if self._audio_on:
            return
        try:
            import pygame.mixer as _mx
            from config import ConfigManager
            from engines.audio_engine import BinauralAudioEngine
            from engines.tts_engine import TTSEngine

            if not _mx.get_init():
                _mx.pre_init(44100, -16, 6, 512)
                _mx.init()

            # Write muted=True *before* creating the engine so its __init__
            # sees the flag and skips auto-play (no audio blast on app open).
            self._write_live({"audio_muted": True})

            self._audio_cfg    = ConfigManager()
            self._audio_engine = BinauralAudioEngine(self._audio_cfg)
            self._tts_engine   = TTSEngine(self._audio_cfg.config)
            self._audio_on     = True
            print("[Panel] Audio engine started (binaural + noise + TTS).")
        except Exception as e:
            print(f"[Panel] Audio engine init failed: {e}")

    def _stop_audio(self):
        """Stop the audio engine background thread cleanly.
        Does NOT call pygame.mixer.quit() — the mixer thread is still alive;
        quitting while it runs crashes the process.  Process exit cleans up."""
        self._audio_on = False
        if self._audio_engine is not None:
            try:
                self._audio_engine.stop()
            except Exception:
                pass
        self._audio_engine = None
        self._tts_engine   = None
        self._audio_cfg    = None
        print("[Panel] Audio engine stopped.")

    # ── EEG engine ────────────────────────────────────────────────────────────

    def _toggle_eeg(self) -> None:
        """Connect or disconnect based on the button label (source of truth).

        Using button text avoids the pitfall where a dead-but-not-None engine
        causes _toggle_eeg to reconnect instead of cleaning up.
        """
        if self._eeg_connect_btn.cget("text") == "Disconnect EEG":
            self._stop_eeg()
        else:
            self._connect_eeg()

    def _connect_eeg(self) -> None:
        # If the previous engine is still shutting down, retry after 200 ms
        # so the board is fully released before the new session starts.
        if self._eeg_stop_thread is not None and self._eeg_stop_thread.is_alive():
            self.root_tk.after(200, self._connect_eeg)
            return

        try:
            from eeg.eeg_engine import EEGEngine  # noqa: PLC0415
        except ImportError:
            self._eeg_status_lbl.config(text="brainflow not installed", fg=RP["love"])
            print("[Panel] EEG: brainflow not installed — run: pip install brainflow")
            return

        self._eeg_engine = EEGEngine(self._eeg_cfg)
        self._eeg_engine.start()
        self._eeg_connect_btn.config(text="Disconnect EEG", fg=RP["love"])
        self._eeg_status_lbl.config(text="connecting…", fg=RP["gold"])
        print("[Panel] EEG engine started.")
        self._eeg_poll_gen += 1
        self._poll_eeg_status(self._eeg_poll_gen)

    def _stop_eeg(self) -> None:
        old_engine = self._eeg_engine
        self._eeg_engine = None
        # Update UI immediately — don't wait for the board to release
        self._eeg_connect_btn.config(text="Connect EEG", fg=RP["foam"])
        self._eeg_status_lbl.config(text="disconnected", fg=RP["muted"])
        self._eeg_state_lbl.config(text="state: —")
        for band in ("delta", "theta", "alpha", "beta", "gamma"):
            canvas, w, _ = self._eeg_bars[band]
            canvas.coords("bar", 0, 0, 0, 8)
            self._eeg_bar_lbls[band].config(text="0.00")
        if old_engine is not None:
            # stop() joins the thread — run in background so the UI stays live
            def _do_stop():
                try:
                    old_engine.stop()
                except Exception:
                    pass
            self._eeg_stop_thread = threading.Thread(
                target=_do_stop, daemon=True, name="EEGStop"
            )
            self._eeg_stop_thread.start()
        print("[Panel] EEG engine stopping.")

    def _trigger_eeg_scoring(self, session_folder: str, duration_s: float) -> None:
        """Run EEG session scoring after display stops. Runs in a background thread.

        Calls SessionScorer with accumulated time-series data from the EEGEngine,
        prints the composite score + summary to the console log, and writes a brief
        agent_message entry so it appears in the agent console.
        """
        try:
            from session.session_scorer import SessionScorer, generate_session_summary
            engine = self._eeg_engine
            if engine is None:
                return

            # Build freq_lead_data from the FreqLeader's live keys (it runs in the
            # agent subprocess and writes its state to live_control.json)
            live = self._read_live()
            freq_lead_data: dict = {}
            if live.get("freq_lead_phase") not in (None, "inactive"):
                freq_lead_data = {
                    "start_freq":      live.get("eeg_iaf_hz"),   # IAF = meet target
                    "end_freq":        live.get("freq_lead_current"),
                    "holds_total":     live.get("freq_lead_holds", 0),
                    "steps_completed": live.get("freq_lead_steps", 0),
                }

            session_data = engine.get_session_data_for_scoring(
                session_id     = session_folder,
                session_preset = session_folder,
                duration_sec   = int(duration_s),
                freq_lead_data = freq_lead_data,
            )
            if not session_data.get("sef95_series"):
                return   # no EEG data was actually collected this session

            scorer  = SessionScorer()
            metrics = scorer.score_session(session_data)
            summary = generate_session_summary(metrics)
            score   = metrics.get("composite_score", 0.0)
            print(f"[Panel] EEG session score: {score:.0f}/100 — {summary}")
            # Push into live_control.json — the agent_message poll loop handles
            # the console append, so we don't call _console_append separately.
            try:
                import time as _time
                self._write_live({
                    "agent_message": {
                        "text":           f"[EEG Scoring] {summary}",
                        "ts":             _time.time(),
                        "needs_response": False,
                        "via":            ["console"],
                        "style":          {"voice_mode": "silent"},
                    }
                })
            except Exception:
                self._console_append(f"[EEG] {summary}", tag="eeg")
        except Exception as e:
            print(f"[Panel] EEG scoring error: {e}")

    def _poll_eeg_status(self, gen: int = 0) -> None:
        """Check EEG connection status and update the status label.

        *gen* is a generation counter bumped on every new _connect_eeg() call.
        Stale polls from a previous connection silently exit so they can't race
        with a newer poll loop that was started after a reconnect.
        """
        if gen != self._eeg_poll_gen:
            return  # stale poll from a previous connection — discard

        if self._eeg_engine is None:
            return

        # Thread died (failed to connect, or hardware disconnected) — always clean up.
        # Don't gate on eeg_connected: it may be stale from a prior session.
        if not self._eeg_engine.is_alive():
            self._eeg_engine = None
            self._eeg_connect_btn.config(text="Connect EEG", fg=RP["foam"])
            self._eeg_status_lbl.config(text="connection failed", fg=RP["love"])
            return

        try:
            d = self._read_live()
            connected = bool(d.get("eeg_connected", False))
            quality   = str(d.get("eeg_quality", ""))
            motion    = bool(d.get("imu_motion_contaminated", False))
            if connected:
                if motion:
                    self._eeg_status_lbl.config(text="● motion", fg=RP["muted"])
                elif quality == "warming":
                    self._eeg_status_lbl.config(text="● warming up", fg=RP["muted"])
                else:
                    color = RP["foam"] if quality == "good" else RP["gold"]
                    self._eeg_status_lbl.config(
                        text=f"● {quality or 'connected'}", fg=color
                    )
                self._eeg_connect_btn.config(text="Disconnect EEG", fg=RP["love"])
            else:
                self._eeg_status_lbl.config(text="connecting…", fg=RP["gold"])

            # Persist FAA resting baseline to user_profile when first ready
            if d.get("eeg_faa_baseline_ready"):
                mean_val = d.get("eeg_faa_baseline_mean")
                std_val  = d.get("eeg_faa_baseline_std")
                if mean_val is not None:
                    self._save_faa_baseline_to_profile(float(mean_val), float(std_val or 0.0))
                    self._write_live({"eeg_faa_baseline_ready": False})

            # ── IAF calibration microfeedback ─────────────────────────────────
            if self._calibrating_iaf:
                cal_status = str(d.get("calibration_status", "recording"))
                remaining  = d.get("calibration_time_remaining_s")
                conf       = d.get("calibration_iaf_confidence", 0.0)
                hint       = str(d.get("calibration_hint") or "")

                # Local countdown: tick down between engine 5-second updates
                if remaining is not None:
                    self._cal_remaining_s = int(remaining)
                else:
                    self._cal_remaining_s = max(0, self._cal_remaining_s - 1)

                if cal_status == "extending":
                    conf_pct = f"  ·  {conf:.0%}" if conf else ""
                    self._eeg_cal_lbl.config(
                        text=f"Extending… {self._cal_remaining_s} s{conf_pct}",
                        fg=RP["iris"],
                    )
                elif cal_status == "recording":
                    conf_pct = f"  ·  {conf:.0%}" if conf else ""
                    self._eeg_cal_lbl.config(
                        text=f"Recording… {self._cal_remaining_s} s{conf_pct}",
                        fg=RP["gold"],
                    )

                if hint:
                    self._eeg_cal_hint_lbl.config(text=hint)

            # ── Band power bars — zero when disconnected ──────────────────────
            for band, (canvas, max_w, _) in self._eeg_bars.items():
                val = (float(d.get(f"eeg_{band}", 0.0) or 0.0)
                       if connected else 0.0)
                canvas.coords("bar", 0, 0, int(val * max_w), 8)
                self._eeg_bar_lbls[band].config(text=f"{val:.2f}")
            state_str = d.get("eeg_state") or ""
            iaf_val   = d.get("eeg_iaf_hz")
            if state_str:
                self._eeg_state_lbl.config(text=f"state: {state_str}")
            if iaf_val is not None:
                self._eeg_iaf_lbl.config(text=f"IAF: {iaf_val:.2f} Hz")

            # ── Derived metrics ───────────────────────────────────────────────
            trance = d.get("eeg_trance_score")
            if trance is not None:
                self._eeg_trance_lbl.config(text=f"Trance  {trance:.2f}")
            sef95 = d.get("eeg_sef95")
            if sef95 is not None:
                self._eeg_sef95_lbl.config(text=f"SEF95   {sef95:.1f} Hz")
            faa    = d.get("eeg_faa")
            faa_st = d.get("eeg_faa_state") or ""
            if faa is not None:
                sign  = "+" if faa >= 0 else ""
                color = (RP["foam"]  if "approach" in faa_st else
                         RP["love"]  if "withdraw" in faa_st else
                         RP["muted"])
                self._eeg_faa_lbl.config(
                    text=f"FAA     {sign}{faa:.2f} {faa_st[:6]}", fg=color)
            assr   = d.get("eeg_entrainment_strength")
            assr_c = d.get("eeg_entrainment_confidence") or ""
            if assr is not None:
                color = RP["foam"] if assr_c == "active" else RP["muted"]
                self._eeg_assr_lbl.config(
                    text=f"ASSR    {assr:.2f} {assr_c[:3]}", fg=color)
            cphase = d.get("conductor_phase") or ""
            if cphase:
                color = (RP["iris"]  if cphase not in ("calibration", "session_end") else
                         RP["muted"] if cphase == "session_end" else
                         RP["subtle"])
                self._conductor_phase_lbl.config(text=f"Phase   {cphase}", fg=color)
            fl_ph  = d.get("freq_lead_phase") or ""
            fl_cur = d.get("freq_lead_current")
            if fl_ph and fl_ph != "inactive":
                self._freq_lead_lbl.config(
                    text=f"Lead    {fl_ph} {fl_cur or '—'} Hz", fg=RP["foam"])
            else:
                self._freq_lead_lbl.config(text="Lead    —", fg=RP["muted"])

        except Exception:
            pass
        self.root_tk.after(1000, self._poll_eeg_status, gen)

    def _start_iaf_calibration(self) -> None:
        """Run a 30-second IAF calibration in a background thread.

        Flow: 3-second eyes-closed instruction → beep → 30-second recording
        (extendable to 45 s by the engine) → beep on completion → result displayed.

        Live microfeedback (confidence, channel SQI, hints) is driven entirely
        by _poll_eeg_status reading calibration_* keys from live_control.json,
        so no local countdown ticker is needed here.
        """
        if self._eeg_engine is None or not self._eeg_engine.is_alive():
            self._eeg_cal_lbl.config(text="Connect EEG first", fg=RP["love"])
            return

        _duration  = 30
        _pre_delay = 3   # seconds of "close your eyes" instruction before recording
        self._eeg_cal_btn.config(state="disabled")
        self._eeg_cal_lbl.config(
            text=f"Close your eyes… starting in {_pre_delay} s", fg=RP["subtle"]
        )
        self._eeg_cal_hint_lbl.config(text="")

        def _beep(freq: int, ms: int) -> None:
            try:
                import winsound
                winsound.Beep(freq, ms)
            except Exception:
                pass

        # Pre-recording instruction countdown (UI thread only — no engine yet)
        _pre = [_pre_delay]
        def _pre_tick():
            _pre[0] -= 1
            if _pre[0] > 0:
                self._eeg_cal_lbl.config(
                    text=f"Close your eyes… starting in {_pre[0]} s", fg=RP["subtle"]
                )
                self.root_tk.after(1000, _pre_tick)
            else:
                threading.Thread(target=lambda: _beep(880, 300),
                                 daemon=True).start()
                _start_recording()
        self.root_tk.after(1000, _pre_tick)

        def _start_recording() -> None:
            # Arm the live-feedback poller
            self._calibrating_iaf  = True
            self._cal_remaining_s  = _duration

            def _run() -> None:
                iaf = None
                try:
                    iaf = self._eeg_engine.run_iaf_calibration(
                        duration_s=float(_duration))
                    if iaf is not None:
                        self._save_iaf_to_profile(iaf)
                except Exception as e:
                    print(f"[Panel] IAF calibration error: {e}")
                finally:
                    _beep(660, 200)
                    __import__("time").sleep(0.25)
                    _beep(880, 300)

                    def _done():
                        self._calibrating_iaf = False
                        self._eeg_cal_hint_lbl.config(text="")
                        self._eeg_cal_btn.config(state="normal")
                        if iaf is not None:
                            self._eeg_cal_lbl.config(
                                text=f"IAF = {iaf:.2f} Hz ✓", fg=RP["foam"]
                            )
                            self._eeg_iaf_lbl.config(text=f"IAF: {iaf:.2f} Hz")
                        else:
                            self._eeg_cal_lbl.config(
                                text="Detection failed", fg=RP["love"]
                            )
                    self.root_tk.after(0, _done)

            threading.Thread(target=_run, daemon=True,
                             name="IAFCalibration").start()

    def _save_iaf_to_profile(self, iaf_hz: float) -> None:
        """Write IAF calibration result to user_profile.json.

        Reloads from disk first to avoid overwriting concurrent updates.
        Cannot call somna_agent.update_profile() directly (different process);
        uses the same reload-then-write pattern instead.
        Also reads calibration_iaf_confidence from live_control.json so the
        profile records how reliable this calibration was.
        """
        from eeg.eeg_engine import build_iaf_profile_update  # noqa: PLC0415
        profile_path = self.root / "user_profile.json"
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8")) \
                if profile_path.exists() else {}
            live = self._read_live()
            iaf_conf = live.get("calibration_iaf_confidence")
            profile.update(build_iaf_profile_update(iaf_hz, iaf_conf))
            profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            conf_str = f"  conf={iaf_conf:.2f}" if iaf_conf is not None else ""
            print(f"[Panel] IAF saved to profile: {iaf_hz:.2f} Hz{conf_str}")
        except Exception as e:
            print(f"[Panel] Failed to save IAF to profile: {e}")

    def _save_faa_baseline_to_profile(self, mean: float, std: float) -> None:
        """Persist the FAA resting baseline to user_profile.json.

        Uses the same reload-before-write pattern as _save_iaf_to_profile to
        avoid clobbering concurrent profile updates from the agent subprocess.
        """
        profile_path = self.root / "user_profile.json"
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8")) \
                if profile_path.exists() else {}
            profile["faa_baseline_mean"] = round(mean, 4)
            profile["faa_baseline_std"]  = round(std,  4)
            profile["faa_baseline_calibrated_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
            profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            print(f"[Panel] FAA baseline saved to profile: mean={mean:.4f}  std={std:.4f}")
        except Exception as e:
            print(f"[Panel] Failed to save FAA baseline to profile: {e}")

    def _poll_audio(self):
        """50 ms heartbeat: update audio config + fire any ready TTS phrase."""
        if self._audio_on and self._tts_engine is not None:
            try:
                self._audio_cfg.update()
            except Exception:
                pass
            try:
                result = self._tts_engine.poll_ready(session_active=self._is_running())
                if result:
                    phrase, dur_ms = result
                    ts = time.time()
                    d = self._read_live()
                    d["tts_playing"]    = phrase
                    d["tts_playing_ts"] = ts
                    d["tts_playing_ms"] = int(dur_ms)
                    self._atomic_save(d)
                    # Clear after the clip finishes so the phrase lock ends
                    self.root_tk.after(
                        int(dur_ms) + 300,
                        lambda: self._write_live({"tts_playing": None,
                                                  "tts_playing_ms": 0}),
                    )
            except Exception as e:
                print(f"[Panel] TTS poll error: {e}")
        self.root_tk.after(50, self._poll_audio)

    def _load_user_profile_snippet(self) -> str:
        """One-line profile summary for the agent startup console message."""
        try:
            profile_path = self.root / "user_profile.json"
            if not profile_path.exists():
                return "(no profile yet)"
            p = json.loads(profile_path.read_text(encoding="utf-8"))
            name  = p.get("name") or "unnamed"
            total = p.get("engagement", {}).get("total_sessions", 0)
            last  = (p.get("engagement", {}).get("last_session_date")
                     or (p.get("last_session") or {}).get("date"))
            days  = "?"
            if last:
                import datetime as _dt
                try:
                    days = (_dt.date.today()
                            - _dt.date.fromisoformat(last)).days
                except Exception:
                    pass
            return (f"  User: {name}  sessions: {total}  "
                    f"last session: {days} day(s) ago")
        except Exception:
            return ""

    def _show_memory_dialog(self):
        """Open a small Toplevel for viewing and pruning agent memory (notes + goals)."""
        profile_path = self.root / "user_profile.json"

        def _read_profile() -> dict:
            try:
                return json.loads(profile_path.read_text(encoding="utf-8"))
            except Exception:
                return {}

        def _save_profile(p: dict) -> None:
            profile_path.write_text(json.dumps(p, indent=2, ensure_ascii=False),
                                    encoding="utf-8")

        win = tk.Toplevel(self.root_tk)
        win.title("Agent Memory")
        win.configure(bg=RP["base"])
        win.resizable(False, False)
        win.grab_set()

        pad = {"padx": 8, "pady": 4}

        # ── Notes ─────────────────────────────────────────────────────────────
        tk.Label(win, text="Notes", font=FONT_HEADER,
                 bg=RP["base"], fg=RP["iris"]).grid(
            row=0, column=0, sticky="w", **pad)

        notes_frame = tk.Frame(win, bg=RP["overlay"], bd=0)
        notes_frame.grid(row=1, column=0, columnspan=2, sticky="ew", **pad)
        notes_lb = tk.Listbox(
            notes_frame, height=6, width=60,
            bg=RP["overlay"], fg=RP["text"],
            selectbackground=RP["iris"], selectforeground=RP["base"],
            font=FONT_SMALL, relief="flat", bd=0, highlightthickness=0,
            activestyle="none",
        )
        notes_sb = tk.Scrollbar(notes_frame, orient="vertical",
                                command=notes_lb.yview,
                                bg=RP["overlay"], troughcolor=RP["surface"])
        notes_sb.pack(side="right", fill="y")
        notes_lb.pack(side="left", fill="both", expand=True)
        notes_lb.config(yscrollcommand=notes_sb.set)

        def _reload_notes():
            p = _read_profile()
            notes_lb.delete(0, "end")
            for n in (p.get("notes") or []):
                notes_lb.insert("end", n if isinstance(n, str) else str(n))

        _reload_notes()

        btn_row = tk.Frame(win, bg=RP["base"])
        btn_row.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        def _delete_note():
            sel = notes_lb.curselection()
            if not sel:
                return
            idx = sel[0]
            p = _read_profile()
            notes = list(p.get("notes") or [])
            if 0 <= idx < len(notes):
                notes.pop(idx)
                p["notes"] = notes
                _save_profile(p)
                _reload_notes()

        def _clear_notes():
            p = _read_profile()
            p["notes"] = []
            _save_profile(p)
            _reload_notes()

        tk.Button(btn_row, text="Delete Selected", font=FONT_SMALL,
                  bg=RP["overlay"], fg=RP["text"],
                  activebackground=RP["hl_high"], activeforeground=RP["text"],
                  relief="flat", bd=0, padx=8, pady=2,
                  cursor="hand2", command=_delete_note,
                  ).pack(side="left", padx=(0, 6))

        tk.Button(btn_row, text="Clear All Notes", font=FONT_SMALL,
                  bg=RP["love"], fg=RP["base"],
                  activebackground=RP["rose"], activeforeground=RP["base"],
                  relief="flat", bd=0, padx=8, pady=2,
                  cursor="hand2", command=_clear_notes,
                  ).pack(side="left", padx=(0, 6))

        # ── Goals ─────────────────────────────────────────────────────────────
        tk.Label(win, text="Goals", font=FONT_HEADER,
                 bg=RP["base"], fg=RP["iris"]).grid(
            row=3, column=0, sticky="w", **pad)

        goals_frame = tk.Frame(win, bg=RP["overlay"], bd=0)
        goals_frame.grid(row=4, column=0, columnspan=2, sticky="ew", **pad)
        goals_lb = tk.Listbox(
            goals_frame, height=4, width=60,
            bg=RP["overlay"], fg=RP["text"],
            selectbackground=RP["iris"], selectforeground=RP["base"],
            font=FONT_SMALL, relief="flat", bd=0, highlightthickness=0,
            activestyle="none",
        )
        goals_sb = tk.Scrollbar(goals_frame, orient="vertical",
                                command=goals_lb.yview,
                                bg=RP["overlay"], troughcolor=RP["surface"])
        goals_sb.pack(side="right", fill="y")
        goals_lb.pack(side="left", fill="both", expand=True)
        goals_lb.config(yscrollcommand=goals_sb.set)

        def _reload_goals():
            p = _read_profile()
            goals_lb.delete(0, "end")
            for g in (p.get("goals") or []):
                label = g.get("title") or g.get("text") or str(g)
                goals_lb.insert("end", label)

        _reload_goals()

        gbtn_row = tk.Frame(win, bg=RP["base"])
        gbtn_row.grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        def _delete_goal():
            sel = goals_lb.curselection()
            if not sel:
                return
            idx = sel[0]
            p = _read_profile()
            goals = list(p.get("goals") or [])
            if 0 <= idx < len(goals):
                goals.pop(idx)
                p["goals"] = goals
                _save_profile(p)
                _reload_goals()

        def _clear_goals():
            p = _read_profile()
            p["goals"] = []
            _save_profile(p)
            _reload_goals()

        tk.Button(gbtn_row, text="Delete Selected", font=FONT_SMALL,
                  bg=RP["overlay"], fg=RP["text"],
                  activebackground=RP["hl_high"], activeforeground=RP["text"],
                  relief="flat", bd=0, padx=8, pady=2,
                  cursor="hand2", command=_delete_goal,
                  ).pack(side="left", padx=(0, 6))

        tk.Button(gbtn_row, text="Clear All Goals", font=FONT_SMALL,
                  bg=RP["love"], fg=RP["base"],
                  activebackground=RP["rose"], activeforeground=RP["base"],
                  relief="flat", bd=0, padx=8, pady=2,
                  cursor="hand2", command=_clear_goals,
                  ).pack(side="left")

        # ── Close ─────────────────────────────────────────────────────────────
        tk.Button(win, text="Close", font=FONT_SMALL,
                  bg=RP["overlay"], fg=RP["text"],
                  activebackground=RP["hl_high"], activeforeground=RP["text"],
                  relief="flat", bd=0, padx=12, pady=3,
                  cursor="hand2", command=win.destroy,
                  ).grid(row=6, column=0, columnspan=2, pady=(4, 8))

    def _atomic_save(self, data: dict):
        """Patch live_control.json synchronously via the in-process StateServer.

        Bypasses the async TCP queue so the file is on disk before this call
        returns — critical for startup sequences where a subprocess is launched
        immediately after and must read the updated state.
        """
        try:
            self._state_server._apply_patch(data)
        except Exception:
            pass

    def _write_live(self, updates: dict):
        """Patch live_control.json synchronously via the in-process StateServer."""
        try:
            self._state_server._apply_patch(updates)
        except Exception:
            pass

    def _read_settings(self) -> dict:
        """Read user_settings.json.  Never raises; returns {} on any error."""
        try:
            return json.loads(self._settings_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_settings(self, updates: dict | None = None):
        """Persist user-global prefs to user_settings.json (read-modify-write).
        If *updates* is None, captures the full set of _USER_SETTINGS_KEYS from
        the current widget state."""
        try:
            existing = self._read_settings()
            if updates is None:
                vals = self._get_all_widget_values()
                updates = {k: vals[k] for k in _USER_SETTINGS_KEYS if k in vals}
            existing.update(updates)
            self._settings_file.write_text(json.dumps(existing, indent=2),
                                           encoding="utf-8")
        except Exception:
            pass

    def _on_close(self):
        self._stop_display()
        self._stop_agent()
        self._stop_eeg()
        self._stop_audio()
        self.root_tk.destroy()
        self._state_server.stop()

    # ── Color picker ──────────────────────────────────────────────────────────

    def _pick_spiral_color(self):
        color = colorchooser.askcolor(title="Spiral Base Color")
        if color[1]:
            rgb = color[0]
            hex_color = f"#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x}"
            self.color_swatch.config(bg=hex_color)
            data = self._read_live()
            data["spiral_base_color"] = [int(rgb[0]), int(rgb[1]), int(rgb[2])]
            self._atomic_save(data)

    def _pick_text_color(self):
        color = colorchooser.askcolor(title="Text Color")
        if color[1]:
            rgb = color[0]
            hex_color = f"#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x}"
            self.text_color_swatch.config(bg=hex_color)
            data = self._read_live()
            data["text_color"] = [int(rgb[0]), int(rgb[1]), int(rgb[2])]
            self._atomic_save(data)

    def _get_base_color(self):
        return self._read_live().get("spiral_base_color", [235, 111, 146])

    def _get_text_color(self):
        return self._read_live().get("text_color", [255, 105, 180])

    # ── live_control.json ─────────────────────────────────────────────────────

    def _read_live(self):
        try:
            return json.loads(self.live_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _load_current_values(self):
        self._ui_syncing = True   # prevent Scale command callbacks from writing stale values
        try:
            d = self._read_live()
            # Overlay user_settings.json on top — those prefs survive concurrent
            # live_control.json overwrites by the display subprocess.
            d.update(self._read_settings())
            self._beats_muted = bool(d.get("audio_muted", self._beats_muted))
            self.carrier.set(d.get("carrier_frequency", 200))
            self.beat.set(d.get("beat_frequency", 10))
            self.volume.set(d.get("volume", 80))
            self.beat_type.set(d.get("beat_type", "binaural"))
            _nc = d.get("noise_color", "pink")
            self.noise_color_var.set(_nc)
            self._refresh_noise_btn_highlights(_nc)
            self.noise_vol.set(d.get("noise_volume", 30))
            self.veil_opac.set(d.get("veil_opacity", 45))
            self.bg_speed.set(int(d.get("slideshow_interval", 2.0) * 1000))
            self.font_mode.set(d.get("font_switch_mode", "intelligent"))
            self.sync_var.set(d.get("center_flash_sync_to_beat", True))
            self.duty.set(d.get("flash_duty_cycle", 0.38))
            self.variance.set(int(d.get("flash_variance", 0.22) * 100))
            self.center_on.set(d.get("center_flash_on_time", 120))
            self.center_off.set(d.get("center_flash_off_time", 80))
            self.shadow_opac.set(d.get("shadow_opacity", 12))
            self.shadow_on.set(d.get("shadow_flash_on_time", 40))
            self.shadow_off.set(d.get("shadow_flash_off_time", 180))
            self.subliminal_intensity.set(d.get("subliminal_intensity", 0.5))
            self.shadow_count.set(d.get("shadow_count_target", 5))
            self.shadow_exclusion.set(d.get("shadow_exclusion_pct", 0.27))
            self.sr_noise.set(d.get("sr_noise_level", 0.0))
            self._breath_mod_var.set(bool(d.get("breath_mod", False)))
            self.breath_rate.set(d.get("breath_rate", 0.10))
            self.breath_depth.set(d.get("breath_depth", 0.15))
            self.spiral_style.set(d.get("spiral_style", "tunnel_dream"))
            rgb = d.get("spiral_base_color", [235, 111, 146])
            self.color_swatch.config(bg=f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")
            tc = d.get("text_color", [255, 105, 180])
            self.text_color_swatch.config(bg=f"#{tc[0]:02x}{tc[1]:02x}{tc[2]:02x}")
            self.spiral_count.set(d.get("spiral_count", 4))
            self.spiral_tight.set(d.get("spiral_tightness", 5.5))
            self.spiral_thick.set(d.get("spiral_thickness", 14))
            self.spiral_speed.set(d.get("spiral_speed_multiplier", 1.0))
            self.spiral_chaos.set(d.get("spiral_chaos", 0.12))
            self.spiral_opac.set(d.get("spiral_opacity", 88))
            self.trail_decay.set(int(float(d.get("trail_decay", 0.0)) * 100))
            self.veil_mode.set(d.get("veil_mode") or "auto")
            _saved_mode = d.get("bg_mode") or "slideshow"
            self.bg_mode_var.set("none (transparent)" if _saved_mode == "none" else _saved_mode)
            self.ganzfeld_gain.set(d.get("bg_ganzfeld_gain", 0.55))
            self.ganzfeld_cct.set(d.get("bg_ganzfeld_cct_k", 3200))
            self.ganzfeld_breath.set(d.get("bg_ganzfeld_breath_hz", 0.05))
            # Migrate legacy color mode names to new labels
            cm = d.get("spiral_color_mode", "rainbow")
            if cm == "cycle": cm = "rainbow"
            if cm == "bw":    cm = "solid"
            self.spiral_color_mode.set(cm)
            # TTS — restore saved voice/backend so the field doesn't revert to defaults
            if d.get("tts_backend"):
                self.tts_backend.set(d["tts_backend"])
                self._on_tts_backend_change()  # update field visibility for loaded backend
            if d.get("tts_voice"):
                self.tts_voice.set(d["tts_voice"])
            # Window / Overlay
            self.tts_enabled.set(d.get("tts_enabled", False))
            self.tts_subliminal.set(d.get("tts_subliminal", False))
            self.win_topmost.set(d.get("window_always_on_top", False))
            self.win_clickthrough.set(d.get("window_click_through", False))
            self.win_opacity.set(d.get("window_opacity", 100))
            # Post-processing
            self.pp_ca.set(d.get("pp_ca_strength", 0.0))
            self.pp_bloom.set(d.get("pp_bloom_intensity", 0.0))
            self.pp_bloom_thresh.set(d.get("pp_bloom_threshold", 0.5))
            self.pp_vignette.set(d.get("pp_vignette_intensity", 0.0))
            self.pp_vignette_sigma.set(d.get("pp_vignette_sigma", 0.4))
            # Audio enhancements
            self.am_depth.set(d.get("am_depth", 0.0))
            self.noise_spectral_tilt.set(d.get("noise_spectral_tilt", 1.0))
            self.binaural_blend.set(d.get("binaural_blend", 1.0))
            # GENUS
            self._genus_active_var.set(bool(d.get("genus_active", False)))
            self._genus_visual_var.set(bool(d.get("genus_visual_enabled", True)))
            self.genus_depth.set(d.get("genus_modulation_depth", 0.5))
            self.genus_duration.set(d.get("genus_session_duration_min", 20))
            # Playlist
            for item in (d.get("playlist") or []):
                if item not in self._pl_items():
                    self._playlist_lb.insert("end", item)
            self._sync_playlist_mode_from_live(d.get("playlist_mode", "sequential"))
        except Exception:
            traceback.print_exc()
        finally:
            self._ui_syncing = False

        # Push user preferences into live_control.json so the display subprocess
        # picks them up even when _update() was suppressed by _ui_syncing.
        prefs = self._read_settings()
        if prefs:
            self._write_live(prefs)

    def _update_flash_rate_readout(self):
        on_ms  = max(5, int(self.center_on.get()))
        off_ms = max(5, int(self.center_off.get()))
        rate   = 1000.0 / (on_ms + off_ms)
        synced = self.sync_var.get()
        if synced:
            self._flash_rate_var.set("↑ controlled by Beat Δ when sync is on")
        else:
            subliminal = on_ms < 50
            tag = "  ← subliminal" if subliminal else ""
            self._flash_rate_var.set(f"≈ {rate:.1f} Hz  ({on_ms} ms on){tag}")

    def _get_all_widget_values(self) -> dict:
        """Snapshot of every UI widget value, keyed by live_control param name."""
        return {
            "carrier_frequency":         float(self.carrier.get()),
            "beat_frequency":            float(self.beat.get()),
            "volume":                    float(self.volume.get()),
            "beat_type":                 self.beat_type.get(),
            "noise_color":               self.noise_color_var.get(),
            "noise_volume":              float(self.noise_vol.get()),
            "veil_opacity":              float(self.veil_opac.get()),
            "slideshow_interval":        float(self.bg_speed.get()) / 1000,
            "font_switch_mode":          self.font_mode.get(),
            "center_flash_sync_to_beat": bool(self.sync_var.get()),
            "flash_duty_cycle":          float(self.duty.get()),
            "flash_variance":            float(self.variance.get()) / 100,
            "center_flash_on_time":      int(self.center_on.get()),
            "center_flash_off_time":     int(self.center_off.get()),
            "shadow_opacity":            float(self.shadow_opac.get()),
            "shadow_flash_on_time":      int(self.shadow_on.get()),
            "shadow_flash_off_time":     int(self.shadow_off.get()),
            "subliminal_intensity":      float(self.subliminal_intensity.get()),
            "shadow_count_target":       int(self.shadow_count.get()),
            "shadow_exclusion_pct":      float(self.shadow_exclusion.get()),
            "sr_noise_level":            float(self.sr_noise.get()),
            "breath_mod":                bool(self._breath_mod_var.get()),
            "breath_rate":               float(self.breath_rate.get()),
            "breath_depth":              float(self.breath_depth.get()),
            "spiral_style":              self.spiral_style.get(),
            "spiral_base_color":         self._get_base_color(),
            "spiral_count":              int(self.spiral_count.get()),
            "spiral_tightness":          float(self.spiral_tight.get()),
            "spiral_thickness":          int(self.spiral_thick.get()),
            "spiral_speed_multiplier":   float(self.spiral_speed.get()),
            "spiral_chaos":              float(self.spiral_chaos.get()),
            "spiral_opacity":            int(self.spiral_opac.get()),
            "trail_decay":               round(float(self.trail_decay.get()) / 100.0, 2),
            "veil_mode":                 None if self.veil_mode.get() == "auto" else self.veil_mode.get(),
            "bg_mode":                   ("none" if "transparent" in self.bg_mode_var.get()
                                          else self.bg_mode_var.get()),
            "bg_ganzfeld_gain":          round(float(self.ganzfeld_gain.get()), 2),
            "bg_ganzfeld_cct_k":         float(self.ganzfeld_cct.get()),
            "bg_ganzfeld_breath_hz":     round(float(self.ganzfeld_breath.get()), 3),
            "spiral_color_mode":         self.spiral_color_mode.get(),
            "tts_enabled":               bool(self.tts_enabled.get()),
            "tts_backend":               self.tts_backend.get(),
            "tts_voice":                 self.tts_voice.get().strip(),
            "tts_volume":                float(self.tts_volume.get()),
            "tts_api_url":               self.tts_api_url.get().strip(),
            "tts_api_key":               self.tts_api_key.get().strip(),
            "tts_subliminal":            bool(self.tts_subliminal.get()),
            "tts_subliminal_vol":        float(self.tts_subli_vol.get()),
            "tts_subliminal_hz":         float(self.tts_subli_hz.get()),
            "window_always_on_top":      bool(self.win_topmost.get()),
            "window_click_through":      bool(self.win_clickthrough.get()),
            "window_opacity":            int(self.win_opacity.get()),
            "pp_ca_strength":            float(self.pp_ca.get()),
            "pp_bloom_intensity":        float(self.pp_bloom.get()),
            "pp_bloom_threshold":        float(self.pp_bloom_thresh.get()),
            "pp_vignette_intensity":     float(self.pp_vignette.get()),
            "pp_vignette_sigma":         float(self.pp_vignette_sigma.get()),
            "am_depth":                  float(self.am_depth.get()),
            "noise_spectral_tilt":       float(self.noise_spectral_tilt.get()),
            "binaural_blend":            float(self.binaural_blend.get()),
            "genus_active":              bool(self._genus_active_var.get()),
            "genus_visual_enabled":      bool(self._genus_visual_var.get()),
            "genus_modulation_depth":    float(self.genus_depth.get()),
            "genus_session_duration_min": int(self.genus_duration.get()),
        }

    def _poll_ui_sync(self):
        """Sync slider positions from live_control.json so the UI tracks
        timeline-interpolated values.  Guarded by _ui_syncing to prevent
        _update() from writing back what we just read."""
        if time.monotonic() - self._last_user_interaction < 2.0:
            self.root_tk.after(500, self._poll_ui_sync)
            return

        try:
            d = self._read_live()
        except Exception:
            self.root_tk.after(500, self._poll_ui_sync)
            return

        # EEG bars and derived metrics are now owned by _poll_eeg_status
        # (1 s dedicated loop, not gated by user interaction)

        # ── VR SSVEP readout ─────────────────────────────────────────────────
        try:
            if d.get("vr_headset_active"):
                bi  = d.get("ssvep_binocular_index")
                sw  = d.get("ssvep_switch_rate_hz")
                bi_s = f"{bi:.2f}" if bi is not None else "—"
                sw_s = f"{sw:.3f}Hz" if sw is not None else "—"
                color = (RP["foam"]  if (bi or 0) > 0.6 else
                         RP["gold"]  if (bi or 0) > 0.4 else
                         RP["muted"])
                self._vr_ssvep_lbl.config(
                    text=f"binocular {bi_s}   switch {sw_s}", fg=color)
        except Exception:
            pass

        # ── Conductor status strip in console header ──────────────────────────
        try:
            csum   = d.get("conductor_summary") or {}
            cphase = csum.get("conductor_phase") or d.get("conductor_phase") or ""
            if cphase and cphase not in ("session_end", ""):
                iaf_v  = csum.get("iaf_hz")
                frac   = csum.get("frac_count", 0)
                fmax   = csum.get("frac_max", 0)
                trance = d.get("eeg_trance_score")
                iaf_s  = f"{iaf_v:.1f} Hz" if iaf_v else "—"
                tr_s   = f"{trance:.2f}" if trance is not None else "—"
                self._conductor_status_lbl.config(
                    text=f"phase: {cphase}  |  frac {frac}/{fmax}"
                         f"  |  IAF {iaf_s}  |  trance {tr_s}",
                    fg=RP["foam"],
                )
            else:
                self._conductor_status_lbl.config(
                    text="phase: —  |  frac —  |  IAF —  |  trance —",
                    fg=RP["muted"],
                )
        except Exception:
            pass

        if self._is_running():
            try:
                self._ui_syncing = True
                self.carrier.set(d.get("carrier_frequency", self.carrier.get()))
                self.beat.set(d.get("beat_frequency", self.beat.get()))
                self.volume.set(d.get("volume", self.volume.get()))
                bt = d.get("beat_type")
                if bt:
                    self.beat_type.set(bt)
                self.noise_vol.set(d.get("noise_volume", self.noise_vol.get()))
                self.veil_opac.set(d.get("veil_opacity", self.veil_opac.get()))
                self.ganzfeld_gain.set(d.get("bg_ganzfeld_gain", self.ganzfeld_gain.get()))
                self.ganzfeld_cct.set(d.get("bg_ganzfeld_cct_k", self.ganzfeld_cct.get()))
                self.ganzfeld_breath.set(d.get("bg_ganzfeld_breath_hz", self.ganzfeld_breath.get()))
                self.shadow_opac.set(d.get("shadow_opacity", self.shadow_opac.get()))
                self.spiral_opac.set(d.get("spiral_opacity", self.spiral_opac.get()))
                self.trail_decay.set(int(float(d.get("trail_decay",
                    self.trail_decay.get() / 100.0)) * 100))
                self.spiral_tight.set(d.get("spiral_tightness", self.spiral_tight.get()))
                self.spiral_speed.set(d.get("spiral_speed_multiplier", self.spiral_speed.get()))
                self.spiral_chaos.set(d.get("spiral_chaos", self.spiral_chaos.get()))
                self.spiral_thick.set(d.get("spiral_thickness", self.spiral_thick.get()))
                self.spiral_count.set(d.get("spiral_count", self.spiral_count.get()))
                self.center_on.set(d.get("center_flash_on_time", self.center_on.get()))
                self.center_off.set(d.get("center_flash_off_time", self.center_off.get()))
                self.duty.set(d.get("flash_duty_cycle", self.duty.get()))
                if "center_flash_sync_to_beat" in d:
                    self.sync_var.set(bool(d["center_flash_sync_to_beat"]))
                self.shadow_on.set(d.get("shadow_flash_on_time", self.shadow_on.get()))
                self.shadow_off.set(d.get("shadow_flash_off_time", self.shadow_off.get()))
                self.subliminal_intensity.set(
                    d.get("subliminal_intensity", self.subliminal_intensity.get()))
                self.shadow_count.set(
                    d.get("shadow_count_target", self.shadow_count.get()))
                self.shadow_exclusion.set(
                    d.get("shadow_exclusion_pct", self.shadow_exclusion.get()))
                self.sr_noise.set(d.get("sr_noise_level", self.sr_noise.get()))
                self.breath_rate.set(d.get("breath_rate", self.breath_rate.get()))
                self.breath_depth.set(d.get("breath_depth", self.breath_depth.get()))
                if "breath_mod" in d:
                    self._breath_mod_var.set(bool(d["breath_mod"]))
                ss = d.get("spiral_style")
                if ss:
                    self.spiral_style.set(ss)
                vm = d.get("veil_mode")
                self.veil_mode.set(vm if vm else "auto")
                # TTS booleans — agent may toggle these mid-session
                if "tts_enabled" in d:
                    self.tts_enabled.set(bool(d["tts_enabled"]))
                if "tts_subliminal" in d:
                    self.tts_subliminal.set(bool(d["tts_subliminal"]))
                # Post-processing
                self.pp_ca.set(d.get("pp_ca_strength", self.pp_ca.get()))
                self.pp_bloom.set(d.get("pp_bloom_intensity", self.pp_bloom.get()))
                self.pp_bloom_thresh.set(d.get("pp_bloom_threshold", self.pp_bloom_thresh.get()))
                self.pp_vignette.set(d.get("pp_vignette_intensity", self.pp_vignette.get()))
                self.pp_vignette_sigma.set(d.get("pp_vignette_sigma", self.pp_vignette_sigma.get()))
                # Audio enhancements
                self.am_depth.set(d.get("am_depth", self.am_depth.get()))
                self.noise_spectral_tilt.set(d.get("noise_spectral_tilt", self.noise_spectral_tilt.get()))
                self.binaural_blend.set(d.get("binaural_blend", self.binaural_blend.get()))
                # GENUS status label
                try:
                    capable = d.get("genus_visual_display_capable")
                    if capable is True:
                        self._genus_status_lbl.config(text="display: capable", fg=RP["foam"])
                    elif capable is False:
                        self._genus_status_lbl.config(text="display: audio-only", fg=RP["gold"])
                    else:
                        self._genus_status_lbl.config(text="display: —", fg=RP["muted"])
                except Exception:
                    pass
                # After syncing, update the snapshot so _update doesn't see diffs
                self._last_ui_snapshot = self._get_all_widget_values()
            except Exception:
                pass
            finally:
                self._ui_syncing = False

        self.root_tk.after(500, self._poll_ui_sync)

    def _update(self, *_):
        if self._ui_syncing:
            return
        self._last_user_interaction = time.monotonic()
        self._update_flash_rate_readout()
        try:
            current = self._get_all_widget_values()
            # Only write params that actually changed from last snapshot
            # so the timeline runner doesn't lock params the user never touched.
            dirty = {}
            for k, v in current.items():
                old = self._last_ui_snapshot.get(k)
                if old != v:
                    dirty[k] = v
            if not dirty:
                return
            self._last_ui_snapshot = current
            self._atomic_save(dirty)
            # Persist user-global prefs to their own race-safe file whenever
            # any of those keys were part of the dirty set.
            if dirty.keys() & _USER_SETTINGS_KEYS:
                self._save_settings({k: dirty[k]
                                     for k in dirty if k in _USER_SETTINGS_KEYS})
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    ControlPanel()
