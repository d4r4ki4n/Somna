"""
tmr_cue_manager.py — Targeted Memory Reactivation Audio Cue Generator  (Bible Ch.7 §7.5)
=================================================================================
Generates deterministic, pool-keyed audio cues for TMR encoding and replay.

Each of the six content pools has a distinct tonal signature (frequency pair,
waveform shape, AM profile, duration).  Per-affirmation micro-variations are
derived from the MD5 hash of the affirmation text so the same phrase always
produces the same cue — no audio files to ship, no randomness at runtime.

Usage (audio_engine.py side):
    cue_mgr = CueManager()
    audio = cue_mgr.generate(pool="IDENTITY", content_hash="abc123...")
    # audio is float32 ndarray, shape (N, 2), values in [-1.0, 1.0], SR=44100

Usage (conductor.py / tmr_engine.py side):
    h = CueManager.hash_affirmation(phrase_text)
    cue_id = CueManager.get_cue_id("RELEASE", h)
"""

from __future__ import annotations

import hashlib
from typing import Dict, Tuple

import numpy as np

SR: int = 44100  # samples per second — must match pygame.mixer.pre_init rate

# ── Pool tonal signatures ────────────────────────────────────────────────────
# Each entry defines the unmodified (non-hash-jittered) base parameters.
# Micro-variations are added per-affirmation from the content_hash bytes.
#
# f_left / f_right: fundamental tones on left and right channels (Hz)
# am_rate:          amplitude-modulation frequency (Hz); creates a gentle pulse
# am_depth:         AM index 0–1 (0 = no modulation, 1 = full on/off)
# duration_ms:      cue length in milliseconds
# waveform:         "sine" | "sine_harmonic" | "sine_triangle"
#   sine_harmonic   adds a −6 dB octave harmonic (brighter, more forward)
#   sine_triangle   blends with triangle partial (warmer, subtler)
# attack_ms:        raised-cosine attack ramp
# release_ms:       raised-cosine release ramp

POOL_SIGNATURES: Dict[str, dict] = {
    "IDENTITY": {
        # Identity / self-concept — warm and centred
        "f_left": 528.0,
        "f_right": 524.0,
        "am_rate": 4.0,
        "am_depth": 0.35,
        "duration_ms": 250,
        "waveform": "sine",
        "attack_ms": 12,
        "release_ms": 35,
    },
    "RELEASE": {
        # Release / letting go — smooth and receding
        "f_left": 396.0,
        "f_right": 393.5,
        "am_rate": 3.0,
        "am_depth": 0.25,
        "duration_ms": 200,
        "waveform": "sine",
        "attack_ms": 10,
        "release_ms": 30,
    },
    "POTENTIAL": {
        # Capability / growth — brighter, with harmonic content
        "f_left": 639.0,
        "f_right": 641.5,
        "am_rate": 6.0,
        "am_depth": 0.30,
        "duration_ms": 300,
        "waveform": "sine_harmonic",
        "attack_ms": 8,
        "release_ms": 25,
    },
    "SOMATIC": {
        # Body / grounding — deep fundamental, slow pulse
        "f_left": 174.0,
        "f_right": 171.0,
        "am_rate": 2.5,
        "am_depth": 0.40,
        "duration_ms": 350,
        "waveform": "sine",
        "attack_ms": 20,
        "release_ms": 50,
    },
    "PURPOSE": {
        # Goals / motivation — forward, triangle blend
        "f_left": 741.0,
        "f_right": 744.0,
        "am_rate": 5.5,
        "am_depth": 0.28,
        "duration_ms": 250,
        "waveform": "sine_triangle",
        "attack_ms": 8,
        "release_ms": 20,
    },
    "TRANSITION": {
        # State change / fluidity — mid-range, gentle modulation
        "f_left": 285.0,
        "f_right": 282.5,
        "am_rate": 3.5,
        "am_depth": 0.32,
        "duration_ms": 220,
        "waveform": "sine",
        "attack_ms": 15,
        "release_ms": 40,
    },
}

_FALLBACK_POOL = "IDENTITY"

# ── Pool-label keyword mapping ───────────────────────────────────────────────
# Maps substrings of timeline_label → TMR pool name.
# First match wins; fall back to IDENTITY if none match.
_LABEL_KEYWORDS: tuple = (
    ("release",     "RELEASE"),
    ("let_go",      "RELEASE"),
    ("letting",     "RELEASE"),
    ("somatic",     "SOMATIC"),
    ("body",        "SOMATIC"),
    ("breath",      "SOMATIC"),
    ("grounding",   "SOMATIC"),
    ("potential",   "POTENTIAL"),
    ("capab",       "POTENTIAL"),
    ("abilit",      "POTENTIAL"),
    ("purpose",     "PURPOSE"),
    ("goal",        "PURPOSE"),
    ("work",        "PURPOSE"),
    ("motivat",     "PURPOSE"),
    ("transit",     "TRANSITION"),
    ("change",      "TRANSITION"),
    ("shift",       "TRANSITION"),
    ("identity",    "IDENTITY"),
    ("self",        "IDENTITY"),
    ("who",         "IDENTITY"),
)


def pool_for_label(label: str) -> str:
    """Map a timeline_label string to the nearest TMR pool name."""
    low = (label or "").lower()
    for keyword, pool in _LABEL_KEYWORDS:
        if keyword in low:
            return pool
    return _FALLBACK_POOL


# ── Audio generation helpers ─────────────────────────────────────────────────

def hash_affirmation(text: str) -> str:
    """Deterministic 32-char MD5 hex digest of affirmation text."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _hash_jitter(content_hash: str) -> Tuple[float, float, float, float]:
    """Extract (freq_left_delta, freq_right_delta, am_rate_delta, phase_offset)
    from the first 8 hex chars of the content hash.

    All deltas are intentionally small so each cue stays recognisably within
    its pool family while being uniquely distinguishable per affirmation.
    """
    b = bytes.fromhex(content_hash[:8])
    freq_l_delta = (b[0] / 255.0 - 0.5) * 4.0    # ±2 Hz
    freq_r_delta = (b[1] / 255.0 - 0.5) * 4.0    # ±2 Hz
    am_delta     = (b[2] / 255.0 - 0.5) * 1.0    # ±0.5 Hz
    phase        = (b[3] / 255.0) * 2.0 * np.pi  # 0 – 2π radians
    return freq_l_delta, freq_r_delta, am_delta, phase


def _make_envelope(n: int, attack_n: int, release_n: int) -> np.ndarray:
    """Raised-cosine attack + flat sustain + raised-cosine release."""
    env = np.ones(n, dtype=np.float32)
    if attack_n > 0:
        t = np.linspace(0.0, np.pi, attack_n)
        env[:attack_n] = (0.5 - 0.5 * np.cos(t)).astype(np.float32)
    if release_n > 0 and release_n <= n:
        t = np.linspace(0.0, np.pi, release_n)
        env[-release_n:] = (0.5 + 0.5 * np.cos(t)).astype(np.float32)
    return env


def _make_waveform(freq: float, phase_offset: float, n: int,
                   waveform: str) -> np.ndarray:
    t = np.arange(n, dtype=np.float64) / SR
    angle = 2.0 * np.pi * freq * t + phase_offset
    if waveform == "sine_harmonic":
        # Fundamental + octave at −6 dB (0.5× amplitude)
        return (0.75 * np.sin(angle) + 0.25 * np.sin(2.0 * angle)).astype(np.float32)
    if waveform == "sine_triangle":
        # Blend sine with a 3-partial triangle approximation for warmth
        tri = np.sin(angle) - np.sin(3.0 * angle) / 9.0 + np.sin(5.0 * angle) / 25.0
        tri *= 8.0 / (np.pi ** 2)
        return (0.6 * np.sin(angle) + 0.4 * tri).astype(np.float32)
    return np.sin(angle).astype(np.float32)


# ── CueManager ───────────────────────────────────────────────────────────────

class CueManager:
    """Generates and caches per-pool, per-affirmation TMR audio cues.

    All generation is deterministic: the same (pool, content_hash) pair always
    produces the same audio array.  The LRU-style cache (bounded to _MAX_CACHED
    entries) prevents regenerating frequently-used cues.
    """

    _MAX_CACHED: int = 64

    def __init__(self) -> None:
        self._cache: dict = {}

    def generate(self, pool: str, content_hash: str) -> np.ndarray:
        """Return a float32 stereo array of shape (N, 2) at SR=44100.

        Values are in [-1.0, 1.0].  Stereo format matches pygame sndarray
        expectations for a 2-channel Sound object.
        """
        key = (pool, content_hash)
        if key in self._cache:
            return self._cache[key]

        sig = POOL_SIGNATURES.get(pool, POOL_SIGNATURES[_FALLBACK_POOL])
        freq_ld, freq_rd, am_delta, phase_offset = _hash_jitter(content_hash)

        f_left  = sig["f_left"]  + freq_ld
        f_right = sig["f_right"] + freq_rd
        am_rate = max(0.5, sig["am_rate"] + am_delta)
        am_dep  = float(sig["am_depth"])
        n       = int(SR * sig["duration_ms"] / 1000)
        atk_n   = int(SR * sig["attack_ms"]  / 1000)
        rel_n   = int(SR * sig["release_ms"] / 1000)

        t = np.arange(n, dtype=np.float64) / SR

        # Amplitude modulation — slow sinusoidal pulsing
        am = (1.0 - am_dep) + am_dep * 0.5 * (
            1.0 + np.sin(2.0 * np.pi * am_rate * t + phase_offset)
        )
        am = am.astype(np.float32)

        gate  = _make_envelope(n, atk_n, rel_n)
        left  = _make_waveform(f_left,  phase_offset,              n, sig["waveform"])
        right = _make_waveform(f_right, phase_offset + 0.1 * np.pi, n, sig["waveform"])

        left  = left  * am * gate
        right = right * am * gate

        # Normalise to ±0.85 peak to leave headroom for mixer summing
        peak  = max(float(np.max(np.abs(left))), float(np.max(np.abs(right))), 1e-9)
        scale = 0.85 / peak
        audio = np.stack(
            [(left * scale).astype(np.float32),
             (right * scale).astype(np.float32)],
            axis=1,
        )  # shape (N, 2)

        if len(self._cache) >= self._MAX_CACHED:
            del self._cache[next(iter(self._cache))]
        self._cache[key] = audio
        return audio

    @staticmethod
    def get_cue_id(pool: str, content_hash: str) -> str:
        """Stable unique identifier for a (pool, affirmation) pair."""
        return f"{pool}:{content_hash[:12]}"

    @staticmethod
    def hash_affirmation(text: str) -> str:
        """Deterministic 32-char hex digest of affirmation text."""
        return hash_affirmation(text)
