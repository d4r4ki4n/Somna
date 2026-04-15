"""
eeg_visual_coupler.py — EEG→Visual gain matrix (Bible Ch.9 §9.2 biofeedback mode)

Maps live EEG band powers to visual layer parameters in real-time.
Only active when eeg_visual_coupling_enabled is True AND eeg_connected is True.

Call apply(cfg) once per frame in the display render loop.  It returns a
*shallow-merged* dict — the original cfg dict is not mutated.  Only the
target visual keys are overridden.

Formula per mapping:
  adjusted = clamp(baseline + gain × master_gain × band_power, lo, hi)

Band powers from eeg_engine are total-power-normalised (0–1, five bands sum ≈ 1).
At equal-power distribution each band ≈ 0.2.  Gains are calibrated so that
a genuinely dominant band (0.4–0.6) produces a clearly perceptible visual shift.

Default matrix
──────────────
  eeg_alpha  →  spiral_opacity (+)   high alpha (relaxed, entrained) → brighter spiral
  eeg_theta  →  spiral_speed  (−)   high theta (dreamy)              → slower rotation
  eeg_beta   →  spiral_chaos  (+)   high beta  (aroused, distracted) → more chaos
  eeg_delta  →  spiral_loom_depth   high delta (approaching sleep)   → loom activates
               + spiral_loom_enabled auto-set True when delta > 0.15
"""

from __future__ import annotations

_DELTA_LOOM_THRESHOLD = 0.15   # above this delta power, loom is auto-enabled

# (source_band_key, target_param_key, gain, clamp_lo, clamp_hi)
_DEFAULT_MATRIX: list[tuple[str, str, float, float, float]] = [
    ("eeg_alpha", "spiral_opacity",          50.0,   0.0, 100.0),
    ("eeg_theta", "spiral_speed_multiplier", -1.5,   0.05,  5.0),
    ("eeg_beta",  "spiral_chaos",             0.4,   0.0,   1.0),
]


def apply(cfg: dict) -> dict:
    """Return a merged cfg dict with EEG-driven visual param overrides applied.

    If coupling is disabled or EEG is not connected the original cfg dict is
    returned unchanged (no copy, no allocation).
    """
    if not cfg.get("eeg_visual_coupling_enabled", False):
        return cfg
    if not cfg.get("eeg_connected", False):
        return cfg

    master_gain = float(cfg.get("eeg_visual_coupling_gain", 1.0) or 1.0)
    if master_gain < 1e-6:
        return cfg

    overrides: dict = {}

    for band_key, param_key, gain, lo, hi in _DEFAULT_MATRIX:
        band_power = float(cfg.get(band_key, 0.0) or 0.0)
        baseline   = float(cfg.get(param_key, 0.0) or 0.0)
        adjusted   = max(lo, min(hi, baseline + gain * master_gain * band_power))
        overrides[param_key] = adjusted

    # Delta → loom depth (and auto-enable loom when delta is dominant)
    delta_power = float(cfg.get("eeg_delta", 0.0) or 0.0)
    if delta_power > 0.0:
        loom_baseline = float(cfg.get("spiral_loom_depth", 0.0) or 0.0)
        overrides["spiral_loom_depth"] = max(0.0, min(1.0,
            loom_baseline + 0.6 * master_gain * delta_power))
        if delta_power >= _DELTA_LOOM_THRESHOLD:
            overrides["spiral_loom_enabled"] = True

    return {**cfg, **overrides}
