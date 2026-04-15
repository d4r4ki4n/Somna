"""
phrase_pool.py
Somna — Shared phrase pool utility

All affirmation layers (veil, center_text, shadows) use this to get
their current phrase list. Priority:

  1. config["affirmations_pool"]  — written by timeline_runner when a
                                    session is running and a tag group
                                    is active
  2. affirmations.txt in session folder (uses config["session_name"])
  3. root-level affirmations.txt

Exposes a PhrasePool object that layers hold onto. Call update(config)
each tick — it returns True if the pool changed (veil needs to rebuild).

Shadow word support
-------------------
pick_shadow() returns a single word suitable for subliminal presentation.
Source priority:
  1. Explicit # [shadows] section in affirmations.txt
  2. Single-token items in the active pool (no spaces — real single words)
  3. Built-in curated word set

Chain sequential revelation
---------------------------
pick() now locks to an active chain until all words have been shown
consecutively, then resumes random selection. This turns >> sequences into
actual narrative arcs: "let go >> deeper >> gone" displays as three
consecutive flashes, not fragmented random interleavings.
"""

from pathlib import Path
from typing import List, Optional, Union
import random


# layers/ → project root
_ROOT = Path(__file__).parent.parent

# Type alias: a pool item is either a plain string or an ordered chain list
_PoolItem = Union[str, List[str]]

# Built-in shadow word fallback — used when affirmations.txt has no [shadows] section
# and the active pool has no single-word items.
_DEFAULT_SHADOW_WORDS: List[str] = [
    "soft", "deep", "safe", "warm", "still", "open", "calm", "rest",
    "free", "yours", "down", "ease", "sink", "hold", "release", "drift",
    "quiet", "heavy", "slow", "melt", "gone", "empty", "fall", "true",
]


def _find_affirmations_file(session_name: Optional[str]) -> Optional[Path]:
    """Return the Path of the affirmations file that _load_file would use, without reading it."""
    if session_name:
        p = _ROOT / "sessions" / session_name / "affirmations.txt"
        if p.exists():
            return p
    p = _ROOT / "affirmations.txt"
    return p if p.exists() else None


def _parse_file(path: Path) -> tuple[List[_PoolItem], List[str]]:
    """
    Parse an affirmations.txt file.

    Returns:
        phrases     — full pool for CenterText (list of str | list[str] chains)
        shadow_words — single words from # [shadows] section (may be empty)

    The # [shadows] section tag signals that subsequent plain lines are
    single words intended for subliminal use. Lines in this section are
    NOT added to the main phrase pool; they are exclusive to pick_shadow().

    Syntax:
      plain line           → single phrase (str)
      word | word2         → random variants, each added as separate str entries
      word >> word2 >> …   → sequential chain stored as list[str]
      # [tag]              → standard section header (included in phrase pool)
      # [shadows]          → subliminal word section (exclusive to pick_shadow)
      # [pool_id.shadows]  → semantic selector sub-pool (skipped here; read by semantic_selector)
      # [pool_id.center]   → semantic selector sub-pool (skipped here)
    """
    phrases: List[_PoolItem] = []
    shadow_words: List[str]  = []
    in_shadows = False

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                inner = line.lstrip("#").strip()
                if inner.startswith("[") and inner.endswith("]"):
                    tag = inner[1:-1].strip()
                    # Semantic selector sub-pools are handled by semantic_selector.py
                    if "." in tag:
                        in_shadows = False
                        continue
                    in_shadows = (tag == "shadows")
                continue
            # Skip bare [tag] section headers (legacy format)
            if line.startswith("[") and line.endswith("]"):
                in_shadows = False
                continue

            if in_shadows:
                # Shadow words: single tokens only (split on | for variants too)
                if "|" in line:
                    shadow_words.extend(w.strip() for w in line.split("|") if w.strip())
                else:
                    word = line.strip()
                    if word:
                        shadow_words.append(word)
            else:
                if ">>" in line:
                    items = [p.strip() for p in line.split(">>") if p.strip()]
                    if items:
                        phrases.append(items)
                elif "|" in line:
                    phrases.extend(p.strip() for p in line.split("|") if p.strip())
                else:
                    phrases.append(line)

    return phrases, shadow_words


def _load_file(session_name: Optional[str]) -> List[_PoolItem]:
    """Load phrases from the appropriate file (phrases only, no shadow words)."""
    candidates = []
    if session_name:
        candidates.append(_ROOT / "sessions" / session_name / "affirmations.txt")
    candidates.append(_ROOT / "affirmations.txt")

    for path in candidates:
        if path.exists():
            phrases, _ = _parse_file(path)
            if phrases:
                return phrases

    return ["..."]


def _load_shadow_words(session_name: Optional[str]) -> List[str]:
    """Load the [shadows] section from the appropriate affirmations file."""
    candidates = []
    if session_name:
        candidates.append(_ROOT / "sessions" / session_name / "affirmations.txt")
    candidates.append(_ROOT / "affirmations.txt")

    for path in candidates:
        if path.exists():
            _, shadow_words = _parse_file(path)
            if shadow_words:
                return shadow_words

    return []


class PhrasePool:
    """
    Holds the current active phrase list and detects changes.

    Pool items are either plain strings or chain lists (list[str]).

    Chain sequential revelation: once pick() selects a chain, subsequent
    calls return each word in sequence until the chain is exhausted, then
    normal random selection resumes. This makes >> sequences create actual
    consecutive narrative arcs in the display.

    Usage:
        pool = PhrasePool(config)

        # each frame:
        if pool.update(config):
            self._rebuild()          # only veil needs this
        phrase = pool.pick()         # CenterText / Veil
        word   = pool.pick_shadow()  # Shadows (single word, subliminal)
    """

    def __init__(self, config: dict):
        self._pool: List[_PoolItem] = []
        self._shadow_words: List[str] = []
        self._pool_id: object = None   # identity sentinel for change detection

        # Chain sequential revelation state
        self._active_chain: Optional[List[str]] = None
        self._active_chain_pos: int = 0

        self.update(config, force=True)

    def _reset_state(self) -> None:
        self._active_chain     = None
        self._active_chain_pos = 0

    def update(self, config: dict, force: bool = False) -> bool:
        """
        Sync pool from config. Returns True if the pool changed.
        Call every frame (cheap — only reloads on actual change).
        """
        live_pool = config.get("affirmations_pool")

        if live_pool is not None:
            new_id = id(live_pool)
            if force or new_id != self._pool_id:
                if force or live_pool != self._pool:
                    self._pool        = list(live_pool)
                    self._shadow_words = []   # live pool has no shadow section
                    self._pool_id     = new_id
                    self._reset_state()
                    return True
                self._pool_id = new_id
            return False
        else:
            session_name = config.get("session_folder")
            fpath = _find_affirmations_file(session_name)
            mtime = fpath.stat().st_mtime if fpath else 0.0
            new_id = ("file", session_name, mtime)
            if force or new_id != self._pool_id:
                phrases, shadow_words = (
                    _parse_file(fpath) if fpath and fpath.exists()
                    else (["..."], [])
                )
                self._pool        = phrases or ["..."]
                self._shadow_words = shadow_words
                self._pool_id     = new_id
                self._reset_state()
                return True
            return False

    def pick(self) -> str:
        """Return a phrase from the pool.

        If a chain is currently active, returns the next word in sequence
        until the chain is exhausted, then resumes random selection.
        This ensures >> chains play as consecutive flashes, not fragmented
        random interleavings.
        """
        if not self._pool:
            return "..."

        # If mid-chain, advance it
        if self._active_chain is not None:
            result = self._active_chain[self._active_chain_pos]
            self._active_chain_pos += 1
            if self._active_chain_pos >= len(self._active_chain):
                self._active_chain     = None
                self._active_chain_pos = 0
            return result

        item = random.choice(self._pool)
        if isinstance(item, list):
            # Start chain — return first word, set up state for subsequent picks
            self._active_chain     = item
            self._active_chain_pos = 1
            return item[0]
        return item

    def pick_shadow(self) -> str:
        """Return a single word for subliminal (Shadows layer) use.

        Source priority (Chien et al. 2023 — subliminal priming requires
        direct semantic associates; multi-word phrases don't work):
          1. Explicit # [shadows] section from affirmations.txt
          2. Single-token items in the active pool (no spaces)
          3. Built-in curated single-word fallback set
        """
        if self._shadow_words:
            return random.choice(self._shadow_words)

        # Extract single-word items from the active pool
        words = [item for item in self._pool
                 if isinstance(item, str) and " " not in item.strip()]
        if words:
            return random.choice(words)

        return random.choice(_DEFAULT_SHADOW_WORDS)

    @property
    def phrases(self) -> List[str]:
        """Flat list of all strings; chains are expanded in-order."""
        out: List[str] = []
        for item in self._pool:
            if isinstance(item, list):
                out.extend(item)
            else:
                out.append(item)
        return out

    @property
    def has_shadow_words(self) -> bool:
        """True if an explicit [shadows] section was found."""
        return bool(self._shadow_words)
