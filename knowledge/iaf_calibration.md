# IAF Calibration Reference for Somna
*Knowledge-Base Injection — EEG Integration Module*
*v1.0 | 29 March 2026*

---

## What Is IAF and Why It Matters

Individual Alpha Frequency (IAF) is the dominant frequency of the posterior alpha rhythm during relaxed wakefulness (eyes closed). Population mean ≈ 10 Hz, but range is 7.5–12.5 Hz with significant individual variation.

IAF is a trait-like neurophysiological marker linked to information processing speed, working memory capacity, and general cognitive performance. It is stable within an individual over months to years but varies substantially between individuals.

**Why this matters for Somna:** Generic 10 Hz alpha targeting is statistically wrong for a significant fraction of users. Beyond entrainment targeting, IAF defines the boundaries between ALL adjacent frequency bands. A user with IAF = 8.5 Hz whose alpha sits at 8.5 Hz will have that activity classified as theta under default fixed-band schemes — a critical error for sleep staging, state detection, and relaxation measurement.

---

## IAF-Relative Band Boundaries

IAF personalizes frequency band definitions by anchoring all boundaries relative to the measured peak:

| Band | Lower Bound | Upper Bound | Formula |
|------|-------------|-------------|---------|
| Delta | 0.5 Hz | IAF − 6 Hz | `0.5 → IAF - 6` |
| Theta | IAF − 6 Hz | IAF − 2 Hz | `IAF - 6 → IAF - 2` |
| **Alpha** | **IAF − 2 Hz** | **IAF + 2 Hz** | **`IAF - 2 → IAF + 2`** |
| Beta | IAF + 2 Hz | 30 Hz | `IAF + 2 → 30` |
| Gamma | 30 Hz | 100 Hz | unchanged |

### Worked Example: IAF = 9.5 Hz vs. Default 10 Hz

| Band | Personalized (IAF = 9.5) | Default (10 Hz) | Shift |
|------|--------------------------|-----------------|-------|
| Delta | 0.5 – 3.5 Hz | 0.5 – 4.0 Hz | −0.5 Hz |
| Theta | 3.5 – 7.5 Hz | 4.0 – 8.0 Hz | −0.5 Hz |
| Alpha | 7.5 – 11.5 Hz | 8.0 – 12.0 Hz | −0.5 Hz |
| Beta | 11.5 – 30.0 Hz | 12.0 – 30.0 Hz | −0.5 Hz |
| Gamma | 30 – 100 Hz | 30 – 100 Hz | none |

A 0.5 Hz IAF difference shifts every sub-gamma boundary. For a user with IAF = 8.5 Hz, the shift is 1.5 Hz — activity at 7.8 Hz (alpha for them) gets classified as theta under fixed defaults. This directly impacts:

- **Edison Mode / SSILD sleep staging** — theta/alpha boundary `IAF − 2` is the N1 detection threshold
- **Entrainment targeting** — binaural beat frequencies must match the user's actual alpha
- **Agent state detection** — relaxed/drowsy/focused assessments depend on the correct band
- **GENUS baseline measurement** — alpha power before/after stimulation

---

## Detection Algorithms

### Method 1: Peak Alpha Frequency (PAF) — Spectral Peak

Compute PSD via Welch's method, find the frequency bin with maximum power in 7–13 Hz.

| Pros | Cons |
|------|------|
| Fast, simple, deterministic | Sensitive to noise |
| Direct BrainFlow support | Fails if no clear peak (~10–15% of healthy adults have flat alpha spectra) |
| Easy to validate | Biased by spectral resolution (nfft determines bin width) |

BrainFlow call: `DataFilter.get_psd_welch(data, nfft, overlap, sr, window)` returns `(amplitudes, frequencies)`. Find `argmax` in alpha range.

### Method 2: Center of Gravity (CoG) — Weighted Average Frequency

```
CoG = Σ(f_i × P_i) / Σ(P_i)   for all f_i in alpha range [7, 13] Hz
```

More robust than PAF — works even without a sharp spectral peak. Less sensitive to noise. Typically within 0.5 Hz of PAF; tends slightly lower.

Reference: Corcoran et al. 2018, Psychophysiology — open-source `restingIAF` Python package provides both PAF and CoG estimators.

### Method 3: Rapid-IAF (Sequential Bayesian Estimation)

Source: Iwama & Ushiba 2024, IEEE Trans. Neural Syst. Rehabil. Eng.

- Determines IAF from **< 26 seconds** of resting eyes-closed EEG
- **95% success rate** across N=147 participants
- IAF was more stable than task-related frequency measures (higher ICC)
- More complex to implement but superior for rapid calibration

**Recommended approach for Somna:** PAF primary, CoG fallback if no clear peak (prominence < 1.5× mean alpha power). Duration: 30 seconds eyes-closed resting EEG.

---

## IAF Stability

- Uudeberg et al. 2025 (Scientific Reports): Monthly EEG for 12 months. Alpha IAF shows excellent ICC reliability. Stable over at least one year.
- Popov et al. (Psychophysiology): Good-to-excellent test-retest reliability in young and older adults.
- IAF decreases ~0.05 Hz/year in adults — negligible over months.

**Conclusion: One calibration is sufficient long-term.** Store in `user_profile.json` and reuse. Offer optional recalibration; do not require it.

---

## BrainFlow Implementation

### Core Detection Function

```python
import numpy as np
from brainflow.data_filter import DataFilter, WindowOperations

def detect_iaf_with_confidence(eeg_data, sampling_rate=256,
                               alpha_low=7.0, alpha_high=13.0):
    """Detect IAF and return a confidence score.

    Returns:
        (iaf_hz, confidence, detail_dict)
        - iaf_hz:     float — median IAF across channels (PAF or CoG fallback per channel)
        - confidence: float 0–1 — see compute_iaf_confidence() below
        - detail:     dict — raw components for logging
    """
    # ... per-channel PAF/CoG extraction, then:
    # confidence = compute_iaf_confidence(channel_iafs, peak_powers,
    #                                     mean_alpha_power, iaf_30s, iaf_60s)
    ...

def detect_iaf(eeg_data, sampling_rate=256, alpha_low=7.0, alpha_high=13.0):
    """Thin backward-compat wrapper — returns iaf_hz only (no confidence)."""
    iaf_hz, _, _ = detect_iaf_with_confidence(eeg_data, sampling_rate,
                                               alpha_low, alpha_high)
    return iaf_hz
```

### IAF Confidence Heuristic

`compute_iaf_confidence(channel_iafs, peak_powers, mean_alpha_power, iaf_30s, iaf_60s)` returns a
float 0–1 from three weighted components:

| Component | Weight | Metric | Good → 1.0 | Bad → 0.0 |
|-----------|--------|--------|-----------|----------|
| Agreement | 0.40 | Std dev of per-channel IAFs | < 0.5 Hz spread | > 2 Hz spread |
| Stability | 0.35 | `abs(iaf_30s − iaf_60s)` | < 0.5 Hz drift | > 1.5 Hz drift |
| Prominence | 0.25 | Peak-to-band-mean ratio − 1 | 3× mean (ratio = 3.0) | 1× mean (flat) |

Prominence uses a **linear** scale from 1× to 3× band mean (not log), mapping `[1.0 → 0.0]` to
`[3.0 → 1.0]`. This is intentionally lenient for the broad synthetic alpha peak and for users with
diffuse but real alpha.

### Confidence-Gated Calibration Loop

`run_iaf_calibration(duration_s=30.0)` ticks every 5 s, writing live feedback to `live_control.json`:

```
calibration_status           "recording" | "extending" | "done"
calibration_time_remaining_s int seconds left in current window
calibration_iaf_hz           float — best candidate so far
calibration_iaf_confidence   float 0–1 — current confidence score
calibration_channel_sqi      dict — per-channel SQI
calibration_hint             str — user-facing microfeedback message
```

At the **30-second mark** (end of `original_duration`), one of three paths is taken:
- `conf >= 0.65` → **accept** immediately
- `0.35 <= conf < 0.65` → **extend** by 15 s (max_duration becomes 45 s); this only happens once
- `conf < 0.35` → **fallback** — use best candidate regardless

After any extension the loop runs to `max_duration` regardless, then accepts the best candidate.

**Threshold note for real hardware:** 0.65 is calibrated for clean real EEG. BrainFlow's synthetic
board generates broad diffuse alpha that rarely exceeds 0.55 confidence, so synthetic runs often
trigger the 15 s extension and finish at ~0.43–0.53. This is expected — the result is still valid.

### Calibration Startup Flow

```python
# In eeg_engine.py startup:
profile = _load_user_profile()  # read user_profile.json

if profile.get("iaf_hz"):
    iaf_hz     = profile["iaf_hz"]
    band_bounds = profile["iaf_band_boundaries"]
    _patch_live({"eeg_iaf_hz": iaf_hz, "eeg_band_boundaries": band_bounds})
else:
    # Trigger calibration via agent
    _patch_live({"eeg_needs_iaf_calibration": True})
    # somna_agent.py sees this flag and delivers:
    # "Close your eyes and relax for 30 seconds."
    # After 30s of EEG collection, calls detect_iaf() and saves result
```

### Saving IAF to `user_profile.json`

> **Important:** Do NOT write `user_profile.json` directly. Always use `update_profile()` from `somna_agent.py` to prevent concurrent write races between `somna_agent.py` and `somna_heartbeat.py`. The function below shows the data shape — pass these keys to `update_profile()`, not to a direct file write.

```python
def build_iaf_profile_update(iaf_hz: float,
                              iaf_confidence: float | None = None) -> dict:
    """Build the profile update dict to pass to update_profile().
    iaf_confidence is optional; omit if not available.
    """
    update = {
        "iaf_hz": round(iaf_hz, 2),
        "iaf_calibrated_at": datetime.now().isoformat(),
        "iaf_method": "paf_with_cog_fallback",
        "iaf_band_boundaries": {
            "delta": [0.5,                  round(iaf_hz - 6, 2)],
            "theta": [round(iaf_hz - 6, 2), round(iaf_hz - 2, 2)],
            "alpha": [round(iaf_hz - 2, 2), round(iaf_hz + 2, 2)],
            "beta":  [round(iaf_hz + 2, 2), 30.0],
            "gamma": [30.0,                 100.0],
        }
    }
    if iaf_confidence is not None:
        update["iaf_confidence"] = round(float(iaf_confidence), 3)
    return update

# Usage — called from control_panel.py _save_iaf_to_profile():
# profile.update(build_iaf_profile_update(iaf_hz, iaf_conf))
# Note: control_panel.py does a reload-first merge; it does NOT call update_profile()
# directly because it runs in a different process from somna_agent.py.
```

---

## `user_profile.json` Schema Addition

```json
{
  "iaf_hz": 9.7,
  "iaf_confidence": 0.712,
  "iaf_calibrated_at": "2026-04-01T14:30:00",
  "iaf_method": "paf_with_cog_fallback",
  "iaf_band_boundaries": {
    "delta": [0.5, 3.7],
    "theta": [3.7, 7.7],
    "alpha": [7.7, 11.7],
    "beta":  [11.7, 30.0],
    "gamma": [30.0, 100.0]
  }
}
```

## `live_control.json` Keys

```json
{
  "eeg_iaf_hz": 9.7,
  "eeg_needs_iaf_calibration": false,
  "eeg_band_boundaries": {
    "delta": [0.5, 3.7],
    "theta": [3.7, 7.7],
    "alpha": [7.7, 11.7],
    "beta":  [11.7, 30.0],
    "gamma": [30.0, 100.0]
  }
}
```

`eeg_band_boundaries` is written at startup so `eeg_engine.py`, `somna_agent.py`, and any future modules all use the same personalized boundaries without each re-reading the profile.

---

## How Every Mode Benefits

| Mode | Before IAF | After IAF |
|------|-----------|-----------|
| Binaural/Isochronic entrainment | Generic 10 Hz alpha target | User's actual IAF (e.g., 9.2 Hz) |
| Theta entrainment | Generic 6 Hz | `IAF − 4` Hz (center of personalized theta) |
| Edison Mode N1 detection | Fixed 8 Hz theta/alpha boundary | `IAF − 2` boundary — dramatically reduces false positives |
| SSILD sleep staging | Same fixed boundary issue | Same fix — N1 detection accuracy improves |
| Agent state detection (relaxed/drowsy) | Population-average bands | User's actual neural activity ranges |
| GENUS alpha baseline | Off-band measurement risk | Accurate pre/post alpha power comparison |

---

## Critical Implementation Notes

| Item | Detail |
|------|--------|
| Board ID | `BoardIds.MUSE_2_BOARD = 38` — NOT 22 (requires BLED112 dongle) |
| EEG channels | `get_eeg_names()` incorrectly returns Fp1/Fp2 — actual positions are AF7/AF8 |
| Sampling rate | 256 Hz (DEFAULT_PRESET) |
| Data retrieval | `get_current_board_data(n)` — non-destructive during calibration |
| `live_control.json` writes | `_patch_live()` — NOT `llm_driver.send()` |
| Profile writes | **`update_profile()` from `somna_agent.py` only** — never direct `json.dump` |
| Beat frequency key | `beat_type` — NOT `beat_mode` |
| Dev/testing | `BoardIds.SYNTHETIC_BOARD = -1` generates synthetic alpha at ~10 Hz |
| Recalibration | Offer via control panel button; agent can suggest if alpha patterns seem anomalous |

---

## References

1. Iwama S, Ushiba J (2024). Rapid-IAF: Rapid Identification of Individual Alpha Frequency in EEG Data Using Sequential Bayesian Estimation. *IEEE Trans. Neural Syst. Rehabil. Eng.*, 32, 915–922.
2. Corcoran AW, Alday PM, Schlesewsky M, Bornkessel-Schlesewsky I (2018). Toward a reliable, automated method of individual alpha frequency (IAF) quantification. *Psychophysiology*, 55(7), e13064.
3. Uudeberg T et al. (2025). Individual stability of single-channel EEG measures over one year in healthy adults. *Scientific Reports*, 15, 28426.
4. Popov T et al. (2023). Test-retest reliability of resting-state EEG in young and older adults. *Psychophysiology*, 60(4), e14268.
