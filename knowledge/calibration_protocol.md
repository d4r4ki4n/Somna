# Calibration & First-10-Sessions Protocol
**Author:** Research  
**Date:** 3 April 2026  
**Status:** Specification — Bible Ch.2 Â§Calibration

---

## 1. The Problem: Population Defaults Are Not Your Neurophysiology

Every threshold currently hardcoded across Docs 17–25 is a literature-derived population estimate, not a measurement from the actual user's brain. The following thresholds are in active use with no individual characterization:

| Threshold | Source | Problem |
|-----------|--------|---------|
| `trance_score > 0.6` (Bible Ch.2 Â§SEF95, SEF95-based) | Clinical anesthesia monitoring literature (Tobar et al. 2022) | Population estimate |
| `ASSR confidence > 0.3` (Bible Ch.2 Â§ASSR) | Arbitrary starting point | No individual characterization |
| `FAA > 0` for affirmation gating (Bible Ch.2 Â§FAA) | Metzen et al. 2021 (N=370) found no population-level frontal alpha asymmetry | No "normal" direction exists |
| `IAF ≈ 10 Hz` (Bible Ch.3 Â§Frequency-Leading) | Population mean | Individual range is 8–13 Hz |
| `SEF95 < 10 Hz = deep trance` (Bible Ch.2 Â§SEF95) | ICU sedation monitoring, not hypnotic entrainment | Wrong domain |
| Session scoring ranges (Bible Ch.5 Â§Scoring) | Population norms | Not personal performance range |

Muse 2 is validated for PSD, IAF, and FAA measurement (Cannard & Wahbeh, bioRxiv) and alpha detection comparable to research-grade DSI-24 (Lee et al. 2026, Scientific Reports), but absolute values will differ from clinical EEG literature due to electrode placement, impedance characteristics, and 4-channel limitation. Ricci et al. found SEF95 bias of 0.62 Hz between clinical devices with 95% limits of agreement spanning nearly 10 Hz — Muse 2 divergence from literature values is expected and acceptable as long as personal baselines are established.

**The solution:** 10 structured sessions that progressively exercise each subsystem, capture personal neurophysiological baselines, and replace every population default with individually-measured values.

Reference: Nam & Choi 2020 (*NeuroRegulation*): initially setting thresholds for easy compensation (high reward frequency) was more effective than hard compensation — so the protocol starts with deliberately lenient thresholds and tightens progressively.

---

## 2. Architecture: `calibration_manager.py`

New module. Purpose: manage the first-10-sessions calibration protocol, persist results to `somna.db`, and expose a threshold lookup API that the conductor and session scorer query to replace population defaults with personal values.

### Integration Pattern

```python
# Before:
if trance_score > 0.65:

# After:
if trance_score > cal.get_threshold("trance_moderate", 0.65):
```

The fallback is always the current hardcoded value — zero regression risk until personal data exists.

### Integration Points

**`conductor.py`:** At startup, check `calibration_manager.calibration_complete`. If not complete, call `get_session_protocol()` to determine which phases are permitted via `_can_transition_to()`. All threshold lookups use `get_threshold(metric, population_fallback)`.

**`session_scorer.py`:** After calibration complete, scoring scales each metric to personal 0–1 range. `get_threshold('sef95_awake')` provides the ceiling, `get_threshold('sef95_deep')` provides the floor for depth scoring.

**`somna_agent.py`:** Agent reads `calibration_manager.current_session_number` and `calibration_manager.get_session_protocol()`. Adjusts behavior per session phase. After each session, agent runs `post_session_queries` defined in the protocol.

---

## 3. Database Schema

### `calibration_baselines`
One row per measurement window. Stores per-channel SQI and per-metric band powers for every baseline capture.

Fields: `session_number`, `metric`, `channel`, `condition` (`eyes_closed`/`eyes_open`/`entrainment`/`trance`), `value`, `sd`, `n_samples`, `sqi_mean`, `timestamp`. UNIQUE on `(session_number, metric, channel, condition)`.

### `calibration_sessions`
One row per calibration session. Tracks phase, timing, maximum conductor phase reached, and the JSON blob of thresholds derived at session end.

### `calibration_thresholds`
One row per metric (PRIMARY KEY). Stores derived personal threshold with derivation method and confidence level (`provisional`/`moderate`/`final`).

### `calibration_assr_curve`
Append-only. Records ASSR strength at each frequency tested during entrainment sessions, building a personal frequency-response curve.

---

## 4. Session Protocol — The 10 Sessions

### Phase A: Hardware Verification & Resting Baselines (Sessions 1–2)

**Session 1 — Hardware Verification & Eyes-Closed Baseline (15 min)**

Protocol sequence:
1. **SQI hardware check (60 s):** Log per-channel SQI. Target: all channels achieve FULL tier (SQI ≥ 0.7) for ≥ 30 of 60 seconds. Agent provides only fit guidance via `_say()`.
2. **Eyes-closed baseline 1 (3 min):** Capture full PSD from 0.5 Hz upward. Compute and log: IAF (peak alpha 8–13 Hz), SEF95, band powers (delta 0.5–4, theta 4–8, alpha 8–13, beta 13–30, gamma 30–45), FAA = ln(alpha_AF8) − ln(alpha_AF7), spectral slope (1/f exponent via log-log PSD regression). Agent cue: *"Let your weight settle. Breathe normally."* No further speech during measurement.
3. **Eyes-open baseline (3 min):** Same metrics. Agent cue: *"Open your eyes. Rest your gaze."* The magnitude of alpha suppression relative to eyes-closed is itself a useful individual marker.
4. **Eyes-closed baseline 2 (3 min):** Repeat for within-session stability. Flag if IAF differs > 0.5 Hz between windows.
5. **Spectral slope computation:** Linear regression of log(PSD) vs log(freq) over 2–40 Hz excluding alpha peak (8–13 Hz). The exponent (negative) is the 1/f slope — shallower (less negative) in trance states.
6. **Log all metrics to `calibration_baselines`.**

**Session 2 — Repeat baseline for reliability (15 min):** Identical protocol. Compare IAF between Session 1 and 2. Compute alpha reactivity ratio: `eyes_closed_alpha / eyes_open_alpha`. After Session 2, derive provisional IAF, SEF95_awake, FAA_resting, and spectral_slope_awake thresholds.

### Phase B: Subsystem Characterization (Sessions 3–6)

**Sessions 3–4 — ASSR Frequency Sweep:** Allow through INDUCTION phase. Log ASSR strength at each frequency from IAF down to 4 Hz as conductor steps down. Build personal `calibration_assr_curve`. After Session 4, derive `assr_transition` (p25 of curve strengths) and `assr_strong` (p60).

**Sessions 5–6 — Full Induction + Deepening:** Allow through MAINTENANCE. Affirmations enabled. No fractionation yet. After Session 6, derive `sef95_light`, `sef95_moderate`, `sef95_deep` from session_metrics percentiles. Derive trance_score thresholds proportionally from personal SEF95 range.

### Phase C: Integration (Sessions 7–8)

Allow through full FRACTIONATION cycle. Adaptive frequency leading enabled. After Session 8, all thresholds should be at `moderate` confidence.

### Phase D: Closed-Loop (Sessions 9–10)

Full autonomous operation. All adaptive features active. Final thresholds derived at `final` confidence.

---

## 5. Threshold Derivation Methods

| Metric | Source data | Method |
|--------|-------------|--------|
| `iaf` | `calibration_baselines`, `eyes_closed` | Mean across all EC windows |
| `sef95_awake` | `calibration_baselines`, `eyes_closed` | Mean of high-SQI (≥ 0.5) windows |
| `faa_resting` | `calibration_baselines`, `eyes_closed` | Mean |
| `faa_approach` | `calibration_baselines` | Mean + 0.1 SD |
| `assr_transition` | `calibration_assr_curve` | p25 of strength distribution |
| `assr_strong` | `calibration_assr_curve` | p60 of strength distribution |
| `sef95_light` | `session_metrics.depth_mean_sef95` | p75 |
| `sef95_moderate` | `session_metrics.depth_mean_sef95` | Median |
| `sef95_deep` | `session_metrics.depth_min_sef95` | p10 |

---

## 6. Phase Unlock Schedule

| Sessions | Calibration Phase | Conductor Phases Permitted |
|----------|-------------------|---------------------------|
| 1–2 | `baseline` | CALIBRATION only |
| 3–4 | `subsystem` | + INDUCTION |
| 5–6 | `subsystem` (extended) | + DEEPENING, MAINTENANCE |
| 7–8 | `integration` | + full FRACTIONATION cycle |
| 9–10 | `closed_loop` | All phases |
| 11+ | `complete` | All phases (personal thresholds active) |

---

## 7. Post-Session Analysis Protocol

After each calibration session, the agent must run specific queries:

**Sessions 1–2:** No `query_session_performance` — read `calibration_baselines` directly. Report: IAF, SEF95 resting, FAA resting, alpha reactivity ratio, per-channel SQI summary.

**Sessions 3–4:** `query_session_performance(last_n=1, metrics=['sqi_mean', 'assr_strength'])`. Also report from `calibration_assr_curve`: ASSR at IAF, frequency descent range, strongest and weakest entrainment frequencies.

**Sessions 5–6:** Add `depth_min_sef95`, `depth_mean_sef95`, `assr_mean`, `receptivity_approach_pct`. Report SEF95 range during trance, alpha-theta crossing detection, FAA distribution.

**Sessions 7–10:** Full metrics + trend query over completed calibration sessions. Report adaptive leading descent range, fractionation cycle count, threshold updates applied.

---

## 8. Recalibration Triggers

- **Hardware change** (e.g. Muse 2 → Muse S): MANDATORY full recalibration from Session 1.
- **Metric drift:** 20-session rolling mean drifts > 2 SD from calibration value for any tracked metric.
- **Elapsed time:** 90 days since last calibration completion.
- **Manual request:** User can force recalibration at any time.

Previous calibration data is archived (not deleted) for longitudinal comparison.

---

## 9. Open Questions

- **FAA integration with conductor phase transitions:** What FAA thresholds should gate the DEEPENING vs MAINTENANCE decision? Session 6 will generate the data to answer this.
- **Spectral slope computation:** The linear regression on log-log PSD (1/f exponent extraction) is a `numpy.polyfit` call on `log(freqs)` vs `log(psd)`, but the frequency range for the fit matters (typically 2–40 Hz, excluding the alpha peak).
- **Fractionation timing calibration:** Session 8 will generate cycle data, but optimal emerge hold duration and redrop readiness criteria need analysis after real EEG traces are available.

---

## Key Insight

Once implemented, every session from #1 onward generates data that makes every subsequent session more precisely tuned to the user's neurophysiology. Session 1 runs on population defaults. Session 11 runs on a complete personal neurophysiological profile. That's the arc.
