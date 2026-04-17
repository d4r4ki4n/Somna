import json
import traceback
import numpy as np
import pygame
import time
import threading
from pathlib import Path
from ipc import patch_live

_TMR_AVAILABLE = False
try:
    from session.tmr_cue_manager import CueManager as _CueManager

    _TMR_AVAILABLE = True
except Exception:
    pass

_LIVE_PATH = Path(__file__).parent.parent / "live_control.json"


def _cfg_float(cfg: dict, key: str, default: float) -> float:
    """Read a float from the config dict, safely handling None / missing / bad values."""
    v = cfg.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _cfg_str(cfg: dict, key: str, default: str) -> str:
    v = cfg.get(key)
    return str(v) if v is not None else default


# Colored-noise color names in display order (matches control panel)
NOISE_COLORS = ("white", "pink", "brown", "blue", "violet", "grey")


class BinauralAudioEngine:
    """Phase-tracked binaural beats with true two-channel crossfade.

    Two mixer channels (A and B) act as "active" and "standby".  Steady-state
    audio streams on the active channel with perfectly continuous phase-tracked
    chunks (no loop-point clicks for any beat frequency).

    On a frequency change (after the 80 ms debounce settles), the standby
    channel is primed with the new frequency at full volume and the old
    active channel is stopped immediately.  Because the new channel is
    already at full volume before the stop, there is no audible gap.
    Any overlap of two different carrier frequencies creates interference
    beating, so the hard stop is intentional.

    Volume changes are debounced 40 ms and applied via set_volume on the
    active channel only, eliminating zipper noise.
    """

    _CHUNK_SEC = 2.0
    _POLL_SEC = 0.025
    _DEBOUNCE_SEC = 0.08  # frequency: wait for slider to settle
    _VOL_DEBOUNCE = 0.04  # volume:    shorter window, no restart needed

    def __init__(self, config):
        # pre_init is called by VisualDisplay before pygame.init(); calling
        # init() here ensures the mixer is active even if this class is used
        # standalone, without re-initialising it if already running.
        pygame.mixer.init()
        pygame.mixer.set_num_channels(
            7
        )  # 0+1 binaural crossfade, 2 noise, 3 sleep bursts, 4+5 TTS, 6 TMR

        self.config = config
        self.sample_rate = 44100
        self.current_carrier = 200.0
        self.current_beat = 10.0
        self.volume = 0.8

        self._chan_a = pygame.mixer.Channel(0)
        self._chan_b = pygame.mixer.Channel(1)

        # Per-channel phase accumulators for seamless chunk continuity.
        # [0] = left (carrier), [1] = right (carrier + beat),
        # [2] = isochronic envelope, [3] = breath AM envelope
        self._phases_a = [0.0, 0.0, 0.0, 0.0]
        self._phases_b = [0.0, 0.0, 0.0, 0.0]

        # Breath modulation (Tier 1 — passive respiratory entrainment)
        self._breath_mod = False
        self._breath_rate = 0.1  # Hz (6 bpm default — population resonance mode)
        self._breath_depth = 0.20  # fraction of carrier amplitude

        self._lock = threading.Lock()

        # Beat-type selection: "binaural" | "isochronic" | "both"
        self._beat_type = "binaural"

        # Beat-phase accumulator: 0.0–1.0, written to live_control.json
        # Written every 8 ticks (200 ms) — fast enough for visual sync,
        # half the file-write pressure of the previous 100 ms cadence.
        self._beat_phase = 0.0
        self._phase_write_counter = 0

        # Crossfade state
        self._active = self._chan_a
        self._standby = self._chan_b
        self._active_phases = self._phases_a
        self._standby_phases = self._phases_b

        # Frequency debounce
        self._pending_carrier = None
        self._pending_beat = None
        self._change_at = None

        # Volume debounce
        self._pending_vol = None
        self._vol_change_at = None

        # Colored noise — dedicated channel, independent of binaural beats
        self._noise_chan = pygame.mixer.Channel(2)
        self._noise_color = "pink"
        self._noise_vol = 30.0
        self._noise_rng = np.random.default_rng()
        self._noise_sound = None

        # Bible Ch.10 §10.2 §3.3 — spectral tilt (1/f^α tracking)
        self._noise_spectral_tilt: float = 1.0
        self._tilt_update_counter: int = 0  # rebuild noise every ~10 s

        # Bible Ch.10 §10.2 §3.2 — AM depth (isochronic envelope depth)
        self._am_depth: float = 0.8
        self._am_depth_target: float = 0.8

        # ── Bible Ch.3 §3.7 — Spatial audio (optional, additive) ───────────────────────
        try:
            from engines.spatial_audio import SpatialAudioEngine as _SAE

            self._spatial: "_SAE | None" = _SAE(sample_rate=self.sample_rate)
        except Exception:
            self._spatial = None

        # Sleep burst channel — channel 3, one-shot 70 ms pink noise bursts
        # Used for both alpha anti-phase (SLEEP_APPROACH) and slow-wave
        # phase-locked enhancement (SLEEP_MAINTAIN).  Bible Ch.7 §7.1 §8.3.
        self._burst_chan = pygame.mixer.Channel(3)
        self._last_burst_cmd_ts: float = 0.0  # deduplicate burst commands

        # TMR cue channel — channel 6, one-shot tonal cues (Bible Ch.7 §7.5)
        # Separate from burst channel so sleep bursts and TMR cues never collide.
        self._tmr_chan = pygame.mixer.Channel(6)
        self._last_tmr_cue_ts: float = 0.0
        self._tmr_cue_mgr = _CueManager() if _TMR_AVAILABLE else None

        # Audio duck / pattern interrupt (entrainment_effects.md §1)
        self._ch_tts = pygame.mixer.Channel(4)
        self._tts_was_busy = False
        self._duck_armed = False
        self._duck_restore_ts: float = 0.0
        self._last_duck_ts: float = 0.0
        self._saved_vol_active: float | None = None
        self._saved_vol_noise: float | None = None

        # ── GENUS rectangular pulse state (Bible Ch.4 Addendum A / genus_protocol.md) ──────────
        # Rectangular 1ms ON / 24ms OFF click train at 40 Hz.  Separate from the
        # normal binaural/isochronic path; activated by genus_active flag.
        self._genus_active: bool = False
        self._genus_frequency: float = 40.0
        self._genus_pulse_ms: float = 1.0
        self._genus_session_start: float = 0.0
        self._genus_session_duration_s: float = 3600.0  # 60 min default
        # Bible Ch.4 Addendum A §3 — ramp gain written by Conductor during RAMP_UP and WIND_DOWN.
        # Scales the pulse amplitude (0.0 = silent, 1.0 = full target amplitude).
        self._genus_audio_gain: float = 1.0

        self._stop_evt = threading.Event()

        # Respect initial mute state so the app doesn't blast on startup.
        # The audio loop handles playback start once audio_muted goes False.
        initial_muted = bool(config.config.get("audio_muted", False))
        self._build_and_play_noise("pink", play=not initial_muted)
        if not initial_muted:
            self._active.play(self._next_chunk_on(self._active_phases))
            self._active.queue(self._next_chunk_on(self._active_phases))
            self._active.set_volume(self.volume)
            self._standby.set_volume(0.0)

        self._thread = threading.Thread(
            target=self._audio_loop, name="AudioEngine", daemon=True
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Colored noise — runs on its own dedicated Channel(2), completely
    # independent of the binaural beat channels so there is no interference.
    # ------------------------------------------------------------------

    _NOISE_BUF_SEC = 10  # loop length before seam
    _NOISE_FADE_SEC = 0.05  # crossfade seam length

    @staticmethod
    def _a_weight(f_hz: np.ndarray) -> np.ndarray:
        """Amplitude A-weighting curve (for grey noise inverse-weighting)."""
        f2 = f_hz**2
        ra = (
            12200.0**2
            * f2**2
            / (
                (f2 + 20.6**2)
                * np.sqrt((f2 + 107.7**2) * (f2 + 737.9**2))
                * (f2 + 12200.0**2)
            )
        )
        return ra + 1e-12

    def _build_noise_buffer(
        self,
        color: str,
        spectral_tilt: float = 1.0,
    ) -> np.ndarray:
        """Generate a peak-normalised, seamlessly loopable mono noise buffer.

        spectral_tilt — Bible Ch.10 §10.2 §3.3: exponent α in 1/f^α. When α=1.0, identical
        to classic pink. Applied as a relative correction relative to pink baseline
        so the perceptual color is preserved while timbre shifts with brain state.
        Range [0.8, 1.5] clamped; default 1.0 = no change.
        """
        fade_n = int(self.sample_rate * self._NOISE_FADE_SEC)
        N = int(self.sample_rate * self._NOISE_BUF_SEC) + fade_n

        white = self._noise_rng.standard_normal(N)

        if color == "white":
            out = white
        else:
            f = np.fft.rfftfreq(N)
            # Zero out DC and everything below 20 Hz to prevent sub-audible
            # amplitude swings that make the noise sound horrible.
            hp_bin = max(1, int(20.0 * N / self.sample_rate))
            f[:hp_bin] = 1.0  # placeholder so division doesn't blow up
            spectrum = np.fft.rfft(white)
            spectrum[:hp_bin] = 0.0

            if color == "pink":
                spectrum[hp_bin:] /= np.sqrt(f[hp_bin:])
            elif color == "brown":
                spectrum[hp_bin:] /= f[hp_bin:]
            elif color == "blue":
                spectrum[hp_bin:] *= np.sqrt(f[hp_bin:])
            elif color == "violet":
                spectrum[hp_bin:] *= f[hp_bin:]
            elif color == "grey":
                freqs_hz = f * self.sample_rate
                freqs_hz[:hp_bin] = 1.0
                spectrum[hp_bin:] /= self._a_weight(freqs_hz[hp_bin:])

            # ── Spectral tilt correction (Bible Ch.10 §10.2 §3.3) ───────────────────────
            # Relative to 1/f^1 (pink baseline):
            # multiply by (f/f_ref)^(1 - α), where f_ref = 0.5 (Nyquist = 1 in rfftfreq).
            # When α = 1.0, correction = 1.0 everywhere (identity).
            tilt = float(np.clip(spectral_tilt, 0.8, 1.5))
            if abs(tilt - 1.0) > 0.01 and color not in ("white", "grey"):
                f_ref = 0.5
                safe_f = np.maximum(f[hp_bin:], 1e-10)
                tilt_filter = np.power(safe_f / f_ref, 1.0 - tilt)
                spectrum[hp_bin:] *= tilt_filter

            out = np.fft.irfft(spectrum, N)

        # Crossfade tail into head so the pygame loop() has no audible seam
        fade = np.linspace(0.0, 1.0, fade_n)
        out[:fade_n] = out[:fade_n] * fade + out[-fade_n:] * (1.0 - fade)
        out = out[:-fade_n]

        peak = np.max(np.abs(out)) + 1e-12
        return (out / peak * 0.92).astype(np.float32)

    def _build_and_play_noise(
        self,
        color: str,
        play: bool = True,
        spectral_tilt: float = 1.0,
    ) -> None:
        """(Re-)generate the looping noise buffer and start it on Channel 2."""
        self._noise_chan.stop()
        self._noise_sound = None
        if color == "off":
            return
        buf = self._build_noise_buffer(color, spectral_tilt=spectral_tilt)
        # Stereo: identical on both channels — mono noise avoids accidental
        # binaural-beat-like effects from left/right decorrelation.
        stereo = np.column_stack([buf, buf])
        sound = pygame.sndarray.make_sound((stereo * 32767.0).astype(np.int16))
        self._noise_sound = sound
        if play:
            self._noise_chan.play(sound, loops=-1)
            self._noise_chan.set_volume(self._noise_vol / 100.0)

    # ── Sleep burst: 70 ms pink noise with 10 ms raised-cosine ramps ─────────

    def _play_tmr_cue(self, pool: str, content_hash: str, gain: float) -> None:
        """Play a TMR tonal cue on Channel 6 (Bible Ch.7 §7.5).

        Generates (or retrieves from cache) the float32 stereo array from
        CueManager, converts to int16, and plays non-blocking on the dedicated
        TMR channel.  Does nothing if CueManager is unavailable.
        """
        if self._tmr_cue_mgr is None:
            return
        try:
            audio = self._tmr_cue_mgr.generate(pool, content_hash)
            pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
            sound = pygame.sndarray.make_sound(pcm)
            self._tmr_chan.stop()
            self._tmr_chan.play(sound)
            self._tmr_chan.set_volume(min(1.0, max(0.0, gain)))
        except Exception:
            pass

    def _deliver_sleep_burst(self, volume: float, duration_ms: int = 50) -> None:
        """Deliver a single phase-locked pink noise burst on Channel 3.

        Envelope: 10 ms ramp-up (raised cosine) → duration_ms hold → 10 ms ramp-down.
        Total length = duration_ms + 20 ms.  Mirrors the isochronic RCOS pattern.
        """
        try:
            ramp_ms = 10
            ramp_n = int(self.sample_rate * ramp_ms / 1000)
            hold_n = int(self.sample_rate * duration_ms / 1000)
            total_n = ramp_n + hold_n + ramp_n

            # Pink noise base
            wn = self._noise_rng.standard_normal(total_n).astype(np.float64)
            freqs = np.fft.rfftfreq(total_n, d=1.0 / self.sample_rate)
            fft_w = np.fft.rfft(wn)
            freqs[0] = 1.0
            fft_w /= np.sqrt(freqs)
            pink = np.fft.irfft(fft_w, n=total_n).astype(np.float32)
            pink /= np.max(np.abs(pink)) + 1e-9

            # Raised cosine envelope (10 ms ramp up, hold, 10 ms ramp down)
            t_ramp = np.linspace(0.0, np.pi / 2, ramp_n, dtype=np.float32)
            ramp_up = np.sin(t_ramp) ** 2
            hold_env = np.ones(hold_n, dtype=np.float32)
            ramp_down = np.cos(t_ramp) ** 2
            envelope = np.concatenate([ramp_up, hold_env, ramp_down])
            burst_mono = pink * envelope

            # Stereo (identical channels)
            stereo = np.column_stack([burst_mono, burst_mono])
            sound = pygame.sndarray.make_sound(
                (stereo * 32767.0).clip(-32768, 32767).astype(np.int16)
            )
            self._burst_chan.stop()
            self._burst_chan.play(sound)
            self._burst_chan.set_volume(min(1.0, volume / 100.0))
        except Exception:
            pass

    # ------------------------------------------------------------------

    def _next_chunk_on(self, phases: list) -> pygame.mixer.Sound:
        """Generate the next chunk, supporting binaural, isochronic, or both modes.

        phases = [carrier_phase, carrier+beat_phase, isochronic_envelope_phase, breath_phase]
        All four are advanced on every call regardless of mode so switching modes
        mid-session maintains phase continuity.
        """
        n = int(self.sample_rate * self._CHUNK_SEC)
        t = np.arange(n) / self.sample_rate

        with self._lock:
            c = self.current_carrier
            b = self.current_beat
            btype = self._beat_type
            carrier_wave = getattr(self, "_carrier_waveform", "sine")
            breath_mod = self._breath_mod
            breath_rate = self._breath_rate
            breath_depth = self._breath_depth
            # Bible Ch.10 §10.2 §3.2 — AM depth (accessed via _am_depth_live set in audio_loop)
            am_depth = float(getattr(self, "_am_depth_live", 0.8))
            lp = phases[0]
            rp = phases[1]
            ip = phases[2]
            bp = phases[3]

            # isochronic envelope respects am_depth: trough = 1-am_depth, peak = 1.0
            # at depth=1.0: oscillates 0→1 (full); at 0.0: constant 1.0 (off)
            def _am_envelope():
                # cos goes 1→-1→1, so scaled: (1 + cos)/2 = 0→1
                phase_sig = 0.5 * (1.0 + np.cos(2.0 * np.pi * b * t + ip))
                # Depth scaling: trough at (1 - am_depth), peak at 1.0
                return (1.0 - am_depth) + am_depth * phase_sig

            def _carrier(freq: float, phase: float) -> np.ndarray:
                """Generate one carrier signal using the configured waveform shape."""
                x = 2.0 * np.pi * freq * t + phase
                if carrier_wave == "square":
                    return np.sign(np.sin(x)).astype(np.float32)
                if carrier_wave == "triangle":
                    # Normalised sawtooth folded into triangle: range [-1, 1]
                    s = x / (2.0 * np.pi)
                    return (2.0 * np.abs(2.0 * (s - np.floor(s + 0.5))) - 1.0).astype(
                        np.float32
                    )
                if carrier_wave == "sawtooth":
                    s = x / (2.0 * np.pi)
                    return (2.0 * (s - np.floor(s + 0.5))).astype(np.float32)
                return np.sin(x).astype(np.float32)  # sine (default)

            if btype == "isochronic":
                # Single carrier, amplitude-modulated at beat_freq via raised cosine
                mono = _carrier(c, lp) * _am_envelope()
                left = right = mono
            elif btype == "both":
                # Bible Ch.10 §10.2 §3.1 "dual": binaural + isochronic blend
                # binaural_blend controls balance (default 0.3 = mostly isochronic)
                bl = float(getattr(self, "_binaural_blend", 0.3))
                bi_weight = bl
                iso_weight = 1.0 - bl
                bi_l = _carrier(c, lp) * bi_weight
                bi_r = _carrier(c + b, rp) * bi_weight
                iso = _carrier(c, lp) * iso_weight * _am_envelope()
                left = bi_l + iso
                right = bi_r + iso
            else:  # "binaural" (default) — frequency offset creates the beat
                left = _carrier(c, lp)
                right = _carrier(c + b, rp)

            # Breath AM — sinusoidal volume swell at breathing rate.
            # Applied multiplicatively after beat type so it modulates the
            # whole carrier without affecting the beat/isochronic envelope.
            # Formula: amplitude × (1 + depth × sin(2π × rate × t + phase))
            if breath_mod and breath_depth > 0.0:
                breath_env = 1.0 + breath_depth * np.sin(
                    2.0 * np.pi * breath_rate * t + bp
                )
                left = left * breath_env
                right = right * breath_env

            # Always advance all four phases for continuity across mode switches
            phases[0] = (lp + 2.0 * np.pi * c * self._CHUNK_SEC) % (2.0 * np.pi)
            phases[1] = (rp + 2.0 * np.pi * (c + b) * self._CHUNK_SEC) % (2.0 * np.pi)
            phases[2] = (ip + 2.0 * np.pi * b * self._CHUNK_SEC) % (2.0 * np.pi)
            phases[3] = (bp + 2.0 * np.pi * breath_rate * self._CHUNK_SEC) % (
                2.0 * np.pi
            )

        stereo = np.column_stack((left, right))

        # ── Bible Ch.3 §3.7 — Spatial audio mix (additive) ────────────────────────────
        if self._spatial is not None:
            try:
                live = {}
                try:
                    from pathlib import Path as _P
                    import json as _js

                    _lp = _P(__file__).parent.parent / "live_control.json"
                    if _lp.exists():
                        live = _js.loads(_lp.read_text(encoding="utf-8"))
                except Exception:
                    pass
                spatial_master = float(live.get("spatial_audio_master", 0.0) or 0.0)
                if spatial_master > 0.0:
                    block = self._spatial.render_block(n, live)
                    stereo = stereo + block.astype(np.float64) * spatial_master
                    # Looming gain envelope (except when TTS is active)
                    if not live.get("tts_active", False):
                        bg_phase = float(live.get("bg_looming_phase", 0.0) or 0.0)
                        env = self._spatial.get_looming_envelope(n, bg_phase)
                        stereo *= env[:, np.newaxis]
            except Exception:
                pass

        return pygame.sndarray.make_sound(
            (np.clip(stereo, -1.0, 1.0) * 32767.0).astype(np.int16)
        )

    def _genus_chunk(self) -> pygame.mixer.Sound:
        """Generate a GENUS rectangular pulse buffer (genus_protocol.md §2.1).

        1 ms ON at full amplitude, 24 ms OFF (zero), tiled to fill _CHUNK_SEC.
        Monaural — both channels identical (not binaural separation).
        NO smoothing, NO Hanning window on individual pulses.
        Amplitude is scaled by _genus_audio_gain (0.0–1.0) for RAMP_UP / WIND_DOWN.
        """
        freq = self._genus_frequency
        pulse_ms = self._genus_pulse_ms
        period_s = 1.0 / freq
        pulse_s = pulse_ms / 1000.0
        off_s = period_s - pulse_s

        on_n = max(1, int(np.ceil(pulse_s * self.sample_rate)))
        off_n = max(1, int(np.ceil(off_s * self.sample_rate)))
        cycle = np.zeros(on_n + off_n, dtype=np.float32)
        gain = max(0.0, min(1.0, self._genus_audio_gain))
        cycle[:on_n] = gain  # sharp rectangular pulse, scaled

        n_total = int(self.sample_rate * self._CHUNK_SEC)
        n_cycles = int(np.ceil(n_total / len(cycle)))
        mono = np.tile(cycle, n_cycles)[:n_total]
        stereo = np.column_stack((mono, mono))
        return pygame.sndarray.make_sound(
            (np.clip(stereo, -1.0, 1.0) * 32767.0).astype(np.int16)
        )

    def _crossfade(self):
        """Swap channels: prime standby with new frequency at full volume,
        fade out old active over _XFADE_MS."""
        try:
            # Reset standby phases — start fresh for the new frequency
            self._standby_phases[0] = 0.0
            self._standby_phases[1] = 0.0
            self._standby_phases[2] = 0.0
            self._standby_phases[3] = 0.0

            # Prime standby with two new-frequency chunks
            self._standby.play(self._next_chunk_on(self._standby_phases))
            self._standby.queue(self._next_chunk_on(self._standby_phases))
            self._standby.set_volume(self.volume)

            # Hard-stop old channel — any overlap of two different binaural
            # frequencies creates audible interference beating; the new channel
            # is already at full volume so there is no gap.
            self._active.stop()

            # Swap roles
            self._active, self._standby = self._standby, self._active
            self._active_phases, self._standby_phases = (
                self._standby_phases,
                self._active_phases,
            )

        except Exception as exc:
            print(f"[Audio] Crossfade error: {exc} — recovering")
            try:
                self._active_phases[:] = [0.0, 0.0, 0.0, 0.0]
                self._active.play(self._next_chunk_on(self._active_phases))
                self._active.queue(self._next_chunk_on(self._active_phases))
                self._active.set_volume(self.volume)
            except Exception as exc2:
                print(f"[Audio] Recovery failed: {exc2}")

    # ------------------------------------------------------------------
    def _audio_loop(self):
        _consecutive_errors = 0
        _first_error_in_run = True  # log full traceback only on first new error
        while not self._stop_evt.is_set():
            try:
                cfg = self.config.update()
                paused = bool(cfg.get("timeline_paused", False))
                muted = bool(cfg.get("audio_muted", False))
                new_carrier = _cfg_float(cfg, "carrier_frequency", 200.0)
                new_beat = _cfg_float(cfg, "beat_frequency", 10.0)
                new_vol = _cfg_float(cfg, "volume", 80.0) / 100.0
                new_btype = _cfg_str(cfg, "beat_type", "binaural")

                # Bible Ch.10 §10.2 §3.1 — entrainment_mode overrides beat_type
                entrainment_mode = _cfg_str(cfg, "entrainment_mode", "")
                if entrainment_mode in ("dual", "hybrid"):
                    new_btype = "both"
                elif entrainment_mode == "isochronic":
                    new_btype = "isochronic"
                elif entrainment_mode == "binaural":
                    new_btype = "binaural"
                # else: use beat_type as before

                new_wave = _cfg_str(cfg, "carrier_waveform", "sine")
                if new_wave not in ("sine", "square", "triangle", "sawtooth"):
                    new_wave = "sine"

                with self._lock:
                    self._beat_type = new_btype
                    self._carrier_waveform = new_wave
                    self._binaural_blend = float(cfg.get("binaural_blend", 0.3) or 0.3)
                    self._breath_mod = bool(cfg.get("breath_mod", False))
                    self._breath_rate = max(
                        0.04, min(0.2, _cfg_float(cfg, "breath_rate", 0.1))
                    )
                    self._breath_depth = max(
                        0.0, min(0.5, _cfg_float(cfg, "breath_depth", 0.20))
                    )

                # ── GENUS rectangular pulse mode (genus_protocol.md §5.1) ─────────
                genus_active = bool(cfg.get("genus_active", False))
                if genus_active != self._genus_active:
                    self._genus_active = genus_active
                    if genus_active:
                        # Record session start for auto-stop timer
                        self._genus_session_start = time.monotonic()
                        self._genus_frequency = float(
                            cfg.get("genus_frequency", 40.0) or 40.0
                        )
                        self._genus_pulse_ms = float(
                            cfg.get("genus_audio_pulse_ms", 1.0) or 1.0
                        )
                        dur_min = float(cfg.get("genus_session_duration_min", 60) or 60)
                        self._genus_session_duration_s = dur_min * 60.0
                    else:
                        self._genus_session_start = 0.0

                if genus_active:
                    # Update params while active (allow live tweaks)
                    self._genus_frequency = float(
                        cfg.get("genus_frequency", 40.0) or 40.0
                    )
                    self._genus_pulse_ms = float(
                        cfg.get("genus_audio_pulse_ms", 1.0) or 1.0
                    )
                    # Bible Ch.4 Addendum A §3 — Conductor writes genus_audio_gain during ramp/wind-down
                    self._genus_audio_gain = float(
                        cfg.get("genus_audio_gain", 1.0) or 1.0
                    )
                    # Session auto-stop
                    elapsed_s = time.monotonic() - self._genus_session_start
                    remaining_s = self._genus_session_duration_s - elapsed_s
                    patch_live(
                        {
                            "genus_session_elapsed_s": round(elapsed_s, 1),
                            "genus_session_remaining_s": round(
                                max(0.0, remaining_s), 1
                            ),
                        }
                    )
                    if remaining_s <= 0.0:
                        patch_live({"genus_active": False})

                # ── Beat-phase accumulator: advances even when muted ──────────
                # When GENUS is active, advance phase at 40 Hz for AV sync.
                if not paused:
                    phase_freq = (
                        self._genus_frequency
                        if self._genus_active
                        else self.current_beat
                    )
                    self._beat_phase = (
                        self._beat_phase + self._POLL_SEC * phase_freq
                    ) % 1.0
                    self._phase_write_counter = (self._phase_write_counter + 1) % 8
                    if self._phase_write_counter == 0:
                        patch_live({"beat_phase": round(self._beat_phase, 4)})

                # ── Colored noise (independent channel) ───────────────────────
                new_noise_color = _cfg_str(cfg, "noise_color", "pink")
                new_noise_vol = _cfg_float(cfg, "noise_volume", 30.0)

                # ── Bible Ch.10 §10.2 §3.3 — spectral tilt tracking ──────────────────────
                new_tilt = float(cfg.get("noise_spectral_tilt", 1.0) or 1.0)
                if cfg.get("noise_tilt_track_brain", False):
                    slope = float(cfg.get("eeg_spectral_slope", -1.0) or -1.0)
                    new_tilt = float(np.clip(abs(slope), 0.8, 1.5))
                tilt_changed = abs(new_tilt - self._noise_spectral_tilt) > 0.05
                if tilt_changed:
                    self._noise_spectral_tilt = new_tilt
                    self._tilt_update_counter = 0  # force rebuild

                # ── Bible Ch.10 §10.2 §3.2 — AM depth (smooth 5 s interpolation) ─────────
                self._am_depth_target = float(cfg.get("am_depth", 0.8) or 0.8)
                # Interpolate at ~1 unit / 5s per audio loop tick
                if abs(self._am_depth - self._am_depth_target) > 0.001:
                    step = self._POLL_SEC / 5.0
                    if self._am_depth < self._am_depth_target:
                        self._am_depth = min(
                            self._am_depth_target, self._am_depth + step
                        )
                    else:
                        self._am_depth = max(
                            self._am_depth_target, self._am_depth - step
                        )
                # Pass current am_depth to chunk generator via lock
                with self._lock:
                    self._am_depth_live = self._am_depth

                if new_noise_color != self._noise_color or tilt_changed:
                    self._noise_color = new_noise_color
                    self._build_and_play_noise(
                        new_noise_color,
                        play=not muted,
                        spectral_tilt=self._noise_spectral_tilt,
                    )
                    self._tilt_update_counter = 0
                elif False:  # placeholder for periodic rebuild
                    pass

                if new_noise_vol != self._noise_vol:
                    self._noise_vol = new_noise_vol
                    if self._noise_color != "off" and self._noise_sound:
                        self._noise_chan.set_volume(new_noise_vol / 100.0)

                # Silence while globally muted; restore on resume.
                # timeline_paused is intentionally NOT checked here — beats should
                # continue running through session pauses and at session end.
                # The mute button is the sole gatekeeper for audio.
                if muted:
                    if self._active.get_volume() > 0:
                        self._active.set_volume(0.0)
                    if self._noise_chan.get_volume() > 0:
                        self._noise_chan.set_volume(0.0)
                    # Keep the binaural channel's queue alive even when muted.
                    # If the two pre-queued chunks drain (~4 s), the channel stops
                    # and some Windows drivers fire a hardware state-change click.
                    # Queueing at volume 0 prevents the channel from ever going idle.
                    if not self._active.get_busy():
                        self._active_phases[:] = [0.0, 0.0, 0.0, 0.0]
                        self._active.play(self._next_chunk_on(self._active_phases))
                        self._active.queue(self._next_chunk_on(self._active_phases))
                    elif not self._active.get_queue():
                        self._active.queue(self._next_chunk_on(self._active_phases))
                    self._stop_evt.wait(timeout=self._POLL_SEC)
                    continue
                else:
                    # Binaural / GENUS channel: restart if stopped.
                    # When GENUS is active, use rectangular pulse chunks instead.
                    if not self._active.get_busy():
                        self._active_phases[:] = [0.0, 0.0, 0.0, 0.0]
                        if self._genus_active and bool(
                            cfg.get("genus_audio_enabled", True)
                        ):
                            self._active.play(self._genus_chunk())
                            self._active.queue(self._genus_chunk())
                        else:
                            self._active.play(self._next_chunk_on(self._active_phases))
                            self._active.queue(self._next_chunk_on(self._active_phases))
                        self._active.set_volume(self.volume)
                    elif self._active.get_volume() == 0.0:
                        self._active.set_volume(self.volume)
                    # Noise channel: same logic.
                    if self._noise_sound and self._noise_color != "off":
                        if not self._noise_chan.get_busy():
                            self._noise_chan.play(self._noise_sound, loops=-1)
                            self._noise_chan.set_volume(self._noise_vol / 100.0)
                        elif self._noise_chan.get_volume() == 0.0:
                            self._noise_chan.set_volume(self._noise_vol / 100.0)

                # ── Sleep burst delivery (Bible Ch.7 §7.1 §8.3) ────────────────────
                burst_ts = cfg.get("sleep_burst_cmd_ts")
                if burst_ts and not muted and burst_ts > self._last_burst_cmd_ts + 0.20:
                    self._last_burst_cmd_ts = float(burst_ts)
                    burst_vol = float(cfg.get("sleep_burst_volume", 12))
                    burst_ms = int(cfg.get("sleep_burst_duration_ms", 50))
                    self._deliver_sleep_burst(burst_vol, burst_ms)

                # ── TMR cue delivery (Bible Ch.7 §7.5) ───────────────────────────
                tmr_cmd = cfg.get("tmr_cue_cmd")
                if tmr_cmd and not muted and isinstance(tmr_cmd, dict):
                    tmr_ts = float(tmr_cmd.get("ts", 0.0) or 0.0)
                    if tmr_ts > self._last_tmr_cue_ts + 0.20:
                        self._last_tmr_cue_ts = tmr_ts
                        self._play_tmr_cue(
                            pool=tmr_cmd.get("pool", "IDENTITY"),
                            content_hash=tmr_cmd.get("content_hash", "0" * 32),
                            gain=float(tmr_cmd.get("gain", 0.12)),
                        )

                # ── Audio duck / pattern interrupt (entrainment_effects.md §1) ───
                duck_ms = int(cfg.get("tts_duck_ms", 0) or 0)
                duck_trigger = cfg.get("tts_duck_trigger")
                if duck_trigger == "next" and duck_ms > 0:
                    self._duck_armed = True

                tts_busy = self._ch_tts.get_busy()
                if self._duck_armed and tts_busy and not self._tts_was_busy:
                    now_mono = time.monotonic()
                    if now_mono - self._last_duck_ts >= 30.0 and not muted:
                        effective_ms = min(duck_ms, 200)
                        self._saved_vol_active = self._active.get_volume()
                        self._saved_vol_noise = self._noise_chan.get_volume()
                        self._active.set_volume(0.0)
                        self._noise_chan.set_volume(0.0)
                        self._duck_restore_ts = now_mono + effective_ms / 1000.0
                        self._last_duck_ts = now_mono
                    self._duck_armed = False
                    try:
                        patch_live({"tts_duck_trigger": None})
                    except Exception:
                        pass
                self._tts_was_busy = tts_busy

                # Restore volumes after duck duration expires
                if self._duck_restore_ts > 0:
                    if time.monotonic() >= self._duck_restore_ts:
                        if self._saved_vol_active is not None:
                            self._active.set_volume(self._saved_vol_active)
                        if self._saved_vol_noise is not None and self._noise_sound:
                            self._noise_chan.set_volume(self._saved_vol_noise)
                        self._duck_restore_ts = 0.0
                        self._saved_vol_active = None
                        self._saved_vol_noise = None

                now = time.monotonic()

                # ── Volume: debounced 40 ms, applied via set_volume only ───
                vol_ref = (
                    self._pending_vol if self._pending_vol is not None else self.volume
                )
                if abs(new_vol - vol_ref) > 0.005:
                    self._pending_vol = new_vol
                    self._vol_change_at = now
                elif self._pending_vol is not None:
                    if now - self._vol_change_at >= self._VOL_DEBOUNCE:
                        self.volume = self._pending_vol
                        self._pending_vol = None
                        self._vol_change_at = None
                        self._active.set_volume(self.volume)

                # ── Frequency: 80 ms debounce then crossfade ───────────────
                ref_c = (
                    self._pending_carrier
                    if self._pending_carrier is not None
                    else self.current_carrier
                )
                ref_b = (
                    self._pending_beat
                    if self._pending_beat is not None
                    else self.current_beat
                )

                moving = abs(new_carrier - ref_c) > 0.05 or abs(new_beat - ref_b) > 0.05

                if moving:
                    self._pending_carrier = new_carrier
                    self._pending_beat = new_beat
                    self._change_at = now
                elif self._pending_carrier is not None:
                    if now - self._change_at >= self._DEBOUNCE_SEC:
                        old_c = self.current_carrier
                        old_b = self.current_beat
                        with self._lock:
                            self.current_carrier = self._pending_carrier
                            self.current_beat = self._pending_beat
                        self._pending_carrier = None
                        self._pending_beat = None
                        self._change_at = None
                        # Only crossfade for large jumps (slider drag, agent command).
                        # Tiny gradient steps update in-place — the next queued chunk
                        # picks up the new frequency at a natural boundary with no
                        # hard stop and no audible click.
                        if (
                            abs(self.current_carrier - old_c)
                            + abs(self.current_beat - old_b)
                        ) >= 2.0:
                            self._crossfade()

                # ── Keep active queue full ─────────────────────────────────
                if not self._active.get_queue():
                    self._active.queue(self._next_chunk_on(self._active_phases))

                _consecutive_errors = 0
                self._stop_evt.wait(timeout=self._POLL_SEC)

            except Exception as exc:
                _consecutive_errors += 1
                if _first_error_in_run:
                    # Full traceback on the first error so crashes are diagnosable
                    print(f"[Audio] Loop error #{_consecutive_errors}: {exc}")
                    traceback.print_exc()
                    _first_error_in_run = False
                else:
                    print(f"[Audio] Loop error #{_consecutive_errors}: {exc}")

                if _consecutive_errors >= 3:
                    print("[Audio] Consecutive errors — attempting channel reinit.")
                    try:
                        # Do NOT call pygame.mixer.quit() — the mixer is owned by
                        # control_panel_imgui.py.  Just stop all channels and recreate them.
                        for ch in (self._chan_a, self._chan_b, self._noise_chan):
                            try:
                                ch.stop()
                            except Exception:
                                pass
                        time.sleep(0.2)
                        self._chan_a = pygame.mixer.Channel(0)
                        self._chan_b = pygame.mixer.Channel(1)
                        self._noise_chan = pygame.mixer.Channel(2)
                        self._active = self._chan_a
                        self._standby = self._chan_b
                        self._active_phases = self._phases_a
                        self._standby_phases = self._phases_b
                        self._active_phases[:] = [0.0, 0.0, 0.0, 0.0]
                        self._active.play(self._next_chunk_on(self._active_phases))
                        self._active.queue(self._next_chunk_on(self._active_phases))
                        self._active.set_volume(self.volume)
                        if not self._noise_chan.get_busy():
                            self._build_and_play_noise(self._noise_color)
                        _consecutive_errors = 0
                        _first_error_in_run = True
                        print("[Audio] Channel reinit successful.")
                    except Exception as reinit_exc:
                        print(f"[Audio] Reinit failed: {reinit_exc} — sleeping 2s")
                        traceback.print_exc()
                        time.sleep(2.0)
                else:
                    self._stop_evt.wait(timeout=self._POLL_SEC)

    def stop(self):
        self._stop_evt.set()
        self._chan_a.stop()
        self._chan_b.stop()
        self._noise_chan.stop()
