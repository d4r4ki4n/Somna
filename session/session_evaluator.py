"""
session/session_evaluator.py — Post-session learning (Bible Ch.5 §5.5 §9)
=================================================================
Runs after each session ends.  Scores the session across six
components, evaluates each logged Director decision, updates the
user model in the DB, and writes session_history + decision outcome
records.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from session.session_director import (
    DecisionRecord,
    SessionLog,
    SessionPlan,
    ConditioningDelta,
    _clamp,
    DECISION_POSITIVE_THRESHOLD,
)
from session.session_planner import UserProfile


# ── Evaluation weights ────────────────────────────────────────────────────────

EVAL_W_DEPTH        = 0.30
EVAL_W_CONDITIONING = 0.20
EVAL_W_ADHERENCE    = 0.15
EVAL_W_EFFICIENCY   = 0.15
EVAL_W_STABILITY    = 0.10
EVAL_W_EMERGENCE    = 0.10

# Induction threshold for preferred_induction update
INDUCTION_GOOD_THRESHOLD = 0.65

# Exponential moving average alpha for user profile updates
PROFILE_EMA_ALPHA = 0.3


# ── Output data structures ────────────────────────────────────────────────────

@dataclass
class ScoredDecision:
    decision:      DecisionRecord
    outcome_score: float   # -1.0, 0.0, or 1.0


@dataclass
class SessionOutcome:
    session_id:             str
    session_score:          float
    depth_score:            float
    conditioning_score:     float
    plan_adherence_score:   float
    efficiency_score:       float
    stability_score:        float
    emergence_score:        float
    scored_decisions:       list[ScoredDecision]
    outcome_notes:          str = ""


# ── SessionEvaluator ──────────────────────────────────────────────────────────

class SessionEvaluator:
    """
    Post-session scoring and user model update (Bible Ch.5 §5.5 §9).

    Usage:
        evaluator = SessionEvaluator(db=somna_db)
        outcome   = evaluator.evaluate(session_plan, session_log)
    """

    def __init__(self, db) -> None:
        self.db = db

    def evaluate(
        self,
        session_plan: SessionPlan,
        session_log:  SessionLog,
    ) -> SessionOutcome:
        """Score the session, update user profile, write DB records."""
        try:
            profile = self._load_user_profile()
        except Exception:
            profile = UserProfile.create_default()

        depth        = self._score_depth(session_log)
        conditioning = self._score_conditioning(session_log)
        adherence    = self._score_plan_adherence(session_plan, session_log)
        efficiency   = self._score_efficiency(session_log, profile)
        stability    = self._score_stability(session_log)
        emergence    = self._score_emergence(session_log)

        composite = _clamp(
            EVAL_W_DEPTH        * depth
            + EVAL_W_CONDITIONING * conditioning
            + EVAL_W_ADHERENCE  * adherence
            + EVAL_W_EFFICIENCY * efficiency
            + EVAL_W_STABILITY  * stability
            + EVAL_W_EMERGENCE  * emergence,
            0.0, 1.0,
        )

        scored_decisions = self._evaluate_decisions(
            session_log.decisions, session_log.trance_score_timeseries
        )
        notes = self._generate_outcome_notes(composite, depth, stability)

        outcome = SessionOutcome(
            session_id=session_plan.session_id,
            session_score=composite,
            depth_score=depth,
            conditioning_score=conditioning,
            plan_adherence_score=adherence,
            efficiency_score=efficiency,
            stability_score=stability,
            emergence_score=emergence,
            scored_decisions=scored_decisions,
            outcome_notes=notes,
        )

        try:
            self._update_user_profile(profile, session_plan, session_log, composite)
            self._write_session_record(session_plan, session_log, outcome)
        except Exception:
            pass   # never block a session end on evaluator failure

        return outcome

    # ── Component scorers ─────────────────────────────────────────────────────

    def _score_depth(self, log: SessionLog) -> float:
        ts    = log.trance_score_timeseries or []
        total = len(ts) or 1
        time_light  = sum(1 for t in ts if 0.2 <= t < 0.4)
        time_medium = sum(1 for t in ts if 0.4 <= t < 0.6)
        time_deep   = sum(1 for t in ts if t >= 0.6)
        raw = (0.2 * time_light + 0.5 * time_medium + 1.0 * time_deep) / total
        return _clamp(raw, 0.0, 1.0)

    def _score_conditioning(self, log: SessionLog) -> float:
        if not log.conditioning_deltas:
            return 0.5   # neutral when no conditioning targeted
        deltas = [d.post_strength - d.pre_strength for d in log.conditioning_deltas]
        positive = sum(max(0.0, d) for d in deltas)
        max_possible = max(len(deltas), 1)
        return _clamp(positive / max_possible, 0.0, 1.0)

    def _score_plan_adherence(
        self, plan: SessionPlan, log: SessionLog,
    ) -> float:
        deviations = []
        for planned, actual in zip(plan.phase_plan, log.phase_durations):
            if planned.target_duration_s > 0:
                dev = abs(actual - planned.target_duration_s) / planned.target_duration_s
                deviations.append(dev)
        if not deviations:
            return 1.0
        mean_dev = sum(deviations) / len(deviations)
        return _clamp(1.0 - mean_dev, 0.0, 1.0)

    def _score_efficiency(self, log: SessionLog, profile: UserProfile) -> float:
        if log.time_to_peak_s <= 0 or profile.avg_time_to_peak_s <= 0:
            return 0.5
        return _clamp(profile.avg_time_to_peak_s / log.time_to_peak_s, 0.0, 1.0)

    def _score_stability(self, log: SessionLog) -> float:
        scores = log.trance_scores_during_work
        if len(scores) < 10:
            return 0.5
        mean_s = sum(scores) / len(scores)
        variance = sum((s - mean_s) ** 2 for s in scores) / len(scores)
        return _clamp(1.0 - variance * 10.0, 0.0, 1.0)

    def _score_emergence(self, log: SessionLog) -> float:
        hr_ok   = log.emergence_hr_deviation < 0.10
        depth_ok = log.final_trance_score < 0.1
        planned  = max(1, log.planned_emergence_duration_s)
        timely   = log.emergence_duration_s <= planned * 1.5
        return 0.4 * float(hr_ok) + 0.4 * float(depth_ok) + 0.2 * float(timely)

    # ── Decision evaluation ───────────────────────────────────────────────────

    def _evaluate_decisions(
        self,
        decisions: list[DecisionRecord],
        timeseries: list[float],
    ) -> list[ScoredDecision]:
        scored: list[ScoredDecision] = []
        for d in decisions:
            if d.authority_level < 1:
                continue
            # Approximate index in timeseries from timestamp offset
            session_start = timeseries[0] if timeseries else 0.0
            t_idx = max(0, int(d.timestamp - (session_start or d.timestamp)))

            pre_window  = timeseries[max(0, t_idx - 120): t_idx]
            post_window = timeseries[t_idx: min(len(timeseries), t_idx + 120)]

            pre_slope  = self._linreg_slope(pre_window)
            post_slope = self._linreg_slope(post_window)
            delta = post_slope - pre_slope

            if delta >= DECISION_POSITIVE_THRESHOLD:
                score = 1.0
            elif delta <= -DECISION_POSITIVE_THRESHOLD:
                score = -1.0
            else:
                score = 0.0

            scored.append(ScoredDecision(decision=d, outcome_score=score))
        return scored

    # ── User model update ─────────────────────────────────────────────────────

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
        return UserProfile.create_default()

    def _update_user_profile(
        self,
        profile:      UserProfile,
        plan:         SessionPlan,
        log:          SessionLog,
        composite:    float,
    ) -> None:
        a = PROFILE_EMA_ALPHA
        profile.sessions_completed   += 1
        profile.total_session_time_s += log.duration_s
        profile.last_session_at       = log.started_at

        profile.avg_peak_depth = (
            a * log.achieved_peak_depth + (1 - a) * profile.avg_peak_depth
        )
        profile.max_achieved_depth = max(
            profile.max_achieved_depth, log.achieved_peak_depth
        )

        # Update preferred arc if this one scored better
        last_preferred_score = getattr(profile, "_last_preferred_arc_score", 0.0)
        if log.arc_template != profile.preferred_arc and composite > last_preferred_score:
            profile.preferred_arc = log.arc_template

        # Update preferred induction
        if log.induction_effectiveness > INDUCTION_GOOD_THRESHOLD:
            profile.preferred_induction = log.induction_strategy

        # Update timing averages
        if log.time_to_induction_s > 0:
            profile.avg_time_to_induction_s = (
                a * log.time_to_induction_s + (1 - a) * profile.avg_time_to_induction_s
            )
        if log.time_to_peak_s > 0:
            profile.avg_time_to_peak_s = (
                a * log.time_to_peak_s + (1 - a) * profile.avg_time_to_peak_s
            )

        profile.updated_at = time.time()
        try:
            self.db.save_director_profile(vars(profile))
        except Exception:
            pass

    # ── DB write ──────────────────────────────────────────────────────────────

    def _write_session_record(
        self,
        plan:    SessionPlan,
        log:     SessionLog,
        outcome: SessionOutcome,
    ) -> None:
        record = {
            "session_id":                       plan.session_id,
            "started_at":                       log.started_at,
            "ended_at":                         log.ended_at,
            "duration_s":                       log.duration_s,
            "arc_template":                     plan.arc_template,
            "session_goal":                     plan.session_goal,
            "target_peak_depth":                plan.target_peak_depth,
            "achieved_peak_depth":              log.achieved_peak_depth,
            "avg_depth":                        log.avg_depth,
            "time_in_deep_s":                   log.time_in_deep_s,
            "depth_trajectory_score":           log.depth_trajectory_score,
            "induction_strategy":               log.induction_strategy,
            "induction_effectiveness":          log.induction_effectiveness,
            "conditioning_reinforcement_score": outcome.conditioning_score,
            "plan_adherence":                   outcome.plan_adherence_score,
            "director_redirects":               log.redirect_count,
            "intensity_cycles_completed":       log.intensity_cycles_completed,
            "pace_confidence_final":            log.pace_confidence_final,
            "user_satisfaction":                log.user_satisfaction,
            "outcome_notes":                    outcome.outcome_notes,
        }
        try:
            self.db.insert_session_history(record)
        except Exception:
            pass

        # Update outcome_score on each logged decision
        for sd in outcome.scored_decisions:
            try:
                self.db.update_decision_outcome(
                    sd.decision.decision_id, sd.outcome_score
                )
            except Exception:
                pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _generate_outcome_notes(
        self, composite: float, depth: float, stability: float
    ) -> str:
        label = (
            "Excellent session."  if composite >= 0.8 else
            "Strong session."    if composite >= 0.65 else
            "Moderate session."  if composite >= 0.5 else
            "Light session."
        )
        depth_note = (
            "Good depth achieved." if depth >= 0.6 else
            "Moderate depth." if depth >= 0.35 else
            "Shallow — depth work recommended next session."
        )
        stability_note = (
            "Very stable WORK phase." if stability >= 0.7 else
            "Some variability during WORK." if stability >= 0.45 else
            "WORK phase was unstable — check environmental factors."
        )
        return f"{label} {depth_note} {stability_note}"

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
