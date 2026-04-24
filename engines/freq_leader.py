"""
freq_leader.py — Adaptive Frequency Leading (Meet-and-Lead)
============================================================
Closed-loop binaural beat descent via ASSR verification. (Somna Bible Ch.6 §6.2)

The leader runs in a background daemon thread, polling every _POLL_INTERVAL
seconds. It only becomes active when ``freq_lead_enabled: true`` is written
to live_control.json by the agent. The agent calls start() at agent init and
stop() on shutdown; the leader itself is passive until enabled.

Key reconciliation (Somna key names vs. Bible Ch.6 §6.2 names):
    beat_frequency        ← "beat_freq" in Doc
    eeg_iaf_hz            ← "eeg_iaf" in Doc
    eeg_entrainment_strength ← "eeg_assr_confidence" in Doc
    eeg_sqi_composite     ← "eeg_sqi" in Doc
    freq_lead_enabled     ← new key; agent writes to activate

IPC: all writes via patch_live() (read-modify-write). Never overwrite.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from ipc import patch_live, read_live

_POLL_INTERVAL = 10.0  # seconds between update cycles


# ── IPC ───────────────────────────────────────────────────────────────────────
def _read_live() -> dict:
    try:
        return read_live()
    except Exception:
        return {}


# ── State machine ─────────────────────────────────────────────────────────────


class LeadPhase(Enum):
    INACTIVE = "inactive"
    MEET = "meet"
    LEAD = "lead"
    HOLD = "hold"
    SUSTAIN = "sustain"
    FAILED = "failed"


@dataclass
class LeadState:
    current_freq: float = 10.0
    target_freq: float = 4.0
    start_freq: float = 10.0
    phase: LeadPhase = LeadPhase.INACTIVE
    step_size: float = 0.10
    step_interval: float = 30.0
    lock_threshold: float = 0.60
    hold_threshold: float = 0.40
    relock_needed: int = 2
    max_hold: float = 120.0
    # Private timing/counting
    _last_step_time: float = field(default=0.0, repr=False)
    _hold_start: float = field(default=0.0, repr=False)
    _relock_count: int = field(default=0, repr=False)
    steps_completed: int = 0
    holds_total: int = 0
    # Fast-follower detection
    _fast_steps: int = field(default=0, repr=False)
    _fast_threshold: int = 3


# ── AdaptiveFrequencyLeader ───────────────────────────────────────────────────


class AdaptiveFrequencyLeader:
    """Closed-loop frequency descent using ASSR verification.

    Usage:
        leader = AdaptiveFrequencyLeader(target_freq=4.0)
        leader.start()
        # ... later ...
        leader.stop()

    To activate from the agent:
        patch_live({"freq_lead_enabled": True, "freq_lead_target_hz": 4.0})
    """

    def __init__(
        self,
        target_freq: float = 4.0,
        step_size: float = 0.10,
        step_interval: float = 30.0,
        lock_threshold: float = 0.60,
        hold_threshold: float = 0.40,
        relock_needed: int = 2,
        max_hold: float = 120.0,
    ):
        self._default_target = target_freq
        self._default_step_size = step_size
        self._default_step_iv = step_interval
        self._default_lock = lock_threshold
        self._default_hold = hold_threshold
        self._default_relock = relock_needed
        self._default_max_hold = max_hold

        self.state = LeadState(phase=LeadPhase.INACTIVE)
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._narrated_phases: set[str] = set()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="FreqLeader"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self.state.phase not in (LeadPhase.INACTIVE, LeadPhase.FAILED):
            patch_live(
                {
                    "freq_lead_phase": "inactive",
                    "freq_lead_enabled": False,
                }
            )
        self.state.phase = LeadPhase.INACTIVE

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                live = _read_live()

                enabled = live.get("freq_lead_enabled", False)
                if not enabled:
                    if self.state.phase != LeadPhase.INACTIVE:
                        self._deactivate()
                    self._stop_evt.wait(timeout=_POLL_INTERVAL)
                    continue

                # Activation / re-configuration
                if self.state.phase == LeadPhase.INACTIVE:
                    self._activate(live)
                else:
                    # Allow agent to update target mid-session
                    new_target = live.get("freq_lead_target_hz")
                    if (
                        new_target is not None
                        and abs(new_target - self.state.target_freq) > 0.05
                    ):
                        self.state.target_freq = round(float(new_target), 2)
                        print(
                            f"[FreqLeader] Target updated to {self.state.target_freq} Hz"
                        )

                # Read gate metrics
                sqi = float(live.get("eeg_sqi_composite", 1.0))
                assr = float(live.get("eeg_entrainment_strength", 0.0))

                # Alpha-overlap correction (Bible Ch.6 §6.2 §9.3)
                if live.get("eeg_entrainment_confidence") == "alpha_overlap":
                    assr *= 0.7

                # Conductor passthrough: don't write beat_frequency — the
                # external agent is driving parameters directly.  Still compute
                # and publish freq_lead_current as a recommendation.
                hints = live.get("agent_conductor_hints") or {}
                if hints.get("passthrough"):
                    if self.state.phase != LeadPhase.INACTIVE:
                        patch_live(
                            {
                                "freq_lead_phase": self.state.phase.value,
                                "freq_lead_current": round(self.state.current_freq, 2),
                                "freq_lead_steps": self.state.steps_completed,
                                "freq_lead_holds": self.state.holds_completed,
                            }
                        )
                    self._stop_evt.wait(timeout=_POLL_INTERVAL)
                    continue

                # SQI gate
                if sqi < 0.5:
                    self._stop_evt.wait(timeout=_POLL_INTERVAL)
                    continue

                # Run phase handler
                self._update(assr, time.time())

            except Exception as e:
                print(f"[FreqLeader] Error: {e}")

            self._stop_evt.wait(timeout=_POLL_INTERVAL)

    # ── Activation ────────────────────────────────────────────────────────────

    def _activate(self, live: dict) -> None:
        # Treat stale eeg_iaf_hz as the authoritative starting frequency.
        # The conductor also reads it before falling back to 10.0 (INDUCTION
        # transition), so both stay in sync automatically.
        current_beat = float(live.get("beat_frequency") or 10.0)
        iaf = float(live.get("eeg_iaf_hz") or current_beat)
        tgt = float(live.get("freq_lead_target_hz") or iaf)

        # Use the conductor's explicit mode to determine the starting phase so
        # we don't have to infer intent from the iaf/tgt relationship.
        mode = (live.get("freq_lead_mode") or "meet").lower()
        if mode == "sustain":
            initial_phase = LeadPhase.SUSTAIN
        else:
            # "meet" and "lead" both start at MEET — active descent requires
            # ASSR confirmation first, regardless of the conductor's mode hint.
            initial_phase = LeadPhase.MEET

        self.state = LeadState(
            current_freq=iaf,
            target_freq=tgt,
            start_freq=iaf,
            phase=initial_phase,
            step_size=self._default_step_size,
            step_interval=self._default_step_iv,
            lock_threshold=self._default_lock,
            hold_threshold=self._default_hold,
            relock_needed=self._default_relock,
            max_hold=self._default_max_hold,
        )
        self._narrated_phases.clear()
        # Do NOT write beat_frequency here.  The conductor already set it to
        # the correct value in its phase transition; overwriting it on
        # activation would undo that and trigger LLM interference detection.
        patch_live(
            {
                "freq_lead_phase": initial_phase.value,
                "freq_lead_target": tgt,
                "freq_lead_current": round(iaf, 2),
                "freq_lead_steps": 0,
                "freq_lead_holds": 0,
            }
        )
        print(
            f"[FreqLeader] Activated — start={iaf:.2f} Hz, target={tgt:.2f} Hz  phase={initial_phase.value}"
        )

    def _deactivate(self) -> None:
        live = _read_live()
        # Restore to EEG IAF if available; otherwise keep the current
        # beat_frequency so deactivation doesn't snap to an unrelated value.
        iaf = float(live.get("eeg_iaf_hz") or live.get("beat_frequency") or 10.0)
        patch_live(
            {
                "beat_frequency": round(iaf, 2),
                "freq_lead_phase": "inactive",
                "freq_lead_enabled": False,
            }
        )
        self.state.phase = LeadPhase.INACTIVE
        print("[FreqLeader] Deactivated — beat_frequency preserved at IAF")

    # ── Phase handlers ────────────────────────────────────────────────────────

    def _update(self, assr: float, now: float) -> None:
        if self.state.phase == LeadPhase.MEET:
            self._handle_meet(assr, now)
        elif self.state.phase == LeadPhase.LEAD:
            self._handle_lead(assr, now)
        elif self.state.phase == LeadPhase.HOLD:
            self._handle_hold(assr, now)
        elif self.state.phase == LeadPhase.SUSTAIN:
            self._handle_sustain(assr, now)

        patch_live(
            {
                "freq_lead_phase": self.state.phase.value,
                "freq_lead_current": round(self.state.current_freq, 2),
                "freq_lead_steps": self.state.steps_completed,
                "freq_lead_holds": self.state.holds_total,
            }
        )

    def _handle_meet(self, assr: float, now: float) -> None:
        if assr >= self.state.lock_threshold:
            self.state.phase = LeadPhase.LEAD
            self.state._last_step_time = now
            self._narrate("meet_locked", "There you are. Beginning the descent.")

    def _handle_lead(self, assr: float, now: float) -> None:
        # Target reached?
        if self.state.current_freq <= self.state.target_freq:
            self.state.phase = LeadPhase.SUSTAIN
            self._narrate("target_reached", "You've arrived. Staying here with you.")
            return

        # Entrainment lost?
        if assr < self.state.hold_threshold:
            self.state.phase = LeadPhase.HOLD
            self.state._hold_start = now
            self.state._relock_count = 0
            self.state._fast_steps = 0
            self.state.holds_total += 1
            self._narrate(
                "first_hold", "Pausing here — your rhythm needs a moment to settle."
            )
            return

        # Time for next step?
        iv = self.state.step_interval
        if now - self.state._last_step_time >= iv:
            if assr >= self.state.lock_threshold:
                old_freq = self.state.current_freq
                self.state.current_freq = round(
                    max(
                        self.state.current_freq - self.state.step_size,
                        self.state.target_freq,
                    ),
                    2,
                )
                self.state._last_step_time = now
                self.state.steps_completed += 1
                self.state._fast_steps += 1
                patch_live({"beat_frequency": self.state.current_freq})

                # Alpha-theta crossing narration (~7.5–8 Hz)
                if old_freq > 8.0 >= self.state.current_freq:
                    self._narrate(
                        "alpha_theta_crossing",
                        "Passing through the drowsy threshold. Let your body go heavy.",
                        force=True,
                    )

                # Fast-follower: halve step interval after 3 holds-free steps
                if (
                    self.state._fast_steps >= self.state._fast_threshold
                    and self.state.holds_total == 0
                    and self.state.step_interval > 15.0
                ):
                    self.state.step_interval = max(15.0, self.state.step_interval / 2)
                    print(
                        f"[FreqLeader] Fast-follower: step_interval → "
                        f"{self.state.step_interval:.0f}s"
                    )

    def _handle_hold(self, assr: float, now: float) -> None:
        hold_dur = now - self.state._hold_start

        # Timeout: step back slightly
        if hold_dur > self.state.max_hold:
            self.state.current_freq = round(
                min(
                    self.state.current_freq + self.state.step_size,
                    self.state.start_freq,
                ),
                2,
            )
            patch_live({"beat_frequency": self.state.current_freq})
            self.state._hold_start = now
            return

        if assr >= self.state.lock_threshold:
            self.state._relock_count += 1
            if self.state._relock_count >= self.state.relock_needed:
                self.state.phase = LeadPhase.LEAD
                self.state._last_step_time = now
                self._narrate("re_entrained", "There you go. Continuing down.")
        else:
            self.state._relock_count = 0

    def _handle_sustain(self, assr: float, now: float) -> None:
        if assr < self.state.hold_threshold:
            # Micro-step back and re-descend
            self.state.current_freq = round(
                self.state.current_freq + self.state.step_size, 2
            )
            self.state.phase = LeadPhase.LEAD
            self.state._last_step_time = now
            patch_live({"beat_frequency": self.state.current_freq})
            self._narrate(
                "sustain_dropout", "Stepping back just a touch. No rush.", force=True
            )

    # ── Narration helpers ─────────────────────────────────────────────────────

    def _narrate(self, key: str, text: str, force: bool = False) -> None:
        """Write one agent_message for a phase transition (once per key unless forced)."""
        if not force and key in self._narrated_phases:
            return
        cur = _read_live().get("agent_message") or {}
        if isinstance(cur, dict) and cur.get("needs_response"):
            return
        self._narrated_phases.add(key)
        patch_live(
            {
                "agent_message": {
                    "text": text,
                    "ts": time.time(),
                    "needs_response": False,
                    "via": ["overlay", "console", "tts"],
                    "style": {
                        "voice_mode": "tts",
                        "intensity": "soft",
                        "zoom_speed": "slow",
                        "needs_response": False,
                    },
                    "timeout_s": 12.0,
                }
            }
        )
        print(f"[FreqLeader] Narrate: {text}")

    # ── Public state accessors (for scoring) ──────────────────────────────────

    def get_lead_data(self) -> dict:
        """Return a freq_lead_data dict for SessionScorer."""
        return {
            "start_freq": self.state.start_freq,
            "end_freq": self.state.current_freq,
            "holds_total": self.state.holds_total,
            "steps_completed": self.state.steps_completed,
            "phase": self.state.phase.value,
        }
