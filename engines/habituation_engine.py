"""
engines/habituation_engine.py — Habituation & Novelty Management Engine (Bible Ch.10 §10.3)
==================================================================================
Tracks novelty at three timescales (micro / meso / macro) to prevent semantic
satiation and maintain perceptual salience throughout a session.

Four core types:
  StimulusRecord          — per-stimulus state (novelty score, counters, state)
  NoveltyBudget           — session novelty accounting with per-layer caps
  DishabituationScheduler — active surprise events to restore depleted novelty
  HabituationEngine       — orchestrator; wires the three above + DB persistence

Integration:
  - Call engine.on_stimulus_presented(stimulus_id, class, layer, duration_s)
    after every delivery (center_text, veil/shadows, audio, visual change)
  - Call engine.tick() at ~1 Hz; returns patch dict to write to live_control.json
  - Call engine.get_novelty(stimulus_id) to gate semantic_selector pool filtering
  - Call engine.on_session_end() at session close
  - Conductor checks engine.budget.remaining() to detect class exhaustion
"""

from __future__ import annotations

import json
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from ipc import patch_live

_ROOT      = Path(__file__).parent.parent
_LIVE_PATH = _ROOT / "live_control.json"
def _db():
    from content_tools import somna_db
    return somna_db


# ── Stimulus state lifecycle ──────────────────────────────────────────────────

class StimulusState(Enum):
    NOVEL    = "novel"
    ACTIVE   = "active"
    COOLING  = "cooling"
    RETIRED  = "retired"
    ARCHIVED = "archived"


# ── Timescale constants ───────────────────────────────────────────────────────

# τ_micro — consecutive-presentation decay constant (number of presentations)
_TAU_MICRO: dict[str, float] = {
    "word":    8.0,
    "visual": 20.0,
    "audio":  45.0,
    "spiral": 20.0,
    "fractal":20.0,
    "beat":   45.0,
    "tone":   45.0,
}
_TAU_MICRO_DEFAULT = 15.0

# Recovery gap (seconds) — gap resets consecutive_presentations → 0
_RECOVERY_GAP_S: dict[str, float] = {
    "word":    30.0,
    "visual": 120.0,
    "audio":   60.0,
    "spiral": 120.0,
    "beat":    60.0,
}
_RECOVERY_GAP_DEFAULT = 60.0

# Session budget — max presentations per class per session (meso)
_SESSION_BUDGET: dict[str, int] = {
    "visual":      60,
    "shadows":     40,
    "center_text": 25,
    "audio":       80,
    "voice":       15,
    "word":        25,
}
_SESSION_BUDGET_DEFAULT = 30

# τ_macro — lifetime-sessions decay constant
_TAU_MACRO: dict[str, float] = {
    "visual": 15.0,
    "word":   25.0,
    "audio":  30.0,
}
_TAU_MACRO_DEFAULT = 20.0

# Rest recovery rate per day (macro bonus)
_REST_RECOVERY_RATE = 0.02
_REST_RECOVERY_CAP  = 0.30

# Novelty budget (session)
_TOTAL_BUDGET   = 100.0
_RESERVE        = 20.0
_BASE_COST      = 1.0
_COST_FLOOR     = 0.1

# Rotation thresholds
_COOLING_THRESHOLD       = 0.30
_REACTIVATION_THRESHOLD  = 0.50
_MAX_COOLING_CYCLES      = 3
_RETIREMENT_REST_DAYS    = 30.0
_ARCHIVE_THRESHOLD       = 0.05

# Semantic gate thresholds
NOVELTY_GATE_THRESHOLD   = 0.20   # exclude from selection below this
NOVELTY_CONDITIONING_CAP = 0.30   # signal conditioning engine if below this


# ═══════════════════════════════════════════════════════════════════════════════
# StimulusRecord
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StimulusRecord:
    stimulus_id:             str
    stimulus_class:          str   # 'word', 'visual', 'audio', 'spiral', ...
    layer:                   str   # 'center_text', 'shadows', 'visual', 'audio', 'voice'

    # Micro counters
    consecutive_presentations: int   = 0
    last_presented_ts:         float = 0.0

    # Meso counters
    session_presentations: int = 0

    # Macro counters (DB-persisted)
    lifetime_presentations: int   = 0
    lifetime_sessions:      int   = 0
    first_used_ts:          float = 0.0
    last_session_ts:        float = 0.0

    # State
    state:           StimulusState = StimulusState.NOVEL
    cooling_since_ts: float        = 0.0
    times_cooled:    int           = 0

    # Computed
    novelty_score:    float = 1.0
    effectiveness_ema: float = 1.0

    def as_db_dict(self) -> dict:
        return {
            "stimulus_id":           self.stimulus_id,
            "stimulus_class":        self.stimulus_class,
            "layer":                 self.layer,
            "lifetime_presentations":self.lifetime_presentations,
            "lifetime_sessions":     self.lifetime_sessions,
            "first_used_ts":         self.first_used_ts,
            "last_session_ts":       self.last_session_ts,
            "state":                 self.state.value,
            "cooling_since_ts":      self.cooling_since_ts or None,
            "times_cooled":          self.times_cooled,
            "macro_novelty":         self.novelty_score,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# NoveltyBudget
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class NoveltyBudget:
    total_budget:        float = _TOTAL_BUDGET
    spent:               float = 0.0
    reserve:             float = _RESERVE
    visual_budget:       float = 60.0
    audio_budget:        float = 80.0
    shadows_budget:      float = 40.0
    center_text_budget:  float = 25.0
    voice_budget:        float = 15.0

    _layer_spent: dict[str, float] = field(default_factory=dict)

    def spend(self, layer: str, cost: float) -> None:
        self.spent += cost
        self._layer_spent[layer] = self._layer_spent.get(layer, 0.0) + cost

    def remaining(self, layer: str | None = None) -> float:
        """Remaining budget, globally or for a specific layer."""
        if layer is None:
            return max(0.0, self.total_budget - self.spent)
        cap_map = {
            "visual":      self.visual_budget,
            "audio":       self.audio_budget,
            "shadows":     self.shadows_budget,
            "center_text": self.center_text_budget,
            "voice":       self.voice_budget,
        }
        cap   = cap_map.get(layer, _SESSION_BUDGET_DEFAULT)
        spent = self._layer_spent.get(layer, 0.0)
        return max(0.0, cap - spent)

    def is_exhausted(self, layer: str) -> bool:
        return self.remaining(layer) <= 0.0

    def reset(self) -> None:
        self.spent = 0.0
        self._layer_spent.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# DishabituationScheduler
# ═══════════════════════════════════════════════════════════════════════════════

class DishabituationScheduler:
    """
    Schedules surprise/deviant events when aggregate novelty drops too low.

    Trigger types and per-type cooldowns (seconds):
      visual     — sudden visual parameter change (unexpected color, shape)
      audio      — deviant tone or beat change
      crossmodal — simultaneous multi-sense shift
      semantic   — cross-pool phrase intrusion
      gain       — SR noise boost
    """

    _TRIGGER_COOLDOWNS = {
        "visual":     180.0,
        "audio":      120.0,
        "crossmodal": 300.0,
        "semantic":    90.0,
        "gain":       150.0,
    }
    _TRIGGER_THRESHOLD      = 0.40
    _MAX_TRIGGERS           = 8
    _MIN_INTERVAL_S         = 90.0
    _RECENCY_PENALTY_WINDOW = 3    # same type not repeated within last N triggers
    _DEPTH_CEILING          = 0.80 # above this trance depth only mild triggers

    def __init__(self):
        self._triggers_fired  = 0
        self._last_trigger_ts = 0.0
        self._trigger_history : deque[tuple[float, str]] = deque(maxlen=20)
        self._pending_trigger : str | None = None
        self._per_type_ts     : dict[str, float] = {}

    def check(self, mean_novelty: float, trance_score: float = 0.0,
              reserve_remaining: float = _RESERVE) -> bool:
        """Return True if conditions warrant scheduling a dishabituation event."""
        if mean_novelty >= self._TRIGGER_THRESHOLD:
            return False
        if self._triggers_fired >= self._MAX_TRIGGERS:
            return False
        now = time.time()
        if now - self._last_trigger_ts < self._MIN_INTERVAL_S:
            return False
        if reserve_remaining <= 0:
            return False
        self._select_trigger(trance_score)
        return self._pending_trigger is not None

    def _select_trigger(self, trance_score: float) -> None:
        """Pick the least-recently-used trigger type that respects its cooldown."""
        now     = time.time()
        options = list(self._TRIGGER_COOLDOWNS.keys())

        # Build recency exclusion set
        recent_types = {t for _, t in list(self._trigger_history)[-self._RECENCY_PENALTY_WINDOW:]}

        # Only mild triggers at high trance depth
        if trance_score > self._DEPTH_CEILING:
            options = ["semantic", "gain"]

        random.shuffle(options)
        for t in options:
            if t in recent_types:
                continue
            cooldown = self._TRIGGER_COOLDOWNS[t]
            if now - self._per_type_ts.get(t, 0.0) >= cooldown:
                self._pending_trigger = t
                return
        self._pending_trigger = None

    def get_pending_trigger(self) -> str | None:
        """Consume and return the pending trigger, or None."""
        t = self._pending_trigger
        if t is not None:
            now = time.time()
            self._pending_trigger     = None
            self._last_trigger_ts     = now
            self._per_type_ts[t]      = now
            self._trigger_history.append((now, t))
            self._triggers_fired     += 1
        return t

    def reset(self) -> None:
        self._triggers_fired   = 0
        self._last_trigger_ts  = 0.0
        self._trigger_history.clear()
        self._pending_trigger  = None
        self._per_type_ts.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# HabituationEngine
# ═══════════════════════════════════════════════════════════════════════════════

class HabituationEngine:
    """
    Central novelty tracking orchestrator.

    Typical per-session lifecycle:
        eng = HabituationEngine(session_id)
        # ... each time content is shown:
        novelty = eng.on_stimulus_presented('vortex_spiral', 'spiral', 'visual', 2.5)
        # ... at 1 Hz cadence:
        patch = eng.tick()
        patch_live(patch)
        # ... at session end:
        eng.on_session_end()
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._records  : dict[str, StimulusRecord] = {}
        self.budget    = NoveltyBudget()
        self._scheduler = DishabituationScheduler()
        self._tick_count = 0

        self._load_macro_state()

    # ── Macro state bootstrap ─────────────────────────────────────────────────

    def _load_macro_state(self) -> None:
        """Pre-populate StimulusRecord cache from DB macro state."""
        try:
            rows = _db().get_all_stimulus_exposure()
            for sid, row in rows.items():
                rec = self._get_or_create(sid, row.get("stimulus_class", ""), row.get("layer", ""))
                rec.lifetime_presentations = row.get("lifetime_presentations", 0)
                rec.lifetime_sessions      = row.get("lifetime_sessions", 0)
                rec.first_used_ts          = row.get("first_used_ts") or 0.0
                rec.last_session_ts        = row.get("last_session_ts") or 0.0
                rec.times_cooled           = row.get("times_cooled", 0)
                state_str = row.get("state", "novel")
                try:
                    rec.state = StimulusState(state_str)
                except ValueError:
                    rec.state = StimulusState.NOVEL
                rec.novelty_score = self._compute_novelty(rec)
        except Exception:
            pass

    # ── Core per-delivery hook ────────────────────────────────────────────────

    def on_stimulus_presented(
        self,
        stimulus_id:    str,
        stimulus_class: str,
        layer:          str,
        duration_s:     float = 1.0,
    ) -> float:
        """
        Record one stimulus presentation; return current novelty score.

        Should be called by center_text, veil, audio_engine, etc.
        """
        rec = self._get_or_create(stimulus_id, stimulus_class, layer)
        now = time.time()

        # Micro: check recovery gap
        tau_recover = _RECOVERY_GAP_S.get(stimulus_class, _RECOVERY_GAP_DEFAULT)
        if rec.last_presented_ts > 0 and (now - rec.last_presented_ts) > tau_recover:
            rec.consecutive_presentations = 0

        # Update counters
        rec.consecutive_presentations += 1
        rec.session_presentations     += 1
        rec.lifetime_presentations    += 1
        rec.last_presented_ts          = now

        if rec.first_used_ts == 0.0:
            rec.first_used_ts = now

        # Promote NOVEL → ACTIVE on first use
        if rec.state == StimulusState.NOVEL:
            rec.state = StimulusState.ACTIVE

        # Compute novelty
        rec.novelty_score = self._compute_novelty(rec)

        # Budget cost
        cost = self._compute_cost(rec.novelty_score)
        self.budget.spend(layer, cost)

        # Check rotation
        self._check_rotation(rec)

        return rec.novelty_score

    # ── Novelty formula ───────────────────────────────────────────────────────

    def _compute_novelty(self, rec: StimulusRecord) -> float:
        # Micro: exponential decay in consecutive presentations
        tau_micro = _TAU_MICRO.get(rec.stimulus_class, _TAU_MICRO_DEFAULT)
        micro     = math.exp(-rec.consecutive_presentations / tau_micro)

        # Meso: quadratic budget consumption within session
        sess_budget = _SESSION_BUDGET.get(rec.layer,
                      _SESSION_BUDGET.get(rec.stimulus_class, _SESSION_BUDGET_DEFAULT))
        meso_ratio  = min(1.0, rec.session_presentations / max(sess_budget, 1))
        meso        = max(0.0, 1.0 - meso_ratio ** 2)

        # Macro: lifetime sessions decay
        tau_macro  = _TAU_MACRO.get(rec.stimulus_class, _TAU_MACRO_DEFAULT)
        macro_base = math.exp(-rec.lifetime_sessions / tau_macro)

        # Rest bonus
        now      = time.time()
        days_off = (now - rec.last_session_ts) / 86400.0 if rec.last_session_ts else 0.0
        rest_rec = min(_REST_RECOVERY_CAP, days_off * _REST_RECOVERY_RATE)
        macro    = min(1.0, macro_base + rest_rec)

        novelty  = micro * meso * macro
        return max(0.0, min(1.0, novelty))

    def _compute_cost(self, novelty: float) -> float:
        return _BASE_COST * (1.0 / max(novelty, _COST_FLOOR))

    # ── Rotation logic ────────────────────────────────────────────────────────

    def _check_rotation(self, rec: StimulusRecord) -> None:
        """Transition ACTIVE stimuli to COOLING/RETIRED when macro_novelty is low."""
        if rec.state != StimulusState.ACTIVE:
            return

        # Compute macro novelty alone for rotation threshold
        tau_macro  = _TAU_MACRO.get(rec.stimulus_class, _TAU_MACRO_DEFAULT)
        macro_base = math.exp(-rec.lifetime_sessions / tau_macro)
        now        = time.time()
        days_off   = (now - rec.last_session_ts) / 86400.0 if rec.last_session_ts else 0.0
        rest_rec   = min(_REST_RECOVERY_CAP, days_off * _REST_RECOVERY_RATE)
        macro      = min(1.0, macro_base + rest_rec)

        if macro < _ARCHIVE_THRESHOLD:
            rec.state = StimulusState.ARCHIVED
        elif macro < _COOLING_THRESHOLD:
            if rec.times_cooled >= _MAX_COOLING_CYCLES:
                rec.state = StimulusState.RETIRED
            else:
                rec.state = StimulusState.COOLING
                rec.cooling_since_ts = now
                rec.times_cooled    += 1

    def _try_reactivate(self, rec: StimulusRecord) -> None:
        """Check if a COOLING stimulus is ready to return to ACTIVE."""
        if rec.state != StimulusState.COOLING:
            return
        # Reactivate when projected novelty is above threshold
        temp       = rec.consecutive_presentations
        rec.consecutive_presentations = 0
        projected  = self._compute_novelty(rec)
        rec.consecutive_presentations = temp
        if projected >= _REACTIVATION_THRESHOLD:
            rec.state = StimulusState.ACTIVE

    # ── Tick (1 Hz) ───────────────────────────────────────────────────────────

    def tick(self) -> dict:
        """
        Called at approximately 1 Hz.
        Returns a dict of live_control.json keys to write.
        """
        self._tick_count += 1
        now = time.time()

        # Re-evaluate cooling records
        for rec in self._records.values():
            if rec.state == StimulusState.COOLING:
                self._try_reactivate(rec)
            if rec.state == StimulusState.ACTIVE:
                rec.novelty_score = self._compute_novelty(rec)

        # Aggregate stats
        active_scores = [r.novelty_score for r in self._records.values()
                         if r.state == StimulusState.ACTIVE]
        mean_novelty  = sum(active_scores) / len(active_scores) if active_scores else 1.0

        active_count  = sum(1 for r in self._records.values() if r.state == StimulusState.ACTIVE)
        cooling_count = sum(1 for r in self._records.values() if r.state == StimulusState.COOLING)

        # Read live trance for dishabituation guard
        try:
            live         = json.loads(_LIVE_PATH.read_text(encoding="utf-8"))
            trance_score = float(live.get("eeg_trance_score_v2", 0.0) or 0.0)
        except Exception:
            trance_score = 0.0

        # Dishabituation scheduler
        reserve_left = max(0.0, self.budget.reserve
                           - self.budget._layer_spent.get("_reserve", 0.0))
        if self._scheduler.check(mean_novelty, trance_score, reserve_left):
            trigger = self._scheduler.get_pending_trigger()
        else:
            trigger = None

        return {
            "habituation_mean_novelty":       round(mean_novelty, 3),
            "habituation_trigger_pending":    trigger,
            "habituation_budget_remaining":   round(self.budget.remaining(), 1),
            "habituation_active_count":       active_count,
            "habituation_cooling_count":      cooling_count,
        }

    # ── Session end ───────────────────────────────────────────────────────────

    def on_session_end(self) -> None:
        """Flush macro state to DB and reset meso/micro counters."""
        self._flush_to_db()
        self.budget.reset()
        self._scheduler.reset()
        for rec in self._records.values():
            rec.lifetime_sessions += 1
            rec.session_presentations = 0
            rec.consecutive_presentations = 0
            rec.last_session_ts = time.time()

    def _flush_to_db(self) -> None:
        for rec in self._records.values():
            try:
                _db().upsert_stimulus_exposure(
                    stimulus_id          = rec.stimulus_id,
                    stimulus_class       = rec.stimulus_class,
                    layer                = rec.layer,
                    presentations_delta  = 0,  # already accumulated
                    exposure_s_delta     = 0.0,
                    state                = rec.state.value,
                    macro_novelty        = rec.novelty_score,
                    cooling_since_ts     = rec.cooling_since_ts or None,
                )
            except Exception:
                pass

    # ── Public accessors ──────────────────────────────────────────────────────

    def get_novelty(self, stimulus_id: str) -> float:
        """Return current novelty score for a stimulus; 1.0 if unseen."""
        rec = self._records.get(stimulus_id)
        return rec.novelty_score if rec else 1.0

    def is_usable(self, stimulus_id: str) -> bool:
        """False when novelty is below the semantic-selector gate threshold."""
        return self.get_novelty(stimulus_id) >= NOVELTY_GATE_THRESHOLD

    def needs_rotation(self, stimulus_id: str) -> bool:
        """True when the stimulus class is budget-exhausted for its layer."""
        rec = self._records.get(stimulus_id)
        if rec is None:
            return False
        return self.budget.is_exhausted(rec.layer)

    def get_active_stimuli(self, layer: str | None = None) -> list[str]:
        """Return stimulus_ids in ACTIVE state, optionally filtered by layer."""
        return [
            sid for sid, r in self._records.items()
            if r.state == StimulusState.ACTIVE
            and (layer is None or r.layer == layer)
        ]

    def ranked_by_novelty(self, stimulus_ids: list[str]) -> list[str]:
        """Return stimulus_ids sorted descending by novelty score."""
        return sorted(
            stimulus_ids,
            key=lambda sid: self.get_novelty(sid),
            reverse=True,
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_or_create(
        self, stimulus_id: str, stimulus_class: str, layer: str
    ) -> StimulusRecord:
        if stimulus_id not in self._records:
            self._records[stimulus_id] = StimulusRecord(
                stimulus_id    = stimulus_id,
                stimulus_class = stimulus_class,
                layer          = layer,
            )
        return self._records[stimulus_id]

    # ── Mean novelty property ─────────────────────────────────────────────────

    @property
    def mean_novelty(self) -> float:
        active = [r.novelty_score for r in self._records.values()
                  if r.state == StimulusState.ACTIVE]
        return sum(active) / len(active) if active else 1.0
