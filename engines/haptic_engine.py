"""Lovense BLE Haptic Engine for Somna.

Bible refs: Ch.1 §8.3 (Haptic Controller), Ch.2 §12 (Haptic Channel),
Ch.3 §3.8 Channel 6, Ch.6 §4-8 (Conditioning Delivery).

Hardware: Lovense vibrotactile devices connected via BLE using the
Buttplug.io protocol (buttplug-py library). Device discovery uses
manufacturer-specific advertising data with company ID 0x0396 and
device name prefix "LVS-".

Motor count is device-dependent (Edge 2 = 2 motors, Nora = 2, etc.).
The engine auto-detects motor count on connection.

Dual-motor vibrotactile beats: When two motors vibrate at slightly
different intensities, the user perceives a low-frequency beat — a
haptic analog of binaural beats. The haptic_frequency_hz parameter
controls the *perceived beat frequency* by oscillating the intensity
delta between motors at the target rate. This enables somatic
entrainment at theta/delta frequencies even though the motors
themselves operate at fixed hardware rates.

Live keys read:
  haptic_intensity     — 0-100, gain-adjusted by crossmodal_gain.py
  haptic_frequency_hz  — perceived beat frequency from Interference Graph
  haptic_pattern       — pattern name (continuous, pulse, wave, ramp, fractionation)
  haptic_pattern_speed — pattern cycle speed 0.1-10.0
  hardware_channels_connected — list including "haptic" when connected
  sleep_stage          — WAKE/N1/N2/N3/REM for sleep gating
  conductor_phase      — session phase for pattern selection

Live keys written:
  haptic_connected     — bool, connection state
  haptic_device_name   — str, discovered device name
  haptic_motor_count   — int, number of motors detected
  haptic_actual_intensity — float, safety-capped current output (primary motor)
  haptic_safety_state  — dict, safety enforcer status

Pattern types:
  continuous  — steady vibration at set intensity and frequency
  pulse       — on/off at pattern_speed Hz, duty cycle 50%
  wave        — sinusoidal intensity modulation at pattern_speed Hz
  ramp        — linear ramp from 0 to intensity over pattern_speed seconds
  fractionation — emerge/hold/reinduce cycle matching Conductor FSM
  tmr_cue     — brief 200ms burst for TMR haptic anchor delivery
  conditioned_anchor — Pavlovian anchor pattern (Bible Ch.1 §15.5)
"""

from __future__ import annotations

import asyncio
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
    from buttplug import Client, WebsocketConnector

    _BUTTPLUG_AVAILABLE = True
except ImportError:
    _BUTTPLUG_AVAILABLE = False


LOVENSE_NAME_PREFIX = "Lovense"
DEFAULT_INTENSITY = 0.0
MAX_INTENSITY = 100.0
MAX_RAMP_RATE_PER_S = 20.0
PING_BACK_DURATION_S = 0.2
PING_BACK_INTENSITY = 20.0
COMFORT_CAL_START = 10.0
COMFORT_CAL_END = 50.0
COMFORT_CAL_STEP = 5.0
COMFORT_CAL_HOLD_S = 3.0
TMR_CUE_DURATION_S = 0.2
CONDITIONED_ANCHOR_DURATION_S = 0.5
CONDITIONED_ANCHOR_FREQ_HZ = 25.0


class HapticPattern(str, Enum):
    CONTINUOUS = "continuous"
    PULSE = "pulse"
    WAVE = "wave"
    RAMP = "ramp"
    FRACTIONATION = "fractionation"
    TMR_CUE = "tmr_cue"
    CONDITIONED_ANCHOR = "conditioned_anchor"


PATTERN_NAMES = [p.value for p in HapticPattern]


class HapticEngine:
    """Lovense BLE haptic output engine.

    Started by control_panel_imgui.py when the user clicks "Connect Lovense"
    or during hardware discovery. Runs as an asyncio event loop in a background
    thread that reads live_control.json at ~10 Hz and sends commands to the device.
    """

    def __init__(self):
        self._safety = DeviceSafetyEnforcer(
            channel="haptic",
            max_intensity=MAX_INTENSITY,
            max_ramp_rate_per_s=MAX_RAMP_RATE_PER_S,
        )
        self._connected = False
        self._device_name: Optional[str] = None
        self._motor_count: int = 0
        self._client: Optional[Client] = None
        self._device = None
        self._running = False
        self._thread = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_tick = time.time()
        self._pattern_state: dict = {}

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def safety(self) -> DeviceSafetyEnforcer:
        return self._safety

    def start(self, connector_url: str = "ws://127.0.0.1:12345") -> bool:
        if not _BUTTPLUG_AVAILABLE:
            log.warning("buttplug-py not installed — haptic engine unavailable")
            return False
        if self._running:
            return True

        self._running = True
        import threading

        self._thread = threading.Thread(
            target=self._thread_entry,
            args=(connector_url,),
            name="haptic-engine",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._loop is not None and not self._loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self._async_disconnect(), self._loop)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        self._loop = None

    def ping_back(self) -> bool:
        if not self._connected or self._device is None:
            return False
        try:
            if self._loop is not None and not self._loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(
                    self._async_send(PING_BACK_INTENSITY), self._loop
                )
                future.result(timeout=2.0)
                time.sleep(PING_BACK_DURATION_S)
                future = asyncio.run_coroutine_threadsafe(
                    self._async_send(0.0), self._loop
                )
                future.result(timeout=2.0)
            return True
        except Exception as e:
            log.error("haptic ping-back failed: %s", e)
            return False

    def start_comfort_calibration(self) -> None:
        self._pattern_state = {
            "type": "comfort_cal",
            "current": COMFORT_CAL_START,
            "step_time": time.time(),
            "done": False,
            "ceiling": None,
        }

    def advance_comfort_calibration(self) -> Optional[float]:
        """Advance to next calibration step. Returns the new intensity, or
        None if calibration is complete (ceiling already set)."""
        ps = self._pattern_state
        if ps.get("type") != "comfort_cal" or ps.get("done"):
            return None
        nxt = ps["current"] + COMFORT_CAL_STEP
        if nxt > COMFORT_CAL_END:
            ps["done"] = True
            ps["ceiling"] = ps["current"]
            return None
        ps["current"] = nxt
        ps["step_time"] = time.time()
        return nxt

    def finish_comfort_calibration(self, ceiling: Optional[float] = None) -> float:
        """End calibration. Returns the recorded ceiling."""
        ps = self._pattern_state
        ps["done"] = True
        if ceiling is not None:
            ps["ceiling"] = ceiling
        elif ps.get("ceiling") is None:
            ps["ceiling"] = ps.get("current", COMFORT_CAL_START)
        return ps["ceiling"]

    def comfort_calibration_active(self) -> bool:
        return self._pattern_state.get(
            "type"
        ) == "comfort_cal" and not self._pattern_state.get("done", False)

    def comfort_calibration_state(self) -> Optional[dict]:
        if self._pattern_state.get("type") != "comfort_cal":
            return None
        return dict(self._pattern_state)

    def trigger_tmr_cue(self, intensity: float = 30.0) -> None:
        if not self._connected or self._loop is None:
            return
        safe = self._safety.cap_intensity(intensity)
        try:
            asyncio.run_coroutine_threadsafe(self._async_send(safe), self._loop)
            time.sleep(TMR_CUE_DURATION_S)
            asyncio.run_coroutine_threadsafe(self._async_send(0.0), self._loop)
        except Exception as e:
            log.error("TMR cue failed: %s", e)

    def trigger_conditioned_anchor(self, intensity: float = 60.0) -> None:
        if not self._connected or self._loop is None:
            return
        safe = self._safety.cap_intensity(intensity)
        try:
            asyncio.run_coroutine_threadsafe(self._async_send(safe), self._loop)
            time.sleep(CONDITIONED_ANCHOR_DURATION_S)
            asyncio.run_coroutine_threadsafe(self._async_send(0.0), self._loop)
        except Exception as e:
            log.error("conditioned anchor failed: %s", e)

    def emergency_stop(self, reason: str = EmergencyStopReason.UNKNOWN) -> None:
        self._safety.trigger_emergency(reason)
        if self._connected and self._loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(self._async_send(0.0), self._loop)
            except Exception:
                pass

    # ── Async internals ──────────────────────────────────────────────────────

    def _thread_entry(self, connector_url: str) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_run(connector_url))
        except Exception as e:
            log.error("haptic engine loop crashed: %s", e)
        finally:
            self._connected = False
            self._loop.close()

    async def _async_run(self, connector_url: str) -> None:
        if not await self._async_connect(connector_url):
            return

        from ipc import patch_live

        try:
            while self._running:
                try:
                    now = time.time()
                    dt = now - self._last_tick
                    self._last_tick = now

                    live = self._read_live()
                    if live is None:
                        await asyncio.sleep(0.1)
                        continue

                    self._update_safety_state(live)

                    if not self._connected:
                        await asyncio.sleep(0.1)
                        continue

                    target = self._compute_target(live, dt)
                    safe = self._safety.cap_intensity(target, dt)

                    beat_hz = float(live.get("haptic_frequency_hz", 0.0) or 0.0)
                    secondary = self._compute_vtb_secondary(safe, beat_hz)
                    await self._async_send(safe, secondary=secondary)

                    haptic_cue = live.get("tmr_haptic_cue")
                    if haptic_cue and isinstance(haptic_cue, dict):
                        cue_ts = float(haptic_cue.get("ts", 0))
                        if abs(time.time() - cue_ts) < 0.5:
                            cue_intensity = float(haptic_cue.get("intensity", 30.0))
                            cue_dur = float(haptic_cue.get("duration_s", 0.2))
                            cue_safe = self._safety.cap_intensity(cue_intensity)
                            if cue_safe > 0:
                                await self._async_send(cue_safe)
                                await asyncio.sleep(cue_dur)
                                await self._async_send(safe)

                    patch = {
                        "haptic_connected": True,
                        "haptic_device_name": self._device_name or "",
                        "haptic_motor_count": self._motor_count,
                        "haptic_actual_intensity": round(safe, 2),
                        "haptic_vtb_active": secondary is not None,
                        "haptic_vtb_secondary": round(secondary, 2)
                        if secondary is not None
                        else None,
                        "haptic_safety_state": self._safety.status_dict(),
                    }
                    connected_list = list(
                        set(live.get("hardware_channels_connected") or [])
                    )
                    if "haptic" not in connected_list:
                        connected_list.append("haptic")
                        patch["hardware_channels_connected"] = connected_list

                    patch_live(patch)
                    await asyncio.sleep(0.1)

                except Exception as e:
                    log.error("haptic loop error: %s", e)
                    self._connected = False
                    try:
                        patch_live(
                            {
                                "haptic_connected": False,
                                "haptic_actual_intensity": 0.0,
                            }
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(1.0)
        finally:
            await self._async_disconnect()

    async def _async_connect(self, connector_url: str) -> bool:
        try:
            client = Client("Somna Haptic")
            connector = WebsocketConnector(connector_url)
            await client.connect(connector)

            await client.start_scanning()
            await asyncio.sleep(5.0)

            lovense_devices = [
                d
                for d in client.devices.values()
                if d.name and LOVENSE_NAME_PREFIX in d.name
            ]
            if not lovense_devices:
                log.warning("no Lovense devices found (scanned 5 s)")
                await client.disconnect()
                return False

            self._device = lovense_devices[0]
            self._device_name = self._device.name
            self._motor_count = len(self._device.actuators)
            self._client = client
            self._connected = True

            log.info(
                "Lovense connected: %s (%d motors)",
                self._device_name,
                self._motor_count,
            )
            return True
        except Exception as e:
            log.error("Lovense BLE connection failed: %s", e)
            self._connected = False
            return False

    async def _async_disconnect(self) -> None:
        if self._connected and self._client is not None:
            try:
                await self._async_send(0.0)
                await self._client.disconnect()
            except Exception:
                pass
        self._connected = False
        self._device = None
        self._client = None
        self._device_name = None
        self._motor_count = 0

    async def _async_send(
        self, intensity: float, secondary: float | None = None
    ) -> None:
        """Send intensity to device motors.

        For single-motor devices, secondary is ignored.
        For dual-motor devices, secondary controls motor 1 if provided,
        otherwise both motors get the same intensity.
        """
        if self._device is None or not self._connected:
            return
        primary = max(0.0, min(1.0, intensity / 100.0))
        sec = (
            max(0.0, min(1.0, secondary / 100.0)) if secondary is not None else primary
        )
        try:
            actuators = list(self._device.actuators)
            if len(actuators) >= 2 and secondary is not None:
                await actuators[0].command(primary)
                await actuators[1].command(sec)
            else:
                for actuator in actuators:
                    await actuator.command(primary)
        except Exception as e:
            log.error("haptic send failed: %s", e)
            self._connected = False

    # ── Synchronous helpers (no buttplug calls) ──────────────────────────────

    def _update_safety_state(self, live: dict) -> None:
        sleep_stage = live.get("eeg_sleep_stage", "WAKE") or "WAKE"
        self._safety.set_sleep_stage(sleep_stage)

        session_count = live.get("total_sessions", 0)
        if live.get("display_active"):
            session_count += 1
        if session_count >= 7:
            tier = UnlockTier.TIER_4
        elif session_count >= 5:
            tier = UnlockTier.TIER_3
        elif session_count >= 3:
            tier = UnlockTier.TIER_2
        else:
            tier = UnlockTier.TIER_1
        self._safety.set_unlock_tier(tier)

        haptic_sleep_n1n2 = live.get("haptic_sleep_enabled_n1n2", False)
        self._safety.set_haptic_sleep_n1n2(bool(haptic_sleep_n1n2))

        comfort = live.get("haptic_comfort_ceiling")
        if comfort is not None:
            self._safety.set_comfort_ceiling(float(comfort))

    def _compute_target(self, live: dict, dt: float) -> float:
        if self._safety.emergency_active:
            return 0.0

        # Comfort calibration overrides normal pattern
        ps = self._pattern_state
        if ps.get("type") == "comfort_cal" and not ps.get("done", False):
            if time.time() - ps["step_time"] >= COMFORT_CAL_HOLD_S:
                nxt = ps["current"] + COMFORT_CAL_STEP
                if nxt > COMFORT_CAL_END:
                    ps["done"] = True
                    ps["ceiling"] = ps["current"]
                    from ipc import patch_live as _pl

                    _pl({"haptic_comfort_ceiling": ps["ceiling"]})
                else:
                    ps["current"] = nxt
                    ps["step_time"] = time.time()
            return ps["current"]

        pattern = live.get("haptic_pattern", "continuous") or "continuous"
        base_intensity = float(live.get("haptic_intensity", 0) or 0)
        speed = float(live.get("haptic_pattern_speed", 1.0) or 1.0)

        if pattern == HapticPattern.CONTINUOUS.value:
            return base_intensity

        elif pattern == HapticPattern.PULSE.value:
            phase = (time.time() * speed) % 1.0
            return base_intensity if phase < 0.5 else 0.0

        elif pattern == HapticPattern.WAVE.value:
            phase = (time.time() * speed) % 1.0
            return base_intensity * (0.5 + 0.5 * math.sin(2 * math.pi * phase))

        elif pattern == HapticPattern.RAMP.value:
            if "ramp_start" not in self._pattern_state:
                self._pattern_state["ramp_start"] = time.time()
            elapsed = time.time() - self._pattern_state["ramp_start"]
            progress = min(1.0, elapsed / max(speed, 0.1))
            return base_intensity * progress

        elif pattern == HapticPattern.FRACTIONATION.value:
            return self._fractionation_pattern(live, base_intensity, speed)

        elif pattern == HapticPattern.TMR_CUE.value:
            return base_intensity

        elif pattern == HapticPattern.CONDITIONED_ANCHOR.value:
            return base_intensity

        return base_intensity

    def _compute_vtb_secondary(
        self, base_intensity: float, beat_freq_hz: float
    ) -> float | None:
        """Compute secondary motor intensity for vibrotactile beats.

        The perceived beat frequency comes from oscillating the intensity
        delta between two motors. At any instant, motor 0 is at base and
        motor 1 is offset by a sinusoidal modulation scaled so the peak
        delta produces a noticeable but comfortable intensity difference.

        Returns None for single-motor devices (no VTB possible).
        """
        if self._motor_count < 2:
            return None
        if beat_freq_hz <= 0.0 or base_intensity <= 0.0:
            return None

        phase = (time.time() * beat_freq_hz) % 1.0
        modulation = math.sin(2.0 * math.pi * phase)

        # Delta amplitude: 40% of base intensity for a clearly
        # perceptible beat. The interference pattern — the "third thing"
        # between the two motors — needs significant intensity difference
        # to emerge consciously.
        delta = base_intensity * 0.40 * modulation
        secondary = base_intensity - delta
        return max(0.0, min(100.0, secondary))

    def _fractionation_pattern(
        self,
        live: dict,
        base: float,
        speed: float,
    ) -> float:
        frac_phase = live.get("fractionation_phase", "") or ""
        if frac_phase.startswith("EMERGE") or frac_phase.startswith("HOLD"):
            return 0.0
        elif frac_phase == "INDUCTION":
            return base * 0.3
        elif frac_phase.startswith("DEEP"):
            return base
        elif frac_phase == "REINDUCE":
            t = time.time()
            if "reinduce_start" not in self._pattern_state:
                self._pattern_state["reinduce_start"] = t
            elapsed = t - self._pattern_state["reinduce_start"]
            ramp_duration = 1.0 / max(speed, 0.1)
            progress = min(1.0, elapsed / ramp_duration)
            return base * progress
        return base

    @staticmethod
    def _read_live() -> Optional[dict]:
        try:
            from ipc import read_live

            return read_live()
        except Exception:
            return None
