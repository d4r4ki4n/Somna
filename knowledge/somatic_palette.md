# Somatic Palette System

**Status:** Specification (v2 — rebuilt with full subsystem integration)

**Author:** Ed / Reese

**Date:** 17 April 2026

**Loaded by:** `_load_idle_knowledge()` during idle planning; also referenced during MAINTENANCE chord evaluation

**Authority:** This file is the operational reference for the LLM agent. The authoritative design specification lives in the Somna Bible, Chapter 4 — Session Architecture, §Somatic-Palette. When this file and the Bible disagree, the Bible wins.

---

## 1. What Is a Palette Entry

A palette entry records: **this cross-modal configuration (chord)** + **this entry context** -> **this state outcome** for this user.

A chord is a snapshot of audio/visual parameters active when an evaluation window opens during MAINTENANCE:

| Chord Parameter | Source |
|---|---|
| `beat_frequency` | Conductor / palette override |
| `carrier_waveform` | Conductor / palette override |
| `noise_color` | Conductor / palette override |
| `noise_volume` | Conductor / palette override |
| `spiral_style` | Conductor / palette override |
| `veil_mode` | Conductor / palette override |

Over many sessions these entries accumulate into a personal response map — a library of what works for this specific user at specific times of day and entry states.

---

## 2. Chord Testing Protocol

Each chord is evaluated over a **12-15 minute window** in the MAINTENANCE phase.

The agent monitors three failure conditions; any single failure triggers an abandon and chord switch:

- `trance_score` never exceeds 0.40 after 8 minutes
- `faa_value` persistently negative (avoidant approach state) for > 6 minutes
- depth composite flat or declining across the full window

On failure: the agent requests fractionation via `request_fractionation` in `agent_conductor_hints`. The Conductor runs FRAC_EMERGE -> FRAC_EMERGE_HOLD -> FRAC_REDROP. On MAINTENANCE re-entry there is a **3-minute cooldown** before the new chord's evaluation window opens, giving the system time to settle.

A session caps at **3 chord switches** to prevent fractionation exhaustion.

### 2.1 When All 3 Switches Fail

If all 3 chord switches fail within a session, the agent should:

1. **Do not request a 4th fractionation.** The cap is absolute.
2. **Fall back to the user's all-time best chord** — the palette entry with the highest `outcome_score` and `n_observations >= 3`. If no such entry exists, fall back to the session.yaml default parameters.
3. **Continue the session in MAINTENANCE** with the fallback chord. Do not suggest emergence unless the user requests it or `trance_score` remains below 0.30 for > 10 minutes.
4. **Log the session as `palette_exhausted = true`** in the session record. This flags the session for post-session analysis — three consecutive chord failures may indicate an entry-state problem (bad day, physiological state, time of day) rather than a chord problem.

---

## 3. Chord Selection — Exploration-Exploitation

When selecting the next chord after a failure (or when recommending a chord at session start), the agent uses a score + uncertainty heuristic:

**Formula:**

```
selection_score = outcome_score + 1 / (n_observations + 1)
```

Where:
- `outcome_score` = historical average outcome for this chord (0.0 - 1.0)
- `n_observations` = number of completed evaluation windows for this chord

**Effect:** A chord tried 1-2 times with a promising score outranks a well-worn chord at the same average. This balances exploitation (use what's proven) with exploration (discover something better).

| n_observations | Exploration Bonus | Effect |
|---|---|---|
| 0 (never tried) | +1.000 | Maximum exploration — always try untested chords |
| 1 | +0.500 | Strong exploration pull |
| 2 | +0.333 | Moderate |
| 5 | +0.167 | Mild |
| 10+ | < 0.091 | Negligible — exploitation dominates |

When palette history is sparse or unavailable (first few sessions), the agent steps through predefined beat frequency and carrier waveform variations to populate the palette quickly. Start with: 6 Hz sine, 5 Hz triangle, 4 Hz sawtooth, 7 Hz sine — these cover the theta range with different carrier characters.

---

## 4. Palette Families

Five named families assigned by LLM annotation post-session:

| Family | Character | Best Entry Conditions |
|---|---|---|
| `grounding` | Stable, gentle onset. Low arousal entry. | Scattered / anxious user; daytime; alpha range beats (8-12 Hz). |
| `depth_charge` | Maximum trance depth. Sustained maintenance work. | Calm, motivated entry; delta/theta (1-4 Hz); sawtooth or triangle carrier. |
| `focus` | Flat, low complexity. Clear-headed. | Work-adjacent sessions; learning; 4-7 Hz theta; sine or triangle. |
| `emotional` | High FAA approach. Emotional processing. | After a difficult day; pairs naturally with reconsolidation sequences. |
| `creative` | Moderate complexity drift. Loose exploration. | Ideation; journaling; light trance; 5-7 Hz theta; moderate noise. |

---

## 5. State Types

Assigned alongside family from observed session arc. Seven canonical state types:

| State Type | Signature |
|---|---|
| `rapid_onset` | Deep state reached in < 5 minutes |
| `sustained_depth` | Maintained depth for > 20 minutes |
| `emotional_opening` | High FAA approach + elevated emotional content engagement |
| `gradual_build` | Slow, steady deepening over > 15 minutes; no rapid transitions |
| `volatile` | Frequent depth fluctuations; trance_score variance > 0.15 |
| `focus_clarity` | Flat, stable depth with high cognitive clarity markers |
| `creative_drift` | Moderate depth with periodic spontaneous depth oscillations |

**Note:** AGENTS.md may list a subset of these. This file has the canonical set. If the LLM annotation encounters a session arc that doesn't fit any of these 7 types, assign the closest match and add a `state_notes` field to the palette entry with a brief description.

---

## 6. Entry Context Fields

When recording a palette entry, populate ALL of the following entry context fields:

| Field | Type | Source |
|---|---|---|
| `entry_time_hour` | int (0-23) | System clock at session start |
| `entry_trance` | float (0.0-1.0) | trance_score at MAINTENANCE entry |
| `days_since_last` | int | Days since last completed session |
| `entry_mood` | string | Agent's assessment from pre-session interaction (if available) |
| `recent_sleep` | string | User-reported or inferred sleep quality (if available) |

`entry_mood` and `recent_sleep` are optional — they depend on the agent having pre-session interaction data. When unavailable, store as `null`. Do not fabricate mood or sleep data.

---

## 7. Recommendation Filtering

### 7.1 `_palette_recommend()` Logic

When recommending a chord for a new session, filter palette history by:

1. **Time window:** `entry_time_hour +/- 3 hours` from current session start time
2. **Apply selection_score formula** (section 3) to filtered candidates
3. **Return top candidate** by selection_score

**Tuning note:** The +/- 3 hour window is a default, not a constant. For users who session at highly consistent times (e.g., always at 3 PM), this window is appropriate. For users who session irregularly across the day, consider widening to +/- 5 hours to include more candidates. The agent can adjust this based on the user's `entry_time_hour` distribution in palette history — if the standard deviation of entry times is > 4 hours, widen the window.

### 7.2 Cold Start

When palette history has fewer than 5 entries, skip recommendation filtering entirely. Use the predefined exploration sequence (section 3) until enough data accumulates.

---

## 8. Interference Graph Integration

The Somatic Palette and the Interference Graph are architecturally coupled:

- **User-composed chords as palette candidates:** When the user composes a chord via the Interference Graph UI (dragging nodes, applying preset stamps), the agent should treat the resulting parameter configuration as an explicit palette candidate. Record it as a palette entry with `source = "user_composed"` rather than `source = "agent_selected"`.

- **Spread knob interaction:** The Interference Graph's spread knob applies per-channel frequency offset on top of each channel's individual base frequency. When a palette chord specifies `beat_frequency = 6.0`, the spread knob may shift individual channels to 5.8, 6.0, 6.2, etc. The palette records the **base** frequency, not the spread-adjusted values.

- **Chord fingerprint recording:** Every MAINTENANCE window records a chord fingerprint regardless of whether the palette system initiated the chord. This means user-adjusted parameters during a session are captured and feed back into the palette's learning loop. See `session_db.py` for the fingerprint schema.

- **Priority:** User overrides via the Interference Graph UI take highest priority. When the user is actively adjusting parameters, the palette system should not fight them — suspend chord evaluation until the user stops adjusting (no UI interaction for > 60 seconds).

---

## 9. Valid Spiral Styles

When authoring palette experiments or specifying chord parameters, use only these 14 valid styles:

`tunnel_dream`, `galaxy`, `archimedean`, `kaleidoscope`, `interference`, `electric`, `vortex`, `dna`, `fibonacci`, `rose`, `moire`, `spirograph`, `fermat`, `superformula`

Any style name not in this list will be silently ignored or cause a crash. Do NOT use `hypno_spiral`, `liminal`, or any other unlisted name.

---

## 10. Example: Authoring a Palette Experiment

When the agent wants to test a new chord during idle planning, it authors an experiment entry:

```json
{
  "chord": {
    "beat_frequency": 5.5,
    "carrier_waveform": "triangle",
    "noise_color": "brown",
    "noise_volume": 0.3,
    "spiral_style": "tunnel_dream",
    "veil_mode": "tunnel"
  },
  "hypothesis": "Triangle carrier at 5.5 Hz may produce deeper sustained state than sine at same frequency",
  "priority": 0.72,
  "source": "agent_exploration"
}
```

The experiment is queued for the next session. When MAINTENANCE begins and chord selection runs, queued experiments compete with palette recommendations via the selection_score formula. Experiments with no observations get the maximum exploration bonus (+1.0), so they will be tried unless a proven chord has an outcome_score > 1.0 (impossible — scores are 0.0-1.0), guaranteeing that queued experiments are always tested.

---

## 11. DB Schema (Snapshot)

**Warning:** This schema is a snapshot for agent reference. If queries fail, check `session/session_db.py` for the current schema — it is the single source of truth.

### `palette_entries` table

| Column | Type | Description |
|---|---|---|
| id | INTEGER PRIMARY KEY | Auto-increment |
| session_id | TEXT | FK to sessions table |
| beat_frequency | REAL | Hz |
| carrier_waveform | TEXT | sine / triangle / sawtooth / square |
| noise_color | TEXT | white / pink / brown / blue / violet / grey / red |
| noise_volume | REAL | 0.0-1.0 |
| spiral_style | TEXT | One of 14 valid styles |
| veil_mode | TEXT | scroll / rain / drift / converge / strobe / tunnel / null |
| outcome_score | REAL | 0.0-1.0 composite |
| n_observations | INTEGER | Completed evaluation windows |
| family | TEXT | grounding / depth_charge / focus / emotional / creative |
| state_type | TEXT | One of 7 canonical types |
| entry_time_hour | INTEGER | 0-23 |
| entry_trance | REAL | 0.0-1.0 |
| days_since_last | INTEGER | |
| entry_mood | TEXT | nullable |
| recent_sleep | TEXT | nullable |
| source | TEXT | agent_selected / agent_exploration / user_composed |
| created_at | TEXT | ISO 8601 timestamp |

---

## 12. Cross-References

| System | Relationship |
|---|---|
| Conductor FSM (`conductor_fsm.md`) | Palette overrides conductor-owned params during MAINTENANCE; conductor retains chaos, trail_decay, sr_noise_level |
| Reconsolidation Protocol (`reconsolidation_protocol.md`) | `emotional` family chords pair with reconsolidation; recon does not affect chord evaluation timing |
| Interference Graph (Bible Ch.9) | User-composed chords feed palette; spread knob offsets are additive |
| Session Design (`session_design.md`) | Session.yaml provides fallback chord params when palette is empty |
| Delivery Gate (`conductor_fsm.md` §Conflict Resolution) | Chord evaluation metrics (trance_score, faa_value) are the same metrics the delivery gate reads — no separate measurement |
