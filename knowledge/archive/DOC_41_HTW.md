# Doc 41 — Hypnagogic Training Window (HTW)

**Status:** Implemented.  
**Depends on:** Doc 39 (sleep stages), Doc 40 (TMR registry), Doc 35 (DeliveryGate / TTS).

---

## Overview

Natural NREM sleep architecture produces N1 epochs every ~90 minutes as the
sleeper cycles between deeper stages and lighter ones.  Doc 39's SLEEP_MAINTAIN
phase watches these windows pass; this doc specifies a new Conductor phase —
`SLEEP_TRAINING` — that intercepts them deliberately.

During a natural N1 window, prefrontal suppression is already underway, critical
evaluation is minimal, and the brain is theta-dominant — the same band targeted
during waking trance deepening.  The next NREM consolidation cycle is minutes
away.  A brief (~5 minute) targeted content session delivered here produces
reinforcement effects that are qualitatively different from waking-state
affirmation delivery because:

1. The brain's filter is already at its lowest during N1.
2. The content presented immediately precedes the consolidation cycle that
   processes whatever was most recently in working memory.
3. Audio at low gain does not trigger arousal in N1 the way it would at the
   waking boundary.  A TTS whisper (~6% gain) alongside SSB subliminals
   (~14% gain) delivers both the explicit phrase and its subliminal neural
   signature simultaneously.  The pairing of the two channels — the
   "feel" of the subliminal and the explicit word — is encoded more
   deeply in this state than during any waking repetition.

After the window, the Conductor transitions to `SLEEP_ONSET` (not
`SLEEP_APPROACH`), actively guiding the sleeper back into N2/N3 via SWE
phase-locked bursts.

---

## Phase arc

```
SLEEP_MAINTAIN
    │
    │  N1 detected (3 consecutive epochs) + HTW eligible
    ▼
SLEEP_TRAINING ──── EEG lost / user interaction / alpha surge >60s ──▶ SLEEP_WAKE
    │
    │  timeout (5 min) OR N2/N3 detected early (3 epochs)
    ▼
SLEEP_ONSET ──▶ SLEEP_MAINTAIN (resumes normal loop)
    │
    │  WAKE detected (5 epochs)
    ▼
SLEEP_APPROACH (fallback if N2 does not return quickly)
```

SLEEP_TRAINING transitions to `SLEEP_ONSET`, not `SLEEP_APPROACH`.
The sleeper is already in N1 — the alpha anti-phase disruption used in
SLEEP_APPROACH targets waking-state cortical inhibition and is wrong-phase
here.  SLEEP_ONSET's SWE delta bursts and slow beat targeting are exactly right
for pushing N1 → N2.

---

## HTW eligibility gate

All conditions must hold simultaneously before the Conductor intercepts an N1
epoch.

| Condition | Threshold | Rationale |
|-----------|-----------|-----------|
| N2 + N3 time banked | ≥ 3600 s | Do not interrupt the critical first hour |
| Time since last HTW | ≥ 5400 s | Align with natural ~90 min ultradian cycle |
| HTW count this session | < 3 | Avoid fragmenting sleep excessively |
| `eeg_signal_lost` | False | Safety: no stimulation without signal |
| Content available | TMR registry non-empty OR `agent_sleep_plan` present | Always have phrases ready |
| Current stage | N1 for ≥ 3 consecutive 2 s epochs | Confirm the window, not a transient |

The 3-epoch (6 s) confirmation prevents triggering on transient noise.
N1 windows typically last 1–5 minutes, so 6 s latency costs nothing.

---

## TTS + SSB pairing rationale

The key design choice: both channels play the same phrase simultaneously.

- **SSB** (~14% gain): carries the "feel" of the phrase — the ultrasonic carrier
  that the nervous system processes without conscious decoding.  Over many
  sessions this channel builds a subliminal neural signature for each phrase.
- **TTS whisper** (~6% gain): carries the explicit content — the actual words
  delivered just at the edge of audibility.

In N1 state, the brain receives both without the filtering that separates them
in waking.  The neural pattern for the phrase (subliminal) and its explicit
meaning (audible) are co-encoded in working memory at the moment of deepest
receptivity, immediately before the consolidation cycle.  In subsequent waking
sessions, when the SSB channel fires at full strength, it retrieves the TTS
association more readily than if the pairing had only occurred during alert
waking state.

Reverb is disabled in SLEEP_TRAINING.  Any room-filling echo texture raises
the acoustic arousal threshold.  The whisper must be intimate and dry.

---

## Audio and visual parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `beat_frequency` | 5.5 Hz | Low-end theta — drowsy range, not alert |
| `beat_type` | binaural | Isochronic AM pulse too stimulating |
| `tts_enabled` | True | |
| `tts_volume` | 6 | Barely audible whisper |
| `tts_subliminal` | True | SSB on |
| `tts_subliminal_vol` | 14 | Slightly above TTS audible gain |
| `tts_pool_style` | `{"pitch": "-10Hz", "rate": "-30%"}` | Slower, warmer synthesis |
| `noise_color` | off | No continuous texture |
| `gain_mode` | `sleep_training` | Crossmodal gain profile |
| `center_flash_on_time` | 4000 ms | Long dwell — gently present, not subliminal |
| `center_flash_off_time` | 8000 ms | ~12 s cycle |
| `center_flash_sync_to_beat` | False | Theta at 5.5 Hz would be too fast |

**CrossmodalGainEngine `"sleep_training"` profile:**

| Channel | Ceiling |
|---------|---------|
| beats | 0.80 |
| noise | 0.00 |
| speech_tts | 0.06 |
| speech_sub | 0.14 |
| pattern (spirals) | 0.00 |
| text_veil | 0.00 |
| text_shadow | 0.25 |
| text_center | 0.35 |

---

## Pre-synthesis

Between when HTW becomes eligible (during SLEEP_MAINTAIN, potentially 30–90
minutes before the first N1 window) and when the window actually opens, the
Conductor writes `tts_presynth_phrases` and `tts_pool_style` to
`live_control.json`.  The TTS worker synthesizes these into a separate
`_presynth_ready` buffer using the whisper profile.  When `SLEEP_TRAINING`
starts, `tts_use_presynth: true` is set and `poll_ready()` serves from this
buffer first.  By the time N1 arrives (minimum 6 seconds of N1 confirmation
after eligibility is met), the buffer is already warm.  The first phrase fires
within one flash cycle (~8 s) of entry with zero synthesis latency.

---

## Phrase selection

Priority order in `_select_training_phrases()`:

1. `agent_sleep_plan.phrases` — if the agent has run `read_sleep_report` and
   written a plan, use those phrases (up to 6).
2. TMR registry fallback — select the 6 affirmations from `tmr_cue_registry`
   with the lowest `encoding_count` (most under-reinforced content first).
3. Current `affirmations_pool` as last resort.

Selected phrases replace `affirmations_pool` for the duration of the window.
On exit, the original pool is restored.

---

## Agent sleep planning

`somna_agent.py` contains a `_sleep_planning_tick()` method called from
`_interactive_tick()` when the Conductor phase is `SLEEP_MAINTAIN`.  If no
`agent_sleep_plan` exists or the existing one is > 5400 s old, it calls the
`read_sleep_report` tool, selects a focus pool (lowest-coverage content), and
writes `agent_sleep_plan` to `live_control.json`.  This happens silently — no
voice prompt, no user interaction.  The plan persists until consumed by the
next HTW window.

---

## `read_sleep_report` tool

Reads `sleep_stage_log`, `tmr_cue_registry`, `tmr_replay_log`, and
`sleep_training_log` for the current session.  Returns:

```json
{
  "elapsed_sleep_s": 7200,
  "stage_distribution": {"N1": 420, "N2": 3600, "N3": 1800, "REM": 0, "WAKE": 180},
  "htw_count": 1,
  "tmr_replay_count": 12,
  "tmr_encoding_summary": {
    "IDENTITY":   {"phrases": 4, "mean_encoding_count": 3.2},
    "POTENTIAL":  {"phrases": 2, "mean_encoding_count": 1.5},
    "PURPOSE":    {"phrases": 0, "mean_encoding_count": 0}
  },
  "recommended_focus_pool": "PURPOSE",
  "underreinforced_phrases": ["I build toward what matters", "..."],
  "next_htw_eligible_in_s": 3200
}
```

The agent uses this to select which content to prioritise in the next window.
It can also surface a morning summary if the user opens the console after a
sleep session.

---

## Abort conditions

Checked on every 30 s Conductor tick during `SLEEP_TRAINING`:

| Trigger | Exit target | Rationale |
|---------|-------------|-----------|
| `eeg_signal_lost` | SLEEP_WAKE | Safety — no stimulation without signal |
| `timeline_locked_params` non-empty | SLEEP_WAKE | User is awake and touching controls |
| `eeg_alpha` > 0.25 for > 60 s | SLEEP_WAKE | Genuine arousal, not just a transient |
| 300 s elapsed | SLEEP_ONSET | Hard timeout — push back toward N2 |
| N2/N3 for ≥ 3 epochs | SLEEP_ONSET | Early deepening — great outcome |

On any exit: restore `affirmations_pool` and TTS params, clear
`tts_use_presynth`, log to `sleep_training_log`, set `tmr_lockout_until`
for HTW duration + 60 s buffer so TMR replay doesn't immediately fire over
the freshly delivered content.

---

## Database

**`sleep_training_log` table:**

```sql
CREATE TABLE IF NOT EXISTS sleep_training_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT    NOT NULL,
    htw_index         INTEGER NOT NULL,
    started_at        REAL    NOT NULL,
    duration_s        REAL    NOT NULL,
    stage_at_entry    TEXT    NOT NULL DEFAULT 'N1',
    stage_at_exit     TEXT    NOT NULL,
    focus_pool        TEXT    NOT NULL DEFAULT '',
    phrases_delivered INTEGER NOT NULL DEFAULT 0,
    exit_reason       TEXT    NOT NULL
);
```

**New `session_metrics` columns** (added via idempotent ALTER TABLE):
- `htw_count INTEGER`
- `htw_total_duration_s REAL`
- `htw_success_rate REAL` — fraction of windows that exited via `n2_detected`
  rather than `timeout` or `alpha_surge`

---

## live_control.json keys added

| Key | Type | Owner | Description |
|-----|------|-------|-------------|
| `tts_presynth_phrases` | list[str] | Conductor | Phrases to pre-synthesize into `_presynth_ready` buffer |
| `tts_use_presynth` | bool | Conductor | When true, `poll_ready()` serves from `_presynth_ready` first |
| `tts_pool_style` | dict | Conductor | Pitch/rate overrides for pool synthesis worker (`{"pitch": "-10Hz", "rate": "-30%"}`) |
| `agent_sleep_plan` | dict | Agent | `{focus_pool, phrases, ts}` — written by sleep planning tick, consumed by `_select_training_phrases()` |

---

## Implementation files

| File | Change |
|------|--------|
| `conductor.py` | `Phase.SLEEP_TRAINING`; `_TICK_RATES` entry; `_htw_count`, `_htw_last_ts`, `_htw_start_ts`, `_pre_htw_state`, `_htw_phrases_presynth`, `_htw_alpha_surge_ts` state; `_htw_eligible()`, `_presynth_training_phrases()`, `_select_training_phrases()`, `_enter_sleep_training()`, `_exit_sleep_training()` methods; SLEEP_MAINTAIN and SLEEP_TRAINING transition blocks |
| `tts_engine.py` | `_presynth_ready` deque; `tts_presynth_phrases` pre-fetch in `_worker()`; `tts_use_presynth` check in `poll_ready()`; `tts_pool_style` passed to `_build_backend()` during pool synthesis |
| `crossmodal_gain.py` | `"sleep_training"` entry in `SLEEP_GAIN_PROFILES` |
| `content_tools/sleep_report.py` | `read_sleep_report(session_id)` — aggregate query |
| `content_tools/__init__.py` | `read_sleep_report` tool schema + dispatch |
| `content_tools/somna_db.py` | `sleep_training_log` table; `log_sleep_training_window()`; ALTER TABLE for `htw_*` columns |
| `somna_agent.py` | `_sleep_planning_tick()` method; call from `_interactive_tick()` |
