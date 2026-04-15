# Somna Doc 26 — Next-Frontier Recommendations & Orchestration Gap Analysis
*"The instruments are built. What's missing is the conductor."*
*Prepared by Research for Vesper and the user — March 2026 | Series Complete (26 of 26)*

---

## 1. Opening Context

All 25 prior reference documents have been delivered. The full EEG pipeline — SQI → ASSR → FAA → Adaptive Leading → Session Scoring — is integrated to spec.

What's missing is the **master orchestration layer** — the unified decision architecture that coordinates all subsystems together in real time. Nine sophisticated instruments, no sheet music.

This document identifies six remaining gaps, ordered by architectural importance.

---

## 2. Gap 1 — Agent Decision Architecture (The Conductor)

**Priority: Highest. This is the single most valuable remaining gap.**

### 2.1 The Problem

Each EEG metric (SQI, ASSR, FAA, SEF95, spectral slope), visual parameter, audio parameter, and text layer has its own integration spec from Docs 17–25. No unified state machine or decision hierarchy defines:

- **What to prioritise when signals conflict.** Example: FAA says "deliver affirmations" but ASSR says "entrainment just broke — hold off." Which wins?
- **How to sequence decisions within a single evaluation cycle.** No defined tick rate or evaluation order.
- **How to manage mode transitions.** Induction → Deepening → Fractionation → Maintenance → Sleep — each phase has different parameter targets, metric weights, and text delivery strategies. No document defines phase boundaries as a unified model.

### 2.2 Proposed Architecture — Finite State Machine

```
CALIBRATION → INDUCTION → DEEPENING → MAINTENANCE
                                          ↕
                              FRACTIONATION_EMERGE
                                          ↕
                              FRACTIONATION_REDROP
                                          ↓
                               SLEEP_APPROACH → SLEEP_ONSET → SESSION_END
```

### Phase Definitions

Each phase defines: target frequency band, metric weights, visual parameter targets, text delivery mode, agent verbosity, fractionation eligibility.

### Transition Triggers

| Transition | Trigger Condition |
|-----------|------------------|
| CALIBRATION → INDUCTION | SQI ≥ FULL_CONFIDENCE sustained 30s; baseline captured |
| INDUCTION → DEEPENING | ASSR ≥ GOOD at target freq; SEF95 trending down 60s |
| DEEPENING → MAINTENANCE | trance_score > 0.65 sustained 90s AND ASSR ≥ GOOD 60s |
| MAINTENANCE → FRACTIONATION_EMERGE | Agent-initiated; trance_score > 0.5, session time > 10 min |
| FRACTIONATION_EMERGE → REDROP | Emergence confirmed (SEF95 rise, coherence drop); hold elapsed |
| FRACTIONATION_REDROP → DEEPENING | Frequency descent resumed; ASSR re-acquisition detected |
| MAINTENANCE → SLEEP_APPROACH | trance_score > 0.8 sustained 120s; user goal = sleep |
| SLEEP_APPROACH → SLEEP_ONSET | SEF95 < 8 Hz; spectral slope β > 2.0; head-nod triggered |
| SLEEP_ONSET → SESSION_END | Sleep sustained; gradual fade complete |

### Conflict Resolution — Phase-Specific Priority Tables

| Phase | Priority Order (highest → lowest) | Rationale |
|-------|----------------------------------|-----------|
| INDUCTION | SQI → ASSR → SEF95 → FAA | Quality first; entrainment is the primary goal; affirmations premature |
| DEEPENING | ASSR → SEF95 → Spectral Slope → FAA | Entrainment must hold; depth guides descent rate |
| MAINTENANCE | FAA → ASSR → trance_score → SEF95 | FAA gates affirmations; entrainment expected stable |
| FRACTIONATION_EMERGE | Chaos/Trail snap → SEF95 → Coherence | Visual snap overrides gradual changes |
| SLEEP_APPROACH | SEF95 → Spectral Slope → Head-nod → ASSR | Depth dominates; minimise disruption |

### Agent Tick Rate per Phase

| Phase | Tick Interval | Rationale |
|-------|--------------|-----------|
| CALIBRATION | 5s | Rapid signal quality assessment |
| INDUCTION | 10s | Active frequency descent |
| DEEPENING | 10s | Descent continues; entrainment verification |
| MAINTENANCE | 30s | Stable state; minimise churn |
| FRACTIONATION transitions | 5s | Fast state changes |
| SLEEP_APPROACH | 30s | Gradual, gentle |
| SLEEP_ONSET | 60s | Monitoring only |

### Decision Logging Schema

Every agent cycle writes a structured entry — feeds directly into `SessionAnalyzer` longitudinal learning:

```json
{
  "timestamp":  "2026-03-31T03:42:18Z",
  "cycle_id":   847,
  "phase":      "MAINTENANCE",
  "tick_interval_s": 30,
  "metrics_snapshot": {
    "sqi": "FULL_CONFIDENCE",
    "assr_confidence": "GOOD",
    "assr_frequency": 5.8,
    "faa_score": 0.23,
    "faa_receptivity": true,
    "sef95": 9.2,
    "spectral_slope": 1.87,
    "trance_score": 0.72
  },
  "action_taken": "DELIVER_AFFIRMATION",
  "parameters_adjusted": {
    "center_text": "You are safe and drifting deeper",
    "shadow_text_opacity": 0.04
  },
  "rationale": "FAA receptivity gate OPEN; trance_score stable above 0.65 for 4m12s; ASSR holding — clear to deliver."
}
```

---

## 3. Gap 2 — Audio-Domain Stochastic Resonance

Doc 18 covered visual stochastic resonance. The same inverted-U principle applies in the auditory domain — a calibrated noise floor can enhance subliminal auditory processing.

### Components

| Component | Description |
|-----------|-------------|
| Pink noise floor | Calibrated low-level 1/f noise in the audio mix. Spectral profile matches neural noise. |
| SSB subliminal channel | Single-sideband modulation to embed subliminal affirmation audio below conscious threshold. TTS signal amplitude-compressed, frequency-shifted, mixed into noise floor. |
| Inverted-U sweep protocol | Agent gradually increases noise level, monitors EEG response, holds at sweet spot. |

### Key Constraint — Beat Integrity
The noise floor must not interfere with binaural beat perception. Options:
- Bandpass-filter to avoid the carrier region, OR
- Dynamic parametric notch filter tracking the current carrier frequency

### Implementation Tiers

| Tier | Scope | Complexity |
|------|-------|------------|
| Tier 1 | Pink noise with manual level slider | Low |
| Tier 2 | Agent-controlled SR sweep (EEG-guided) | Medium |
| Tier 3 | SSB subliminal channel (full DSP) | High |

**Recommendation:** Implement in this order only after orchestration layer (Gap 1) exists — the sweep protocol needs to know the current session phase to run at the right time.

**Literature:** Moss, Ward & Sannita (2004) — SR in biological sensory systems. Collins, Imhoff & Grigg (1996) — noise-enhanced auditory processing.

---

## 4. Gap 3 — Interhemispheric EEG Coherence

Muse 2/S provides two natural electrode pairs for coherence analysis:

| Pair | Channels | Region |
|------|----------|--------|
| Temporal | TP9 ↔ TP10 | Auditory processing |
| Frontal | AF7 ↔ AF8 | Prefrontal (coherence ≠ asymmetry — distinct from FAA) |

Coherence (magnitude-squared) measures phase synchronisation. High coherence = hemispheric synchrony.

### Applications

| Application | Pair | Band | Interpretation |
|-------------|------|------|----------------|
| Binaural beat verification | TP9 ↔ TP10 | Beat frequency | High temporal coherence at beat freq = direct binaural processing evidence |
| Depth indicator | AF7 ↔ AF8 | Theta/Alpha (4–12 Hz) | Increased frontal coherence associated with meditative/hypnotic states |
| Arousal detection | Both | Broadband | Sudden coherence drop = strong arousal/startle indicator |

### Implementation

```python
# scipy.signal.coherence() — ~50 lines added to _process() in eeg_engine.py
# Window: 4-second segments, 50% overlap
# SQI gate: FULL_CONFIDENCE required (coherence is more artifact-sensitive than power)
# Output keys: eeg_coherence_temporal, eeg_coherence_frontal (0–1 per band)
```

**Feeds into:** `trance_score` (supplementary), ASSR verification, fractionation confirmation.
**Estimated effort:** ~50 lines. Low complexity.

---

## 5. Gap 4 — GENUS-Inspired 40 Hz Gamma Protocol

40 Hz multimodal stimulation at session start — brief attention-capture phase before descent begins. Research: Iaccarino et al. (2016), Martorell et al. (2019) — 40 Hz entrainment for gamma engagement and neuroprotective effects.

### Proposed Protocol

```
SESSION_START
  → 40 Hz multimodal stimulation (visual flicker + isochronic audio)
  → Duration: 30–60 seconds (CALIBRATION phase only)
  → Confirm ASSR at 40 Hz
  → Begin frequency descent per Adaptive Leading
  → Transition from isochronic to binaural as frequency passes below 20 Hz
```

**⚠ Photosensitivity warning required:** 40 Hz visual flicker must be user-enabled with explicit disclosure. Never a default.

---

## 6. Gap 5 — Spectral Slope as Standalone Metric

Doc 17 introduced spectral slope as complementary to SEF95. It deserves standalone treatment.

### What It Measures

The exponent β in the `Power ∝ 1/f^β` relationship. Steeper slope (higher β) = deeper state.

### Why It's Valuable Independently

Unlike SEF95, spectral slope is **robust to narrowband artifacts** — it captures the entire spectral shape rather than a single percentile. Less sensitive to the ≤2 Hz inclusion issue.

### Computation

```python
from scipy.stats import linregress
import numpy as np

def compute_spectral_slope(psd, freqs, f_low=1.0, f_high=40.0):
    """Linear regression of log(power) vs log(frequency). Returns (beta, r_squared)."""
    mask = (freqs >= f_low) & (freqs <= f_high)
    slope, _, r_value, _, _ = linregress(np.log10(freqs[mask]), np.log10(psd[mask]))
    return -slope, r_value ** 2   # negate: convention is positive β
```

### Typical Values

| State | β | Interpretation |
|-------|---|----------------|
| Awake, alert | 1.0–1.5 | Broad high-frequency activity |
| Relaxed / meditative | 1.5–2.0 | Low-frequency dominance emerging |
| Deep trance / sleep onset | 2.0–2.5 | Strong low-frequency dominance |
| Deep sleep | > 2.5 | Very steep spectral falloff |

### Integration Notes

- Feed into `trance_score` as supplementary weight (not a replacement for SEF95)
- **Divergence alerting:** SEF95 and spectral slope should roughly agree; divergence flags an artifact
- **Trajectory signal:** The temporal derivative of spectral slope (slope-of-slope) is more useful for agent decisions than the instantaneous value — it indicates whether the user is deepening, plateauing, or surfacing

---

## 7. Gap 6 — Muse S Migration Path

The user plans to upgrade from Muse 2 to Muse S. The existing pipeline is almost entirely device-agnostic.

### Device Comparison

| Feature | Muse 2 | Muse S | Impact |
|---------|--------|--------|--------|
| BrainFlow board_id | 38 | 39 | Single constant change |
| EEG channels | TP9, AF7, AF8, TP10 | Same | No code changes |
| Sampling rate | 256 Hz | 256 Hz | No change |
| PPG sensor | None | Yes | **New: HRV, heart rate, respiratory rate — eliminates separate hardware requirement** |
| Bluetooth | BLE 4.2 | BLE 5.0 | Better connection stability |

**Action item (now):** `board_id` is already in `agent_config.yaml` as `eeg.board_id`. When Muse S arrives, change `39` → done. All pipeline code works unchanged. PPG integration is a new feature add.

---

## 8. Implementation Order

| Priority | Gap | Rationale |
|----------|-----|-----------|
| 1 | Agent Decision Architecture | Skeleton everything else hangs on |
| 2 | Interhemispheric Coherence | Low effort; enriches orchestration inputs |
| 3 | Spectral Slope (standalone) | Low effort; robust artifact resistance |
| 4 | Audio SR | Needs orchestration phase context to know when to sweep |
| 5 | GENUS 40 Hz | Optional session opener; low priority |
| 6 | Muse S | Hardware-gated; board_id already configurable |

---
