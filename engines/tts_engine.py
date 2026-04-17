"""
tts_engine.py
Somna — Text-to-Speech Engine

Architecture: pre-synthesis queue, display follows audio.
  1. Background thread continuously pre-synthesises phrases from the phrase
     pool and parks them in a small ready buffer (default 2 ahead).
  2. CenterTextLayer calls poll_ready() each frame.
     When a sound is ready, poll_ready() starts playback and returns
     (phrase, duration_ms).  CenterTextLayer locks the phrase visible for
     exactly that duration, then resumes normal flash behaviour.
  3. Because synthesis latency (~200-500 ms) is absorbed by pre-fetching,
     there is no per-flash API call and no race against the flash timer.

Backends
--------
  edge   — Microsoft Edge neural TTS (free, no key).
           pip install edge-tts
           Voice examples: en-US-JennyNeural, en-US-AriaNeural, en-US-SaraNeural

  openai — OpenAI /v1/audio/speech OR any compatible local server
           (Kokoro-FastAPI, OpenedAI-speech, piper-tts-server …).
           Set tts_api_url to your server's base URL.
           Set tts_api_key to "none" for unauthenticated local servers.
           Voice examples (OpenAI): alloy, echo, fable, nova, shimmer
           Voice examples (Kokoro): af_bella, af_sarah, bm_george …

Silent-subliminal mode (optional)
----------------------------------
Applies Lowry SSB-AM modulation (same algorithm as the Audacity 'silent
subliminals' Nyquist plugin).  Note: the result is NOT literally silent —
it sits at ~17.5 kHz, which IS audible to people with good HF hearing as a
faint tone.  The speech content is incoherent at that frequency; the
perceptual effect is neurological, not conscious decoding.
Extra deps: pip install scipy miniaudio

live_control.json keys
-----------------------
  tts_enabled        bool    master on/off
  tts_backend        str     "edge" | "openai" | "local"
  tts_voice          str     voice name (backend-specific)
  tts_volume         float   0–100, audible channel
  tts_subliminal     bool    enable SSB subliminal layer
  tts_subliminal_vol float   0–100, subliminal channel
  tts_subliminal_hz  float   carrier Hz (14000–20000, default 17500)
  tts_api_url        str     base URL for openai/local backend
  tts_api_key        str     API key ("none" for local servers)
  tts_model          str     model name (default "tts-1")
"""

import io
import json
import queue
import threading
import time
import wave
from collections import deque
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
import pygame

from layers.phrase_pool import PhrasePool

# ── Mixer channel allocation ──────────────────────────────────────────────────
_CH_TTS = 4  # audible TTS
_CH_SUBLI = 5  # subliminal layer
_MIN_CH = 6


# ── Backends ──────────────────────────────────────────────────────────────────


class _Backend(ABC):
    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Return synthesised audio bytes."""

    @property
    def fmt(self) -> str:
        return "mp3"


class _EdgeBackend(_Backend):
    def __init__(
        self, voice: str = "en-US-JennyNeural", pitch: str = "+0Hz", rate: str = "+0%"
    ):
        self.voice = voice
        self.pitch = pitch or "+0Hz"
        self.rate = rate or "+0%"

    def synthesize(self, text: str) -> bytes:
        import asyncio
        import edge_tts

        pitch = self.pitch
        rate = self.rate

        async def _run() -> bytes:
            kwargs: dict = {}
            if rate and rate != "+0%":
                kwargs["rate"] = rate
            if pitch and pitch != "+0Hz":
                kwargs["pitch"] = pitch
            communicate = edge_tts.Communicate(text, self.voice, **kwargs)
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            return buf.getvalue()

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()


class _OpenAIBackend(_Backend):
    def __init__(
        self,
        api_key: str,
        voice: str = "nova",
        model: str = "tts-1",
        base_url: str = "https://api.openai.com/v1",
    ):
        self.api_key = api_key
        self.voice = voice
        self.model = model
        self.base_url = base_url.rstrip("/")

    def synthesize(self, text: str) -> bytes:
        import json, urllib.request

        payload = json.dumps(
            {
                "model": self.model,
                "input": text,
                "voice": self.voice,
                "response_format": "wav",
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/audio/speech",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()

    @property
    def fmt(self) -> str:
        return "wav"


# ── SSB subliminal (Lowry method) ─────────────────────────────────────────────


def _ssb_modulate(audio_bytes: bytes, carrier_hz: float = 17500.0) -> Optional[bytes]:
    """
    Shift speech to a high-frequency carrier via single-sideband AM.
    Requires: pip install scipy miniaudio
    Returns WAV bytes at 44100 Hz / 16-bit mono, or None on error.
    """
    try:
        import miniaudio
        from scipy import signal as sig
    except ImportError as e:
        print(f"[TTS] Subliminal unavailable ({e}). pip install scipy miniaudio")
        return None

    SR = 44100
    try:
        decoded = miniaudio.decode(
            audio_bytes,
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=1,
            sample_rate=SR,
        )
        s = np.frombuffer(decoded.samples, dtype=np.float32).copy()
    except Exception as e:
        print(f"[TTS] Subliminal decode error: {e}")
        return None

    nyq = SR / 2.0
    cutoff = min(carrier_hz / 2.0, nyq - carrier_hz) * 0.95
    if cutoff <= 0:
        print(f"[TTS] Carrier {carrier_hz:.0f} Hz too high for {SR} Hz sample rate")
        return None

    try:
        from scipy import signal as sig

        b, a = sig.butter(4, 80.0 / nyq, btype="high")
        s = sig.filtfilt(b, a, s)
        b, a = sig.butter(8, cutoff / nyq, btype="low")
        s = sig.filtfilt(b, a, s)
        t = np.arange(len(s), dtype=np.float64) / SR
        s = 2.0 * s * np.cos(2.0 * np.pi * carrier_hz * t)
        b, a = sig.butter(8, carrier_hz / nyq, btype="high")
        s = sig.filtfilt(b, a, s)

        peak = np.max(np.abs(s))
        if peak > 0:
            s = s / peak * 0.30

        s16 = (s * 32767.0).clip(-32768, 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SR)
            wf.writeframes(s16.tobytes())
        return buf.getvalue()
    except Exception as e:
        print(f"[TTS] Subliminal processing error: {e}")
        return None


# ── Entrainment voice effects ─────────────────────────────────────────────────


def _apply_beat_mod(pcm: np.ndarray, beat_hz: float, sr: int) -> np.ndarray:
    """Amplitude-modulate *pcm* at *beat_hz* (±25 % depth).

    Subtly pulses the voice at the current entrainment frequency, reinforcing
    the binaural beat target through the auditory amplitude envelope.
    Works best during theta / delta sessions (< 8 Hz).

    Parameters
    ----------
    pcm     int16 mono or stereo numpy array (from miniaudio decode).
    beat_hz beat frequency in Hz (e.g. 4.5).
    sr      sample rate in Hz.
    """
    if beat_hz <= 0 or len(pcm) == 0:
        return pcm
    frames = len(pcm) if pcm.ndim == 1 else pcm.shape[0]
    t = np.arange(frames, dtype=np.float64) / sr
    mod = (0.75 + 0.25 * np.sin(2.0 * np.pi * beat_hz * t)).astype(np.float32)
    if pcm.ndim == 2:
        mod = mod[:, np.newaxis]
    result = (pcm.astype(np.float32) * mod).clip(-32768, 32767).astype(np.int16)
    return result


def _apply_reverb(
    pcm: np.ndarray, sr: int, delay_ms: int = 80, decay: float = 0.35
) -> np.ndarray:
    """Add a single echo layer to create a spacious, dissociative quality.

    A short delay + decay produces a room-like presence that doesn't muddy
    speech but adds psychological distance — useful for deepener phrases.

    Parameters
    ----------
    pcm      int16 mono or stereo numpy array.
    sr       sample rate in Hz.
    delay_ms echo delay in milliseconds (default 80 ms).
    decay    echo amplitude (0–1, default 0.35).
    """
    if len(pcm) == 0:
        return pcm
    delay_samples = int(sr * delay_ms / 1000)
    out = pcm.astype(np.float32).copy()
    if pcm.ndim == 1:
        out[delay_samples:] += pcm[:-delay_samples].astype(np.float32) * decay
    else:
        out[delay_samples:] += pcm[:-delay_samples].astype(np.float32) * decay
    return out.clip(-32768, 32767).astype(np.int16)


def _apply_reverb_chain(
    pcm: np.ndarray,
    sr: int,
    reverb_wet: float = 0.0,
    reverb_room_ms: int = 80,
    delay_ms: int = 0,
    delay_feedback: float = 0.0,
) -> np.ndarray:
    """Full reverb + delay chain for TTS voice processing.

    entrainment_effects.md section 2: Schroeder-style reverb with echo delay.
    Applied at pre-synthesis time, zero runtime latency.

    Parameters
    ----------
    pcm              int16 mono or stereo numpy array.
    sr               sample rate in Hz.
    reverb_wet       0.0-1.0 wet/dry mix (0 = dry, 0.7 = large hall).
    reverb_room_ms   20-500 reverb tail length in ms.
    delay_ms         0-300 echo delay in ms (0 = disabled).
    delay_feedback   0.0-0.8 echo feedback gain.
    """
    if len(pcm) == 0:
        return pcm
    if reverb_wet <= 0.0 and delay_ms <= 0:
        return pcm

    out = pcm.astype(np.float32).copy()

    if reverb_wet > 0.0:
        delay_n = max(1, int(sr * reverb_room_ms / 1000))
        reverb_buf = np.zeros_like(out)
        if delay_n < len(out):
            reverb_buf[delay_n:] = out[:-delay_n] * reverb_wet * 0.5
        tap2 = int(delay_n * 0.67)
        if 0 < tap2 < len(out):
            reverb_buf[tap2:] += out[:-tap2] * reverb_wet * 0.3
        out = out + reverb_buf

    if delay_ms > 0 and delay_feedback > 0.0:
        delay_n = max(1, int(sr * delay_ms / 1000))
        echo = np.zeros_like(out)
        if delay_n < len(out):
            echo[delay_n:] = out[:-delay_n] * delay_feedback
        out = out + echo

    return out.clip(-32768, 32767).astype(np.int16)


# ── Main engine ───────────────────────────────────────────────────────────────


class TTSEngine:
    """
    Pre-synthesis TTS engine.

    The background thread continuously cooks phrases from the phrase pool
    ahead of time and parks them in a small ready buffer.

    CenterTextLayer calls poll_ready() once per frame:
      - If a sound is ready: playback starts immediately and the method
        returns (phrase, duration_ms) so the display can lock that phrase
        visible for the audio duration.
      - If nothing is ready yet: returns None, display runs normally.
    """

    _PREFETCH = 2  # number of phrases to keep pre-cooked

    def __init__(self, config: dict):
        self.config = config
        self._pool = PhrasePool(config)

        # Deque of (phrase: str, sound: pygame.Sound, duration_ms: float, subli_sound)
        self._ready: deque = deque()
        # Priority deque for one-shot agent prompts (checked first by poll_ready)
        self._prompt_ready: deque = deque()
        # Pre-synthesis buffer for HTW (Bible Ch.9 §9.1) — filled before the window opens
        self._presynth_ready: deque = deque()
        self._last_presynth_phrases: list = []
        self._lock = threading.Lock()

        self._ch_tts: Optional[pygame.mixer.Channel] = None
        self._ch_subli: Optional[pygame.mixer.Channel] = None

        # Cooldown: suppress regular affirmations for N seconds after an agent
        # prompt plays, so the plain voice doesn't cut in immediately after the
        # modded agent voice and kill the effect.
        self._prompt_cooldown_until: float = 0.0
        self._PROMPT_COOLDOWN_S: float = 4.0

        # Session tracking — flush pre-cooked queue on session change
        self._current_session_folder: str = config.get("session_folder", "")

        # Dedup: seed from existing agent_message so stale messages aren't
        # re-synthesized as "new" on startup.
        _existing_msg = config.get("agent_message") or {}
        self._last_agent_msg_ts: float = (
            float(_existing_msg.get("ts", 0) or 0)
            if isinstance(_existing_msg, dict)
            else 0.0
        )

        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="TTSEngine"
        )
        self._thread.start()

    # ── Public API ────────────────────────────────────────────────────────────

    def poll_ready(self, session_active: bool = True) -> Optional[tuple[str, float]]:
        """
        Non-blocking.  If a pre-synthesised sound is waiting, play whichever
        channels are enabled and return (phrase, duration_ms).

        Priority: one-shot agent prompts (_prompt_ready) are played before
        the regular affirmation pool (_ready).

        tts_enabled  — controls audible voice playback
        tts_subliminal — controls SSB ultrasonic playback; independent of
                         tts_enabled so silent-sub mode works without voice.
        """
        # Never interrupt a phrase mid-playback — let the channel drain first.
        # This is the guard that keeps the queue from clipping over itself.
        if self._ch_tts is not None and self._ch_tts.get_busy():
            return None
        if self._ch_subli is not None and self._ch_subli.get_busy():
            return None

        tts_on = self.config.get("tts_enabled", False)
        subli_on = self.config.get("tts_subliminal", False)

        # Check priority queue first (one-shot agent prompts).
        # These play regardless of tts_enabled — voice_mode gates them instead.
        import time as _time

        with self._lock:
            if self._prompt_ready:
                phrase, sound, dur_ms, subli_sound, voice_mode = (
                    self._prompt_ready.popleft()
                )
                self._ensure_channels()
                play_tts = voice_mode in ("tts", "both")
                play_subli = voice_mode in ("subliminal", "both")
                if play_tts and sound is not None:
                    tts_vol = self.config.get("tts_volume", 65) / 100.0
                    if tts_vol > 0.01:
                        self._ch_tts.set_volume(tts_vol)
                        self._ch_tts.play(sound)
                if play_subli and subli_sound is not None:
                    subli_vol = self.config.get("tts_subliminal_vol", 20) / 100.0
                    if subli_vol > 0.01:
                        self._ch_subli.set_volume(subli_vol)
                        self._ch_subli.play(subli_sound)
                # Suppress regular affirmations briefly so the plain voice
                # doesn't cut in right after the modded agent voice.
                if play_tts:
                    self._prompt_cooldown_until = (
                        _time.time() + (dur_ms / 1000.0) + self._PROMPT_COOLDOWN_S
                    )
                return (phrase, dur_ms)

        if not tts_on and not subli_on:
            return None

        # Don't drain the regular affirmation pool when no session is running —
        # agent prompts (above) still play, but background phrases should not.
        if not session_active:
            return None

        # Honour post-prompt cooldown: give the agent's modded voice room to land.
        if _time.time() < self._prompt_cooldown_until:
            return None

        # HTW pre-synthesis buffer (Bible Ch.9 §9.1): serve from _presynth_ready when active
        use_presynth = self.config.get("tts_use_presynth", False)
        with self._lock:
            if use_presynth and self._presynth_ready:
                phrase, sound, dur_ms, subli_sound = self._presynth_ready.popleft()
            elif not use_presynth and self._ready:
                phrase, sound, dur_ms, subli_sound = self._ready.popleft()
            else:
                return None

        self._ensure_channels()

        if tts_on:
            tts_vol = self.config.get("tts_volume", 65) / 100.0
            if tts_vol > 0.01:
                self._ch_tts.set_volume(tts_vol)
                self._ch_tts.play(sound)

        if subli_on and subli_sound is not None:
            subli_vol = self.config.get("tts_subliminal_vol", 20) / 100.0
            if subli_vol > 0.01:
                self._ch_subli.set_volume(subli_vol)
                self._ch_subli.play(subli_sound)

        return (phrase, dur_ms)

    def update_pool(self):
        """Call each frame so the internal phrase pool stays in sync with config."""
        self._pool.update(self.config)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _ensure_channels(self):
        if pygame.mixer.get_num_channels() < _MIN_CH:
            pygame.mixer.set_num_channels(_MIN_CH)
        if self._ch_tts is None:
            self._ch_tts = pygame.mixer.Channel(_CH_TTS)
        if self._ch_subli is None:
            self._ch_subli = pygame.mixer.Channel(_CH_SUBLI)

    def _build_backend(self, style: Optional[dict] = None) -> Optional[_Backend]:
        """Build a TTS backend, optionally overriding pitch/rate from *style*."""
        name = self.config.get("tts_backend", "edge").lower()
        if name == "edge":
            try:
                pitch = (style or {}).get("pitch", "+0Hz") or "+0Hz"
                rate = (style or {}).get("rate", "+0%") or "+0%"
                return _EdgeBackend(
                    voice=self.config.get("tts_voice", "en-US-JennyNeural"),
                    pitch=pitch,
                    rate=rate,
                )
            except ImportError:
                print("[TTS] edge-tts not installed. pip install edge-tts")
                return None
        api_key = self.config.get("tts_api_key", "none")
        voice = self.config.get("tts_voice", "nova")
        model = self.config.get("tts_model", "tts-1")
        base_url = (
            self.config.get("tts_api_url", "http://localhost:8020")
            if name == "local"
            else "https://api.openai.com/v1"
        )
        return _OpenAIBackend(
            api_key=api_key, voice=voice, model=model, base_url=base_url
        )

    @staticmethod
    def _load_sound(
        audio_bytes: bytes,
        beat_mod: bool = False,
        beat_hz: float = 8.0,
        reverb: bool = False,
        reverb_wet: float = 0.0,
        reverb_room_ms: int = 80,
        delay_ms: int = 0,
        delay_feedback: float = 0.0,
    ) -> Optional[pygame.mixer.Sound]:
        """
        Decode + resample to the exact pygame mixer format (44100 Hz stereo s16).
        Applies a 20 ms linear fade-in to eliminate the click at the start of
        each new line caused by an abrupt waveform discontinuity.

        Optional post-processing effects:
          beat_mod        - amplitude modulation at *beat_hz*
          reverb          - short echo layer for spacious quality (legacy)
          reverb_wet      - 0.0-1.0 reverb wet/dry mix (new FX chain)
          reverb_room_ms  - 20-500 reverb tail length in ms
          delay_ms        - 0-300 echo delay in ms
          delay_feedback  - 0.0-0.8 echo feedback gain
        """
        try:
            import miniaudio

            freq, _size, channels = pygame.mixer.get_init()
            decoded = miniaudio.decode(
                audio_bytes,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=channels,
                sample_rate=freq,
            )
            samples = np.frombuffer(decoded.samples, dtype=np.int16).copy()
            frames = len(samples) // channels
            s2d = samples.reshape(frames, channels)

            # 20 ms fade-in ramp to eliminate start-of-line click
            fade = min(int(freq * 0.020), frames)
            ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)[:, np.newaxis]
            s2d[:fade] = (s2d[:fade] * ramp).astype(np.int16)

            # ── Optional entrainment effects ──────────────────────────────────
            if beat_mod and beat_hz > 0:
                s2d = _apply_beat_mod(s2d, beat_hz, freq)
            if reverb:
                s2d = _apply_reverb(s2d, freq)
            if reverb_wet > 0.0 or delay_ms > 0:
                s2d = _apply_reverb_chain(
                    s2d,
                    freq,
                    reverb_wet=reverb_wet,
                    reverb_room_ms=reverb_room_ms,
                    delay_ms=delay_ms,
                    delay_feedback=delay_feedback,
                )

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(2)
                wf.setframerate(freq)
                wf.writeframes(s2d.reshape(-1).tobytes())
            buf.seek(0)
            return pygame.mixer.Sound(file=buf)
        except Exception as e:
            print(f"[TTS] Load/resample failed: {e}")
            return None

    def _handle_tts_prompt(self, text: str, style: dict) -> None:
        """Synthesise a one-shot agent prompt and queue it in _prompt_ready.

        Called from the worker thread when ``agent_message`` with ``"tts"`` in
        its ``via`` list is detected.  Style params (pitch, rate, beat_mod,
        reverb, voice_mode) come from the message's ``style`` dict.
        """
        voice_mode = style.get("voice_mode", "tts")
        if voice_mode == "silent":
            return  # visual-only prompt — no TTS needed

        try:
            backend = self._build_backend(style=style)
            if backend is None:
                return

            audio = backend.synthesize(text)
            if not audio:
                return

            beat_hz = float(self.config.get("beat_frequency", 8.0))
            sound = self._load_sound(
                audio,
                beat_mod=bool(style.get("beat_mod", False)),
                beat_hz=beat_hz,
                reverb=bool(style.get("reverb", False)),
                reverb_wet=float(style.get("reverb_wet", 0.0)),
                reverb_room_ms=int(style.get("reverb_room_ms", 80)),
                delay_ms=int(style.get("delay_ms", 0)),
                delay_feedback=float(style.get("delay_feedback", 0.0)),
            )
            if sound is None:
                return

            dur_ms = sound.get_length() * 1000.0

            # Subliminal version (always pre-process so toggle works at play time)
            carrier = float(self.config.get("tts_subliminal_hz", 16000))
            subli_bytes = _ssb_modulate(audio, carrier)
            subli_sound = self._load_sound(subli_bytes) if subli_bytes else None

            with self._lock:
                self._prompt_ready.append(
                    (text, sound, dur_ms, subli_sound, voice_mode)
                )

            pass

        except Exception as e:
            print(f"[TTS] Prompt synthesis error: {e}")

    def _worker(self):
        """Continuously pre-synthesise phrases into the ready buffer.

        Also monitors ``config["agent_message"]`` for one-shot agent TTS
        and processes them with priority into ``_prompt_ready``.
        """
        while True:
            # ── Check for unified agent_message ───────────────────────────
            agent_msg = self.config.get("agent_message") or {}
            if isinstance(agent_msg, dict) and agent_msg.get("text"):
                msg_ts = float(agent_msg.get("ts", 0) or 0)
                msg_text = agent_msg["text"]
                via = agent_msg.get("via", [])
                if ("tts" in via) and msg_ts != getattr(self, "_last_agent_msg_ts", 0):
                    self._last_agent_msg_ts = msg_ts
                    style = agent_msg.get("style") or {}
                    self._handle_tts_prompt(msg_text, style)

            # ── Flush stale phrases on session change ──────────────────────
            new_folder = self.config.get("session_folder", "")
            if new_folder != self._current_session_folder:
                self._current_session_folder = new_folder
                with self._lock:
                    self._ready.clear()

            # ── HTW pre-synthesis (Bible Ch.9 §9.1): fill _presynth_ready ──────────────
            presynth_phrases = self.config.get("tts_presynth_phrases") or []
            if isinstance(presynth_phrases, list) and presynth_phrases:
                if presynth_phrases != self._last_presynth_phrases:
                    # Phrase list changed — flush stale buffer
                    with self._lock:
                        self._presynth_ready.clear()
                    self._last_presynth_phrases = list(presynth_phrases)

                with self._lock:
                    already = {p for p, *_ in self._presynth_ready}
                    presynth_buffered = len(self._presynth_ready)

                if presynth_buffered < len(presynth_phrases):
                    next_phrase = next(
                        (p for p in presynth_phrases if p not in already),
                        None,
                    )
                    if next_phrase:
                        pool_style = self.config.get("tts_pool_style") or {}
                        ps_backend = self._build_backend(
                            style=pool_style if pool_style else None
                        )
                        if ps_backend is not None:
                            try:
                                audio = ps_backend.synthesize(next_phrase)
                                if audio:
                                    ps_fx = pool_style
                                    sound = self._load_sound(
                                        audio,
                                        reverb_wet=float(ps_fx.get("reverb_wet", 0.0)),
                                        reverb_room_ms=int(
                                            ps_fx.get("reverb_room_ms", 80)
                                        ),
                                        delay_ms=int(ps_fx.get("delay_ms", 0)),
                                        delay_feedback=float(
                                            ps_fx.get("delay_feedback", 0.0)
                                        ),
                                    )
                                    if sound is not None:
                                        dur_ms = sound.get_length() * 1000.0
                                        carrier = float(
                                            self.config.get("tts_subliminal_hz", 16000)
                                        )
                                        subli_bytes = _ssb_modulate(audio, carrier)
                                        subli_sound = (
                                            self._load_sound(subli_bytes)
                                            if subli_bytes
                                            else None
                                        )
                                        with self._lock:
                                            self._presynth_ready.append(
                                                (
                                                    next_phrase,
                                                    sound,
                                                    dur_ms,
                                                    subli_sound,
                                                )
                                            )
                            except Exception:
                                pass
                        time.sleep(0.15)
                        continue

            # ── Regular pool pre-fetch ─────────────────────────────────────
            tts_on = self.config.get("tts_enabled", False)
            subli_on = self.config.get("tts_subliminal", False)
            with self._lock:
                buffered = len(self._ready)

            if not (tts_on or subli_on) or buffered >= self._PREFETCH:
                time.sleep(0.15)
                continue

            pool_style = self.config.get("tts_pool_style") or {}
            backend = self._build_backend(style=pool_style if pool_style else None)
            if backend is None:
                time.sleep(2.0)
                continue

            self._pool.update(self.config)
            phrase = self._pool.pick()
            if not phrase:
                time.sleep(0.5)
                continue

            try:
                audio = backend.synthesize(phrase)
                if not audio:
                    continue

                ps_fx = self.config.get("tts_pool_style") or {}
                sound = self._load_sound(
                    audio,
                    reverb_wet=float(ps_fx.get("reverb_wet", 0.0)),
                    reverb_room_ms=int(ps_fx.get("reverb_room_ms", 80)),
                    delay_ms=int(ps_fx.get("delay_ms", 0)),
                    delay_feedback=float(ps_fx.get("delay_feedback", 0.0)),
                )
                if sound is None:
                    continue

                dur_ms = sound.get_length() * 1000.0

                # Always pre-process the subliminal so the toggle can be
                # flipped at any time without stale None entries in the queue.
                carrier = float(self.config.get("tts_subliminal_hz", 16000))
                subli_bytes = _ssb_modulate(audio, carrier)
                subli_sound = self._load_sound(subli_bytes) if subli_bytes else None

                with self._lock:
                    self._ready.append((phrase, sound, dur_ms, subli_sound))

            except Exception as e:
                print(f"[TTS] Synthesis error: {e}")
                time.sleep(1.0)
