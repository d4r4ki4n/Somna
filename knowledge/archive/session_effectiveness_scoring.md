# Session Effectiveness Scoring Reference
**Somna Doc 25 — Author: Research | 30 March 2026 | Capstone of EEG Pipeline**

## 1. Overview

Session effectiveness scoring is the longitudinal feedback loop. Every other EEG pipeline metric operates within a single session. This module aggregates them into a post-session composite score, writes it to `somna.db`, and over 10–20 sessions reveals patterns that let the agent optimize session configurations automatically.

**Without scoring:** each session is an island — the agent has no memory of what worked.  
**With scoring:** "sessions with IAF start + 0.1 Hz/30s descent + converge veil score 15% higher than fixed 6 Hz + drift" — and the agent can act on that.

No real-time EEG processing. Reads accumulated buffers after session ends. Summary delivered via `_say()` through `agent_message` with `needs_response: false`.

## 2. Component Metrics

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `depth_min_sef95` | float Hz | SEF95 (Doc 17) | Minimum SEF95 achieved. Lower = deeper. |
| `depth_mean_sef95` | float Hz | SEF95 | Mean SEF95, excluding first 2 min calibration |
| `time_in_target_sec` | int | SEF95 | Seconds in target SEF95 band |
| `time_in_target_pct` | float % | SEF95 | % of active session in target state |
| `transition_speed_sec` | int/null | SEF95 | Seconds from start to first entering target |
| `stability_sef95_std` | float Hz | SEF95 | SEF95 std during sustain phase (lower = more stable) |
| `entrainment_mean_assr` | float | ASSR (Doc 22) | Mean entrainment across session |
| `entrainment_peak_assr` | float | ASSR | Highest entrainment achieved |
| `entrainment_lock_pct` | float % | ASSR | % time ASSR > 0.6 (locked) |
| `receptivity_mean_faa` | float | FAA (Doc 23) | Mean FAA during affirmation windows |
| `receptivity_approach_pct` | float % | FAA | % affirmation windows in approach state |
| `signal_quality_mean` | float | SQI (Doc 21) | Mean SQI — data hygiene, not effectiveness |
| `signal_quality_dropout_pct` | float % | SQI | % time SQI < 0.5 |
| `composite_score` | float 0–100 | Computed | Weighted composite of all above |

## 3. Composite Score Weights

| Component | Weight | Rationale |
|-----------|--------|-----------|
| Depth | 0.25 | Most direct correlate of the user's "sinking" experience |
| Time in Target | 0.20 | Duration matters — brief dips don't count |
| Stability | 0.15 | Sustained low SEF95 without bouncing |
| Entrainment | 0.15 | Validates beats are actually working |
| Receptivity | 0.15 | Affirmation windows landing in approach state |
| Transition | 0.10 | Fast onset is nice but less important than sustained depth |

SQI penalty: if mean SQI < 0.7, score is scaled down proportionally. At SQI = 0.35, score is halved.

## 4. somna.db Schema — session_metrics Table

New table alongside existing tables. References session_id from session logs (no FK constraint — schemas evolve independently).

```sql
CREATE TABLE IF NOT EXISTS session_metrics (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id               TEXT NOT NULL,
    session_date             TEXT NOT NULL,
    session_preset           TEXT,
    duration_sec             INTEGER,
    depth_min_sef95          REAL,
    depth_mean_sef95         REAL,
    time_in_target_sec       INTEGER,
    time_in_target_pct       REAL,
    target_band_low          REAL,
    target_band_high         REAL,
    entrainment_mean_assr    REAL,
    entrainment_peak_assr    REAL,
    entrainment_lock_pct     REAL,
    transition_speed_sec     INTEGER,
    stability_sef95_std      REAL,
    receptivity_mean_faa     REAL,
    receptivity_approach_pct REAL,
    signal_quality_mean      REAL,
    signal_quality_dropout_pct REAL,
    composite_score          REAL,
    freq_lead_start_hz       REAL,
    freq_lead_end_hz         REAL,
    freq_lead_holds          INTEGER,
    freq_lead_steps          INTEGER,
    beat_type                TEXT,
    veil_mode_primary        TEXT,
    spiral_style             INTEGER,
    spiral_chaos             REAL,
    trail_decay              REAL,
    agent_notes              TEXT,
    created_at               TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session_metrics_date   ON session_metrics(session_date);
CREATE INDEX IF NOT EXISTS idx_session_metrics_score  ON session_metrics(composite_score);
CREATE INDEX IF NOT EXISTS idx_session_metrics_preset ON session_metrics(session_preset);
```

## 5. Longitudinal Analysis — Queries

After 10–20 sessions `SessionAnalyzer` can answer:
- Does the user entrain better on weeknights vs weekends? (group by strftime('%w', session_date))
- Does trail_decay > 0.3 correlate with deeper sessions?
- Which spiral style produces the best composite scores?
- Is there a time-of-day effect on transition speed?
- Is the user's overall trend improving? (`analyzer.trend("composite_score", n=20)`)

## 6. Agent Auto-Optimization Protocol

1. **Query at session start** — `best_config_for_preset()` for selected preset + `trend()` for overall direction
2. **Compare configs** — current vs. recommended from top-scoring sessions
3. **Adjust conservatively** — max 2 parameter changes at once (attribution requires isolation)
4. **Log the decision** — record in `agent_notes` (e.g., "Switched to converge veil — top 3 sessions all used converge")
5. **Evaluate after 5 sessions** — compare new mean vs previous 5-session mean
6. **Revert if no improvement**

**Guardrails:**
- Minimum 10 sessions before any auto-optimization
- Maximum 2 parameter changes per session
- Filter sessions with `signal_quality_mean < 0.5`
- 5-session evaluation window
- All adjustments via `_patch_live()` — never overwrite live_control.json

**Explainability:** The agent must be able to explain every decision with data. "I'm using converge veil tonight because your three best sessions all used it. Average score 72 vs 58 with drift."

## 7. Session Summary Delivery

After `SessionScorer.score_session()`, generate a spoken summary via `_say()` with `needs_response: false`. Aphantasia-safe — somatic/factual framing only. No "imagine," "picture," or guided imagery.

**Score interpretation:**
- ≥ 80: "Excellent session."
- 60–79: "Good session."
- 40–59: "Decent session — room to settle deeper next time."
- < 40: "Light session. That's fine — depth varies naturally."

## 8. Pipeline Completeness

| Doc | Module | Feeds Scoring |
|-----|--------|---------------|
| Doc 17 | SEF95 | depth, stability, time_in_target, transition_speed |
| Doc 21 | SQI | signal_quality, SQI penalty |
| Doc 22 | ASSR | entrainment metrics |
| Doc 23 | FAA | receptivity metrics |
| Doc 24 | Freq Leading | freq_lead_start/end/holds/steps |
| Doc 12 | Session Mgmt | preset, target_band, config snapshot |
| **Doc 25** | **Scoring** | **All above → composite_score → agent learning** |
