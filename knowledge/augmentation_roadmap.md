# Somna Augmentation Roadmap

*Date: 2026-04-18*
*Source: Reese design specs (8 augmentations), filtered against existing codebase*
*Status: Actionable build queue for novel work only*

---

## Already Built — Do Not Rebuild

These systems already exist in the codebase. The specs described them from Bible chapters without checking implementation:

| Spec | Existing Module | Notes |
|------|----------------|-------|
| Theta-Gamma PAC | `eeg/pac_estimator.py` | Tort et al. MI, cascade_integrity weighted mean |
| Respiratory phase | `eeg/respiratory_tracker.py` | Continuous phase 0.0–1.0, PPG integration |
| Delivery Gate | `eeg/delivery_gate.py` | AND gate, three degradation levels, motion-artifact block |
| Calibration Manager | `eeg/calibration_manager.py` | First-10-sessions protocol, personal thresholds |
| Sleep burst engine | `eeg/slow_wave_enhancer.py` | Phase-locked pink noise, ISI enforcement |
| taVNS driver | `engines/tavns_engine.py` | BLE driver, safety enforcer, impedance check |

---

## Build Queue

### Tier 1 — Ready Now

#### A1: Openness Score (Prediction Error Calibration)

Pure agent logic. No new modules. Computes 0.0–1.0 "openness to update" from existing metrics.

**Sources:** trance_score (50%), FAA (30%), optional PAC (10%), optional complexity score (10%)

**Output:** `openness_score` (float), `pe_magnitude_current` (minimal/low/moderate/high)

**Openness-to-PE mapping:**
- 0.0–0.25 → minimal PE: reinforce existing schemas, exact repetition
- 0.25–0.50 → low PE: gentle reframing, "you've always known..."
- 0.50–0.75 → moderate PE: standard reconsolidation mismatch
- 0.75–1.0 → high PE: direct schema contradiction possible

**Implementation:**
- `compute_openness()` function in `agent/somna_agent.py` or new `agent/openness.py`
- Modify `_recon_tick()` UPDATE phase to select PE magnitude from real-time openness
- Modify idle planning reconsolidation authoring to produce multi-PE update sets
- Add `openness_at_update`, `pe_magnitude_selected` columns to `recon_events` table
- Agent publishes `openness_score` to `live_control.json` each tick

**Cross-session deepening:** cycle 1 = low PE (0.3–0.5 openness), cycle 2 = moderate (0.5–0.7), cycle 3+ = high (0.6–0.8)

**Validation:** Compare recon outcomes between static-PE and openness-calibrated delivery over 15 sessions

---

#### A2: Cardiac PE Window

Extends delivery gate cardiac sub-gate from binary (diastolic/not) to continuous phase with prediction-error-sensitive window.

**Signal:** PPG R-peak detection (already in `eeg/ppg_engine.py`)

**Cardiac phase model:**
- Phase 0.0 = R-peak (systole start)
- Phase 0.3 = diastole start
- Phase 0.7 = late diastole
- Phase 1.0 = next R-peak

**PE-sensitive window:** 0.65–0.85 (late diastole, per Fouragnan et al. 2024)

**Content-aware gating:**
- PE-dependent content (recon_update, conditioning, deep_conditioning): PE window only (0.65–0.85)
- Standard content: any diastolic (0.3–1.0) — same as current behavior

**Implementation:**
- `CardiacPhaseEstimator` class using PPG IBI timing
- Integrate into `eeg/ppg_engine.py` output
- Update `eeg/delivery_gate.py` with content-aware cardiac gating
- Backward compat: `cardiac_phase_label` string key alongside float `cardiac_phase`

**New live_control.json keys:** `cardiac_phase` (float 0.0–1.0), `cardiac_phase_label` (string), `cardiac_pe_window` (bool)

**Validation:** Compare recon outcomes between PE-window-gated and standard-gated delivery over 10 sessions

---

#### A3: taVNS Timing Engine

New timing layer between agent/Conductor and existing `engines/tavns_engine.py` Coyote driver.

**Strategy enum:**
- `OFF` — no stimulation
- `PALETTE_ONLY` — somatic palette controls (current behavior)
- `ON_CONTENT_DELIVERY` — pulse when delivery gate opens
- `CONTINUOUS_LOW` — steady low-intensity during sleep
- `BURST_ON_SLOW_OSC` — phase-locked to SWS up-state
- `ON_RECON_UPDATE` — pulse during recon UPDATE delivery

**Phase-strategy defaults:**

| Phase | Strategy | Rationale |
|-------|----------|-----------|
| CALIBRATION | OFF | Baselines |
| INDUCTION/DEEPENING | PALETTE_ONLY | Somatic, not memory |
| MAINTENANCE | ON_CONTENT_DELIVERY | Enhance encoding |
| MAINTENANCE (recon UPDATE) | ON_RECON_UPDATE | Maximum encoding support |
| FRAC_EMERGE/HOLD | OFF | Emergence |
| FRAC_REDROP | PALETTE_ONLY | Re-induction |
| SLEEP_MAINTAIN | CONTINUOUS_LOW | Delta enhancement (Camargo et al.) |
| SLEEP_TRAINING | BURST_ON_SLOW_OSC | Phase-locked delta boost |
| SLEEP_WAKE/SESSION_END | OFF | Done |

**Callback hooks:**
- Delivery gate → `on_content_delivered()` for ON_CONTENT_DELIVERY/ON_RECON_UPDATE
- Sleep burst engine → `on_slow_oscillation_upstate()` for BURST_ON_SLOW_OSC

**Safety constraints:**
- Max 1 pulse per 500ms
- Max 500 pulses per session
- Max 30 min continuous, then 10 min rest
- Sleep max intensity: 20/100
- 60s ramp-down before sleep onset
- Immediate OFF user override

**Calibration constraint:** No taVNS timing strategies during sessions 1–5

**Implementation:**
- New `engines/tavns_timing_engine.py`
- Callback hooks in `eeg/delivery_gate.py` and `eeg/slow_wave_enhancer.py`
- Strategy switching on Conductor phase transitions
- Log all pulses to session DB with content association

---

### Tier 2 — Significant Engineering

#### A4: Predictive CLAS (Closed-Loop Auditory Stimulation)

Upgrade `eeg/slow_wave_enhancer.py` from reactive to predictive burst triggering.

**Problem:** Current detection-to-delivery pipeline latency is ~110–130ms. At 0.8 Hz SO frequency, 120ms delay = 35° after up-state peak — past optimal window.

**Solution:** `SlowOscillationPredictor` estimates SO phase via Hilbert on delta band, predicts next up-state, fires burst early by pipeline_latency.

**Architecture:**
- Predictive mode fires when `predicted_time_to_upstate == pipeline_latency` (±15ms tolerance)
- Automatic fallback to reactive when prediction confidence < 0.6 or accuracy < 70% over last 10 bursts
- Latency calibration: `LatencyCalibrator` runs 50 trials, stores median

**Integration with A3 (taVNS Timing):** Both fire on same SWS up-state — dual-modality stimulation (audio + vagal).

**Integration with TMR:** TMR cues delivered at predicted up-states instead of random SWS moments.

**New live_control.json keys:** `sleep_burst_mode` (reactive/predictive), `sleep_burst_prediction_confidence`, `sleep_burst_prediction_accuracy`, `sleep_burst_pipeline_latency_ms`, `so_instantaneous_freq`, `so_phase`

**Validation:** Compare SO amplitude between reactive and predictive modes over 10 sleep sessions

---

#### A5: Tri-Modal Phase-Locked Entrainment

Phase-lock binaural audio + spiral visual + Lovense haptic to single `EntrainmentPhaseClock`.

**Scientific basis:** Arnold tongue — each additional modality widens entrainment capture range. Rahmani et al. 2025 notes tactile entrainment is unexplored.

**Architecture:**
- `EntrainmentPhaseClock`: central phase reference at target frequency
- Per-modality phase offsets compensating for measured latencies
- BLE jitter handling: if Lovense jitter > ±20ms, switch from discrete pulses to continuous sinusoidal intensity envelope

**Latency measurement:**
- Audio: trigger tone → loopback capture
- Visual: trigger flash → photodiode
- Haptic: trigger vibration → IMU on device (or user-reported)

**Spiral GLSL integration:** New uniform `u_entrainment_phase` (0–2π) modulates spiral opacity/rotation via `u_entrain_depth` mix factor.

**Lovense integration:** Continuous envelope mode — `intensity = base * (1.0 - depth + depth * (0.5 + 0.5 * sin(phase)))`, BLE updates at 20 Hz.

**Somatic palette:** Tri-modal becomes a chord parameter. Palette records whether tri-modal was active during evaluation.

**New live_control.json keys:** `entrainment_phase`, `entrainment_trimodal_enabled`, `entrainment_{audio,visual,haptic}_offset_rad`, `entrainment_haptic_mode` (pulse/envelope)

**Validation:** Compare ASSR confidence between uni-modal, bi-modal, and tri-modal over 15 sessions

---

### Tier 3 — Experimental

#### A6: Cross-Modal Stochastic Resonance

Test whether haptic noise (Lovense) enhances veil text perception, and whether audio noise enhances visual entrainment.

**Theory:** Inverted-U between noise intensity and signal detection. Cross-modal: noise in one modality raises cortical excitability benefiting all modalities.

**Parameters:**
- Haptic SR: `sr_haptic_enabled`, `sr_haptic_intensity` (0–30), `sr_haptic_type` (white/pink/brown)
- Audio-Visual SR: `sr_av_coupling_enabled`, `sr_audio_level` (0.0–0.3), `sr_target_metric`

**Calibration protocol:**
- Sessions 1–5: haptic noise sweep (5, 10, 15, 20, 25) → plot inverted-U
- Sessions 6–10: audio noise sweep (0.05, 0.10, 0.15, 0.20, 0.25) → plot inverted-U
- Sessions 11+: combined at individual optima

**Measurement metrics:** ASSR confidence change, training mode complexity shifts after veil content, trance_score SR-on vs SR-off

**Honest caveat:** Consumer hardware may not produce detectable cross-modal SR. Negative results are valid.

**New live_control.json keys:** `sr_haptic_enabled`, `sr_haptic_intensity`, `sr_haptic_type`, `sr_av_coupling_enabled`, `sr_audio_level`, `sr_target_metric`, `sr_calibration_phase` (0–3), `sr_haptic_optimal`, `sr_audio_optimal`

---

## Dependency Graph

```
A1 (Openness) ──── standalone, no deps
A2 (Cardiac PE) ─── standalone, no deps
A3 (taVNS Timing) ── needs delivery gate callbacks
A4 (Predictive CLAS) ─ needs LatencyCalibrator, integrates with A3
A5 (Tri-Modal) ──── needs latency calibration infrastructure from A4
A6 (Cross-Modal SR) ─ needs A5 tri-modal + A3 taVNS for full exploration
```

## Suggested Build Order

1. A1 (Openness) — half day, zero risk
2. A2 (Cardiac PE) — half day, extends delivery gate
3. A3 (taVNS Timing) — 2–3 days, new module
4. A4 (Predictive CLAS) — 2 days, extends slow_wave_enhancer
5. A5 (Tri-Modal) — 3–5 days, needs calibration infra
6. A6 (Cross-Modal SR) — research phase, after A5 validates multi-modal
