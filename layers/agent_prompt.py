"""
layers/agent_prompt.py

Renders the agent's question directly in the display window as large, glowing
text that slowly zooms in from a starting scale to full size, then sits there
until the prompt is cleared from live_control.json.

This replaces the need for a pop-up dialog when the display is running in
always-on-top / overlay mode — the question becomes part of the experience
rather than a jarring system dialog.

Style is controlled per-prompt via ``cfg["llm_prompt_style"]``:
    glow_color    – hex string e.g. "#FFA060" (default amber)
    text_color    – hex string e.g. "#FFF0E6" (default warm white)
    font          – "default" or any system font name (e.g. "impact", "georgia")
    zoom_speed    – "slow" | "normal" | "fast" | "static"
    intensity     – "soft" | "normal" | "intense"
"""

import pygame
from layers.font_manager import discover_fonts, make_font


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_hex(hex_str: str, fallback: tuple) -> tuple:
    """Parse a CSS hex color string → (R, G, B).  Falls back gracefully."""
    if not isinstance(hex_str, str):
        return fallback
    try:
        h = hex_str.lstrip("#")
        if len(h) == 3:
            h = h[0] * 2 + h[1] * 2 + h[2] * 2
        if len(h) != 6:
            return fallback
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return fallback


# ── Per-intensity settings ────────────────────────────────────────────────────

_INTENSITY: dict[str, dict] = {
    "soft": {
        "base_scale": 0.55,  # starts bigger, less dramatic zoom-in
        "max_scale": 0.80,  # caps below full-screen to stay subtle
        "backdrop_max_alpha": 55,
    },
    "normal": {
        "base_scale": 0.28,
        "max_scale": 1.00,
        "backdrop_max_alpha": 120,
    },
    "intense": {
        "base_scale": 0.12,  # starts tiny, fills past 100% (crops)
        "max_scale": 1.15,
        "backdrop_max_alpha": 170,
    },
}

# Zoom-in duration per speed preset (seconds to reach max_scale)
_ZOOM_SECS: dict[str, float] = {
    "slow": 25.0,
    "normal": 12.0,
    "fast": 5.0,
    "static": 0.0,  # instant — no zoom animation
}

_DEFAULT_GLOW_COLOR = (255, 160, 100)  # amber
_DEFAULT_TEXT_COLOR = (255, 240, 230)  # warm white


class AgentPromptLayer:
    """Reads ``cfg["llm_prompt"]`` each frame and renders it as a slow,
    steadily-growing overlay.  Clears itself the moment the key is gone.

    Visual style (colors, intensity, font, zoom speed) is read from
    ``cfg["llm_prompt_style"]`` if present.
    """

    _MAX_FONT = 148  # px — rendered once, then scaled by pygame
    _GLOW_PASSES = [  # (dx, dy, alpha) for glow halo
        (-6, 0, 40),
        (6, 0, 40),
        (0, -6, 40),
        (0, 6, 40),
        (-4, -4, 30),
        (4, -4, 30),
        (-4, 4, 30),
        (4, 4, 30),
        (-10, 0, 18),
        (10, 0, 18),
        (0, -10, 18),
        (0, 10, 18),
    ]

    def __init__(self):
        self._prompt: str | None = None
        self._prev_prompt: str | None = None
        self._zoom_time: float = 0.0
        self._prompt_timeout: float = 0.0  # from agent_message.timeout_s
        self._prompt_elapsed: float = 0.0  # seconds since prompt was set
        self._full_surf: pygame.Surface | None = None
        self._font: pygame.font.Font | None = None
        self._session: str = "default"
        self._style: dict = {}  # cached style for current prompt

    # ── Font loading ──────────────────────────────────────────────────────────

    def _load_font(self, session: str, font_name: str = "default") -> pygame.font.Font:
        if font_name and font_name != "default":
            try:
                return pygame.font.SysFont(font_name, self._MAX_FONT, bold=True)
            except Exception:
                pass
        paths = discover_fonts(session)
        chosen = paths[0] if paths else None
        return make_font(chosen, self._MAX_FONT, bold=(chosen is None), serif=True)

    def _get_font(self, session: str, font_name: str = "default") -> pygame.font.Font:
        cache_key = f"{session}::{font_name}"
        if self._font is None or cache_key != getattr(self, "_font_key", ""):
            self._session = session
            self._font_key = cache_key
            self._font = self._load_font(session, font_name)
            self._full_surf = None  # invalidate render cache
        return self._font

    # ── Text rendering ────────────────────────────────────────────────────────

    @staticmethod
    def _wrap(text: str, font: pygame.font.Font, max_w: int) -> list[str]:
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

    def _render_full(self, W: int) -> pygame.Surface:
        """Render the prompt at _MAX_FONT with glow halo; cached until prompt changes."""
        font = self._font
        text = self._prompt if self._prompt else ""
        max_w = int(W * 0.92)
        lines = self._wrap(text, font, max_w)

        style = self._style
        text_rgb = _parse_hex(style.get("text_color", ""), _DEFAULT_TEXT_COLOR)
        glow_rgb = _parse_hex(style.get("glow_color", ""), _DEFAULT_GLOW_COLOR)

        line_surfs = [font.render(ln, True, text_rgb) for ln in lines]
        glow_surfs = [font.render(ln, True, glow_rgb) for ln in lines]

        gap = 18
        pad = 20
        total_h = sum(s.get_height() for s in line_surfs) + gap * max(
            len(line_surfs) - 1, 0
        )
        total_w = max(s.get_width() for s in line_surfs)

        surf = pygame.Surface((total_w + pad * 2, total_h + pad * 2), pygame.SRCALPHA)

        y = pad
        for ls, gs in zip(line_surfs, glow_surfs):
            x = pad + (total_w - ls.get_width()) // 2
            for dx, dy, ga in self._GLOW_PASSES:
                tmp = gs.copy()
                tmp.set_alpha(ga)
                surf.blit(tmp, (x + dx, y + dy))
            surf.blit(ls, (x, y))
            y += ls.get_height() + gap

        return surf

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, dt: float, cfg: dict) -> None:
        agent_msg = cfg.get("agent_message") or {}
        if isinstance(agent_msg, dict) and agent_msg.get("text"):
            via = agent_msg.get("via", [])
            if "overlay" in via or not via:
                prompt = agent_msg["text"]
                style = agent_msg.get("style") or {}
            else:
                prompt = None
                style = {}
        else:
            prompt = None
            style = {}

        session = cfg.get("session_folder", "default")
        font_name = style.get("font", "default") or "default"
        self._get_font(session, font_name)

        # Detect a new / changed prompt — reset animation and re-render
        if prompt != self._prev_prompt:
            self._prev_prompt = prompt
            self._prompt = prompt
            self._zoom_time = 0.0
            self._prompt_elapsed = 0.0
            self._prompt_timeout = (
                float(agent_msg.get("timeout_s") or 0)
                if isinstance(agent_msg, dict)
                else 0.0
            )
            self._full_surf = None
            self._style = dict(style)  # snapshot style for this prompt

        if self._prompt:
            zoom_speed = style.get("zoom_speed", "normal")
            if zoom_speed != "static":
                self._zoom_time += dt
            # Auto-dismiss once timeout_s has elapsed, matching the agent's own
            # _clear_message() intent even if the agent thread is slow.
            if self._prompt_timeout > 0:
                self._prompt_elapsed += dt
                if self._prompt_elapsed >= self._prompt_timeout:
                    self._prev_prompt = (
                        self._prompt
                    )  # keep remembered so same msg doesn't re-trigger
                    self._prompt = None

    def draw(self, surface: pygame.Surface) -> None:
        if not self._prompt:
            return

        W, H = surface.get_size()

        if self._full_surf is None:
            self._full_surf = self._render_full(W)

        style = self._style
        zoom_speed = style.get("zoom_speed", "normal")
        intensity = style.get("intensity", "normal")
        cfg_int = _INTENSITY.get(intensity, _INTENSITY["normal"])
        zoom_secs = _ZOOM_SECS.get(zoom_speed, _ZOOM_SECS["normal"])

        base_scale = cfg_int["base_scale"]
        max_scale = cfg_int["max_scale"]
        bd_max = cfg_int["backdrop_max_alpha"]

        if zoom_speed == "static" or zoom_secs <= 0:
            scale = max_scale
            ease = 1.0
        else:
            t = min(self._zoom_time / zoom_secs, 1.0)
            ease = 1.0 - (1.0 - t) ** 2  # quadratic ease-out
            scale = base_scale + (max_scale - base_scale) * ease

        sw = max(1, int(self._full_surf.get_width() * scale))
        sh = max(1, int(self._full_surf.get_height() * scale))
        scaled = pygame.transform.smoothscale(self._full_surf, (sw, sh))

        backdrop_alpha = int(bd_max * ease)
        strip_h = sh + 80
        backdrop = pygame.Surface((W, strip_h), pygame.SRCALPHA)
        # Tint backdrop with a very dark version of the glow color rather than
        # pure black — keeps the bar visually connected to the text's palette.
        gr, gg, gb = _parse_hex(style.get("glow_color", "#FFA060"), (255, 160, 96))
        tint_r = max(0, min(255, int(gr * 0.12)))
        tint_g = max(0, min(255, int(gg * 0.12)))
        tint_b = max(0, min(255, int(gb * 0.12)))
        backdrop.fill((tint_r, tint_g, tint_b, backdrop_alpha))
        surface.blit(backdrop, (0, (H - strip_h) // 2))

        x = (W - sw) // 2
        y = (H - sh) // 2
        surface.blit(scaled, (x, y))
