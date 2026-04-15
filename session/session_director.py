"""
session/session_director.py — Session Director Architecture (Bible Ch.5 §5.5)
=====================================================================
Meso-loop session architect.  Operates between the Conductor (micro-loop,
seconds) and the SessionPlanner/SessionEvaluator (macro-loop, sessions).

Tick is called once per second from somna_agent._interactive_tick(), AFTER
conductor.tick() so Director patches can override Conductor targets.

All five arc templates are defined as frozen dataclass instances at module
level in ARC_TEMPLATES.  Constants are module-level named values — no magic
numbers in method bodies.
"""

from __future__ import annotations

import math
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

# InductionRunner import (graceful — available once session package is complete)
try:
    from session.induction_runner import (
        InductionRunner,
        StrategySelector,
        STRATEGY_REGISTRY,
    )
    _INDUCTION_AVAILABLE = True
except ImportError:
    _INDUCTION_AVAILABLE = False

# ── Module-level constants (all tunable) ──────────────────────────────────────

TRAJECTORY_EVAL_INTERVAL_S  = 30
TRAJECTORY_WINDOW_S         = 180
MIN_SESSION_FOR_SLEEP_FORK_S = 1200    # 20 min
EMERGENCY_DEPTH_FLOOR       = 0.15
HR_SPIKE_THRESHOLD          = 0.20
SURFACING_THRESHOLD         = 0.05
DEPTH_DECLINE_THRESHOLD     = 0.0005  # slope/s
DEPTH_ADVANCE_THRESHOLD     = 0.001   # slope/s
MAX_BUILD_DURATION_S        = 300
MIN_RELAX_DURATION_S        = 120
PACE_BRIDGE_DURATION_S      = 20
LEAD_VERIFY_WINDOW_S        = 60
SIGNAL_LOST_HOLD_S          = 30
MOTION_EXTEND_S             = 60
INDUCTION_RETRY_LIMIT       = 2

# Intensity channel weights
INTENSITY_W_GAIN        = 0.30
INTENSITY_W_CONTENT     = 0.25
INTENSITY_W_ENTRAINMENT = 0.20
INTENSITY_W_NOVELTY     = 0.15
INTENSITY_W_TTS         = 0.10

# Pace confidence
PACE_CONFIDENCE_INITIAL       = 0.5
PACE_CONFIDENCE_SUCCESS_BOOST = 0.08
PACE_CONFIDENCE_FAIL_PENALTY  = 0.15
PACE_CONFIDENCE_DECAY_RATE    = 0.001
PACE_CONFIDENCE_MIN           = 0.1
PACE_CONFIDENCE_MAX           = 0.95

# Trajectory thresholds
HRV_STABILITY_THRESHOLD = 0.20
STILLNESS_THRESHOLD     = 0.5
DECISION_POSITIVE_THRESHOLD = 0.001


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ── Enumerations ─────────────────────────────────────────────────────────────

class DirectorPhase(str, Enum):
    ARRIVAL              = "ARRIVAL"
    INDUCTION            = "INDUCTION"
    DEEPENING            = "DEEPENING"
    WORK                 = "WORK"
    WORK_BLOCK           = "WORK_BLOCK"
    MICRO_CONSOLIDATION  = "MICRO_CONSOLIDATION"
    CONSOLIDATION        = "CONSOLIDATION"
    EMERGENCE            = "EMERGENCE"
    SLEEP_TRANSITION     = "SLEEP_TRANSITION"


class IntensityCycleState(str, Enum):
    BUILD_UP = "BUILD_UP"
    PEAK     = "PEAK"
    RELAX    = "RELAX"


class TrajectoryStatus(str, Enum):
    CONTINUE    = "CONTINUE"
    ACCELERATE  = "ACCELERATE"
    DECELERATE  = "DECELERATE"
    REDIRECT    = "REDIRECT"
    FORK        = "FORK"


class DecisionType(str, Enum):
    PHASE_TRANSITION    = "phase_transition"
    REDIRECT            = "redirect"
    INTENSITY_CHANGE    = "intensity_change"
    POOL_SWITCH         = "pool_switch"
    INDUCTION_SWITCH    = "induction_switch"
    SLEEP_FORK          = "sleep_fork"
    DISHABITUATION      = "dishabituation"
    DEPTH_TARGET_ADJUST = "depth_target_adjust"
    TRAJECTORY          = "trajectory"
    CONDITIONING_DEPLOY = "conditioning_deploy"
    ARC_MODIFICATION    = "arc_modification"


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class PhasePlan:
    phase:             DirectorPhase
    target_duration_s: int
    min_duration_s:    int
    max_duration_s:    int
    entry_condition:   str
    exit_condition:    str
    intensity_target:  float
    content_pools:     list[str]
    gain_ceiling:      float


@dataclass(frozen=True)
class ArcTemplate:
    name:                   str
    phase_sequence:         tuple[DirectorPhase, ...]
    duration_ratios:        tuple[float, ...]
    intensity_profile:      str
    max_intensity_cycles:   int
    default_build_up_rate:  float
    default_peak_hold_s:    int
    default_relax_floor:    float
    target_depth_min:       float
    target_depth_max:       float
    sleep_fork_default:     bool
    cycling_phases:         tuple[DirectorPhase, ...]


@dataclass
class IntensityCycle:
    cycle_index:       int
    cycle_peak_target: float
    build_up_rate:     float
    peak_hold_s:       int
    relax_floor:       float
    state:             IntensityCycleState = IntensityCycleState.BUILD_UP
    state_elapsed_s:   int = 0
    completed:         bool = False


@dataclass
class DecisionRecord:
    timestamp:       float
    decision_type:   DecisionType
    decision_value:  str
    authority_level: int
    rationale:       str
    state_snapshot:  dict
    outcome_score:   Optional[float] = None
    decision_id:     str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class PaceResult:
    aligned:              bool
    user_deeper:          bool
    user_shallower:       bool
    confidence:           float
    recommended_action:   str   # "proceed" | "skip_ahead" | "extend" | "regress"


@dataclass
class SessionPlan:
    session_id:              str
    created_at:              float
    session_goal:            str
    target_peak_depth:       float
    estimated_duration_s:    int
    arc_template:            str
    phase_plan:              list[PhasePlan]
    contingency_branches:    dict[str, list[PhasePlan]]
    content_strategy:        dict[str, dict]
    induction_strategy:      str
    priority_pools:          list[str]
    conditioning_targets:    list[str]
    sleep_fork_enabled:      bool


@dataclass
class ConditioningDelta:
    association_id: str
    pre_strength:   float
    post_strength:  float


@dataclass
class SessionLog:
    started_at:                    float
    ended_at:                      float
    duration_s:                    int
    arc_template:                  str
    induction_strategy:            str
    trance_score_timeseries:       list[float]
    trance_scores_during_work:     list[float]
    achieved_peak_depth:           float
    avg_depth:                     float
    time_in_deep_s:                int
    time_to_induction_s:           float
    time_to_peak_s:                float
    depth_trajectory_score:        float
    induction_effectiveness:       float
    conditioning_deltas:           list[ConditioningDelta]
    phase_durations:               list[int]
    decisions:                     list[DecisionRecord]
    redirect_count:                int
    intensity_cycles_completed:    int
    pace_confidence_final:         float
    emergence_hr_deviation:        float
    final_trance_score:            float
    emergence_duration_s:          int
    planned_emergence_duration_s:  int
    user_satisfaction:             Optional[float] = None


# ── Phase metadata lookup tables ──────────────────────────────────────────────

# exit conditions as strings; evaluated by _evaluate_condition()
_PHASE_EXIT_CONDITIONS: dict[DirectorPhase, str] = {
    DirectorPhase.ARRIVAL:             "baseline_complete AND phase_elapsed >= min_duration",
    DirectorPhase.INDUCTION:           "trance_score_v2 >= 0.25 AND phase_elapsed >= min_duration",
    DirectorPhase.DEEPENING:           "trance_score_v2 >= target_peak_depth_x0.8 AND cycles_complete",
    DirectorPhase.WORK:                "phase_elapsed >= target_duration",
    DirectorPhase.WORK_BLOCK:          "phase_elapsed >= target_duration",
    DirectorPhase.MICRO_CONSOLIDATION: "phase_elapsed >= min_duration",
    DirectorPhase.CONSOLIDATION:       "intensity < 0.2 AND phase_elapsed >= min_duration",
    DirectorPhase.EMERGENCE:           "trance_score_v2 < 0.1 AND phase_elapsed >= min_duration",
    DirectorPhase.SLEEP_TRANSITION:    "handoff_to_doc39",
}

_PHASE_INTENSITY_TARGETS: dict[DirectorPhase, float] = {
    DirectorPhase.ARRIVAL:             0.15,
    DirectorPhase.INDUCTION:           0.35,
    DirectorPhase.DEEPENING:           0.65,
    DirectorPhase.WORK:                0.80,
    DirectorPhase.WORK_BLOCK:          0.75,
    DirectorPhase.MICRO_CONSOLIDATION: 0.30,
    DirectorPhase.CONSOLIDATION:       0.20,
    DirectorPhase.EMERGENCE:           0.05,
    DirectorPhase.SLEEP_TRANSITION:    0.15,
}

_PHASE_GAIN_CEILINGS: dict[DirectorPhase, float] = {
    DirectorPhase.ARRIVAL:             0.30,
    DirectorPhase.INDUCTION:           0.50,
    DirectorPhase.DEEPENING:           0.70,
    DirectorPhase.WORK:                0.85,
    DirectorPhase.WORK_BLOCK:          0.80,
    DirectorPhase.MICRO_CONSOLIDATION: 0.40,
    DirectorPhase.CONSOLIDATION:       0.35,
    DirectorPhase.EMERGENCE:           0.20,
    DirectorPhase.SLEEP_TRANSITION:    0.30,
}

_PHASE_CONTENT_POOLS: dict[DirectorPhase, list[str]] = {
    DirectorPhase.ARRIVAL:             ["ambient_support"],
    DirectorPhase.INDUCTION:           ["general_induction", "entrainment_heavy"],
    DirectorPhase.DEEPENING:           ["deepening_somatic", "breath_anchors"],
    DirectorPhase.WORK:                ["conditioning_primary", "identity_work"],
    DirectorPhase.WORK_BLOCK:          ["conditioning_primary", "anchor_strengthening"],
    DirectorPhase.MICRO_CONSOLIDATION: ["ambient_support", "somatic_familiar"],
    DirectorPhase.CONSOLIDATION:       ["balanced_general", "somatic_familiar"],
    DirectorPhase.EMERGENCE:           ["emergence_gentle"],
    DirectorPhase.SLEEP_TRANSITION:    ["sleep_bridge", "body_scan_progressive"],
}

# Induction strategy names for retry rotation
INDUCTION_STRATEGIES = [
    "ENTRAINMENT_HEAVY",
    "SOMATIC_ANCHOR",
    "BREATH_LEAD",
    "PROGRESSIVE_RELAXATION",
    "COGNITIVE_OVERLOAD",
    "FRACTIONATION",
    "FIXATION_FADE",
    "PACE_AND_LEAD",
]


# ── Arc template definitions ──────────────────────────────────────────────────

_GENTLE_DESCENT = ArcTemplate(
    name="GENTLE_DESCENT",
    phase_sequence=(
        DirectorPhase.ARRIVAL,
        DirectorPhase.INDUCTION,
        DirectorPhase.DEEPENING,
        DirectorPhase.WORK,
        DirectorPhase.CONSOLIDATION,
        DirectorPhase.EMERGENCE,
    ),
    duration_ratios=(0.05, 0.15, 0.35, 0.25, 0.15, 0.05),
    intensity_profile="slow_ramp",
    max_intensity_cycles=2,
    default_build_up_rate=0.002,
    default_peak_hold_s=120,
    default_relax_floor=0.3,
    target_depth_min=0.5,
    target_depth_max=0.6,
    sleep_fork_default=False,
    cycling_phases=(DirectorPhase.DEEPENING,),
)

_WAVE_PATTERN = ArcTemplate(
    name="WAVE_PATTERN",
    phase_sequence=(
        DirectorPhase.ARRIVAL,
        DirectorPhase.INDUCTION,
        DirectorPhase.DEEPENING,
        DirectorPhase.WORK,
        DirectorPhase.CONSOLIDATION,
        DirectorPhase.DEEPENING,
        DirectorPhase.WORK,
        DirectorPhase.CONSOLIDATION,
        DirectorPhase.EMERGENCE,
    ),
    duration_ratios=(0.05, 0.10, 0.15, 0.10, 0.08, 0.15, 0.10, 0.12, 0.15),
    intensity_profile="oscillating",
    max_intensity_cycles=4,
    default_build_up_rate=0.004,
    default_peak_hold_s=90,
    default_relax_floor=0.25,
    target_depth_min=0.6,
    target_depth_max=0.7,
    sleep_fork_default=False,
    cycling_phases=(DirectorPhase.DEEPENING, DirectorPhase.WORK),
)

_DEEP_PLATEAU = ArcTemplate(
    name="DEEP_PLATEAU",
    phase_sequence=(
        DirectorPhase.ARRIVAL,
        DirectorPhase.INDUCTION,
        DirectorPhase.DEEPENING,
        DirectorPhase.WORK,
        DirectorPhase.CONSOLIDATION,
        DirectorPhase.EMERGENCE,
    ),
    duration_ratios=(0.03, 0.07, 0.15, 0.50, 0.15, 0.10),
    intensity_profile="fast_plateau",
    max_intensity_cycles=1,
    default_build_up_rate=0.005,
    default_peak_hold_s=300,
    default_relax_floor=0.5,
    target_depth_min=0.7,
    target_depth_max=0.85,
    sleep_fork_default=False,
    cycling_phases=(DirectorPhase.WORK,),
)

_CONDITIONING_FOCUS = ArcTemplate(
    name="CONDITIONING_FOCUS",
    phase_sequence=(
        DirectorPhase.ARRIVAL,
        DirectorPhase.INDUCTION,
        DirectorPhase.DEEPENING,
        DirectorPhase.WORK_BLOCK,
        DirectorPhase.MICRO_CONSOLIDATION,
        DirectorPhase.WORK_BLOCK,
        DirectorPhase.MICRO_CONSOLIDATION,
        DirectorPhase.WORK_BLOCK,
        DirectorPhase.MICRO_CONSOLIDATION,
        DirectorPhase.CONSOLIDATION,
        DirectorPhase.EMERGENCE,
    ),
    duration_ratios=(0.05, 0.10, 0.15, 0.12, 0.03, 0.12, 0.03, 0.12, 0.03, 0.12, 0.13),
    intensity_profile="stepped_blocks",
    max_intensity_cycles=3,
    default_build_up_rate=0.003,
    default_peak_hold_s=60,
    default_relax_floor=0.35,
    target_depth_min=0.5,
    target_depth_max=0.7,
    sleep_fork_default=False,
    cycling_phases=(DirectorPhase.WORK_BLOCK,),
)

_SLEEP_BRIDGE = ArcTemplate(
    name="SLEEP_BRIDGE",
    phase_sequence=(
        DirectorPhase.ARRIVAL,
        DirectorPhase.INDUCTION,
        DirectorPhase.DEEPENING,
        DirectorPhase.WORK,
        DirectorPhase.SLEEP_TRANSITION,
    ),
    duration_ratios=(0.05, 0.15, 0.25, 0.30, 0.25),
    intensity_profile="ramp_then_decay",
    max_intensity_cycles=2,
    default_build_up_rate=0.003,
    default_peak_hold_s=90,
    default_relax_floor=0.3,
    target_depth_min=0.6,
    target_depth_max=0.75,
    sleep_fork_default=True,
    cycling_phases=(DirectorPhase.DEEPENING, DirectorPhase.WORK),
)

# ── GENUS arc templates (genus_protocol.md §5 / Bible Ch.4 Addendum A) ──────────────────────
# GENUS sessions run at 40 Hz continuously — no depth ramp, no sleep fork.
# The Director's role is to orchestrate cognitive engagement content over the
# flicker/click-train stimulus rather than guide depth progression.

_GENUS_DAILY = ArcTemplate(
    name="GENUS_DAILY",
    phase_sequence=(
        DirectorPhase.ARRIVAL,
        DirectorPhase.INDUCTION,
        DirectorPhase.WORK,          # 40 Hz stimulation + cognitive engagement
        DirectorPhase.CONSOLIDATION,
    ),
    duration_ratios=(0.03, 0.07, 0.83, 0.07),   # 2 min / 4 min / 50 min / 4 min of 60 min
    intensity_profile="flat",                    # no depth ramp — constant 40 Hz
    max_intensity_cycles=0,
    default_build_up_rate=0.0,
    default_peak_hold_s=3600,
    default_relax_floor=0.5,
    target_depth_min=0.0,
    target_depth_max=0.0,                        # depth not targeted; entrainment ratio tracked instead
    sleep_fork_default=False,
    cycling_phases=(),
)

_GENUS_ENHANCED = ArcTemplate(
    name="GENUS_ENHANCED",
    # GENUS + mild hypnotic induction for frontal→hippocampal entrainment boost
    # (Mlinarič 2025: cognitive engagement enhances GENUS effect)
    phase_sequence=(
        DirectorPhase.ARRIVAL,
        DirectorPhase.INDUCTION,
        DirectorPhase.WORK,
        DirectorPhase.CONSOLIDATION,
    ),
    duration_ratios=(0.03, 0.12, 0.75, 0.10),
    intensity_profile="flat",
    max_intensity_cycles=1,                      # one mild intensity cycle for engagement
    default_build_up_rate=0.001,
    default_peak_hold_s=1800,
    default_relax_floor=0.4,
    target_depth_min=0.0,
    target_depth_max=0.0,
    sleep_fork_default=False,
    cycling_phases=(DirectorPhase.WORK,),
)

_GENUS_AUDIO_ONLY = ArcTemplate(
    name="GENUS_AUDIO_ONLY",
    # Safe mode: audio clicks only, no visual flicker (photosensitive users)
    phase_sequence=(
        DirectorPhase.ARRIVAL,
        DirectorPhase.INDUCTION,
        DirectorPhase.WORK,
        DirectorPhase.CONSOLIDATION,
    ),
    duration_ratios=(0.03, 0.07, 0.83, 0.07),
    intensity_profile="flat",
    max_intensity_cycles=0,
    default_build_up_rate=0.0,
    default_peak_hold_s=3600,
    default_relax_floor=0.5,
    target_depth_min=0.0,
    target_depth_max=0.0,
    sleep_fork_default=False,
    cycling_phases=(),
)

_GENUS_NEUROPROTECTION = ArcTemplate(
    name="GENUS_NEUROPROTECTION",
    # Bible Ch.4 Addendum A §4.3 — Extended GENUS (40–60 min) followed by abbreviated
    # CONDITIONING_FOCUS trance (20–30 min) targeting pools whose Rescorla-Wagner
    # strength has decayed below maintenance threshold.
    # Arc: ARRIVAL → INDUCTION → WORK (GENUS active, 2400–3600 s) →
    #      CONSOLIDATION (TRANSITION_DESCENT 180 s + conditioning trance) →
    #      EMERGENCE → SESSION_END
    phase_sequence=(
        DirectorPhase.ARRIVAL,
        DirectorPhase.INDUCTION,
        DirectorPhase.WORK,
        DirectorPhase.CONSOLIDATION,
        DirectorPhase.EMERGENCE,
    ),
    duration_ratios=(0.02, 0.05, 0.60, 0.28, 0.05),  # 90 min target: ~2 / 4 / 54 / 25 / 5 min
    intensity_profile="flat",
    max_intensity_cycles=1,            # one conditioning pass in CONSOLIDATION
    default_build_up_rate=0.002,
    default_peak_hold_s=1200,          # 20-min conditioning trance window
    default_relax_floor=0.35,
    target_depth_min=0.0,
    target_depth_max=0.55,             # mild-moderate depth; enough for conditioning
    sleep_fork_default=False,
    cycling_phases=(DirectorPhase.CONSOLIDATION,),
)

# Public lookup dict  name → template
ARC_TEMPLATES: dict[str, ArcTemplate] = {
    t.name: t for t in (
        _GENTLE_DESCENT, _WAVE_PATTERN, _DEEP_PLATEAU,
        _CONDITIONING_FOCUS, _SLEEP_BRIDGE,
        _GENUS_DAILY, _GENUS_ENHANCED, _GENUS_AUDIO_ONLY,
        _GENUS_NEUROPROTECTION,
    )
}

# ── SessionDirector ───────────────────────────────────────────────────────────

class SessionDirector:
    """
    Meso-loop session architect (Bible Ch.5 §5.5).

    Called once per second via director.tick(state).
    Returns a dict of live_control.json patches.
    """

    def __init__(self, session_plan: SessionPlan) -> None:
        self.plan           = session_plan
        self.phase_index    = 0
        self.current_phase  = session_plan.phase_plan[0].phase
        self.current_phase_plan = session_plan.phase_plan[0]

        self.session_start_time = time.time()
        self.session_elapsed_s  = 0
        self.phase_elapsed_s    = 0
        self.phase_start_time   = time.time()

        # Intensity state
        self.desired_intensity  = self.current_phase_plan.intensity_target * 0.5
        self.actual_intensity   = 0.0
        self.current_cycle: Optional[IntensityCycle] = None
        self.cycles_completed   = 0

        # Trajectory / feedback state
        self.trance_history:   list[float] = []
        self.trance_score_v2   = 0.0
        self.prev_trance_score = 0.0
        self.heart_rate_deviation = 0.0
        self.hrv_cv            = 0.0
        self.stillness_index   = 1.0
        self.trajectory_status = TrajectoryStatus.CONTINUE
        self.last_trajectory_eval: float = 0.0

        # Work phase trance tracking
        self._work_trance_scores: list[float] = []
        self._peak_depth:         float = 0.0
        self._time_in_deep:       int   = 0
        self._induction_done_at:  Optional[float] = None
        self._peak_reached_at:    Optional[float] = None

        # Pacing state
        self.pace_confidence  = PACE_CONFIDENCE_INITIAL
        self.in_bridge        = False
        self.bridge_start_time = 0.0
        self._pending_next_phase: Optional[DirectorPhase] = None
        self._lead_verify_deadline: float = 0.0

        # Decision log
        self.decisions:        list[DecisionRecord] = []
        self.redirect_count    = 0
        self.induction_attempts = 0

        # InductionRunner (Bible Ch.6 §6.7) — created on first INDUCTION tick
        self._induction_runner: Optional["InductionRunner"] = None
        self._induction_done:   bool = False

        # Signal quality tracking
        self.signal_lost_duration_s = 0
        self.motion_duration_s      = 0

        # Emergence tracking
        self._emergence_start_at:  Optional[float] = None
        self._emergence_hr_dev:    float = 0.0

    # ── Public entry point ────────────────────────────────────────────────────

    def tick(self, state: dict) -> dict:
        """
        Called once per second.  Returns live_control.json patch dict.

        Required state keys (all optional with safe defaults):
          trance_score_v2, autonomic_depth, stillness_index,
          heart_rate, heart_rate_baseline, eeg_signal_lost,
          imu_motion_contaminated, avg_crossmodal_gain,
          content_semantic_density, entrainment_aggressiveness,
          novelty_level, tts_prosodic_intensity,
          conditioning_response, hrv_cv
        """
        self.session_elapsed_s = int(time.time() - self.session_start_time)
        self.phase_elapsed_s   = int(time.time() - self.phase_start_time)

        # ── Update tracked state ──────────────────────────────────────────────
        self.prev_trance_score = self.trance_score_v2
        self.trance_score_v2   = float(state.get("trance_score_v2", 0.0) or 0.0)
        self.trance_history.append(self.trance_score_v2)
        if len(self.trance_history) > TRAJECTORY_WINDOW_S * 2:
            self.trance_history = self.trance_history[-TRAJECTORY_WINDOW_S:]

        self.hrv_cv         = float(state.get("hrv_cv", 0.0) or 0.0)
        self.stillness_index = float(state.get("stillness_index", 1.0) or 1.0)

        hr      = float(state.get("heart_rate", 0.0) or 0.0)
        hr_base = float(state.get("heart_rate_baseline", hr) or hr) or hr
        self.heart_rate_deviation = (
            abs(hr - hr_base) / hr_base if hr_base > 0.0 else 0.0
        )

        # peak / deep tracking
        if self.trance_score_v2 > self._peak_depth:
            self._peak_depth = self.trance_score_v2
        if self.trance_score_v2 >= 0.6:
            self._time_in_deep += 1

        if self.current_phase == DirectorPhase.WORK:
            self._work_trance_scores.append(self.trance_score_v2)

        if (self._induction_done_at is None
                and self.trance_score_v2 >= 0.25
                and self.current_phase != DirectorPhase.ARRIVAL):
            self._induction_done_at = float(self.session_elapsed_s)

        if (self._peak_reached_at is None
                and self.trance_score_v2 >= self.plan.target_peak_depth * 0.9):
            self._peak_reached_at = float(self.session_elapsed_s)

        # ── Signal quality ────────────────────────────────────────────────────
        if state.get("eeg_signal_lost", False):
            self.signal_lost_duration_s += 1
        else:
            self.signal_lost_duration_s = 0

        if state.get("imu_motion_contaminated", False):
            self.motion_duration_s += 1
        else:
            self.motion_duration_s = 0

        # Hold if signal lost too long
        if self.signal_lost_duration_s > SIGNAL_LOST_HOLD_S:
            return self._build_patches()

        # Extend phase when motion contaminated
        if self.motion_duration_s > MOTION_EXTEND_S:
            self.current_phase_plan.target_duration_s = min(
                self.current_phase_plan.max_duration_s,
                self.current_phase_plan.target_duration_s + 1,
            )

        # ── Emergency check ───────────────────────────────────────────────────
        if self._check_emergency():
            self._handle_emergency_emergence()
            return self._build_patches()

        # ── Compute intensity ─────────────────────────────────────────────────
        self.actual_intensity = self._compute_intensity(state)

        # ── Intensity cycling ─────────────────────────────────────────────────
        if self.current_phase in self._cycling_phases() and self.current_cycle is not None:
            self._update_intensity_cycle()

        # ── Enforce monotonic decrease in CONSOLIDATION / EMERGENCE ──────────
        if self.current_phase in (DirectorPhase.CONSOLIDATION,
                                   DirectorPhase.EMERGENCE,
                                   DirectorPhase.SLEEP_TRANSITION,
                                   DirectorPhase.MICRO_CONSOLIDATION):
            self.desired_intensity = min(
                self.desired_intensity,
                self.current_phase_plan.intensity_target,
            )
            self.desired_intensity = max(
                0.0, self.desired_intensity - self.current_phase_plan.intensity_target * 0.002
            )

        # ── Pace confidence decay ─────────────────────────────────────────────
        self._apply_pace_decay()

        # ── Bridge completion ─────────────────────────────────────────────────
        if self.in_bridge:
            if (time.time() - self.bridge_start_time) >= PACE_BRIDGE_DURATION_S:
                self.in_bridge = False
                self._complete_transition()

        # ── Trajectory evaluation (every TRAJECTORY_EVAL_INTERVAL_S seconds) ──
        if (self.session_elapsed_s - self.last_trajectory_eval
                >= TRAJECTORY_EVAL_INTERVAL_S):
            self.trajectory_status = self._evaluate_trajectory()
            self.last_trajectory_eval = self.session_elapsed_s
            self._handle_trajectory(self.trajectory_status)

        # ── Phase transition check ────────────────────────────────────────────
        if not self.in_bridge and self._should_transition():
            next_phase = self._get_next_phase()
            if next_phase is not None:
                self._execute_transition(next_phase)

        # ── InductionRunner tick (Bible Ch.6 §6.7) ─────────────────────────────────────
        induction_patches: dict = {}
        if (
            _INDUCTION_AVAILABLE
            and self.current_phase == DirectorPhase.INDUCTION
            and not self._induction_done
        ):
            if self._induction_runner is None:
                try:
                    selector = StrategySelector(STRATEGY_REGISTRY)
                    ppg_ok   = float(state.get("heart_rate", 0.0) or 0.0) > 0.0
                    ctx = {
                        "session_count":  getattr(self.plan, "session_count", 0),
                        "ppg_available":  ppg_ok,
                        "arc_template":   self.plan.arc_template,
                        "synthetic_board": False,
                    }
                    chosen_id = selector.select_strategy(
                        user_profile={},
                        session_context=ctx,
                    )
                    strategy = STRATEGY_REGISTRY.get(chosen_id)
                    if strategy:
                        self._induction_runner = InductionRunner(strategy=strategy)
                        self.induction_attempts += 1
                        self._log_decision(
                            DecisionType.INDUCTION_STRATEGY,
                            {"strategy": chosen_id},
                            "InductionRunner selected",
                        )
                except Exception:
                    pass

            if self._induction_runner is not None:
                try:
                    eeg_state = {
                        "trance_score_v2": self.trance_score_v2,
                        "alpha_ratio":     float(state.get("alpha_ratio", 0.3) or 0.3),
                        "theta_ratio":     float(state.get("theta_ratio", 0.2) or 0.2),
                    }
                    ppg_state = {
                        "available":     float(state.get("heart_rate", 0.0) or 0.0) > 0.0,
                        "heart_rate":    float(state.get("heart_rate", 0.0) or 0.0),
                        "breath_rate":   float(state.get("breath_rate", 0.0) or 0.0),
                        "hrv_rmssd":     float(state.get("hrv_cv", 0.0) or 0.0) * 100.0,
                    }
                    imu_state = {
                        "stillness_index":               self.stillness_index,
                        "motion_contaminated_consecutive": (
                            1 if state.get("imu_motion_contaminated") else 0
                        ),
                    }
                    result = self._induction_runner.tick(eeg_state, ppg_state, imu_state)
                    induction_patches = self._induction_runner.live_patches

                    if result == "INDUCTION_COMPLETE":
                        self._induction_done = True
                        induction_patches["induction_success"] = True
                    elif result == "REDIRECT":
                        redirect_id = self._induction_runner.redirect_to
                        new_strat = STRATEGY_REGISTRY.get(redirect_id)
                        if new_strat:
                            self._induction_runner = InductionRunner(strategy=new_strat)
                            self.induction_attempts += 1
                            self._log_decision(
                                DecisionType.INDUCTION_STRATEGY,
                                {"strategy": redirect_id, "redirect": True},
                                "InductionRunner redirect",
                            )
                    elif result == "INDUCTION_FAILED":
                        self._induction_done = True
                except Exception:
                    pass

        # ── Sleep fork arming ─────────────────────────────────────────────────
        sleep_armed = (
            self.plan.sleep_fork_enabled
            and self.session_elapsed_s > MIN_SESSION_FOR_SLEEP_FORK_S
        )

        base_patches = self._build_patches(sleep_armed=sleep_armed)
        # InductionRunner patches only add new keys; Director patches take precedence
        merged = {**induction_patches, **base_patches}
        return merged

    def export_session_log(self) -> SessionLog:
        """Build a SessionLog from accumulated internal state, for the Evaluator."""
        now   = time.time()
        dur   = self.session_elapsed_s
        ts    = self.trance_history or [0.0]
        avg_d = sum(ts) / len(ts)
        depth_scores = ts[-60:] if len(ts) >= 60 else ts
        n = len(depth_scores)
        depth_traj = self._linear_regression_slope(depth_scores) if n >= 2 else 0.0

        # Estimate phase durations from decision log
        phase_durations: list[int] = []
        for pp in self.plan.phase_plan:
            phase_durations.append(pp.target_duration_s)  # best we have without timestamps

        return SessionLog(
            started_at=self.session_start_time,
            ended_at=now,
            duration_s=dur,
            arc_template=self.plan.arc_template,
            induction_strategy=self.plan.induction_strategy,
            trance_score_timeseries=list(self.trance_history),
            trance_scores_during_work=list(self._work_trance_scores),
            achieved_peak_depth=self._peak_depth,
            avg_depth=avg_d,
            time_in_deep_s=self._time_in_deep,
            time_to_induction_s=float(self._induction_done_at or 0.0),
            time_to_peak_s=float(self._peak_reached_at or 0.0),
            depth_trajectory_score=float(_clamp(depth_traj * 200, -1.0, 1.0)),
            induction_effectiveness=_clamp(self.trance_score_v2 / 0.6, 0.0, 1.0),
            conditioning_deltas=[],
            phase_durations=phase_durations,
            decisions=list(self.decisions),
            redirect_count=self.redirect_count,
            intensity_cycles_completed=self.cycles_completed,
            pace_confidence_final=self.pace_confidence,
            emergence_hr_deviation=self._emergence_hr_dev,
            final_trance_score=self.trance_score_v2,
            emergence_duration_s=self.phase_elapsed_s
                if self.current_phase == DirectorPhase.EMERGENCE else 0,
            planned_emergence_duration_s=next(
                (pp.target_duration_s for pp in self.plan.phase_plan
                 if pp.phase == DirectorPhase.EMERGENCE), 180
            ),
        )

    # ── Intensity ─────────────────────────────────────────────────────────────

    def _compute_intensity(self, state: dict) -> float:
        ceiling = self.current_phase_plan.gain_ceiling or 1.0
        gain_i  = float(state.get("avg_crossmodal_gain", 0.0) or 0.0) / ceiling
        return _clamp(
            INTENSITY_W_GAIN        * _clamp(gain_i, 0.0, 1.0)
            + INTENSITY_W_CONTENT   * _clamp(float(state.get("content_semantic_density", 0.0) or 0.0), 0.0, 1.0)
            + INTENSITY_W_ENTRAINMENT * _clamp(float(state.get("entrainment_aggressiveness", 0.0) or 0.0), 0.0, 1.0)
            + INTENSITY_W_NOVELTY   * _clamp(float(state.get("novelty_level", 0.0) or 0.0), 0.0, 1.0)
            + INTENSITY_W_TTS       * _clamp(float(state.get("tts_prosodic_intensity", 0.0) or 0.0), 0.0, 1.0),
            0.0, 1.0,
        )

    def _update_intensity_cycle(self) -> None:
        cycle = self.current_cycle
        if cycle is None or cycle.completed:
            return
        cycle.state_elapsed_s += 1

        if cycle.state == IntensityCycleState.BUILD_UP:
            self.desired_intensity = min(
                self.desired_intensity + cycle.build_up_rate,
                cycle.cycle_peak_target,
            )
            at_target = self.actual_intensity >= 0.85 * cycle.cycle_peak_target
            timed_out = cycle.state_elapsed_s >= MAX_BUILD_DURATION_S
            if at_target or timed_out:
                cycle.state = IntensityCycleState.PEAK
                cycle.state_elapsed_s = 0
                self._log_decision(
                    DecisionType.INTENSITY_CHANGE, "PEAK",
                    f"build_up complete: at_target={at_target}, timed_out={timed_out}",
                    self._snapshot(),
                )

        elif cycle.state == IntensityCycleState.PEAK:
            self.desired_intensity = cycle.cycle_peak_target
            hold_done  = cycle.state_elapsed_s >= cycle.peak_hold_s
            surfacing  = (self.trance_score_v2
                          < self.prev_trance_score - SURFACING_THRESHOLD)
            if hold_done or surfacing:
                cycle.state = IntensityCycleState.RELAX
                cycle.state_elapsed_s = 0
                self._log_decision(
                    DecisionType.INTENSITY_CHANGE, "RELAX",
                    f"peak done: hold_done={hold_done}, surfacing={surfacing}",
                    self._snapshot(),
                )

        elif cycle.state == IntensityCycleState.RELAX:
            self.desired_intensity = max(
                self.desired_intensity - cycle.build_up_rate * 0.75,
                cycle.relax_floor,
            )
            min_met      = cycle.state_elapsed_s >= MIN_RELAX_DURATION_S
            floor_reached = self.desired_intensity <= cycle.relax_floor + 0.02
            if min_met and floor_reached:
                cycle.completed = True
                self._start_next_cycle_or_end()

    # ── Pace and transition ───────────────────────────────────────────────────

    def _should_transition(self) -> bool:
        pp = self.current_phase_plan
        if self.phase_elapsed_s >= pp.max_duration_s:
            return True
        if self.phase_elapsed_s < pp.min_duration_s:
            return False
        return self._evaluate_condition(pp.exit_condition)

    def _execute_transition(self, next_phase: DirectorPhase) -> None:
        pace = self._pace_check()
        self._update_pace_confidence(pace)

        if pace.recommended_action == "skip_ahead":
            self._log_decision(
                DecisionType.PHASE_TRANSITION,
                f"skip_to_{next_phase.value}",
                f"user deeper than expected (score={self.trance_score_v2:.2f}), skipping",
                self._snapshot(),
            )
            self._direct_transition(next_phase)

        elif pace.recommended_action == "extend":
            self.current_phase_plan.target_duration_s = min(
                self.current_phase_plan.max_duration_s,
                self.current_phase_plan.target_duration_s + 60,
            )
            self._log_decision(
                DecisionType.PHASE_TRANSITION,
                "extend_current",
                f"user shallower than expected, extending {self.current_phase.value}",
                self._snapshot(),
            )

        else:  # "proceed" or "regress"
            self._pending_next_phase = next_phase
            self.in_bridge = True
            self.bridge_start_time = time.time()
            self._log_decision(
                DecisionType.PHASE_TRANSITION,
                f"bridge_to_{next_phase.value}",
                f"pace check aligned, bridging to {next_phase.value}",
                self._snapshot(),
            )

    def _direct_transition(self, next_phase: DirectorPhase) -> None:
        new_idx = self.phase_index + 1
        # Find the next occurrence of next_phase in the plan from current position
        for i in range(new_idx, len(self.plan.phase_plan)):
            if self.plan.phase_plan[i].phase == next_phase:
                new_idx = i
                break

        if new_idx >= len(self.plan.phase_plan):
            return  # no more phases

        self.phase_index        = new_idx
        self.current_phase      = next_phase
        self.current_phase_plan = self.plan.phase_plan[new_idx]
        self.phase_start_time   = time.time()
        self.phase_elapsed_s    = 0
        self.desired_intensity  = self.current_phase_plan.intensity_target

        if (next_phase == DirectorPhase.INDUCTION
                and self._induction_done_at is None):
            self._induction_done_at = float(self.session_elapsed_s)

        if next_phase == DirectorPhase.EMERGENCE:
            self._emergence_start_at = time.time()

        if next_phase in self._cycling_phases():
            self._start_intensity_cycling()

    def _complete_transition(self) -> None:
        nxt = self._pending_next_phase or self._get_next_phase()
        self._pending_next_phase = None
        if nxt is not None:
            self._direct_transition(nxt)
        self._lead_verify_deadline = time.time() + LEAD_VERIFY_WINDOW_S

    def _pace_check(self) -> PaceResult:
        target   = self.current_phase_plan.intensity_target
        depth_ok = self.trance_score_v2 >= target * 0.8
        hrv_ok   = self.hrv_cv < HRV_STABILITY_THRESHOLD
        still    = self.stillness_index > STILLNESS_THRESHOLD
        aligned  = depth_ok and (hrv_ok or self.hrv_cv == 0.0) and still
        deeper   = self.trance_score_v2 > target * 1.2
        shallower = self.trance_score_v2 < target * 0.5

        if deeper:
            return PaceResult(True, True, False, 0.9, "skip_ahead")
        if aligned:
            return PaceResult(True, False, False, 0.8, "proceed")
        if shallower:
            return PaceResult(False, False, True, 0.7, "extend")
        return PaceResult(False, False, False, 0.5, "extend")

    def _update_pace_confidence(self, result: PaceResult) -> None:
        if result.aligned:
            self.pace_confidence = min(
                PACE_CONFIDENCE_MAX,
                self.pace_confidence + PACE_CONFIDENCE_SUCCESS_BOOST,
            )
        else:
            self.pace_confidence = max(
                PACE_CONFIDENCE_MIN,
                self.pace_confidence - PACE_CONFIDENCE_FAIL_PENALTY,
            )

    def _apply_pace_decay(self) -> None:
        self.pace_confidence = max(
            PACE_CONFIDENCE_MIN,
            self.pace_confidence - PACE_CONFIDENCE_DECAY_RATE,
        )

    # ── Trajectory evaluation ─────────────────────────────────────────────────

    def _evaluate_trajectory(self) -> TrajectoryStatus:
        window   = self.trance_history[-TRAJECTORY_WINDOW_S:] if self.trance_history else []
        slope    = self._linear_regression_slope(window)
        p_ratio  = (self.phase_elapsed_s / self.current_phase_plan.target_duration_s
                    if self.current_phase_plan.target_duration_s > 0 else 1.0)
        s_ratio  = (self.session_elapsed_s / self.plan.estimated_duration_s
                    if self.plan.estimated_duration_s > 0 else 1.0)
        pace_delta = p_ratio - s_ratio
        quality  = _clamp(
            (float(self.signal_lost_duration_s == 0) * 0.5
             + self.stillness_index * 0.3
             + (1.0 - _clamp(self.hrv_cv, 0.0, 1.0)) * 0.2),
            0.0, 1.0,
        )

        # FORK: sleep or emergency
        if self._detect_drowsiness() and self.plan.sleep_fork_enabled:
            if self.session_elapsed_s > MIN_SESSION_FOR_SLEEP_FORK_S:
                return TrajectoryStatus.FORK

        if (self.current_phase == DirectorPhase.WORK
                and self.trance_score_v2 < EMERGENCY_DEPTH_FLOOR
                and self.heart_rate_deviation > HR_SPIKE_THRESHOLD):
            return TrajectoryStatus.FORK

        # REDIRECT: strategy failure
        if (self.current_phase == DirectorPhase.INDUCTION
                and self.phase_elapsed_s > 120
                and self.trance_score_v2 < 0.1):
            return TrajectoryStatus.REDIRECT

        if (self.current_phase in (DirectorPhase.DEEPENING, DirectorPhase.WORK)
                and slope < -DEPTH_DECLINE_THRESHOLD
                and self.phase_elapsed_s > 120):
            return TrajectoryStatus.REDIRECT

        # ACCELERATE
        if (slope > DEPTH_ADVANCE_THRESHOLD
                and self.trance_score_v2 > self.current_phase_plan.intensity_target * 0.9
                and pace_delta < -0.15):
            return TrajectoryStatus.ACCELERATE

        # DECELERATE
        if (slope < 0 and pace_delta > 0.2) or quality < 0.5:
            return TrajectoryStatus.DECELERATE

        return TrajectoryStatus.CONTINUE

    def _handle_trajectory(self, status: TrajectoryStatus) -> None:
        if status == TrajectoryStatus.CONTINUE:
            return

        if status == TrajectoryStatus.ACCELERATE:
            remaining = self._remaining_phases()
            for pp in remaining:
                pp.target_duration_s = max(
                    pp.min_duration_s,
                    int(pp.target_duration_s * 0.85),
                )
            self._log_decision(
                DecisionType.TRAJECTORY, "ACCELERATE",
                "ahead of schedule, compressing remaining phases",
                self._snapshot(),
            )

        elif status == TrajectoryStatus.DECELERATE:
            self.current_phase_plan.target_duration_s = min(
                self.current_phase_plan.max_duration_s,
                int(self.current_phase_plan.target_duration_s * 1.25),
            )
            self.desired_intensity *= 0.9
            self._log_decision(
                DecisionType.TRAJECTORY, "DECELERATE",
                "behind schedule or signal issues, extending phase",
                self._snapshot(),
            )

        elif status == TrajectoryStatus.REDIRECT:
            self._handle_redirect("trajectory_eval_failure")

        elif status == TrajectoryStatus.FORK:
            if self._detect_drowsiness():
                self._handle_sleep_fork()
            else:
                self._handle_emergency_emergence()

    # ── Redirect, sleep fork, emergency ──────────────────────────────────────

    def _handle_redirect(self, reason: str) -> None:
        self.redirect_count += 1

        if self.current_phase == DirectorPhase.INDUCTION:
            self.induction_attempts += 1
            if self.induction_attempts <= INDUCTION_RETRY_LIMIT:
                alt = self._pick_alternative_induction()
                self._log_decision(
                    DecisionType.REDIRECT,
                    f"induction_switch_to_{alt}",
                    f"induction failing at {self.phase_elapsed_s}s, attempt "
                    f"{self.induction_attempts}, switching to {alt}",
                    self._snapshot(),
                )
                self.phase_start_time = time.time()
                self.current_phase_plan.content_pools = [f"induction_{alt}"]
            else:
                if "induction_failure" in self.plan.contingency_branches:
                    self._apply_contingency("induction_failure")

        elif self.current_phase in (DirectorPhase.DEEPENING, DirectorPhase.WORK):
            current_pools = set(self.current_phase_plan.content_pools)
            alt_pools = [p for p in self.plan.priority_pools if p not in current_pools]
            if alt_pools:
                self.current_phase_plan.content_pools = alt_pools[:3]
                self._log_decision(
                    DecisionType.POOL_SWITCH,
                    str(alt_pools[:3]),
                    f"depth declining in {self.current_phase.value}, switching pools",
                    self._snapshot(),
                )
            self.desired_intensity *= 0.85

    def _handle_sleep_fork(self) -> None:
        self._log_decision(
            DecisionType.SLEEP_FORK, "engage",
            f"drowsiness detected at {self.session_elapsed_s}s, forking to SLEEP_TRANSITION",
            self._snapshot(),
        )
        sleep_pp = PhasePlan(
            phase=DirectorPhase.SLEEP_TRANSITION,
            target_duration_s=600, min_duration_s=120, max_duration_s=900,
            entry_condition="drowsiness_sustained",
            exit_condition="handoff_to_doc39",
            intensity_target=0.15,
            content_pools=["sleep_bridge"],
            gain_ceiling=0.3,
        )
        self.plan.phase_plan.insert(self.phase_index + 1, sleep_pp)
        self._direct_transition(DirectorPhase.SLEEP_TRANSITION)

    def _handle_emergency_emergence(self) -> None:
        self._log_decision(
            DecisionType.PHASE_TRANSITION, "emergency_emergence",
            f"emergency: depth={self.trance_score_v2:.2f}, "
            f"hr_dev={self.heart_rate_deviation:.2f}",
            self._snapshot(),
        )
        em_pp = PhasePlan(
            phase=DirectorPhase.EMERGENCE,
            target_duration_s=180, min_duration_s=60, max_duration_s=300,
            entry_condition="emergency",
            exit_condition="trance_score_v2 < 0.1",
            intensity_target=0.0,
            content_pools=["emergence_gentle"],
            gain_ceiling=0.2,
        )
        self.phase_index = len(self.plan.phase_plan)
        self.plan.phase_plan.append(em_pp)
        self.current_phase      = DirectorPhase.EMERGENCE
        self.current_phase_plan = em_pp
        self.phase_start_time   = time.time()
        self.desired_intensity  = 0.0

    def _apply_contingency(self, branch: str) -> None:
        branch_plans = self.plan.contingency_branches.get(branch, [])
        if not branch_plans:
            return
        self.plan.phase_plan[self.phase_index + 1: self.phase_index + 1] = branch_plans
        self._log_decision(
            DecisionType.REDIRECT, f"contingency:{branch}",
            f"applying contingency branch: {branch}",
            self._snapshot(),
        )

    # ── Safety and helpers ────────────────────────────────────────────────────

    def _check_emergency(self) -> bool:
        vulnerable = self.current_phase in (
            DirectorPhase.WORK, DirectorPhase.DEEPENING, DirectorPhase.WORK_BLOCK,
        )
        return (vulnerable
                and self.trance_score_v2 < EMERGENCY_DEPTH_FLOOR
                and self.heart_rate_deviation > HR_SPIKE_THRESHOLD)

    def _detect_drowsiness(self) -> bool:
        """Proxy: low trance score + very slow progression in late session."""
        return (self.session_elapsed_s > 1200
                and self.trance_score_v2 < 0.15
                and self.stillness_index > 0.8)

    def _pick_alternative_induction(self) -> str:
        current = self.plan.induction_strategy
        alts = [s for s in INDUCTION_STRATEGIES if s != current]
        return random.choice(alts) if alts else current

    def _remaining_phases(self) -> list[PhasePlan]:
        return self.plan.phase_plan[self.phase_index + 1:]

    def _get_next_phase(self) -> Optional[DirectorPhase]:
        idx = self.phase_index + 1
        if idx < len(self.plan.phase_plan):
            return self.plan.phase_plan[idx].phase
        return None

    def _cycling_phases(self) -> tuple[DirectorPhase, ...]:
        template = ARC_TEMPLATES.get(self.plan.arc_template)
        return template.cycling_phases if template else ()

    def _start_intensity_cycling(self) -> None:
        template = ARC_TEMPLATES.get(self.plan.arc_template)
        if template is None:
            return
        self.current_cycle = IntensityCycle(
            cycle_index=self.cycles_completed,
            cycle_peak_target=self.current_phase_plan.intensity_target,
            build_up_rate=template.default_build_up_rate,
            peak_hold_s=template.default_peak_hold_s,
            relax_floor=template.default_relax_floor,
            state=IntensityCycleState.BUILD_UP,
        )

    def _start_next_cycle_or_end(self) -> None:
        template = ARC_TEMPLATES.get(self.plan.arc_template)
        self.cycles_completed += 1
        if template and self.cycles_completed < template.max_intensity_cycles:
            self._start_intensity_cycling()
        else:
            self.current_cycle = None

    def _compute_plan_adherence(self) -> float:
        if self.current_phase_plan.target_duration_s <= 0:
            return 1.0
        ratio = self.phase_elapsed_s / self.current_phase_plan.target_duration_s
        return _clamp(1.0 - abs(1.0 - ratio), 0.0, 1.0)

    def _evaluate_condition(self, condition: str) -> bool:
        """
        Safe condition evaluator (no eval()).
        Handles the condition strings defined in _PHASE_EXIT_CONDITIONS.
        """
        cond = condition.lower()

        if "handoff_to_doc39" in cond:
            return False  # sleep handoff is handled by trajectory FORK

        if "trance_score_v2 >= 0.25" in cond:
            if self.trance_score_v2 < 0.25:
                return False

        if "trance_score_v2 < 0.1" in cond:
            if self.trance_score_v2 >= 0.1:
                return False

        if "target_peak_depth_x0.8" in cond:
            target = self.plan.target_peak_depth * 0.8
            cycling_done = (self.current_cycle is None
                            or self.cycles_completed > 0)
            if self.trance_score_v2 < target or not cycling_done:
                return False

        if "intensity < 0.2" in cond:
            if self.actual_intensity >= 0.2:
                return False

        if "cycles_complete" in cond:
            # Allow forward even if cycling isn't done, once target_duration is met
            pass

        if "baseline_complete" in cond:
            return self.phase_elapsed_s >= self.current_phase_plan.min_duration_s

        # Fallback: time-based
        return self.phase_elapsed_s >= self.current_phase_plan.target_duration_s

    @staticmethod
    def _linear_regression_slope(values: list[float]) -> float:
        n = len(values)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n
        num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        den = sum((i - x_mean) ** 2 for i in range(n))
        return num / den if den != 0 else 0.0

    def _log_decision(
        self,
        decision_type: DecisionType,
        value: str,
        rationale: str,
        state_snapshot: dict,
        authority_level: int = 1,
    ) -> None:
        self.decisions.append(DecisionRecord(
            timestamp=time.time(),
            decision_type=decision_type,
            decision_value=value,
            authority_level=authority_level,
            rationale=rationale,
            state_snapshot=state_snapshot,
        ))

    def _snapshot(self) -> dict:
        return {
            "trance_score":     self.trance_score_v2,
            "phase":            self.current_phase.value,
            "intensity":        round(self.actual_intensity, 3),
            "desired_intensity": round(self.desired_intensity, 3),
            "pace_confidence":  round(self.pace_confidence, 3),
            "session_elapsed":  self.session_elapsed_s,
            "phase_elapsed":    self.phase_elapsed_s,
        }

    def _build_patches(self, sleep_armed: bool = False) -> dict:
        remaining_phase = max(
            0, self.current_phase_plan.target_duration_s - self.phase_elapsed_s,
        )
        remaining_session = max(
            0, self.plan.estimated_duration_s - self.session_elapsed_s,
        )
        next_phase = self._get_next_phase()
        return {
            "director_phase":               self.current_phase.value,
            "director_intensity":           round(self.actual_intensity, 3),
            "director_intensity_target":    round(self.desired_intensity, 3),
            "director_intensity_cycle_state": (
                self.current_cycle.state.value
                if self.current_cycle else IntensityCycleState.BUILD_UP.value
            ),
            "director_pace_confidence":     round(self.pace_confidence, 3),
            "director_plan_adherence":      round(self._compute_plan_adherence(), 3),
            "director_trajectory_status":   self.trajectory_status.value,
            "director_phase_elapsed_s":     self.phase_elapsed_s,
            "director_phase_remaining_s":   remaining_phase,
            "director_session_elapsed_s":   self.session_elapsed_s,
            "director_session_remaining_s": remaining_session,
            "director_depth_target":        round(self.plan.target_peak_depth, 3),
            "director_current_arc":         self.plan.arc_template,
            "director_sleep_fork_armed":    sleep_armed,
            "director_active_pools":        list(self.current_phase_plan.content_pools),
            "director_gain_ceiling":        round(self.current_phase_plan.gain_ceiling, 3),
            "director_next_phase":          next_phase.value if next_phase else "",
            "director_redirect_count":      self.redirect_count,
        }
