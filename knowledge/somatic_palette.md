# Somatic Palette System

## What is a palette entry?

A palette entry records: **this cross-modal configuration (chord)** + **this entry context** → **this state outcome** for this user.

A chord is a snapshot of audio/visual parameters active when an evaluation window opens during MAINTENANCE: `beat_frequency`, `carrier_waveform`, `noise_color`, `noise_volume`, `spiral_style`, `veil_mode`.

Over many sessions these entries accumulate into a personal response map — a library of what works for this specific user at specific times of day and entry states.

---

## Chord testing protocol

Each chord is evaluated over a **12–15 minute window** in the MAINTENANCE phase.

The agent monitors three failure conditions; any single failure triggers an abandon and chord switch:

- `trance_score` never exceeds 0.40 after 8 minutes
- `faa_value` persistently negative (avoidant approach state) for > 6 minutes
- depth composite flat or declining across the full window

On failure: the agent requests fractionation via `request_fractionation` in `agent_conductor_hints`. The Conductor runs FRAC_EMERGE → FRAC_REDROP. On MAINTENANCE re-entry there is a **3-minute cooldown** before the new chord's evaluation window opens, giving the system time to settle.

A session caps at **3 chord switches** to prevent fractionation exhaustion.

---

## Chord selection on switch (optimization principle)

When selecting the next chord after a failure, the agent uses a score + uncertainty heuristic:

> **Prefer chords with high historical outcome_score AND high uncertainty (few observations).**

A chord tried 1–2 times with a promising score outranks a well-worn chord at the same average. This balances exploitation (use what's proven) with exploration (discover something better).

When palette history is sparse or unavailable, the agent steps through predefined beat frequency and carrier waveform variations to populate the palette quickly.

---

## Palette families

Five named families assigned by LLM annotation post-session:

| Family | Character | Best entry conditions |
|---|---|---|
| `grounding` | Stable, gentle onset. Low arousal entry. | Scattered / anxious user; daytime; alpha range beats (8–12 Hz). |
| `depth_charge` | Maximum trance depth. Sustained maintenance work. | Calm, motivated entry; delta/theta (1–4 Hz); sawtooth or triangle carrier. |
| `focus` | Flat, low complexity. Clear-headed. | Work-adjacent sessions; learning; 4–7 Hz theta; sine or triangle. |
| `emotional` | High FAA approach. Emotional processing. | After a difficult day; pairs naturally with reconsolidation sequences. |
| `creative` | Moderate complexity drift. Loose exploration. | Ideation; journaling; light trance; 5–7 Hz theta; moderate noise. |

---

## State types

Assigned alongside family from observed session arc:

| State type | Signature |
|---|---|
| `rapid_onset` | Deep state reached in < 5 minutes |
| `sustained_depth` | Maintained depth for > 20 minutes |
| `emotional_opening` | High trance complexity that collapses to very low |
| `focus_clarity` | Persistently low flat complexity throughout |
| `creative_drift` | Moderate complexity with high phrase novelty |

State type may be `null` when the chord was abandoned or the window was too short to characterise.

---

## Entry context

Each palette entry records the user's state at chord onset:

- `entry_time_hour` — hour of day (0–23); same chord can behave differently at 09:00 vs 22:00
- `days_since_last` — time since last session; affects depth ceiling and responsiveness
- `entry_trance` — EEG trance score at the moment the chord was applied; captures baseline depth

`_palette_recommend()` filters by entry_hour (±3 hours) before selecting the starting chord, so the recommendation is calibrated to the current time of day.

---

## Palette summary in planning context

The planning prompt includes a `Somatic palette:` block with:
- Per-family entry counts, average score, and best-chord config
- Count of entries awaiting annotation
- For post-session cycles: a list of chords tested in the just-ended session

In post-session mode you **must** produce a `palette_annotations` list covering every chord listed. See the Response Schema section of the idle planning system prompt for the exact format.

---

## What the system does NOT do

- Palette families are assigned by LLM annotation post-session — they are never hardcoded to a session type.
- The agent does not guarantee a chord switch will reach a better state; it records the outcome either way. The library grows from both successes and abandons.
- Palette integration with reconsolidation (e.g., preferring `emotional` family for recon sessions) is a natural follow-on once families have enough data to query.

---

## Authoring `author_palette_experiment` (idle planning)

When the palette is sparse for a family (< 3 entries), you may include `"author_palette_experiment"` in the `actions` array to suggest an explicit experiment for the next session. This is advisory — the agent's chord-tick logic will attempt it automatically anyway.

Use this action when you have a hypothesis worth documenting: for example, noticing that a user responds well to sawtooth waveform and wanting to confirm it in the theta range for `emotional` family.

Schema:
```json
{
  "actions": ["author_palette_experiment"],
  "palette_experiment": {
    "session": "<session_folder>",
    "family": "<target family>",
    "chord": {
      "beat_frequency": 4.0,
      "carrier_waveform": "sawtooth",
      "spiral_style": "hypno_spiral",
      "veil_mode": "drift"
    },
    "hypothesis": "Sawtooth carrier at 4 Hz may drive stronger emotional opening than sine at same frequency."
  }
}
```

The agent logs the experiment intent as a profile note and sets `is_experiment=true` on the resulting palette entry.
