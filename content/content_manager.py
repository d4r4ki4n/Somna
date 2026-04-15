"""
content/content_manager.py — Content Design & SSML Builder (Bible Ch.3 §3.6)
=====================================================================
Central coordinator for generating subliminal content across three delivery layers:
  Shadows    — single high-frequency word (≤2 words, direct imperative style)
  CenterText — 3-7 word indirect phrase
  TTS        — 10-30 word indirect suggestion with SSML prosody markup

Three components on this class:
  _load_pools       — JSON pool loader with validation
  build_ssml        — SSML builder for TTS phrases
  _validate_template — imagery / imperative QC gate

Integration:
  - SemanticSelector (Bible Ch.6 §6.6) selects pool_id by EEG state
  - HabituationEngine (Bible Ch.10 §10.3) gates novelty-depleted items
  - DeliveryGate (Bible Ch.4 §4.6) schedules TTS onset on breath phase
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ROOT       = Path(__file__).parent.parent
_POOLS_DIR  = _ROOT / "content_pools"

# ── SSML-safe prosody defaults (Bible Ch.3 §3.6 §12.1) ────────────────────────────────

@dataclass
class ProsodyParams:
    rate_percent:       int   = 70          # 70 % ≈ ~120-130 spm
    base_pitch_shift_st: int  = 0           # semitones relative to baseline
    pitch_step_st:      float = -1.0        # descend F0 per phrase
    break_ms:           int   = 600         # pause between phrases (400-800 ms)
    breath_phase:       float | None = None # exhalation target (0.5) or None


# ── Content pool dataclass ────────────────────────────────────────────────────

@dataclass
class ContentPool:
    pool_id:              str
    shadows_words:        list[str]       = field(default_factory=list)
    centertext_templates: list[str]       = field(default_factory=list)
    tts_templates:        list[str]       = field(default_factory=list)
    synonym_rings:        list[list[str]] = field(default_factory=list)
    pnd_scores:           dict[str, float]= field(default_factory=dict)
    frequency_band:       dict[str, str]  = field(default_factory=dict)
    vocabulary:           dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "ContentPool":
        return cls(
            pool_id              = d["pool_id"],
            shadows_words        = d.get("shadows_words",        []),
            centertext_templates = d.get("centertext_templates", []),
            tts_templates        = d.get("tts_templates",        []),
            synonym_rings        = d.get("synonym_rings",        []),
            pnd_scores           = d.get("pnd_scores",           {}),
            frequency_band       = d.get("frequency_band",       {}),
            vocabulary           = d.get("vocabulary",           {}),
        )


# ── QC constants ──────────────────────────────────────────────────────────────

# Visual imagery blacklist (Bible Ch.3 §3.6 §10.3)
VISUAL_IMAGERY_BLACKLIST: frozenset[str] = frozenset({
    "see", "look", "picture", "imagine", "visualize", "visualise",
    "watch", "gaze", "view", "observe", "appear", "bright", "dark",
    "color", "colour", "light", "scene", "landscape", "horizon",
    "staircase", "beach", "meadow", "garden", "forest", "rainbow",
    "sunset", "sunrise", "sky", "ocean", "cloud", "star", "fire",
})

# Somatic vocabulary intersection (Bible Ch.3 §3.6 §10.3 rule 4)
SOMATIC_VOCABULARY: frozenset[str] = frozenset({
    "breath", "breathe", "exhale", "inhale", "body", "chest", "belly",
    "arms", "legs", "hands", "spine", "shoulders", "heavy", "warm",
    "soft", "melting", "sinking", "floating", "weight", "tension",
    "release", "relax", "letting", "ease", "settle", "still",
    "heart", "pulse", "slow", "deep", "ground", "sink",
    # Interoceptive / proprioceptive vocabulary
    "feel", "feels", "felt", "feeling",
    "sense", "sensing", "sensation",
    "notice", "noticing",
    "aware", "awareness",
    "inside", "inward",
    "whole", "wholeness",
})

# Repetition caps per layer per session
SHADOWS_REP_CAP    = 15
CENTERTEXT_REP_CAP = 8
TTS_REP_CAP        = 4


# ═══════════════════════════════════════════════════════════════════════════════
# ContentManager
# ═══════════════════════════════════════════════════════════════════════════════

class ContentManager:
    """
    Loads content pools, generates per-layer suggestions, and builds SSML.

    Usage:
        mgr = ContentManager()                 # loads all JSON files in content_pools/
        word   = mgr.get_shadows_word("warmth_comfort", habituation)
        phrase = mgr.get_centertext_phrase("warmth_comfort", word, habituation)
        ssml   = mgr.get_tts_ssml("warmth_comfort", phrase, habituation=habituation)
    """

    def __init__(
        self,
        pools_path: str | None = None,
        session_db=None,
    ):
        self._db          = session_db
        self._pools_dir   = Path(pools_path) if pools_path else _POOLS_DIR
        self.pools: dict[str, ContentPool] = {}
        self._session_use_counts: dict[str, dict[str, int]] = {}  # pool → {item → count}
        self._load_pools(self._pools_dir)

    # ── Pool loading ──────────────────────────────────────────────────────────

    def _load_pools(self, path: Path) -> None:
        """
        Load all *.json files in path as content pools.
        Validates each template; raises ValueError on QC failure.
        """
        if not path.exists():
            return
        for jfile in sorted(path.glob("*.json")):
            try:
                data = json.loads(jfile.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise ValueError(f"Pool file {jfile.name} is not valid JSON: {e}") from e

            # Support both {"pools": [...]} and single-pool {pool_id: ...}
            pool_list = data.get("pools", [data] if "pool_id" in data else [])
            for pool_data in pool_list:
                pool = ContentPool.from_dict(pool_data)
                for tmpl in pool.tts_templates:
                    errors = self._validate_template(tmpl, layer="tts")
                    if errors:
                        raise ValueError(
                            f"Pool {pool.pool_id!r} template {tmpl!r} failed QC: {errors}"
                        )
                for tmpl in pool.centertext_templates:
                    errors = self._validate_template(tmpl, layer="centertext")
                    if errors:
                        raise ValueError(
                            f"Pool {pool.pool_id!r} template {tmpl!r} failed QC: {errors}"
                        )
                self.pools[pool.pool_id] = pool

    # ── Layer selectors ───────────────────────────────────────────────────────

    def get_shadows_word(
        self,
        pool_id: str,
        habituation=None,
        exclude: str = "",
        session_time_s: float | None = None,
    ) -> str:
        """Return one Shadows word from the pool, gated by habituation and rep cap.

        Applies session-temporal vocabulary widening (Bible Ch.3 §3.6 §10.4):
          0–10 min  → high-frequency words only
          10–20 min → high + moderate frequency words
          > 20 min  → full vocabulary (no frequency filter)
        """
        pool = self.pools.get(pool_id)
        if pool is None or not pool.shadows_words:
            return ""
        candidates = [w for w in pool.shadows_words if w != exclude]

        # Session-temporal frequency gating
        if session_time_s is not None and pool.frequency_band:
            t = float(session_time_s)
            if t < 600:       # < 10 min: high only
                allowed = {"high"}
            elif t < 1200:    # 10–20 min: high + moderate
                allowed = {"high", "moderate"}
            else:
                allowed = None  # no restriction after 20 min
            if allowed:
                gated = [w for w in candidates
                         if pool.frequency_band.get(w, "high") in allowed]
                if gated:
                    candidates = gated

        if habituation is not None:
            fresh = [w for w in candidates if habituation.is_usable(w)]
            if fresh:
                candidates = fresh
        # Respect repetition cap
        counts = self._session_use_counts.setdefault(pool_id, {})
        under_cap = [w for w in candidates if counts.get(w, 0) < SHADOWS_REP_CAP]
        if under_cap:
            candidates = under_cap
        word = random.choice(candidates) if candidates else ""
        if word:
            counts[word] = counts.get(word, 0) + 1
            if habituation is not None:
                habituation.on_stimulus_presented(word, "word", "shadows")
        return word

    def get_centertext_phrase(
        self,
        pool_id: str,
        shadows_word: str = "",
        habituation=None,
    ) -> str:
        """Return one CenterText phrase, avoiding the current shadows word.

        Cross-layer collision avoidance (Bible Ch.3 §3.6 §10.5): the active Shadows word
        is excluded both from template selection (literal match) AND from slot
        fills in _populate_template, so it cannot slip through a {body_part} etc.
        """
        pool = self.pools.get(pool_id)
        if pool is None or not pool.centertext_templates:
            return ""
        candidates = pool.centertext_templates
        # Template-level exclusion: skip any template that contains the shadows word
        if shadows_word:
            filtered = [t for t in candidates if shadows_word.lower() not in t.lower()]
            if filtered:
                candidates = filtered
        if habituation is not None:
            fresh = [t for t in candidates if habituation.is_usable(t)]
            if fresh:
                candidates = fresh
        counts = self._session_use_counts.setdefault(pool_id, {})
        under_cap = [t for t in candidates if counts.get(t, 0) < CENTERTEXT_REP_CAP]
        if under_cap:
            candidates = under_cap
        tmpl = random.choice(candidates) if candidates else ""
        if tmpl:
            # Slot-level exclusion: shadows word cannot appear via vocabulary fills
            phrase = self._populate_template(
                tmpl, pool,
                exclude_words=[shadows_word] if shadows_word else None,
            )
            counts[tmpl] = counts.get(tmpl, 0) + 1
            if habituation is not None:
                habituation.on_stimulus_presented(phrase, "word", "center_text")
            return phrase
        return ""

    def get_tts_suggestion(
        self,
        pool_id: str,
        centertext_phrase: str = "",
        prosody_params: ProsodyParams | None = None,
        habituation=None,
    ) -> str:
        """Return a plain-text TTS suggestion (without SSML) from the pool."""
        pool = self.pools.get(pool_id)
        if pool is None or not pool.tts_templates:
            return ""
        if prosody_params is None:
            prosody_params = ProsodyParams()
        candidates = pool.tts_templates
        if habituation is not None:
            fresh = [t for t in candidates if habituation.is_usable(t)]
            if fresh:
                candidates = fresh
        counts = self._session_use_counts.setdefault(pool_id, {})
        under_cap = [t for t in candidates if counts.get(t, 0) < TTS_REP_CAP]
        if under_cap:
            candidates = under_cap
        tmpl = random.choice(candidates) if candidates else ""
        if tmpl:
            text = self._populate_template(tmpl, pool)
            counts[tmpl] = counts.get(tmpl, 0) + 1
            if habituation is not None:
                habituation.on_stimulus_presented(text, "word", "voice")
            return text
        return ""

    def get_tts_ssml(
        self,
        pool_id: str,
        centertext_phrase: str = "",
        prosody_params: ProsodyParams | None = None,
        habituation=None,
    ) -> str:
        """Return full SSML string ready for TTS engine."""
        text = self.get_tts_suggestion(pool_id, centertext_phrase,
                                       prosody_params, habituation)
        if not text:
            return ""
        return self.build_ssml(text, prosody_params or ProsodyParams())

    # ── SSML builder ─────────────────────────────────────────────────────────

    def build_ssml(self, text: str, params: ProsodyParams) -> str:
        """
        Wrap text in SSML prosody markup (Bible Ch.3 §3.6 §4.2–4.4).

        Splits on "…" or ". " boundaries; each phrase gets:
          - <prosody rate="{rate_percent}%" pitch="{descending_st}st">
          - <break time="{break_ms}ms"/> between phrases
          - <emphasis> on embedded commands (words in *asterisks*)
        """
        phrases = self._split_into_phrases(text)
        parts: list[str] = []
        for i, phrase in enumerate(phrases):
            pitch_st = params.base_pitch_shift_st + (i * params.pitch_step_st)
            pitch_tag = (f"+{pitch_st:.0f}st" if pitch_st >= 0 else f"{pitch_st:.0f}st")

            # Handle *emphasis* markup
            phrase_ssml = re.sub(
                r"\*(.+?)\*",
                r"<emphasis>\1</emphasis>",
                phrase.strip(),
            )

            part = (
                f'<prosody rate="{params.rate_percent}%" pitch="{pitch_tag}">'
                f"{phrase_ssml}"
                f"</prosody>"
            )
            parts.append(part)
            if i < len(phrases) - 1:
                parts.append(f'<break time="{params.break_ms}ms"/>')

        inner = "".join(parts)
        return f"<speak>{inner}</speak>"

    # ── Template helpers ──────────────────────────────────────────────────────

    def _validate_template(
        self,
        template: str,
        layer: str = "tts",
    ) -> list[str]:
        """
        Run QC on a content template. Returns list of error strings (empty = pass).

        Rules (Bible Ch.3 §3.6 §10.3):
          1. No visual imagery tokens (all layers)
          2. At least one somatic/interoceptive anchor word (TTS only — centertext
             templates are shorter and may rely on slot fills for somatic content)
        """
        errors: list[str] = []
        # Strip placeholder markers for token analysis
        clean = re.sub(r"\{[^}]+\}", " ", template).lower()
        tokens = set(clean.split())

        # Rule 1: visual imagery blacklist (all layers)
        hits = tokens & VISUAL_IMAGERY_BLACKLIST
        if hits:
            errors.append(f"Visual imagery: {hits}")

        # Rule 2: somatic anchor required (TTS only).
        # Uses prefix matching (≥4-char roots) so inflections like "heaviness",
        # "softening", "dissolved", "breathing" all count.
        if layer == "tts":
            has_somatic_slot = bool(re.search(r"\{body_part\}", template, re.IGNORECASE))
            somatic_roots = {w for w in SOMATIC_VOCABULARY if len(w) >= 4}
            has_somatic = (
                has_somatic_slot
                or any(tok.startswith(root) for tok in tokens for root in somatic_roots)
                or bool(tokens & SOMATIC_VOCABULARY)
            )
            if not has_somatic:
                errors.append("No somatic anchor word found")

        return errors

    def _populate_template(
        self,
        template: str,
        pool: ContentPool,
        exclude_words: list[str] | None = None,
    ) -> str:
        """Replace {slot} placeholders with vocabulary words from pool."""
        exclude = set(exclude_words or [])

        def _fill(match: re.Match) -> str:
            slot = match.group(1)
            options = pool.vocabulary.get(slot, [slot])
            if exclude:
                options = [w for w in options if w not in exclude] or options
            return random.choice(options) if options else slot

        return re.sub(r"\{([^}]+)\}", _fill, template)

    def _split_into_phrases(self, text: str) -> list[str]:
        """Split text on '…', '...', or '. ' boundaries for SSML phrase wrapping."""
        parts = re.split(r"\.{2,}|(?<=[a-z])\.\s+", text)
        return [p.strip() for p in parts if p.strip()]

    def rotate_if_needed(
        self,
        word_or_phrase: str,
        pool_id: str,
        habituation=None,
    ) -> str:
        """
        If the item is over-habituated, return an alternative from the same pool.
        Falls back to the original if no alternative exists.
        """
        if habituation is None or habituation.is_usable(word_or_phrase):
            return word_or_phrase
        pool = self.pools.get(pool_id)
        if pool is None:
            return word_or_phrase
        all_items = pool.shadows_words + pool.centertext_templates
        alternatives = [
            item for item in all_items
            if item != word_or_phrase and habituation.is_usable(item)
        ]
        return random.choice(alternatives) if alternatives else word_or_phrase

    # ── Convenience ───────────────────────────────────────────────────────────

    def reset_session_counts(self) -> None:
        """Call at session start to reset per-session repetition counters."""
        self._session_use_counts.clear()

    @property
    def pool_ids(self) -> list[str]:
        return list(self.pools.keys())

    def has_pool(self, pool_id: str) -> bool:
        return pool_id in self.pools
