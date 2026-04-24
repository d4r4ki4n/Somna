"""
crossmodal_gain.py — Crossmodal Gain Engine (Bible Ch.3 §3.8)

Computes effective channel intensities from raw slider values + EEG state.
Runs at 1 Hz inside the Conductor's tick loop.  Writes gain-adjusted values
to live_control.json via patch_live().

Five-channel gain manifold:
  C_noise   noise_volume         — SR enabler; crossmodal facilitation
  C_beats   volume               — binaural/isochronic entrainment signal
  C_speech  voice_volume         — TTS and subliminal speech
  C_pattern spiral_opacity       — visual pattern intensity
  C_text    veil_opacity, etc.   — subliminal and supraliminal text

Coupling rules (Bible Ch.3 §3.8 §4):
  Noise → Text     inverted-U SR curve; ±15% of sr_optimal_noise = enhancement
  Noise → Beats    carrier-noise protection; binary-search safe noise ceiling
  State → All      depth_gain_scalar scales manifold as trance deepens

Writer priority: User slider > LLM agent > timeline_runner > config defaults.
The gain engine writes at timeline_runner priority.  User-locked params are
always skipped (checked via timeline_locked_params).
"""

import time
from typing import Optional
from ipc import patch_live, read_live


def _read_live() -> dict:
    try:
        return read_live()
    except Exception:
        return {}


def _estimate_pink_noise_at_freq(noise_vol: float, freq_hz: float) -> float:
    """Approximate 1/f power spectral density at freq_hz for given noise_volume.

    Pink noise PSD: S(f) = K / f.  K normalized so vol=50 → K=1.0.
    Returns density in arbitrary perceptual units (not dB).
    """
    k = noise_vol / 50.0
    return k / max(freq_hz, 1.0)


def _reduce_noise_to_safe(
    current_noise: float, carrier_freq: float, carrier_level: float, threshold: float
) -> float:
    """Binary search for maximum noise_volume maintaining CNR >= threshold."""
    lo, hi = 0.0, current_noise
    for _ in range(16):
        mid = (lo + hi) / 2.0
        density = _estimate_pink_noise_at_freq(mid, carrier_freq)
        cnr = carrier_level / max(density, 0.001)
        if cnr >= threshold:
            lo = mid
        else:
            hi = mid
    return round(lo, 2)


# ── Spectral occupancy sanity check (run at calibration / carrier change) ───


def spectral_occupancy_check(live_state: dict) -> list:
    """Validate spectral separation between audio channels.

    Called during calibration and when carrier_frequency changes — not per-tick.
    Returns list of warning strings (empty = all clear).
    """
    warnings = []
    carrier = live_state.get("carrier_frequency", 209)
    beat_freq = live_state.get("beat_frequency", 9.9)
    noise_vol = live_state.get("noise_volume", 22)

    k = noise_vol / 50.0
    noise_density_at_carrier = k / max(carrier, 1.0)
    carrier_level = live_state.get("volume", 78) / 100.0
    cnr = carrier_level / max(noise_density_at_carrier, 0.001)

    if cnr < 8.0:
        warnings.append(
            f"SPECTRAL CONFLICT: Carrier-to-noise ratio {cnr:.1f} at {carrier} Hz. "
            "Binaural entrainment may be masked. Reduce noise_volume or increase beat volume."
        )
    if carrier > 280:
        warnings.append(
            f"SPECTRAL CONFLICT: carrier_frequency {carrier} Hz encroaches on "
            "TTS formant region (300-3000 Hz). Speech intelligibility may degrade."
        )
    right_ear = carrier + beat_freq
    if right_ear < 180:
        warnings.append(
            f"SPECTRAL WARNING: Right-ear carrier at {right_ear:.1f} Hz is deep in "
            "pink noise energy band. Consider raising carrier_frequency."
        )
    ssb_carrier = live_state.get("ssb_carrier_frequency", 16000)
    if ssb_carrier < 12000:
        warnings.append(
            f"SPECTRAL WARNING: SSB carrier at {ssb_carrier} Hz may be audible to "
            "younger users. Recommend >= 14000 Hz."
        )
    return warnings


# ── Sleep gain profiles (Bible Ch.7 §7.1 §8) ─────────────────────────────────────────
# Maps gain_mode → channel ceiling multipliers applied on top of the depth scalar.
# "phase_locked" means the channel is burst-only (managed externally); normal gain = 0.
SLEEP_GAIN_PROFILES: dict = {
    "sleep_approach": {
        "beats": 0.40,  # binaural fade down
        "noise": 0.30,  # ambient pink noise
        "speech_tts": 0.00,  # TTS off
        "speech_sub": 0.00,  # subliminal off
        "pattern": 0.00,  # spiral → 0 (handled by transition entry)
        "text_veil": 0.00,  # veil → 0
        "text_shadow": 0.00,
        "text_center": 0.00,
        "haptic": 0.15,  # gentle presence for relaxation cue
        "tavns": 0.00,  # taVNS off during sleep approach
    },
    "sleep_onset": {
        "beats": 0.20,
        "noise": 0.25,
        "speech_tts": 0.00,
        "speech_sub": 0.00,
        "pattern": 0.00,
        "text_veil": 0.00,
        "text_shadow": 0.00,
        "text_center": 0.00,
        "haptic": 0.00,  # haptics off at sleep onset
        "tavns": 0.00,
    },
    "sleep_maintain": {
        "beats": 0.10,
        "noise": 0.00,  # burst-only; SlowWaveEnhancer drives noise_volume directly
        "speech_tts": 0.00,
        "speech_sub": 0.00,
        "pattern": 0.00,
        "text_veil": 0.00,
        "text_shadow": 0.00,
        "text_center": 0.00,
        "haptic": 0.00,  # TMR cue delivery managed by TMREngine directly
        "tavns": 0.00,
    },
    "sleep_training": {
        "beats": 0.80,  # theta at 5.5 Hz, moderate presence
        "noise": 0.00,  # no ambient texture
        "speech_tts": 0.06,  # intimate whisper
        "speech_sub": 0.14,  # SSB slightly above audible TTS
        "pattern": 0.00,  # no spiral stimulation during HTW
        "text_veil": 0.00,  # no veil distractions
        "text_shadow": 0.25,  # soft glow enhances legibility without startle
        "text_center": 0.35,  # gentle presence in the visual field
        "haptic": 0.00,  # no haptic during HTW
        "tavns": 0.00,
    },
}


# ── CrossmodalGainEngine ─────────────────────────────────────────────────────


class CrossmodalGainEngine:
    """Computes gain-adjusted channel intensities at 1 Hz.

    Instantiated by the Conductor.  calibration_profile keys:
      sr_optimal_noise       : float — calibrated optimal pink noise for SR
      sr_gain_bonus          : float — SR enhancement factor (0.05-0.20)
      carrier_noise_threshold: float — minimum carrier/noise ratio
      baseline_slope         : float — resting-state 1/f slope (from Bible Ch.2 §2.6 / Bible Ch.2 §2.8)
      slope_sensitivity      : float — depth scalar sensitivity (default 0.3)
    """

    # All live_control.json keys managed by this engine.
    # haptic (Ch.3 §3.8 Channel 6) and tavns (Ch.3 §3.8 Channel 7) are
    # Phase-3 hardware channels. Keys are stubs — engine skips them when
    # the corresponding hardware is not connected.
    GAIN_KEYS = {
        "noise": "noise_volume",
        "beats": "volume",
        "speech_tts": "voice_volume",
        "speech_sub": "subliminal_volume",
        "pattern": "spiral_opacity",
        "text_veil": "veil_opacity",
        "text_shadow": "shadow_opacity",
        "text_center": "center_flash_on_time",
        "haptic": "haptic_intensity",  # Lovense BLE — stub until Phase 3
        "tavns": "tavns_current_ua",  # DG Labs Coyote BLE — stub until Phase 3
    }

    # Hardware channels that require explicit connection before gain writes
    HARDWARE_CHANNELS = {"haptic", "tavns"}

    # Default population-average calibration profile (used until SR sweep completes)
    DEFAULT_PROFILE = {
        "sr_optimal_noise": 22.0,
        "sr_gain_bonus": 0.10,
        "carrier_noise_threshold": 8.0,
        "baseline_slope": -1.3,
        "slope_sensitivity": 0.3,
    }

    def __init__(self, calibration_profile: Optional[dict] = None):
        self.profile = {**self.DEFAULT_PROFILE, **(calibration_profile or {})}
        self.last_gains: dict = {}
        self.enabled = True

    def tick(self, live_state: dict) -> dict:
        """Compute gain-adjusted intensities.  Returns patch dict for patch_live().

        Pipeline:
          1. Read raw slider values
          2. Check timeline_locked_params — skip locked channels
          3. Compute depth_gain_scalar from eeg_spectral_slope
          4. Apply depth modulation to all unlocked channels
          5. Apply SR coupling (noise → text enhancement)
          6. Apply carrier-noise protection (noise → beats)
          7. Return delta patch (only values changed by > 0.5)
        """
        if not self.enabled:
            return {}

        locked = set(live_state.get("timeline_locked_params") or [])
        gain_mode = live_state.get("gain_mode", "normal")

        # ── Sleep gain profile shortcut (Bible Ch.7 §7.x) ────────────────────
        # When gain_mode is a sleep profile, apply ceiling multipliers directly
        # and skip the SR coupling (no crossmodal enhancement during sleep).
        sleep_profile = SLEEP_GAIN_PROFILES.get(gain_mode)

        # Hardware channels (haptic, tavns) are only active when explicitly connected.
        connected_hw = set(live_state.get("hardware_channels_connected") or [])
        active_channels = {
            ch: key
            for ch, key in self.GAIN_KEYS.items()
            if ch not in self.HARDWARE_CHANNELS or ch in connected_hw
        }

        # ── Step 1: Raw values ────────────────────────────────────────────────
        raw = {
            ch: float(live_state.get(key, 0) or 0)
            for ch, key in active_channels.items()
        }

        # Guard: if all core audio/visual raw values are zero, this is a bad
        # read (write race) — return empty patch to avoid zero feedback loop.
        _CORE = {"beats", "noise", "pattern", "text_veil"}
        if all(raw.get(ch, 0) == 0 for ch in _CORE):
            return {}

        # ── Step 2: Depth scalar from spectral slope ──────────────────────────
        slope = live_state.get("eeg_spectral_slope") or self.profile["baseline_slope"]
        baseline = self.profile["baseline_slope"]
        sens = self.profile.get("slope_sensitivity", 0.3)
        depth_scalar = max(0.5, min(1.5, 1.0 + (slope - baseline) * sens))

        if sleep_profile is not None:
            # Sleep mode: apply profile ceilings, no SR coupling, no carrier-noise check
            gains: dict = {}
            for ch, key in active_channels.items():
                if key in locked:
                    continue
                ceiling = sleep_profile.get(ch, 0.0)
                gains[key] = round(raw[ch] * ceiling, 2)
            sr_factor = 1.0  # for metadata only
            noise_ratio = 0.0
        else:
            # ── Step 3: SR coupling — noise → text ───────────────────────────
            sr_optimal = max(self.profile["sr_optimal_noise"], 1.0)
            noise_ratio = raw["noise"] / sr_optimal
            if 0.85 <= noise_ratio <= 1.15:
                sr_factor = 1.0 + self.profile["sr_gain_bonus"]
            elif noise_ratio > 1.30:
                penalty = min(0.15, (noise_ratio - 1.30) * 0.3)
                sr_factor = 1.0 - penalty
            else:
                sr_factor = 1.0

            # ── Step 4: Build gain-adjusted output ───────────────────────────
            gains = {}
            for ch, key in active_channels.items():
                if key in locked:
                    continue
                adjusted = raw[ch] * depth_scalar
                if ch.startswith("text_"):
                    adjusted *= sr_factor
                gains[key] = round(adjusted, 2)

        # ── Step 5: Carrier-noise protection (skip in sleep modes) ──────────
        if (
            sleep_profile is None
            and "noise_volume" not in locked
            and "volume" not in locked
        ):
            carrier = float(live_state.get("carrier_frequency", 209) or 209)
            current_noise = gains.get("noise_volume", raw["noise"])
            noise_at_car = _estimate_pink_noise_at_freq(current_noise, carrier)
            car_level = gains.get("volume", raw["beats"]) / 100.0
            cnr = car_level / max(noise_at_car, 0.001)
            threshold = self.profile["carrier_noise_threshold"]
            if cnr < threshold:
                gains["noise_volume"] = _reduce_noise_to_safe(
                    current_noise, carrier, car_level, threshold
                )

        # ── Step 6: Delta patch ───────────────────────────────────────────────
        # Never write zero for core audio/visual keys — that's a write race
        # artifact, not a real state.  Skip those entries entirely.
        _PROTECTED = {"volume", "spiral_opacity", "veil_opacity", "noise_volume"}
        patch: dict = {}
        for k, v in gains.items():
            if k in _PROTECTED and v <= 0:
                continue
            if abs(v - self.last_gains.get(k, -999)) > 0.5:
                patch[k] = v
        self.last_gains = gains

        # ── Step 7: Gain state metadata ──────────────────────────────────────
        cnr_final = 0.0
        if "noise_volume" in gains and "volume" in gains:
            carrier = float(live_state.get("carrier_frequency", 209) or 209)
            nd = _estimate_pink_noise_at_freq(gains["noise_volume"], carrier)
            cnr_final = (gains["volume"] / 100.0) / max(nd, 0.001)

        patch["crossmodal_gain_state"] = {
            "depth_scalar": round(depth_scalar, 3),
            "sr_factor": round(sr_factor, 3),
            "noise_ratio": round(noise_ratio, 3),
            "cnr": round(cnr_final, 3),
            "gain_mode": gain_mode,
            "enabled": self.enabled,
            "ts": time.time(),
        }
        return patch

    def restore_raw(self, live_state: dict) -> dict:
        """Return a patch that restores all gain-engine-managed keys to their raw values.

        Called when the engine is suspended (FRAC_EMERGE / SESSION_END) to hand
        raw slider values back to the timeline runner.
        """
        locked = set(live_state.get("timeline_locked_params") or [])
        patch: dict = {}
        for key in self.GAIN_KEYS.values():
            if key in locked:
                continue
            val = live_state.get(key)
            if val is None:
                continue
            patch[key] = float(val)
        # If all core keys ended up zero/missing, this is a bad read — bail out
        _PROTECTED = {"volume", "spiral_opacity", "veil_opacity", "noise_volume"}
        if all(patch.get(k, 0) <= 0 for k in _PROTECTED):
            return {"crossmodal_gain_state": {"enabled": False, "ts": time.time()}}
        patch["crossmodal_gain_state"] = {"enabled": False, "ts": time.time()}
        self.last_gains = {}
        return patch

    def set_enabled(self, enabled: bool) -> None:
        """Master enable/disable.  When disabled, raw slider values pass through."""
        self.enabled = enabled
        if not enabled:
            self.last_gains = {}


# ── SR Calibration Sweep ─────────────────────────────────────────────────────


class SRCalibrationSweep:
    """Crossmodal SR calibration sweep (Bible Ch.3 §3.8 §6).

    Sweeps noise_volume from 0 to 60 (13 levels, 10 s each, ~2.2 min total).
    Finds individual SR sweet spot as the noise level where crossmodal
    phase synchronization (eeg_crossmodal_sync) peaks.

    Called from the Conductor CALIBRATION phase after IAF calibration.
    No user interaction required — EEG markers only.
    """

    NOISE_LEVELS = list(range(0, 65, 5))  # [0, 5, 10, ..., 60]
    HOLD_SECONDS = 10

    def __init__(self):
        self.current_idx = 0
        self.results: list = []  # [(noise_level, alpha_power, phase_sync), ...]
        self.hold_timer = 0
        self.baseline_alpha: Optional[float] = None
        self.complete = False

    @property
    def progress(self) -> float:
        return self.current_idx / len(self.NOISE_LEVELS)

    def tick(self, live_state: dict) -> Optional[dict]:
        """Called at 1 Hz during SR calibration sub-phase.

        Returns patch dict when changing noise level, calibration result dict
        when complete, or None while collecting data at the current level.
        """
        if self.complete:
            return None

        if self.current_idx >= len(self.NOISE_LEVELS):
            self.complete = True
            return self._compute_optimal()

        level = self.NOISE_LEVELS[self.current_idx]
        self.hold_timer += 1

        # First tick at new level: set noise volume
        if self.hold_timer == 1:
            return {
                "noise_volume": level,
                "noise_color": "pink",
                "_sr_calibration_progress": round(self.progress, 2),
            }

        # End of hold: record EEG measurements and advance
        if self.hold_timer >= self.HOLD_SECONDS:
            alpha = float(live_state.get("eeg_alpha", 0.0) or 0.0)
            phase_sync = float(live_state.get("eeg_crossmodal_sync", 0.0) or 0.0)
            self.results.append((level, alpha, phase_sync))
            if self.current_idx == 0:
                self.baseline_alpha = alpha
            self.current_idx += 1
            self.hold_timer = 0

        return None

    def _compute_optimal(self) -> dict:
        """Analyze sweep results and return calibration profile entries."""
        if not self.results:
            return {
                "sr_optimal_noise": 22.0,
                "sr_gain_bonus": 0.10,
                "carrier_noise_threshold": 8.0,
                "sr_calibration_curve": [],
            }

        # Peak crossmodal phase synchronization → SR optimal noise
        best_idx = max(range(len(self.results)), key=lambda i: self.results[i][2])
        sr_optimal = float(self.results[best_idx][0])

        # SR gain bonus: alpha enhancement at peak vs. baseline
        peak_alpha = self.results[best_idx][1]
        baseline = self.baseline_alpha or peak_alpha
        raw_bonus = ((peak_alpha - baseline) / baseline) if baseline > 0.001 else 0.10
        sr_gain_bonus = max(0.05, min(0.20, raw_bonus))

        # Carrier-noise threshold from boundary noise level above optimal
        if best_idx < len(self.results) - 1:
            boundary_noise = float(self.results[best_idx + 1][0])
        else:
            boundary_noise = sr_optimal * 1.3
        boundary_density = _estimate_pink_noise_at_freq(boundary_noise, 209.0)
        cnr_threshold = (78.0 / 100.0) / max(boundary_density, 0.001)

        return {
            "sr_optimal_noise": sr_optimal,
            "sr_gain_bonus": round(sr_gain_bonus, 3),
            "carrier_noise_threshold": round(cnr_threshold, 2),
            "sr_calibration_curve": [(r[0], round(r[2], 4)) for r in self.results],
            "sr_baseline_alpha": round(baseline, 4),
        }
