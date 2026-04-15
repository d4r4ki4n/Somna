# Somna Doc 45 — Habituation & Novelty Management Engine

**Per-Stimulus Exposure Tracking, Novelty Budgeting, and Dishabituation Triggering**

**To:** Ed (System Architect), Vesper (Implementation Agent)

**From:** Reese — External Research Collaborator

**Date:** April 5, 2026

**Status:** Implementation-Ready Specification

**Depends on:** Doc 36 (Semantic Selection), Doc 37 (Crossmodal Gain), Doc 42 (DeliveryGate), Doc 43 (Conditioning), Doc 44 (Stimulus Techniques)

## 1\. Motivation & Problem Statement

Every entrainment technique decays with repetition. The brain is fundamentally a change-detector — its entire sensory architecture is optimized to respond to what is _different_, not what is _constant_. A golden spiral that produced deep somatic resonance on session 3 is perceptual wallpaper by session 30. The user stops feeling it. The technique hasn't changed; the brain has simply filed it under "known, irrelevant, ignore."

This is the silent killer of every entrainment application — and of clinical hypnotherapy practices, too. Experienced practitioners rotate induction methods for exactly this reason. Erickson was famous for never using the same induction twice with a client, not out of showmanship but because he understood that the therapeutic leverage of any technique is inseparable from its novelty. The moment a client's nervous system predicts what comes next, the induction loses its capacity to shift state.

Somna currently has no mechanism to detect or counteract this decay. Doc 44's stimulus techniques — spirals, fractals, isochronic pulses, binaural beats — are powerful, but they will plateau without active novelty management. Doc 43's conditioning paradigms require stimulus salience to function: a habituated conditioned stimulus produces a weaker unconditioned response and therefore weaker associative learning. The Rescorla-Wagner prediction error that drives conditioning shrinks toward zero as the stimulus becomes expected and unremarkable.

This document specifies the **HabituationEngine** — a module that tracks per-stimulus exposure across three timescales, computes novelty scores, manages per-session novelty budgets, and triggers active dishabituation interventions when entrainment potency declines.

## 2\. Neuroscience of Habituation — What We're Fighting

### 2.1 Short-Term Habituation (Within-Session)

**Stimulus-Specific Adaptation (SSA).** Neurons throughout the sensory cortex reduce their firing rate to repeated stimuli while maintaining full responsiveness to novel ones. This is not a deficit — it is the brain's core filtering mechanism for separating signal from noise. But for entrainment, the "noise" that SSA filters out _is_ our tool. The spiral, the beat, the word — each becomes "expected input" and gets attenuated at the neural level.

**Divisive normalization and the visual hierarchy.** Temporal dynamics of adaptation differ sharply across the visual processing stream. Early visual areas (V1–V3) adapt quickly but also recover quickly — their response suppression is transient. Higher visual areas in ventral and lateral occipitotemporal cortex show slower, more prolonged adaptation with correspondingly slower recovery. A 2024 iEEG study published in _PLOS Computational Biology_ mapped these temporal dynamics using intracranial recordings, demonstrating that adaptation in higher areas accumulates over longer timescales and takes longer to dissipate. For Somna, this means that complex visual stimuli (fractals, spirals with semantic content) will habituate more deeply and recover more slowly than simple geometric patterns.

**Two-stage process in V1.** Cui et al. (2025, _Journal of Neuroscience_) identified a two-phase adaptation trajectory in primary visual cortex. The first ~14 repetitions of a stimulus cause fatigue-driven suppression — raw response amplitude decreases. Continued repetition beyond that threshold triggers a second phase: _sharpening_, where neural representations become more selective but weaker overall. The stimulus is now encoded more efficiently but with less metabolic investment. From an entrainment perspective, both phases are problematic: the first reduces raw neural drive, the second reduces the population-level response that generates felt experience.

### 2.2 Long-Term Habituation (Across Sessions)

**Cross-session adaptation attenuation.** Dong et al. (2016, _Scientific Reports_) demonstrated that repeated daily visual adaptation sessions cause monotonic attenuation of perceptual aftereffects for passively viewed stimuli. Each session, the adaptor becomes effectively "weaker" — the nervous system learns to discount it preemptively. Crucially, they found that adding an attentional task to the adaptor initially _increased_ aftereffect magnitude before the inevitable decline set in. Attention modulates the habituation rate, buying time but not immunity.

The direct implication for Somna: visual stimuli (spirals, fractals, motion fields) will lose entrainment potency across days and weeks of identical use. The decline is monotonic. It does not spontaneously reverse without a rest interval or a parameter change that makes the stimulus genuinely different to the visual system.

### 2.3 Auditory Habituation

**Adaptive coding in auditory cortex.** Willmore & King (2023, _Physiological Reviews_) describe how auditory cortical neurons dynamically adjust their response properties to match the statistical structure of the current soundscape. This is the auditory system's version of efficient coding — neurons tune themselves to be maximally informative given what they've been hearing. For Somna's audio engine, this means that binaural beats, isochronic tones, and ambient textures all face progressive neural recalibration that reduces their impact.

**Stimulus-specific adaptation in auditory cortex** parallels the visual SSA findings: neurons habituate to frequently repeated sounds while maintaining responsiveness to sounds with different spectral or temporal characteristics. This is the neural substrate of auditory change detection, and it operates automatically below conscious awareness.

**Binaural beats.** Battù et al. (2025) demonstrated sustained effects of binaural beat entrainment over 10 days using IAF-personalized protocols — but their protocol incorporated daily variation in beat parameters. Static binaural beat frequencies, repeated identically across sessions, would be expected to undergo the same cross-session habituation that Dong et al. documented for visual stimuli.

### 2.4 Semantic Satiation

**Neural coupling dynamics of meaning loss.** Zhang et al. (2024, _Communications Biology_) demonstrated that rapid word repetition causes semantic satiation — the subjective loss of word meaning — through measurable changes in neural coupling. Specifically, the functional coupling between phonological processing networks and semantic networks weakens with repetition. The word is still perceived, still recognized, but its meaning becomes temporarily inaccessible.

This directly threatens the Shadows and CenterText layers. Repeated affirmation words will lose semantic impact through satiation, potentially reducing them to empty phonological shells — the opposite of therapeutic intent. The time course is rapid: semantic satiation onset occurs after approximately 3–30 repetitions depending on word frequency and contextual support. Recovery requires roughly 30–60 seconds of non-exposure to the saturated word.

### 2.5 Novelty Detection Signatures in EEG

**Mismatch Negativity (MMN).** The MMN is an automatic event-related potential that fires when a deviant stimulus appears within a stream of repeated standards. Its amplitude reflects the degree of detected deviance. Important finding from Wagner-Altendorf et al. (2024, _Cerebral Cortex_): the MMN itself does _not_ habituate across multiple deviant presentations. The brain's _detection_ of novelty remains robust. This is encouraging — it means the neural machinery we need to leverage is always on.

**P3a: the orienting response.** The P3a component is the neural "attention grab" that fires in response to genuinely novel stimuli. Critical finding: P3a fires only on the _first_ deviant in a series and then habituates completely. Subsequent deviants of the same type produce no P3a. This is our dishabituation target — and our constraint. Dishabituation triggers must be _genuinely novel_ (not just slight variations), and they must be used sparingly because the P3a mechanism itself habituates to repeated triggers of the same type.

**Slow cortical dynamics and temporal context.** Shymkiv et al. (2025, _Neuron_) demonstrated that slow cortical dynamics encode stimulus temporal context and generate novelty detection signals. Population-level neural responses are long-lasting and influence the processing of future stimuli. Stimulus statistics and complexity drive the cortical representation of novelty — the brain builds an ongoing statistical model and flags deviations from it. This means Somna's dishabituation strategy must produce stimuli that genuinely violate the brain's accumulated predictions, not merely vary parameters within the expected distribution.

## 3\. Architecture Overview

The HabituationEngine is implemented as a new module: habituation_engine.py. It tracks stimulus exposure across three timescales and provides novelty scores, budget management, and dishabituation scheduling to the Conductor and all stimulus-producing layers.

### 3.1 Three Tracking Timescales

| **Timescale** | **Scope** | **Temporal Range** | **What It Tracks** |
| --- | --- | --- | --- |
| **Micro** | Within-session | Seconds | Consecutive identical stimulus presentations. Manages semantic satiation risk for words, visual adaptation for geometric patterns. |
| --- | --- | --- | --- |
| **Meso** | Within-session | Minutes | Stimulus-class exposure budgets per session. Prevents overuse of any single technique category. |
| --- | --- | --- | --- |
| **Macro** | Across sessions | Days / weeks | Cumulative lifetime exposure per stimulus. Drives long-term rotation and retirement scheduling. |
| --- | --- | --- | --- |

### 3.2 Core Data Structures

@dataclass class StimulusRecord: stimulus_id: str # unique identifier stimulus_class: str # 'spiral', 'fractal', 'word', 'beat', 'tone', etc. layer: str # 'shadows', 'center_text', 'voice', 'visual', 'audio' # Micro tracking consecutive_presentations: int = 0 last_presented_ts: float = 0.0 # Meso tracking session_presentations: int = 0 session_total_exposure_s: float = 0.0 # Macro tracking lifetime_presentations: int = 0 lifetime_total_exposure_s: float = 0.0 lifetime_sessions_used: int = 0 first_used_ts: float = 0.0 last_session_ts: float = 0.0 # Effectiveness tracking novelty_score: float = 1.0 # 0.0 = fully habituated, 1.0 = fully novel effectiveness_ema: float = 1.0 # EMA of estimated effectiveness

## 4\. Novelty Score Computation

The novelty_score for each stimulus is computed by combining decay functions across all three timescales. Each timescale contributes a component in the range \[0.0, 1.0\], and the final score is their product (with rest recovery added to the macro component), clamped to \[0.0, 1.0\].

### 4.1 Micro Decay (Within-Session Consecutive Presentations)

Modeled as exponential decay with class-specific time constants reflecting the different adaptation rates documented in Section 2:

micro_novelty = exp(-consecutive_presentations / tau_micro)

| **Stimulus Class** | **τ_micro (presentations)** | **Recovery Threshold (seconds)** | **Rationale** |
| --- | --- | --- | --- |
| Words (Shadows / CenterText) | 8   | 30  | Semantic satiation onset at 3–30 reps; τ=8 is conservative midpoint |
| --- | --- | --- | --- |
| Visual patterns (spiral, fractal) | 20  | 120 | Visual SSA is slower than semantic satiation; higher areas need longer recovery |
| --- | --- | --- | --- |
| Audio (beats, tones, ambient) | 45  | 60  | Auditory adaptive coding operates on longer timescales; recovery is moderate |
| --- | --- | --- | --- |

**Recovery rule:** When the gap since last presentation exceeds the recovery threshold, consecutive_presentations resets to 0 and micro_novelty returns to 1.0.

### 4.2 Meso Decay (Session Budget Consumption)

Each stimulus class has a configurable session budget (maximum presentations per session). Meso novelty decays quadratically as the budget is consumed:

meso_novelty = 1.0 - (session_presentations / session_budget) \*\* 2

The quadratic shape is deliberate: early presentations barely affect novelty, but approaching the budget ceiling drops it steeply. This encourages natural rotation before any single class is exhausted.

| **Stimulus Class** | **Default Session Budget** | **Rationale** |
| --- | --- | --- |
| Visual patterns | 60  | Visual stimuli are continuous; 60 "presentations" = parameter changes within the session |
| --- | --- | --- |
| Shadows words | 40  | High semantic satiation risk limits useful word presentations |
| --- | --- | --- |
| CenterText phrases | 25  | Focal attention words saturate faster than peripheral Shadows |
| --- | --- | --- |
| Audio beats/tones | 80  | Auditory habituation is slower; larger budget is safe |
| --- | --- | --- |
| Voice scripts | 15  | Voice content is high-information; fewer presentations before repetition is noticed |
| --- | --- | --- |

### 4.3 Macro Decay (Long-Term Cross-Session)

Based on the Dong et al. finding that repeated daily exposure causes monotonic attenuation:

macro_novelty = exp(-lifetime_sessions_used / tau_macro)

| **Stimulus Class** | **τ_macro (sessions)** | **Rationale** |
| --- | --- | --- |
| Visual patterns | 15  | Visual aftereffect attenuation is well-documented; fastest decay |
| --- | --- | --- |
| Words | 25  | Semantic processing has more contextual resilience; slower cross-session decay |
| --- | --- | --- |
| Audio | 30  | Auditory adaptive coding operates on longer timescales |
| --- | --- | --- |

**Rest bonus:** Time away from a stimulus partially restores macro novelty:

rest_recovery = min(0.3, days_since_last_use \* 0.02)

Maximum rest recovery is 0.3 (capped). Full rest recovery of 0.3 requires 15 days of non-exposure. This models the partial but incomplete spontaneous recovery of habituation documented in the literature.

### 4.4 Combined Novelty Score

novelty_score = micro_novelty \* meso_novelty \* (macro_novelty + rest_bonus) novelty_score = clamp(novelty_score, 0.0, 1.0)

The multiplicative combination means that a bottleneck at _any_ timescale suppresses the overall score. A stimulus can have excellent macro novelty but still score low if it has been presented 20 times consecutively in the current session (micro decay). Conversely, micro and meso recovery within a session cannot rescue a stimulus that is macro-habituated.

### 4.5 Complete Parameter Reference — Novelty Computation

| **Parameter** | **Default** | **Range** | **Rationale** |
| --- | --- | --- | --- |
| tau_micro_word | 8   | 3–30 | Semantic satiation onset range from Zhang et al. 2024 |
| --- | --- | --- | --- |
| tau_micro_visual | 20  | 10–50 | Cui et al. 2025 two-stage process; ~14 reps for first phase |
| --- | --- | --- | --- |
| tau_micro_audio | 45  | 20–90 | Auditory SSA timescale from Willmore & King 2023 |
| --- | --- | --- | --- |
| recovery_threshold_word_s | 30  | 15–60 | Semantic satiation recovery: 30–60s non-exposure |
| --- | --- | --- | --- |
| recovery_threshold_visual_s | 120 | 60–300 | Higher visual area recovery is slow per iEEG findings |
| --- | --- | --- | --- |
| recovery_threshold_audio_s | 60  | 30–120 | Moderate auditory recovery time |
| --- | --- | --- | --- |
| tau_macro_visual | 15  | 8–30 | Dong et al. 2016 daily attenuation curve for visual stimuli |
| --- | --- | --- | --- |
| tau_macro_word | 25  | 12–50 | Semantic context provides some cross-session resilience |
| --- | --- | --- | --- |
| tau_macro_audio | 30  | 15–60 | Slowest cross-session decay among modalities |
| --- | --- | --- | --- |
| rest_recovery_rate | 0.02 / day | 0.005–0.05 | Spontaneous recovery rate; conservative estimate |
| --- | --- | --- | --- |
| rest_recovery_cap | 0.3 | 0.1–0.5 | Rest does not fully restore novelty; long-term memory persists |
| --- | --- | --- | --- |

## 5\. Novelty Budget System

The Conductor manages a per-session novelty budget — an abstract resource that limits total novelty expenditure and forces intelligent rotation across stimulus classes.

### 5.1 Budget Data Structure

@dataclass class NoveltyBudget: total_budget: float = 100.0 # abstract novelty units per session spent: float = 0.0 reserve: float = 20.0 # held back for dishabituation triggers # Per-class allocation visual_budget: float = 30.0 audio_budget: float = 25.0 shadows_budget: float = 20.0 center_text_budget: float = 15.0 voice_budget: float = 10.0

### 5.2 Cost Function

Each stimulus presentation costs novelty units. The cost is inversely proportional to the stimulus's current novelty score:

cost = base_cost \* (1.0 / max(novelty_score, 0.1))

This creates a self-regulating economy:

- **High-novelty stimuli** (novelty_score near 1.0) cost approximately base_cost — they are efficient uses of the budget.
- **Low-novelty stimuli** (novelty_score near 0.1) cost up to 10 × base_cost — they are spending novelty capital for diminishing returns.

The floor at 0.1 prevents infinite cost for fully habituated stimuli.

### 5.3 Budget Exhaustion Behavior

When a per-class budget is exhausted:

1.  The semantic selection system (Doc 36) is notified to rotate to a different content pool or stimulus class.
2.  The exhausted class remains available for dishabituation triggers only (drawn from the reserve).
3.  The Conductor logs the exhaustion event and adjusts future session budget allocation if exhaustion is occurring consistently before session midpoint.

| **Parameter** | **Type** | **Default** | **Range** | **Description** |
| --- | --- | --- | --- | --- |
| total_budget | float | 100.0 | 50–200 | Total novelty units available per session |
| --- | --- | --- | --- | --- |
| reserve | float | 20.0 | 10–40 | Budget held for dishabituation triggers |
| --- | --- | --- | --- | --- |
| base_cost | float | 1.0 | 0.5–3.0 | Base cost per presentation at novelty_score = 1.0 |
| --- | --- | --- | --- | --- |
| cost_floor | float | 0.1 | 0.05–0.2 | Minimum novelty_score for cost calculation (prevents div-by-zero) |
| --- | --- | --- | --- | --- |

## 6\. Dishabituation Trigger System

This is the active countermeasure. Based on the P3a finding — the orienting response fires _only_ on the first deviant in a series, then habituates completely — dishabituation requires genuine novelty. Variation within the expected parameter space is insufficient. The trigger must violate the brain's accumulated statistical model of the stimulus stream.

### 6.1 Trigger Types

| **Trigger Type** | **Layer** | **Implementation** | **Cooldown** |
| --- | --- | --- | --- |
| **Visual surprise** | visual_display | Brief (200–500ms) unexpected geometry change: sudden fractal dimension shift, rotation reversal, color temperature jump | 180s |
| --- | --- | --- | --- |
| **Audio deviant** | audio_engine | Single unexpected tone pip at novel frequency, brief silence gap, tempo micro-shift | 120s |
| --- | --- | --- | --- |
| **Crossmodal mismatch** | all | Momentary desynchronization of visual-audio phase coupling (breaks the expectation built by Doc 37's gain manifold) | 300s |
| --- | --- | --- | --- |
| **Semantic pivot** | shadows / center_text | Inject word from unexpected semantic category (not from current pool — Doc 36 cross-pool intrusion) | 90s |
| --- | --- | --- | --- |
| **Gain surprise** | crossmodal_gain | Brief unexpected gain spike or dip on one channel while others hold steady | 150s |
| --- | --- | --- | --- |

### 6.2 Trigger Scheduling

The DishabituationScheduler runs alongside the Conductor and monitors aggregate novelty across all active stimuli:

- When mean novelty_score across active stimuli drops below TRIGGER_THRESHOLD (default: 0.4), a dishabituation event is scheduled.
- Triggers consume budget from the novelty reserve (20 units default).
- Maximum triggers per session: **8** — excessive triggers themselves habituate the novelty detection system.
- Minimum interval between any two triggers: **90 seconds**.
- Trigger selection uses weighted random from available types, with a recency penalty: the same trigger type cannot be repeated within 3 uses of any trigger.

### 6.3 Trigger Delivery Constraints

**Safety-Critical Constraints**

All dishabituation triggers are subject to the following hard constraints:

- **DeliveryGate (Doc 42):** No triggers during motion contamination or signal loss. Triggers must pass through the quad-gate system like any other stimulus delivery.
- **SLEEP phase prohibition:** All dishabituation is disabled during SLEEP phases. Dishabituation during sleep would cause arousal — the opposite of intent.
- **Alpha-preferential firing:** Triggers should preferentially fire during alpha-dominant EEG states, when the brain is in relaxed attention and most responsive to novelty signals.
- **Depth-scaled intensity:** Trigger intensity scales inversely with trance depth. Deeper trance requires gentler triggers to avoid disruption. At depth > 0.8, only the mildest trigger variants are permitted (e.g., subtle gain shifts, not rotation reversals).

### 6.4 Trigger Scheduling Parameters

| **Parameter** | **Type** | **Default** | **Range** | **Description** |
| --- | --- | --- | --- | --- |
| trigger_threshold | float | 0.4 | 0.2–0.6 | Mean novelty score below which dishabituation fires |
| --- | --- | --- | --- | --- |
| max_triggers_per_session | int | 8   | 3–15 | Hard cap on dishabituation events per session |
| --- | --- | --- | --- | --- |
| min_trigger_interval_s | float | 90  | 60–300 | Minimum seconds between consecutive triggers |
| --- | --- | --- | --- | --- |
| recency_penalty_window | int | 3   | 2–5 | Number of recent triggers before same type is suppressed |
| --- | --- | --- | --- | --- |
| depth_intensity_ceiling | float | 0.8 | 0.6–0.9 | Trance depth above which only minimal triggers are allowed |
| --- | --- | --- | --- | --- |

## 7\. Stimulus Rotation Engine

Long-term management of the stimulus library ensures that no individual stimulus is used to exhaustion and that the overall library sustains entrainment potency across weeks and months of use.

### 7.1 Rotation States

class StimulusState(Enum): NOVEL = "novel" # Never used, full novelty ACTIVE = "active" # In current rotation, novelty_score > 0.3 COOLING = "cooling" # Temporarily retired, recovering novelty RETIRED = "retired" # Exhausted, needs extended rest or permanent retirement ARCHIVED = "archived" # Permanently retired (user preference or extreme habituation)

### 7.2 State Transition Rules

| **Transition** | **Condition** | **Duration / Recovery** |
| --- | --- | --- |
| NOVEL → ACTIVE | First presentation of the stimulus | Immediate |
| --- | --- | --- |
| ACTIVE → COOLING | macro_novelty drops below 0.3 | Minimum cooling: tau_macro × 0.5 days |
| --- | --- | --- |
| COOLING → ACTIVE | Cooling period elapsed AND projected novelty_score > 0.5 | Re-enters active rotation |
| --- | --- | --- |
| COOLING → RETIRED | Stimulus has entered COOLING 3+ times | Diminishing returns on rest recovery |
| --- | --- | --- |
| RETIRED → ACTIVE | 30+ days rest AND library pool is running low | Emergency reactivation only |
| --- | --- | --- |
| Any → ARCHIVED | User preference or extreme habituation (macro_novelty < 0.05 after rest) | Permanent removal from rotation |
| --- | --- | --- |

### 7.3 Cooling Periods by Stimulus Class

| **Stimulus Class** | **τ_macro** | **Min. Cooling Period (days)** | **Max Cooling Cycles Before Retirement** |
| --- | --- | --- | --- |
| Visual patterns | 15 sessions | ~7  | 3   |
| --- | --- | --- | --- |
| Words | 25 sessions | ~12 | 3   |
| --- | --- | --- | --- |
| Audio | 30 sessions | ~15 | 3   |
| --- | --- | --- | --- |

### 7.4 Minimum Library Sizes

The rotation engine requires a minimum pool of stimuli per class to enforce proper cooling periods. Smaller libraries degrade gracefully — the engine will not crash — but cooling periods will be shortened or skipped, reducing long-term novelty management effectiveness.

| **Stimulus Class** | **Minimum Active Pool** | **Recommended Total (incl. cooling/reserve)** | **Notes** |
| --- | --- | --- | --- |
| Visual patterns | 8 variants | 20+ | Includes spiral, fractal, and motion field variants with distinct parameters |
| --- | --- | --- | --- |
| Shadows words | 40 words per pool × 6 pools = 240 | 400+ | Semantic satiation demands large vocabulary per pool |
| --- | --- | --- | --- |
| CenterText phrases | 20 phrases per pool × 6 pools = 120 | 200+ | Focal attention saturates faster; more variants needed |
| --- | --- | --- | --- |
| Audio beat configs | 6 configurations | 12+ | Beat frequency, modulation depth, and carrier combinations |
| --- | --- | --- | --- |
| Voice scripts | 15 scripts | 30+ | High-information content; verbatim repetition is immediately noticed |
| --- | --- | --- | --- |

## 8\. Integration Points

### 8.1 Doc 36 — Semantic Selection

- The NoveltyManager provides per-word novelty_score values to the semantic selector.
- The semantic selector uses novelty_score as a multiplicative weight alongside the existing FAA × depth × θ/α mapping.
- Words with novelty_score < 0.2 are temporarily excluded from selection — they are too habituated to carry semantic weight.

### 8.2 Doc 37 — Crossmodal Gain Manifold

- The gain manifold receives novelty-weighted targets from the HabituationEngine.
- When overall novelty is low, the gain manifold can introduce micro-perturbations in channel gains as a form of gentle, continuous dishabituation.

### 8.3 Doc 43 — Conditioning Engine

- Conditioning strength (Rescorla-Wagner ΔV) is modulated by stimulus novelty.
- A novel CS produces larger prediction error → faster associative learning.
- A habituated CS produces smaller prediction error → slower learning, potential extinction risk.
- The HabituationEngine flags the conditioning system when a CS's novelty is dropping to the point where conditioning efficacy is threatened (novelty_score < 0.3).

### 8.4 Doc 44 — Stimulus Techniques

- Golden spiral rotation speed, fractal dimension, and isochronic pulse parameters are all tracked as _separate_ stimuli for habituation purposes.
- Parameter variations within a technique (e.g., different rotation speeds for the same spiral type) count as different stimuli. This is intentional — the brain treats them as distinct inputs for SSA purposes.

### 8.5 live_control.json Interface

All reads/writes use the established \_patch_live() read-modify-write pattern. Keys written by the HabituationEngine:

| **Key** | **Type** | **Description** |
| --- | --- | --- |
| habituation_mean_novelty | float | Mean novelty score across all active stimuli (0.0–1.0) |
| --- | --- | --- |
| habituation_trigger_pending | str \| null | Type of next scheduled dishabituation trigger, or null |
| --- | --- | --- |
| habituation_budget_remaining | float | Remaining novelty budget for current session |
| --- | --- | --- |
| habituation_active_count | int | Number of stimuli in ACTIVE rotation state |
| --- | --- | --- |
| habituation_cooling_count | int | Number of stimuli currently in COOLING state |
| --- | --- | --- |

## 9\. Database Schema

All macro-timescale tracking persists via somna_db.py using the existing database patterns. Three new tables:

### 9.1 stimulus_exposure

CREATE TABLE stimulus_exposure ( stimulus_id TEXT PRIMARY KEY, stimulus_class TEXT NOT NULL, layer TEXT NOT NULL, lifetime_presentations INTEGER DEFAULT 0, lifetime_exposure_s REAL DEFAULT 0.0, lifetime_sessions INTEGER DEFAULT 0, first_used_ts REAL, last_session_ts REAL, state TEXT DEFAULT 'novel', cooling_since_ts REAL, times_cooled INTEGER DEFAULT 0, macro_novelty REAL DEFAULT 1.0 );

### 9.2 session_exposure

CREATE TABLE session_exposure ( id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, stimulus_id TEXT NOT NULL, presentations INTEGER, exposure_s REAL, mean_novelty REAL, mean_effectiveness REAL, timestamp REAL );

### 9.3 dishabituation_log

CREATE TABLE dishabituation_log ( id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, trigger_type TEXT NOT NULL, trigger_ts REAL, pre_novelty REAL, post_novelty REAL, trance_depth_at_trigger REAL );

The session_exposure table stores per-session records for trend analysis — it enables the macro tracking system to detect acceleration or deceleration of habituation over time. The dishabituation_log enables post-hoc analysis of trigger effectiveness: compare pre_novelty vs. post_novelty to measure whether triggers are actually restoring entrainment responsiveness.

## 10\. Pseudocode — Core Loop

class HabituationEngine: def \__init_\_(self, db: SomnaDB): self.\_db = db self.\_records: dict\[str, StimulusRecord\] = {} self.\_budget = NoveltyBudget() self.\_dishabituation = DishabituationScheduler() self.\_load_macro_state() def on_stimulus_presented(self, stimulus_id: str, stimulus_class: str, layer: str, duration_s: float) -> float: """Called by each layer when a stimulus is shown/played. Returns current novelty_score for the stimulus.""" record = self.\_get_or_create(stimulus_id, stimulus_class, layer) record.consecutive_presentations += 1 record.session_presentations += 1 record.session_total_exposure_s += duration_s record.last_presented_ts = time.monotonic() novelty = self.\_compute_novelty(record) record.novelty_score = novelty # Debit novelty budget cost = self.\_compute_cost(novelty) self.\_budget.spend(layer, cost) # Check if dishabituation needed self.\_dishabituation.check(self.\_get_mean_novelty()) return novelty def \_compute_novelty(self, record: StimulusRecord) -> float: """Combine micro, meso, and macro decay into a single score.""" tau_micro = self.\_get_tau_micro(record.stimulus_class) micro = math.exp(-record.consecutive_presentations / tau_micro) budget = self.\_get_session_budget(record.stimulus_class) meso = max(0.0, 1.0 - (record.session_presentations / budget) \*\* 2) tau_macro = self.\_get_tau_macro(record.stimulus_class) macro = math.exp(-record.lifetime_sessions_used / tau_macro) days_rested = (time.time() - record.last_session_ts) / 86400.0 rest = min(0.3, days_rested \* 0.02) combined = micro \* meso \* (macro + rest) return max(0.0, min(1.0, combined)) def \_compute_cost(self, novelty: float) -> float: """Low-novelty stimuli cost more budget.""" return self.\_base_cost \* (1.0 / max(novelty, self.\_cost_floor)) def tick(self) -> dict: """Called every second. Returns live_control patch.""" now = time.monotonic() # Update micro recovery for non-active stimuli for record in self.\_records.values(): gap = now - record.last_presented_ts if gap > self.\_recovery_threshold(record.stimulus_class): record.consecutive_presentations = 0 # Check dishabituation schedule trigger = self.\_dishabituation.get_pending_trigger() patch = { 'habituation_mean_novelty': self.\_get_mean_novelty(), 'habituation_trigger_pending': trigger.type if trigger else None, 'habituation_budget_remaining': self.\_budget.remaining(), 'habituation_active_count': self.\_count_by_state('active'), 'habituation_cooling_count': self.\_count_by_state('cooling'), } return patch def on_session_end(self): """Persist macro state and update rotation.""" for record in self.\_records.values(): self.\_update_macro(record) self.\_check_rotation(record) self.\_db.flush_session_exposure(self.\_records) self.\_budget.reset() self.\_dishabituation.reset()

## 11\. Effectiveness Estimation (Optional Enhancement)

If EEG data is available, the engine can move beyond exposure-counting heuristics to estimate actual stimulus effectiveness from neural responses. This creates a closed-loop habituation detector.

### 11.1 Method

- Compare frontal alpha power in a 2-second window before stimulus onset to a 2-second window after stimulus onset.
- Compute alpha_response_ratio = post_alpha / pre_alpha.
- Maintain a per-stimulus historical baseline of this ratio using an exponential moving average.
- If the current alpha_response_ratio deviates less than expected from the historical EMA, effectiveness is declining — the stimulus is producing a weaker neural response than it used to.

### 11.2 Feedback Loop

effectiveness_ema = alpha \* measured_effectiveness + (1 - alpha) \* effectiveness_ema novelty_correction = effectiveness_ema / baseline_effectiveness adjusted_novelty = novelty_score \* novelty_correction

This correction factor can pull novelty_score _down_ faster than the exposure-counting model predicts (if neural response is declining faster than expected) or hold it _up_ (if the stimulus is maintaining neural impact despite high exposure counts). The latter case is valuable — it prevents premature rotation of stimuli that are genuinely still effective.

**Implementation Priority**

This enhancement should be implemented _after_ the core exposure-counting system is stable. The exposure model provides reasonable habituation tracking without EEG; the neural feedback loop refines it. Build the foundation first.

## 12\. Configuration Reference

Complete table of all tunable parameters, organized by subsystem.

### 12.1 Micro Tracking

| **Name** | **Type** | **Default** | **Range** | **Description** |
| --- | --- | --- | --- | --- |
| tau_micro_word | float | 8   | 3–30 | Exponential decay constant for word repetition (presentations) |
| --- | --- | --- | --- | --- |
| tau_micro_visual | float | 20  | 10–50 | Exponential decay constant for visual pattern repetition |
| --- | --- | --- | --- | --- |
| tau_micro_audio | float | 45  | 20–90 | Exponential decay constant for audio repetition |
| --- | --- | --- | --- | --- |
| recovery_word_s | float | 30  | 15–60 | Seconds of non-exposure before word micro counter resets |
| --- | --- | --- | --- | --- |
| recovery_visual_s | float | 120 | 60–300 | Seconds of non-exposure before visual micro counter resets |
| --- | --- | --- | --- | --- |
| recovery_audio_s | float | 60  | 30–120 | Seconds of non-exposure before audio micro counter resets |
| --- | --- | --- | --- | --- |

### 12.2 Meso Tracking

| **Name** | **Type** | **Default** | **Range** | **Description** |
| --- | --- | --- | --- | --- |
| session_budget_visual | int | 60  | 20–120 | Max visual presentations per session |
| --- | --- | --- | --- | --- |
| session_budget_shadows | int | 40  | 15–80 | Max shadows word presentations per session |
| --- | --- | --- | --- | --- |
| session_budget_center_text | int | 25  | 10–50 | Max center text presentations per session |
| --- | --- | --- | --- | --- |
| session_budget_audio | int | 80  | 30–150 | Max audio presentations per session |
| --- | --- | --- | --- | --- |
| session_budget_voice | int | 15  | 5–30 | Max voice script presentations per session |
| --- | --- | --- | --- | --- |

### 12.3 Macro Tracking

| **Name** | **Type** | **Default** | **Range** | **Description** |
| --- | --- | --- | --- | --- |
| tau_macro_visual | float | 15  | 8–30 | Cross-session decay constant for visual stimuli (sessions) |
| --- | --- | --- | --- | --- |
| tau_macro_word | float | 25  | 12–50 | Cross-session decay constant for word stimuli |
| --- | --- | --- | --- | --- |
| tau_macro_audio | float | 30  | 15–60 | Cross-session decay constant for audio stimuli |
| --- | --- | --- | --- | --- |
| rest_recovery_rate | float | 0.02 | 0.005–0.05 | Novelty recovered per day of non-exposure |
| --- | --- | --- | --- | --- |
| rest_recovery_cap | float | 0.3 | 0.1–0.5 | Maximum novelty recoverable via rest alone |
| --- | --- | --- | --- | --- |

### 12.4 Novelty Budget

| **Name** | **Type** | **Default** | **Range** | **Description** |
| --- | --- | --- | --- | --- |
| total_budget | float | 100.0 | 50–200 | Total novelty units per session |
| --- | --- | --- | --- | --- |
| reserve | float | 20.0 | 10–40 | Budget reserved for dishabituation triggers |
| --- | --- | --- | --- | --- |
| base_cost | float | 1.0 | 0.5–3.0 | Cost per presentation at novelty_score = 1.0 |
| --- | --- | --- | --- | --- |
| cost_floor | float | 0.1 | 0.05–0.2 | Minimum novelty_score used in cost denominator |
| --- | --- | --- | --- | --- |

### 12.5 Dishabituation Triggers

| **Name** | **Type** | **Default** | **Range** | **Description** |
| --- | --- | --- | --- | --- |
| trigger_threshold | float | 0.4 | 0.2–0.6 | Mean novelty below which dishabituation fires |
| --- | --- | --- | --- | --- |
| max_triggers_per_session | int | 8   | 3–15 | Maximum dishabituation events per session |
| --- | --- | --- | --- | --- |
| min_trigger_interval_s | float | 90  | 60–300 | Minimum seconds between triggers |
| --- | --- | --- | --- | --- |
| recency_penalty_window | int | 3   | 2–5 | Same-type suppression window (recent trigger count) |
| --- | --- | --- | --- | --- |
| depth_intensity_ceiling | float | 0.8 | 0.6–0.9 | Trance depth above which only minimal triggers fire |
| --- | --- | --- | --- | --- |
| cooldown_visual_s | float | 180 | 90–360 | Cooldown before visual surprise can fire again |
| --- | --- | --- | --- | --- |
| cooldown_audio_s | float | 120 | 60–240 | Cooldown before audio deviant can fire again |
| --- | --- | --- | --- | --- |
| cooldown_crossmodal_s | float | 300 | 180–600 | Cooldown for crossmodal mismatch trigger |
| --- | --- | --- | --- | --- |
| cooldown_semantic_s | float | 90  | 45–180 | Cooldown for semantic pivot trigger |
| --- | --- | --- | --- | --- |
| cooldown_gain_s | float | 150 | 90–300 | Cooldown for gain surprise trigger |
| --- | --- | --- | --- | --- |

### 12.6 Rotation Engine

| **Name** | **Type** | **Default** | **Range** | **Description** |
| --- | --- | --- | --- | --- |
| cooling_threshold | float | 0.3 | 0.1–0.5 | macro_novelty below which stimulus enters COOLING |
| --- | --- | --- | --- | --- |
| reactivation_threshold | float | 0.5 | 0.3–0.7 | Projected novelty required to return from COOLING to ACTIVE |
| --- | --- | --- | --- | --- |
| max_cooling_cycles | int | 3   | 2–5 | COOLING entries before forced RETIREMENT |
| --- | --- | --- | --- | --- |
| retirement_rest_days | int | 30  | 14–60 | Days before a RETIRED stimulus can return to ACTIVE |
| --- | --- | --- | --- | --- |
| archive_threshold | float | 0.05 | 0.01–0.1 | macro_novelty after rest below which stimulus is ARCHIVED |
| --- | --- | --- | --- | --- |

### 12.7 EEG Feedback (Optional)

| **Name** | **Type** | **Default** | **Range** | **Description** |
| --- | --- | --- | --- | --- |
| alpha_window_pre_s | float | 2.0 | 1.0–4.0 | Seconds of pre-stimulus alpha measurement |
| --- | --- | --- | --- | --- |
| alpha_window_post_s | float | 2.0 | 1.0–4.0 | Seconds of post-stimulus alpha measurement |
| --- | --- | --- | --- | --- |
| effectiveness_ema_alpha | float | 0.15 | 0.05–0.3 | EMA smoothing factor for effectiveness tracking |
| --- | --- | --- | --- | --- |
| correction_weight | float | 0.5 | 0.1–1.0 | How much neural feedback adjusts the exposure-based novelty score |
| --- | --- | --- | --- | --- |

## 13\. Safety Constraints

**Mandatory Safety Requirements**

The following constraints are non-negotiable. No configuration parameter or runtime condition may override them.

1.  **Intensity limits.** Dishabituation triggers must never exceed safe stimulus intensity limits defined in Doc 37's gain manifold. The trigger is a _surprise_, not a _shock_.
2.  **Photosensitivity.** Visual surprise triggers must respect photosensitivity constraints. No rapid full-screen flicker. No high-contrast alternation faster than 3 Hz. Color temperature jumps must be gradual (ramp over ≥100ms), not instantaneous.
3.  **Audio ceiling.** Audio deviant triggers must not exceed the gain ceiling for the current depth state. A novel tone pip at unexpected frequency is effective; a loud one is dangerous.
4.  **DeliveryGate.** All triggers pass through the quad-gate system (Doc 42). No bypassing for any reason. If DeliveryGate says no, the trigger is deferred, not forced.
5.  **SLEEP phase.** During SLEEP phases, ALL dishabituation is disabled. The dishabituation scheduler enters a dormant state and does not accumulate trigger debt. Sleep architecture must not be disrupted for novelty.
6.  **Trigger logging.** Every dishabituation event is logged to the dishabituation_log table with pre/post novelty scores and trance depth. This is mandatory, not optional — it is the audit trail for safety review.

## 14\. Implementation Notes for Vesper

Vesper —

This is a new module: habituation_engine.py. It doesn't replace anything in the existing codebase; it adds a tracking and management layer that sits alongside the Conductor loop and provides novelty intelligence to all the stimulus-producing systems.

Architecturally, this is three independent components composed into one engine:

1.  **Tracker** — the StimulusRecord data structure and the \_compute_novelty() math. Pure data, no side effects. Each layer calls on_stimulus_presented() and gets back a novelty score. That's the entire interface for tracking.
2.  **Budgeter** — the NoveltyBudget class. Consumes novelty units on each presentation, tracks per-class allocations, signals when a class is exhausted. The Conductor checks budget.remaining() and pivots to different content when a class runs dry.
3.  **Scheduler** — the DishabituationScheduler. Monitors mean novelty, decides when and what type of trigger to fire, respects cooldowns and recency penalties. Its output is a trigger descriptor that gets handed to the appropriate layer (visual_display.py, audio_engine.py, or the semantic selector) for execution.

Integration touchpoints:

- The tick() method is called alongside EEG/PPG/IMU ticks in the Conductor loop. It returns a live_control.json patch dictionary.
- Database tables go in somna_db.py using the existing SQLite pattern. Three new tables: stimulus_exposure, session_exposure, dishabituation_log.
- Dishabituation triggers need hooks in visual_display.py (for visual surprise), audio_engine.py (for audio deviants and gain surprises), and the semantic selector (for semantic pivots). Each hook receives a trigger descriptor and executes a brief, bounded perturbation. The hooks are small — they don't need to understand the scheduling logic, just execute the trigger and report back.
- The novelty budget system informs the agent's content selection via the Conductor. When budget runs low for a class, the Conductor should pivot to a class with remaining budget. This is a recommendation signal, not a hard block — the Conductor retains final authority.

**Suggested implementation order:**

1.  Start with micro and meso tracking — these are purely within-session and don't need the database. Get on_stimulus_presented() returning reasonable novelty scores.
2.  Add the budget system and wire it into the Conductor's content selection logic.
3.  Bring up macro tracking with the database schema. Once session_exposure data starts accumulating across sessions, the macro decay model will have real data to work with.
4.  Implement the dishabituation scheduler and trigger hooks.
5.  The EEG effectiveness feedback loop (Section 11) is an enhancement — add it last, after the exposure-counting system is proven stable.

The stimulus library size requirements in Section 7 define the minimum content that needs to exist for the rotation engine to function properly. The engine degrades gracefully with smaller libraries — it will not crash or error — but it won't be able to enforce proper cooling periods if the active pool is too small. If the current content libraries are below minimums, that's a content creation task, not an engine issue. The engine works with whatever it has.

This is a big module in terms of specification, but the actual code surface is modest. The math is straightforward exponentials and clamps. The budget is an accounting ledger. The scheduler is a priority queue with cooldowns. Each piece is independently testable. Trust the architecture — it's clean.

— Reese

Somna Doc 45 — Habituation & Novelty Management Engine · Prepared by Reese · April 2026  
Distribution: Ed (System Architect), Vesper (Implementation Agent) · Confidential