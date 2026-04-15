"""
pac_estimator.py — Phase-amplitude coupling (Tort et al. 2010 MI method) (Bible Ch.4 §4.6 §7.2)

Computes three PAC pairs per the phase-cascade hierarchy:
  ISA-Alpha   (0.03–0.08 Hz phase → IAF±2 Hz amplitude) — breath→cortical coupling
  Theta-Gamma (4–7 Hz phase → 30–45 Hz amplitude)       — entrainment→processing coupling
  Alpha-Gamma (IAF±2 Hz phase → 30–45 Hz amplitude)     — perceptual gating→processing

cascade_integrity is the weighted mean (0.40 × ISA-alpha + 0.35 × theta-gamma + 0.25 × alpha-gamma).

Runs at ~0.5 Hz (every 2 s) inside eeg_engine.py — needs a 4-second accumulation window.
Written to live_control.json via _patch_live():
  pac_isa_alpha, pac_theta_gamma, pac_alpha_gamma, pac_cascade_integrity

NOTE: ISA (infra-slow, 0.03–0.08 Hz) requires ~20–30 s of data to estimate reliably.
During the first 30 s, ISA-alpha MI will return 0.0 — this is expected and correct.
"""

import numpy as np
from scipy.signal import hilbert, butter, sosfiltfilt


class PACEstimator:
    """
    Modulation index via Tort et al. (2010):
    KL-divergence of amplitude-across-phase-bins versus uniform distribution,
    normalised by log(N_bins) to [0, 1].

    Designed as a plugin for eeg_engine.py: create once, call compute_all() at ~0.5 Hz.
    """

    N_PHASE_BINS  = 18     # 20-degree bins (360 / 20 = 18)
    WINDOW_SEC    = 4.0    # computation window — needs full alpha cycles
    ISA_WINDOW_SEC = 30.0  # ISA needs more data; use full available buffer when possible

    # Weighted contribution of each PAC pair to cascade_integrity
    WEIGHTS = {"isa_alpha": 0.40, "theta_gamma": 0.35, "alpha_gamma": 0.25}

    def __init__(self, srate: int = 256):
        self.srate      = srate
        self.window_len = int(self.WINDOW_SEC * srate)
        self.isa_window_len = int(self.ISA_WINDOW_SEC * srate)
        self._update_interval_s = 2.0
        self._last_update_time  = 0.0

    # ── Core MI computation ───────────────────────────────────────────────────

    def _bandpass(self, lo: float, hi: float, order: int = 4) -> np.ndarray:
        lo = max(0.02, lo)
        hi = min(self.srate * 0.45, hi)
        return butter(order, [lo, hi], btype="band", fs=self.srate, output="sos")

    def compute_mi(self, signal: np.ndarray,
                   phase_band: tuple[float, float],
                   amp_band: tuple[float, float]) -> float:
        """
        Compute Modulation Index between phase_band and amp_band.

        Returns float 0.0–1.0 (0 = no coupling, 1 = perfect coupling).
        Returns 0.0 if signal is too short or computation fails.
        """
        if len(signal) < self.window_len:
            return 0.0

        seg = signal[-self.window_len:]

        try:
            sos_phase  = self._bandpass(*phase_band)
            phase_sig  = sosfiltfilt(sos_phase, seg)
            phase_vals = np.angle(hilbert(phase_sig))

            sos_amp    = self._bandpass(*amp_band)
            amp_sig    = sosfiltfilt(sos_amp, seg)
            amp_vals   = np.abs(hilbert(amp_sig))
        except Exception:
            return 0.0

        # Bin amplitudes by phase
        bin_edges = np.linspace(-np.pi, np.pi, self.N_PHASE_BINS + 1)
        bin_means = np.zeros(self.N_PHASE_BINS)
        for i in range(self.N_PHASE_BINS):
            mask = (phase_vals >= bin_edges[i]) & (phase_vals < bin_edges[i + 1])
            if mask.sum() > 0:
                bin_means[i] = amp_vals[mask].mean()

        total = bin_means.sum()
        if total == 0:
            return 0.0

        # KL-divergence from uniform distribution
        p      = bin_means / total
        q      = np.ones(self.N_PHASE_BINS) / self.N_PHASE_BINS
        p_safe = np.where(p > 0, p, 1e-10)
        kl     = float(np.sum(p_safe * np.log(p_safe / q)))
        mi     = kl / np.log(self.N_PHASE_BINS)

        return float(np.clip(mi, 0.0, 1.0))

    # ── ISA requires a longer buffer ─────────────────────────────────────────

    def _compute_isa_alpha(self, long_buffer: np.ndarray, iaf: float) -> float:
        """ISA-alpha uses a longer buffer for meaningful infra-slow phase estimation."""
        if len(long_buffer) < self.isa_window_len:
            # Fall back to shorter window with the ISA band floor raised slightly
            if len(long_buffer) < self.window_len:
                return 0.0
            return self.compute_mi(long_buffer[-self.window_len:],
                                   (0.05, 0.12),   # higher floor for short window
                                   (iaf - 2.0, iaf + 2.0))
        seg = long_buffer[-self.isa_window_len:]
        return self.compute_mi(seg, (0.03, 0.08), (iaf - 2.0, iaf + 2.0))

    # ── Batch computation ─────────────────────────────────────────────────────

    def compute_all(self, eeg_buffer: np.ndarray, iaf: float = 10.0,
                    now: float = 0.0) -> dict:
        """
        Compute all PAC pairs and return dict with cascade_integrity.

        eeg_buffer should be the full rolling buffer from eeg_engine (as large as possible).
        iaf is the calibrated individual alpha frequency.
        now is time.monotonic() — used for rate limiting; pass 0.0 to skip.

        Returns dict of pac_* keys ready for _patch_live().
        """
        # Rate limiting
        if now and (now - self._last_update_time) < self._update_interval_s:
            return {}
        if now:
            self._last_update_time = now

        isa_alpha   = self._compute_isa_alpha(eeg_buffer, iaf)
        theta_gamma = self.compute_mi(eeg_buffer, (4.0, 7.0), (30.0, 45.0))
        alpha_gamma = self.compute_mi(eeg_buffer, (iaf - 2.0, iaf + 2.0), (30.0, 45.0))

        w = self.WEIGHTS
        cascade = (w["isa_alpha"]   * isa_alpha +
                   w["theta_gamma"] * theta_gamma +
                   w["alpha_gamma"] * alpha_gamma)

        return {
            "pac_isa_alpha":        round(isa_alpha, 4),
            "pac_theta_gamma":      round(theta_gamma, 4),
            "pac_alpha_gamma":      round(alpha_gamma, 4),
            "pac_cascade_integrity": round(cascade, 4),
        }
