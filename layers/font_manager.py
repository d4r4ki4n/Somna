import pygame
import random
import time
from pathlib import Path


class FontManager:
    """Timer-based font switching with a loaded-font cache.

    Modes
    -----
    intelligent  — font changes every 5-12 s (calm, dwell-heavy).
    rapid        — font changes every 0.15-0.45 s (strobing overload effect).

    get_font() is called every frame for every veil phrase.  Without caching,
    each call would load the .ttf file from disk, allocate memory, and return
    a fresh object — hundreds of times per second.  The cache keyed on
    (path, size) means each (font, size) combination is loaded exactly once
    and reused.  The cache is cleared when the font selection changes.
    """

    _INTELLIGENT_MIN = 5.0
    _INTELLIGENT_MAX = 12.0
    _RAPID_MIN       = 0.15
    _RAPID_MAX       = 0.45

    def __init__(self, config: dict):
        self.config      = config
        self.font_pool   = self._load_fonts()
        self.current_font: str | None = None
        self._next_switch = 0.0
        self._cache: dict[tuple, pygame.font.Font] = {}
        self._switch()

    # ------------------------------------------------------------------
    def _load_fonts(self) -> list:
        session  = self.config.get("session_folder", "default")
        font_dir = Path(__file__).parent.parent / "sessions" / session / "fonts"
        fonts    = [str(f) for f in font_dir.glob("*.ttf")] if font_dir.exists() else []
        # Also pick up .otf files
        if font_dir.exists():
            fonts += [str(f) for f in font_dir.glob("*.otf")]
        return fonts or [None]

    def _switch(self):
        if self.font_pool:
            self.current_font = random.choice(self.font_pool)
        mode = self.config.get("font_switch_mode", "intelligent")
        if mode == "rapid":
            self._next_switch = time.monotonic() + random.uniform(
                self._RAPID_MIN, self._RAPID_MAX
            )
        else:
            self._next_switch = time.monotonic() + random.uniform(
                self._INTELLIGENT_MIN, self._INTELLIGENT_MAX
            )
        # Clear cache: the new font needs fresh Font objects
        self._cache.clear()

    # ------------------------------------------------------------------
    def get_font(self, size: int) -> pygame.font.Font:
        if time.monotonic() >= self._next_switch:
            self._switch()
        key = (self.current_font, size)
        if key not in self._cache:
            self._cache[key] = (
                pygame.font.Font(self.current_font, size)
                if self.current_font
                else pygame.font.SysFont("arialblack", size, bold=True)
            )
        return self._cache[key]
