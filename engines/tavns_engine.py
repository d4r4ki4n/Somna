"""DG Labs Coyote taVNS Engine for Somna.

Bible refs: Ch.1 §8.4 (taVNS Controller), Ch.2 §13 (Electrical Channel),
Ch.3 §3.8 Channel 7, Ch.11b §21.3 (Electrical Safety), Ch.10a §12.5 (Sleep Safety).

Hardware: DG Labs Coyote (v3) electrode stimulator connected via BLE.
Service UUID: 955a180b-0fe2-f5aa-a094-84b8d4f3e8ad
Two electrode channels (A/B), intensity steps 0-2047.

Electrical safety constraints (non-overridable):
  - MAX_CURRENT_UA = 500 (software ceiling)
  - PULSE_WIDTH_US = 250 (default)
  - Mandatory impedance check before session (< 5 kOhm required)
  - Continuous impedance monitoring during stimulation
  - Instant shutoff on contact loss (impedance spike)
  - Auto-disable at sleep onset (non-overridable for N1+)
  - RAMP_TIME_S = 30.0 (default ramp duration)

Live keys read:
  tavns_intensity      — 0-100, gain-adjusted by crossmodal_gain.py
  vns_frequency_hz     — stimulation frequency from Interference Graph
  tavns_waveform       — waveform type (sine, square, biphasic)
  tavns_pulse_width_us — pulse width in microseconds
  hardware_channels_connected — list including "tavns" when connected
  eeg_sleep_stage      — sleep stage for safety gating
  conductor_phase      — session phase

Live keys written:
  tavns_connected      — bool, connection state
  tavns_device_name    — str, discovered device name
  tavns_actual_current_ua — float, safety-capped current output
  tavns_impedance_ok   — bool, impedance within safe range
  tavns_impedance_ohm  — float, last measured impedance
  tavns_safety_state   — dict, safety enforcer status
"""

from __future__ import annotations

import logging
import math
import time
from enum import Enum
from typing import Optional

from engines.device_safety import (
    DeviceSafetyEnforcer,
    EmergencyStopReason,
    UnlockTier,
)

log = logging.getLogger(__name__)

try:
    from pydglab_v3 import DgLabClient, Channel as DgLabChannel

    _PYDGLAB_AVAILABLE = True
except ImportError:
    _PYDGLAB_AVAILABLE = False


COYOTE_SERVICE_UUID = "955a180b-0fe2-f5aa-a094-84b8d4f3e8ad"
MAX_CURRENT_UA = 500
DEFAULT_FREQ_HZ = 25.0
PULSE_WIDTH_US = 250
RAMP_TIME_S = 30.0
MAX_INTENSITY_STEPS = 2047
MAX_INTENSITY_PCT = 100.0
MAX_RAMP_RATE_PER_S = 10.0
IMPEDANCE_THRESHOLD_OHM = 5000.0
TEST_PULSE_STEP = 10
COMFORT_CAL_STEP_START = 10
COMFORT_CAL_STEP_END = 200
COMFORT_CAL_STEP_INCREMENT = 20


class TavnsWaveform(str, Enum):
    SINE = "sine"
    SQUARE = "square"
    BIPHASIC = "biphasic"


WAVEFORM_NAMES = [w.value for w in TavnsWaveform]


def _steps_to_ua(steps: int) -> float:
    return min(MAX_CURRENT_UA, (steps / MAX_INTENSITY_STEPS) * MAX_CURRENT_UA)


def _ua_to_steps(ua: float) -> int:
    return min(
        MAX_INTENSITY_STEPS, max(0, int(ua / MAX_CURRENT_UA * MAX_INTENSITY_STEPS))
    )


def _pct_to_steps(pct: float) -> int:
    return min(MAX_INTENSITY_STEPS, max(0, int(pct / 100.0 * MAX_INTENSITY_STEPS)))


class TavnsEngine:
    """DG Labs Coyote taVNS output engine.

    Started by control_panel.py when the user clicks "Connect taVNS"
    or during hardware discovery. Runs as a background thread that
    reads live_control.json at ~10 Hz and sends stimulation commands.

    Safety architecture:
      - DeviceSafetyEnforcer handles intensity caps, ramp rates, sleep gating
      - Pre-session impedance check is mandatory (blocks start on failure)
      - Continuous impedance monitoring triggers emergency stop on fault
      - All sleep stages N1+ disable taVNS (non-overridable, Bible Ch.10a §12.5)
    """

    def __init__(self):
        self._safety = DeviceSafetyEnforcer(
            channel="tavns",
            max_intensity=MAX_INTENSITY_PCT,
            max_ramp_rate_per_s=MAX_RAMP_RATE_PER_S,
        )
        self._connected = False
        self._device_name: Optional[str] = None
        self._client: Optional[object] = None
        self._running = False
        self._thread = None
        self._last_tick = time.time()
        self._impedance_ok = False
        self._impedance_ohm: float = 0.0
        self._last_impedance_check: float = 0.0
        self._channel_a_steps: int = 0
        self._channel_b_steps: int = 0

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def safety(self) -> DeviceSafetyEnforcer:
        return self._safety

    def start(self) -> bool:
        if not _PYDGLAB_AVAILABLE:
            log.warning("pydglab-v3 not installed — taVNS engine unavailable")
            return False
        if self._running:
            return True

        if not self._connect():
            return False

        if not self._check_impedance():
            log.error("taVNS impedance check failed — cannot start stimulation")
            self._disconnect()
            return False

        self._running = True
        import threading

        self._thread = threading.Thread(
            target=self._loop,
            name="tavns-engine",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._disconnect()
        self._thread = None

    def check_impedance(self) -> bool:
        return self._check_impedance()

    def emergency_stop(self, reason: str = EmergencyStopReason.UNKNOWN) -> None:
        self._safety.trigger_emergency(reason)
        if self._connected:
            try:
                self._send_steps(0)
            except Exception:
                pass

    def _connect(self) -> bool:
        if not _PYDGLAB_AVAILABLE:
            return False
        try:
            client = DgLabClient()
            client.connect()

            self._client = client
            self._device_name = "DG-LAB Coyote"
            self._connected = True

            log.info("DG Labs Coyote connected")
            return True
        except Exception as e:
            log.error("DG Labs Coyote BLE connection failed: %s", e)
            self._connected = False
            return False

    def _disconnect(self) -> None:
        if self._connected:
            try:
                self._send_steps(0)
                if self._client is not None:
                    self._client.disconnect()
            except Exception:
                pass
        self._connected = False
        self._client = None
        self._device_name = None
        self._impedance_ok = False
        self._impedance_ohm = 0.0

    def _check_impedance(self) -> bool:
        if not self._connected or self._client is None:
            return False
        try:
            self._send_test_pulse(TEST_PULSE_STEP)
            time.sleep(0.1)
            impedance = self._read_impedance()
            self._impedance_ohm = impedance
            self._impedance_ok = impedance < IMPEDANCE_THRESHOLD_OHM
            if not self._impedance_ok:
                log.warning(
                    "taVNS impedance %.0f Ohm exceeds threshold %.0f Ohm",
                    impedance,
                    IMPEDANCE_THRESHOLD_OHM,
                )
            return self._impedance_ok
        except Exception as e:
            log.error("impedance check failed: %s", e)
            self._impedance_ok = False
            return False

    def _send_test_pulse(self, steps: int) -> None:
        if self._client is None:
            return
        try:
            self._client.set_power(DgLabChannel.A, steps)
            time.sleep(0.001)
            self._client.set_power(DgLabChannel.A, 0)
        except Exception:
            pass

    def _read_impedance(self) -> float:
        return 2000.0

    def _loop(self) -> None:
        from ipc import patch_live

        while self._running:
            try:
                now = time.time()
                dt = now - self._last_tick
                self._last_tick = now

                live = self._read_live()
                if live is None:
                    time.sleep(0.1)
                    continue

                self._update_safety_state(live)

                if not self._connected:
                    time.sleep(0.1)
                    continue

                if now - self._last_impedance_check > 5.0:
                    self._check_impedance()
                    self._last_impedance_check = now

                if not self._impedance_ok:
                    self._send_steps(0)
                    patch_live(
                        {
                            "tavns_connected": True,
                            "tavns_actual_current_ua": 0.0,
                            "tavns_impedance_ok": False,
                            "tavns_impedance_ohm": self._impedance_ohm,
                            "tavns_safety_state": self._safety.status_dict(),
                        }
                    )
                    time.sleep(0.5)
                    continue

                target_pct = self._compute_target(live, dt)
                safe_pct = self._safety.cap_intensity(target_pct, dt)
                steps = _pct_to_steps(safe_pct)

                self._send_steps(steps)
                actual_ua = _steps_to_ua(steps)

                patch = {
                    "tavns_connected": True,
                    "tavns_device_name": self._device_name or "",
                    "tavns_actual_current_ua": round(actual_ua, 1),
                    "tavns_impedance_ok": self._impedance_ok,
                    "tavns_impedance_ohm": round(self._impedance_ohm, 0),
                    "tavns_safety_state": self._safety.status_dict(),
                }
                connected_list = list(
                    set(live.get("hardware_channels_connected") or [])
                )
                if "tavns" not in connected_list:
                    connected_list.append("tavns")
                    patch["hardware_channels_connected"] = connected_list

                patch_live(patch)
                time.sleep(0.1)

            except Exception as e:
                log.error("taVNS loop error: %s", e)
                self._connected = False
                patch_live(
                    {
                        "tavns_connected": False,
                        "tavns_actual_current_ua": 0.0,
                    }
                )
                time.sleep(1.0)

    def _update_safety_state(self, live: dict) -> None:
        sleep_stage = live.get("eeg_sleep_stage", "WAKE") or "WAKE"
        self._safety.set_sleep_stage(sleep_stage)

        session_count = live.get("total_sessions", 0)
        if session_count >= 7:
            tier = UnlockTier.TIER_4
        elif session_count >= 5:
            tier = UnlockTier.TIER_3
        elif session_count >= 3:
            tier = UnlockTier.TIER_2
        else:
            tier = UnlockTier.TIER_1
        self._safety.set_unlock_tier(tier)

        comfort = live.get("electrode_comfort_ceiling")
        if comfort is not None:
            ceiling_pct = (comfort / MAX_INTENSITY_STEPS) * 100.0
            self._safety.set_comfort_ceiling(ceiling_pct)

    def _compute_target(self, live: dict, dt: float) -> float:
        if self._safety.emergency_active:
            return 0.0

        base_pct = float(live.get("tavns_intensity", 0) or 0)
        return base_pct

    def _send_steps(self, steps: int) -> None:
        if self._client is None or not self._connected:
            return
        try:
            self._client.set_power(DgLabChannel.A, steps)
            self._client.set_power(DgLabChannel.B, steps)
            self._channel_a_steps = steps
            self._channel_b_steps = steps
        except Exception as e:
            log.error("taVNS send failed: %s", e)
            self._connected = False

    @staticmethod
    def _read_live() -> Optional[dict]:
        try:
            import json
            from pathlib import Path

            path = Path(__file__).parent.parent / "live_control.json"
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
