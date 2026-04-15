"""
sleep_classifier.py — Real-time sleep stage classifier for Muse 2 (Bible Ch.7 §7.1 §3)

Deterministic threshold-based decision tree.  Runs every tick (2 s) inside
eeg_engine.py on features already computed by Bible Ch.2 §2.8 and the band-power pipeline.

Input features:
  spectral_slope      — already computed by depth_features.py (Bible Ch.2 §2.8)
  delta/theta/alpha   — relative band-power ratios from eeg_engine.py
  sigma_power         — absolute 11–16 Hz power (new)
  spindle_density     — spindles per 30 s from SpindleDetector (new)
  beta_dropout        — bool: beta < 15% of wake baseline (new)
  muscle_artifact_idx — HF power ratio; proxy for EMG (new)

Output:
  stage      : str   — "WAKE" | "N1" | "N2" | "N3" | "REM"
  confidence : float — 0.0–1.0 based on feature agreement
"""

from __future__ import annotations
from typing import Optional


class SleepStageClassifier:
    """Real-time sleep stage classification from 4-channel Muse 2 EEG.

    Operates on the same 2-second tick as eeg_engine.py.  Thresholds default
    to population values from Lanthier et al. (2024) / Lendner et al. (2020);
    per-user calibration overrides are applied from somna_db on first session.

    Hysteresis: three consecutive agreeing epochs required to declare a
    stage transition.  Returns the previous stable stage until consensus forms.
    """

    DEFAULTS: dict = {
        "slope_wake_n1":    -1.8,   # shallower → Wake; steeper → N1+
        "slope_n1_n2":      -2.2,   # N1/N2 boundary
        "slope_n2_n3":      -2.6,   # N2/N3 boundary
        "slope_rem_ceil":   -1.9,   # REM shows near-wake shallow slope
        "delta_n3_floor":    0.40,  # N3 requires delta ratio > 40%
        "spindle_n2_floor":  2.0,   # spindles/30 s confirms N2
        "alpha_wake_floor":  0.15,  # Wake: alpha ratio > 15%
        "beta_dropout_ceil": 0.15,  # Sleep: beta < 15% of baseline
        "rem_theta_floor":   0.25,  # REM: elevated theta without delta surge
    }

    _HYSTERESIS_COUNT = 3           # consecutive matching epochs for transition

    def __init__(self, user_thresholds: Optional[dict] = None):
        self.thresholds: dict = {**self.DEFAULTS, **(user_thresholds or {})}
        self._stage_history: list[str] = []   # last 30 epochs
        self._wake_beta_baseline: Optional[float] = None
        self._confidence: float = 0.0
        self._stable_stage: str = "WAKE"

    # ── Calibration ───────────────────────────────────────────────────────────

    def set_wake_baseline(self, beta_power: float) -> None:
        """Called during calibration to establish the wake beta reference."""
        self._wake_beta_baseline = beta_power

    def update_thresholds(self, new_thresholds: dict) -> None:
        """Merge in per-user thresholds from somna_db calibration."""
        self.thresholds.update(new_thresholds)

    # ── Classification ────────────────────────────────────────────────────────

    def classify(self, features: dict) -> tuple[str, float]:
        """Classify one epoch.  Returns (stage, confidence).

        features dict requires:
          spectral_slope, delta_power_ratio, theta_power_ratio,
          alpha_power_ratio, spindle_density, beta_dropout (bool)
        """
        t = self.thresholds
        slope   = features.get("spectral_slope") or -1.5
        delta   = features.get("delta_power_ratio") or 0.0
        theta   = features.get("theta_power_ratio") or 0.0
        alpha   = features.get("alpha_power_ratio") or 0.0
        spindles = features.get("spindle_density") or 0.0
        beta_drop = bool(features.get("beta_dropout", False))

        votes: dict[str, float] = {}

        # ── Rule 1: spectral slope as primary axis (Lendner et al. 2020) ──────
        if slope > t["slope_wake_n1"]:
            votes["WAKE"] = votes.get("WAKE", 0) + 0.40
        elif slope > t["slope_n1_n2"]:
            votes["N1"] = votes.get("N1", 0) + 0.30
        elif slope > t["slope_n2_n3"]:
            votes["N2"] = votes.get("N2", 0) + 0.40
        else:
            votes["N3"] = votes.get("N3", 0) + 0.40

        # REM: near-wake slope + elevated theta + low delta
        if (slope > t["slope_rem_ceil"]
                and theta > t["rem_theta_floor"]
                and delta < t["delta_n3_floor"]):
            votes["REM"] = votes.get("REM", 0) + 0.30

        # ── Rule 2: alpha persistence — Wake vs N1 ────────────────────────────
        if alpha > t["alpha_wake_floor"]:
            votes["WAKE"] = votes.get("WAKE", 0) + 0.20
        else:
            for stage in ("N1", "N2", "N3"):
                votes[stage] = votes.get(stage, 0) + 0.05

        # ── Rule 3: spindle density confirms N2 (Warby et al. 2014) ──────────
        if spindles >= t["spindle_n2_floor"]:
            votes["N2"] = votes.get("N2", 0) + 0.30

        # ── Rule 4: delta dominance confirms N3 ───────────────────────────────
        if delta > t["delta_n3_floor"]:
            votes["N3"] = votes.get("N3", 0) + 0.30

        # ── Rule 5: beta dropout distinguishes sleep from wake ────────────────
        if beta_drop:
            for stage in ("N1", "N2", "N3", "REM"):
                votes[stage] = votes.get(stage, 0) + 0.10
        else:
            votes["WAKE"] = votes.get("WAKE", 0) + 0.15

        if not votes:
            return self._stable_stage, 0.0

        # Winner-take-all
        raw_stage = max(votes, key=votes.get)
        total = sum(votes.values())
        self._confidence = votes[raw_stage] / total if total > 0 else 0.0

        # Hysteresis: accumulate history, require 3 consecutive matching epochs
        self._stage_history.append(raw_stage)
        if len(self._stage_history) > 30:
            self._stage_history.pop(0)

        recent = (self._stage_history[-self._HYSTERESIS_COUNT:]
                  if len(self._stage_history) >= self._HYSTERESIS_COUNT
                  else self._stage_history)

        if len(set(recent)) == 1:
            # Full consensus → commit transition
            self._stable_stage = recent[0]
            return self._stable_stage, self._confidence

        # Partial consensus → hold previous stable, reduce confidence
        return self._stable_stage, self._confidence * 0.70

    # ── Post-session adaptation ───────────────────────────────────────────────

    @staticmethod
    def update_thresholds_from_session(
        session_metrics: dict,
        current_thresholds: dict,
        alpha: float = 0.20,
    ) -> dict:
        """Exponential moving average threshold update after each sleep session.

        Uses the same 0.8/0.2 EMA rule as Bible Ch.2 §2.6 calibration updates.
        Only adjusts boundaries if outcome data is available and meaningful.
        """
        updated = dict(current_thresholds)

        # Relax N1 threshold if sleep onset latency exceeded 20 min
        sol = session_metrics.get("sleep_onset_latency_s")
        if sol and sol > 1200:
            updated["slope_wake_n1"] = (
                (1 - alpha) * updated["slope_wake_n1"]
                + alpha * (updated["slope_wake_n1"] + 0.10)
            )

        # Widen all slope thresholds if mean confidence was low
        mean_conf = session_metrics.get("mean_sleep_confidence", 1.0)
        if mean_conf < 0.50:
            for key in ("slope_wake_n1", "slope_n1_n2", "slope_n2_n3"):
                spread = -1 if "wake" in key else 1
                updated[key] *= 1.0 - alpha * 0.05 * spread

        return updated
