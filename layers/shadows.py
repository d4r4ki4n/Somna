import math
import time
import pygame
import random
from layers.font_manager import FontManager
from layers.phrase_pool import PhrasePool


class ShadowsLayer:
    """Truly subliminal — fixed short timings, random placement + drift.

    Each shadow position carries its own phrase so the viewer's peripheral
    field is covered with varied content rather than one repeated word.
    Font size scales with screen height for consistent perceived size across
    resolutions.  Drift wraps on all four edges.
    """

    # Base font size at 1080p; scales linearly with screen height
    _BASE_SIZE = 88
    _BASE_H    = 1080

    def __init__(self, config: dict):
        self.config   = config
        self.font_mgr = FontManager(config)
        self.pool     = PhrasePool(config)

        self.count    = int(config.get("shadow_count", 9))  # single words are compact; more positions fill the field
        self.opacity  = config.get("shadow_opacity", 25)
        # Key spec: Bible Ch.10 §10.2 §6 — shadows_display_ms / shadows_mask_isi_ms.
        # Fall back to legacy shadow_flash_on_time / shadow_flash_off_time.
        self.on_time  = config.get("shadows_display_ms",
                        config.get("shadow_flash_on_time",   33))
        self.off_time = config.get("shadows_mask_isi_ms",
                        config.get("shadow_flash_off_time",  167))
        self.timer    = 0
        self.visible  = True
        # Bible Ch.10 §10.2 §6 — display mode: "continuous" or "phase_locked"
        # phase_locked: only flash during aligned beat-phase window (first 15% of cycle)
        self._display_mode = config.get("shadows_display_mode", "continuous")
        self._phase_accum  = 0.0   # tracks beat phase for phase_locked gating

        # Per-position state: phrase, position, drift velocity
        self.phrases   = []
        self.positions = []
        self.drifts    = []
        self._font_size = self._BASE_SIZE
        self._init_positions()

    # ------------------------------------------------------------------
    def _screen(self):
        return pygame.display.get_surface().get_size()

    def _scaled_font_size(self) -> int:
        _, h = self._screen()
        return max(36, int(self._BASE_SIZE * h / self._BASE_H))

    def _spread_positions(self, w: int, h: int, phrases: list[str]) -> list[list[float]]:
        """Place phrases on a shuffled grid so no two start on top of each other."""
        excl   = float(self.config.get("shadow_exclusion_pct", 0.27))
        count  = len(phrases)
        cols   = max(1, round(math.sqrt(count * w / h)))
        rows   = max(1, math.ceil(count / cols))
        cw, ch = w / cols, h / rows
        cells  = [(c, r) for r in range(rows) for c in range(cols)]
        random.shuffle(cells)
        cx, cy  = w / 2, h / 2
        margin  = self._font_size
        result  = []
        for idx, phrase in enumerate(phrases):
            approx_w = len(phrase) * int(self._font_size * 0.6)
            if idx < len(cells):
                cc, cr = cells[idx]
                x = cc * cw + random.uniform(margin, max(margin + 1, cw - margin))
                y = cr * ch + random.uniform(margin * 0.5, max(margin + 1, ch - margin * 0.5))
            else:
                x = random.uniform(60, w - approx_w - 20)
                y = random.uniform(60, h - self._font_size - 20)
            # Clamp to screen
            x = max(20, min(w - approx_w - 20, x))
            y = max(20, min(h - self._font_size - 20, y))
            # Nudge away from dead-centre (configurable exclusion zone)
            if abs(x - cx) < w * excl and abs(y - cy) < h * excl:
                x += w * (excl + 0.05) if x < cx else -w * (excl + 0.05)
                x = max(20, min(w - approx_w - 20, x))
            result.append([float(x), float(y)])
        return result

    def _init_positions(self):
        w, h = self._screen()
        self.phrases   = [self.pool.pick_shadow() for _ in range(self.count)]
        self._font_size = self._scaled_font_size()
        self.positions = self._spread_positions(w, h, self.phrases)
        self.drifts    = [
            (random.uniform(-0.35, 0.35), random.uniform(-0.25, 0.25))
            for _ in range(self.count)
        ]

    def _refresh_phrases(self):
        """Give every position a fresh single word and a spread-out location.

        Draws from pick_shadow() which enforces the Chien et al. single-word
        constraint: subliminal priming only works for direct semantic associates,
        not multi-word phrases. If a semantic cascade prime is pending (Bible Ch.6 §6.6),
        one slot is replaced with the semantically selected word.
        """
        w, h = self._screen()
        self._font_size  = self._scaled_font_size()
        self.phrases     = [self.pool.pick_shadow() for _ in range(self.count)]

        # Inject semantic shadow prime if pending (Bible Ch.6 §6.6): replace one slot
        prime = self.config.get("_shadow_prime_word")
        if prime and self.config.get("_shadow_prime_pending"):
            inject_idx = random.randrange(len(self.phrases)) if self.phrases else 0
            if self.phrases:
                self.phrases[inject_idx] = prime
            self.config["_shadow_prime_pending"] = False

        self.positions   = self._spread_positions(w, h, self.phrases)
        self.drifts      = [
            (random.uniform(-0.35, 0.35), random.uniform(-0.25, 0.25))
            for _ in range(self.count)
        ]

    # ------------------------------------------------------------------
    def update(self, dt: float):
        # Agent-controlled keys take precedence over slider values
        self.opacity  = self.config.get("shadow_opacity_target",
                        self.config.get("shadow_opacity",                12))
        # Spec keys (Bible Ch.10 §10.2 §6) preferred; legacy keys as fallback
        self.on_time  = self.config.get("shadows_display_ms",
                        self.config.get("shadow_flash_on_ms",
                        self.config.get("shadow_flash_on_time",          33)))
        self.off_time = self.config.get("shadows_mask_isi_ms",
                        self.config.get("shadow_flash_off_ms",
                        self.config.get("shadow_flash_off_time",        167)))
        self._display_mode = self.config.get("shadows_display_mode", "continuous")

        # Respect agent-controlled phrase count (reinit positions if count changes)
        new_count = int(self.config.get("shadow_count_target",
                        self.config.get("shadow_count",                   6)))
        if new_count != self.count:
            self.count = new_count
            self._init_positions()

        self.pool.update(self.config)

        # ── Phase-locked mode: track beat phase accumulator ───────────────
        # Show the flash only when the beat phase is in the first 15% of a
        # cycle (the "onset window"), matching the temporal binding window
        # from Bible Ch.10 §10.2 §4.3.  The beat_phase key is written by audio_engine.
        if self._display_mode == "phase_locked":
            beat_hz   = max(0.1, float(self.config.get("beat_frequency", 10.0) or 10.0))
            beat_phase = float(self.config.get("beat_phase", 0.0) or 0.0)
            # gate: allow flash only in phase 0.0–0.15 of a beat cycle
            in_window = beat_phase < 0.15
            # If we're transitioning into the window, start the flash
            if in_window and not self.visible:
                self.visible = True
                self.timer   = 0
                self._refresh_phrases()
            elif not in_window and self.visible and self.timer > self.on_time:
                self.visible = False
                self.timer   = 0
            self.timer += dt * 1000
        else:
            # Continuous mode: simple timer-driven on/off
            self.timer += dt * 1000
            threshold = self.on_time if self.visible else self.off_time
            if self.timer > threshold:
                self.visible = not self.visible
                self.timer   = 0
                if not self.visible:
                    self._refresh_phrases()

        # Drift with full-edge wrapping
        w, h = self._screen()
        for i in range(self.count):
            self.positions[i][0] += self.drifts[i][0] * dt * 30
            self.positions[i][1] += self.drifts[i][1] * dt * 30
            x, y = self.positions[i]
            if x < -300:  self.positions[i][0] = float(w + 50)
            if x > w + 300: self.positions[i][0] = -50.0
            if y < -120:  self.positions[i][1] = float(h + 30)
            if y > h + 120: self.positions[i][1] = -30.0

    # ------------------------------------------------------------------
    def _color(self):
        c = self.config.get("text_color", [255, 105, 180])
        return (int(c[0]), int(c[1]), int(c[2]))

    def draw(self, surface: pygame.Surface):
        if not self.visible:
            return

        alpha  = int(self.opacity * 2.55)
        color  = self._color()
        size   = self._scaled_font_size()

        # Reuse a single font object for all phrases this frame
        font = self.font_mgr.get_font(size)

        for i, phrase in enumerate(self.phrases):
            surf = font.render(phrase.upper(), True, color)
            surf.set_alpha(alpha)
            surface.blit(surf, (int(self.positions[i][0]),
                                int(self.positions[i][1])))
