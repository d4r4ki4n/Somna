"""
session_scorer.py — Post-Session Effectiveness Scoring (Somna Bible Ch.6 §6.3)
=====================================================================
Computes a composite effectiveness score from accumulated EEG time-series
data after a session ends. Writes results to somna.db and returns a summary
string suitable for delivery via the agent's _say() mechanism.

All DB access goes through content_tools.somna_db — never import sqlite3 here.

Usage:
    from session_scorer import SessionScorer, SessionAnalyzer, generate_session_summary
    scorer  = SessionScorer()
    metrics = scorer.score_session(session_data)
    summary = generate_session_summary(metrics)
    # deliver summary via somna_agent._say()
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np

from content_tools import somna_db as _db

_ROOT = Path(__file__).parent.parent

# CalibrationManager — optional import; if missing, population ranges are used.
_cal: object = None
try:
    from eeg.calibration_manager import CalibrationManager as _CM
    _cal = _CM()
except Exception:
    pass


def _cal_threshold(metric: str, fallback: float) -> float:
    """Return personal calibrated threshold or population fallback."""
    if _cal is not None:
        return _cal.get_threshold(metric, fallback)  # type: ignore[union-attr]
    return fallback


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_composite_score(metrics: dict, weights: dict | None = None) -> float:
    """Compute a single 0–100 effectiveness score from component metrics.

    Weights emphasize depth and stability — the two metrics most directly
    tied to subjective session quality (Ed's "sinking" experience).
    SQI penalty halves the score at mean SQI = 0.35.
    """
    if weights is None:
        # Weights from Bible Ch.2 §2.6 §10 (Reese's implementation spec)
        weights = {
            "depth":          0.25,
            "entrainment":    0.25,
            "receptivity":    0.20,
            "stability":      0.15,
            "time_in_target": 0.10,
            "transition":     0.05,
        }

    # Depth: SEF95 lower is better.
    # After calibration: personal range (sef95_awake ceiling, sef95_deep floor).
    # Before calibration: population range 4–22 Hz.
    depth_sef95 = metrics.get("depth_min_sef95")
    if depth_sef95 is not None:
        cal_complete = _cal is not None and getattr(_cal, "calibration_complete", False)
        if cal_complete:
            ceiling = _cal_threshold("sef95_awake", 22.0)   # type: ignore[arg-type]
            floor   = _cal_threshold("sef95_deep",   4.0)
        else:
            ceiling = 22.0
            floor   =  4.0
        span       = max(ceiling - floor, 1.0)
        depth_norm = _clamp((ceiling - depth_sef95) / span, 0.0, 1.0)
    else:
        depth_norm = 0.0

    target_norm = _clamp((metrics.get("time_in_target_pct") or 0.0) / 100.0, 0.0, 1.0)

    entrain_norm = _clamp(metrics.get("entrainment_mean_assr") or 0.0, 0.0, 1.0)

    tsec = metrics.get("transition_speed_sec")
    trans_norm = (1.0 - _clamp((tsec or 0.0) / 1800.0, 0.0, 1.0)
                  if tsec is not None else 0.0)

    std = metrics.get("stability_sef95_std")
    stab_norm  = (1.0 - _clamp((std or 0.0) / 5.0, 0.0, 1.0)
                  if std is not None else 0.5)

    recep_norm = _clamp((metrics.get("receptivity_approach_pct") or 0.0) / 100.0, 0.0, 1.0)

    raw = (
        weights["depth"]          * depth_norm +
        weights["time_in_target"] * target_norm +
        weights["entrainment"]    * entrain_norm +
        weights["transition"]     * trans_norm +
        weights["stability"]      * stab_norm +
        weights["receptivity"]    * recep_norm
    )

    # SQI penalty — noisy sessions get a lower composite
    sqi_factor = _clamp((metrics.get("signal_quality_mean") or 0.7) / 0.7, 0.0, 1.0)

    return round(raw * sqi_factor * 100.0, 1)


def generate_session_summary(metrics: dict) -> str:
    """Generate a brief, aphantasia-safe spoken summary for post-session delivery.

    Somatic/factual framing only. No imagery language.
    """
    score      = metrics.get("composite_score") or 0.0
    depth      = metrics.get("depth_min_sef95")
    target_pct = metrics.get("time_in_target_pct") or 0.0
    assr_mean  = metrics.get("entrainment_mean_assr") or 0.0
    duration   = metrics.get("duration_sec") or 0

    mins = duration // 60

    if assr_mean > 0.7:   entrain_label = "strong"
    elif assr_mean > 0.5: entrain_label = "solid"
    elif assr_mean > 0.3: entrain_label = "moderate"
    else:                 entrain_label = "light"

    if score >= 80:   score_comment = "Excellent session."
    elif score >= 60: score_comment = "Good session."
    elif score >= 40: score_comment = "Decent session — room to settle deeper next time."
    else:             score_comment = "Light session. That's fine — depth varies naturally."

    depth_str = f"You reached {depth:.1f} Hz at your deepest. " if depth else ""
    summary = (
        f"Session complete — {mins} minutes. "
        f"{depth_str}"
        f"Spent {target_pct:.0f}% of the session in your target state. "
        f"Entrainment was {entrain_label}. "
        f"Score: {score:.0f} out of 100. {score_comment}"
    )
    return summary


# ── SessionScorer ─────────────────────────────────────────────────────────────

class SessionScorer:
    """Computes and stores post-session effectiveness metrics.

    Called once when a session ends. Pass the dict returned by
    EEGEngine.get_session_data_for_scoring() as ``session_data``.
    """

    def score_session(self, session_data: dict) -> dict:
        """Compute all metrics and write to somna.db.

        session_data expected keys:
            sef95_series:        list[float]
            assr_series:         list[float]
            faa_series:          list[float]
            sqi_series:          list[float]
            affirmation_windows: list[tuple[int,int]]  (start_idx, end_idx)
            target_band:         tuple[float, float]   (low, high Hz)
            session_id:          str
            session_preset:      str
            duration_sec:        int
            config_snapshot:     dict
            freq_lead_data:      dict
        """
        sef95  = np.array(session_data.get("sef95_series") or [], dtype=float)
        assr   = np.array(session_data.get("assr_series")  or [], dtype=float)
        faa    = np.array(session_data.get("faa_series")   or [], dtype=float)
        sqi    = np.array(session_data.get("sqi_series")   or [], dtype=float)
        target_low, target_high = session_data.get("target_band", (0.0, 8.0))
        aff_windows = session_data.get("affirmation_windows") or []
        cal_skip    = 120  # skip first 2 min calibration

        sef95_active = sef95[cal_skip:] if len(sef95) > cal_skip else sef95

        m: dict = {}

        # ── Depth ──
        m["depth_min_sef95"]  = float(np.min(sef95_active))  if len(sef95_active) else None
        m["depth_mean_sef95"] = float(np.mean(sef95_active)) if len(sef95_active) else None

        # ── Time in target ──
        if len(sef95_active):
            in_target = (sef95_active >= target_low) & (sef95_active <= target_high)
            m["time_in_target_sec"] = int(np.sum(in_target))
            m["time_in_target_pct"] = round(100.0 * float(np.mean(in_target)), 1)
        else:
            m["time_in_target_sec"] = 0
            m["time_in_target_pct"] = 0.0

        # ── Transition speed ──
        if len(sef95_active):
            idxs = np.where(sef95_active <= target_high)[0]
            m["transition_speed_sec"] = int(idxs[0]) + cal_skip if len(idxs) else None
        else:
            m["transition_speed_sec"] = None

        # ── Stability (std after first target entry) ──
        if m["transition_speed_sec"] is not None and len(sef95_active):
            first = m["transition_speed_sec"] - cal_skip
            sustain = sef95_active[first:]
            m["stability_sef95_std"] = float(np.std(sustain)) if len(sustain) > 1 else 0.0
        else:
            m["stability_sef95_std"] = None

        # ── Entrainment ──
        m["entrainment_mean_assr"] = float(np.mean(assr)) if len(assr) else 0.0
        m["entrainment_peak_assr"] = float(np.max(assr))  if len(assr) else 0.0
        m["entrainment_lock_pct"]  = round(100.0 * float(np.mean(assr > 0.6)), 1) if len(assr) else 0.0

        # ── Receptivity during affirmation windows ──
        if len(faa) and aff_windows:
            aff_faa = []
            for s, e in aff_windows:
                if s < len(faa) and e <= len(faa):
                    aff_faa.extend(faa[s:e].tolist())
            if aff_faa:
                arr = np.array(aff_faa)
                m["receptivity_mean_faa"]    = float(np.mean(arr))
                m["receptivity_approach_pct"] = round(100.0 * float(np.mean(arr > 0.1)), 1)
            else:
                m["receptivity_mean_faa"]    = 0.0
                m["receptivity_approach_pct"] = 0.0
        else:
            m["receptivity_mean_faa"]    = (float(np.mean(faa)) if len(faa) else 0.0)
            # Fallback: whole-session FAA receptivity if no windows tagged
            m["receptivity_approach_pct"] = (
                round(100.0 * float(np.mean(faa > 0.1)), 1) if len(faa) else 0.0
            )

        # ── Signal quality ──
        m["signal_quality_mean"]        = float(np.mean(sqi)) if len(sqi) else 0.0
        m["signal_quality_dropout_pct"] = round(100.0 * float(np.mean(sqi < 0.5)), 1) if len(sqi) else 100.0

        # ── Composite ──
        m["composite_score"] = compute_composite_score(m)

        # ── Persist ──
        row = {
            **m,
            "session_id":    session_data.get("session_id"),
            "session_date":  datetime.now().isoformat(timespec="seconds"),
            "session_preset": session_data.get("session_preset"),
            "duration_sec":  session_data.get("duration_sec"),
            "target_band":   (target_low, target_high),
            "config_snapshot": session_data.get("config_snapshot", {}),
            "freq_lead_data":  session_data.get("freq_lead_data", {}),
        }
        try:
            _db.write_session_metrics(row)
        except Exception as e:
            print(f"[Scorer] DB write failed: {e}")

        return m


# ── SessionAnalyzer ───────────────────────────────────────────────────────────

class SessionAnalyzer:
    """Queries session_metrics for longitudinal patterns.

    Called by the agent during idle periods or at session start to inform
    configuration choices for auto-optimization (Bible Ch.6 §6.3 §7).
    """

    def get_recent_scores(self, n: int = 20) -> list[dict]:
        return _db.get_session_metrics(n)

    def best_config_for_preset(self, preset: str, top_n: int = 5) -> dict:
        return _db.best_config_for_preset(preset, top_n)

    def trend(self, metric: str = "composite_score", n: int = 20) -> dict:
        return _db.trend_metric(metric, n)

    def optimization_recommendation(self, preset: str) -> dict | None:
        """Return a 1–2 parameter change recommendation if data warrants it.

        Returns None if fewer than 10 sessions exist for this preset.
        """
        recent = self.get_recent_scores(20)
        preset_sessions = [r for r in recent
                           if r.get("session_preset") == preset
                           and (r.get("signal_quality_mean") or 0) > 0.5]
        if len(preset_sessions) < 10:
            return None

        cfg = self.best_config_for_preset(preset, top_n=5)
        if not cfg or not cfg.get("sample_size"):
            return None

        # Current session's most recent config (latest row for this preset)
        latest = next((r for r in recent if r.get("session_preset") == preset), None)
        if not latest:
            return None

        changes = {}
        if (cfg.get("recommended_veil_mode") and latest.get("veil_mode_primary")
                and cfg["recommended_veil_mode"] != latest["veil_mode_primary"]):
            changes["veil_mode"] = cfg["recommended_veil_mode"]

        if (cfg.get("recommended_spiral_style") and latest.get("spiral_style")
                and cfg["recommended_spiral_style"] != latest["spiral_style"]):
            changes["spiral_style"] = cfg["recommended_spiral_style"]

        if (cfg.get("recommended_beat_type") and latest.get("beat_type")
                and cfg["recommended_beat_type"] != latest["beat_type"]):
            changes["beat_type"] = cfg["recommended_beat_type"]

        if not changes:
            return None

        # Keep max 2 changes — prioritise beat_type (audio quality) over visual params
        priority = ["beat_type", "veil_mode", "spiral_style"]
        ordered  = sorted(changes.items(), key=lambda kv: priority.index(kv[0])
                          if kv[0] in priority else len(priority))
        items    = ordered[:2]
        return {
            "changes":      dict(items),
            "avg_score":    cfg.get("avg_score"),
            "sample_size":  cfg.get("sample_size"),
            "rationale":    (f"Top {cfg['sample_size']} sessions for '{preset}' "
                             f"averaged {cfg['avg_score']:.1f} points."),
        }
