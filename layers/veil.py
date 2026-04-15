"""
veil.py
Somna — Veil affirmation layer

Seven animation modes, randomly selected and periodically changed.
Mode can also be set via config["veil_mode"] for LLM/session control.

Modes:
  scroll    — dense block scrolling in a randomized direction
  rain      — phrases fall in independent vertical columns at varying speeds
  drift     — individual phrases float with independent velocities, fade in/out
  converge  — phrases flow inward from all edges toward center
  strobe    — single large phrase flashes supraliminal center (follows flash timing)
  mirror    — scroll but every other tile is horizontally flipped (symmetry wall)
  tunnel    — phrases spawn small at center, scale up as they rush toward the viewer
"""

import pygame
import random
import math
from collections import OrderedDict
from layers.font_manager import FontManager
from layers.phrase_pool import PhrasePool


# How long before the veil picks a new random mode/direction (seconds)
_MODE_CHANGE_MIN = 30.0
_MODE_CHANGE_MAX = 90.0

# Max distinct (text, size, color) triples to keep in the render cache.
# At ~15 unique phrases × 4 sizes × 1 colour = ~60 entries typical.
_RENDER_CACHE_MAX = 256

_MODES = ["scroll", "rain", "drift", "converge", "strobe", "tunnel"]

# Quantized sizes for tunnel mode perspective scaling.
# Snapping to these values keeps the render cache viable (avoids per-frame misses).
_TUNNEL_SIZES = [10, 13, 17, 22, 28, 36, 46, 60, 78, 100, 130, 164]


class _DriftPhrase:
    """A single floating phrase for drift mode."""
    __slots__ = ("text", "x", "y", "vx", "vy", "alpha", "fade_dir",
                 "font_path", "size")

    def __init__(self, text, x, y, vx, vy, font_path, size):
        self.text      = text
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = vx, vy
        self.alpha     = 0.0
        self.fade_dir  = 1   # 1=fading in, -1=fading out
        self.font_path = font_path
        self.size      = size


class VeilLayer:
    """Dense affirmation veil with multiple animated display modes."""

    def __init__(self, config: dict):
        self.config   = config
        self.font_mgr = FontManager(config)
        self.pool     = PhrasePool(config)

        self.opacity_base = config.get("veil_opacity", 45)
        self.density      = config.get("veil_density", 1.3)

        self._w = pygame.display.get_surface().get_width()
        self._h = pygame.display.get_surface().get_height()

        # Mode state
        self._mode        = None   # set by _pick_mode()
        self._mode_timer  = 0.0
        self._mode_change = random.uniform(_MODE_CHANGE_MIN, _MODE_CHANGE_MAX)
        self._last_color  = None   # for scroll surface rebuild on color change

        # Scroll mode state
        self._scroll_surface = None
        self._scroll_x       = 0.0
        self._scroll_y       = 0.0
        self._scroll_vx      = 0.0
        self._scroll_vy      = 0.0

        # Rain mode state — list of (x, y, speed, phrase, alpha) per column
        self._rain_cols: list = []

        # Drift mode state
        self._drift_phrases: list = []

        # Converge mode state — same structure as rain but with direction vectors
        self._converge_phrases: list = []

        # Strobe mode state
        self._strobe_phrase:  str   = "..."
        self._strobe_visible: bool  = False
        self._strobe_timer:   float = 0.0
        self._strobe_surf:    object = None  # cached rendered surface

        # Tunnel mode state — list of phrase dicts with depth/angle/spread
        self._tunnel_phrases: list = []

        # Rendered-surface cache: (text_upper, size, color_rgb) -> pygame.Surface
        # Keyed so cache is automatically busted when color or font changes.
        self._render_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self._cache_font_key = self.font_mgr.current_font

        self._pick_mode(force=True)

    # ── Mode selection ────────────────────────────────────────────────────────

    def _pick_mode(self, force: bool = False):
        # Respect config override (exclude strobe/mirror from random rotation
        # so they only appear when explicitly requested — they're strong effects)
        cfg_mode = self.config.get("veil_mode")
        if cfg_mode and cfg_mode in _MODES:
            new_mode = cfg_mode
        else:
            # strobe, mirror, tunnel only appear when explicitly requested —
            # they're strong effects that don't suit random rotation
            new_mode = random.choice(["scroll", "rain", "drift", "converge", "tunnel"])

        if force or new_mode != self._mode:
            self._mode = new_mode
            self._mode_timer = 0.0
            self._mode_change = random.uniform(_MODE_CHANGE_MIN, _MODE_CHANGE_MAX)
            self._init_mode()

    def _init_mode(self):
        w, h = self._w, self._h
        if self._mode == "scroll":
            self._init_scroll()
        elif self._mode == "rain":
            self._init_rain(w, h)
        elif self._mode == "drift":
            self._init_drift(w, h)
        elif self._mode == "converge":
            self._init_converge(w, h)
        elif self._mode == "strobe":
            self._init_strobe()
        elif self._mode == "mirror":
            self._init_mirror()
        elif self._mode == "tunnel":
            self._init_tunnel(w, h)

    # ── Scroll mode ───────────────────────────────────────────────────────────

    def _text_color(self):
        c = self.config.get("text_color", [255, 105, 180])
        return (int(c[0]), int(c[1]), int(c[2]))

    def _init_scroll(self):
        """Build the tiled scroll surface in one of several dense layout patterns."""
        w, h = self._w * 2, self._h * 2
        self._scroll_surface = pygame.Surface((w, h), pygame.SRCALPHA)
        lines = self.pool.phrases or ["..."]
        color = self._text_color()
        self._last_color = color

        # Pick direction and pattern together so cardinal directions are always
        # paired with layouts whose per-row/column offsets prevent phrase smearing.
        cardinal_h = [(1.0, 0.0), (-1.0, 0.0)]
        cardinal_v = [(0.0, 1.0), (0.0, -1.0)]
        diagonals  = [
            (0.8,  0.8), (-0.8, 0.8), (0.8, -0.8), (-0.8, -0.8),
            (0.4,  1.0), (1.0,  0.4), (-0.4, 1.0), (1.0, -0.4),
            (0.4, -1.0), (-1.0, 0.4),
        ]
        direction_type = random.choice(["horizontal", "vertical", "diagonal"])
        if direction_type == "horizontal":
            _dir    = random.choice(cardinal_h)
            pattern = random.choice(["stagger", "scatter"])
        elif direction_type == "vertical":
            _dir    = random.choice(cardinal_v)
            pattern = random.choice(["columns", "scatter"])
        else:
            _dir    = random.choice(diagonals)
            pattern = random.choice(["rows", "columns", "diagonal", "scatter", "stagger"])

        if pattern == "rows":
            # Dense horizontal rows — phrases repeat across each row, rows fill height
            font_sz = random.choice([36, 44, 52])
            font    = self.font_mgr.get_font(font_sz)
            row_gap = int(font_sz * 1.6)
            col_gap = 40
            y = 0
            phrase_idx = 0
            while y < h:
                x = random.randint(-60, 0)
                while x < w:
                    phrase = lines[phrase_idx % len(lines)]
                    txt = font.render(phrase.upper(), True, color)
                    self._scroll_surface.blit(txt, (x, y))
                    x += txt.get_width() + col_gap
                    phrase_idx += 1
                y += row_gap

        elif pattern == "columns":
            # Multiple independent vertical columns of text
            font_sz   = random.choice([32, 40, 48])
            font      = self.font_mgr.get_font(font_sz)
            col_width = int(font_sz * 10)
            row_gap   = int(font_sz * 1.8)
            phrase_idx = 0
            col_x = 0
            while col_x < w:
                y = random.randint(-row_gap * 2, 0)
                while y < h:
                    phrase = lines[phrase_idx % len(lines)]
                    txt = font.render(phrase.upper(), True, color)
                    self._scroll_surface.blit(txt, (col_x, y))
                    y += row_gap
                    phrase_idx += 1
                col_x += col_width

        elif pattern == "diagonal":
            # Phrases along parallel diagonal bands
            font_sz  = random.choice([40, 52, 60])
            font     = self.font_mgr.get_font(font_sz)
            step_x   = int(font_sz * 7)
            step_y   = int(font_sz * 1.8)
            phrase_idx = 0
            y = -step_y
            while y < h + step_y:
                x = -step_x + int((y / step_y) * step_x * 0.6)
                while x < w + step_x:
                    phrase = lines[phrase_idx % len(lines)]
                    txt = font.render(phrase.upper(), True, color)
                    self._scroll_surface.blit(txt, (x % w, y % h))
                    x += step_x
                    phrase_idx += 1
                y += step_y

        elif pattern == "scatter":
            # Randomly scattered phrases at varying sizes — higher density than before
            phrase_idx = 0
            count = int(self.density * max(40, len(lines) * 4))
            for _ in range(count):
                font_sz = random.choice([28, 36, 44, 52])
                font    = self.font_mgr.get_font(font_sz)
                phrase  = lines[phrase_idx % len(lines)]
                txt     = font.render(phrase.upper(), True, color)
                x = random.randint(0, max(1, w - txt.get_width()))
                y = random.randint(0, max(1, h - txt.get_height()))
                self._scroll_surface.blit(txt, (x, y))
                phrase_idx += 1

        else:  # stagger — alternating rows offset by half the line width
            font_sz = random.choice([36, 44, 52])
            font    = self.font_mgr.get_font(font_sz)
            row_gap = int(font_sz * 1.7)
            col_gap = 36
            y       = 0
            row_n   = 0
            phrase_idx = 0
            while y < h:
                x_start = (col_gap * 3 // 2) if (row_n % 2 == 1) else 0
                x = x_start
                while x < w + col_gap:
                    phrase = lines[phrase_idx % len(lines)]
                    txt = font.render(phrase.upper(), True, color)
                    self._scroll_surface.blit(txt, (x % w, y))
                    x += txt.get_width() + col_gap
                    phrase_idx += 1
                y += row_gap
                row_n += 1

        self._scroll_x = 0.0
        self._scroll_y = 0.0

        dx, dy = _dir
        speed  = random.uniform(0.5, 1.6)
        self._scroll_vx = dx * speed
        self._scroll_vy = dy * speed

    def _update_scroll(self, dt: float, beat_freq: float):
        self.opacity_base = self.config.get("veil_opacity", 45)
        sw = self._scroll_surface.get_width()
        sh = self._scroll_surface.get_height()
        self._scroll_x = (self._scroll_x + self._scroll_vx * dt * 60) % sw
        self._scroll_y = (self._scroll_y + self._scroll_vy * dt * 60) % sh

    def _draw_scroll(self, surface: pygame.Surface, beat_freq: float):
        if not self._scroll_surface:
            return
        pulse = self._beat_pulse(beat_freq)
        alpha = int(self.opacity_base * (1 + pulse) * 2.55)
        # set_alpha() on the surface directly — no copy needed
        self._scroll_surface.set_alpha(max(20, min(255, alpha)))
        sw, sh = self._scroll_surface.get_size()
        sx, sy = int(-self._scroll_x), int(-self._scroll_y)
        for ox in (0, sw):
            for oy in (0, sh):
                surface.blit(self._scroll_surface, (sx + ox, sy + oy))

    # ── Rain mode ─────────────────────────────────────────────────────────────

    def _init_rain(self, w: int, h: int):
        col_w   = 220
        n_cols  = max(1, w // col_w)
        self._rain_cols = []
        for i in range(n_cols):
            x = i * col_w + random.randint(0, col_w - 1)
            self._rain_cols.append({
                "x":       float(x),
                "y":       float(random.randint(-h, 0)),
                "speed":   random.uniform(80, 260),
                "phrase":  self.pool.pick(),
                "alpha":   random.randint(30, 120),
                "size":    random.choice([48, 56, 64, 72]),
            })

    def _update_rain(self, dt: float):
        h = self._h
        for col in self._rain_cols:
            col["y"] += col["speed"] * dt
            if col["y"] > h + 80:
                col["y"]    = random.randint(-200, -40)
                col["phrase"] = self.pool.pick()
                col["speed"] = random.uniform(80, 260)
                col["alpha"] = random.randint(30, 120)

    def _draw_rain(self, surface: pygame.Surface, beat_freq: float):
        pulse        = self._beat_pulse(beat_freq)
        opacity_mult = self.opacity_base / 50.0 * (1 + pulse)
        color = self._text_color()
        for col in self._rain_cols:
            surf = self._render_cached(col["phrase"], col["size"], color)
            a    = int(min(255, col["alpha"] * opacity_mult * 2.55))
            surf.set_alpha(a)
            surface.blit(surf, (int(col["x"]), int(col["y"])))

    # ── Drift mode ────────────────────────────────────────────────────────────

    def _init_drift(self, w: int, h: int):
        count = int(self.density * 4)
        self._drift_phrases = []
        font_pool = self.font_mgr.config.get("_font_pool", [None])
        for _ in range(count):
            speed  = random.uniform(10, 80)
            angle  = random.uniform(0, math.tau)
            phrase = _DriftPhrase(
                text      = self.pool.pick(),
                x         = random.randint(0, w),
                y         = random.randint(0, h),
                vx        = math.cos(angle) * speed,
                vy        = math.sin(angle) * speed,
                font_path = None,
                size      = random.choice([52, 64, 76, 90]),
            )
            phrase.alpha = random.uniform(0, 100)
            self._drift_phrases.append(phrase)

    def _update_drift(self, dt: float):
        w, h = self._w, self._h
        for p in self._drift_phrases:
            p.x += p.vx * dt
            p.y += p.vy * dt
            # Fade in/out
            p.alpha += p.fade_dir * dt * random.uniform(20, 50)
            if p.alpha >= 120:
                p.fade_dir = -1
                p.alpha    = 120.0
            elif p.alpha <= 0:
                p.fade_dir = 1
                p.alpha    = 0.0
                p.text     = self.pool.pick()
                p.x        = random.randint(0, w)
                p.y        = random.randint(0, h)
                angle      = random.uniform(0, math.tau)
                speed      = random.uniform(10, 80)
                p.vx       = math.cos(angle) * speed
                p.vy       = math.sin(angle) * speed
            # Soft wrap
            if p.x < -200: p.x = w + 50
            if p.x > w + 200: p.x = -50
            if p.y < -100: p.y = h + 30
            if p.y > h + 100: p.y = -30

    def _draw_drift(self, surface: pygame.Surface, beat_freq: float):
        pulse        = self._beat_pulse(beat_freq)
        opacity_mult = self.opacity_base / 50.0 * (1 + pulse)
        color = self._text_color()
        for p in self._drift_phrases:
            surf = self._render_cached(p.text, p.size, color)
            a    = int(min(255, p.alpha * opacity_mult * 2.55))
            surf.set_alpha(a)
            surface.blit(surf, (int(p.x), int(p.y)))

    # ── Converge mode ─────────────────────────────────────────────────────────

    # Snap sizes for render-cache efficiency.
    _CONVERGE_SIZES = [24, 30, 38, 48, 60, 72, 84]

    def _converge_spawn(self, w, h, cx, cy, progress=None):
        """Return a fresh converge-phrase dict. progress=None → random stagger."""
        edge = random.randint(0, 3)
        if edge == 0:   ox, oy = random.randint(0, w), -60
        elif edge == 1: ox, oy = random.randint(0, w), h + 60
        elif edge == 2: ox, oy = -60, random.randint(0, h)
        else:           ox, oy = w + 60, random.randint(0, h)
        t = random.uniform(0.0, 0.95) if progress is None else progress
        x = ox + (cx - ox) * t
        y = oy + (cy - oy) * t
        dx = cx - x; dy = cy - y
        dist = math.sqrt(dx*dx + dy*dy) or 1
        speed = random.uniform(50, 120)
        return {
            "text":         self.pool.pick(),
            "x": float(x), "y": float(y),
            "vx": dx / dist * speed,
            "vy": dy / dist * speed,
            "alpha":        random.randint(50, 140),
            "size_at_edge": random.choice([64, 72, 84]),
        }

    def _init_converge(self, w: int, h: int):
        count = max(4, int(self.density * 4))
        cx, cy = w / 2, h / 2
        self._converge_phrases = [
            self._converge_spawn(w, h, cx, cy) for _ in range(count)
        ]

    def _update_converge(self, dt: float):
        w, h = self._w, self._h
        cx, cy = w / 2, h / 2
        for p in self._converge_phrases:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            # Crossed center: dot product flips sign
            dx = cx - p["x"]; dy = cy - p["y"]
            if p["vx"] * dx + p["vy"] * dy < 0:
                p.update(self._converge_spawn(w, h, cx, cy, progress=0.0))

    def _draw_converge(self, surface: pygame.Surface, beat_freq: float):
        pulse        = self._beat_pulse(beat_freq)
        opacity_mult = self.opacity_base / 50.0 * (1 + pulse)
        color = self._text_color()
        cx, cy = self._w / 2, self._h / 2
        max_dist = math.sqrt(cx * cx + cy * cy)

        for p in self._converge_phrases:
            dist_to_c = math.sqrt((p["x"] - cx) ** 2 + (p["y"] - cy) ** 2)
            # Size shrinks from size_at_edge (far) to ~30% (near center)
            scale    = 0.30 + 0.70 * min(1.0, dist_to_c / (max_dist * 0.75))
            raw_size = int(p["size_at_edge"] * scale)
            size     = min(self._CONVERGE_SIZES,
                           key=lambda s: abs(s - raw_size))
            surf = self._render_cached(p["text"], size, color)
            # Fade out as phrases approach center
            center_fade = min(1.0, dist_to_c / (max_dist * 0.3 + 1e-6))
            a    = int(min(255, p["alpha"] * center_fade * opacity_mult * 2.55))
            surf.set_alpha(a)
            bx = int(p["x"] - surf.get_width()  / 2)
            by = int(p["y"] - surf.get_height() / 2)
            surface.blit(surf, (bx, by))

    # ── Strobe mode ───────────────────────────────────────────────────────────

    def _init_strobe(self):
        self._strobe_phrase  = self.pool.pick() or "..."
        self._strobe_visible = False
        self._strobe_timer   = 0.0
        self._strobe_surf    = None

    def _update_strobe(self, dt: float):
        on_ms  = max(16, self.config.get("center_flash_on_time",  120))
        off_ms = max(16, self.config.get("center_flash_off_time", 80))
        self._strobe_timer += dt * 1000.0

        if self._strobe_visible:
            if self._strobe_timer >= on_ms:
                self._strobe_visible = False
                self._strobe_timer   = 0.0
        else:
            if self._strobe_timer >= off_ms:
                self._strobe_visible = True
                self._strobe_timer   = 0.0
                phrase = self.pool.pick() or "..."
                if phrase != self._strobe_phrase:
                    self._strobe_phrase = phrase
                    self._strobe_surf   = None  # invalidate

    def _draw_strobe(self, surface: pygame.Surface):
        if not self._strobe_visible:
            return
        w, h = self._w, self._h
        target_size = max(40, int(h * 0.13))
        color = self._text_color()

        if self._strobe_surf is None:
            words   = self._strobe_phrase.upper().split()
            lines   = []
            current = []
            font    = self.font_mgr.get_font(target_size)
            # Greedy word-wrap: break when line would exceed 80% of screen width
            for word in words:
                test = " ".join(current + [word])
                if font.size(test)[0] > w * 0.80 and current:
                    lines.append(" ".join(current))
                    current = [word]
                else:
                    current.append(word)
            if current:
                lines.append(" ".join(current))

            # Render each line and composite onto a single surface
            line_surfs = [font.render(ln, True, color) for ln in lines]
            line_h     = max(s.get_height() for s in line_surfs)
            total_h    = len(line_surfs) * line_h
            total_w    = max(s.get_width() for s in line_surfs)
            composite  = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
            for idx, ls in enumerate(line_surfs):
                composite.blit(ls, ((total_w - ls.get_width()) // 2, idx * line_h))
            self._strobe_surf = composite

        opacity = int(self.opacity_base * 2.55)
        self._strobe_surf.set_alpha(max(30, min(255, opacity)))
        sw, sh = self._strobe_surf.get_size()
        surface.blit(self._strobe_surf, ((w - sw) // 2, (h - sh) // 2))

    # ── Tunnel mode ───────────────────────────────────────────────────────────

    def _init_tunnel(self, w: int, h: int):
        """Fixed radial arms: each phrase is born tiny at center and grows as
        it flies outward along its arm angle.  Arms are evenly spaced so the
        layout stays organised rather than noisy."""
        arm_count = max(5, min(10, int(self.density * 7)))
        self._tunnel_phrases = []
        for i in range(arm_count):
            angle = (i / arm_count) * math.tau
            # Stagger starting progress so arms aren't all at the same position
            progress = random.uniform(0.02, 0.95)
            self._tunnel_phrases.append({
                "text":     self.pool.pick(),
                "progress": progress,   # 0 = born at centre, 1 = reached edge
                "speed":    random.uniform(0.18, 0.42),
                "angle":    angle,
            })

    def _update_tunnel(self, dt: float):
        for p in self._tunnel_phrases:
            p["progress"] += p["speed"] * dt
            if p["progress"] >= 1.0:
                p["progress"] = 0.0
                p["text"]     = self.pool.pick()
                p["speed"]    = random.uniform(0.18, 0.42)
                # Keep the same arm angle — renew phrase on same arm

    def _draw_tunnel(self, surface: pygame.Surface, beat_freq: float):
        pulse        = self._beat_pulse(beat_freq)
        opacity_mult = self.opacity_base / 50.0 * (1 + pulse)
        color  = self._text_color()
        w, h   = self._w, self._h
        cx, cy = w / 2.0, h / 2.0
        reach  = min(w, h) * 0.62  # max radius a phrase travels before reset

        # Draw back-to-front (lowest progress = smallest/nearest-centre first)
        for p in sorted(self._tunnel_phrases, key=lambda x: x["progress"]):
            prog = p["progress"]
            if prog < 0.02:
                continue

            # Size: starts at 10 px, reaches ~14% of screen height at the edge
            raw_size = int(10 + h * 0.13 * prog ** 1.4)
            size     = min(_TUNNEL_SIZES, key=lambda s: abs(s - raw_size))

            # Radial position along the arm
            radius = prog ** 1.1 * reach
            px = cx + math.cos(p["angle"]) * radius
            py = cy + math.sin(p["angle"]) * radius

            # Alpha: quick fade-in from centre, sharp fade-out near edge
            if prog < 0.10:
                raw_alpha = prog / 0.10
            elif prog > 0.80:
                raw_alpha = max(0.0, (1.0 - prog) / 0.20)
            else:
                raw_alpha = 1.0

            a = int(min(255, raw_alpha * opacity_mult * 255))
            if a <= 4:
                continue

            surf = self._render_cached(p["text"], size, color)
            surf.set_alpha(a)
            bx = int(px - surf.get_width() / 2)
            by = int(py - surf.get_height() / 2)
            surface.blit(surf, (bx, by))

    # ── Render cache ─────────────────────────────────────────────────────────

    def _render_cached(self, text: str, size: int, color: tuple) -> pygame.Surface:
        """Return a cached rendered surface, creating it if necessary.

        set_alpha() is called by the caller after this returns — that's safe
        because we blit immediately after each set_alpha, so frame-to-frame
        ordering never conflicts even when two phrases share the same surface.
        """
        font     = self.font_mgr.get_font(size)
        font_key = self.font_mgr.current_font

        # Font switched — old rendered surfaces are wrong typeface, nuke them
        if font_key != self._cache_font_key:
            self._render_cache.clear()
            self._cache_font_key = font_key

        key = (text.upper(), size, color)
        cached = self._render_cache.get(key)
        if cached is not None:
            self._render_cache.move_to_end(key)
            return cached

        surf = font.render(text.upper(), True, color)
        self._render_cache[key] = surf
        if len(self._render_cache) > _RENDER_CACHE_MAX:
            self._render_cache.popitem(last=False)   # evict least-recently-used
        return surf

    # ── Beat pulse helper ─────────────────────────────────────────────────────

    def _beat_pulse(self, beat_freq: float) -> float:
        if beat_freq <= 0.1:
            return 0.0
        duty  = self.config.get("flash_duty_cycle", 0.38)
        var   = self.config.get("flash_variance", 0.22)
        # Use audio engine's authoritative phase when available; fall back to wall clock
        audio_phase = self.config.get("beat_phase")
        if audio_phase is not None:
            phase = float(audio_phase)
        else:
            cycle = 1000.0 / beat_freq
            phase = (pygame.time.get_ticks() % cycle) / cycle
        return (0.3 + 0.7 * abs(phase - duty)) * var

    # ── Public update / draw ──────────────────────────────────────────────────

    def update(self, dt: float, beat_freq: float):
        # Live config
        self.opacity_base = self.config.get("veil_opacity", 45)
        self._w = pygame.display.get_surface().get_width()
        self._h = pygame.display.get_surface().get_height()

        # Pool or color change — scroll mode needs a surface rebuild
        pool_changed  = self.pool.update(self.config)
        color_changed = self._text_color() != self._last_color
        if pool_changed or color_changed:
            if self._mode == "scroll":
                self._init_scroll()
            elif self._mode == "strobe":
                self._strobe_surf = None  # invalidate phrase cache

        # Mode timer
        self._mode_timer += dt
        cfg_mode = self.config.get("veil_mode")
        if cfg_mode and cfg_mode != self._mode:
            self._pick_mode()
        elif not cfg_mode and self._mode_timer >= self._mode_change:
            self._pick_mode()

        # Update active mode
        if self._mode == "scroll":
            self._update_scroll(dt, beat_freq)
        elif self._mode == "rain":
            self._update_rain(dt)
        elif self._mode == "drift":
            self._update_drift(dt)
        elif self._mode == "converge":
            self._update_converge(dt)
        elif self._mode == "strobe":
            self._update_strobe(dt)
        elif self._mode == "tunnel":
            self._update_tunnel(dt)

    def draw(self, surface: pygame.Surface, beat_freq: float):
        if self._mode == "scroll":
            self._draw_scroll(surface, beat_freq)
        elif self._mode == "rain":
            self._draw_rain(surface, beat_freq)
        elif self._mode == "drift":
            self._draw_drift(surface, beat_freq)
        elif self._mode == "converge":
            self._draw_converge(surface, beat_freq)
        elif self._mode == "strobe":
            self._draw_strobe(surface)
        elif self._mode == "tunnel":
            self._draw_tunnel(surface, beat_freq)
