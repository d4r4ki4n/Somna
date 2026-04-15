# Doc 49 — Induction Strategy Library

**Somna Hypnotic Entrainment Application**

**Status:** Draft — pending implementation

**Author:** Reese (research collaborator)

**Date:** 5 April 2026

**Audience:** Ed (developer) · Vesper (LLM coding agent)

**Depends on:** Doc 35 (PhaseTracker / DeliveryGate) · Doc 36 (Neural-State Semantic Selection) · Doc 37 (Crossmodal Gain Architecture) · Doc 38 (Trance Depth Estimation v2) · Doc 42 (Cardiac-Phase Gating & Autonomic-Inertial Integration) · Doc 43 (Conditioning & Reinforcement) · Doc 44 (Stimulus Techniques & Optimization) · Doc 46 (Content Design Methodology) · Doc 47 (Visual & Audio Enhancement Architecture) · Doc 48 (Session Director Architecture)

# 1\. Overview

Ed — Doc 48's SessionPlanner references induction strategies by name but never defines them as structured, executable programs. The planner says "use ENTRAINMENT_HEAVY" and then waves its hands. This document fills the gap completely. Every induction strategy is specified here as a full machine-readable configuration: phase sequences, timing profiles, stimulus parameters, EEG/physiological success criteria, fallback logic, and clinical evidence. This is the implementation spec — Vesper should be able to build the entire InductionRunner + StrategySelector system from this document in a single pass.

We also specify the **strategy selection engine** that picks the right induction for a given user and session context, and the **effectiveness metrics** that let SessionEvaluator learn which strategies work for you over time.

## 1.1 The Gruzelier Three-Stage Model

Every Somna induction strategy is built on Gruzelier's (1998) neurophysiological model of hypnotic induction. The model describes three sequential cortical stages that any successful induction must traverse:

- **Stage I — Focused Attentional Engagement:** Left anterior activation. The thalamocortical attentional network engages, parietofrontal connections strengthen. The subject fixates on and concentrates on the induction stimulus. EEG signature: increased frontal midline theta (absorption), sustained alpha.
- **Stage II — Frontolimbic Inhibition:** Suspension of reality testing and critical evaluation. Prefrontal executive control diminishes. The "letting go" transition — the moment the conscious mind stops analysing and starts accepting. EEG signature: reduced beta, increased alpha/theta ratio.
- **Stage III — Posterior Cortical Redistribution:** Activity shifts to posterior cortical regions, particularly right hemisphere in high-susceptible subjects. In classical hypnosis literature, this stage is associated with passive imagery experience. **In Somna, Stage III replaces passive imagery entirely with somatic/interoceptive/conceptual absorption.**

**Aphantasia Adaptation — Stage III**

Ed has extreme aphantasia — zero voluntary visual imagery. This is not a limitation for hypnotic induction. Research confirms that aphantasic individuals are often highly hypnotizable precisely because they process through bodily awareness, emotional resonance, and conceptual knowing rather than visual imagery (Institute of Consciousness, 2024). Somna's Stage III targets somatic absorption (body weight, warmth, tingling, pressure), interoceptive awareness (heartbeat, breath rhythm, muscle release), and conceptual depth (the _sense_ of depth, the _knowing_ of relaxation) — channels that are fully intact and often enhanced in aphantasic individuals. No strategy in this library uses guided visual imagery, mental staircases, beach scenes, or any visualization-dependent content. Every content pool referenced here (Doc 36, Doc 46) is already designed aphantasia-first.

Different strategies emphasize different entry points into the three-stage sequence. ENTRAINMENT_HEAVY hammers Stage I with frequency-following response. SOMATIC_ANCHOR enters through Stage II via interoceptive focus. COGNITIVE_OVERLOAD forces a Stage I → Stage II transition by exhausting executive control. The strategies are enumerated fully in Section 4.

# 2\. Strategy Data Model

## 2.1 InductionStrategy

Each strategy is a frozen dataclass (or dict, Vesper's call on implementation) with the following fields:

| **Field** | **Type** | **Description** |
| --- | --- | --- |
| strategy_id | str | Unique identifier, e.g. "ENTRAINMENT_HEAVY" |
| --- | --- | --- |
| display_name | str | Human-readable name for UI/logs |
| --- | --- | --- |
| description | str | One-line summary of mechanism |
| --- | --- | --- |
| gruzelier_emphasis | str | Which Gruzelier stage this strategy enters through: "STAGE_I", "STAGE_II", "STAGE_I_II" |
| --- | --- | --- |
| primary_mechanism | str | Core neurophysiological mechanism (prose) |
| --- | --- | --- |
| expected_time_to_trance_s | tuple\[int, int\] | (min, max) seconds typical range |
| --- | --- | --- |
| phase_sequence | list\[InductionPhase\] | Ordered list of micro-phases within the induction |
| --- | --- | --- |
| stimulus_config | dict | Entrainment parameters, gain profiles, content pool priorities |
| --- | --- | --- |
| success_criteria | dict | EEG/physiological thresholds indicating successful induction |
| --- | --- | --- |
| failure_criteria | dict | Conditions indicating strategy is failing |
| --- | --- | --- |
| redirect_strategy | str \| None | Fallback strategy_id if this one fails |
| --- | --- | --- |
| contraindications | list\[str\] | Conditions where this strategy should not be selected |
| --- | --- | --- |
| conditioning_hooks | dict | Which conditioning paradigms (Doc 43) this strategy naturally supports |
| --- | --- | --- |
| session_count_unlock | int | Minimum completed sessions before strategy becomes available (0 = always) |
| --- | --- | --- |

## 2.2 InductionPhase

Each micro-phase within a strategy:

| **Field** | **Type** | **Description** |
| --- | --- | --- |
| phase_name | str | Unique name within strategy, e.g. "CAPTURE", "DESCEND" |
| --- | --- | --- |
| duration_range_s | tuple\[int, int\] | (min, max) seconds this phase should last |
| --- | --- | --- |
| target_eeg_state | dict | Target band power ratios: {"theta_alpha_ratio": 0.8, "beta_suppression": 0.3} |
| --- | --- | --- |
| stimulus_params | dict | What each layer does during this phase (keyed by layer name) |
| --- | --- | --- |
| transition_trigger | str | Condition to advance to next phase (expression or named criterion) |
| --- | --- | --- |
| timeout_action | str | What happens if transition_trigger not met within duration_range_s\[1\]: "advance", "extend", "fail" |
| --- | --- | --- |

@dataclass(frozen=True) class InductionPhase: phase_name: str duration_range_s: tuple\[int, int\] target_eeg_state: dict stimulus_params: dict transition_trigger: str timeout_action: str # "advance" | "extend" | "fail" @dataclass class InductionStrategy: strategy_id: str display_name: str description: str gruzelier_emphasis: str # "STAGE_I" | "STAGE_II" | "STAGE_I_II" primary_mechanism: str expected_time_to_trance_s: tuple\[int, int\] phase_sequence: list\[InductionPhase\] stimulus_config: dict success_criteria: dict failure_criteria: dict redirect_strategy: str | None contraindications: list\[str\] conditioning_hooks: dict session_count_unlock: int = 0

# 3\. Strategy Definitions

Eight strategies follow. Each is fully specified — Vesper can instantiate these directly from the tables and code blocks below. The strategies are ordered roughly by mechanistic complexity.

## 3.1 ENTRAINMENT_HEAVY — "Neural Frequency Lock"

| **Field** | **Value** |
| --- | --- |
| **strategy_id** | "ENTRAINMENT_HEAVY" |
| --- | --- |
| **display_name** | "Neural Frequency Lock" |
| --- | --- |
| **description** | IAF-matched multi-channel entrainment drives cortical oscillations toward target theta/alpha band via frequency following response. |
| --- | --- |
| **gruzelier_emphasis** | "STAGE_I" — attentional capture via rhythmic stimulus |
| --- | --- |
| **expected_time_to_trance_s** | (120, 300) |
| --- | --- |
| **redirect_strategy** | "BREATH_LEAD" |
| --- | --- |
| **contraindications** | \["photosensitive_epilepsy", "user_preference_no_strobe"\] |
| --- | --- |
| **session_count_unlock** | 0   |
| --- | --- |
| **conditioning_hooks** | {"entrainment_onset_cs": "isochronic_pulse_pattern", "frequency_descent_cs": "theta_relaxation_ur"} |
| --- | --- |

**Primary mechanism:** Auditory Steady-State Response (ASSR) + Visual Steady-State Response (VSSR) frequency following response. The brain's oscillatory networks entrain to periodic external stimuli when the stimulus frequency is close to a natural resonance. IAF-matched entrainment locks cortical alpha, then a gradual frequency ramp pulls oscillations downward toward upper theta. This is Gruzelier Stage I in its purest form — attentional capture via rhythmic driving. The transition to Stage II occurs naturally as theta dominance increases and prefrontal analytical processing diminishes.

### Phase Sequence

| **#** | **Phase** | **Duration (s)** | **Target EEG** | **Stimulus Parameters** | **Transition Trigger** | **Timeout** |
| --- | --- | --- | --- | --- | --- | --- |
| 1   | **CAPTURE** | 30–60 | alpha_power > baseline, frontal_midline_theta onset | Isochronic pulses at IAF, gain 0.4. Golden spiral rotation at IAF. Binaural beat at IAF. Background Ganzfeld field steady. TTS silent. SSB silent. | alpha_coherence > 0.6 sustained 10s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 2   | **DESCEND** | 60–120 | theta_alpha_ratio increasing, PAF slowing | Linear frequency ramp: IAF → IAF−2 Hz (upper theta). Isochronic gain rises to 0.6. Spiral rotation slows proportionally. Binaural beat tracks ramp. Background Ganzfeld begins 0.1 Hz breathing cycle (luminance modulation). GLSL warmth tint increases. | theta_alpha_ratio > 0.7 sustained 10s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 3   | **THETA_FLOOR** | 30–90 | theta_power sustained, beta_suppression < 0.3 | Hold at target theta frequency. AM depth profiling active (Doc 44). TTS from SOMATIC_ANCHORING pool at whisper gain (0.15). SSB from depth-appropriate pool (Doc 36 mapping). Isochronic holds at 0.6. Binaural holds. | trance_score_v2 >= 0.40 sustained 10s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 4   | **STABILIZE** | 30–60 | theta dominant, stable variance | Reduce all entrainment gains by 20%. TTS continues at whisper. Monitor trance_score_v2 variance — should remain within ±0.05. | trance_score_v2 >= 0.45, sustained 15s, 2-of-3 axes converging | advance |
| --- | --- | --- | --- | --- | --- | --- |

**Success criteria:** {"trance_score_v2_min": 0.45, "convergence_rule": "2_of_3_axes", "sustain_duration_s": 15}

**Failure criteria:** {"trance_score_v2_below": 0.2, "after_elapsed_s": 240, "alt": "alpha_power_increasing_trend_over_60s"}

**Evidence:** Jensen & Barrett 2024 — slow wave hypothesis posits that theta/alpha bandwidth facilitates hypnotic responsivity by reducing cortical noise. Landry et al 2024 — peak alpha frequency dynamics characterize induction in high-susceptible subjects; PAF slowing by 0.5–1.0 Hz is a reliable induction marker. The frequency following response (FFR) is one of the most robust phenomena in auditory neuroscience — ASSR drives are measurable even under anaesthesia. Visual FFR via SSVEP is equally well-established. Combining ASSR + VSSR for crossmodal entrainment is Somna's specific innovation.

## 3.2 SOMATIC_ANCHOR — "Body Awareness Descent"

| **Field** | **Value** |
| --- | --- |
| **strategy_id** | "SOMATIC_ANCHOR" |
| --- | --- |
| **display_name** | "Body Awareness Descent" |
| --- | --- |
| **description** | Progressive interoceptive attention narrowing drives parasympathetic dominance and frontolimbic inhibition. |
| --- | --- |
| **gruzelier_emphasis** | "STAGE_II" — frontolimbic inhibition via interoceptive focus |
| --- | --- |
| **expected_time_to_trance_s** | (180, 420) |
| --- | --- |
| **redirect_strategy** | "BREATH_LEAD" |
| --- | --- |
| **contraindications** | \["somatic_hypervigilance", "chronic_pain_body_focus_aversive"\] |
| --- | --- |
| **session_count_unlock** | 0   |
| --- | --- |
| **conditioning_hooks** | {"body_scan_cs": "relaxation_response_ur", "anchor_point_cs": "depth_ur"} |
| --- | --- |

**Primary mechanism:** Directing attention sequentially through body regions activates the insular cortex (the brain's interoceptive hub) and progressively reduces prefrontal executive activity. When passive attention rests on a muscle group, Golgi tendon organ activation triggers a reflexive relaxation response, and the parasympathetic cascade follows. This is a direct Gruzelier Stage II entry — the "letting go" happens not through any verbal suggestion to let go, but through the physiological reality of muscles releasing as interoceptive attention touches them. For aphantasic individuals, this is often the most natural induction path: the body is always available as an attentional anchor, and somatic awareness channels are typically robust.

### Phase Sequence

| **#** | **Phase** | **Duration (s)** | **Target EEG** | **Stimulus Parameters** | **Transition Trigger** | **Timeout** |
| --- | --- | --- | --- | --- | --- | --- |
| 1   | **GROUND** | 30–60 | alpha_power > baseline | TTS from SOMATIC_ANCHORING pool: awareness of contact points — feet on floor, back against chair, hands resting. Gentle entrainment at IAF, gain 0.2. Background warm Ganzfeld field. GLSL warmth tint at 0.3. | alpha_power increase detected OR elapsed > 45s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 2   | **SCAN_DESCEND** | 60–120 | theta_alpha_ratio rising, beta decreasing | TTS guides attention through body regions: feet → legs → torso → arms → shoulders → neck → jaw → forehead. Somatic vocabulary (Doc 46): pressure, temperature, weight, texture, tingling, pulsing. Entrainment frequency begins slow descent (0.5 Hz/min). Content pool shifts toward WARMTH_COMFORT. Binaural ramp begins. GLSL blur begins at 0.1. | theta_alpha_ratio > 0.5 OR body_scan_complete | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 3   | **ANCHOR_DEEPEN** | 60–120 | sustained theta increase, frontal_midline_theta > baseline | TTS narrows to single body anchor point (default: hands or chest center — configurable per user_profile). Repetitive somatic language creates semantic satiation around the anchor: weight, warmth, pulse, heaviness, settling. Isochronic gain 0.3. Binaural at theta target. SSB onset from depth-appropriate pool. | trance_score_v2 >= 0.35 sustained 10s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 4   | **DISSOLVE** | 30–90 | theta dominant, beta_suppression < 0.25 | Content shifts to DISSOLUTION pool (Doc 36). TTS gain fades from 0.15 → 0.05. SSB gain rises from 0.1 → 0.25. Entrainment holds at theta target. GLSL blur increases to 0.4. Background Ganzfeld breathing slows to 0.05 Hz. | trance_score_v2 >= 0.40 sustained 10s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 5   | **STABILIZE** | 30–60 | theta dominant, stable | Reduce entrainment gains by 20%. Monitor variance. TTS at whisper. Same stabilize logic as ENTRAINMENT_HEAVY. | trance_score_v2 >= 0.40, sustained 15s, imu_stillness >= 0.85 | advance |
| --- | --- | --- | --- | --- | --- | --- |

**Success criteria:** {"trance_score_v2_min": 0.40, "ppg_hrv_rmssd": "increasing_trend", "imu_stillness_index_min": 0.85}

**Failure criteria:** {"imu_motion_contaminated": true, "consecutive_ticks": 3, "after_phase": "SCAN_DESCEND", "alt": {"trance_score_v2_below": 0.15, "after_elapsed_s": 300}}

**Evidence:** Aphantasia research confirms somatic/interoceptive channels are fully viable for hypnotic induction and often enhanced in non-visual processors. Bustamante-Sánchez et al 2026 (_Scientific Reports_) demonstrates that progressive muscle attention produces parasympathetic dominance — significant RMSSD increase, pNN50 increase, HF power increase, HR decrease, LF decrease. Gruzelier Stage II inhibition is directly targeted by the insular cortex activation → prefrontal deactivation pathway. This strategy is the recommended default for Ed specifically.

## 3.3 BREATH_LEAD — "Respiratory Pacing"

| **Field** | **Value** |
| --- | --- |
| **strategy_id** | "BREATH_LEAD" |
| --- | --- |
| **display_name** | "Respiratory Pacing" |
| --- | --- |
| **description** | Pace-then-lead respiratory entrainment toward resonance frequency amplifies RSA and vagal tone for parasympathetic-driven induction. |
| --- | --- |
| **gruzelier_emphasis** | "STAGE_I_II" — attention capture via breath awareness, then autonomic shift |
| --- | --- |
| **expected_time_to_trance_s** | (150, 360) |
| --- | --- |
| **redirect_strategy** | "SOMATIC_ANCHOR" (if PPG available), "ENTRAINMENT_HEAVY" (if PPG unavailable) |
| --- | --- |
| **contraindications** | \["respiratory_distress", "breath_focus_aversive", "ppg_available_false"\] |
| --- | --- |
| **session_count_unlock** | 0   |
| --- | --- |
| **conditioning_hooks** | {"paced_breathing_cs": "parasympathetic_dominance_ur", "exhale_phase_cs": "suggestion_receptivity_ur"} |
| --- | --- |

**Primary mechanism:** Respiratory sinus arrhythmia (RSA) amplification via paced breathing toward resonance frequency (~6 breaths/min, 0.1 Hz). At resonance frequency, the respiratory and cardiovascular oscillations phase-lock, producing maximal RSA amplitude and dramatic HRV increases. Vagal tone surges, parasympathetic dominance follows. Kumar's IISc thesis demonstrated that coherent breathing at resonance frequency produces measurable cortical integration increases in theta and alpha bands. The Ericksonian pacing-and-leading principle (Doc 48) is the behavioural chassis: match the user's current breath rate exactly (pace), then gradually slow it toward target (lead).

### Phase Sequence

| **#** | **Phase** | **Duration (s)** | **Target EEG** | **Stimulus Parameters** | **Transition Trigger** | **Timeout** |
| --- | --- | --- | --- | --- | --- | --- |
| 1   | **PACE** | 30–60 | alpha stable, no agitation markers | Read ppg_breath_rate from PPG engine. Audio/visual entrainment matches current breath rate exactly. Isochronic AM syncs to respiratory phase (louder on exhale). TTS: simple breath-awareness prompts from SOMATIC_ANCHORING pool — "Notice the breath moving... the rhythm that's already there." Background Ganzfeld breathing field matches user rate. | ppg_breath_rate stable (variance < 0.3 bpm) for 20s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 2   | **LEAD_DOWN** | 60–120 | alpha increasing, theta onset | Gradually slow entrainment breath rate by 0.5 breaths/min per 30s toward target (6 bpm or user's calibrated resonance frequency from Doc 28). Ganzfeld breathing field tracks paced rate. Binaural beat frequency descends in parallel (IAF → IAF−1.5 Hz). Isochronic gain rises to 0.4. TTS delivery remains breath-gated to exhale. | ppg_breath_rate within 1.0 bpm of target | extend (max +60s) |
| --- | --- | --- | --- | --- | --- | --- |
| 3   | **COHERE** | 60–120 | theta_alpha_ratio > 0.6, frontal_midline_theta up | Hold at resonance frequency. ppg_hrv_rmssd should be rising. Cardiac-phase gating (Doc 42) fully active — TTS suggestions delivered during cardiac systole for maximal interoceptive coupling. Content shifts to WARMTH_COMFORT pool. Delivery gated to respiratory exhale phase. SSB onset at gain 0.1. | ppg_hrv_rmssd > baseline + 15% sustained 15s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 4   | **DEEPEN** | 30–90 | theta dominant | Introduce theta-band entrainment overlay. Content shifts toward depth-appropriate pool per Doc 36 state-space mapping. SSB gain rises to 0.2. GLSL blur increases. Isochronic gain at 0.5. Respiratory pacing cues become more subtle (reduce TTS references to breath, let the rhythm continue autonomically). | trance_score_v2 >= 0.35 sustained 10s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 5   | **STABILIZE** | 30–60 | theta stable, low variance | Reduce respiratory pacing cues. If breath rate and trance_score hold without active pacing, induction succeeded. Standard stabilization monitoring. | trance_score_v2 >= 0.35, ppg_breath_rate within 0.5 bpm of target, ppg_hrv_rmssd > baseline + 15% | advance |
| --- | --- | --- | --- | --- | --- | --- |

**Success criteria:** {"trance_score_v2_min": 0.35, "ppg_breath_rate_within": 0.5, "ppg_hrv_rmssd_increase_pct": 15}

**Failure criteria:** {"ppg_breath_rate_not_decreasing_after_s": 120, "phase": "LEAD_DOWN", "alt": "ppg_available_false"}

**Evidence:** Coherent/resonance frequency breathing at ~6 cpm produces maximal RSA amplitude and HRV — this is one of the most replicated findings in psychophysiology. Kumar (IISc thesis) demonstrated increased theta/alpha cortical integration during slow-paced breathing in meditation practitioners. Respiratory pacing is a core Ericksonian technique — pace the client's current breathing, then lead it slower. The cardiac-phase gating integration (Doc 42) adds a Somna-specific layer: suggestions land during the cardiac cycle window of maximal interoceptive sensitivity.

## 3.4 PROGRESSIVE_RELAXATION — "Tension-Release Cascade"

| **Field** | **Value** |
| --- | --- |
| **strategy_id** | "PROGRESSIVE_RELAXATION" |
| --- | --- |
| **display_name** | "Tension-Release Cascade" |
| --- | --- |
| **description** | Jacobson PMR adapted for audio delivery — tension-release cycles trigger Golgi tendon organ reflex relaxation cascading through ANS. |
| --- | --- |
| **gruzelier_emphasis** | "STAGE_II" — peripheral-to-central relaxation triggers frontolimbic inhibition |
| --- | --- |
| **expected_time_to_trance_s** | (240, 480) |
| --- | --- |
| **redirect_strategy** | "ENTRAINMENT_HEAVY" |
| --- | --- |
| **contraindications** | \["chronic_pain_tension_contraindicated", "mobility_limitations"\] |
| --- | --- |
| **session_count_unlock** | 0   |
| --- | --- |
| **conditioning_hooks** | {"tension_release_cs": "deep_relaxation_ur", "sequential_release_cs": "progressive_depth_ur"} |
| --- | --- |

**Primary mechanism:** Jacobson progressive muscle relaxation. Voluntary muscle tension for 5 seconds activates Golgi tendon organs (GTOs), which are stretch receptors in tendons. When tension is released, GTOs trigger a reflex relaxation response that goes deeper than baseline — the muscle relaxes more than it was before the tension. This parasympathetic rebound cascades through the autonomic nervous system. Each tension-release cycle drives RMSSD upward and cortical beta downward. After 4–6 cycles, cumulative parasympathetic dominance triggers the Gruzelier Stage II transition. This is the slowest strategy but also the most mechanistically transparent — the body literally teaches itself to let go.

### Phase Sequence

| **#** | **Phase** | **Duration (s)** | **Target EEG** | **Stimulus Parameters** | **Transition Trigger** | **Timeout** |
| --- | --- | --- | --- | --- | --- | --- |
| 1   | **ORIENT** | 20–40 | baseline capture | TTS orients: "Notice the weight of your hands where they rest. In a moment, you'll tense and release muscle groups, one at a time. No need to force anything — just notice the contrast between tension and release." Pure somatic instruction, no conceptual framing. Entrainment at IAF, gain 0.15. | elapsed > 25s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 2   | **TENSION_CYCLE** | 120–240 | alpha increasing, beta decreasing with each release | TTS guides through 4–6 muscle groups: hands/fists → forearms → shoulders → jaw → forehead → full body. Each group: 5s tension instruction ("Clench your fists now... feel the tightness..."), 5s hold, 10s release + somatic attention ("And let go... notice how different that feels... the warmth spreading into the fingers..."). Entrainment at IAF during tension, drops 0.5 Hz during each release. Background Ganzfeld colour temperature descends with each release (cooler → warmer). GLSL blur increments +0.05 per release. | all_muscle_groups_completed AND alpha_power > baseline + 20% | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 3   | **PASSIVE_DESCENT** | 60–120 | theta_alpha_ratio > 0.6, beta_suppression strong | Post-PMR period. All muscle groups released. TTS shifts to WARMTH_COMFORT pool — heaviness, warmth, weight, settling, sinking. Entrainment ramps from current toward theta target (IAF−3 Hz). GLSL blur at 0.3. SSB onset. Isochronic gain 0.4. | trance_score_v2 >= 0.30 sustained 10s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 4   | **STABILIZE** | 30–60 | theta dominant, stable | Standard stabilization. Reduce gains 20%. Monitor variance. | trance_score_v2 >= 0.35, imu_stillness >= 0.90, ppg_hrv_rmssd > baseline + 20% | advance |
| --- | --- | --- | --- | --- | --- | --- |

**Success criteria:** {"trance_score_v2_min": 0.35, "imu_stillness_index_min": 0.90, "ppg_hrv_rmssd_increase_pct": 20}

**Failure criteria:** {"imu_motion_contaminated_persistent_through": "TENSION_CYCLE", "alt": {"trance_score_v2_below": 0.15, "after_elapsed_s": 360}}

**Evidence:** Bustamante-Sánchez et al 2026 (_Scientific Reports_) — PMR produces significant parasympathetic dominance: RMSSD increase, pNN50 increase, HF power increase, HR decrease, LF decrease. Neurosity review confirms Golgi tendon organ reflex cascade measurably shifts brainwave patterns toward alpha/theta dominance. Jacobson PMR is one of the most extensively validated relaxation induction techniques in clinical literature, with meta-analytic support spanning seven decades.

## 3.5 COGNITIVE_OVERLOAD — "Saturation Gate"

| **Field** | **Value** |
| --- | --- |
| **strategy_id** | "COGNITIVE_OVERLOAD" |
| --- | --- |
| **display_name** | "Saturation Gate" |
| --- | --- |
| **description** | Ericksonian confusion technique — multi-channel stimulus saturation exhausts prefrontal executive control, then sudden simplification creates immediate relief-gate trance entry. |
| --- | --- |
| **gruzelier_emphasis** | "STAGE_I" — attentional capture via cognitive saturation → forced Stage II transition |
| --- | --- |
| **expected_time_to_trance_s** | (90, 240) |
| --- | --- |
| **redirect_strategy** | "SOMATIC_ANCHOR" |
| --- | --- |
| **contraindications** | \["anxiety_disorder", "sensory_processing_sensitivity", "first_session", "user_preference_gentle"\] |
| --- | --- |
| **session_count_unlock** | 3   |
| --- | --- |
| **conditioning_hooks** | {"overload_onset_cs": "relief_anticipation_ur", "relief_gate_cs": "instant_depth_ur"} |
| --- | --- |

**Primary mechanism:** Milton Erickson's confusion technique (1948). Simultaneous multi-channel stimulus delivery saturates working memory capacity (Miller's 7±2 chunks), exhausting prefrontal executive control resources. The conscious mind attempts to track and analyse all channels — multiple audio streams, visual complexity, linguistic confusion — and fails. When all channels suddenly reduce to a single, clear, simple suggestion, the brain welcomes it as relief. The contrast between saturation and simplicity produces a PGO-spike-like orienting response that opens a transient gate for trance entry. This is Gruzelier Stage I → Stage II forced transition via executive exhaustion. Troxler fading and attentional tunnelling occur as sensory gating narrows during saturation.

**Safety Gate**

This strategy is **never** used on new users (session_count_unlock = 3). It requires prior session data confirming the user does not have anxiety or sensory processing sensitivity. StrategySelector enforces this hard constraint.

### Phase Sequence

| **#** | **Phase** | **Duration (s)** | **Target EEG** | **Stimulus Parameters** | **Transition Trigger** | **Timeout** |
| --- | --- | --- | --- | --- | --- | --- |
| 1   | **LAYER_BUILD** | 20–40 | beta increase (engagement/processing load) | Rapid onset of multiple simultaneous stimuli: golden spiral at IAF rotation, isochronic pulse at IAF+1 Hz (offset), binaural beat at IAF−1 Hz (different offset), TTS from IDENTITY pool with Milton Model embedded commands (Doc 46), SSB from a different pool simultaneously, background Ganzfeld looming. All gains moderate (0.3–0.4). | beta_power > baseline + 30% (cognitive load confirmed) | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 2   | **SATURATE** | 30–90 | beta sustained high → plateau → begin decline (executive exhaustion onset) | Increase stimulus density. TTS delivery rate increases to upper bound (6 Hz syllable rate). Add ASMR spatial texture. Visual fractal edge density increases. Confusion-pattern language in TTS: temporal ambiguity, nested negations, presuppositional stacking ("And you don't have to not notice what you weren't already beginning to feel..."). Isochronic gain 0.5. All channels competing for attentional resources. | beta_power begins declining from plateau (executive fatigue signal) | advance (critical — do not extend SATURATE beyond max) |
| --- | --- | --- | --- | --- | --- | --- |
| 3   | **RELIEF_GATE** | 10–20 | alpha spike (relief response), theta onset | Sudden reduction to single channel. All visual fades to simple warm Ganzfeld. Audio reduces to single low binaural tone (6 Hz theta). One clear, simple TTS suggestion from SOMATIC_ANCHORING: "And that's right... just this... just here... settling." Gains: TTS 0.2, binaural 0.3, everything else 0.0. Maximum contrast with SATURATE. | alpha_spike detected AND theta_onset | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 4   | **CAPTURE_DESCENT** | 30–60 | theta rising, alpha settling | Standard theta descent from relief point. Entrainment ramps toward theta target. Content shifts per depth (Doc 36). SSB onset. GLSL blur increases. Gentle, slow pacing — the opposite of SATURATE. | trance_score_v2 >= 0.35 sustained 10s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 5   | **STABILIZE** | 30–60 | theta dominant, stable | Standard stabilization. | trance_score_v2 >= 0.40, sustained 15s | advance |
| --- | --- | --- | --- | --- | --- | --- |

**Success criteria:** {"trance_score_v2_min": 0.40, "alpha_spike_at_relief_gate": true, "theta_increase_post_gate": true}

**Failure criteria:** {"user_interaction_event_during": "SATURATE", "alt": "beta_power_sustained_increase_60s_post_saturate"}

**Evidence:** Erickson 1948 (_Experimental Hypnosis_) — confusion technique developed for resistant and highly analytical subjects. The technique works by presenting contradictory or incomprehensible suggestions requiring constant reorientation until the subject welcomes any clear directive as cognitive relief. Gruzelier model explains this as forced Stage I → Stage II transition via executive exhaustion. The relief-gate moment maps to the PGO spike orienting response observed in rapid induction techniques.

## 3.6 FRACTIONATION — "Depth Ratchet"

| **Field** | **Value** |
| --- | --- |
| **strategy_id** | "FRACTIONATION" |
| --- | --- |
| **display_name** | "Depth Ratchet" |
| --- | --- |
| **description** | Repeated induction-emergence-reinduction cycles exploit residual trance carry-forward (homoaction) to achieve progressively greater depth. |
| --- | --- |
| **gruzelier_emphasis** | "STAGE_I_II" — repeated cycling through attention → inhibition |
| --- | --- |
| **expected_time_to_trance_s** | (180, 360) |
| --- | --- |
| **redirect_strategy** | "ENTRAINMENT_HEAVY" |
| --- | --- |
| **contraindications** | \["first_2_sessions"\] |
| --- | --- |
| **session_count_unlock** | 2   |
| --- | --- |
| **conditioning_hooks** | {"reinduction_cue_cs": "rapid_depth_ur", "emergence_partial_cs": "depth_anticipation_ur"} |
| --- | --- |

**Primary mechanism:** Vogt fractionation (1890s). Repeated induction-emergence-reinduction cycles, where each cycle carries "residual trance" forward. The subject does not return to full baseline wakefulness during partial emergence — they return to a state that is already deeper than where they started. The homoaction principle: each re-induction is faster and achieves greater depth. Dave Elman's clinical protocol relied on fractionation as a core component, routinely achieving somnambulistic depth within 3–5 cycles in a 5-minute window. For Somna, this strategy is particularly powerful because it builds experiential evidence _within a single session_ that depth can increase — the user feels the ratchet happening, which reinforces expectancy.

### Phase Sequence

| **#** | **Phase** | **Duration (s)** | **Target EEG** | **Stimulus Parameters** | **Transition Trigger** | **Timeout** |
| --- | --- | --- | --- | --- | --- | --- |
| 1   | **FIRST_INDUCTION** | 60–90 | alpha up, light theta onset | Standard brief induction: entrainment at IAF, gentle TTS from SOMATIC_ANCHORING, eyes-open visual fixation on spiral → Ganzfeld fade. Isochronic gain 0.3. Binaural at IAF. Target: light trance. | trance_score_v2 >= 0.20 | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 2   | **EMERGENCE_1** | 15–20 | alpha increase, theta decrease (partial arousal) | Partial arousal cue via TTS: "Becoming aware of the room again... the weight of your body in the chair... the sounds around you..." Entrainment frequency rises briefly toward 14 Hz (low beta). Visual brightens — Ganzfeld luminance increases. NOT full emergence — just enough to shift EEG toward waking alpha. Record peak_trance_score from FIRST_INDUCTION. | alpha_power > theta_power (arousal confirmed) | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 3   | **RE_INDUCTION_1** | 40–60 | theta > previous peak | Immediate re-induction with accelerated pacing. TTS: "And dropping back down now... twice as deep as before... notice how much faster it happens this time..." Entrainment descends 2× faster than FIRST_INDUCTION ramp rate. Isochronic gain 0.45. Target: trance_score_v2 >= previous_peak + 0.10. | trance_score_v2 >= previous_peak + 0.10 | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 4   | **EMERGENCE_2** | 10–15 | partial arousal (briefer than EMERGENCE_1) | Briefer arousal. Lighter touch. TTS: "Coming up just a little..." Entrainment rises briefly. Shorter duration. Record peak_trance_score from RE_INDUCTION_1. | alpha_power uptick detected | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 5   | **RE_INDUCTION_2** | 30–45 | theta dominant, deep | Third descent. TTS: "Three times as deep now... the body knows exactly where to go..." Fastest entrainment ramp (3× FIRST_INDUCTION rate). Content shifts to depth-appropriate pool (Doc 36). SSB onset. GLSL blur at 0.4. Isochronic gain 0.5. | trance_score_v2 >= previous_peak + 0.10 | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 6   | **STABILIZE** | 30–60 | theta dominant, stable at achieved depth | Standard stabilization at achieved depth. Reduce entrainment gains 20%. | trance_score_v2 >= 0.50, sustained 15s | advance |
| --- | --- | --- | --- | --- | --- | --- |

**Success criteria:** {"trance_score_v2_min": 0.50, "ratchet_verified": "each_reinduction_peak_gt_previous"}

**Failure criteria:** {"ratchet_failing": "reinduction_peak_not_exceeding_previous", "alt": {"trance_score_v2_below": 0.25, "after_all_cycles": true}}

**Evidence:** Vogt (1890s) first observed the ratchet effect in clinical practice. LCCH Asia 2025 review confirms homoaction mechanism and residual trance carry-forward as robust phenomena. Casiglia et al 2012 (_International Journal of Clinical and Experimental Hypnosis_) compared relaxation-based vs fractionation deepening and found fractionation achieves greater depth markers on physiological measures. Dave Elman's clinical protocol, documented extensively in _Hypnotherapy_ (1964), uses fractionation as the core component for achieving somnambulistic depth in approximately 5 minutes.

## 3.7 FIXATION_FADE — "Attentional Narrowing"

| **Field** | **Value** |
| --- | --- |
| **strategy_id** | "FIXATION_FADE" |
| --- | --- |
| **display_name** | "Attentional Narrowing" |
| --- | --- |
| **description** | Sustained foveal fixation induces Troxler fading, retinal fatigue, and thalamic sensory gating → natural eye closure → depth. |
| --- | --- |
| **gruzelier_emphasis** | "STAGE_I" — classical eye fixation → fatigue → Stage II transition |
| --- | --- |
| **expected_time_to_trance_s** | (120, 300) |
| --- | --- |
| **redirect_strategy** | "SOMATIC_ANCHOR" |
| --- | --- |
| **contraindications** | \["eye_conditions", "user_preference_no_strobe", "vr_mode"\] |
| --- | --- |
| **session_count_unlock** | 0   |
| --- | --- |
| **conditioning_hooks** | {"fixation_point_cs": "eye_fatigue_ur", "eye_closure_cs": "depth_onset_ur"} |
| --- | --- |

**Primary mechanism:** James Braid's original 1843 technique, updated with modern neurophysiology. Sustained foveal fixation on a single visual target produces three concurrent effects: (1) Troxler fading — unchanging peripheral stimuli disappear from conscious awareness as the visual cortex habituates, (2) retinal fatigue — sustained muscular effort of convergence and accommodation produces genuine eye fatigue, and (3) thalamic sensory gating — the Thalamic Reticular Nucleus (TRN) progressively inhibits non-essential sensory channels, creating experiential tunnel attention. Natural eye fatigue coupled with TTS suggestions of heaviness produces eye closure — the moment of closure is a powerful state-transition anchor. Gruzelier Stage I (fixation/attention) → Stage II (fatigue-coupled letting go) transition is the most classical induction pathway.

### Phase Sequence

| **#** | **Phase** | **Duration (s)** | **Target EEG** | **Stimulus Parameters** | **Transition Trigger** | **Timeout** |
| --- | --- | --- | --- | --- | --- | --- |
| 1   | **FIXATE** | 30–60 | alpha stable, frontal_midline_theta onset (absorption) | Single high-contrast visual focal point (spiral centre or radiant point). Sub-threshold IAF luminance modulation (Doc 47) — drives frequency following without conscious awareness. Audio: gentle isochronic at IAF, gain 0.2. TTS: "Let your attention rest on that single point... noticing how everything else becomes less important... just this one point of focus..." | frontal_midline_theta > baseline + 15% | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 2   | **FADE** | 30–60 | alpha increasing, peripheral visual processing decreasing | Troxler fading onset supported by GLSL vignette increase (peripheral darkening). Background Ganzfeld radial looming at 0.05 Hz — subtle sense of tunnelling. TTS references the fading: "The edges softening now... the world narrowing down to just this... less and less to track..." Isochronic gain rises to 0.3. | alpha_power > baseline + 25% (Troxler + absorption) | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 3   | **CLOSE** | 20–40 | paradoxical alpha increase (eye closure), theta onset | Eye closure transition. Ganzfeld field replaces focal point (full-field warm colour). GLSL blur maxes at 0.5. Descending Shepard tone begins (Doc 47). TTS: "Those heavy eyelids... letting them rest now... nothing to see, nothing to track... just the warmth behind closed lids..." Entrainment begins frequency descent from IAF toward theta. | alpha_spike detected (eye closure marker) | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 4   | **DESCENT** | 30–90 | theta rising, alpha settling post-closure | Post-closure deepening. TTS shifts to somatic content: body weight, warmth, heaviness, settling. Entrainment ramps toward theta target. Content shifts per depth (Doc 36). SSB onset. Binaural at theta. Isochronic gain 0.4. | trance_score_v2 >= 0.30 sustained 10s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 5   | **STABILIZE** | 30–60 | theta dominant, stable | Standard stabilization. | trance_score_v2 >= 0.35, sustained 15s | advance |
| --- | --- | --- | --- | --- | --- | --- |

**Success criteria:** {"trance_score_v2_min": 0.35, "alpha_spike_at_close": true, "theta_transition_post_close": true}

**Failure criteria:** {"user_interaction_event_during": "FIXATE", "alt": "no_alpha_increase_after_close_phase"}

**Evidence:** James Braid (1843) — the original "hypnotism" technique was eye fixation on a bright object held slightly above eye level. Gruzelier 1998 explicitly describes fixation → fatigue → inhibition as the classical induction pathway. Troxler fading (Troxler, 1804) is one of the oldest documented perceptual phenomena — unchanging peripheral stimuli disappear within 20 seconds. The coupling of natural physiological fatigue with verbal suggestion of heaviness compounds both effects. This is the most historically grounded strategy in the library.

## 3.8 PACE_AND_LEAD — "Physiological Mirror"

| **Field** | **Value** |
| --- | --- |
| **strategy_id** | "PACE_AND_LEAD" |
| --- | --- |
| **display_name** | "Physiological Mirror" |
| --- | --- |
| **description** | Real-time biofeedback-driven Ericksonian pacing builds unconscious agreement frame, then leads physiological state toward trance. |
| --- | --- |
| **gruzelier_emphasis** | "STAGE_I_II" — pacing captures attention via recognition, leading transitions to inhibition |
| --- | --- |
| **expected_time_to_trance_s** | (150, 360) |
| --- | --- |
| **redirect_strategy** | "ENTRAINMENT_HEAVY" (if PPG unavailable), "SOMATIC_ANCHOR" (if PPG available but lead not followed) |
| --- | --- |
| **contraindications** | \["ppg_available_false", "synthetic_board_mode"\] |
| --- | --- |
| **session_count_unlock** | 1   |
| --- | --- |
| **conditioning_hooks** | {"pacing_accuracy_cs": "trust_response_ur", "leading_suggestion_cs": "physiological_compliance_ur"} |
| --- | --- |

**Primary mechanism:** Ericksonian pacing and leading adapted for real-time biofeedback. The system uses EEG, PPG, and IMU data to generate TTS content that accurately describes the user's _current_ physiological state. "Your heart is beating at its own steady pace... your breath is moving slowly... you're sitting very still..." Each accurate statement is a truism the unconscious mind validates — yes, that's true. After 3–5 accurate pacing statements, an unconscious agreement frame (yes-set) is established. The system then begins "leading" — making statements that slightly precede the desired physiological shift: "Your breath is beginning to slow a little more..." The Non-Awareness Set (Erickson) is the core linguistic pattern: drawing attention to things happening outside normal conscious awareness ("You might not have noticed how much your shoulders have already softened..."). This strategy is unique to Somna because real-time sensor data enables _genuinely accurate_ pacing rather than the generic scripted truisms of traditional Ericksonian practice.

**Implementation Note**

This strategy has a **hard requirement** for real-time physiological data. It cannot run in synthetic board mode. StrategySelector must verify ppg_available == True before selecting this strategy. The pacing phase requires template-based TTS generation where physiological values are interpolated into pre-written sentence frames at delivery time — ContentManager (Doc 46) needs a PACING_TEMPLATE content pool for this.

### Phase Sequence

| **#** | **Phase** | **Duration (s)** | **Target EEG** | **Stimulus Parameters** | **Transition Trigger** | **Timeout** |
| --- | --- | --- | --- | --- | --- | --- |
| 1   | **READ** | 10–20 | baseline capture only | Silent sensor assessment. System reads ppg_heart_rate, ppg_breath_rate, imu_stillness_index, EEG band powers. No stimulus output — just baseline capture. Background Ganzfeld at neutral warm. No TTS, no SSB, no entrainment. | baseline_capture_complete (all sensors reporting) | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 2   | **PACE** | 60–120 | alpha stable or increasing (relaxation from being "seen") | TTS delivers pacing statements matched to real physiology from PACING_TEMPLATE pool: "Your heart is beating at \[rate\] beats per minute... steady... consistent..." / "Your breath is moving at its own natural pace... about \[rate\] breaths per minute..." / "You're sitting quite still right now..." Each statement is a verifiable truism. Entrainment matches current IAF exactly, gain 0.2. Background matches current state (if alert: brighter, cooler; if already relaxed: warmer, dimmer). Delivery pacing: one statement every 8–12 seconds. | 3+ pacing statements delivered AND alpha_power > baseline | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 3   | **BRIDGE** | 20–30 | alpha sustained, theta onset | Transitional language linking pacing to leading: "And as you notice these things... each heartbeat can carry you a little further into this..." / "The breath already knows where it's going..." Ericksonian temporal ambiguity. Entrainment begins gentle descent (0.3 Hz/min). Isochronic onset at gain 0.25. | elapsed > 20s | advance |
| --- | --- | --- | --- | --- | --- | --- |
| 4   | **LEAD** | 60–120 | theta_alpha_ratio increasing, beta decreasing | TTS leads physiological changes slightly ahead of current state: "Your breath is beginning to slow... becoming deeper..." / "The muscles in your shoulders are starting to soften..." / "You might not have noticed how much heavier your hands have become..." System targets ppg_breath_rate decrease, alpha increase. Content shifts toward WARMTH_COMFORT pool. Gains rise gradually: isochronic → 0.4, binaural → 0.35. Entrainment descends toward theta. SSB onset at 0.1. | ppg_breath_rate &lt; PACE baseline − 2 bpm AND trance_score_v2 &gt;= 0.30 | advance (if trance_score progressing), fail (if flat) |
| --- | --- | --- | --- | --- | --- | --- |
| 5   | **DEEPEN_AND_STABILIZE** | 30–60 | theta dominant, stable | If physiology followed the lead, continue descent. Standard depth-appropriate content (Doc 36). Reduce pacing references — the unconscious agreement frame is established. SSB gain 0.2. Stabilization monitoring. | trance_score_v2 >= 0.35, ppg_breath_rate decreased from PACE baseline, ppg_hrv_rmssd increased from baseline | advance |
| --- | --- | --- | --- | --- | --- | --- |

**Success criteria:** {"trance_score_v2_min": 0.35, "ppg_breath_rate_decreased": true, "ppg_hrv_rmssd_increased": true}

**Failure criteria:** {"physiology_not_following_lead_after_s": 90, "phase": "LEAD", "alt": "ppg_available_false"}

**Evidence:** Ericksonian pacing and leading is foundational to indirect/permissive hypnosis — Erickson's clinical work from the 1950s–1970s repeatedly demonstrated that accurate observation of client behaviour, fed back as verbal pacing, creates the conditions for subsequent leading. Mike Mandel Hypnosis Academy documents the yes-set → agreement frame → leading sequence as a systematic protocol. The Non-Awareness Set (Erickson) draws attention to unconscious processes, creating a mild dissociative shift that facilitates trance entry. Somna's biofeedback-driven implementation is, to our knowledge, a novel application — no existing hypnotic system uses real-time physiological data for machine-generated pacing statements.

# 4\. Strategy Selection Engine

## 4.1 StrategySelector Class

The StrategySelector integrates with SessionPlanner (Doc 48). It is called once at the start of the INDUCTION phase to select the optimal strategy for this user and session context.

class StrategySelector: """Selects optimal induction strategy given user profile and session context.""" def \__init_\_(self, strategy_registry: dict\[str, InductionStrategy\], db): self.registry = strategy_registry # strategy_id -> InductionStrategy self.db = db def select_strategy( self, user_profile: dict, session_context: dict # arc_template, ppg_available, session_count, etc. ) -> str: """Returns strategy_id of selected strategy.""" candidates = list(self.registry.keys()) # 1. Hard filters: contraindications + session_count_unlock candidates = self.\_filter_contraindications(candidates, user_profile) candidates = self.\_filter_session_unlock(candidates, session_context\["session_count"\]) # 2. PPG availability filter if not session_context.get("ppg_available", False): candidates = \[c for c in candidates if c not in ("BREATH_LEAD", "PACE_AND_LEAD")\] # 3. User explicit preference (overrides all below if valid) preferred = user_profile.get("preferred_strategy") if preferred and preferred in candidates: return preferred # 4. First session special case if session_context\["session_count"\] == 0: first_session_eligible = \[ "SOMATIC_ANCHOR", "BREATH_LEAD", "PROGRESSIVE_RELAXATION", "FIXATION_FADE" \] candidates = \[c for c in candidates if c in first_session_eligible\] if "BREATH_LEAD" in candidates: return "BREATH_LEAD" return "SOMATIC_ANCHOR" # 5. Previous session analysis effectiveness = self.\_get_effectiveness_scores(user_profile) # 6. Novelty / habituation check last_3 = self.\_get_last_n_strategies(user_profile\["user_id"\], n=3) if len(set(last_3)) == 1 and last_3\[0\] in candidates: # Same strategy 3x in a row — demote it habituated = last_3\[0\] candidates_without = \[c for c in candidates if c != habituated\] if candidates_without: candidates = candidates_without # 7. Arc template alignment arc = session_context.get("arc_template", "GENTLE_DESCENT") arc_preferred = ARC_STRATEGY_MAP.get(arc, \[\]) arc_candidates = \[c for c in candidates if c in arc_preferred\] if arc_candidates: candidates = arc_candidates # 8. Weighted random selection weights = \[effectiveness.get(c, 0.5) for c in candidates\] return random.choices(candidates, weights=weights, k=1)\[0\] # Arc → preferred strategies mapping ARC_STRATEGY_MAP = { "GENTLE_DESCENT": \["SOMATIC_ANCHOR", "BREATH_LEAD", "PROGRESSIVE_RELAXATION"\], "WAVE_PATTERN": \["FRACTIONATION", "ENTRAINMENT_HEAVY"\], "DEEP_PLATEAU": \["ENTRAINMENT_HEAVY", "COGNITIVE_OVERLOAD"\], "CONDITIONING_FOCUS": \["PACE_AND_LEAD", "SOMATIC_ANCHOR"\], "SLEEP_BRIDGE": \["BREATH_LEAD", "PROGRESSIVE_RELAXATION"\], }

## 4.2 Strategy History DB Table

CREATE TABLE IF NOT EXISTS strategy_history ( id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, strategy_id TEXT NOT NULL, started_at REAL NOT NULL, completed_at REAL, outcome TEXT CHECK(outcome IN ('success','partial','failure','redirected')), time_to_trance_s REAL, peak_trance_score REAL, redirected_to TEXT, redirect_reason TEXT, effectiveness_score REAL, eeg_snapshot TEXT, -- JSON: band powers at success/failure moment ppg_snapshot TEXT, -- JSON: HR, HRV, breath_rate at success/failure notes TEXT );

## 4.3 Effectiveness Scoring

SessionEvaluator computes an effectiveness_score (0.0–1.0) for each induction attempt after the induction phase completes (success, failure, or redirect):

def compute_effectiveness( strategy: InductionStrategy, actual_time_s: float, peak_trance_score: float, trance_variance_stabilize: float, rmssd_delta_ms: float, was_redirected: bool ) -> float: """Compute effectiveness score for a completed induction attempt.""" expected_min, expected_max = strategy.expected_time_to_trance_s # time_score: faster = better, capped at 1.0 time_score = 1.0 - clamp( (actual_time_s - expected_min) / (expected_max - expected_min), 0.0, 1.0 ) # depth_score: reaching 0.6 trance depth = perfect depth_score = clamp(peak_trance_score / 0.6, 0.0, 1.0) # stability_score: low variance during stabilize = good stability_score = 1.0 - clamp(trance_variance_stabilize / 0.1, 0.0, 1.0) # autonomic_score: 20ms RMSSD increase = perfect autonomic_score = clamp(rmssd_delta_ms / 20.0, 0.0, 1.0) # redirect_penalty redirect_penalty = -0.3 if was_redirected else 0.0 raw = (0.3 \* time_score + 0.3 \* depth_score + 0.2 \* stability_score + 0.2 \* autonomic_score + redirect_penalty) return clamp(raw, 0.0, 1.0)

The per-strategy running effectiveness is stored in user_profile.strategy_effectiveness as an exponential moving average (EMA) with α = 0.3, giving recent sessions 3× the weight of older ones while maintaining long-term trend awareness.

## 4.4 User Profile Integration

Add to the user_profile table (Doc 48 schema extension):

ALTER TABLE user_profile ADD COLUMN preferred_strategy TEXT; -- User's explicitly preferred strategy (nullable, set via settings UI) ALTER TABLE user_profile ADD COLUMN strategy_effectiveness TEXT DEFAULT '{}'; -- JSON dict: {"ENTRAINMENT_HEAVY": 0.72, "SOMATIC_ANCHOR": 0.85, ...} ALTER TABLE user_profile ADD COLUMN contraindication_flags TEXT DEFAULT '\[\]'; -- JSON list: \["photosensitive_epilepsy", "chronic_pain_tension_contraindicated"\]

# 5\. Live Control Keys

New live_control.json keys introduced by this document:

| **Key** | **Type** | **Writer** | **Description** |
| --- | --- | --- | --- |
| induction_strategy_id | str | SessionPlanner | Currently active induction strategy |
| --- | --- | --- | --- |
| induction_phase | str | InductionRunner | Current micro-phase within the strategy (e.g., "CAPTURE", "DESCEND") |
| --- | --- | --- | --- |
| induction_phase_elapsed_s | float | InductionRunner | Seconds elapsed in current micro-phase |
| --- | --- | --- | --- |
| induction_phase_progress | float | InductionRunner | 0.0–1.0 progress through current phase (elapsed / duration_max) |
| --- | --- | --- | --- |
| induction_target_frequency | float | InductionRunner | Current target entrainment frequency (Hz) |
| --- | --- | --- | --- |
| induction_breath_target | float | InductionRunner | Target breath rate (bpm) — written only during BREATH_LEAD strategy |
| --- | --- | --- | --- |
| induction_success | bool | InductionRunner | True when success_criteria met |
| --- | --- | --- | --- |
| induction_redirecting | bool | InductionRunner | True during strategy redirect transition |
| --- | --- | --- | --- |
| induction_redirect_to | str | InductionRunner | strategy_id of redirect target |
| --- | --- | --- | --- |

# 6\. InductionRunner Class

The InductionRunner is the real-time executor. It takes an InductionStrategy, ticks every second, applies stimulus parameters per the current phase, checks transition triggers and success/failure criteria, and manages redirects.

class InductionRunner: """Executes an InductionStrategy in real-time, writing stimulus parameters to live_control and monitoring physiological state for phase transitions, success, and failure.""" def \__init_\_(self, strategy: InductionStrategy, live: dict, db): self.strategy = strategy self.live = live self.db = db self.current_phase_idx = 0 self.phase_start_time = time.time() self.induction_start_time = self.phase_start_time self.peak_trance_scores = \[\] # for FRACTIONATION ratchet tracking self.history_row = self.\_create_history_row() # Write initial live_control state self.\_patch_live_init() def tick(self, eeg_state: dict, ppg_state: dict, imu_state: dict) -> str: """Called every second during INDUCTION phase. Returns: 'RUNNING' — still inducting 'INDUCTION_COMPLETE' — success criteria met 'REDIRECT' — switching to fallback strategy 'INDUCTION_FAILED' — no fallback available, induction failed """ phase = self.strategy.phase_sequence\[self.current_phase_idx\] elapsed = time.time() - self.phase_start_time total_elapsed = time.time() - self.induction_start_time # Apply phase stimulus config to live_control self.\_apply_stimulus(phase, elapsed) # Check global success criteria (not per-phase) if self.\_check_success(eeg_state, ppg_state, imu_state): self.\_complete('success', total_elapsed) return 'INDUCTION_COMPLETE' # Check failure criteria if self.\_check_failure(eeg_state, ppg_state, imu_state, total_elapsed): return self.\_handle_failure(total_elapsed) # Check phase transition trigger if self.\_check_transition(phase, eeg_state, ppg_state, imu_state, elapsed): self.\_advance_phase() elif elapsed > phase.duration_range_s\[1\]: self.\_handle_timeout(phase) # Update live_control with current state self.\_patch_live(elapsed, phase) return 'RUNNING' def \_handle_failure(self, total_elapsed: float) -> str: """Handle strategy failure — redirect or report.""" if self.strategy.redirect_strategy: redirect_to = self.strategy.redirect_strategy self.live\["induction_redirecting"\] = True self.live\["induction_redirect_to"\] = redirect_to self.\_complete('redirected', total_elapsed, redirect_to=redirect_to) return 'REDIRECT' self.\_complete('failure', total_elapsed) return 'INDUCTION_FAILED' def \_apply_stimulus(self, phase: InductionPhase, elapsed: float): """Merge phase.stimulus_params into live_control. Respects writer priority: User slider > LLM agent > InductionRunner > defaults """ for layer, params in phase.stimulus_params.items(): for key, value in params.items(): live_key = f"{layer}\_{key}" # Only write if no higher-priority writer has overridden if not self.\_is_overridden(live_key): self.live\[live_key\] = value def \_check_success(self, eeg: dict, ppg: dict, imu: dict) -> bool: """Check strategy-level success criteria.""" criteria = self.strategy.success_criteria trance = eeg.get("trance_score_v2", 0.0) min_score = criteria.get("trance_score_v2_min", 0.35) if trance &lt; min_score: return False # Check convergence rule if specified conv = criteria.get("convergence_rule") if conv == "2_of_3_axes": if not self.\_check_convergence(eeg): return False # Check sustain duration sustain = criteria.get("sustain_duration_s", 15) if not self.\_sustained_above(min_score, sustain): return False # Strategy-specific criteria if "ppg_hrv_rmssd" in criteria: if not self.\_check_rmssd_trend(ppg, criteria\["ppg_hrv_rmssd"\]): return False if "imu_stillness_index_min" in criteria: if imu.get("stillness_index", 0) < criteria\["imu_stillness_index_min"\]: return False if "ratchet_verified" in criteria: if not self.\_verify_ratchet(): return False return True def \_check_failure(self, eeg: dict, ppg: dict, imu: dict, elapsed: float) -&gt; bool: """Check strategy-level failure criteria.""" criteria = self.strategy.failure_criteria # Time-based failure max_time = criteria.get("after_elapsed_s") min_score = criteria.get("trance_score_v2_below") if max_time and min_score: if elapsed > max_time and eeg.get("trance_score_v2", 0) &lt; min_score: return True # User interaction (discomfort signal) if criteria.get("user_interaction_event_during"): target_phase = criteria\["user_interaction_event_during"\] current = self.strategy.phase_sequence\[self.current_phase_idx\] if (current.phase_name == target_phase and self.live.get("user_interaction_event")): return True # PPG unavailability (hard fail for PPG-dependent strategies) if criteria.get("alt") == "ppg_available_false": if not ppg.get("available", True): return True # Strategy-specific if criteria.get("imu_motion_contaminated"): if imu.get("motion_contaminated_consecutive", 0) &gt;= 3: current = self.strategy.phase_sequence\[self.current_phase_idx\] after = criteria.get("after_phase") if after and self.\_phase_index(after) is not None: if self.current_phase_idx > self.\_phase_index(after): return True return False def \_advance_phase(self): """Move to next phase in sequence.""" self.current_phase_idx += 1 self.phase_start_time = time.time() if self.current_phase_idx >= len(self.strategy.phase_sequence): # Past last phase — treat as timeout of final phase self.current_phase_idx = len(self.strategy.phase_sequence) - 1 def \_handle_timeout(self, phase: InductionPhase): """Handle phase duration timeout.""" action = phase.timeout_action if action == "advance": self.\_advance_phase() elif action == "extend": pass # Let it run (extend has its own max in LEAD_DOWN) elif action == "fail": self.\_handle_failure(time.time() - self.induction_start_time) def \_patch_live(self, elapsed: float, phase: InductionPhase): """Update live_control with current induction state.""" self.live\["induction_strategy_id"\] = self.strategy.strategy_id self.live\["induction_phase"\] = phase.phase_name self.live\["induction_phase_elapsed_s"\] = round(elapsed, 1) max_dur = phase.duration_range_s\[1\] self.live\["induction_phase_progress"\] = round( min(elapsed / max_dur, 1.0), 3 ) self.live\["induction_success"\] = False self.live\["induction_redirecting"\] = False def \_complete(self, outcome: str, total_elapsed: float, redirect_to: str = None): """Write completion row to strategy_history table.""" self.live\["induction_success"\] = (outcome == "success") self.db.execute( "UPDATE strategy_history SET completed_at=?, outcome=?, " "time_to_trance_s=?, peak_trance_score=?, redirected_to=? " "WHERE id=?", (time.time(), outcome, total_elapsed, max(self.peak_trance_scores, default=0.0), redirect_to, self.history_row) )

# 7\. Integration Map

How InductionRunner connects to the existing Somna architecture:

## 7.1 SessionDirector (Doc 48)

SessionDirector enters the INDUCTION phase → calls StrategySelector.select_strategy(user_profile, session_context) → instantiates InductionRunner(strategy, live, db) → calls InductionRunner.tick(eeg, ppg, imu) every second during the INDUCTION phase → when tick() returns 'INDUCTION_COMPLETE', SessionDirector transitions to DEEPENING. If tick() returns 'REDIRECT', SessionDirector instantiates a new InductionRunner with the redirect target strategy and continues. If 'INDUCTION_FAILED' (no redirect available), SessionDirector enters a graceful degradation path — switch to maintenance-level entrainment and attempt deepening from whatever state was achieved.

## 7.2 Conductor FSM

InductionRunner operates _within_ the Conductor's INDUCTION phase. It does not create new Conductor phases — it orchestrates stimulus parameters within the existing phase boundary. The Conductor sees INDUCTION as a single phase; InductionRunner's micro-phases are internal subdivisions invisible to the Conductor FSM.

## 7.3 DeliveryGate (Doc 35 / Doc 42)

InductionRunner writes stimulus parameters to live_control, but all actual delivery still passes through DeliveryGate's quad-gate (EEG gate, cardiac gate, respiratory gate, IMU gate). During early induction phases, DeliveryGate timeout thresholds should be relaxed: respiratory gate timeout at 15s for induction (vs 10s for maintenance), cardiac gate may be bypassed during ENTRAINMENT_HEAVY CAPTURE phase when physiological coupling hasn't yet been established.

## 7.4 ContentManager (Doc 46)

InductionRunner specifies content pool priorities per phase (e.g., SOMATIC_ANCHORING → WARMTH_COMFORT → DISSOLUTION). ContentManager handles actual word selection, PND compliance, prosodic targeting, and the aphantasia-first vocabulary constraints. The new PACING_TEMPLATE pool for PACE_AND_LEAD requires ContentManager support for runtime variable interpolation in sentence frames.

## 7.5 CrossmodalGainManifold (Doc 37)

InductionRunner writes target gains per layer (isochronic, binaural, TTS, SSB, background, GLSL). The gain manifold still enforces spectral occupancy limits and depth-dependent fadedown curves. InductionRunner gain requests are _suggestions_ — the manifold may clamp them to maintain crossmodal balance.

## 7.6 HabituationEngine (Doc 45)

Strategy rotation in StrategySelector (the "3 consecutive" rule in step 6) prevents macro-habituation to induction methods. Within-strategy micro-habituation (specific TTS phrases, specific binaural patterns) is handled by ContentManager's novelty rotation and the AM depth profiling system (Doc 44).

## 7.7 ConditioningEngine (Doc 43)

Each strategy's conditioning_hooks field specifies which CS-US pairings are naturally established during that induction. For example, SOMATIC_ANCHOR naturally conditions "somatic attention" (CS) → "relaxation response" (US). FRACTIONATION conditions "re-induction cue" (CS) → "rapid depth" (US). Over sessions, the induction process _itself_ becomes a conditioned stimulus for trance entry — this is the mechanism behind the common clinical observation that experienced hypnotic subjects enter trance faster with each session.

## 7.8 LLM Agent Context

InductionRunner writes induction_strategy_id and induction_phase to live_control.json. The LLM agent (Vesper) can read these to understand where in the induction process the user currently is. If the strategy is failing (trance_score not progressing, failure criteria approaching), the agent can provide contextual meta-commentary or adjust content tone — but cannot override InductionRunner's phase progression or stimulus parameters directly.

# Appendix A: Strategy Quick-Reference Table

| **Strategy ID** | **Display Name** | **Gruzelier Stage** | **Time Range (s)** | **PPG Required** | **Session Unlock** | **Best For Arc** | **Redirect Target** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ENTRAINMENT_HEAVY | Neural Frequency Lock | I   | 120–300 | No  | 0   | WAVE_PATTERN, DEEP_PLATEAU | BREATH_LEAD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SOMATIC_ANCHOR | Body Awareness Descent | II  | 180–420 | No  | 0   | GENTLE_DESCENT, CONDITIONING_FOCUS | BREATH_LEAD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BREATH_LEAD | Respiratory Pacing | I+II | 150–360 | Yes | 0   | GENTLE_DESCENT, SLEEP_BRIDGE | SOMATIC_ANCHOR / ENTRAINMENT_HEAVY |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PROGRESSIVE_RELAXATION | Tension-Release Cascade | II  | 240–480 | No  | 0   | GENTLE_DESCENT, SLEEP_BRIDGE | ENTRAINMENT_HEAVY |
| --- | --- | --- | --- | --- | --- | --- | --- |
| COGNITIVE_OVERLOAD | Saturation Gate | I (forced→II) | 90–240 | No  | 3   | DEEP_PLATEAU | SOMATIC_ANCHOR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FRACTIONATION | Depth Ratchet | I+II | 180–360 | No  | 2   | WAVE_PATTERN | ENTRAINMENT_HEAVY |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FIXATION_FADE | Attentional Narrowing | I   | 120–300 | No  | 0   | GENTLE_DESCENT | SOMATIC_ANCHOR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PACE_AND_LEAD | Physiological Mirror | I+II | 150–360 | Yes (hard) | 1   | CONDITIONING_FOCUS | ENTRAINMENT_HEAVY / SOMATIC_ANCHOR |
| --- | --- | --- | --- | --- | --- | --- | --- |

# Appendix B: EEG Success Markers Summary

Consolidated EEG markers that indicate successful induction, applicable across all strategies. These are the signals InductionRunner.\_check_success() evaluates:

| **Marker** | **Direction** | **Significance** | **Source** |
| --- | --- | --- | --- |
| Alpha power (8–12 Hz) | Initial ↑ then ↓ | Initial increase = relaxation onset. Subsequent decrease as theta takes over = trance deepening. | Gruzelier 1998 |
| --- | --- | --- | --- |
| Theta power (4–8 Hz) | Sustained ↑ | Primary trance entry marker. Sustained theta increase across frontal and central sites indicates absorption and reduced executive control. | Jensen & Barrett 2024 |
| --- | --- | --- | --- |
| Peak alpha frequency (PAF) | ↓ by 0.5–1.0 Hz | PAF slowing is a reliable depth indicator in high-susceptible subjects. Measurable within 2–3 minutes of successful induction. | Landry et al 2024 |
| --- | --- | --- | --- |
| Frontal midline theta (Fmθ) | ↑   | Indicates absorption and focused internal attention. Elevated in meditation and hypnotic absorption states. | Brandmeyer & Delorme 2020 |
| --- | --- | --- | --- |
| Interhemispheric alpha coherence | ↑   | Increased bilateral alpha coherence indicates hypnotic state establishment. Distinguishes genuine trance from simple relaxation. | Gruzelier 1998 |
| --- | --- | --- | --- |
| 1/f spectral slope | Steepening | Steeper aperiodic slope indicates cortical inhibition and depth. Used in trance_score_v2 computation (Doc 38). | Doc 38 |
| --- | --- | --- | --- |
| BIS-equivalent index | ↓ from ~97 to ~86 | Bispectral-equivalent computation drops during hypnotic induction. Values below 90 indicate moderate depth. | Zech et al 2023 |
| --- | --- | --- | --- |
| Beta power (13–30 Hz) | ↓   | Decreased beta indicates reduced critical evaluation, analytical processing, and executive vigilance. Stage II marker. | Gruzelier 1998 |
| --- | --- | --- | --- |

# Appendix C: Aphantasia Adaptation Notes

Confirmation that all eight strategies in this library are fully aphantasia-compatible:

- **No strategy requires visual imagery.** Every strategy operates through external stimulus (screen-driven visual entrainment, audio delivery) combined with somatic/interoceptive/conceptual content. The visual display layer shows geometric patterns and colour fields for entrainment — it never asks the user to generate internal mental images.
- **All visual components are stimulus-driven (external), not imagery-driven (internal).** The golden spiral, Ganzfeld fields, GLSL post-processing effects, and luminance modulations are retinal stimuli that drive frequency following response through the visual cortex. They work identically regardless of the user's imagery capacity.
- **TTS content exclusively uses somatic, interoceptive, proprioceptive, auditory, and conceptual vocabulary.** Content pools (Doc 46) are designed aphantasia-first. Primary categories: pressure, temperature, weight, texture, tingling, pulsing, heaviness, warmth, settling, sinking, expanding, dissolving. Zero references to seeing, picturing, imagining, or visualizing anything in the mind's eye.
- **Content pools (Doc 36) are already designed aphantasia-first.** The SOMATIC_ANCHORING, WARMTH_COMFORT, DISSOLUTION, and IDENTITY pools all operate through non-visual sensory and conceptual channels. The Doc 46 content methodology explicitly prohibits visualization-dependent language.
- **Research confirms aphantasic individuals often show enhanced somatic/interoceptive processing.** The Institute of Consciousness (2024) review found that aphantasic individuals frequently report heightened bodily awareness, stronger interoceptive sensitivity, and robust emotional/conceptual processing — all of which are the exact channels Somna's induction strategies target. SOMATIC_ANCHOR and BREATH_LEAD are predicted to be particularly effective for this population because they directly leverage the channels where aphantasic processing is strongest.

**Design Principle**

Somna's aphantasia-first design is not an accommodation or workaround — it is the primary design. The somatic/interoceptive/conceptual channels targeted by these strategies are arguably more direct pathways to autonomic regulation than visual imagery, which requires an additional cognitive translation step. An aphantasic user is not missing a channel; they are skipping an intermediary.

— End of Doc 49. Reese, 5 April 2026. Ready for implementation.