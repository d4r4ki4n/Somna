"""
vr_ssvep_detector.py — SSVEP & Binocular Integration Detector (Bible Ch.8 §8.1 §5, Bible Ch.8 §8.2 §5)
======================================================================================
Intended to run as an in-thread plugin inside EEGEngine.  Does NOT open
its own BrainFlow board connection; instead it receives raw AF7/AF8 samples
pushed by EEGEngine's main acquisition loop via update_batch().

On each tick (nominally every 1 s) detect() runs a Welch PSD on the last
WINDOW_S seconds of samples, applies 1/f correction, computes SNR at the
driving frequencies and their intermodulation products, and writes the
results to live_control.json via patch_live().

Keys written to live_control.json:
    ssvep_left_snr          — SNR at left-eye tag frequency
    ssvep_right_snr         — SNR at right-eye tag frequency
    ssvep_binocular_index   — proxy for binocular integration (0–1)
    ssvep_im_f1_plus_f2     — power at f_L + f_R (IM product)
    ssvep_im_f1_minus_f2    — power at |f_L - f_R| (IM product)
    ssvep_dominance_raw     — (left_snr − right_snr) / (left_snr + right_snr) ∈ [−1,+1]
    ssvep_switch_rate_hz    — zero-crossing rate of dominance signal (rivalry switch rate)
    ssvep_timestamp         — time.time() of last computation

All SNR values are dimensionless dB (10 * log10(signal / noise)).
A positive SNR indicates the frequency is reliably present.
A binocular_index > 0.5 and positive IM products together suggest strong
binocular integration — a useful proxy for trance depth (Bible Ch.8 §8.2 §7).
"""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

import numpy as np
from ipc import patch_live

_LIVE_PATH = Path(__file__).parent.parent / "live_control.json"

# ── Detection parameters ──────────────────────────────────────────────────────
WINDOW_S = 4.0  # rolling window for Welch PSD (seconds)
NPERSEG_RATIO = 0.5  # nperseg = WINDOW_S * FS * ratio
SNR_NEIGHBOR_BINS = 2  # bins each side of target for noise estimate
MIN_SNR_DB = 1.0  # SNR threshold for "signal present"
DOMINANCE_HISTORY = 30  # samples for switch-rate estimation


def _snr_at_freq(freqs: np.ndarray, psd_db: np.ndarray, target_hz: float) -> float:
    """Compute SNR (dB) at target_hz using neighbor bins as noise estimate.

    psd_db is already 1/f-corrected (log-linear detrended).
    """
    idx = int(np.argmin(np.abs(freqs - target_hz)))
    bin_power = psd_db[idx]

    lo = max(0, idx - SNR_NEIGHBOR_BINS - 1)
    hi = min(len(psd_db) - 1, idx + SNR_NEIGHBOR_BINS + 1)
    neighbor_mask = np.ones(len(psd_db), dtype=bool)
    neighbor_mask[max(0, idx - 1) : idx + 2] = False
    neighbors = psd_db[lo:hi][neighbor_mask[lo:hi]]

    noise_floor = (
        float(neighbors.mean()) if len(neighbors) > 0 else float(np.median(psd_db))
    )
    return float(bin_power - noise_floor)


def _correct_1f(freqs: np.ndarray, psd: np.ndarray) -> np.ndarray:
    """Apply 1/f correction by fitting a log-log line and subtracting the trend.

    Returns the psd in dB units relative to the 1/f baseline.
    """
    valid = (freqs > 1.0) & np.isfinite(psd) & (psd > 0)
    if not np.any(valid):
        return 10.0 * np.log10(np.maximum(psd, 1e-30))

    log_f = np.log10(freqs[valid])
    log_psd = np.log10(psd[valid])

    try:
        slope, intercept = np.polyfit(log_f, log_psd, 1)
    except Exception:
        return 10.0 * np.log10(np.maximum(psd, 1e-30))

    trend = slope * np.log10(np.maximum(freqs, 1e-9)) + intercept
    psd_db = 10.0 * np.log10(np.maximum(psd, 1e-30))
    return psd_db - trend  # 1/f-corrected dB


class SSVEPDetector:
    """In-thread SSVEP detection plugin for EEGEngine.

    Instantiate once.  Call update_batch() for every EEG processing tick
    to feed raw AF7/AF8 samples.  Call detect() once per second (or on
    every tick) to compute the current SSVEP profile.

    Example (inside EEGEngine main loop):
        if self._ssvep_plugin is not None:
            self._ssvep_plugin.update_batch(eeg_data[1], eeg_data[2])
            self._ssvep_plugin.detect(f_left, f_right)
    """

    def __init__(self, fs: int = 256):
        self.fs = fs
        self._window_n = int(WINDOW_S * fs)
        self._af7: deque[float] = deque(maxlen=self._window_n)
        self._af8: deque[float] = deque(maxlen=self._window_n)

        # Dominance history for switch-rate estimation
        self._dominance_history: deque[float] = deque(maxlen=DOMINANCE_HISTORY)

        self._last_f_left: float = 0.0
        self._last_f_right: float = 0.0
        self._last_result: dict = {}

    # ── Feed samples ─────────────────────────────────────────────────────────

    def update_batch(self, af7_samples: np.ndarray, af8_samples: np.ndarray) -> None:
        """Extend internal ring buffers with new samples.

        af7_samples, af8_samples: 1-D arrays of shape (n_new_samples,)
        Called once per EEG processing tick (typically every 256 samples at 256 Hz).
        """
        self._af7.extend(af7_samples.tolist())
        self._af8.extend(af8_samples.tolist())

    # ── Main detection ────────────────────────────────────────────────────────

    def detect(self, f_left: float, f_right: float) -> dict:
        """Run SSVEP detection at the current driving frequencies.

        Returns a result dict and writes the same keys to live_control.json.
        Returns empty dict if insufficient data or scipy unavailable.
        """
        if f_left <= 0.0 or f_right <= 0.0:
            return {}
        if len(self._af7) < self._window_n // 2:
            return {}

        try:
            from scipy import signal as _sig
        except ImportError:
            return {}

        self._last_f_left = f_left
        self._last_f_right = f_right

        nperseg = max(64, int(self._window_n * NPERSEG_RATIO))
        af7 = np.array(self._af7, dtype=np.float64)
        af8 = np.array(self._af8, dtype=np.float64)

        freqs, psd_af7 = _sig.welch(af7, fs=self.fs, nperseg=nperseg)
        _, psd_af8 = _sig.welch(af8, fs=self.fs, nperseg=nperseg)

        # Average the two channels for binocular metrics
        psd_avg = 0.5 * (psd_af7 + psd_af8)

        psd_af7_db = _correct_1f(freqs, psd_af7)
        psd_af8_db = _correct_1f(freqs, psd_af8)
        psd_avg_db = _correct_1f(freqs, psd_avg)

        snr_left = _snr_at_freq(freqs, psd_af7_db, f_left)
        snr_right = _snr_at_freq(freqs, psd_af8_db, f_right)

        f_sum = f_left + f_right
        f_diff = abs(f_left - f_right)
        im_sum = _snr_at_freq(freqs, psd_avg_db, f_sum)
        im_diff = _snr_at_freq(freqs, psd_avg_db, f_diff)

        # Binocular integration index: both tags positive + at least one IM positive
        binocular_index = self._binocular_index(snr_left, snr_right, im_sum, im_diff)

        # Dominance: signed ratio of left vs right response
        denom = abs(snr_left) + abs(snr_right)
        dominance = (snr_left - snr_right) / denom if denom > 1e-9 else 0.0
        self._dominance_history.append(dominance)
        switch_rate = self._estimate_switch_rate()

        result = {
            "ssvep_left_snr": round(snr_left, 3),
            "ssvep_right_snr": round(snr_right, 3),
            "ssvep_binocular_index": round(binocular_index, 3),
            "ssvep_im_f1_plus_f2": round(im_sum, 3),
            "ssvep_im_f1_minus_f2": round(im_diff, 3),
            "ssvep_dominance_raw": round(dominance, 3),
            "ssvep_switch_rate_hz": round(switch_rate, 4),
            "ssvep_f_left": round(f_left, 2),
            "ssvep_f_right": round(f_right, 2),
            "ssvep_timestamp": time.time(),
        }
        self._last_result = result
        patch_live(result)
        return result

    # ── Conductor-facing helpers ──────────────────────────────────────────────

    def dominance_index(self) -> float:
        """Smoothed dominance value from history.  Positive = left dominant."""
        if not self._dominance_history:
            return 0.0
        return float(np.mean(self._dominance_history))

    def binocular_integration_strong(self) -> bool:
        """True if the last detection showed strong binocular integration."""
        return self._last_result.get("ssvep_binocular_index", 0.0) > 0.5

    def switch_rate_elevated(self, threshold_hz: float = 0.15) -> bool:
        """True if the rivalry switch rate is above threshold (deep engagement)."""
        return self._last_result.get("ssvep_switch_rate_hz", 0.0) > threshold_hz

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _binocular_index(
        snr_l: float, snr_r: float, im_sum: float, im_diff: float
    ) -> float:
        """Composite binocular integration index on [0, 1].

        Both SSVEP tags must be positive, and at least one intermodulation
        product must also be positive for the index to exceed 0.5.
        """
        if snr_l < MIN_SNR_DB or snr_r < MIN_SNR_DB:
            return max(0.0, 0.3 * (snr_l + snr_r) / (2 * abs(MIN_SNR_DB) + 1))

        # Both tags reliably detected — scale by IM products
        base_score = 0.5
        tag_bonus = min(0.25, 0.05 * min(snr_l, snr_r))
        im_bonus = min(0.25, 0.05 * max(0.0, max(im_sum, im_diff)))
        return min(1.0, base_score + tag_bonus + im_bonus)

    def _estimate_switch_rate(self) -> float:
        """Estimate binocular rivalry switch rate from dominance sign changes."""
        h = list(self._dominance_history)
        if len(h) < 4:
            return 0.0
        signs = np.sign(h)
        crossings = int(np.sum(np.abs(np.diff(signs)) > 0))
        window_duration_s = len(h) * 1.0  # 1 sample per second tick
        return crossings / max(window_duration_s, 1.0)
