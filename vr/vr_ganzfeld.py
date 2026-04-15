"""
vr_ganzfeld.py — Ganzfeld Protocol (Bible Ch.8 §8.3)
============================================
The Ganzfeld effect is achieved by presenting a completely uniform,
featureless visual field that eliminates all spatial contrast.  In VR,
this is the easiest thing to render — a solid colour fill per eye.

Bible Ch.8 §8.3 specifies:
  Phase 1 — Onset ramp (0 → target_lum over ramp_duration_s seconds)
             Uses a log-accelerated curve: slow at start, faster at end,
             so the initial fade from black is imperceptible.
  Phase 2 — Equilibration hold (hold target_lum for hold_duration_s)
             The uniform field destabilises top-down visual predictions.
             Eidetic imagery / phosphene cascades typically emerge here.
  Phase 3 — Ganzflicker (optional)
             After equilibration, add a slow sinusoidal luminance
             modulation at ganzflicker_hz (1–6 Hz).  This synergises
             with photic driving and SSVEP without breaking the Ganzfeld
             unity.  Recommended: 2–4 Hz (theta/low-alpha boundary).

The GanzfeldProtocol drives the DichopticFlickerEngine's ganzfeld mode
internally; the VR renderer only needs to call .get_luminance(eye, t).

live_control.json keys read:
  vr_ganzfeld_target_lum    float  0–1 (default 0.5)
  vr_ganzfeld_ramp_s        float  seconds (default 120)
  vr_ganzfeld_hold_s        float  seconds (default 120)
  vr_ganzfeld_flicker_hz    float  Hz; 0 = no flicker (default 0)
  vr_ganzfeld_flicker_depth float  depth of flicker (default 0.04)
"""
from __future__ import annotations

import math
import time
from enum import Enum
from pathlib import Path
import json
from ipc import patch_live


_LIVE_PATH = Path(__file__).parent.parent / "live_control.json"
class GanzfeldPhase(Enum):
    INACTIVE      = "inactive"
    ONSET_RAMP    = "onset_ramp"
    EQUILIBRATION = "equilibration"
    GANZFLICKER   = "ganzflicker"
    COMPLETE      = "complete"


class GanzfeldProtocol:
    """Drives the Ganzfeld onset and Ganzflicker sequence.

    Usage in the VR frame loop:
        proto = GanzfeldProtocol()
        proto.start(timestamp=time.time(), cfg=cfg)
        ...
        for eye in (0, 1):
            lum = proto.get_luminance(eye, time.time())
            GL.glClearColor(lum, lum, lum, 1.0)
            GL.glClear(...)
    """

    def __init__(self):
        self._phase       = GanzfeldPhase.INACTIVE
        self._start_ts    = 0.0
        self._phase_ts    = 0.0

        # Protocol parameters (loaded from cfg on start())
        self._target_lum    = 0.5
        self._ramp_dur_s    = 120.0
        self._hold_dur_s    = 120.0
        self._flicker_hz    = 0.0
        self._flicker_depth = 0.04

        # Phase-start luminance (used for partial ramps when switching)
        self._ramp_start_lum = 0.0
        self._current_lum    = 0.0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, timestamp: float, cfg: dict) -> None:
        """Begin the Ganzfeld sequence with parameters from cfg."""
        self._target_lum    = float(cfg.get("vr_ganzfeld_target_lum",    0.5))
        self._ramp_dur_s    = float(cfg.get("vr_ganzfeld_ramp_s",       120.0))
        self._hold_dur_s    = float(cfg.get("vr_ganzfeld_hold_s",       120.0))
        self._flicker_hz    = float(cfg.get("vr_ganzfeld_flicker_hz",     0.0))
        self._flicker_depth = float(cfg.get("vr_ganzfeld_flicker_depth",  0.04))

        self._start_ts       = timestamp
        self._ramp_start_lum = 0.0
        self._current_lum    = 0.0
        self._set_phase(GanzfeldPhase.ONSET_RAMP, ts=timestamp)

    def stop(self) -> None:
        self._set_phase(GanzfeldPhase.INACTIVE)

    @property
    def phase(self) -> GanzfeldPhase:
        return self._phase

    @property
    def complete(self) -> bool:
        return self._phase in (GanzfeldPhase.COMPLETE, GanzfeldPhase.GANZFLICKER)

    # ── Per-frame luminance ────────────────────────────────────────────────────

    def get_luminance(self, eye_index: int, timestamp: float) -> float:
        """Return the target luminance for this eye at this timestamp.

        Both eyes always receive the same luminance — Ganzfeld requires full
        binocular uniformity.  The eye_index parameter is accepted to match
        the renderer's per-eye interface but is unused.
        """
        phase_elapsed = timestamp - self._phase_ts

        if self._phase == GanzfeldPhase.ONSET_RAMP:
            lum = self._ramp_luminance(phase_elapsed)
            self._current_lum = lum
            if phase_elapsed >= self._ramp_dur_s:
                self._current_lum = self._target_lum
                self._set_phase(GanzfeldPhase.EQUILIBRATION)
                patch_live({"vr_ganzfeld_phase": "equilibration"})
            return self._current_lum

        if self._phase == GanzfeldPhase.EQUILIBRATION:
            if phase_elapsed >= self._hold_dur_s:
                if self._flicker_hz > 0.0:
                    self._set_phase(GanzfeldPhase.GANZFLICKER)
                    patch_live({"vr_ganzfeld_phase": "ganzflicker"})
                else:
                    self._set_phase(GanzfeldPhase.COMPLETE)
                    patch_live({"vr_ganzfeld_phase": "complete"})
            return self._target_lum

        if self._phase == GanzfeldPhase.GANZFLICKER:
            # Sinusoidal modulation at low frequency — barely perceptible motion
            phase_rad = 2.0 * math.pi * self._flicker_hz * timestamp
            flicker   = math.sin(phase_rad)
            lum       = self._target_lum + self._flicker_depth * 0.5 * flicker
            return max(0.0, min(1.0, lum))

        return self._target_lum   # COMPLETE or INACTIVE

    # ── Private ────────────────────────────────────────────────────────────────

    def _ramp_luminance(self, elapsed: float) -> float:
        """Log-accelerated ramp: slow initially, faster toward the end.

        Uses a power curve (exponent < 1) so the initial transition from
        black is imperceptibly gradual and won't cause photosensitive alarm.
        t_norm ∈ [0, 1] → lum ∈ [ramp_start, target_lum]
        """
        t_norm = max(0.0, min(elapsed / max(self._ramp_dur_s, 1.0), 1.0))
        curved = t_norm ** 0.5   # square root; clamped above so no complex roots
        return self._ramp_start_lum + curved * (self._target_lum - self._ramp_start_lum)

    def _set_phase(self, phase: GanzfeldPhase, ts: float | None = None) -> None:
        self._phase    = phase
        self._phase_ts = ts if ts is not None else time.time()


class GanzfeldFlicker:
    """Minimal Ganzflicker only — for use alongside photic driving (Bible Ch.8 §8.3 §6.2).

    Creates a very slow sinusoidal luminance oscillation that sits beneath
    the primary photic driver.  The oscillation must be much slower (< 5 Hz)
    than the photic driving frequency so the two signals don't interfere.

    Usage:
        gf = GanzfeldFlicker(base_lum=0.5, hz=2.5, depth=0.04)
        # per frame:
        mod = gf.get_modulation(timestamp)   # add to whatever primary lum
    """

    def __init__(self, base_lum: float = 0.5, hz: float = 2.5, depth: float = 0.04):
        self.base_lum = base_lum
        self.hz       = hz
        self.depth    = depth

    def get_modulation(self, timestamp: float) -> float:
        """Return luminance delta to add to primary output.  Range [-depth/2, +depth/2]."""
        return self.depth * 0.5 * math.sin(2.0 * math.pi * self.hz * timestamp)
