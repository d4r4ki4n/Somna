# Conductor FSM — Session Phase Specification

**Status:** Specification (v2 — rebuilt with full subsystem integration)

**Author:** Ed / Reese

**Date:** 17 April 2026

**Loaded by:** Active session ticks via `conductor.tick()` in `_interactive_tick`

**Authority:** This file is a compact reference for the LLM agent during active sessions. The authoritative design specification lives in the Somna Bible, Chapter 4 — Session Architecture. When this file and the Bible disagree, the Bible wins.

---

## Overview

The Conductor is the top-level FSM that orchestrates all Somna subsystems into a coherent session arc. It is the **single agent-side entity** that writes to `live_control.json` via the IPC StateServer.

**File:** `session/conductor.py`. Instantiated by `SomnaAgent` at fresh session start; ticked via `conductor.tick()` in `_interactive_tick`.

**Write API:** All Conductor writes use the module-level function:

```python
from ipc import patch_live
patch_live({"beat_frequency": 6.0, "spiral_style": "tunnel_dream"})
```

Do NOT use `_patch_live()` (deprecated private method pattern). Do NOT write `live_control.json` directly. See Bible Ch.1 §IPC-StateServer.

---

## Design Principles

1. **Single Writer Rule** — Conductor is the only agent-side entity that writes to `live_control.json`. All subsystem trackers (SQI, ASSR, FAA, FreqLeader, SessionScorer) are read-only sensors.
   Bible Ch.1 §3: One-Origin Rule

2. **Phase Primacy** — Every decision is made in context of the current phase. No phaseless operation.
   Bible Ch.4 §8

3. **Metric Gating Cascade** — SQI first → metric-specific confidence → phase transition. Always in that order.
   Bible Ch.2 §7

4. **Hysteresis by Design** — Transitions toward deeper states require shorter hold times. Exception: fractionation transitions are deliberately fast in both directions.
   Bible Ch.4 §12

5. **Graceful Degradation** — Timer-based fallback when EEG is unavailable. Sessions always complete.
   Bible Ch.4 §15

---

## Fourteen Phases

The Conductor has 14 phases across three domains: trance (7), sleep (5), GENUS (1), plus SESSION_END.

| Phase | Entry Condition | Target Band | Tick Rate | Frac. Eligible |
|---|---|---|---|---|
| CALIBRATION | Session start | None | 5 s | No |
| INDUCTION | SQI >= REDUCED x2ch for 30 s + IAF detected | Alpha (IAF) | 10 s | No |
| DEEPENING | ASSR confidence >= REDUCED for 60 s | Alpha -> Theta | 10 s | After 5 min |
| MAINTENANCE | trance_score > 0.65 (90 s) + ASSR >= REDUCED (60 s) | Theta 4-7 Hz | 30 s | Yes |
| FRAC_EMERGE | Frac eligible + trance > 0.5 (60 s) | Alpha (return to IAF) | 5 s | No |
| FRAC_EMERGE_HOLD | SEF95 > 15 or 45 s timeout | Alpha | 5 s | No |
| FRAC_REDROP | Hold elapsed 15-45 s | Theta | 10 s | Yes |
| GENUS_BLOCK | GENUS requested + eligibility met | Gamma 40 Hz | 10 s | No |
| SLEEP_APPROACH | session_type=sleep + depth criteria | Theta -> Delta | 30 s | No |
| SLEEP_ONSET | sleep_onset_detected or SEF95 < 8 for 120 s | Delta / silence | 60 s | No |
| SLEEP_MAINTAIN | N2 or N3 for >= 3 consecutive epochs after SLEEP_ONSET | Delta | 60 s | No |
| SLEEP_TRAINING | HTW eligible + N1 for >= 3 epochs during SLEEP_MAINTAIN | Theta 5.5 Hz | 30 s | No |
| SLEEP_WAKE | WAKE for >= 30 s during SLEEP_MAINTAIN | -- | 30 s | No |
| SESSION_END | Timer / user stop / sleep duration met / 2 min of WAKE | Ramp to IAF | -- | No |

---

## Key Parameter Targets Per Phase

### CALIBRATION
| Parameter | Value | Notes |
|---|---|---|
| beat_frequency | 0 | No entrainment during baseline |
| spiral_chaos | 0.15 | Minimal visual complexity |
| trail_decay | 0.0 | No FBO trail |
| veil_mode | drift | Gentle, non-directional |
| shadow_opacity_target | 0 | No subliminal shadows |
| sr_noise_level | 0.0 | No stochastic resonance |

### INDUCTION
| Parameter | Value | Notes |
|---|---|---|
| beat_frequency | IAF | Meet the user's individual alpha |
| spiral_chaos | 0.2 | Low complexity |
| trail_decay | 0.3 | Mild trail begins |
| veil_mode | scroll or converge | Directional text flow |
| shadow_opacity_target | 20 | Subliminal shadows begin |
| freq_lead_mode | meet | Match, don't lead yet |

### DEEPENING
| Parameter | Value | Notes |
|---|---|---|
| spiral_style | See Palette Override below | Default: tunnel_dream or galaxy |
| veil_mode | converge or tunnel | Immersive modes |
| spiral_chaos | 0.25 -> 0.4 | Increasing over phase |
| trail_decay | 0.4 -> 0.6 | Building persistence |
| sr_noise_level | 0.0-0.15 | Gradual introduction |
| freq_lead_mode | lead | Active frequency descent |

**Note on `spiral_style`:** The original specification used `"liminal"` — this style name appears in the Doc 16 integration map but may have been renamed in the spiral renderer. Verify against the 14 valid styles in `spiral_layer.py`: `tunnel_dream`, `galaxy`, `archimedean`, `kaleidoscope`, `interference`, `electric`, `vortex`, `dna`, `fibonacci`, `rose`, `moire`, `spirograph`, `fermat`, `superformula`. If `liminal` is not recognized, use `tunnel_dream` (closest perceptual equivalent — immersive depth-inducing geometry).

### MAINTENANCE
| Parameter | Value | Notes |
|---|---|---|
| veil_mode | tunnel | Maximum immersion |
| spiral_style | See Palette Override below | Default: tunnel_dream or galaxy |
| trail_decay | 0.6-0.85 | High persistence |
| sr_noise_level | 0.05-0.12 | Sustained low-level noise |
| shadow_opacity_target | 15 | Subliminal maintained |
| freq_lead_mode | sustain | Hold theta depth |

### FRAC_EMERGE
| Parameter | Value | Notes |
|---|---|---|
| spiral_chaos | 0.05 | SNAP — V1 perceptual jolt |
| trail_decay | 0.0 | SNAP — clean break |
| sr_noise_level | 0.0 | Withdrawn |
| shadow_opacity_target | 25 | Increased (orienting) |
| freq_lead_mode | meet | Return toward IAF |

### FRAC_EMERGE_HOLD
Hold at post-emerge values. SEF95 > 15 confirms cortical arousal, or 45 s timeout.

### FRAC_REDROP
Gradual ramp from snap values back toward pre-emerge parameters. This asymmetry (fast emerge, slow redrop) is perceptually significant — the Vogt model requires it.

### GENUS_BLOCK
| Parameter | Value | Notes |
|---|---|---|
| beat_frequency | 40 | Gamma isochronic |
| beat_type | isochronic | Clicks, not binaural |
| spiral_style | interference or kaleidoscope | High-complexity geometric |
| spiral_chaos | 0.5-0.7 | Elevated visual complexity |
| veil_mode | strobe | Stroboscopic flicker |
| shadow_opacity_target | 0 | No subliminal content |
| sr_noise_level | 0.0 | Clean signal |
| trail_decay | 0.2-0.4 | Moderate, not immersive |

**GENUS content constraint:** Cognitive engagement content ONLY. No hypnotic patterns, no deepening language, no affirmations. See Bible Ch.4 Addendum A for full GENUS specification.

### SLEEP_APPROACH
| Parameter | Value | Notes |
|---|---|---|
| veil_mode | drift | Gentle, non-stimulating |
| trail_decay | 0.85-0.95 | High, approaching total persistence |
| shadow_opacity_target | 12 -> 8 | Tapering |
| sr_noise_level | tapering to 0 | Withdrawn before sleep |
| freq_lead_mode | step-ramp | Stepped frequency descent toward delta |

**freq_lead_mode = "step-ramp":** Unlike `lead` (continuous descent), step-ramp drops the target frequency in discrete steps (e.g., 6 Hz -> 4 Hz -> 2 Hz) with 3-5 minute holds at each step. This prevents overshoot — continuous ramping toward delta can push past the user's natural descent rate and cause arousal. Step-ramp lets the brain settle at each plateau before the next drop.

### SLEEP_ONSET
| Parameter | Value | Notes |
|---|---|---|
| ALL TEXT LAYERS | OFF | No visual text |
| tts_enabled | False | Silent |
| freq_lead_enabled | False | No entrainment |
| spiral_opacity | 0 | Dark |
| veil_opacity | 0 | Dark |

**SLEEP_ONSET is SILENT.** No audio, no text, no visuals. The user is falling asleep.

### SLEEP_MAINTAIN
| Parameter | Value | Notes |
|---|---|---|
| gain_mode | sleep_maintain | Sleep-specific audio profile |
| tts_enabled | False | No voice |
| SWE | Active | Phase-locked pink noise bursts |
| TMR | Active on N2/N3 | Replay encoded cues |

Agent writes `agent_sleep_plan` here (silent, no voice). TMR replay respects `recon_locked_phrases` — see Reconsolidation Integration below.

### SLEEP_TRAINING (Hypnagogic Training Window)
| Parameter | Value | Notes |
|---|---|---|
| gain_mode | sleep_training | HTW audio profile |
| beat_frequency | 5.5 Hz binaural | Theta hold |
| tts_volume | 6 | Whisper level |
| tts_subliminal_vol | 14 | SSB above TTS |
| center_flash_on_time | 4000 ms | Long exposure |
| center_flash_off_time | 8000 ms | Long gap |

Affirmations pool replaced with pre-selected training phrases. TTS pre-synthesized before window opens via `_presynth_ready` buffer. Agent LLM prompts suppressed. Max 5 minutes. Exits to SLEEP_ONSET on deepening or timeout; to SLEEP_WAKE on genuine arousal.

### SLEEP_WAKE
Metrics compiled (sleep efficiency, time-in-stage, SWA ratio). Agent says "Rest well." Transitions to SESSION_END after 2 minutes of confirmed wake.

### SESSION_END
Beat frequency ramps to IAF. Visual parameters fade. Session metrics finalized and written to DB.

---

## Somatic Palette Override

When a somatic palette chord is active during MAINTENANCE, the chord's parameters take precedence for:

- `beat_frequency`
- `carrier_waveform` (mapped to `beat_type`)
- `noise_color`
- `noise_volume`
- `spiral_style`
- `veil_mode`

The Conductor still owns these parameters regardless of palette state:

- `spiral_chaos`
- `trail_decay`
- `sr_noise_level`
- `shadow_opacity_target`
- `breath_mod`
- `breath_rate`

When no palette recommendation is available (sparse history, first session, or all candidates filtered out), the per-phase defaults listed above apply.

The palette evaluation window (12-15 min) runs within MAINTENANCE. If a chord fails (see `somatic_palette.md` for failure conditions), the agent requests fractionation via `agent_conductor_hints`. After FRAC_REDROP re-enters MAINTENANCE, there is a 3-minute cooldown before the new chord's evaluation window opens. Maximum 3 chord switches per session.

---

## Reconsolidation Integration

When a reconsolidation protocol is active during MAINTENANCE:

- The recon engine's `_recon_tick()` runs alongside the Conductor's tick
- During LOCKOUT phase, `recon_locked_phrases` prevents TMR replay of retrieve-tagged content
- Lockout is trace-specific — all other TMR content fires normally
- The Conductor does not need to change phase for reconsolidation — it stays in MAINTENANCE throughout
- See `reconsolidation_protocol.md` for the full five-phase protocol

---

## Agent-Conductor Communication

### Agent -> Conductor: `agent_conductor_hints`

The agent writes hints to `live_control.json` via `patch_live()`. The Conductor reads these each tick:

| Hint Key | Type | Effect |
|---|---|---|
| request_fractionation | bool | Conductor initiates FRAC_EMERGE if eligible |
| suggest_emergence | bool | Conductor begins SESSION_END sequence |
| depth_target | float | Suggested trance_score target (advisory, not binding) |
| language_items_ready | bool | Language module has pre-synthesized items queued |
| recon_phase | string | Current reconsolidation phase (idle/retrieve/labilize/update/lockout/complete) |

### Conductor -> Agent: State Publication

The Conductor publishes state to `live_control.json` every tick:

| Key | Type | Content |
|---|---|---|
| conductor_phase | string | Current phase name (one of 14) |
| conductor_phase_elapsed | float | Seconds in current phase |
| conductor_frac_count | int | Fractionation cycles completed |
| conductor_frac_eligible | bool | Whether fractionation is currently allowed |
| conductor_depth_trend | string | rising / stable / declining / volatile |

---

## Conflict Resolution (Per Phase)

**INDUCTION:** ASSR is primary gate (weight 1.0). FAA receptivity does NOT compensate for ASSR failure.

**DEEPENING:** trance rising + ASSR declining -> HOLD freq leading. FAA withdrawal > 60 s -> consider fractionation as intervention.

**MAINTENANCE:** FAA negative > 30 s -> suppress affirmations. trance_score rate < -0.1/min -> consider fractionation. Rate < -0.05/min -> nudge beat_frequency down 0.05 Hz.

**FRACTIONATION:** FAA withdrawal spikes during FRAC_EMERGE are EXPECTED (orienting response to V1 jolt). Do NOT treat as negative signal.

**SLEEP_APPROACH:** Declining ASSR is EXPECTED AND GOOD. Do NOT attempt to re-entrain. The brain is supposed to desynchronize from the entrainment signal as it approaches sleep.

---

## Fractionation Details

The `chaos` snap to 0.05 and `trail_decay` snap to 0.0 on FRAC_EMERGE implements the V1 perceptual jolt. This is deterministic — not dependent on prompt engineering. The gradual ramp on FRAC_REDROP creates the perceptual asymmetry (fast emergence, slow redescent) that the Vogt model requires.

Hold durations: first cycle = 35 s, second = 25 s, third+ = 15 s.

Max fractionations by session length:
- < 25 min: 1
- < 35 min: 2
- < 50 min: 3
- 50+ min: 4

See Bible Ch.4 Addendum A for timing constraints.

---

## Conductor-Owned Parameters

The following parameters are exclusively managed by the Conductor when active. The LLM agent's `adjustments` are filtered to exclude these:

**Conductor-owned:** `beat_frequency`, `beat_type`, `spiral_chaos`, `trail_decay`, `veil_mode`, `spiral_style`, `shadow_opacity_target`, `sr_noise_level`, `breath_mod`, `breath_rate`

**Agent-retained:** `volume`, `audio_muted`, `tts_enabled`, `tts_subliminal`, `noise_volume`, speech/prompt content, `next_affirmation`

**Palette interaction:** When a somatic palette chord is active, the chord sets values for the subset of conductor-owned params listed in Somatic Palette Override above. The Conductor does not fight the palette — it reads the palette's values as its own targets for those parameters.

---

## Freq Lead Modes

| Mode | Behavior | Used In |
|---|---|---|
| meet | Match user's current dominant frequency | CALIBRATION (implicit), INDUCTION, FRAC_EMERGE |
| lead | Continuously descend toward target band | DEEPENING |
| hold | Freeze at current frequency | Emergency / metric conflict |
| sustain | Maintain current theta depth | MAINTENANCE |
| step-ramp | Discrete stepped descent with plateau holds | SLEEP_APPROACH |

---

## Timer-Based Fallback

When `_timer_mode` is active (EEG disabled or sustained SQI failure), `_evaluate_transitions` uses a fixed schedule:

| Elapsed | Phase Entered |
|---|---|
| 0 min | CALIBRATION |
| 1 min | INDUCTION |
| 5 min | DEEPENING |
| 15 min | MAINTENANCE |

The session hard-stop at `session_duration` still applies — MAINTENANCE holds until then. Visual parameter snaps (chaos, trail_decay) execute identically to EEG-guided mode.

---

## DB Schema (Snapshot)

**Warning:** This schema is a snapshot for agent reference. If queries fail, check `session/session_db.py` for the current schema — it is the single source of truth.

`conductor_decisions` table in `somna.db` — one row per Conductor tick. `phase_summary` view aggregates by session+phase for SessionAnalyzer queries.

### Key Queries

- **Induction learning curve:** `SELECT AVG(phase_duration) FROM phase_summary WHERE phase='INDUCTION' GROUP BY session_id`
- **Fractionation effectiveness:** Compare avg_trance_score in MAINTENANCE before/after fractionation cycles
- **Phase-specific problems:** Low ASSR during DEEPENING but acceptable during INDUCTION -> frequency leading issue, not initial entrainment
- **FAA-affirmation correlation:** Cross-reference avg_faa in MAINTENANCE with affirmation counts

---

## Integration Map

| Subsystem | Integration Point |
|---|---|
| Fractionation (Bible Ch.4 Addendum A) | FRAC_EMERGE/HOLD/REDROP phases; chaos-snap V1 jolt |
| Sleep Onset (Bible Ch.7) | SLEEP_APPROACH + SLEEP_ONSET phases; step-ramp schedule |
| Spiral Renderer | spiral_style per phase; verify against 14 valid styles |
| SEF95 / Trance Score (Bible Ch.2) | Primary transition metric; sleep onset gate |
| Stochastic Resonance (Bible Ch.8) | sr_noise_level per phase; withdrawn during frac + sleep |
| FBO Trail Decay (Bible Ch.8) | Snap to 0 on EMERGE, gradual ramp on REDROP |
| Subliminal Text (Bible Ch.6) | veil_mode tunnel/converge during deep phases |
| SQI (Bible Ch.2) | Gates entire evaluation cycle — checked FIRST every tick |
| ASSR (Bible Ch.2) | Gates freq leading; modality switch protocol |
| FAA (Bible Ch.2) | Gates affirmation delivery; withdrawal expected during FRAC_EMERGE |
| Adaptive Freq Leading (Bible Ch.3) | Conductor sets mode: meet/lead/hold/sustain/step-ramp |
| Session Scoring (Bible Ch.4) | Decision log -> conductor_decisions -> phase_summary view |
| Sleep Enhancement (Bible Ch.7) | SleepStageClassifier, SlowWaveEnhancer; SLEEP phases |
| TMR (Bible Ch.7) | Trance encoding + NREM replay; respects recon_locked_phrases |
| HTW (Bible Ch.7) | SLEEP_TRAINING phase; eligibility gate; TTS presynth |
| Somatic Palette (Bible Ch.4) | Chord override during MAINTENANCE; evaluation window timing |
| Reconsolidation (Bible Ch.6) | recon_locked_phrases lockout during MAINTENANCE; trace-specific TMR blocking |
| Interference Graph (Bible Ch.9) | User-composed chords feed palette candidates; spread knob offsets |
| Language Module | language_items_ready hint; delivery during DEEPENING/MAINTENANCE |
