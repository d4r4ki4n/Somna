"""
engines/conditioning_engine.py — Conditioning & Reinforcement Architecture (Bible Ch.10 §10.1)
====================================================================================
Implements Pavlovian CS–US associative learning on top of Somna's delivery pipeline.

Seven runtime components:
  StrengthTracker        — Rescorla-Wagner acquisition/extinction per (cs, us) pair
  ReinforcementScheduler — Variable-ratio schedule gating (CR-like probabilistic delivery)
  ShapingEngine          — Operant neurofeedback: progressive percentile targets
  SecondOrderTrainer     — CS2–CS1 pairings without full US (opt-in)
  PortableResponseEvaluator — External cue-test: CR detection outside full protocol
  AssociationRegistry    — DB read/write for pairing events
  ConditioningEngine     — Central coordinator wrapping all of the above

Integration:
  - Call engine.on_delivery() after every confirmed affirmation delivery (in somna_agent tick)
  - Call engine.should_deliver() to get VR schedule approval before queuing delivery
  - Call engine.get_sdl_candidates() to rank pool items by state-dependent learning (SDL) match
  - Call engine.end_session() at session close
"""

from __future__ import annotations

import json
import math
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from ipc import patch_live, read_live

_ROOT = Path(__file__).parent.parent

# ── IPC helpers ───────────────────────────────────────────────────────────────


def _read_live() -> dict:
    try:
        return read_live()
    except Exception:
        return {}


def _db():
    from content_tools import somna_db

    return somna_db


# ── Rescorla-Wagner parameters ────────────────────────────────────────────────

_LAMBDA = 1.0  # asymptote
_BETA_EXT_RATIO = 0.3  # extinction rate = _BETA_EXT_RATIO * beta_us

# ── Shaping constants ─────────────────────────────────────────────────────────

_INITIAL_PERCENTILE = 70
_FINAL_PERCENTILE = 30
_SHAPING_SESSIONS = 20

# ── Second-order conditioning constants ──────────────────────────────────────

SOC_MIN_FIRST_ORDER_STRENGTH = 0.6
SOC_PAIRS_PER_SESSION = 5
SOC_CS2_LEAD_MS = 500
SOC_PAIR_DURATION_MS = 2000

# ── Portable Response Evaluator constants ─────────────────────────────────────

PRE_BASELINE_S = 60.0
PRE_INTER_STIMULUS_S = 10.0
PRE_POST_CUE_WINDOW_S = 10.0
PRE_CR_THETA_INCREASE = 0.15
PRE_CR_RMSSD_INCREASE = 0.10
PRE_CR_TRANCE_INCREASE = 0.08

# ── Graduation criteria ───────────────────────────────────────────────────────

GRAD_MIN_STRENGTH = 0.7
GRAD_MIN_TRIALS = 30
GRAD_MIN_CR_RATE = 0.60


# ═══════════════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class NeuralStateFingerprint:
    """Six-dimensional encoding of the subject's neural state at delivery time."""

    faa: float = 0.0
    trance_score: float = 0.0
    theta_alpha_ratio: float = 0.0
    spectral_slope: float = 0.0
    coherence: float = 0.0
    autonomic_depth: float = 0.0

    def distance(self, other: "NeuralStateFingerprint") -> float:
        """Euclidean distance in normalised 6-D space (all dims in [0,1] range)."""
        dims_self = [
            self.faa,
            self.trance_score,
            self.theta_alpha_ratio,
            min(abs(self.spectral_slope) / 3.0, 1.0),
            self.coherence,
            self.autonomic_depth,
        ]
        dims_other = [
            other.faa,
            other.trance_score,
            other.theta_alpha_ratio,
            min(abs(other.spectral_slope) / 3.0, 1.0),
            other.coherence,
            other.autonomic_depth,
        ]
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(dims_self, dims_other)))

    @classmethod
    def from_live(cls, live: dict) -> "NeuralStateFingerprint":
        return cls(
            faa=float(live.get("eeg_faa_value", 0.0) or 0.0),
            trance_score=float(live.get("eeg_trance_score_v2", 0.0) or 0.0),
            theta_alpha_ratio=float(live.get("eeg_theta_alpha_ratio", 0.0) or 0.0),
            spectral_slope=float(live.get("eeg_spectral_slope", 0.0) or 0.0),
            coherence=float(live.get("eeg_frontal_alpha_coh", 0.0) or 0.0),
            autonomic_depth=float(live.get("autonomic_depth", 0.0) or 0.0),
        )

    def to_dict(self) -> dict:
        return {
            "faa": round(self.faa, 4),
            "trance_score": round(self.trance_score, 4),
            "theta_alpha_ratio": round(self.theta_alpha_ratio, 4),
            "spectral_slope": round(self.spectral_slope, 4),
            "coherence": round(self.coherence, 4),
            "autonomic_depth": round(self.autonomic_depth, 4),
        }


@dataclass
class InteroceptiveContext:
    """Cardiac/respiratory context at delivery — for CS profile tracking."""

    cardiac_phase: float = 0.0
    respiratory_phase: float = 0.0
    hrv_rmssd: float = 0.0
    autonomic_depth: float = 0.0
    stillness_index: float = 1.0

    @classmethod
    def from_live(cls, live: dict) -> "InteroceptiveContext":
        return cls(
            cardiac_phase=float(live.get("ppg_cardiac_phase", 0.0) or 0.0),
            respiratory_phase=float(live.get("respiratory_phase", 0.0) or 0.0),
            hrv_rmssd=float(live.get("ppg_hrv_rmssd", 0.0) or 0.0),
            autonomic_depth=float(live.get("autonomic_depth", 0.0) or 0.0),
            stillness_index=float(live.get("imu_stillness_index", 1.0) or 1.0),
        )


@dataclass
class ConditioningStrength:
    """Per (cs_identity, us_type, conductor_phase) associative strength state."""

    cs_identity: str
    cs_pool: str
    us_type: str
    conductor_phase: str = ""
    strength: float = 0.0
    trial_count: int = 0
    last_pairing_ts: int = 0  # epoch ms
    last_extinction_check_ts: int = 0
    salience: float = 1.0
    extinction_rate: float = 0.02
    is_second_order: bool = False


@dataclass
class CueTone:
    pool: str
    tone_hz: float = 200.0
    duration_ms: int = 500


@dataclass
class CueTestTrialResult:
    pool: str
    cr_detected: bool
    theta_delta: float
    rmssd_delta: float
    trance_delta: float


@dataclass
class CueTestResult:
    trials: list[CueTestTrialResult]
    overall_cr_rate: float
    graduated_pools: list[str]


# ═══════════════════════════════════════════════════════════════════════════════
# StrengthTracker
# ═══════════════════════════════════════════════════════════════════════════════


class StrengthTracker:
    """Rescorla-Wagner acquisition / extinction updates."""

    def __init__(self):
        # In-memory cache — writes to DB each update
        self._cache: dict[tuple, ConditioningStrength] = {}

    def load_from_db(self, session_id: str) -> None:
        """Preload strengths for this session's active pools from DB."""
        rows = _db().get_conditioning_strengths()
        for r in rows:
            key = (r["cs_identity"], r["us_type"], r.get("conductor_phase", ""))
            self._cache[key] = ConditioningStrength(
                cs_identity=r["cs_identity"],
                cs_pool=r.get("cs_pool", ""),
                us_type=r["us_type"],
                conductor_phase=r.get("conductor_phase", ""),
                strength=r["strength"],
                trial_count=r["trial_count"],
                last_pairing_ts=r.get("last_pairing_ts", 0),
                last_extinction_check_ts=r.get("last_extinction_check_ts", 0),
                salience=r.get("salience", 1.0),
                extinction_rate=r.get("extinction_rate", 0.02),
                is_second_order=bool(r.get("is_second_order", False)),
            )

    def get(
        self, cs_identity: str, us_type: str, conductor_phase: str = ""
    ) -> ConditioningStrength:
        key = (cs_identity, us_type, conductor_phase)
        if key not in self._cache:
            self._cache[key] = ConditioningStrength(
                cs_identity=cs_identity,
                cs_pool="",
                us_type=us_type,
                conductor_phase=conductor_phase,
            )
        return self._cache[key]

    def compute_salience(self, cs: ConditioningStrength) -> float:
        """Salience decays with repeated exposure; recovers with gap between sessions."""
        exposure_decay = 1.0 / (1.0 + 0.05 * cs.trial_count)
        context_bonus = 0.3 if self._in_trance_context() else 0.0
        now_ms = int(time.time() * 1000)
        days_since = (
            (now_ms - cs.last_pairing_ts) / 86_400_000 if cs.last_pairing_ts else 0.0
        )
        recency_bonus = min(0.2, days_since * 0.02)
        return min(1.0, exposure_decay + context_bonus + recency_bonus)

    def _in_trance_context(self) -> bool:
        live = _read_live()
        return float(live.get("eeg_trance_score_v2", 0.0) or 0.0) > 0.3

    def acquire(
        self,
        cs_identity: str,
        cs_pool: str,
        us_type: str,
        conductor_phase: str,
        us_magnitude: float,  # β_us — measured UCR intensity 0–1
        is_second_order: bool = False,
    ) -> float:
        """Rescorla-Wagner acquisition: ΔV = α_cs × β_us × (λ – V_total)."""
        cs = self.get(cs_identity, us_type, conductor_phase)
        cs.cs_pool = cs_pool
        cs.is_second_order = is_second_order

        alpha = self.compute_salience(cs)
        cs.salience = alpha

        # Bible Ch.4 Addendum A §10.3 — GENUS encoding bonus: 15% boost when content is delivered
        # during verified GENUS entrainment (sub_phase=ACTIVE, ratio >= 1.5).
        try:
            _live_snap = _read_live()
            if (
                _live_snap.get("genus_sub_phase") == "ACTIVE"
                and float(_live_snap.get("eeg_genus_ratio", 0.0) or 0.0) >= 1.5
            ):
                alpha = alpha * 1.15
        except Exception:
            pass

        # V_total = sum of all active CS strengths for this US type
        v_total = sum(
            s.strength
            for (ci, ut, cp), s in self._cache.items()
            if ut == us_type and cp == conductor_phase
        )
        delta_v = alpha * us_magnitude * (_LAMBDA - v_total)
        delta_v = max(0.0, delta_v)  # acquisition never decreases strength

        cs.strength = min(1.0, cs.strength + delta_v)
        cs.trial_count += 1
        cs.last_pairing_ts = int(time.time() * 1000)

        self._persist(cs)
        return cs.strength

    def extinguish(
        self,
        cs_identity: str,
        us_type: str,
        conductor_phase: str,
        beta_us: float = 0.3,
    ) -> float:
        """Extinction: ΔV = -α_cs × β_extinction × V."""
        cs = self.get(cs_identity, us_type, conductor_phase)
        beta_ext = _BETA_EXT_RATIO * beta_us
        alpha = self.compute_salience(cs)
        delta = -alpha * beta_ext * cs.strength
        cs.strength = max(0.0, cs.strength + delta)
        cs.last_extinction_check_ts = int(time.time() * 1000)
        self._persist(cs)
        return cs.strength

    def _persist(self, cs: ConditioningStrength) -> None:
        try:
            _db().upsert_conditioning_strength(
                cs_identity=cs.cs_identity,
                cs_pool=cs.cs_pool,
                us_type=cs.us_type,
                conductor_phase=cs.conductor_phase,
                strength_delta=0.0,
                salience=cs.salience,
                extinction_rate=cs.extinction_rate,
                is_second_order=cs.is_second_order,
            )
            _db().set_conditioning_strength(
                cs_identity=cs.cs_identity,
                us_type=cs.us_type,
                conductor_phase=cs.conductor_phase,
                strength=cs.strength,
                trial_count=cs.trial_count,
                last_pairing_ts=cs.last_pairing_ts,
                last_extinction_check_ts=cs.last_extinction_check_ts,
            )
        except Exception:
            pass

    def get_pool_mean_strength(self, cs_pool: str, us_type: str = "trance") -> float:
        """Mean strength across all CS in a pool for a given US type."""
        vals = [
            s.strength
            for (ci, ut, cp), s in self._cache.items()
            if s.cs_pool == cs_pool and ut == us_type
        ]
        return sum(vals) / len(vals) if vals else 0.0

    def get_strongest_pools(self, us_type: str = "trance", top_n: int = 3) -> list[str]:
        by_pool: dict[str, list[float]] = {}
        for (ci, ut, cp), s in self._cache.items():
            if ut == us_type:
                by_pool.setdefault(s.cs_pool, []).append(s.strength)
        pool_means = {p: sum(v) / len(v) for p, v in by_pool.items() if v}
        return sorted(pool_means, key=pool_means.get, reverse=True)[:top_n]


# ═══════════════════════════════════════════════════════════════════════════════
# ReinforcementScheduler
# ═══════════════════════════════════════════════════════════════════════════════


class ReinforcementScheduler:
    """Variable-ratio delivery schedule — adapts from continuous to VR-6 as strength grows."""

    # Strength → (vr_mean, vr_min, vr_max)
    _VR_TABLE = [
        (0.0, 0.3, None),  # continuous
        (0.3, 0.6, (2, 1, 3)),
        (0.6, 0.8, (4, 2, 6)),
        (0.8, 1.01, (6, 3, 9)),
    ]

    def __init__(self):
        self._gate_count = 0
        self._next_fire = 1

    def should_deliver(self, cs_strength: float) -> bool:
        """Return True if the current gate-count is at or past the next scheduled fire."""
        self._gate_count += 1

        # Continuous phase — deliver every time while still building
        if cs_strength < 0.3:
            return True

        if self._gate_count >= self._next_fire:
            vr_min, vr_max = self._get_range(cs_strength)
            self._next_fire = self._gate_count + random.randint(vr_min, vr_max)
            return True
        return False

    def _get_range(self, strength: float) -> tuple[int, int]:
        for lo, hi, rng in self._VR_TABLE:
            if lo <= strength < hi:
                if rng is None:
                    return (1, 1)  # continuous — always fire
                _, vr_min, vr_max = rng
                return vr_min, vr_max
        return (3, 6)

    @property
    def current_schedule(self) -> str:
        """Human-readable schedule label for live_control status."""
        return "continuous" if self._gate_count < 3 else "vr"

    @property
    def vr_mean(self) -> int:
        return 3  # nominal for status reporting


# ═══════════════════════════════════════════════════════════════════════════════
# ShapingEngine
# ═══════════════════════════════════════════════════════════════════════════════


class ShapingEngine:
    """Progressive percentile target shaping for operant neurofeedback."""

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self._sessions_done = 0
        self.reward_history: deque[float] = deque(maxlen=1000)
        self._load_progress()

    def _load_progress(self) -> None:
        live = _read_live()
        self._sessions_done = int(live.get("conditioning_shaping_sessions", 0) or 0)

    def compute_threshold(self, recent_values: list[float]) -> float:
        """Return the trance_score percentile threshold for the current shaping stage."""
        if not recent_values:
            return 0.0
        pct = self.current_percentile / 100.0
        sorted_vals = sorted(recent_values)
        idx = max(0, int(pct * len(sorted_vals)) - 1)
        return sorted_vals[idx]

    def advance_session(self) -> None:
        """Call at session end to step the shaping progression."""
        self._sessions_done = min(self._sessions_done + 1, _SHAPING_SESSIONS)
        try:
            _db().upsert_shaping_progress(
                self.user_id,
                "shaping_sessions",
                float(self._sessions_done),
                self.current_percentile,
            )
        except Exception:
            pass

    def record_reward(self, trance_value: float) -> None:
        self.reward_history.append(trance_value)

    @property
    def current_percentile(self) -> int:
        frac = min(self._sessions_done / _SHAPING_SESSIONS, 1.0)
        return round(
            _INITIAL_PERCENTILE - frac * (_INITIAL_PERCENTILE - _FINAL_PERCENTILE)
        )

    @property
    def session_count(self) -> int:
        return self._sessions_done


# ═══════════════════════════════════════════════════════════════════════════════
# SecondOrderTrainer
# ═══════════════════════════════════════════════════════════════════════════════


class SecondOrderTrainer:
    """CS2–CS1 pairings in MAINTENANCE phase without full US (opt-in)."""

    def __init__(self):
        self._pairs_this_session = 0

    def eligible(self, cs1_strength: float) -> bool:
        return (
            cs1_strength >= SOC_MIN_FIRST_ORDER_STRENGTH
            and self._pairs_this_session < SOC_PAIRS_PER_SESSION
        )

    def run_soc_pair(
        self,
        cs2_identity: str,
        cs1_tone_pool: str,
        session_id: str,
        conductor_phase: str,
    ) -> None:
        """
        Record a CS2–CS1 pairing without US.

        The actual stimulus presentation is handled externally (audio_engine, veil, etc.).
        This method records the pairing event into DB and increments the counter.
        """
        record_id = str(uuid.uuid4())
        try:
            _db().log_conditioning_association(
                record_id=record_id,
                session_id=session_id,
                timestamp_ms=int(time.time() * 1000),
                cs_class="second_order",
                cs_identity=cs2_identity,
                cs_pool="",
                us_type=f"cs1:{cs1_tone_pool}",
                us_magnitude=0.0,
                conductor_phase=conductor_phase,
                modality="soc",
                contiguity_ms=SOC_CS2_LEAD_MS,
            )
        except Exception:
            pass
        self._pairs_this_session += 1
        patch_live({"conditioning_soc_pairs_this_session": self._pairs_this_session})

    def reset_session(self) -> None:
        self._pairs_this_session = 0


# ═══════════════════════════════════════════════════════════════════════════════
# AssociationRegistry
# ═══════════════════════════════════════════════════════════════════════════════


class AssociationRegistry:
    """Batched write adapter for conditioning_associations table."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._pending: list[dict] = []
        self._BATCH = 20

    def record(self, **kwargs) -> None:
        self._pending.append(kwargs)
        if len(self._pending) >= self._BATCH:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        for rec in self._pending:
            try:
                _db().log_conditioning_association(**rec)
            except Exception:
                pass
        self._pending.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# PortableResponseEvaluator
# ═══════════════════════════════════════════════════════════════════════════════


class PortableResponseEvaluator:
    """
    External cue-test: plays TMR tones and measures conditioned responses.

    This runs outside a full session (between sessions) to test whether
    conditioning has transferred to a portable CR (theta ↑, RMSSD ↑, trance ↑).
    """

    def _snapshot(self) -> dict:
        live = _read_live()
        return {
            "trance": float(live.get("eeg_trance_score_v2", 0.0) or 0.0),
            "theta_alpha": float(live.get("eeg_theta_alpha_ratio", 0.0) or 0.0),
            "rmssd": float(live.get("ppg_hrv_rmssd", 0.0) or 0.0),
        }

    def _detect_cr(self, baseline: dict, post: dict) -> CueTestTrialResult:
        """Return True CR if ≥ 2 of 3 metrics exceed threshold."""
        theta_delta = post["theta_alpha"] - baseline["theta_alpha"]
        rmssd_delta = post["rmssd"] - baseline["rmssd"] * PRE_CR_RMSSD_INCREASE
        trance_delta = post["trance"] - baseline["trance"]

        hits = sum(
            [
                theta_delta
                >= PRE_CR_THETA_INCREASE * max(baseline["theta_alpha"], 0.01),
                rmssd_delta >= 0,  # any positive shift counts since baseline may be 0
                trance_delta >= PRE_CR_TRANCE_INCREASE,
            ]
        )
        return CueTestTrialResult(
            pool="",
            cr_detected=hits >= 2,
            theta_delta=theta_delta,
            rmssd_delta=rmssd_delta,
            trance_delta=trance_delta,
        )

    def run_cue_test(self, cue_tones: list[CueTone]) -> CueTestResult:
        """
        Lightweight synchronous cue-test.

        NOTE: This method sleeps (blocking). Run it in a dedicated thread or subprocess.
        The actual tone playback should be triggered via live_control.json before calling.
        """
        baseline = self._snapshot()
        time.sleep(PRE_BASELINE_S)  # wait for EEG to settle
        baseline = self._snapshot()

        trials: list[CueTestTrialResult] = []
        shuffled = list(cue_tones)
        random.shuffle(shuffled)

        for tone in shuffled:
            patch_live(
                {
                    "conditioning_cue_tone_pool": tone.pool,
                    "conditioning_cue_tone_hz": tone.tone_hz,
                    "conditioning_cue_active": True,
                }
            )
            time.sleep(tone.duration_ms / 1000.0)
            patch_live({"conditioning_cue_active": False})
            time.sleep(PRE_POST_CUE_WINDOW_S)

            post = self._snapshot()
            result = self._detect_cr(baseline, post)
            result.pool = tone.pool
            trials.append(result)
            time.sleep(PRE_INTER_STIMULUS_S)

        cr_rate = sum(t.cr_detected for t in trials) / len(trials) if trials else 0.0
        graduated = [t.pool for t in trials if t.cr_detected]

        return CueTestResult(
            trials=trials,
            overall_cr_rate=cr_rate,
            graduated_pools=graduated,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ConditioningEngine  (central coordinator)
# ═══════════════════════════════════════════════════════════════════════════════


class ConditioningEngine:
    """
    Central coordinator for all conditioning sub-systems.

    Usage in somna_agent.py tick:
        # At session start
        self._cond = ConditioningEngine(session_id)

        # Each tick, after delivery:
        self._cond.on_delivery(
            cs_class='spiral_style', cs_identity='vortex', cs_pool='somatic_release',
            neural_state=NeuralStateFingerprint.from_live(live), ...
        )

        # Before queuing delivery:
        if not self._cond.should_deliver(cs_identity, cs_pool):
            return  # VR schedule says skip this opportunity

        # Pool / item selection:
        candidates = self._cond.get_sdl_candidates(neural_state, pool='depth_descent')

        # At session end:
        self._cond.end_session()
    """

    def __init__(self, session_id: str, user_id: str = "default"):
        self.session_id = session_id
        self.user_id = user_id

        self._tracker = StrengthTracker()
        self._scheduler = ReinforcementScheduler()
        self._shaping = ShapingEngine(user_id)
        self._soc = SecondOrderTrainer()
        self._registry = AssociationRegistry(session_id)
        self._pre = PortableResponseEvaluator()

        self._enabled = True
        self._session_pairings = 0

        # Neural state fingerprint history for SDL matching
        self._fingerprint_history: list[tuple[str, NeuralStateFingerprint]] = []

        self._tracker.load_from_db(session_id)
        self._sync_live()

    # ── Primary interface ──────────────────────────────────────────────────────

    def on_delivery(
        self,
        cs_class: str,
        cs_identity: str,
        cs_pool: str,
        neural_state: NeuralStateFingerprint,
        delivery_gate: dict,
        conductor_phase: str,
        cardiac_phase: float = 0.0,
        respiratory_phase: float = 0.0,
        us_magnitude: float = 0.0,
    ) -> None:
        """Call after every confirmed affirmation delivery."""
        if not self._enabled:
            return

        live = _read_live()
        trance = float(live.get("eeg_trance_score_v2", 0.0) or 0.0)

        # Safety gate: don't record aversive pairings at very low trance
        if trance < 0.2:
            return

        # Use measured trance as US magnitude if not explicitly provided
        if us_magnitude <= 0.0:
            us_magnitude = trance

        # Log to DB
        record_id = str(uuid.uuid4())
        self._registry.record(
            record_id=record_id,
            session_id=self.session_id,
            timestamp_ms=int(time.time() * 1000),
            cs_class=cs_class,
            cs_identity=cs_identity,
            cs_pool=cs_pool,
            us_type="trance",
            us_magnitude=us_magnitude,
            conductor_phase=conductor_phase,
            modality="multimodal",
            contiguity_ms=0,
            delivery_gate_state=delivery_gate,
            neural_state_fingerprint=neural_state.to_dict(),
            cardiac_phase=cardiac_phase,
            respiratory_phase=respiratory_phase,
        )

        # Rescorla-Wagner update
        self._tracker.acquire(
            cs_identity=cs_identity,
            cs_pool=cs_pool,
            us_type="trance",
            conductor_phase=conductor_phase,
            us_magnitude=us_magnitude,
        )

        # Track neural fingerprints for SDL
        self._fingerprint_history.append((cs_identity, neural_state))
        if len(self._fingerprint_history) > 200:
            self._fingerprint_history = self._fingerprint_history[-200:]

        self._session_pairings += 1
        self._shaping.record_reward(trance)
        self._sync_live()

    def should_deliver(
        self, cs_identity: str, cs_pool: str, us_type: str = "trance"
    ) -> bool:
        """Return True if the VR schedule approves this delivery opportunity."""
        if not self._enabled:
            return True  # disabled → don't interfere
        cs = self._tracker.get(cs_identity, us_type, "")
        return self._scheduler.should_deliver(cs.strength)

    def get_sdl_candidates(
        self,
        current_state: NeuralStateFingerprint,
        pool: str,
        top_n: int = 5,
    ) -> list[str]:
        """
        Return cs_identity strings from pool, ranked by state-dependent learning match.

        Items whose historical neural state closest-matches the current state
        are ranked first — they were encoded under similar conditions and are
        most likely to fire strongly now.
        """
        pool_hist = [
            (ci, ns)
            for ci, ns in self._fingerprint_history
            if any(
                s.cs_pool == pool
                for (c, u, p), s in self._tracker._cache.items()
                if c == ci
            )
        ]
        if not pool_hist:
            return []

        scored: list[tuple[float, str]] = []
        for ci, ns in pool_hist:
            dist = current_state.distance(ns)
            score = 1.0 / (1.0 + dist)
            scored.append((score, ci))
        scored.sort(reverse=True)

        seen: set[str] = set()
        result: list[str] = []
        for _, ci in scored:
            if ci not in seen:
                seen.add(ci)
                result.append(ci)
            if len(result) >= top_n:
                break
        return result

    def get_li_flagged_items(self, pool: str, threshold: int = 50) -> list[str]:
        """
        Return cs_identities whose trial_count exceeds the LI rotation threshold.

        These have been over-exposed and should be temporarily de-prioritised (LI:
        latent inhibition — pre-exposure reduces later conditionability).
        """
        flagged = []
        for (ci, ut, cp), s in self._tracker._cache.items():
            if s.cs_pool == pool and s.trial_count >= threshold:
                flagged.append(ci)
        return list(set(flagged))

    def is_graduated(
        self, cs_identity: str, cs_pool: str, session_id: str, us_type: str = "trance"
    ) -> bool:
        """Return True if this CS has reached graduation criteria."""
        cs = self._tracker.get(cs_identity, us_type, "")
        if cs.strength < GRAD_MIN_STRENGTH or cs.trial_count < GRAD_MIN_TRIALS:
            return False
        return True

    def end_session(self) -> dict:
        """Flush registry, advance shaping, write status to live_control. Returns report."""
        self._registry.flush()
        self._soc.reset_session()
        self._shaping.advance_session()

        strongest = self._tracker.get_strongest_pools()
        report = {
            "session_pairings": self._session_pairings,
            "strongest_pools": strongest,
            "shaping_percentile": self._shaping.current_percentile,
            "overall_strength": self._get_overall_strength(),
        }
        self._sync_live()
        return report

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get_overall_strength(self) -> float:
        vals = [s.strength for s in self._tracker._cache.values()]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    def _sync_live(self) -> None:
        """Write status keys to live_control.json."""
        strongest = self._tracker.get_strongest_pools()
        all_pools = list(
            {s.cs_pool for s in self._tracker._cache.values() if s.cs_pool}
        )
        weakest = sorted(
            all_pools,
            key=lambda p: self._tracker.get_pool_mean_strength(p),
        )
        li_flagged: list[str] = []
        for pool in all_pools:
            li_flagged.extend(self.get_li_flagged_items(pool))

        patch_live(
            {
                "conditioning_session_pairing_count": self._session_pairings,
                "conditioning_overall_strength": round(self._get_overall_strength(), 4),
                "conditioning_strongest_pool": strongest[0] if strongest else "",
                "conditioning_weakest_pool": weakest[0] if weakest else "",
                "conditioning_shaping_percentile": self._shaping.current_percentile,
                "conditioning_current_schedule": self._scheduler.current_schedule,
                "conditioning_vr_mean": self._scheduler.vr_mean,
                "conditioning_li_flagged_items": list(set(li_flagged)),
                "conditioning_soc_pairs_this_session": self._soc._pairs_this_session,
            }
        )
