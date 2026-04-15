"""
slow_wave_enhancer.py — Phase-locked pink noise burst delivery (Bible Ch.7 §7.1 §6)

Delivers 50 ms pink noise bursts at slow-oscillation up-states (delta phase ≈ 0)
to enhance slow-wave activity during N2/N3 sleep.

Science: Ngo et al. (2013, Neuron); Kasties et al. (2025); Jongejan et al. (bioRxiv).
Enhancement mechanism: pink noise at the thalamocortical up-state entrains and
amplifies slow-wave activity, improving memory consolidation by ~25%.

This class decides when to deliver a burst based on:
  - Current sleep stage (N2 or N3 only)
  - Delta phase gate (eeg_delta_in_gate from PhaseTracker)
  - Minimum inter-stimulus interval (800 ms)
  - Maximum burst rate (1.2/s — matching natural SO frequency)
  - Auto-disable if stage drops to Wake for > 10 s

The actual burst is delivered by audio_engine.py reading sleep_burst_cmd_ts
from live_control.json.  This class writes that key via the returned patch dict
which the Conductor applies via _patch_live().
"""

from __future__ import annotations

import time
from typing import Optional
import numpy as np


class SlowWaveEnhancer:
    """Phase-locked pink noise burst scheduler for SWS enhancement.

    Called every Conductor tick during SLEEP_MAINTAIN.
    Reads delta phase gate and sleep stage; returns a _patch_live patch.
    """

    MIN_ISI_S   = 0.80    # minimum inter-stimulus interval (seconds)
    MAX_RATE_HZ = 1.20    # hard cap; equivalent to MIN_ISI

    def __init__(self):
        self._last_stimulus_ts: float  = 0.0
        self._burst_count: int         = 0
        self._enhancement_active: bool = False
        self._swa_baseline: Optional[float] = None
        self._swa_history: list[float] = []
        self._wake_since: Optional[float] = None   # timestamp when WAKE streak started
        self._disabled: bool           = False     # latched True after WAKE > 10 s

    # ── Tick ──────────────────────────────────────────────────────────────────

    def tick(
        self,
        live_state: dict,
        sleep_stage: str,
        timestamp: Optional[float] = None,
    ) -> dict:
        """Call every Conductor tick.  Returns a live_control.json patch dict.

        Delivers a burst command when:
          - Stage is N2 or N3
          - Delta phase gate is open (eeg_delta_in_gate is True)
          - ISI constraint is satisfied

        Args:
            live_state  : current live_control.json snapshot
            sleep_stage : from SleepStageClassifier ("N2", "N3", "WAKE", ...)
            timestamp   : time.time() float; defaults to time.time()

        Returns patch dict for _patch_live().  Keys written:
            sleep_burst_cmd_ts : float  — monotonic timestamp; audio_engine fires
                                          if this is newer than its last burst
            sleep_sw_burst_count: int   — cumulative burst count for session metrics
        """
        now = timestamp if timestamp is not None else time.time()

        if self._disabled:
            return {}

        if sleep_stage not in ("N2", "N3"):
            self._enhancement_active = False
            if sleep_stage == "WAKE":
                if self._wake_since is None:
                    self._wake_since = now
                elif (now - self._wake_since) >= 10.0:
                    # Subject has been fully awake for 10 s — disable for remainder of session
                    self._disabled = True
            else:
                self._wake_since = None
            return {}

        self._wake_since = None
        self._enhancement_active = True

        # Phase gate: only deliver at delta up-state (surface-positive peak ≈ phase 0)
        if not live_state.get("eeg_delta_in_gate", False):
            return {}

        # TMR coordination: yield to TMREngine priority lockout (Bible Ch.7 §7.5 §4.3)
        tmr_lockout = float(live_state.get("tmr_lockout_until", 0) or 0)
        if now < tmr_lockout:
            return {}

        # ISI enforcement
        if (now - self._last_stimulus_ts) < self.MIN_ISI_S:
            return {}

        # Deliver burst
        self._last_stimulus_ts = now
        self._burst_count += 1

        # N3 gets full volume; N2 gets 80% (lighter enhancement for lighter stage)
        vol_mul = 1.0 if sleep_stage == "N3" else 0.80
        burst_vol = int(live_state.get("sleep_sw_enhance_volume", 12) * vol_mul)

        return {
            "sleep_burst_cmd_ts":    now,
            "sleep_burst_volume":    burst_vol,
            "sleep_burst_duration_ms": 50,
            "sleep_sw_burst_count":  self._burst_count,
        }

    # ── SWA tracking ─────────────────────────────────────────────────────────

    def record_delta(self, delta_power: float) -> float:
        """Track slow-wave activity level relative to pre-enhancement baseline.

        Returns the SWA enhancement ratio (0.0 until baseline is warm,
        then (current_mean - baseline) / baseline).
        """
        if self._swa_baseline is None:
            self._swa_baseline = delta_power
            return 0.0

        self._swa_history.append(delta_power)
        if len(self._swa_history) > 150:   # 5 min at 2 s ticks
            self._swa_history.pop(0)

        mean_current = float(np.mean(self._swa_history))
        return (mean_current - self._swa_baseline) / (self._swa_baseline + 1e-9)

    @property
    def enhancement_active(self) -> bool:
        return self._enhancement_active

    @property
    def burst_count(self) -> int:
        return self._burst_count
