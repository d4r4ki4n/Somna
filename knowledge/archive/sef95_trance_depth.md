# SEF95 and Spectral Slope — Trance Depth Metrics

Doc 17 in Research Reference Series. Authored by Research (External Research Collaborator), March 2026.

---

## What SEF95 Is

SEF95 (Spectral Edge Frequency 95%) is the frequency below which 95% of total EEG spectral power lies. It is a single continuous scalar that drops as the brain enters deeper states:

| State | SEF95 Range | Context |
|-------|-------------|---------|
| Awake / Alert | > 20 Hz (typically 20–25) | Beta-dominant waking EEG |
| Light Sedation / Relaxation | 15–20 Hz | Alpha-dominant, early relaxation |
| Moderate Sedation / Trance | 10–15 Hz | Theta emergence, hypnotic engagement zone |
| Deep Sedation / Deep Sleep | < 10 Hz | Delta-dominant, NREM stages 2–3 |
| Oversedation / Burst Suppression | < 8 Hz | Clinical concern zone — not a Somna target |

Clinical precedent: SEF95 is used in BIS (Bispectral Index) monitors for anesthesia depth monitoring.

Zech et al. 2023: BIS drops from ~97.7 to ~86.4 during hypnosis induction; CSI drops from ~94.6 to ~77.7. EEG-derived depth metrics do respond to non-pharmacological hypnotic induction.

---

## CRITICAL: Full Spectrum from 0.5 Hz

Hight et al. 2025 discovered that excluding frequencies below 2 Hz from the SEF95 computation inflates the result by approximately 30%. The PSD **must** include the full spectrum from 0.5 Hz upward. This is not optional.

---

## BrainFlow Implementation

### compute_sef95()

```python
import numpy as np
from brainflow.data_filter import DataFilter

def compute_sef95(eeg_data: np.ndarray, sampling_rate: int = 256) -> float:
    """
    Compute SEF95 from a single EEG channel.
    eeg_data: 1D array of EEG samples (recommend 2-4 seconds = 512-1024 samples)
    Returns: SEF95 in Hz
    """
    psd = DataFilter.get_psd_welch(
        eeg_data, nfft=256, overlap=128,
        sampling_rate=sampling_rate, window=2  # HAMMING
    )
    powers, freqs = psd[0], psd[1]

    # CRITICAL: include full spectrum from 0.5 Hz (Hight et al. 2025)
    mask = freqs >= 0.5
    powers, freqs = powers[mask], freqs[mask]

    cumulative = np.cumsum(powers)
    idx = np.searchsorted(cumulative, 0.95 * cumulative[-1])
    return float(freqs[min(idx, len(freqs) - 1)])
```

For Muse 2 (board_id=38): channels TP9 (0), AF7 (1), AF8 (2), TP10 (3). Average across channels or use frontal (AF7/AF8) for trance-relevant activity. Apply exponential moving average with tau ≈ 3–5 seconds to reduce jitter.

---

## Complementary Metric: Spectral Slope (1/f Exponent)

EEG power spectrum follows a 1/fα distribution. The exponent steepens as the brain enters deeper states.

Kozhemiako et al. 2022 (eNeuro, N=10,255): slope steepens wake → NREM → REM with large, consistent effect sizes.
Schneider et al. 2022 (Frontiers in Neuroinformatics): slope shows "especially large and consistent variability between sleep stages and low variability between subjects."

| Spectral Slope | Approximate State |
|---------------|-------------------|
| −1.0 to −1.5 | Alert / Engaged |
| −2.0 to −2.5 | Relaxed / Trance |
| Steeper than −2.5 | Deep Sleep |

### compute_spectral_slope()

```python
def compute_spectral_slope(eeg_data: np.ndarray, sampling_rate: int = 256) -> float:
    """
    Compute 1/f spectral slope via linear regression on log-log PSD.
    Returns: slope (negative float, steeper = deeper state)
    """
    psd = DataFilter.get_psd_welch(
        eeg_data, nfft=256, overlap=128,
        sampling_rate=sampling_rate, window=2
    )
    powers, freqs = psd[0], psd[1]

    mask = (freqs >= 2.0) & (freqs <= 30.0)
    log_freqs = np.log10(freqs[mask])
    log_powers = np.log10(powers[mask] + 1e-10)

    slope, _ = np.polyfit(log_freqs, log_powers, 1)
    return float(slope)
```

---

## live_control.json Keys

| Key | Type | Default | Writer | Reader |
|-----|------|---------|--------|--------|
| `eeg_sef95` | float | null | eeg_engine.py | somna_agent.py |
| `eeg_spectral_slope` | float | null | eeg_engine.py | somna_agent.py |

Both computed from the same `DataFilter.get_psd_welch()` call already used for band power extraction. Overhead is negligible.

---

## Composite trance_score Formula

Combine SEF95 + spectral slope + theta/alpha ratio:

```python
trance_score = (
    0.4 * normalize(sef95, high=25, low=8) +
    0.3 * normalize(slope, high=-1.0, low=-3.0) +
    0.3 * theta_alpha_ratio_normalized
)
```

Where `normalize(x, high, low)` maps the raw value's range to 0.0–1.0. Starting weights 0.4/0.3/0.3 are tunable.

---

## Agent Usage Rules

- Do not make binary state decisions from a single metric. Use the trend (is SEF95 dropping? is slope steepening?) as much as the absolute value.
- During fractionation: expect SEF95 to rise sharply during emergence and fall during reinduction. Rate of SEF95 recovery after emergence indicates reinduction ease.
- During sleep onset: SEF95 < 12–15 Hz combined with slope steeper than −2.0 is a strong N1 entry indicator.
- If `eeg_quality = "poor"`, treat the last "good" reading as current state. Do not make frequency decisions on bad data.
