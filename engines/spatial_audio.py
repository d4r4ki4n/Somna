"""
engines/spatial_audio.py — Spatial Audio Enhancement Layer (Bible Ch.3 §3.7)
====================================================================
Additive audio layer mixed into the main binaural/isochronic output.

Four sub-generators:
  StereoPanner     — entrainment-rate L/R sweep (constant power, at sub-LFO freq)
  ASMRTextureGen   — Poisson-distributed filtered pink noise bursts
  LoomingSync      — 75 ms delayed looming phase ±1.5 dB gain envelope
  ShepardToneGen   — slow descending Shepard/Risset tone (6 octaves, Gaussian)

Usage (from audio_engine.py):
    self._spatial = SpatialAudioEngine(sample_rate=44100)
    # ... in chunk generation:
    block = self._spatial.render_block(n_frames, live_state)
    # mix block into master at spatial_audio_master gain
"""

from __future__ import annotations

import math
import random
import time
from collections import deque
from typing import Optional

import numpy as np


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pink_noise(rng: np.random.Generator, n: int, sr: int) -> np.ndarray:
    """Fast approximate pink noise via 1/f spectral shaping."""
    white = rng.standard_normal(n)
    f     = np.fft.rfftfreq(n)
    hp    = max(1, int(80.0 * n / sr))
    spec  = np.fft.rfft(white)
    f[:hp] = 1.0
    spec[:hp] = 0.0
    spec[hp:] /= np.sqrt(f[hp:])
    pink = np.fft.irfft(spec, n).astype(np.float32)
    pk   = np.max(np.abs(pink)) + 1e-12
    return (pink / pk * 0.92).astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════════════
# StereoPanner (Bible Ch.3 §3.7 §4.2)
# ═══════════════════════════════════════════════════════════════════════════════

class StereoPanner:
    """Constant-power stereo pan sweep at entrainment_freq_hz rate."""

    _DEFAULT_DEPTH = 0.7

    def __init__(self, sample_rate: int = 44100):
        self.sr    = sample_rate
        self._phase = 0.0

    def render(
        self,
        n: int,
        entrainment_hz: float,
        gain: float,
    ) -> np.ndarray:
        """Return (n, 2) float32 stereo output, scaled by gain."""
        if gain < 1e-6 or entrainment_hz <= 0.0:
            return np.zeros((n, 2), dtype=np.float32)

        t    = np.arange(n) / self.sr
        pan  = math.sin(2 * math.pi * entrainment_hz * t[0] + self._phase)
        # Full vector
        phi  = 2 * math.pi * entrainment_hz / self.sr
        phase_vec = (2 * math.pi * entrainment_hz * t + self._phase).astype(np.float32)
        pan_vec   = np.sin(phase_vec) * self._DEFAULT_DEPTH   # range [-depth, +depth]

        # Constant-power: left = cos((pan+1)*pi/4), right = sin((pan+1)*pi/4)
        angle  = (pan_vec + 1.0) * (math.pi / 4.0)
        left   = np.cos(angle).astype(np.float32)
        right  = np.sin(angle).astype(np.float32)

        # Advance phase
        self._phase = float((phase_vec[-1] + phi) % (2 * math.pi))

        noise  = np.random.default_rng().standard_normal(n).astype(np.float32) * 0.1
        return np.column_stack([left * noise, right * noise]) * gain


# ═══════════════════════════════════════════════════════════════════════════════
# ASMRTextureGen (Bible Ch.3 §3.7 §4.3)
# ═══════════════════════════════════════════════════════════════════════════════

class ASMRTextureGen:
    """Poisson-distributed pink noise bursts: soft, continuous ASMR-like texture."""

    _RAMP_UP_MS   = 50
    _DECAY_MS     = 200
    _LPF_CUTOFF   = 2000.0    # Hz
    _HPF_CUTOFF   = 80.0      # Hz

    def __init__(self, sample_rate: int = 44100):
        self.sr       = sample_rate
        self._rng     = np.random.default_rng()
        self._pending : deque[dict] = deque()   # queued burst events
        self._mean_interval_s = 2.0             # Poisson mean, phase-dependent
        self._next_event_s    = 0.0

    def _compute_mean_interval(self, conductor_phase: str) -> float:
        intervals = {
            "calibration": 3.0,
            "induction":   2.5,
            "deepening":   2.0,
            "maintenance": 1.5,
            "sleep_approach": 3.0,
        }
        return intervals.get(conductor_phase.lower(), 2.0)

    def _generate_burst(self, duration_ms: int, pan: float) -> dict:
        ramp_n  = int(self.sr * self._RAMP_UP_MS / 1000)
        hold_n  = int(self.sr * duration_ms / 1000)
        decay_n = int(self.sr * self._DECAY_MS / 1000)
        total_n = ramp_n + hold_n + decay_n

        pink = _pink_noise(self._rng, total_n, self.sr)
        # Simple RC low/high-pass approximation (per-sample IIR)
        rc_lp = 1.0 - math.exp(-2 * math.pi * self._LPF_CUTOFF / self.sr)
        rc_hp = 1.0 - math.exp(-2 * math.pi * self._HPF_CUTOFF / self.sr)
        y_lp  = np.zeros(total_n, dtype=np.float32)
        y_hp  = np.zeros(total_n, dtype=np.float32)
        for i in range(total_n):
            y_lp[i] = y_lp[i-1] + rc_lp * (pink[i] - y_lp[i-1]) if i > 0 else pink[i]
        prev_hp = 0.0
        prev_x  = float(y_lp[0])
        for i in range(total_n):
            x = float(y_lp[i])
            y_hp[i] = rc_hp * (prev_hp + x - prev_x)
            prev_hp, prev_x = float(y_hp[i]), x

        # Envelope
        ramp_up   = np.sin(np.linspace(0, math.pi / 2, ramp_n, dtype=np.float32)) ** 2
        hold_env  = np.ones(hold_n, dtype=np.float32)
        decay_env = np.cos(np.linspace(0, math.pi / 2, decay_n, dtype=np.float32)) ** 2
        envelope  = np.concatenate([ramp_up, hold_env, decay_env])
        mono      = y_hp * envelope * 0.03

        # Pan ±0.4
        pan_clamp = max(-0.4, min(0.4, pan))
        angle = (pan_clamp + 1.0) * (math.pi / 4.0)
        left  = mono * math.cos(angle)
        right = mono * math.sin(angle)
        return {"stereo": np.column_stack([left, right]), "offset": 0}

    def render(
        self,
        n: int,
        elapsed_s: float,
        gain: float,
        conductor_phase: str = "",
    ) -> np.ndarray:
        if gain < 1e-6:
            return np.zeros((n, 2), dtype=np.float32)

        self._mean_interval_s = self._compute_mean_interval(conductor_phase)

        # Schedule new burst (Poisson via exponential inter-arrival)
        if elapsed_s >= self._next_event_s:
            duration_ms = int(self._rng.integers(80, 200))
            pan         = float(self._rng.uniform(-0.4, 0.4))
            burst       = self._generate_burst(duration_ms, pan)
            self._pending.append(burst)
            # Next event: exponential distribution
            self._next_event_s = elapsed_s + float(
                self._rng.exponential(self._mean_interval_s)
            )

        out = np.zeros((n, 2), dtype=np.float32)
        still_pending = deque()
        for burst in self._pending:
            stereo = burst["stereo"]
            start  = burst["offset"]
            remain = len(stereo) - start
            if remain <= 0:
                continue
            copy_n = min(n, remain)
            out[:copy_n] += stereo[start : start + copy_n]
            burst["offset"] = start + copy_n
            if start + copy_n < len(stereo):
                still_pending.append(burst)
        self._pending = still_pending
        return out * gain


# ═══════════════════════════════════════════════════════════════════════════════
# LoomingSync (Bible Ch.3 §3.7 §4.4)
# ═══════════════════════════════════════════════════════════════════════════════

class LoomingSync:
    """75 ms delay buffer; ±1.5 dB looming gain envelope."""

    _DELAY_MS      = 75.0
    _GAIN_AMPLITUDE = 0.17   # ~1.5 dB = 10^(1.5/20) - 1 ≈ 0.189; doc uses 0.17

    def __init__(self, sample_rate: int = 44100):
        self.sr          = sample_rate
        self._delay_n    = int(sample_rate * self._DELAY_MS / 1000)
        self._buf        = np.zeros(self._delay_n * 2, dtype=np.float32)
        self._buf_pos    = 0
        self._phase_hist = deque([0.0] * self._delay_n, maxlen=self._delay_n)

    def update_phase(self, bg_looming_phase: float) -> None:
        self._phase_hist.append(bg_looming_phase)

    def get_gain_envelope(self, n: int) -> np.ndarray:
        delayed_phase = self._phase_hist[0] if self._phase_hist else 0.0
        gain = 1.0 + self._GAIN_AMPLITUDE * math.sin(2 * math.pi * delayed_phase)
        return np.full(n, gain, dtype=np.float32)


# ═══════════════════════════════════════════════════════════════════════════════
# ShepardToneGen (Bible Ch.3 §3.7 §4.5)
# ═══════════════════════════════════════════════════════════════════════════════

class ShepardToneGen:
    """Slowly descending Shepard/Risset tone: 6 octave-spaced partials, Gaussian envelope."""

    _OCTAVES       = 6
    _CENTER_FREQ   = 440.0
    _CENTER_LOG2   = math.log2(440.0)
    _SIGMA_OCTAVES = 2.0
    _DESCENT_ST_PER_S = 1.0 / 30.0    # 1 semitone per 30 s
    _SEMITONE      = 2.0 ** (1.0 / 12.0)

    _ACTIVE_PHASES = {
        "deepening", "maintenance", "sleep_approach",
        "sleep_onset", "sleep_maintain",
    }

    def __init__(self, sample_rate: int = 44100):
        self.sr         = sample_rate
        self._pitch_st  = 0.0           # cumulative semitone descent
        self._phases    = [0.0] * self._OCTAVES
        self._last_t    = time.monotonic()

    def render(
        self,
        n: int,
        gain: float,
        conductor_phase: str = "",
    ) -> np.ndarray:
        if gain < 1e-6 or conductor_phase.lower() not in self._ACTIVE_PHASES:
            return np.zeros((n, 2), dtype=np.float32)

        now = time.monotonic()
        dt  = now - self._last_t
        self._last_t = now

        # Advance pitch descent
        self._pitch_st += self._DESCENT_ST_PER_S * dt
        # Reset per octave so it seems to descend forever
        if self._pitch_st >= 12.0:
            self._pitch_st -= 12.0

        t   = np.arange(n, dtype=np.float32) / self.sr
        out = np.zeros(n, dtype=np.float32)

        for i in range(self._OCTAVES):
            # Frequency: center ± i octaves, shifted by cumulative semitone descent
            log2_f = self._CENTER_LOG2 + i - self._OCTAVES / 2 - self._pitch_st / 12.0
            freq   = 2.0 ** log2_f

            # Gaussian amplitude weight on log2(freq)
            diff   = log2_f - self._CENTER_LOG2
            amp    = math.exp(-(diff ** 2) / (2 * self._SIGMA_OCTAVES ** 2))

            # Sinusoid with phase continuity
            phase_vec = 2 * math.pi * freq * t + self._phases[i]
            out      += amp * np.sin(phase_vec)
            self._phases[i] = float((phase_vec[-1] + 2 * math.pi * freq / self.sr) % (2 * math.pi))

        # Normalize and gain
        pk  = np.max(np.abs(out)) + 1e-12
        out = (out / pk * 0.01).astype(np.float32)  # ~1% master
        mono_stereo = np.column_stack([out, out])
        return mono_stereo * gain


# ═══════════════════════════════════════════════════════════════════════════════
# SpatialAudioEngine (central coordinator)
# ═══════════════════════════════════════════════════════════════════════════════

class SpatialAudioEngine:
    """
    Additive spatial audio layer for Somna (Bible Ch.3 §3.7 §4).

    Called from audio_engine.py; returns a (n_frames, 2) float32 stereo block
    that is mixed into the master output at `spatial_audio_master` gain.

    Usage:
        engine = SpatialAudioEngine(44100)
        block  = engine.render_block(n_frames, live_state)
        # add block to master mix at spatial_audio_master gain
    """

    def __init__(self, sample_rate: int = 44100):
        self.sr      = sample_rate
        self._panner = StereoPanner(sample_rate)
        self._asmr   = ASMRTextureGen(sample_rate)
        self._looming = LoomingSync(sample_rate)
        self._shepard = ShepardToneGen(sample_rate)
        self._elapsed_s = 0.0

    def render_block(self, n_frames: int, live: dict) -> np.ndarray:
        """Return (n_frames, 2) float32 stereo additive block."""
        out = np.zeros((n_frames, 2), dtype=np.float32)

        entrainment_hz   = float(live.get("entrainment_freq_hz") or
                                 live.get("beat_frequency") or 10.0)
        conductor_phase  = str(live.get("conductor_phase") or "")
        bg_looming_phase = float(live.get("bg_looming_phase") or 0.0)

        pan_gain     = float(live.get("spatial_panning_gain",  0.0) or 0.0)
        asmr_gain    = float(live.get("spatial_asmr_gain",     0.0) or 0.0)
        shepard_gain = float(live.get("spatial_shepard_gain",  0.0) or 0.0)
        looming_gain = float(live.get("spatial_looming_gain",  0.5) or 0.5)

        # ── 1. Stereo panner ────────────────────────────────────────────────
        out += self._panner.render(n_frames, entrainment_hz, pan_gain)

        # ── 2. ASMR bursts ──────────────────────────────────────────────────
        self._elapsed_s += n_frames / self.sr
        out += self._asmr.render(n_frames, self._elapsed_s, asmr_gain, conductor_phase)

        # ── 3. Shepard tone ─────────────────────────────────────────────────
        out += self._shepard.render(n_frames, shepard_gain, conductor_phase)

        return out

    def get_looming_envelope(self, n_frames: int, bg_looming_phase: float) -> np.ndarray:
        """
        Update phase history and return (n_frames,) gain envelope for looming.
        Caller multiplies master mix by this envelope (except TTS channel).
        """
        self._looming.update_phase(bg_looming_phase)
        return self._looming.get_gain_envelope(n_frames)
