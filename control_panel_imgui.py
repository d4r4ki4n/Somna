"""Somna Control Panel — Dear ImGui implementation.

Replaces the Tkinter control_panel.py with a hardware-accelerated ImGui panel
rendered via imgui-bundle + hello_imgui.

Architecture:
  - Reads live state every frame via ConfigManager (render thread).
  - Writes parameter changes via ipc.patch_live() (StateClient).
  - Rendering is data-driven via ControlPanelManager (panel_config.json).
  - Audio engines (binaural + noise + TTS) run in this process on a 50 ms
    thread-timer loop, identical to the legacy control_panel.py.  The display
    subprocess uses SDL_AUDIODRIVER=dummy and never touches the mixer.
  - Background session-state polling (500 ms) handles agent-commanded
    launch/stop, agent_message → console, EEG scoring, record_session_played.

Per Bible Ch.9 §9.1 (Control Panel Architecture) and Bible Ch.9 §9.2 (ImGui Visual Design Reference).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import ctypes

import numpy as np

from imgui_bundle import imgui, hello_imgui

from config import ConfigManager
from ipc import StateServer, patch_live
from ui.panel_theme import (
    apply_somna_theme,
    load_somna_fonts,
    hex_to_rgba,
    token_u32,
    token_rgba,
    RP,
)
from ui.control_panel_manager import ControlPanelManager
from ui.viz_registry import VisualizationRegistry
from ui.console import SpectrogramConsole
from ui.session_player import SessionPlayer, SessionEntry, SessionState
from ui.session_editor_imgui import SessionEditorModal
from ui.interference_graph_integration import install_interference_graph
from ui.biosignal_dashboard import BiosignalDashboard

PANEL_WIDTH = 420

_USER_SETTINGS_KEYS = {
    "window_always_on_top",
    "window_click_through",
    "window_opacity",
    "tts_voice",
    "tts_backend",
    "tts_api_url",
    "tts_api_key",
}

_PANEL_GROUPS = [
    {
        "label": "Session",
        "sections": {"Session", "Induction", "Content", "Affirmations"},
    },
    {"label": "Audio", "sections": {"Audio", "TTS", "Spirals"}, "cols": 3},
    {
        "label": "Visual",
        "sections": {"Veil & BG", "Overlay", "Visual/Audio"},
        "cols": 3,
    },
    {"label": "Biosignal", "sections": {"EEG", "Director", "Biosignal"}, "cols": 3},
    {"label": "Sleep", "sections": {"Sleep", "TMR", "HTW"}, "cols": 3},
    {"label": "Hardware", "sections": {"Haptic", "taVNS", "OpenXR"}, "cols": 3},
    {
        "label": "Conditioning",
        "sections": {"Conditioning", "Habituation", "GENUS"},
        "cols": 3,
    },
]


class ControlPanelImGui:
    """Dear ImGui control panel for Somna.

    Usage:
        ControlPanelImGui().run()   # blocks until window closed
    """

    # ── Geometry persistence ──────────────────────────────────────────────────

    _GEOM_FILE = Path(__file__).parent / "panel_geometry.json"

    _DEFAULT_SIDEBAR_W = 280.0
    _DEFAULT_CONSOLE_H = 380.0

    def _load_panel_geometry(self) -> dict:
        """Window rect + resizable sidebar / console heights for panel_geometry.json."""
        scr_w = ctypes.windll.user32.GetSystemMetrics(0)
        scr_h = ctypes.windll.user32.GetSystemMetrics(1)
        vy = ctypes.windll.user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
        out = {
            "x": scr_w - PANEL_WIDTH,
            "y": max(vy, 0),
            "w": PANEL_WIDTH,
            "h": scr_h,
            "sidebar_width": self._DEFAULT_SIDEBAR_W,
            "console_bar_height": self._DEFAULT_CONSOLE_H,
        }
        try:
            g = json.loads(self._GEOM_FILE.read_text(encoding="utf-8"))
            x, y, w, h = int(g["x"]), int(g["y"]), int(g["w"]), int(g["h"])
            out["x"] = x
            out["y"] = max(vy, y)
            out["w"] = max(320, w)
            out["h"] = max(400, h)
            sw = float(g.get("sidebar_width", self._DEFAULT_SIDEBAR_W))
            ch = float(g.get("console_bar_height", self._DEFAULT_CONSOLE_H))
            # Same clamps as ControlPanelManager drag handles (approx. using saved w/h)
            out["sidebar_width"] = max(
                200.0,
                min(out["w"] * 0.65, sw),
            )
            out["console_bar_height"] = max(
                120.0,
                min(float(out["h"]) - 100.0, ch),
            )
            if "debug_mode" in g:
                out["debug_mode"] = bool(g["debug_mode"])
            sec_exp = g.get("section_expanded")
            if isinstance(sec_exp, dict):
                out["section_expanded"] = {str(k): bool(v) for k, v in sec_exp.items()}
            sec_ord = g.get("section_order")
            if isinstance(sec_ord, list):
                out["section_order"] = [str(s) for s in sec_ord]
        except Exception:
            pass
        return out

    def _save_geometry(self) -> None:
        try:
            # Read position via hello_imgui / SDL so the coordinate space is
            # identical to what from_coords uses on the next launch.
            # GetWindowRect includes the invisible DWM shadow (~8px each side)
            # which causes per-cycle Y drift when round-tripped through SDL.
            geom = hello_imgui.get_runner_params().app_window_params.window_geometry
            x, y = int(geom.position[0]), int(geom.position[1])
            w, h = int(geom.size[0]), int(geom.size[1])
            pm = self._panel_manager
            payload = {
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "sidebar_width": float(pm._sidebar_width),
                "console_bar_height": float(pm._console_bar_height),
                "debug_mode": pm._debug_mode,
                "section_expanded": dict(pm._section_expanded),
                "section_order": list(pm._section_order),
            }
            self._GEOM_FILE.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── User settings ─────────────────────────────────────────────────────────

    def _load_user_settings(self) -> dict:
        try:
            return json.loads(
                (self._root / "user_settings.json").read_text(encoding="utf-8")
            )
        except Exception:
            return {}

    def _save_user_settings(self) -> None:
        """Persist relevant live keys to user_settings.json on exit."""
        try:
            live = self._live or {}
            saved = self._load_user_settings()
            for k in _USER_SETTINGS_KEYS:
                if k in live and live[k] is not None:
                    saved[k] = live[k]
            (self._root / "user_settings.json").write_text(
                json.dumps(saved, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"[Panel] user_settings save error: {e}")

    # ── Init ──────────────────────────────────────────────────────────────────

    def __init__(self) -> None:
        self._root = Path(__file__).parent
        self._live_path = self._root / "live_control.json"

        self._state_server = StateServer(self._live_path)
        self._state_server.start()

        if not self._live_path.exists():
            self._live_path.write_text("{}", encoding="utf-8")

        self._cfg: ConfigManager = ConfigManager()
        self._live: dict = {}

        # Subprocess handles
        self._display_proc: subprocess.Popen | None = None
        self._agent_proc: subprocess.Popen | None = None
        self._eeg_engine: Any = None
        self._eeg_stop_thread: threading.Thread | None = None
        self._eeg_cfg = self._load_eeg_cfg()

        # Hardware output engines (BLE devices)
        self._haptic_engine: Any = None
        self._tavns_engine: Any = None

        # Session names (for index lookups; player holds SessionEntry objects)
        self._session_names: list[str] = self._scan_sessions()
        self._selected_session_idx: int = 0
        self._last_session_folder: str = ""

        # Spectrogram console (replaces plain text log)
        self._console = SpectrogramConsole()
        self._console.system("Somna control panel started.")
        self._console.system("Tip: Ctrl+Click any slider to type a value.")

        # Winamp-style session player
        self._player = SessionPlayer()
        self._player.load_sessions(self._load_session_entries())
        self._player.on_start_session = lambda e: self._launch_display_for(e.name)
        self._player.on_stop_session = self._stop_display
        self._player.on_start_agent = self._toggle_agent
        self._player.on_toggle_beats = self._toggle_beats
        self._player.on_new_session = self._new_session
        self._player.on_edit_session = lambda e: self._edit_session(e)
        self._player.on_queue_change = self._sync_playlist_to_live

        # Visualization toggle registry (populated after panel_manager is built)
        self._viz = VisualizationRegistry(
            presets_dir=str(self._root / "presets" / "viz")
        )

        # SteamVR overlay toggle (passed as --vr to visual_display_runner.py)
        self._vr_mode: bool = False

        # OpenXR headset subprocess
        self._vr_headset_proc: subprocess.Popen | None = None
        self._vr_headset_poll: threading.Timer | None = None
        self._vr_status: str = "inactive"
        self._vr_safety: str = ""
        # VR control state (written to live_control.json on change)
        self._vr_mode_idx: int = 0  # ganzfeld / photic / rivalry / dichoptic_ssvep
        self._vr_left_hz: float = 7.83
        self._vr_right_hz: float = 10.0
        self._vr_depth: float = 0.20
        self._vr_bg_lum: float = 0.50
        self._vr_vection: bool = False
        self._vr_vection_speed: float = 0.50

        # Display lifecycle tracking (for EEG scoring trigger)
        self._display_was_running: bool = False
        self._display_session_start: float = 0.0

        # Audio engine state
        self._audio_on: bool = False
        self._audio_engine: Any = None
        self._tts_engine: Any = None
        self._audio_cfg: Any = None

        # Background poll timers
        self._audio_poll_timer: threading.Timer | None = None
        self._session_poll_timer: threading.Timer | None = None

        # Seek bar state (updated from live; only written back on drag-release)
        self._seek_value: float = 0.0

        # Agent console (SpectrogramConsole created above; keep tracking state)
        # Seed dedup timestamps from live_control.json so stale messages
        # from a previous session aren't re-logged on startup.
        _init_live = self._cfg.update()
        self._agent_msg_ts: float = float(
            (_init_live.get("agent_message") or {}).get("ts", 0) or 0
        )
        self._last_resp_ts: float = float(_init_live.get("response_timestamp") or 0)
        self._last_console_ts: float = 0.0
        self._console_input: str = ""

        # LLM prompt modal (for agent_message needs_response)
        # Agent prompt — launched as a standalone subprocess (ui/agent_prompt_dialog.py)
        self._prompt_proc: subprocess.Popen | None = None

        # EEG band history for scrolling display (90 × 500 ms ≈ 45 s)
        self._eeg_band_history: deque = deque(maxlen=90)

        # ImGui session editor modal
        self._session_editor = SessionEditorModal(self._root)

        # Settings modal (absorbs old memory modal)
        self._settings_open: bool = False
        self._settings_tab: int = 0
        self._settings_profile: dict = {}
        self._settings_sel_note: int = -1
        self._settings_sel_goal: int = -1
        self._settings_name_buf: str = ""
        self._settings_aph_idx: int = 0
        self._settings_sel_modality: int = -1
        # Agent tab state
        self._agent_cfg_buf: dict = {}
        self._agent_url_buf: str = ""
        self._agent_key_buf: str = ""
        self._agent_model_buf: str = ""
        self._agent_test_status: str = ""
        self._agent_test_running: bool = False

        # Welcome wizard (5-step first-run modal)
        self._welcome_step: int = 0
        self._welcome_name_buf: str = ""
        self._welcome_goals_buf: str = ""
        self._welcome_hw_status: str = ""
        self._welcome_hw_scanned: bool = False
        self._welcome_llm_url_buf: str = ""
        self._welcome_llm_key_buf: str = ""
        self._welcome_llm_model_buf: str = ""
        self._welcome_llm_test_status: str = ""
        self._welcome_llm_test_running: bool = False
        self._welcome_active: bool = False
        self._welcome_checked: bool = False

        # Session Zero safety modal (pre-first-session)
        self._sz_safety_open: bool = False
        self._sz_safety_checked: bool = False
        self._sz_photo_check: bool = False
        self._sz_photo_risk: bool = False
        self._sz_ssb_check: bool = False
        self._sz_safety_ack: bool = False
        self._sz_pending_launch: bool = False

        # User settings (persisted window/TTS prefs)
        self._user_settings: dict = self._load_user_settings()

        # Binaural presets
        self._binaural_presets: dict = self._load_binaural_presets()

        # Data-driven panel manager — session player in sidebar, console bar at top
        config_path = self._root / "panel_config.json"
        self._panel_manager = ControlPanelManager(
            config_path,
            transport_fn=lambda cw: self._render_timeline_strip(),
        )
        _geom0 = self._load_panel_geometry()
        self._panel_manager.set_sidebar(
            lambda w, h: self._player.render(width=w, height=h),
            width=float(_geom0["sidebar_width"]),
        )
        # height here is the shared top-zone height (session player + console, side by side)
        self._panel_manager.set_console_bar(
            self._render_console_bar,
            height=float(_geom0["console_bar_height"]),
        )
        self._panel_manager.set_essential_extra(self._render_essential_extras)
        self._panel_manager.set_section_extra("EEG", self._render_eeg_controls)
        self._panel_manager.set_section_extra("OpenXR", self._render_openxr_section)
        self._panel_manager.set_section_extra("Haptic", self._render_haptic_controls)
        self._panel_manager.set_section_extra("taVNS", self._render_tavns_controls)
        self._panel_manager.set_section_extra(
            "Edison Mode", self._render_edison_controls
        )
        self._ig, self._ig_panel = install_interference_graph(self._panel_manager)

        self._biosignal_dashboard = BiosignalDashboard()
        self._last_poll_frame: int = -1

        # Restore persisted UI state
        if "debug_mode" in _geom0:
            self._panel_manager._debug_mode = _geom0["debug_mode"]
        if "section_expanded" in _geom0:
            self._panel_manager._section_expanded.update(_geom0["section_expanded"])
        if "section_order" in _geom0:
            self._panel_manager._section_order = _geom0["section_order"]

        # Clear orphaned agent state from a previous crashed session
        try:
            live = self._cfg.update()
            orphan_clear = {}
            if live.get("agent_message"):
                orphan_clear["agent_message"] = None
            if live.get("session_time"):
                orphan_clear["session_time"] = 0
            if live.get("response_timestamp"):
                orphan_clear["response_timestamp"] = None
                orphan_clear["user_response"] = None
            if live.get("tts_playing"):
                orphan_clear["tts_playing"] = None
                orphan_clear["tts_playing_ts"] = None
                orphan_clear["tts_playing_ms"] = 0
            if orphan_clear:
                patch_live(orphan_clear)
        except Exception:
            pass

        # Start audio engines and background polls
        self._start_audio()
        self._schedule_audio_poll()
        self._schedule_session_poll()

    # ── Audio engines ─────────────────────────────────────────────────────────

    def _start_audio(self) -> None:
        """Initialise pygame.mixer and start BinauralAudioEngine + TTSEngine.

        Binaural starts muted so there's no audio blast on open.  The display
        subprocess sets SDL_AUDIODRIVER=dummy and never owns the mixer.
        """
        if self._audio_on:
            return
        try:
            import pygame.mixer as _mx
            from engines.audio_engine import BinauralAudioEngine
            from engines.tts_engine import TTSEngine

            if not _mx.get_init():
                _mx.pre_init(44100, -16, 6, 512)
                _mx.init()

            patch_live({"audio_muted": True})

            self._audio_cfg = ConfigManager()
            self._audio_engine = BinauralAudioEngine(self._audio_cfg)
            self._tts_engine = TTSEngine(self._audio_cfg.config)
            self._audio_on = True
            print("[Panel] Audio engine started (binaural + noise + TTS).")
        except Exception as e:
            print(f"[Panel] Audio start failed: {e}")

    def _schedule_audio_poll(self) -> None:
        self._audio_poll_timer = threading.Timer(0.05, self._poll_audio)
        self._audio_poll_timer.daemon = True
        self._audio_poll_timer.start()

    def _poll_audio(self) -> None:
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
                    patch_live(
                        {
                            "tts_playing": phrase,
                            "tts_playing_ts": ts,
                            "tts_playing_ms": int(dur_ms),
                        }
                    )

                    def _clear() -> None:
                        patch_live({"tts_playing": None, "tts_playing_ms": 0})

                    threading.Timer(int(dur_ms) / 1000.0 + 0.3, _clear).start()
            except Exception as e:
                print(f"[Panel] TTS poll error: {e}")

        if self._audio_on and not self._live.get("audio_muted", True):
            try:
                live = self._live
                carrier = float(live.get("carrier_frequency", 209.0))
                fb = max(float(live.get("beat_frequency", 4.0)), 0.1)
                noise_v = float(live.get("noise_volume", 0)) / 100.0

                # breath_rate in live_control.json is BPM (4–20); convert to Hz
                self._console._breath_hz = (
                    max(float(live.get("breath_rate", 15.0)), 1.0) / 60.0
                )

                sr = 16384
                n = int(sr * 0.05)  # ~819 samples per 50 ms tick

                if not hasattr(self, "_wf_phase"):
                    self._wf_phase = 0.0
                t = (np.arange(n, dtype=np.float32) / sr) + self._wf_phase
                self._wf_phase += n / sr

                left = np.sin(2.0 * np.pi * carrier * t)
                right = np.sin(2.0 * np.pi * (carrier + fb) * t)

                if noise_v > 0.01:
                    noise = np.random.randn(n).astype(np.float32) * noise_v * 0.25
                    left = left + noise
                    right = right + noise

                self._console.push_audio(left, right)
            except Exception:
                pass

        self._schedule_audio_poll()

    def _stop_audio(self) -> None:
        if self._audio_poll_timer:
            self._audio_poll_timer.cancel()
            self._audio_poll_timer = None
        if self._audio_engine is not None:
            try:
                self._audio_engine.stop()
            except Exception:
                pass
        self._audio_engine = None
        self._tts_engine = None
        self._audio_on = False

    # ── Session state poll ────────────────────────────────────────────────────

    def _schedule_session_poll(self) -> None:
        self._session_poll_timer = threading.Timer(0.5, self._poll_session_state)
        self._session_poll_timer.daemon = True
        self._session_poll_timer.start()

    def _poll_session_state(self) -> None:
        """500 ms background poll: EEG scoring, record plays, agent messages,
        agent-commanded launch/stop."""
        live = self._live

        running = self._is_running()

        # EEG session scoring: trigger when display stops after ≥60 s
        if running and not self._display_was_running:
            self._display_session_start = time.time()
        elif not running and self._display_was_running:
            session_folder = live.get("session_folder", "unknown")
            duration_s = time.time() - self._display_session_start
            if duration_s >= 60.0 and self._eeg_engine is not None:
                threading.Thread(
                    target=self._trigger_eeg_scoring,
                    args=(session_folder, duration_s),
                    daemon=True,
                    name="EEGScoring",
                ).start()
        self._display_was_running = running

        # Keep SessionPlayer state in sync with the actual display process
        player_state = SessionState.RUNNING if running else SessionState.IDLE
        if self._player.state != player_state:
            self._player.state = player_state
            if not running:
                self._player._playing = -1
            else:
                cur = live.get("session_folder", "")
                if cur:
                    self._player.mark_playing(cur)

        # Record session play event when session folder changes
        cur_folder = live.get("session_folder", "")
        if cur_folder and cur_folder != self._last_session_folder:
            self._last_session_folder = cur_folder
            if running:
                try:
                    from content_tools.somna_db import record_session_played

                    record_session_played(cur_folder)
                except Exception:
                    pass

        # EEG: dead-thread cleanup + FAA baseline handoff
        if self._eeg_engine is not None and not self._eeg_engine.is_alive():
            self._console.warn("EEG thread stopped — disconnecting.", src="EEG")
            self._eeg_engine = None
            self._eeg_band_history.clear()
        if self._eeg_engine is not None and live.get("eeg_connected"):
            self._eeg_band_history.append(
                (
                    float(live.get("eeg_delta", 0) or 0),
                    float(live.get("eeg_theta", 0) or 0),
                    float(live.get("eeg_alpha", 0) or 0),
                    float(live.get("eeg_beta", 0) or 0),
                    float(live.get("eeg_gamma", 0) or 0),
                )
            )

        if self._eeg_engine is not None and live.get("eeg_faa_baseline_ready"):
            mean_val = live.get("eeg_faa_baseline_mean")
            std_val = live.get("eeg_faa_baseline_std")
            if mean_val is not None:
                self._save_faa_baseline_to_profile(
                    float(mean_val), float(std_val or 0.0)
                )
                patch_live({"eeg_faa_baseline_ready": False})

        # Agent-commanded display launch / stop
        if live.get("_agent_launch_display"):
            patch_live({"_agent_launch_display": None})
            if self._needs_session_zero():
                self._sz_pending_launch = True
                self._sz_safety_open = True
            else:
                self._launch_display()
        if live.get("_agent_stop_display"):
            patch_live({"_agent_stop_display": None})
            if self._display_proc is not None:
                self._stop_display()

        # Agent message channel → console + LLM dialog
        agent_msg = live.get("agent_message") or {}
        if isinstance(agent_msg, dict) and agent_msg.get("text"):
            msg_ts = float(agent_msg.get("ts", 0) or 0)
            if msg_ts > self._agent_msg_ts:
                self._agent_msg_ts = msg_ts
                text = agent_msg["text"]
                via = agent_msg.get("via", [])

                if text.startswith("[EEG"):
                    self._console.warn(text, src="EEG")
                elif "silent" in text.lower() and "headband" in text.lower():
                    self._console.warn(text, src="warn")
                else:
                    self._console.agent(text)

                needs_r = bool(agent_msg.get("needs_response", False))
                timeout_s = agent_msg.get("timeout_s")

                if needs_r and (
                    self._prompt_proc is None or self._prompt_proc.poll() is not None
                ):
                    args = [sys.executable, "-m", "ui.agent_prompt_dialog", text]
                    if timeout_s:
                        args.append(str(float(timeout_s)))
                    self._prompt_proc = subprocess.Popen(args, cwd=str(self._root))

        # Echo user responses back to console
        resp_ts = live.get("response_timestamp")
        if resp_ts is not None and resp_ts != getattr(self, "_last_resp_ts", None):
            self._last_resp_ts = resp_ts
            resp = live.get("user_response")
            self._console.info(f"You: {resp}" if resp else "You: (skipped)", src="you")

        # Legacy agent_console_response channel
        console_resp = live.get("agent_console_response") or ""
        if console_resp and console_resp != self._last_console_ts:
            self._last_console_ts = console_resp
            self._console.agent(console_resp)

        self._schedule_session_poll()

    def _console_append(self, text: str) -> None:
        if text.startswith("[Agent]"):
            self._console.agent(text[7:].strip())
        elif text.startswith("[You]"):
            self._console.info(text[5:].strip(), src="you")
        elif "[EEG" in text:
            self._console.system(text)
        else:
            self._console.info(text)

    def _trigger_eeg_scoring(self, session_folder: str, duration_s: float) -> None:
        """Ported from legacy control_panel.py — runs in a background thread."""
        try:
            from session.session_scorer import SessionScorer, generate_session_summary

            engine = self._eeg_engine
            if engine is None:
                return

            live = self._live
            freq_lead_data: dict = {}
            if live.get("freq_lead_phase") not in (None, "inactive"):
                freq_lead_data = {
                    "start_freq": live.get("eeg_iaf_hz"),
                    "end_freq": live.get("freq_lead_current"),
                    "holds_total": live.get("freq_lead_holds", 0),
                    "steps_completed": live.get("freq_lead_steps", 0),
                }

            session_data = engine.get_session_data_for_scoring(
                session_id=session_folder,
                session_preset=session_folder,
                duration_sec=int(duration_s),
                freq_lead_data=freq_lead_data,
            )
            if not session_data.get("sef95_series"):
                return  # no EEG data was actually collected

            scorer = SessionScorer()
            metrics = scorer.score_session(session_data)
            summary = generate_session_summary(metrics)
            score = metrics.get("composite_score", 0.0)
            print(f"[Panel] EEG session score: {score:.0f}/100 — {summary}")
            patch_live(
                {
                    "agent_message": {
                        "text": f"[EEG Scoring] {summary}",
                        "ts": time.time(),
                        "needs_response": False,
                        "via": ["console"],
                        "style": {"voice_mode": "silent"},
                    }
                }
            )
        except Exception as e:
            print(f"[Panel] EEG scoring error: {e}")

    # ── Binaural presets ──────────────────────────────────────────────────────

    def _load_binaural_presets(self) -> dict:
        try:
            return json.loads(
                (self._root / "binaural_presets.json").read_text(encoding="utf-8")
            )
        except Exception:
            return {}

    # ── OpenXR VR headset ─────────────────────────────────────────────────────

    _VR_MODES = ["ganzfeld", "photic", "rivalry", "dichoptic_ssvep"]

    def _write_vr_params(self) -> None:
        """Push current VR slider state into live_control.json."""
        mode = self._VR_MODES[self._vr_mode_idx]
        patch_live(
            {
                "vr_render_mode": mode,
                "vr_background_lum": self._vr_bg_lum,
                "vr_rivalry_left_hz": self._vr_left_hz,
                "vr_rivalry_right_hz": self._vr_right_hz,
                "vr_ssvep_left_hz": self._vr_left_hz,
                "vr_ssvep_right_hz": self._vr_right_hz,
                "vr_rivalry_depth": self._vr_depth,
                "vr_ssvep_depth": self._vr_depth,
                "vr_photic_hz": self._vr_left_hz,
                "vr_photic_depth": self._vr_depth,
                "vr_vection_enabled": self._vr_vection,
                "vr_vection_speed": self._vr_vection_speed,
            }
        )

    def _start_vr_headset(self) -> None:
        if self._vr_headset_proc and self._vr_headset_proc.poll() is None:
            return
        patch_live({"vr_headset_enabled": True})
        self._write_vr_params()
        self._vr_headset_proc = subprocess.Popen(
            [sys.executable, str(self._root / "vr" / "vr_display_runner.py")],
            cwd=str(self._root),
        )
        self._vr_status = "starting…"
        self._vr_safety = ""
        self._schedule_vr_poll()

    def _stop_vr_headset(self) -> None:
        patch_live({"vr_headset_enabled": False})
        self._vr_status = "stopping…"
        if self._vr_headset_poll:
            self._vr_headset_poll.cancel()
            self._vr_headset_poll = None
        threading.Timer(2.0, self._force_kill_vr_headset).start()

    def _force_kill_vr_headset(self) -> None:
        if self._vr_headset_proc and self._vr_headset_proc.poll() is None:
            self._vr_headset_proc.terminate()
        self._vr_headset_proc = None
        self._vr_status = "inactive"
        self._vr_safety = ""

    def _schedule_vr_poll(self) -> None:
        self._vr_headset_poll = threading.Timer(2.0, self._poll_vr_headset)
        self._vr_headset_poll.daemon = True
        self._vr_headset_poll.start()

    def _poll_vr_headset(self) -> None:
        if self._vr_headset_proc is None:
            return
        if self._vr_headset_proc.poll() is not None:
            self._vr_headset_proc = None
            self._vr_status = "inactive"
            self._vr_safety = ""
            return
        live = self._live
        if live.get("vr_safety_kill"):
            self._vr_status = "SAFETY KILL"
            self._vr_safety = "paroxysmal — stopped"
        elif live.get("vr_headset_active"):
            frames = int(live.get("vr_frame_count", 0) or 0)
            self._vr_status = f"active ({frames} fr)"
            self._vr_safety = "OK"
        else:
            self._vr_status = "starting…"
        self._schedule_vr_poll()

    def _render_openxr_section(self, avail_w: float) -> None:
        """Extra controls for the Advanced → OpenXR section (see panel_config.json)."""
        self._render_openxr_controls(avail_w, compact=False)

    def _render_openxr_controls(self, avail_w: float, *, compact: bool) -> None:
        """Native OpenXR headset runner: launch, status, and (unless compact) full tuning."""
        from ui.panel_theme import token_rgba

        vr_running = (
            self._vr_headset_proc is not None and self._vr_headset_proc.poll() is None
        )

        def _status_colors() -> None:
            if "SAFETY" in self._vr_status:
                imgui.push_style_color(
                    imgui.Col_.text, imgui.ImVec4(*hex_to_rgba("#eb6f92"))
                )
            elif "active" in self._vr_status:
                imgui.push_style_color(
                    imgui.Col_.text, imgui.ImVec4(*hex_to_rgba("#9ccfd8"))
                )
            else:
                imgui.push_style_color(
                    imgui.Col_.text, imgui.ImVec4(*hex_to_rgba("#6e6a86"))
                )

        if compact:
            imgui.separator()
            imgui.text_colored(
                imgui.ImVec4(*token_rgba("text_muted")), "OpenXR headset"
            )
            imgui.same_line()
            _status_colors()
            imgui.text(self._vr_status)
            imgui.pop_style_color()
            if self._vr_safety:
                c = "#eb6f92" if "parox" in self._vr_safety else "#9ccfd8"
                imgui.same_line()
                imgui.push_style_color(imgui.Col_.text, imgui.ImVec4(*hex_to_rgba(c)))
                imgui.text(f"  {self._vr_safety}")
                imgui.pop_style_color()

            if vr_running:
                imgui.push_style_color(
                    imgui.Col_.button, imgui.ImVec4(*hex_to_rgba("#eb6f92", 0.50))
                )
                if imgui.button("Stop OpenXR", imgui.ImVec2(avail_w, 0)):
                    self._stop_vr_headset()
                imgui.pop_style_color()
            else:
                imgui.push_style_color(
                    imgui.Col_.button, imgui.ImVec4(*hex_to_rgba("#c4a7e7", 0.35))
                )
                if imgui.button("Launch OpenXR", imgui.ImVec2(avail_w, 0)):
                    self._start_vr_headset()
                imgui.pop_style_color()
            imgui.push_style_color(
                imgui.Col_.text, imgui.ImVec4(*token_rgba("text_muted"))
            )
            imgui.text_wrapped(
                "Native ganzfeld / photic / rivalry in the HMD (pyopenxr). "
                "Not the SteamVR desktop mirror. Full tuning: switch layer to "
                "Advanced and open the OpenXR section."
            )
            imgui.pop_style_color()
            return

        imgui.separator()
        imgui.push_style_color(imgui.Col_.text, imgui.ImVec4(*token_rgba("text_muted")))
        imgui.text_wrapped(
            "Native per-eye field (ganzfeld, photic, dichoptic). "
            "This is not the SteamVR mirror — use transport Mirror on/off for that. "
            "Connect EEG while a session runs for live SSVEP readouts below."
        )
        imgui.pop_style_color()
        imgui.spacing()

        _status_colors()
        imgui.text(f"Status: {self._vr_status}")
        imgui.pop_style_color()
        if self._vr_safety:
            safety_col = "#eb6f92" if "parox" in self._vr_safety else "#9ccfd8"
            imgui.push_style_color(
                imgui.Col_.text, imgui.ImVec4(*hex_to_rgba(safety_col))
            )
            imgui.text(f"Safety: {self._vr_safety}")
            imgui.pop_style_color()

        half = max(80.0, avail_w * 0.5 - 4)
        if vr_running:
            imgui.push_style_color(
                imgui.Col_.button, imgui.ImVec4(*hex_to_rgba("#eb6f92", 0.50))
            )
            if imgui.button("Stop OpenXR", imgui.ImVec2(half, 0)):
                self._stop_vr_headset()
            imgui.pop_style_color()
        else:
            imgui.push_style_color(
                imgui.Col_.button, imgui.ImVec4(*hex_to_rgba("#c4a7e7", 0.35))
            )
            if imgui.button("Launch OpenXR", imgui.ImVec2(half, 0)):
                self._start_vr_headset()
            imgui.pop_style_color()

        imgui.same_line()
        imgui.set_next_item_width(half)
        changed, self._vr_mode_idx = imgui.combo(
            "##vr_mode", self._vr_mode_idx, self._VR_MODES
        )
        if changed:
            self._write_vr_params()

        stereo = self._VR_MODES[self._vr_mode_idx] in ("rivalry", "dichoptic_ssvep")
        lbl_w = avail_w * 0.35
        ctrl_w = avail_w - lbl_w - 8

        def _row_slider(
            label: str, val: float, lo: float, hi: float, fmt: str = "%.1f"
        ) -> float:
            imgui.text(label)
            imgui.same_line(lbl_w)
            imgui.set_next_item_width(ctrl_w)
            _, new_val = imgui.slider_float(f"##{label}", val, lo, hi, fmt)
            if imgui.is_item_deactivated_after_edit():
                self._write_vr_params()
                return new_val
            return val

        self._vr_left_hz = _row_slider(
            "Left Hz" if stereo else "Freq Hz", self._vr_left_hz, 1.0, 40.0
        )
        if stereo:
            self._vr_right_hz = _row_slider("Right Hz", self._vr_right_hz, 1.0, 40.0)
        self._vr_depth = _row_slider("Depth", self._vr_depth, 0.0, 1.0)
        self._vr_bg_lum = _row_slider("BG Lum", self._vr_bg_lum, 0.0, 1.0)

        imgui.text("Vection")
        imgui.same_line(lbl_w)
        vc_changed, self._vr_vection = imgui.checkbox("##vr_vection", self._vr_vection)
        if vc_changed:
            self._write_vr_params()
        if self._vr_vection:
            imgui.same_line()
            imgui.set_next_item_width(ctrl_w - 24)
            _, self._vr_vection_speed = imgui.slider_float(
                "##vr_vs", self._vr_vection_speed, 0.0, 1.0, "spd %.2f"
            )
            if imgui.is_item_deactivated_after_edit():
                self._write_vr_params()

        ssvep_idx = self._live.get("ssvep_binocular_index")
        ssvep_hz = self._live.get("ssvep_switch_rate_hz")
        if ssvep_idx is not None or ssvep_hz is not None:
            imgui.push_style_color(
                imgui.Col_.text, imgui.ImVec4(*hex_to_rgba("#908caa"))
            )
            parts = []
            if ssvep_idx is not None:
                parts.append(f"SSVEP idx {float(ssvep_idx):.2f}")
            if ssvep_hz is not None:
                parts.append(f"switch {float(ssvep_hz):.1f} Hz")
            imgui.text("  " + "  |  ".join(parts))
            imgui.pop_style_color()

    # ── Entry point ──────────────────────────────────────────────────────────

    def run(self) -> None:
        """Block until the panel window is closed."""
        g0 = self._load_panel_geometry()
        x, y, w, h = int(g0["x"]), int(g0["y"]), int(g0["w"]), int(g0["h"])

        runner = hello_imgui.RunnerParams()
        runner.app_window_params.window_title = "Somna"
        runner.app_window_params.window_geometry.size = [w, h]
        runner.app_window_params.window_geometry.position = [x, y]
        runner.app_window_params.window_geometry.position_mode = (
            hello_imgui.WindowPositionMode.from_coords
        )
        runner.app_window_params.resizable = True

        runner.callbacks.setup_imgui_style = self._setup_style
        runner.callbacks.load_additional_fonts = self._load_fonts
        runner.callbacks.before_exit = self._cleanup

        runner.fps_idling.enable_idling = True
        runner.fps_idling.fps_idle = 40.0
        runner.fps_idling.fps_max = 60.0

        runner.docking_params.layout_name = "Default"
        runner.ini_filename = "somna_dock_layout.ini"
        runner.ini_filename_use_app_window_title = False
        runner.imgui_window_params.default_imgui_window_type = (
            hello_imgui.DefaultImGuiWindowType.provide_full_screen_dock_space
        )

        windows: list = []
        splits: list = []

        # MainDockSpace
        #   ├── LeftCol (25% left)
        #   │     ├── Sessions (top half)
        #   │     └── Panels (bottom half) — toggle checkboxes
        #   ├── ConsoleSpace (top 25%)
        #   │     └── Console
        #   ├── ControlsSpace (strip below console)
        #   │     └── Controls
        #   └── MainDockSpace remainder — blank workspace for section windows

        split_left = hello_imgui.DockingSplit()
        split_left.initial_dock = "MainDockSpace"
        split_left.new_dock = "LeftCol"
        split_left.direction = imgui.Dir_.left
        split_left.ratio = 0.33
        split_left.node_flags = imgui.DockNodeFlags_.auto_hide_tab_bar
        splits.append(split_left)

        split_panels = hello_imgui.DockingSplit()
        split_panels.initial_dock = "LeftCol"
        split_panels.new_dock = "PanelSpace"
        split_panels.direction = imgui.Dir_.down
        split_panels.ratio = 0.20
        split_panels.node_flags = imgui.DockNodeFlags_.auto_hide_tab_bar
        splits.append(split_panels)

        split_console = hello_imgui.DockingSplit()
        split_console.initial_dock = "MainDockSpace"
        split_console.new_dock = "ConsoleSpace"
        split_console.direction = imgui.Dir_.up
        split_console.ratio = 0.25
        split_console.node_flags = imgui.DockNodeFlags_.auto_hide_tab_bar
        splits.append(split_console)

        split_controls = hello_imgui.DockingSplit()
        split_controls.initial_dock = "MainDockSpace"
        split_controls.new_dock = "ControlsSpace"
        split_controls.direction = imgui.Dir_.up
        split_controls.ratio = 0.18
        split_controls.node_flags = imgui.DockNodeFlags_.auto_hide_tab_bar
        splits.append(split_controls)

        runner.docking_params.docking_splits = splits

        # ── Windows ────────────────────────────────────────────────────────

        dw_player = hello_imgui.DockableWindow()
        dw_player.label = "Sessions"
        dw_player.dock_space_name = "LeftCol"
        dw_player.gui_function = self._render_session_player
        dw_player.is_visible = True
        dw_player.remember_is_visible = True
        dw_player.can_be_closed = False
        windows.append(dw_player)

        dw_panels = hello_imgui.DockableWindow()
        dw_panels.label = "Panels"
        dw_panels.dock_space_name = "PanelSpace"
        dw_panels.gui_function = self._render_panel_toggles
        dw_panels.is_visible = True
        dw_panels.remember_is_visible = True
        dw_panels.can_be_closed = False
        windows.append(dw_panels)

        dw_console = hello_imgui.DockableWindow()
        dw_console.label = "Console"
        dw_console.dock_space_name = "ConsoleSpace"
        dw_console.gui_function = self._render_console_window
        dw_console.is_visible = True
        dw_console.remember_is_visible = True
        dw_console.can_be_closed = False
        windows.append(dw_console)

        pm = self._panel_manager

        dw_ess = hello_imgui.DockableWindow()
        dw_ess.label = "Controls"
        dw_ess.dock_space_name = "ControlsSpace"
        dw_ess.gui_function = self._render_essential_window
        dw_ess.is_visible = True
        dw_ess.remember_is_visible = True
        dw_ess.can_be_closed = False
        windows.append(dw_ess)

        dw_dash = hello_imgui.DockableWindow()
        dw_dash.label = "Biosignal"
        dw_dash.dock_space_name = "MainDockSpace"
        dw_dash.gui_function = self._render_dashboard
        dw_dash.is_visible = True
        dw_dash.remember_is_visible = True
        dw_dash.can_be_closed = False
        dw_dash.include_in_view_menu = True
        windows.append(dw_dash)

        dw_welcome = hello_imgui.DockableWindow()
        dw_welcome.label = "Welcome"
        dw_welcome.dock_space_name = "MainDockSpace"
        dw_welcome.gui_function = self._render_welcome
        dw_welcome.is_visible = False
        dw_welcome.remember_is_visible = True
        dw_welcome.can_be_closed = False
        dw_welcome.include_in_view_menu = False
        windows.append(dw_welcome)

        for sec_name in pm.section_names():
            dw = hello_imgui.DockableWindow()
            dw.label = sec_name
            dw.dock_space_name = "MainDockSpace"
            dw.gui_function = self._make_section_renderer(sec_name)
            dw.is_visible = False
            dw.remember_is_visible = True
            dw.can_be_closed = False
            dw.include_in_view_menu = True
            windows.append(dw)

        runner.docking_params.dockable_windows = windows

        hello_imgui.run(runner)

    def _poll_live(self) -> None:
        frame = imgui.get_frame_count()
        if frame == self._last_poll_frame:
            return
        self._last_poll_frame = frame
        try:
            self._live = self._cfg.update()
        except Exception:
            pass
        self._player.agent_running = self._is_agent_running()
        self._panel_manager.update(self._live)

    def _render_session_player(self) -> None:
        self._poll_live()
        imgui.push_style_var(imgui.StyleVar_.window_padding, imgui.ImVec2(0, 0))
        avail = imgui.get_content_region_avail()
        self._player.render(width=avail.x, height=avail.y)
        imgui.pop_style_var()

    def _render_welcome(self) -> None:
        from ui.panel_theme import token_rgba

        avail = imgui.get_content_region_avail()
        imgui.set_cursor_pos(
            imgui.ImVec2(
                (avail.x - imgui.calc_text_size("Somna").x) * 0.5,
                avail.y * 0.3,
            )
        )
        imgui.text_colored(imgui.ImVec4(*token_rgba("text_muted")), "Somna")
        imgui.set_cursor_pos(
            imgui.ImVec2(
                avail.x * 0.5 - 80,
                avail.y * 0.3 + 28,
            )
        )
        imgui.text_colored(
            imgui.ImVec4(*token_rgba("text_disabled")), "Enable panels from the sidebar"
        )

    def _render_console_window(self) -> None:
        self._poll_live()
        avail_w = imgui.get_content_region_avail().x
        avail_h = imgui.get_content_region_avail().y
        self._render_console_bar(avail_w, avail_h)
        self._render_welcome_wizard()
        self._render_session_zero_modal()

    def _render_essential_window(self) -> None:
        self._poll_live()
        self._panel_manager.render_essential()
        self._session_editor.render(self._live)

    def _render_panel_toggles(self) -> None:
        imgui.push_style_var(imgui.StyleVar_.window_padding, imgui.ImVec2(4, 0))
        pm = self._panel_manager
        sec_names = pm.section_names()
        runner = hello_imgui.get_runner_params()

        all_toggles = set(sec_names)
        _mandatory = {"Sessions", "Console", "Controls", "Panels", "Welcome"}
        for dw in runner.docking_params.dockable_windows:
            if dw.include_in_view_menu and dw.label not in _mandatory:
                all_toggles.add(dw.label)

        imgui.text_disabled("Panels")
        imgui.spacing()

        for group in _PANEL_GROUPS:
            label = group["label"]
            cols = group.get("cols", 2)
            members = sorted(s for s in all_toggles if s in group["sections"])
            if not members:
                continue

            imgui.text_colored(imgui.ImVec4(*token_rgba("text_muted")), label)

            col_w = imgui.get_content_region_avail().x / cols
            for i, sec_name in enumerate(members):
                col = i % cols
                if col > 0:
                    imgui.same_line(col * col_w + 4)
                dw = runner.docking_params.dockable_window_of_name(sec_name)
                if dw is None:
                    imgui.text(sec_name)
                    continue
                visible = dw.is_visible
                _changed, visible = imgui.checkbox(f"{sec_name}##toggle", visible)
                if _changed:
                    dw.is_visible = visible
                    dw.remember_is_visible = visible

            imgui.spacing()

        uncategorized = sorted(
            s for s in all_toggles if not any(s in g["sections"] for g in _PANEL_GROUPS)
        )
        if uncategorized:
            imgui.text_colored(imgui.ImVec4(*token_rgba("text_muted")), "Other")
            col_w = imgui.get_content_region_avail().x / 2
            for i, sec_name in enumerate(uncategorized):
                col = i % 2
                if col > 0:
                    imgui.same_line(col * col_w + 4)
                dw = runner.docking_params.dockable_window_of_name(sec_name)
                if dw is None:
                    continue
                visible = dw.is_visible
                _changed, visible = imgui.checkbox(f"{sec_name}##toggle", visible)
                if _changed:
                    dw.is_visible = visible
                    dw.remember_is_visible = visible

        imgui.pop_style_var()

    def _make_section_renderer(self, name: str):
        def _render():
            self._poll_live()
            self._panel_manager.render_section_docked(name)

        return _render

    # ── hello_imgui callbacks ─────────────────────────────────────────────────

    def _setup_style(self) -> None:
        apply_somna_theme()

    def _load_fonts(self) -> None:
        load_somna_fonts()

    def _cleanup(self) -> None:
        if self._session_poll_timer:
            self._session_poll_timer.cancel()
        if self._vr_headset_poll:
            self._vr_headset_poll.cancel()
        self._stop_audio()
        self._stop_haptic()
        self._stop_tavns()
        self._save_geometry()
        self._save_user_settings()
        self._stop_display()
        self._stop_agent()
        self._force_kill_vr_headset()
        if self._state_server:
            self._state_server.stop()

    def _render_dashboard(self) -> None:
        self._poll_live()
        self._biosignal_dashboard.update(self._live)
        self._biosignal_dashboard.render()

    # ── Transport / session controls ─────────────────────────────────────────

    def _render_console_bar(
        self, bar_w: float, bar_h: float, debug_mode: bool | None = None
    ) -> None:
        """Horizontal console band at the top of the right area.

        When debug_mode is not None (sidebar mode) the Debug toggle button is
        rendered in the top-right corner of this bar.
        """
        from ui.console import (
            LogLevel,
            log_info_system_rgba_f,
            log_info_user_rgba_f,
            log_level_rgba_f,
        )

        bar_w = imgui.get_content_region_avail().x
        _console_bar_y0 = imgui.get_cursor_pos_y()

        # ── Filter toggles (label color = log line color for that stream) ──────
        filter_rows = [
            ("Agent", "level", LogLevel.AGENT),
            ("EEG", "level", LogLevel.SYSTEM),
            ("Warn", "level", LogLevel.WARNING),
            ("System", "info_system", None),
            ("You", "info_user", None),
        ]
        for label, kind, level in filter_rows:
            if kind == "level":
                cur = self._console._filters.get(level, True)
                r, g, b, a = log_level_rgba_f(level)
            elif kind == "info_system":
                cur = self._console._show_info_system
                r, g, b, a = log_info_system_rgba_f()
            else:
                cur = self._console._show_info_user
                r, g, b, a = log_info_user_rgba_f()
            if not cur:
                a *= 0.48
            imgui.push_style_color(imgui.Col_.text, imgui.ImVec4(r, g, b, a))
            _, nv = imgui.checkbox(f"{label}##cflt_{label}", cur)
            imgui.pop_style_color()
            if nv != cur:
                if kind == "level":
                    self._console._filters[level] = nv
                elif kind == "info_system":
                    self._console._show_info_system = nv
                else:
                    self._console._show_info_user = nv
            if imgui.is_item_hovered():
                if kind == "info_user":
                    tip = "Your console input. Click to show or hide."
                elif kind == "info_system":
                    tip = "General status and info lines. Click to show or hide."
                else:
                    tip = f"Log color for {label}. Click to show or hide these lines."
                imgui.set_tooltip(tip)
            imgui.same_line(spacing=4)

        # ── Conductor / IAF status string ────────────────────────────────────
        live = self._live
        csum = live.get("conductor_summary") or {}
        cphase = (
            csum.get("conductor_phase")
            or live.get("conductor_phase")
            or live.get("timeline_label", "")
        )
        iaf_v = csum.get("iaf_hz") or live.get("iaf_hz")
        frac = csum.get("frac_count", 0)
        fmax = csum.get("frac_max", 0)
        trance = live.get("eeg_trance_score")

        if cphase and cphase not in ("session_end", ""):
            iaf_s = f"{float(iaf_v):.1f} Hz" if iaf_v is not None else "—"
            tr_s = f"{float(trance):.2f}" if trance is not None else "—"
            status = f"phase: {cphase}  |  frac {frac}/{fmax}  |  IAF {iaf_s}  |  trance {tr_s}"
            status_col = imgui.ImVec4(*hex_to_rgba(RP["foam"]))
        else:
            status = "phase: —  |  frac —  |  IAF —  |  trance —"
            status_col = imgui.ImVec4(*token_rgba("text_muted"))

        # ── Right-side buttons: status | ⚙ | [E A D] ────────────────────
        btn_h = imgui.get_frame_height()
        gear_w = imgui.calc_text_size("\u2699").x + 14

        dbg_btn_w = imgui.calc_text_size("Debug").x + 16
        if debug_mode is not None:
            right_reserved = gear_w + 6 + dbg_btn_w + 2
        else:
            right_reserved = gear_w + 2

        pad = (
            bar_w
            - imgui.get_cursor_pos_x()
            - imgui.calc_text_size(status).x
            - right_reserved
        )
        if pad > 4:
            imgui.same_line(spacing=pad)
        imgui.text_colored(status_col, status)
        imgui.same_line(spacing=12)

        if imgui.button("\u2699##opensettings", imgui.ImVec2(gear_w, btn_h)):
            self._open_settings_modal()
        if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
            imgui.set_tooltip("Settings")

        if debug_mode is not None:
            imgui.same_line(spacing=4)
            if debug_mode:
                imgui.push_style_color(
                    imgui.Col_.button, imgui.ImVec4(*hex_to_rgba("#c4a7e7", 0.55))
                )
            if imgui.button("Debug##lay", imgui.ImVec2(dbg_btn_w, btn_h)):
                self._panel_manager._debug_mode = not self._panel_manager._debug_mode
            if debug_mode:
                imgui.pop_style_color()

        # same_line(0) ensures we are in mid-line state so new_line() terminates
        # cleanly without adding a blank row.
        imgui.same_line(spacing=0)
        imgui.new_line()

        # ── Spectrogram console body — fills all remaining column height ─────
        # Measure how much the filter row actually consumed instead of guessing.
        filter_consumed = imgui.get_cursor_pos_y() - _console_bar_y0
        style = imgui.get_style()
        item_h = imgui.get_frame_height()
        input_h = item_h + style.item_spacing.y * 2 + style.window_padding.y
        console_h = max(60.0, bar_h - filter_consumed - input_h)
        self._console.render(width=bar_w, height=console_h)

        # ── Send row ──────────────────────────────────────────────────────────
        imgui.set_next_item_width(bar_w - 64)
        c_enter, self._console_input = imgui.input_text(
            "##console_in",
            self._console_input,
            flags=imgui.InputTextFlags_.enter_returns_true,
        )
        imgui.same_line()
        send = c_enter
        if imgui.button("Send##cs", imgui.ImVec2(58, 0)):
            send = True
        if send and self._console_input.strip():
            msg = self._console_input.strip()
            self._console.info(msg, src="you")
            patch_live({"user_console_input": msg, "user_console_ts": time.time()})
            self._console_input = ""

        self._render_settings_modal()

    def _render_timeline_strip(self) -> None:
        """Thin strip: seek bar + pause/restart, visible only when a session is running."""
        avail_w = imgui.get_content_region_avail().x
        running = self._is_running()
        if not running:
            return

        t = float(self._live.get("session_time", 0) or 0)
        dur = float(self._live.get("session_duration", 0) or 0)
        lbl = self._live.get("timeline_label", "")
        paused = bool(self._live.get("timeline_paused", False))
        third = avail_w / 3 - 3

        if imgui.button("Resume" if paused else "Pause", imgui.ImVec2(third, 0)):
            self._send_timeline_cmd("resume" if paused else "pause")
        imgui.same_line()
        if imgui.button("Restart", imgui.ImVec2(third, 0)):
            self._send_timeline_cmd("restart")
        imgui.same_line()
        imgui.push_style_color(
            imgui.Col_.button,
            imgui.ImVec4(*hex_to_rgba("#c4a7e7", 0.45 if self._vr_mode else 0.0)),
        )
        _svr_lbl = "Mirror on" if self._vr_mode else "Mirror off"
        if imgui.button(_svr_lbl, imgui.ImVec2(third, 0)):
            self._vr_mode = not self._vr_mode
        imgui.pop_style_color()
        if imgui.is_item_hovered():
            imgui.set_tooltip(
                "Mirrors the Somna desktop window into the headset via SteamVR overlay "
                "(visual_display --vr). Separate from native OpenXR flicker — "
                "use Essential strip or Advanced → OpenXR for OpenXR."
            )

        if dur > 0:
            if not imgui.is_item_active():
                self._seek_value = t / dur
            imgui.set_next_item_width(avail_w)
            _, self._seek_value = imgui.slider_float(
                "##seek", self._seek_value, 0.0, 1.0, ""
            )
            if imgui.is_item_deactivated_after_edit():
                patch_live(
                    {
                        "seek_time": self._seek_value * dur,
                        "_timeline_cmd": "seek",
                    }
                )
            mins, secs = int(t) // 60, int(t) % 60
            tot_m, tot_s = int(dur) // 60, int(dur) % 60
            imgui.text_disabled(f"{mins}:{secs:02d} / {tot_m}:{tot_s:02d}  {lbl}")

    def _render_essential_extras(self, avail_w: float) -> None:
        """Noise color selector + binaural preset buttons for the Essential panel."""
        from ui.panel_theme import token_rgba

        _btn_gap = 4
        lbl_col = imgui.ImVec4(*token_rgba("text_muted"))
        pad_x = imgui.get_style().window_padding.x

        imgui.text_colored(lbl_col, "Noise")
        imgui.same_line(spacing=4)
        rw = max(60.0, avail_w - imgui.get_cursor_pos_x() + pad_x)
        self._render_noise_buttons(rw, btn_gap=_btn_gap)

        imgui.spacing()

        imgui.text_colored(lbl_col, "Presets")
        imgui.same_line(spacing=4)
        rw2 = max(60.0, avail_w - imgui.get_cursor_pos_x() + pad_x)
        self._render_binaural_presets(rw2, btn_gap=_btn_gap)

    def _render_noise_buttons(self, avail_w: float, *, btn_gap: float = 3.0) -> None:
        colors = [
            ("off", "#444444"),
            ("white", "#dddddd"),
            ("pink", "#e094c0"),
            ("brown", "#a06840"),
            ("blue", "#4090d0"),
            ("violet", "#9060d0"),
            ("grey", "#888888"),
        ]
        current = str(self._live.get("noise_color", "pink"))
        ng = max(0.0, float(btn_gap))
        btn_w = (avail_w - (len(colors) - 1) * ng) / len(colors)
        for i, (name, col_hex) in enumerate(colors):
            active = current == name
            if active:
                imgui.push_style_color(
                    imgui.Col_.button, imgui.ImVec4(*hex_to_rgba(col_hex, 1.0))
                )
                imgui.push_style_color(
                    imgui.Col_.text, imgui.ImVec4(0.05, 0.02, 0.08, 1.0)
                )
            else:
                imgui.push_style_color(
                    imgui.Col_.button, imgui.ImVec4(*hex_to_rgba(col_hex, 0.22))
                )
                imgui.push_style_color(
                    imgui.Col_.text, imgui.ImVec4(*hex_to_rgba(col_hex, 0.85))
                )
            if imgui.button(name.capitalize(), imgui.ImVec2(btn_w, 0)):
                patch_live({"noise_color": name})
            imgui.pop_style_color(2)
            if i < len(colors) - 1:
                imgui.same_line(spacing=ng)

    def _render_binaural_presets(self, avail_w: float, *, btn_gap: float = 3.0) -> None:
        """Band buttons (click = default freq, hover = popup preset list).
        Matches the original Tkinter nested-tooltip design."""
        from ui.panel_theme import token_rgba as _trga

        BANDS = [
            ("Delta", "\u03b4 Delta", 2.0, 0, 4),
            ("Theta", "\u03b8 Theta", 6.0, 4, 8),
            ("Alpha", "\u03b1 Alpha", 10.0, 8, 12),
            ("Beta", "\u03b2 Beta", 16.0, 12, 30),
            ("Gamma", "\u03b3 Gamma", 40.0, 30, 999),
        ]

        groups: dict[str, list] = {b[0]: [] for b in BANDS}
        for name, preset in self._binaural_presets.items():
            if not isinstance(preset, dict):
                continue
            beat = float(preset.get("beat", 10))
            for bname, _, _d, lo, hi in BANDS:
                if lo <= beat < hi:
                    groups[bname].append((name, preset))
                    break

        active = [
            (bname, blabel, default)
            for bname, blabel, default, *_ in BANDS
            if groups[bname]
        ]
        if not active:
            return

        spacing = max(0.0, float(btn_gap))
        btn_w = (avail_w - spacing * (len(active) - 1)) / len(active)

        ROW_H = 18.0
        c_name = imgui.color_convert_float4_to_u32(imgui.ImVec4(*_trga("text_value")))
        c_hz = imgui.color_convert_float4_to_u32(imgui.ImVec4(*_trga("text_muted")))
        c_desc = imgui.color_convert_float4_to_u32(imgui.ImVec4(*_trga("text_muted")))
        c_hov = imgui.IM_COL32(86, 82, 110, 90)

        for i, (bname, blabel, default_beat) in enumerate(active):
            if i > 0:
                imgui.same_line(spacing=spacing)

            if imgui.button(f"{blabel}##bb_{bname}", imgui.ImVec2(btn_w, 0)):
                patch_live({"beat_frequency": default_beat, "carrier_frequency": 200.0})

            # Capture button rect before the hover check so the popup can reference it
            btn_min = imgui.get_item_rect_min()
            btn_max = imgui.get_item_rect_max()

            # Hover → open dropdown popup with fine-tuned presets
            if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
                imgui.set_next_window_pos(
                    imgui.ImVec2(btn_min.x, btn_max.y + 2), imgui.Cond_.always
                )
                imgui.open_popup(f"##bbp_{bname}")

            imgui.set_next_window_size_constraints(
                imgui.ImVec2(max(btn_w * len(active), 240), 0),
                imgui.ImVec2(440, 260),
            )
            if imgui.begin_popup(f"##bbp_{bname}", imgui.WindowFlags_.no_move):
                # Close automatically when mouse leaves both the popup and the button
                mp = imgui.get_io().mouse_pos
                pw = imgui.get_window_pos()
                pw_end = imgui.ImVec2(
                    pw.x + imgui.get_window_width(), pw.y + imgui.get_window_height()
                )
                in_popup = pw.x <= mp.x <= pw_end.x and pw.y <= mp.y <= pw_end.y
                in_btn = (
                    btn_min.x <= mp.x <= btn_max.x and btn_min.y <= mp.y <= btn_max.y
                )
                if not in_popup and not in_btn:
                    imgui.close_current_popup()

                entries = groups[bname]
                pop_w = imgui.get_content_region_avail().x
                NAME_W = pop_w * 0.45
                HZ_W = 52.0
                dl = imgui.get_window_draw_list()
                for name, preset in entries:
                    carrier = float(preset.get("carrier", 200.0))
                    beat = float(preset.get("beat", 10.0))
                    desc = preset.get("desc", "")

                    # size=(0, ROW_H) — width 0 means "fill available", row height fixed
                    clicked, _ = imgui.selectable(
                        f"##bps_{name}",
                        False,
                        imgui.SelectableFlags_.none,
                        imgui.ImVec2(0, ROW_H),
                    )
                    if clicked:
                        patch_live(
                            {"carrier_frequency": carrier, "beat_frequency": beat}
                        )
                        imgui.close_current_popup()
                    if imgui.is_item_hovered():
                        dl.add_rect_filled(
                            imgui.get_item_rect_min(),
                            imgui.get_item_rect_max(),
                            c_hov,
                        )
                        if desc:
                            imgui.set_tooltip(
                                f"{name}  \u2014  {beat:.1f} Hz @ {int(carrier)} Hz\n{desc}"
                            )

                    p = imgui.get_item_rect_min()
                    ty = p.y + (ROW_H - imgui.get_text_line_height()) * 0.5
                    dl.add_text(imgui.ImVec2(p.x + 4, ty), c_name, name)
                    dl.add_text(imgui.ImVec2(p.x + NAME_W, ty), c_hz, f"{beat:.1f} Hz")
                    avail_desc = pop_w - NAME_W - HZ_W - 8
                    if desc and avail_desc > 20:
                        d = desc
                        ew = imgui.calc_text_size("\u2026").x
                        while d and imgui.calc_text_size(d).x > avail_desc - ew:
                            d = d[:-1]
                        if len(d) < len(desc):
                            d += "\u2026"
                        dl.add_text(imgui.ImVec2(p.x + NAME_W + HZ_W, ty), c_desc, d)

                imgui.end_popup()

    # ── Session management helpers ────────────────────────────────────────────

    def _load_session_entries(self) -> list[SessionEntry]:
        """Build SessionEntry objects from session.yaml metadata."""
        import yaml

        entries = []
        sessions_dir = self._root / "sessions"
        for name in self._session_names:
            dur, cat, desc = "", "General", ""
            try:
                data = (
                    yaml.safe_load(
                        (sessions_dir / name / "session.yaml").read_text(
                            encoding="utf-8"
                        )
                    )
                    or {}
                )
                # Top-level `duration:` key (seconds) is the canonical source
                dur_s = data.get("duration") or 0
                if not dur_s:
                    # Fall back to last keyframe time
                    kf = data.get("keyframes", [])
                    dur_s = max((k.get("time", 0) for k in kf), default=0)
                dur = f"{int(dur_s) // 60}m" if dur_s else ""
                cat = data.get("category") or data.get("defaults", {}).get(
                    "category", "General"
                )
                desc = (data.get("description") or "").strip()
            except Exception:
                pass
            entries.append(SessionEntry(name, dur, cat, desc, str(sessions_dir / name)))
        return entries

    def _launch_display_for(self, name: str) -> None:
        """Start a session by name (called from SessionPlayer callback)."""
        try:
            self._selected_session_idx = self._session_names.index(name)
        except ValueError:
            pass
        self._launch_display()

    def _scan_sessions(self) -> list[str]:
        sessions_dir = self._root / "sessions"
        if not sessions_dir.exists():
            return []
        return sorted(
            p.name
            for p in sessions_dir.iterdir()
            if p.is_dir() and (p / "session.yaml").exists()
        )

    def _load_selected_session(self) -> None:
        if not self._session_names:
            return
        name = self._session_names[self._selected_session_idx]
        patch_live({"session_folder": name, "_timeline_cmd": "load"})

    def _send_timeline_cmd(self, cmd: str) -> None:
        patch_live({"_timeline_cmd": cmd})

    def _is_running(self) -> bool:
        return self._display_proc is not None and self._display_proc.poll() is None

    def _launch_display(self) -> None:
        if self._is_running():
            return
        if self._needs_session_zero():
            self._sz_pending_launch = True
            self._sz_safety_open = True
            return
        # Zero stale session_time, unmute beats, push selected session + window prefs
        try:
            sel = (
                self._session_names[self._selected_session_idx]
                if self._session_names
                else ""
            )
            live_sel = self._live.get("session_folder", "")
            pre: dict = {"session_time": 0, "audio_muted": False}
            if sel:
                pre["session_folder"] = sel
            elif live_sel:
                pre["session_folder"] = live_sel
            # Push saved window prefs so the display subprocess reads correct values
            for k in ("window_always_on_top", "window_click_through", "window_opacity"):
                if k in self._user_settings:
                    pre[k] = self._user_settings[k]
            patch_live(pre)
        except Exception:
            pass
        args = [sys.executable, str(self._root / "visual_display_runner.py")]
        if self._vr_mode:
            args.append("--vr")
        self._display_proc = subprocess.Popen(args, cwd=str(self._root))

    def _stop_display(self) -> None:
        if self._display_proc and self._display_proc.poll() is None:
            self._display_proc.terminate()
        self._display_proc = None
        # terminate() on Windows skips visual_display_runner's finally block so
        # session_time never gets zeroed there — do it here.
        # Also clear any pending agent-relaunch command so the running agent
        # can't immediately queue a new display launch before the process is dead.
        patch_live(
            {
                "session_time": 0,
                "audio_muted": True,
                "_agent_launch_display": None,
                "_timeline_cmd": None,
                "agent_message": None,
                "user_response": None,
                "response_timestamp": None,
                "tts_playing": None,
                "tts_playing_ts": None,
                "tts_playing_ms": 0,
            }
        )
        if self._tts_engine is not None:
            with self._tts_engine._lock:
                self._tts_engine._ready.clear()
                self._tts_engine._prompt_ready.clear()
        self._console.clear()
        self._console.reset_waveform()

    def _is_agent_running(self) -> bool:
        return self._agent_proc is not None and self._agent_proc.poll() is None

    def _launch_agent(self) -> None:
        if self._is_agent_running():
            return
        self._agent_proc = subprocess.Popen(
            [sys.executable, "-m", "agent.somna_agent"],
            cwd=str(self._root),
        )

    def _stop_agent(self) -> None:
        if self._agent_proc and self._agent_proc.poll() is None:
            self._agent_proc.terminate()
        self._agent_proc = None

    def _toggle_agent(self) -> None:
        if self._is_agent_running():
            self._stop_agent()
        else:
            self._launch_agent()

    def _toggle_beats(self) -> None:
        """Toggle audio engine mute — wired to the session player's Beats button."""
        muted = bool(self._live.get("audio_muted", True))
        patch_live({"audio_muted": not muted})
        self._player._beats_on = muted  # beats_on = not muted

    def _sync_playlist_to_live(self, queue: list[str]) -> None:
        """Mirror the session queue to live_control.json so the timeline runner sees it."""
        patch_live(
            {
                "playlist": queue,
                "playlist_mode": "sequential",
                "playlist_index": 0,
            }
        )

    def _new_session(self) -> None:
        """Open the ImGui session editor for a new (blank) session."""
        new_path = self._root / "sessions" / "new_session"
        self._session_editor.open(new_path, self._live)

    def _edit_session(self, entry) -> None:
        """Open the ImGui session editor for an existing session."""
        session_path: Path | None = None
        if entry and getattr(entry, "file_path", None):
            session_path = Path(entry.file_path).parent
        self._session_editor.open(session_path, self._live)

    def _load_eeg_cfg(self) -> dict:
        try:
            import yaml

            cfg_path = self._root / "agent_config.yaml"
            with open(cfg_path, encoding="utf-8") as f:
                full = yaml.safe_load(f) or {}
            return full.get("eeg", {})
        except Exception:
            return {}

    def _connect_eeg(self) -> None:
        if self._eeg_stop_thread is not None and self._eeg_stop_thread.is_alive():
            threading.Timer(0.3, self._connect_eeg).start()
            return
        try:
            from eeg.eeg_engine import EEGEngine
        except ImportError:
            print("[Panel] EEG: brainflow not installed")
            return
        self._eeg_engine = EEGEngine(self._eeg_cfg)
        self._eeg_engine.start()
        print("[Panel] EEG engine started.")

    def _stop_eeg(self) -> None:
        old_engine = self._eeg_engine
        self._eeg_engine = None
        if old_engine is not None:

            def _do_stop() -> None:
                try:
                    old_engine.stop()
                except Exception:
                    pass

            self._eeg_stop_thread = threading.Thread(
                target=_do_stop,
                daemon=True,
                name="EEGStop",
            )
            self._eeg_stop_thread.start()
        print("[Panel] EEG engine stopping.")

    # ── Settings modal (gear button in console bar) ─────────────────────────

    _SETTINGS_TABS = ["Profile", "Agent", "Display", "Audio", "Advanced"]
    _AOPH_OPTIONS = ["none", "minimal", "moderate", "vivid"]

    def _open_settings_modal(self) -> None:
        self._settings_profile = {}
        try:
            self._settings_profile = json.loads(
                (self._root / "user_profile.json").read_text(encoding="utf-8")
            )
        except Exception:
            pass
        self._settings_name_buf = (
            self._settings_profile.get("name")
            or self._settings_profile.get("user_name")
            or ""
        )
        aph = self._settings_profile.get("aphantasia") or "none"
        self._settings_aph_idx = (
            self._AOPH_OPTIONS.index(aph) if aph in self._AOPH_OPTIONS else 0
        )
        self._settings_sel_modality = -1
        self._settings_sel_note = -1
        self._settings_sel_goal = -1
        self._load_agent_cfg_buf()
        self._settings_open = True

    def _load_agent_cfg_buf(self) -> None:
        self._agent_cfg_buf = {}
        try:
            import yaml

            raw = (self._root / "agent_config.yaml").read_text(encoding="utf-8")
            self._agent_cfg_buf = yaml.safe_load(raw) or {}
        except Exception:
            pass
        self._agent_url_buf = str(self._agent_cfg_buf.get("base_url", ""))
        self._agent_key_buf = str(self._agent_cfg_buf.get("api_key", ""))
        self._agent_model_buf = str(self._agent_cfg_buf.get("model", ""))
        self._agent_test_status = ""
        self._agent_test_running = False

    def _save_agent_cfg_buf(self) -> None:
        try:
            import yaml

            path = self._root / "agent_config.yaml"
            raw = path.read_text(encoding="utf-8")
            cfg = yaml.safe_load(raw) or {}
            cfg["base_url"] = self._agent_url_buf
            cfg["api_key"] = self._agent_key_buf
            cfg["model"] = self._agent_model_buf
            out_lines = []
            for line in raw.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("base_url:") or stripped.startswith("base_url "):
                    out_lines.append(f'base_url: "{self._agent_url_buf}"')
                elif stripped.startswith("api_key:") or stripped.startswith("api_key "):
                    if self._agent_key_buf:
                        out_lines.append(f'api_key: "{self._agent_key_buf}"')
                    else:
                        out_lines.append('api_key: ""')
                elif stripped.startswith("model:") or stripped.startswith("model "):
                    out_lines.append(f'model:    "{self._agent_model_buf}"')
                else:
                    out_lines.append(line)
            path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
            self._console.info(
                "Agent config saved. Restart agent to apply.", src="settings"
            )
        except Exception as e:
            self._console.error(f"Failed to save agent config: {e}")

    def _test_agent_connection(self) -> None:
        import urllib.request
        import urllib.error

        self._agent_test_running = True
        self._agent_test_status = "Testing..."
        url = self._agent_url_buf.rstrip("/")
        if "/v1" not in url:
            url += "/v1"
        endpoint = f"{url}/models"
        api_key = self._agent_key_buf or None
        try:
            req = urllib.request.Request(
                endpoint, headers={"Content-Type": "application/json"}
            )
            if api_key:
                req.add_header("Authorization", f"Bearer {api_key}")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    self._agent_test_status = "OK — connected"
                else:
                    self._agent_test_status = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            self._agent_test_status = f"HTTP {e.code}"
        except Exception as e:
            self._agent_test_status = f"Failed: {e}"
        self._agent_test_running = False

    def _render_settings_modal(self) -> None:
        from ui.panel_theme import token_rgba as _trga

        if self._settings_open:
            imgui.open_popup("Settings##settings")
            self._settings_open = False

        centre = imgui.get_main_viewport().get_center()
        imgui.set_next_window_pos(centre, imgui.Cond_.appearing, imgui.ImVec2(0.5, 0.5))
        imgui.set_next_window_size_constraints(
            imgui.ImVec2(520, 300), imgui.ImVec2(680, 9999)
        )

        opened, _ = imgui.begin_popup_modal(
            "Settings##settings",
            flags=imgui.WindowFlags_.always_auto_resize,
        )
        if not opened:
            return

        muted = imgui.ImVec4(*_trga("text_muted"))
        val = imgui.ImVec4(*_trga("text_value"))
        iris = imgui.ImVec4(*_trga("source_agent"))
        foam = imgui.ImVec4(*_trga("button_bg"))
        love = imgui.ImVec4(*_trga("alert_red"))
        green = imgui.ImVec4(*_trga("success_green"))
        avail_w = imgui.get_content_region_avail().x

        if imgui.begin_tab_bar("##settings_tabs"):
            for i, tab_name in enumerate(self._SETTINGS_TABS):
                selected, _ = imgui.begin_tab_item(f"{tab_name}##stab{i}")
                if selected:
                    self._settings_tab = i
                    if i == 0:
                        self._render_settings_profile(avail_w, muted, val, iris, _trga)
                    elif i == 1:
                        self._render_settings_agent(
                            avail_w, muted, val, iris, foam, green
                        )
                    elif i == 2:
                        self._render_settings_display(avail_w, muted, val)
                    elif i == 3:
                        self._render_settings_audio(avail_w, muted, val)
                    elif i == 4:
                        self._render_settings_advanced(avail_w, muted, val, love)
                    imgui.end_tab_item()
            imgui.end_tab_bar()

        imgui.spacing()
        imgui.separator()
        btn_w = 90.0
        imgui.set_cursor_pos_x((avail_w - btn_w) * 0.5)
        if imgui.button("Close##settingsclose", imgui.ImVec2(btn_w, 0)):
            imgui.close_current_popup()
            self._settings_sel_note = -1
            self._settings_sel_goal = -1

        imgui.end_popup()

    # ── Profile tab ──────────────────────────────────────────────────────────

    def _render_settings_profile(self, avail_w, muted, val, iris, _trga):
        p = self._settings_profile

        def _read():
            try:
                return json.loads(
                    (self._root / "user_profile.json").read_text(encoding="utf-8")
                )
            except Exception:
                return {}

        def _write(updated):
            try:
                (self._root / "user_profile.json").write_text(
                    json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                self._settings_profile = updated
            except Exception as e:
                self._console.error(f"Profile write failed: {e}")

        iaf = p.get("iaf_hz")
        sessions = p.get("total_sessions") or 0

        imgui.text_colored(muted, "Name")
        imgui.same_line(spacing=8)
        imgui.set_next_item_width(160)
        name_changed, new_name = imgui.input_text("##setname", self._settings_name_buf)
        if name_changed:
            self._settings_name_buf = new_name
            updated = _read()
            updated["name"] = new_name
            updated["user_name"] = new_name
            _write(updated)

        imgui.same_line(spacing=16)
        imgui.text_colored(muted, "Aphantasia")
        imgui.same_line(spacing=8)
        imgui.set_next_item_width(110)
        aph_changed, new_aph_idx = imgui.combo(
            "##setaph", self._settings_aph_idx, self._AOPH_OPTIONS
        )
        if aph_changed:
            self._settings_aph_idx = new_aph_idx
            updated = _read()
            updated["aphantasia"] = self._AOPH_OPTIONS[new_aph_idx]
            _write(updated)

        imgui.same_line(spacing=16)
        if iaf:
            imgui.text_colored(muted, f"IAF {float(iaf):.1f} Hz")
            imgui.same_line(spacing=16)
        imgui.text_colored(muted, f"Sessions {sessions}")
        imgui.spacing()

        # Personality mode toggle
        imgui.text_colored(muted, "Agent Style")
        imgui.same_line(spacing=8)
        imgui.set_next_item_width(130)
        pers_modes = ["guide", "directive"]
        cur_pers = p.get("personality_mode", "guide")
        cur_pers_idx = pers_modes.index(cur_pers) if cur_pers in pers_modes else 0
        pers_changed, new_pers_idx = imgui.combo("##setpers", cur_pers_idx, pers_modes)
        if pers_changed:
            updated = _read()
            if pers_modes[new_pers_idx] == "guide":
                updated.pop("personality_mode", None)
            else:
                updated["personality_mode"] = pers_modes[new_pers_idx]
            _write(updated)
        imgui.same_line(spacing=8)
        imgui.text_colored(
            val if cur_pers == "directive" else muted,
            "Commanding" if cur_pers == "directive" else "Warm & permissive",
        )
        imgui.spacing()

        modalities = list(p.get("modality_preference") or [])
        if modalities:
            imgui.text_colored(iris, "Modality preference")
            if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
                imgui.set_tooltip(
                    "Order the agent uses when choosing language and sensory anchors.\n"
                    "Drag with \u2191 \u2193 to prioritise."
                )
            btn_w = 22.0
            swap_a, swap_b = -1, -1
            for i, mod in enumerate(modalities):
                selected = self._settings_sel_modality == i
                if selected:
                    imgui.push_style_color(
                        imgui.Col_.text, imgui.ImVec4(*_trga("success_green"))
                    )
                clicked, _ = imgui.selectable(
                    f"  {i + 1}. {mod}##smod{i}",
                    selected,
                    imgui.SelectableFlags_.none,
                    imgui.ImVec2(avail_w - btn_w * 2 - 16, 0),
                )
                if selected:
                    imgui.pop_style_color()
                if clicked:
                    self._settings_sel_modality = i if not selected else -1
                imgui.same_line()
                imgui.begin_disabled(i == 0)
                if imgui.button(f"\u2191##su{i}", imgui.ImVec2(btn_w, 0)):
                    swap_a, swap_b = i - 1, i
                imgui.end_disabled()
                imgui.same_line(spacing=2)
                imgui.begin_disabled(i == len(modalities) - 1)
                if imgui.button(f"\u2193##sd{i}", imgui.ImVec2(btn_w, 0)):
                    swap_a, swap_b = i, i + 1
                imgui.end_disabled()
            if swap_a >= 0:
                updated = _read()
                mods = list(updated.get("modality_preference") or modalities)
                mods[swap_a], mods[swap_b] = mods[swap_b], mods[swap_a]
                updated["modality_preference"] = mods
                _write(updated)
                self._settings_sel_modality = (
                    swap_b
                    if swap_a == self._settings_sel_modality
                    else swap_a
                    if swap_b == self._settings_sel_modality
                    else self._settings_sel_modality
                )

        designations = p.get("designations") or []
        if designations:
            imgui.spacing()
            imgui.text_colored(muted, "Designations")
            imgui.push_text_wrap_pos(0.0)
            imgui.text_colored(
                imgui.ImVec4(*_trga("source_user_lock")), "  ".join(designations)
            )
            imgui.pop_text_wrap_pos()
            if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
                imgui.set_tooltip(
                    "Assigned by the agent based on session history. Read-only."
                )

        imgui.separator()
        imgui.spacing()

        imgui.text_colored(iris, "Notes")
        imgui.same_line(
            spacing=avail_w
            - imgui.calc_text_size("Notes").x
            - imgui.calc_text_size("Clear All").x
            - 24
        )
        if imgui.small_button("Clear All##sclrnotes"):
            updated = _read()
            updated["notes"] = []
            _write(updated)
            self._settings_sel_note = -1
        notes = list(p.get("notes") or [])
        imgui.begin_child(
            "##snotes_list",
            imgui.ImVec2(avail_w, 100),
            child_flags=imgui.ChildFlags_.borders,
        )
        for i, note in enumerate(notes):
            text = note if isinstance(note, str) else str(note)
            selected = self._settings_sel_note == i
            clicked, _ = imgui.selectable(
                f"{text}##sn{i}",
                selected,
                imgui.SelectableFlags_.none,
                imgui.ImVec2(0, 0),
            )
            if clicked:
                self._settings_sel_note = i if not selected else -1
        imgui.end_child()
        if imgui.button("Delete Selected##sdelnote"):
            if 0 <= self._settings_sel_note < len(notes):
                updated = _read()
                ns = list(updated.get("notes") or [])
                ns.pop(self._settings_sel_note)
                updated["notes"] = ns
                _write(updated)
                self._settings_sel_note = -1

        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        imgui.text_colored(iris, "Goals")
        imgui.same_line(
            spacing=avail_w
            - imgui.calc_text_size("Goals").x
            - imgui.calc_text_size("Clear All").x
            - 24
        )
        if imgui.small_button("Clear All##sclrgoals"):
            updated = _read()
            updated["goals"] = []
            _write(updated)
            self._settings_sel_goal = -1
        goals = list(p.get("goals") or [])
        imgui.begin_child(
            "##sgoals_list",
            imgui.ImVec2(avail_w, 80),
            child_flags=imgui.ChildFlags_.borders,
        )
        for i, goal in enumerate(goals):
            label = (
                goal.get("title") or goal.get("text") or str(goal)
                if isinstance(goal, dict)
                else str(goal)
            )
            nc = len(goal.get("progress_notes", [])) if isinstance(goal, dict) else 0
            if nc:
                label = f"{label}  ({nc} notes)"
            selected = self._settings_sel_goal == i
            clicked, _ = imgui.selectable(
                f"{label}##sg{i}",
                selected,
                imgui.SelectableFlags_.none,
                imgui.ImVec2(0, 0),
            )
            if clicked:
                self._settings_sel_goal = i if not selected else -1
            if isinstance(goal, dict) and goal.get("description"):
                if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
                    imgui.set_tooltip(goal["description"])
        imgui.end_child()
        if imgui.button("Delete Selected##sdelgoal"):
            if 0 <= self._settings_sel_goal < len(goals):
                updated = _read()
                gs = list(updated.get("goals") or [])
                gs.pop(self._settings_sel_goal)
                updated["goals"] = gs
                _write(updated)
                self._settings_sel_goal = -1

        themes = p.get("responsive_themes") or []
        if themes:
            imgui.spacing()
            imgui.text_colored(iris, "Responsive themes")
            imgui.push_text_wrap_pos(0.0)
            imgui.text_colored(muted, "  ".join(themes))
            imgui.pop_text_wrap_pos()

    # ── Agent tab ────────────────────────────────────────────────────────────

    def _render_settings_agent(self, avail_w, muted, val, iris, foam, green):
        imgui.text_colored(iris, "LLM Configuration")
        imgui.spacing()

        imgui.set_next_item_width(avail_w - 8)
        imgui.text_colored(muted, "Endpoint URL")
        imgui.set_next_item_width(avail_w - 8)
        url_changed, new_url = imgui.input_text("##agenturl", self._agent_url_buf)
        if url_changed:
            self._agent_url_buf = new_url

        imgui.spacing()
        imgui.text_colored(muted, "API Key")
        imgui.set_next_item_width(avail_w - 8)
        key_changed, new_key = imgui.input_text(
            "##agentkey", self._agent_key_buf, flags=imgui.InputTextFlags_.password
        )
        if key_changed:
            self._agent_key_buf = new_key

        imgui.spacing()
        imgui.text_colored(muted, "Model")
        imgui.set_next_item_width(avail_w - 8)
        model_changed, new_model = imgui.input_text(
            "##agentmodel", self._agent_model_buf
        )
        if model_changed:
            self._agent_model_buf = new_model

        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        btn_w = 120.0
        if imgui.button("Test Connection##agenttest", imgui.ImVec2(btn_w, 0)):
            threading.Thread(
                target=self._test_agent_connection, daemon=True, name="AgentTestConn"
            ).start()
        imgui.same_line(spacing=8)
        if self._agent_test_status:
            is_ok = self._agent_test_status.startswith("OK")
            col = green if is_ok else imgui.ImVec4(*token_rgba("alert_red"))
            imgui.text_colored(col, self._agent_test_status)

        imgui.spacing()
        imgui.spacing()

        save_w = 100.0
        if imgui.button("Save##agentsave", imgui.ImVec2(save_w, 0)):
            self._save_agent_cfg_buf()
        imgui.same_line(spacing=8)
        imgui.text_colored(muted, "Restart agent to apply changes.")

        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        imgui.text_colored(muted, "Agent config: agent_config.yaml")
        if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
            imgui.set_tooltip(
                "Edit this file directly for advanced settings\n(sampling params, knowledge files, idle planning)."
            )

    # ── Display tab ──────────────────────────────────────────────────────────

    def _render_settings_display(self, avail_w, muted, val):
        settings = self._user_settings
        live = self._live or {}

        imgui.text_colored(imgui.ImVec4(*token_rgba("source_agent")), "Window")
        imgui.spacing()

        aot = bool(settings.get("window_always_on_top", True))
        changed, new_aot = imgui.checkbox("Always on top##saot", aot)
        if changed:
            self._user_settings["window_always_on_top"] = new_aot
            patch_live({"window_always_on_top": new_aot})
            self._save_user_settings()

        ct = bool(settings.get("window_click_through", True))
        changed, new_ct = imgui.checkbox("Click-through##sct", ct)
        if changed:
            self._user_settings["window_click_through"] = new_ct
            patch_live({"window_click_through": new_ct})
            self._save_user_settings()

        opacity = float(settings.get("window_opacity", 100))
        imgui.set_next_item_width(200)
        changed, new_opacity = imgui.slider_float(
            "Opacity##sopac", opacity, 10, 100, "%.0f%%"
        )
        if changed:
            self._user_settings["window_opacity"] = new_opacity
            patch_live({"window_opacity": new_opacity})
            self._save_user_settings()

    # ── Audio tab ────────────────────────────────────────────────────────────

    def _render_settings_audio(self, avail_w, muted, val):
        settings = self._user_settings

        imgui.text_colored(imgui.ImVec4(*token_rgba("source_agent")), "TTS")
        imgui.spacing()

        voice = str(settings.get("tts_voice", ""))
        imgui.text_colored(muted, "Voice")
        imgui.same_line(spacing=8)
        imgui.set_next_item_width(avail_w - 80)
        changed, new_voice = imgui.input_text("##sttsvoice", voice)
        if changed:
            self._user_settings["tts_voice"] = new_voice
            patch_live({"tts_voice": new_voice})
            self._save_user_settings()

        if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
            imgui.set_tooltip(
                "Edge TTS voice name (e.g. en-US-AriaNeural).\nList voices: edge-tts --list-voices"
            )

    # ── Advanced tab ─────────────────────────────────────────────────────────

    def _render_settings_advanced(self, avail_w, muted, val, love):
        imgui.text_colored(imgui.ImVec4(*token_rgba("source_agent")), "Danger Zone")
        imgui.spacing()

        if imgui.button("Reset Onboarding##resetonboard", imgui.ImVec2(180, 0)):
            try:
                p = json.loads(
                    (self._root / "user_profile.json").read_text(encoding="utf-8")
                )
                p["onboarding_complete"] = False
                p.pop("engagement", None)
                (self._root / "user_profile.json").write_text(
                    json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                self._console.warn(
                    "Onboarding reset. Restart agent to re-run.", src="settings"
                )
            except Exception as e:
                self._console.error(f"Failed to reset onboarding: {e}")
        if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
            imgui.set_tooltip(
                "Clears onboarding_complete flag and engagement data.\nAgent will re-run onboarding on next start."
            )

        imgui.spacing()

        if imgui.button("Recalibrate IAF##recaliaf", imgui.ImVec2(180, 0)):
            live = self._live or {}
            if live.get("eeg_connected"):
                patch_live({"eeg_needs_iaf_calibration": True})
                self._console.info("IAF recalibration requested.", src="settings")
            else:
                self._console.warn("Connect EEG first.", src="settings")
        if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
            imgui.set_tooltip(
                "Re-run Individual Alpha Frequency calibration.\nRequires connected EEG headset."
            )

    # ── Welcome wizard (first-run modal) ─────────────────────────────────────

    def _check_welcome(self) -> None:
        if self._welcome_checked:
            return
        self._welcome_checked = True
        try:
            p = json.loads(
                (self._root / "user_profile.json").read_text(encoding="utf-8")
            )
        except Exception:
            p = {}
        eng = p.get("engagement", {})
        if eng.get("onboarding_complete"):
            return
        self._welcome_active = True
        self._welcome_step = 0
        self._welcome_name_buf = ""
        self._welcome_goals_buf = ""
        self._welcome_hw_status = ""
        self._welcome_hw_scanned = False
        try:
            import yaml

            cfg = (
                yaml.safe_load(
                    (self._root / "agent_config.yaml").read_text(encoding="utf-8")
                )
                or {}
            )
        except Exception:
            cfg = {}
        self._welcome_llm_url_buf = str(cfg.get("base_url", ""))
        self._welcome_llm_key_buf = str(cfg.get("api_key", ""))
        self._welcome_llm_model_buf = str(cfg.get("model", ""))

    def _render_welcome_wizard(self) -> None:
        self._check_welcome()
        if not self._welcome_active:
            return

        from ui.panel_theme import token_rgba as _trga

        imgui.open_popup("Welcome to Somna##welcome")

        centre = imgui.get_main_viewport().get_center()
        imgui.set_next_window_pos(centre, imgui.Cond_.appearing, imgui.ImVec2(0.5, 0.5))
        imgui.set_next_window_size(imgui.ImVec2(520, 400))

        opened, _ = imgui.begin_popup_modal(
            "Welcome to Somna##welcome",
            flags=imgui.WindowFlags_.no_resize | imgui.WindowFlags_.no_move,
        )
        if not opened:
            return

        muted = imgui.ImVec4(*_trga("text_muted"))
        val = imgui.ImVec4(*_trga("text_value"))
        iris = imgui.ImVec4(*_trga("source_agent"))
        foam = imgui.ImVec4(*_trga("text_value"))
        avail_w = imgui.get_content_region_avail().x
        step = self._welcome_step
        total_steps = 5

        # Progress dots
        for i in range(total_steps):
            if i > 0:
                imgui.same_line(spacing=4)
            col = iris if i <= step else muted
            filled = "\u25cf" if i <= step else "\u25cb"
            imgui.text_colored(col, filled)
        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        if step == 0:
            self._render_welcome_0(avail_w, muted, val, iris)
        elif step == 1:
            self._render_welcome_1(avail_w, muted, val, iris)
        elif step == 2:
            self._render_welcome_2(avail_w, muted, val, iris)
        elif step == 3:
            self._render_welcome_3(avail_w, muted, val, iris)
        elif step == 4:
            self._render_welcome_4(avail_w, muted, val, iris)

        imgui.end_popup()

    def _finish_welcome(self) -> None:
        try:
            p = json.loads(
                (self._root / "user_profile.json").read_text(encoding="utf-8")
            )
        except Exception:
            p = {}
        goals = [g.strip() for g in self._welcome_goals_buf.split(",") if g.strip()]
        p["name"] = self._welcome_name_buf or "friend"
        p["user_name"] = p["name"]
        p.setdefault("engagement", {})["onboarding_complete"] = True
        p.setdefault("engagement", {})["total_sessions"] = 0
        if goals:
            p["goals"] = [
                {"id": g.lower(), "title": g, "description": "", "progress_notes": []}
                for g in goals
            ]
        (self._root / "user_profile.json").write_text(
            json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._welcome_active = False
        imgui.close_current_popup()

    # Step 0: Welcome
    def _render_welcome_0(self, avail_w, muted, val, iris):
        imgui.spacing()
        imgui.spacing()
        imgui.text_colored(iris, "Welcome to Somna.")
        imgui.spacing()
        imgui.push_text_wrap_pos(avail_w)
        imgui.text_colored(
            muted,
            "Somna is a neurofeedback and hypnosis platform that uses binaural beats, "
            "visual entrainment, and an AI companion to guide you into deep relaxation "
            "and altered states.",
        )
        imgui.spacing()
        imgui.text_colored(muted, "Let's get you set up. This takes about a minute.")
        imgui.pop_text_wrap_pos()
        imgui.spacing()
        imgui.spacing()
        imgui.spacing()
        imgui.set_cursor_pos_x((avail_w - 120) * 0.5)
        if imgui.button("Get Started##w0next", imgui.ImVec2(120, 0)):
            self._welcome_step = 1

    # Step 1: Name + Goals
    def _render_welcome_1(self, avail_w, muted, val, iris):
        imgui.text_colored(iris, "About You")
        imgui.spacing()

        imgui.text_colored(muted, "What should I call you?")
        imgui.set_next_item_width(avail_w - 16)
        _, self._welcome_name_buf = imgui.input_text("##wname", self._welcome_name_buf)

        imgui.spacing()
        imgui.spacing()
        imgui.text_colored(muted, "What brings you here?")
        imgui.set_next_item_width(avail_w - 16)
        _, self._welcome_goals_buf = imgui.input_text(
            "##wgoals",
            self._welcome_goals_buf,
            flags=imgui.InputTextFlags_.enter_returns_true,
        )
        if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
            imgui.set_tooltip("e.g. relaxation, sleep, focus, curiosity, pleasure")

        imgui.spacing()
        imgui.spacing()
        has_input = bool(self._welcome_name_buf.strip())
        if not has_input:
            imgui.begin_disabled()
        imgui.set_cursor_pos_x((avail_w - 120) * 0.5)
        if imgui.button("Next##w1next", imgui.ImVec2(120, 0)):
            self._welcome_step = 2
        if not has_input:
            imgui.end_disabled()

    # Step 2: Hardware scan
    def _render_welcome_2(self, avail_w, muted, val, iris):
        imgui.text_colored(iris, "Hardware")
        imgui.spacing()
        imgui.push_text_wrap_pos(avail_w)
        imgui.text_colored(
            muted,
            "Somna works with Muse EEG headbands, Lovense haptic devices, and "
            "DG Labs Coyote electrodes. These are optional — audio and visuals "
            "work great on their own.",
        )
        imgui.pop_text_wrap_pos()
        imgui.spacing()

        if not self._welcome_hw_scanned:
            if imgui.button("Scan for Devices##w2scan", imgui.ImVec2(180, 0)):
                self._welcome_hw_status = self._do_hw_scan()
                self._welcome_hw_scanned = True
            imgui.same_line(spacing=8)
            imgui.text_colored(muted, "or")
            imgui.same_line(spacing=8)
            if imgui.button("Skip##w2skip", imgui.ImVec2(80, 0)):
                self._welcome_hw_status = "skipped"
                self._welcome_hw_scanned = True
        else:
            if self._welcome_hw_status == "skipped":
                imgui.text_colored(muted, "Skipped. You can connect devices anytime.")
            elif self._welcome_hw_status:
                imgui.text_colored(val, self._welcome_hw_status)
            else:
                imgui.text_colored(
                    muted,
                    "No devices found. That's fine — audio/visual mode works great.",
                )
            imgui.spacing()

        if self._welcome_hw_scanned:
            imgui.set_cursor_pos_x((avail_w - 120) * 0.5)
            if imgui.button("Next##w2next", imgui.ImVec2(120, 0)):
                self._welcome_step = 3

    def _do_hw_scan(self) -> str:
        found = []
        try:
            import brainflow

            found.append("BrainFlow available (EEG support ready)")
        except ImportError:
            pass
        if not found:
            return ""
        return "; ".join(found)

    # Step 3: LLM setup
    def _render_welcome_3(self, avail_w, muted, val, iris):
        imgui.text_colored(iris, "AI Companion")
        imgui.spacing()
        imgui.push_text_wrap_pos(avail_w)
        imgui.text_colored(
            muted,
            "Somna's AI companion adapts sessions to you in real time, guides you "
            "through experiences, and learns what works best. It requires an LLM endpoint "
            "(local or cloud).",
        )
        imgui.pop_text_wrap_pos()
        imgui.spacing()

        imgui.text_colored(muted, "Endpoint URL")
        imgui.set_next_item_width(avail_w - 16)
        _, self._welcome_llm_url_buf = imgui.input_text(
            "##wllmurl", self._welcome_llm_url_buf
        )
        imgui.spacing()

        imgui.text_colored(muted, "API Key")
        imgui.set_next_item_width(avail_w - 16)
        _, self._welcome_llm_key_buf = imgui.input_text(
            "##wllmkey", self._welcome_llm_key_buf, flags=imgui.InputTextFlags_.password
        )
        imgui.spacing()

        imgui.text_colored(muted, "Model Name")
        imgui.set_next_item_width(avail_w - 16)
        _, self._welcome_llm_model_buf = imgui.input_text(
            "##wllmmodel", self._welcome_llm_model_buf
        )
        imgui.spacing()

        if imgui.button("Test Connection##wllmtest", imgui.ImVec2(140, 0)):
            threading.Thread(
                target=self._do_welcome_llm_test, daemon=True, name="WelcomeLLMTest"
            ).start()
        imgui.same_line(spacing=8)
        if self._welcome_llm_test_status:
            is_ok = self._welcome_llm_test_status.startswith("OK")
            col = (
                imgui.ImVec4(*token_rgba("success_green"))
                if is_ok
                else imgui.ImVec4(*token_rgba("alert_red"))
            )
            imgui.text_colored(col, self._welcome_llm_test_status)
        if self._welcome_llm_test_running:
            imgui.same_line(spacing=4)
            imgui.text_colored(muted, "...")

        imgui.spacing()
        imgui.spacing()

        has_url = bool(self._welcome_llm_url_buf.strip())
        if has_url:
            if imgui.button("Save & Next##w3next", imgui.ImVec2(140, 0)):
                self._save_welcome_llm()
                self._welcome_step = 4
            imgui.same_line(spacing=8)
        imgui.text_colored(muted, "or")
        imgui.same_line(spacing=8)
        if imgui.button("Skip for now##w3skip", imgui.ImVec2(120, 0)):
            self._welcome_step = 4

    def _do_welcome_llm_test(self) -> None:
        import urllib.request
        import urllib.error

        self._welcome_llm_test_running = True
        self._welcome_llm_test_status = "Testing..."
        url = self._welcome_llm_url_buf.rstrip("/")
        if "/v1" not in url:
            url += "/v1"
        try:
            req = urllib.request.Request(
                f"{url}/models", headers={"Content-Type": "application/json"}
            )
            if self._welcome_llm_key_buf:
                req.add_header("Authorization", f"Bearer {self._welcome_llm_key_buf}")
            with urllib.request.urlopen(req, timeout=5) as resp:
                self._welcome_llm_test_status = (
                    "OK — connected" if resp.status == 200 else f"HTTP {resp.status}"
                )
        except urllib.error.HTTPError as e:
            self._welcome_llm_test_status = f"HTTP {e.code}"
        except Exception as e:
            self._welcome_llm_test_status = f"Failed: {e}"
        self._welcome_llm_test_running = False

    def _save_welcome_llm(self) -> None:
        try:
            path = self._root / "agent_config.yaml"
            raw = path.read_text(encoding="utf-8")
            out_lines = []
            for line in raw.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("base_url:") or stripped.startswith("base_url "):
                    out_lines.append(f'base_url: "{self._welcome_llm_url_buf}"')
                elif stripped.startswith("api_key:") or stripped.startswith("api_key "):
                    if self._welcome_llm_key_buf:
                        out_lines.append(f'api_key: "{self._welcome_llm_key_buf}"')
                    else:
                        out_lines.append('api_key: ""')
                elif stripped.startswith("model:") or stripped.startswith("model "):
                    out_lines.append(f'model:    "{self._welcome_llm_model_buf}"')
                else:
                    out_lines.append(line)
            path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        except Exception:
            pass

    # Step 4: Ready
    def _render_welcome_4(self, avail_w, muted, val, iris):
        imgui.spacing()
        imgui.spacing()
        imgui.text_colored(iris, "You're all set.")
        imgui.spacing()
        imgui.push_text_wrap_pos(avail_w)
        imgui.text_colored(
            muted,
            "Your session library is on the left. Pick one and hit play to begin. "
            "The console above is where the AI companion talks to you.",
        )
        imgui.spacing()
        llm_ok = bool(self._welcome_llm_url_buf.strip())
        if not llm_ok:
            imgui.text_colored(
                imgui.ImVec4(*token_rgba("warning_amber")),
                "No LLM configured. You can set one up later in Settings \u2192 Agent.",
            )
            imgui.spacing()
        imgui.text_colored(
            muted,
            "Click the \u2699 gear icon in the console bar anytime to change settings.",
        )
        imgui.pop_text_wrap_pos()
        imgui.spacing()
        imgui.spacing()
        imgui.spacing()
        imgui.set_cursor_pos_x((avail_w - 120) * 0.5)
        if imgui.button("Let's Go##w4done", imgui.ImVec2(120, 0)):
            self._finish_welcome()

    # ── Session Zero safety/consent modal ────────────────────────────────────────

    def _needs_session_zero(self) -> bool:
        if self._sz_safety_checked:
            return False
        try:
            p = json.loads(
                (self._root / "user_profile.json").read_text(encoding="utf-8")
            )
        except Exception:
            return True
        if p.get("session_zero_status") in ("complete", "complete_minimal"):
            self._sz_safety_checked = True
            return False
        eng = p.get("engagement", {})
        if not eng.get("onboarding_complete"):
            return False
        return True

    def _render_session_zero_modal(self) -> None:
        if not self._sz_safety_open:
            return

        from ui.panel_theme import token_rgba as _trga

        imgui.open_popup("Session Zero##sz")

        centre = imgui.get_main_viewport().get_center()
        imgui.set_next_window_pos(centre, imgui.Cond_.appearing, imgui.ImVec2(0.5, 0.5))
        imgui.set_next_window_size(imgui.ImVec2(520, 420))

        opened, _ = imgui.begin_popup_modal(
            "Session Zero##sz",
            flags=imgui.WindowFlags_.no_resize,
        )
        if not opened:
            return

        muted = imgui.ImVec4(*_trga("text_muted"))
        val = imgui.ImVec4(*_trga("text_value"))
        iris = imgui.ImVec4(*_trga("source_agent"))
        love = imgui.ImVec4(*_trga("alert_red"))
        green = imgui.ImVec4(*_trga("success_green"))
        avail_w = imgui.get_content_region_avail().x

        imgui.text_colored(iris, "Before your first session")
        imgui.spacing()
        imgui.push_text_wrap_pos(avail_w)
        imgui.text_colored(
            muted, "A few quick safety items to acknowledge. This only appears once."
        )
        imgui.pop_text_wrap_pos()
        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        imgui.text_colored(val, "Photosensitive screening")
        imgui.push_text_wrap_pos(avail_w - 10)
        imgui.text_colored(
            muted,
            "Somna uses rhythmic visual effects (spirals, flicker, color washes). "
            "Have you ever had seizures, migraines, or strong discomfort triggered by "
            "flashing lights?",
        )
        imgui.pop_text_wrap_pos()
        _, self._sz_photo_check = imgui.checkbox(
            "I do not have photosensitive epilepsy or related conditions##sz_photo",
            self._sz_photo_check,
        )
        if not self._sz_photo_check:
            _, self._sz_photo_risk = imgui.checkbox(
                "I have a history of photosensitivity but accept the risk##sz_photorisk",
                self._sz_photo_risk,
            )
        else:
            self._sz_photo_risk = False
        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        imgui.text_colored(val, "Subliminal content (SSB)")
        imgui.push_text_wrap_pos(avail_w - 10)
        imgui.text_colored(
            muted,
            "Somna can display affirmation text below your threshold of conscious "
            "perception, reinforcing your chosen content. You will not consciously see "
            "these messages. This is entirely optional and can be changed in Settings.",
        )
        imgui.pop_text_wrap_pos()
        _, self._sz_ssb_check = imgui.checkbox(
            "Enable subliminal text blending (optional)##sz_ssb",
            self._sz_ssb_check,
        )
        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        imgui.text_colored(val, "Safety acknowledgment")
        imgui.push_text_wrap_pos(avail_w - 10)
        imgui.text_colored(
            muted,
            "You can stop any session at any time by closing the display window or "
            "pressing the stop button. If you have a VR headset, do not use it if you "
            "feel disoriented. Binaural beats work best with headphones. Do not use "
            "while driving or operating machinery.",
        )
        imgui.pop_text_wrap_pos()
        _, self._sz_safety_ack = imgui.checkbox(
            "I understand and accept##sz_ack",
            self._sz_safety_ack,
        )
        imgui.spacing()

        can_proceed = self._sz_safety_ack and (
            self._sz_photo_check or self._sz_photo_risk
        )

        btn_w = 120.0
        imgui.set_cursor_pos_x((avail_w - btn_w) * 0.5)
        if not can_proceed:
            imgui.begin_disabled(True)
        if imgui.button("Begin##sz_begin", imgui.ImVec2(btn_w, 0)):
            self._finish_session_zero()
        if not can_proceed:
            imgui.end_disabled()

        if not self._sz_safety_ack:
            imgui.spacing()
            imgui.text_colored(
                muted, "Please acknowledge the safety information above."
            )

        imgui.end_popup()

    def _finish_session_zero(self) -> None:
        import datetime

        try:
            profile_path = self._root / "user_profile.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            profile = {}

        profile["session_zero_status"] = "complete_minimal"
        profile["session_zero_completed_utc"] = datetime.datetime.utcnow().isoformat(
            timespec="seconds"
        )
        profile["safety_consent"] = {
            "photosensitive_risk": "elevated" if self._sz_photo_risk else "normal",
            "ssb_enabled": self._sz_ssb_check,
            "safety_acknowledged": True,
            "acknowledged_utc": datetime.datetime.utcnow().isoformat(
                timespec="seconds"
            ),
        }

        profile_path.write_text(
            json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        if self._sz_photo_risk:
            patch_live({"photic_driving_disabled": True})

        self._sz_safety_open = False
        self._sz_safety_checked = True
        imgui.close_current_popup()

        if self._sz_pending_launch:
            self._sz_pending_launch = False
            self._launch_display()

    # ── EEG device control panel ──────────────────────────────────────────────

    def _render_eeg_controls(self, avail_w: float) -> None:
        """Device connect / IAF calibration controls at the top of the EEG section."""
        from ui.panel_theme import token_rgba as _trga

        avail_w = imgui.get_content_region_avail().x
        live = dict(self._live)
        connected = bool(live.get("eeg_connected"))
        synthetic = bool(
            self._eeg_cfg.get("synthetic", self._eeg_cfg.get("eeg_synthetic", True))
        )
        engine_up = self._eeg_engine is not None

        # Status dot + label
        if engine_up and connected:
            dot_col = imgui.ImVec4(*_trga("success_green"))
            status = "Connected" + (" (synthetic)" if synthetic else "")
        elif engine_up:
            dot_col = imgui.ImVec4(*_trga("source_user_lock"))
            status = "Connecting\u2026"
        else:
            dot_col = imgui.ImVec4(*_trga("text_muted"))
            status = "Disconnected"

        imgui.text_colored(dot_col, "\u25cf")
        imgui.same_line(spacing=4)
        imgui.text_colored(imgui.ImVec4(*_trga("text_muted")), status)

        imgui.spacing()

        # Connect / Disconnect button
        btn_w = (avail_w - imgui.get_style().item_spacing.x) * 0.5
        if engine_up:
            if imgui.button("Disconnect##eeg_dis", imgui.ImVec2(btn_w, 0)):
                self._stop_eeg()
        else:
            if imgui.button("Connect Muse##eeg_con", imgui.ImVec2(btn_w, 0)):
                self._connect_eeg()

        imgui.same_line(spacing=4)

        # IAF Calibration button — only enabled when connected and not synthetic
        iaf_ready = engine_up and connected and not synthetic
        if not iaf_ready:
            imgui.begin_disabled()
        if imgui.button("IAF Calibration##eeg_iaf", imgui.ImVec2(btn_w, 0)):
            self._run_iaf_calibration()
        if not iaf_ready:
            imgui.end_disabled()
        if imgui.is_item_hovered(imgui.HoveredFlags_.delay_short):
            if iaf_ready:
                imgui.set_tooltip(
                    "Record 30 s of resting EEG to measure your Individual\n"
                    "Alpha Frequency (IAF). Used to personalise beat targeting."
                )
            else:
                imgui.set_tooltip("Connect a real Muse headset to run IAF calibration.")

        # Board type indicator + last IAF result
        board_id = self._eeg_cfg.get("board_id", self._eeg_cfg.get("eeg_board_id", 38))
        board_name = {38: "Muse 2", 39: "Muse S"}.get(board_id, f"Board {board_id}")
        iaf_hz = live.get("eeg_iaf_hz") or live.get("iaf_hz")

        imgui.spacing()
        muted = imgui.ImVec4(*_trga("text_muted"))
        val = imgui.ImVec4(*_trga("text_value"))
        imgui.text_colored(muted, f"Board: ")
        imgui.same_line(spacing=3)
        imgui.text_colored(val, "Synthetic" if synthetic else board_name)
        if iaf_hz is not None:
            imgui.same_line(spacing=12)
            imgui.text_colored(muted, "IAF: ")
            imgui.same_line(spacing=3)
            imgui.text_colored(val, f"{float(iaf_hz):.1f} Hz")

        # Live calibration readout — visible while cal is running
        cal_status = live.get("calibration_status", "")
        if cal_status in ("recording", "extending"):
            remaining = live.get("calibration_time_remaining_s")
            conf = live.get("calibration_iaf_confidence") or 0.0
            hint = str(live.get("calibration_hint") or "")
            conf_str = f"  ·  {conf:.0%}" if conf else ""
            rem_str = f"{int(remaining)} s" if remaining is not None else "…"
            status_col = (
                imgui.ImVec4(*_trga("source_user_lock"))
                if cal_status == "extending"
                else imgui.ImVec4(*_trga("warning_amber"))
            )
            imgui.text_colored(
                status_col, f"{cal_status.capitalize()}… {rem_str}{conf_str}"
            )
            if hint:
                imgui.push_text_wrap_pos(0.0)
                imgui.text_colored(muted, hint)
                imgui.pop_text_wrap_pos()

        imgui.separator()

        if connected:
            self._render_eeg_monitor(avail_w)

    # ── Haptic device control panel ──────────────────────────────────────────────

    def _render_haptic_controls(self, avail_w: float) -> None:
        """Connect / disconnect / ping-back controls for Lovense haptic device."""
        live = dict(self._live)
        connected = bool(live.get("haptic_connected"))
        engine_up = self._haptic_engine is not None

        from imgui_bundle import imgui

        btn_w = avail_w * 0.48

        if engine_up and connected:
            name = live.get("haptic_device_name", "?")
            motors = live.get("haptic_motor_count", "?")
            imgui.text_colored(
                imgui.ImVec4(0.27, 0.80, 0.40, 1.0),
                f"Connected: {name} ({motors} motors)",
            )
        elif engine_up:
            imgui.text_colored(imgui.ImVec4(0.94, 0.69, 0.57, 1.0), "Connecting...")
        else:
            imgui.text("No device")

        if imgui.button(
            "Disconnect##haptic_dis" if connected else "Connect Lovense##haptic_con",
            imgui.ImVec2(btn_w, 0),
        ):
            if connected:
                self._stop_haptic()
            else:
                self._connect_haptic()

        imgui.same_line()
        ping_enabled = engine_up and connected
        if not ping_enabled:
            imgui.begin_disabled(True)
        if imgui.button("Ping##haptic_ping", imgui.ImVec2(btn_w, 0)):
            if self._haptic_engine is not None:
                self._haptic_engine.ping_back()
        if not ping_enabled:
            imgui.end_disabled()

    def _connect_haptic(self) -> None:
        try:
            from engines.haptic_engine import HapticEngine
        except ImportError:
            self._console.warn("haptic_engine not available.", src="Haptic")
            return
        self._haptic_engine = HapticEngine()
        ok = self._haptic_engine.start()
        if ok:
            self._console.system("Lovense haptic engine connecting...", src="Haptic")
        else:
            self._console.warn(
                "buttplug-py not installed or connection failed.", src="Haptic"
            )
            self._haptic_engine = None

    def _stop_haptic(self) -> None:
        if self._haptic_engine is not None:
            self._haptic_engine.stop()
            self._haptic_engine = None
            from ipc import patch_live

            patch_live({"haptic_connected": False, "haptic_actual_intensity": 0.0})
            self._console.system("Lovense haptic engine stopped.", src="Haptic")

    # ── taVNS device control panel ───────────────────────────────────────────────

    def _render_tavns_controls(self, avail_w: float) -> None:
        """Connect / disconnect / impedance check for DG Labs Coyote."""
        live = dict(self._live)
        connected = bool(live.get("tavns_connected"))
        engine_up = self._tavns_engine is not None

        from imgui_bundle import imgui

        btn_w = avail_w * 0.48

        if engine_up and connected:
            imp_ok = bool(live.get("tavns_impedance_ok"))
            imp_ohm = float(live.get("tavns_impedance_ohm", 0))
            col = (
                imgui.ImVec4(0.27, 0.80, 0.40, 1.0)
                if imp_ok
                else imgui.ImVec4(0.94, 0.69, 0.57, 1.0)
            )
            imp_str = "OK" if imp_ok else "HIGH"
            imgui.text_colored(
                col, f"Connected · Impedance: {imp_ohm:.0f} Ohm ({imp_str})"
            )
        elif engine_up:
            imgui.text_colored(imgui.ImVec4(0.94, 0.69, 0.57, 1.0), "Connecting...")
        else:
            imgui.text("No device")

        if imgui.button(
            "Disconnect##tavns_dis" if connected else "Connect Coyote##tavns_con",
            imgui.ImVec2(btn_w, 0),
        ):
            if connected:
                self._stop_tavns()
            else:
                self._connect_tavns()

        imgui.same_line()
        imp_btn_enabled = engine_up and connected
        if not imp_btn_enabled:
            imgui.begin_disabled(True)
        if imgui.button("Check Impedance##tavns_imp", imgui.ImVec2(btn_w, 0)):
            if self._tavns_engine is not None:
                ok = self._tavns_engine.check_impedance()
                status = "OK" if ok else "HIGH — check electrode placement"
                self._console.system(f"Impedance check: {status}", src="taVNS")
        if not imp_btn_enabled:
            imgui.end_disabled()

    def _connect_tavns(self) -> None:
        try:
            from engines.tavns_engine import TavnsEngine
        except ImportError:
            self._console.warn("tavns_engine not available.", src="taVNS")
            return
        self._tavns_engine = TavnsEngine()
        ok = self._tavns_engine.start()
        if ok:
            self._console.system(
                "DG Labs Coyote taVNS engine connecting...", src="taVNS"
            )
        else:
            self._console.warn(
                "pydglab-v3 not installed, impedance check failed, or connection failed.",
                src="taVNS",
            )
            self._tavns_engine = None

    def _stop_tavns(self) -> None:
        if self._tavns_engine is not None:
            self._tavns_engine.stop()
            self._tavns_engine = None
            from ipc import patch_live

            patch_live({"tavns_connected": False, "tavns_actual_current_ua": 0.0})
            self._console.system("DG Labs Coyote taVNS engine stopped.", src="taVNS")

    def _render_edison_controls(self, avail_w: float) -> None:
        """Edison Mode controls — only meaningful when edison_active is True."""
        from ui.panel_theme import token_rgba as _trga

        live = dict(self._live)
        edison_active = bool(live.get("edison_active"))
        if not edison_active:
            imgui.text_disabled("Not active (launch an Edison session)")
            return

        edison_state = str(live.get("edison_state", ""))
        cycle_count = int(live.get("edison_cycle_count", 0))
        seed_topic = str(live.get("edison_seed_topic", ""))

        from ui.panel_widgets import draw_badge

        state_colors = {
            "PREPARATION": "text_muted",
            "SEED_DELIVERY": "text_label",
            "MONITORING": "slider_grab",
            "N1_HOLD": "alert_amber",
            "CAPTURE": "warning_amber",
            "CYCLE_COMPLETE": "success_green",
            "SESSION_END": "text_muted",
        }
        badge_color = state_colors.get(edison_state, "text_primary")
        draw_badge(edison_state, _trga(badge_color))
        imgui.same_line()
        imgui.text(f"Cycle {cycle_count}")

        if seed_topic:
            imgui.text(f"Seed: {seed_topic}")

        at_ratio = live.get("eeg_alpha_theta_ratio")
        if at_ratio is not None:
            imgui.text(f"Alpha/Theta: {float(at_ratio):.2f}")

        sleep_stage = str(live.get("eeg_sleep_stage", "WAKE"))
        imgui.text(f"Sleep stage: {sleep_stage}")

        imgui.separator()

        if edison_state == "PREPARATION":
            if imgui.button("Ready"):
                from ipc import patch_live

                patch_live({"edison_user_ready": True})

        elif edison_state == "N1_HOLD":
            n1_entry_ts = live.get("edison_n1_entry_timestamp")
            if n1_entry_ts:
                import time as _t

                elapsed = _t.time() - float(n1_entry_ts)
                hold_target = float(live.get("edison_n1_hold_seconds", 60))
                imgui.text(f"N1 hold: {elapsed:.0f}s / {hold_target:.0f}s")

        elif edison_state == "CAPTURE":
            imgui.text_colored(*_trga("warning_amber"), "Listening for response...")

        elif edison_state == "CYCLE_COMPLETE":
            if imgui.button("Another cycle"):
                from ipc import patch_live

                patch_live({"edison_continue": True})
            imgui.same_line()
            if imgui.button("End session"):
                from ipc import patch_live

                patch_live({"edison_end_session": True})

    def _render_eeg_monitor(self, avail_w: float) -> None:
        """EEG brainwave monitor — only rendered when eeg_connected is true."""
        from ui.panel_theme import token_rgba as _trga

        avail_w = imgui.get_content_region_avail().x
        live = dict(self._live)

        # ── Color palette (u32 for draw list, ImVec4 for text) ──────────────────
        # Band colors: delta→iris, theta→foam, alpha→pine, beta→gold, gamma→rose
        from ui.panel_theme import hex_to_u32 as _u32

        C_DELTA = token_u32("source_agent")  # iris
        C_THETA = token_u32("success_green")  # foam
        C_ALPHA = _u32(RP["pine"], 1.0)  # pine
        C_BETA = token_u32("source_user_lock")  # gold
        C_GAMMA = _u32(RP["rose"], 1.0)  # rose

        BAND_COLS_U32 = [C_DELTA, C_THETA, C_ALPHA, C_BETA, C_GAMMA]
        BAND_NAMES = ["δ Delta", "θ Theta", "α Alpha", "β Beta", "γ Gamma"]
        BAND_KEYS = ["eeg_delta", "eeg_theta", "eeg_alpha", "eeg_beta", "eeg_gamma"]

        muted = imgui.ImVec4(*_trga("text_muted"))
        val = imgui.ImVec4(*_trga("text_value"))
        c_foam = imgui.ImVec4(*_trga("success_green"))
        c_gold = imgui.ImVec4(*_trga("source_user_lock"))
        c_love = imgui.ImVec4(*_trga("alert_red"))

        BAR_H = 9.0
        # Consistent label column: widest label + small gap
        LABEL_W = max(imgui.calc_text_size(n).x for n in BAND_NAMES) + 8
        start_x = imgui.get_cursor_pos_x()  # window-local X at the left margin

        # ── 1. Band power bars ───────────────────────────────────────────────────
        for key, name, col in zip(BAND_KEYS, BAND_NAMES, BAND_COLS_U32):
            val_f = max(0.0, min(1.0, float(live.get(key) or 0.0)))

            # Label
            imgui.text_colored(muted, name)
            imgui.same_line(spacing=0)

            # Snap cursor to consistent bar-start X, then measure remaining space
            imgui.set_cursor_pos_x(start_x + LABEL_W)
            bar_x, bar_y = imgui.get_cursor_screen_pos()
            bar_w = imgui.get_content_region_avail().x

            dl = imgui.get_window_draw_list()
            dl.add_rect_filled(
                imgui.ImVec2(bar_x, bar_y),
                imgui.ImVec2(bar_x + bar_w, bar_y + BAR_H),
                _u32(RP["hl_low"], 1.0),
                2.0,
            )
            if val_f > 0.0:
                dl.add_rect_filled(
                    imgui.ImVec2(bar_x, bar_y),
                    imgui.ImVec2(bar_x + bar_w * val_f, bar_y + BAR_H),
                    col,
                    2.0,
                )
            imgui.dummy(imgui.ImVec2(bar_w, BAR_H))

        imgui.spacing()

        # ── 2. Derived metrics strip ─────────────────────────────────────────────
        eeg_state = str(live.get("eeg_state") or "").replace("_", " ")
        sef95 = live.get("eeg_sef95")
        trance_raw = (
            live.get("eeg_trance_score_v2") or live.get("eeg_trance_score") or 0.0
        )
        trance = float(trance_raw)

        if eeg_state:
            imgui.text_colored(val, eeg_state)
            imgui.same_line(spacing=12)
        if sef95 is not None:
            imgui.text_colored(muted, f"SEF95 {float(sef95):.1f} Hz")
            imgui.same_line(spacing=12)

        # Trance score: interpolate foam→gold→love
        if trance <= 0.5:
            t2 = trance * 2.0
            tr_col = imgui.ImVec4(
                c_foam.x + (c_gold.x - c_foam.x) * t2,
                c_foam.y + (c_gold.y - c_foam.y) * t2,
                c_foam.z + (c_gold.z - c_foam.z) * t2,
                1.0,
            )
        else:
            t2 = (trance - 0.5) * 2.0
            tr_col = imgui.ImVec4(
                c_gold.x + (c_love.x - c_gold.x) * t2,
                c_gold.y + (c_love.y - c_gold.y) * t2,
                c_gold.z + (c_love.z - c_gold.z) * t2,
                1.0,
            )
        imgui.text_colored(tr_col, f"Trance {trance:.2f}")

        imgui.spacing()

        # ── 3. FAA balance bar ───────────────────────────────────────────────────
        faa_state = str(live.get("eeg_faa_state") or "insufficient_data")
        if faa_state != "insufficient_data":
            faa_val = float(live.get("eeg_faa") or 0.0)
            faa_val = max(-1.0, min(1.0, faa_val))

            FAA_H = 8.0
            half_w = (avail_w - LABEL_W) * 0.5

            cp = imgui.get_cursor_screen_pos()
            dl = imgui.get_window_draw_list()
            center_x = cp.x + LABEL_W + half_w

            # Track
            dl.add_rect_filled(
                imgui.ImVec2(cp.x + LABEL_W, cp.y),
                imgui.ImVec2(cp.x + LABEL_W + half_w * 2.0, cp.y + FAA_H),
                _u32(RP["hl_low"], 1.0),
                2.0,
            )
            # Fill
            fill_col = _u32(RP["foam"], 1.0) if faa_val >= 0 else _u32(RP["love"], 1.0)
            if faa_val >= 0:
                dl.add_rect_filled(
                    imgui.ImVec2(center_x, cp.y),
                    imgui.ImVec2(center_x + half_w * faa_val, cp.y + FAA_H),
                    fill_col,
                    2.0,
                )
            else:
                dl.add_rect_filled(
                    imgui.ImVec2(center_x + half_w * faa_val, cp.y),
                    imgui.ImVec2(center_x, cp.y + FAA_H),
                    fill_col,
                    2.0,
                )
            # Center tick
            dl.add_line(
                imgui.ImVec2(center_x, cp.y - 1),
                imgui.ImVec2(center_x, cp.y + FAA_H + 1),
                _u32(RP["subtle"], 1.0),
                1.0,
            )

            sign_str = f"+{faa_val:.2f}" if faa_val >= 0 else f"{faa_val:.2f}"
            imgui.text_colored(muted, "FAA")
            imgui.same_line(spacing=0)
            imgui.dummy(imgui.ImVec2(half_w * 2.0 + 4, FAA_H))
            imgui.same_line(spacing=8)
            faa_col = c_foam if faa_val >= 0 else c_love
            imgui.text_colored(faa_col, f"{sign_str}  {faa_state}")

            imgui.spacing()

        # ── 4. ASSR / entrainment row ────────────────────────────────────────────
        ent_strength = live.get("eeg_entrainment_strength")
        ent_conf = str(live.get("eeg_entrainment_confidence") or "")
        if ent_strength is not None:
            conf_active = ent_conf.lower().startswith("active")
            assr_col = c_foam if conf_active else muted
            imgui.text_colored(
                assr_col, f"ASSR  {float(ent_strength):.2f}  {ent_conf[:6]}"
            )
            imgui.spacing()

        # ── 5. Per-channel SQI dots ──────────────────────────────────────────────
        SQI_KEYS = ["eeg_sqi_tp9", "eeg_sqi_af7", "eeg_sqi_af8", "eeg_sqi_tp10"]
        SQI_LABELS = ["TP9", "AF7", "AF8", "TP10"]

        def _sqi_col(v: float) -> imgui.ImVec4:
            if v >= 0.7:
                return c_foam
            if v >= 0.4:
                return c_gold
            return c_love

        imgui.text_colored(muted, "SQI ")
        imgui.same_line(spacing=4)
        for label, key in zip(SQI_LABELS, SQI_KEYS):
            sqi = float(live.get(key) or 0.0)
            imgui.text_colored(muted, label)
            imgui.same_line(spacing=2)
            imgui.text_colored(_sqi_col(sqi), "\u25c6")  # ◆
            imgui.same_line(spacing=8)
        imgui.new_line()

        imgui.spacing()

        # ── 6. Scrolling band history ────────────────────────────────────────────
        HIST_H = 60.0
        SAMPLES = 90
        history = list(self._eeg_band_history)

        imgui.begin_child(
            "##eeg_hist",
            imgui.ImVec2(avail_w, HIST_H),
            child_flags=imgui.ChildFlags_.none,
            window_flags=(
                imgui.WindowFlags_.no_scroll_with_mouse
                | imgui.WindowFlags_.no_scrollbar
            ),
        )
        cpos = imgui.get_cursor_screen_pos()
        cw = imgui.get_content_region_avail().x
        dl = imgui.get_window_draw_list()

        # Background
        dl.add_rect_filled(
            cpos,
            imgui.ImVec2(cpos.x + cw, cpos.y + HIST_H),
            _u32(RP["hl_low"], 1.0),
        )

        if history:
            col_w = cw / SAMPLES
            n = len(history)
            x_off = (SAMPLES - n) * col_w  # right-align recent samples

            for si, sample in enumerate(history):
                x0 = cpos.x + x_off + si * col_w
                x1 = x0 + col_w + 0.5  # tiny overlap avoids gaps
                y_bottom = cpos.y + HIST_H
                y_cur = y_bottom

                for band_val, col in zip(sample, BAND_COLS_U32):
                    seg_h = band_val * HIST_H
                    if seg_h < 0.5:
                        continue
                    dl.add_rect_filled(
                        imgui.ImVec2(x0, y_cur - seg_h),
                        imgui.ImVec2(x1, y_cur),
                        col,
                    )
                    y_cur -= seg_h

        imgui.end_child()

        imgui.spacing()

    def _run_iaf_calibration(self) -> None:
        """Fire IAF calibration in a background thread and write result to live."""
        engine = self._eeg_engine
        if engine is None:
            return

        def _do_cal() -> None:
            try:
                result = engine.run_iaf_calibration(duration_s=30.0)
                if isinstance(result, (int, float)):
                    iaf = float(result)
                    patch_live({"eeg_iaf_hz": iaf, "iaf_hz": iaf})
                    self._save_iaf_to_profile(iaf)
                    self._console.system(
                        f"IAF calibration complete: {iaf:.2f} Hz", src="EEG"
                    )
                else:
                    self._console.warn("IAF calibration returned no result.", src="EEG")
            except Exception as e:
                self._console.error(f"IAF calibration failed: {e}", src="EEG")

        threading.Thread(target=_do_cal, daemon=True, name="IAFCal").start()
        self._console.system("IAF calibration started (30 s)…", src="EEG")

    def _save_iaf_to_profile(self, iaf_hz: float) -> None:
        """Reload-merge user_profile.json with IAF result. Same pattern as Tk."""
        from eeg.eeg_engine import build_iaf_profile_update

        profile_path = self._root / "user_profile.json"
        try:
            profile = (
                json.loads(profile_path.read_text(encoding="utf-8"))
                if profile_path.exists()
                else {}
            )
            live = self._cfg.update()
            iaf_conf = live.get("calibration_iaf_confidence")
            profile.update(build_iaf_profile_update(iaf_hz, iaf_conf))
            profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            conf_str = f"  conf={iaf_conf:.2f}" if iaf_conf is not None else ""
            self._console.system(
                f"IAF saved to profile: {iaf_hz:.2f} Hz{conf_str}", src="EEG"
            )
        except Exception as exc:
            self._console.error(f"Failed to save IAF to profile: {exc}", src="EEG")

    def _save_faa_baseline_to_profile(self, mean: float, std: float) -> None:
        """Reload-merge user_profile.json with FAA resting baseline."""
        import datetime

        profile_path = self._root / "user_profile.json"
        try:
            profile = (
                json.loads(profile_path.read_text(encoding="utf-8"))
                if profile_path.exists()
                else {}
            )
            profile["faa_baseline_mean"] = round(mean, 4)
            profile["faa_baseline_std"] = round(std, 4)
            profile["faa_baseline_calibrated_at"] = datetime.datetime.now().isoformat(
                timespec="seconds"
            )
            profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            self._console.system(
                f"FAA baseline saved: mean={mean:.4f}  std={std:.4f}", src="EEG"
            )
        except Exception as exc:
            self._console.error(f"Failed to save FAA baseline: {exc}", src="EEG")
