"""
content_tools/somna_db.py — SQLite backend for image metadata and generation log.

Replaces per-session tags.json and gen_log.json with a single somna.db file at
the project root.  Uses Python's stdlib sqlite3 — zero installation, zero server,
invisible to the end user.

Tables:
    images          — one row per (session, filename); replaces tags.json
    gen_log         — append-only generation history; replaces gen_log.json
    session_quality — one row per session creation pipeline run; tracks review
                      scores so quality trends can be reviewed over time

WAL journal mode is enabled so the pipeline CLI and a running agent can write
concurrently without blocking each other.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_DB_PATH = _ROOT / "somna.db"

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS images (
    session          TEXT NOT NULL,
    filename         TEXT NOT NULL,
    tags             TEXT NOT NULL DEFAULT '[]',
    open_tags        TEXT NOT NULL DEFAULT '[]',
    caption_text     TEXT NOT NULL DEFAULT '',
    quality          TEXT NOT NULL DEFAULT 'keep',
    style            TEXT NOT NULL DEFAULT '',
    conditioning_hook TEXT NOT NULL DEFAULT '',
    gen_scores       TEXT,
    PRIMARY KEY (session, filename)
);

CREATE TABLE IF NOT EXISTS gen_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    session      TEXT NOT NULL,
    theme        TEXT NOT NULL,
    tag          TEXT NOT NULL,
    attempt      INTEGER NOT NULL DEFAULT 1,
    prompt       TEXT NOT NULL DEFAULT '',
    prompt_base  TEXT NOT NULL DEFAULT '',
    caption      TEXT NOT NULL DEFAULT '',
    ref_image    TEXT NOT NULL DEFAULT '',
    action       TEXT NOT NULL DEFAULT '',
    vq           INTEGER,
    pf           INTEGER,
    cv           INTEGER,
    failure_note TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_gen_log_session_theme
    ON gen_log(session, theme);

CREATE TABLE IF NOT EXISTS session_quality (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_name            TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    intent                  TEXT NOT NULL DEFAULT '',
    attempts                INTEGER NOT NULL DEFAULT 1,
    arc_coherence           INTEGER,
    phrase_quality          INTEGER,
    technical_validity      INTEGER,
    conditioning_effectiveness INTEGER,
    passed                  INTEGER NOT NULL DEFAULT 0,
    failure_note            TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_session_quality_name
    ON session_quality(session_name);

CREATE TABLE IF NOT EXISTS sessions (
    name         TEXT    PRIMARY KEY,
    description  TEXT    NOT NULL DEFAULT '',
    image_tags   TEXT    NOT NULL DEFAULT '[]',
    duration_s   REAL    NOT NULL DEFAULT 0,
    category     TEXT    NOT NULL DEFAULT 'general',
    is_favorite  BOOLEAN NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    last_played  TEXT,
    play_count   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_last_played ON sessions(last_played);
CREATE INDEX IF NOT EXISTS idx_sessions_category    ON sessions(category);

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
    -- Phase-cascade temporal coordination (Bible Ch.4 §4.6)
    peak_isa_alpha_pac       REAL,   -- peak ISA-alpha modulation index over session
    peak_theta_gamma_pac     REAL,   -- peak theta-gamma MI
    mean_cascade_integrity   REAL,   -- mean weighted cascade_integrity
    optimal_breath_rate      REAL,   -- breath_rate that produced highest ISA-alpha PAC
    optimal_beat_hz          REAL,   -- beat_frequency that produced highest theta-gamma PAC
    phase_gate_hit_rate      REAL,   -- fraction of fires that were fully gated vs fallback
    delivery_rate_hz         REAL,   -- actual achieved affirmation delivery rate
    created_at               TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session_metrics_date   ON session_metrics(session_date);
CREATE INDEX IF NOT EXISTS idx_session_metrics_score  ON session_metrics(composite_score);
CREATE INDEX IF NOT EXISTS idx_session_metrics_preset ON session_metrics(session_preset);

-- Bible Ch.2 §2.9: per-delivery event log for cardiac phase analysis
CREATE TABLE IF NOT EXISTS delivery_log (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT    NOT NULL,
    timestamp             REAL    NOT NULL,
    content_hash          TEXT,
    pool                  TEXT,
    gate_mode             TEXT,
    gate_relaxation_level INTEGER DEFAULT 0,
    cardiac_phase         REAL,
    cardiac_diastole      INTEGER DEFAULT 0,
    autonomic_depth       REAL,
    stillness_index       REAL,
    respiratory_phase     REAL,
    alpha_phase           REAL,
    trance_score          REAL
);
CREATE INDEX IF NOT EXISTS idx_delivery_log_session ON delivery_log(session_id);
CREATE INDEX IF NOT EXISTS idx_delivery_log_ts      ON delivery_log(timestamp);

CREATE TABLE IF NOT EXISTS conductor_decisions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT    NOT NULL,
    timestamp        REAL    NOT NULL,
    session_elapsed  REAL    NOT NULL,
    phase            TEXT    NOT NULL,
    action           TEXT    NOT NULL,
    rationale        TEXT,
    sqi_confidence   TEXT,
    trance_score     REAL,
    sef95            REAL,
    assr_strength    REAL,
    assr_confidence  TEXT,
    faa_value        REAL,
    beat_freq        REAL,
    chaos            REAL,
    trail_decay      REAL,
    tick_rate        INTEGER,
    parameters_json  TEXT
);

CREATE INDEX IF NOT EXISTS idx_conductor_session ON conductor_decisions(session_id);
CREATE INDEX IF NOT EXISTS idx_conductor_phase   ON conductor_decisions(phase);
CREATE INDEX IF NOT EXISTS idx_conductor_action  ON conductor_decisions(action);

-- ── Calibration tables (Bible Ch.2 §2.6) ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS calibration_baselines (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_number INTEGER NOT NULL,
    metric         TEXT    NOT NULL,
    channel        TEXT,
    condition      TEXT    NOT NULL,
    value          REAL    NOT NULL,
    sd             REAL,
    n_samples      INTEGER,
    sqi_mean       REAL,
    timestamp      TEXT    NOT NULL,
    UNIQUE(session_number, metric, channel, condition)
);

CREATE TABLE IF NOT EXISTS calibration_sessions (
    session_number            INTEGER PRIMARY KEY,
    phase                     TEXT NOT NULL,
    started_at                TEXT NOT NULL,
    completed_at              TEXT,
    duration_seconds          REAL,
    max_conductor_phase_reached TEXT,
    notes                     TEXT,
    thresholds_derived        TEXT
);

CREATE TABLE IF NOT EXISTS calibration_thresholds (
    metric              TEXT PRIMARY KEY,
    value               REAL NOT NULL,
    derived_from_sessions TEXT NOT NULL,
    derivation_method   TEXT NOT NULL,
    confidence          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calibration_assr_curve (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_number INTEGER NOT NULL,
    frequency_hz   REAL    NOT NULL,
    assr_strength  REAL    NOT NULL,
    hold_duration_s REAL   NOT NULL,
    sqi_mean       REAL,
    timestamp      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS content_cascades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    ts              REAL    NOT NULL,
    pool_id         TEXT    NOT NULL,
    shadow_word     TEXT,
    center_phrase   TEXT,
    voice_phrase    TEXT,
    cascade_index   INTEGER,
    conductor_phase TEXT,
    faa             REAL,
    trance_score    REAL,
    theta_alpha_ratio REAL,
    sqi             TEXT
);

CREATE TABLE IF NOT EXISTS content_effectiveness (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT    NOT NULL,
    pool_id          TEXT    NOT NULL,
    cascade_count    INTEGER,
    mean_delta_trance REAL,
    mean_delta_faa   REAL,
    mean_delta_assr  REAL,
    effectiveness_score REAL
);

CREATE TABLE IF NOT EXISTS pool_transitions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    ts              REAL    NOT NULL,
    from_pool       TEXT,
    to_pool         TEXT    NOT NULL,
    faa             REAL,
    trance_score    REAL,
    theta_alpha_ratio REAL,
    conductor_phase TEXT
);

CREATE TABLE IF NOT EXISTS pool_weights (
    pool_id       TEXT PRIMARY KEY,
    weight        REAL    NOT NULL DEFAULT 1.0,
    last_updated  REAL,
    session_count INTEGER DEFAULT 0
);

CREATE VIEW IF NOT EXISTS phase_summary AS
SELECT
    session_id,
    phase,
    COUNT(*)                                                AS tick_count,
    MIN(session_elapsed)                                    AS phase_start,
    MAX(session_elapsed)                                    AS phase_end,
    MAX(session_elapsed) - MIN(session_elapsed)             AS phase_duration,
    AVG(trance_score)                                       AS avg_trance_score,
    MIN(CASE WHEN sef95 IS NOT NULL THEN sef95 END)         AS min_sef95,
    AVG(assr_strength)                                      AS avg_assr,
    AVG(faa_value)                                          AS avg_faa,
    SUM(CASE WHEN action LIKE 'TRANSITION%' THEN 1 ELSE 0 END) AS transition_count
FROM conductor_decisions
GROUP BY session_id, phase;

-- Bible Ch.3 §3.8: gain engine decisions (per-tick, batched writes)
CREATE TABLE IF NOT EXISTS gain_decisions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT    NOT NULL,
    ts                    REAL    NOT NULL,
    conductor_phase       TEXT    NOT NULL,
    depth_scalar          REAL,
    sr_factor             REAL,
    noise_ratio           REAL,
    raw_noise             REAL,
    effective_noise       REAL,
    raw_text_opacity      REAL,
    effective_text_opacity REAL,
    carrier_noise_ratio   REAL
);
CREATE INDEX IF NOT EXISTS idx_gain_decisions_session
    ON gain_decisions(session_id, ts);

-- Bible Ch.3 §3.8: SR calibration results (per-user, longitudinal)
CREATE TABLE IF NOT EXISTS sr_calibration (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT    NOT NULL,
    calibrated_at         REAL    NOT NULL,
    sr_optimal_noise      REAL    NOT NULL,
    sr_gain_bonus         REAL    NOT NULL,
    calibration_curve     TEXT    NOT NULL,
    baseline_alpha        REAL,
    carrier_noise_threshold REAL
);
CREATE INDEX IF NOT EXISTS idx_sr_calibration_session
    ON sr_calibration(session_id);

-- Bible Ch.3 §3.8: per-session, per-phase gain summary view
CREATE VIEW IF NOT EXISTS gain_summary AS
SELECT
    session_id,
    conductor_phase,
    AVG(depth_scalar)         AS mean_depth_scalar,
    AVG(sr_factor)            AS mean_sr_factor,
    MIN(effective_noise)      AS min_eff_noise,
    MAX(effective_noise)      AS max_eff_noise,
    AVG(carrier_noise_ratio)  AS mean_cnr,
    MIN(carrier_noise_ratio)  AS min_cnr,
    COUNT(*)                  AS tick_count
FROM gain_decisions
GROUP BY session_id, conductor_phase;

-- Bible Ch.2 §2.8: per-tick depth estimation log
CREATE TABLE IF NOT EXISTS depth_estimates (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT    NOT NULL,
    ts                REAL    NOT NULL,
    spectral_slope    REAL,
    slope_confidence  REAL,
    frontal_alpha_coh REAL,
    frontal_beta_coh  REAL,
    temporal_theta_coh REAL,
    beta_env_corr     REAL,
    coherence_depth   REAL,
    trance_score_v1   REAL,
    trance_score_v2   REAL,
    conductor_phase   TEXT
);
CREATE INDEX IF NOT EXISTS idx_depth_estimates_session
    ON depth_estimates(session_id, ts);

-- Bible Ch.2 §2.8: session-level depth summary view
CREATE VIEW IF NOT EXISTS depth_summary AS
SELECT
    session_id,
    conductor_phase,
    AVG(spectral_slope)    AS mean_slope,
    MIN(spectral_slope)    AS deepest_slope,
    AVG(coherence_depth)   AS mean_coh_depth,
    MAX(coherence_depth)   AS peak_coh_depth,
    AVG(beta_env_corr)     AS mean_beta_env,
    MIN(beta_env_corr)     AS min_beta_env,
    AVG(trance_score_v2)   AS mean_depth_v2,
    MAX(trance_score_v2)   AS peak_depth_v2,
    COUNT(*)               AS tick_count
FROM depth_estimates
GROUP BY session_id, conductor_phase;

-- Bible Ch.2 §2.8: baseline coherence values from calibration
CREATE TABLE IF NOT EXISTS calibration_v2 (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id                 TEXT    NOT NULL,
    calibrated_at              REAL    NOT NULL,
    iaf_hz                     REAL    NOT NULL,
    baseline_slope             REAL    NOT NULL,
    baseline_frontal_alpha_coh REAL,
    baseline_beta_env_corr     REAL,
    baseline_temporal_theta_coh REAL,
    slope_samples              TEXT,
    calibration_quality        TEXT
);

-- Bible Ch.7 §7.1: sleep stage log (30-s throttle → ≈960 rows/8-h session)
CREATE TABLE IF NOT EXISTS sleep_stage_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    timestamp       REAL    NOT NULL,
    stage           TEXT    NOT NULL,   -- WAKE, N1, N2, N3, REM
    confidence      REAL    NOT NULL,
    spectral_slope  REAL,
    delta_power     REAL,
    spindle_density REAL,
    sigma_amplitude REAL,
    sw_burst_delivered INTEGER DEFAULT 0
);

-- Bible Ch.7 §7.1: per-user sleep classifier calibration thresholds
CREATE TABLE IF NOT EXISTS sleep_calibration (
    id                           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id                   TEXT    NOT NULL,
    timestamp                    REAL    NOT NULL,
    slope_wake_n1                REAL,
    slope_n1_n2                  REAL,
    slope_n2_n3                  REAL,
    slope_rem_ceil               REAL,
    delta_n3_floor               REAL,
    spindle_n2_floor             REAL,
    alpha_wake_floor             REAL,
    beta_dropout_ceil            REAL,
    rem_theta_floor              REAL,
    calib_slope_wake             REAL,
    calib_beta_wake              REAL,
    calib_alpha_antiphase_tolerance REAL,
    calib_spindle_baseline       REAL,
    calib_swa_response_ratio     REAL
);

-- ── HTW (Bible Ch.9 §9.1) ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sleep_training_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT    NOT NULL,
    htw_index         INTEGER NOT NULL,
    started_at        REAL    NOT NULL,
    duration_s        REAL    NOT NULL,
    stage_at_entry    TEXT    NOT NULL DEFAULT 'N1',
    stage_at_exit     TEXT    NOT NULL DEFAULT 'UNKNOWN',
    focus_pool        TEXT    NOT NULL DEFAULT '',
    phrases_delivered INTEGER NOT NULL DEFAULT 0,
    exit_reason       TEXT    NOT NULL DEFAULT 'unknown'
);
CREATE INDEX IF NOT EXISTS idx_sleep_training_session
    ON sleep_training_log(session_id);

-- ── Edison Mode captures (Bible Ch.7 §29) ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS edison_captures (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              TEXT    NOT NULL,
    capture_index           INTEGER NOT NULL,
    n1_onset_ts             REAL    NOT NULL DEFAULT 0,
    n1_duration_s           REAL    NOT NULL DEFAULT 0,
    alpha_theta_ratio       REAL    NOT NULL DEFAULT 0,
    seed_topic              TEXT    NOT NULL DEFAULT '',
    user_report             TEXT    NOT NULL DEFAULT '',
    eeg_snapshot             TEXT    NOT NULL DEFAULT '{}',
    wake_cue_type           TEXT    NOT NULL DEFAULT 'normal',
    cycle_complete_ts       REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_edison_captures_session
    ON edison_captures(session_id);

-- ── TMR tables (Bible Ch.7 §7.5) ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tmr_cue_registry (
    session_id      TEXT    NOT NULL,
    pool            TEXT    NOT NULL,
    content_hash    TEXT    NOT NULL,
    affirmation_text TEXT   NOT NULL DEFAULT '',
    encoding_count  INTEGER NOT NULL DEFAULT 0,
    strength        REAL    NOT NULL DEFAULT 0.5,
    last_encoded_at REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, pool, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_tmr_registry_session ON tmr_cue_registry(session_id);

CREATE TABLE IF NOT EXISTS tmr_encoding_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    pool            TEXT    NOT NULL,
    content_hash    TEXT    NOT NULL,
    affirmation_text TEXT   NOT NULL DEFAULT '',
    timestamp       REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tmr_encoding_session ON tmr_encoding_log(session_id);

CREATE TABLE IF NOT EXISTS tmr_replay_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    pool            TEXT    NOT NULL,
    content_hash    TEXT    NOT NULL,
    sleep_stage     TEXT    NOT NULL,
    timestamp       REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tmr_replay_session ON tmr_replay_log(session_id);

-- ── Bible Ch.10 §10.1: Conditioning & Reinforcement ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS conditioning_associations (
    record_id               TEXT    PRIMARY KEY,
    session_id              TEXT    NOT NULL,
    timestamp_ms            INTEGER NOT NULL,
    cs_class                TEXT    NOT NULL DEFAULT '',
    cs_identity             TEXT    NOT NULL DEFAULT '',
    cs_pool                 TEXT    NOT NULL DEFAULT '',
    us_type                 TEXT    NOT NULL DEFAULT '',
    us_magnitude            REAL    NOT NULL DEFAULT 0.0,
    delivery_gate_state     TEXT,
    neural_state_fingerprint TEXT,
    cardiac_phase           REAL,
    respiratory_phase       REAL,
    conductor_phase         TEXT    NOT NULL DEFAULT '',
    modality                TEXT    NOT NULL DEFAULT '',
    contiguity_ms           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cond_assoc_session
    ON conditioning_associations(session_id);
CREATE INDEX IF NOT EXISTS idx_cond_assoc_identity
    ON conditioning_associations(cs_identity, cs_pool);
CREATE INDEX IF NOT EXISTS idx_cond_assoc_phase
    ON conditioning_associations(conductor_phase, timestamp_ms);

CREATE TABLE IF NOT EXISTS conditioning_strengths (
    cs_identity             TEXT    NOT NULL,
    cs_pool                 TEXT    NOT NULL,
    us_type                 TEXT    NOT NULL,
    conductor_phase         TEXT    NOT NULL DEFAULT '',
    strength                REAL    NOT NULL DEFAULT 0.0,
    trial_count             INTEGER NOT NULL DEFAULT 0,
    last_pairing_ts         INTEGER NOT NULL DEFAULT 0,
    last_extinction_check_ts INTEGER NOT NULL DEFAULT 0,
    salience                REAL    NOT NULL DEFAULT 1.0,
    extinction_rate         REAL    NOT NULL DEFAULT 0.02,
    is_second_order         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (cs_identity, us_type, conductor_phase)
);
CREATE INDEX IF NOT EXISTS idx_cond_strengths_pool
    ON conditioning_strengths(cs_pool);

CREATE TABLE IF NOT EXISTS shaping_progress (
    user_id             TEXT    NOT NULL,
    metric_name         TEXT    NOT NULL,
    current_percentile  REAL    NOT NULL DEFAULT 0.0,
    session_count       INTEGER NOT NULL DEFAULT 0,
    best_session_value  REAL,
    mean_session_value  REAL,
    last_session_ts     REAL,
    PRIMARY KEY (user_id, metric_name)
);

CREATE TABLE IF NOT EXISTS cue_test_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT    NOT NULL,
    test_ts             REAL    NOT NULL,
    cs_identity         TEXT    NOT NULL DEFAULT '',
    cs_pool             TEXT    NOT NULL DEFAULT '',
    baseline_snapshot   TEXT,
    trial_results       TEXT,
    overall_cr_rate     REAL,
    graduated_pools     TEXT
);
CREATE INDEX IF NOT EXISTS idx_cue_test_session
    ON cue_test_results(session_id);

-- ── Bible Ch.10 §10.3: Habituation & Novelty Management ─────────────────────────────────

CREATE TABLE IF NOT EXISTS stimulus_exposure (
    stimulus_id             TEXT    PRIMARY KEY,
    stimulus_class          TEXT    NOT NULL,
    layer                   TEXT    NOT NULL,
    lifetime_presentations  INTEGER NOT NULL DEFAULT 0,
    lifetime_exposure_s     REAL    NOT NULL DEFAULT 0.0,
    lifetime_sessions       INTEGER NOT NULL DEFAULT 0,
    first_used_ts           REAL,
    last_session_ts         REAL,
    state                   TEXT    NOT NULL DEFAULT 'novel',
    cooling_since_ts        REAL,
    times_cooled            INTEGER NOT NULL DEFAULT 0,
    macro_novelty           REAL    NOT NULL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS session_exposure (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT    NOT NULL,
    stimulus_id         TEXT    NOT NULL,
    presentations       INTEGER NOT NULL DEFAULT 0,
    exposure_s          REAL    NOT NULL DEFAULT 0.0,
    mean_novelty        REAL,
    mean_effectiveness  REAL,
    timestamp           REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_exposure_session
    ON session_exposure(session_id);
CREATE INDEX IF NOT EXISTS idx_session_exposure_stimulus
    ON session_exposure(stimulus_id);

CREATE TABLE IF NOT EXISTS dishabituation_log (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              TEXT    NOT NULL,
    trigger_type            TEXT    NOT NULL,
    trigger_ts              REAL    NOT NULL,
    pre_novelty             REAL,
    post_novelty            REAL,
    trance_depth_at_trigger REAL
);
CREATE INDEX IF NOT EXISTS idx_dishab_session
    ON dishabituation_log(session_id);

-- ── Bible Ch.5 §5.5: Session Director ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS director_profile (
    user_id                  TEXT    PRIMARY KEY,
    sessions_completed       INTEGER NOT NULL DEFAULT 0,
    total_session_time_s     INTEGER NOT NULL DEFAULT 0,
    avg_peak_depth           REAL    NOT NULL DEFAULT 0.0,
    max_achieved_depth       REAL    NOT NULL DEFAULT 0.0,
    preferred_induction      TEXT    NOT NULL DEFAULT 'entrainment_heavy',
    preferred_arc            TEXT    NOT NULL DEFAULT 'GENTLE_DESCENT',
    depth_signature          TEXT,
    avg_time_to_induction_s  REAL    NOT NULL DEFAULT 300.0,
    avg_time_to_peak_s       REAL    NOT NULL DEFAULT 900.0,
    sleep_fork_success_rate  REAL    NOT NULL DEFAULT 0.0,
    last_session_at          REAL,
    created_at               REAL    NOT NULL,
    updated_at               REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS session_history (
    session_id                       TEXT    PRIMARY KEY,
    user_id                          TEXT    NOT NULL DEFAULT '',
    started_at                       REAL    NOT NULL,
    ended_at                         REAL,
    duration_s                       INTEGER,
    arc_template                     TEXT,
    session_goal                     TEXT,
    target_peak_depth                REAL,
    achieved_peak_depth              REAL,
    avg_depth                        REAL,
    time_in_deep_s                   INTEGER,
    depth_trajectory_score           REAL,
    induction_strategy               TEXT,
    induction_effectiveness          REAL,
    conditioning_reinforcement_score REAL,
    plan_adherence                   REAL,
    director_redirects               INTEGER NOT NULL DEFAULT 0,
    intensity_cycles_completed       INTEGER NOT NULL DEFAULT 0,
    pace_confidence_final            REAL,
    user_satisfaction                REAL,
    outcome_notes                    TEXT
);
CREATE INDEX IF NOT EXISTS idx_session_history_user
    ON session_history(user_id);
CREATE INDEX IF NOT EXISTS idx_session_history_started
    ON session_history(started_at);

CREATE TABLE IF NOT EXISTS session_decisions (
    decision_id     TEXT    PRIMARY KEY,
    session_id      TEXT    NOT NULL,
    timestamp       REAL    NOT NULL,
    decision_type   TEXT    NOT NULL DEFAULT '',
    decision_value  TEXT,
    authority_level INTEGER NOT NULL DEFAULT 0,
    rationale       TEXT,
    state_snapshot  TEXT,
    outcome_score   REAL
);
CREATE INDEX IF NOT EXISTS idx_session_decisions_session
    ON session_decisions(session_id);

-- ── Bible Ch.4 Addendum A: GENUS Integration ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS content_pipeline (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_id                     TEXT    NOT NULL,
    item_hash                   TEXT    NOT NULL,
    genus_encoded               INTEGER NOT NULL DEFAULT 0,
    genus_session_id            TEXT,
    genus_entrainment_at_delivery REAL,
    trance_deepened             INTEGER NOT NULL DEFAULT 0,
    trance_session_id           TEXT,
    tmr_consolidated            INTEGER NOT NULL DEFAULT 0,
    tmr_session_id              TEXT,
    pipeline_complete           INTEGER NOT NULL DEFAULT 0,
    created_ts                  TEXT    NOT NULL,
    updated_ts                  TEXT    NOT NULL,
    UNIQUE(pool_id, item_hash)
);
CREATE INDEX IF NOT EXISTS idx_content_pipeline_pool
    ON content_pipeline(pool_id);
CREATE INDEX IF NOT EXISTS idx_content_pipeline_incomplete
    ON content_pipeline(pipeline_complete)
    WHERE pipeline_complete = 0;

-- Reconsolidation protocol events
CREATE TABLE IF NOT EXISTS recon_events (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session               TEXT    NOT NULL,
    target_trace          TEXT    NOT NULL,
    ts                    REAL    NOT NULL,
    update_delivered      INTEGER NOT NULL DEFAULT 0,
    gate_hits             INTEGER NOT NULL DEFAULT 0,
    reconsolidation_clean INTEGER NOT NULL DEFAULT 1,
    notes                 TEXT
);
CREATE INDEX IF NOT EXISTS idx_recon_events_trace
    ON recon_events(target_trace);
CREATE INDEX IF NOT EXISTS idx_recon_events_session
    ON recon_events(session, ts DESC);

-- Somatic palette entries: per-chord cross-modal config + outcome records
CREATE TABLE IF NOT EXISTS palette_entries (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    session                TEXT    NOT NULL,
    session_metrics_id     TEXT,
    ts                     REAL    NOT NULL,
    chord_index            INTEGER NOT NULL DEFAULT 0,
    beat_frequency         REAL,
    carrier_waveform       TEXT,
    noise_color            TEXT,
    noise_volume           REAL,
    spiral_style           TEXT,
    veil_mode              TEXT,
    entry_time_hour        INTEGER,
    days_since_last        REAL,
    entry_trance           REAL,
    outcome_score          REAL,
    depth_min_sef95        REAL,
    faa_approach_pct       REAL,
    delivery_gate_hit_rate REAL,
    duration_maintenance_s REAL,
    abandoned              INTEGER NOT NULL DEFAULT 0,
    eeg_theta              REAL,
    eeg_alpha              REAL,
    eeg_faa                REAL,
    eeg_spindle_density    REAL,
    state_type             TEXT,
    palette_family         TEXT,
    annotation_notes       TEXT,
    is_experiment          INTEGER NOT NULL DEFAULT 0,
    experiment_param       TEXT,
    confidence             REAL    NOT NULL DEFAULT 0.5
);
CREATE INDEX IF NOT EXISTS idx_palette_entries_session
    ON palette_entries(session, ts DESC);
CREATE INDEX IF NOT EXISTS idx_palette_entries_family
    ON palette_entries(palette_family, outcome_score DESC);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_schema() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        # Bible Ch.6 §6.6 migration: if content_cascades was created with a broken FK
        # referencing sessions(session_id) (non-existent column), drop and
        # recreate it without the FK constraint.
        fk_info = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='content_cascades'"
        ).fetchone()
        if fk_info and "REFERENCES sessions" in (fk_info[0] or ""):
            conn.executescript("""
                DROP TABLE IF EXISTS content_cascades;
                DROP TABLE IF EXISTS content_effectiveness;
                DROP TABLE IF EXISTS pool_transitions;
            """)
            conn.executescript(_SCHEMA)
            conn.commit()

        # Bible Ch.7 §7.1 migration: add sleep columns to session_metrics (idempotent)
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(session_metrics)").fetchall()
        }
        sleep_columns = [
            ("sleep_onset_latency_s", "REAL"),
            ("total_sleep_time_s", "REAL"),
            ("sleep_efficiency", "REAL"),
            ("time_in_n1_s", "REAL"),
            ("time_in_n2_s", "REAL"),
            ("time_in_n3_s", "REAL"),
            ("time_in_rem_s", "REAL"),
            ("swa_enhancement_ratio", "REAL"),
            ("spindle_count", "INTEGER"),
            ("mean_spindle_density", "REAL"),
            ("alpha_antiphase_bursts", "INTEGER"),
            ("sw_enhance_bursts", "INTEGER"),
            ("wake_after_sleep_onset_s", "REAL"),
        ]
        for col_name, col_type in sleep_columns:
            if col_name not in existing:
                conn.execute(
                    f"ALTER TABLE session_metrics ADD COLUMN {col_name} {col_type}"
                )

        # Bible Ch.4 §4.6 migration: add phase-cascade temporal coordination columns
        pac_columns = [
            ("peak_isa_alpha_pac", "REAL"),
            ("peak_theta_gamma_pac", "REAL"),
            ("mean_cascade_integrity", "REAL"),
            ("optimal_breath_rate", "REAL"),
            ("optimal_beat_hz", "REAL"),
            ("phase_gate_hit_rate", "REAL"),
            ("delivery_rate_hz", "REAL"),
        ]
        for col_name, col_type in pac_columns:
            if col_name not in existing:
                conn.execute(
                    f"ALTER TABLE session_metrics ADD COLUMN {col_name} {col_type}"
                )

        # Bible Ch.9 §9.1 migration: add HTW summary columns to session_metrics
        htw_columns = [
            ("htw_count", "INTEGER"),
            ("htw_total_duration_s", "REAL"),
            ("htw_success_rate", "REAL"),
        ]
        for col_name, col_type in htw_columns:
            if col_name not in existing:
                conn.execute(
                    f"ALTER TABLE session_metrics ADD COLUMN {col_name} {col_type}"
                )

        # Bible Ch.2 §2.9 migration: add autonomic/cardiac/IMU summary columns to session_metrics
        doc42_columns = [
            ("ppg_available_pct", "REAL"),
            ("ppg_mean_hr", "REAL"),
            ("ppg_mean_rmssd", "REAL"),
            ("ppg_baseline_rmssd", "REAL"),
            ("autonomic_depth_mean", "REAL"),
            ("autonomic_depth_max", "REAL"),
            ("imu_motion_events", "INTEGER"),
            ("imu_mean_stillness", "REAL"),
            ("delivery_gate_cardiac_hit_pct", "REAL"),
            ("depth_confidence_high_pct", "REAL"),
        ]
        for col_name, col_type in doc42_columns:
            if col_name not in existing:
                conn.execute(
                    f"ALTER TABLE session_metrics ADD COLUMN {col_name} {col_type}"
                )

        # Bible Ch.4 Addendum A migration: add GENUS tracking columns to session_history
        sh_existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(session_history)").fetchall()
        }
        genus_sh_columns = [
            ("genus_included", "INTEGER DEFAULT 0"),
            ("genus_duration_s", "INTEGER DEFAULT 0"),
            ("genus_mean_entrainment_ratio", "REAL DEFAULT 0.0"),
            ("genus_peak_entrainment_ratio", "REAL DEFAULT 0.0"),
            ("genus_fallback", "INTEGER DEFAULT 0"),
            ("genus_fallback_reason", "TEXT"),
            ("genus_content_items_delivered", "INTEGER DEFAULT 0"),
            ("genus_arc_template", "TEXT"),
        ]
        for col_name, col_def in genus_sh_columns:
            if col_name not in sh_existing:
                conn.execute(
                    f"ALTER TABLE session_history ADD COLUMN {col_name} {col_def}"
                )

        # Bible Ch.4 Addendum A migration: add GENUS preference columns to director_profile
        dp_existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(director_profile)").fetchall()
        }
        genus_dp_columns = [
            ("genus_epilepsy_ack", "INTEGER DEFAULT 0"),
            ("genus_visual_enabled", "INTEGER DEFAULT 1"),
            ("genus_audio_only_preference", "INTEGER DEFAULT 0"),
            ("genus_sessions_lifetime", "INTEGER DEFAULT 0"),
            ("genus_last_session_ts", "TEXT"),
            ("genus_mean_entrainment_history", "REAL DEFAULT 0.0"),
            ("genus_enabled", "INTEGER DEFAULT 1"),
        ]
        for col_name, col_def in genus_dp_columns:
            if col_name not in dp_existing:
                conn.execute(
                    f"ALTER TABLE director_profile ADD COLUMN {col_name} {col_def}"
                )

        # Bible Ch.6 §6.7 migration: strategy_history table (induction runner)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS strategy_history (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             TEXT    NOT NULL DEFAULT 'default',
                session_id          TEXT    NOT NULL DEFAULT '',
                strategy_id         TEXT    NOT NULL,
                started_at          REAL    NOT NULL,
                completed_at        REAL,
                outcome             TEXT    CHECK(outcome IN
                                        ('success','partial','failure','redirected')),
                time_to_trance_s    REAL,
                peak_trance_score   REAL,
                redirected_to       TEXT,
                redirect_reason     TEXT,
                effectiveness_score REAL,
                eeg_snapshot        TEXT,
                ppg_snapshot        TEXT,
                notes               TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_strategy_history_user
                ON strategy_history(user_id, started_at DESC);
        """)

        # Bible Ch.6 §6.7 migration: add strategy-preference columns to director_profile
        if "preferred_strategy" not in dp_existing:
            conn.execute(
                "ALTER TABLE director_profile ADD COLUMN preferred_strategy TEXT"
            )
        if "strategy_effectiveness" not in dp_existing:
            conn.execute(
                "ALTER TABLE director_profile ADD COLUMN "
                "strategy_effectiveness TEXT DEFAULT '{}'"
            )
        if "contraindication_flags" not in dp_existing:
            conn.execute(
                "ALTER TABLE director_profile ADD COLUMN "
                "contraindication_flags TEXT DEFAULT '[]'"
            )

        conn.commit()


# Run schema creation once at import time — idempotent, fast.
_ensure_schema()


# ── Image metadata ────────────────────────────────────────────────────────────


def load_tags(session: str) -> dict:
    """Return {filename: meta_dict} for every tagged image in the session."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM images WHERE session=?", (session,)
        ).fetchall()
    result = {}
    for row in rows:
        result[row["filename"]] = {
            "tags": json.loads(row["tags"]),
            "open_tags": json.loads(row["open_tags"]),
            "caption_text": row["caption_text"],
            "quality": row["quality"],
            "style": row["style"],
            "conditioning_hook": row["conditioning_hook"],
            "gen_scores": (
                json.loads(row["gen_scores"]) if row["gen_scores"] else None
            ),
        }
    return result


def get_tagged_filenames(session: str) -> set[str]:
    """Return the set of filenames that already have a DB entry for this session.

    Faster than load_tags() when you only need to know which images are tagged.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT filename FROM images WHERE session=?", (session,)
        ).fetchall()
    return {row["filename"] for row in rows}


def save_image_meta(session: str, filename: str, meta: dict) -> None:
    """Upsert a single image's metadata row."""
    gen_scores = meta.get("gen_scores")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO images
                (session, filename, tags, open_tags, caption_text,
                 quality, style, conditioning_hook, gen_scores)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session, filename) DO UPDATE SET
                tags             = excluded.tags,
                open_tags        = excluded.open_tags,
                caption_text     = excluded.caption_text,
                quality          = excluded.quality,
                style            = excluded.style,
                conditioning_hook= excluded.conditioning_hook,
                gen_scores       = excluded.gen_scores
            """,
            (
                session,
                filename,
                json.dumps(meta.get("tags", []), ensure_ascii=False),
                json.dumps(meta.get("open_tags", []), ensure_ascii=False),
                meta.get("caption_text", ""),
                meta.get("quality", "keep"),
                meta.get("style", ""),
                meta.get("conditioning_hook", ""),
                json.dumps(gen_scores, ensure_ascii=False) if gen_scores else None,
            ),
        )
        conn.commit()


def save_tags(session: str, tags_dict: dict) -> None:
    """Bulk upsert from a {filename: meta} dict.

    Drop-in replacement for the old _save_tags / write_tags helpers.
    Wraps save_image_meta in a single transaction for efficiency.
    """
    with _connect() as conn:
        for filename, meta in tags_dict.items():
            gen_scores = meta.get("gen_scores")
            conn.execute(
                """
                INSERT INTO images
                    (session, filename, tags, open_tags, caption_text,
                     quality, style, conditioning_hook, gen_scores)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session, filename) DO UPDATE SET
                    tags             = excluded.tags,
                    open_tags        = excluded.open_tags,
                    caption_text     = excluded.caption_text,
                    quality          = excluded.quality,
                    style            = excluded.style,
                    conditioning_hook= excluded.conditioning_hook,
                    gen_scores       = excluded.gen_scores
                """,
                (
                    session,
                    filename,
                    json.dumps(meta.get("tags", []), ensure_ascii=False),
                    json.dumps(meta.get("open_tags", []), ensure_ascii=False),
                    meta.get("caption_text", ""),
                    meta.get("quality", "keep"),
                    meta.get("style", ""),
                    meta.get("conditioning_hook", ""),
                    json.dumps(gen_scores, ensure_ascii=False) if gen_scores else None,
                ),
            )
        conn.commit()


# ── Generation log ────────────────────────────────────────────────────────────


def load_gen_log(
    session: str,
    theme: str | None = None,
    limit: int = 200,
) -> list:
    """Return recent gen_log entries as a list of dicts.

    Entries are returned in chronological order (oldest first), with scores
    re-wrapped into a nested dict for backward compatibility with
    _build_history_context in image_gen_pipeline.py.
    """
    with _connect() as conn:
        if theme:
            rows = conn.execute(
                """SELECT * FROM gen_log
                   WHERE session=? AND theme=?
                   ORDER BY id DESC LIMIT ?""",
                (session, theme, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM gen_log WHERE session=? ORDER BY id DESC LIMIT ?",
                (session, limit),
            ).fetchall()

    # Return in chronological order, oldest first
    result = []
    for row in reversed(rows):
        entry = dict(row)
        # Re-wrap flat columns into scores dict for callers that expect it
        entry["scores"] = {
            "visual_quality": entry.pop("vq", None),
            "prompt_fidelity": entry.pop("pf", None),
            "conditioning_value": entry.pop("cv", None),
        }
        result.append(entry)
    return result


def save_session_quality(session_name: str, pipeline_result: dict) -> None:
    """Record review scores from a session creation pipeline run.

    ``pipeline_result`` is the dict returned by ``run_session_creation_cycle``.
    Call this after every run regardless of pass/fail so quality trends are
    visible over time.
    """
    import datetime as _dt

    scores = pipeline_result.get("review_scores") or {}
    passed = 1 if pipeline_result.get("status") == "created" else 0
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO session_quality
                (session_name, created_at, intent, attempts,
                 arc_coherence, phrase_quality, technical_validity,
                 conditioning_effectiveness, passed, failure_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_name,
                _dt.datetime.now().isoformat(timespec="seconds"),
                pipeline_result.get("intent", ""),
                pipeline_result.get("attempts", 1),
                scores.get("arc_coherence"),
                scores.get("phrase_quality"),
                scores.get("technical_validity"),
                scores.get("conditioning_effectiveness"),
                passed,
                scores.get("failure_note", "") or "",
            ),
        )
        conn.commit()


SESSION_CATEGORIES = [
    "general",
    "focus",
    "sleep",
    "entrainment",
    "genus",
    "edison",
    "ssild",
    "custom",
]


# ── Session registry ──────────────────────────────────────────────────────────


def upsert_session(
    name: str,
    description: str = "",
    image_tags: list | None = None,
    duration_s: float = 0,
    category: str = "general",
) -> None:
    """Register or update session metadata.

    INSERT sets created_at, is_favorite, and play_count to their defaults and
    never overwrites them on subsequent calls.  Only description, image_tags,
    duration_s, and category are updated on conflict.
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (name, description, image_tags, duration_s, category)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                image_tags  = excluded.image_tags,
                duration_s  = excluded.duration_s,
                category    = excluded.category
            """,
            (
                name,
                description or "",
                json.dumps(image_tags or [], ensure_ascii=False),
                float(duration_s or 0),
                category or "general",
            ),
        )
        conn.commit()


def record_session_played(name: str) -> None:
    """Bump play_count and stamp last_played for the given session."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (name, play_count, last_played)
            VALUES (?, 1, datetime('now', 'localtime'))
            ON CONFLICT(name) DO UPDATE SET
                play_count  = play_count + 1,
                last_played = datetime('now', 'localtime')
            """,
            (name,),
        )
        conn.commit()


def get_all_session_meta() -> dict:
    """Return {name: meta_dict} for every session in the registry."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM sessions").fetchall()
    return {
        row["name"]: {
            "description": row["description"],
            "image_tags": json.loads(row["image_tags"]),
            "duration_s": row["duration_s"],
            "category": row["category"],
            "is_favorite": bool(row["is_favorite"]),
            "created_at": row["created_at"],
            "last_played": row["last_played"],
            "play_count": row["play_count"],
        }
        for row in rows
    }


def get_images_by_tags(tags: list) -> list:
    """Return [{session, filename}] rows whose tags or open_tags overlap with tags.

    Uses SQLite JSON functions — scans all sessions in the images table.
    Falls back to an in-process filter if the sqlite version is old.
    """
    if not tags:
        return []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT session, filename, tags, open_tags FROM images"
        ).fetchall()
    tag_set = {t.lower() for t in tags}
    results = []
    for row in rows:
        try:
            all_tags = json.loads(row["tags"]) + json.loads(row["open_tags"])
        except Exception:
            continue
        if any(t.lower() in tag_set for t in all_tags):
            results.append({"session": row["session"], "filename": row["filename"]})
    return results


def toggle_favorite(name: str) -> bool:
    """Flip is_favorite for the named session and return the new value."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (name, is_favorite)
            VALUES (?, 1)
            ON CONFLICT(name) DO UPDATE SET
                is_favorite = NOT is_favorite
            """,
            (name,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT is_favorite FROM sessions WHERE name=?", (name,)
        ).fetchone()
    return bool(row["is_favorite"]) if row else True


# ── Generation log ────────────────────────────────────────────────────────────

# ── Session metrics (Bible Ch.6 §6.3) ──────────────────────────────────────────────────


def write_session_metrics(m: dict) -> int:
    """Insert a session metrics row. Returns the new row id."""
    cfg = m.get("config_snapshot") or {}
    fl = m.get("freq_lead_data") or {}
    cas = m.get("cascade_data") or {}  # Bible Ch.4 §4.6 phase-cascade summary
    target = m.get("target_band", (0.0, 8.0))
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO session_metrics (
                session_id, session_date, session_preset, duration_sec,
                depth_min_sef95, depth_mean_sef95,
                time_in_target_sec, time_in_target_pct,
                target_band_low, target_band_high,
                entrainment_mean_assr, entrainment_peak_assr, entrainment_lock_pct,
                transition_speed_sec, stability_sef95_std,
                receptivity_mean_faa, receptivity_approach_pct,
                signal_quality_mean, signal_quality_dropout_pct,
                composite_score,
                freq_lead_start_hz, freq_lead_end_hz,
                freq_lead_holds, freq_lead_steps,
                beat_type, veil_mode_primary, spiral_style,
                spiral_chaos, trail_decay, agent_notes,
                peak_isa_alpha_pac, peak_theta_gamma_pac, mean_cascade_integrity,
                optimal_breath_rate, optimal_beat_hz,
                phase_gate_hit_rate, delivery_rate_hz
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
            """,
            (
                m.get("session_id"),
                m.get("session_date"),
                m.get("session_preset"),
                m.get("duration_sec"),
                m.get("depth_min_sef95"),
                m.get("depth_mean_sef95"),
                m.get("time_in_target_sec"),
                m.get("time_in_target_pct"),
                target[0],
                target[1],
                m.get("entrainment_mean_assr"),
                m.get("entrainment_peak_assr"),
                m.get("entrainment_lock_pct"),
                m.get("transition_speed_sec"),
                m.get("stability_sef95_std"),
                m.get("receptivity_mean_faa"),
                m.get("receptivity_approach_pct"),
                m.get("signal_quality_mean"),
                m.get("signal_quality_dropout_pct"),
                m.get("composite_score"),
                fl.get("start_freq"),
                fl.get("end_freq"),
                fl.get("holds_total"),
                fl.get("steps_completed"),
                cfg.get("beat_type", "binaural"),
                cfg.get("veil_mode_primary"),
                cfg.get("spiral_style"),
                cfg.get("spiral_chaos"),
                cfg.get("trail_decay"),
                m.get("agent_notes"),
                cas.get("peak_isa_alpha_pac"),
                cas.get("peak_theta_gamma_pac"),
                cas.get("mean_cascade_integrity"),
                cas.get("optimal_breath_rate"),
                cas.get("optimal_beat_hz"),
                cas.get("phase_gate_hit_rate"),
                cas.get("delivery_rate_hz"),
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_session_metrics(n: int = 20) -> list[dict]:
    """Return the N most recent session_metrics rows as dicts."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM session_metrics ORDER BY session_date DESC LIMIT ?", (n,)
        ).fetchall()
    return [dict(r) for r in rows]


def best_config_for_preset(preset: str, top_n: int = 5) -> dict:
    """Find config parameters from top-scoring sessions for a given preset."""
    from collections import Counter

    with _connect() as conn:
        rows = conn.execute(
            """SELECT * FROM session_metrics
               WHERE session_preset=? AND signal_quality_mean > 0.5
               ORDER BY composite_score DESC LIMIT ?""",
            (preset, top_n),
        ).fetchall()
    if not rows:
        return {}
    configs = [dict(r) for r in rows]

    def _most_common(lst):
        flt = [x for x in lst if x is not None]
        return Counter(flt).most_common(1)[0][0] if flt else None

    def _mean(lst):
        flt = [x for x in lst if x is not None]
        return round(float(sum(flt) / len(flt)), 3) if flt else None

    return {
        "recommended_spiral_style": _most_common([c["spiral_style"] for c in configs]),
        "recommended_veil_mode": _most_common(
            [c["veil_mode_primary"] for c in configs]
        ),
        "recommended_beat_type": _most_common([c["beat_type"] for c in configs]),
        "avg_chaos": _mean([c["spiral_chaos"] for c in configs]),
        "avg_trail_decay": _mean([c["trail_decay"] for c in configs]),
        "avg_score": _mean([c["composite_score"] for c in configs]),
        "sample_size": len(configs),
    }


def trend_metric(metric: str, n: int = 20) -> dict:
    """Compute trend direction for a metric over the last N sessions."""
    safe = {
        "composite_score",
        "depth_min_sef95",
        "depth_mean_sef95",
        "entrainment_mean_assr",
        "receptivity_approach_pct",
        "signal_quality_mean",
        "transition_speed_sec",
    }
    if metric not in safe:
        return {"trend": "invalid_metric"}
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT {metric} FROM session_metrics "
            f"WHERE {metric} IS NOT NULL ORDER BY session_date DESC LIMIT ?",
            (n,),
        ).fetchall()
    if not rows:
        return {"trend": "no_data"}
    values = [r[0] for r in reversed(rows)]  # chronological
    if len(values) < 3:
        return {"trend": "insufficient_data", "values": values}

    import numpy as _np

    x = _np.arange(len(values))
    slope, _ = _np.polyfit(x, values, 1)
    if slope > 0.5:
        direction = "improving"
    elif slope < -0.5:
        direction = "declining"
    else:
        direction = "stable"
    return {
        "trend": direction,
        "slope": round(float(slope), 3),
        "latest": values[-1],
        "mean": round(float(sum(values) / len(values)), 2),
        "sessions_analyzed": len(values),
    }


# ── Generation log ────────────────────────────────────────────────────────────


def append_gen_log(session: str, entry: dict) -> None:
    """Append one generation attempt to the log.

    Accepts the same dict shape produced by run_pipeline_cycle, including
    the nested 'scores' key.
    """
    scores = entry.get("scores") or {}
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO gen_log
                (ts, session, theme, tag, attempt, prompt, prompt_base,
                 caption, ref_image, action, vq, pf, cv, failure_note, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.get("ts", ""),
                session,
                entry.get("theme", ""),
                entry.get("tag", ""),
                entry.get("attempt", 1),
                entry.get("prompt", ""),
                entry.get("prompt_base", ""),
                entry.get("caption", ""),
                entry.get("ref_image", ""),
                entry.get("action", ""),
                scores.get("visual_quality"),
                scores.get("prompt_fidelity"),
                scores.get("conditioning_value"),
                entry.get("failure_note", ""),
                entry.get("note", ""),
            ),
        )
        conn.commit()


# ── Conductor decision log ─────────────────────────────────────────────────────


def write_conductor_decisions_batch(session_id: str, entries: list) -> None:
    """Flush a batch of Conductor decision log entries to somna.db.

    Each entry is a dict produced by Conductor._log_decision():
        timestamp, session_elapsed, phase, action, rationale,
        sqi_confidence, trance_score, sef95, assr_strength, assr_confidence,
        faa_value, beat_freq, chaos, trail_decay, tick_rate, parameters_json
    """
    if not entries:
        return
    rows = []
    for e in entries:
        rows.append(
            (
                session_id,
                e.get("timestamp"),
                e.get("session_elapsed"),
                e.get("phase"),
                e.get("action"),
                e.get("rationale"),
                e.get("sqi_confidence"),
                e.get("trance_score"),
                e.get("sef95"),
                e.get("assr_strength"),
                e.get("assr_confidence"),
                e.get("faa_value"),
                e.get("beat_freq"),
                e.get("chaos"),
                e.get("trail_decay"),
                e.get("tick_rate"),
                e.get("parameters_json"),
            )
        )
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO conductor_decisions
                (session_id, timestamp, session_elapsed, phase, action, rationale,
                 sqi_confidence, trance_score, sef95, assr_strength, assr_confidence,
                 faa_value, beat_freq, chaos, trail_decay, tick_rate, parameters_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def get_phase_summary(session_id: str) -> list:
    """Return phase_summary rows for a given session_id."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM phase_summary WHERE session_id = ? ORDER BY phase_start",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_latest_session_notes(session_name: str, notes: str) -> None:
    """Write agent_notes onto the most recent session_metrics row for this session.

    No-op if no session_metrics rows exist for session_name yet (e.g. no EEG
    was active so session_scorer never ran).
    """
    with _connect() as conn:
        conn.execute(
            """
            UPDATE session_metrics SET agent_notes = ?
            WHERE id = (
                SELECT id FROM session_metrics
                WHERE session_id = ?
                ORDER BY id DESC LIMIT 1
            )
            """,
            (notes, session_name),
        )
        conn.commit()


# ── Calibration DB access ─────────────────────────────────────────────────────


def cal_upsert_baseline(
    session_number: int,
    metric: str,
    condition: str,
    value: float,
    channel: str | None = None,
    sd: float | None = None,
    n_samples: int | None = None,
    sqi_mean: float | None = None,
) -> None:
    import time as _time

    with _connect() as conn:
        conn.execute(
            """INSERT INTO calibration_baselines
               (session_number, metric, channel, condition, value, sd,
                n_samples, sqi_mean, timestamp)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(session_number, metric, channel, condition)
               DO UPDATE SET value=excluded.value, sd=excluded.sd,
                             n_samples=excluded.n_samples, sqi_mean=excluded.sqi_mean,
                             timestamp=excluded.timestamp""",
            (
                session_number,
                metric,
                channel,
                condition,
                value,
                sd,
                n_samples,
                sqi_mean,
                _time.strftime("%Y-%m-%dT%H:%M:%S"),
            ),
        )
        conn.commit()


def cal_get_baselines(
    session_number: int | None = None,
    metric: str | None = None,
    condition: str | None = None,
) -> list:
    clauses, params = [], []
    if session_number is not None:
        clauses.append("session_number = ?")
        params.append(session_number)
    if metric is not None:
        clauses.append("metric = ?")
        params.append(metric)
    if condition is not None:
        clauses.append("condition = ?")
        params.append(condition)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM calibration_baselines {where} ORDER BY session_number, timestamp",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def cal_upsert_threshold(
    metric: str,
    value: float,
    derived_from_sessions: str,
    derivation_method: str,
    confidence: str,
) -> None:
    import time as _time

    with _connect() as conn:
        conn.execute(
            """INSERT INTO calibration_thresholds
               (metric, value, derived_from_sessions, derivation_method,
                confidence, updated_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(metric) DO UPDATE SET
                 value=excluded.value,
                 derived_from_sessions=excluded.derived_from_sessions,
                 derivation_method=excluded.derivation_method,
                 confidence=excluded.confidence,
                 updated_at=excluded.updated_at""",
            (
                metric,
                value,
                derived_from_sessions,
                derivation_method,
                confidence,
                _time.strftime("%Y-%m-%dT%H:%M:%S"),
            ),
        )
        conn.commit()


def cal_get_thresholds() -> dict:
    """Return {metric: value} for all stored thresholds."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT metric, value FROM calibration_thresholds"
        ).fetchall()
    return {r["metric"]: r["value"] for r in rows}


def cal_log_session(
    session_number: int,
    phase: str,
    started_at: str,
    completed_at: str | None = None,
    duration_seconds: float | None = None,
    max_phase_reached: str | None = None,
    notes: str = "",
    thresholds_json: str = "",
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO calibration_sessions
               (session_number, phase, started_at, completed_at,
                duration_seconds, max_conductor_phase_reached,
                notes, thresholds_derived)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(session_number) DO UPDATE SET
                 completed_at=excluded.completed_at,
                 duration_seconds=excluded.duration_seconds,
                 max_conductor_phase_reached=excluded.max_conductor_phase_reached,
                 notes=excluded.notes,
                 thresholds_derived=excluded.thresholds_derived""",
            (
                session_number,
                phase,
                started_at,
                completed_at,
                duration_seconds,
                max_phase_reached,
                notes,
                thresholds_json,
            ),
        )
        conn.commit()


def cal_get_sessions() -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM calibration_sessions ORDER BY session_number"
        ).fetchall()
    return [dict(r) for r in rows]


def cal_append_assr_curve(
    session_number: int,
    frequency_hz: float,
    assr_strength: float,
    hold_duration_s: float,
    sqi_mean: float | None = None,
) -> None:
    import time as _time

    with _connect() as conn:
        conn.execute(
            """INSERT INTO calibration_assr_curve
               (session_number, frequency_hz, assr_strength,
                hold_duration_s, sqi_mean, timestamp)
               VALUES (?,?,?,?,?,?)""",
            (
                session_number,
                frequency_hz,
                assr_strength,
                hold_duration_s,
                sqi_mean,
                _time.strftime("%Y-%m-%dT%H:%M:%S"),
            ),
        )
        conn.commit()


def cal_get_assr_curve(session_number: int | None = None) -> list:
    where = "WHERE session_number = ?" if session_number is not None else ""
    params = [session_number] if session_number is not None else []
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM calibration_assr_curve {where} ORDER BY frequency_hz",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


# ── Semantic selector (Bible Ch.6 §6.6) ────────────────────────────────────────────────


def write_content_cascades_batch(session_id: str, cascades: list) -> None:
    """Bulk-insert cascade events logged by SemanticSelector."""
    if not cascades:
        return
    rows = [
        (
            session_id,
            c.get("ts", 0.0),
            c.get("pool_id", ""),
            c.get("shadow_word"),
            c.get("center_phrase"),
            c.get("voice_phrase"),
            c.get("cascade_index"),
            c.get("conductor_phase"),
            c.get("faa"),
            c.get("trance_score"),
            c.get("theta_alpha_ratio"),
            c.get("sqi"),
        )
        for c in cascades
    ]
    with _connect() as conn:
        conn.executemany(
            """INSERT INTO content_cascades
               (session_id, ts, pool_id, shadow_word, center_phrase, voice_phrase,
                cascade_index, conductor_phase, faa, trance_score, theta_alpha_ratio, sqi)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()


def write_pool_transitions_batch(session_id: str, transitions: list) -> None:
    """Bulk-insert pool transition events logged by SemanticSelector."""
    if not transitions:
        return
    rows = [
        (
            session_id,
            t.get("ts", 0.0),
            t.get("from_pool"),
            t.get("to_pool", ""),
            t.get("faa"),
            t.get("trance"),
            t.get("theta_alpha"),
            t.get("conductor_phase"),
        )
        for t in transitions
    ]
    with _connect() as conn:
        conn.executemany(
            """INSERT INTO pool_transitions
               (session_id, ts, from_pool, to_pool, faa, trance_score,
                theta_alpha_ratio, conductor_phase)
               VALUES (?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()


def write_content_effectiveness(session_id: str, pool_scores: dict) -> None:
    """Insert per-pool effectiveness scores after session end."""
    if not pool_scores:
        return
    rows = [
        (
            session_id,
            pool_id,
            scores.get("cascade_count", 0),
            scores.get("mean_delta_trance"),
            scores.get("mean_delta_faa"),
            scores.get("mean_delta_assr"),
            scores.get("effectiveness_score"),
        )
        for pool_id, scores in pool_scores.items()
    ]
    with _connect() as conn:
        conn.executemany(
            """INSERT INTO content_effectiveness
               (session_id, pool_id, cascade_count, mean_delta_trance,
                mean_delta_faa, mean_delta_assr, effectiveness_score)
               VALUES (?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()


def update_pool_weights(pool_scores: dict, ema_alpha: float = 0.3) -> None:
    """
    EMA-update pool_weights table from a per-pool effectiveness dict.
    pool_scores: {pool_id: {"effectiveness_score": float}}
    """
    if not pool_scores:
        return
    import time as _time

    now = _time.time()
    with _connect() as conn:
        for pool_id, scores in pool_scores.items():
            new_eff = scores.get("effectiveness_score", 0.0) or 0.0
            row = conn.execute(
                "SELECT weight, session_count FROM pool_weights WHERE pool_id = ?",
                (pool_id,),
            ).fetchone()
            if row:
                old_weight = row["weight"]
                new_weight = (1 - ema_alpha) * old_weight + ema_alpha * (1.0 + new_eff)
                conn.execute(
                    """UPDATE pool_weights
                       SET weight = ?, last_updated = ?, session_count = session_count + 1
                       WHERE pool_id = ?""",
                    (new_weight, now, pool_id),
                )
            else:
                conn.execute(
                    """INSERT INTO pool_weights (pool_id, weight, last_updated, session_count)
                       VALUES (?, ?, ?, 1)""",
                    (pool_id, 1.0 + new_eff * ema_alpha, now),
                )
        conn.commit()


def get_pool_weights() -> dict:
    """Load current pool weights for session start. Returns {pool_id: weight}."""
    with _connect() as conn:
        rows = conn.execute("SELECT pool_id, weight FROM pool_weights").fetchall()
    return {r["pool_id"]: r["weight"] for r in rows}


def get_pool_effectiveness_history(pool_id: str, n_sessions: int = 20) -> list:
    """Longitudinal pool performance for a given pool_id."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT * FROM content_effectiveness
               WHERE pool_id = ?
               ORDER BY id DESC LIMIT ?""",
            (pool_id, n_sessions),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Bible Ch.3 §3.8: Crossmodal Gain Engine ───────────────────────────────────────────


def log_gain_decision(
    session_id: str,
    ts: float,
    conductor_phase: str,
    depth_scalar,
    sr_factor,
    noise_ratio,
    raw_noise,
    effective_noise,
    raw_text_opacity,
    effective_text_opacity,
    carrier_noise_ratio,
) -> None:
    """Insert one gain decision record.  Caller batches at its own rate."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO gain_decisions
               (session_id, ts, conductor_phase, depth_scalar, sr_factor, noise_ratio,
                raw_noise, effective_noise, raw_text_opacity, effective_text_opacity,
                carrier_noise_ratio)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id,
                ts,
                conductor_phase,
                depth_scalar,
                sr_factor,
                noise_ratio,
                raw_noise,
                effective_noise,
                raw_text_opacity,
                effective_text_opacity,
                carrier_noise_ratio,
            ),
        )
        conn.commit()


def store_sr_calibration(session_id: str, calibration_result: dict) -> None:
    """Persist SR calibration results for longitudinal tracking."""
    import time as _t

    with _connect() as conn:
        conn.execute(
            """INSERT INTO sr_calibration
               (session_id, calibrated_at, sr_optimal_noise, sr_gain_bonus,
                calibration_curve, baseline_alpha, carrier_noise_threshold)
               VALUES (?,?,?,?,?,?,?)""",
            (
                session_id,
                _t.time(),
                calibration_result["sr_optimal_noise"],
                calibration_result["sr_gain_bonus"],
                json.dumps(calibration_result.get("sr_calibration_curve", [])),
                calibration_result.get("sr_baseline_alpha"),
                calibration_result.get("carrier_noise_threshold"),
            ),
        )
        conn.commit()


def get_latest_sr_calibration(session_id: str = None) -> Optional[dict]:
    """Return the most recent SR calibration record.

    If session_id is None, returns the global latest across all sessions.
    Returns None if no calibration has been performed yet.
    """
    with _connect() as conn:
        if session_id:
            row = conn.execute(
                "SELECT * FROM sr_calibration WHERE session_id=? ORDER BY calibrated_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM sr_calibration ORDER BY calibrated_at DESC LIMIT 1"
            ).fetchone()
    if not row:
        return None
    return {
        "sr_optimal_noise": row["sr_optimal_noise"],
        "sr_gain_bonus": row["sr_gain_bonus"],
        "calibration_curve": json.loads(row["calibration_curve"]),
        "baseline_alpha": row["baseline_alpha"],
        "carrier_noise_threshold": row["carrier_noise_threshold"],
    }


# ── Bible Ch.2 §2.8: Depth Estimation ─────────────────────────────────────────────────


def log_depth_estimate(
    session_id: str,
    ts: float,
    conductor_phase: str,
    spectral_slope,
    slope_confidence,
    frontal_alpha_coh,
    frontal_beta_coh,
    temporal_theta_coh,
    beta_env_corr,
    coherence_depth,
    trance_score_v1,
    trance_score_v2,
) -> None:
    """Insert one depth estimation record.  Called at EEG tick rate (1 Hz)."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO depth_estimates
               (session_id, ts, conductor_phase,
                spectral_slope, slope_confidence,
                frontal_alpha_coh, frontal_beta_coh, temporal_theta_coh,
                beta_env_corr, coherence_depth,
                trance_score_v1, trance_score_v2)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id,
                ts,
                conductor_phase,
                spectral_slope,
                slope_confidence,
                frontal_alpha_coh,
                frontal_beta_coh,
                temporal_theta_coh,
                beta_env_corr,
                coherence_depth,
                trance_score_v1,
                trance_score_v2,
            ),
        )
        conn.commit()


def store_calibration_v2(
    session_id: str,
    iaf_hz: float,
    baseline_slope: float,
    baseline_frontal_alpha_coh: Optional[float] = None,
    baseline_beta_env_corr: Optional[float] = None,
    baseline_temporal_theta_coh: Optional[float] = None,
    slope_samples: Optional[list] = None,
    calibration_quality: str = "good",
) -> None:
    """Persist Bible Ch.2 §2.8 baseline coherence and slope from calibration window."""
    import time as _t

    with _connect() as conn:
        conn.execute(
            """INSERT INTO calibration_v2
               (session_id, calibrated_at, iaf_hz, baseline_slope,
                baseline_frontal_alpha_coh, baseline_beta_env_corr,
                baseline_temporal_theta_coh, slope_samples, calibration_quality)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                session_id,
                _t.time(),
                iaf_hz,
                baseline_slope,
                baseline_frontal_alpha_coh,
                baseline_beta_env_corr,
                baseline_temporal_theta_coh,
                json.dumps(slope_samples) if slope_samples else None,
                calibration_quality,
            ),
        )
        conn.commit()


def get_latest_calibration_v2(session_id: str = None) -> Optional[dict]:
    """Return most recent Bible Ch.2 §2.8 calibration record."""
    with _connect() as conn:
        if session_id:
            row = conn.execute(
                "SELECT * FROM calibration_v2 WHERE session_id=? ORDER BY calibrated_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM calibration_v2 ORDER BY calibrated_at DESC LIMIT 1"
            ).fetchone()
    if not row:
        return None
    return {
        "iaf_hz": row["iaf_hz"],
        "baseline_slope": row["baseline_slope"],
        "baseline_frontal_alpha_coh": row["baseline_frontal_alpha_coh"],
        "baseline_beta_env_corr": row["baseline_beta_env_corr"],
        "baseline_temporal_theta_coh": row["baseline_temporal_theta_coh"],
        "calibration_quality": row["calibration_quality"],
    }


# ── Bible Ch.7 §7.1: Sleep stage log + sleep calibration ───────────────────────────────


def log_sleep_stage(
    session_id: str,
    ts: float,
    stage: str,
    confidence: float,
    spectral_slope: Optional[float] = None,
    delta_power: Optional[float] = None,
    spindle_density: Optional[float] = None,
    sigma_amplitude: Optional[float] = None,
    sw_burst_delivered: int = 0,
) -> None:
    """Insert one throttled (30-s) sleep stage record."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO sleep_stage_log
               (session_id, timestamp, stage, confidence,
                spectral_slope, delta_power, spindle_density, sigma_amplitude,
                sw_burst_delivered)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                session_id,
                ts,
                stage,
                confidence,
                spectral_slope,
                delta_power,
                spindle_density,
                sigma_amplitude,
                sw_burst_delivered,
            ),
        )
        conn.commit()


def log_sleep_calibration(session_id: str, thresholds: dict) -> None:
    """Persist per-user sleep classifier threshold update."""
    import time as _t

    with _connect() as conn:
        conn.execute(
            """INSERT INTO sleep_calibration
               (session_id, timestamp,
                slope_wake_n1, slope_n1_n2, slope_n2_n3, slope_rem_ceil,
                delta_n3_floor, spindle_n2_floor, alpha_wake_floor,
                beta_dropout_ceil, rem_theta_floor,
                calib_slope_wake, calib_beta_wake,
                calib_alpha_antiphase_tolerance, calib_spindle_baseline,
                calib_swa_response_ratio)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id,
                _t.time(),
                thresholds.get("slope_wake_n1"),
                thresholds.get("slope_n1_n2"),
                thresholds.get("slope_n2_n3"),
                thresholds.get("slope_rem_ceil"),
                thresholds.get("delta_n3_floor"),
                thresholds.get("spindle_n2_floor"),
                thresholds.get("alpha_wake_floor"),
                thresholds.get("beta_dropout_ceil"),
                thresholds.get("rem_theta_floor"),
                thresholds.get("calib_slope_wake"),
                thresholds.get("calib_beta_wake"),
                thresholds.get("calib_alpha_antiphase_tolerance"),
                thresholds.get("calib_spindle_baseline"),
                thresholds.get("calib_swa_response_ratio"),
            ),
        )
        conn.commit()


def get_latest_sleep_calibration(session_id: str = None) -> Optional[dict]:
    """Return most recent sleep classifier thresholds for per-user override."""
    with _connect() as conn:
        if session_id:
            row = conn.execute(
                """SELECT * FROM sleep_calibration WHERE session_id=?
                   ORDER BY timestamp DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM sleep_calibration ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
    if not row:
        return None
    return dict(row)


# ── TMR functions (Bible Ch.7 §7.5) ────────────────────────────────────────────────────


def upsert_tmr_cue_registry(
    session_id: str,
    pool: str,
    content_hash: str,
    affirmation_text: str,
    strength_alpha: float = 0.20,
) -> None:
    """Insert or update a cue registry entry.

    On each encoding event, encoding_count increments by 1 and strength is
    updated via EMA toward a target of 0.5 + 0.5 * min(count / 10, 1.0) —
    i.e., the cue builds from 0.5 to 1.0 over ~10 presentations.  The
    scheduler's inverted-U priority curve then favours mid-range strengths,
    naturally de-prioritising over-learned cues.
    """
    import time as _time

    now = _time.time()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT encoding_count, strength FROM tmr_cue_registry "
            "WHERE session_id=? AND pool=? AND content_hash=?",
            (session_id, pool, content_hash),
        ).fetchone()
        if existing:
            count = existing["encoding_count"] + 1
            target = 0.5 + 0.5 * min(count / 10.0, 1.0)
            strength = (
                existing["strength"] * (1 - strength_alpha) + target * strength_alpha
            )
            conn.execute(
                """UPDATE tmr_cue_registry
                   SET encoding_count=?, strength=?, last_encoded_at=?,
                       affirmation_text=?
                   WHERE session_id=? AND pool=? AND content_hash=?""",
                (
                    count,
                    round(strength, 4),
                    now,
                    affirmation_text,
                    session_id,
                    pool,
                    content_hash,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO tmr_cue_registry
                   (session_id, pool, content_hash, affirmation_text,
                    encoding_count, strength, last_encoded_at)
                   VALUES (?, ?, ?, ?, 1, 0.5, ?)""",
                (session_id, pool, content_hash, affirmation_text, now),
            )
        conn.commit()


def get_tmr_cue_registry(session_id: str) -> list:
    """Return all cue registry rows for a session as a list of dicts."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT pool, content_hash, affirmation_text, encoding_count, strength "
            "FROM tmr_cue_registry WHERE session_id=? ORDER BY last_encoded_at DESC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def log_tmr_encoding(
    session_id: str,
    pool: str,
    content_hash: str,
    affirmation_text: str,
    timestamp: float,
) -> None:
    """Append one row to tmr_encoding_log."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO tmr_encoding_log
               (session_id, pool, content_hash, affirmation_text, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, pool, content_hash, affirmation_text, timestamp),
        )
        conn.commit()


def log_tmr_replay(
    session_id: str,
    pool: str,
    content_hash: str,
    sleep_stage: str,
    timestamp: float,
) -> None:
    """Append one row to tmr_replay_log."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO tmr_replay_log
               (session_id, pool, content_hash, sleep_stage, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, pool, content_hash, sleep_stage, timestamp),
        )
        conn.commit()


# ── HTW functions (Bible Ch.9 §9.1) ────────────────────────────────────────────────────


def log_sleep_training_window(
    session_id: str,
    htw_index: int,
    started_at: float,
    duration_s: float,
    stage_at_entry: str,
    stage_at_exit: str,
    focus_pool: str,
    phrases_delivered: int,
    exit_reason: str,
) -> None:
    """Append one row to sleep_training_log."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO sleep_training_log
               (session_id, htw_index, started_at, duration_s,
                stage_at_entry, stage_at_exit, focus_pool,
                phrases_delivered, exit_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                htw_index,
                started_at,
                duration_s,
                stage_at_entry,
                stage_at_exit,
                focus_pool,
                phrases_delivered,
                exit_reason,
            ),
        )
        conn.commit()


def get_sleep_stage_log_summary(session_id: str) -> dict:
    """Return {stage: total_seconds} and total elapsed from sleep_stage_log."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT stage, COUNT(*) as n
               FROM sleep_stage_log
               WHERE session_id=?
               GROUP BY stage""",
            (session_id,),
        ).fetchall()
    dist = {r["stage"]: r["n"] * 30 for r in rows}  # 30 s per log entry
    return dist


def log_edison_capture(
    session_id: str,
    capture_index: int,
    n1_onset_ts: float,
    n1_duration_s: float,
    alpha_theta_ratio: float,
    seed_topic: str,
    user_report: str,
    eeg_snapshot: str,
    wake_cue_type: str,
    cycle_complete_ts: float,
) -> None:
    """Append one capture row to edison_captures."""
    with _connect() as conn:
        conn.execute(
            """INSERT INTO edison_captures
               (session_id, capture_index, n1_onset_ts, n1_duration_s,
                alpha_theta_ratio, seed_topic, user_report, eeg_snapshot,
                wake_cue_type, cycle_complete_ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                capture_index,
                n1_onset_ts,
                n1_duration_s,
                alpha_theta_ratio,
                seed_topic,
                user_report,
                eeg_snapshot,
                wake_cue_type,
                cycle_complete_ts,
            ),
        )
        conn.commit()


def get_edison_captures(session_id: str) -> list:
    """Return all captures for a session, ordered by capture_index."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM edison_captures WHERE session_id=? ORDER BY capture_index",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_tmr_replay_summary(session_id: str) -> dict:
    """Return {pool: replay_count} from tmr_replay_log."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT pool, COUNT(*) as n
               FROM tmr_replay_log
               WHERE session_id=?
               GROUP BY pool""",
            (session_id,),
        ).fetchall()
    return {r["pool"]: r["n"] for r in rows}


def update_session_htw_metrics(
    session_id: str,
    htw_count: int,
    htw_total_duration_s: float,
    htw_success_rate: float,
) -> None:
    """Write HTW aggregate columns onto the existing session_metrics row.

    Must be called after log_session_metrics() has already created the row.
    Silently no-ops if no row exists for that session_id yet.
    """
    with _connect() as conn:
        conn.execute(
            """UPDATE session_metrics
               SET htw_count=?, htw_total_duration_s=?, htw_success_rate=?
               WHERE session_id=?""",
            (htw_count, round(htw_total_duration_s, 1), htw_success_rate, session_id),
        )
        conn.commit()


def get_sleep_training_log_summary(session_id: str) -> dict:
    """Return {htw_count, total_duration_s, success_rate} for a session."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT duration_s, exit_reason FROM sleep_training_log WHERE session_id=?",
            (session_id,),
        ).fetchall()
    if not rows:
        return {"htw_count": 0, "total_duration_s": 0.0, "success_rate": 0.0}
    total = len(rows)
    successes = sum(1 for r in rows if r["exit_reason"] == "n2_detected")
    return {
        "htw_count": total,
        "total_duration_s": sum(r["duration_s"] for r in rows),
        "success_rate": round(successes / total, 3),
    }


# ── Bible Ch.10 §10.1: Conditioning Engine ───────────────────────────────────────────────


def log_conditioning_association(
    record_id: str,
    session_id: str,
    timestamp_ms: int,
    cs_class: str,
    cs_identity: str,
    cs_pool: str,
    us_type: str,
    us_magnitude: float,
    conductor_phase: str,
    modality: str,
    contiguity_ms: int,
    delivery_gate_state: dict | None = None,
    neural_state_fingerprint: dict | None = None,
    cardiac_phase: float | None = None,
    respiratory_phase: float | None = None,
) -> None:
    """Append one CS–US pairing event."""
    with _connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO conditioning_associations
               (record_id, session_id, timestamp_ms, cs_class, cs_identity, cs_pool,
                us_type, us_magnitude, delivery_gate_state, neural_state_fingerprint,
                cardiac_phase, respiratory_phase, conductor_phase, modality, contiguity_ms)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record_id,
                session_id,
                timestamp_ms,
                cs_class,
                cs_identity,
                cs_pool,
                us_type,
                us_magnitude,
                json.dumps(delivery_gate_state) if delivery_gate_state else None,
                json.dumps(neural_state_fingerprint)
                if neural_state_fingerprint
                else None,
                cardiac_phase,
                respiratory_phase,
                conductor_phase,
                modality,
                contiguity_ms,
            ),
        )
        conn.commit()


def upsert_conditioning_strength(
    cs_identity: str,
    cs_pool: str,
    us_type: str,
    conductor_phase: str,
    strength_delta: float,
    salience: float = 1.0,
    extinction_rate: float = 0.02,
    is_second_order: bool = False,
) -> None:
    """Increment trial_count and EMA-update strength by delta."""
    import time as _t

    now_ms = int(_t.time() * 1000)
    with _connect() as conn:
        row = conn.execute(
            "SELECT strength, trial_count FROM conditioning_strengths "
            "WHERE cs_identity=? AND us_type=? AND conductor_phase=?",
            (cs_identity, us_type, conductor_phase),
        ).fetchone()
        if row:
            new_strength = max(0.0, min(1.0, row["strength"] + strength_delta))
            conn.execute(
                """UPDATE conditioning_strengths
                   SET strength=?, trial_count=trial_count+1, last_pairing_ts=?,
                       salience=?, extinction_rate=?
                   WHERE cs_identity=? AND us_type=? AND conductor_phase=?""",
                (
                    round(new_strength, 4),
                    now_ms,
                    salience,
                    extinction_rate,
                    cs_identity,
                    us_type,
                    conductor_phase,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO conditioning_strengths
                   (cs_identity, cs_pool, us_type, conductor_phase, strength,
                    trial_count, last_pairing_ts, salience, extinction_rate, is_second_order)
                   VALUES (?,?,?,?,?,1,?,?,?,?)""",
                (
                    cs_identity,
                    cs_pool,
                    us_type,
                    conductor_phase,
                    max(0.0, min(1.0, strength_delta)),
                    now_ms,
                    salience,
                    extinction_rate,
                    int(is_second_order),
                ),
            )
        conn.commit()


def get_conditioning_strengths(cs_pool: str = None) -> list[dict]:
    """Return all (or pool-filtered) conditioning strength rows."""
    with _connect() as conn:
        if cs_pool:
            rows = conn.execute(
                "SELECT * FROM conditioning_strengths WHERE cs_pool=? ORDER BY strength DESC",
                (cs_pool,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM conditioning_strengths ORDER BY strength DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def upsert_shaping_progress(
    user_id: str,
    metric_name: str,
    session_value: float,
    current_percentile: float,
) -> None:
    """Update shaping progress EMA for a user metric."""
    import time as _t

    now = _t.time()
    with _connect() as conn:
        row = conn.execute(
            "SELECT best_session_value, mean_session_value, session_count "
            "FROM shaping_progress WHERE user_id=? AND metric_name=?",
            (user_id, metric_name),
        ).fetchone()
        if row:
            best = max(row["best_session_value"] or session_value, session_value)
            n = (row["session_count"] or 0) + 1
            mean = (
                (row["mean_session_value"] or session_value) * (n - 1) + session_value
            ) / n
            conn.execute(
                """UPDATE shaping_progress
                   SET current_percentile=?, session_count=?, best_session_value=?,
                       mean_session_value=?, last_session_ts=?
                   WHERE user_id=? AND metric_name=?""",
                (
                    current_percentile,
                    n,
                    round(best, 4),
                    round(mean, 4),
                    now,
                    user_id,
                    metric_name,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO shaping_progress
                   (user_id, metric_name, current_percentile, session_count,
                    best_session_value, mean_session_value, last_session_ts)
                   VALUES (?,?,?,1,?,?,?)""",
                (
                    user_id,
                    metric_name,
                    current_percentile,
                    session_value,
                    session_value,
                    now,
                ),
            )
        conn.commit()


def log_cue_test_result(
    session_id: str,
    cs_identity: str,
    cs_pool: str,
    overall_cr_rate: float,
    trial_results: list,
    graduated_pools: list,
    baseline_snapshot: dict | None = None,
) -> None:
    """Record one conditioned-response test event."""
    import time as _t

    with _connect() as conn:
        conn.execute(
            """INSERT INTO cue_test_results
               (session_id, test_ts, cs_identity, cs_pool, baseline_snapshot,
                trial_results, overall_cr_rate, graduated_pools)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                session_id,
                _t.time(),
                cs_identity,
                cs_pool,
                json.dumps(baseline_snapshot) if baseline_snapshot else None,
                json.dumps(trial_results),
                overall_cr_rate,
                json.dumps(graduated_pools),
            ),
        )
        conn.commit()


# ── Bible Ch.10 §10.3: Habituation Engine ────────────────────────────────────────────────


def get_stimulus_exposure(stimulus_id: str) -> dict | None:
    """Return the full exposure row for a stimulus, or None if unseen."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM stimulus_exposure WHERE stimulus_id=?", (stimulus_id,)
        ).fetchone()
    return dict(row) if row else None


def upsert_stimulus_exposure(
    stimulus_id: str,
    stimulus_class: str,
    layer: str,
    presentations_delta: int = 1,
    exposure_s_delta: float = 0.0,
    state: str = "novel",
    macro_novelty: float = 1.0,
    cooling_since_ts: float | None = None,
) -> None:
    """Increment lifetime counters and update novelty state."""
    import time as _t

    now = _t.time()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM stimulus_exposure WHERE stimulus_id=?", (stimulus_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE stimulus_exposure
                   SET lifetime_presentations = lifetime_presentations + ?,
                       lifetime_exposure_s = lifetime_exposure_s + ?,
                       last_session_ts = ?,
                       state = ?,
                       macro_novelty = ?,
                       cooling_since_ts = COALESCE(?, cooling_since_ts)
                   WHERE stimulus_id=?""",
                (
                    presentations_delta,
                    exposure_s_delta,
                    now,
                    state,
                    macro_novelty,
                    cooling_since_ts,
                    stimulus_id,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO stimulus_exposure
                   (stimulus_id, stimulus_class, layer, lifetime_presentations,
                    lifetime_exposure_s, lifetime_sessions, first_used_ts,
                    last_session_ts, state, cooling_since_ts, times_cooled, macro_novelty)
                   VALUES (?,?,?,?,?,1,?,?,?,?,0,?)""",
                (
                    stimulus_id,
                    stimulus_class,
                    layer,
                    presentations_delta,
                    exposure_s_delta,
                    now,
                    now,
                    state,
                    cooling_since_ts,
                    macro_novelty,
                ),
            )
        conn.commit()


def log_session_exposure(
    session_id: str,
    stimulus_id: str,
    presentations: int,
    exposure_s: float,
    mean_novelty: float | None = None,
    mean_effectiveness: float | None = None,
) -> None:
    """Log per-session exposure totals for a stimulus."""
    import time as _t

    with _connect() as conn:
        conn.execute(
            """INSERT INTO session_exposure
               (session_id, stimulus_id, presentations, exposure_s,
                mean_novelty, mean_effectiveness, timestamp)
               VALUES (?,?,?,?,?,?,?)""",
            (
                session_id,
                stimulus_id,
                presentations,
                exposure_s,
                mean_novelty,
                mean_effectiveness,
                _t.time(),
            ),
        )
        conn.commit()


def log_dishabituation(
    session_id: str,
    trigger_type: str,
    pre_novelty: float,
    post_novelty: float,
    trance_depth: float | None = None,
) -> None:
    """Record one dishabituation event."""
    import time as _t

    with _connect() as conn:
        conn.execute(
            """INSERT INTO dishabituation_log
               (session_id, trigger_type, trigger_ts, pre_novelty,
                post_novelty, trance_depth_at_trigger)
               VALUES (?,?,?,?,?,?)""",
            (
                session_id,
                trigger_type,
                _t.time(),
                pre_novelty,
                post_novelty,
                trance_depth,
            ),
        )
        conn.commit()


def get_all_stimulus_exposure() -> dict[str, dict]:
    """Return {stimulus_id: exposure_row} for the habituation engine to preload."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM stimulus_exposure").fetchall()
    return {r["stimulus_id"]: dict(r) for r in rows}


# ── Bible Ch.5 §5.5: Session Director ──────────────────────────────────────────────────


def get_director_profile(user_id: str = "default") -> dict | None:
    """Return the director profile row for the given user, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM director_profile WHERE user_id=?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def upsert_director_profile(user_id: str = "default", **updates) -> None:
    """Create or update the director profile with keyword-argument overrides."""
    import time as _t

    now = _t.time()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT user_id FROM director_profile WHERE user_id=?", (user_id,)
        ).fetchone()
        if existing:
            if updates:
                updates["updated_at"] = now
                sets = ", ".join(f"{k}=?" for k in updates)
                conn.execute(
                    f"UPDATE director_profile SET {sets} WHERE user_id=?",
                    (*updates.values(), user_id),
                )
        else:
            conn.execute(
                """INSERT INTO director_profile
                   (user_id, created_at, updated_at)
                   VALUES (?,?,?)""",
                (user_id, now, now),
            )
            if updates:
                updates["updated_at"] = now
                sets = ", ".join(f"{k}=?" for k in updates)
                conn.execute(
                    f"UPDATE director_profile SET {sets} WHERE user_id=?",
                    (*updates.values(), user_id),
                )
        conn.commit()


def open_session_history(session_id: str, user_id: str, **kwargs) -> None:
    """Insert a new session_history row at session start."""
    import time as _t

    started_at = kwargs.pop("started_at", _t.time())
    cols = ["session_id", "user_id", "started_at"] + list(kwargs.keys())
    vals = [session_id, user_id, started_at] + list(kwargs.values())
    placeholders = ",".join("?" * len(vals))
    with _connect() as conn:
        conn.execute(
            f"INSERT OR IGNORE INTO session_history ({','.join(cols)}) "
            f"VALUES ({placeholders})",
            vals,
        )
        conn.commit()


def close_session_history(session_id: str, **updates) -> None:
    """Update session_history at session end with outcome metrics."""
    import time as _t

    updates.setdefault("ended_at", _t.time())
    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        with _connect() as conn:
            conn.execute(
                f"UPDATE session_history SET {sets} WHERE session_id=?",
                (*updates.values(), session_id),
            )
            conn.commit()


def get_session_history(session_id: str) -> dict | None:
    """Return the session_history row, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM session_history WHERE session_id=?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


def get_recent_session_history(user_id: str = "default", n: int = 10) -> list[dict]:
    """Return the N most recent session_history rows for a user."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM session_history WHERE user_id=? "
            "ORDER BY started_at DESC LIMIT ?",
            (user_id, n),
        ).fetchall()
    return [dict(r) for r in rows]


def log_session_decision(
    decision_id: str,
    session_id: str,
    decision_type: str,
    decision_value: str = "",
    authority_level: int = 0,
    rationale: str = "",
    state_snapshot: dict | None = None,
    outcome_score: float | None = None,
) -> None:
    """Append one Session Director decision record."""
    import time as _t

    with _connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO session_decisions
               (decision_id, session_id, timestamp, decision_type, decision_value,
                authority_level, rationale, state_snapshot, outcome_score)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                decision_id,
                session_id,
                _t.time(),
                decision_type,
                decision_value,
                authority_level,
                rationale,
                json.dumps(state_snapshot) if state_snapshot else None,
                outcome_score,
            ),
        )
        conn.commit()


def get_session_decisions(session_id: str) -> list[dict]:
    """Return all decisions for a session in chronological order."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM session_decisions WHERE session_id=? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Bible Ch.5 §5.5 additional helpers ────────────────────────────────────────────────


def save_director_profile(data: dict, user_id: str = "default") -> None:
    """Upsert director_profile from a plain dict (from UserProfile.vars())."""
    data = {k: v for k, v in data.items() if k not in ("_last_preferred_arc_score",)}
    data["user_id"] = data.get("user_id") or user_id
    upsert_director_profile(
        **{k: v for k, v in data.items() if k != "user_id"}, user_id=data["user_id"]
    )


def get_weak_conditioning_associations(
    threshold: float = 0.5, limit: int = 3
) -> list[dict]:
    """Return associations with strength below threshold, ordered weakest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM conditioning_strengths "
            "WHERE strength < ? ORDER BY strength ASC LIMIT ?",
            (threshold, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def insert_session_history(record: dict) -> None:
    """Insert a new session_history row from a dict (used by SessionEvaluator)."""
    import time as _t

    record = dict(record)
    record.setdefault("user_id", "default")
    record.setdefault("started_at", _t.time())
    cols = list(record.keys())
    placeholders = ",".join("?" * len(cols))
    with _connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO session_history ({','.join(cols)}) "
            f"VALUES ({placeholders})",
            list(record.values()),
        )
        conn.commit()


def update_decision_outcome(decision_id: str, outcome_score: float) -> None:
    """Write outcome_score to a session_decisions row after evaluation."""
    with _connect() as conn:
        conn.execute(
            "UPDATE session_decisions SET outcome_score=? WHERE decision_id=?",
            (outcome_score, decision_id),
        )
        conn.commit()


# ── Bible Ch.4 Addendum A: GENUS Content Pipeline ───────────────────────────────────────────


def upsert_content_pipeline(pool_id: str, item_hash: str) -> None:
    """Register a content item in the pipeline (idempotent)."""
    import time as _t

    now = _t.time()
    ts = str(now)
    with _connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO content_pipeline
               (pool_id, item_hash, created_ts, updated_ts)
               VALUES (?,?,?,?)""",
            (pool_id, item_hash, ts, ts),
        )
        conn.commit()


def advance_content_pipeline(
    pool_id: str,
    item_hash: str,
    stage: str,
    session_id: str | None = None,
    entrainment_ratio: float | None = None,
) -> None:
    """Mark a pipeline stage complete for an item.

    ``stage`` must be one of ``'genus'``, ``'trance'``, or ``'tmr'``.
    When all three are marked the ``pipeline_complete`` flag is set automatically.
    """
    import time as _t

    ts = str(_t.time())
    col_map = {
        "genus": ("genus_encoded", "genus_session_id"),
        "trance": ("trance_deepened", "trance_session_id"),
        "tmr": ("tmr_consolidated", "tmr_session_id"),
    }
    if stage not in col_map:
        return
    done_col, sid_col = col_map[stage]
    extra_set = ""
    extra_vals: list = []
    if stage == "genus" and entrainment_ratio is not None:
        extra_set = ", genus_entrainment_at_delivery=?"
        extra_vals = [entrainment_ratio]
    with _connect() as conn:
        conn.execute(
            f"""UPDATE content_pipeline
                SET {done_col}=1, {sid_col}=?, updated_ts=?{extra_set},
                    pipeline_complete = CASE WHEN genus_encoded=1 AND trance_deepened=1
                                             AND tmr_consolidated=1 THEN 1 ELSE 0 END
                WHERE pool_id=? AND item_hash=?""",
            [session_id, ts, *extra_vals, pool_id, item_hash],
        )
        conn.commit()


def get_incomplete_pipeline_items(pool_id: str | None = None) -> list[dict]:
    """Return content items that have not yet completed all pipeline stages."""
    with _connect() as conn:
        if pool_id:
            rows = conn.execute(
                "SELECT * FROM content_pipeline WHERE pipeline_complete=0 AND pool_id=?",
                (pool_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM content_pipeline WHERE pipeline_complete=0"
            ).fetchall()
    return [dict(r) for r in rows]


# ── Bible Ch.6 §6.7: Induction Strategy Library ───────────────────────────────────────


def log_induction_outcome(
    strategy_id: str,
    outcome: str,
    time_to_trance_s: float,
    peak_trance_score: float,
    effectiveness_score: float,
    user_id: str = "default",
    session_id: str = "",
    redirected_to: str = "",
    eeg_snapshot: dict | None = None,
    ppg_snapshot: dict | None = None,
) -> None:
    """Append a row to strategy_history and update strategy_effectiveness EMA."""
    import time as _t

    now = _t.time()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO strategy_history
               (user_id, session_id, strategy_id, started_at, completed_at,
                outcome, time_to_trance_s, peak_trance_score,
                redirected_to, effectiveness_score, eeg_snapshot, ppg_snapshot)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user_id,
                session_id,
                strategy_id,
                now - time_to_trance_s,
                now,
                outcome,
                time_to_trance_s,
                peak_trance_score,
                redirected_to or None,
                effectiveness_score,
                json.dumps(eeg_snapshot) if eeg_snapshot else None,
                json.dumps(ppg_snapshot) if ppg_snapshot else None,
            ),
        )
        # Update EMA in director_profile.strategy_effectiveness
        row = conn.execute(
            "SELECT strategy_effectiveness FROM director_profile WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if row:
            try:
                eff_map: dict = json.loads(row[0] or "{}")
            except Exception:
                eff_map = {}
            alpha = 0.3
            prev = float(eff_map.get(strategy_id, effectiveness_score))
            eff_map[strategy_id] = round(
                alpha * effectiveness_score + (1 - alpha) * prev, 4
            )
            conn.execute(
                "UPDATE director_profile SET strategy_effectiveness=? WHERE user_id=?",
                (json.dumps(eff_map), user_id),
            )
        conn.commit()


def get_recent_strategy_history(
    user_id: str = "default",
    limit: int = 5,
) -> list[dict]:
    """Return the most recent strategy_history rows for a user (newest first)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM strategy_history WHERE user_id=? "
            "ORDER BY started_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Reconsolidation protocol ───────────────────────────────────────────────────


def log_recon_event(
    session: str,
    target_trace: str,
    ts: float,
    update_delivered: bool = False,
    gate_hits: int = 0,
    reconsolidation_clean: bool = True,
    notes: str = "",
) -> int:
    """Append one row to recon_events. Returns the new row id."""
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO recon_events
               (session, target_trace, ts, update_delivered, gate_hits,
                reconsolidation_clean, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session,
                target_trace,
                float(ts),
                int(update_delivered),
                int(gate_hits),
                int(reconsolidation_clean),
                notes or "",
            ),
        )
        conn.commit()
        return cur.lastrowid or 0


def read_recon_events(
    session: str | None = None,
    target_trace: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return recon_events rows newest-first, optionally filtered."""
    with _connect() as conn:
        if session and target_trace:
            rows = conn.execute(
                "SELECT * FROM recon_events WHERE session=? AND target_trace=? "
                "ORDER BY ts DESC LIMIT ?",
                (session, target_trace, limit),
            ).fetchall()
        elif session:
            rows = conn.execute(
                "SELECT * FROM recon_events WHERE session=? ORDER BY ts DESC LIMIT ?",
                (session, limit),
            ).fetchall()
        elif target_trace:
            rows = conn.execute(
                "SELECT * FROM recon_events WHERE target_trace=? "
                "ORDER BY ts DESC LIMIT ?",
                (target_trace, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM recon_events ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


# ── Somatic palette entries ────────────────────────────────────────────────────


def log_palette_entry(
    session: str,
    chord_index: int = 0,
    beat_frequency: float | None = None,
    carrier_waveform: str | None = None,
    noise_color: str | None = None,
    noise_volume: float | None = None,
    spiral_style: str | None = None,
    veil_mode: str | None = None,
    entry_time_hour: int | None = None,
    days_since_last: float | None = None,
    entry_trance: float | None = None,
    outcome_score: float | None = None,
    depth_min_sef95: float | None = None,
    faa_approach_pct: float | None = None,
    delivery_gate_hit_rate: float | None = None,
    duration_maintenance_s: float | None = None,
    abandoned: bool = False,
    eeg_theta: float | None = None,
    eeg_alpha: float | None = None,
    eeg_faa: float | None = None,
    eeg_spindle_density: float | None = None,
    is_experiment: bool = False,
    experiment_param: str | None = None,
    confidence: float = 0.5,
    ts: float | None = None,
) -> int:
    """Insert one chord evaluation record. Returns the new row id."""
    import time as _time

    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO palette_entries
               (session, ts, chord_index,
                beat_frequency, carrier_waveform, noise_color, noise_volume,
                spiral_style, veil_mode,
                entry_time_hour, days_since_last, entry_trance,
                outcome_score, depth_min_sef95, faa_approach_pct,
                delivery_gate_hit_rate, duration_maintenance_s,
                abandoned, eeg_theta, eeg_alpha, eeg_faa, eeg_spindle_density,
                is_experiment, experiment_param, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?)""",
            (
                session,
                float(ts or _time.time()),
                int(chord_index),
                beat_frequency,
                carrier_waveform,
                noise_color,
                noise_volume,
                spiral_style,
                veil_mode,
                entry_time_hour,
                days_since_last,
                entry_trance,
                outcome_score,
                depth_min_sef95,
                faa_approach_pct,
                delivery_gate_hit_rate,
                duration_maintenance_s,
                int(abandoned),
                eeg_theta,
                eeg_alpha,
                eeg_faa,
                eeg_spindle_density,
                int(is_experiment),
                experiment_param,
                float(confidence),
            ),
        )
        conn.commit()
        return cur.lastrowid or 0


def annotate_palette_entry(
    entry_id: int,
    state_type: str | None = None,
    family: str | None = None,
    notes: str | None = None,
    confidence: float | None = None,
) -> None:
    """Write LLM-derived annotation fields onto an existing palette_entries row."""
    updates: list[str] = []
    params: list = []
    if state_type is not None:
        updates.append("state_type=?")
        params.append(state_type)
    if family is not None:
        updates.append("palette_family=?")
        params.append(family)
    if notes is not None:
        updates.append("annotation_notes=?")
        params.append(notes)
    if confidence is not None:
        updates.append("confidence=?")
        params.append(float(confidence))
    if not updates:
        return
    params.append(entry_id)
    with _connect() as conn:
        conn.execute(
            f"UPDATE palette_entries SET {', '.join(updates)} WHERE id=?", params
        )
        conn.commit()


def best_palette_for_family(
    family: str,
    entry_hour: int | None = None,
    top_n: int = 5,
) -> list[dict]:
    """Return top palette entries for a family, optionally filtered to ±3 hours of entry_hour."""
    with _connect() as conn:
        if entry_hour is not None:
            lo = (entry_hour - 3) % 24
            hi = (entry_hour + 3) % 24
            if lo <= hi:
                hour_clause = "AND entry_time_hour BETWEEN ? AND ?"
                hour_params = (lo, hi)
            else:
                hour_clause = "AND (entry_time_hour >= ? OR entry_time_hour <= ?)"
                hour_params = (lo, hi)
            rows = conn.execute(
                f"""SELECT * FROM palette_entries
                    WHERE palette_family=? AND abandoned=0
                          AND outcome_score IS NOT NULL
                          {hour_clause}
                    ORDER BY outcome_score DESC, confidence DESC
                    LIMIT ?""",
                (family, *hour_params, top_n),
            ).fetchall()
            if not rows:
                rows = conn.execute(
                    """SELECT * FROM palette_entries
                       WHERE palette_family=? AND abandoned=0
                             AND outcome_score IS NOT NULL
                       ORDER BY outcome_score DESC, confidence DESC
                       LIMIT ?""",
                    (family, top_n),
                ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM palette_entries
                   WHERE palette_family=? AND abandoned=0
                         AND outcome_score IS NOT NULL
                   ORDER BY outcome_score DESC, confidence DESC
                   LIMIT ?""",
                (family, top_n),
            ).fetchall()
    return [dict(r) for r in rows]


def get_palette_summary() -> dict:
    """Return a summary of palette coverage: per-family counts, avg score, best chord."""
    families = ["grounding", "depth_charge", "focus", "emotional", "creative"]
    summary: dict = {}
    with _connect() as conn:
        for fam in families:
            rows = conn.execute(
                """SELECT beat_frequency, carrier_waveform, noise_color, spiral_style,
                          veil_mode, outcome_score, abandoned, is_experiment, confidence
                   FROM palette_entries WHERE palette_family=?
                   ORDER BY outcome_score DESC NULLS LAST""",
                (fam,),
            ).fetchall()
            all_rows = [dict(r) for r in rows]
            kept = [
                r
                for r in all_rows
                if not r["abandoned"] and r["outcome_score"] is not None
            ]
            abandoned = [r for r in all_rows if r["abandoned"]]
            scores = [r["outcome_score"] for r in kept]
            avg = round(sum(scores) / len(scores), 3) if scores else None
            best = kept[0] if kept else None
            summary[fam] = {
                "n_entries": len(kept),
                "n_abandoned": len(abandoned),
                "avg_score": avg,
                "best_chord": {
                    k: best[k]
                    for k in (
                        "beat_frequency",
                        "carrier_waveform",
                        "noise_color",
                        "spiral_style",
                        "veil_mode",
                        "outcome_score",
                    )
                }
                if best
                else None,
            }

        total = conn.execute("SELECT COUNT(*) FROM palette_entries").fetchone()[0]
        unann = conn.execute(
            "SELECT COUNT(*) FROM palette_entries WHERE palette_family IS NULL AND abandoned=0"
        ).fetchone()[0]

    summary["_meta"] = {"total_entries": total, "unannotated": unann}
    return summary
