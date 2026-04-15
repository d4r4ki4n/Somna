# Doc 50 — GENUS SessionDirector Integration Bridge

**Somna Technical Specification**

**Status:** Specification — ready for implementation

**Author:** Ed

**Date:** 5 April 2026

**Version:** 1.0

| **Field** | **Value** |
| --- | --- |
| **Depends on** | Doc 48 (Session Director Architecture), Doc 49 (Induction Strategy Library), Doc 43 (Conditioning & Reinforcement), Doc 42 (Cardiac-Phase Gating & Autonomic-Inertial), Doc 36 (Neural-State Semantic Selection), Doc 39 (Sleep Enhancement), Doc 40 (TMR), GENUS Reference Document |
| --- | --- |
| **Modifies** | conductor.py, session_director.py, session_planner.py, delivery_gate.py, eeg_engine.py, live_control.json schema |
| --- | --- |

# 1\. Purpose

This document specifies how the SessionDirector (Doc 48) invokes, manages, and transitions to/from GENUS 40 Hz gamma entrainment blocks within Somna's session architecture. The GENUS Reference Document defines the stimulus parameters, safety requirements, and research basis. This document wires those capabilities into the session lifecycle.

GENUS and trance serve fundamentally different neurological functions. Trance targets alpha (8–12 Hz) and theta (4–8 Hz) suppression of critical evaluation. GENUS targets gamma (40 Hz) entrainment for neuroprotective glymphatic activation and enhanced encoding via frontal-hippocampal coupling. These are mutually exclusive frequency domains — they cannot coexist in the same temporal window.

This mutual exclusivity is not a limitation. It creates a three-stage conditioning pipeline that emerged from the intersection of Docs 43, 36, 40, and the GENUS research:

**Encode** (GENUS) → **Deepen** (Trance) → **Consolidate** (Sleep)

Each stage leverages a different brain state for a different function. GENUS drives frontal-hippocampal coupling during active cognitive engagement (Mlinaric 2025: intracranial EEG confirmed enhanced entrainment with cognitive load). Trance suppresses critical evaluation, allowing suggestions to bypass prefrontal filtering. Sleep TMR replays cued content during slow-oscillation up-states for long-term consolidation.

# 2\. Frequency Exclusivity Principle

**Rule:** At any point during a session, exactly one frequency domain is active. The system operates in one of three frequency modes:

| **Mode** | **Target Band** | **Entrainment Method** | **Content Type** |
| --- | --- | --- | --- |
| GAMMA | 40 Hz | Isochronic clicks + stroboscopic flicker | Cognitive engagement: affirmations read actively, agent prompts, focus tasks |
| --- | --- | --- | --- |
| ALPHA_THETA | 8–12 Hz (alpha) / 4–8 Hz (theta) | Binaural secondary + isochronic primary + visual spiral at IAF | Hypnotic: veils, subliminals, TTS whisper, somatic anchoring |
| --- | --- | --- | --- |
| SLEEP | 0.5–4 Hz (delta) / 12–15 Hz (spindle) | SO phase-locked pink noise, spindle-gated TMR | Consolidation: TMR cues, SWE bursts, HTW whisper |
| --- | --- | --- | --- |

**Transitions between modes require a dedicated transition phase.** No stimulus from the departing mode may overlap with any stimulus from the arriving mode. The transition phases are specified in Section 5.

**Corollary:** All entrainment parameters (beat frequencies, visual rotation speeds, isochronic rates, modulation depths) are bound to the active mode. When the Conductor enters a GENUS phase, all alpha/theta entrainment ceases. When it exits, all gamma stimulation ceases before alpha/theta begins.

# 3\. GENUS_BLOCK — Conductor Phase Specification

GENUS runs as a first-class Conductor phase called GENUS_BLOCK, not as a separate session system or pre/post protocol. This keeps it within the existing phase cascade, subject to the same authority framework (Doc 48 Section: 4-tier authority), and visible to the SessionDirector's macro/meso/micro triple loop.

## 3.1 Phase Definition

Phase: GENUS_BLOCK Entry sources: SESSION_START (GENUS-first arcs), TRANSITION_ASCENT (from trance), EMERGENCE (standalone GENUS after trance) Exit targets: TRANSITION_DESCENT (to trance), GENUS_COOLDOWN (standalone end), EMERGENCY_STOP Duration: Configurable. Standalone: 3600 s (60 min, per clinical protocol). Hybrid pre-trance: 600–1800 s (10–30 min). Hybrid post-trance: 600–1200 s (10–20 min).

## 3.2 Internal Sub-Phases

GENUS_BLOCK contains three internal sub-phases managed by the Conductor:

| **Sub-Phase** | **Duration** | **Function** |
| --- | --- | --- |
| GENUS_RAMP_UP | 60–120 s | Audio-only isochronic clicks begin at 50% amplitude, ramp to target over 60 s. Visual flicker begins at 30% modulation depth after audio is stable (30 s delay), ramps to 100% over 30 s. Allows the brain to entrain gradually. Baseline gamma power measured during the first 15 s (audio-only, pre-flicker) for entrainment ratio calculation. |
| --- | --- | --- |
| GENUS_ACTIVE | Remaining duration minus cooldown | Full 40 Hz AV stimulation at spec parameters. Cognitive engagement content delivered via DeliveryGate (GENUS mode). Entrainment ratio monitored continuously. |
| --- | --- | --- |
| GENUS_WIND_DOWN | 60 s | Visual flicker fades from 100% to 0% over 30 s. Audio clicks fade from target amplitude to 0% over the following 30 s. No content delivery. This is not TRANSITION_DESCENT — it is the internal shutdown of GENUS stimuli before any mode transition occurs. |
| --- | --- | --- |

## 3.3 State Machine

┌──────────────────┐ │ SESSION_START │ │ (GENUS-first) │ └────────┬─────────┘ │ ▼ ┌──────────────────┐ │ GENUS_RAMP_UP │──── entrainment_ratio < 1.2 after 120s ──▶ GENUS_FALLBACK └────────┬─────────┘ │ entrainment_ratio ≥ 1.5 ▼ ┌──────────────────┐ │ GENUS_ACTIVE │──── duration elapsed ──▶ GENUS_WIND_DOWN │ │──── user interrupt ──▶ GENUS_WIND_DOWN │ │──── safety trigger ──▶ EMERGENCY_STOP │ │──── entrainment_ratio < 1.2 for 120s ──▶ GENUS_FALLBACK └────────┬─────────┘ │ ▼ ┌──────────────────┐ │ GENUS_WIND_DOWN │──── 60s elapsed ──▶ \[next phase per arc\] └──────────────────┘ GENUS_FALLBACK: Log failure reason. If hybrid arc, skip to TRANSITION_DESCENT and proceed to trance. If standalone, proceed to GENUS_COOLDOWN → session end. Do not retry GENUS in the same session.

## 3.4 GENUS_COOLDOWN

A 120-second post-GENUS settling phase for standalone GENUS sessions (no trance follow-on). No stimulation. EEG continues recording for post-session gamma persistence measurement. The agent may deliver a brief verbal summary of the session via TTS at conversational gain.

# 4\. Arc Templates

Doc 48 defines five arc templates for the SessionDirector (GENTLE_DESCENT, WAVE_PATTERN, DEEP_PLATEAU, CONDITIONING_FOCUS, SLEEP_BRIDGE). This document adds three GENUS-aware templates.

## 4.1 GENUS_STANDALONE

Pure GENUS session. No trance component.

GENUS_RAMP_UP → GENUS_ACTIVE (3600s) → GENUS_WIND_DOWN → GENUS_COOLDOWN → SESSION_END

**Use case:** Daily neuroprotective maintenance. User wants the clinical protocol dose without trance. Also used when session time is limited to ~65 minutes.

**Content strategy during GENUS_ACTIVE:** Agent delivers cognitive engagement content — affirmations presented as active reading tasks on the veil layer, comprehension prompts requiring internal response, somatic awareness cues that maintain frontal engagement without inducing relaxation. Content drawn from WARMTH_COMFORT and GROUNDING_TEXTURE pools (Doc 36) — avoid DISSOLUTION and STILLNESS_EMPTINESS pools which are trance-targeted.

## 4.2 GENUS_TRANCE_HYBRID

GENUS block followed by trance. Implements the Encode → Deepen pipeline within a single session.

GENUS_RAMP_UP → GENUS_ACTIVE (600–1800s) → GENUS_WIND_DOWN → TRANSITION_DESCENT (180s) → INDUCTION → \[normal trance cascade per Doc 49\] → EMERGENCE → SESSION_END

**Use case:** Full-spectrum session. GENUS encodes content with enhanced frontal-hippocampal coupling; the subsequent trance deepens the same content with prefrontal suppression removed. The transition phase bridges the two frequency domains.

**Content linkage:** The SessionDirector ensures that content pools activated during GENUS_ACTIVE overlap with those targeted during the trance phase. This is not coincidental — the same pool IDs are passed to both phases. The GENUS block primes the neural substrate; the trance block exploits it.

**Duration budget:** SessionDirector allocates GENUS_ACTIVE duration based on total available session time:

| **Total Session Time** | **GENUS_ACTIVE** | **Trance Cascade** |
| --- | --- | --- |
| 90 min | 20 min | 60 min |
| --- | --- | --- |
| 120 min | 30 min | 75 min |
| --- | --- | --- |
| 150 min | 30 min | 105 min |
| --- | --- | --- |

Transition phases and ramp/wind-down consume the remainder.

## 4.3 GENUS_NEUROPROTECTION

Extended GENUS with abbreviated trance focused on conditioning reinforcement.

GENUS_RAMP_UP → GENUS_ACTIVE (2400–3600s) → GENUS_WIND_DOWN → TRANSITION_DESCENT (180s) → CONDITIONING_FOCUS \[abbreviated, 20–30 min\] → EMERGENCE → SESSION_END

**Use case:** User prioritizes neuroprotection but wants to maintain conditioning strength. The abbreviated trance phase runs only the CONDITIONING_FOCUS arc (Doc 48) targeting pools whose Rescorla-Wagner strength (Doc 43) has decayed below maintenance threshold.

# 5\. Transition Phases

## 5.1 TRANSITION_DESCENT (Gamma → Alpha/Theta)

Duration: 180 seconds (3 minutes). Non-negotiable minimum.

**Purpose:** Bridge the perceptual and neurological gap between active gamma engagement and receptive alpha/theta trance. The user's brain must shift from high-frequency externally-focused processing to low-frequency internally-focused processing.

**Sequence:**

| **Time (s)** | **Audio** | **Visual** | **Content** |
| --- | --- | --- | --- |
| 0–30 | Silence (GENUS audio already ceased in WIND_DOWN) | Black screen, no stimulation | None |
| --- | --- | --- | --- |
| 30–90 | Pink noise fades in from 0% to 40% gain. Binaural carrier tone fades in at 10% gain. | Background color fades from black to warm Ganzfeld base color (Doc 47). Luminance rises slowly. | Agent delivers a single grounding phrase via TTS at conversational gain: short, somatic, present-tense. "Notice the weight of your body." |
| --- | --- | --- | --- |
| 90–150 | Binaural beat begins at 10 Hz (alpha), amplitude rises to target. Isochronic alpha pulses begin at 30% depth. Pink noise holds. | Spiral geometry fades in at 0% opacity → 30%. Rotation begins at IAF. Ganzfeld breathing begins. | Agent begins pace-and-lead (Doc 49): matching current state before leading toward relaxation. |
| --- | --- | --- | --- |
| 150–180 | Full alpha/theta entrainment parameters per induction strategy. | Full visual entrainment per Doc 47. | Induction micro-phase 1 begins. |
| --- | --- | --- | --- |

**Key Constraint**

No alpha/theta stimulus may begin before T+30s. No GENUS stimulus may persist past T+0s. The 30-second silence window is a hard perceptual boundary.

## 5.2 TRANSITION_ASCENT (Alpha/Theta → Gamma)

Duration: 180 seconds. Used only in post-trance GENUS blocks (rare; primarily for research/testing).

**Sequence:** Mirror of TRANSITION_DESCENT. Alpha/theta entrainment fades out over 0–60s. Silence window 60–90s. GENUS audio ramp begins at 90s. Visual flicker begins at 120s. Full GENUS by 180s.

**Note:** This transition follows EMERGENCE. The user is already at waking-state arousal before TRANSITION_ASCENT begins. The silence window is shorter (30s vs 60s) because the direction is toward alertness, not away from it.

# 6\. SessionDirector Decision Logic

## 6.1 GENUS Invocation Criteria

The SessionPlanner (Doc 48 macro loop) evaluates GENUS eligibility at session planning time. GENUS is included in the session arc when ANY of:

| **Criterion** | **Source** | **Condition** |
| --- | --- | --- |
| User request | Session config / UI | genus_requested = true |
| --- | --- | --- |
| Neuroprotection schedule | session_history DB | Time since last GENUS session ≥ 20 hours (target: daily) |
| --- | --- | --- |
| Conditioning encode needed | Doc 43 Rescorla-Wagner tracker | Any pool has new content not yet GENUS-encoded AND user has completed ≥ 3 prior GENUS sessions (familiarity threshold) |
| --- | --- | --- |
| Monitor capable | system_config | monitor_refresh_rate ≥ 80 OR genus_audio_only_mode = true |
| --- | --- | --- |

GENUS is excluded when ANY of:

| **Criterion** | **Source** | **Condition** |
| --- | --- | --- |
| Epilepsy warning not acknowledged | user_config DB | genus_epilepsy_ack = false (first-session modal not yet confirmed) |
| --- | --- | --- |
| Available time insufficient | Session config | Total session time < 15 minutes (minimum viable GENUS block = 10 min active + 5 min ramp/wind-down) |
| --- | --- | --- |
| Previous session failure | session_history DB | Last GENUS session ended in GENUS_FALLBACK AND no parameter adjustments made since |
| --- | --- | --- |
| User opt-out | user_config DB | genus_enabled = false |
| --- | --- | --- |
| Sleep-targeted session | Arc template | SLEEP_BRIDGE arc — GENUS is contraindicated before sleep onset; 40 Hz gamma is an arousal signal |
| --- | --- | --- |

## 6.2 Arc Selection Logic

When GENUS is eligible, the SessionPlanner selects the arc template:

def select_genus_arc(session_time_s, genus_priority, conditioning_needs): if session_time_s < 900: # < 15 min return None # GENUS excluded if genus_priority == 'standalone' or session_time_s < 2400: # < 40 min return 'GENUS_STANDALONE' if conditioning_needs.any_below_threshold(): return 'GENUS_NEUROPROTECTION' # long GENUS + abbreviated conditioning trance return 'GENUS_TRANCE_HYBRID' # balanced encode → deepen

## 6.3 GENUS as Occasion Setter

Per Doc 43 paradigm 5 (Occasion Setting): the distinctive multisensory experience of 40 Hz stimulation — the rhythmic clicking, the flicker, the unique perceptual gestalt — becomes associated with conditioning content delivered during GENUS_ACTIVE. After repeated pairings, onset of 40 Hz stimulation begins eliciting preparatory conditioned responses BEFORE content delivery begins.

**Implementation cost: zero.** This is an emergent property of delivering conditioning content during a perceptually distinctive context. The SessionDirector does not need to manage it — it happens automatically. However, it means GENUS sessions should consistently pair with conditioning content to strengthen the occasion-setting association. The SessionPlanner should prefer GENUS_TRANCE_HYBRID or GENUS_NEUROPROTECTION over GENUS_STANDALONE when conditioning pools have active content.

# 7\. DeliveryGate — GENUS Mode

Doc 42 specifies a quad-gate for stimulus delivery: respiratory phase × alpha phase × cardiac diastole × motion clearance. GENUS mode modifies one axis and retains the other three.

## 7.1 Gate Axis Substitution

| **Gate Axis** | **Trance Mode (Doc 42)** | **GENUS Mode** |
| --- | --- | --- |
| Respiratory phase | Expiration window (phase 0.5–0.85) | **Retained.** Content delivered during expiration for maximal somatic receptivity. |
| --- | --- | --- |
| Neural phase | Alpha trough (phase 0.4–0.6 of IAF cycle) | **Replaced.** Gamma verification gate: entrainment_ratio ≥ 1.5 over the last 5 s. If the brain is not entrained, content delivery is gated — the user is not in the receptive state that justifies delivery. |
| --- | --- | --- |
| Cardiac phase | Diastole (R-peak + 300ms to next R - 100ms) | **Retained.** Diastole enhances sensory processing regardless of frequency domain. |
| --- | --- | --- |
| Motion clearance | imu_motion_contaminated = false | **Retained.** Motion artifacts corrupt EEG measurement needed for entrainment verification. |
| --- | --- | --- |
| SQI | eeg_sqi ≥ 0.6 | **Retained but threshold adjusted to 0.4.** 40 Hz visual flicker creates electromagnetic artifacts that depress SQI. A lower threshold prevents the gate from blocking all delivery during visual GENUS. Audio-only GENUS retains 0.6 threshold. |
| --- | --- | --- |

## 7.2 Gamma Verification Gate

class GammaVerificationGate: """ Replaces AlphaPhaseGate during GENUS_BLOCK phases. Instead of waiting for a specific phase of the alpha cycle (which doesn't exist during gamma entrainment), this gate checks whether 40 Hz entrainment is actually occurring. If the brain isn't entrained, content delivery would not benefit from the enhanced encoding pathway — gate stays closed. """ def \__init_\_(self): self.entrainment_window_s = 5.0 self.min_ratio = 1.5 # moderate entrainment threshold self.strong_ratio = 2.0 # strong entrainment — prioritize delivery def is_open(self, eeg_state: dict) -> bool: ratio = eeg_state.get('genus_entrainment_ratio', 0.0) return ratio >= self.min_ratio def delivery_priority(self, eeg_state: dict) -> float: """ Returns 0.0–1.0 priority scalar. SessionDirector uses this to decide whether to deliver high-value content (strong entrainment) or low-value filler (moderate entrainment). """ ratio = eeg_state.get('genus_entrainment_ratio', 0.0) if ratio >= self.strong_ratio: return 1.0 if ratio >= self.min_ratio: return (ratio - self.min_ratio) / (self.strong_ratio - self.min_ratio) return 0.0

## 7.3 Content Priority During GENUS

The delivery_priority() scalar from the gamma verification gate feeds into content selection:

| **Priority Range** | **Content Tier** | **Examples** |
| --- | --- | --- |
| 0.8–1.0 (strong entrainment) | Tier 1: High-value conditioning content | Novel affirmations, agent comprehension prompts, new pool introductions |
| --- | --- | --- |
| 0.5–0.8 (moderate entrainment) | Tier 2: Reinforcement content | Previously encountered affirmations, somatic awareness cues |
| --- | --- | --- |
| 0.0–0.5 (weak/no entrainment) | No content delivery | Gate closed. Stimulation continues but content is withheld until entrainment strengthens. |
| --- | --- | --- |

# 8\. EEG Measurement During GENUS

## 8.1 The Artifact Problem

40 Hz visual flicker creates two artifact sources in EEG:

1.  **Electromagnetic interference:** Monitor refresh cycles at 40 Hz bleed into scalp electrodes.
2.  **Eye movement artifacts:** Pupillary light reflex and microsaccades driven by flicker generate frontal EMG contamination.

These artifacts inflate measured 40 Hz power, making entrainment ratio unreliable during visual flicker.

## 8.2 Measurement Strategy

**Audio-only verification windows.** Every 60 seconds during GENUS_ACTIVE, visual flicker pauses for a 5-second measurement window. Audio continues uninterrupted. Gamma power measured during this window reflects neural entrainment without visual artifact contamination.

Timeline (60s cycle): \[──── visual + audio (55s) ────\]\[── audio only (5s) ──\] ↑ measurement window genus_entrainment_ratio = 40Hz_power_measurement_window / 40Hz_power_baseline

**Baseline:** Measured during the first 15 seconds of GENUS_RAMP_UP (audio-only, before visual flicker begins). Stored as genus_baseline_gamma in session state.

**Fallback:** If genus_visual_enabled = false (audio-only mode), no measurement windows needed. Continuous 40 Hz power monitoring is valid because there is no visual artifact source. Entrainment ratio computed continuously with 5-second sliding window.

## 8.3 Muse 2 Channel Selection for Gamma

| **Channel** | **Location** | **GENUS Utility** |
| --- | --- | --- |
| AF7 | Left frontal | Primary gamma measurement — frontal cortex is the target for cognitive engagement effects |
| --- | --- | --- |
| AF8 | Right frontal | Primary gamma measurement — bilateral frontal average |
| --- | --- | --- |
| TP9 | Left temporal | Secondary — confirms entrainment propagation to temporal regions |
| --- | --- | --- |
| TP10 | Right temporal | Secondary — confirms entrainment propagation to temporal regions |
| --- | --- | --- |

**Entrainment ratio** = mean(AF7_40Hz, AF8_40Hz) / baseline. Temporal channels logged for research telemetry but not used in gate decisions.

## 8.4 Narrow-Band Power Extraction

def compute_gamma_power(eeg_samples, sample_rate=256, target_hz=40.0, bandwidth=2.0): """ Extract 40 Hz narrow-band power from EEG. Uses FFT over the measurement window. Band: 38–42 Hz. Returns mean power spectral density in the target band. Parameters ---------- eeg_samples : np.ndarray — shape (n_channels, n_samples), channels = \[TP9, AF7, AF8, TP10\] sample_rate : int — 256 Hz for Muse 2 DEFAULT_PRESET target_hz : float — 40.0 bandwidth : float — +/- 2 Hz → 38–42 Hz band """ n = eeg_samples.shape\[1\] freqs = np.fft.rfftfreq(n, d=1.0/sample_rate) # Frontal channels only (AF7=index 1, AF8=index 2) frontal = eeg_samples\[1:3, :\] # shape (2, n_samples) fft_result = np.abs(np.fft.rfft(frontal, axis=1)) \*\* 2 band_mask = (freqs >= target_hz - bandwidth) & (freqs <= target_hz + bandwidth) band_power = fft_result\[:, band_mask\].mean() return band_power

# 9\. Content Strategy During GENUS

## 9.1 Why Content Matters

Mlinaric 2025 (11 patients, 490 intracranial contacts) demonstrated that cognitive engagement during 40 Hz stimulation ENHANCES entrainment strength and spatial extent. Information flow shifts from frontal cortex to hippocampus — the encoding pathway. Passive exposure (Cognito device, DIY setups) does not produce this effect.

Somna is the only GENUS implementation that layers interactive cognitive content over flicker. This is a structural advantage backed by intracranial data.

## 9.2 Content Delivery Modes During GENUS

Three content channels operate during GENUS_ACTIVE:

| **Channel** | **Method** | **Content Type** | **Gain** |
| --- | --- | --- | --- |
| Veil text | ScrollingVeilLayer (Doc 47) | Affirmations rendered as readable text, scrolling at a pace requiring active reading | Visual: rendered OVER the flicker layer (flicker = background, text = foreground). Text must be high-contrast against alternating black/white frames — use a solid semi-transparent backing panel behind text. |
| --- | --- | --- | --- |
| TTS voice | TTS at conversational volume | Agent prompts, comprehension questions, somatic cues | Audio: mixed over isochronic clicks. TTS gain = 60–80% relative to click volume. Clicks remain perceptually dominant. |
| --- | --- | --- | --- |
| Subliminal text (SSB) | SubSensoryBridgeLayer (Doc 47) | Priming phrases matching active pool | Standard SSB parameters per Doc 47. Rendered on the flicker layer — subliminal timing exploits the 12.5ms ON frames for sub-threshold presentation. |
| --- | --- | --- | --- |

## 9.3 Content Pool Selection

During GENUS_BLOCK, content is drawn from a restricted pool set:

| **Pool** | **GENUS Use** | **Rationale** |
| --- | --- | --- |
| WARMTH_COMFORT | Yes | Somatic, grounding, compatible with alert engagement |
| --- | --- | --- |
| GROUNDING_TEXTURE | Yes | Interoceptive awareness, present-tense, maintains frontal activation |
| --- | --- | --- |
| SOMATIC_ANCHORING | Yes | Body-focused, concrete, high frontal engagement |
| --- | --- | --- |
| IDENTITY | Conditional | Only if GENUS_TRANCE_HYBRID or GENUS_NEUROPROTECTION arc — primes identity content for trance deepening |
| --- | --- | --- |
| DISSOLUTION | No  | Incompatible with alert, engaged GENUS state |
| --- | --- | --- |
| STILLNESS_EMPTINESS | No  | Incompatible with active cognitive engagement |
| --- | --- | --- |

## 9.4 Agent Behavior During GENUS

The LLM agent (somna_agent.py) operates in a distinct mode during GENUS_BLOCK:

- **Tone:** Conversational, present-tense, alert. NOT hypnotic, NOT drowsy, NOT whispered.
- **Function:** Cognitive engagement facilitator. Asks questions that require internal processing ("Notice where in your body you feel most relaxed right now"). Does NOT use Milton Model patterns (Doc 46) — those are reserved for trance.
- **Pacing:** One prompt every 45–90 seconds. Sufficient silence between prompts for the user to process internally. Prompts timed to DeliveryGate GENUS mode openings.
- **Content linkage:** When the session arc is GENUS_TRANCE_HYBRID, the agent's GENUS-phase prompts should introduce themes that will be deepened during trance. Example: GENUS phase introduces "Notice the warmth in your hands" → Trance phase deepens with "That warmth spreading now, all by itself, deeper..."

# 10\. Conditioning Integration

## 10.1 Three-Stage Pipeline

The Encode → Deepen → Consolidate pipeline operates across the full 24-hour cycle:

| **Stage** | **Brain State** | **Mechanism** | **Doc** |
| --- | --- | --- | --- |
| **Encode** | GENUS: 40 Hz gamma, alert, engaged | Frontal-hippocampal coupling drives content into episodic memory. Enhanced by cognitive engagement (Mlinaric 2025). 40 Hz sensory context serves as occasion setter (Doc 43 paradigm 5). | This doc + GENUS Reference |
| --- | --- | --- | --- |
| **Deepen** | Trance: alpha/theta, receptive, prefrontal suppression | Milton Model suggestions bypass critical evaluation. Conditioned associations strengthened via evaluative conditioning (Doc 43 paradigm 2). State-dependent encoding (Doc 43 paradigm 4) binds content to trance state. | Doc 36, Doc 43, Doc 46 |
| --- | --- | --- | --- |
| **Consolidate** | Sleep: NREM slow oscillations + spindles | TMR replays cued content during SO up-states (Doc 40). Spindle-gated replay transfers hippocampal traces to neocortex. HTW (Doc 41) exploits N1 windows for additional reinforcement. | Doc 39, Doc 40, Doc 41 |
| --- | --- | --- | --- |

## 10.2 Cross-Stage Content Tracking

The SessionDirector maintains a content_pipeline state that tracks which content items have progressed through each stage:

content_pipeline = { "pool_id": "WARMTH_COMFORT", "item_hash": "a3f7c9...", "genus_encoded": True, # Delivered during GENUS_ACTIVE with entrainment_ratio >= 1.5 "genus_session_id": 47, "trance_deepened": True, # Delivered during trance DEEPEN/MAINTAIN phase "trance_session_id": 47, "tmr_consolidated": False, # Not yet replayed during sleep TMR "tmr_priority": 0.82, # ConsolidationScheduler priority (Doc 40) }

Items that complete all three stages receive a pipeline_complete flag. The ConsolidationScheduler (Doc 40) prioritizes items that have been GENUS-encoded AND trance-deepened but not yet TMR-consolidated — these have the highest consolidation potential.

## 10.3 Rescorla-Wagner Integration

Doc 43's Rescorla-Wagner strength tracker receives an encoding_bonus when content is delivered during verified GENUS entrainment:

\# In conditioning_engine.py, during strength update: if delivery_context == 'GENUS' and entrainment_ratio >= 1.5: encoding_bonus = 0.15 # 15% boost to learning rate for GENUS-encoded content alpha_effective = alpha \* (1.0 + encoding_bonus)

This bonus reflects the enhanced encoding pathway demonstrated by Mlinaric 2025 intracranial data. It is conservative — the actual neural advantage is likely larger, but the Rescorla-Wagner model is a simplification.

# 11\. Live Control Interface

## 11.1 New Keys

All GENUS runtime state is managed through live_control.json via \_patch_live(). Keys from the GENUS Reference Document are retained. This section adds session-integration keys:

{ "genus_active": false, "genus_frequency": 40.0, "genus_audio_pulse_ms": 1.0, "genus_visual_duty_cycle": 0.5, "genus_audio_enabled": true, "genus_visual_enabled": true, "genus_session_duration_min": 60, "genus_modulation_depth": 1.0, "genus_session_start_time": null, "genus_phase": "IDLE", "genus_sub_phase": null, "genus_entrainment_ratio": 0.0, "genus_baseline_gamma": null, "genus_measurement_window_active": false, "genus_content_tier": 0, "genus_fallback_reason": null, "genus_sessions_completed": 0, "genus_last_session_ts": null, "genus_audio_ramp_pct": 0.0, "genus_visual_ramp_pct": 0.0 }

## 11.2 Key Semantics

| **Key** | **Type** | **Writer** | **Description** |
| --- | --- | --- | --- |
| genus_phase | string | Conductor | Current GENUS lifecycle phase: IDLE, RAMP_UP, ACTIVE, WIND_DOWN, COOLDOWN, FALLBACK |
| --- | --- | --- | --- |
| genus_sub_phase | string or null | Conductor | Sub-phase within GENUS_ACTIVE if applicable |
| --- | --- | --- | --- |
| genus_entrainment_ratio | float | eeg_engine | Ratio of current frontal 40 Hz power to baseline. Updated every measurement window (60s cycle) during visual GENUS; continuously during audio-only GENUS. |
| --- | --- | --- | --- |
| genus_baseline_gamma | float or null | eeg_engine | Baseline frontal 40 Hz power measured during RAMP_UP (first 15s, audio-only). Null before first measurement. |
| --- | --- | --- | --- |
| genus_measurement_window_active | bool | Conductor | True during the 5-second audio-only measurement windows. Visual engine reads this to pause flicker. |
| --- | --- | --- | --- |
| genus_content_tier | int | delivery_gate | 0 = gate closed, 1 = Tier 2 (reinforcement), 2 = Tier 1 (high-value). Derived from GammaVerificationGate.delivery_priority(). |
| --- | --- | --- | --- |
| genus_fallback_reason | string or null | Conductor | If GENUS_FALLBACK triggered: "low_entrainment", "eeg_lost", "user_interrupt" |
| --- | --- | --- | --- |
| genus_sessions_completed | int | session_planner | Total GENUS sessions completed (lifetime). Persisted to DB. Used for familiarity threshold checks. |
| --- | --- | --- | --- |
| genus_last_session_ts | ISO string or null | session_planner | Timestamp of last completed GENUS session. Persisted to DB. Used for daily scheduling. |
| --- | --- | --- | --- |
| genus_audio_ramp_pct | float | Conductor | Current audio amplitude as fraction 0.0–1.0 during ramp-up/wind-down. Audio engine reads this. |
| --- | --- | --- | --- |
| genus_visual_ramp_pct | float | Conductor | Current visual modulation depth as fraction 0.0–1.0 during ramp-up/wind-down. Visual engine reads this. |
| --- | --- | --- | --- |

## 11.3 Writer Priority

Per existing convention: User slider > LLM agent > Conductor > config defaults. The user can override genus_audio_enabled, genus_visual_enabled, genus_modulation_depth at any time via UI controls.

# 12\. Safety

All safety requirements from the GENUS Reference Document are retained. This section adds session-integration safety constraints.

## 12.1 Epilepsy Safety Gate

Before the first GENUS session, the system displays a modal warning about photosensitive epilepsy risk. The user must explicitly acknowledge. Stored as genus_epilepsy_ack in user_config DB table. Until acknowledged, GENUS phases are excluded from all arc templates.

If the user selects "I have photosensitive epilepsy" or equivalent, genus_visual_enabled is permanently set to false in user config. Audio-only GENUS remains available.

## 12.2 Emergency Stop

GENUS inherits the existing emergency stop (Escape key, <100ms latency). During GENUS_BLOCK, emergency stop:

1.  Immediately sets genus_active = false
2.  Audio clicks cease within 1 audio buffer (~5ms at 44100 Hz)
3.  Visual flicker ceases on the next frame (<12.5ms)
4.  Phase transitions to EMERGENCY_STOP
5.  No content delivery
6.  Session logged with genus_fallback_reason = "emergency_stop"

## 12.3 Frequency Collision Prevention

A runtime assertion prevents simultaneous GENUS and trance stimulation:

def \_validate_frequency_exclusivity(live: dict) -> None: genus_active = live.get('genus_active', False) trance_entrainment = live.get('entrainment_active', False) # existing key from trance system if genus_active and trance_entrainment: raise FrequencyCollisionError( "GENUS (40 Hz) and trance entrainment (alpha/theta) cannot be active simultaneously. " "This is a state machine bug — both should never be true at once." )

This assertion runs on every \_patch_live() call. A collision is a bug, not a user error — it means the Conductor state machine has a transition defect.

## 12.4 Volume Safety

GENUS audio hard maximum: 78 dB SPL (per GENUS Reference Document). The audio engine enforces this ceiling independently of gain controls. During GENUS_BLOCK, the existing TTS gain is reduced to 60–80% of click volume to prevent combined audio levels from exceeding comfort thresholds.

## 12.5 Session Duration Limits

Maximum single GENUS_ACTIVE duration: 3600 seconds (60 minutes). This matches the clinical protocol. The SessionDirector cannot allocate more than 60 minutes of GENUS_ACTIVE time regardless of total session duration. If the user manually overrides genus_session_duration_min above 60, the Conductor caps at 60 and logs the override attempt.

## 12.6 GENUS and Sleep Arcs

GENUS_BLOCK is contraindicated in SLEEP_BRIDGE arcs. 40 Hz gamma is a cortical arousal signal — it directly opposes sleep onset. The SessionPlanner must never compose an arc that transitions from GENUS to SLEEP_APPROACH or SLEEP_ONSET. If the user requests a GENUS + sleep session, the SessionPlanner inserts a full trance cascade between GENUS and sleep phases, with minimum 30 minutes of trance before any sleep phase.

# 13\. Database Schema Additions

## 13.1 Session History Extension

Add to the session_history table:

ALTER TABLE session_history ADD COLUMN genus_included BOOLEAN DEFAULT FALSE; ALTER TABLE session_history ADD COLUMN genus_duration_s INTEGER DEFAULT 0; ALTER TABLE session_history ADD COLUMN genus_mean_entrainment_ratio FLOAT DEFAULT 0.0; ALTER TABLE session_history ADD COLUMN genus_peak_entrainment_ratio FLOAT DEFAULT 0.0; ALTER TABLE session_history ADD COLUMN genus_fallback BOOLEAN DEFAULT FALSE; ALTER TABLE session_history ADD COLUMN genus_fallback_reason TEXT DEFAULT NULL; ALTER TABLE session_history ADD COLUMN genus_content_items_delivered INTEGER DEFAULT 0; ALTER TABLE session_history ADD COLUMN genus_arc_template TEXT DEFAULT NULL;

## 13.2 User Profile Extension

Add to the user_profile table:

ALTER TABLE user_profile ADD COLUMN genus_epilepsy_ack BOOLEAN DEFAULT FALSE; ALTER TABLE user_profile ADD COLUMN genus_visual_enabled BOOLEAN DEFAULT TRUE; ALTER TABLE user_profile ADD COLUMN genus_audio_only_preference BOOLEAN DEFAULT FALSE; ALTER TABLE user_profile ADD COLUMN genus_sessions_lifetime INTEGER DEFAULT 0; ALTER TABLE user_profile ADD COLUMN genus_last_session_ts TEXT DEFAULT NULL; ALTER TABLE user_profile ADD COLUMN genus_mean_entrainment_history FLOAT DEFAULT 0.0; ALTER TABLE user_profile ADD COLUMN genus_enabled BOOLEAN DEFAULT TRUE;

## 13.3 Content Pipeline Table

New table for cross-stage content tracking:

CREATE TABLE content_pipeline ( id INTEGER PRIMARY KEY AUTOINCREMENT, pool_id TEXT NOT NULL, item_hash TEXT NOT NULL, genus_encoded BOOLEAN DEFAULT FALSE, genus_session_id INTEGER DEFAULT NULL, genus_entrainment_at_delivery FLOAT DEFAULT NULL, trance_deepened BOOLEAN DEFAULT FALSE, trance_session_id INTEGER DEFAULT NULL, tmr_consolidated BOOLEAN DEFAULT FALSE, tmr_session_id INTEGER DEFAULT NULL, pipeline_complete BOOLEAN DEFAULT FALSE, created_ts TEXT NOT NULL, updated_ts TEXT NOT NULL, FOREIGN KEY (genus_session_id) REFERENCES session_history(id), FOREIGN KEY (trance_session_id) REFERENCES session_history(id), FOREIGN KEY (tmr_session_id) REFERENCES session_history(id) ); CREATE INDEX idx_content_pipeline_pool ON content_pipeline(pool_id); CREATE INDEX idx_content_pipeline_incomplete ON content_pipeline(pipeline_complete) WHERE pipeline_complete = FALSE;

# 14\. Integration Touchpoints

Summary of modifications to existing modules:

| **Module** | **Change** | **Details** |
| --- | --- | --- |
| conductor.py | Add GENUS_BLOCK phase | State machine additions per Section 3. GENUS_RAMP_UP, GENUS_ACTIVE, GENUS_WIND_DOWN, GENUS_COOLDOWN, GENUS_FALLBACK sub-states. Measurement window timer (60s cycle). Ramp/wind-down gain interpolation. |
| --- | --- | --- |
| session_director.py | Add GENUS arc templates | Three new templates per Section 4. Meso-loop intensity cycling (Doc 48) does not apply during GENUS — there is no BUILD_UP/PEAK/RELAX within GENUS_ACTIVE. Intensity is constant. |
| --- | --- | --- |
| session_planner.py | GENUS eligibility and arc selection | Decision logic per Section 6. DB queries for genus_last_session_ts, genus_sessions_lifetime, genus_epilepsy_ack. |
| --- | --- | --- |
| delivery_gate.py | GENUS mode | GammaVerificationGate class per Section 7. Mode switch based on genus_phase. SQI threshold adjustment (0.6 → 0.4) during visual GENUS. |
| --- | --- | --- |
| eeg_engine.py | 40 Hz power extraction | compute_gamma_power() per Section 8. Measurement window logic. Baseline capture during RAMP_UP. genus_entrainment_ratio written to live_control.json. |
| --- | --- | --- |
| audio_engine.py | Isochronic click generation | Already specified in GENUS Reference Document. This doc adds: ramp gain control via genus_audio_ramp_pct, TTS mixing during clicks, measurement window awareness (continue clicks when visual pauses). |
| --- | --- | --- |
| visual_display.py | Flicker mode + measurement pause | Already specified in GENUS Reference Document. This doc adds: genus_measurement_window_active check — pause flicker and hold black frame during measurement windows. Text backing panel for veil readability over flicker. |
| --- | --- | --- |
| conditioning_engine.py | Encoding bonus | Rescorla-Wagner alpha modifier per Section 10.3. Content pipeline tracking per Section 10.2. |
| --- | --- | --- |
| somna_agent.py | GENUS engagement mode | Conversational tone, cognitive engagement prompts, theme priming for hybrid arcs. NOT Milton Model. Prompt pacing 45–90s. |
| --- | --- | --- |
| somna_db.py | Schema additions | Per Section 13. Three ALTER TABLE blocks + one CREATE TABLE. |
| --- | --- | --- |
| live_control.json | New keys | Per Section 11. Twelve new keys. |
| --- | --- | --- |

# 15\. Implementation Order

Recommended implementation sequence to minimize blocked dependencies:

1.  **Database schema** (Section 13) — unblocks everything else.
2.  **EEG gamma extraction** (Section 8) — compute_gamma_power(), baseline capture, entrainment ratio calculation. Can be tested with synthetic board.
3.  **Live control keys** (Section 11) — add keys with safe defaults.
4.  **GammaVerificationGate** (Section 7) — can be unit-tested in isolation.
5.  **Conductor GENUS phases** (Section 3) — state machine, sub-phases, ramp/wind-down interpolation, measurement window timer.
6.  **Transition phases** (Section 5) — TRANSITION_DESCENT and TRANSITION_ASCENT timing sequences.
7.  **Arc templates** (Section 4) — wire into SessionPlanner.
8.  **SessionPlanner decision logic** (Section 6) — eligibility checks, arc selection.
9.  **Content pipeline** (Section 10) — cross-stage tracking, Rescorla-Wagner bonus.
10. **Agent GENUS mode** (Section 9) — prompt templates, tone switching, theme priming.
11. **Safety assertions** (Section 12) — frequency collision check, epilepsy gate, duration cap.

# References

- GENUS Reference Document (Somna project internal, v1.0, 28 March 2026)
- Doc 48 — Session Director Architecture
- Doc 49 — Induction Strategy Library
- Doc 43 — Conditioning & Reinforcement Architecture
- Doc 42 — Cardiac-Phase Gating & Autonomic-Inertial Fusion
- Doc 36 — Neural-State Semantic Selection
- Doc 39 — Closed-Loop Sleep Enhancement
- Doc 40 — Targeted Memory Reactivation
- Doc 41 — Hypnagogic Training Window (Vesper)
- Doc 47 — Visual & Audio Enhancement Architecture
- Doc 46 — Content Design Methodology
- Mlinaric et al. 2025, _Communications Biology_ — intracranial EEG showing cognitive engagement enhances 40 Hz entrainment
- Murdock et al. 2024, _Nature_ — glymphatic mechanism (VIP interneurons → arterial pulsatility → CSF influx → amyloid clearance)
- Chan et al. 2022, _PLOS ONE_ — Phase I/II human trial
- Chan & Tsai 2025, _Alzheimer's & Dementia_ — 30-month open-label extension
- Iaccarino et al. 2016, _Nature_ — foundational 40 Hz mouse study