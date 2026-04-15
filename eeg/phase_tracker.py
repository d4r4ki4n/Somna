"""
phase_tracker.py — Real-time alpha/theta phase estimation for Muse 2 (Bible Ch.4 §4.6 §4.1)

Endpoint-corrected Hilbert transform. Runs inside eeg_engine.py at ~10 Hz.
IAF is kept in sync with calibration recalibrations (Bible Ch.2 §2.6).
"""

import numpy as np
from scipy.signal import hilbert, butter, sosfiltfilt


class PhaseTracker:
    """
    Real-time instantaneous phase estimation using endpoint-corrected Hilbert transform.

    PhaseTracker.push_samples() is called each EEG loop iteration.
    PhaseTracker.estimate_phase() is called at ~10 Hz when rate-limiting allows.

    IAF (individual alpha frequency) comes from calibrated eeg_iaf_hz in live_control.json.
    Called via update_iaf() whenever IAF recalibrates.

    Bands supported: "alpha", "theta", "delta".
    Delta (0.5–1.5 Hz) requires buffer_sec >= 8.0 for reliable phase estimation
    (need several full slow-oscillation cycles).
    """

    BUFFER_SEC     = 2.0   # rolling window length (override to 8.0 for delta)
    UPDATE_HZ      = 10    # target update rate (every ~100 ms)
    TROUGH_PHASE   = np.pi # alpha trough = phase π (inhibitory minimum, noise floor lowest)
    TROUGH_WINDOW  = 0.3   # radians tolerance around π for "at trough"
    MIN_SAMPLES    = 128   # minimum samples required before estimating

    def __init__(self, srate: int = 256, iaf_hz: float = 10.0,
                 buffer_sec: float = 0.0):
        self.srate      = srate
        self.iaf_hz     = iaf_hz
        buf_sec         = buffer_sec if buffer_sec > 0 else self.BUFFER_SEC
        self.buffer_len = int(buf_sec * srate)
        self._buffer    = np.zeros(self.buffer_len)
        self._sample_count = 0
        self._update_interval_s = 1.0 / self.UPDATE_HZ
        self._last_update_time  = 0.0
        self._sos_alpha = self._design_bandpass(iaf_hz - 2.0, iaf_hz + 2.0)
        self._sos_theta = self._design_bandpass(4.0, 7.0)
        self._sos_delta = self._design_bandpass(0.5, 1.5)

    # ── Filter design ─────────────────────────────────────────────────────────

    def _design_bandpass(self, lo: float, hi: float, order: int = 4) -> np.ndarray:
        lo = max(0.5, lo)
        hi = min(self.srate * 0.45, hi)
        return butter(order, [lo, hi], btype="band", fs=self.srate, output="sos")

    def update_iaf(self, new_iaf: float):
        """Called when IAF recalibrates (Bible Ch.2 §2.6). Rebuilds the alpha filter."""
        self.iaf_hz     = new_iaf
        self._sos_alpha = self._design_bandpass(new_iaf - 2.0, new_iaf + 2.0)

    # ── Sample ingestion ──────────────────────────────────────────────────────

    def push_samples(self, samples: np.ndarray):
        """Push new EEG samples into the rolling buffer. Called every loop iteration."""
        n = len(samples)
        if n == 0:
            return
        self._buffer = np.roll(self._buffer, -n)
        self._buffer[-n:] = samples
        self._sample_count += n

    # ── Phase estimation ──────────────────────────────────────────────────────

    def estimate_phase(self, band: str = "alpha", now: float = 0.0) -> dict:
        """
        Returns instantaneous phase estimate with endpoint correction.

        Endpoint correction: mirror-pad buffer edges to reduce Hilbert
        edge artifacts, then extract phase only from the center.

        Returns dict with: phase, amplitude, at_trough, confidence.
        Returns nulled dict when insufficient data.
        """
        if self._sample_count < self.MIN_SAMPLES:
            return {"phase": None, "amplitude": 0.0, "at_trough": False, "confidence": 0.0}

        # Rate limiting — caller should also rate-limit, but guard here too
        if now and (now - self._last_update_time) < self._update_interval_s:
            return {"phase": None, "amplitude": 0.0, "at_trough": False, "confidence": 0.0,
                    "skipped": True}

        if now:
            self._last_update_time = now

        if band == "alpha":
            sos = self._sos_alpha
        elif band == "theta":
            sos = self._sos_theta
        else:
            sos = self._sos_delta

        try:
            filtered = sosfiltfilt(sos, self._buffer)
        except Exception:
            return {"phase": None, "amplitude": 0.0, "at_trough": False, "confidence": 0.0}

        # Mirror-pad to suppress Hilbert edge artifacts
        pad_len = self.srate // 2  # 0.5 s mirror pad
        padded  = np.concatenate([
            filtered[pad_len:0:-1],
            filtered,
            filtered[-2:-pad_len - 2:-1],
        ])

        analytic  = hilbert(padded)
        center    = analytic[pad_len:-pad_len]
        phase     = float(np.angle(center[-1]))
        amplitude = float(np.abs(center[-1]))

        # Confidence: SNR of amplitude vs noise floor
        snr        = amplitude / (float(np.std(self._buffer)) + 1e-9)
        confidence = float(min(1.0, snr / 3.0))

        at_trough = abs(phase - self.TROUGH_PHASE) < self.TROUGH_WINDOW

        return {
            "phase":      phase,
            "amplitude":  amplitude,
            "at_trough":  at_trough,
            "confidence": confidence,
        }

    def estimate_both(self, now: float = 0.0) -> dict:
        """
        Convenience: estimate alpha and theta in one call.
        Returns combined dict with alpha_ and theta_ prefixed keys.
        """
        alpha = self.estimate_phase("alpha", now=now)
        # Theta uses a separate rate-limited call without passing now so it shares
        # the update slot — theta phase used downstream but doesn't need its own window
        theta_raw = self.estimate_phase("theta", now=0.0)

        return {
            "alpha_phase":      alpha.get("phase"),
            "alpha_amplitude":  alpha.get("amplitude", 0.0),
            "alpha_at_trough":  alpha.get("at_trough", False),
            "alpha_confidence": alpha.get("confidence", 0.0),
            "theta_phase":      theta_raw.get("phase"),
        }
