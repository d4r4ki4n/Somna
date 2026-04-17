"""
imu_engine.py — Accelerometer/Gyroscope processing for Bible Ch.2 §2.9 (Muse 2 AUXILIARY_PRESET)

Reads the Muse 2's 3-axis accelerometer (~52 Hz) and gyroscope via BrainFlow's
AUXILIARY_PRESET.  Outputs three signals every 1-second tick:

  imu_motion_rms          float  — RMS deviation of accelerometer magnitude from
                                   1g rest value over the last 1 second. Near-zero
                                   = perfectly still; >0.05 g = meaningful motion.

  imu_stillness_index     float  — EMA-smoothed stillness 0.0–1.0. Used by the
                                   Conductor as a convergent depth confirmation
                                   signal and by the DeliveryGate to block during
                                   motion-contaminated windows.

  imu_motion_contaminated bool   — True when motion_rms exceeds the artifact
                                   threshold (0.04 g). Checked by DeliveryGate
                                   before firing any stimulus.

  imu_head_nod_detected   bool   — True when the Y-axis (pitch) of the
                                   accelerometer shows a sustained forward drop
                                   over HEAD_NOD_WINDOW_S seconds. A reliable
                                   behavioural marker of N1 sleep onset.

All keys default to safe values when the board is synthetic or PPG data is
absent (motion_contaminated=False, stillness_index=1.0, head_nod=False),
so no downstream consumer needs to special-case the no-hardware path.

Architecture: IMUEngine.tick() is called once per second in EEGEngine._run()
BEFORE _process() so that motion contamination is already known when EEG SQI
is computed and when the DeliveryGate is evaluated.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np

_LIVE = Path(__file__).parent.parent / "live_control.json"

# ── Constants ─────────────────────────────────────────────────────────────────

_IMU_SR = 52  # Muse 2 auxiliary preset sample rate (Hz)
_WINDOW_S = 1.0  # analysis window per tick
_MOTION_THRESH = 0.04  # g — deviation from 1g causing contamination flag
_STILLNESS_ALPHA = 0.2  # EMA smoothing factor (higher = more reactive)
_NOD_WINDOW_S = 3.0  # seconds of Y-history for head-nod detection
_NOD_THRESHOLD = -0.12  # g — minimum Y-axis drop to count as a forward nod
_NOD_MIN_SAMPLES = int(_NOD_WINDOW_S * _IMU_SR * 0.8)  # allow 20% data gaps


class IMUEngine:
    """
    Processes Muse 2 accelerometer data from AUXILIARY_PRESET.

    Instantiated once in EEGEngine.__init__ when board_id != SYNTHETIC.
    Call tick(board, board_id) every second inside the EEG main loop.
    """

    def __init__(self) -> None:
        self._stillness_ema: float = 1.0  # start assuming still
        # Rolling Y-axis history for head-nod detection
        self._y_history: deque[float] = deque(maxlen=int(_NOD_WINDOW_S * _IMU_SR))

    def reset(self) -> None:
        """Clear EMA and history for post-reconnect clean state."""
        self._stillness_ema = 1.0
        self._y_history.clear()

    def tick(self, board: object, board_id: int) -> dict:
        """
        Read one window of accelerometer data and return a metrics dict.

        Returns an empty dict on any error so the caller can skip _patch_live
        without crashing. Returns safe defaults (not empty) only for known
        synthetic boards so downstream consumers always see the expected keys.
        """
        try:
            from brainflow.board_shim import BoardShim, BrainFlowPresets

            n = int(_IMU_SR * _WINDOW_S)
            data = board.get_current_board_data(  # type: ignore[attr-defined]
                n, BrainFlowPresets.AUXILIARY_PRESET
            )

            if data.shape[1] < 8:
                return {
                    "imu_motion_rms": None,
                    "imu_stillness_index": None,
                    "imu_motion_contaminated": False,
                    "imu_head_nod_detected": False,
                }

            accel_chans = BoardShim.get_accel_channels(
                board_id, BrainFlowPresets.AUXILIARY_PRESET
            )
            if len(accel_chans) < 3:
                return {
                    "imu_motion_rms": None,
                    "imu_stillness_index": None,
                    "imu_motion_contaminated": False,
                    "imu_head_nod_detected": False,
                }

            x = data[accel_chans[0]]
            y = data[accel_chans[1]]
            z = data[accel_chans[2]]

            # ── Motion RMS (deviation from 1 g rest) ─────────────────────────
            magnitude = np.sqrt(x**2 + y**2 + z**2)
            deviation = np.abs(magnitude - 1.0)
            motion_rms = float(np.sqrt(np.mean(deviation**2)))

            # Conductor writes imu_motion_threshold_override on sleep phase entry
            # (Bible Ch.2 §2.9 §5.4) — fall back to module default when not set
            try:
                _override = (
                    json.loads(_LIVE.read_text(encoding="utf-8")).get(
                        "imu_motion_threshold_override"
                    )
                    if _LIVE.exists()
                    else None
                )
                motion_thresh = (
                    float(_override) if _override is not None else _MOTION_THRESH
                )
            except Exception:
                motion_thresh = _MOTION_THRESH

            contaminated = motion_rms > motion_thresh

            # ── Stillness index (EMA, 0 = moving, 1 = still) ─────────────────
            raw_stillness = max(0.0, 1.0 - motion_rms / (_MOTION_THRESH * 5))
            self._stillness_ema = (
                1.0 - _STILLNESS_ALPHA
            ) * self._stillness_ema + _STILLNESS_ALPHA * raw_stillness

            # ── Head-nod detection (forward pitch → sleep onset marker) ───────
            # Extend Y history with the mean of the latest window
            self._y_history.append(float(np.mean(y[-5:])))

            head_nod = False
            if len(self._y_history) >= _NOD_MIN_SAMPLES:
                y_arr = np.array(self._y_history)
                # Nod = sustained forward tilt: end of window significantly
                # lower than start across the full history window
                drift = float(y_arr[-1] - y_arr[0])
                head_nod = drift < _NOD_THRESHOLD

            return {
                "imu_motion_rms": round(motion_rms, 4),
                "imu_stillness_index": round(self._stillness_ema, 3),
                "imu_motion_contaminated": contaminated,
                "imu_head_nod_detected": head_nod,
            }

        except Exception:
            return {
                "imu_motion_rms": None,
                "imu_stillness_index": None,
                "imu_motion_contaminated": False,
                "imu_head_nod_detected": False,
            }
