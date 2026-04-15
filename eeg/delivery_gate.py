"""
delivery_gate.py — Phase-cascade AND gate for subliminal stimulus delivery (Bible Ch.4 §4.6 §5.1, Bible Ch.2 §2.9 §3)

Gate logic (quad-gate, Bible Ch.2 §2.9):
  fire = respiratory_hot AND alpha_at_trough AND cardiac_diastole AND sqi_ok AND NOT motion_contaminated

Progressive relaxation hierarchy (gate_relaxation_level in return dict):
  Level 0: Full quad-gate (respiratory + alpha + cardiac + SQI, no motion)
  Level 1: Cardiac dropped after phase-specific timeout (respiratory + alpha + SQI)
  Level 2: Alpha dropped after 25 s stall (respiratory + cardiac + SQI)
  Level 3: Emergency respiratory-only after 40 s stall
  resp_only: SQI below threshold — respiratory gate only, no alpha/cardiac

The gate never blocks delivery entirely. The 40 s emergency fallback ensures
affirmations always fire — the system is always at least as good as the current
fixed duty cycle. This is non-negotiable (Bible Ch.4 §4.6 §13).
"""

import time

# Stall thresholds for progressive gate relaxation
_ALPHA_GATE_TIMEOUT_S     = 25.0   # drop alpha after this many seconds stalled
_EMERGENCY_TIMEOUT_S      = 40.0   # force respiratory-only delivery after this

# Phase-specific cardiac gate timeouts (Bible Ch.2 §2.9 §3.5)
# Keys match Conductor Phase.value strings
_CARDIAC_TIMEOUT_S: dict[str, float] = {
    "induction":       15.0,
    "deepening":       15.0,
    "maintenance":     15.0,
    "frac_emerge":     15.0,
    "frac_emerge_hold": 15.0,
    "frac_redrop":     15.0,
    "emergence":       10.0,
    "sleep_approach":  10.0,
    "sleep_onset":     10.0,
    "sleep_maintain":  10.0,
    "sleep_training":   8.0,
}
_DEFAULT_CARDIAC_TIMEOUT_S = 15.0

# Phase-specific motion thresholds in g (Bible Ch.2 §2.9 §5.4)
_MOTION_THRESH_SLEEP: dict[str, float] = {
    "sleep_approach":  0.02,
    "sleep_onset":     0.02,
    "sleep_maintain":  0.02,
    "sleep_training":  0.02,
}
_DEFAULT_MOTION_THRESH = 0.04


class DeliveryGate:
    """
    Decides WHEN to fire affirmation flashes and spiral convergence pulses.

    Instantiated once inside CenterTextLayer. Its should_fire() method is called
    every update() tick (at display framerate); it rate-limits internally.

    All gate parameters are read from live_control.json via the config dict
    passed to CenterTextLayer — keys are polled each call so they live-update
    without restarting the display process.
    """

    def __init__(self):
        self._last_fire_time = 0.0
        self._fire_count     = 0
        self._gated_count    = 0
        # Rolling delivery rate tracking
        self._rate_window    = []   # list of monotonic fire timestamps
        self._rate_window_s  = 5.0  # compute rate over last 5 s
        # Trace conditioning hook (Bible Ch.10 §10.1 §11.2) — set by display host if available
        self._conditioning   = None   # optional ConditioningEngine reference

    # ── Primary interface ─────────────────────────────────────────────────────

    def should_fire(self, config: dict) -> dict:
        """
        Called at display framerate by CenterTextLayer.update().

        Reads gate parameters live from config (live_control.json mirror):
          phase_gate_enabled        — master switch (bool, default False)
          phase_gate_min_interval_ms — rate cap (int, default 200)
          phase_gate_max_interval_ms — timeout fallback (int, default 2000)
          phase_gate_trough_window   — radians tolerance (float, default 0.3)
          phase_gate_confidence_min  — min confidence for gated mode (float, default 0.5)
          alpha_at_trough            — bool, written by eeg_engine.py
          alpha_phase_confidence     — float, written by eeg_engine.py
          respiratory_hot            — bool, written by eeg_engine.py
          eeg_connected              — bool
          eeg_sqi                    — float 0–1
          eeg_sqi_min_threshold      — float, default 0.40
          ppg_cardiac_diastole       — bool, written by PPGEngine (Bible Ch.2 §2.9)
          imu_motion_contaminated    — bool, written by IMUEngine (Bible Ch.2 §2.9)
          imu_motion_rms             — float g, written by IMUEngine (Bible Ch.2 §2.9)
          conductor_phase            — str, written by Conductor
          imu_motion_threshold_override — float, written by Conductor on sleep entry

        Returns:
          {"fire": bool, "reason": str, "mode": "gated"|"resp_only"|"fallback"|"disabled",
           "gate_relaxation_level": int (0–3)}
        """
        # ── Master switch — if disabled, caller uses legacy timer ─────────────
        if not config.get("phase_gate_enabled", False):
            return {"fire": False, "reason": "gate_disabled", "mode": "disabled",
                    "gate_relaxation_level": 0}

        now     = time.monotonic()
        elapsed = now - self._last_fire_time

        min_s = config.get("phase_gate_min_interval_ms", 200) / 1000.0
        max_s = config.get("phase_gate_max_interval_ms", 2000) / 1000.0

        # ── Rate limiter ──────────────────────────────────────────────────────
        if elapsed < min_s:
            return {"fire": False, "reason": "rate_limited", "mode": "gated",
                    "gate_relaxation_level": 0}

        # ── Timeout fallback — never block longer than max_s ─────────────────
        if elapsed > max_s:
            return self._record_fire(now, reason="timeout_fallback",
                                     mode="fallback", relaxation=3)

        # ── Motion artifact block (Bible Ch.2 §2.9 §3.1) ──────────────────────────────
        phase_name    = str(config.get("conductor_phase", "induction")).lower()
        motion_thresh = _MOTION_THRESH_SLEEP.get(phase_name, _DEFAULT_MOTION_THRESH)
        # Conductor may override via imu_motion_threshold_override
        override = config.get("imu_motion_threshold_override")
        if override is not None:
            motion_thresh = float(override)
        motion_rms = float(config.get("imu_motion_rms", 0.0) or 0.0)
        if motion_rms > motion_thresh or config.get("imu_motion_contaminated", False):
            return {"fire": False, "reason": "motion_contaminated", "mode": "gated",
                    "gate_relaxation_level": 0}

        # ── Determine EEG quality ─────────────────────────────────────────────
        eeg_ok   = bool(config.get("eeg_connected", False))
        sqi      = float(config.get("eeg_sqi", 0.0) or 0.0)
        sqi_min  = float(config.get("eeg_sqi_min_threshold", 0.40))
        sqi_ok   = eeg_ok and (sqi >= sqi_min)

        conf_min   = float(config.get("phase_gate_confidence_min", 0.5))
        at_trough  = bool(config.get("alpha_at_trough", False))
        confidence = float(config.get("alpha_phase_confidence", 0.0) or 0.0)
        resp_hot   = bool(config.get("respiratory_hot", False))

        # Cardiac diastole gate — permissive default when PPG not available
        cardiac_ok = bool(config.get("ppg_cardiac_diastole", True))

        # ── Progressive relaxation based on stall time (Bible Ch.2 §2.9 §3.4) ─────────
        cardiac_timeout = _CARDIAC_TIMEOUT_S.get(phase_name, _DEFAULT_CARDIAC_TIMEOUT_S)

        if elapsed > _EMERGENCY_TIMEOUT_S:
            # Level 3: emergency — respiratory only
            if resp_hot:
                return self._record_fire(now, reason="emergency_resp_only",
                                         mode="fallback", relaxation=3)
        elif elapsed > _ALPHA_GATE_TIMEOUT_S:
            # Level 2: drop alpha — respiratory + cardiac + SQI
            if sqi_ok and resp_hot and cardiac_ok:
                return self._record_fire(now, reason="relaxed_no_alpha",
                                         mode="gated", relaxation=2)
            if not sqi_ok and resp_hot:
                return self._record_fire(now, reason="resp_only_stalled",
                                         mode="resp_only", relaxation=2)
        elif elapsed > cardiac_timeout:
            # Level 1: drop cardiac — respiratory + alpha + SQI
            if sqi_ok and at_trough and resp_hot and confidence >= conf_min:
                return self._record_fire(now, reason="relaxed_no_cardiac",
                                         mode="gated", relaxation=1)
            if not sqi_ok and resp_hot and elapsed >= 0.5:
                return self._record_fire(now, reason="resp_only",
                                         mode="resp_only", relaxation=1)
        else:
            # Level 0: full quad-gate
            if sqi_ok and at_trough and resp_hot and cardiac_ok and confidence >= conf_min:
                return self._record_fire(now, reason="phase_gated",
                                         mode="gated", relaxation=0)
            # Level 1 (respiratory only when EEG absent)
            if not sqi_ok and resp_hot and elapsed >= 0.5:
                return self._record_fire(now, reason="resp_only",
                                         mode="resp_only", relaxation=0)

        # ── Still waiting ─────────────────────────────────────────────────────
        reason = "waiting_for_gate" if sqi_ok else "waiting_resp"
        return {"fire": False, "reason": reason,
                "mode": "gated" if sqi_ok else "resp_only",
                "gate_relaxation_level": 0}

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _record_fire(self, now: float, reason: str, mode: str,
                     relaxation: int = 0) -> dict:
        self._last_fire_time = now
        self._fire_count    += 1
        if mode == "gated" and relaxation == 0:
            self._gated_count += 1
        self._rate_window.append(now)
        self._rate_window = [t for t in self._rate_window
                             if now - t <= self._rate_window_s]
        return {"fire": True, "reason": reason, "mode": mode,
                "gate_relaxation_level": relaxation}

    # ── Diagnostics ───────────────────────────────────────────────────────────

    @property
    def hit_rate(self) -> float:
        """Rolling fraction of fires that were fully gated (vs fallback/resp-only)."""
        if self._fire_count == 0:
            return 0.0
        return self._gated_count / self._fire_count

    @property
    def delivery_rate_hz(self) -> float:
        """Actual achieved delivery rate over the last rate_window_s seconds."""
        if len(self._rate_window) < 2:
            return 0.0
        span = self._rate_window[-1] - self._rate_window[0]
        if span <= 0:
            return 0.0
        return (len(self._rate_window) - 1) / span

    def notify_delivered(self, config: dict, cs_identity: str, cs_pool: str) -> None:
        """
        Call after a phrase is physically displayed (Bible Ch.10 §10.1 §11.2 trace conditioning hook).

        The display layer calls this once per rendered phrase so the conditioning engine
        can record the CS–US pairing at the precise display moment.  No-op when no
        conditioning engine is attached or when conditioning_engine_enabled is False.
        """
        if self._conditioning is None:
            return
        if not config.get("conditioning_engine_enabled", False):
            return
        try:
            import json
            from pathlib import Path
            _live = Path(__file__).parent.parent / "live_control.json"
            live  = json.loads(_live.read_text(encoding="utf-8")) if _live.exists() else {}
            from engines.conditioning_engine import NeuralStateFingerprint
            ns = NeuralStateFingerprint.from_live(live)
            self._conditioning.on_delivery(
                cs_class        = "veil_phrase",
                cs_identity     = cs_identity,
                cs_pool         = cs_pool,
                neural_state    = ns,
                delivery_gate   = self.diagnostics_dict(),
                conductor_phase = str(config.get("conductor_phase") or ""),
                cardiac_phase   = float(live.get("ppg_cardiac_phase") or 0.0),
                respiratory_phase= float(live.get("respiratory_phase") or 0.0),
                us_magnitude    = float(live.get("eeg_trance_score_v2") or 0.0),
            )
        except Exception:
            pass

    def diagnostics_dict(self) -> dict:
        """For writing to live_control.json diagnostics keys."""
        return {
            "phase_gate_hit_rate":  round(self.hit_rate, 3),
            "delivery_rate_hz":     round(self.delivery_rate_hz, 2),
        }
