"""
calibration_manager.py — First-10-Sessions Calibration Protocol (Somna Bible Ch.2 §2.6)
==============================================================================
Sits between eeg_engine, conductor, and session_scorer as a threshold lookup
layer.  Before any personal calibration data exists, every call to
get_threshold(metric, fallback) returns the fallback — zero regression risk.
Once calibration sessions provide personal neurophysiological measurements,
the fallback is replaced by the actual measured value.

Integration pattern (everywhere a hardcoded threshold currently exists):

    # Before:
    if trance_score > 0.65:

    # After:
    if trance_score > cal.get_threshold("trance_moderate", 0.65):

The CalibrationManager is instantiated once and shared across conductor and
session_scorer. DB path defaults to the project-root somna.db.
"""
from __future__ import annotations

import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent

# Population-level fallback values (from Bible Ch.2 §2.6 — only used until personal
# measurements replace them).
_POPULATION_DEFAULTS: dict[str, float] = {
    "iaf":                    10.0,   # Hz — population mean
    "sef95_awake":            22.0,   # Hz — eyes-closed resting
    "sef95_light":            18.0,   # Hz — light trance
    "sef95_moderate":         15.0,   # Hz — moderate trance (induction gate)
    "sef95_deep":             10.0,   # Hz — deep trance / maintenance
    "faa_approach":            0.0,   # FAA > 0 → approach state
    "faa_resting":             0.0,   # resting baseline FAA
    "assr_transition":         0.3,   # ASSR confidence threshold for gating
    "assr_strong":             0.6,   # strong entrainment lock
    "spectral_slope_awake":   -1.8,   # 1/f exponent at rest
    "spectral_slope_trance":  -2.4,   # 1/f exponent in trance
    # trance_score thresholds (0–1 composite, SEF95-derived)
    "trance_light":            0.40,
    "trance_moderate":         0.65,
    "trance_deep":             0.80,
    "trance_frac_eligible":    0.50,
    "trance_sleep_approach":   0.60,
}

# Phase names the conductor uses
_PHASE_ORDER = [
    "CALIBRATION", "INDUCTION", "DEEPENING",
    "MAINTENANCE",
    "FRAC_EMERGE", "FRAC_EMERGE_HOLD", "FRAC_REDROP",
    "SLEEP_APPROACH", "SESSION_END",
]

# Per calibration-phase: which conductor phases are permitted
_PHASE_ALLOWLIST: dict[str, Optional[list[str]]] = {
    "baseline":    ["CALIBRATION"],
    "subsystem":   ["CALIBRATION", "INDUCTION"],
    "integration": ["CALIBRATION", "INDUCTION", "DEEPENING", "MAINTENANCE",
                    "FRAC_EMERGE", "FRAC_EMERGE_HOLD", "FRAC_REDROP"],
    "closed_loop": None,   # None = all phases allowed
}

# Session-number → calibration phase + expanded allowlist for sessions 5–6
def _phase_for_session(n: int) -> str:
    if n <= 2:  return "baseline"
    if n <= 6:  return "subsystem"
    if n <= 8:  return "integration"
    return "closed_loop"


class CalibrationManager:
    """Manages the first-10-sessions calibration protocol.

    Reads/writes calibration tables in somna.db via content_tools.somna_db.
    Exposes get_threshold() as the primary API for conductor and session_scorer.
    """

    CALIBRATION_SESSIONS_REQUIRED = 10

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or (_ROOT / "somna.db")
        # Ensure tables exist by touching the DB through somna_db
        from content_tools import somna_db as _db
        _db._connect()  # triggers _init_db which runs PRAGMA + CREATE IF NOT EXISTS
        self._db = _db
        self._cache: dict[str, float] = {}
        self._load_cache()

    # ── Core API ─────────────────────────────────────────────────────────────

    def get_threshold(self, metric: str, fallback: float) -> float:
        """Return personal threshold if calibrated, else fallback.

        This is the primary integration point — a drop-in replacement for
        every hardcoded numeric threshold in conductor.py and session_scorer.py.
        """
        return self._cache.get(metric, fallback)

    @property
    def calibration_complete(self) -> bool:
        """True when all 10 sessions are logged and final thresholds derived."""
        sessions = self._db.cal_get_sessions()
        completed = [s for s in sessions if s.get("completed_at")]
        return len(completed) >= self.CALIBRATION_SESSIONS_REQUIRED

    @property
    def current_session_number(self) -> int:
        """Next calibration session to run (1–10), or 11+ if complete."""
        sessions = self._db.cal_get_sessions()
        completed = [s for s in sessions if s.get("completed_at")]
        return len(completed) + 1

    @property
    def sessions_completed(self) -> int:
        sessions = self._db.cal_get_sessions()
        return len([s for s in sessions if s.get("completed_at")])

    # ── Protocol configuration ────────────────────────────────────────────────

    def get_session_protocol(self) -> dict:
        """Return protocol config for the current calibration session.

        Returned dict keys match the interface in Bible Ch.2 §2.6 §2.1.
        """
        n = self.current_session_number
        if n > self.CALIBRATION_SESSIONS_REQUIRED:
            return {
                "session_number":        n,
                "phase":                 "complete",
                "max_conductor_phase":   None,
                "enable_affirmations":   True,
                "enable_adaptive_leading": True,
                "enable_fractionation":  True,
                "duration_minutes":      None,
                "focus_metrics":         [],
                "post_session_queries":  [],
            }

        phase = _phase_for_session(n)

        # Duration + features unlock per session
        if n <= 2:
            duration        = 15
            enable_aff      = False
            enable_lead     = False
            enable_frac     = False
            focus           = ["iaf", "sef95", "faa", "alpha_power", "sqi_mean"]
            post_queries    = ["baseline_report"]
            max_phase       = "CALIBRATION"
        elif n <= 4:
            duration        = 20
            enable_aff      = False
            enable_lead     = False
            enable_frac     = False
            focus           = ["assr_strength", "assr_confidence", "sqi_mean"]
            post_queries    = ["assr_report"]
            max_phase       = "INDUCTION"
        elif n <= 6:
            duration        = 30
            enable_aff      = True
            enable_lead     = False
            enable_frac     = False
            focus           = ["sef95", "trance_score", "faa", "assr_strength"]
            post_queries    = ["session_metrics_report"]
            max_phase       = "MAINTENANCE"
        elif n <= 8:
            duration        = 40
            enable_aff      = True
            enable_lead     = True
            enable_frac     = True
            focus           = ["sef95", "trance_score", "faa", "assr_strength",
                               "fractionation_cycles"]
            post_queries    = ["session_metrics_report", "threshold_update_report"]
            max_phase       = "FRAC_REDROP"
        else:  # 9–10
            duration        = None  # full session duration
            enable_aff      = True
            enable_lead     = True
            enable_frac     = True
            focus           = ["composite_score", "depth_min_sef95",
                               "entrainment_mean_assr", "receptivity_approach_pct"]
            post_queries    = ["full_session_report", "trend_report"]
            max_phase       = None

        return {
            "session_number":          n,
            "phase":                   phase,
            "max_conductor_phase":     max_phase,
            "enable_affirmations":     enable_aff,
            "enable_adaptive_leading": enable_lead,
            "enable_fractionation":    enable_frac,
            "duration_minutes":        duration,
            "focus_metrics":           focus,
            "post_session_queries":    post_queries,
        }

    def can_transition_to(self, target_phase: str) -> bool:
        """Return True if the conductor is allowed to enter target_phase.

        Used in conductor.py as a gate before every phase transition during
        the calibration period.  After calibration_complete, always True.
        """
        if self.calibration_complete:
            return True

        protocol = self.get_session_protocol()
        n     = protocol["session_number"]
        phase = protocol["phase"]

        # Sessions 5–6 are 'subsystem' in the table but unlock through MAINTENANCE
        if phase == "subsystem" and n in (5, 6):
            allowed = ["CALIBRATION", "INDUCTION", "DEEPENING", "MAINTENANCE"]
        else:
            allowed = _PHASE_ALLOWLIST.get(phase)

        if allowed is None:
            return True
        return target_phase.upper() in allowed

    # ── Data logging ──────────────────────────────────────────────────────────

    def log_baseline(
        self,
        metric: str,
        value: float,
        condition: str,
        session: int | None = None,
        channel: str | None = None,
        sd: float | None = None,
        n_samples: int | None = None,
        sqi_mean: float | None = None,
    ) -> None:
        """Record a resting baseline measurement."""
        n = session if session is not None else self.current_session_number
        self._db.cal_upsert_baseline(
            session_number=n, metric=metric, condition=condition,
            value=value, channel=channel, sd=sd,
            n_samples=n_samples, sqi_mean=sqi_mean,
        )

    def log_session_complete(
        self,
        session_number: int | None = None,
        notes: str = "",
        max_phase_reached: str = "",
        started_at: str = "",
        duration_seconds: float | None = None,
    ) -> dict[str, float]:
        """Mark a calibration session as complete and derive thresholds."""
        n = session_number if session_number is not None else self.current_session_number
        phase = _phase_for_session(n)

        new_thresholds = self.derive_thresholds(through_session=n)
        thresholds_json = json.dumps(new_thresholds)

        self._db.cal_log_session(
            session_number   = n,
            phase            = phase,
            started_at       = started_at or time.strftime("%Y-%m-%dT%H:%M:%S"),
            completed_at     = time.strftime("%Y-%m-%dT%H:%M:%S"),
            duration_seconds = duration_seconds,
            max_phase_reached= max_phase_reached,
            notes            = notes,
            thresholds_json  = thresholds_json,
        )
        self._load_cache()
        return new_thresholds

    def log_assr_curve_point(
        self,
        frequency_hz: float,
        assr_strength: float,
        hold_duration_s: float,
        sqi_mean: float | None = None,
        session_number: int | None = None,
    ) -> None:
        n = session_number if session_number is not None else self.current_session_number
        self._db.cal_append_assr_curve(
            session_number=n, frequency_hz=frequency_hz,
            assr_strength=assr_strength, hold_duration_s=hold_duration_s,
            sqi_mean=sqi_mean,
        )

    # ── Threshold derivation ─────────────────────────────────────────────────

    def derive_thresholds(self, through_session: int) -> dict[str, float]:
        """Compute personal thresholds from all data through `through_session`.

        Each metric uses the derivation method appropriate to its role:
        - Resting baselines (IAF, SEF95_awake, FAA): mean of eyes-closed windows
        - Depth thresholds: derived from session_metrics percentiles
        - ASSR thresholds: from calibration_assr_curve
        """
        thresholds: dict[str, float] = {}

        # ── IAF, SEF95_awake, spectral_slope_awake ────────────────────────────
        # Available from sessions 1-2 (eyes_closed condition)
        for metric, cal_key, method in [
            ("iaf",             "iaf",               "mean_ec"),
            ("sef95",           "sef95_awake",        "mean_ec"),
            ("spectral_slope",  "spectral_slope_awake", "mean_ec"),
        ]:
            rows = self._db.cal_get_baselines(metric=metric, condition="eyes_closed")
            vals = [r["value"] for r in rows
                    if r["session_number"] <= through_session
                    and (r.get("sqi_mean") or 0) >= 0.5]
            if len(vals) >= 1:
                thresholds[cal_key] = round(statistics.mean(vals), 3)

        # ── FAA resting ────────────────────────────────────────────────────────
        rows = self._db.cal_get_baselines(metric="faa", condition="eyes_closed")
        vals = [r["value"] for r in rows if r["session_number"] <= through_session]
        if vals:
            thresholds["faa_resting"] = round(statistics.mean(vals), 4)
            # Approach = resting + 0.1 SD above mean (conservative)
            if len(vals) >= 2:
                try:
                    sd = statistics.stdev(vals)
                    thresholds["faa_approach"] = round(statistics.mean(vals) + 0.1 * sd, 4)
                except statistics.StatisticsError:
                    pass

        # ── Alpha reactivity ratio ─────────────────────────────────────────────
        ec_rows = self._db.cal_get_baselines(metric="alpha_power", condition="eyes_closed")
        eo_rows = self._db.cal_get_baselines(metric="alpha_power", condition="eyes_open")
        ec_vals = [r["value"] for r in ec_rows if r["session_number"] <= through_session]
        eo_vals = [r["value"] for r in eo_rows if r["session_number"] <= through_session]
        if ec_vals and eo_vals:
            ratio = statistics.mean(ec_vals) / max(statistics.mean(eo_vals), 1e-9)
            thresholds["alpha_reactivity_ratio"] = round(ratio, 3)

        # ── ASSR thresholds (from calibration_assr_curve, sessions 3-4+) ──────
        if through_session >= 3:
            curve = self._db.cal_get_assr_curve()
            curve = [p for p in curve if p["session_number"] <= through_session
                     and (p.get("sqi_mean") or 0) >= 0.4]
            if curve:
                strengths = sorted([p["assr_strength"] for p in curve])
                if strengths:
                    n = len(strengths)
                    thresholds["assr_transition"] = round(
                        strengths[max(0, int(n * 0.25))], 3)   # p25
                    thresholds["assr_strong"]     = round(
                        strengths[max(0, int(n * 0.60))], 3)   # p60

        # ── SEF95 trance range (from session_metrics, sessions 5+) ────────────
        if through_session >= 5:
            thresholds.update(self._derive_sef95_trance_thresholds(through_session))

        # Persist each derived threshold
        completed_str = ",".join(str(i) for i in range(1, through_session + 1))
        confidence = (
            "provisional" if through_session <= 4 else
            "moderate"    if through_session <= 8 else
            "final"
        )
        for metric, value in thresholds.items():
            method_key = {
                "iaf":               "mean_ec",
                "sef95_awake":       "mean_ec",
                "faa_resting":       "mean_ec",
                "faa_approach":      "mean_ec_plus_0.1sd",
                "assr_transition":   "p25_curve",
                "assr_strong":       "p60_curve",
                "sef95_light":       "p25_session",
                "sef95_moderate":    "p50_session",
                "sef95_deep":        "p10_session",
            }.get(metric, "mean")
            self._db.cal_upsert_threshold(
                metric=metric, value=value,
                derived_from_sessions=completed_str,
                derivation_method=method_key,
                confidence=confidence,
            )

        return thresholds

    def _derive_sef95_trance_thresholds(self, through_session: int) -> dict[str, float]:
        """Derive personal SEF95 depth thresholds from session_metrics rows."""
        from content_tools import somna_db as db
        try:
            rows = db.get_session_metrics(recent_n=50)
        except Exception:
            return {}

        sef_min_vals = [r["depth_min_sef95"] for r in rows
                        if r.get("depth_min_sef95") is not None]
        sef_mean_vals = [r["depth_mean_sef95"] for r in rows
                         if r.get("depth_mean_sef95") is not None]
        if not sef_min_vals:
            return {}

        sef_min_sorted  = sorted(sef_min_vals)
        sef_mean_sorted = sorted(sef_mean_vals) if sef_mean_vals else sef_min_sorted

        n = len(sef_min_sorted)
        out: dict[str, float] = {}
        # sef95_light = p75 of mean_sef95 (you're usually in light range)
        out["sef95_light"]    = round(sef_mean_sorted[max(0, int(n * 0.75))], 2)
        # sef95_moderate = median of mean_sef95
        out["sef95_moderate"] = round(statistics.median(sef_mean_sorted), 2)
        # sef95_deep = p10 of min_sef95 (deep excursions)
        out["sef95_deep"]     = round(sef_min_sorted[max(0, int(n * 0.10))], 2)

        # Derive trance_score thresholds proportionally from sef95 range
        awake = self._cache.get("sef95_awake", 22.0)
        deep  = out["sef95_deep"]
        span  = max(awake - deep, 1.0)
        out["trance_light"]        = round(1.0 - (out["sef95_light"]    - deep) / span, 3)
        out["trance_moderate"]     = round(1.0 - (out["sef95_moderate"] - deep) / span, 3)
        out["trance_deep"]         = round(1.0 - max((deep + 1.0        - deep) / span, 0), 3)
        out["trance_frac_eligible"]= round(max(0.3, out["trance_moderate"] - 0.15), 3)
        out["trance_sleep_approach"]= round(out["trance_moderate"] - 0.05, 3)

        return out

    # ── Recalibration detection ───────────────────────────────────────────────

    def needs_recalibration(self, current_board_id: int | None = None) -> bool:
        """True if recalibration is recommended.

        Triggers: hardware change, 90+ days since calibration,
        or 20-session metric drift > 2 SD.
        """
        if not self.calibration_complete:
            return False

        sessions = self._db.cal_get_sessions()
        completed = [s for s in sessions if s.get("completed_at")]
        if not completed:
            return False
        last_cal = completed[-1]

        # Hardware change
        if current_board_id is not None:
            first = sessions[0] if sessions else {}
            notes = first.get("notes", "") or ""
            if f"board_id={current_board_id}" in notes or not notes:
                pass  # can't determine board from notes alone without extra tracking
            # Check via thresholds table metadata if board was stored
            thresholds = self._db.cal_get_thresholds()
            stored_board = thresholds.get("_board_id")
            if stored_board is not None and int(stored_board) != current_board_id:
                return True

        # Elapsed time
        try:
            cal_date = datetime.fromisoformat(last_cal["completed_at"])
            if (datetime.now() - cal_date).days > 90:
                return True
        except Exception:
            pass

        # Metric drift — requires 20+ post-calibration sessions
        try:
            recent = self._db.get_session_metrics(recent_n=20)
            if len(recent) < 20:
                return False
            for metric, col in [
                ("sef95_awake",  "depth_mean_sef95"),
                ("faa_resting",  "receptivity_mean_faa"),
            ]:
                cal_val = self._cache.get(metric)
                if cal_val is None:
                    continue
                vals = [r[col] for r in recent if r.get(col) is not None]
                if len(vals) < 10:
                    continue
                recent_mean = statistics.mean(vals)
                recent_sd   = statistics.stdev(vals)
                if recent_sd > 0 and abs(recent_mean - cal_val) > 2 * recent_sd:
                    return True
        except Exception:
            pass

        return False

    # ── State summary for agent context ──────────────────────────────────────

    def status_summary(self) -> str:
        """One-line status string for agent prompt injection."""
        n = self.sessions_completed
        if self.calibration_complete:
            t = self._cache
            return (
                f"Calibration complete ({self.CALIBRATION_SESSIONS_REQUIRED} sessions). "
                f"Personal thresholds active — "
                f"IAF={t.get('iaf', '?')} Hz, "
                f"SEF95_awake={t.get('sef95_awake', '?')} Hz, "
                f"SEF95_deep={t.get('sef95_deep', '?')} Hz, "
                f"trance_moderate={t.get('trance_moderate', '?')}."
            )
        protocol = self.get_session_protocol()
        next_n = protocol["session_number"]
        return (
            f"Calibration in progress: {n}/{self.CALIBRATION_SESSIONS_REQUIRED} sessions "
            f"complete. Next: Session {next_n} ({protocol['phase']} phase, "
            f"{protocol['duration_minutes']} min). "
            f"Population defaults active until personal thresholds derived."
        )

    def agent_constraints_summary(self) -> str:
        """Behavioral constraints for the current calibration session."""
        if self.calibration_complete:
            return ""
        p = self.get_session_protocol()
        n = p["session_number"]
        constraints = []
        if not p["enable_affirmations"]:
            constraints.append("affirmations DISABLED (baseline session)")
        if not p["enable_fractionation"]:
            constraints.append("fractionation DISABLED")
        if not p["enable_adaptive_leading"]:
            constraints.append("adaptive frequency leading DISABLED")
        if p["max_conductor_phase"]:
            constraints.append(f"conductor phase capped at {p['max_conductor_phase']}")
        if p["duration_minutes"]:
            constraints.append(f"session duration capped at {p['duration_minutes']} min")

        if not constraints:
            return ""
        return (f"CALIBRATION SESSION {n}/10 — constraints: "
                + "; ".join(constraints) + ".")

    # ── Private ───────────────────────────────────────────────────────────────

    def _load_cache(self) -> None:
        """Reload the threshold cache from DB."""
        self._cache = {}
        try:
            stored = self._db.cal_get_thresholds()
            self._cache.update(stored)
        except Exception:
            pass
