# Calibration & First-10-Sessions Protocol

**Status:** Specification (v2 — targeted fixes: Bible refs, package paths, subsystem cross-references)

**Author:** Ed / Reese

**Date:** 17 April 2026

**Loaded by:** `conductor.py` at session startup (checks `calibration_complete`); `_load_idle_knowledge()` during first 10 sessions

**Authority:** This file is the operational reference for the LLM agent. The authoritative design specification lives in the Somna Bible, Chapter 2 — Biosignal Science, §Calibration. When this file and the Bible disagree, the Bible wins.

---

## 1. The Problem: Population Defaults Are Not Your Neurophysiology

Every threshold currently hardcoded across the codebase is a literature-derived population estimate, not a measurement from the actual user's brain. The following thresholds are in active use with no individual characterization:

| Threshold | Bible Reference | Problem |
|-----------|----------------|---------|
| `trance_score > 0.6` (SEF95-based) | Bible Ch.2 §SEF95 | Population estimate from clinical anesthesia monitoring (Tobar et al. 2022) |
| `ASSR confidence > 0.3` | Bible Ch.2 §ASSR | Arbitrary starting point, no individual characterization |
| `FAA > 0` for affirmation gating | Bible Ch.2 §FAA | Metzen et al. 2021 (N=370) found no population-level frontal alpha asymmetry — no "normal" direction exists |
| `IAF ≈ 10 Hz` | Bible Ch.3 §Frequency-Leading | Population mean; individual range is 8–13 Hz |
| `SEF95 < 10 Hz = deep trance` | Bible Ch.2 §SEF95 | ICU sedation monitoring, not hypnotic entrainment — wrong domain |
| Session scoring ranges | Bible Ch.5 §Scoring | Population norms, not personal performance range |

Muse 2 is validated for PSD, IAF, and FAA measurement (Cannard & Wahbeh, bioRxiv) and alpha detection comparable to research-grade DSI-24 (Lee et al. 2026, Scientific Reports), but absolute values will differ from clinical EEG literature due to electrode placement, impedance characteristics, and 4-channel limitation. Ricci et al. found SEF95 bias of 0.62 Hz between clinical devices with 95% limits of agreement spanning nearly 10 Hz — Muse 2 divergence from literature values is expected and acceptable as long as personal baselines are established.

**The solution:** 10 structured sessions that progressively exercise each subsystem, capture personal neurophysiological baselines, and replace every population default with individually-measured values.

Reference: Nam & Choi 2020 (*NeuroRegulation*): initially setting thresholds for easy compensation (high reward frequency) was more effective than hard compensation — so the protocol starts with deliberately lenient thresholds and tightens progressively.

---

## 2. Architecture: `session/calibration_manager.py`

Module location: `session/calibration_manager.py` (within the `session` package).

Purpose: manage the first-10-sessions calibration protocol, persist results to `somna.db`, and expose a threshold lookup API that the Conductor and session scorer query to replace population defaults with personal values.

### Integration Pattern

```python
from session.calibration_manager import CalibrationManager

cal = CalibrationManager(db_path="somna.db")

# Before (hardcoded population default):
if trance_score > 0.65:

# After (personal threshold with population fallback):
if trance_score > cal.get_threshold("trance_moderate", 0.65):
```

The fallback is always the current hardcoded value — zero regression risk until personal data exists.

All parameter writes go through the IPC StateServer:

```python
from ipc import patch_live
patch_live({"calibration_phase": "session_3", "calibration_status": "active"})
```

Do NOT use `_patch_live()` (deprecated). Do NOT write `live_control.json` directly.

### Integration Points

**`session/conductor.py`:** At startup, check `calibration_manager.calibration_complete`. If not complete, the Conductor uses lenient thresholds from the calibration manager. If complete, all phase transition thresholds use personal values.

**`agent/somna_agent.py`:** During idle planning for calibration sessions (1–10), the agent loads this knowledge file and plans sessions according to the progressive protocol below.

**`session/session_db.py`:** Calibration results are stored in a `calibration_baselines` table alongside the standard session tables.

---

## 3. The 10-Session Progressive Protocol

Each session targets specific subsystems for exercising and measurement. Sessions build on each other — earlier sessions establish baselines that later sessions refine.

### Sessions 1–3: Baseline Establishment

| Session | Focus | Subsystems Exercised | Measurements Captured |
|---------|-------|---------------------|----------------------|
| 1 | Eyes-closed resting baseline | EEG only (no entrainment) | Resting IAF, resting alpha power, resting theta/alpha ratio, resting SEF95, resting FAA direction |
| 2 | Basic entrainment response | Binaural engine, spiral layer | Entrainment response latency, alpha→theta transition time, first trance_score peak |
| 3 | Depth exploration | Conductor (CALIBRATION→INDUCTION→DEEPENING→MAINTENANCE) | Personal trance_score range (min/max), MAINTENANCE entry threshold, ASSR confidence baseline |

**Key constraints for sessions 1–3:**
- Use population-default thresholds (lenient)
- No content delivery beyond basic veil text (settling prompts only)
- No conditioning, no reconsolidation, no training mode
- Session duration: 20–30 minutes
- Agent mode: interactive (frequent check-ins to establish complexity score baseline)

### Sessions 4–6: Subsystem Exercise

| Session | Focus | Subsystems Exercised | Measurements Captured |
|---------|-------|---------------------|----------------------|
| 4 | Content delivery | TTS engine, veil, center flash, delivery gate | Delivery gate acceptance rate, TTS clarity score, center flash detection threshold |
| 5 | Conditioning baseline | Conditioning engine (Rescorla-Wagner), semantic selector | CS-US pairing response, initial association strength curve, conditioning paradigm response (via `content/conditioning_engine.py`) |
| 6 | Fractionation response | Conductor fractionation phases (FRAC_EMERGE→HOLD→REDROP) | Ratchet effect magnitude (pre/post trance_score delta), optimal hold duration, theta recovery time |

**Key constraints for sessions 4–6:**
- Begin using calibrated thresholds from sessions 1–3 where available
- Agent mode: interactive for sessions 4–5, observe for session 6 (test autonomous Conductor behavior)
- Session duration: 30–45 minutes
- **No reconsolidation.** Reconsolidation requires stable, known depth thresholds to safely gate RETRIEVE. Running recon with uncalibrated thresholds risks activating traces at insufficient depth. Reconsolidation is prohibited during all 10 calibration sessions.
- **No training mode during calibration.** Training mode's complexity score baseline should be established from sessions 1–3 interactive responses, but the operant conditioning loop should not run until thresholds are stable.

### Sessions 7–9: Refinement and Edge Cases

| Session | Focus | Subsystems Exercised | Measurements Captured |
|---------|-------|---------------------|----------------------|
| 7 | Sleep onset (if user does sleep sessions) | Conductor sleep phases, TMR cue manager | Personal SOL, sleep onset EEG signature, alpha dropout pattern |
| 8 | Extended session / depth ceiling | Full stack (60+ minute session) | Maximum sustainable trance_score, depth plateau characteristics, FAA stability over time |
| 9 | Somatic palette seeding | Palette system, Interference Graph | First 2–3 chord evaluations, initial palette entries, personal chord response patterns |

**Key constraints for sessions 7–9:**
- All thresholds should now use personal values from sessions 1–6
- Session 9 specifically seeds the somatic palette with initial data — the palette's exploration-exploitation formula (`outcome_score + 1/(n_obs + 1)`) will be in heavy exploration mode with all chords at n_obs ≤ 2
- Agent should log palette entries with full entry context (`entry_time_hour`, `days_since_last`, `entry_trance`, `entry_mood`, `recent_sleep`)
- Session duration: 45–60 minutes (session 8: 60+ minutes)

### Session 10: Full Integration Test

| Session | Focus | Subsystems Exercised | Measurements Captured |
|---------|-------|---------------------|----------------------|
| 10 | Full autonomous session | All subsystems simultaneously | End-to-end session score, all thresholds validated, calibration_complete flag |

**Session 10 checklist:**
- Conductor runs full phase progression autonomously
- Somatic palette selects and evaluates a chord
- Content delivery pipeline fires through delivery gate
- At least one fractionation cycle occurs
- Agent operates in observe mode (minimal intervention)
- On completion: `calibration_manager.mark_complete()` sets `calibration_complete = true`

---

## 4. Threshold Table — Population Defaults → Personal Values

| Threshold | Population Default | Calibration Session | Personal Value Derivation |
|-----------|-------------------|--------------------|--------------------------| 
| IAF | 10.0 Hz | Session 1 | Measured resting alpha peak frequency |
| Resting theta/alpha ratio | 0.5 | Session 1 | Measured resting ratio |
| trance_moderate | 0.65 | Session 3 | 70th percentile of personal trance_score distribution |
| trance_deep | 0.80 | Session 8 | 90th percentile of personal trance_score distribution |
| ASSR_confidence_floor | 0.30 | Session 3 | Mean ASSR confidence during confirmed entrainment |
| FAA_baseline_direction | 0 (neutral) | Session 1 | Mean FAA across 5-minute resting period |
| MAINTENANCE_entry | 0.65 (90 s) | Session 3 | Personal trance_moderate threshold |
| Fractionation hold | 30 s | Session 6 | Optimal hold from first frac response |
| SOL_typical | 15 min | Session 7 | Measured personal SOL |
| Delivery gate depth floor | 0.40 | Session 4 | Depth at which content delivery is first effective |

---

## 5. Somatic Palette Cross-Reference

The calibration protocol and somatic palette system are parallel personalization systems:

| System | What It Personalizes | Data Source | When It Stabilizes |
|--------|---------------------|-------------|-------------------|
| Calibration | EEG thresholds (IAF, trance_score ranges, ASSR floors) | Resting baselines + session metrics | After 10 sessions |
| Somatic Palette | Audio/visual chord effectiveness per entry context | Chord evaluation during MAINTENANCE | After 15–20 sessions (continuous learning) |

**Interaction:** Calibration data directly affects palette chord evaluation. The palette's failure threshold (`trance_score < 0.40 after 8 min`) should use the calibrated `trance_moderate` threshold, not the population default. After calibration completes, the palette system should query `cal.get_threshold("trance_moderate", 0.65)` for its evaluation floor.

Session 9 specifically seeds the palette with initial chord data. The exploration-exploitation formula will be in heavy exploration mode during early sessions — this is expected and correct. The palette needs 3–5 observations per chord before exploitation becomes reliable.

---

## 6. Post-Calibration

After session 10 marks `calibration_complete = true`:

1. All Conductor phase transitions use personal thresholds
2. The agent stops loading this knowledge file during idle planning
3. Session scoring uses personal ranges instead of population norms
4. The somatic palette begins exploitation-weighted chord selection
5. Reconsolidation protocols become available (depth thresholds are now trusted)
6. Training mode becomes available (complexity score baseline established)

**Recalibration triggers:**
- User reports significant life change (new medication, sleep schedule shift, major stress)
- 3+ consecutive sessions with anomalous trance_score distribution (>2σ from personal baseline)
- Hardware change (new Muse headset, different electrode positioning)

On recalibration: run sessions 1 and 3 only (baseline + depth exploration). Full 10-session protocol is not needed — the subsystem exercise sessions (4–9) only need to run once.

---

## 7. Research Citations

| Source | Contribution |
|--------|-------------|
| Nam & Choi 2020 | Lenient initial thresholds → progressive tightening (NeuroRegulation) |
| Cannard & Wahbeh (bioRxiv) | Muse 2 validated for PSD, IAF, FAA measurement |
| Lee et al. 2026 | Muse 2 alpha detection comparable to research-grade DSI-24 (Scientific Reports) |
| Ricci et al. | SEF95 inter-device bias of 0.62 Hz — justifies personal baseline approach |
| Tobar et al. 2022 | trance_score population thresholds from clinical anesthesia monitoring |
| Metzen et al. 2021 | No population-level FAA direction (N=370) — personal baseline required |
