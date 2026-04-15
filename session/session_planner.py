"""
session/session_planner.py — Pre-session planning (Bible Ch.5 §5.5 §8)
=============================================================
Runs once before each session.  Queries the user model database,
evaluates recent session outcomes, and produces a SessionPlan for
the SessionDirector to execute.
"""

from __future__ import annotations

import datetime
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from session.session_director import (
    ARC_TEMPLATES,
    DirectorPhase,
    INDUCTION_STRATEGIES,
    PhasePlan,
    SessionPlan,
    _PHASE_CONTENT_POOLS,
    _PHASE_EXIT_CONDITIONS,
    _PHASE_GAIN_CEILINGS,
    _PHASE_INTENSITY_TARGETS,
    _clamp,
)

try:
    from session.induction_runner import StrategySelector, STRATEGY_REGISTRY
    _SELECTOR_AVAILABLE = True
except ImportError:
    _SELECTOR_AVAILABLE = False


# ── User model data structures ────────────────────────────────────────────────

@dataclass
class UserProfile:
    user_id:                 str
    sessions_completed:      int   = 0
    total_session_time_s:    int   = 0
    avg_peak_depth:          float = 0.0
    max_achieved_depth:      float = 0.0
    preferred_induction:     str   = "entrainment_heavy"
    preferred_arc:           str   = "GENTLE_DESCENT"
    avg_time_to_induction_s: float = 300.0
    avg_time_to_peak_s:      float = 900.0
    sleep_fork_success_rate: float = 0.0
    last_session_at:         Optional[float] = None
    created_at:              float = field(default_factory=time.time)
    updated_at:              float = field(default_factory=time.time)

    @classmethod
    def create_default(cls) -> "UserProfile":
        return cls(user_id="default", created_at=time.time(), updated_at=time.time())


@dataclass
class SessionRecord:
    """Lightweight record loaded from session_history."""
    session_id:             str
    arc_template:           str
    session_goal:           str
    achieved_peak_depth:    float
    induction_strategy:     str
    induction_effectiveness: float
    avg_depth:              float
    time_in_deep_s:         int
    duration_s:             int
    started_at:             float


@dataclass
class HistoryAnalysis:
    depth_trend:            Optional[float]
    best_arc:               Optional[str]
    best_induction:         Optional[str]
    conditioning_gaps:      list[str]
    last_arc_used:          Optional[str]
    sessions_since_variety: int

    @classmethod
    def empty(cls) -> "HistoryAnalysis":
        return cls(
            depth_trend=None,
            best_arc=None,
            best_induction=None,
            conditioning_gaps=[],
            last_arc_used=None,
            sessions_since_variety=0,
        )


# ── Pool ranking per goal ─────────────────────────────────────────────────────

_POOL_RANKINGS: dict[str, list[str]] = {
    "deepening_practice": [
        "deepening_somatic", "entrainment_heavy", "breath_anchors",
        "progressive_relaxation",
    ],
    "conditioning_reinforcement": [
        "conditioning_primary", "reinforcement_somatic",
        "anchor_strengthening", "identity_work",
    ],
    "sleep_preparation": [
        "sleep_bridge", "body_scan_progressive", "breath_slowing",
        "ambient_minimal",
    ],
    "exploration": [
        "general_induction", "somatic_exploration",
        "conceptual_frameworks", "novelty_high",
    ],
    "maintenance": [
        "balanced_general", "somatic_familiar", "light_conditioning",
        "ambient_support",
    ],
}

_PHASE_ENTRY_CONDITIONS: dict[DirectorPhase, str] = {
    DirectorPhase.ARRIVAL:             "session_start",
    DirectorPhase.INDUCTION:           "arrival_complete",
    DirectorPhase.DEEPENING:           "trance_score_v2 >= 0.25",
    DirectorPhase.WORK:                "trance_score_v2 >= target_peak_depth_x0.8",
    DirectorPhase.WORK_BLOCK:          "trance_score_v2 >= 0.4",
    DirectorPhase.MICRO_CONSOLIDATION: "work_block_complete",
    DirectorPhase.CONSOLIDATION:       "work_complete",
    DirectorPhase.EMERGENCE:           "consolidation_complete OR emergency",
    DirectorPhase.SLEEP_TRANSITION:    "drowsiness_detected AND sleep_fork_armed",
}


# ── SessionPlanner ────────────────────────────────────────────────────────────

class SessionPlanner:
    """
    Pre-session planning engine (Bible Ch.5 §5.5 §8).

    Usage:
        planner = SessionPlanner(db=somna_db_instance)
        plan = planner.plan_session(user_request={"goal": "deepening_practice"})
    """

    def __init__(self, db) -> None:
        """
        Args:
            db: somna_db module or object with get_user_profile(),
                save_user_profile(), get_recent_sessions(), and
                get_association_registry() methods.
        """
        self.db = db
        self._plan_conditioning_targets: list[str] = []

    def plan_session(self, user_request: Optional[dict] = None) -> SessionPlan:
        """Produce a SessionPlan for the upcoming session."""
        profile  = self._load_user_profile()
        history  = self._load_recent_sessions(limit=5)
        analysis = self._analyze_history(history)

        goal       = (user_request or {}).get("goal") or self._auto_select_goal(profile, analysis)
        arc        = (user_request or {}).get("arc_template") or self._select_arc(profile, analysis)
        depth      = (user_request or {}).get("target_peak_depth") or self._set_depth_target(profile, analysis)
        induction  = (user_request or {}).get("induction_strategy") or self._select_induction(profile, analysis)
        duration   = (user_request or {}).get("duration_s") or self._estimate_duration(profile, arc)
        sleep_fork = (
            arc == "SLEEP_BRIDGE"
            or bool((user_request or {}).get("sleep_fork", False))
            or self._is_evening_session()
        )

        cond_targets = self._select_conditioning_targets(profile, goal)
        self._plan_conditioning_targets = cond_targets

        phase_plan    = self._build_phase_plan(arc, profile, int(duration))
        contingencies = self._build_contingencies(phase_plan)
        content_strat = self._build_content_strategy(goal, phase_plan)

        return SessionPlan(
            session_id=str(uuid.uuid4()),
            created_at=time.time(),
            session_goal=goal,
            target_peak_depth=float(depth),
            estimated_duration_s=int(duration),
            arc_template=arc,
            phase_plan=phase_plan,
            contingency_branches=contingencies,
            content_strategy=content_strat,
            induction_strategy=induction,
            priority_pools=self._rank_pools(goal),
            conditioning_targets=cond_targets,
            sleep_fork_enabled=sleep_fork,
        )

    # ── Profile management ────────────────────────────────────────────────────

    def _load_user_profile(self) -> UserProfile:
        try:
            row = self.db.get_director_profile()
            if row:
                p = UserProfile(user_id=row.get("user_id", "default"))
                for k in vars(p):
                    if k in row:
                        setattr(p, k, row[k])
                return p
        except Exception:
            pass
        p = UserProfile.create_default()
        self._save_user_profile(p)
        return p

    def _save_user_profile(self, profile: UserProfile) -> None:
        try:
            self.db.save_director_profile(vars(profile))
        except Exception:
            pass

    # ── History analysis ──────────────────────────────────────────────────────

    def _load_recent_sessions(self, limit: int = 5) -> list[SessionRecord]:
        try:
            rows = self.db.get_recent_session_history(limit=limit)
            records = []
            for r in (rows or []):
                records.append(SessionRecord(
                    session_id=r.get("session_id", ""),
                    arc_template=r.get("arc_template", "GENTLE_DESCENT"),
                    session_goal=r.get("session_goal", "exploration"),
                    achieved_peak_depth=float(r.get("achieved_peak_depth", 0.0) or 0.0),
                    induction_strategy=r.get("induction_strategy", "entrainment_heavy"),
                    induction_effectiveness=float(r.get("induction_effectiveness", 0.5) or 0.5),
                    avg_depth=float(r.get("avg_depth", 0.0) or 0.0),
                    time_in_deep_s=int(r.get("time_in_deep_s", 0) or 0),
                    duration_s=int(r.get("duration_s", 0) or 0),
                    started_at=float(r.get("started_at", 0.0) or 0.0),
                ))
            return records
        except Exception:
            return []

    def _analyze_history(self, history: list[SessionRecord]) -> HistoryAnalysis:
        if not history:
            return HistoryAnalysis.empty()

        depths = [s.achieved_peak_depth for s in history]
        depth_trend = self._linreg_slope(depths)

        arc_scores: dict[str, list[float]] = {}
        ind_scores: dict[str, list[float]] = {}
        for s in history:
            arc_scores.setdefault(s.arc_template, []).append(s.achieved_peak_depth)
            ind_scores.setdefault(s.induction_strategy, []).append(s.induction_effectiveness)

        best_arc = max(arc_scores, key=lambda k: sum(arc_scores[k]) / len(arc_scores[k])) if arc_scores else None
        best_ind = max(ind_scores, key=lambda k: sum(ind_scores[k]) / len(ind_scores[k])) if ind_scores else None

        sessions_since_variety = 0
        for s in reversed(history):
            if s.arc_template == best_arc:
                sessions_since_variety += 1
            else:
                break

        return HistoryAnalysis(
            depth_trend=depth_trend,
            best_arc=best_arc,
            best_induction=best_ind,
            conditioning_gaps=self._find_conditioning_gaps(),
            last_arc_used=history[0].arc_template if history else None,
            sessions_since_variety=sessions_since_variety,
        )

    def _find_conditioning_gaps(self) -> list[str]:
        """Return association IDs that have low strength and need reinforcement."""
        try:
            rows = self.db.get_weak_conditioning_associations(threshold=0.5, limit=3)
            return [r.get("association_id", "") for r in (rows or [])]
        except Exception:
            return []

    # ── Goal / arc / depth selection ──────────────────────────────────────────

    def _auto_select_goal(self, profile: UserProfile, analysis: HistoryAnalysis) -> str:
        if analysis.conditioning_gaps:
            return "conditioning_reinforcement"
        if (analysis.depth_trend is not None
                and analysis.depth_trend < 0.001
                and profile.sessions_completed > 10):
            return "deepening_practice"
        if self._is_evening_session() and profile.sleep_fork_success_rate > 0.5:
            return "sleep_preparation"
        if profile.sessions_completed < 5:
            return "exploration"
        return "maintenance"

    def _select_arc(self, profile: UserProfile, analysis: HistoryAnalysis) -> str:
        if profile.sessions_completed < 5:
            return "GENTLE_DESCENT"

        # Bible Ch.4 Addendum A §6.1–6.2 — evaluate GENUS eligibility before variety/depth logic.
        # Estimate session duration for minimum-time gate (900 s).
        estimated_s = self._estimate_duration(profile, analysis.best_arc or "GENTLE_DESCENT")
        if self._is_genus_eligible(profile, analysis, int(estimated_s)):
            return self._select_genus_arc(int(estimated_s), analysis)

        if analysis.sessions_since_variety >= 3:
            alternatives = [
                a for a in ARC_TEMPLATES
                if a != analysis.best_arc
                and not (a == "DEEP_PLATEAU" and profile.sessions_completed < 5)
                and not a.startswith("GENUS_")   # exclude GENUS from random variety picks
            ]
            if alternatives:
                return random.choice(alternatives)

        return analysis.best_arc or profile.preferred_arc or "GENTLE_DESCENT"

    def _is_genus_eligible(
        self,
        profile: UserProfile,
        analysis: HistoryAnalysis,
        session_duration_s: int,
    ) -> bool:
        """Bible Ch.4 Addendum A §6.1 — check all GENUS inclusion and exclusion criteria."""
        # Exclusion: minimum session time (15 min)
        if session_duration_s < 900:
            return False

        # Exclusion: SLEEP_BRIDGE arc is contraindicated with GENUS
        if (analysis.last_arc_used or "") == "SLEEP_BRIDGE":
            return False

        try:
            dp = self.db.get_director_profile() or {}
        except Exception:
            dp = {}

        # Exclusion: user has opted out
        if not dp.get("genus_enabled", True):
            return False

        # Exclusion: epilepsy warning not yet acknowledged (first-session gate)
        if not dp.get("genus_epilepsy_ack", False):
            return False

        # Exclusion: previous GENUS session ended in FALLBACK with no adjustments
        try:
            recent = self.db.get_recent_sessions(limit=1) or []
            if recent:
                last = recent[0] if isinstance(recent[0], dict) else {}
                if last.get("genus_fallback") and not dp.get("genus_adjusted_since_fallback"):
                    return False
        except Exception:
            pass

        # Inclusion: monitor refresh rate >= 80 Hz (or audio-only mode)
        try:
            import json
            from pathlib import Path
            _live = Path(__file__).parent.parent / "live_control.json"
            live  = json.loads(_live.read_text(encoding="utf-8"))
            refresh_ok = (
                int(live.get("display_refresh_rate", 0) or 0) >= 80
                or bool(live.get("genus_audio_only_mode", False))
                or bool(dp.get("genus_audio_only_mode", False))
            )
        except Exception:
            refresh_ok = False
        if not refresh_ok:
            return False

        # Inclusion: daily scheduling — at least 20 h since last GENUS session
        last_ts = dp.get("genus_last_session_ts")
        if last_ts:
            try:
                hours_since = (time.time() - float(last_ts)) / 3600.0
                if hours_since < 20.0:
                    return False
            except Exception:
                pass
        # If genus_last_session_ts is absent the user has never done GENUS → eligible

        return True

    def _select_genus_arc(self, session_duration_s: int, analysis: HistoryAnalysis) -> str:
        """Bible Ch.4 Addendum A §6.2 — select the appropriate GENUS arc template."""
        try:
            dp = self.db.get_director_profile() or {}
        except Exception:
            dp = {}

        # Audio-only takes precedence when visual flicker is disabled
        if dp.get("genus_audio_only_mode") or dp.get("genus_visual_disabled"):
            return "GENUS_AUDIO_ONLY"

        # Check whether any conditioning pool has decayed below maintenance threshold
        conditioning_needed = False
        try:
            reg = self.db.get_association_registry() or {}
            # Maintenance threshold: strength < 0.3 on any pool with prior sessions
            conditioning_needed = any(
                v.get("strength", 1.0) < 0.3
                for v in reg.values()
                if v.get("trial_count", 0) >= 3
            )
        except Exception:
            pass

        # Short session (<40 min): standalone GENUS only
        if session_duration_s < 2400:
            return "GENUS_DAILY"

        # Long session with conditioning deficit: neuroprotection + conditioning trance
        if conditioning_needed:
            return "GENUS_NEUROPROTECTION"

        # Default long session: hybrid GENUS + mild trance
        return "GENUS_ENHANCED"

    def _select_induction(self, profile: UserProfile, analysis: HistoryAnalysis) -> str:
        # Use StrategySelector (Bible Ch.6 §6.7) if available
        if _SELECTOR_AVAILABLE:
            try:
                selector = StrategySelector(STRATEGY_REGISTRY, db=self.db)
                ctx = {
                    "session_count":  profile.sessions_completed,
                    "ppg_available":  False,   # unknown at planning time; conservative
                    "arc_template":   analysis.preferred_arc or "GENTLE_DESCENT",
                    "synthetic_board": False,
                }
                # Load contraindication flags and effectiveness from DB if possible
                user_profile_dict: dict = {}
                try:
                    dp = self.db.get_director_profile()
                    if dp:
                        user_profile_dict["contraindication_flags"] = (
                            dp.get("contraindication_flags", [])
                        )
                        user_profile_dict["strategy_effectiveness"] = (
                            dp.get("strategy_effectiveness", {})
                        )
                        user_profile_dict["preferred_strategy"] = (
                            dp.get("preferred_strategy")
                        )
                except Exception:
                    pass
                return selector.select_strategy(user_profile_dict, ctx)
            except Exception:
                pass
        # Fallback: legacy logic
        if analysis.best_induction:
            last_score = self._last_induction_score(analysis)
            if last_score < 0.5:
                alts = [s for s in INDUCTION_STRATEGIES if s != analysis.best_induction]
                if alts:
                    return random.choice(alts)
            return analysis.best_induction
        return profile.preferred_induction

    def _last_induction_score(self, analysis: HistoryAnalysis) -> float:
        """Proxy: no direct access here — return neutral 0.6."""
        return 0.6

    def _set_depth_target(self, profile: UserProfile, analysis: HistoryAnalysis) -> float:
        if profile.sessions_completed < 3:
            return 0.5
        trend   = analysis.depth_trend or 0.0
        stretch = 0.02 + 0.03 * _clamp(trend, 0.0, 1.0)
        target  = profile.avg_peak_depth + stretch
        ceiling = profile.max_achieved_depth + 0.1
        return _clamp(target, 0.3, min(ceiling, 0.95))

    def _estimate_duration(self, profile: UserProfile, arc: str) -> int:
        base = {
            "DEEP_PLATEAU":       2700,
            "SLEEP_BRIDGE":       2400,
            "CONDITIONING_FOCUS": 2400,
            "WAVE_PATTERN":       2100,
        }.get(arc, 1800)

        if profile.sessions_completed > 5 and profile.total_session_time_s > 0:
            avg_s = profile.total_session_time_s / profile.sessions_completed
            avg_min = avg_s / 60.0
            if avg_min > 0 and profile.avg_peak_depth / avg_min < 0.01:
                base = int(base * 1.2)

        return _clamp(int(base), 600, 7200)

    # ── Phase plan construction ───────────────────────────────────────────────

    def _build_phase_plan(
        self, arc_name: str, profile: UserProfile, duration_s: int,
    ) -> list[PhasePlan]:
        template = ARC_TEMPLATES.get(arc_name, ARC_TEMPLATES["GENTLE_DESCENT"])
        plans: list[PhasePlan] = []

        for phase, ratio in zip(template.phase_sequence, template.duration_ratios):
            target_dur = int(duration_s * ratio)

            if phase == DirectorPhase.INDUCTION:
                target_dur = max(target_dur, int(profile.avg_time_to_induction_s))

            min_dur = max(30, int(target_dur * 0.5))
            max_dur = int(target_dur * 2.5)

            plans.append(PhasePlan(
                phase=phase,
                target_duration_s=target_dur,
                min_duration_s=min_dur,
                max_duration_s=max_dur,
                entry_condition=_PHASE_ENTRY_CONDITIONS.get(phase, ""),
                exit_condition=_PHASE_EXIT_CONDITIONS.get(phase, "phase_elapsed >= target_duration"),
                intensity_target=_PHASE_INTENSITY_TARGETS.get(phase, 0.5),
                content_pools=list(_PHASE_CONTENT_POOLS.get(phase, ["ambient_support"])),
                gain_ceiling=_PHASE_GAIN_CEILINGS.get(phase, 0.5),
            ))

        return plans

    def _build_contingencies(self, phase_plan: list[PhasePlan]) -> dict[str, list[PhasePlan]]:
        return {
            "induction_failure": [
                PhasePlan(
                    phase=DirectorPhase.INDUCTION,
                    target_duration_s=300, min_duration_s=120, max_duration_s=600,
                    entry_condition="redirect_triggered",
                    exit_condition="trance_score_v2 >= 0.2",
                    intensity_target=0.3,
                    content_pools=["induction_alt", "breath_anchors"],
                    gain_ceiling=0.5,
                ),
            ],
            "depth_plateau": [
                PhasePlan(
                    phase=DirectorPhase.DEEPENING,
                    target_duration_s=240, min_duration_s=120, max_duration_s=480,
                    entry_condition="depth_stalled",
                    exit_condition="trance_score_v2 increasing for 60s",
                    intensity_target=0.6,
                    content_pools=["deepening_somatic", "breath_anchors"],
                    gain_ceiling=0.7,
                ),
            ],
            "drowsiness_detected": [
                PhasePlan(
                    phase=DirectorPhase.SLEEP_TRANSITION,
                    target_duration_s=600, min_duration_s=120, max_duration_s=900,
                    entry_condition="drowsiness_sustained > 60s",
                    exit_condition="handoff_to_doc39",
                    intensity_target=0.2,
                    content_pools=["sleep_bridge"],
                    gain_ceiling=0.3,
                ),
            ],
        }

    def _build_content_strategy(
        self, goal: str, phase_plan: list[PhasePlan],
    ) -> dict[str, dict]:
        strategy: dict[str, dict] = {}
        for pp in phase_plan:
            strategy[pp.phase.value] = {
                "pool_priorities": list(pp.content_pools),
                "priming_targets": [],
                "conditioning_targets": (
                    self._plan_conditioning_targets
                    if pp.phase in (DirectorPhase.WORK, DirectorPhase.WORK_BLOCK)
                    else []
                ),
            }
        return strategy

    def _rank_pools(self, goal: str) -> list[str]:
        return list(_POOL_RANKINGS.get(goal, _POOL_RANKINGS["exploration"]))

    def _select_conditioning_targets(
        self, profile: UserProfile, goal: str,
    ) -> list[str]:
        if goal != "conditioning_reinforcement":
            return []
        try:
            rows = self.db.get_weak_conditioning_associations(threshold=0.5, limit=3)
            return [r.get("association_id", "") for r in (rows or [])]
        except Exception:
            return []

    def _is_evening_session(self) -> bool:
        h = datetime.datetime.now().hour
        return h >= 20 or h < 4

    @staticmethod
    def _linreg_slope(values: list[float]) -> float:
        n = len(values)
        if n < 2:
            return 0.0
        xm = (n - 1) / 2.0
        ym = sum(values) / n
        num = sum((i - xm) * (v - ym) for i, v in enumerate(values))
        den = sum((i - xm) ** 2 for i in range(n))
        return num / den if den != 0 else 0.0
