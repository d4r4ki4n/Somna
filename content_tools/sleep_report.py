"""
content_tools/sleep_report.py — Sleep session analysis for agent planning (Bible Ch.9 §9.1)

Aggregates sleep_stage_log, tmr_cue_registry, tmr_replay_log, and
sleep_training_log into a structured report.  Called by the agent's
sleep planning tick (_sleep_planning_tick in somna_agent.py) to select
the focus pool and under-reinforced phrases for the next HTW window.
Also surfaceable as a morning debrief.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from content_tools.somna_db import (
    get_sleep_stage_log_summary,
    get_tmr_cue_registry,
    get_tmr_replay_summary,
    get_sleep_training_log_summary,
)

# Minimum encoding count before a phrase is considered "adequately reinforced"
_ADEQUATE_ENCODING = 3

# TMR pool names in priority order for zero-data sessions
_ALL_POOLS = ["IDENTITY", "RELEASE", "POTENTIAL", "SOMATIC", "PURPOSE", "TRANSITION"]


def read_sleep_report(session_id: str) -> Dict[str, Any]:
    """Return an aggregated sleep session report for the given session.

    All values are safe to pass directly to the LLM — no raw bytes or
    large arrays.  Missing data fields default to zero / empty rather
    than raising.
    """
    if not session_id:
        return {"error": "session_id required"}

    try:
        stage_dist = get_sleep_stage_log_summary(session_id)
    except Exception:
        stage_dist = {}

    try:
        registry = get_tmr_cue_registry(session_id)
    except Exception:
        registry = []

    try:
        replay_by_pool = get_tmr_replay_summary(session_id)
    except Exception:
        replay_by_pool = {}

    try:
        htw_summary = get_sleep_training_log_summary(session_id)
    except Exception:
        htw_summary = {"htw_count": 0, "total_duration_s": 0.0, "success_rate": 0.0}

    # ── Stage totals ─────────────────────────────────────────────────────────
    elapsed_sleep_s = sum(stage_dist.get(s, 0)
                          for s in ("N1", "N2", "N3", "REM"))

    # ── TMR encoding summary by pool ─────────────────────────────────────────
    pool_data: Dict[str, dict] = {}
    for pool in _ALL_POOLS:
        pool_rows = [r for r in registry if r.get("pool") == pool]
        pool_data[pool] = {
            "phrases":            len(pool_rows),
            "mean_encoding_count": (
                round(sum(r.get("encoding_count", 0) for r in pool_rows)
                      / len(pool_rows), 2)
                if pool_rows else 0
            ),
            "replay_count": replay_by_pool.get(pool, 0),
        }

    # ── Under-reinforced phrases ──────────────────────────────────────────────
    # Sort registry by encoding_count ascending; take phrases below threshold
    under = sorted(
        [r for r in registry
         if r.get("encoding_count", 0) < _ADEQUATE_ENCODING
         and r.get("affirmation_text")],
        key=lambda r: r.get("encoding_count", 0),
    )
    underreinforced_phrases = [r["affirmation_text"] for r in under[:6]]

    # ── Recommended focus pool ────────────────────────────────────────────────
    # Pool with the most under-reinforced phrases; break ties by lowest mean
    # encoding count.  Fall back to IDENTITY if registry is empty.
    def _pool_score(pool: str) -> tuple:
        pd = pool_data[pool]
        under_count = sum(
            1 for r in registry
            if r.get("pool") == pool
            and r.get("encoding_count", 0) < _ADEQUATE_ENCODING
        )
        return (-under_count, pd["mean_encoding_count"])

    if registry:
        recommended_pool = min(_ALL_POOLS, key=_pool_score)
        # If the recommended pool has no under-reinforced phrases, try falling
        # back to the pool with zero representation at all
        zero_pools = [p for p in _ALL_POOLS if pool_data[p]["phrases"] == 0]
        if zero_pools and pool_data[recommended_pool]["phrases"] > 0:
            recommended_pool = zero_pools[0]
    else:
        recommended_pool = "IDENTITY"

    # ── Next HTW eligibility estimate ─────────────────────────────────────────
    n2n3_s       = stage_dist.get("N2", 0) + stage_dist.get("N3", 0)
    htw_count    = htw_summary["htw_count"]
    # Very rough: if banked < 3600, estimate time until 1-hour mark
    next_eligible = max(0.0, 3600.0 - n2n3_s) if n2n3_s < 3600.0 else 0.0

    return {
        "session_id":             session_id,
        "elapsed_sleep_s":        elapsed_sleep_s,
        "stage_distribution":     {
            "N1":   stage_dist.get("N1",   0),
            "N2":   stage_dist.get("N2",   0),
            "N3":   stage_dist.get("N3",   0),
            "REM":  stage_dist.get("REM",  0),
            "WAKE": stage_dist.get("WAKE", 0),
        },
        "htw_count":              htw_count,
        "htw_total_duration_s":   round(htw_summary["total_duration_s"], 1),
        "htw_success_rate":       htw_summary["success_rate"],
        "tmr_replay_count":       sum(replay_by_pool.values()),
        "tmr_encoding_summary":   pool_data,
        "recommended_focus_pool": recommended_pool,
        "underreinforced_phrases": underreinforced_phrases,
        "next_htw_eligible_in_s": round(next_eligible),
    }
