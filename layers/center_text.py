import time
import pygame
import random
from layers.phrase_pool import PhrasePool
from layers.font_manager import FontManager
from eeg.delivery_gate import DeliveryGate


class CenterTextLayer:
    """Beat-synced flashing center text. Phrase pool is live — updates instantly
    when the timeline runner switches tag groups.

    When phase_gate_enabled is True in live_control.json, the flash timer is
    replaced by the DeliveryGate AND logic (Bible Ch.4 §4.6 §5): text fires only when
    alpha_at_trough AND respiratory_hot, falling back gracefully when EEG is
    unavailable. The legacy fixed duty cycle is always the fallback floor.
    """

    def __init__(self, config: dict, tts_engine=None):
        self.config = config
        self.pool = PhrasePool(config)
        self.current = self.pool.pick()
        self.timer = 0
        self.visible = True
        self.font_mgr = FontManager(config)
        self._tts = tts_engine

        # Phase-cascade delivery gate (Bible Ch.4 §4.6). Created once; reads config live.
        self._delivery_gate = DeliveryGate()
        self._gate_diag_interval_s = 5.0  # write diagnostics to config every 5 s
        self._gate_diag_last_t = 0.0

        # Semantic cascade 200ms delay (Bible Ch.6 §6.6 §4 — Shadows must precede CenterText)
        # When a semantic cascade fires: shadow prime is set immediately; the center
        # phrase is held for _CASCADE_DELAY_MS before flashing (Delavari et al. 2025).
        self._CASCADE_DELAY_MS = 200
        self._cascade_pending_ms: float = 0.0  # countdown to cascade flash
        self._cascade_phrase: str = ""  # center phrase to show when ready

        # When TTS is playing, we lock the display on that phrase for the
        # duration of the audio clip instead of running the normal flash timer.
        self._tts_lock_ms = 0.0  # ms remaining in current TTS voice lock
        # Dedup timestamp: last tts_playing_ts we acted on (panel-owned TTS path)
        self._last_tts_ts: float = 0.0

        self._cached_surf = None
        self._cache_key = None

    def _switch_font(self):
        pass

    def _calculate_times(self, beat_freq: float):
        sync = self.config.get("center_flash_sync_to_beat", True)
        if sync and beat_freq > 0.1:
            cycle_ms = 1000.0 / beat_freq
            duty = self.config.get("flash_duty_cycle", 0.38)
            var = self.config.get("flash_variance", 0.22)
            jitter = random.uniform(-var, var)
            on_time = cycle_ms * duty * (1 + jitter)
            off_time = cycle_ms * (1 - duty) * (1 - jitter)
            # Floor clamp keeps center text supraliminal at high beat frequencies
            on_floor = int(self.config.get("center_flash_on_floor_ms", 60))
            return max(on_floor, int(on_time)), max(10, int(off_time))
        return (
            self.config.get("center_flash_on_time", 120),
            self.config.get("center_flash_off_time", 80),
        )

    def update(self, dt: float, current_beat_freq: float):
        self.pool.update(self.config)

        if self._tts is not None:
            self._tts.update_pool()

        # ── Semantic cascade 200ms delay countdown (Bible Ch.6 §6.6 §4) ───────────────
        # Shadows prime fires at t=0 (set in config); CenterText fires at t+200ms.
        if self._cascade_pending_ms > 0:
            self._cascade_pending_ms -= dt * 1000
            if self._cascade_pending_ms <= 0:
                self._cascade_pending_ms = 0.0
                self._trigger_flash(phrase=self._cascade_phrase or None)
                self._cascade_phrase = ""

        # ── TTS voice-lock mode ───────────────────────────────────────────────
        # While a voice line is playing we hold the phrase visible for the full
        # audio duration, ignoring the normal flash timer entirely.
        if self._tts_lock_ms > 0:
            self._tts_lock_ms -= dt * 1000
            if self._tts_lock_ms <= 0:
                self.visible = False
                self.timer = 0
                self._cached_surf = None
            return

        # ── Poll TTS for next ready phrase ────────────────────────────────────
        # Only poll when we're between phrases (invisible / off period), so we
        # don't interrupt a phrase that's already being shown.
        if not self.visible:
            if self._tts is not None:
                # In-process TTSEngine (legacy path, used when engine is local)
                result = self._tts.poll_ready()
                if result is not None:
                    phrase, dur_ms = result
                    self.current = phrase
                    self.visible = True
                    self._tts_lock_ms = dur_ms
                    self._cached_surf = None
                    self._switch_font()
                    self._advance_seq_cursor()
                    return
            else:
                # Control-panel-owned TTS: sync via tts_playing in live_control.json
                phrase = self.config.get("tts_playing")
                ts = float(self.config.get("tts_playing_ts", 0) or 0)
                dur_ms = float(self.config.get("tts_playing_ms", 0) or 0)
                if phrase and dur_ms > 0 and ts > self._last_tts_ts:
                    self._last_tts_ts = ts
                    self.current = phrase
                    self.visible = True
                    self._tts_lock_ms = dur_ms
                    self._cached_surf = None
                    self._switch_font()
                    self._advance_seq_cursor()
                    return

        # ── Flash timer / phase-gated delivery ───────────────────────────────
        # When phase_gate_enabled is true, the DeliveryGate decides the "off→on"
        # transition. The "on→off" (visibility expiry) still uses the legacy on_time
        # so flash duration is preserved — gating only controls when a new phrase fires.
        on_time, off_time = self._calculate_times(current_beat_freq)
        self.timer += dt * 1000

        if self.visible:
            # Always expire visibility using the legacy on-time duration
            if self.timer > on_time:
                self.visible = False
                self.timer = 0
                self._cached_surf = None
        else:
            # Beat-phase locked firing: when center_flash_sync_to_beat is on,
            # wait for beat_phase to cross 0 (downbeat) before firing. This
            # locks the text flash to the binaural beat rhythm precisely.
            beat_phase = float(self.config.get("beat_phase", 0.0) or 0.0)
            sync = self.config.get("center_flash_sync_to_beat", True)
            on_downbeat = (not sync) or beat_phase < 0.05

            gate_result = self._delivery_gate.should_fire(self.config)
            if gate_result["mode"] == "disabled":
                # Legacy path: fixed off-time duration + beat sync
                if self.timer > off_time and on_downbeat:
                    self._trigger_flash()
            elif gate_result["fire"] and self._cascade_pending_ms <= 0 and on_downbeat:
                # Phase-gated path: fire when gate opens (or timeout fallback)
                self.timer = 0
                self.config["phase_gate_last_reason"] = gate_result["reason"]
                self.config["phase_gate_mode"] = gate_result["mode"]

                # ── Semantic cascade path (Bible Ch.6 §6.6) ────────────────────────────
                # When semantic_selector_enabled, prime Shadows immediately and
                # defer CenterText by CASCADE_DELAY_MS (≥200ms per Delavari 2025).
                cascade = self.config.get("semantic_cascade")
                if (
                    self.config.get("semantic_selector_enabled", False)
                    and isinstance(cascade, dict)
                    and cascade.get("center_phrase")
                ):
                    # t=0: inject shadow prime (ShadowsLayer reads on next refresh)
                    self.config["_shadow_prime_word"] = cascade["shadow_word"]
                    self.config["_shadow_prime_pending"] = True
                    # Queue voice phrase for agent/TTS to pick up
                    if cascade.get("voice_phrase"):
                        self.config["semantic_voice_phrase"] = cascade["voice_phrase"]
                    # t+200ms: CenterText fires with cascade center_phrase
                    self._cascade_phrase = cascade["center_phrase"]
                    self._cascade_pending_ms = float(self._CASCADE_DELAY_MS)
                else:
                    # Standard (non-semantic) phase-gated flash
                    self._trigger_flash()

                # Periodically write rolling diagnostics
                now_t = time.monotonic()
                if now_t - self._gate_diag_last_t > self._gate_diag_interval_s:
                    self._gate_diag_last_t = now_t
                    diag = self._delivery_gate.diagnostics_dict()
                    self.config.update(diag)

    def _trigger_flash(self, phrase: str | None = None):
        """Transition to visible state with a new phrase.

        phrase — when provided (semantic cascade path), skips pool.pick().
                 When None, draws from the phrase pool as usual.
        """
        self.visible = True
        self.timer = 0
        self.current = phrase if phrase else self.pool.pick()
        if self.config.get("font_switch_mode", "intelligent") == "intelligent":
            self._switch_font()
        # Signal spiral layer to produce a convergence pulse (Bible Ch.4 §4.6 §9.2)
        if self.config.get("spiral_phase_pulse", False):
            self.config["_spiral_pulse_pending"] = True
        self._cached_surf = None

    def _advance_seq_cursor(self):
        """Advance the pool's sequential cursor to keep pace with TTS.

        When TTS voice-lock activates, center_text displays the TTS phrase
        but never calls pool.pick() for it — so the sequential cursor stays
        frozen. This method silently advances the cursor by one position so
        that any inter-TTS gap flashes the next phrase in sequence rather
        than rewinding to the beginning.
        """
        if self.pool._seq_mode and self.pool._pool:
            self.pool.pick()

    def _color(self):
        c = self.config.get("text_color", [255, 105, 180])
        return (int(c[0]), int(c[1]), int(c[2]))

    @staticmethod
    def _wrap(text: str, font: pygame.font.Font, max_w: int) -> list[str]:
        """Break text into lines that each fit within max_w pixels."""
        words = text.split()
        lines, current = [], []
        for word in words:
            test = " ".join(current + [word])
            if font.size(test)[0] <= max_w:
                current.append(word)
            else:
                if current:
                    lines.append(" ".join(current))
                current = [word]
        if current:
            lines.append(" ".join(current))
        return lines or [text]

    def get_surface(self):
        if not self.visible:
            if self._cached_surf is None or self._cache_key != ("hidden",):
                s = pygame.Surface((1, 1), pygame.SRCALPHA)
                s.set_alpha(0)
                self._cached_surf = s
                self._cache_key = ("hidden",)
            return self._cached_surf

        color = self._color()
        screen = pygame.display.get_surface()
        max_w = int(screen.get_width() * 0.88)
        key = (self.current, self.font_mgr.current_font, color, max_w)

        if self._cached_surf is None or self._cache_key != key:
            font = self.font_mgr.get_font(140)

            lines = self._wrap(self.current.upper(), font, max_w)

            if len(lines) == 1:
                self._cached_surf = font.render(lines[0], True, color)
            else:
                line_surfs = [font.render(ln, True, color) for ln in lines]
                gap = 12
                total_h = sum(s.get_height() for s in line_surfs) + gap * (
                    len(line_surfs) - 1
                )
                total_w = max(s.get_width() for s in line_surfs)
                surf = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
                y = 0
                for ls in line_surfs:
                    surf.blit(ls, ((total_w - ls.get_width()) // 2, y))
                    y += ls.get_height() + gap
                self._cached_surf = surf

            self._cache_key = key

        return self._cached_surf
