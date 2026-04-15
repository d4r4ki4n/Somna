# HRV Coherence Breathing Guide Reference for Somna
*Planning Document — PPG-Based HRV Biofeedback Module*
*v1.0 | 29 March 2026*

> **STATUS: BLOCKED — Implementation pending PPG hardware verification on real Muse 2.**
> The BrainFlow `config_board()` command to enable PPG on Muse 2 is uncertain. See Section 3 for test procedure. Do not implement the HRV module until this is resolved on real hardware.

---

## 1. HRV Coherence Science

### What Is HRV

Heart Rate Variability = fluctuations in the time intervals between successive heartbeats (inter-beat intervals, IBI). A healthy heart is NOT a metronome — it exhibits complex non-linear oscillations. Higher HRV indicates better autonomic flexibility and resilience.

Key metrics:

| Metric | Definition | Normal Resting Range |
|--------|-----------|----------------------|
| RMSSD | Root mean square of successive IBI differences — primary parasympathetic (vagal) metric | 20–80 ms |
| SDNN | Standard deviation of IBI — reflects overall HRV | 50–100 ms |
| LF/HF ratio | Low-freq (0.04–0.15 Hz) / high-freq (0.15–0.4 Hz) power ratio — sympathovagal balance | Context-dependent |
| Coherence score | Power at dominant frequency / total power in 0.04–0.26 Hz | 0–1 (higher = better) |

### HRV Coherence

Coherence = a state where heart rhythm becomes highly ordered at a single dominant frequency.

```
coherence_score = power_at_dominant_freq / total_power_in_0.04–0.26 Hz range
```

High coherence (> 0.5) = synchronized, efficient autonomic regulation. Associated with improved emotional stability, cognitive function, reduced stress, enhanced parasympathetic tone.

### Resonance Frequency

The cardiovascular system has a natural resonance frequency (~0.1 Hz / 6 breaths/min for most adults) but with significant individual variation. Breathing at one's personal resonance frequency produces the largest HRV amplitude oscillations, maximizing baroreflex sensitivity.

From the **largest HRV biofeedback study ever conducted** — Balaji et al. 2025 (Scientific Reports, 1.8 million sessions):
- Most common coherence frequency: **0.10 Hz (~6 breaths/min)**
- Personal resonance frequency is extremely stable across sessions (**SD < 0.012 Hz**)
- Positive emotions correlated with higher coherence scores
- Many users' highest coherence in 0.04–0.10 Hz range (deeper, slower breathing)

### HRV-EEG Coupling — The Somna Connection

- **Demin & Poskotinova 2025 (Life):** HRV biofeedback increased alpha EEG activity across all brain regions. Direct HRV → EEG coupling — coherent breathing measurably shifts brain state toward alpha dominance.
- **Pardo-Rodriguez et al. 2025 (Frontiers):** Conscious breathing at resonance frequencies enhances bidirectional cortical-autonomic coupling. Gamma band shows strongest causal effects on autonomic regulation.
- **Saito et al. 2024:** RCT confirmed HRV biofeedback training increases resting vagally-mediated HRV — benefits persist beyond training sessions.

**Critical implication for Somna:** HRV coherence breathing is not just an autonomic exercise — it directly enhances the alpha-dominant brain state that entrainment modes target. A 5-minute pre-session coherence breathing warm-up could prime the brain for deeper entrainment.

---

## 2. Muse 2 PPG Hardware

### Hardware Specs

- Muse 2 has a built-in forehead PPG (photoplethysmography) sensor
- PPG measures blood volume changes via infrared light reflection from skin surface
- Forehead PPG is less reliable than finger/ear PPG but sufficient for IBI estimation
- Accessed via **`ANCILLARY_PRESET`** at ~64 Hz sampling rate

### PPG Access via BrainFlow

```python
from brainflow.board_shim import BoardShim, BoardIds, BrainFlowPresets

# PPG channel indices
ppg_channels = BoardShim.get_ppg_channels(
    BoardIds.MUSE_2_BOARD,
    BrainFlowPresets.ANCILLARY_PRESET
)

# Non-destructive 1-second read from PPG preset
ppg_data = board.get_current_board_data(64, BrainFlowPresets.ANCILLARY_PRESET)
ppg_ir  = ppg_data[ppg_channels[0]]  # Infrared channel
ppg_red = ppg_data[ppg_channels[1]]  # Red channel
```

### PPG Enable Command — HARDWARE VERIFICATION REQUIRED

**Do not implement until this is resolved on real Muse 2 hardware.**

- BrainFlow 5.1.0 changelog confirms `config_board("p50")` enables the **5th EEG channel** on Muse 2
- Earlier docs suggest `config_board("p61")` may be needed to enable PPG streaming
- It is **uncertain** whether PPG requires an explicit enable command or is automatically available when reading from `ANCILLARY_PRESET`

**Test procedure on real hardware:**
1. Connect Muse 2, `prepare_session()`, `start_stream()`
2. Attempt `board.get_current_board_data(64, BrainFlowPresets.ANCILLARY_PRESET)` without any `config_board()` call
3. If PPG data is present → auto-enabled, no command needed
4. If not: try `board.config_board("p61")` and re-read
5. Document which command works and update `brainflow_reference.md` accordingly

---

## 3. PPG-Derived HRV Computation

### IBI Extraction

```python
import numpy as np
from brainflow.data_filter import DataFilter, FilterTypes

def extract_ibis_from_ppg(ppg_data, sampling_rate=64):
    """Extract inter-beat intervals from PPG signal.

    Args:
        ppg_data:      1D array of PPG IR channel data
        sampling_rate: int, Hz (64 for Muse 2 ANCILLARY_PRESET)

    Returns:
        ibis:        list of IBIs in milliseconds
        peak_indices: indices of detected pulse peaks
    """
    # Bandpass filter: 0.5–4 Hz (30–240 BPM range)
    DataFilter.perform_bandpass(
        ppg_data, sampling_rate, 2.0, 1.5,
        2, FilterTypes.BUTTERWORTH, 0
    )

    # Threshold-based peak detection
    threshold    = np.percentile(ppg_data, 60)
    min_distance = int(sampling_rate * 0.4)  # 400 ms minimum between beats (~150 BPM max)

    peaks = []
    for i in range(1, len(ppg_data) - 1):
        if (ppg_data[i] > ppg_data[i-1] and
            ppg_data[i] > ppg_data[i+1] and
            ppg_data[i] > threshold):
            if not peaks or (i - peaks[-1]) >= min_distance:
                peaks.append(i)

    ibis = []
    for i in range(1, len(peaks)):
        ibi_ms = (peaks[i] - peaks[i-1]) / sampling_rate * 1000
        if 400 < ibi_ms < 1500:  # 40–150 BPM; reject artifacts
            ibis.append(ibi_ms)

    return ibis, peaks
```

BrainFlow also provides `DataFilter.get_heart_rate()` and `get_oxygen_level()` for single-value heart rate / SpO2 — but for continuous IBI series needed for HRV, manual peak detection gives more control.

### HRV Metrics

```python
def compute_hrv_metrics(ibis):
    """Compute HRV metrics from inter-beat intervals (minimum ~60 seconds of data)."""
    ibis = np.array(ibis)
    successive_diffs = np.diff(ibis)
    return {
        "rmssd_ms":    round(float(np.sqrt(np.mean(successive_diffs ** 2))), 1),
        "sdnn_ms":     round(float(np.std(ibis)), 1),
        "mean_hr_bpm": round(float(60000 / np.mean(ibis)), 1),
    }
```

### Coherence Score

```python
from scipy.signal import welch

def compute_coherence_score(ibis):
    """Compute HRV coherence score.

    coherence = power at dominant frequency / total power in 0.04–0.26 Hz

    Args:
        ibis: array of IBIs in milliseconds

    Returns:
        coherence_score: float 0–1
        dominant_freq:   float Hz
    """
    resample_rate = 4.0  # Hz — standard for HRV frequency analysis
    ibi_times    = np.cumsum(ibis) / 1000.0  # seconds
    regular_times = np.arange(ibi_times[0], ibi_times[-1], 1 / resample_rate)
    ibi_interp   = np.interp(regular_times, ibi_times, ibis)
    ibi_interp   = ibi_interp - np.mean(ibi_interp)  # detrend

    freqs, psd = welch(ibi_interp, fs=resample_rate, nperseg=len(ibi_interp) // 2)

    coh_mask  = (freqs >= 0.04) & (freqs <= 0.26)
    coh_psd   = psd[coh_mask]
    coh_freqs = freqs[coh_mask]

    if len(coh_psd) == 0:
        return 0.0, 0.0

    total_power = np.sum(coh_psd)
    peak_idx    = np.argmax(coh_psd)
    peak_freq   = coh_freqs[peak_idx]

    narrow_mask = (coh_freqs >= peak_freq - 0.015) & (coh_freqs <= peak_freq + 0.015)
    peak_power  = np.sum(coh_psd[narrow_mask])

    coherence = peak_power / total_power if total_power > 0 else 0.0
    return round(coherence, 3), round(peak_freq, 3)
```

---

## 4. Breathing Guide Protocol

### Breathing Rate Reference

| Breaths/min | Frequency (Hz) | Cycle Duration |
|-------------|----------------|----------------|
| 4.5 | 0.075 | 13.3 s |
| 5.0 | 0.083 | 12.0 s |
| 5.5 | 0.092 | 10.9 s |
| **6.0** | **0.100** | **10.0 s** ← most common resonance |
| 7.0 | 0.117 | 8.6 s |

### Session Phases

- **Discovery Phase** (first 3 sessions): Sweep 4.5 → 7.0 BPM in 0.5 BPM steps, 2 minutes each. Monitor coherence at each rate. Highest coherence = user's resonance frequency.
- **Training Phase** (ongoing): Breathe at discovered resonance frequency, 10–20 minutes. Real-time coherence feedback.
- **Pre-Session Warm-Up** (regular use): 5-minute coherence breathing before any entrainment session to prime alpha-dominant brain state.

### Visual Pacer (Spiral Layer)

Use the existing spiral renderer: expansion = inhale, contraction = exhale.

```
scale = base_scale + amplitude * sin(2π * breathing_freq * t)
```

- Inhale: 40–50% of cycle (4 s for 6 BPM / 10 s cycle)
- Exhale: 50–60% of cycle (6 s)
- Smooth sinusoidal scaling — not linear
- Display coherence score as center text, updated every 5 seconds
- Color-code: red (< 0.3), yellow (0.3–0.5), green (> 0.5)

### Cross-Session Resonance Frequency Discovery

| Session | Protocol |
|---------|----------|
| First | Sweep 4.5–7.0 BPM, log coherence at each rate |
| Second | Narrow sweep around best rate ± 0.5 BPM in 0.25 BPM steps |
| Third | Confirm resonance frequency, store in `user_profile.json` |
| Subsequent | Use stored frequency directly, monitor for stability |

### `user_profile.json` Schema Addition

```json
{
  "hrv_resonance_freq_hz": 0.092,
  "hrv_resonance_bpm": 5.5,
  "hrv_resonance_calibrated_at": "2026-04-15T20:00:00",
  "hrv_resonance_coherence_at_discovery": 0.72,
  "hrv_baseline_rmssd_ms": 42.3,
  "hrv_baseline_coherence": 0.35,
  "hrv_sessions_completed": 3
}
```

**Write via `update_profile()` from `somna_agent.py` — never direct file write.**

---

## 5. EEG Monitoring During HRV Sessions

Monitor alpha power alongside HRV during coherence breathing:
- Expected: alpha power increases during high-coherence states (Demin & Poskotinova 2025)
- Log both HRV coherence and alpha power at 5-second intervals for cross-session analysis
- This provides empirical verification of cortical-autonomic coupling on Somna's specific hardware

### Combined Log Format

```json
{
  "event": "hrv_breathing_tick",
  "timestamp": "2026-04-15T20:05:30",
  "coherence_score": 0.68,
  "dominant_freq_hz": 0.092,
  "rmssd_ms": 55.2,
  "mean_hr_bpm": 62.3,
  "eeg_alpha_power": 0.42,
  "eeg_theta_power": 0.18,
  "eeg_alpha_theta_ratio": 2.33,
  "breathing_rate_bpm": 5.5,
  "breathing_phase": "exhale"
}
```

---

## 6. Pre-Session Warm-Up Use Case

5-minute coherence breathing at resonance frequency before any Somna session type drives alpha power up — the brain is already in a receptive state when the main session begins.

Proposed session YAML extension (optional `warm_up` block):

```yaml
warm_up:
  type: hrv_breathing
  duration_minutes: 5
  breathing_rate: "resonance"   # uses stored hrv_resonance_freq_hz from profile
  visual_pacer: true
  coherence_feedback: true
```

`timeline_runner.py` would check for a `warm_up` block before starting the main session timeline. Warm-up runs as a mini-session, then transitions seamlessly into the main session.

---

## 7. Integration Details

### `live_control.json` Keys

```json
{
  "hrv_active": true,
  "hrv_coherence_score": 0.68,
  "hrv_dominant_freq_hz": 0.092,
  "hrv_rmssd_ms": 55.2,
  "hrv_mean_hr_bpm": 62.3,
  "hrv_breathing_target_bpm": 5.5,
  "hrv_breathing_phase": "exhale",
  "hrv_breathing_phase_progress": 0.65
}
```

### Module Architecture

New module: `hrv_engine.py` — follows `timeline_runner.py` pattern.
- Background thread, started by control panel
- Reads PPG from `ANCILLARY_PRESET`
- Computes IBI, HRV metrics, coherence score
- Writes to `live_control.json` via `_patch_live()`
- Runs alongside `eeg_engine.py` simultaneously — different presets, same board session

### Board Details

| Parameter | Value |
|-----------|-------|
| Board ID | `BoardIds.MUSE_2_BOARD = 38` |
| PPG preset | `BrainFlowPresets.ANCILLARY_PRESET` (~64 Hz) |
| EEG preset | `BrainFlowPresets.DEFAULT_PRESET` (256 Hz) |
| Simultaneous read | Both presets readable from same board session |
| PPG retrieval | `board.get_current_board_data(64, BrainFlowPresets.ANCILLARY_PRESET)` |
| Buffer method | `get_current_board_data()` — non-destructive. **Never `get_board_data()` in a loop.** |

---

## 8. Critical Implementation Notes

- **PPG enable command is uncertain — verify on real hardware first before writing any HRV code.**
- Forehead PPG is inherently noisier than finger/ear PPG. Expect ~10–20% artifact rate. Aggressive artifact rejection is essential.
- IBI artifact rejection: discard IBIs outside 400–1500 ms (40–150 BPM). Also discard IBIs differing from local median by > 20%.
- **Coherence minimum data:** coherence score requires at least 60 seconds of clean IBI data to be meaningful.
- Breathing pacer must be smooth and predictable — any jitter disrupts breathing rhythm and reduces coherence. At 144 Hz vsync, the spiral pacer should be perfectly smooth.
- All `live_control.json` writes via `_patch_live()` — not `llm_driver.send()`.
- All `user_profile.json` writes via `update_profile()` — not direct file write.
- `beat_type` key (not `beat_mode`) for audio generation mode.
- Development without hardware: `SYNTHETIC_BOARD = -1` does not generate realistic PPG data. Need a separate PPG data simulator or recorded data playback for pre-hardware testing.

---

## References

1. Balaji S et al. (2025). Heart rate variability biofeedback in a global study of the most common coherence frequencies and the impact of emotional states. *Scientific Reports*, 15, 3241.
2. Demin D, Poskotinova L (2025). Brain Bioelectric Responses to Short-Term Heart Rate Variability Biofeedback Training. *Life*, 15(1), 11.
3. Pardo-Rodriguez MN et al. (2025). Conscious breathing enhances bidirectional cortical-autonomic modulation. *Frontiers in Systems Neuroscience*, 19.
4. Saito I et al. (2024). HRV biofeedback training increases resting vagally-mediated HRV. *Applied Psychophysiology and Biofeedback*.
5. Shaffer F, Meehan ZM (2020). A Practical Guide to Resonance Frequency Assessment for Heart Rate Variability Biofeedback. *Frontiers in Neuroscience*, 14, 570400.
