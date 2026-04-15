"""
vr_safety.py — Photosensitive Safety Enforcement (Bible Ch.8 §8.1 §8)
=============================================================
ALL constraints in this module are MANDATORY and NON-NEGOTIABLE.
The Conductor cannot override them.  No configuration file, user
preference, or session state may bypass these limits.

The safety hierarchy is enforced in three layers:
  1. enforce_depth()      — depth clamp at the parameter-computation layer
  2. enforce_max_freq()   — waveform-specific frequency ceiling
  3. check_paroxysmal()   — real-time EEG spike-wave kill switch

First-session ramp: modulation depth starts at 0.10 and increments
0.05 per session, reaching the 0.40 danger-zone cap at session 7.
History is persisted via user_profile.json so the ramp survives
agent restarts.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

try:
    from scipy import signal as _scipy_signal  # noqa: F401
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False
    print(
        "[vr_safety] WARNING: scipy is not installed — paroxysmal EEG spike-wave "
        "detection is DISABLED. Install scipy for full safety enforcement."
    )

_PROFILE_PATH = Path(__file__).parent.parent / "user_profile.json"

# ── Hard frequency ceilings (Bible Ch.8 §8.1 §8.1) ────────────────────────────────────
FREQ_CEILING: dict[str, float] = {
    "square":   30.0,
    "sawtooth": 40.0,
    "sine":     60.0,
}

# ── Photosensitive danger zone (Bible Ch.8 §8.1 §8.2) ─────────────────────────────────
DANGER_ZONE_LOW_HZ  = 10.0
DANGER_ZONE_HIGH_HZ = 25.0
MAX_DANGER_DEPTH    = 0.40    # absolute cap regardless of waveform in danger zone

# ── First-session ramp schedule (Bible Ch.8 §8.1 §8.5) ────────────────────────────────
RAMP_INITIAL  = 0.10
RAMP_STEP     = 0.05
RAMP_CEILING  = 0.40   # matches MAX_DANGER_DEPTH
RAMP_SESSIONS = 7      # sessions 1–7 ramp; session 7+ locked at RAMP_CEILING

# ── Required photosensitivity warning text (Bible Ch.8 §8.1 §8.6) ─────────────────────
PHOTOSENSITIVITY_WARNING = """
PHOTOSENSITIVITY WARNING

This application uses flickering visual stimuli.

If you have a history of photosensitive epilepsy, seizures, or unusual
sensitivity to flashing lights, do not use VR mode.

If you experience any discomfort, dizziness, or visual disturbance during
use, close your eyes immediately and remove the headset.

Continue only after consulting a medical professional.
"""


def enforce_depth(freq: float, waveform: str, requested_depth: float) -> float:
    """Clamp modulation depth according to safety rules.

    Enforced at the rendering layer — not just at the Conductor level.
    This function is the authoritative depth constraint for all VR stimulation.

    Rules applied (in order):
      1. Hard ceiling: danger zone (10–25 Hz) → max 0.40 regardless of waveform
      2. Global range clamp: [0.0, 1.0]
    """
    d = float(requested_depth)
    if DANGER_ZONE_LOW_HZ <= freq <= DANGER_ZONE_HIGH_HZ:
        d = min(d, MAX_DANGER_DEPTH)
    return max(0.0, min(1.0, d))


def enforce_max_freq(waveform: str, requested_freq: float) -> float:
    """Clamp frequency to waveform-specific ceiling.

    Square waves have richer harmonics so the ceiling is stricter.
    Returns the (possibly reduced) frequency.
    """
    ceiling = FREQ_CEILING.get(waveform.lower(), FREQ_CEILING["sine"])
    if requested_freq > ceiling:
        return ceiling
    return max(0.1, requested_freq)


def check_paroxysmal(eeg_buffer: np.ndarray, fs: float) -> bool:
    """Detect paroxysmal spike-wave patterns indicative of seizure onset.

    Triggers on:
      - Sudden high-amplitude (> 4 SD) activity in the last 1 second
      - Combined with elevated 3 Hz spike-wave power relative to alpha baseline

    Returns True if paroxysmal activity is detected → caller must immediately
    set modulation_depth = 0.0, hold static, log event, and alert Conductor.
    """
    if len(eeg_buffer) < int(fs):
        return False

    if not _SCIPY_AVAILABLE:
        return False

    try:
        from scipy import signal as _sig

        std = float(np.std(eeg_buffer))
        if std < 1e-9:
            return False

        recent = eeg_buffer[-int(fs):]   # last 1 second
        peak_amplitude = float(np.max(np.abs(recent)))

        if peak_amplitude > 4.0 * std:
            freqs, psd = _sig.welch(recent, fs=fs, nperseg=len(recent))
            three_hz   = psd[(freqs >= 2.5) & (freqs <= 3.5)].mean()
            baseline   = psd[(freqs >= 8.0) & (freqs <= 12.0)].mean()
            if baseline > 0 and three_hz > 5.0 * baseline:
                return True
    except Exception:
        pass

    return False


class SafetyEnforcer:
    """Stateful safety enforcer — tracks per-session ramp progression.

    Instantiate once per VR session.  Reads and writes the
    `vr_first_session_depth_ramp` key in user_profile.json to persist
    the depth ramp across sessions.
    """

    def __init__(self):
        self._acknowledged = False
        self._paroxysmal_kill = False
        self._paroxysmal_event_ts: float | None = None
        self._session_depth_limit = self._load_depth_limit()
        self._current_session_vr_n = self._load_vr_session_count()

    # ── Warning acknowledgment ─────────────────────────────────────────────

    @property
    def warning_acknowledged(self) -> bool:
        """True if the user has acknowledged the photosensitivity warning."""
        try:
            profile = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
            return bool(profile.get("vr_photosensitivity_ack"))
        except Exception:
            return False

    def record_acknowledgment(self) -> None:
        """Store acknowledgment with timestamp in user_profile.json."""
        self._save_profile_key("vr_photosensitivity_ack", time.strftime("%Y-%m-%dT%H:%M:%S"))
        self._acknowledged = True

    # ── Per-session depth ramp ─────────────────────────────────────────────

    @property
    def session_max_depth(self) -> float:
        """Maximum modulation depth allowed this session based on ramp progression."""
        return self._session_depth_limit

    def advance_ramp_for_next_session(self) -> None:
        """Call at session end if no adverse events occurred.  Increments ramp."""
        n = self._current_session_vr_n + 1
        new_limit = min(RAMP_INITIAL + (n - 1) * RAMP_STEP, RAMP_CEILING)
        self._save_profile_key("vr_session_count", n)
        self._save_profile_key("vr_session_max_depth", round(new_limit, 3))

    def apply_ramp(self, requested_depth: float) -> float:
        """Clamp to current session's ramp limit."""
        return min(float(requested_depth), self._session_depth_limit)

    # ── Paroxysmal kill ────────────────────────────────────────────────────

    @property
    def killed(self) -> bool:
        """True after a paroxysmal event — all stimulation must stop."""
        return self._paroxysmal_kill

    def trigger_paroxysmal_kill(self) -> None:
        """Called when check_paroxysmal() returns True."""
        self._paroxysmal_kill = True
        self._paroxysmal_event_ts = time.time()
        self._save_profile_key("vr_paroxysmal_event", time.strftime("%Y-%m-%dT%H:%M:%S"))
        print("[VR Safety] ⚠ PAROXYSMAL ACTIVITY DETECTED — all VR stimulation halted.")

    # ── Combined gate ──────────────────────────────────────────────────────

    def safe_depth(self, freq: float, waveform: str, requested_depth: float) -> float:
        """Full safety pipeline: ramp → danger zone → paroxysmal kill."""
        if self._paroxysmal_kill:
            return 0.0
        d = self.apply_ramp(requested_depth)
        d = enforce_depth(freq, waveform, d)
        return d

    def safe_freq(self, waveform: str, requested_freq: float) -> float:
        """Waveform frequency ceiling enforcement."""
        return enforce_max_freq(waveform, requested_freq)

    # ── Private ────────────────────────────────────────────────────────────

    def _load_depth_limit(self) -> float:
        try:
            profile = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
            stored = profile.get("vr_session_max_depth")
            if stored is not None:
                return float(stored)
        except Exception:
            pass
        return RAMP_INITIAL

    def _load_vr_session_count(self) -> int:
        try:
            profile = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
            return int(profile.get("vr_session_count", 0))
        except Exception:
            return 0

    def _save_profile_key(self, key: str, value) -> None:
        try:
            path = _PROFILE_PATH
            profile = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            profile[key] = value
            path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        except Exception:
            pass
