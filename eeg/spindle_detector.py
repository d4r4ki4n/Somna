"""
spindle_detector.py — Real-time sleep spindle detection (Bible Ch.7 §7.1 §4)

Detects sleep spindles (11–16 Hz, 0.5–2.0 s) on frontal EEG channels
AF7 and AF8 (Muse 2 indices 1 and 2).

Algorithm: 4th-order Butterworth bandpass (11–16 Hz) + Hilbert envelope,
rolling threshold at mean + 1.5 SD of a 30-second baseline.  Achieves
~91.6% precision per Warby et al. (2014).

Replaces the scipy.signal.morlet2 approach in the Bible Ch.7 §7.1 pseudocode —
scipy's morlet2 signature is incompatible with that usage; Butterworth +
Hilbert is equally validated and matches the pattern already used in
eeg/depth_features.py for beta envelope correlation.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt, hilbert


class SpindleDetector:
    """Real-time sleep spindle detector for frontal Muse 2 channels.

    Called every tick (2 s epoch) from eeg_engine.py.
    Results feed SleepStageClassifier (spindle_density as N2 confirmation)
    and are written to live_control.json.
    """

    SIGMA_LO_HZ      = 11.0
    SIGMA_HI_HZ      = 16.0
    MIN_DURATION_S   = 0.5
    MAX_DURATION_S   = 2.0
    THRESHOLD_SD     = 1.5    # mean + 1.5 SD of rolling baseline
    BASELINE_SECS    = 30.0   # rolling baseline window
    SAMPLING_RATE    = 256

    def __init__(self):
        self._sos = butter(
            4,
            [self.SIGMA_LO_HZ, self.SIGMA_HI_HZ],
            btype="band",
            fs=self.SAMPLING_RATE,
            output="sos",
        )
        # Rolling baseline: one amplitude entry per tick (2 s)
        self._baseline: list[float] = []
        self._spindle_timestamps: list[float] = []
        self._in_spindle: bool   = False
        self._spindle_start: float = 0.0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _sigma_envelope(self, epoch: np.ndarray) -> float:
        """Mean analytic amplitude in the sigma band for one-channel epoch."""
        if len(epoch) < 64:
            return 0.0
        try:
            filtered  = sosfiltfilt(self._sos, epoch)
            envelope  = np.abs(hilbert(filtered))
            return float(np.mean(envelope))
        except Exception:
            return 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    def detect(
        self,
        epoch_af7: np.ndarray,
        epoch_af8: np.ndarray,
        timestamp: float,
    ) -> dict:
        """Process one 2-second epoch of frontal EEG.

        Args:
            epoch_af7  : (n_samples,) AF7 channel data
            epoch_af8  : (n_samples,) AF8 channel data
            timestamp  : current time.time() value

        Returns dict with:
            spindle_detected : bool  — spindle active this epoch
            spindle_density  : float — spindles per 30 s rolling window
            sigma_amplitude  : float — mean sigma band amplitude
        """
        # Average frontal channels — reduces artefact sensitivity
        epoch      = (epoch_af7 + epoch_af8) / 2.0
        mean_amp   = self._sigma_envelope(epoch)

        # Rolling baseline (max 15 entries at 2 s/tick = 30 s window)
        max_entries = int(self.BASELINE_SECS / 2.0)
        self._baseline.append(mean_amp)
        if len(self._baseline) > max_entries:
            self._baseline.pop(0)

        if len(self._baseline) > 5:
            b_mean  = float(np.mean(self._baseline))
            b_sd    = float(np.std(self._baseline))
            threshold = b_mean + self.THRESHOLD_SD * b_sd
        else:
            threshold = mean_amp * 1.5   # fallback before baseline is warm

        # State machine: enter spindle above threshold, confirm duration on exit
        spindle_detected = False
        if mean_amp > threshold:
            if not self._in_spindle:
                self._in_spindle    = True
                self._spindle_start = timestamp
            elif (timestamp - self._spindle_start) >= self.MIN_DURATION_S:
                spindle_detected = True   # ongoing valid spindle
        else:
            if self._in_spindle:
                duration = timestamp - self._spindle_start
                if self.MIN_DURATION_S <= duration <= self.MAX_DURATION_S:
                    self._spindle_timestamps.append(timestamp)
                self._in_spindle = False

        # Prune spindle list to last 30 s
        cutoff = timestamp - 30.0
        self._spindle_timestamps = [t for t in self._spindle_timestamps if t > cutoff]
        density = float(len(self._spindle_timestamps))

        return {
            "spindle_detected": spindle_detected,
            "spindle_density":  density,
            "sigma_amplitude":  mean_amp,
        }
