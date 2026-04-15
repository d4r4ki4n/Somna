"""
eeg/depth_features.py — Spectral Slope + Interhemispheric Coherence (Bible Ch.2 §2.8)

Three-axis trance depth estimation:
  Axis 1 (Oscillatory)  — existing theta/alpha + SEF95 in eeg_engine.py
  Axis 2 (Aperiodic)    — 1/f spectral slope (eeg_spectral_slope) — already computed
  Axis 3 (Connectivity) — interhemispheric coherence + beta envelope correlation

All functions are pure — no IO, no side effects.  Wire into eeg_engine.py after
the existing Welch PSD block.

Scientific basis:
  Spectral slope: Donoghue et al. (2020), Voytek et al. (2015) — E/I balance proxy
  Coherence:      Jensen & Vidal-Garcia (2006), Naish et al. (2014)
  Beta envelope:  Naish et al. (2014) — SHAP #1 feature for deep hypnosis
  Three-axis composite: See Bible Ch.2 §2.8 §5
"""

import numpy as np
from typing import Optional


# ── Spectral slope helpers ────────────────────────────────────────────────────

def compute_spectral_slope(psd_freqs: np.ndarray, psd_power: np.ndarray,
                           fit_range: tuple = (2.0, 40.0)) -> float:
    """Compute 1/f spectral slope (aperiodic exponent) from Welch PSD.

    Linear regression on log-log PSD in the fit_range.  Typical values:
      -1.0 to -1.5  = alert wakefulness
      -1.5 to -2.0  = relaxed / light trance
      -2.0 to -2.5  = moderate trance
      -2.5 to -3.0  = deep trance / NREM-like
    """
    mask = (psd_freqs >= fit_range[0]) & (psd_freqs <= fit_range[1])
    freqs = psd_freqs[mask]
    power = np.maximum(psd_power[mask], 1e-12)
    if len(freqs) < 4:
        return -1.5   # safe default if insufficient range
    log_f = np.log10(freqs)
    log_p = np.log10(power)
    slope, _ = np.polyfit(log_f, log_p, 1)
    return float(slope)


def frontal_spectral_slope(psd_af7: np.ndarray, psd_af8: np.ndarray,
                           freqs: np.ndarray) -> float:
    """Average frontal PSD (AF7 + AF8), then compute slope."""
    return compute_spectral_slope(freqs, (psd_af7 + psd_af8) / 2.0)


def gated_slope_update(new_slope: float, quality: str,
                       prev_slope: float, alpha: float = 0.3) -> tuple:
    """EMA-smoothed slope update with SQI gating.

    Returns (smoothed_slope, confidence).
    On 'unusable' signal, holds previous value and returns 0.0 confidence.
    On 'poor', slows the EMA to be more conservative.
    """
    if quality == "unusable":
        return prev_slope, 0.0
    confidence = 1.0 if quality in ("good", "full", "reduced") else 0.5
    effective_alpha = alpha * confidence
    smoothed = prev_slope * (1.0 - effective_alpha) + new_slope * effective_alpha
    return smoothed, confidence


# ── Interhemispheric coherence ────────────────────────────────────────────────

def compute_band_coherence(signal_left: np.ndarray, signal_right: np.ndarray,
                           fs: float = 256.0,
                           nperseg: Optional[int] = None) -> dict:
    """Per-band interhemispheric coherence via scipy.signal.coherence.

    nperseg defaults to min(256, len(signal)) for the 2-second rolling buffer.
    Returns dict: theta_coh, alpha_coh, beta_coh, overall_coh.
    """
    from scipy.signal import coherence
    if len(signal_left) < 32 or len(signal_right) < 32:
        return {"theta_coh": 0.5, "alpha_coh": 0.5, "beta_coh": 0.5, "overall_coh": 0.5}

    seg = nperseg or min(256, len(signal_left))
    freqs, coh = coherence(signal_left, signal_right, fs=fs,
                           nperseg=seg, noverlap=seg // 2)
    bands = {
        "theta":   (4.0,  8.0),
        "alpha":   (8.0,  13.0),
        "beta":    (13.0, 30.0),
        "overall": (4.0,  30.0),
    }
    result = {}
    for name, (lo, hi) in bands.items():
        mask = (freqs >= lo) & (freqs <= hi)
        result[f"{name}_coh"] = float(np.mean(coh[mask])) if mask.any() else 0.5
    return result


def compute_beta_envelope_correlation(signal_left: np.ndarray,
                                      signal_right: np.ndarray,
                                      fs: float = 256.0) -> float:
    """Pearson r of beta (13–30 Hz) amplitude envelopes between hemispheres.

    SHAP #1 feature for classifying deep hypnosis (Naish et al. 2014).
    High r (0.6–0.9) = synchronized bilateral beta = normal wakefulness.
    Low r (0.0–0.3)  = decoupled hemispheric processing = deep trance.
    """
    from scipy.signal import butter, filtfilt, hilbert
    if len(signal_left) < 64 or len(signal_right) < 64:
        return 1.0   # insufficient data — assume synchronized (safe default)
    nyq = fs / 2.0
    b, a = butter(4, [13.0 / nyq, 30.0 / nyq], btype="band")
    beta_left  = filtfilt(b, a, signal_left)
    beta_right = filtfilt(b, a, signal_right)
    env_left  = np.abs(hilbert(beta_left))
    env_right = np.abs(hilbert(beta_right))
    if np.std(env_left) < 1e-10 or np.std(env_right) < 1e-10:
        return 1.0
    return float(np.corrcoef(env_left, env_right)[0, 1])


def coherence_depth_indicator(frontal_alpha_coh: float,
                               frontal_beta_env_corr: float,
                               temporal_theta_coh: float) -> float:
    """Composite coherence depth indicator (0=alert, 1=deep trance).

    Combines DECREASING frontal coherence (executive decoupling) with
    INCREASING temporal theta coherence (auditory entrainment binding).
    Frontal decoupling weighted 0.65, temporal binding 0.35.
    """
    frontal_score  = 1.0 - ((frontal_alpha_coh + frontal_beta_env_corr) / 2.0)
    temporal_score = temporal_theta_coh
    composite = 0.65 * frontal_score + 0.35 * temporal_score
    return float(max(0.0, min(1.0, composite)))


# ── Enhanced three-axis trance score ─────────────────────────────────────────

def enhanced_trance_score(oscillatory_score: float,
                          spectral_slope: float,
                          coherence_depth: float,
                          baseline_slope: float,
                          weights: tuple = (0.40, 0.30, 0.30)) -> float:
    """Three-axis trance depth composite (Bible Ch.2 §2.8 §5).

    Args:
        oscillatory_score: existing eeg_trance_score (0–1)
        spectral_slope:    current 1/f slope (negative float, e.g. -1.5)
        coherence_depth:   coherence_depth_indicator output (0–1)
        baseline_slope:    resting-state slope from calibration
        weights:           (oscillatory, slope, coherence), must sum to 1.0

    Oscillatory 0.40 — most validated; theta/alpha + SEF95
    Slope       0.30 — strongest single-metric arousal discriminator
    Coherence   0.30 — connectivity dimension missed by other axes
    """
    w_osc, w_slope, w_coh = weights
    slope_range      = 1.3   # expected range: baseline ~-1.2, deep ~-2.5
    slope_normalized = max(0.0, min(1.0, (baseline_slope - spectral_slope) / slope_range))
    composite = (w_osc * oscillatory_score
                 + w_slope * slope_normalized
                 + w_coh  * coherence_depth)
    return float(max(0.0, min(1.0, composite)))


def update_depth_weights(current_weights: tuple,
                         session_correlations: dict,
                         learning_rate: float = 0.05,
                         floor: float = 0.10) -> tuple:
    """Adapt three-axis weights from session-level correlations.

    EMA toward softmax-normalized |correlations|.  Floor = 0.10 ensures
    no axis is completely discarded.  ~20 sessions to shift substantially.
    """
    w_osc, w_slope, w_coh = current_weights
    abs_corrs = [
        abs(session_correlations.get("oscillatory", 0.33)),
        abs(session_correlations.get("slope",       0.33)),
        abs(session_correlations.get("coherence",   0.33)),
    ]
    total   = sum(abs_corrs) or 1.0
    targets = [c / total for c in abs_corrs]
    new_w   = tuple(max(floor, w * (1 - learning_rate) + t * learning_rate)
                    for w, t in zip(current_weights, targets))
    s = sum(new_w)
    return tuple(w / s for w in new_w)


# ── Convergent evidence rule ──────────────────────────────────────────────────

def convergent_check(oscillatory_ready: bool, slope_ready: bool,
                     coherence_ready: bool, min_axes: int = 2) -> bool:
    """Require convergent evidence from at least min_axes depth axes.

    Prevents false phase transitions from single-axis artifacts.
    Default min_axes=2: any two of three axes must agree.
    """
    return sum([oscillatory_ready, slope_ready, coherence_ready]) >= min_axes
