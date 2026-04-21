"""
Somna EEG Engine
================
Acquires EEG from a BrainFlow-compatible board (default: SYNTHETIC_BOARD for
Phase 0 development) and writes processed band-power metrics to live_control.json
for consumption by the agent and display layers.

Phase 0: SYNTHETIC_BOARD (-1) — generates synthetic alpha at ~10 Hz.
Phase 2: Swap to MUSE_2_BOARD (38) when hardware arrives (no code changes
         beyond the board_id in agent_config.yaml).

IPC pattern: patch_live() — same pattern as audio_engine.py, timeline_runner.py.
             Never use llm_driver.send() for live_control.json writes.

Board ID note:
  38 = MUSE_2_BOARD  (native BLE, no dongle) — use this for Muse 2
  39 = MUSE_S_BOARD  (Muse S — recommended for sleep/lying-down sessions)
  NEVER use 22 (MUSE_2_BLED_BOARD) — that requires a $30 BLED112 USB dongle.
"""

import json
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np

_LIVE_PATH = Path(__file__).parent.parent / "live_control.json"
_PROFILE_PATH = Path(__file__).parent.parent / "user_profile.json"
# Muse 2 channel order from BrainFlow: indices 0-3 → TP9, AF7, AF8, TP10
_CH_NAMES = ["tp9", "af7", "af8", "tp10"]
_CH_WEIGHTS_ASSR = {"tp9": 0.15, "af7": 0.35, "af8": 0.35, "tp10": 0.15}

# ── IPC helpers ───────────────────────────────────────────────────────────────

from ipc import patch_live


def _read_live() -> dict:
    try:
        return (
            json.loads(_LIVE_PATH.read_text(encoding="utf-8"))
            if _LIVE_PATH.exists()
            else {}
        )
    except Exception:
        return {}


def _load_profile() -> dict:
    try:
        return (
            json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
            if _PROFILE_PATH.exists()
            else {}
        )
    except Exception:
        return {}


# ── SQI (Signal Quality Index) — Bible Ch.5 §5.3 ───────────────────────────────────────


def _sqi_amplitude(ch: np.ndarray) -> float:
    """Amplitude-based quality score. 1.0 = clean, 0.0 = saturated/dead."""
    if np.any(np.abs(ch) > 500.0):
        return 0.0
    rms = float(np.sqrt(np.mean(ch**2)))
    if rms < 2.0:
        return 0.0
    if rms <= 80.0:
        return 1.0
    if rms <= 150.0:
        return max(0.0, 1.0 - (rms - 80.0) / 70.0)
    return 0.0


def _sqi_spectral_flatness(ch: np.ndarray, fs: int = 256) -> float:
    """Spectral flatness (Wiener entropy) — detects muscle (EMG) artifact.

    Normal EEG is 1/f-shaped (flatness ~0.05–0.15).
    Muscle artifact flattens the spectrum (flatness > 0.3).
    """
    try:
        from scipy.signal import welch as _welch

        freqs, psd = _welch(ch, fs=fs, nperseg=min(256, len(ch)))
    except Exception:
        return 0.5  # neutral on failure
    mask = (freqs >= 1.0) & (freqs <= 45.0)
    p = psd[mask]
    if len(p) == 0 or np.any(p <= 0):
        return 0.5
    # Geometric mean via log — avoids scipy.stats.gmean dependency
    log_mean = np.mean(np.log(p + 1e-30))
    arith_mean = np.mean(p)
    flatness = float(np.exp(log_mean) / (arith_mean + 1e-30))
    if flatness <= 0.15:
        return 1.0
    if flatness <= 0.40:
        return max(0.0, 1.0 - (flatness - 0.15) / 0.25)
    return 0.0


def _sqi_hf_ratio(ch: np.ndarray, fs: int = 256) -> float:
    """High-frequency power ratio — confirms muscle artifact.

    Normal EEG: HF (30-45 Hz) power < 15% of total (1-45 Hz).
    Muscle-contaminated: > 30%.
    """
    try:
        from scipy.signal import welch as _welch

        freqs, psd = _welch(ch, fs=fs, nperseg=min(256, len(ch)))
    except Exception:
        return 0.5
    total_mask = (freqs >= 1.0) & (freqs <= 45.0)
    hf_mask = (freqs >= 30.0) & (freqs <= 45.0)
    total = float(np.sum(psd[total_mask]))
    hf = float(np.sum(psd[hf_mask]))
    if total <= 0:
        return 0.5
    ratio = hf / total
    if ratio <= 0.15:
        return 1.0
    if ratio <= 0.40:
        return max(0.0, 1.0 - (ratio - 0.15) / 0.25)
    return 0.0


def compute_channel_sqi(ch: np.ndarray, fs: int = 256) -> float:
    """Multiplicative 3-component SQI for one EEG channel.

    Multiplicative: if ANY component is bad, the channel is bad.
    Conservatively biased toward false negatives (reject good) over
    false positives (trust bad).
    """
    return _sqi_amplitude(ch) * _sqi_spectral_flatness(ch, fs) * _sqi_hf_ratio(ch, fs)


class SQITracker:
    """Per-channel SQI with EMA smoothing and hysteresis confidence gating.

    Confidence levels (Bible Ch.5 §5.3 §4.2):
        full     — composite ≥ 0.7, all 4 channels usable
        reduced  — composite 0.5–0.7, 3–4 channels
        low      — composite 0.3–0.5, 2–3 channels
        none     — composite < 0.3

    Hysteresis: 3 s to gate DOWN, 5 s to gate UP.
    """

    _LEVELS = ("none", "low", "reduced", "full")

    _WARMUP_TICKS = 8  # ~8 seconds after connect before gating on SQI

    def __init__(self, alpha: float = 0.3):
        self._alpha = alpha
        self._ema = {ch: 0.5 for ch in _CH_NAMES}
        self._history: list[float] = []  # composite history (last 120 s)
        self._confidence = "none"
        self._below_ctr = 0  # consecutive ticks below next threshold
        self._above_ctr = 0
        self._prompted = False
        self._warmup_ctr = self._WARMUP_TICKS

    def update(self, raw_sqi: dict) -> tuple[dict, str]:
        """EMA-smooth raw SQI values and update confidence.

        Returns (smoothed_dict, confidence_str).
        """
        smoothed: dict[str, float] = {}
        for ch in _CH_NAMES:
            raw = float(raw_sqi.get(ch, 0.0))
            self._ema[ch] = self._alpha * raw + (1 - self._alpha) * self._ema[ch]
            smoothed[ch] = round(self._ema[ch], 3)

        composite = round(float(np.mean(list(smoothed.values()))), 3)
        usable = sum(1 for v in smoothed.values() if v >= 0.3)
        self._history.append(composite)
        if len(self._history) > 120:
            self._history = self._history[-120:]

        # During warmup, EMA builds up but confidence stays "none" (UI shows
        # "warming up") so we don't fire false unusable/low events.
        if self._warmup_ctr > 0:
            self._warmup_ctr -= 1
            return smoothed, "none"

        prev = self._confidence
        self._confidence = self._gate(composite, usable)
        if self._confidence in ("none", "low") and prev in ("reduced", "full"):
            ch_str = " ".join(f"{c}:{v:.2f}" for c, v in smoothed.items())
            raw_str = " ".join(f"{c}:{raw_sqi.get(c, 0):.2f}" for c in _CH_NAMES)
            print(f"[EEG] SQI drop  ema={ch_str}  composite={composite:.2f}")
            print(f"[EEG] SQI raw   {raw_str}")
        return smoothed, self._confidence

    def _gate(self, composite: float, usable: int) -> str:
        """Apply hysteresis to smooth confidence-level transitions."""
        target = self._level_for(composite, usable)
        current_idx = self._LEVELS.index(self._confidence)
        target_idx = self._LEVELS.index(target)

        if target_idx < current_idx:  # downgrade
            self._above_ctr = 0
            self._below_ctr += 1
            if self._below_ctr >= 3:
                self._below_ctr = 0
                return target
        elif target_idx > current_idx:  # upgrade
            self._below_ctr = 0
            self._above_ctr += 1
            if self._above_ctr >= 3:
                self._above_ctr = 0
                return target
        else:
            self._below_ctr = 0
            self._above_ctr = 0
        return self._confidence

    @staticmethod
    def _level_for(composite: float, usable: int) -> str:
        if composite >= 0.6 and usable >= 3:
            return "full"
        if composite >= 0.4 and usable >= 3:
            return "reduced"
        if composite >= 0.2 and usable >= 2:
            return "low"
        return "none"

    def should_headband_prompt(self) -> bool:
        """True once when composite has been < 0.3 for 60 consecutive seconds."""
        if self._prompted:
            return False
        if len(self._history) < 60:
            return False
        if all(v < 0.3 for v in self._history[-60:]):
            self._prompted = True
            return True
        return False

    def reset_session(self) -> None:
        """Reset per-session state (prompted flag) on new session."""
        self._prompted = False
        self._history.clear()


# ── ASSR (Entrainment Verification) — Bible Ch.5 §5.4 ──────────────────────────────────


def _assr_welch(ch: np.ndarray, fs: int = 256, nperseg: int = 512):
    """Welch PSD for ASSR detection. nperseg=512 → 0.5 Hz resolution."""
    try:
        from scipy.signal import welch as _welch

        return _welch(ch, fs=fs, nperseg=nperseg, noverlap=nperseg // 2, window="hann")
    except Exception:
        return np.array([]), np.array([])


def _estimate_1f_background(
    freqs: np.ndarray, psd: np.ndarray, beat_freq: float, exclude_width: float = 2.0
) -> float:
    """Fit log-log 1/f line to PSD excluding beat frequency and harmonics.

    Returns estimated background power at beat_freq.
    """
    mask = (freqs >= 1.0) & (freqs <= 45.0)
    # Exclude beat frequency + first two harmonics
    for h in [1, 2, 3]:
        fc = beat_freq * h
        mask &= ~((freqs >= fc - exclude_width) & (freqs <= fc + exclude_width))
    # Exclude natural alpha band when beat is outside it
    if not (8.0 <= beat_freq <= 13.0):
        mask &= ~((freqs >= 8.0) & (freqs <= 13.0))

    fit_f = freqs[mask]
    fit_p = psd[mask]
    if len(fit_f) < 5:
        valid = psd[(freqs >= 1.0) & (freqs <= 45.0)]
        return float(np.median(valid)) if len(valid) else 1e-10

    log_f = np.log10(fit_f)
    log_p = np.log10(fit_p + 1e-20)
    coeffs = np.polyfit(log_f, log_p, 1)
    return float(10 ** (coeffs[0] * np.log10(beat_freq) + coeffs[1]))


def _compute_entrainment_strength(
    freqs: np.ndarray, psd: np.ndarray, beat_freq: float, window: float = 0.5
) -> tuple[float, float]:
    """Excess power above 1/f background → entrainment strength 0.0–1.0.

    Returns (strength, excess_ratio).
    """
    beat_mask = (freqs >= beat_freq - window) & (freqs <= beat_freq + window)
    if not np.any(beat_mask):
        return 0.0, 0.0
    measured = float(np.max(psd[beat_mask]))
    background = _estimate_1f_background(freqs, psd, beat_freq)
    if background <= 0:
        return 0.0, 0.0
    excess = measured / background
    if excess <= 1.0:
        return 0.0, round(excess, 2)
    # Logarithmic mapping: ratio 2→0.30, 4→0.60, 8→0.90, 10+→1.0
    strength = min(1.0, float(np.log2(excess) / np.log2(10.0)))
    return round(strength, 3), round(excess, 2)


def band_coherence(
    ch_a: np.ndarray,
    ch_b: np.ndarray,
    fs: int = 256,
    f_low: float | None = None,
    f_high: float | None = None,
) -> float:
    """Mean magnitude-squared coherence between two channels in [f_low, f_high].

    Returns 0.0 on failure or when the band is not specified (returns full-band mean).
    """
    try:
        from scipy.signal import coherence as _coh

        freqs, cxy = _coh(ch_a, ch_b, fs=fs, nperseg=min(512, len(ch_a)), noverlap=256)
        if f_low is not None and f_high is not None:
            mask = (freqs >= f_low) & (freqs <= f_high)
            if not np.any(mask):
                return 0.0
            return float(np.mean(cxy[mask]))
        return float(np.mean(cxy))
    except Exception:
        return 0.0


def composite_assr(
    power_strength: float, coherence: float, alpha_ambiguous: bool = False
) -> float:
    """Blend power-based entrainment strength with inter-channel coherence.

    Weighting (from spec):
        power_strength: 0.70
        coherence:      0.30

    When beat frequency is within 1 Hz of IAF (alpha_ambiguous), the alpha band
    naturally inflates both power and coherence, so we down-weight the composite.
    """
    base = 0.70 * power_strength + 0.30 * coherence
    if alpha_ambiguous:
        base *= 0.70  # 30% penalty for ambiguous alpha overlap
    return round(float(max(0.0, min(1.0, base))), 3)


class ASSRTracker:
    """Sliding-window ASSR history with trend detection and modality switching.

    Computes every update_interval seconds using a min_window_seconds rolling
    window. First result available after min_window_seconds into the session.
    """

    def __init__(self, min_window_seconds: int = 60, update_interval: int = 30):
        self._min_window = min_window_seconds
        self._update_iv = update_interval
        self._history: list[
            tuple[float, float, float]
        ] = []  # (ts, strength, beat_freq)
        self._last_update = 0.0
        self._switch_count = 0
        self._max_switches = 3

    def should_update(self, session_elapsed: float) -> bool:
        if session_elapsed < self._min_window:
            return False
        return (session_elapsed - self._last_update) >= self._update_iv

    def record(self, ts: float, strength: float, beat_freq: float) -> None:
        self._history.append((ts, strength, beat_freq))
        self._last_update = ts

    def get_trend(self, n: int = 4) -> str:
        if len(self._history) < 2:
            return "insufficient_data"
        recent = [h[1] for h in self._history[-n:]]
        if all(s < 0.1 for s in recent):
            return "absent"
        if len(recent) >= 3:
            slope = (recent[-1] - recent[0]) / len(recent)
            if slope > 0.05:
                return "rising"
            if slope < -0.05:
                return "declining"
        return "stable"

    def should_switch_modality(self) -> bool:
        if self._switch_count >= self._max_switches or len(self._history) < 2:
            return False
        return all(h[1] < 0.1 for h in self._history[-2:])

    def reset_session(self) -> None:
        self._history.clear()
        self._last_update = 0.0
        self._switch_count = 0


# ── FAA (Frontal Alpha Asymmetry) — Bible Ch.6 §6.1 ───────────────────────────────────


class FAATracker:
    """Frontal Alpha Asymmetry for receptivity-gated affirmation delivery.

    Computes FAA = ln(alpha_right) − ln(alpha_left) from AF7/AF8 channels.
    Positive FAA = greater left activation = approach/receptive state.
    SQI-gated: marks as "insufficient_data" when either frontal channel < 0.5.

    Baseline calibration: the first 60 valid FAA samples (resting, first minute of
    a session) are accumulated. Once ready, the approach/withdrawal thresholds shift
    to ``baseline_mean ± 0.10`` so the gate is personalised to this user's resting
    asymmetry rather than the population default of ±0.10.
    """

    ALPHA_LOW = 8.0
    ALPHA_HIGH = 13.0
    APPROACH_THRESHOLD = 0.10  # population default; overridden by set_thresholds()
    WITHDRAW_THRESHOLD = -0.10
    ROLLING_N = 10  # 10 × 1-s ticks = 10-second rolling average
    ALPHA_FLOOR = 1e-8  # combined floor; below this = alpha_suppressed
    BASELINE_N = 60  # samples to accumulate for resting baseline

    def __init__(self):
        self._buffer: deque = deque(maxlen=self.ROLLING_N)
        # Mutable thresholds (shifted by set_thresholds after baseline is known)
        self._approach_thresh: float = self.APPROACH_THRESHOLD
        self._withdraw_thresh: float = self.WITHDRAW_THRESHOLD
        # Resting baseline accumulation (first BASELINE_N valid non-suppressed samples)
        self._resting_buf: deque = deque(maxlen=self.BASELINE_N)
        self._baseline_ready: bool = False
        self._baseline_mean: float | None = None
        self._baseline_std: float | None = None

    def set_thresholds(self, approach: float, withdraw: float) -> None:
        """Override the default ±0.10 thresholds with personalised values."""
        self._approach_thresh = approach
        self._withdraw_thresh = withdraw

    def get_baseline(self) -> dict | None:
        """Return baseline dict when ready, else None.

        Called by EEGEngine after each tick to detect when the baseline has just
        been computed so it can be written to live_control.json for the agent.
        """
        if not self._baseline_ready:
            return None
        return {
            "faa_baseline_mean": round(self._baseline_mean, 4),
            "faa_baseline_std": round(self._baseline_std, 4),
        }

    def compute(
        self, eeg_data: np.ndarray, sqi_af7: float, sqi_af8: float, sampling_rate: int
    ) -> dict:
        """Compute FAA from one 1-second EEG window.

        eeg_data: shape (n_channels, n_samples); AF7=index 1, AF8=index 2.
        """
        if eeg_data.shape[0] < 3 or sqi_af7 < 0.5 or sqi_af8 < 0.5:
            return {
                "eeg_faa": 0.0,
                "eeg_faa_raw": 0.0,
                "eeg_faa_state": "insufficient_data",
            }
        try:
            from scipy.signal import welch as _welch

            af7 = eeg_data[1]
            af8 = eeg_data[2]
            nperseg = min(len(af7), sampling_rate)  # up to 1-second window

            def _alpha_power(ch: np.ndarray) -> float:
                freqs, psd = _welch(
                    ch, fs=sampling_rate, nperseg=nperseg, noverlap=nperseg // 2
                )
                mask = (freqs >= self.ALPHA_LOW) & (freqs <= self.ALPHA_HIGH)
                power = float(np.trapz(psd[mask], freqs[mask]))
                return max(power, 1e-30)

            al = _alpha_power(af7)
            ar = _alpha_power(af8)

            # Alpha suppression check: both hemispheres globally suppressed
            if al + ar < self.ALPHA_FLOOR:
                self._buffer.append(0.0)
                return {
                    "eeg_faa": 0.0,
                    "eeg_faa_raw": 0.0,
                    "eeg_faa_state": "alpha_suppressed",
                }

            faa_raw = float(np.log(ar) - np.log(al))
            self._buffer.append(faa_raw)
            faa_smooth = float(np.mean(self._buffer))

            # Accumulate resting baseline (first BASELINE_N valid samples per session)
            if not self._baseline_ready:
                self._resting_buf.append(faa_raw)
                if len(self._resting_buf) >= self.BASELINE_N:
                    import numpy as _np2

                    arr = _np2.array(self._resting_buf)
                    self._baseline_mean = float(_np2.mean(arr))
                    self._baseline_std = float(_np2.std(arr))
                    # Shift thresholds to baseline ± 0.10
                    self._approach_thresh = round(self._baseline_mean + 0.10, 4)
                    self._withdraw_thresh = round(self._baseline_mean - 0.10, 4)
                    self._baseline_ready = True

            if faa_smooth > self._approach_thresh:
                state = "approach"
            elif faa_smooth < self._withdraw_thresh:
                state = "withdrawal"
            else:
                state = "neutral"

            return {
                "eeg_faa": round(faa_smooth, 4),
                "eeg_faa_raw": round(faa_raw, 4),
                "eeg_faa_state": state,
            }
        except Exception:
            return {
                "eeg_faa": 0.0,
                "eeg_faa_raw": 0.0,
                "eeg_faa_state": "insufficient_data",
            }

    def reset(self) -> None:
        """Reset rolling buffer and resting accumulator for a new session.

        The calibrated thresholds (_approach_thresh / _withdraw_thresh) are
        intentionally preserved — they were loaded from user_profile at engine
        start and remain valid across multiple sessions.
        """
        self._buffer.clear()
        self._resting_buf.clear()
        self._baseline_ready = False
        self._baseline_mean = None
        self._baseline_std = None


# ── IAF detection ─────────────────────────────────────────────────────────────


def _normalize(v: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return float(max(0.0, min(1.0, (v - lo) / (hi - lo))))


def compute_iaf_confidence(
    channel_iafs: list,
    peak_powers: list,
    mean_alpha_power: float,
    iaf_30s: float | None,
    iaf_60s: float | None,
) -> tuple[float, dict]:
    """Compute a 0–1 confidence score for IAF detection.

    Weights (revised to match real EEG prominence ranges):
      - agreement_score  (0.40): inter-channel IAF consistency — most diagnostic
      - stability_score  (0.35): temporal stability (half vs full window)
      - prominence_score (0.25): alpha peak above band mean — supplementary

    Prominence normalization: linear over [1.0, 3.0] (prominence=1 means no peak,
    prominence=3 means peak is 3× band-mean, which is strong for real EEG).
    This avoids the log1p/5.0 scale that underweighted clean but moderate peaks.

    Returns (iaf_confidence, detail_dict).
    """
    # Prominence: median peak PSD vs mean alpha-band PSD, linearly scaled
    median_peak = float(np.median(peak_powers)) if peak_powers else 0.0
    prominence = median_peak / (mean_alpha_power + 1e-12)
    prominence_score = _normalize(prominence - 1.0, 0.0, 2.0)  # [1,3] → [0,1]

    # Agreement: std of per-channel IAF estimates (low std = high agreement)
    std_iaf = float(np.std(channel_iafs)) if len(channel_iafs) >= 2 else 2.0
    agreement_score = 1.0 - _normalize(std_iaf, 0.0, 2.0)

    # Stability: how much the half-window estimate differs from the full estimate
    if iaf_30s is not None and iaf_60s is not None:
        stability_score = 1.0 - _normalize(abs(iaf_30s - iaf_60s), 0.0, 1.5)
    else:
        stability_score = 0.5  # neutral when only one window is available

    iaf_conf = 0.25 * prominence_score + 0.40 * agreement_score + 0.35 * stability_score
    iaf_conf = round(float(max(0.0, min(1.0, iaf_conf))), 3)

    return iaf_conf, {
        "prominence_score": round(prominence_score, 3),
        "agreement_score": round(agreement_score, 3),
        "stability_score": round(stability_score, 3),
        "std_iaf": round(std_iaf, 3),
    }


def detect_iaf_with_confidence(
    eeg_data,
    sampling_rate: int = 256,
    alpha_low: float = 7.0,
    alpha_high: float = 13.0,
    half_data: np.ndarray | None = None,
) -> tuple[float | None, float, dict]:
    """Detect IAF and return a confidence score.

    Args:
        eeg_data:      2D array (n_channels, n_samples) — full window
        half_data:     first-half array for stability comparison (optional)

    Returns:
        (iaf_hz, confidence, detail_dict)
        iaf_hz is None if detection failed entirely.
    """
    try:
        from brainflow.data_filter import DataFilter, WindowOperations
    except ImportError:
        return None, 0.0, {}

    def _extract_channel_iaf(data_2d):
        """Extract per-channel IAF, peak power, and mean alpha power."""
        try:
            nfft = DataFilter.get_nearest_power_of_two(sampling_rate)
            if nfft >= data_2d.shape[1]:
                nfft //= 2
            if nfft < 4:
                return [], [], 0.0
            overlap = nfft // 2

            ch_iafs, ch_peaks, alpha_powers = [], [], []
            for ch_data in data_2d:
                try:
                    psd, freqs = DataFilter.get_psd_welch(
                        ch_data.copy(),
                        nfft,
                        overlap,
                        sampling_rate,
                        WindowOperations.HANNING.value,
                    )
                except Exception:
                    continue
                alpha_mask = (freqs >= alpha_low) & (freqs <= alpha_high)
                alpha_psd = psd[alpha_mask]
                alpha_freqs = freqs[alpha_mask]
                if len(alpha_psd) == 0:
                    continue
                peak_idx = int(np.argmax(alpha_psd))
                peak_power = float(alpha_psd[peak_idx])
                mean_power = float(np.mean(alpha_psd))
                alpha_powers.append(mean_power)
                ch_peaks.append(peak_power)
                if peak_power >= 1.5 * mean_power:
                    ch_iafs.append(float(alpha_freqs[peak_idx]))
                else:
                    cog = float(
                        np.sum(alpha_freqs * alpha_psd) / (np.sum(alpha_psd) + 1e-12)
                    )
                    ch_iafs.append(cog)
            return (
                ch_iafs,
                ch_peaks,
                float(np.mean(alpha_powers)) if alpha_powers else 0.0,
            )
        except Exception:
            return [], [], 0.0

    try:
        ch_iafs, ch_peaks, mean_alpha = _extract_channel_iaf(eeg_data)
        iaf_full = float(np.median(ch_iafs)) if ch_iafs else None

        # Stability: re-run on first half of data if provided
        iaf_half = None
        if half_data is not None and half_data.shape[1] >= 4:
            half_iafs, _, _ = _extract_channel_iaf(half_data)
            iaf_half = float(np.median(half_iafs)) if half_iafs else None

        if iaf_full is None:
            return None, 0.0, {}

        confidence, detail = compute_iaf_confidence(
            ch_iafs, ch_peaks, mean_alpha, iaf_half, iaf_full
        )
        detail["iaf_hz"] = round(iaf_full, 2)
        detail["method"] = "paf_with_cog_fallback"
        detail["n_channels"] = len(ch_iafs)
        return iaf_full, confidence, detail

    except Exception:
        return None, 0.0, {}


def detect_iaf(
    eeg_data, sampling_rate: int = 256, alpha_low: float = 7.0, alpha_high: float = 13.0
):
    """Thin wrapper — returns iaf_hz only (backward-compat)."""
    iaf, _, _ = detect_iaf_with_confidence(
        eeg_data, sampling_rate, alpha_low, alpha_high
    )
    return iaf


# Hint templates keyed by channel name (lowest-SQI channel → hint)
_CAL_HINTS: dict[str, str] = {
    "tp9": "Left ear loose — tuck the left armband snug under the ear.",
    "tp10": "Right ear loose — tuck the right armband snug under the ear.",
    "af7": "Left forehead sensor loose — press the headband gently to your brow.",
    "af8": "Right forehead sensor loose — press the headband gently to your brow.",
}
_CAL_HINT_GENERAL = [
    "Relax your jaw and breathe slowly.",
    "Sit still for 10 seconds — small movements make the signal noisy.",
    "Tilt your head slightly forward and hold for a moment.",
]


def _select_calibration_hint(
    channel_sqi: dict, last_hint_at: float, hint_interval: float = 15.0
) -> str:
    """Pick one actionable calibration hint, rate-limited to hint_interval seconds."""
    if time.time() - last_hint_at < hint_interval:
        return ""  # don't spam
    bad = {ch: v for ch, v in channel_sqi.items() if v < 0.6}
    if not bad:
        return ""
    worst_ch = min(bad, key=bad.get)
    return _CAL_HINTS.get(worst_ch, _CAL_HINT_GENERAL[0])


def build_iaf_profile_update(
    iaf_hz: float, iaf_confidence: float | None = None
) -> dict:
    """Build the profile update dict to pass to somna_agent.update_profile()."""
    update = {
        "iaf_hz": round(iaf_hz, 2),
        "iaf_calibrated_at": datetime.now().isoformat(),
        "iaf_method": "paf_with_cog_fallback",
        "iaf_band_boundaries": {
            "delta": [0.5, round(iaf_hz - 6, 2)],
            "theta": [round(iaf_hz - 6, 2), round(iaf_hz - 2, 2)],
            "alpha": [round(iaf_hz - 2, 2), round(iaf_hz + 2, 2)],
            "beta": [round(iaf_hz + 2, 2), 30.0],
            "gamma": [30.0, 100.0],
        },
    }
    if iaf_confidence is not None:
        update["iaf_confidence"] = round(float(iaf_confidence), 3)
    return update


# ── EEG Engine ────────────────────────────────────────────────────────────────


class EEGEngine:
    """BrainFlow-based EEG acquisition and processing thread.

    Writes the following keys to live_control.json every ~1 second:
        eeg_connected, eeg_quality, eeg_confidence,
        eeg_sqi_tp9, eeg_sqi_af7, eeg_sqi_af8, eeg_sqi_tp10,
        eeg_sqi_composite, eeg_sqi_usable_channels,
        eeg_dominant_band, eeg_delta, eeg_theta, eeg_alpha,
        eeg_beta, eeg_gamma, eeg_gamma_40hz,
        eeg_alpha_theta_ratio, eeg_beta_alpha_ratio,
        eeg_frontal_asymmetry, eeg_trance_score, eeg_state,
        eeg_iaf_hz, eeg_sef95, eeg_spectral_slope,
        eeg_entrainment_strength, eeg_entrainment_confidence,
        eeg_entrainment_trend, eeg_entrainment_beat_freq,
        eeg_entrainment_channel_agreement,
        eeg_entrainment_recommend_modality,
        eeg_timestamp

    Usage:
        engine = EEGEngine(config_dict)
        engine.start()
        ...
        engine.stop()
    """

    def __init__(self, config: dict):
        """
        config keys:
            eeg_synthetic (bool)  — True = SYNTHETIC_BOARD
            eeg_board_id  (int)   — 38 = MUSE_2_BOARD, 39 = MUSE_S_BOARD
        """
        try:
            from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds

            self._BoardShim = BoardShim
            self._BrainFlowInputParams = BrainFlowInputParams
            self._BoardIds = BoardIds
        except ImportError as e:
            raise ImportError(
                "brainflow is not installed. Run: pip install brainflow"
            ) from e

        synthetic = bool(config.get("synthetic", config.get("eeg_synthetic", True)))
        if synthetic:
            self.board_id = self._BoardIds.SYNTHETIC_BOARD.value
        else:
            self.board_id = int(config.get("board_id", config.get("eeg_board_id", 38)))
        self.params = self._BrainFlowInputParams()
        serial_port = config.get("serial_port")
        if serial_port:
            self.params.serial_port = str(serial_port)
        self.board = None
        self._stop = threading.Event()
        self._thread = None  # type: threading.Thread

        # Circular buffer: 5 minutes of 1-Hz samples for trend analysis
        self.history: deque = deque(maxlen=300)

        # Calibration state written by control_panel callback
        self._calibrating = False
        self._calibration_data: list = []
        self._calibration_done = threading.Event()
        # Shared calibration status — written by calibration thread,
        # merged into live_control.json by the main loop (one writer).
        self._cal_state: dict = {}

        # IAF and FAA baseline loaded from profile at startup
        self._iaf_hz: float | None = None
        profile = _load_profile()
        if profile.get("iaf_hz"):
            self._iaf_hz = float(profile["iaf_hz"])

        faa_baseline_mean = profile.get("faa_baseline_mean")
        if faa_baseline_mean is not None:
            approach = round(float(faa_baseline_mean) + 0.10, 4)
            withdraw = round(float(faa_baseline_mean) - 0.10, 4)
            # Will be set on the tracker after it is created below

        # EMA smoothing state for SEF95 and spectral slope (tau ≈ 4 s at 1 Hz tick)
        self._ema_sef95: float | None = None
        self._ema_slope: float | None = None
        self._EMA_ALPHA = 0.25  # ~4 s time constant at 1 Hz

        # Bible Ch.2 §2.8 — Interhemispheric coherence state
        # Rolling 2-second buffer per channel (4 ch × 512 samples at 256 Hz)
        self._coh_buffer: np.ndarray = np.zeros((4, 512))
        self._coh_buffer_ready: bool = False
        self._coh_ticks: int = 0
        self._ema_coh_depth: float | None = None
        self._slope_confidence: float = 0.0
        # Baseline slope from calibration; default -1.3 (typical alert wakefulness)
        self._baseline_slope: float = (
            float(profile.get("baseline_slope", -1.3))
            if profile.get("baseline_slope")
            else -1.3
        )
        # Per-user weight vector for the three-axis composite (updated by SessionAnalyzer)
        self._depth_weights: tuple = (0.40, 0.30, 0.30)

        # ── SQI, ASSR, and FAA trackers (Bible Ch.5 §5.3 / Bible Ch.5 §5.4 / Bible Ch.6 §6.1) ──────────────
        self._sqi_tracker = SQITracker(alpha=0.3)
        self._assr_tracker = ASSRTracker(min_window_seconds=60, update_interval=30)
        self._faa_tracker = FAATracker()
        # Apply stored FAA thresholds from profile (if available)
        if faa_baseline_mean is not None:
            self._faa_tracker.set_thresholds(approach, withdraw)
        self._last_sqi_smoothed: dict = {}
        self._last_sqi_confidence: str = "none"
        self._prev_sqi_confidence: str = (
            "none"  # for phase_gate auto-enable edge detection
        )
        self._session_start_wall: float = 0.0
        self._faa_baseline_emitted: bool = False  # True after first live_control write
        self._depth_log_last: float = 0.0  # throttle: log depth estimate every 10 s

        # Time-series buffers for post-session scoring (Bible Ch.6 §6.3)
        self._series_sef95: list[float] = []
        self._series_assr: list[float] = []
        self._series_faa: list[float] = []
        self._series_sqi: list[float] = []

        # GENUS entrainment ratio tracking (genus_protocol.md §5.3)
        # Pre-GENUS baseline captured during first 60 s of genus_active window.
        self._genus_baseline_40hz: float = 0.0
        self._genus_baseline_samples: list[float] = []
        self._genus_baseline_done: bool = False
        self._genus_was_active: bool = False

        # Optional VR SSVEP plugin (set by Conductor when VR is active)
        self._vr_ssvep_plugin = None

        # Bible Ch.2 §2.9 — PPG and IMU engines (None on synthetic board)
        self._ppg = None
        self._imu = None

        # ── Phase-cascade plugins (Bible Ch.4 §4.6) ────────────────────────────────────
        from eeg.phase_tracker import PhaseTracker
        from eeg.respiratory_tracker import RespiratoryTracker
        from eeg.pac_estimator import PACEstimator

        iaf_for_tracker = self._iaf_hz if self._iaf_hz else 10.0
        self._phase_tracker = PhaseTracker(srate=256, iaf_hz=iaf_for_tracker)
        # Delta PhaseTracker (Bible Ch.7 §7.1): 8 s buffer for reliable 0.5–1.5 Hz estimation
        self._delta_tracker = PhaseTracker(
            srate=256, iaf_hz=iaf_for_tracker, buffer_sec=8.0
        )
        self._resp_tracker = RespiratoryTracker(
            breath_rate=float(_read_live().get("breath_rate", 0.10) or 0.10)
        )
        self._pac_estimator = PACEstimator(srate=256)
        # Long rolling buffer for PAC (up to 30 s at 256 Hz = 7680 samples)
        self._pac_buffer: np.ndarray = np.zeros(256 * 30)
        self._pac_last_breath_rate: float = 0.0

        # ── Sleep stage classifier + spindle detector (Bible Ch.7 §7.1) ────────────────
        from eeg.sleep_classifier import SleepStageClassifier
        from eeg.spindle_detector import SpindleDetector

        self._sleep_classifier = SleepStageClassifier()
        self._spindle_detector = SpindleDetector()
        # Wake beta baseline — set once during CALIBRATION phase
        self._wake_beta_baseline: float | None = None
        # Throttle: log sleep stage every 30 s (one entry per 30-s epoch ≈ 960 rows/8 h)
        self._sleep_log_last: float = 0.0
        # Alpha anti-phase burst tracking
        self._alpha_disrupt_last_ts: float = 0.0
        # Gamma verification gate — created once; self-resets via genus_active flag
        from eeg.gamma_verification_gate import GammaVerificationGate

        self._genus_gate = GammaVerificationGate()

    # ── VR plugin interface ────────────────────────────────────────────────────

    def notify_conductor_phase(self, phase_name: str) -> None:
        """Called by Conductor on FSM state transition to adapt the respiratory hot window."""
        self._resp_tracker.set_conductor_phase(phase_name)

    def register_ssvep_plugin(self, plugin) -> None:
        """Attach an SSVEPDetector that receives raw AF7/AF8 samples each tick.

        Call before the session starts.  Pass None to detach.
        The plugin's update_batch() and detect() are called in the EEG thread —
        no locking needed (single writer for live_control.json).
        """
        self._vr_ssvep_plugin = plugin

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="EEGEngine")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._release_board()
        patch_live({"eeg_connected": False})

    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()

    _BOARD_NAMES = {
        -1: "Synthetic",
        22: "Muse 2 (BLED)",
        38: "Muse 2",
        39: "Muse S",
        45: "Muse S (BLED)",
    }

    def _device_name(self) -> str:
        return self._BOARD_NAMES.get(self.board_id, f"Board {self.board_id}")

    def _release_board(self) -> None:
        if self.board is None:
            return
        try:
            from brainflow.board_shim import BrainFlowError

            if self.board.is_prepared():
                try:
                    self.board.stop_stream()
                except Exception:
                    pass
                try:
                    self.board.release_session()
                except BrainFlowError:
                    self._BoardShim.release_all_sessions()
        except Exception:
            pass
        self.board = None

    # ── Main thread ───────────────────────────────────────────────────────────

    def _run(self) -> None:
        from brainflow.board_shim import BrainFlowError, BrainFlowInputParams

        max_retries = 3
        for attempt in range(max_retries):
            if self._stop.is_set():
                return
            try:
                self.board = self._BoardShim(self.board_id, self.params)
                self.board.prepare_session()
                # Muse 2: enable ANCILLARY preset for PPG before start_stream
                if self.board_id in (22, 38):
                    try:
                        resp = self.board.config_board("p50")
                        print(f"[EEG] config_board p50 response: {resp}")
                    except Exception as cb_e:
                        print(f"[EEG] config_board p50 failed: {cb_e}")
                elif self.board_id in (39, 45):
                    try:
                        resp = self.board.config_board("p61")
                        print(f"[EEG] config_board p61 response: {resp}")
                    except Exception as cb_e:
                        print(f"[EEG] config_board p61 failed: {cb_e}")
                self.board.start_stream(450_000)
                break
            except Exception as e:
                print(
                    f"[EEG] Connection attempt {attempt + 1}/{max_retries} failed: {e}"
                )
                self._release_board()
                if attempt < max_retries - 1:
                    wait_s = 10 if self.params.serial_port else 5
                    self._stop.wait(timeout=wait_s * (attempt + 1))
        else:
            print("[EEG] Could not connect — giving up.")
            patch_live({"eeg_connected": False, "eeg_quality": "unusable"})
            return

        # Spin up PPG and IMU engines for real hardware (not synthetic)
        if self.board_id != -1:
            try:
                from eeg.ppg_engine import PPGEngine

                self._ppg = PPGEngine()
                print("[EEG] PPG engine started.")
            except Exception as ppg_e:
                print(f"[EEG] PPG engine unavailable: {ppg_e}")
            try:
                from eeg.imu_engine import IMUEngine

                self._imu = IMUEngine()
                print("[EEG] IMU engine started.")
            except Exception as imu_e:
                print(f"[EEG] IMU engine unavailable: {imu_e}")

        device_name = self._device_name()
        patch_live(
            {
                "eeg_connected": True,
                "eeg_device_name": device_name,
                "eeg_quality": "good",
                "eeg_confidence": "none",
                "eeg_entrainment_confidence": "unavailable",
                "eeg_entrainment_strength": 0.0,
                "eeg_entrainment_trend": "insufficient_data",
            }
        )
        print(f"[EEG] Connected — board_id={self.board_id}  device={device_name}")

        eeg_channels = self._BoardShim.get_eeg_channels(self.board_id)
        sampling_rate = self._BoardShim.get_sampling_rate(self.board_id)
        window = sampling_rate  # 1-second window

        # Publish IAF from profile if available
        if self._iaf_hz is not None:
            patch_live(
                {
                    "eeg_iaf_hz": self._iaf_hz,
                    "eeg_needs_iaf_calibration": False,
                }
            )
        else:
            patch_live({"eeg_needs_iaf_calibration": True})

        # Reset per-session trackers and scoring buffers
        self._sqi_tracker.reset_session()
        self._assr_tracker.reset_session()
        self._faa_tracker.reset()
        self._series_sef95.clear()
        self._series_assr.clear()
        self._series_faa.clear()
        self._series_sqi.clear()
        self._session_start_wall = time.time()
        self._faa_baseline_emitted = False
        _stale_ticks = 0
        _STALE_SIGNAL_LOST = 3
        _STALE_RECONNECT = 10
        _STALE_ALREADY_REPORTED = False

        while not self._stop.is_set():
            try:
                data = self.board.get_current_board_data(window)
                if data.shape[1] < window:
                    _stale_ticks += 1

                    if (
                        _stale_ticks == _STALE_SIGNAL_LOST
                        and not _STALE_ALREADY_REPORTED
                    ):
                        _STALE_ALREADY_REPORTED = True
                        print(
                            f"[EEG] No data for {_STALE_SIGNAL_LOST}s — "
                            f"signal lost, clearing stale values"
                        )
                        patch_live(
                            {
                                "eeg_signal_lost": True,
                                "ppg_available": False,
                                "ppg_heart_rate": None,
                                "ppg_hrv_rmssd": None,
                                "ppg_breath_rate": None,
                                "ppg_breath_phase": None,
                                "ppg_cardiac_phase": None,
                                "ppg_cardiac_diastole": None,
                                "ppg_last_peak_age_ms": None,
                                "ppg_autonomic_depth": None,
                                "imu_motion_rms": None,
                                "imu_stillness_index": None,
                                "imu_motion_contaminated": False,
                                "imu_head_nod_detected": False,
                            }
                        )

                    if _stale_ticks >= _STALE_RECONNECT:
                        raise RuntimeError(
                            f"Stream frozen for {_STALE_RECONNECT}s — forcing reconnect"
                        )

                    self._stop.wait(timeout=1.0)
                    continue

                if _stale_ticks > 0:
                    print(f"[EEG] Data recovered after {_stale_ticks}s stale period")
                    patch_live({"eeg_signal_lost": False})
                _stale_ticks = 0
                _STALE_ALREADY_REPORTED = False

                eeg_data = data[eeg_channels]

                # Accumulate calibration data if requested
                if self._calibrating:
                    self._calibration_data.append(eeg_data.copy())

                # ── IMU tick (Bible Ch.2 §2.9) — runs before _process so gate knows ────
                # about motion before EEG metrics are written.
                if self._imu is not None:
                    imu_state = self._imu.tick(self.board, self.board_id)
                    if imu_state:
                        patch_live(imu_state)
                        # Cache for _process() so SQI degradation sees current motion
                        self._imu_contaminated_cache = bool(
                            imu_state.get("imu_motion_contaminated", False)
                        )

                # ── 1s processing cycle ───────────────────────────────────────
                state = self._process(eeg_data, eeg_channels, sampling_rate)
                if self._cal_state:
                    state.update(self._cal_state)
                patch_live(state)
                self.history.append(state)

                # ── PPG tick (Bible Ch.2 §2.9) — runs after EEG so it doesn't delay ────
                # the main 1 s cycle if the ANCILLARY read is slow.
                if self._ppg is not None:
                    ppg_state = self._ppg.tick(self.board, self.board_id)
                    if ppg_state:
                        patch_live(ppg_state)
                        # Hand real breath phase to RespiratoryTracker
                        if ppg_state.get("ppg_available") and ppg_state.get(
                            "ppg_breath_rate"
                        ):
                            self._resp_tracker.update_ppg_phase(
                                float(ppg_state["ppg_breath_phase"]),
                                float(ppg_state["ppg_breath_rate"]),
                            )

                # ── GENUS entrainment verification (genus_protocol.md §5.3) ──
                # Gate is persistent — update() self-resets when genus_active is False,
                # preserving ratio_history and above_moderate_ticks across brief toggles.
                self._genus_gate.update(state)

                # ── Phase gate auto-enable (Bible Ch.4 §4.6) ───────────────────────────
                # When SQI crosses into usable territory for the first time this
                # session, enable phase-gated delivery automatically so the user
                # never has to set phase_gate_enabled manually.
                # Crossing back to low/none disables it to prevent false gates.
                new_conf = self._last_sqi_confidence
                if new_conf != self._prev_sqi_confidence:
                    if new_conf in ("full", "reduced"):
                        live_for_gate = _read_live()
                        if not live_for_gate.get("phase_gate_enabled"):
                            patch_live({"phase_gate_enabled": True})
                            print("[EEG] SQI sufficient — phase gate enabled.")
                    elif new_conf in ("low", "none") and self._prev_sqi_confidence in (
                        "full",
                        "reduced",
                    ):
                        patch_live({"phase_gate_enabled": False})
                        print(
                            f"[EEG] SQI degraded to {new_conf!r} — phase gate disabled."
                        )
                    self._prev_sqi_confidence = new_conf

                # ── VR SSVEP plugin (Bible Ch.8 §8.1) ──────────────────────────────────
                if self._vr_ssvep_plugin is not None:
                    # AF7=index 1, AF8=index 2 in Muse 2 channel order
                    self._vr_ssvep_plugin.update_batch(eeg_data[1], eeg_data[2])
                    live_cfg = _read_live()
                    f_l = float(live_cfg.get("vr_rivalry_left_hz", 0.0))
                    f_r = float(live_cfg.get("vr_rivalry_right_hz", 0.0))
                    if f_l > 0.0 and f_r > 0.0:
                        self._vr_ssvep_plugin.detect(f_l, f_r)

                # ── VR paroxysmal buffer (Bible Ch.8 §8.1 §8) ─────────────────────────
                # Write the last 256 raw AF7 samples so vr_display_runner.py
                # can feed check_paroxysmal() without a second BrainFlow connection.
                # Only written when VR headset is active to avoid constant disk I/O.
                if state.get("eeg_connected") and _read_live().get("vr_headset_active"):
                    patch_live(
                        {
                            "eeg_raw_af7_last_256": eeg_data[1, -256:].tolist(),
                            "eeg_raw_af8_last_256": eeg_data[2, -256:].tolist(),
                        }
                    )

                # ── Phase-cascade tracking (Bible Ch.4 §4.6) ───────────────────────────
                # AF7 (index 1) is the primary frontal channel for phase estimation.
                af7 = eeg_data[1]
                now_mono = time.monotonic()

                # Push samples into rolling phase buffers (alpha/theta + delta)
                self._phase_tracker.push_samples(af7)
                self._delta_tracker.push_samples(af7)

                # Keep PAC long buffer updated (roll and append)
                n_new = len(af7)
                self._pac_buffer = np.roll(self._pac_buffer, -n_new)
                self._pac_buffer[-n_new:] = af7

                # Sync respiratory tracker with live breath_rate whenever it changes
                live_for_resp = _read_live()
                br = float(live_for_resp.get("breath_rate", 0.10) or 0.10)
                if br != self._pac_last_breath_rate:
                    self._resp_tracker.update_breath_rate(br)
                    self._pac_last_breath_rate = br

                # Sync IAF with latest calibration
                current_iaf = float(live_for_resp.get("eeg_iaf_hz", 0) or 0)
                if (
                    current_iaf > 0
                    and abs(current_iaf - self._phase_tracker.iaf_hz) > 0.05
                ):
                    self._phase_tracker.update_iaf(current_iaf)

                # Phase estimation at ~10 Hz (PhaseTracker rate-limits internally)
                phase_result = self._phase_tracker.estimate_both(now=now_mono)
                resp_state = self._resp_tracker.state_dict()

                phase_patch = {
                    "alpha_phase": phase_result["alpha_phase"],
                    "alpha_phase_confidence": phase_result["alpha_confidence"],
                    "alpha_at_trough": phase_result["alpha_at_trough"],
                    "theta_phase": phase_result["theta_phase"],
                }
                phase_patch.update(resp_state)
                patch_live(phase_patch)

                # Delta phase tracking for slow-wave up-state detection (Bible Ch.7 §7.1 §6)
                delta_result = self._delta_tracker.estimate_phase("delta", now=now_mono)
                if delta_result.get("phase") is not None:
                    d_phase = delta_result["phase"]
                    # Up-state = phase near 0 (surface-positive peak), tolerance 0.3 rad
                    d_in_gate = abs(d_phase) < 0.3 or abs(d_phase - 2 * np.pi) < 0.3
                    patch_live(
                        {
                            "eeg_delta_phase": round(float(d_phase), 4),
                            "eeg_delta_in_gate": bool(d_in_gate),
                            "eeg_delta_amplitude": round(
                                float(delta_result.get("amplitude", 0.0)), 4
                            ),
                        }
                    )

                # PAC estimation at ~0.5 Hz (PACEstimator rate-limits internally)
                iaf = self._phase_tracker.iaf_hz
                pac_patch = self._pac_estimator.compute_all(
                    self._pac_buffer, iaf=iaf, now=now_mono
                )
                if pac_patch:
                    patch_live(pac_patch)

                # Accumulate time-series for post-session scoring (Bible Ch.6 §6.3)
                if state.get("eeg_sef95") is not None:
                    self._series_sef95.append(state["eeg_sef95"])
                if state.get("eeg_entrainment_strength") is not None:
                    self._series_assr.append(state.get("eeg_entrainment_strength", 0.0))
                if state.get("eeg_faa") is not None:
                    self._series_faa.append(state["eeg_faa"])
                if state.get("eeg_sqi_composite") is not None:
                    self._series_sqi.append(state["eeg_sqi_composite"])

                # ── Depth estimate logging (Bible Ch.2 §2.8) ───────────────────────────
                # Throttled to 10 s: ~240 rows for a 40-min session.  Dense
                # enough for per-phase trend analysis; sparse enough to stay lean.
                # Only logs when coherence data is available (slope + v2 score).
                now_ts = time.time()
                if (
                    now_ts - self._depth_log_last >= 10.0
                    and state.get("eeg_trance_score_v2") is not None
                ):
                    try:
                        from content_tools.somna_db import log_depth_estimate

                        live_snap = _read_live()
                        log_depth_estimate(
                            session_id=str(live_snap.get("session_name") or "unknown"),
                            ts=now_ts,
                            conductor_phase=str(live_snap.get("conductor_phase") or ""),
                            spectral_slope=state.get("eeg_spectral_slope"),
                            slope_confidence=state.get("eeg_slope_confidence"),
                            frontal_alpha_coh=state.get("eeg_coherence_frontal_alpha"),
                            frontal_beta_coh=state.get("eeg_coherence_frontal_beta"),
                            temporal_theta_coh=state.get(
                                "eeg_coherence_temporal_theta"
                            ),
                            beta_env_corr=state.get("eeg_beta_env_corr"),
                            coherence_depth=state.get("eeg_coherence_depth"),
                            trance_score_v1=state.get("eeg_trance_score"),
                            trance_score_v2=state.get("eeg_trance_score_v2"),
                        )
                        self._depth_log_last = now_ts
                    except Exception:
                        pass

                # ── Sleep stage classifier + spindle detector (Bible Ch.7 §7.1) ────────
                # Runs every tick on features already computed above.
                # Needs the _process state dict for band powers.
                now_ts = now_ts  # reuse from depth log block above
                _live_snap_sleep = _read_live()
                conductor_phase_name = str(
                    _live_snap_sleep.get("conductor_phase") or ""
                )

                # Capture wake beta baseline during CALIBRATION for beta_dropout
                beta_ratio = float(state.get("eeg_beta", 0.0) or 0.0)
                if (
                    "calibrat" in conductor_phase_name
                    and self._wake_beta_baseline is None
                ):
                    self._wake_beta_baseline = beta_ratio
                    self._sleep_classifier.set_wake_baseline(beta_ratio)

                beta_dropout = (
                    self._wake_beta_baseline is not None
                    and self._wake_beta_baseline > 1e-9
                    and beta_ratio < self._wake_beta_baseline * 0.15
                )

                # Spindle detection on frontal channels
                if eeg_data.shape[0] >= 3:
                    sp_result = self._spindle_detector.detect(
                        epoch_af7=eeg_data[1],
                        epoch_af8=eeg_data[2],
                        timestamp=now_ts,
                    )
                else:
                    sp_result = {
                        "spindle_detected": False,
                        "spindle_density": 0.0,
                        "sigma_amplitude": 0.0,
                    }

                # Sleep stage classification
                sleep_features = {
                    "spectral_slope": state.get("eeg_spectral_slope", -1.5),
                    "delta_power_ratio": float(state.get("eeg_delta", 0.0) or 0.0),
                    "theta_power_ratio": float(state.get("eeg_theta", 0.0) or 0.0),
                    "alpha_power_ratio": float(state.get("eeg_alpha", 0.0) or 0.0),
                    "spindle_density": sp_result["spindle_density"],
                    "beta_dropout": beta_dropout,
                }
                sleep_stage, sleep_conf = self._sleep_classifier.classify(
                    sleep_features
                )

                patch_live(
                    {
                        "eeg_sleep_stage": sleep_stage,
                        "eeg_sleep_confidence": round(float(sleep_conf), 3),
                        "spindle_density": sp_result["spindle_density"],
                        "sigma_amplitude": round(
                            float(sp_result["sigma_amplitude"]), 4
                        ),
                    }
                )

                # Throttled sleep stage logging (30 s → ≈960 rows per 8-hour session)
                if now_ts - self._sleep_log_last >= 30.0:
                    try:
                        from content_tools.somna_db import log_sleep_stage

                        log_sleep_stage(
                            session_id=str(
                                _live_snap_sleep.get("session_name") or "unknown"
                            ),
                            ts=now_ts,
                            stage=sleep_stage,
                            confidence=sleep_conf,
                            spectral_slope=state.get("eeg_spectral_slope"),
                            delta_power=sleep_features["delta_power_ratio"],
                            spindle_density=sp_result["spindle_density"],
                            sigma_amplitude=sp_result["sigma_amplitude"],
                        )
                        self._sleep_log_last = now_ts
                    except Exception:
                        pass

                # Emit FAA resting baseline once it becomes ready (Bible Ch.6 §6.1)
                # The agent reads eeg_faa_baseline_ready and persists to user_profile.
                if not self._faa_baseline_emitted:
                    bl = self._faa_tracker.get_baseline()
                    if bl is not None:
                        patch_live(
                            {
                                "eeg_faa_baseline_mean": bl["faa_baseline_mean"],
                                "eeg_faa_baseline_std": bl["faa_baseline_std"],
                                "eeg_faa_baseline_ready": True,
                            }
                        )
                        self._faa_baseline_emitted = True
                        print(
                            f"[EEG] FAA resting baseline ready: "
                            f"mean={bl['faa_baseline_mean']:.4f}  "
                            f"std={bl['faa_baseline_std']:.4f}  "
                            f"thresholds: approach>{self._faa_tracker._approach_thresh:.3f}  "
                            f"withdraw<{self._faa_tracker._withdraw_thresh:.3f}"
                        )

                # ── Headband prompt when SQI critically low ───────────────────
                if self._sqi_tracker.should_headband_prompt():
                    cur = state.get("agent_message") or {}
                    if not (isinstance(cur, dict) and cur.get("needs_response")):
                        patch_live(
                            {
                                "agent_message": {
                                    "text": "The headband may need a small adjustment. "
                                    "When you're ready, gently press it snug "
                                    "against your forehead.",
                                    "ts": time.time(),
                                    "needs_response": False,
                                    "via": ["console", "tts"],
                                    "style": {
                                        "voice_mode": "tts",
                                        "intensity": "soft",
                                        "needs_response": False,
                                    },
                                    "timeout_s": None,
                                }
                            }
                        )

                # ── ASSR update (every 30s, 60s window, full SQI only) ─────────
                session_elapsed = time.time() - self._session_start_wall
                if (
                    self._last_sqi_confidence == "full"
                    and self._assr_tracker.should_update(session_elapsed)
                ):
                    self._assr_update(eeg_channels, sampling_rate, session_elapsed)

                self._stop.wait(timeout=1.0)

            except Exception as e:
                print(f"[EEG] Stream error: {e} — reconnecting")
                patch_live({"eeg_connected": False, "eeg_quality": "unusable"})
                self._stop.wait(timeout=5.0)
                if self._stop.is_set():
                    break
                # Release the dead session and re-establish BLE connection
                self._release_board()
                reconnected = False
                for attempt in range(3):
                    if self._stop.is_set():
                        break
                    try:
                        self.board = self._BoardShim(self.board_id, self.params)
                        self.board.prepare_session()
                        if self.board_id in (22, 38):
                            try:
                                self.board.config_board("p50")
                            except Exception:
                                pass
                        elif self.board_id in (39, 45):
                            try:
                                self.board.config_board("p61")
                            except Exception:
                                pass
                        self.board.start_stream(450_000)
                        reconnected = True
                        self._sqi_tracker._warmup_ctr = SQITracker._WARMUP_TICKS
                        if self._ppg is not None:
                            self._ppg.reset()
                        if self._imu is not None:
                            self._imu.reset()
                        print(f"[EEG] Reconnected on attempt {attempt + 1}.")
                        patch_live(
                            {
                                "eeg_connected": True,
                                "eeg_signal_lost": False,
                                "ppg_available": False,
                            }
                        )
                        break
                    except Exception as re:
                        print(f"[EEG] Reconnect attempt {attempt + 1}/3 failed: {re}")
                        self._release_board()
                        self._stop.wait(timeout=5.0)
                if not reconnected and not self._stop.is_set():
                    print("[EEG] Could not reconnect — giving up.")
                    patch_live({"eeg_connected": False, "eeg_quality": "unusable"})
                    break

        self._release_board()

    # ── Processing ────────────────────────────────────────────────────────────

    def _process(
        self, eeg_data: np.ndarray, eeg_channels: list, sampling_rate: int
    ) -> dict:
        """Compute SQI, gate downstream metrics, return live_control patch dict."""
        from brainflow.data_filter import DataFilter, DetrendOperations

        # ── Step 1: SQI on raw data (before any filtering) ────────────────────
        n_ch = min(4, eeg_data.shape[0])
        raw_sqi = {}
        for i in range(n_ch):
            raw_sqi[_CH_NAMES[i]] = compute_channel_sqi(eeg_data[i], sampling_rate)
        # Fill missing channels with 0
        for ch in _CH_NAMES:
            raw_sqi.setdefault(ch, 0.0)

        smoothed, confidence = self._sqi_tracker.update(raw_sqi)
        self._last_sqi_smoothed = smoothed
        self._last_sqi_confidence = confidence

        composite = round(float(np.mean(list(smoothed.values()))), 3)
        usable = sum(1 for v in smoothed.values() if v >= 0.3)

        # Bible Ch.2 §2.9 §5.1 — IMU-aware SQI degradation.
        # Head movement introduces muscle artifact and electrode displacement noise.
        # When IMU reports contamination, halve the composite confidence so downstream
        # consumers (phase gate, conductor) treat depth estimates conservatively.
        # _imu_contaminated_cache is set by the IMU tick in _run() before _process().
        motion_contaminated = getattr(self, "_imu_contaminated_cache", False)
        if motion_contaminated:
            composite = round(composite * 0.5, 3)
        self._suppress_trance_update = motion_contaminated

        warming_up = self._sqi_tracker._warmup_ctr > 0
        quality_str = (
            "warming"
            if warming_up
            else {
                "full": "good",
                "reduced": "good",
                "low": "poor",
                "none": "unusable",
            }.get(confidence, "poor")
        )

        signal_lost = confidence == "none"
        base = {
            "eeg_connected": True,
            "eeg_quality": quality_str,
            "eeg_confidence": confidence,
            "eeg_sqi_tp9": smoothed["tp9"],
            "eeg_sqi_af7": smoothed["af7"],
            "eeg_sqi_af8": smoothed["af8"],
            "eeg_sqi_tp10": smoothed["tp10"],
            "eeg_sqi_composite": composite,
            "eeg_sqi_usable_channels": usable,
            "eeg_timestamp": time.time(),
            # Bible Ch.7 §7.5: safety flag consumed by TMREngine and SlowWaveEnhancer
            "eeg_signal_lost": signal_lost,
        }

        # ── Step 2: Gate downstream metrics ───────────────────────────────────
        if confidence == "none":
            # Nothing trustworthy — return SQI only
            return base

        # ── Step 3: Preprocessing (detrend + bandpass) on clean channels ──────
        try:
            clean = eeg_data.copy()
            for i in range(n_ch):
                if smoothed.get(_CH_NAMES[i], 0.0) >= 0.3:  # use all non-dead channels
                    try:
                        DataFilter.detrend(clean[i], DetrendOperations.LINEAR.value)
                        DataFilter.perform_bandpass(
                            clean[i],
                            sampling_rate,
                            1.0,
                            50.0,
                            4,
                            0,
                            0.0,
                        )
                    except Exception:
                        pass

            # Band powers — only over channels with acceptable SQI
            clean_indices = [
                i for i in range(n_ch) if smoothed.get(_CH_NAMES[i], 0.0) >= 0.3
            ]
            if not clean_indices:
                return base

            bands_result = DataFilter.get_avg_band_powers(
                clean, clean_indices, sampling_rate, True
            )
            delta, theta, alpha, beta, gamma = [float(x) for x in bands_result[0]]
        except Exception:
            return base

        total = delta + theta + alpha + beta + gamma + 1e-12
        delta_n = delta / total
        theta_n = theta / total
        alpha_n = alpha / total
        beta_n = beta / total
        gamma_n = gamma / total

        # Narrow-band 40 Hz (GENUS monitoring — genus_protocol.md §5.3)
        gamma_40hz = 0.0
        genus_ratio = 1.0
        try:
            g40 = DataFilter.get_custom_band_powers(
                clean,
                [(38.0, 42.0)],
                clean_indices,
                sampling_rate,
                True,
            )
            gamma_40hz = float(g40[0][0]) if g40 else 0.0
        except Exception:
            pass

        # Entrainment ratio: computed only while genus_active
        # We read live_control here (cached reference is the base dict we're building on top of)
        genus_active = bool(base.get("genus_active", False))
        if not genus_active:
            # Reset baseline state so next GENUS session captures fresh baseline
            if self._genus_was_active:
                self._genus_baseline_samples = []
                self._genus_baseline_done = False
                self._genus_baseline_40hz = 0.0
                self._genus_was_active = False
        else:
            self._genus_was_active = True
            if not self._genus_baseline_done:
                # Accumulate baseline for first 60 s (up to 30 samples at ~2 s each)
                self._genus_baseline_samples.append(gamma_40hz)
                if len(self._genus_baseline_samples) >= 30:
                    raw = [x for x in self._genus_baseline_samples if x > 0]
                    self._genus_baseline_40hz = float(np.mean(raw)) if raw else 1e-9
                    self._genus_baseline_done = True
            if self._genus_baseline_done and self._genus_baseline_40hz > 0:
                genus_ratio = gamma_40hz / max(self._genus_baseline_40hz, 1e-9)

        # Frontal asymmetry: ln(AF8) − ln(AF7)
        # Muse 2/S: ch0=TP9, ch1=AF7, ch2=AF8, ch3=TP10
        frontal_asym = 0.0
        af7_ok = smoothed.get("af7", 0.0) >= 0.3
        af8_ok = smoothed.get("af8", 0.0) >= 0.3
        if af7_ok and af8_ok and eeg_data.shape[0] >= 3:
            try:
                af7_pow = float(np.mean(clean[1] ** 2))
                af8_pow = float(np.mean(clean[2] ** 2))
                if af7_pow > 0 and af8_pow > 0:
                    frontal_asym = float(np.log(af8_pow) - np.log(af7_pow))
            except Exception:
                pass

        alpha_theta = alpha_n / (theta_n + 1e-12)
        beta_alpha = beta_n / (alpha_n + 1e-12)

        # ── Step 4: SEF95 + spectral slope (reduced or full confidence) ───────
        sef95: float | None = None
        spectral_slope: float | None = None
        if confidence in ("reduced", "full"):
            try:
                from brainflow.data_filter import WindowOperations

                nfft_sef = DataFilter.get_nearest_power_of_two(sampling_rate)
                if (
                    nfft_sef >= sampling_rate
                ):  # get_psd_welch requires nfft < data_len strictly
                    nfft_sef //= 2
                channel_psds = []
                for i in clean_indices:
                    try:
                        psd_vals, psd_freqs = DataFilter.get_psd_welch(
                            clean[i].copy(),
                            nfft_sef,
                            nfft_sef // 2,
                            sampling_rate,
                            WindowOperations.HAMMING.value,
                        )
                        channel_psds.append((psd_vals, psd_freqs))
                    except Exception:
                        pass

                if channel_psds:
                    avg_psd = np.mean([p[0] for p in channel_psds], axis=0)
                    freqs_sef = channel_psds[0][1]

                    mask_sef = freqs_sef >= 0.5
                    p_sef = avg_psd[mask_sef]
                    f_sef = freqs_sef[mask_sef]
                    if len(p_sef) > 0:
                        cum = np.cumsum(p_sef)
                        idx = int(np.searchsorted(cum, 0.95 * cum[-1]))
                        sef95 = float(f_sef[min(idx, len(f_sef) - 1)])

                    mask_slope = (freqs_sef >= 2.0) & (freqs_sef <= 30.0)
                    lf = np.log10(freqs_sef[mask_slope])
                    lp = np.log10(avg_psd[mask_slope] + 1e-10)
                    if len(lf) >= 4:
                        slope_val, _ = np.polyfit(lf, lp, 1)
                        spectral_slope = float(slope_val)
            except Exception:
                pass

        # EMA smoothing
        if sef95 is not None:
            self._ema_sef95 = (
                sef95
                if self._ema_sef95 is None
                else self._ema_sef95 + self._EMA_ALPHA * (sef95 - self._ema_sef95)
            )
        if spectral_slope is not None:
            self._ema_slope = (
                spectral_slope
                if self._ema_slope is None
                else self._ema_slope
                + self._EMA_ALPHA * (spectral_slope - self._ema_slope)
            )

        # ── Step 4b: Interhemispheric coherence (Bible Ch.2 §2.8) ──────────────────────
        # Update the rolling 2-second buffer with clean (detrended+bandpass) data.
        # The buffer is [4 ch × 512 samples]: ch0=TP9, ch1=AF7, ch2=AF8, ch3=TP10
        frontal_coh_result = {"alpha_coh": 0.5, "theta_coh": 0.5, "beta_coh": 0.5}
        temporal_coh_result = {"theta_coh": 0.5}
        beta_env_corr_val = 1.0
        coh_depth_val = 0.0
        if n_ch >= 2:
            n_new = clean.shape[1]
            buf_len = self._coh_buffer.shape[1]
            roll_by = min(n_new, buf_len)
            self._coh_buffer = np.roll(self._coh_buffer, -roll_by, axis=1)
            n_write = min(clean.shape[0], 4)
            self._coh_buffer[:n_write, -roll_by:] = clean[:n_write, :roll_by]
            self._coh_ticks += 1
            if self._coh_ticks >= 2:
                self._coh_buffer_ready = True

        if confidence in ("reduced", "full") and self._coh_buffer_ready:
            try:
                from eeg.depth_features import (
                    compute_band_coherence,
                    compute_beta_envelope_correlation,
                    coherence_depth_indicator,
                )

                af7_buf = self._coh_buffer[1]
                af8_buf = self._coh_buffer[2]
                tp9_buf = self._coh_buffer[0]
                tp10_buf = self._coh_buffer[3]

                frontal_coh_result = compute_band_coherence(
                    af7_buf, af8_buf, fs=float(sampling_rate)
                )
                temporal_coh_result = compute_band_coherence(
                    tp9_buf, tp10_buf, fs=float(sampling_rate)
                )
                beta_env_corr_val = compute_beta_envelope_correlation(
                    af7_buf, af8_buf, fs=float(sampling_rate)
                )
                coh_depth_val = coherence_depth_indicator(
                    frontal_coh_result["alpha_coh"],
                    beta_env_corr_val,
                    temporal_coh_result["theta_coh"],
                )
            except Exception:
                pass

        # EMA-smooth coherence depth
        if coh_depth_val != 0.0:
            self._ema_coh_depth = (
                coh_depth_val
                if self._ema_coh_depth is None
                else self._ema_coh_depth
                + self._EMA_ALPHA * (coh_depth_val - self._ema_coh_depth)
            )
        # Slope confidence: 1.0 for full, 0.5 for reduced
        self._slope_confidence = (
            1.0 if confidence == "full" else (0.5 if confidence == "reduced" else 0.0)
        )

        # ── Step 5: Trance score ───────────────────────────────────────────────
        def _norm(v, hi, lo):
            return max(0.0, min(1.0, (v - hi) / (lo - hi))) if (lo - hi) != 0 else 0.0

        score_theta_alpha = max(
            0.0, min(1.0, (theta_n + 0.5 * delta_n) / (alpha_n + beta_n + 1e-12) * 0.5)
        )
        if self._ema_sef95 is not None and self._ema_slope is not None:
            trance_score = (
                0.4 * _norm(self._ema_sef95, 25.0, 8.0)
                + 0.3 * _norm(self._ema_slope, -1.0, -3.0)
                + 0.3 * score_theta_alpha
            )
        else:
            trance_score = score_theta_alpha

        # Three-axis composite (Bible Ch.2 §2.8 §5) — published as eeg_trance_score_v2
        # Bible Ch.2 §2.9 §5.1: suppress updates during motion — hold last value to prevent
        # depth score oscillation from brief movements (position adjustments, etc.)
        if getattr(self, "_suppress_trance_update", False):
            trance_score_v2 = getattr(self, "_last_trance_score_v2", trance_score)
        else:
            trance_score_v2 = trance_score  # fallback: v1 until coherence is ready
            if self._ema_slope is not None and self._ema_coh_depth is not None:
                try:
                    from eeg.depth_features import enhanced_trance_score

                    trance_score_v2 = enhanced_trance_score(
                        trance_score,
                        self._ema_slope,
                        self._ema_coh_depth,
                        self._baseline_slope,
                        weights=self._depth_weights,
                    )
                except Exception:
                    pass
            trance_score_v2 = round(max(0.0, min(1.0, trance_score_v2)), 3)
            self._last_trance_score_v2 = trance_score_v2

        # Widen adaptation thresholds at reduced confidence (Bible Ch.5 §5.3 §4.2)
        if confidence == "reduced":
            trance_score = round(
                trance_score, 2
            )  # coarser precision signals lower trust

        trance_score = round(max(0.0, min(1.0, trance_score)), 3)

        # ── Step 6: State classification ──────────────────────────────────────
        if alpha_n > 0.35 and alpha_theta > 1.2:
            eeg_state = "awake"
        elif alpha_n > 0.25 and alpha_theta > 0.8:
            eeg_state = "relaxed"
        elif theta_n > alpha_n and alpha_theta < 0.8:
            eeg_state = "trance" if gamma_n > 0.05 else "n1_entry"
        elif theta_n > 0.35 and alpha_theta < 0.5:
            eeg_state = "n1"
        else:
            eeg_state = "relaxed"

        bands_named = [
            ("delta", delta_n),
            ("theta", theta_n),
            ("alpha", alpha_n),
            ("beta", beta_n),
            ("gamma", gamma_n),
        ]
        dominant = max(bands_named, key=lambda x: x[1])[0]

        # ── FAA (Bible Ch.6 §6.1) — requires reduced or full confidence ────────────────
        faa_result = {
            "eeg_faa": 0.0,
            "eeg_faa_raw": 0.0,
            "eeg_faa_state": "insufficient_data",
        }
        if confidence in ("reduced", "full"):
            faa_result = self._faa_tracker.compute(
                eeg_data,
                sqi_af7=smoothed.get("af7", 0.0),
                sqi_af8=smoothed.get("af8", 0.0),
                sampling_rate=sampling_rate,
            )

        base.update(
            {
                "eeg_dominant_band": dominant,
                "eeg_delta": round(delta_n, 4),
                "eeg_theta": round(theta_n, 4),
                "eeg_alpha": round(alpha_n, 4),
                "eeg_beta": round(beta_n, 4),
                "eeg_gamma": round(gamma_n, 4),
                "eeg_gamma_40hz": round(gamma_40hz, 6),
                "eeg_genus_ratio": round(genus_ratio, 3),
                "eeg_alpha_theta_ratio": round(alpha_theta, 3),
                "eeg_beta_alpha_ratio": round(beta_alpha, 3),
                "eeg_frontal_asymmetry": round(frontal_asym, 4),
                "eeg_trance_score": trance_score,
                "eeg_state": eeg_state,
                "eeg_iaf_hz": self._iaf_hz,
                "eeg_sef95": round(self._ema_sef95, 2)
                if self._ema_sef95 is not None
                else None,
                "eeg_spectral_slope": round(self._ema_slope, 3)
                if self._ema_slope is not None
                else None,
                # Bible Ch.2 §2.8 — three-axis depth markers
                "eeg_slope_confidence": round(self._slope_confidence, 2),
                "eeg_coherence_frontal_alpha": round(
                    frontal_coh_result.get("alpha_coh", 0.5), 4
                ),
                "eeg_coherence_frontal_beta": round(
                    frontal_coh_result.get("beta_coh", 0.5), 4
                ),
                "eeg_coherence_temporal_theta": round(
                    temporal_coh_result.get("theta_coh", 0.5), 4
                ),
                "eeg_beta_env_corr": round(beta_env_corr_val, 4),
                "eeg_coherence_depth": round(self._ema_coh_depth or 0.0, 4),
                "eeg_trance_score_v2": trance_score_v2,
                **faa_result,
            }
        )
        return base

    # ── ASSR ──────────────────────────────────────────────────────────────────

    def _assr_update(
        self, eeg_channels: list, sampling_rate: int, session_elapsed: float
    ) -> None:
        """Compute ASSR entrainment strength and publish to live_control.json.

        Called from the main loop at 30-second intervals when SQI is full.
        Reads a 60-second rolling window from the board.
        """
        try:
            n_samples = 60 * sampling_rate
            data = self.board.get_current_board_data(n_samples)
            if data.shape[1] < n_samples:
                return  # not enough data yet

            live = _read_live()
            beat_freq = float(live.get("beat_frequency", 10.0))
            iaf = self._iaf_hz or 10.0

            # Check for alpha band ambiguity (beat ≈ IAF ± 1 Hz)
            alpha_ambiguous = abs(beat_freq - iaf) < 1.0

            n_ch = min(4, len(eeg_channels))
            ch_results: dict[str, dict] = {}
            w_sum = 0.0
            w_tot = 0.0
            ch_arrays: dict[str, np.ndarray] = {}

            for i in range(n_ch):
                ch_name = _CH_NAMES[i]
                sqi_val = self._last_sqi_smoothed.get(ch_name, 0.0)
                if sqi_val < 0.5:
                    continue  # skip bad channels

                ch_data = data[eeg_channels[i], :]
                ch_arrays[ch_name] = ch_data
                freqs, psd = _assr_welch(ch_data, fs=sampling_rate)
                if len(freqs) == 0:
                    continue

                strength, ratio = _compute_entrainment_strength(freqs, psd, beat_freq)
                w = _CH_WEIGHTS_ASSR[ch_name]
                ch_results[ch_name] = {"strength": strength, "excess_ratio": ratio}
                w_sum += strength * w
                w_tot += w

            if w_tot == 0:
                power_composite = 0.0
                agreement = "insufficient_channels"
            else:
                power_composite = round(w_sum / w_tot, 3)
                if len(ch_results) >= 3:
                    vals = [v["strength"] for v in ch_results.values()]
                    sd = float(np.std(vals))
                    agreement = (
                        "high" if sd < 0.15 else "moderate" if sd < 0.30 else "low"
                    )
                else:
                    agreement = "insufficient_channels"

            # ── Coherence augmentation (Bible Ch.5 §5.4 §coherence) ───────────────────
            # Compute coherence between temporal pair (TP9↔TP10) and frontal
            # pair (AF7↔AF8) at the entrainment frequency band ±0.5 Hz.
            # Only available when SQI is full (all 4 channels present).
            coherence_score = 0.0
            coh_tp = None
            coh_af = None
            if (
                all(ch in ch_arrays for ch in ("tp9", "tp10", "af7", "af8"))
                and self._last_sqi_confidence == "full"
            ):
                band_lo = max(0.5, beat_freq - 1.0)
                band_hi = beat_freq + 1.0
                coh_tp = band_coherence(
                    ch_arrays["tp9"],
                    ch_arrays["tp10"],
                    fs=sampling_rate,
                    f_low=band_lo,
                    f_high=band_hi,
                )
                coh_af = band_coherence(
                    ch_arrays["af7"],
                    ch_arrays["af8"],
                    fs=sampling_rate,
                    f_low=band_lo,
                    f_high=band_hi,
                )
                coherence_score = round(0.5 * coh_tp + 0.5 * coh_af, 3)

            composite = composite_assr(
                power_composite, coherence_score, alpha_ambiguous
            )

            self._assr_tracker.record(session_elapsed, composite, beat_freq)
            trend = self._assr_tracker.get_trend()

            patch: dict = {
                "eeg_entrainment_strength": composite,
                "eeg_entrainment_power_strength": power_composite,
                "eeg_entrainment_coherence": coherence_score,
                "eeg_entrainment_coherence_tp": coh_tp,
                "eeg_entrainment_coherence_af": coh_af,
                "eeg_entrainment_confidence": "active",
                "eeg_entrainment_trend": trend,
                "eeg_entrainment_beat_freq": beat_freq,
                "eeg_entrainment_channel_agreement": agreement,
                "eeg_entrainment_recommend_modality": None,
            }

            if alpha_ambiguous:
                patch["eeg_entrainment_confidence"] = "alpha_overlap"
                print(
                    f"[EEG] ASSR: beat {beat_freq:.1f} Hz ≈ IAF {iaf:.1f} Hz — "
                    "entrainment measurement ambiguous (alpha overlap)"
                )

            # Modality switching logic — never during sleep sessions
            session_type = str(live.get("session_name", "") or "")
            in_sleep = "sleep" in session_type.lower()

            if not in_sleep and self._assr_tracker.should_switch_modality():
                current_modality = str(live.get("beat_type", "binaural"))
                if current_modality == "binaural":
                    patch["eeg_entrainment_recommend_modality"] = "isochronic"
                    patch["eeg_entrainment_recommend_reason"] = (
                        "binaural_assr_absent_2_consecutive — monaural beats "
                        "produce stronger cortical entrainment (Orozco Perez 2020)"
                    )
                    print(
                        "[EEG] ASSR absent (binaural) — recommending switch to isochronic"
                    )
                elif current_modality == "isochronic":
                    patch["eeg_entrainment_recommend_modality"] = "fm"
                    patch["eeg_entrainment_recommend_reason"] = (
                        "isochronic_assr_also_absent — FM entrainment engages "
                        "different neural pathway via tonotopic sustained field response"
                    )
                    print("[EEG] ASSR absent (isochronic) — recommending switch to FM")
                else:
                    patch["eeg_entrainment_recommend_modality"] = "bilateral"
                    patch["eeg_entrainment_recommend_reason"] = (
                        "spectral/temporal/tonal ASSR all absent — bilateral panning "
                        "provides spatial entrainment via interhemispheric alternation"
                    )
                    print(
                        "[EEG] ASSR absent (all modalities) — recommending bilateral panning"
                    )
                self._assr_tracker._switch_count += 1

            elif in_sleep and trend == "declining" and composite < 0.3:
                # Declining ASSR during sleep = expected progress, not failure
                patch["eeg_entrainment_trend"] = "declining_sleep_expected"

            patch_live(patch)
            coh_str = (
                f" coh={coherence_score:.2f}(tp={coh_tp:.2f},af={coh_af:.2f})"
                if coh_tp is not None
                else ""
            )
            print(
                f"[EEG] ASSR: strength={composite:.3f} power={power_composite:.3f}"
                f"{coh_str} trend={trend} agreement={agreement} "
                f"beat={beat_freq:.1f}Hz "
                f"{'(alpha-overlap)' if alpha_ambiguous else ''}"
            )

        except Exception as e:
            print(f"[EEG] ASSR update error: {e}")
            patch_live({"eeg_entrainment_confidence": "unavailable"})

    # ── IAF calibration ───────────────────────────────────────────────────────

    def run_iaf_calibration(self, duration_s: float = 30.0):
        """Collect EEG for *duration_s* seconds and return detected IAF.

        Blocks the calling thread.  Call from a non-UI background thread.

        Progressive microfeedback is written to live_control.json every 5 s:
            calibration_status:         "recording" | "extending" | "done" | "failed"
            calibration_iaf_hz:         float or null
            calibration_iaf_confidence: 0–1 float
            calibration_channel_sqi:    {tp9, af7, af8, tp10} smoothed SQI values
            calibration_hint:           actionable text or ""
            calibration_time_remaining_s: int

        Accept/extend/fallback thresholds (from spec):
            ≥ 0.70 → accept immediately after initial window
            0.40–0.69 → extend once by 15 s, accept if ≥ 0.70 after extension
            < 0.40  → fallback (use candidate if >0 channels found, else None)

        Returns iaf_hz (float) or None on failure.
        """
        if not self.is_alive():
            print("[EEG] Cannot calibrate — engine not running.")
            return None

        tick_s = 5
        original_duration = duration_s  # immutable; used for the extend/accept gate
        max_duration = duration_s  # grows by 15 s on one extension
        extended_once = False
        iaf_result: float | None = None
        last_hint_at = 0.0
        all_data: np.ndarray | None = None
        iaf_cand: float | None = None  # always holds last good candidate

        print(f"[EEG] IAF calibration started ({duration_s:.0f}s).")
        self._cal_state.update(
            {
                "calibration_status": "recording",
                "calibration_iaf_hz": None,
                "calibration_iaf_confidence": 0.0,
                "calibration_channel_sqi": {ch: 0.0 for ch in _CH_NAMES},
                "calibration_hint": "",
                "calibration_time_remaining_s": int(max_duration),
            }
        )

        self._calibration_data = []
        self._calibrating = True
        elapsed = 0

        try:
            while elapsed < max_duration:
                self._stop.wait(timeout=float(tick_s))
                elapsed += tick_s
                if self._stop.is_set():
                    break

                if not self._calibration_data:
                    remaining = int(max_duration - elapsed)
                    self._cal_state.update({"calibration_time_remaining_s": remaining})
                    continue

                # Build arrays for confidence analysis
                all_data = np.concatenate(self._calibration_data, axis=1)
                half_len = all_data.shape[1] // 2
                half_data = all_data[:, :half_len] if half_len >= 4 else None

                sampling_rate = self._BoardShim.get_sampling_rate(self.board_id)
                iaf_cand, conf, _detail = detect_iaf_with_confidence(
                    all_data, sampling_rate, half_data=half_data
                )

                channel_sqi = {
                    ch: round(self._last_sqi_smoothed.get(ch, 0.0), 2)
                    for ch in _CH_NAMES
                }
                hint = _select_calibration_hint(channel_sqi, last_hint_at)
                if hint:
                    last_hint_at = time.time()

                remaining = int(max_duration - elapsed)
                self._cal_state.update(
                    {
                        "calibration_status": "extending"
                        if extended_once
                        else "recording",
                        "calibration_iaf_hz": round(iaf_cand, 2) if iaf_cand else None,
                        "calibration_iaf_confidence": conf,
                        "calibration_channel_sqi": channel_sqi,
                        "calibration_hint": hint,
                        "calibration_time_remaining_s": remaining,
                    }
                )
                print(
                    f"[EEG] IAF calibration tick: elapsed={elapsed:.0f}s "
                    f"iaf={iaf_cand} conf={conf:.2f} sqi={channel_sqi}"
                )

                # Accept/extend gate fires ONCE at the end of the original window.
                # After an extension, we let the loop run to max_duration naturally.
                if elapsed >= original_duration and not extended_once:
                    if conf >= 0.65:
                        # Sufficient confidence — accept immediately
                        iaf_result = iaf_cand
                        break
                    elif conf >= 0.35:
                        # Marginal — extend once and keep collecting
                        extended_once = True
                        max_duration = original_duration + 15
                        self._cal_state.update(
                            {
                                "calibration_status": "extending",
                                "calibration_time_remaining_s": int(
                                    max_duration - elapsed
                                ),
                            }
                        )
                        print("[EEG] IAF confidence insufficient — extending 15 s")
                    else:
                        # Too low to be worth extending — take what we have
                        iaf_result = iaf_cand
                        break

        finally:
            self._calibrating = False
            self._calibration_data = []

        # If the loop exited naturally (hit max_duration without a break), accept
        # whatever candidate we accumulated rather than failing silently.
        if iaf_result is None and iaf_cand is not None:
            iaf_result = iaf_cand

        if iaf_result is None:
            print("[EEG] IAF detection failed — no clear alpha peak.")
            self._cal_state.update(
                {"calibration_status": "failed", "calibration_hint": ""}
            )
            return None

        # Re-run final confidence on the accumulated data with a proper stability window
        sampling_rate = self._BoardShim.get_sampling_rate(self.board_id)
        final_conf = 0.0
        if all_data is not None:
            half_len = all_data.shape[1] // 2
            final_half = all_data[:, :half_len] if half_len >= 4 else None
            _, final_conf, _ = detect_iaf_with_confidence(
                all_data, sampling_rate, half_data=final_half
            )

        print(f"[EEG] IAF accepted: {iaf_result:.2f} Hz  conf={final_conf:.2f}")
        self._iaf_hz = iaf_result
        self._cal_state.update(
            {
                "eeg_iaf_hz": round(iaf_result, 2),
                "eeg_needs_iaf_calibration": False,
                "calibration_status": "done",
                "calibration_iaf_confidence": final_conf,
                "calibration_hint": "",
            }
        )
        return iaf_result

    # ── Post-session data for scoring (Bible Ch.6 §6.3) ────────────────────────────────

    def get_session_data_for_scoring(
        self,
        session_id: str,
        session_preset: str = "",
        duration_sec: int = 0,
        target_band: tuple = (0.0, 8.0),
        config_snapshot: dict | None = None,
        freq_lead_data: dict | None = None,
    ) -> dict:
        """Return a dict suitable for SessionScorer.score_session().

        Copies the accumulated time-series buffers (sef95, assr, faa, sqi)
        collected during this session's run. Call once at session end before
        the next session resets the buffers.
        """
        live = _read_live()
        veil_modes = [
            r.get("veil_mode") for r in list(self.history) if r.get("veil_mode")
        ]
        from collections import Counter

        veil_primary = Counter(veil_modes).most_common(1)[0][0] if veil_modes else None

        snap = config_snapshot or {}
        if not snap:
            snap = {
                "beat_type": live.get("beat_type", "binaural"),
                "veil_mode_primary": veil_primary,
                "spiral_style": live.get("spiral_style"),
                "spiral_chaos": live.get("spiral_chaos"),
                "trail_decay": live.get("trail_decay"),
            }

        return {
            "session_id": session_id,
            "session_preset": session_preset,
            "duration_sec": duration_sec,
            "target_band": target_band,
            "sef95_series": list(self._series_sef95),
            "assr_series": list(self._series_assr),
            "faa_series": list(self._series_faa),
            "sqi_series": list(self._series_sqi),
            "affirmation_windows": [],  # filled by agent if available
            "config_snapshot": snap,
            "freq_lead_data": freq_lead_data or {},
        }

    # ── History ───────────────────────────────────────────────────────────────

    def get_history_summary(self, samples: int = 60):
        """Summarise the last *samples* entries for agent consumption."""
        recent = list(self.history)[-samples:]
        if not recent:
            return {"samples": 0}

        def _avg(key: str) -> float:
            vals = [r[key] for r in recent if isinstance(r.get(key), (int, float))]
            return round(sum(vals) / len(vals), 3) if vals else 0.0

        def _trend(key: str) -> str:
            vals = [r[key] for r in recent if isinstance(r.get(key), (int, float))]
            if len(vals) < 6:
                return "stable"
            first_half = sum(vals[: len(vals) // 2]) / (len(vals) // 2)
            second_half = sum(vals[len(vals) // 2 :]) / (len(vals) - len(vals) // 2)
            delta = second_half - first_half
            if delta > 0.02:
                return "rising"
            if delta < -0.02:
                return "falling"
            return "stable"

        good_count = sum(1 for r in recent if r.get("eeg_quality") == "good")
        dominant_hist = [
            r.get("eeg_dominant_band", "") for r in recent if r.get("eeg_dominant_band")
        ]

        faa_hist = [
            r.get("eeg_faa_state", "") for r in recent if r.get("eeg_faa_state")
        ]
        approach_pct = (
            round(faa_hist.count("approach") / len(faa_hist), 2) if faa_hist else 0.0
        )

        return {
            "samples": len(recent),
            "period_minutes": round(len(recent) / 60, 1),
            "trend": {
                "alpha": _trend("eeg_alpha"),
                "theta": _trend("eeg_theta"),
                "beta": _trend("eeg_beta"),
                "faa": _trend("eeg_faa"),
            },
            "avg_alpha_theta_ratio": _avg("eeg_alpha_theta_ratio"),
            "avg_beta_alpha_ratio": _avg("eeg_beta_alpha_ratio"),
            "avg_trance_score": _avg("eeg_trance_score"),
            "avg_sqi_composite": _avg("eeg_sqi_composite"),
            "avg_entrainment": _avg("eeg_entrainment_strength"),
            "avg_faa": _avg("eeg_faa"),
            "faa_approach_pct": approach_pct,
            "dominant_band_history": dominant_hist[-10:],
            "quality_good_pct": round(good_count / len(recent), 2),
        }
