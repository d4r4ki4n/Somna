"""
timeline_runner.py
Somna — Session Timeline Runner

Runs as a background thread. Reads session.yaml, tracks elapsed time,
interpolates parameter values between keyframes, and writes results to
live_control.json every 100ms.

User keyframe locks: if a value in live_control.json differs from what
the runner wrote last tick, something external (user slider, LLM) changed
it. That parameter is locked until the timeline crosses the next keyframe
that includes it, at which point the timeline reasserts control.
"""

import threading
import time
import json
import math
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from ipc import patch_live


# ── Parameters that interpolate vs cut instantly ──────────────────────────────

INTERPOLATABLE = {
    # Audio
    "beat_frequency",
    "carrier_frequency",
    "volume",
    "noise_volume",
    # Veil / background
    "veil_opacity",
    "veil_scroll_speed_x",
    "veil_scroll_speed_y",
    "slideshow_interval",
    "bg_opacity",
    # Text timing
    "center_flash_on_time",
    "center_flash_off_time",
    "flash_duty_cycle",
    "flash_variance",
    # Shadows
    "shadow_opacity",
    "shadow_flash_on_time",
    "shadow_flash_off_time",
    # Spirals — all numeric properties interpolate smoothly
    "spiral_opacity",
    "spiral_tightness",
    "spiral_chaos",
    "spiral_count",
    "spiral_thickness",
    "spiral_speed_multiplier",
    "entrainment_strength",
    "trail_decay",
    "feedback_strength",
    "sr_noise_level",
    # Post-processing pipeline
    "pp_bloom_intensity",
    "pp_ca_strength",
    "pp_film_grain",
    # TTS FX chain (entrainment_effects.md §2)
    "tts_reverb_wet",
    "tts_reverb_room_ms",
    "tts_delay_ms",
    "tts_delay_feedback",
    # FM entrainment
    "fm_mod_depth",
    # Bilateral panning
    "bilateral_rate",
    "bilateral_depth",
}

INSTANT_ONLY = {
    "spiral_style",
    "font_switch_mode",
    "veil_mode",
    "center_flash_sync_to_beat",
    "spiral_show_text",
    "spiral_color_mode",
    "start_fullscreen",
    "beat_sync_master",
    "phrases",
    "audio_muted",
    "beat_type",
    "carrier_waveform",
    "noise_color",
    "bilateral_panning",
    "bilateral_mode",
    "tts_enabled",
    "tts_subliminal",
    "tts_duck_ms",
    "tts_duck_trigger",
    "feedback_mode",
}

# Application-level fallbacks — used if not set in session defaults or timeline
APP_DEFAULTS = {
    # Audio
    "beat_frequency": 10.0,
    "carrier_frequency": 200.0,
    "volume": 80.0,
    # Veil / background
    "veil_opacity": 45.0,
    "veil_scroll_speed_x": 1.2,
    "veil_scroll_speed_y": 0.8,
    "veil_mode": None,
    "slideshow_interval": 3.0,
    # Text timing
    "center_flash_on_time": 120,
    "center_flash_off_time": 80,
    "center_flash_sync_to_beat": True,
    "flash_duty_cycle": 0.38,
    "flash_variance": 0.22,
    # Shadows
    "shadow_opacity": 25,
    "shadow_flash_on_time": 40,
    "shadow_flash_off_time": 180,
    # Spirals
    "spiral_style": "tunnel_dream",
    "spiral_count": 4,
    "spiral_opacity": 88,
    "spiral_tightness": 6.0,
    "spiral_chaos": 0.1,
    "spiral_thickness": 14,
    "spiral_speed_multiplier": 1.0,
    "spiral_color_mode": "rainbow",
    "spiral_show_text": False,
    # Text / font
    "font_switch_mode": "intelligent",
    # Affirmations
    "phrases": None,
    # Audio on/off — sessions default to beats ON; user "Stop Beats" creates a lock
    "audio_muted": False,
    "beat_type": "binaural",
    "noise_volume": 30.0,
    "noise_color": "pink",
}


# ── Easing functions ──────────────────────────────────────────────────────────


def _ease(t: float, curve: str) -> float:
    """t is 0.0→1.0 progress. Returns eased 0.0→1.0."""
    t = max(0.0, min(1.0, t))
    if curve == "instant":
        return 1.0
    if curve == "linear":
        return t
    if curve == "ease_in":
        return t * t
    if curve == "ease_out":
        return 1.0 - (1.0 - t) ** 2
    if curve == "ease_in_out":
        return t * t * (3.0 - 2.0 * t)  # smoothstep
    return t  # fallback to linear


def _interpolate(a: float, b: float, t: float, curve: str) -> float:
    return a + (b - a) * _ease(t, curve)


# ── Session loader ────────────────────────────────────────────────────────────


class Session:
    """Parsed representation of a session.yaml."""

    def __init__(self, session_path: Path):
        self.path = session_path
        self.yaml_file = session_path / "session.yaml"
        self.affirmations_file = session_path / "affirmations.txt"

        raw = {}
        if self.yaml_file.exists():
            with open(self.yaml_file, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}

        self.name: str = raw.get("name", session_path.name)
        self.description: str = raw.get("description", "")
        self.duration: Optional[float] = raw.get("duration", None)

        # Merge app defaults ← session defaults
        self.defaults: Dict[str, Any] = {**APP_DEFAULTS}
        for k, v in raw.get("defaults", {}).items():
            self.defaults[k] = v

        # Parse timeline into sorted list of keyframe dicts
        self.keyframes: List[Dict] = self._parse_keyframes(raw.get("timeline", []))

        # Parse loops
        self.loops: List[Dict] = raw.get("loops", [])

        # Parse affirmation tag groups + sequential tags
        self.phrase_groups, self._sequential_tags = self._parse_affirmations()

    def _parse_keyframes(self, raw_timeline: list) -> List[Dict]:
        # Reserved keys that are NOT session parameters
        _meta = {"t", "label", "ease", "params"}
        kfs = []
        for entry in raw_timeline:
            # Start from explicit nested params: (default session format)
            params = dict(entry.get("params") or {})
            # Also collect any top-level non-meta keys (focus_flow / shorthand format)
            for k, v in entry.items():
                if k not in _meta:
                    params.setdefault(k, v)  # nested params: wins on conflict
            kf = {
                "t": float(entry["t"]),
                "label": entry.get("label", ""),
                "ease": entry.get("ease", "linear"),
                "params": params,
            }
            kfs.append(kf)
        return sorted(kfs, key=lambda k: k["t"])

    def _parse_affirmations(self) -> tuple[Dict[str, List], set]:
        """
        Returns (groups, sequential_tags):
          groups         — dict of tag_name → [pool_items]
          sequential_tags — set of tag names that use :seq mode

        The special key None holds untagged phrases (active when phrases=null).
        All phrases are also accessible via the None key as a full fallback.

        Pool items are strings or lists of strings (sequential chains):
          word | word2       → two separate str entries (random variants)
          word >> word2 >> … → one list[str] entry (sequential chain)

        Tag syntax:
          # [tag_name]       → random mode (default)
          # [tag_name:seq]   → sequential mode — phrases play in written order
        """
        groups: Dict[str, List] = {None: []}
        sequential_tags: set = set()
        current_tag = None

        path = self.affirmations_file
        if not path.exists():
            path = self.path.parent.parent / "affirmations.txt"
        if not path.exists():
            return groups, sequential_tags

        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("# [") and line.endswith("]"):
                    raw_tag = line[3:-1].strip()
                    if raw_tag.endswith(":seq"):
                        current_tag = raw_tag[:-4].strip().lower()
                        sequential_tags.add(current_tag)
                    else:
                        current_tag = raw_tag.lower()
                    if current_tag not in groups:
                        groups[current_tag] = []
                elif line.startswith("#"):
                    continue
                elif ">>" in line:
                    chain = [p.strip() for p in line.split(">>") if p.strip()]
                    if chain:
                        if current_tag is not None:
                            groups[current_tag].append(chain)
                        groups[None].append(chain)
                else:
                    phrases = [p.strip() for p in line.split("|") if p.strip()]
                    if current_tag is not None:
                        groups[current_tag].extend(phrases)
                    groups[None].extend(phrases)

        return groups, sequential_tags

    def get_phrases(self, tag: Optional[str]) -> List[str]:
        """Return phrases for the given tag, falling back to full pool."""
        if tag and tag in self.phrase_groups:
            return self.phrase_groups[tag]
        return self.phrase_groups.get(None, ["..."])


# ── Timeline Runner ───────────────────────────────────────────────────────────


class TimelineRunner(threading.Thread):
    """
    Background thread that drives session playback.

    Call start() to begin. Call stop() to shut down cleanly.
    Call load_session(path) to swap sessions at any time.
    Call seek(t) to jump to a timestamp.
    Call pause() / resume() to control playback.
    """

    TICK_MS = 100  # ms between timeline writes

    def __init__(self, root: Path):
        super().__init__(daemon=True, name="TimelineRunner")
        self.root = root
        self.live_path = root / "live_control.json"
        self._lock = threading.RLock()  # reentrant — allows load inside tick
        self._stop_evt = threading.Event()

        # Playback state
        self._session: Optional[Session] = None
        self._paused: bool = True
        self._elapsed: float = 0.0  # session time in seconds
        self._wall_last: float = 0.0  # wall clock at last tick

        # User keyframe lock: param → value the user set
        self._user_locks: Dict[str, Any] = {}

        # What we wrote last tick (for lock detection)
        self._last_written: Dict[str, Any] = {}

        # Loop state: index into session.loops → remaining count
        self._loop_counters: Dict[int, int] = {}

        # Playlist state — loaded from live_control.json
        self._playlist: List[str] = []
        self._playlist_mode: str = "sequential"
        self._playlist_index: int = 0
        self._playlist_autoadvance: bool = (
            False  # opt-in; default off protects integration window
        )
        self._session_ended: bool = False  # one-shot flag

        # Fractionation state machine — None when inactive
        # Keys: cycles_total, cycle_idx, phase, phase_wall, depth_hz,
        #       ascent_hz, new_depth_hz, ascent_s, hold_s, descent_s,
        #       pause_s, base_spiral_speed
        self._frac: Optional[Dict] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def load_session(self, session_path: Path):
        with self._lock:
            self._session = Session(session_path)
            self._elapsed = 0.0
            self._wall_last = time.time()
            self._user_locks = {}
            self._last_written = {}
            self._loop_counters = {}
            # Seed loop counters from session
            for i, loop in enumerate(self._session.loops):
                if loop.get("count", 1) != 0:
                    self._loop_counters[i] = loop.get("count", 1)
        # Flush stale phrase pool so TTS doesn't play the previous session's
        # affirmations during the brief window before the first timeline tick.
        try:
            patch_live(
                {
                    "affirmations_pool": None,
                    "phrases_active": None,
                    "affirmations_mode": "random",
                }
            )
        except Exception:
            pass
        print(f"[Timeline] Loaded: {self._session.name}")

    def pause(self):
        with self._lock:
            self._paused = True
        print("[Timeline] Paused")

    def resume(self):
        with self._lock:
            self._wall_last = time.time()
            self._paused = False
        print("[Timeline] Resumed")

    def seek(self, t: float):
        with self._lock:
            self._elapsed = max(0.0, t)
            self._wall_last = time.time()
            self._user_locks = {}  # locks don't survive a seek
            self._loop_counters = {}
            if self._session:
                for i, loop in enumerate(self._session.loops):
                    self._loop_counters[i] = loop.get("count", 1)
        print(f"[Timeline] Seeked to {t:.1f}s")

    def stop(self):
        self._stop_evt.set()

    @property
    def elapsed(self) -> float:
        return self._elapsed

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def current_label(self) -> str:
        if not self._session:
            return ""
        kf = self._current_keyframe()
        return kf["label"] if kf else ""

    @property
    def locked_params(self) -> set:
        """Currently user-locked parameter names — for UI gold indicators."""
        return set(self._user_locks.keys())

    # ── Thread main ───────────────────────────────────────────────────────────

    def run(self):
        while not self._stop_evt.is_set():
            start = time.time()

            with self._lock:
                self._handle_commands()
                self._tick()

            elapsed_ms = (time.time() - start) * 1000
            sleep_ms = max(1, self.TICK_MS - elapsed_ms)
            time.sleep(sleep_ms / 1000)

    # ── External command handling ──────────────────────────────────────────────

    def _handle_commands(self):
        """Consume timeline control commands written to live_control.json by
        external processes (control panel, LLM driver, etc.)."""
        try:
            data = self._read_live()

            # Always sync playlist config from live data (non-destructive read)
            self._sync_playlist_from_live(data)

            cmd = data.get("_timeline_cmd")
            if not cmd:
                return

            if cmd == "pause":
                self._paused = True
                print("[Timeline] Paused via command")

            elif cmd == "resume":
                self._wall_last = time.time()
                self._paused = False
                print("[Timeline] Resumed via command")

            elif cmd == "restart":
                self._elapsed = 0.0
                self._wall_last = time.time()
                self._paused = False
                self._user_locks = {}
                self._loop_counters = {}
                self._session_ended = False
                if self._session:
                    for i, loop in enumerate(self._session.loops):
                        if loop.get("count", 1) != 0:
                            self._loop_counters[i] = loop.get("count", 1)
                print("[Timeline] Restarted via command")

            elif cmd == "load":
                session_name = data.get("session_folder", "default")
                session_path = self.root / "sessions" / session_name
                if session_path.exists():
                    self.load_session(session_path)  # RLock lets us re-enter
                    print(f"[Timeline] Loaded session '{session_name}' via command")
                else:
                    print(f"[Timeline] Session '{session_name}' not found")

            elif cmd == "playlist_next":
                self._session_ended = False
                if self._playlist:
                    nxt = (self._playlist_index + 1) % len(self._playlist)
                    self._jump_to_playlist(nxt)
                    print(f"[Timeline] Manual playlist next → {nxt}")

            elif cmd == "playlist_prev":
                self._session_ended = False
                if self._playlist:
                    prv = (self._playlist_index - 1) % len(self._playlist)
                    self._jump_to_playlist(prv)
                    print(f"[Timeline] Manual playlist prev → {prv}")

            elif cmd == "seek":
                seek_to = float(data.get("seek_time") or 0.0)
                if self._session:
                    seek_to = max(0.0, min(seek_to, self._session.duration))
                else:
                    seek_to = max(0.0, seek_to)
                self._elapsed = seek_to
                self._wall_last = time.time()
                self._user_locks = {}
                self._loop_counters = {}
                self._session_ended = False
                print(f"[Timeline] Seeked to {seek_to:.1f}s via command")

            elif cmd == "fractionate":
                if self._frac is not None:
                    print("[Timeline] Fractionation already active — ignoring.")
                else:
                    opts = data.get("fractionation_opts") or {}
                    curr_hz = float(data.get("beat_frequency", 6.0))
                    curr_spd = float(data.get("spiral_speed_multiplier", 1.0))
                    curr_chs = float(data.get("spiral_chaos", 0.12))
                    curr_td = float(data.get("trail_decay", 0.0))
                    n_cycles = int(opts.get("cycles", 3))
                    # Target depth for first induction: 1.5 Hz below current
                    depth_hz = max(
                        curr_hz - float(opts.get("induction_drop_hz", 1.5)), 1.5
                    )
                    emerge_hz = min(
                        depth_hz + float(opts.get("emerge_hz_boost", 2.5)), 11.0
                    )
                    self._frac = {
                        # --- configuration ---
                        "cycles_total": n_cycles,
                        "emerge_hz_boost": float(opts.get("emerge_hz_boost", 2.5)),
                        "induction_timeout_s": float(
                            opts.get("induction_timeout_s", 300.0)
                        ),
                        "hold_s": float(opts.get("hold_s", 180.0)),
                        "emerge_s": float(opts.get("emerge_s", 30.0)),
                        "emerge_ramp_s": 15.0,  # portion spent ramping up
                        # DEEP duration per cycle — last cycle is longest
                        "deep_s": float(opts.get("deep_s", 240.0)),
                        # REINDUCE timeout shortens: cycle 0=300s, 1=120s, 2=90s, 3+=60s
                        "reinduce_timeouts": [300.0, 120.0, 90.0, 60.0, 45.0],
                        # --- state ---
                        "phase": "INDUCTION",
                        "cycle_idx": 0,
                        "phase_wall": time.time(),
                        # --- frequency ---
                        "start_hz": curr_hz,
                        "depth_hz": depth_hz,  # deepens -0.5 Hz each cycle
                        "emerge_hz": emerge_hz,
                        # --- EEG gating ---
                        "baseline_theta_alpha": None,
                        "baseline_samples": [],  # rolling 30-s window
                        "baseline_ready": False,
                        "prev_peak_ta": 0.0,  # best TA ratio last cycle
                        "curr_peak_ta": 0.0,  # tracking during REINDUCE
                        "ta_above_thresh_since": None,  # for INDUCTION gate
                        # --- visual preservation ---
                        "base_spiral_speed": curr_spd,
                        "base_spiral_chaos": curr_chs,
                        "base_trail_decay": curr_td,
                    }
                    data["fractionation_active"] = True
                    data["fractionation_phase"] = "INDUCTION"
                    data["fractionation_cycle"] = 1
                    print(
                        f"[Timeline] Fractionation started: {n_cycles} cycles, "
                        f"start={curr_hz:.1f}Hz → depth={depth_hz:.1f}Hz → "
                        f"emerge={emerge_hz:.1f}Hz"
                    )

            elif cmd == "stop":
                import pygame as _pg

                print("[Timeline] Stop command received — quitting display.")
                _pg.event.post(_pg.event.Event(_pg.QUIT))

            # Consume the command so it isn't re-executed next tick
            patch_live({"_timeline_cmd": None})

        except Exception as exc:
            print(f"[Timeline] Command error: {exc}")

    # ── Core tick ─────────────────────────────────────────────────────────────

    def _tick(self):
        if self._session is None:
            return

        # Advance wall time
        now = time.time()
        if not self._paused:
            dt = now - self._wall_last
            self._elapsed += dt
        self._wall_last = now

        # Handle loops — rewind elapsed if inside an active loop
        self._elapsed = self._apply_loops(self._elapsed)

        # Check for natural session end.
        # Default: pause and hold. The return keyframe has already ramped the
        # user back to alpha — the integration window that follows is sacred
        # and must not be punched through by another session's defaults.
        # Opt-in: playlist_autoadvance=true restores conveyor-belt playback.
        if not self._paused and self._session_is_over():
            if not self._session_ended:
                self._session_ended = True
                if self._playlist_autoadvance and self._playlist:
                    self._advance_playlist()
                    return  # load_session resets state; next tick starts fresh
                else:
                    self._paused = True
                    try:
                        patch_live({"timeline_paused": True})
                    except Exception:
                        pass
                    print(
                        "[Timeline] Session ended — paused (playlist_autoadvance=False)"
                    )
        else:
            self._session_ended = False

        # Detect user overrides → create/refresh locks
        self._detect_user_locks()

        # Compute target values at current elapsed time
        values = self._compute_values(self._elapsed)

        # Fractionation overrides beat_frequency + spiral_speed_multiplier
        # for the duration of the technique; all other params are unaffected.
        if self._frac is not None:
            values.update(self._frac_tick())

        # Remove locked params from what we're about to write
        for param in self._user_locks:
            values.pop(param, None)

        # Write to live_control.json
        self._write_live(values)

    # ── Playlist ──────────────────────────────────────────────────────────────

    def _sync_playlist_from_live(self, data: Dict):
        """Pull playlist keys from live_control.json into internal state."""
        pl = data.get("playlist", [])
        if isinstance(pl, list):
            self._playlist = [str(s) for s in pl]
            self._playlist_mode = str(data.get("playlist_mode", "sequential"))
        self._playlist_autoadvance = bool(data.get("playlist_autoadvance", False))

    def _session_is_over(self) -> bool:
        """True when the session timeline has naturally reached its end.

        If session.yaml declares an explicit duration, that is the sole authority
        so the displayed countdown always matches when the session actually ends.
        The last-keyframe check is a fallback for sessions with no declared duration.
        """
        if self._session is None:
            return False
        # Explicit duration: authoritative — keyframe position is irrelevant
        if self._session.duration:
            return self._elapsed >= self._session.duration
        # No explicit duration: end at the last keyframe (no active loops)
        if self._session.keyframes:
            last_t = self._session.keyframes[-1]["t"]
            if self._elapsed >= last_t:
                any_active = any(
                    self._loop_counters.get(i, 0) not in (0,)
                    for i in range(len(self._session.loops))
                )
                if not any_active:
                    return True
        return False

    def _jump_to_playlist(self, idx: int):
        """Directly load a specific playlist index (for manual prev/next)."""
        if not self._playlist or idx < 0 or idx >= len(self._playlist):
            return
        self._playlist_index = idx
        try:
            patch_live({"playlist_index": idx})
        except Exception:
            pass
        name = self._playlist[idx]
        path = self.root / "sessions" / name
        if path.exists():
            self.load_session(path)
            self._paused = False
            print(f"[Timeline] Playlist jumped to [{idx}] '{name}'")
        else:
            print(f"[Timeline] Playlist: '{name}' not found")

    def _advance_playlist(self):
        """Load the next session based on mode. Called when a session ends."""
        if not self._playlist:
            print("[Timeline] Session ended — no playlist active")
            self._paused = True
            return

        n = len(self._playlist)
        idx = self._playlist_index
        mode = self._playlist_mode

        if mode == "loop_one":
            next_idx = idx  # stay on same session
        elif mode == "shuffle":
            import random

            candidates = [i for i in range(n) if i != idx] or list(range(n))
            next_idx = random.choice(candidates)
        elif mode == "loop":
            next_idx = (idx + 1) % n
        else:  # sequential
            next_idx = idx + 1
            if next_idx >= n:
                print("[Timeline] Playlist finished")
                self._paused = True
                return

        self._playlist_index = next_idx
        try:
            patch_live({"playlist_index": next_idx})
        except Exception:
            pass
        session_name = self._playlist[next_idx]
        session_path = self.root / "sessions" / session_name
        if session_path.exists():
            self.load_session(session_path)
            self._paused = False
            print(
                f"[Timeline] Playlist → [{next_idx}/{n - 1}] '{session_name}' "
                f"(mode={mode})"
            )
        else:
            print(f"[Timeline] Playlist: session '{session_name}' not found, skipping")
            self._paused = True

    # ── Loop handling ─────────────────────────────────────────────────────────

    def _apply_loops(self, t: float) -> float:
        """
        Check if t has crossed any active loop boundary.
        If so, rewind to from_t and decrement the counter.
        Returns adjusted t.
        """
        for i, loop in enumerate(self._session.loops):
            from_t = float(loop["from_t"])
            to_t = float(loop["to_t"])
            count = self._loop_counters.get(i, 0)

            if count == 0:
                continue  # loop exhausted, skip

            if t >= to_t and t > from_t:
                if count == -1:
                    # Infinite loop — just rewind
                    print(f"[Timeline] Loop '{loop.get('label', i)}' rewinding (∞)")
                    return from_t + (t - to_t)
                elif count > 1:
                    self._loop_counters[i] = count - 1
                    print(
                        f"[Timeline] Loop '{loop.get('label', i)}' "
                        f"rewinding ({self._loop_counters[i]} remaining)"
                    )
                    return from_t + (t - to_t)
                else:
                    # Last pass — let it through, mark exhausted
                    self._loop_counters[i] = 0

        return t

    # ── Value computation ─────────────────────────────────────────────────────

    def _compute_values(self, t: float) -> Dict[str, Any]:
        """
        For every parameter, find the surrounding keyframe pair and
        interpolate. Returns a flat dict of all param values.
        """
        result: Dict[str, Any] = dict(self._session.defaults)
        keyframes = self._session.keyframes

        if not keyframes:
            # Freeform session (timeline: []) — the agent owns all params.
            # Only metadata (session_time, etc.) is written; don't re-apply
            # defaults every tick and clobber agent adjustments.
            return {}

        # Find the last keyframe at or before t, and the next one after t
        prev_kf = None
        next_kf = None

        for kf in keyframes:
            if kf["t"] <= t:
                prev_kf = kf
            else:
                if next_kf is None:
                    next_kf = kf
                break

        if prev_kf is None:
            # Before the first keyframe — use defaults
            return result

        # Apply prev_kf values as the "current" state
        for param, value in prev_kf["params"].items():
            result[param] = value

        if next_kf is None:
            # Past the last keyframe — just hold prev values
            return result

        # Interpolate between prev_kf and next_kf
        segment_duration = next_kf["t"] - prev_kf["t"]
        if segment_duration <= 0:
            for param, value in next_kf["params"].items():
                result[param] = value
            return result

        progress = (t - prev_kf["t"]) / segment_duration
        ease = next_kf.get("ease", "linear")

        for param, target in next_kf["params"].items():
            source = prev_kf["params"].get(param, self._session.defaults.get(param))

            if param in INTERPOLATABLE and source is not None:
                result[param] = _interpolate(
                    float(source), float(target), progress, ease
                )
            else:
                # Instant-only: hold prev value until we reach next_kf["t"]
                result[param] = prev_kf["params"].get(
                    param, self._session.defaults.get(param)
                )

        return result

    def _current_keyframe(self) -> Optional[Dict]:
        if not self._session or not self._session.keyframes:
            return None
        result = None
        for kf in self._session.keyframes:
            if kf["t"] <= self._elapsed:
                result = kf
        return result

    # ── Fractionation state machine ───────────────────────────────────────

    def _frac_tick(self) -> Dict[str, Any]:
        """Advance the Vogt fractionation state machine.

        Returns a dict that overrides the normal timeline write for this tick.
        Sets self._frac = None on completion.

        States per spec (knowledge/fractionation_protocol.md):
          INDUCTION  – ramp beat from start_hz down to depth_hz.
                       Gate: theta/alpha > 1.2× baseline for 10 s (EEG), or
                       induction_timeout_s elapsed (time fallback).
          HOLD       – stay at depth_hz for hold_s (time-gated, cycle 1 only).
          EMERGE     – lift beat to emerge_hz over 15 s, hold remainder of
                       emerge_s (time-gated, ~30 s total). Visual jolt: sharp
                       geometry resets trail_decay and spiral_chaos to 0.
          REINDUCE   – ramp beat from emerge_hz back to new depth_hz (0.5 Hz
                       deeper than last). Duration shortens each cycle.
                       Gate: theta/alpha > prev cycle peak, OR timeout.
          DEEP       – therapeutic window at new depth_hz (deep_s, time-gated).
                       Cycles 2+ skip HOLD and begin here after the prev DEEP.

        After last DEEP: COMPLETE — fractionation_active → False, beat stays.
        """
        f = self._frac
        now = time.time()
        el = now - f["phase_wall"]
        phase = f["phase"]

        # ── Read live EEG data for gating ─────────────────────────────────
        live = self._read_live()
        eeg_theta = live.get("eeg_theta", 0.0) or 0.0
        eeg_alpha = live.get("eeg_alpha", 0.0) or 0.0
        eeg_quality = live.get("eeg_quality", "unknown")
        eeg_ok = eeg_quality in ("good", "fair") and eeg_alpha > 0.0
        ta_ratio = (eeg_theta / eeg_alpha) if (eeg_ok and eeg_alpha > 0) else 0.0

        # ── Baseline capture (first 30 s of INDUCTION) ────────────────────
        if not f["baseline_ready"] and eeg_ok and ta_ratio > 0:
            f["baseline_samples"].append(ta_ratio)
            if len(f["baseline_samples"]) >= 10:  # 10 ticks × 100ms = ~1 s of data
                f["baseline_theta_alpha"] = sum(f["baseline_samples"]) / len(
                    f["baseline_samples"]
                )
                f["baseline_ready"] = True
                print(
                    f"[Timeline] Frac baseline TA ratio: {f['baseline_theta_alpha']:.3f}"
                )

        baseline_ta = f["baseline_theta_alpha"] or 0.5
        ta_thresh = baseline_ta * 1.2

        # ── Phase transition logic ─────────────────────────────────────────
        if phase == "INDUCTION":
            # EEG gate: ratio above threshold for ≥10 s
            if eeg_ok and ta_ratio >= ta_thresh:
                if f["ta_above_thresh_since"] is None:
                    f["ta_above_thresh_since"] = now
                elif now - f["ta_above_thresh_since"] >= 10.0:
                    self._frac_advance("HOLD", now)
                    el, phase = 0.0, "HOLD"
            else:
                f["ta_above_thresh_since"] = None
            # Time fallback
            if phase == "INDUCTION" and el >= f["induction_timeout_s"]:
                self._frac_advance("HOLD", now)
                el, phase = 0.0, "HOLD"

        elif phase == "HOLD" and el >= f["hold_s"]:
            self._frac_advance("EMERGE", now)
            el, phase = 0.0, "EMERGE"

        elif phase == "EMERGE" and el >= f["emerge_s"]:
            # Deepen for next cycle: 0.5 Hz lower, min 1.5 Hz
            f["depth_hz"] = max(f["depth_hz"] - 0.5, 1.5)
            f["emerge_hz"] = min(f["depth_hz"] + f["emerge_hz_boost"], 11.0)
            f["curr_peak_ta"] = 0.0
            self._frac_advance("REINDUCE", now)
            el, phase = 0.0, "REINDUCE"

        elif phase == "REINDUCE":
            # Track best theta/alpha during this phase
            if ta_ratio > f["curr_peak_ta"]:
                f["curr_peak_ta"] = ta_ratio
            # EEG gate: ratio exceeds previous cycle peak
            prev_peak = f["prev_peak_ta"]
            ri_timeout = f["reinduce_timeouts"][
                min(f["cycle_idx"], len(f["reinduce_timeouts"]) - 1)
            ]
            eeg_gated = eeg_ok and prev_peak > 0 and ta_ratio >= prev_peak * 1.05
            if eeg_gated or el >= ri_timeout:
                f["prev_peak_ta"] = f["curr_peak_ta"]
                self._frac_advance("DEEP", now)
                el, phase = 0.0, "DEEP"

        elif phase == "DEEP" and el >= f["deep_s"]:
            if f["cycle_idx"] + 1 >= f["cycles_total"]:
                self._frac_advance("COMPLETE", now)
                el, phase = 0.0, "COMPLETE"
            else:
                f["cycle_idx"] += 1
                # Subsequent cycles skip HOLD — jump straight to EMERGE
                self._frac_advance("EMERGE", now)
                el, phase = 0.0, "EMERGE"

        # ── Compute output values for this phase ───────────────────────────
        cycle_n = f["cycle_idx"] + 1
        result: Dict[str, Any] = {
            "fractionation_active": True,
            "fractionation_phase": phase
            if phase == "COMPLETE"
            else f"{phase}_{cycle_n}",
            "fractionation_cycle": cycle_n,
        }

        if phase == "INDUCTION":
            t = min(el / max(f["induction_timeout_s"], 1.0), 1.0)
            result["beat_frequency"] = (
                f["start_hz"] + (f["depth_hz"] - f["start_hz"]) * t
            )
            result["spiral_speed_multiplier"] = f["base_spiral_speed"]
            result["spiral_chaos"] = f["base_spiral_chaos"]
            result["trail_decay"] = f["base_trail_decay"]

        elif phase == "HOLD":
            result["beat_frequency"] = f["depth_hz"]
            result["spiral_speed_multiplier"] = f["base_spiral_speed"]
            result["spiral_chaos"] = f["base_spiral_chaos"]
            result["trail_decay"] = f["base_trail_decay"]

        elif phase == "EMERGE":
            # First emerge_ramp_s: ramp beat up to emerge_hz; then hold there
            ramp_s = f["emerge_ramp_s"]
            if el < ramp_s:
                t = el / ramp_s
                result["beat_frequency"] = (
                    f["depth_hz"] + (f["emerge_hz"] - f["depth_hz"]) * t
                )
            else:
                result["beat_frequency"] = f["emerge_hz"]
            # Visual jolt: sharp geometry, no trails — bottom-up orienting response
            result["spiral_speed_multiplier"] = f["base_spiral_speed"] + 0.3
            result["spiral_chaos"] = 0.0
            result["trail_decay"] = 0.0

        elif phase == "REINDUCE":
            ri_dur = f["reinduce_timeouts"][
                min(f["cycle_idx"], len(f["reinduce_timeouts"]) - 1)
            ]
            t = min(el / max(ri_dur, 1.0), 1.0)
            result["beat_frequency"] = (
                f["emerge_hz"] + (f["depth_hz"] - f["emerge_hz"]) * t
            )
            # Restore visuals gradually during re-induction
            result["spiral_speed_multiplier"] = f["base_spiral_speed"] + 0.3 * (1.0 - t)
            result["spiral_chaos"] = f["base_spiral_chaos"] * t
            result["trail_decay"] = f["base_trail_decay"] * t

        elif phase == "DEEP":
            result["beat_frequency"] = f["depth_hz"]
            result["spiral_speed_multiplier"] = f["base_spiral_speed"]
            result["spiral_chaos"] = f["base_spiral_chaos"]
            result["trail_decay"] = f["base_trail_decay"]

        elif phase == "COMPLETE":
            result["beat_frequency"] = f["depth_hz"]
            result["spiral_speed_multiplier"] = f["base_spiral_speed"]
            result["spiral_chaos"] = f["base_spiral_chaos"]
            result["trail_decay"] = f["base_trail_decay"]
            result["fractionation_active"] = False
            result["fractionation_phase"] = "complete"
            self._frac = None
            print("[Timeline] Fractionation complete.")

        return result

    def _frac_advance(self, new_phase: str, now: float) -> None:
        """Transition self._frac to new_phase and reset the phase clock."""
        f = self._frac
        print(
            f"[Timeline] Frac {f['phase']} → {new_phase} "
            f"(cycle {f['cycle_idx'] + 1}/{f['cycles_total']})"
        )
        f["phase"] = new_phase
        f["phase_wall"] = now
        f["ta_above_thresh_since"] = None

    # ── User lock detection ───────────────────────────────────────────────────

    def _detect_user_locks(self):
        """
        Read live_control.json. Any timeline-managed value that differs from
        what we wrote last tick was changed externally → lock it.
        Only considers INTERPOLATABLE and INSTANT_ONLY params to avoid
        locking unrelated UI-only keys (tts, window flags, etc.).
        """
        current_live = self._read_live()
        managed = INTERPOLATABLE | INSTANT_ONLY
        for param, current_val in current_live.items():
            if param not in managed or param not in self._last_written:
                continue
            last_val = self._last_written[param]
            try:
                if param in INTERPOLATABLE:
                    if abs(float(current_val) - float(last_val)) > 0.01:
                        self._user_locks[param] = current_val
                elif current_val != last_val:
                    self._user_locks[param] = current_val
            except (TypeError, ValueError):
                pass

    def _expire_locks(self, computed_values: Dict[str, Any]):
        """
        Remove a lock when the timeline has crossed a keyframe that
        explicitly sets that parameter. The timeline will reassert from
        the keyframe's value on the next tick.
        """
        if not self._session or not self._session.keyframes:
            return

        # Find the keyframe we most recently crossed
        just_crossed = None
        for kf in self._session.keyframes:
            if kf["t"] <= self._elapsed:
                just_crossed = kf

        if just_crossed is None:
            return

        expired = [
            param for param in list(self._user_locks) if param in just_crossed["params"]
        ]
        for param in expired:
            print(f"[Timeline] Lock expired: {param} → resuming from keyframe value")
            del self._user_locks[param]

    # ── live_control.json I/O ─────────────────────────────────────────────────

    def _read_live(self) -> Dict:
        try:
            return json.loads(self.live_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_live(self, values: Dict[str, Any]):
        """
        Patch timeline values into live_control.json via the StateServer.
        The server merges the patch so no keys not in values are disturbed.
        """
        try:
            patch: Dict[str, Any] = {}
            for param, value in values.items():
                if param == "phrases":
                    patch["phrases_active"] = value
                    patch["affirmations_pool"] = self._session.get_phrases(value)
                    seq = value in self._session._sequential_tags if value else False
                    patch["affirmations_mode"] = "sequential" if seq else "random"
                else:
                    patch[param] = value

            patch.update(
                {
                    "session_name": self._session.name,
                    "session_folder": self._session.path.name,
                    "session_time": round(self._elapsed, 1),
                    "session_duration": self._session.duration,
                    "timeline_label": self.current_label,
                    "timeline_paused": self._paused,
                    "timeline_locked_params": list(self._user_locks.keys()),
                    "playlist_index": self._playlist_index,
                }
            )
            patch_live(patch)
            self._last_written = {k: v for k, v in values.items() if k != "phrases"}
        except Exception as e:
            print(f"[Timeline] Write failed: {e}")


# ── Convenience factory ───────────────────────────────────────────────────────


def make_runner(root: Path, session_name: str = "default") -> TimelineRunner:
    """Create, load, and return a ready-to-start TimelineRunner."""
    runner = TimelineRunner(root)
    session_path = root / "sessions" / session_name
    if session_path.exists():
        runner.load_session(session_path)
    else:
        print(
            f"[Timeline] Session '{session_name}' not found — "
            f"runner idle until load_session() is called"
        )
    return runner
