"""conductor.py — Somna Session Conductor FSM  (Bible Ch.6 §6.5)
======================================================
The top-level FSM that orchestrates all Somna subsystems into a coherent
session arc.  It is the ONLY agent-side entity that writes to
live_control.json.  All subsystem trackers (SQI, ASSR, FAA, FreqLeader,
SessionScorer) are read-only sensors; they compute and write their own metrics
to live_control.json; the Conductor reads those metrics and decides what to do.

Key Somna naming adaptations vs. Research's pseudocode:
    beat_freq      → beat_frequency      (canonical Somna key)
    chaos          → spiral_chaos        (canonical Somna key)
    modality       → beat_type           (canonical Somna key)
    sr_noise_level → sr_noise_level      (already exists in _ADJUSTABLE_PARAMS)
    shadow_opacity → shadow_opacity_target (agent-preferred subliminal key)
    SQI tiers      → lowercase in live state ("none"/"low"/"reduced"/"full")
                     Conductor uppercases them internally for logic

Writer priority (per AGENTS.md):
    User slider  >  Conductor / LLM agent  >  timeline_runner  >  defaults
The Conductor respects timeline_locked_params just like the agent does.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from ipc import patch_live

_LIVE = Path(__file__).parent.parent / "live_control.json"
_DB_AVAILABLE = False
try:
    from content_tools.somna_db import write_conductor_decisions_batch

    _DB_AVAILABLE = True
except Exception:
    pass

# CalibrationManager — optional; falls back gracefully if missing
_CAL_AVAILABLE = False
try:
    from eeg.calibration_manager import CalibrationManager as _CalibrationManager

    _CAL_AVAILABLE = True
except Exception:
    pass

# CrossmodalGainEngine — optional; falls back gracefully if missing
_GAIN_AVAILABLE = False
try:
    from engines.crossmodal_gain import CrossmodalGainEngine, SRCalibrationSweep

    _GAIN_AVAILABLE = True
except Exception:
    pass


# ── SQI tier ordering ─────────────────────────────────────────────────────────

SQI_RANK: Dict[str, int] = {"NONE": 0, "LOW": 1, "REDUCED": 2, "FULL": 3}


def _sqi_rank(tier: Optional[str]) -> int:
    if not tier:
        return 0
    return SQI_RANK.get(tier.upper(), 0)


# ── Phase definitions ─────────────────────────────────────────────────────────


class Phase(Enum):
    CALIBRATION = "calibration"
    INDUCTION = "induction"
    DEEPENING = "deepening"
    MAINTENANCE = "maintenance"
    FRAC_EMERGE = "frac_emerge"
    FRAC_EMERGE_HOLD = "frac_emerge_hold"
    FRAC_REDROP = "frac_redrop"
    SLEEP_APPROACH = "sleep_approach"
    SLEEP_ONSET = "sleep_onset"
    SLEEP_MAINTAIN = "sleep_maintain"
    SLEEP_TRAINING = "sleep_training"
    SLEEP_WAKE = "sleep_wake"
    EDISON_PREPARATION = "edison_preparation"
    EDISON_SEED = "edison_seed"
    EDISON_MONITORING = "edison_monitoring"
    EDISON_N1_HOLD = "edison_n1_hold"
    EDISON_CAPTURE = "edison_capture"
    EDISON_CYCLE_END = "edison_cycle_end"
    SSILD_PRE_TECHNIQUE = "ssild_pre_technique"
    SSILD_QUICK_CYCLES = "ssild_quick_cycles"
    SSILD_SLOW_CYCLES = "ssild_slow_cycles"
    SSILD_POST_TECHNIQUE = "ssild_post_technique"
    SSILD_REM_MONITORING = "ssild_rem_monitoring"
    SSILD_DREAM_JOURNAL = "ssild_dream_journal"
    SESSION_END = "session_end"
    # GENUS 40 Hz protocol (genus_protocol.md §5) — replaces normal depth phases
    GENUS_BLOCK = "genus_block"


# Parameters the Conductor exclusively owns when active.
# Agent LLM adjustments that clash with these are filtered out.
CONDUCTOR_OWNED_PARAMS = frozenset(
    {
        "beat_frequency",
        "beat_type",
        "spiral_chaos",
        "trail_decay",
        "veil_mode",
        "spiral_style",
        "shadow_opacity_target",
        "sr_noise_level",
        "breath_mod",
        "breath_rate",
        "pp_bloom_intensity",
        "pp_film_grain",
        "pp_ca_strength",
        "entrainment_strength",
    }
)

HAPTIC_OWNED_WHEN_CONNECTED = frozenset(
    {
        "haptic_intensity",
        "haptic_pattern",
    }
)
TAVNS_OWNED_WHEN_CONNECTED = frozenset(
    {
        "tavns_intensity",
        "tavns_waveform",
    }
)

HAPTIC_PHASE_PROFILES = {
    Phase.CALIBRATION: {"intensity": 0, "pattern": "continuous"},
    Phase.INDUCTION: {"intensity": 15, "pattern": "ramp"},
    Phase.DEEPENING: {"intensity": 35, "pattern": "wave"},
    Phase.MAINTENANCE: {"intensity": 45, "pattern": "continuous"},
    Phase.FRAC_EMERGE: {"intensity": 5, "pattern": "continuous"},
    Phase.FRAC_EMERGE_HOLD: {"intensity": 0, "pattern": "continuous"},
    Phase.FRAC_REDROP: {"intensity": 25, "pattern": "ramp"},
    Phase.SLEEP_APPROACH: {"intensity": 10, "pattern": "wave"},
    Phase.SLEEP_ONSET: {"intensity": 0, "pattern": "continuous"},
    Phase.SLEEP_MAINTAIN: {"intensity": 0, "pattern": "continuous"},
    Phase.SLEEP_TRAINING: {"intensity": 0, "pattern": "continuous"},
    Phase.SLEEP_WAKE: {"intensity": 0, "pattern": "continuous"},
    Phase.EDISON_PREPARATION: {"intensity": 0, "pattern": "continuous"},
    Phase.EDISON_SEED: {"intensity": 0, "pattern": "continuous"},
    Phase.EDISON_MONITORING: {"intensity": 0, "pattern": "continuous"},
    Phase.EDISON_N1_HOLD: {"intensity": 0, "pattern": "continuous"},
    Phase.EDISON_CAPTURE: {"intensity": 5, "pattern": "pulse"},
    Phase.EDISON_CYCLE_END: {"intensity": 0, "pattern": "continuous"},
    Phase.SSILD_PRE_TECHNIQUE: {"intensity": 0, "pattern": "continuous"},
    Phase.SSILD_QUICK_CYCLES: {"intensity": 0, "pattern": "continuous"},
    Phase.SSILD_SLOW_CYCLES: {"intensity": 0, "pattern": "continuous"},
    Phase.SSILD_POST_TECHNIQUE: {"intensity": 0, "pattern": "continuous"},
    Phase.SSILD_REM_MONITORING: {"intensity": 0, "pattern": "continuous"},
    Phase.SSILD_DREAM_JOURNAL: {"intensity": 0, "pattern": "continuous"},
    Phase.SESSION_END: {"intensity": 0, "pattern": "continuous"},
    Phase.GENUS_BLOCK: {"intensity": 20, "pattern": "pulse"},
}

TAVNS_PHASE_PROFILES = {
    Phase.CALIBRATION: {"intensity": 0, "waveform": "sine"},
    Phase.INDUCTION: {"intensity": 10, "waveform": "sine"},
    Phase.DEEPENING: {"intensity": 20, "waveform": "sine"},
    Phase.MAINTENANCE: {"intensity": 30, "waveform": "sine"},
    Phase.FRAC_EMERGE: {"intensity": 0, "waveform": "sine"},
    Phase.FRAC_EMERGE_HOLD: {"intensity": 0, "waveform": "sine"},
    Phase.FRAC_REDROP: {"intensity": 15, "waveform": "sine"},
    Phase.SLEEP_APPROACH: {"intensity": 0, "waveform": "sine"},
    Phase.SLEEP_ONSET: {"intensity": 0, "waveform": "sine"},
    Phase.SLEEP_MAINTAIN: {"intensity": 0, "waveform": "sine"},
    Phase.SLEEP_TRAINING: {"intensity": 0, "waveform": "sine"},
    Phase.SLEEP_WAKE: {"intensity": 0, "waveform": "sine"},
    Phase.EDISON_PREPARATION: {"intensity": 0, "waveform": "sine"},
    Phase.EDISON_SEED: {"intensity": 0, "waveform": "sine"},
    Phase.EDISON_MONITORING: {"intensity": 0, "waveform": "sine"},
    Phase.EDISON_N1_HOLD: {"intensity": 0, "waveform": "sine"},
    Phase.EDISON_CAPTURE: {"intensity": 5, "waveform": "sine"},
    Phase.EDISON_CYCLE_END: {"intensity": 0, "waveform": "sine"},
    Phase.SSILD_PRE_TECHNIQUE: {"intensity": 0, "waveform": "sine"},
    Phase.SSILD_QUICK_CYCLES: {"intensity": 0, "waveform": "sine"},
    Phase.SSILD_SLOW_CYCLES: {"intensity": 0, "waveform": "sine"},
    Phase.SSILD_POST_TECHNIQUE: {"intensity": 0, "waveform": "sine"},
    Phase.SSILD_REM_MONITORING: {"intensity": 0, "waveform": "sine"},
    Phase.SSILD_DREAM_JOURNAL: {"intensity": 0, "waveform": "sine"},
    Phase.SESSION_END: {"intensity": 0, "waveform": "sine"},
    Phase.GENUS_BLOCK: {"intensity": 10, "waveform": "biphasic"},
}

# Per-phase tick rates in seconds
_TICK_RATES: Dict[Phase, Optional[int]] = {
    Phase.CALIBRATION: 5,
    Phase.INDUCTION: 10,
    Phase.DEEPENING: 10,
    Phase.MAINTENANCE: 30,
    Phase.FRAC_EMERGE: 5,
    Phase.FRAC_EMERGE_HOLD: 5,
    Phase.FRAC_REDROP: 10,
    Phase.SLEEP_APPROACH: 30,
    Phase.SLEEP_ONSET: 60,
    Phase.SLEEP_MAINTAIN: 60,
    Phase.SLEEP_TRAINING: 30,
    Phase.SLEEP_WAKE: 30,
    Phase.EDISON_PREPARATION: 5,
    Phase.EDISON_SEED: 5,
    Phase.EDISON_MONITORING: 5,
    Phase.EDISON_N1_HOLD: 5,
    Phase.EDISON_CAPTURE: 10,
    Phase.EDISON_CYCLE_END: 10,
    Phase.SSILD_PRE_TECHNIQUE: 5,
    Phase.SSILD_QUICK_CYCLES: 3,
    Phase.SSILD_SLOW_CYCLES: 5,
    Phase.SSILD_POST_TECHNIQUE: 15,
    Phase.SSILD_REM_MONITORING: 15,
    Phase.SSILD_DREAM_JOURNAL: 10,
    Phase.SESSION_END: None,
    Phase.GENUS_BLOCK: 30,  # check every 30 s; GENUS runs autonomously
}


def _interpret_binocular(vr: dict) -> str:
    """Short human-readable interpretation of VR binocular metrics for agent context."""
    if not vr:
        return "no VR data"
    bi = vr.get("binocular_index")
    sw = vr.get("switch_rate_hz")
    dom = vr.get("dominance_raw")
    if bi is None:
        return "ssvep not yet computed"
    parts = []
    if bi > 0.7:
        parts.append(f"strong binocular integration (index={bi:.2f})")
    elif bi > 0.4:
        parts.append(f"moderate binocular integration (index={bi:.2f})")
    else:
        parts.append(f"weak binocular integration (index={bi:.2f}) — rivalry shallow")
    if sw is not None:
        if sw > 0.15:
            parts.append(
                f"rivalry switch rate elevated ({sw:.3f} Hz — deep engagement)"
            )
        else:
            parts.append(f"rivalry switch rate low ({sw:.3f} Hz)")
    if dom is not None:
        eye = "left" if dom > 0.1 else ("right" if dom < -0.1 else "balanced")
        parts.append(f"{eye}-eye dominant (dom={dom:.2f})")
    return "; ".join(parts)


# Timer-based fallback phase schedules (minutes into session → phase)
# Keyed by total session duration bucket.
_TIMER_SCHEDULE: List[Tuple[int, Phase]] = [
    (0, Phase.CALIBRATION),
    (1, Phase.INDUCTION),
    (5, Phase.DEEPENING),
    (15, Phase.MAINTENANCE),
]


class Conductor:
    """Top-level FSM orchestrating all Somna subsystems.

    Single Writer: this is the ONLY agent-side entity that writes to
    live_control.json.  All subsystem outputs are read from the same file.

    Instantiated by SomnaAgent at fresh session start; ticked via tick().
    """

    def __init__(
        self,
        session_id: str,
        session_type: str,
        session_duration_min: int,
        synthetic_board: bool = False,
        eeg_enabled: bool = True,
    ):
        self.session_id = session_id
        self.session_type = (
            session_type  # "standard" | "sleep" | "edison" | "ssild" | "genus"
        )
        self.session_duration = session_duration_min * 60
        self.synthetic_board = synthetic_board
        self.eeg_enabled = eeg_enabled
        # EEG engine reference — injected after construction for respiratory hot-window
        # adaptation on phase transitions (Bible Ch.4 §4.6 §6.2). Optional; guards with hasattr.
        self._eeg_engine: Any = None

        self.phase = Phase.CALIBRATION
        self.phase_entered_at = time.time()
        self.session_start = time.time()

        # Fractionation state
        self.fractionation_count = 0
        self.max_fractionations = self._calc_max_fractionations(session_duration_min)
        self.pre_emerge_params: Dict[str, Any] = {}

        # Calibration outputs
        self.iaf: Optional[float] = None
        self.current_target_freq: Optional[float] = None

        # Modality switching (INDUCTION)
        self._modality_switches = 0
        self._current_modality = "binaural"

        # Hold timers for hysteresis — maps condition_key → first_met_timestamp
        self._hold_timers: Dict[str, float] = {}

        # Trance score history for rate-of-change calculation
        self._trance_history: List[Tuple[float, float]] = []

        # Decision log — flushed to DB every 10 entries or on transition
        self._decision_log: List[Dict] = []
        self._log_flush_counter = 0

        # Degrade mode: timer-only operation when EEG unavailable
        self._degraded = False
        self._degraded_since: Optional[float] = None

        # Last metrics snapshot — updated every tick for assessment()
        self._last_metrics: Dict[str, Any] = {}

        # Agent-supplied hints — updated each tick from live_control.json.
        # Keys: depth_patience (float multiplier), request_fractionation (bool),
        #       target_floor_hz (float | None), note (str).
        self._hints: Dict[str, Any] = {}

        # Phase transition history — list of (phase_value, duration_s) tuples,
        # newest last.  Used to build a compact arc narrative for agent context.
        self._phase_history: List[Tuple[str, float]] = []

        # CalibrationManager — personal threshold lookup (Bible Ch.2 §2.6).
        # Always instantiated; before any calibration data exists every
        # get_threshold() call returns the population fallback unchanged.
        self.cal: Optional["_CalibrationManager"] = None
        if _CAL_AVAILABLE:
            try:
                self.cal = _CalibrationManager()
            except Exception as e:
                print(f"[Conductor] CalibrationManager unavailable: {e}")

        if not eeg_enabled:
            # EEG disabled in config — activate timer mode immediately so the
            # Conductor never waits for EEG data that will never arrive.
            self._timer_mode = True
            print("[Conductor] EEG disabled — timer fallback active from start")
        elif synthetic_board:
            self._timer_mode = True
            print("[Conductor] SYNTHETIC_BOARD detected — timer fallback active")

        # VR photic closed-loop state
        self._vr_photic_hz = 10.0  # current commanded frequency
        self._vr_photic_hold_s = 0.0  # seconds since last adjustment
        self._vr_photic_last_snr = 0.0  # SNR from last detection at current freq
        self._vr_photic_adj_ts = 0.0  # timestamp of last frequency nudge

        # VR session state tracking for edge detection
        self._vr_was_active = False  # previous tick's vr_headset_active value

        # Bible Ch.4 Addendum A §3 — GENUS sub-phase state machine
        self._genus_sub_phase: str = "RAMP_UP"
        self._genus_sub_entered_at: float = 0.0
        self._genus_low_ent_since: Optional[float] = None

        # Bible Ch.3 §3.8 — Crossmodal Gain Engine
        # Instantiated lazily on first INDUCTION tick so calibration profile is available.
        self._gain_engine: Optional["CrossmodalGainEngine"] = None
        self._gain_engine_active = False
        self._sr_sweep: Optional["SRCalibrationSweep"] = None
        self._sr_sweep_done = False

        # Bible Ch.7 §7.1 — Sleep enhancement state
        try:
            from eeg.slow_wave_enhancer import SlowWaveEnhancer

            self._swe: "SlowWaveEnhancer" = SlowWaveEnhancer()
        except Exception:
            self._swe = None  # type: ignore[assignment]

        # Bible Ch.7 §7.5 — TMR engine (encoding + replay)
        self._tmr: Optional[Any] = None
        try:
            from session.tmr_engine import TMREngine as _TMREngine

            self._tmr = _TMREngine(session_id)
        except Exception:
            pass

        # Consecutive sleep stage history for hysteresis-based transitions
        self._stage_history: list[str] = []
        # Sleep session metrics (accumulated during sleep phases, logged on SESSION_END)
        self._sleep_onset_latency_s: Optional[float] = None
        self._sleep_approach_entered_at: float = 0.0
        self._sleep_time_in_stage: dict = {"N1": 0.0, "N2": 0.0, "N3": 0.0, "REM": 0.0}
        self._sleep_last_stage_ts: float = 0.0
        self._alpha_disrupt_burst_count: int = 0
        self._alpha_disrupt_last_alpha: Optional[float] = None  # for abort detection

        # Bible Ch.9 §9.1 — Hypnagogic Training Window (HTW) state
        self._htw_count: int = 0
        self._htw_success_count: int = 0
        self._htw_total_duration_s: float = 0.0
        self._htw_last_ts: float = 0.0
        self._htw_phrases_presynth: bool = False
        self._htw_start_ts: float = 0.0
        self._pre_htw_state: Dict = {}
        self._htw_alpha_surge_ts: Optional[float] = None

        # Bible Ch.1 §8 — Hardware output channel state
        self._haptic_connected = False
        self._tavns_connected = False
        self._hardware_checked_this_tick = False

        # Bible Ch.7 §29 — Edison Mode manager
        self._edison = None
        self._is_edison = session_type == "edison"
        if self._is_edison:
            try:
                from session.edison_mode import EdisonModeManager

                live_tmp = {}
                try:
                    live_tmp = json.loads(_LIVE.read_text(encoding="utf-8"))
                except Exception:
                    pass
                self._edison = EdisonModeManager(
                    n1_hold_seconds=float(live_tmp.get("edison_n1_hold_seconds", 60)),
                    max_cycles=int(live_tmp.get("edison_max_cycles", 5)),
                    seed_topic=str(live_tmp.get("edison_seed_topic", "")),
                )
            except Exception as e:
                print(f"[Conductor] EdisonModeManager unavailable: {e}")

        # Bible Ch.7 §§30-31 — SSILD engine
        self._ssild = None
        self._is_ssild = session_type == "ssild"
        if self._is_ssild:
            try:
                from session.ssild_engine import SSILDEngine

                self._ssild = SSILDEngine()
            except Exception as e:
                print(f"[Conductor] SSILDEngine unavailable: {e}")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def get_tick_rate(self) -> Optional[int]:
        """Return current phase tick rate in seconds, or None if session ended."""
        return _TICK_RATES[self.phase]

    def tick(self) -> None:
        """Single evaluation cycle.  Called by the agent thread at tick_rate Hz.

        Flow: read → SQI gate → evaluate transitions → resolve conflicts →
              compute parameters → write → speak → FAA-gate affirmations → log.
        """
        if self.phase == Phase.SESSION_END:
            return

        now = time.time()
        elapsed = now - self.session_start
        phase_dur = now - self.phase_entered_at
        self._hardware_checked_this_tick = False

        # Always: session timer hard stop
        if elapsed >= self.session_duration and self.phase != Phase.SESSION_END:
            self._transition(self.phase, Phase.SESSION_END, {})
            return

        # ── GENUS_BLOCK: 40 Hz protocol with internal sub-phases (Bible Ch.4 Addendum A §3) ─────
        # Sub-phases: RAMP_UP → ACTIVE → WIND_DOWN → (SESSION_END or FALLBACK)
        # FALLBACK: low entrainment detected; abort gracefully.
        try:
            _live_tmp = json.loads(_LIVE.read_text(encoding="utf-8"))
        except Exception:
            _live_tmp = {}

        genus_active = bool(_live_tmp.get("genus_active", False))
        genus_remaining = float(_live_tmp.get("genus_session_remaining_s", 3600.0))
        genus_elapsed = float(_live_tmp.get("genus_session_elapsed_s", 0.0))
        genus_ratio = float(_live_tmp.get("eeg_genus_ratio", 1.0))

        # Enter GENUS_BLOCK on first activation
        if (
            genus_active
            and self.session_type == "genus"
            and self.phase != Phase.GENUS_BLOCK
        ):
            self._transition(
                self.phase,
                Phase.GENUS_BLOCK,
                {
                    "beat_frequency": 40.0,
                    "beat_type": "isochronic",
                    "entrainment_mode": "isochronic",
                    "timeline_label": "genus_block",
                    "genus_conductor_active": True,
                    "genus_sub_phase": "RAMP_UP",
                    "genus_audio_gain": 0.5,
                    "genus_modulation_depth": 0.0,
                },
            )
            self._genus_sub_phase = "RAMP_UP"
            self._genus_sub_entered_at = now
            self._genus_low_ent_since = None

        if self.phase == Phase.GENUS_BLOCK:
            sub = self._genus_sub_phase
            sub_dur = now - self._genus_sub_entered_at

            # ── User/timer interrupt while not yet winding down → start WIND_DOWN
            if not genus_active and sub not in ("WIND_DOWN", "FALLBACK"):
                self._genus_sub_phase = "WIND_DOWN"
                self._genus_sub_entered_at = now
                sub = "WIND_DOWN"
                sub_dur = 0.0
                patch_live({"genus_fallback_reason": None})

            # ── Pre-emptive wind-down when ≤60 s remain (timer-driven sessions)
            if sub == "ACTIVE" and genus_remaining <= 60.0:
                self._genus_sub_phase = "WIND_DOWN"
                self._genus_sub_entered_at = now
                sub = "WIND_DOWN"
                sub_dur = 0.0

            genus_level = _live_tmp.get("genus_entrainment_level", "absent")

            if sub == "RAMP_UP":
                # Audio ramp 0.5 → 1.0 over 60 s (doc: 50% → target over 60 s)
                audio_gain = min(1.0, 0.5 + sub_dur / 120.0)
                # Visual ramp: hold 0 for first 30 s, then 0.3 → 1.0 from 30–60 s
                if sub_dur < 30.0:
                    vis_depth = 0.0
                else:
                    vis_depth = min(1.0, 0.3 + (sub_dur - 30.0) / 30.0 * 0.7)

                patch_live(
                    {
                        "beat_frequency": 40.0,
                        "entrainment_mode": "isochronic",
                        "conductor_phase": "genus_block",
                        "genus_sub_phase": "RAMP_UP",
                        "genus_conductor_active": True,
                        "genus_audio_gain": round(audio_gain, 3),
                        "genus_modulation_depth": round(vis_depth, 3),
                        "timeline_label": "genus_block",
                    }
                )
                # Advance to ACTIVE once audio is fully ramped and either EEG
                # confirms entrainment or no EEG is available.
                eeg_ok = genus_ratio >= 1.5 or not self.eeg_enabled
                if sub_dur >= 60.0 and eeg_ok:
                    self._genus_sub_phase = "ACTIVE"
                    self._genus_sub_entered_at = now
                elif sub_dur >= 120.0:
                    # Forced advance; write fallback note if entrainment is weak
                    if self.eeg_enabled and genus_ratio < 1.2:
                        patch_live({"genus_fallback_reason": "low_entrainment_ramp"})
                    self._genus_sub_phase = "ACTIVE"
                    self._genus_sub_entered_at = now
                return

            elif sub == "ACTIVE":
                # Monitor entrainment; trigger FALLBACK on sustained low ratio
                if self.eeg_enabled and genus_ratio < 1.2:
                    if self._genus_low_ent_since is None:
                        self._genus_low_ent_since = now
                    elif now - self._genus_low_ent_since >= 120.0:
                        self._genus_sub_phase = "FALLBACK"
                        self._genus_sub_entered_at = now
                        patch_live({"genus_fallback_reason": "low_entrainment_active"})
                        return
                else:
                    self._genus_low_ent_since = None

                # User-configured modulation depth (preserves slider setting)
                user_depth = float(
                    _live_tmp.get(
                        "genus_user_modulation_depth",
                        _live_tmp.get("genus_modulation_depth", 1.0),
                    )
                    or 1.0
                )
                patch_live(
                    {
                        "beat_frequency": 40.0,
                        "entrainment_mode": "isochronic",
                        "conductor_phase": "genus_block",
                        "genus_sub_phase": "ACTIVE",
                        "genus_conductor_active": True,
                        "genus_audio_gain": 1.0,
                        "genus_modulation_depth": user_depth,
                        "timeline_label": "genus_block",
                        "agent_conductor_hints": {
                            "genus_active": True,
                            "genus_elapsed_s": genus_elapsed,
                            "genus_remaining_s": genus_remaining,
                            "genus_ratio": genus_ratio,
                            "genus_level": genus_level,
                        },
                    }
                )
                return

            elif sub == "WIND_DOWN":
                # First 30 s: fade visual to 0; next 30 s: fade audio to 0.
                if sub_dur < 30.0:
                    vis_depth = max(0.0, 1.0 - sub_dur / 30.0)
                    audio_gain = 1.0
                elif sub_dur < 60.0:
                    vis_depth = 0.0
                    audio_gain = max(0.0, 1.0 - (sub_dur - 30.0) / 30.0)
                else:
                    vis_depth = 0.0
                    audio_gain = 0.0

                patch_live(
                    {
                        "conductor_phase": "genus_block",
                        "genus_sub_phase": "WIND_DOWN",
                        "genus_audio_gain": round(audio_gain, 3),
                        "genus_modulation_depth": round(vis_depth, 3),
                    }
                )
                if sub_dur >= 60.0:
                    self._transition(
                        Phase.GENUS_BLOCK,
                        Phase.SESSION_END,
                        {
                            "genus_conductor_active": False,
                            "genus_active": False,
                            "genus_audio_gain": 0.0,
                            "genus_modulation_depth": 0.0,
                        },
                    )
                return

            elif sub == "FALLBACK":
                # Immediately zero stimuli, brief hold, then end session.
                patch_live(
                    {
                        "conductor_phase": "genus_block",
                        "genus_sub_phase": "FALLBACK",
                        "genus_conductor_active": False,
                        "genus_audio_gain": 0.0,
                        "genus_modulation_depth": 0.0,
                    }
                )
                if sub_dur >= 5.0:
                    self._transition(
                        Phase.GENUS_BLOCK,
                        Phase.SESSION_END,
                        {
                            "genus_conductor_active": False,
                            "genus_active": False,
                        },
                    )
                return

        # ── EDISON MODE: state-driven N1 interception (Bible Ch.7 §29) ───────────
        if self._is_edison and self._edison is not None:
            # On first tick, enter EDISON_PREPARATION
            if self.phase == Phase.CALIBRATION:
                self._transition(self.phase, Phase.EDISON_PREPARATION, {})
                return

            # Delegate to the EdisonModeManager for state updates
            live_snap_edison = {}
            try:
                live_snap_edison = json.loads(_LIVE.read_text(encoding="utf-8"))
            except Exception:
                pass
            edison_updates = self._edison.tick(live_snap_edison)
            if edison_updates and "agent_message" in edison_updates:
                cur = live_snap_edison.get("agent_message") or {}
                if isinstance(cur, dict) and cur.get("needs_response"):
                    edison_updates.pop("agent_message", None)
            if edison_updates:
                patch_live(edison_updates)

            # Mirror Edison manager state → Conductor phase
            from session.edison_mode import EdisonState

            edison_state = self._edison.state
            phase_map = {
                EdisonState.PREPARATION: Phase.EDISON_PREPARATION,
                EdisonState.SEED_DELIVERY: Phase.EDISON_SEED,
                EdisonState.MONITORING: Phase.EDISON_MONITORING,
                EdisonState.N1_HOLD: Phase.EDISON_N1_HOLD,
                EdisonState.CAPTURE: Phase.EDISON_CAPTURE,
                EdisonState.CYCLE_COMPLETE: Phase.EDISON_CYCLE_END,
                EdisonState.SESSION_END: Phase.SESSION_END,
            }
            target_phase = phase_map.get(edison_state)
            if target_phase and target_phase != self.phase:
                self._transition(self.phase, target_phase, {})

            # Clear one-shot signals
            if live_snap_edison.get("edison_user_ready"):
                patch_live({"edison_user_ready": None})
            if live_snap_edison.get("edison_continue"):
                patch_live({"edison_continue": None})
            if live_snap_edison.get("edison_end_session"):
                patch_live({"edison_end_session": None})
            return

        # ── SSILD: TTS-guided sensory cycling (Bible Ch.7 §§30-31) ─────────────────
        if self._is_ssild and self._ssild is not None:
            if self.phase == Phase.CALIBRATION:
                self._transition(self.phase, Phase.SSILD_PRE_TECHNIQUE, {})
                return

            live_snap_ssild = {}
            try:
                live_snap_ssild = json.loads(_LIVE.read_text(encoding="utf-8"))
            except Exception:
                pass
            ssild_updates = self._ssild.tick(live_snap_ssild)
            if ssild_updates and "agent_message" in ssild_updates:
                cur = live_snap_ssild.get("agent_message") or {}
                if isinstance(cur, dict) and cur.get("needs_response"):
                    ssild_updates.pop("agent_message", None)
            if ssild_updates:
                patch_live(ssild_updates)

            from session.ssild_engine import SSILDPhase

            ssild_phase = self._ssild.phase
            ssild_map = {
                SSILDPhase.PRE_TECHNIQUE: Phase.SSILD_PRE_TECHNIQUE,
                SSILDPhase.QUICK_CYCLES: Phase.SSILD_QUICK_CYCLES,
                SSILDPhase.SLOW_CYCLES: Phase.SSILD_SLOW_CYCLES,
                SSILDPhase.POST_TECHNIQUE: Phase.SSILD_POST_TECHNIQUE,
                SSILDPhase.REM_MONITORING: Phase.SSILD_REM_MONITORING,
                SSILDPhase.DREAM_JOURNAL: Phase.SSILD_DREAM_JOURNAL,
                SSILDPhase.COMPLETE: Phase.SESSION_END,
            }
            target_phase = ssild_map.get(ssild_phase)
            if target_phase and target_phase != self.phase:
                self._transition(self.phase, target_phase, {})
            return

        # ── Step 1: Read all metrics ──────────────────────────────────────────
        metrics = self._read_metrics()
        self._last_metrics = metrics  # expose for assessment()

        # Maintain a rolling 10-tick slope history for _slope_trend()
        depth_m = metrics.get("depth", {})
        if depth_m.get("spectral_slope") is not None:
            history = getattr(self, "_slope_history", [])
            history.append(depth_m["spectral_slope"])
            self._slope_history = history[-10:]

        # ── Step 1b: Read agent hints + Director state ───────────────────────────
        try:
            live_raw = _LIVE.read_text(encoding="utf-8")
            live_snap = json.loads(live_raw)
            hints_raw = live_snap.get("agent_conductor_hints") or {}
            self._hints = hints_raw if isinstance(hints_raw, dict) else {}
            # Bible Ch.5 §5.5 — Director gain ceiling; store for downstream use
            self._director_gain_ceiling = float(
                live_snap.get("director_gain_ceiling", 1.0) or 1.0
            )
            # Director phase hint: if Director is in CONSOLIDATION or EMERGENCE
            # the Conductor should not escalate past those phases
            self._director_phase = live_snap.get("director_phase") or ""
        except Exception:
            live_snap = {}
            self._director_gain_ceiling = 1.0
            self._director_phase = ""

        # ── Step 1c: VR session start — validate frequency allocation ─────────
        vr_now_active = bool(live_snap.get("vr_headset_active"))
        if vr_now_active and not self._vr_was_active:
            self._validate_vr_frequencies(live_snap)
        self._vr_was_active = vr_now_active

        # ── Step 2: SQI gate ─────────────────────────────────────────────────
        sqi = metrics["sqi_confidence"]
        if sqi == "DISABLED":
            # EEG was never enabled — go straight to timer-only mode silently.
            self._enter_degraded_mode(metrics)
        elif sqi == "NONE":
            # EEG is connected but signal is too noisy — announce and hold.
            self._handle_sqi_failure(metrics, phase_dur)
            self._log_decision(
                metrics, "HOLD_SQI_FAILURE", "All-channel SQI below threshold"
            )
            return

        # Exit degraded mode if SQI recovered
        if self._degraded and sqi not in ("NONE", "DISABLED"):
            self._degraded = False
            self._degraded_since = None
            patch_live({"eeg_signal_lost": False})
            print("[Conductor] SQI recovered — exiting degraded mode")

        # ── Step 3: IAF capture ───────────────────────────────────────────────
        if self.iaf is None:
            iaf_live = metrics.get("iaf_hz")
            if iaf_live:
                self.iaf = iaf_live
                self.current_target_freq = iaf_live
                print(f"[Conductor] IAF detected: {iaf_live:.2f} Hz")
            elif phase_dur > 90 and _sqi_rank(metrics["sqi_confidence"]) >= _sqi_rank(
                "REDUCED"
            ):
                self.iaf = 10.0
                self.current_target_freq = 10.0
                self._log_decision(
                    metrics,
                    "IAF_FALLBACK",
                    "IAF not detected after 90 s, using 10.0 Hz",
                )
                print("[Conductor] IAF fallback: 10.0 Hz")

        # ── Step 4: Phase transitions ─────────────────────────────────────────
        next_phase = self._evaluate_transitions(metrics, phase_dur, elapsed)
        if next_phase and next_phase != self.phase:
            old = self.phase
            self._transition(old, next_phase, metrics)
            self._log_decision(
                metrics,
                f"TRANSITION_{old.value}_TO_{next_phase.value}",
                self._transition_rationale(old, next_phase, metrics),
            )
            return

        # ── Step 5: Conflict resolution ───────────────────────────────────────
        adjustments = self._resolve_conflicts(metrics)

        # ── Step 6: Compute parameters ────────────────────────────────────────
        params = self._compute_parameters(metrics, adjustments, phase_dur)

        # ── Step 7: Write to live_control.json ───────────────────────────────
        # Always publish conductor_state alongside any param changes so the
        # control panel and agent always have current phase/assessment data.
        params["conductor_state"] = self._build_state_snapshot(metrics)

        # Bible Ch.2 §2.9 §4 — converged depth estimate (EEG + autonomic)
        depth_est, depth_conf = self._estimate_depth_confidence(live_snap)
        params["depth_estimate"] = depth_est
        params["depth_confidence"] = depth_conf

        # Hard safety clamps — these prevent visual blowout and wasted range
        # regardless of agent hints, session YAML, or dynamic ramp calculations.
        if "trail_decay" in params:
            params["trail_decay"] = min(params["trail_decay"], 0.80)
        if "entrainment_strength" in params:
            params["entrainment_strength"] = min(params["entrainment_strength"], 0.10)

        patch_live(params)

        # ── Step 7.5: Crossmodal Gain Engine (Bible Ch.3 §3.8) ────────────────────────
        self._gain_engine_tick()

        # ── Step 7.6: VR closed-loop photic entrainment (Bible Ch.8 §8.4) ─────────────
        self._vr_photic_loop(metrics)

        # ── Step 8: Agent speech ──────────────────────────────────────────────
        speech = self._get_phase_speech(metrics, adjustments, phase_dur)
        if speech:
            self._say(speech)

        # ── Step 9: FAA-gated affirmation delivery ───────────────────────────
        if self._should_deliver_affirmation(metrics, adjustments):
            self._deliver_affirmation_with_tmr()

        # ── Step 10: Log decision ─────────────────────────────────────────────
        self._log_decision(
            metrics, "MAINTAIN", f"Holding {self.phase.value}; adj={adjustments}"
        )

    def finalize(self) -> None:
        """Flush remaining decision log and mark session end.  Call on display stop."""
        self._flush_log()
        print(
            f"[Conductor] Session finalized — {len(self._decision_log)} "
            f"unflushed entries written"
        )

    # =========================================================================
    # METRIC READING
    # =========================================================================

    def _read_live(self) -> Dict[str, Any]:
        try:
            return json.loads(_LIVE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _read_metrics(self) -> Dict[str, Any]:
        """Read all subsystem outputs from live_control.json.

        Metric availability follows SQI gating (Bible Ch.5 §5.3):
          FULL / REDUCED: full metric suite
          LOW:            FAA available; ASSR unavailable; trance_score unreliable
          NONE:           no EEG metrics trusted
        """
        live = self._read_live()

        eeg_connected = bool(live.get("eeg_connected"))
        raw_conf = live.get("eeg_confidence") or "none"
        # When EEG is not connected at all there is no signal to be "lost" —
        # treat confidence as a special sentinel so the SQI gate can distinguish
        # "hardware absent" from "hardware present but signal bad".
        confidence = raw_conf.upper() if eeg_connected else "DISABLED"

        metrics: Dict[str, Any] = {
            "timestamp": time.time(),
            "eeg_connected": eeg_connected,
            "sqi_confidence": confidence,
            "phase": self.phase.value,
            "sleep_onset_detected": bool(live.get("sleep_onset_detected")),
            "iaf_hz": live.get("eeg_iaf_hz"),
            # Always expose for live display even without full suite
            "beat_frequency": live.get("beat_frequency"),
            "spiral_chaos": live.get("spiral_chaos"),
            "trail_decay": live.get("trail_decay"),
        }

        if _sqi_rank(confidence) >= _sqi_rank("REDUCED"):
            # Full metric suite
            assr_strength = live.get("eeg_entrainment_strength")
            assr_conf_raw = live.get("eeg_entrainment_confidence") or "unavailable"
            # Map Somna ASSR confidence strings to Research SQI-like tiers
            assr_conf = {
                "active": "FULL",
                "alpha_overlap": "REDUCED",
                "unavailable": "NONE",
            }.get(assr_conf_raw.lower(), "NONE")

            metrics["assr"] = {
                "strength": assr_strength or 0.0,
                "confidence": assr_conf,
            }
            faa_val = live.get("eeg_faa") or 0.0
            faa_state = live.get("eeg_faa_state") or "insufficient_data"
            metrics["faa"] = {
                "value": faa_val,
                "state": faa_state,
            }
            trance = live.get("eeg_trance_score")
            metrics["trance_score"] = trance
            if trance is not None:
                self._trance_history.append((metrics["timestamp"], trance))
                # Keep rolling 5-minute window
                cutoff = metrics["timestamp"] - 300
                self._trance_history = [
                    (t, v) for t, v in self._trance_history if t >= cutoff
                ]
            metrics["sef95"] = live.get("eeg_sef95")

        elif confidence == "LOW":
            metrics["assr"] = None
            faa_val = live.get("eeg_faa") or 0.0
            faa_state = live.get("eeg_faa_state") or "insufficient_data"
            metrics["faa"] = {
                "value": faa_val,
                "state": faa_state,
            }
            metrics["trance_score"] = None
            metrics["sef95"] = live.get("eeg_sef95")

        else:  # NONE
            metrics["assr"] = None
            metrics["faa"] = None
            metrics["trance_score"] = None
            metrics["sef95"] = None

        # FreqLeader outputs
        metrics["freq_lead_current"] = live.get("freq_lead_current")
        metrics["freq_lead_phase"] = live.get("freq_lead_phase") or "inactive"

        # Phase-cascade outputs (Bible Ch.4 §4.6) — always present; nulls when EEG absent
        metrics["cascade"] = {
            "cascade_integrity": live.get("pac_cascade_integrity", 0.0) or 0.0,
            "isa_alpha_pac": live.get("pac_isa_alpha", 0.0) or 0.0,
            "theta_gamma_pac": live.get("pac_theta_gamma", 0.0) or 0.0,
            "alpha_gamma_pac": live.get("pac_alpha_gamma", 0.0) or 0.0,
            "alpha_at_trough": live.get("alpha_at_trough", False),
            "alpha_confidence": live.get("alpha_phase_confidence", 0.0) or 0.0,
            "respiratory_hot": live.get("respiratory_hot", False),
            "phase_gate_mode": live.get("phase_gate_mode", "disabled"),
            "phase_gate_hit_rate": live.get("phase_gate_hit_rate", 0.0) or 0.0,
            "delivery_rate_hz": live.get("delivery_rate_hz", 0.0) or 0.0,
        }

        # Bible Ch.2 §2.8 — three-axis depth markers (always included when EEG connected)
        metrics["depth"] = {
            "spectral_slope": live.get("eeg_spectral_slope"),
            "slope_confidence": live.get("eeg_slope_confidence", 0.0) or 0.0,
            "coherence_depth": live.get("eeg_coherence_depth", 0.0) or 0.0,
            "frontal_alpha_coh": live.get("eeg_coherence_frontal_alpha", 0.5) or 0.5,
            "frontal_beta_coh": live.get("eeg_coherence_frontal_beta", 0.5) or 0.5,
            "temporal_theta_coh": live.get("eeg_coherence_temporal_theta", 0.5) or 0.5,
            "beta_env_corr": live.get("eeg_beta_env_corr", 1.0)
            if live.get("eeg_beta_env_corr") is not None
            else 1.0,
            "trance_score_v2": live.get("eeg_trance_score_v2"),
        }

        # VR SSVEP outputs (Bible Ch.8 §8.1/30) — present only when VR is active
        if live.get("vr_headset_active"):
            metrics["vr"] = {
                "binocular_index": live.get("ssvep_binocular_index"),
                "dominance_raw": live.get("ssvep_dominance_raw"),
                "switch_rate_hz": live.get("ssvep_switch_rate_hz"),
                "left_snr": live.get("ssvep_left_snr"),
                "right_snr": live.get("ssvep_right_snr"),
                "im_plus": live.get("ssvep_im_f1_plus_f2"),
                "im_minus": live.get("ssvep_im_f1_minus_f2"),
                "render_mode": live.get("vr_render_mode", "ganzfeld"),
                "safety_kill": live.get("vr_safety_kill", False),
            }
        else:
            metrics["vr"] = None

        return metrics

    # =========================================================================
    # TRANSITION EVALUATION
    # =========================================================================

    def _evaluate_transitions(
        self, m: Dict, phase_dur: float, elapsed: float
    ) -> Optional[Phase]:
        """Check all valid transitions from current phase.  Returns target or None."""
        phase = self.phase
        # live_snap is read lazily inside specific branches (CALIBRATION SR sweep,
        # HTW eligibility, etc.).  Initialise to {} so all code paths that reference
        # it but don't reach a lazy-read branch (e.g. MAINTENANCE → line 807) get a
        # harmless empty dict instead of an UnboundLocalError.
        live_snap: Dict = {}

        # ── Timer-mode fallback (EEG disabled or degraded) ────────────────────
        # When _timer_mode is set, bypass all EEG-gated conditions and advance
        # through phases on a fixed schedule. _TIMER_SCHEDULE maps elapsed-minutes
        # thresholds to phases; we find the latest threshold we've passed and
        # transition there if it differs from the current phase.
        if getattr(self, "_timer_mode", False):
            elapsed_min = elapsed / 60.0
            target_phase = Phase.CALIBRATION
            for minute_mark, sched_phase in _TIMER_SCHEDULE:
                if elapsed_min >= minute_mark:
                    target_phase = sched_phase
            # Only allow forward transitions — never regress to a phase the
            # session has already passed through (e.g. sleep_approach → maintenance).
            _PHASE_ORDER = [
                Phase.CALIBRATION,
                Phase.INDUCTION,
                Phase.DEEPENING,
                Phase.MAINTENANCE,
                Phase.SLEEP_APPROACH,
                Phase.SLEEP_ONSET,
                Phase.SLEEP_MAINTAIN,
                Phase.SESSION_END,
            ]
            current_rank = _PHASE_ORDER.index(phase) if phase in _PHASE_ORDER else 0
            target_rank = (
                _PHASE_ORDER.index(target_phase) if target_phase in _PHASE_ORDER else 0
            )
            if target_rank > current_rank:
                print(
                    f"[Conductor] Timer-mode: {phase.value} → {target_phase.value} "
                    f"at {elapsed_min:.1f} min"
                )
                return target_phase
            # For sleep sessions in MAINTENANCE and beyond, fall through to
            # phase-specific logic so the sleep-stage fallbacks can fire.
            if not (
                self.session_type == "sleep"
                and phase
                in (
                    Phase.MAINTENANCE,
                    Phase.SLEEP_APPROACH,
                    Phase.SLEEP_ONSET,
                    Phase.SLEEP_MAINTAIN,
                )
            ):
                return None

        # ── CALIBRATION ───────────────────────────────────────────────────────
        if phase == Phase.CALIBRATION:
            sqi_ok = _sqi_rank(m["sqi_confidence"]) >= _sqi_rank("REDUCED")
            iaf_ok = self.iaf is not None

            # Bible Ch.3 §3.8 §6: SR calibration sweep — runs after IAF is confirmed.
            # Sweeps noise 0→60 (13 levels × 10 s = ~130 s).  Ticked here at 1 Hz.
            # If the session advances to INDUCTION before completion, the sweep is
            # abandoned and population defaults are used for the gain profile.
            if _GAIN_AVAILABLE and sqi_ok and iaf_ok and not self._sr_sweep_done:
                if self._sr_sweep is None:
                    self._sr_sweep = SRCalibrationSweep()
                    print("[Conductor] SR calibration sweep started")
                if not self._sr_sweep.complete:
                    live_snap = self._read_live()
                    sr_patch = self._sr_sweep.tick(live_snap)
                    if sr_patch:
                        patch_live(sr_patch)
                else:
                    # Sweep complete — persist and update gain profile
                    self._sr_sweep_done = True
                    result = self._sr_sweep._compute_optimal()
                    try:
                        from content_tools.somna_db import store_sr_calibration

                        live_snap = self._read_live()
                        store_sr_calibration(
                            str(live_snap.get("session_name") or "unknown"), result
                        )
                        patch_live(
                            {
                                "sr_optimal_noise": result["sr_optimal_noise"],
                                "sr_gain_bonus": result["sr_gain_bonus"],
                            }
                        )
                        print(
                            f"[Conductor] SR sweep complete: "
                            f"optimal_noise={result['sr_optimal_noise']}, "
                            f"gain_bonus={result['sr_gain_bonus']:.3f}"
                        )
                    except Exception as e:
                        print(f"[Conductor] SR calibration persist error: {e}")

            if sqi_ok and iaf_ok and self._can_transition_to(Phase.INDUCTION):
                # Allow transition once sweep is done or timed out (> 150 s in CALIBRATION)
                sweep_done = (
                    self._sr_sweep_done or not _GAIN_AVAILABLE or phase_dur > 150
                )
                if sweep_done:
                    self._hold_start("cal_ready")
                    if self._hold_met("cal_ready", 30):
                        return Phase.INDUCTION
            else:
                self._hold_reset("cal_ready")

            if phase_dur > 120 and m["sqi_confidence"] == "NONE":
                return Phase.SESSION_END

        # ── INDUCTION ─────────────────────────────────────────────────────────
        elif phase == Phase.INDUCTION:
            assr = m.get("assr")
            assr_ok = assr and _sqi_rank(assr["confidence"]) >= _sqi_rank("REDUCED")

            # VR corroboration (Bible Ch.8 §8.2): binocular rivalry onset confirms entrainment
            # even when ASSR is marginal.  Binocular index > 0.5 at rivalry onset
            # (typically 60–90 s into induction) is treated as equivalent to REDUCED
            # ASSR confidence for the induction lock.
            vr = m.get("vr")
            vr_induction_ok = (
                vr is not None
                and not vr.get("safety_kill")
                and (vr.get("binocular_index") or 0.0) > 0.5
            )
            if assr_ok or vr_induction_ok:
                self._hold_start("induction_lock")
                patience = float(self._hints.get("depth_patience", 1.0))
                if self._hold_met("induction_lock", 60, patience):
                    if self._can_transition_to(Phase.DEEPENING):
                        src = (
                            "VR binocular"
                            if vr_induction_ok and not assr_ok
                            else "ASSR"
                        )
                        # Bible Ch.2 §2.8 §6.1: capture baseline slope + coherence baselines.
                        # INDUCTION is the first phase with reliable EEG; persist to
                        # calibration_v2 so the gain engine and trance composite have
                        # individual references for subsequent sessions.
                        depth = m.get("depth", {})
                        if depth.get("spectral_slope") is not None:
                            patch_live({"eeg_baseline_slope": depth["spectral_slope"]})
                            try:
                                from content_tools.somna_db import store_calibration_v2

                                live_snap = self._read_live()
                                store_calibration_v2(
                                    session_id=str(
                                        live_snap.get("session_name") or "unknown"
                                    ),
                                    iaf_hz=float(self.iaf or 10.0),
                                    baseline_slope=depth["spectral_slope"],
                                    baseline_frontal_alpha_coh=depth.get(
                                        "frontal_alpha_coh"
                                    ),
                                    baseline_beta_env_corr=depth.get("beta_env_corr"),
                                    baseline_temporal_theta_coh=depth.get(
                                        "temporal_theta_coh"
                                    ),
                                    calibration_quality="good",
                                )
                            except Exception:
                                pass
                        print(f"[Conductor] INDUCTION lock via {src}")
                        return Phase.DEEPENING
            else:
                self._hold_reset("induction_lock")

            # Modality switch after 180 s without lock
            if (
                phase_dur > 180
                and not self._hold_active("induction_lock")
                and self._modality_switches < 2
            ):
                self._switch_modality()

            # Hard fail: 10 min total induction
            if phase_dur > 600:
                print("[Conductor] INDUCTION hard fail — no ASSR lock after 10 min")
                return Phase.SESSION_END

        # ── DEEPENING ─────────────────────────────────────────────────────────
        elif phase == Phase.DEEPENING:
            ts = m.get("trance_score")
            assr = m.get("assr")

            ts_ok = ts is not None and ts > self._ct("trance_moderate", 0.65)
            assr_ok = assr and _sqi_rank(assr["confidence"]) >= _sqi_rank("REDUCED")

            # VR trance corroboration (Bible Ch.8 §8.2): elevated binocular index + switch rate
            # act as a secondary trance proxy when EEG data is marginal.
            vr = m.get("vr")
            vr_deep_ok = (
                vr is not None
                and not vr.get("safety_kill")
                and (vr.get("binocular_index") or 0.0) > 0.6
                and (vr.get("switch_rate_hz") or 0.0) > 0.10
            )
            if vr_deep_ok and not ts_ok:
                ts_ok = True  # VR corroborates depth; ASSR still required separately

            if ts_ok:
                self._hold_start("deep_ready")
            else:
                self._hold_reset("deep_ready")
            if assr_ok:
                self._hold_start("deep_assr")
            else:
                self._hold_reset("deep_assr")

            patience = float(self._hints.get("depth_patience", 1.0))
            cascade_ok = True  # default: not blocking when phase gate is disabled
            cascade = m.get("cascade", {})
            if cascade.get("phase_gate_mode") != "disabled":
                # Phase gate is active — require temporal synchronization (Bible Ch.4 §4.6 §12.3)
                ci = float(cascade.get("cascade_integrity") or 0.0)
                cascade_ok = ci >= 0.05
                if not cascade_ok:
                    self._log_decision(
                        "DEEPENING",
                        f"trance_score qualifies for MAINTENANCE but cascade_integrity={ci:.3f} "
                        f"below 0.05 threshold — holding in DEEPENING for temporal synchronization",
                    )

            # Bible Ch.2 §2.8 §6.2 — convergent evidence check.
            # Require 2-of-3 depth axes to agree before DEEPENING → MAINTENANCE.
            # Oscillatory axis: sustained trance_score hold.
            # Aperiodic axis:   slope steepened ≥ 0.2 below baseline (more negative).
            # Connectivity axis: coherence_depth > 0.3 (frontal decoupling visible).
            depth = m.get("depth", {})
            conv_osc = ts_ok
            baseline_s = float(self._live.get("eeg_baseline_slope") or -1.3)
            slope = depth.get("spectral_slope")
            conv_slope = (
                slope is not None
                and depth.get("slope_confidence", 0.0) > 0.5
                and (baseline_s - slope) > 0.2
            )
            conv_coh = depth.get("coherence_depth", 0.0) > 0.3
            try:
                from eeg.depth_features import convergent_check

                convergent_ok = convergent_check(conv_osc, conv_slope, conv_coh)
            except Exception:
                convergent_ok = True  # graceful fallback if module unavailable

            if (
                self._hold_met("deep_ready", 90, patience)
                and self._hold_met("deep_assr", 60, patience)
                and cascade_ok
                and convergent_ok
                and self._can_transition_to(Phase.MAINTENANCE)
            ):
                return Phase.MAINTENANCE

            # Optional fractionation early exit
            if self._frac_eligible(elapsed) and self._can_transition_to(
                Phase.FRAC_EMERGE
            ):
                if ts is not None and ts > self._ct("trance_frac_eligible", 0.5):
                    self._hold_start("frac_ready")
                    if self._hold_met("frac_ready", 60):
                        return Phase.FRAC_EMERGE
                else:
                    self._hold_reset("frac_ready")

            # Sleep branch — Bible Ch.2 §2.8 §6.1: convergent evidence for sleep approach
            depth = m.get("depth", {})
            slope_sleep_ok = (
                depth.get("spectral_slope") is not None
                and depth["spectral_slope"] < -2.2
                and depth.get("coherence_depth", 0.0) > 0.6
            )
            if (
                self.session_type == "sleep"
                and ts is not None
                and ts > self._ct("trance_sleep_approach", 0.6)
                and (slope_sleep_ok or phase_dur > 480)
            ):  # slope-gated or 8-min fallback
                self._hold_start("sleep_ready")
                if self._hold_met("sleep_ready", 120):
                    return Phase.SLEEP_APPROACH
            else:
                self._hold_reset("sleep_ready")

            # Fallback: failing to deepen after 10 min → timer mode
            if phase_dur > 600 and (
                ts is None or ts < self._ct("trance_frac_eligible", 0.5)
            ):
                self._enter_degraded_mode(m)

        # ── MAINTENANCE ───────────────────────────────────────────────────────
        elif phase == Phase.MAINTENANCE:
            if (
                self._frac_eligible(elapsed)
                and phase_dur > 180
                and self._can_transition_to(Phase.FRAC_EMERGE)
            ):
                return Phase.FRAC_EMERGE
            # Timer fallback (non-EEG sleep sessions)
            if self.session_type == "sleep" and phase_dur > 300:
                return Phase.SLEEP_APPROACH
            # Fork detection: EEG-driven trance-to-sleep transition (Bible Ch.7 §7.1 §7.4)
            if (
                self.session_type in ("sleep", "general")
                and phase_dur > 120
                and self._detect_sleep_fork()
            ):
                self._hold_start("sleep_fork")
                if self._hold_met("sleep_fork", 30):
                    return Phase.SLEEP_APPROACH
            else:
                self._hold_reset("sleep_fork")
            # Bible Ch.2 §2.9 §5.3 — behavioral N1 cue: head nod triggers early SLEEP_APPROACH
            # transition before EEG staging confirms N1.  Clear the flag after acting.
            if (
                self.session_type in ("sleep", "general")
                and live_snap.get("sleep_onset_behavioral_cue", False)
                and phase_dur > 60
            ):
                patch_live({"sleep_onset_behavioral_cue": False})
                return Phase.SLEEP_APPROACH
            # Cascade desync watchdog (Bible Ch.4 §4.6 §12.3): if cascade_integrity drops
            # below 0.03 for >30 s while gate is active, log and hint agent to adjust.
            cascade = m.get("cascade", {})
            if cascade.get("phase_gate_mode") != "disabled":
                ci = float(cascade.get("cascade_integrity") or 0.0)
                if ci < 0.03:
                    self._hold_start("cascade_desync")
                    if self._hold_met("cascade_desync", 30):
                        self._log_decision(
                            "MAINTENANCE",
                            f"cascade_integrity={ci:.3f} below 0.03 for >30s — "
                            "temporal desynchronization; agent should adjust breath_rate or beat_frequency",
                        )
                        patch_live({"cascade_desync_hint": True})
                else:
                    self._hold_reset("cascade_desync")
                    patch_live({"cascade_desync_hint": False})

        # ── FRAC_EMERGE ───────────────────────────────────────────────────────
        elif phase == Phase.FRAC_EMERGE:
            sef = m.get("sef95")
            if sef is not None and sef > self._ct("sef95_light", 15.0):
                return Phase.FRAC_EMERGE_HOLD
            if phase_dur > 45:
                return Phase.FRAC_EMERGE_HOLD

        # ── FRAC_EMERGE_HOLD ──────────────────────────────────────────────────
        elif phase == Phase.FRAC_EMERGE_HOLD:
            target = self._select_emerge_hold_duration()
            if phase_dur >= target:
                return Phase.FRAC_REDROP

        # ── FRAC_REDROP ───────────────────────────────────────────────────────
        elif phase == Phase.FRAC_REDROP:
            ts = m.get("trance_score")
            if ts is not None and ts > self._ct("trance_moderate", 0.65):
                self._hold_start("redrop_ready")
                redrop_cascade_ok = True
                cascade = m.get("cascade", {})
                if cascade.get("phase_gate_mode") != "disabled":
                    ci = float(cascade.get("cascade_integrity") or 0.0)
                    redrop_cascade_ok = ci >= 0.03  # cascade must re-establish
                if self._hold_met("redrop_ready", 60) and redrop_cascade_ok:
                    self.fractionation_count += 1
                    return Phase.MAINTENANCE
            else:
                self._hold_reset("redrop_ready")
            if phase_dur > 180:
                self.fractionation_count += 1
                return Phase.DEEPENING

        # ── SLEEP_APPROACH ────────────────────────────────────────────────────
        elif phase == Phase.SLEEP_APPROACH:
            self._sample_sleep_stage()  # update history once per tick
            live_s = self._read_live()
            conf = float(live_s.get("eeg_sleep_confidence", 0.0))

            # Primary: N1 confirmed by 3 consecutive epochs + confidence > 0.6
            if self._consecutive_stage("N1", 3) and conf > 0.6:
                return Phase.SLEEP_ONSET

            # Legacy SEF95 fallback (pre-classifier sessions)
            sef = m.get("sef95")
            assr = m.get("assr")
            sef_low = sef is not None and sef < self._ct("sef95_deep", 8.0)
            assr_low = assr is None or assr["strength"] < self._ct(
                "assr_transition", 0.2
            )
            if sef_low:
                self._hold_start("sleep_sef")
                if self._hold_met("sleep_sef", 120) and assr_low:
                    return Phase.SLEEP_ONSET
            else:
                self._hold_reset("sleep_sef")

            # Alpha safety gate: abort anti-phase if alpha power surged 30% (arousal response)
            current_alpha = live_s.get("eeg_alpha")
            if current_alpha is not None:
                if self._alpha_disrupt_last_alpha is not None:
                    if current_alpha > self._alpha_disrupt_last_alpha * 1.30:
                        patch_live({"sleep_alpha_disrupt_enabled": False})
                        try:
                            from content_tools.somna_db import log_sleep_calibration

                            log_sleep_calibration(
                                str(live_s.get("session_name") or "unknown"),
                                {"calib_alpha_antiphase_tolerance": 0.0},
                            )
                        except Exception:
                            pass
                self._alpha_disrupt_last_alpha = current_alpha

            # Alpha-at-trough burst (phase-locked anti-phase stimulation)
            if live_s.get("sleep_alpha_disrupt_enabled") and live_s.get(
                "alpha_at_trough"
            ):
                burst_vol = int(live_s.get("sleep_alpha_disrupt_volume", 15))
                patch_live(
                    {
                        "sleep_burst_cmd_ts": time.time(),
                        "sleep_burst_volume": burst_vol,
                        "sleep_burst_duration_ms": 50,
                    }
                )
                self._alpha_disrupt_burst_count += 1
                patch_live(
                    {"sleep_alpha_disrupt_burst_count": self._alpha_disrupt_burst_count}
                )

            if self.session_type != "sleep":
                return Phase.MAINTENANCE

        # ── SLEEP_ONSET ───────────────────────────────────────────────────────
        elif phase == Phase.SLEEP_ONSET:
            self._sample_sleep_stage()
            live_s = self._read_live()
            conf = float(live_s.get("eeg_sleep_confidence", 0.0))

            # N2 confirmed: 5 consecutive epochs + confidence > 0.7
            if self._consecutive_stage("N2", 5) and conf > 0.7:
                return Phase.SLEEP_MAINTAIN

            # Reversion to Wake: restart from SLEEP_APPROACH
            if self._consecutive_stage("WAKE", 5):
                return Phase.SLEEP_APPROACH

        # ── SLEEP_MAINTAIN ────────────────────────────────────────────────────
        elif phase == Phase.SLEEP_MAINTAIN:
            self._sample_sleep_stage()
            self._accumulate_sleep_time()

            # Run SlowWaveEnhancer burst scheduler
            if self._swe is not None:
                live_s = self._read_live()
                stage = live_s.get("eeg_sleep_stage", "WAKE")
                swe_patch = self._swe.tick(live_s, stage, time.time())
                if swe_patch:
                    patch_live(swe_patch)
                    # Track SWA ratio in live state
                    delta_power = float(live_s.get("eeg_delta", 0.0) or 0.0)
                    swa_ratio = self._swe.record_delta(delta_power)
                    patch_live({"sleep_swa_enhancement_ratio": round(swa_ratio, 4)})

            # Run TMR replay scheduler (Bible Ch.7 §7.5)
            if self._tmr is not None:
                self._tmr.tick()

            # HTW eligibility check (Bible Ch.9 §9.1) — intercept N1 windows for training
            if self._htw_eligible():
                if not self._htw_phrases_presynth:
                    self._presynth_training_phrases()
                if self._consecutive_stage("N1", 3):  # 3 × 2 s = 6 s confirmed N1
                    return Phase.SLEEP_TRAINING

            # Natural wake detection: 30 s of sustained WAKE → SLEEP_WAKE
            if self._consecutive_stage("WAKE", 15):  # 15 ticks × 2 s = 30 s
                return Phase.SLEEP_WAKE

        # ── SLEEP_TRAINING (Bible Ch.9 §9.1 — HTW) ────────────────────────────────────
        elif phase == Phase.SLEEP_TRAINING:
            self._sample_sleep_stage()
            live_s = self._read_live()

            # Safety aborts — highest priority
            if live_s.get("eeg_signal_lost", False):
                return self._exit_sleep_training("signal_lost", Phase.SLEEP_WAKE)

            if live_s.get("timeline_locked_params"):
                return self._exit_sleep_training("user_interaction", Phase.SLEEP_WAKE)

            # Sustained alpha surge (> 60 s) → genuine arousal, exit to wake
            alpha_power = float(live_s.get("eeg_alpha", 0.0) or 0.0)
            if alpha_power > 0.25:
                if self._htw_alpha_surge_ts is None:
                    self._htw_alpha_surge_ts = time.time()
                elif time.time() - self._htw_alpha_surge_ts > 60.0:
                    return self._exit_sleep_training("alpha_surge", Phase.SLEEP_WAKE)
            else:
                self._htw_alpha_surge_ts = None

            # Early deepening — great outcome, return to maintenance cycle
            if self._consecutive_stage("N2", 3) or self._consecutive_stage("N3", 3):
                return self._exit_sleep_training("n2_detected", Phase.SLEEP_ONSET)

            # Hard 5-minute timeout
            if time.time() - self._htw_start_ts >= 300.0:
                return self._exit_sleep_training("timeout", Phase.SLEEP_ONSET)

        # ── SLEEP_WAKE ────────────────────────────────────────────────────────
        elif phase == Phase.SLEEP_WAKE:
            self._sample_sleep_stage()
            if phase_dur > 120:  # 2 minutes of confirmed wake → end session
                return Phase.SESSION_END

        return None

    # =========================================================================
    # TRANSITION EXECUTION
    # =========================================================================

    def _transition(self, old: Phase, new: Phase, metrics: Dict) -> None:
        """Execute phase transition: update state, snap params, announce."""
        duration = time.time() - self.phase_entered_at
        self._phase_history.append((old.value, round(duration)))
        self._phase_history = self._phase_history[-8:]  # keep last 8 transitions
        print(
            f"[Conductor] {old.value} -> {new.value}  ({duration:.0f}s in {old.value})"
        )
        self.phase = new
        self.phase_entered_at = time.time()
        self._hold_timers.clear()

        # Notify EEG engine so the respiratory hot window adapts per Sánchez Corzo (Bible Ch.4 §4.6 §6.2)
        if self._eeg_engine is not None and hasattr(
            self._eeg_engine, "notify_conductor_phase"
        ):
            self._eeg_engine.notify_conductor_phase(new.value)

        # Snapshot current params before FRAC_EMERGE for ramp-back
        if new == Phase.FRAC_EMERGE:
            live = self._read_live()
            self.pre_emerge_params = {
                "spiral_chaos": live.get("spiral_chaos", 0.4),
                "trail_decay": live.get("trail_decay", 0.6),
            }

        # Bible Ch.1 §8 — Hardware output channel phase transitions
        self._check_hardware()
        hw_params = self._hardware_params(new, 0.0)
        if hw_params:
            patch_live(hw_params)

        if new == Phase.CALIBRATION:
            patch_live(
                {
                    "beat_frequency": 0,
                    "spiral_chaos": 0.15,
                    "trail_decay": 0.0,
                    "veil_mode": "drift",
                    "shadow_opacity_target": 0,
                    "sr_noise_level": 0.0,
                    "conductor_phase": new.value,
                }
            )
            self._say(
                "Let's get settled. Take a breath and adjust the headband until it feels snug."
            )

        elif new == Phase.INDUCTION:
            # FreqLeader no longer writes beat_frequency on activation, so the
            # conductor just anchors to wherever the beat slider currently is.
            # If IAF was calibrated this session, use it; otherwise follow the beat.
            freq = self.iaf or float(self._read_live().get("beat_frequency") or 10.0)
            self.current_target_freq = freq
            ind_patch = {
                "beat_frequency": freq,
                "beat_type": "binaural",
                "spiral_chaos": 0.2,
                "trail_decay": 0.3,
                "veil_mode": "scroll",
                "shadow_opacity_target": 20,
                "sr_noise_level": 0.0,
                "conductor_phase": new.value,
                "freq_lead_enabled": True,
                "freq_lead_mode": "meet",
                "freq_lead_target_hz": freq,
                "tts_pool_style": {"rate": "+0%"},
                "tts_duck_ms": 0,
            }
            # Bible Ch.1 §15.5 — Deploy conditioned anchor during induction
            if self._haptic_connected:
                ind_patch["haptic_pattern"] = "conditioned_anchor"
            patch_live(ind_patch)
            self._say("Entrainment beginning. Let your breath settle.")

        elif new == Phase.DEEPENING:
            patch_live(
                {
                    "spiral_chaos": 0.25,
                    "trail_decay": 0.4,
                    "veil_mode": "converge",
                    "spiral_style": "liminal",
                    "conductor_phase": new.value,
                    "freq_lead_enabled": True,
                    "freq_lead_mode": "lead",
                    "tts_pool_style": {"rate": "-10%"},
                }
            )

        elif new == Phase.MAINTENANCE:
            patch_live(
                {
                    "veil_mode": "tunnel",
                    "spiral_style": "liminal",
                    "shadow_opacity_target": 15,
                    "conductor_phase": new.value,
                    "freq_lead_enabled": True,
                    "freq_lead_mode": "sustain",
                    "freq_lead_target_hz": self.current_target_freq or 6.0,
                    "tts_pool_style": {"rate": "-20%"},
                }
            )

        elif new == Phase.FRAC_EMERGE:
            # SNAP — perceptual jolt
            patch_live(
                {
                    "spiral_chaos": 0.05,
                    "trail_decay": 0.0,
                    "sr_noise_level": 0.0,
                    "shadow_opacity_target": 25,
                    "conductor_phase": new.value,
                    "freq_lead_enabled": True,
                    "freq_lead_mode": "meet",
                    "freq_lead_target_hz": self.iaf or 10.0,
                    "tts_pool_style": {"rate": "+0%"},
                    "tts_duck_ms": 0,
                }
            )
            self._say("Rising now. Notice the shift.")

        elif new == Phase.FRAC_EMERGE_HOLD:
            patch_live(
                {
                    "conductor_phase": new.value,
                }
            )

        elif new == Phase.FRAC_REDROP:
            patch_live(
                {
                    "conductor_phase": new.value,
                    "freq_lead_enabled": True,
                    "freq_lead_mode": "lead",
                    "tts_pool_style": {"rate": "-35%"},
                    "tts_duck_ms": 120,
                }
            )
            self._say("Settling back down.")

        elif new == Phase.SLEEP_APPROACH:
            patch_live(
                {
                    "veil_mode": "drift",
                    "spiral_style": "liminal",
                    "conductor_phase": new.value,
                    "freq_lead_enabled": True,
                    "freq_lead_mode": "lead",
                    "breath_mod": True,
                    "breath_rate": 0.07,
                    "imu_motion_threshold_override": 0.02,  # Bible Ch.2 §2.9 §5.4
                }
            )
            self._enter_sleep_approach()

        elif new == Phase.SLEEP_ONSET:
            patch_live(
                {
                    "shadow_opacity_target": 0,
                    "sr_noise_level": 0.0,
                    "tts_enabled": False,
                    "conductor_phase": new.value,
                    "freq_lead_enabled": False,
                    "imu_motion_threshold_override": 0.02,  # Bible Ch.2 §2.9 §5.4
                }
            )
            self._enter_sleep_onset()

        elif new == Phase.SLEEP_MAINTAIN:
            patch_live(
                {
                    "conductor_phase": new.value,
                    "tts_enabled": False,
                    "imu_motion_threshold_override": 0.02,  # Bible Ch.2 §2.9 §5.4
                }
            )
            self._enter_sleep_maintain()

        elif new == Phase.SLEEP_TRAINING:
            patch_live(
                {
                    "conductor_phase": new.value,
                    "imu_motion_threshold_override": 0.02,  # Bible Ch.2 §2.9 §5.4
                }
            )
            self._enter_sleep_training()

        elif new == Phase.SLEEP_WAKE:
            # Gentle restore: fade in noise, leave binaural at low level
            patch_live(
                {
                    "conductor_phase": new.value,
                    "sleep_sw_enhance_enabled": False,
                    "sleep_alpha_disrupt_enabled": False,
                    "gain_mode": "normal",
                    "imu_motion_threshold_override": None,  # restore default (Bible Ch.2 §2.9 §5.4)
                }
            )
            # Compile sleep session metrics for scoring
            live_sw = self._read_live()
            swa = live_sw.get("sleep_swa_enhancement_ratio", 0.0)
            total_sleep = sum(self._sleep_time_in_stage.values())
            patch_live(
                {
                    "sleep_efficiency": round(
                        total_sleep / max(1.0, time.time() - self.session_start), 4
                    ),
                    "time_in_n1_s": round(self._sleep_time_in_stage.get("N1", 0.0), 1),
                    "time_in_n2_s": round(self._sleep_time_in_stage.get("N2", 0.0), 1),
                    "time_in_n3_s": round(self._sleep_time_in_stage.get("N3", 0.0), 1),
                    "time_in_rem_s": round(
                        self._sleep_time_in_stage.get("REM", 0.0), 1
                    ),
                    "swa_enhancement_ratio": swa,
                    "sw_enhance_bursts": self._swe.burst_count if self._swe else 0,
                    "alpha_antiphase_bursts": self._alpha_disrupt_burst_count,
                }
            )
            self._say("Rest well. Session complete.")

        elif new == Phase.EDISON_PREPARATION:
            patch_live(
                {
                    "beat_frequency": 3.0,
                    "beat_type": "binaural",
                    "carrier_frequency": 200,
                    "volume": 15,
                    "bg_mode": "none",
                    "spiral_chaos": 0.0,
                    "trail_decay": 0.0,
                    "veil_mode": "null",
                    "shadow_opacity_target": 0,
                    "sr_noise_level": 0.0,
                    "noise_color": "off",
                    "conductor_phase": new.value,
                    "freq_lead_enabled": False,
                }
            )
            self._say(
                "Edison Mode active. Get comfortable. When you're ready to begin, "
                "press the Ready button or type 'ready'."
            )

        elif new == Phase.EDISON_SEED:
            patch_live(
                {
                    "beat_frequency": 4.0,
                    "volume": 15,
                    "conductor_phase": new.value,
                }
            )

        elif new == Phase.EDISON_MONITORING:
            patch_live(
                {
                    "conductor_phase": new.value,
                    "tts_enabled": False,
                }
            )

        elif new == Phase.EDISON_N1_HOLD:
            patch_live(
                {
                    "conductor_phase": new.value,
                }
            )
            print(f"[Conductor] Edison N1 hold started")

        elif new == Phase.EDISON_CAPTURE:
            patch_live(
                {
                    "beat_frequency": 8.0,
                    "volume": 30,
                    "shadow_opacity_target": 40,
                    "conductor_phase": new.value,
                    "tts_enabled": True,
                }
            )

        elif new == Phase.EDISON_CYCLE_END:
            patch_live(
                {
                    "beat_frequency": 3.0,
                    "volume": 15,
                    "shadow_opacity_target": 0,
                    "tts_enabled": True,
                    "conductor_phase": new.value,
                }
            )

        elif new == Phase.SSILD_PRE_TECHNIQUE:
            patch_live(
                {
                    "beat_frequency": 8.0,
                    "beat_type": "binaural",
                    "volume": 25,
                    "bg_mode": "none",
                    "spiral_chaos": 0.05,
                    "trail_decay": 0.0,
                    "veil_mode": "drift",
                    "shadow_opacity_target": 0,
                    "sr_noise_level": 0.0,
                    "noise_color": "brown",
                    "noise_volume": 10,
                    "conductor_phase": new.value,
                    "freq_lead_enabled": False,
                }
            )

        elif new == Phase.SSILD_QUICK_CYCLES:
            patch_live(
                {
                    "beat_frequency": 6.0,
                    "volume": 20,
                    "conductor_phase": new.value,
                }
            )

        elif new == Phase.SSILD_SLOW_CYCLES:
            patch_live(
                {
                    "beat_frequency": 5.5,
                    "volume": 15,
                    "veil_mode": "converge",
                    "shadow_opacity_target": 10,
                    "conductor_phase": new.value,
                }
            )

        elif new == Phase.SSILD_POST_TECHNIQUE:
            patch_live(
                {
                    "beat_frequency": 4.0,
                    "volume": 10,
                    "veil_mode": "null",
                    "shadow_opacity_target": 0,
                    "tts_enabled": False,
                    "conductor_phase": new.value,
                    "freq_lead_enabled": False,
                }
            )

        elif new == Phase.SSILD_REM_MONITORING:
            patch_live(
                {
                    "volume": 5,
                    "conductor_phase": new.value,
                }
            )

        elif new == Phase.SSILD_DREAM_JOURNAL:
            patch_live(
                {
                    "beat_frequency": 10.0,
                    "volume": 30,
                    "tts_enabled": True,
                    "conductor_phase": new.value,
                }
            )

        elif new == Phase.SESSION_END:
            patch_live(
                {
                    "conductor_phase": new.value,
                    "freq_lead_enabled": False,
                    "agent_sleep_plan": {},  # clear stale plan before next session
                }
            )
            if self.session_type != "sleep":
                self._say("Session complete. Take a breath before you move.")
            # Persist HTW aggregate metrics for session scoring (Bible Ch.9 §9.1)
            if self._htw_count > 0:
                success_rate = round(self._htw_success_count / self._htw_count, 3)
                try:
                    from content_tools.somna_db import update_session_htw_metrics

                    update_session_htw_metrics(
                        self.session_id,
                        self._htw_count,
                        self._htw_total_duration_s,
                        success_rate,
                    )
                except Exception:
                    pass
            # Write post-sleep debrief for agent (Bible Ch.9 §9.1)
            if self.session_type == "sleep":
                try:
                    from content_tools.somna_db import (
                        get_sleep_stage_log_summary,
                        get_tmr_replay_summary,
                    )

                    stage_dist = get_sleep_stage_log_summary(self.session_id)
                    tmr_replays = get_tmr_replay_summary(self.session_id)
                    elapsed_sleep = sum(
                        stage_dist.get(s, 0) for s in ("N1", "N2", "N3", "REM")
                    )
                    # Recommended focus: pool with fewest replays so far
                    _pools = [
                        "IDENTITY",
                        "RELEASE",
                        "POTENTIAL",
                        "SOMATIC",
                        "PURPOSE",
                        "TRANSITION",
                    ]
                    focus = min(_pools, key=lambda p: tmr_replays.get(p, 0))
                    patch_live(
                        {
                            "pending_sleep_debrief": {
                                "session_id": self.session_id,
                                "ended_at": time.time(),
                                "elapsed_sleep_s": elapsed_sleep,
                                "stage_distribution": stage_dist,
                                "htw_count": self._htw_count,
                                "htw_success_count": self._htw_success_count,
                                "htw_total_duration_s": round(
                                    self._htw_total_duration_s, 1
                                ),
                                "tmr_replay_count": sum(tmr_replays.values()),
                                "recommended_focus_pool": focus,
                            }
                        }
                    )
                except Exception:
                    pass

            # Edison Mode: persist captures to DB (Bible Ch.7 §29)
            if self._is_edison and self._edison is not None:
                try:
                    from content_tools.somna_db import log_edison_capture

                    for cap in self._edison.finalize():
                        log_edison_capture(
                            session_id=self.session_id,
                            capture_index=cap.get("capture_index", 0),
                            n1_onset_ts=cap.get("n1_onset_ts", 0),
                            n1_duration_s=cap.get("n1_duration_s", 0),
                            alpha_theta_ratio=cap.get("alpha_theta_ratio", 0),
                            seed_topic=cap.get("seed_topic", ""),
                            user_report=cap.get("user_report", ""),
                            eeg_snapshot=json.dumps(cap.get("eeg_snapshot", {})),
                            wake_cue_type=cap.get("wake_cue_type", "normal"),
                            cycle_complete_ts=cap.get("cycle_complete_ts", 0),
                        )
                    print(
                        f"[Conductor] Edison Mode: {len(self._edison.captures)} captures saved"
                    )
                except Exception as e:
                    print(f"[Conductor] Edison capture DB error: {e}")

            # SSILD: persist session journal to DB (Bible Ch.7 §§30-31)
            if self._is_ssild and self._ssild is not None:
                try:
                    from content_tools.somna_db import log_ssild_session

                    summary = self._ssild.finalize()
                    log_ssild_session(
                        session_id=self.session_id,
                        quick_cycles_completed=summary["quick_cycles_completed"],
                        slow_cycles_completed=summary["slow_cycles_completed"],
                        rem_periods_detected=summary["rem_periods_detected"],
                        tlr_cues_delivered=summary["tlr_cues_delivered"],
                        lucidity_detected=summary["lucidity_detected"],
                        user_reported_lucidity="",
                        user_reported_dream="",
                        user_reported_cue_awareness="",
                        eeg_rem_summary="{}",
                    )
                    print(
                        f"[Conductor] SSILD session saved: "
                        f"{summary['rem_periods_detected']} REM periods, "
                        f"{summary['tlr_cues_delivered']} TLR cues"
                    )
                except Exception as e:
                    print(f"[Conductor] SSILD DB error: {e}")

            self._flush_log()

    # =========================================================================
    # CONFLICT RESOLUTION (Section 4)
    # =========================================================================

    def _resolve_conflicts(self, m: Dict) -> Dict[str, Any]:
        """Per-phase conflict resolution.  Returns adjustment hints dict."""
        adj: Dict[str, Any] = {}
        phase = self.phase

        if phase == Phase.DEEPENING:
            ts = m.get("trance_score")
            assr = m.get("assr")
            if (
                ts
                and ts > self._ct("trance_frac_eligible", 0.5)
                and assr
                and assr["strength"] < self._ct("assr_transition", 0.3)
            ):
                adj["hold_frequency"] = True
            faa = m.get("faa")
            if faa and faa["value"] < 0:
                sustained = self._faa_sustained_seconds(faa)
                if sustained > 60:
                    adj["consider_fractionation"] = True

        elif phase == Phase.MAINTENANCE:
            faa = m.get("faa")
            if faa and faa["value"] < 0:
                sustained = self._faa_sustained_seconds(faa)
                if sustained > 30:
                    adj["suppress_affirmations"] = True
            ts = m.get("trance_score")
            if ts is not None:
                rate = self._trance_score_rate()
                if rate is not None:
                    if rate < -0.1:
                        adj["consider_fractionation"] = True
                    elif rate < -0.05:
                        adj["nudge_frequency"] = -0.05

        elif phase == Phase.SLEEP_APPROACH:
            adj["assr_decline_expected"] = True

        return adj

    # =========================================================================
    # PARAMETER COMPUTATION
    # =========================================================================

    # Bible Ch.10 §10.2 §5.2 — target AM modulation depth per phase.
    # The audio engine interpolates toward this value at ~1 unit / 5 s.
    _AM_DEPTH_BY_PHASE: Dict["Phase", float] = {}  # populated below class body

    def _compute_parameters(
        self, m: Dict, adj: Dict, phase_dur: float
    ) -> Dict[str, Any]:
        """Compute parameter updates for the current phase tick."""
        params: Dict[str, Any] = {}
        phase = self.phase

        # AM depth: write target on every tick so audio engine can interpolate.
        am_target = Conductor._AM_DEPTH_BY_PHASE.get(phase)
        if am_target is not None:
            params["am_depth"] = am_target

        if phase == Phase.DEEPENING:
            if not adj.get("hold_frequency"):
                target = m.get("freq_lead_current")
                if target:
                    params["beat_frequency"] = round(target, 2)
                    self.current_target_freq = target
            progress = min(phase_dur / 300, 1.0)
            params["spiral_chaos"] = round(0.25 + 0.15 * progress, 3)
            params["trail_decay"] = round(0.4 + 0.2 * progress, 3)

        elif phase == Phase.FRAC_REDROP:
            progress = min(phase_dur / 120, 1.0)
            pre = self.pre_emerge_params
            params["spiral_chaos"] = round(
                0.05 + (pre.get("spiral_chaos", 0.5) - 0.05) * progress, 3
            )
            params["trail_decay"] = round(
                0.0 + (pre.get("trail_decay", 0.7) - 0.0) * progress, 3
            )
            params["shadow_opacity_target"] = max(15, int(25 - 10 * progress))
            target = m.get("freq_lead_current")
            if target:
                params["beat_frequency"] = round(target, 2)
                self.current_target_freq = target

        elif phase == Phase.MAINTENANCE:
            if adj.get("nudge_frequency"):
                current = self.current_target_freq or 6.0
                new_f = max(4.0, current + adj["nudge_frequency"])
                params["beat_frequency"] = round(new_f, 2)
                self.current_target_freq = new_f
            # Agent can suggest a target floor frequency based on historical data.
            floor_hint = self._hints.get("target_floor_hz")
            if floor_hint and not adj.get("nudge_frequency"):
                target = max(3.5, min(8.0, float(floor_hint)))
                current = self.current_target_freq or 6.0
                # Nudge toward the hint 0.1 Hz per tick to avoid jarring jumps
                if abs(current - target) > 0.05:
                    step = 0.1 * (1 if target > current else -1)
                    new_f = round(current + step, 2)
                    params["beat_frequency"] = new_f
                    self.current_target_freq = new_f

        elif phase == Phase.SLEEP_APPROACH:
            target = m.get("freq_lead_current")
            if target:
                params["beat_frequency"] = round(target, 2)
            progress = min(phase_dur / 600, 1.0)
            params["shadow_opacity_target"] = max(0, int(12 - 4 * progress))
            params["sr_noise_level"] = round(max(0.0, 0.05 * (1.0 - progress)), 3)

        hw = self._hardware_params(self.phase, phase_dur)
        params.update(hw)

        # ── EEG-reactive visual mapping (Reese spec §10) ───────────────────
        # Map trance_score to post-processing parameters so visuals breathe
        # with brain state. Only active during waking phases; sleep phases
        # manage their own visual parameters separately.
        if self.phase in (
            Phase.DEEPENING,
            Phase.MAINTENANCE,
            Phase.FRAC_REDROP,
            Phase.FRAC_EMERGE_HOLD,
            Phase.INDUCTION,
        ):
            ts = m.get("trance_score")
            if ts is not None:
                ts = max(0.0, min(1.0, float(ts)))
                # Bloom: 0.1 at shallow → 0.8 at deep
                params["pp_bloom_intensity"] = round(0.1 + 0.7 * ts, 3)
                # Film grain: 0.01 at shallow → 0.06 at deep
                params["pp_film_grain"] = round(0.01 + 0.05 * ts, 4)
                # Chromatic aberration: 0.001 at shallow → 0.004 at deep
                params["pp_ca_strength"] = round(0.001 + 0.003 * ts, 4)
                # Entrainment flicker: 0.0 at shallow → 0.10 at deep
                # Above 0.10 is perceptually too aggressive for sustained use
                if self.phase in (Phase.MAINTENANCE, Phase.DEEPENING):
                    params["entrainment_strength"] = round(0.10 * ts, 3)
                elif self.phase == Phase.FRAC_REDROP:
                    # Ramp entrainment back up during re-drop
                    progress = min(phase_dur / 120, 1.0)
                    params["entrainment_strength"] = round(0.10 * ts * progress, 3)

        return params

    def _check_hardware(self) -> None:
        live = self._read_live()
        connected = set(live.get("hardware_channels_connected") or [])
        self._haptic_connected = "haptic" in connected
        self._tavns_connected = "tavns" in connected
        self._hardware_checked_this_tick = True

    def _hardware_params(self, phase: Phase, phase_dur: float) -> Dict[str, Any]:
        if not self._hardware_checked_this_tick:
            self._check_hardware()

        params: Dict[str, Any] = {}

        if self._haptic_connected:
            profile = HAPTIC_PHASE_PROFILES.get(phase)
            if profile:
                target = profile["intensity"]
                if phase == Phase.DEEPENING:
                    progress = min(phase_dur / 300, 1.0)
                    target = int(15 + 30 * progress)
                elif phase == Phase.FRAC_REDROP:
                    progress = min(phase_dur / 120, 1.0)
                    target = int(5 + 25 * progress)
                params["haptic_intensity"] = target
                params["haptic_pattern"] = profile["pattern"]

        if self._tavns_connected:
            profile = TAVNS_PHASE_PROFILES.get(phase)
            if profile:
                target = profile["intensity"]
                if phase == Phase.DEEPENING:
                    progress = min(phase_dur / 300, 1.0)
                    target = int(10 + 15 * progress)
                elif phase == Phase.FRAC_REDROP:
                    progress = min(phase_dur / 120, 1.0)
                    target = int(5 + 15 * progress)
                params["tavns_intensity"] = target
                params["tavns_waveform"] = profile["waveform"]

        return params

    def _should_deliver_affirmation(self, m: Dict, adj: Dict) -> bool:
        if self.phase not in (Phase.MAINTENANCE, Phase.DEEPENING, Phase.FRAC_REDROP):
            return False
        if adj.get("suppress_affirmations"):
            return False
        faa = m.get("faa")
        if faa is None:
            return False
        if faa["value"] <= 0:
            return False
        # Recon lockout: skip TMR encoding for retrieve phrases currently in the
        # lockout window.  recon_locked_phrases is written by the agent's _recon_tick
        # when entering lockout and cleared on completion.  Blocking TMR encoding here
        # prevents the old trace from being reinforced during consolidation sleep while
        # the reconsolidation window is still open.
        try:
            live = self._read_live()
            locked = live.get("recon_locked_phrases") or []
            if locked:
                phrase = live.get("current_phrase") or ""
                if phrase and phrase in locked:
                    return False
        except Exception:
            pass
        return True

    def _deliver_affirmation_with_tmr(self) -> None:
        """Log the most recently shown affirmation as a TMR encoding event.

        Affirmation delivery is driven entirely by the display layer's own
        DeliveryGate — the Conductor does not need to trigger it.  This method
        reads current_phrase (written to live_control.json by visual_display.py
        on each new phrase flash) and fires the matching TMR audio cue so the
        association between cue and content is recorded in somna_db.

        When TMR is unavailable the method is a no-op; affirmation delivery
        continues exactly as before via the display layer's own timer/gate.
        """
        if self._tmr is None:
            return

        live = self._read_live()
        phrase = live.get("current_phrase", "") or ""
        label = live.get("timeline_label", "") or ""

        if not phrase:
            return

        try:
            from session.tmr_cue_manager import CueManager, pool_for_label

            pool = pool_for_label(label)
            content_hash = CueManager.hash_affirmation(phrase)

            # Fire the audio cue immediately — the phrase is already on screen,
            # so the cue post-dates the flash by up to one Conductor tick (≤30 s).
            # For cross-session sleep replay the precise within-session timing is
            # not critical; what matters is that the same cue always maps to the
            # same phrase content.
            patch_live(
                {
                    "tmr_cue_cmd": {
                        "pool": pool,
                        "content_hash": content_hash,
                        "gain": 0.12,
                        "ts": time.time(),
                    },
                }
            )

            self._tmr.on_affirmation_encoded(pool, content_hash, phrase)

            # Bible Ch.1 §15.5 — Conditioned haptic anchor.
            # Fire a 500 ms vibration at 60% intensity when trance is deep
            # (score > 0.75) and hardware is connected. The same pattern
            # deployed during future INDUCTION phases acts as a conditioned
            # stimulus that accelerates depth onset via Pavlovian association.
            if self._haptic_connected:
                ts = self._last_metrics.get("trance_score")
                if ts is not None and ts > 0.75:
                    patch_live(
                        {
                            "tmr_haptic_cue": {
                                "intensity": 60.0,
                                "duration_s": 0.5,
                                "ts": time.time(),
                                "anchor": True,
                            }
                        }
                    )

        except Exception:
            pass

    # =========================================================================
    # PHASE SPEECH
    # =========================================================================

    def _get_phase_speech(self, m: Dict, adj: Dict, phase_dur: float) -> Optional[str]:
        """Return a speech string for this tick, or None.

        Verbosity levels:
          CALIBRATION   — HIGH   (periodic guidance every ~30 s)
          INDUCTION     — MODERATE (somatic anchors every ~60 s)
          DEEPENING     — LOW    (minimal)
          MAINTENANCE   — MINIMAL (affirmations via deliver_affirmation only)
          SLEEP_ONSET   — SILENT
          SESSION_END   — handled in _transition
        """
        if self.phase in (
            Phase.SLEEP_ONSET,
            Phase.SLEEP_MAINTAIN,
            Phase.SLEEP_TRAINING,
            Phase.SLEEP_WAKE,
            Phase.SESSION_END,
            Phase.MAINTENANCE,
        ):
            return None

        if self.phase == Phase.CALIBRATION:
            # Offer fit guidance periodically
            if 25 <= phase_dur <= 35:
                return "Still settling. Notice the sound and let your body weight drop."
            return None

        if self.phase == Phase.INDUCTION:
            # Somatic anchors every ~90 s
            if 85 <= phase_dur <= 100:
                return (
                    "Notice where your body makes contact with the surface beneath you."
                )
            if 175 <= phase_dur <= 190:
                return "Each breath a little slower, a little heavier."
            return None

        # SQI failure speech is handled separately
        if adj.get("hold_frequency") and phase_dur < 15:
            return None  # don't narrate every hold

        return None

    # =========================================================================
    # SQI FAILURE HANDLING
    # =========================================================================

    def _handle_sqi_failure(self, m: Dict, phase_dur: float) -> None:
        """Freeze all parameters and announce degraded signal."""
        if not self._degraded:
            self._degraded = True
            self._degraded_since = time.time()
            self._say("Signal lost — holding position. Check headband contact.")
            print("[Conductor] Entering degraded mode — SQI NONE all channels")

            # Safety-critical: halt all phase-locked stimulation immediately.
            # Wrong-phase stimulation during signal uncertainty is actively harmful.
            patch_live({"eeg_signal_lost": True})
            if self._tmr is not None:
                self._tmr.eeg_loss_shutdown()
            if self._swe is not None:
                patch_live(
                    {
                        "sleep_alpha_disrupt_enabled": False,
                        "sleep_sw_enhance_enabled": False,
                    }
                )

        # After 60 s of sustained NONE: switch to timer-only mode
        degraded_dur = time.time() - (self._degraded_since or time.time())
        if degraded_dur > 60 and not getattr(self, "_timer_mode", False):
            self._enter_degraded_mode(m)

    def _enter_degraded_mode(self, m: Dict) -> None:
        """Switch to timer-based progression for remainder of session."""
        if getattr(self, "_timer_mode", False):
            return
        self._timer_mode = True
        print("[Conductor] Activating timer-based fallback")
        self._log_decision(
            m,
            "TIMER_FALLBACK",
            "EEG unavailable — switching to timer-based progression",
        )

    # =========================================================================
    # CALIBRATION HELPERS
    # =========================================================================

    def _ct(self, metric: str, fallback: float) -> float:
        """Shorthand: calibrated threshold or population fallback."""
        if self.cal is not None:
            return self.cal.get_threshold(metric, fallback)
        return fallback

    def _can_transition_to(self, target_phase: "Phase") -> bool:
        """True if CalibrationManager permits entering target_phase.

        During the first 10 sessions the conductor is progressively unlocked
        so early sessions capture clean baseline and subsystem data before
        full fractionation is exercised.  After calibration_complete this
        always returns True.
        """
        if self.cal is None or self.cal.calibration_complete:
            return True
        return self.cal.can_transition_to(target_phase.value.upper())

    # SLEEP HELPER METHODS (Bible Ch.7 §7.1)
    # =========================================================================

    def _sample_sleep_stage(self) -> str:
        """Read current sleep stage and append to rolling history. Call once per tick."""
        live = self._read_live()
        stage = live.get("eeg_sleep_stage", "WAKE")
        self._stage_history.append(stage)
        if len(self._stage_history) > 30:
            self._stage_history.pop(0)
        return stage

    def _consecutive_stage(self, target: str, count: int) -> bool:
        """Return True if the last `count` history entries all equal `target`.

        History is populated by _sample_sleep_stage(), called once per tick.
        """
        recent = (
            self._stage_history[-count:] if len(self._stage_history) >= count else []
        )
        return len(recent) == count and all(s == target for s in recent)

    def _detect_sleep_fork(self) -> bool:
        """Detect when trance trajectory is heading toward sleep (Bible Ch.7 §7.1 §7.4).

        Fork criteria (2-of-3 convergent evidence, mirroring Bible Ch.2 §2.8's rule):
          1. Spectral slope steeper than trance-maintenance band (< −2.3)
          2. Interhemispheric frontal alpha coherence below 0.4
          3. Beta envelope correlation below 0.3

        Only triggers for sleep/general session types and when the user has not
        interacted (moved a slider) in the last 60 seconds.
        """
        if self.session_type not in ("sleep", "general"):
            return False
        live = self._read_live()
        # Abort fork detection if the user touched a slider recently.
        # timeline_locked_params being non-empty is a reliable proxy — the
        # timeline runner only populates it when it detects a user-written value.
        if live.get("timeline_locked_params"):
            return False

        slope = live.get("eeg_spectral_slope", -1.5)
        coherence = live.get("eeg_coherence_frontal_alpha", 0.5)
        beta_corr = live.get("eeg_beta_env_corr", 0.5)

        votes = 0
        if slope < -2.3:
            votes += 1
        if coherence < 0.4:
            votes += 1
        if beta_corr < 0.3:
            votes += 1

        # Bible Ch.2 §2.9 §5.3 — head nod as behavioral N1 cue.
        # Write sleep_onset_behavioral_cue so the Conductor tick can act on it
        # even before EEG staging confirms N1.
        if (
            live.get("imu_head_nod_detected", False)
            and live.get("eeg_sleep_stage", "WAKE") == "WAKE"
        ):
            patch_live({"sleep_onset_behavioral_cue": True})

        return votes >= 2

    def _accumulate_sleep_time(self) -> None:
        """Accumulate time-in-stage metrics for sleep session scoring.
        Uses the last entry in _stage_history (set by _sample_sleep_stage this tick).
        """
        stage = self._stage_history[-1] if self._stage_history else "WAKE"
        now = time.time()
        if self._sleep_last_stage_ts > 0 and stage in self._sleep_time_in_stage:
            self._sleep_time_in_stage[stage] += now - self._sleep_last_stage_ts
        self._sleep_last_stage_ts = now
        n2n3 = self._sleep_time_in_stage.get("N2", 0.0) + self._sleep_time_in_stage.get(
            "N3", 0.0
        )
        patch_live({"eeg_n2_n3_banked_s": round(n2n3, 1)})

    def _enter_sleep_approach(self) -> None:
        """Configure phase-cascade for alpha anti-phase disruption (Bressler 2024)."""
        self._sleep_approach_entered_at = time.time()
        self._alpha_disrupt_last_alpha = None
        patch_live(
            {
                # Alpha anti-phase protocol: retarget PhaseTracker to alpha trough
                "sleep_alpha_disrupt_enabled": True,
                "sleep_alpha_disrupt_volume": 15,
                "sleep_alpha_disrupt_duration_ms": 50,
                # Visual fadedown — safety: no visual stimuli during sleep approach
                "spiral_opacity": 0,
                "veil_opacity": 0,
                "center_flash_on_time": 0,
                # Gain manifold: sleep approach profile
                "gain_mode": "sleep_approach",
            }
        )

    def _enter_sleep_onset(self) -> None:
        """Configure phase-cascade for slow-wave enhancement (Bible Ch.7 §7.1 §6)."""
        # Log sleep onset latency
        if self._sleep_approach_entered_at > 0:
            self._sleep_onset_latency_s = time.time() - self._sleep_approach_entered_at
            patch_live({"sleep_onset_latency_s": round(self._sleep_onset_latency_s, 1)})
        patch_live(
            {
                # PhaseTracker retargeted to delta up-state detection
                "sleep_alpha_disrupt_enabled": False,
                "sleep_sw_enhance_enabled": True,
                "sleep_sw_enhance_volume": 12,
                "sleep_sw_enhance_isi_min_ms": 800,
                # Audio: delta binaural ramp
                "beat_frequency": 1.0,
                "carrier_frequency": 180,
                "volume": 30,
                "noise_color": "pink",
                "noise_volume": 25,
                # Gain manifold: sleep onset profile
                "gain_mode": "sleep_onset",
            }
        )

    def _enter_sleep_maintain(self) -> None:
        """Enter sustained sleep maintenance with phase-locked SWS enhancement."""
        self._sleep_last_stage_ts = time.time()
        patch_live(
            {
                "gain_mode": "sleep_maintain",
                "tts_enabled": False,
            }
        )

    # ── HTW helpers (Bible Ch.9 §9.1) ─────────────────────────────────────────────────

    def _htw_eligible(self) -> bool:
        """Return True when conditions allow intercepting the next N1 epoch."""
        live_n = self._read_live()
        override = live_n.get("eeg_n2_n3_banked_s")
        if override is not None:
            n2n3_s = float(override)
        else:
            n2n3_s = self._sleep_time_in_stage.get(
                "N2", 0.0
            ) + self._sleep_time_in_stage.get("N3", 0.0)
        if n2n3_s < 3600.0:
            return False
        if time.time() - self._htw_last_ts < 5400.0:
            return False
        if self._htw_count >= 3:
            return False
        live = self._read_live()
        if live.get("eeg_signal_lost", False):
            return False
        # Require content — either agent sleep plan or TMR registry
        if live.get("agent_sleep_plan"):
            return True
        try:
            from content_tools.somna_db import get_tmr_cue_registry

            return bool(get_tmr_cue_registry(self.session_id))
        except Exception:
            return False

    def _select_training_phrases(self) -> list:
        """Return up to 6 phrases for the next HTW window."""
        live = self._read_live()
        plan = live.get("agent_sleep_plan")
        if isinstance(plan, dict):
            phrases = plan.get("phrases") or []
            if phrases:
                return list(phrases)[:6]
        try:
            from content_tools.somna_db import get_tmr_cue_registry

            rows = get_tmr_cue_registry(self.session_id)
            rows.sort(key=lambda r: r.get("encoding_count", 0))
            phrases = [r["affirmation_text"] for r in rows if r.get("affirmation_text")]
            if phrases:
                return phrases[:6]
        except Exception:
            pass
        pool = live.get("affirmations_pool") or []
        return list(pool)[:6]

    def _presynth_training_phrases(self) -> None:
        """Write tts_presynth_phrases so the TTS worker warms the buffer early."""
        phrases = self._select_training_phrases()
        if not phrases:
            return
        patch_live(
            {
                "tts_presynth_phrases": phrases,
                "tts_pool_style": {"pitch": "-10Hz", "rate": "-30%"},
            }
        )
        self._htw_phrases_presynth = True

    def _enter_sleep_training(self) -> None:
        """Transition into SLEEP_TRAINING: override audio+visual for HTW delivery."""
        live = self._read_live()
        phrases = self._select_training_phrases()

        # Save pre-HTW state so we can restore on exit
        self._pre_htw_state = {
            "affirmations_pool": live.get("affirmations_pool"),
            "tts_enabled": live.get("tts_enabled", False),
            "tts_volume": live.get("tts_volume", 65),
            "tts_subliminal": live.get("tts_subliminal", False),
            "tts_subliminal_vol": live.get("tts_subliminal_vol", 0),
            "center_flash_on_time": live.get("center_flash_on_time", 120),
            "center_flash_off_time": live.get("center_flash_off_time", 80),
            "center_flash_sync_to_beat": live.get("center_flash_sync_to_beat", True),
            "beat_frequency": live.get("beat_frequency", 10.0),
        }

        self._htw_start_ts = time.time()
        self._htw_alpha_surge_ts = None

        patch_live(
            {
                "affirmations_pool": phrases,
                "tts_enabled": True,
                "tts_volume": 6,
                "tts_subliminal": True,
                "tts_subliminal_vol": 14,
                "tts_use_presynth": True,
                "tts_pool_style": {"pitch": "-10Hz", "rate": "-30%"},
                "beat_frequency": 5.5,
                "gain_mode": "sleep_training",
                "center_flash_on_time": 4000,
                "center_flash_off_time": 8000,
                "center_flash_sync_to_beat": False,
                # Pause TMR replay while HTW is active (Bible Ch.7 §7.5 coordination)
                "tmr_lockout_until": time.time() + 360.0,
            }
        )

    def _exit_sleep_training(self, reason: str, next_phase: "Phase") -> "Phase":
        """Restore pre-HTW state, log the window, and return the next phase."""
        duration_s = time.time() - self._htw_start_ts
        stage_at_exit = self._stage_history[-1] if self._stage_history else "UNKNOWN"

        restore = dict(self._pre_htw_state)
        restore.update(
            {
                "tts_use_presynth": False,
                "tts_presynth_phrases": [],
                "tts_pool_style": {},
                "gain_mode": "sleep_maintain",
            }
        )
        # Drop None values (keys that were absent before HTW)
        restore = {k: v for k, v in restore.items() if v is not None}
        patch_live(restore)

        self._htw_count += 1
        self._htw_total_duration_s += duration_s
        if reason == "n2_detected":
            self._htw_success_count += 1
        self._htw_last_ts = time.time()
        self._htw_phrases_presynth = False

        try:
            from content_tools.somna_db import log_sleep_training_window

            live_ex = self._read_live()
            plan = live_ex.get("agent_sleep_plan") or {}
            pool = (
                plan.get("focus_pool", "TMR_FALLBACK")
                if isinstance(plan, dict)
                else "TMR_FALLBACK"
            )
            log_sleep_training_window(
                session_id=self.session_id,
                htw_index=self._htw_count - 1,
                started_at=self._htw_start_ts,
                duration_s=duration_s,
                stage_at_entry="N1",
                stage_at_exit=stage_at_exit,
                focus_pool=pool,
                phrases_delivered=max(0, int(duration_s / 12.0)),
                exit_reason=reason,
            )
        except Exception:
            pass

        return next_phase

    # =========================================================================
    # HOLD TIMER HELPERS (HYSTERESIS)
    # =========================================================================

    def _hold_start(self, key: str) -> None:
        if key not in self._hold_timers:
            self._hold_timers[key] = time.time()

    def _hold_met(self, key: str, required_s: float, patience_mul: float = 1.0) -> bool:
        if key not in self._hold_timers:
            return False
        return (time.time() - self._hold_timers[key]) >= required_s * max(
            0.25, patience_mul
        )

    def _hold_reset(self, key: str) -> None:
        self._hold_timers.pop(key, None)

    def _hold_active(self, key: str) -> bool:
        return key in self._hold_timers

    # =========================================================================
    # FRACTIONATION HELPERS
    # =========================================================================

    def _calc_max_fractionations(self, duration_min: int) -> int:
        if duration_min < 25:
            return 1
        if duration_min < 35:
            return 2
        if duration_min < 50:
            return 3
        return 4

    def _frac_eligible(self, elapsed: float) -> bool:
        base_eligible = (
            elapsed > 300
            and self.fractionation_count < self.max_fractionations
            and self.phase in (Phase.DEEPENING, Phase.MAINTENANCE)
        )
        if base_eligible:
            return True
        # Agent can request an immediate fractionation if the basic eligibility
        # window has opened (elapsed > 180 s) and fracs remain.
        if (
            self._hints.get("request_fractionation")
            and elapsed > 180
            and self.fractionation_count < self.max_fractionations
            and self.phase in (Phase.DEEPENING, Phase.MAINTENANCE)
        ):
            print("[Conductor] Agent-requested fractionation — triggering.")
            # Clear the flag so it doesn't fire every tick
            try:
                raw = json.loads(_LIVE.read_text(encoding="utf-8"))
                hints = raw.get("agent_conductor_hints") or {}
                hints["request_fractionation"] = False
                patch_live({"agent_conductor_hints": hints})
            except Exception:
                pass
            return True
        return False

    def _select_emerge_hold_duration(self) -> float:
        """Bible Ch.3 §3.5 Vogt timing: first cycle longer, later cycles shorter."""
        if self.fractionation_count == 0:
            return 35.0
        if self.fractionation_count == 1:
            return 25.0
        return 15.0

    # =========================================================================
    # MODALITY SWITCHING
    # =========================================================================

    def _switch_modality(self) -> None:
        """Binaural ↔ isochronic per Bible Ch.5 §5.4 ASSR recovery protocol."""
        self._current_modality = (
            "isochronic" if self._current_modality == "binaural" else "binaural"
        )
        self._modality_switches += 1
        patch_live({"beat_type": self._current_modality})
        self._say(f"Adjusting audio approach — switching to {self._current_modality}.")
        self._hold_reset("induction_lock")
        print(
            f"[Conductor] Modality switch → {self._current_modality} "
            f"(switch #{self._modality_switches})"
        )

    # =========================================================================
    # TRANCE SCORE HELPERS
    # =========================================================================

    def _trance_score_rate(self) -> Optional[float]:
        """Linear regression slope of trance score over last 120 s (per minute)."""
        now = time.time()
        recent = [(t, v) for t, v in self._trance_history if now - t <= 120]
        if len(recent) < 3:
            return None
        t0 = recent[0][0]
        times = [(t - t0) / 60.0 for t, _ in recent]
        values = [v for _, v in recent]
        n = len(times)
        st = sum(times)
        sv = sum(values)
        stv = sum(t * v for t, v in zip(times, values))
        st2 = sum(t * t for t in times)
        denom = n * st2 - st * st
        if abs(denom) < 1e-10:
            return 0.0
        return (n * stv - st * sv) / denom

    def _faa_sustained_seconds(self, faa: Dict) -> float:
        """Estimate how long FAA has been in its current polarity.

        Uses the trance history timestamps as a proxy for elapsed ticks.
        A proper implementation would track FAA sign transitions; this is
        a reasonable approximation for the conflict resolution use case.
        """
        # Simple approach: count consecutive ticks with same sign
        if not self._trance_history:
            return 0.0
        return float(_TICK_RATES.get(self.phase) or 10) * 3  # 3 ticks worth

    # =========================================================================
    # DEPTH CONFIDENCE — Bible Ch.2 §2.9 §4
    # =========================================================================

    def _estimate_depth_confidence(self, live: Dict) -> tuple[float, str]:
        """Return (depth_estimate, confidence_level) using EEG + autonomic convergence.

        confidence_level is 'high', 'moderate', or 'low'.
        When EEG and HRV signals agree (divergence < 0.15) the converged mean is
        returned at high confidence.  Major divergence falls back to EEG-only.
        """
        eeg_depth = float(live.get("eeg_trance_score_v2") or 0.0)
        auto_depth = live.get("ppg_autonomic_depth")
        stillness = live.get("imu_stillness_index")

        if auto_depth is None or not live.get("ppg_autonomic_calibrated", False):
            # No calibrated PPG — EEG only, moderate confidence
            return eeg_depth, "moderate"

        auto_depth = float(auto_depth)
        divergence = abs(eeg_depth - auto_depth)

        if divergence < 0.15:
            depth = (eeg_depth + auto_depth) / 2.0
            confidence = "high"
        elif divergence < 0.30:
            depth = min(eeg_depth, auto_depth)  # conservative — pick lower
            confidence = "moderate"
        else:
            depth = eeg_depth  # major divergence — trust EEG
            confidence = "low"

        # Physical stillness as bonus convergent signal
        if (
            stillness is not None
            and float(stillness) > 0.90
            and depth > 0.5
            and confidence != "high"
        ):
            confidence = "high"

        return round(float(depth), 3), confidence

    # =========================================================================
    # LIVE_CONTROL.JSON I/O
    # =========================================================================

    def _say(
        self, text: str, needs_response: bool = False, via: Optional[List[str]] = None
    ) -> None:
        """Deliver a message via agent_message — skips if a prompt is in flight."""
        live = self._read_live()
        cur = live.get("agent_message") or {}
        if isinstance(cur, dict) and cur.get("needs_response"):
            return
        patch_live(
            {
                "agent_message": {
                    "text": text,
                    "ts": time.time(),
                    "needs_response": needs_response,
                    "via": via or ["console", "tts"],
                    "style": {"voice_mode": "tts"},
                }
            }
        )

    # =========================================================================
    # DECISION LOGGING
    # =========================================================================

    def _log_decision(self, m: Dict, action: str, rationale: str) -> None:
        live = self._read_live()
        entry: Dict[str, Any] = {
            "timestamp": time.time(),
            "session_elapsed": time.time() - self.session_start,
            "phase": self.phase.value,
            "action": action,
            "rationale": (
                rationale + f" [agent: {self._hints['note']}]"
                if self._hints.get("note")
                else rationale
            ),
            "sqi_confidence": m.get("sqi_confidence"),
            "trance_score": m.get("trance_score"),
            "sef95": m.get("sef95"),
            "assr_strength": m["assr"]["strength"] if m.get("assr") else None,
            "assr_confidence": m["assr"]["confidence"] if m.get("assr") else None,
            "faa_value": m["faa"]["value"] if m.get("faa") else None,
            "beat_freq": live.get("beat_frequency"),
            "chaos": live.get("spiral_chaos"),
            "trail_decay": live.get("trail_decay"),
            "tick_rate": _TICK_RATES.get(self.phase),
            "parameters_json": json.dumps(
                {
                    k: live.get(k)
                    for k in (
                        "beat_frequency",
                        "beat_type",
                        "spiral_chaos",
                        "trail_decay",
                        "veil_mode",
                        "spiral_style",
                        "shadow_opacity_target",
                        "sr_noise_level",
                    )
                }
            ),
        }
        self._decision_log.append(entry)
        self._log_flush_counter += 1

        if self._log_flush_counter >= 10 or "TRANSITION" in action:
            self._flush_log()

    def _flush_log(self) -> None:
        if not self._decision_log or not _DB_AVAILABLE:
            self._decision_log = []
            self._log_flush_counter = 0
            return
        try:
            write_conductor_decisions_batch(self.session_id, self._decision_log)
        except Exception as e:
            print(f"[Conductor] DB flush error: {e}")
        finally:
            self._decision_log = []
            self._log_flush_counter = 0

    # =========================================================================
    # UTILITY
    # =========================================================================

    def _transition_rationale(self, old: Phase, new: Phase, m: Dict) -> str:
        ts = m.get("trance_score")
        sef = m.get("sef95")
        assr = m.get("assr")
        parts = [f"{old.value} → {new.value}"]
        if ts is not None:
            parts.append(f"trance={ts:.3f}")
        if sef is not None:
            parts.append(f"SEF95={sef:.1f}")
        if assr:
            parts.append(f"ASSR={assr['strength']:.2f}")
        return " | ".join(parts)

    def summary(self) -> Dict[str, Any]:
        """Return a brief state dict for agent context."""
        return {
            "conductor_phase": self.phase.value,
            "iaf_hz": self.iaf,
            "frac_count": self.fractionation_count,
            "frac_max": self.max_fractionations,
            "session_elapsed_s": int(time.time() - self.session_start),
            "degraded": getattr(self, "_timer_mode", False),
            "modality_switches": self._modality_switches,
        }

    def assessment(self) -> Dict[str, Any]:
        """Return a richer dict for the agent's LLM context.

        Includes what the Conductor is currently measuring, what it is
        targeting, and what condition it is waiting on before advancing.
        The agent uses this to make complementary decisions — e.g. leaning
        into heavier somatic language when the trance score is low.
        """
        m = self._last_metrics
        phase = self.phase
        assr = m.get("assr") or {}
        ts = m.get("trance_score")
        sqi = m.get("sqi_confidence", "unknown")

        # Human-readable description of what must happen to advance
        if phase == Phase.CALIBRATION:
            gate = "sqi_confidence >= REDUCED and IAF detected (or 90 s elapsed)"
        elif phase == Phase.INDUCTION:
            gate = "assr_confidence >= REDUCED held for 60 s"
        elif phase == Phase.DEEPENING:
            gate = (
                f"trance_score > {self._ct('trance_moderate', 0.65):.2f} held 90 s "
                f"AND assr held 60 s"
            )
        elif phase == Phase.MAINTENANCE:
            gate = "hold until fractionation or session end"
        elif phase == Phase.FRAC_EMERGE:
            gate = f"sef95 > {self._ct('sef95_light', 15.0):.1f} Hz or 45 s elapsed"
        elif phase == Phase.FRAC_EMERGE_HOLD:
            gate = f"hold {self._select_emerge_hold_duration()} s then redrop"
        elif phase == Phase.FRAC_REDROP:
            gate = (
                f"trance_score > {self._ct('trance_moderate', 0.65):.2f} held 60 s "
                f"(or 180 s hard timeout)"
            )
        elif phase == Phase.SLEEP_APPROACH:
            gate = (
                f"sleep_onset_detected or "
                f"sef95 < {self._ct('sef95_deep', 8.0):.1f} Hz held 120 s"
            )
        elif phase == Phase.EDISON_PREPARATION:
            gate = "user_ready signal or 5 min auto-advance"
        elif phase == Phase.EDISON_SEED:
            gate = "seed prompt delivered + 10 s grace"
        elif phase == Phase.EDISON_MONITORING:
            gate = "N1 detected (eeg_sleep_stage=N1 or alpha/theta ratio < 0.8)"
        elif phase == Phase.EDISON_N1_HOLD:
            gate = (
                f"hold {getattr(self._edison, 'n1_hold_seconds', 60)}s or N2 boundary"
            )
        elif phase == Phase.EDISON_CAPTURE:
            gate = "user verbal response collected (120 s timeout)"
        elif phase == Phase.EDISON_CYCLE_END:
            gate = "user chooses continue or end"
        else:
            gate = "n/a"

        # Phase arc: completed transitions + current phase duration
        phase_dur_s = int(time.time() - self.phase_entered_at)
        arc_parts = [f"{ph}({dur}s)" for ph, dur in self._phase_history[-4:]]
        arc_parts.append(f"{phase.value}({phase_dur_s}s, current)")
        phase_arc = " → ".join(arc_parts)

        # Trance score rate of change (Hz/min over rolling 5-min window)
        ts_rate = self._trance_score_rate()

        cascade = m.get("cascade", {})
        return {
            "phase": phase.value,
            "phase_duration_s": phase_dur_s,
            "phase_arc": phase_arc,
            "timer_mode": getattr(self, "_timer_mode", False),
            "eeg_enabled": self.eeg_enabled,
            "target_freq_hz": self.current_target_freq,
            "iaf_hz": self.iaf,
            "trance_score": ts,
            "trance_trend_per_min": round(ts_rate, 3) if ts_rate is not None else None,
            "assr_confidence": assr.get("confidence"),
            "assr_strength": assr.get("strength"),
            "sqi": sqi,
            "advance_gate": gate,
            "frac_count": self.fractionation_count,
            "frac_max": self.max_fractionations,
            "calibration": self._calibration_summary(),
            "vr": self._vr_summary(),
            # Phase-cascade (Bible Ch.4 §4.6) — present whenever metrics are available
            "cascade_integrity": cascade.get("cascade_integrity"),
            "phase_gate_mode": cascade.get("phase_gate_mode", "disabled"),
            "phase_gate_hit_rate": cascade.get("phase_gate_hit_rate"),
            "delivery_rate_hz": cascade.get("delivery_rate_hz"),
            "isa_alpha_pac": cascade.get("isa_alpha_pac"),
            "theta_gamma_pac": cascade.get("theta_gamma_pac"),
            "resp_hot_window": [
                cascade.get("resp_hot_window_start", 0.6),
                cascade.get("resp_hot_window_end", 0.9),
            ],
            # Bible Ch.2 §2.8 — three-axis depth markers for agent context
            "spectral_slope": m.get("depth", {}).get("spectral_slope"),
            "slope_trend": self._slope_trend(),
            "coherence_depth": m.get("depth", {}).get("coherence_depth"),
            "frontal_decoupling": m.get("depth", {}).get("frontal_alpha_coh"),
            "beta_env_corr": m.get("depth", {}).get("beta_env_corr"),
            "trance_score_v2": m.get("depth", {}).get("trance_score_v2"),
        }

    def _slope_trend(self) -> str:
        """Describe spectral slope direction over recent ticks for agent context."""
        history = getattr(self, "_slope_history", [])
        if len(history) < 3:
            return "stable"
        recent = history[-3:]
        delta = recent[-1] - recent[0]
        if delta < -0.1:
            return "steepening"  # more negative = deeper
        if delta > 0.1:
            return "shallowing"  # less negative = lighter
        return "stable"

    def _validate_vr_frequencies(self, live: dict) -> None:
        """Run the frequency allocation check when the VR headset first becomes active.

        Logs collisions as warnings — does not abort the session, since the user
        has already launched the headset.  Writes vr_freq_warnings to live_control.json
        so the control panel can surface them.
        """
        try:
            from vr.vr_freq_table import build_session_table

            beat_hz = float(live.get("beat_frequency", 6.0))
            iaf_hz = float(self.iaf or 10.0)
            mode = str(live.get("vr_render_mode", "ganzfeld"))
            left_hz = float(live.get("vr_rivalry_left_hz", 7.5))
            right_hz = float(live.get("vr_rivalry_right_hz", 12.0))
            photic_hz = float(live.get("vr_photic_hz", iaf_hz))

            table = build_session_table(
                binaural_beat_hz=beat_hz,
                iaf_hz=iaf_hz,
                photic_enabled=mode == "photic",
                photic_hz=photic_hz,
                rivalry_enabled=mode in ("rivalry", "dichoptic_ssvep"),
                rivalry_left_hz=left_hz,
                rivalry_right_hz=right_hz,
            )
            # If we reach here, no collisions — clear any previous warnings
            patch_live({"vr_freq_warnings": []})
            print(
                f"[Conductor] VR frequency allocation OK — "
                f"binaural={beat_hz}Hz, mode={mode}"
            )
        except ValueError as e:
            warnings = [str(e)]
            patch_live({"vr_freq_warnings": warnings})
            print(f"[Conductor] VR frequency WARNING: {e}")
        except Exception as e:
            print(f"[Conductor] VR frequency check error (non-fatal): {e}")

    def _gain_engine_tick(self) -> None:
        """Run one tick of the crossmodal gain engine (Bible Ch.3 §3.8 §5.2).

        Phase-specific lifecycle per Bible Ch.3 §3.8 §7:
          CALIBRATION       → OFF; SR sweep may run
          INDUCTION         → ON (limited; depth_scalar = 1.0 via slope stub)
          DEEPENING         → ON (ramping)
          MAINTENANCE       → ON (full)
          FRAC_EMERGE/HOLD  → SUSPENDED; raw values restored
          FRAC_REDROP       → ON (resuming from last_gains)
          SLEEP_APPROACH/ONSET/MAINTAIN → ON (aggressive reduction via sleep gain profiles)
          SESSION_END       → OFF; raw values restored
        """
        if not _GAIN_AVAILABLE:
            return

        phase = self.phase

        # Phases where the gain engine is off or suspended
        if phase in (Phase.CALIBRATION, Phase.SESSION_END):
            if self._gain_engine_active:
                self._gain_engine_active = False
                if self._gain_engine:
                    live = self._read_live()
                    patch_live(self._gain_engine.restore_raw(live))
                    patch_live({"crossmodal_gain_enabled": False})
            return

        if phase in (Phase.FRAC_EMERGE, Phase.FRAC_EMERGE_HOLD):
            if self._gain_engine_active:
                self._gain_engine_active = False
                if self._gain_engine:
                    live = self._read_live()
                    patch_live(self._gain_engine.restore_raw(live))
                    patch_live({"crossmodal_gain_enabled": False})
            return

        # Lazily instantiate engine on first active phase
        if self._gain_engine is None:
            profile = self._build_gain_profile()
            try:
                self._gain_engine = CrossmodalGainEngine(profile)
            except Exception as e:
                print(f"[Conductor] CrossmodalGainEngine init failed: {e}")
                return

        # Re-enable if coming out of suspension (e.g. FRAC_REDROP)
        if not self._gain_engine_active:
            self._gain_engine_active = True
            self._gain_engine.set_enabled(True)
            patch_live({"crossmodal_gain_enabled": True})

        # Run gain engine tick
        try:
            live = self._read_live()
            gain_patch = self._gain_engine.tick(live)
            if gain_patch:
                # Log gain decision to DB
                self._log_gain_decision(gain_patch, live)
                patch_live(gain_patch)
        except Exception as e:
            print(f"[Conductor] Gain engine tick error: {e}")

    def _build_gain_profile(self) -> dict:
        """Build calibration profile for CrossmodalGainEngine from stored data."""
        try:
            from content_tools.somna_db import get_latest_sr_calibration

            cal = get_latest_sr_calibration()
            if cal:
                profile = {
                    "sr_optimal_noise": cal.get("sr_optimal_noise", 22.0),
                    "sr_gain_bonus": cal.get("sr_gain_bonus", 0.10),
                    "carrier_noise_threshold": cal.get("carrier_noise_threshold", 8.0),
                }
            else:
                profile = {}
        except Exception:
            profile = {}

        # Blend in baseline slope from live state or calibration
        live = self._read_live()
        baseline_slope = live.get("eeg_baseline_slope") or -1.3
        profile["baseline_slope"] = float(baseline_slope)
        return profile

    def _log_gain_decision(self, gain_patch: dict, live_state: dict) -> None:
        """Write gain decision to DB (non-blocking)."""
        try:
            from content_tools.somna_db import log_gain_decision

            gain_state = gain_patch.get("crossmodal_gain_state", {})
            log_gain_decision(
                session_id=str(live_state.get("session_name", "unknown")),
                ts=gain_state.get("ts", time.time()),
                conductor_phase=self.phase.value,
                depth_scalar=gain_state.get("depth_scalar"),
                sr_factor=gain_state.get("sr_factor"),
                noise_ratio=gain_state.get("noise_ratio"),
                raw_noise=float(live_state.get("noise_volume") or 0),
                effective_noise=gain_patch.get("noise_volume"),
                raw_text_opacity=float(live_state.get("veil_opacity") or 0),
                effective_text_opacity=gain_patch.get("veil_opacity"),
                carrier_noise_ratio=gain_state.get("cnr"),
            )
        except Exception:
            pass

    def _vr_photic_loop(self, metrics: Dict) -> None:
        """Closed-loop photic entrainment: adjust vr_photic_hz to maximise SSVEP SNR.

        Only active when:
          - VR headset is running (vr_headset_active = True)
          - vr_render_mode = "photic"
          - ssvep_left_snr is available (SSVEP detector is running)

        Strategy:
          1. After 60 s at the current frequency, evaluate SNR.
          2. If SNR < 3 dB, nudge the frequency ±0.5 Hz toward IAF.
          3. Nudges are capped at ±3 Hz from the session-start IAF so
             the frequency stays in a therapeutically useful range.
          4. If SNR >= 6 dB, leave the frequency alone (good lock).
        """
        vr = metrics.get("vr")
        if not vr or not vr.get("render_mode") == "photic":
            return
        if not self._read_live().get("vr_headset_active"):
            return

        snr = vr.get("left_snr")
        if snr is None:
            return

        now = time.time()
        self._vr_photic_hold_s += (
            now - self._vr_photic_adj_ts if self._vr_photic_adj_ts else 0
        )
        self._vr_photic_adj_ts = now

        if self._vr_photic_hold_s < 60.0:
            return  # not long enough to evaluate

        self._vr_photic_last_snr = snr

        if snr >= 6.0:
            # Good lock — reset dwell timer and stay
            self._vr_photic_hold_s = 0.0
            return

        if snr < 3.0:
            # Poor entrainment — nudge toward IAF
            iaf = self.iaf or 10.0
            delta = 0.5 if self._vr_photic_hz < iaf else -0.5
            new_hz = self._vr_photic_hz + delta
            # Stay within ±3 Hz of IAF
            new_hz = max(iaf - 3.0, min(iaf + 3.0, new_hz))
            new_hz = round(new_hz * 2) / 2.0  # snap to 0.5 Hz grid
            if new_hz != self._vr_photic_hz:
                self._vr_photic_hz = new_hz
                self._vr_photic_hold_s = 0.0
                patch_live(
                    {
                        "vr_photic_hz": new_hz,
                        "vr_rivalry_left_hz": new_hz,  # also update display
                    }
                )
                print(
                    f"[Conductor] VR photic nudge → {new_hz:.1f} Hz "
                    f"(SNR was {snr:.1f} dB, IAF={iaf:.1f} Hz)"
                )

    def _vr_summary(self) -> dict:
        """Compact VR/SSVEP state for agent assessment injection."""
        vr = self._last_metrics.get("vr")
        if not vr:
            return {"active": False}
        return {
            "active": True,
            "render_mode": vr.get("render_mode", "ganzfeld"),
            "binocular_index": vr.get("binocular_index"),
            "dominance_raw": vr.get("dominance_raw"),
            "switch_rate_hz": vr.get("switch_rate_hz"),
            "safety_kill": vr.get("safety_kill", False),
            "integration_notes": _interpret_binocular(vr),
        }

    def _calibration_summary(self) -> dict:
        """Compact calibration state for agent assessment injection."""
        if self.cal is None:
            return {"available": False}
        return {
            "available": True,
            "complete": self.cal.calibration_complete,
            "sessions_done": self.cal.sessions_completed,
            "sessions_required": self.cal.CALIBRATION_SESSIONS_REQUIRED,
            "current_protocol": self.cal.get_session_protocol()
            if not self.cal.calibration_complete
            else None,
            "personal_thresholds_active": self.cal.calibration_complete,
        }

    def _build_state_snapshot(self, metrics: Dict) -> Dict[str, Any]:
        """Build the lightweight conductor_state dict written to live_control.json."""
        assr = metrics.get("assr") or {}
        return {
            "phase": self.phase.value,
            "timer_mode": getattr(self, "_timer_mode", False),
            "iaf_hz": self.iaf,
            "target_freq_hz": self.current_target_freq,
            "trance_score": metrics.get("trance_score"),
            "assr_strength": assr.get("strength"),
            "assr_conf": assr.get("confidence"),
            "sqi": metrics.get("sqi_confidence"),
            "frac_count": self.fractionation_count,
            "frac_max": self.max_fractionations,
            "ts": metrics.get("timestamp", 0.0),
        }


# ── Bible Ch.10 §10.2 §5.2 — AM depth targets per phase (populated after class def) ──────
# Written every tick; audio_engine interpolates toward the target at ~1 unit/5s.
Conductor._AM_DEPTH_BY_PHASE = {
    Phase.CALIBRATION: 0.00,
    Phase.INDUCTION: 0.15,
    Phase.DEEPENING: 0.30,
    Phase.MAINTENANCE: 0.50,
    Phase.FRAC_EMERGE: 0.20,
    Phase.FRAC_EMERGE_HOLD: 0.20,
    Phase.FRAC_REDROP: 0.40,
    Phase.SLEEP_APPROACH: 0.10,
    Phase.SLEEP_ONSET: 0.00,
    Phase.SLEEP_MAINTAIN: 0.00,
    Phase.SLEEP_TRAINING: 0.10,
    Phase.SLEEP_WAKE: 0.00,
    Phase.EDISON_PREPARATION: 0.00,
    Phase.EDISON_SEED: 0.10,
    Phase.EDISON_MONITORING: 0.00,
    Phase.EDISON_N1_HOLD: 0.00,
    Phase.EDISON_CAPTURE: 0.20,
    Phase.EDISON_CYCLE_END: 0.05,
    Phase.SSILD_PRE_TECHNIQUE: 0.10,
    Phase.SSILD_QUICK_CYCLES: 0.00,
    Phase.SSILD_SLOW_CYCLES: 0.00,
    Phase.SSILD_POST_TECHNIQUE: 0.00,
    Phase.SSILD_REM_MONITORING: 0.00,
    Phase.SSILD_DREAM_JOURNAL: 0.10,
    Phase.GENUS_BLOCK: 0.70,
}
