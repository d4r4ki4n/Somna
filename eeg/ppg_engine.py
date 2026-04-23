"""
ppg_engine.py — PPG processing for Bible Ch.2 §2.9 (Muse 2 ANCILLARY_PRESET)

Reads the Muse 2's photoplethysmography sensor (~64 Hz, forehead IR channel)
via BrainFlow's ANCILLARY_PRESET.  Maintains a 16-second rolling buffer to
enable reliable respiratory rate extraction.  Outputs every 1-second tick:

  ppg_available       bool   — True when PPG data is flowing and valid.

  ppg_heart_rate      float  — Instantaneous heart rate in BPM, computed from
                               the last 16 seconds of R-peak intervals.

  ppg_hrv_rmssd       float  — RMSSD (ms) over the last 16 s inter-beat
                               intervals.  Rises with parasympathetic dominance
                               (relaxation / trance deepening).  Injected into
                               agent context as a fourth convergent depth axis
                               alongside EEG-derived trance_score.

  ppg_breath_rate     float  — Respiratory rate in Hz derived from respiratory
                               sinus arrhythmia (RSA): the spectral peak of the
                               IBI series in the 0.15–0.40 Hz band.  Replaces
                               the synthetic breath clock in RespiratoryTracker
                               when available.

  ppg_breath_phase    float  — Current respiratory phase 0.0–1.0, advanced by
                               a monotonic clock driven by ppg_breath_rate.
                               Written to live_control.json and picked up by
                               RespiratoryTracker.update_ppg_phase() so the
                               entire phase-cascade (DeliveryGate, TMR, HTW)
                               runs on real physiology rather than a synthetic
                               oscillator.

Architecture notes
------------------
- Uses only numpy (already guaranteed present in the EEG stack).
- Peak detection: amplitude-normalized local-maximum scan with 300 ms
  refractory period.  No scipy, no BrainFlow DataFilter calls.
- Respiratory extraction: FFT of the IBI series treated as a ~1 Hz-sampled
  signal.  Frequency resolution = 1/16 ≈ 0.0625 Hz; acceptable for coarse
  respiratory-rate tracking where sub-Hz precision is not required.
- Graceful degradation: if fewer than 4 valid beats are detected, all outputs
  retain their previous values (stale but not wrong).  ppg_available stays
  True to avoid spurious gate disables; only flips False if an exception
  propagates at the BrainFlow read level.
"""

from __future__ import annotations

import time
from collections import deque

import numpy as np

# ── Constants ─────────────────────────────────────────────────────────────────

_PPG_SR = 64  # Muse 2 ancillary preset sample rate (Hz)
_BUFFER_S = 16  # rolling buffer length for IBI analysis
_MIN_BEATS = 4  # minimum valid R-peaks before emitting metrics
_MIN_IBI_S = 0.30  # 200 BPM maximum
_MAX_IBI_S = 1.80  # 33 BPM minimum
_RESP_LO_HZ = 0.15  # respiratory band low
_RESP_HI_HZ = 0.40  # respiratory band high
_PEAK_THRESH = 0.50  # fraction of std for peak threshold (forehead PPG)

# Bible Ch.2 §2.9 §2.2 — cardiac phase gating constants
_SYSTOLE_GUARD_MS = 350  # ms after PPG peak before diastolic window opens
_DIASTOLE_END_FRAC = 0.85  # fraction of mean IBI at which diastolic window closes
_CALIBRATION_S = 60  # seconds of RMSSD baseline calibration
_AUTONOMIC_SIGMOID_CENTER = 0.30  # RMSSD 30% above baseline → midpoint (0.5) depth
_AUTONOMIC_SIGMOID_SLOPE = 5.0  # sigmoid steepness


class PPGEngine:
    """
    Processes Muse 2 PPG data from ANCILLARY_PRESET.

    Instantiated once in EEGEngine.__init__ when board_id != SYNTHETIC.
    Call tick(board, board_id) every second inside the EEG main loop.
    """

    def __init__(self) -> None:
        self._buffer: deque[float] = deque(maxlen=_PPG_SR * _BUFFER_S)
        # Breath phase monotonic clock
        self._breath_phase: float = 0.0
        self._last_tick_t: float = 0.0
        # Retained values for graceful degradation
        self._last_breath_rate: float = 0.0
        self._last_hr: float = 0.0
        self._last_rmssd: float = 0.0
        self._tick_count: int = 0
        self._diag_logged: bool = False
        # Bible Ch.2 §2.9 §2.3 — cardiac phase tracking
        self._last_peak_time: float = 0.0
        self._mean_ibi_s: float = 0.0
        self._ibi_ema_alpha: float = 0.3
        # Bible Ch.2 §2.9 §2.6 — autonomic depth calibration
        self._baseline_rmssd: float | None = None
        self._calibration_rmssd_samples: list[float] = []
        self._calibration_start_time: float = 0.0
        self._calibrated: bool = False
        self._current_autonomic_depth: float = 0.0
        # Staleness tracking — last time fresh metrics were computed
        self._last_fresh_ts: float = 0.0
        self._STALE_TIMEOUT_S: float = 5.0

    # ── Public interface ───────────────────────────────────────────────────────

    def tick(self, board: object, board_id: int) -> dict:
        """
        Read one 1-second chunk from ANCILLARY_PRESET, extend rolling buffer,
        and return a metrics dict for the caller to pass to patch_live().

        Returns {} on hard failure (BrainFlow error) so the caller can skip
        the patch_live() call safely.  Returns a dict with ppg_available=False on soft
        failures (insufficient data) so consumers know the signal is present
        but not yet warm.
        """
        try:
            from brainflow.board_shim import BoardShim, BrainFlowPresets

            n = _PPG_SR  # 1-second chunk
            data = board.get_current_board_data(  # type: ignore[attr-defined]
                n, BrainFlowPresets.ANCILLARY_PRESET
            )

            if data.shape[1] < 8:
                return {"ppg_available": False}

            ppg_chans = BoardShim.get_ppg_channels(
                board_id, BrainFlowPresets.ANCILLARY_PRESET
            )
            if not ppg_chans:
                return {"ppg_available": False}

            # Prefer IR channel (index 1) — most stable for forehead PPG.
            # Fall back to index 0 if only one channel is available.
            ir_idx = ppg_chans[min(1, len(ppg_chans) - 1)]
            ir_chunk = data[ir_idx]
            self._buffer.extend(ir_chunk.tolist())

        except Exception:
            return {}

        # ── Need at least 4 seconds to detect meaningful peaks ────────────────
        if len(self._buffer) < _PPG_SR * 4:
            return {"ppg_available": False}

        arr = np.array(self._buffer, dtype=np.float64)
        arr = arr - np.mean(arr)  # remove DC offset
        peaks = _detect_peaks(arr, _PPG_SR, _PEAK_THRESH)

        if len(peaks) < _MIN_BEATS:
            # Advance phase clock with last known rate and return stale metrics
            self._advance_phase()
            return self._emit(available=True)

        # ── Inter-beat intervals ──────────────────────────────────────────────
        ibis_raw = np.diff(peaks) / _PPG_SR  # seconds
        ibis = ibis_raw[(ibis_raw >= _MIN_IBI_S) & (ibis_raw <= _MAX_IBI_S)]

        if len(ibis) < 2:
            self._advance_phase()
            return self._emit(available=True)

        hr = float(60.0 / np.mean(ibis))
        rmssd = float(np.sqrt(np.mean(np.diff(ibis * 1000.0) ** 2)))  # ms

        # ── Respiratory rate via RSA spectral method ──────────────────────────
        breath_rate = _extract_resp_rate(ibis, self._last_breath_rate)

        # ── Cardiac phase tracking (Bible Ch.2 §2.9 §2.5) ─────────────────────────────
        now = time.monotonic()
        samples_since_peak = len(arr) - int(peaks[-1])
        peak_age_s = samples_since_peak / _PPG_SR
        self._last_peak_time = now - peak_age_s
        current_mean_ibi = float(np.mean(ibis))
        if self._mean_ibi_s > 0:
            self._mean_ibi_s = (
                1 - self._ibi_ema_alpha
            ) * self._mean_ibi_s + self._ibi_ema_alpha * current_mean_ibi
        else:
            self._mean_ibi_s = current_mean_ibi

        # ── Autonomic depth calibration (Bible Ch.2 §2.9 §2.6) ────────────────────────
        if not self._calibrated:
            if self._calibration_start_time == 0:
                self._calibration_start_time = now
            self._calibration_rmssd_samples.append(rmssd)
            if (now - self._calibration_start_time) >= _CALIBRATION_S:
                if len(self._calibration_rmssd_samples) >= 10:
                    self._baseline_rmssd = float(
                        np.median(self._calibration_rmssd_samples)
                    )
                    self._calibrated = True

        if self._calibrated and self._baseline_rmssd and self._baseline_rmssd > 0:
            relative_rmssd = (rmssd - self._baseline_rmssd) / self._baseline_rmssd
            auto_depth = 1.0 / (
                1.0
                + np.exp(
                    -_AUTONOMIC_SIGMOID_SLOPE
                    * (relative_rmssd - _AUTONOMIC_SIGMOID_CENTER)
                )
            )
            self._current_autonomic_depth = float(np.clip(auto_depth, 0.0, 1.0))
        else:
            self._current_autonomic_depth = 0.0

        # ── Advance breath phase clock ────────────────────────────────────────
        self._last_breath_rate = breath_rate
        self._last_hr = hr
        self._last_rmssd = rmssd
        self._advance_phase()

        return self._emit(available=True)

    # ── Internals ─────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear all buffers and retained values for post-reconnect clean state."""
        self._buffer.clear()
        self._breath_phase = 0.0
        self._last_tick_t = 0.0
        self._last_breath_rate = 0.0
        self._last_hr = 0.0
        self._last_rmssd = 0.0
        self._tick_count = 0
        self._last_peak_time = 0.0
        self._mean_ibi_s = 0.0
        self._last_fresh_ts = 0.0

    def _advance_phase(self) -> None:
        """Step the breath phase clock by elapsed wall time × breath_rate."""
        now = time.monotonic()
        if self._last_tick_t > 0 and self._last_breath_rate > 0:
            dt = now - self._last_tick_t
            self._breath_phase = (
                self._breath_phase + dt * self._last_breath_rate
            ) % 1.0
        self._last_tick_t = now

    def _emit(self, available: bool) -> dict:
        now = time.monotonic()

        if available and self._last_hr > 0:
            self._last_fresh_ts = now

        stale = (now - self._last_fresh_ts) > self._STALE_TIMEOUT_S
        if stale or not available:
            return {
                "ppg_available": False,
                "ppg_heart_rate": None,
                "ppg_hrv_rmssd": None,
                "ppg_breath_rate": None,
                "ppg_breath_phase": None,
                "ppg_cardiac_phase": None,
                "ppg_cardiac_diastole": None,
                "ppg_last_peak_age_ms": None,
                "ppg_autonomic_depth": None,
                "ppg_autonomic_baseline": (
                    round(self._baseline_rmssd, 1)
                    if self._baseline_rmssd is not None
                    else None
                ),
                "ppg_autonomic_calibrated": self._calibrated,
            }

        peak_age_ms = (
            (now - self._last_peak_time) * 1000.0 if self._last_peak_time > 0 else 0.0
        )
        if self._mean_ibi_s > 0:
            cardiac_phase = min(1.0, peak_age_ms / (self._mean_ibi_s * 1000.0))
            diastole_end_ms = self._mean_ibi_s * 1000.0 * _DIASTOLE_END_FRAC
            cardiac_diastole = float(_SYSTOLE_GUARD_MS) < peak_age_ms < diastole_end_ms
        else:
            cardiac_phase = 0.5
            cardiac_diastole = True
        return {
            "ppg_available": True,
            "ppg_heart_rate": round(self._last_hr, 1),
            "ppg_hrv_rmssd": round(self._last_rmssd, 1),
            "ppg_breath_rate": round(self._last_breath_rate, 4),
            "ppg_breath_phase": round(self._breath_phase, 4),
            "ppg_cardiac_phase": round(cardiac_phase, 3),
            "ppg_cardiac_diastole": cardiac_diastole,
            "ppg_last_peak_age_ms": round(peak_age_ms, 1),
            "ppg_autonomic_depth": round(self._current_autonomic_depth, 3),
            "ppg_autonomic_baseline": (
                round(self._baseline_rmssd, 1)
                if self._baseline_rmssd is not None
                else None
            ),
            "ppg_autonomic_calibrated": self._calibrated,
        }


# ── Module-level helpers ───────────────────────────────────────────────────────


def _detect_peaks(arr: np.ndarray, sr: int, thresh_factor: float) -> np.ndarray:
    """
    Find R-peaks in a DC-removed PPG signal.

    Parameters
    ----------
    arr          : DC-removed PPG signal (arbitrary units).
    sr           : Sample rate in Hz.
    thresh_factor: Fraction of std used as detection threshold.

    Returns
    -------
    np.ndarray of integer sample indices of detected peaks.
    """
    threshold = float(np.std(arr)) * thresh_factor
    min_dist = int(sr * _MIN_IBI_S)  # samples equivalent to 300 ms

    peaks: list[int] = []
    i = 1
    while i < len(arr) - 1:
        if arr[i] > threshold and arr[i] > arr[i - 1] and arr[i] >= arr[i + 1]:
            # Enforce refractory period: only accept if far enough from last peak
            if not peaks or (i - peaks[-1]) >= min_dist:
                peaks.append(i)
                i += min_dist  # skip the refractory window
                continue
        i += 1

    return np.array(peaks, dtype=np.int64)


def _extract_resp_rate(ibis: np.ndarray, last_rate: float) -> float:
    """
    Estimate respiratory rate from the IBI series via a simple FFT.

    The IBI series is treated as uniformly sampled at ~1 Hz (approximately
    correct at resting heart rate).  The dominant frequency in the respiratory
    band (0.15–0.40 Hz) is returned.  Falls back to last_rate if the spectrum
    has insufficient peaks or the series is too short.
    """
    if len(ibis) < 6:
        return last_rate or 0.15  # 9 breaths/min safe default

    # Approximate sample rate of IBI series (mean heart rate)
    ibi_sr = float(1.0 / np.mean(ibis))  # Hz (e.g. 1.0 at 60 BPM)

    n = len(ibis)
    freqs = np.fft.rfftfreq(n, d=1.0 / ibi_sr)
    power = np.abs(np.fft.rfft(ibis - np.mean(ibis))) ** 2

    resp_mask = (freqs >= _RESP_LO_HZ) & (freqs <= _RESP_HI_HZ)
    if not np.any(resp_mask):
        return last_rate or 0.15

    peak_freq = float(freqs[resp_mask][np.argmax(power[resp_mask])])
    # Sanity check: must be in the valid respiratory range
    if _RESP_LO_HZ <= peak_freq <= _RESP_HI_HZ:
        # Blend toward new estimate to suppress rapid jumps
        if last_rate > 0:
            return last_rate * 0.6 + peak_freq * 0.4
        return peak_freq

    return last_rate or 0.15
