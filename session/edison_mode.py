"""
Edison Mode — Hypnagogic Creativity Capture (Bible Ch.7 §29)

State-driven N1-interception protocol. The user enters a near-sleep state,
the system detects N1 onset via EEG, holds for a configurable duration,
then wakes the user to capture hypnagogic content. Cycles repeat.

This module is a state machine ticked by the Conductor when session_type == "edison".
It does NOT deliver TTS or interact with the agent directly — it writes state
to live_control.json and the agent reacts to those states.

Usage:
    from session.edison_mode import EdisonModeManager, EdisonState
    mgr = EdisonModeManager(n1_hold_seconds=60, max_cycles=5, seed_topic="fractal geometry")
    updates = mgr.tick(live_state_dict)
    patch_live(updates)
"""

import json
import time
from enum import Enum


class EdisonState(Enum):
    PREPARATION = "PREPARATION"
    SEED_DELIVERY = "SEED_DELIVERY"
    MONITORING = "MONITORING"
    N1_HOLD = "N1_HOLD"
    CAPTURE = "CAPTURE"
    CYCLE_COMPLETE = "CYCLE_COMPLETE"
    SESSION_END = "SESSION_END"


_N1_AT_RATIO_THRESHOLD = 0.80
_N2_SIGMA_GUARD_SECONDS = 5.0
_EEG_STALENESS_SECONDS = 10.0
_MONITORING_READY_GRACE = 10.0


class EdisonModeManager:
    def __init__(
        self,
        n1_hold_seconds: float = 60.0,
        max_cycles: int = 5,
        seed_topic: str = "",
        n2_wake_volume: float = 0.8,
    ):
        self.state = EdisonState.PREPARATION
        self.n1_hold_seconds = n1_hold_seconds
        self.max_cycles = max_cycles
        self.seed_topic = seed_topic
        self.n2_wake_volume = n2_wake_volume

        self.cycle_count: int = 0
        self.n1_entry_ts: float = 0.0
        self.seed_delivered_ts: float = 0.0
        self.preparation_start_ts: float = time.time()
        self.capture_start_ts: float = 0.0
        self.last_eeg_ts: float = 0.0
        self.last_at_ratio: float = 1.0
        self.last_sleep_stage: str = "WAKE"

        self.captures: list = []

    def tick(self, live: dict) -> dict:
        self._update_eeg_cache(live)
        handler = {
            EdisonState.PREPARATION: self._tick_preparation,
            EdisonState.SEED_DELIVERY: self._tick_seed_delivery,
            EdisonState.MONITORING: self._tick_monitoring,
            EdisonState.N1_HOLD: self._tick_n1_hold,
            EdisonState.CAPTURE: self._tick_capture,
            EdisonState.CYCLE_COMPLETE: self._tick_cycle_complete,
        }.get(self.state)
        if handler is None:
            return {}
        updates = handler(live)
        base = self._base_state_dict()
        base.update(updates)
        return base

    def _update_eeg_cache(self, live: dict) -> None:
        ts = live.get("eeg_timestamp", 0.0)
        if ts > self.last_eeg_ts:
            self.last_eeg_ts = ts
        self.last_at_ratio = live.get("eeg_alpha_theta_ratio", 1.0)
        self.last_sleep_stage = live.get("eeg_sleep_stage", "WAKE")

    def _base_state_dict(self) -> dict:
        return {
            "edison_active": True,
            "edison_state": self.state.value,
            "edison_seed_topic": self.seed_topic,
            "edison_cycle_count": self.cycle_count,
            "edison_n1_hold_seconds": self.n1_hold_seconds,
            "edison_n1_entry_timestamp": self.n1_entry_ts if self.n1_entry_ts else None,
        }

    def _tick_preparation(self, live: dict) -> dict:
        ready_signal = live.get("edison_user_ready")
        if ready_signal:
            self.state = EdisonState.SEED_DELIVERY
            return {}
        elapsed = time.time() - self.preparation_start_ts
        if elapsed > 300:
            self.state = EdisonState.SEED_DELIVERY
        return {}

    def _tick_seed_delivery(self, live: dict) -> dict:
        if not self.seed_delivered_ts:
            self.seed_delivered_ts = time.time()
            return {
                "agent_message": {
                    "text": (
                        f"Your creative seed is: **{self.seed_topic}**. "
                        "Hold this lightly in your mind. Don't force it — "
                        "just let it sit there as you drift. I'll wake you "
                        "when the moment comes."
                    ),
                    "ts": time.time(),
                    "needs_response": False,
                    "via": ["tts", "overlay"],
                    "style": {"voice_mode": "tts", "intensity": 0.7},
                    "timeout_s": None,
                },
            }
        if time.time() - self.seed_delivered_ts > _MONITORING_READY_GRACE:
            self.state = EdisonState.MONITORING
        return {}

    def _tick_monitoring(self, live: dict) -> dict:
        if self._eeg_stale():
            return {}

        if self._detect_n1_fast():
            self.n1_entry_ts = time.time()
            self.state = EdisonState.N1_HOLD
            print(
                f"[Edison] N1 detected — entering hold (AT ratio={self.last_at_ratio:.2f})"
            )
        return {}

    def _tick_n1_hold(self, live: dict) -> dict:
        if self._eeg_stale():
            return {}

        elapsed = time.time() - self.n1_entry_ts

        if self.last_sleep_stage in ("N2", "N3"):
            print(f"[Edison] N2+ detected during hold — triggering immediate capture")
            return self._trigger_capture("n2_boundary")

        if elapsed >= self.n1_hold_seconds:
            print(
                f"[Edison] N1 hold timer expired ({elapsed:.1f}s) — triggering capture"
            )
            return self._trigger_capture("timer")

        return {}

    def _tick_capture(self, live: dict) -> dict:
        response = live.get("user_response")
        response_ts = live.get("response_timestamp", 0.0)

        if response and response_ts > self.capture_start_ts:
            capture = {
                "capture_index": self.cycle_count,
                "n1_onset_ts": self.n1_entry_ts,
                "n1_duration_s": time.time() - self.n1_entry_ts,
                "alpha_theta_ratio": self.last_at_ratio,
                "seed_topic": self.seed_topic,
                "user_report": response,
                "eeg_snapshot": {
                    "delta": live.get("eeg_delta", 0),
                    "theta": live.get("eeg_theta", 0),
                    "alpha": live.get("eeg_alpha", 0),
                    "beta": live.get("eeg_beta", 0),
                    "gamma": live.get("eeg_gamma", 0),
                },
                "wake_cue_type": getattr(self, "_last_wake_cue_type", "normal"),
                "cycle_complete_ts": time.time(),
            }
            self.captures.append(capture)
            self.cycle_count += 1
            print(
                f"[Edison] Capture #{self.cycle_count} recorded ({len(response)} chars)"
            )

            if self.cycle_count >= self.max_cycles:
                self.state = EdisonState.SESSION_END
                return {}

            self.state = EdisonState.CYCLE_COMPLETE
            return {}

        timeout = time.time() - self.capture_start_ts
        if timeout > 120:
            print("[Edison] Capture timeout (120s) — no response, ending cycle")
            self.cycle_count += 1
            if self.cycle_count >= self.max_cycles:
                self.state = EdisonState.SESSION_END
                return {}
            self.state = EdisonState.CYCLE_COMPLETE

        return {}

    def _tick_cycle_complete(self, live: dict) -> dict:
        continue_signal = live.get("edison_continue")
        end_signal = live.get("edison_end_session")

        if end_signal:
            self.state = EdisonState.SESSION_END
            return {}

        if continue_signal:
            self.n1_entry_ts = 0.0
            self.seed_delivered_ts = 0.0
            self.capture_start_ts = 0.0
            self.state = EdisonState.SEED_DELIVERY
            return {}

        return {}

    def _trigger_capture(self, wake_cue_type: str) -> dict:
        self._last_wake_cue_type = wake_cue_type
        self.capture_start_ts = time.time()

        cue_text = "What were you just experiencing?"
        if wake_cue_type == "n2_boundary":
            cue_text = "You were deeper than intended. What do you remember?"
        if self.cycle_count == 0:
            cue_text = "Welcome back. What was just happening?"

        self.state = EdisonState.CAPTURE
        return {
            "agent_message": {
                "text": cue_text,
                "ts": time.time(),
                "needs_response": True,
                "via": ["tts", "overlay"],
                "style": {
                    "voice_mode": "tts",
                    "intensity": 0.8 if wake_cue_type == "n2_boundary" else 0.6,
                },
                "timeout_s": 120.0,
            },
        }

    def _detect_n1_fast(self) -> bool:
        if self.last_sleep_stage in ("N1",):
            return True
        if self.last_at_ratio < _N1_AT_RATIO_THRESHOLD:
            return True
        return False

    def _eeg_stale(self) -> bool:
        if not self.last_eeg_ts:
            return True
        return (time.time() - self.last_eeg_ts) > _EEG_STALENESS_SECONDS

    def state_dict(self) -> dict:
        return self._base_state_dict()

    def finalize(self) -> list:
        return list(self.captures)
