"""
eeg/gamma_verification_gate.py — GENUS entrainment verification (Bible Ch.4 Addendum A / knowledge/genus_protocol.md)
======================================================================================================
Reads eeg_genus_ratio from live_control.json every tick and classifies
entrainment quality as strong / moderate / weak / absent.

Writes:
  genus_entrainment_verified  bool   True when ratio >= moderate threshold
  genus_entrainment_level     str    "strong" | "moderate" | "weak" | "absent"
  genus_entrainment_ratio     float  current EMA-smoothed ratio

The gate distinguishes genuine neural entrainment from visual-stimulus artifact
by requiring the ratio to be sustained above threshold for a configurable window.
Artifact disappears instantly at stimulation offset; genuine entrainment persists.
"""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from ipc import patch_live

_LIVE = Path(__file__).parent.parent / "live_control.json"

# Entrainment ratio thresholds (vs. pre-GENUS 60-s baseline)
_STRONG_THRESHOLD   = 2.0   # >2.0 = strong
_MODERATE_THRESHOLD = 1.5   # 1.5–2.0 = moderate
_WEAK_THRESHOLD     = 1.2   # 1.2–1.5 = weak

# Sustain window: ratio must stay above threshold for this many ticks
_SUSTAIN_TICKS = 5
class GammaVerificationGate:
    """
    Real-time GENUS entrainment verifier.

    Call update() once per EEG tick (every ~2 s) while genus_active is True.
    Reads eeg_genus_ratio from live_control, applies EMA smoothing and sustain
    window, classifies level, and writes back to live_control.
    """

    _EMA_ALPHA = 0.25   # smoothing weight for incoming ratio

    def __init__(self) -> None:
        self._ema_ratio:         float = 1.0
        self._above_moderate_ticks: int = 0
        self._verified:          bool  = False
        self._level:             str   = "absent"
        self._last_update:       float = 0.0
        self._ratio_history:     deque[float] = deque(maxlen=30)

    def update(self, live: dict | None = None) -> dict:
        """
        Process latest live_control snapshot and return patch dict.

        Parameters
        ----------
        live : optional pre-read live_control dict (avoids double file read)
        """
        if live is None:
            try:
                live = json.loads(_LIVE.read_text(encoding="utf-8"))
            except Exception:
                live = {}

        if not bool(live.get("genus_active", False)):
            # Reset when GENUS is off
            self._verified = False
            self._level    = "absent"
            self._ema_ratio = 1.0
            self._above_moderate_ticks = 0
            return {}

        raw_ratio = float(live.get("eeg_genus_ratio", 1.0) or 1.0)
        self._ema_ratio = (
            self._EMA_ALPHA * raw_ratio + (1.0 - self._EMA_ALPHA) * self._ema_ratio
        )
        self._ratio_history.append(self._ema_ratio)

        # Classify level
        if self._ema_ratio >= _STRONG_THRESHOLD:
            self._level = "strong"
        elif self._ema_ratio >= _MODERATE_THRESHOLD:
            self._level = "moderate"
        elif self._ema_ratio >= _WEAK_THRESHOLD:
            self._level = "weak"
        else:
            self._level = "absent"

        # Sustain verification: must be >= moderate for N consecutive ticks
        if self._ema_ratio >= _MODERATE_THRESHOLD:
            self._above_moderate_ticks += 1
        else:
            self._above_moderate_ticks = 0

        self._verified = (self._above_moderate_ticks >= _SUSTAIN_TICKS)
        self._last_update = time.time()

        patch = {
            "genus_entrainment_verified": self._verified,
            "genus_entrainment_level":    self._level,
            "genus_entrainment_ratio":    round(self._ema_ratio, 3),
        }
        patch_live(patch)
        return patch

    @property
    def verified(self) -> bool:
        return self._verified

    @property
    def level(self) -> str:
        return self._level

    @property
    def ratio(self) -> float:
        return round(self._ema_ratio, 3)
