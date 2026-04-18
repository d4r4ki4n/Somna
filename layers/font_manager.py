import pygame
import random
import time
from pathlib import Path


_ROOT = Path(__file__).parent.parent

_SYSTEM_SERIF_FALLBACKS = (
    "georgia",
    "garamond",
    "palatino linotype",
    "times new roman",
)
_SYSTEM_SANS_FALLBACKS = (
    "arialblack",
    "arial",
    "segoeui",
    "helvetica",
    "dejavusans",
)


def discover_fonts(session: str | None = None) -> list[str | None]:
    """Discover font files with a three-tier fallback chain.

    Priority:
      1. sessions/<session>/fonts/*.ttf + *.otf   (session-specific)
      2. fonts/*.ttf + *.otf                       (project-level defaults)
      3. [None]                                     (system font fallback)

    Returns a list of font file paths, or [None] if no files found.
    """
    candidates = []
    if session:
        candidates.append(_ROOT / "sessions" / session / "fonts")
    candidates.append(_ROOT / "fonts")

    for font_dir in candidates:
        if not font_dir.exists():
            continue
        ttfs = sorted(str(f) for f in font_dir.glob("*.ttf"))
        otfs = sorted(str(f) for f in font_dir.glob("*.otf"))
        found = ttfs + otfs
        if found:
            return found
    return [None]


def make_font(
    font_path: str | None, size: int, bold: bool = True, serif: bool = False
) -> pygame.font.Font:
    """Create a pygame Font object with a rich system-font fallback.

    If font_path is a real file, loads it directly.
    Otherwise falls back through system serif or sans-serif faces.
    """
    if font_path is not None:
        try:
            return pygame.font.Font(font_path, size)
        except Exception:
            pass

    faces = _SYSTEM_SERIF_FALLBACKS if serif else _SYSTEM_SANS_FALLBACKS
    for face in faces:
        try:
            f = pygame.font.SysFont(face, size, bold=bold)
            if f:
                return f
        except Exception:
            continue
    return pygame.font.Font(None, size)


class FontManager:
    """Timer-based font switching with a loaded-font cache.

    Modes
    -----
    intelligent    — font changes every 5-12 s (calm, dwell-heavy).
    rapid          — font changes every 0.15-0.45 s (strobing overload effect).
    beat_sync      — font changes on every beat_phase downstroke (phase ≈ 0).
                     Switches are locked to the entrainment rhythm.
    breathe_sync   — font changes on every exhale transition (respiratory_phase
                     crossing 0.5). Locks font switches to the breath cycle.
    depth_adaptive — switching speed scales with trance_score. At trance_score 0
                     the interval is ~10 s (intelligent-like); at 1.0 it drops to
                     ~0.5 s (near-rapid). The deeper you go, the faster fonts cycle.

    get_font() is called every frame for every veil phrase.  Without caching,
    each call would load the .ttf file from disk, allocate memory, and return
    a fresh object — hundreds of times per second.  The cache keyed on
    (path, size) means each (font, size) combination is loaded exactly once
    and reused.  The cache is cleared when the font selection changes.
    """

    _INTELLIGENT_MIN = 5.0
    _INTELLIGENT_MAX = 12.0
    _RAPID_MIN = 0.15
    _RAPID_MAX = 0.45

    def __init__(self, config: dict):
        self.config = config
        self.font_pool = discover_fonts(config.get("session_folder"))
        self.current_font: str | None = None
        self._next_switch = 0.0
        self._cache: dict[tuple, pygame.font.Font] = {}
        self._last_beat_phase: float = 1.0
        self._last_breath_phase: float = 0.0
        self._switch()

    def _pick_interval(self, mode: str) -> float:
        if mode == "rapid":
            return random.uniform(self._RAPID_MIN, self._RAPID_MAX)
        if mode == "depth_adaptive":
            trance = float(self.config.get("eeg_trance_score", 0.0) or 0.0)
            trance = max(0.0, min(1.0, trance))
            lo = 10.0 - 9.5 * trance
            hi = 12.0 - 11.5 * trance
            return random.uniform(lo, hi)
        return random.uniform(self._INTELLIGENT_MIN, self._INTELLIGENT_MAX)

    def _switch(self):
        if self.font_pool:
            self.current_font = random.choice(self.font_pool)
        mode = self.config.get("font_switch_mode", "intelligent")
        self._next_switch = time.monotonic() + self._pick_interval(mode)
        self._cache.clear()

    def _check_phase_triggers(self) -> bool:
        mode = self.config.get("font_switch_mode", "intelligent")
        if mode == "beat_sync":
            phase = float(self.config.get("beat_phase", 0.0) or 0.0)
            crossed = self._last_beat_phase > 0.5 and phase < 0.5
            self._last_beat_phase = phase
            return crossed
        if mode == "breathe_sync":
            phase = float(
                self.config.get(
                    "ppg_breath_phase", self.config.get("respiratory_phase", 0.0)
                )
                or 0.0
            )
            crossed = self._last_breath_phase < 0.5 and phase >= 0.5
            self._last_breath_phase = phase
            return crossed
        return False

    def get_font(self, size: int) -> pygame.font.Font:
        now = time.monotonic()
        mode = self.config.get("font_switch_mode", "intelligent")

        should_switch = False
        if mode in ("beat_sync", "breathe_sync"):
            should_switch = self._check_phase_triggers()
        elif mode == "depth_adaptive":
            if now >= self._next_switch:
                should_switch = True
        else:
            if now >= self._next_switch:
                should_switch = True

        if should_switch:
            self._switch()

        key = (self.current_font, size)
        if key not in self._cache:
            self._cache[key] = make_font(self.current_font, size)
        return self._cache[key]
