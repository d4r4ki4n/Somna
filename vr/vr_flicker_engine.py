"""
vr_flicker_engine.py — Dichoptic Flicker Engine (Bible Ch.8 §8.1 §4, Bible Ch.8 §8.2 §4)
=======================================================================
Generates per-eye luminance values for the VR renderer.  Supports three
independent operational modes:

  PHOTIC_BILATERAL  — both eyes receive the same frequency (Bible Ch.8 §8.4)
  DICHOPTIC_RIVALRY — each eye receives an independent rivalry tag frequency;
                      phase offsets are fixed to avoid accidental sync (Bible Ch.8 §8.2)
  DICHOPTIC_SSVEP   — each eye receives its own independent SSVEP tag frequency
                      for intermodulation measurement (Bible Ch.8 §8.1)

All frequency and depth changes route through smooth_transition() for
ramp-in over a user-specified duration.  Hard-cutting frequencies mid-stream
would be perceptually jarring and safety-suboptimal.

Luminance range: [background, background + depth * background]  where
  depth = modulation_depth (0–1)
  background = 0.5 (mid-grey Ganzfeld) by default

At depth=0 the output is a constant grey — no flicker.
At depth=1 the output swings from 0.0 to 1.0 (full contrast), which is
above the safety ceiling in the 10–25 Hz danger zone.  See vr_safety.py.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from vr.vr_safety import SafetyEnforcer, enforce_depth, enforce_max_freq


class FlickerMode(Enum):
    PHOTIC_BILATERAL = "photic_bilateral"
    DICHOPTIC_RIVALRY = "dichoptic_rivalry"
    DICHOPTIC_SSVEP   = "dichoptic_ssvep"
    GANZFELD          = "ganzfeld"   # no flicker — uniform grey


@dataclass
class EyeState:
    freq:      float = 0.0
    depth:     float = 0.0
    phase_rad: float = 0.0
    waveform:  str   = "sine"        # "sine" | "square" | "sawtooth"
    background: float = 0.5

    # Smooth transition state
    _target_freq:  Optional[float] = field(default=None, repr=False)
    _target_depth: Optional[float] = field(default=None, repr=False)
    _trans_start:  Optional[float] = field(default=None, repr=False)
    _trans_dur:    float = 0.0


class DichopticFlickerEngine:
    """Thread-safe per-eye luminance generator.

    Indices: 0 = left eye,  1 = right eye.

    Rivalry tag separation MUST be >= 3 Hz.  This is enforced in
    set_rivalry_pair(); a ValueError is raised if violated.
    """

    RIVALRY_MIN_SEPARATION_HZ = 3.0

    def __init__(
        self,
        mode: FlickerMode = FlickerMode.GANZFELD,
        background: float = 0.5,
        safety: Optional[SafetyEnforcer] = None,
    ):
        self.mode = mode
        self.safety = safety or SafetyEnforcer()
        self._eyes = [
            EyeState(background=background, phase_rad=0.0),
            EyeState(background=background, phase_rad=math.pi),  # 180° right-eye offset
        ]

    # ── Primary interface ─────────────────────────────────────────────────────

    def get_luminance(self, eye_index: int, timestamp: float) -> float:
        """Compute instantaneous luminance for eye_index at timestamp (seconds).

        Caller uses this once per render frame per eye.
        """
        st = self._eyes[eye_index]
        self._apply_transition(st, timestamp)

        if self.mode == FlickerMode.GANZFELD or st.freq <= 0.0 or st.depth <= 0.0:
            return st.background

        depth  = self.safety.safe_depth(st.freq, st.waveform, st.depth)
        phase  = 2.0 * math.pi * st.freq * timestamp + st.phase_rad
        carrier = self._waveform_sample(phase, st.waveform)

        # Scale to [background - depth/2, background + depth/2]
        return st.background + depth * 0.5 * carrier

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_mode(self, mode: FlickerMode) -> None:
        self.mode = mode

    def set_photic_bilateral(self, freq: float, depth: float, waveform: str = "sine") -> None:
        """Configure both eyes to flicker at the same frequency (Bible Ch.8 §8.4)."""
        freq  = self.safety.safe_freq(waveform, freq)
        depth = self.safety.safe_depth(freq, waveform, depth)
        for st in self._eyes:
            st.freq     = freq
            st.depth    = depth
            st.waveform = waveform

    def set_rivalry_pair(
        self,
        left_hz: float,
        right_hz: float,
        depth: float = 0.20,
        waveform: str = "square",
    ) -> None:
        """Configure independent rivalry tag frequencies for each eye (Bible Ch.8 §8.2).

        Enforces minimum 3 Hz separation between left and right tags.
        """
        if abs(left_hz - right_hz) < self.RIVALRY_MIN_SEPARATION_HZ:
            raise ValueError(
                f"Rivalry tag separation {abs(left_hz - right_hz):.2f} Hz "
                f"< {self.RIVALRY_MIN_SEPARATION_HZ} Hz minimum.  "
                f"Suggest {left_hz:.1f}/{left_hz + 3.5:.1f} Hz."
            )
        for eye_idx, hz in enumerate((left_hz, right_hz)):
            hz    = self.safety.safe_freq(waveform, hz)
            d     = self.safety.safe_depth(hz, waveform, depth)
            st    = self._eyes[eye_idx]
            st.freq     = hz
            st.depth    = d
            st.waveform = waveform

    def set_ssvep_pair(
        self,
        left_hz: float,
        right_hz: float,
        depth: float = 0.25,
        waveform: str = "sine",
    ) -> None:
        """Configure independent per-eye SSVEP tag frequencies (Bible Ch.8 §8.1)."""
        for eye_idx, hz in enumerate((left_hz, right_hz)):
            hz = self.safety.safe_freq(waveform, hz)
            d  = self.safety.safe_depth(hz, waveform, depth)
            st = self._eyes[eye_idx]
            st.freq     = hz
            st.depth    = d
            st.waveform = waveform

    def set_ganzfeld(self, background: float = 0.5) -> None:
        """Disable all flicker — render uniform Ganzfeld grey (Bible Ch.8 §8.3)."""
        self.mode = FlickerMode.GANZFELD
        for st in self._eyes:
            st.freq       = 0.0
            st.depth      = 0.0
            st.background = background

    # ── Smooth transitions ─────────────────────────────────────────────────────

    def smooth_transition(
        self,
        eye_index: int,
        target_freq: float,
        target_depth: float,
        duration_s: float,
        timestamp: float,
    ) -> None:
        """Initiate a smooth parameter transition for one eye.

        Both freq and depth ramp simultaneously over duration_s seconds.
        """
        st = self._eyes[eye_index]
        st._target_freq  = target_freq
        st._target_depth = self.safety.safe_depth(target_freq, st.waveform, target_depth)
        st._trans_start  = timestamp
        st._trans_dur    = max(0.1, duration_s)

    def smooth_transition_both(
        self,
        target_freq: float,
        target_depth: float,
        duration_s: float,
        timestamp: float,
    ) -> None:
        """Initiate simultaneous smooth transition on both eyes."""
        for i in range(2):
            self.smooth_transition(i, target_freq, target_depth, duration_s, timestamp)

    def fade_out(self, duration_s: float, timestamp: float) -> None:
        """Ramp depth → 0 on both eyes over duration_s seconds."""
        for st in self._eyes:
            st._target_depth = 0.0
            st._target_freq  = st.freq
            st._trans_start  = timestamp
            st._trans_dur    = max(0.1, duration_s)

    # ── State query ────────────────────────────────────────────────────────────

    def current_freqs(self) -> tuple[float, float]:
        """Current (left_hz, right_hz) regardless of transition state."""
        return (self._eyes[0].freq, self._eyes[1].freq)

    def current_depths(self) -> tuple[float, float]:
        return (self._eyes[0].depth, self._eyes[1].depth)

    def is_transitioning(self) -> bool:
        return any(st._target_freq is not None for st in self._eyes)

    # ── Private ────────────────────────────────────────────────────────────────

    @staticmethod
    def _waveform_sample(phase: float, waveform: str) -> float:
        """Return a sample in [-1, +1] for the given waveform type."""
        p = phase % (2.0 * math.pi)
        if waveform == "square":
            return 1.0 if p < math.pi else -1.0
        if waveform == "sawtooth":
            return (p / math.pi) - 1.0
        return math.sin(phase)   # default: sine

    def _apply_transition(self, st: EyeState, now: float) -> None:
        """Interpolate towards target freq/depth if a transition is active."""
        if st._target_freq is None or st._trans_start is None:
            return
        elapsed = now - st._trans_start
        t = min(elapsed / max(st._trans_dur, 1e-9), 1.0)
        t_smooth = t * t * (3.0 - 2.0 * t)   # smoothstep

        st.freq  = st.freq  + t_smooth * (st._target_freq  - st.freq)
        st.depth = st.depth + t_smooth * (st._target_depth - st.depth)

        if t >= 1.0:
            st.freq  = st._target_freq
            st.depth = st._target_depth
            st._target_freq  = None
            st._target_depth = None
            st._trans_start  = None
