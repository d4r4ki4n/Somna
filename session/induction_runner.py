"""
session/induction_runner.py — Induction Strategy Library (Bible Ch.6 §6.7)
==================================================================
Eight fully-specified hypnotic induction strategies, a StrategySelector that
picks the right one for the current user and session context, and an
InductionRunner that executes the selected strategy in real time.

Architecture:
  SessionDirector.tick() ──► InductionRunner.tick(eeg, ppg, imu)
                                 │
                                 ├─ _apply_stimulus() → live_control patches
                                 ├─ _check_success()  → 'INDUCTION_COMPLETE'
                                 ├─ _check_failure()  → 'REDIRECT' | 'INDUCTION_FAILED'
                                 └─ _advance_phase()  → next micro-phase

All eight strategies are aphantasia-first (Bible Ch.6 §6.7 §1.1 / Appendix C).
No strategy uses visual imagery, staircases, beaches, or visualization.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class InductionPhase:
    phase_name:        str
    duration_range_s:  tuple[int, int]
    target_eeg_state:  dict
    stimulus_params:   dict       # layer → {live_control_key: value}
    transition_trigger: str
    timeout_action:    str        # "advance" | "extend" | "fail"


@dataclass
class InductionStrategy:
    strategy_id:              str
    display_name:             str
    description:              str
    gruzelier_emphasis:       str   # "STAGE_I" | "STAGE_II" | "STAGE_I_II"
    primary_mechanism:        str
    expected_time_to_trance_s: tuple[int, int]
    phase_sequence:           list[InductionPhase]
    stimulus_config:          dict
    success_criteria:         dict
    failure_criteria:         dict
    redirect_strategy:        Optional[str]
    contraindications:        list[str]
    conditioning_hooks:       dict
    session_count_unlock:     int = 0


# ── Strategy definitions ──────────────────────────────────────────────────────

ENTRAINMENT_HEAVY = InductionStrategy(
    strategy_id="ENTRAINMENT_HEAVY",
    display_name="Neural Frequency Lock",
    description="IAF-matched multi-channel entrainment drives cortical oscillations toward theta via FFR.",
    gruzelier_emphasis="STAGE_I",
    primary_mechanism=(
        "ASSR + VSSR crossmodal frequency following response. IAF-matched entrainment "
        "locks alpha then ramps down toward upper theta, triggering Stage II naturally."
    ),
    expected_time_to_trance_s=(120, 300),
    redirect_strategy="BREATH_LEAD",
    contraindications=["photosensitive_epilepsy", "user_preference_no_strobe"],
    conditioning_hooks={
        "entrainment_onset_cs": "isochronic_pulse_pattern",
        "frequency_descent_cs": "theta_relaxation_ur",
    },
    session_count_unlock=0,
    stimulus_config={},
    success_criteria={
        "trance_score_v2_min": 0.45,
        "convergence_rule": "2_of_3_axes",
        "sustain_duration_s": 15,
    },
    failure_criteria={
        "trance_score_v2_below": 0.20,
        "after_elapsed_s": 240,
    },
    phase_sequence=[
        InductionPhase(
            phase_name="CAPTURE",
            duration_range_s=(30, 60),
            target_eeg_state={"alpha_power": "above_baseline", "frontal_theta": "onset"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf", "am_depth": 0.6},
                "visual":      {"spiral_speed_multiplier": 1.0, "veil_opacity": 20},
                "audio":       {"volume": 45},
            },
            transition_trigger="alpha_coherence > 0.6 sustained 10s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="DESCEND",
            duration_range_s=(60, 120),
            target_eeg_state={"theta_alpha_ratio": "increasing", "paf": "slowing"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf_minus_2", "am_depth": 0.7},
                "visual":      {"bg_ganzfeld_gain": 0.3, "bg_color_temp_k": 4000,
                                "spiral_speed_multiplier": 0.8},
                "audio":       {"volume": 50},
            },
            transition_trigger="theta_alpha_ratio > 0.7 sustained 10s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="THETA_FLOOR",
            duration_range_s=(30, 90),
            target_eeg_state={"theta_power": "sustained", "beta_suppression": "< 0.3"},
            stimulus_params={
                "entrainment": {"am_depth": 0.75},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.15},
                "visual":      {"veil_opacity": 35},
            },
            transition_trigger="trance_score_v2 >= 0.40 sustained 10s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="STABILIZE",
            duration_range_s=(30, 60),
            target_eeg_state={"theta": "dominant", "variance": "low"},
            stimulus_params={
                "entrainment": {"am_depth": 0.6},
                "audio":       {"volume": 40},
            },
            transition_trigger="trance_score_v2 >= 0.45 sustained 15s",
            timeout_action="advance",
        ),
    ],
)


SOMATIC_ANCHOR = InductionStrategy(
    strategy_id="SOMATIC_ANCHOR",
    display_name="Body Awareness Descent",
    description="Progressive interoceptive attention narrowing drives parasympathetic dominance and frontolimbic inhibition.",
    gruzelier_emphasis="STAGE_II",
    primary_mechanism=(
        "Directing attention through body regions activates insular cortex and reduces "
        "prefrontal executive activity via Golgi tendon reflex relaxation cascade."
    ),
    expected_time_to_trance_s=(180, 420),
    redirect_strategy="BREATH_LEAD",
    contraindications=["somatic_hypervigilance", "chronic_pain_body_focus_aversive"],
    conditioning_hooks={
        "body_scan_cs": "relaxation_response_ur",
        "anchor_point_cs": "depth_ur",
    },
    session_count_unlock=0,
    stimulus_config={},
    success_criteria={
        "trance_score_v2_min": 0.40,
        "ppg_hrv_rmssd": "increasing_trend",
        "imu_stillness_index_min": 0.85,
    },
    failure_criteria={
        "imu_motion_contaminated": True,
        "consecutive_ticks": 3,
        "after_phase": "SCAN_DESCEND",
    },
    phase_sequence=[
        InductionPhase(
            phase_name="GROUND",
            duration_range_s=(30, 60),
            target_eeg_state={"alpha_power": "above_baseline"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf", "am_depth": 0.4},
                "visual":      {"bg_ganzfeld_gain": 0.25, "bg_color_temp_k": 4200},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.20},
            },
            transition_trigger="alpha_power increase detected OR elapsed > 45s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="SCAN_DESCEND",
            duration_range_s=(60, 120),
            target_eeg_state={"theta_alpha_ratio": "rising", "beta": "decreasing"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf_minus_1", "am_depth": 0.5},
                "visual":      {"veil_opacity": 25, "pp_blur_radius": 0.5},
                "content":     {"active_pool": "warmth_comfort", "tts_gain": 0.20},
            },
            transition_trigger="theta_alpha_ratio > 0.5 OR body_scan_complete",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="ANCHOR_DEEPEN",
            duration_range_s=(60, 120),
            target_eeg_state={"frontal_midline_theta": "above_baseline"},
            stimulus_params={
                "entrainment": {"am_depth": 0.55},
                "visual":      {"veil_opacity": 30},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.18},
            },
            transition_trigger="trance_score_v2 >= 0.35 sustained 10s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="DISSOLVE",
            duration_range_s=(30, 90),
            target_eeg_state={"theta": "dominant", "beta_suppression": "< 0.25"},
            stimulus_params={
                "entrainment": {"am_depth": 0.6},
                "visual":      {"pp_blur_radius": 2.0, "bg_ganzfeld_gain": 0.4},
                "content":     {"active_pool": "dissolution", "tts_gain": 0.10},
            },
            transition_trigger="trance_score_v2 >= 0.40 sustained 10s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="STABILIZE",
            duration_range_s=(30, 60),
            target_eeg_state={"theta": "dominant", "variance": "low"},
            stimulus_params={
                "entrainment": {"am_depth": 0.5},
            },
            transition_trigger="trance_score_v2 >= 0.40 sustained 15s imu_stillness >= 0.85",
            timeout_action="advance",
        ),
    ],
)


BREATH_LEAD = InductionStrategy(
    strategy_id="BREATH_LEAD",
    display_name="Respiratory Pacing",
    description="Pace-then-lead toward resonance frequency (~6 bpm) amplifies RSA and vagal tone.",
    gruzelier_emphasis="STAGE_I_II",
    primary_mechanism=(
        "RSA amplification via resonance frequency paced breathing (~0.1 Hz). "
        "Vagal surge → parasympathetic dominance. Ericksonian pace-then-lead principle."
    ),
    expected_time_to_trance_s=(150, 360),
    redirect_strategy="SOMATIC_ANCHOR",
    contraindications=["respiratory_distress", "breath_focus_aversive"],
    conditioning_hooks={
        "paced_breathing_cs": "parasympathetic_dominance_ur",
        "exhale_phase_cs": "suggestion_receptivity_ur",
    },
    session_count_unlock=0,
    stimulus_config={"requires_ppg": True},
    success_criteria={
        "trance_score_v2_min": 0.35,
        "ppg_breath_rate_within": 0.5,
        "ppg_hrv_rmssd_increase_pct": 15,
    },
    failure_criteria={
        "ppg_breath_rate_not_decreasing_after_s": 120,
        "phase": "LEAD_DOWN",
    },
    phase_sequence=[
        InductionPhase(
            phase_name="PACE",
            duration_range_s=(30, 60),
            target_eeg_state={"alpha": "stable"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf", "am_depth": 0.3},
                "visual":      {"bg_ganzfeld_gain": 0.2},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.18},
            },
            transition_trigger="ppg_breath_rate stable variance < 0.3 for 20s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="LEAD_DOWN",
            duration_range_s=(60, 120),
            target_eeg_state={"alpha": "increasing", "theta": "onset"},
            stimulus_params={
                "entrainment": {"beat_frequency": "ramp_to_iaf_minus_1.5", "am_depth": 0.45},
                "visual":      {"bg_ganzfeld_gain": 0.3},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.18},
            },
            transition_trigger="ppg_breath_rate within 1.0 bpm of target",
            timeout_action="extend",
        ),
        InductionPhase(
            phase_name="COHERE",
            duration_range_s=(60, 120),
            target_eeg_state={"theta_alpha_ratio": "> 0.6", "frontal_midline_theta": "up"},
            stimulus_params={
                "entrainment": {"am_depth": 0.55},
                "content":     {"active_pool": "warmth_comfort", "tts_gain": 0.15},
            },
            transition_trigger="ppg_hrv_rmssd > baseline + 15% sustained 15s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="DEEPEN",
            duration_range_s=(30, 90),
            target_eeg_state={"theta": "dominant"},
            stimulus_params={
                "entrainment": {"beat_frequency": "theta_target", "am_depth": 0.6},
                "visual":      {"pp_blur_radius": 1.5},
                "content":     {"active_pool": "dissolution", "tts_gain": 0.12},
            },
            transition_trigger="trance_score_v2 >= 0.35 sustained 10s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="STABILIZE",
            duration_range_s=(30, 60),
            target_eeg_state={"theta": "stable", "variance": "low"},
            stimulus_params={},
            transition_trigger="trance_score_v2 >= 0.35 ppg_breath_rate stable ppg_hrv_rmssd up",
            timeout_action="advance",
        ),
    ],
)


PROGRESSIVE_RELAXATION = InductionStrategy(
    strategy_id="PROGRESSIVE_RELAXATION",
    display_name="Tension-Release Cascade",
    description="Jacobson PMR adapted for audio delivery — GTOs trigger reflex relaxation cascading through ANS.",
    gruzelier_emphasis="STAGE_II",
    primary_mechanism=(
        "Golgi tendon organ reflex cascade from voluntary tension-release cycles. "
        "Parasympathetic rebound after each release deepens cumulatively."
    ),
    expected_time_to_trance_s=(240, 480),
    redirect_strategy="ENTRAINMENT_HEAVY",
    contraindications=["chronic_pain_tension_contraindicated", "mobility_limitations"],
    conditioning_hooks={
        "tension_release_cs": "deep_relaxation_ur",
        "sequential_release_cs": "progressive_depth_ur",
    },
    session_count_unlock=0,
    stimulus_config={},
    success_criteria={
        "trance_score_v2_min": 0.35,
        "imu_stillness_index_min": 0.90,
        "ppg_hrv_rmssd_increase_pct": 20,
    },
    failure_criteria={
        "trance_score_v2_below": 0.15,
        "after_elapsed_s": 360,
    },
    phase_sequence=[
        InductionPhase(
            phase_name="ORIENT",
            duration_range_s=(20, 40),
            target_eeg_state={"baseline": "capture"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf", "am_depth": 0.25},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.20},
            },
            transition_trigger="elapsed > 25s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="TENSION_CYCLE",
            duration_range_s=(120, 240),
            target_eeg_state={"alpha": "increasing", "beta": "decreasing"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf", "am_depth": 0.4},
                "visual":      {"bg_ganzfeld_gain": 0.25, "bg_color_temp_k": 3800},
                "content":     {"active_pool": "grounding_texture", "tts_gain": 0.22},
            },
            transition_trigger="all_muscle_groups_completed AND alpha_power > baseline + 20%",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="PASSIVE_DESCENT",
            duration_range_s=(60, 120),
            target_eeg_state={"theta_alpha_ratio": "> 0.6", "beta_suppression": "strong"},
            stimulus_params={
                "entrainment": {"beat_frequency": "theta_target", "am_depth": 0.55},
                "visual":      {"pp_blur_radius": 1.5, "veil_opacity": 30},
                "content":     {"active_pool": "warmth_comfort", "tts_gain": 0.18},
            },
            transition_trigger="trance_score_v2 >= 0.30 sustained 10s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="STABILIZE",
            duration_range_s=(30, 60),
            target_eeg_state={"theta": "dominant", "variance": "low"},
            stimulus_params={},
            transition_trigger="trance_score_v2 >= 0.35 imu_stillness >= 0.90",
            timeout_action="advance",
        ),
    ],
)


COGNITIVE_OVERLOAD = InductionStrategy(
    strategy_id="COGNITIVE_OVERLOAD",
    display_name="Saturation Gate",
    description="Multi-channel saturation exhausts prefrontal control; sudden simplification creates relief-gate trance entry.",
    gruzelier_emphasis="STAGE_I",
    primary_mechanism=(
        "Ericksonian confusion technique. Simultaneous stimulus saturation exhausts "
        "working memory → executive fatigue → relief-gate contrast → instant trance entry."
    ),
    expected_time_to_trance_s=(90, 240),
    redirect_strategy="SOMATIC_ANCHOR",
    contraindications=[
        "anxiety_disorder", "sensory_processing_sensitivity",
        "first_session", "user_preference_gentle",
    ],
    conditioning_hooks={
        "overload_onset_cs": "relief_anticipation_ur",
        "relief_gate_cs": "instant_depth_ur",
    },
    session_count_unlock=3,
    stimulus_config={},
    success_criteria={
        "trance_score_v2_min": 0.40,
        "sustain_duration_s": 15,
    },
    failure_criteria={
        "trance_score_v2_below": 0.20,
        "after_elapsed_s": 240,
    },
    phase_sequence=[
        InductionPhase(
            phase_name="LAYER_BUILD",
            duration_range_s=(20, 40),
            target_eeg_state={"beta": "above_baseline"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf", "am_depth": 0.4, "binaural_blend": 0.5},
                "visual":      {"spiral_speed_multiplier": 1.2, "fractal_edge_amplitude": 0.3},
                "content":     {"active_pool": "identity", "tts_gain": 0.25},
            },
            transition_trigger="beta_power > baseline + 30%",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="SATURATE",
            duration_range_s=(30, 90),
            target_eeg_state={"beta": "high_then_declining"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf", "am_depth": 0.5},
                "visual":      {"spiral_speed_multiplier": 1.4, "fractal_edge_amplitude": 0.6,
                                "noise_spectral_tilt": 0.8},
                "content":     {"active_pool": "identity", "tts_gain": 0.28},
                "spatial":     {"spatial_asmr_gain": 0.3},
            },
            transition_trigger="beta_power begins declining from plateau",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="RELIEF_GATE",
            duration_range_s=(10, 20),
            target_eeg_state={"alpha": "spike", "theta": "onset"},
            stimulus_params={
                "entrainment": {"beat_frequency": 6.0, "am_depth": 0.5, "binaural_blend": 1.0},
                "visual":      {"spiral_speed_multiplier": 0.3, "fractal_edge_amplitude": 0.0,
                                "bg_ganzfeld_gain": 0.6, "veil_opacity": 10},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.20},
                "spatial":     {"spatial_asmr_gain": 0.0},
            },
            transition_trigger="alpha_spike detected AND theta_onset",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="CAPTURE_DESCENT",
            duration_range_s=(30, 60),
            target_eeg_state={"theta": "rising", "alpha": "settling"},
            stimulus_params={
                "entrainment": {"beat_frequency": "theta_target", "am_depth": 0.55},
                "visual":      {"pp_blur_radius": 1.5},
                "content":     {"active_pool": "warmth_comfort", "tts_gain": 0.15},
            },
            transition_trigger="trance_score_v2 >= 0.35 sustained 10s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="STABILIZE",
            duration_range_s=(30, 60),
            target_eeg_state={"theta": "dominant", "variance": "low"},
            stimulus_params={},
            transition_trigger="trance_score_v2 >= 0.40 sustained 15s",
            timeout_action="advance",
        ),
    ],
)


FRACTIONATION = InductionStrategy(
    strategy_id="FRACTIONATION",
    display_name="Depth Ratchet",
    description="Induction-emergence-reinduction cycles exploit homoaction to achieve progressively greater depth.",
    gruzelier_emphasis="STAGE_I_II",
    primary_mechanism=(
        "Vogt fractionation homoaction principle. Residual trance carry-forward means "
        "each reinduction is faster and achieves greater depth than the last."
    ),
    expected_time_to_trance_s=(180, 360),
    redirect_strategy="ENTRAINMENT_HEAVY",
    contraindications=["first_2_sessions"],
    conditioning_hooks={
        "reinduction_cue_cs": "rapid_depth_ur",
        "emergence_partial_cs": "depth_anticipation_ur",
    },
    session_count_unlock=2,
    stimulus_config={},
    success_criteria={
        "trance_score_v2_min": 0.50,
        "ratchet_verified": "each_reinduction_peak_gt_previous",
        "sustain_duration_s": 15,
    },
    failure_criteria={
        "trance_score_v2_below": 0.25,
        "after_elapsed_s": 360,
    },
    phase_sequence=[
        InductionPhase(
            phase_name="FIRST_INDUCTION",
            duration_range_s=(60, 90),
            target_eeg_state={"alpha": "up", "theta": "onset"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf", "am_depth": 0.4},
                "visual":      {"bg_ganzfeld_gain": 0.2},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.20},
            },
            transition_trigger="trance_score_v2 >= 0.20",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="EMERGENCE_1",
            duration_range_s=(15, 20),
            target_eeg_state={"alpha": "increasing", "theta": "decreasing"},
            stimulus_params={
                "entrainment": {"beat_frequency": 14.0, "am_depth": 0.2},
                "visual":      {"bg_ganzfeld_gain": 0.05, "bg_color_temp_k": 5500},
                "content":     {"active_pool": "ambient_support", "tts_gain": 0.18},
            },
            transition_trigger="alpha_power > theta_power",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="RE_INDUCTION_1",
            duration_range_s=(40, 60),
            target_eeg_state={"theta": "above_previous_peak"},
            stimulus_params={
                "entrainment": {"beat_frequency": "ramp_fast", "am_depth": 0.55},
                "visual":      {"bg_ganzfeld_gain": 0.35, "spiral_speed_multiplier": 0.7},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.18},
            },
            transition_trigger="trance_score_v2 >= previous_peak + 0.10",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="EMERGENCE_2",
            duration_range_s=(10, 15),
            target_eeg_state={"alpha": "uptick"},
            stimulus_params={
                "entrainment": {"beat_frequency": 13.0, "am_depth": 0.2},
                "visual":      {"bg_ganzfeld_gain": 0.1},
            },
            transition_trigger="alpha_power uptick detected",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="RE_INDUCTION_2",
            duration_range_s=(30, 45),
            target_eeg_state={"theta": "dominant", "deep": True},
            stimulus_params={
                "entrainment": {"beat_frequency": "ramp_fastest", "am_depth": 0.65},
                "visual":      {"pp_blur_radius": 2.0, "bg_ganzfeld_gain": 0.5,
                                "spiral_speed_multiplier": 0.5},
                "content":     {"active_pool": "dissolution", "tts_gain": 0.15},
            },
            transition_trigger="trance_score_v2 >= previous_peak + 0.10",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="STABILIZE",
            duration_range_s=(30, 60),
            target_eeg_state={"theta": "dominant", "stable": True},
            stimulus_params={},
            transition_trigger="trance_score_v2 >= 0.50 sustained 15s",
            timeout_action="advance",
        ),
    ],
)


FIXATION_FADE = InductionStrategy(
    strategy_id="FIXATION_FADE",
    display_name="Attentional Narrowing",
    description="Sustained foveal fixation induces Troxler fading, retinal fatigue, and thalamic gating → depth.",
    gruzelier_emphasis="STAGE_I",
    primary_mechanism=(
        "Troxler fading + retinal fatigue + TRN sensory gating from sustained fixation "
        "on spiral centre. Natural eye fatigue → eye closure → classical Stage I→II transition."
    ),
    expected_time_to_trance_s=(120, 300),
    redirect_strategy="SOMATIC_ANCHOR",
    contraindications=["eye_conditions", "user_preference_no_strobe", "vr_mode"],
    conditioning_hooks={
        "fixation_point_cs": "eye_fatigue_ur",
        "eye_closure_cs": "depth_onset_ur",
    },
    session_count_unlock=0,
    stimulus_config={},
    success_criteria={
        "trance_score_v2_min": 0.35,
        "sustain_duration_s": 15,
    },
    failure_criteria={
        "trance_score_v2_below": 0.15,
        "after_elapsed_s": 300,
    },
    phase_sequence=[
        InductionPhase(
            phase_name="FIXATE",
            duration_range_s=(30, 60),
            target_eeg_state={"alpha": "stable", "frontal_midline_theta": "onset"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf", "am_depth": 0.3},
                "visual":      {"spiral_speed_multiplier": 0.9, "pp_iaf_mod_amplitude": 0.02},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.16},
            },
            transition_trigger="frontal_midline_theta > baseline + 15%",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="FADE",
            duration_range_s=(30, 60),
            target_eeg_state={"alpha": "increasing"},
            stimulus_params={
                "entrainment": {"am_depth": 0.4},
                "visual":      {"pp_vignette_intensity": 0.4, "bg_ganzfeld_gain": 0.15,
                                "spiral_speed_multiplier": 0.7},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.15},
            },
            transition_trigger="alpha_power > baseline + 25%",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="CLOSE",
            duration_range_s=(20, 40),
            target_eeg_state={"alpha": "spike", "theta": "onset"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf_minus_2", "am_depth": 0.5},
                "visual":      {"pp_blur_radius": 2.5, "bg_ganzfeld_gain": 0.6,
                                "bg_color_temp_k": 3600},
                "spatial":     {"spatial_shepard_gain": 0.3},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.18},
            },
            transition_trigger="alpha_spike detected",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="DESCENT",
            duration_range_s=(30, 90),
            target_eeg_state={"theta": "rising", "alpha": "settling"},
            stimulus_params={
                "entrainment": {"beat_frequency": "theta_target", "am_depth": 0.55},
                "visual":      {"veil_opacity": 30},
                "content":     {"active_pool": "warmth_comfort", "tts_gain": 0.15},
            },
            transition_trigger="trance_score_v2 >= 0.30 sustained 10s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="STABILIZE",
            duration_range_s=(30, 60),
            target_eeg_state={"theta": "dominant", "variance": "low"},
            stimulus_params={},
            transition_trigger="trance_score_v2 >= 0.35 sustained 15s",
            timeout_action="advance",
        ),
    ],
)


PACE_AND_LEAD = InductionStrategy(
    strategy_id="PACE_AND_LEAD",
    display_name="Physiological Mirror",
    description="Real-time biofeedback-driven Ericksonian pacing builds yes-set frame, then leads state toward trance.",
    gruzelier_emphasis="STAGE_I_II",
    primary_mechanism=(
        "Accurate physiological pacing (EEG/PPG/IMU truisms) establishes unconscious "
        "agreement frame. Leading statements guide physiological shift toward trance. "
        "Non-Awareness Set creates mild dissociative shift. Requires real PPG."
    ),
    expected_time_to_trance_s=(150, 360),
    redirect_strategy="ENTRAINMENT_HEAVY",
    contraindications=["ppg_available_false", "synthetic_board_mode"],
    conditioning_hooks={
        "pacing_accuracy_cs": "trust_response_ur",
        "leading_suggestion_cs": "physiological_compliance_ur",
    },
    session_count_unlock=1,
    stimulus_config={"requires_ppg": True, "requires_real_board": True},
    success_criteria={
        "trance_score_v2_min": 0.35,
        "ppg_breath_rate_decreased": True,
        "ppg_hrv_rmssd_increased": True,
    },
    failure_criteria={
        "physiology_not_following_lead_after_s": 90,
        "phase": "LEAD",
    },
    phase_sequence=[
        InductionPhase(
            phase_name="READ",
            duration_range_s=(10, 20),
            target_eeg_state={"baseline": "capture"},
            stimulus_params={},    # Silent baseline capture
            transition_trigger="baseline_capture_complete",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="PACE",
            duration_range_s=(60, 120),
            target_eeg_state={"alpha": "stable_or_increasing"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf", "am_depth": 0.25},
                "visual":      {"bg_ganzfeld_gain": 0.2},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.18,
                                "pacing_mode": True},
            },
            transition_trigger="3+ pacing statements delivered AND alpha > baseline",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="BRIDGE",
            duration_range_s=(20, 30),
            target_eeg_state={"alpha": "sustained", "theta": "onset"},
            stimulus_params={
                "entrainment": {"beat_frequency": "iaf_minus_0.5", "am_depth": 0.35},
                "content":     {"active_pool": "somatic_anchoring", "tts_gain": 0.18},
            },
            transition_trigger="elapsed > 20s",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="LEAD",
            duration_range_s=(60, 120),
            target_eeg_state={"theta_alpha_ratio": "increasing", "beta": "decreasing"},
            stimulus_params={
                "entrainment": {"beat_frequency": "theta_target", "am_depth": 0.50},
                "visual":      {"bg_ganzfeld_gain": 0.35},
                "content":     {"active_pool": "warmth_comfort", "tts_gain": 0.18,
                                "lead_mode": True},
            },
            transition_trigger="ppg_breath_rate < PACE baseline - 2 bpm AND trance_score_v2 >= 0.30",
            timeout_action="advance",
        ),
        InductionPhase(
            phase_name="DEEPEN_AND_STABILIZE",
            duration_range_s=(30, 60),
            target_eeg_state={"theta": "dominant", "stable": True},
            stimulus_params={
                "entrainment": {"am_depth": 0.5},
            },
            transition_trigger="trance_score_v2 >= 0.35 ppg_breath_rate decreased ppg_hrv_rmssd increased",
            timeout_action="advance",
        ),
    ],
)


# ── Strategy registry and arc mapping ────────────────────────────────────────

STRATEGY_REGISTRY: dict[str, InductionStrategy] = {
    s.strategy_id: s for s in [
        ENTRAINMENT_HEAVY, SOMATIC_ANCHOR, BREATH_LEAD, PROGRESSIVE_RELAXATION,
        COGNITIVE_OVERLOAD, FRACTIONATION, FIXATION_FADE, PACE_AND_LEAD,
    ]
}

ARC_STRATEGY_MAP: dict[str, list[str]] = {
    "GENTLE_DESCENT":    ["SOMATIC_ANCHOR", "BREATH_LEAD", "PROGRESSIVE_RELAXATION"],
    "WAVE_PATTERN":      ["FRACTIONATION", "ENTRAINMENT_HEAVY"],
    "DEEP_PLATEAU":      ["ENTRAINMENT_HEAVY", "COGNITIVE_OVERLOAD"],
    "CONDITIONING_FOCUS": ["PACE_AND_LEAD", "SOMATIC_ANCHOR"],
    "SLEEP_BRIDGE":      ["BREATH_LEAD", "PROGRESSIVE_RELAXATION"],
}


# ── Effectiveness scoring ─────────────────────────────────────────────────────

def compute_effectiveness(
    strategy:                InductionStrategy,
    actual_time_s:           float,
    peak_trance_score:       float,
    trance_variance_stabilize: float,
    rmssd_delta_ms:          float,
    was_redirected:          bool,
) -> float:
    """Compute effectiveness score (0.0–1.0) for a completed induction attempt."""
    exp_min, exp_max = strategy.expected_time_to_trance_s
    denom = max(1, exp_max - exp_min)
    time_score     = 1.0 - _clamp((actual_time_s - exp_min) / denom, 0.0, 1.0)
    depth_score    = _clamp(peak_trance_score / 0.6, 0.0, 1.0)
    stability_score = 1.0 - _clamp(trance_variance_stabilize / 0.1, 0.0, 1.0)
    autonomic_score = _clamp(rmssd_delta_ms / 20.0, 0.0, 1.0)
    redirect_penalty = -0.3 if was_redirected else 0.0
    raw = (
        0.30 * time_score
        + 0.30 * depth_score
        + 0.20 * stability_score
        + 0.20 * autonomic_score
        + redirect_penalty
    )
    return _clamp(raw, 0.0, 1.0)


# ── StrategySelector ──────────────────────────────────────────────────────────

class StrategySelector:
    """
    Selects the optimal induction strategy given user profile and session context.
    Called by SessionDirector when entering INDUCTION phase.
    """

    def __init__(
        self,
        strategy_registry: dict[str, InductionStrategy] = STRATEGY_REGISTRY,
        db=None,
    ) -> None:
        self.registry = strategy_registry
        self.db = db

    def select_strategy(
        self,
        user_profile: dict,
        session_context: dict,
    ) -> str:
        """
        Returns the strategy_id of the selected strategy.

        session_context keys used:
          session_count    int   — completed sessions so far
          ppg_available    bool  — whether real PPG data is available
          arc_template     str   — current session arc name
          synthetic_board  bool  — whether running on synthetic EEG board
          contraindications list — inherited from user profile
        """
        candidates = list(self.registry.keys())

        # 1. Hard filter: contraindications from profile
        candidates = self._filter_contraindications(
            candidates, user_profile.get("contraindication_flags", [])
        )

        # 2. Session count unlock
        session_count = int(session_context.get("session_count", 0))
        candidates = self._filter_session_unlock(candidates, session_count)

        # 3. PPG availability
        ppg_ok = bool(session_context.get("ppg_available", False))
        synthetic = bool(session_context.get("synthetic_board", False))
        if not ppg_ok:
            candidates = [c for c in candidates if c not in ("BREATH_LEAD", "PACE_AND_LEAD")]
        if synthetic:
            candidates = [c for c in candidates if c != "PACE_AND_LEAD"]

        if not candidates:
            return "ENTRAINMENT_HEAVY"  # ultimate fallback

        # 4. Explicit user preference
        preferred = user_profile.get("preferred_strategy")
        if preferred and preferred in candidates:
            return preferred

        # 5. First session — use only gentle strategies
        if session_count == 0:
            first_eligible = [
                "SOMATIC_ANCHOR", "BREATH_LEAD",
                "PROGRESSIVE_RELAXATION", "FIXATION_FADE",
            ]
            gentle = [c for c in candidates if c in first_eligible]
            if gentle:
                if ppg_ok and "BREATH_LEAD" in gentle:
                    return "BREATH_LEAD"
                return "SOMATIC_ANCHOR" if "SOMATIC_ANCHOR" in gentle else gentle[0]

        # 6. Effectiveness scores from user history
        effectiveness = self._get_effectiveness_scores(user_profile)

        # 7. Habituation prevention — demote if same strategy used 3× in a row
        last_3 = self._get_last_n_strategies(user_profile.get("user_id", "default"), n=3)
        if len(set(last_3)) == 1 and last_3[0] in candidates:
            without_habituated = [c for c in candidates if c != last_3[0]]
            if without_habituated:
                candidates = without_habituated

        # 8. Arc template alignment
        arc = session_context.get("arc_template", "GENTLE_DESCENT")
        arc_preferred = ARC_STRATEGY_MAP.get(arc, [])
        arc_aligned = [c for c in candidates if c in arc_preferred]
        if arc_aligned:
            candidates = arc_aligned

        # 9. Weighted random selection
        weights = [max(0.01, effectiveness.get(c, 0.5)) for c in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]

    # ── Private helpers ────────────────────────────────────────────────────────

    def _filter_contraindications(
        self, candidates: list[str], flags: list[str]
    ) -> list[str]:
        result = []
        for cid in candidates:
            strategy = self.registry.get(cid)
            if strategy is None:
                continue
            blocked = any(f in strategy.contraindications for f in flags)
            if not blocked:
                result.append(cid)
        return result or candidates  # never return empty

    def _filter_session_unlock(
        self, candidates: list[str], session_count: int
    ) -> list[str]:
        result = [
            c for c in candidates
            if self.registry[c].session_count_unlock <= session_count
        ]
        return result or candidates

    def _get_effectiveness_scores(self, user_profile: dict) -> dict[str, float]:
        raw = user_profile.get("strategy_effectiveness", {})
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        return raw if isinstance(raw, dict) else {}

    def _get_last_n_strategies(self, user_id: str, n: int = 3) -> list[str]:
        if self.db is None:
            return []
        try:
            rows = self.db.get_recent_strategy_history(user_id=user_id, limit=n)
            return [r.get("strategy_id", "") for r in rows]
        except Exception:
            return []


# ── InductionRunner ───────────────────────────────────────────────────────────

class InductionRunner:
    """
    Real-time executor for an InductionStrategy (Bible Ch.6 §6.7 §6).

    tick() returns one of:
      'RUNNING'            — still inducting
      'INDUCTION_COMPLETE' — success criteria met
      'REDIRECT'           — switching to fallback strategy
      'INDUCTION_FAILED'   — no fallback, induction failed
    """

    def __init__(
        self,
        strategy: InductionStrategy,
        db=None,
    ) -> None:
        self.strategy            = strategy
        self.db                  = db
        self.current_phase_idx   = 0
        self.phase_start_time    = time.time()
        self.induction_start_time = self.phase_start_time

        # Ratchet tracking for FRACTIONATION
        self._peak_scores:  list[float] = []
        self._prev_peak:    float = 0.0

        # Sustained-above tracking for success criteria
        self._above_min_since: Optional[float] = None

        # Baseline capture for PACE_AND_LEAD
        self._baseline_trance: float = 0.0
        self._baseline_hr:     float = 0.0
        self._baseline_breath: float = 0.0
        self._baseline_rmssd:  float = 0.0

        # Completion state
        self.outcome:          str = "running"
        self.redirect_to:      str = ""
        self._patches:         dict = {}

    def tick(
        self,
        eeg_state: dict,
        ppg_state: dict,
        imu_state: dict,
    ) -> str:
        """Called once per second during INDUCTION phase."""
        phase   = self.strategy.phase_sequence[self.current_phase_idx]
        elapsed = time.time() - self.phase_start_time
        total   = time.time() - self.induction_start_time

        trance = float(eeg_state.get("trance_score_v2", 0.0) or 0.0)
        self._peak_scores.append(trance)

        # Baseline capture (PACE_AND_LEAD READ phase)
        if phase.phase_name == "READ" and self._baseline_hr == 0.0:
            self._baseline_hr     = float(ppg_state.get("heart_rate", 0.0) or 0.0)
            self._baseline_breath = float(ppg_state.get("breath_rate", 0.0) or 0.0)
            self._baseline_rmssd  = float(ppg_state.get("hrv_rmssd", 0.0) or 0.0)
            self._baseline_trance = trance

        # Apply stimulus patches (non-destructive suggestions to live state)
        self._patches = self._build_patches(phase, elapsed, total)

        # Check global success criteria
        if self._check_success(trance, ppg_state, imu_state):
            self._complete("success", total)
            return "INDUCTION_COMPLETE"

        # Check global failure criteria
        if self._check_failure(eeg_state, ppg_state, imu_state, total):
            return self._handle_failure(total)

        # Phase transition check
        if self._check_phase_transition(phase, eeg_state, ppg_state, imu_state, elapsed):
            self._advance_phase()
        elif elapsed > phase.duration_range_s[1]:
            self._handle_timeout(phase, total)

        return "RUNNING"

    @property
    def live_patches(self) -> dict:
        """Returns the live_control patches computed on the last tick."""
        return dict(self._patches)

    # ── Success / failure ─────────────────────────────────────────────────────

    def _check_success(
        self, trance: float, ppg: dict, imu: dict
    ) -> bool:
        c = self.strategy.success_criteria
        min_score = float(c.get("trance_score_v2_min", 0.35))
        if trance < min_score:
            self._above_min_since = None
            return False

        # Track sustained duration
        if self._above_min_since is None:
            self._above_min_since = time.time()
        sustain = float(c.get("sustain_duration_s", 10))
        if (time.time() - self._above_min_since) < sustain:
            return False

        # IMU stillness
        still_min = float(c.get("imu_stillness_index_min", 0.0))
        if still_min > 0.0 and float(imu.get("stillness_index", 1.0) or 1.0) < still_min:
            return False

        # Ratchet verification (FRACTIONATION)
        if "ratchet_verified" in c and not self._verify_ratchet():
            return False

        return True

    def _check_failure(
        self, eeg: dict, ppg: dict, imu: dict, total: float
    ) -> bool:
        c = self.strategy.failure_criteria

        # Time-based: trance too low after N seconds
        max_t  = float(c.get("after_elapsed_s", 0) or 0)
        low_t  = float(c.get("trance_score_v2_below", 0) or 0)
        if max_t > 0 and low_t > 0:
            if total > max_t and float(eeg.get("trance_score_v2", 0.0) or 0) < low_t:
                return True

        # PPG dependency failure
        if c.get("alt") == "ppg_available_false":
            if not ppg.get("available", True):
                return True

        # Motion contamination (SOMATIC_ANCHOR)
        if c.get("imu_motion_contaminated"):
            after_phase = c.get("after_phase", "")
            if after_phase:
                phase_names = [p.phase_name for p in self.strategy.phase_sequence]
                after_idx = phase_names.index(after_phase) if after_phase in phase_names else -1
                if self.current_phase_idx > after_idx:
                    consec = int(imu.get("motion_contaminated_consecutive", 0) or 0)
                    if consec >= int(c.get("consecutive_ticks", 3)):
                        return True

        return False

    def _handle_failure(self, total: float) -> str:
        if self.strategy.redirect_strategy:
            self.redirect_to = self.strategy.redirect_strategy
            self._complete("redirected", total, redirect_to=self.redirect_to)
            return "REDIRECT"
        self._complete("failure", total)
        return "INDUCTION_FAILED"

    # ── Phase management ──────────────────────────────────────────────────────

    def _check_phase_transition(
        self,
        phase: InductionPhase,
        eeg: dict,
        ppg: dict,
        imu: dict,
        elapsed: float,
    ) -> bool:
        if elapsed < phase.duration_range_s[0]:
            return False

        trigger = phase.transition_trigger.lower()
        trance  = float(eeg.get("trance_score_v2", 0.0) or 0.0)

        # Most common triggers
        if "elapsed >" in trigger:
            try:
                threshold = float(trigger.split("elapsed >")[1].strip().split("s")[0])
                return elapsed > threshold
            except Exception:
                pass

        if "trance_score_v2 >= " in trigger:
            parts = trigger.split("trance_score_v2 >=")
            try:
                val = float(parts[1].strip().split()[0])
                return trance >= val
            except Exception:
                pass

        if "alpha_power > baseline" in trigger or "alpha_power increase" in trigger:
            alpha_ratio = float(eeg.get("alpha_ratio", 0.0) or 0.0)
            return alpha_ratio > 0.3

        if "baseline_capture_complete" in trigger:
            return elapsed >= phase.duration_range_s[0]

        if "previous_peak" in trigger:
            return trance >= self._prev_peak + 0.10

        if "alpha_power uptick" in trigger or "alpha_spike" in trigger:
            return float(eeg.get("alpha_ratio", 0.0) or 0.0) > 0.4

        if "alpha_power > theta_power" in trigger:
            return (float(eeg.get("alpha_ratio", 0.0) or 0.0)
                    > float(eeg.get("theta_ratio", 0.0) or 0.0))

        # Fallback: max duration reached
        return elapsed >= phase.duration_range_s[1]

    def _advance_phase(self) -> None:
        if self.current_phase_idx < len(self.strategy.phase_sequence) - 1:
            self._prev_peak = max(self._peak_scores) if self._peak_scores else 0.0
            self._peak_scores = []
            self.current_phase_idx += 1
            self.phase_start_time = time.time()

    def _handle_timeout(self, phase: InductionPhase, total: float) -> None:
        if phase.timeout_action == "advance":
            self._advance_phase()
        elif phase.timeout_action == "fail":
            self._handle_failure(total)
        # "extend" — do nothing; runner continues until failure criteria

    # ── Patch / log ───────────────────────────────────────────────────────────

    def _build_patches(
        self, phase: InductionPhase, elapsed: float, total: float
    ) -> dict:
        patches: dict = {
            "induction_strategy_id":    self.strategy.strategy_id,
            "induction_phase":          phase.phase_name,
            "induction_phase_elapsed_s": round(elapsed, 1),
            "induction_phase_progress":  round(
                _clamp(elapsed / max(1, phase.duration_range_s[1]), 0.0, 1.0), 3
            ),
            "induction_success":        False,
            "induction_redirecting":    False,
            "induction_redirect_to":    "",
        }

        # Flatten stimulus_params into live_control key/value pairs
        for layer, params in phase.stimulus_params.items():
            for k, v in params.items():
                if isinstance(v, (int, float, bool, str)):
                    patches[k] = v

        return patches

    def _complete(
        self,
        outcome: str,
        total: float,
        redirect_to: str = "",
    ) -> None:
        self.outcome = outcome
        self._patches["induction_success"] = (outcome == "success")
        self._patches["induction_redirecting"] = (outcome == "redirected")
        self._patches["induction_redirect_to"] = redirect_to

        # Compute and persist effectiveness if DB available
        peak = max(self._peak_scores) if self._peak_scores else 0.0
        eff  = compute_effectiveness(
            strategy=self.strategy,
            actual_time_s=total,
            peak_trance_score=peak,
            trance_variance_stabilize=0.05,   # placeholder; real impl from stabilize phase
            rmssd_delta_ms=5.0,                # placeholder
            was_redirected=(outcome == "redirected"),
        )
        if self.db is not None:
            try:
                self.db.log_induction_outcome(
                    strategy_id=self.strategy.strategy_id,
                    outcome=outcome,
                    time_to_trance_s=total,
                    peak_trance_score=peak,
                    effectiveness_score=eff,
                    redirected_to=redirect_to,
                )
            except Exception:
                pass

    def _verify_ratchet(self) -> bool:
        """Verify each reinduction peaked higher than the previous (FRACTIONATION)."""
        peaks = self._peak_scores
        if len(peaks) < 2:
            return False
        return peaks[-1] > self._prev_peak
