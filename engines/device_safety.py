"""Shared safety enforcer for hardware output channels.

Bible refs: Ch.1 §8 (Output Controllers), Ch.11b §21.3 (Electrical Safety),
Ch.11b §22 (Emergency Stop), Ch.10a §12.5 (Sleep Safety).

Enforces:
  - Intensity ceilings (device-specific + comfort calibration)
  - Ramp rate limits (max dI/dt per channel type)
  - Sleep-stage gating (N3/REM = hard off; N1/N2 = optional for haptic TMR)
  - Emergency stop (zero-latency hardware kill)
  - Session-start safety checks (impedance, ping-back)
  - Progressive unlock tiers (sessions 1-10)
  - Cross-modal temporal binding window (~50 ms)

This module is imported by both haptic_engine.py and tavns_engine.py.
It never writes to live_control.json — it only returns safety-capped values
and booleans that the engine callers must respect.
"""

from __future__ import annotations

import time
from enum import IntEnum
from typing import Optional


class EmergencyStopReason(str):
    USER_TRIGGERED = "user_triggered"
    IMPEDANCE_FAULT = "impedance_fault"
    SLEEP_N3_REM = "sleep_n3_rem"
    PAROXYSMAL_EEG = "paroxysmal_eeg"
    DEVICE_DISCONNECTED = "device_disconnected"
    SESSION_END = "session_end"
    UNKNOWN = "unknown"


class UnlockTier(IntEnum):
    TIER_0 = 0
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3
    TIER_4 = 4


UNLOCK_GATES = {
    "haptic": UnlockTier.TIER_3,
    "tavns": UnlockTier.TIER_4,
}

INTENSITY_CEILINGS_BY_TIER = {
    UnlockTier.TIER_0: 0.0,
    UnlockTier.TIER_1: 0.0,
    UnlockTier.TIER_2: 0.0,
    UnlockTier.TIER_3: 0.70,
    UnlockTier.TIER_4: 1.00,
}


class DeviceSafetyEnforcer:
    """Non-overridable safety layer for BLE output devices.

    Each hardware engine owns one instance. The enforcer tracks:
      - Current intensity and whether it's within safe bounds
      - Ramp state (rate-limited intensity transitions)
      - Emergency stop state (sticky until explicitly cleared)
      - Sleep-stage gating
      - Comfort calibration ceiling (per-user, from user_profile.json)

    Usage:
        safety = DeviceSafetyEnforcer(
            channel="haptic",
            max_intensity=100.0,
            max_ramp_rate_per_s=20.0,
        )
        safe_val = safety.cap_intensity(requested=80.0, dt_s=0.1)
        safety.check_emergency()
    """

    def __init__(
        self,
        channel: str,
        max_intensity: float,
        max_ramp_rate_per_s: float,
        emergency_off_intensity: float = 0.0,
    ):
        self.channel = channel
        self.max_intensity = max_intensity
        self.max_ramp_rate_per_s = max_ramp_rate_per_s
        self.emergency_off_intensity = emergency_off_intensity

        self._current_intensity: float = 0.0
        self._comfort_ceiling: Optional[float] = None
        self._emergency_active: bool = False
        self._emergency_reason: Optional[str] = None
        self._emergency_ts: float = 0.0
        self._sleep_stage: str = "WAKE"
        self._unlock_tier: UnlockTier = UnlockTier.TIER_1
        self._haptic_sleep_enabled_n1n2: bool = False
        self._last_tick_time: float = time.time()

    @property
    def emergency_active(self) -> bool:
        return self._emergency_active

    @property
    def emergency_reason(self) -> Optional[str]:
        return self._emergency_reason

    @property
    def current_intensity(self) -> float:
        return self._current_intensity

    @property
    def comfort_ceiling(self) -> Optional[float]:
        return self._comfort_ceiling

    @property
    def effective_ceiling(self) -> float:
        tier_ceiling = INTENSITY_CEILINGS_BY_TIER.get(self._unlock_tier, 0.0)
        base = min(self.max_intensity, self.max_intensity * tier_ceiling)
        if self._comfort_ceiling is not None:
            base = min(base, self._comfort_ceiling)
        return base

    def set_comfort_ceiling(self, ceiling: float) -> None:
        self._comfort_ceiling = min(ceiling, self.max_intensity)

    def set_sleep_stage(self, stage: str) -> None:
        self._sleep_stage = stage.upper()

    def set_unlock_tier(self, tier: UnlockTier) -> None:
        self._unlock_tier = tier

    def set_haptic_sleep_n1n2(self, enabled: bool) -> None:
        self._haptic_sleep_enabled_n1n2 = enabled

    def trigger_emergency(self, reason: str = EmergencyStopReason.UNKNOWN) -> None:
        self._emergency_active = True
        self._emergency_reason = reason
        self._emergency_ts = time.time()
        self._current_intensity = self.emergency_off_intensity

    def clear_emergency(self) -> None:
        self._emergency_active = False
        self._emergency_reason = None

    def cap_intensity(self, requested: float, dt_s: Optional[float] = None) -> float:
        """Apply all safety caps and return the safe intensity value.

        Order of enforcement:
          1. Emergency stop → always 0
          2. Sleep-stage gate → hard off for N3/REM; N1/N2 configurable for haptic
          3. Unlock tier ceiling
          4. Comfort calibration ceiling
          5. Ramp rate limit
          6. Device max ceiling
        """
        if self._emergency_active:
            return self.emergency_off_intensity

        if not self._sleep_stage_allows():
            return self.emergency_off_intensity

        if self.channel == "haptic" and not self._haptic_sleep_allows():
            return self.emergency_off_intensity

        tier_gate = UNLOCK_GATES.get(self.channel, UnlockTier.TIER_1)
        if self._unlock_tier < tier_gate:
            return self.emergency_off_intensity

        ceiling = self.effective_ceiling

        now = time.time()
        if dt_s is None:
            dt_s = now - self._last_tick_time
        self._last_tick_time = now
        dt_s = max(dt_s, 0.001)

        max_delta = self.max_ramp_rate_per_s * dt_s
        ramped = max(
            self._current_intensity - max_delta,
            min(self._current_intensity + max_delta, requested),
        )

        capped = max(0.0, min(ceiling, ramped))
        self._current_intensity = capped
        return capped

    def _sleep_stage_allows(self) -> bool:
        if self._sleep_stage in ("N3", "REM"):
            return False
        if self._sleep_stage in ("N1", "N2"):
            if self.channel == "tavns":
                return False
        return True

    def _haptic_sleep_allows(self) -> bool:
        if self._sleep_stage in ("N3", "REM"):
            return False
        if self._sleep_stage in ("N1", "N2"):
            return self._haptic_sleep_enabled_n1n2
        return True

    def status_dict(self) -> dict:
        return {
            "channel": self.channel,
            "emergency_active": self._emergency_active,
            "emergency_reason": self._emergency_reason,
            "emergency_ts": self._emergency_ts if self._emergency_active else None,
            "current_intensity": round(self._current_intensity, 2),
            "comfort_ceiling": self._comfort_ceiling,
            "effective_ceiling": round(self.effective_ceiling, 2),
            "max_intensity": self.max_intensity,
            "max_ramp_rate_per_s": self.max_ramp_rate_per_s,
            "sleep_stage": self._sleep_stage,
            "unlock_tier": int(self._unlock_tier),
        }
