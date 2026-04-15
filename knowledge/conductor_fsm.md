# Conductor FSM — Session Phase Specification

Design spec: Bible Ch.4 — Session Architecture

Last updated: 2026-04-11 | Rebuilt from Bible Ch.4 Â§Conductor with Bible citations

## Authority Note

This file is a compact reference for the LLM agent during active sessions. The authoritative design specification lives in the

Somna Bible, Chapter 4 — Session Architecture

. When this file and the Bible disagree, the Bible wins.

## Overview

The Conductor is the top-level FSM that orchestrates all Somna subsystems into a coherent session arc. It is the **single agent-side entity** that calls \_patch_live(). All subsystem trackers (SQI, ASSR, FAA, FreqLeader, SessionScorer) are read-only sensors; they write their outputs to live_control.json and the Conductor reads them there.

**File:** conductor.py at project root. Instantiated by SomnaAgent at fresh session start; ticked via conductor.tick() in \_interactive_tick.

## Design Principles

1.  **Single Writer Rule** — Conductor is the only agent-side entity that writes to live_control.json.  
    Bible Ch.1 §3: One-Origin Rule
2.  **Phase Primacy** — Every decision is made in context of the current phase. No phaseless operation.  
    Bible Ch.4 §8
3.  **Metric Gating Cascade** — SQI first → metric-specific confidence → phase transition. Always in that order.  
    Bible Ch.2 §7
4.  **Hysteresis by Design** — Transitions toward deeper states require shorter hold times. Exception: fractionation transitions are deliberately fast in both directions.  
    Bible Ch.4 §12
5.  **Graceful Degradation** — Timer-based fallback when EEG is unavailable. Sessions always complete.  
    Bible Ch.4 §15

## Fourteen Phases

| **Phase** | **Entry Condition** | **Target Band** | **Tick Rate** | **Frac. Eligible** |
| --- | --- | --- | --- | --- |
| CALIBRATION | Session start | None | 5s  | No  |
| --- | --- | --- | --- | --- |
| INDUCTION | SQI ≥ REDUCED ×2ch for 30s + IAF detected | Alpha (IAF) | 10s | No  |
| --- | --- | --- | --- | --- |
| DEEPENING | ASSR confidence ≥ REDUCED for 60s | Alpha → Theta | 10s | After 5 min |
| --- | --- | --- | --- | --- |
| MAINTENANCE | trance_score > 0.65 (90s) + ASSR ≥ REDUCED (60s) | Theta 4–7 Hz | 30s | Yes |
| --- | --- | --- | --- | --- |
| FRAC_EMERGE | Frac eligible + trance > 0.5 (60s) | Alpha (return to IAF) | 5s  | No  |
| --- | --- | --- | --- | --- |
| FRAC_EMERGE_HOLD | SEF95 > 15 or 45s timeout | Alpha | 5s  | No  |
| --- | --- | --- | --- | --- |
| FRAC_REDROP | Hold elapsed 15–45s | Theta | 10s | Yes |
| --- | --- | --- | --- | --- |
| GENUS_BLOCK | GENUS requested + eligibility met | Gamma 40 Hz | 10s | No  |
| --- | --- | --- | --- | --- |
| SLEEP_APPROACH | session_type=sleep + depth criteria | Theta → Delta | 30s | No  |
| --- | --- | --- | --- | --- |
| SLEEP_ONSET | sleep_onset_detected or SEF95 < 8 for 120s | Delta / silence | 60s | No  |
| --- | --- | --- | --- | --- |
| SLEEP_MAINTAIN | N2 or N3 for ≥ 3 consecutive epochs after SLEEP_ONSET | Delta | 60s | No  |
| --- | --- | --- | --- | --- |
| SLEEP_TRAINING | HTW eligible + N1 for ≥ 3 epochs during SLEEP_MAINTAIN | Theta 5.5 Hz | 30s | No  |
| --- | --- | --- | --- | --- |
| SLEEP_WAKE | WAKE for ≥ 30s during SLEEP_MAINTAIN | —   | 30s | No  |
| --- | --- | --- | --- | --- |
| SESSION_END | Timer / user stop / sleep duration met / 2 min of WAKE | Ramp to IAF | —   | No  |
| --- | --- | --- | --- | --- |

**Note:** GENUS_BLOCK is new — see Bible Ch.4 Addendum A for full specification.

## Key Parameter Targets Per Phase

### CALIBRATION Bible Ch.4 §9

beat_frequency = 0 spiral_chaos = 0.15 trail_decay = 0.0 veil_mode = "drift" shadow_opacity_target= 0 sr_noise_level = 0.0

### INDUCTION Bible Ch.4 §10

beat_frequency = IAF spiral_chaos = 0.2 trail_decay = 0.3 veil_mode = "scroll" | "converge" shadow_opacity_target= 20 freq_lead_mode = "meet"

### DEEPENING Bible Ch.4 §10

spiral_style = "liminal" veil_mode = "converge" | "tunnel" chaos = 0.25 → 0.4 trail_decay = 0.4 → 0.6 sr_noise_level = 0.0–0.15 freq_lead_mode = "lead"

### MAINTENANCE Bible Ch.4 §11

veil_mode = "tunnel" spiral_style = "liminal" trail_decay = 0.6–0.85 sr_noise_level = 0.05–0.12 shadow_opacity_target= 15 freq_lead_mode = "sustain"

### FRAC_EMERGE Bible Ch.4 §12

spiral_chaos = 0.05 ← SNAP trail_decay = 0.0 ← SNAP sr_noise_level = 0.0 shadow_opacity_target= 25 freq_lead_mode = "meet" (toward IAF)

### FRAC_REDROP Bible Ch.4 §12

Gradual ramp from snap values back toward pre-emerge params. Asymmetric: fast emergence, slow redescent.

### GENUS_BLOCK Bible Ch.4 Addendum A

40 Hz isochronic clicks + stroboscopic flicker Cognitive engagement content NO hypnotic patterns See Addendum A for full spec.

### SLEEP_APPROACH Bible Ch.7 §5

veil_mode = "drift" trail_decay = 0.85–0.95 shadow_opacity = tapering 12 → 8 sr_noise_level = tapering to 0

### SLEEP_ONSET Bible Ch.7 §8

ALL TEXT LAYERS OFF tts_enabled = False freq_lead_enabled = False SILENT

### SLEEP_MAINTAIN Bible Ch.7 §10

gain_mode = "sleep_maintain" tts_enabled = False SWE phase-locked pink noise bursts TMR replay on N2/N3

### SLEEP_TRAINING Bible Ch.7 §16

gain_mode = "sleep_training" beat_frequency = 5.5 Hz tts_volume = 6 center_flash_on_time = 4000 ms center_flash_off_time= 8000 ms Max 5 minutes.

### SLEEP_WAKE Bible Ch.7 §18

Metrics compiled. Agent says "Rest well." Transitions to SESSION_END after 2 min of confirmed wake.

## Conflict Resolution (Per Phase)

| **Phase** | **Conflict Scenario** | **Resolution** | **Ref** |
| --- | --- | --- | --- |
| INDUCTION | ASSR failing but FAA positive | ASSR is primary gate. FAA does **NOT** compensate for ASSR failure. | Bible Ch.2 §14 |
| --- | --- | --- | --- |
| DEEPENING | trance rising + ASSR declining | HOLD freq leading. FAA withdrawal > 60s → consider fractionation. | Bible Ch.4 §10 |
| --- | --- | --- | --- |
| MAINTENANCE | FAA negative > 30s | Suppress affirmations. trance_score rate < -0.1/min → consider fractionation. | Bible Ch.4 §11 |
| --- | --- | --- | --- |
| FRACTIONATION | FAA withdrawal spikes during FRAC_EMERGE | EXPECTED. Do **NOT** treat as negative signal. | Bible Ch.4 §12 |
| --- | --- | --- | --- |
| SLEEP_APPROACH | Declining ASSR | EXPECTED AND GOOD. Do **NOT** attempt to re-entrain. | Bible Ch.7 §5 |
| --- | --- | --- | --- |

## Fractionation Integration Bible Ch.4 §12

### Chaos Snap

On FRAC_EMERGE entry, spiral_chaos snaps instantly to 0.05 and trail_decay snaps to 0.0. This is the V1 jolt — a deliberate perceptual disruption that leverages the contrast between deep-trance visual complexity and sudden simplicity.

### Hold Duration

FRAC_EMERGE_HOLD waits for either SEF95 > 15 (cortical arousal confirmed) or a 45-second timeout. The hold phase lasts 15–45 seconds before transitioning to FRAC_REDROP.

### Redrop Ramp

Parameters ramp gradually from snap values back toward pre-emerge targets. The asymmetry is intentional: emergence is fast (snap), redescent is slow (ramp). This produces the deepening-on-return effect central to fractionation.

### Max Fractionations

Maximum **3 fractionation cycles per session**. After the third cycle completes, fractionation eligibility is permanently disabled for the remainder of the session. The Conductor tracks cycle count in frac_count.

## DB Schema Bible Ch.4 §22

### conductor_decisions Table

CREATE TABLE conductor_decisions ( id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, timestamp REAL NOT NULL, phase TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT, metrics_snapshot TEXT, -- JSON blob params_applied TEXT -- JSON blob );

### phase_summary View

CREATE VIEW phase_summary AS SELECT session_id, phase, MIN(timestamp) AS entered_at, MAX(timestamp) AS exited_at, MAX(timestamp) - MIN(timestamp) AS duration_s, COUNT(\*) AS tick_count FROM conductor_decisions GROUP BY session_id, phase ORDER BY entered_at;

### Key Queries

\-- All decisions for current session SELECT \* FROM conductor_decisions WHERE session_id = :sid ORDER BY timestamp; -- Phase durations for session summary SELECT \* FROM phase_summary WHERE session_id = :sid; -- Last N decisions (debugging) SELECT \* FROM conductor_decisions ORDER BY timestamp DESC LIMIT :n;

## Timer-Based Fallback Bible Ch.4 §15

When EEG is unavailable or SQI remains below threshold, the Conductor falls back to timer-driven phase transitions. Sessions always complete.

| **Phase** | **Fallback Duration** | **Next Phase** |
| --- | --- | --- |
| CALIBRATION | 2 min | INDUCTION |
| --- | --- | --- |
| INDUCTION | 5 min | DEEPENING |
| --- | --- | --- |
| DEEPENING | 8 min | MAINTENANCE |
| --- | --- | --- |
| MAINTENANCE | Remaining session time | SESSION_END |
| --- | --- | --- |
| SLEEP_APPROACH | 10 min | SLEEP_ONSET |
| --- | --- | --- |
| SLEEP_ONSET | 15 min | SLEEP_MAINTAIN |
| --- | --- | --- |
| SLEEP_MAINTAIN | Target sleep duration | SESSION_END |
| --- | --- | --- |
| FRAC_EMERGE_HOLD | 45s | FRAC_REDROP |
| --- | --- | --- |
| GENUS_BLOCK | Per protocol duration | Previous phase |
| --- | --- | --- |

## Conductor-Owned Parameters Bible Ch.4 §14

### Parameters Written by Conductor

These are the **only** parameters the Conductor sets directly via \_patch_live():

| **Parameter** | **Type** | **Description** |
| --- | --- | --- |
| beat_frequency | float | Binaural/isochronic beat target frequency (Hz) |
| --- | --- | --- |
| spiral_chaos | float | Visual spiral complexity (0.0–1.0) |
| --- | --- | --- |
| spiral_style | string | "default" \| "liminal" |
| --- | --- | --- |
| trail_decay | float | FBO trail persistence (0.0–1.0) |
| --- | --- | --- |
| veil_mode | string | "drift" \| "scroll" \| "converge" \| "tunnel" |
| --- | --- | --- |
| shadow_opacity_target | int | Subliminal text shadow opacity (0–100) |
| --- | --- | --- |
| sr_noise_level | float | Stochastic resonance noise amplitude (0.0–0.3) |
| --- | --- | --- |
| freq_lead_mode | string | "meet" \| "lead" \| "hold" \| "sustain" \| "step-ramp" |
| --- | --- | --- |
| freq_lead_enabled | bool | Master enable for frequency leading |
| --- | --- | --- |
| tts_enabled | bool | Master enable for TTS output |
| --- | --- | --- |
| tts_volume | int | TTS volume level (0–10) |
| --- | --- | --- |
| gain_mode | string | "normal" \| "sleep_maintain" \| "sleep_training" |
| --- | --- | --- |
| center_flash_on_time | int | Flash on duration (ms) — SLEEP_TRAINING only |
| --- | --- | --- |
| center_flash_off_time | int | Flash off duration (ms) — SLEEP_TRAINING only |
| --- | --- | --- |

### Parameters Read (Not Written) by Conductor

These values are produced by subsystem trackers and consumed read-only:

sqi_level ← SQI tracker assr_confidence ← ASSR tracker faa_score ← FAA tracker trance_score ← SessionScorer sef95 ← EEG pipeline iaf ← Calibration sleep_stage ← SleepStageClassifier freq_lead_actual ← FreqLeader

## Integration Map

| **Bible Reference** | **Subsystem** | **Integration Point** |
| --- | --- | --- |
| Bible Ch.4 §12 | Fractionation | FRAC_EMERGE/HOLD/REDROP phases; chaos-snap V1 jolt |
| --- | --- | --- |
| Bible Ch.7 §5-8 | Sleep Onset | SLEEP_APPROACH + SLEEP_ONSET phases; step-ramp schedule |
| --- | --- | --- |
| Bible Ch.8 §6 | Liminal Spiral | spiral_style="liminal" preferred in DEEPENING + MAINTENANCE |
| --- | --- | --- |
| Bible Ch.2 §9 | SEF95 / Trance Score | Primary transition metric; sleep onset gate |
| --- | --- | --- |
| Bible Ch.3 §14 | Stochastic Resonance | sr_noise_level per phase; withdrawn during frac + sleep |
| --- | --- | --- |
| Bible Ch.8 §7 | FBO Trail Decay | Snap to 0 on EMERGE, gradual ramp on REDROP |
| --- | --- | --- |
| Bible Ch.8 §4-5 | Subliminal Text | veil_mode "tunnel"/"converge" during deep phases |
| --- | --- | --- |
| Bible Ch.2 §7 | SQI | Gates entire evaluation cycle — checked FIRST every tick |
| --- | --- | --- |
| Bible Ch.2 §14 | ASSR | Gates freq leading; modality switch protocol |
| --- | --- | --- |
| Bible Ch.2 §15 | FAA | Gates affirmation delivery; withdrawal expected during FRAC_EMERGE |
| --- | --- | --- |
| Bible Ch.3 §8 | Adaptive Freq Leading | Conductor sets mode: meet/lead/hold/sustain/step-ramp |
| --- | --- | --- |
| Bible Ch.4 §18 | Session Scoring | Decision log → conductor_decisions → phase_summary view |
| --- | --- | --- |
| Bible Ch.7 §10-15 | Sleep Enhancement | SleepStageClassifier, SlowWaveEnhancer; SLEEP phases |
| --- | --- | --- |
| Bible Ch.7 §20-22 | TMR | TMREngine trance encoding + NREM replay; channel 6 |
| --- | --- | --- |
| Bible Ch.7 §16-17 | HTW | SLEEP_TRAINING phase; HTW eligibility gate; TTS presynth |
| --- | --- | --- |
| Bible Ch.4 Addendum A | GENUS | GENUS_BLOCK phase; 40 Hz gamma entrainment; frequency exclusivity |
| --- | --- | --- |

— End of conductor_fsm.md —