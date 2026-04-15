# Fractionation Protocol Reference for Somna
*Doc #13 · Research · 30 March 2026*
*Target: somna_agent.py · Vogt Fractionation Deepening: Timing Model, EEG Markers, Agent Pattern*

---

## Critical Constraint — Aphantasia

the user has **extreme aphantasia** — zero voluntary visualization. All prompts must be somatic/auditory.

- **NEVER** use visualization language: "imagine a staircase," "picture yourself," "see a light"
- **NEVER** narrate state transitions explicitly
- the user experiences entrainment as "sinking" — an imperceptible gradient where he never catches the transition

---

## 1. Mechanism

**Vogt's core observation (1890s)**: Patients hypnotized, emerged, then immediately re-hypnotized entered trance faster and deeper on each subsequent induction. Interruption does not reset progress — it accelerates it.

The interruption is a **ratchet mechanism**. Subjects carry residual trance into the brief waking state. Re-induction begins from the previous depth floor and descends further.

### Why it works (homoaction)

| Factor | Effect |
|--------|--------|
| Confidence | Each successful re-entry confirms ability |
| Familiarity | The route in becomes known; less cognitive work |
| Transition training | The shift mechanism itself is exercised |
| Residual trance | Re-induction starts from an elevated floor, not zero |

### Claire Jack's critical insight

> "Deeper is not always the goal." Fractionation trains **transitions**, not depth. For analytical subjects, "try to go deeper" recruits the monitoring that keeps them on the surface. Depth follows as a side effect of practicing the movement.

This is especially relevant for aphantasia — visualization-based deepening scripts are unavailable. Fractionation sidesteps this entirely.

---

## 2. EEG Markers (Muse 2 Measurable)

| Marker | Band | Behavior | Source |
|--------|------|----------|--------|
| Alpha power | 8–12 Hz | Increases early trance; may decrease as theta dominates deeper | Fehrlin et al. 2023 |
| Theta power | 4–8 Hz | Increases with depth; theta dominance = deep trance | Jensen & Barrett 2024 |
| **Theta/Alpha ratio** | Computed | **Primary metric.** Rising = deepening. Falling = emergence. | Synthesized |

**Not measurable with 4-channel Muse 2**: gamma midline frontal, beta interhemispheric PEC. Do not use as triggers.

The **theta/alpha ratio** (`eeg_theta / eeg_alpha`) is the key computable signal for fractionation state transitions.

---

## 3. Synthesized Timing Model

*No published study provides quantified fractionation timing. These thresholds are starting points — calibrate from the user's real sessions with EEG.*

### Cycle structure

| Phase | Duration | Trigger | Agent behavior |
|-------|----------|---------|----------------|
| Initial Induction | 3–5 min | Theta/alpha ratio > 1.2× resting baseline for 10+ sec | Somatic deepening. RampEngine: alpha → high-theta |
| Deepening Hold | 2–4 min | Time-gated — do NOT wait for "deep enough" | Minimal prompts. Let state consolidate |
| **Partial Emergence** | **15–45 sec** | Time-gated (default: 30 sec) | Single somatic orientation prompt. +2–3 Hz beat lift |
| Re-induction | 1–2 min | Theta/alpha rising faster than initial | Abbreviated deepening, same language as induction |
| Deepened Hold | 3–5 min | Theta/alpha exceeds previous peak OR 90 sec elapsed | Therapeutic window: suggestions, affirmations, silence |

**Emergence duration is the most sensitive parameter.** Too long → residual trance dissipates. Too short → no conditioning signal. Start at 30 sec.

### Progressive shortening

| Cycle | Re-induction time | Rationale |
|-------|------------------|-----------|
| 1 | 3–5 min (full) | No prior conditioning |
| 2 | 1–2 min | Route is known, residual trance present |
| 3 | 45–90 sec | Conditioning strengthening |
| 4+ | 30–60 sec | Nearly automatic transition |

### Cycles by session length

| Session | Cycles | Notes |
|---------|--------|-------|
| 20 min | 2–3 | Final cycle = extended deep hold |
| 30 min | 3–4 | Sweet spot for transition training |
| 45 min | 4–6 | Later cycles very short (30 sec re-induction) |

---

## 4. Agent State Machine

The agent cycles through five states per fractionation cycle, writing state metadata via `_patch_live()`:

```
FRACTIONATION_INDUCTION → FRACTIONATION_HOLD → FRACTIONATION_EMERGE
    → FRACTIONATION_REINDUCE → FRACTIONATION_DEEP → (next cycle)
```

### `live_control.json` writes per state

| State | Keys written |
|-------|-------------|
| INDUCTION | `fractionation_state: "INDUCTION"`, `fractionation_cycle: N` |
| HOLD | `fractionation_state: "HOLD"` |
| EMERGE | `fractionation_state: "EMERGE"` |
| REINDUCE | `fractionation_state: "REINDUCE"`, `fractionation_cycle: N+1` |
| DEEP | `fractionation_state: "DEEP"`, `fractionation_theta_alpha_peak: float` |

### Transition gates

| Transition | Trigger |
|-----------|---------|
| INDUCTION → HOLD | Theta/alpha ratio > 1.2× baseline for 10+ sec (EEG-gated) |
| HOLD → EMERGE | Hold duration elapsed (time-gated — no depth threshold) |
| EMERGE → REINDUCE | Emergence duration elapsed (default 30 sec, time-gated) |
| REINDUCE → DEEP | Theta/alpha > previous cycle peak, OR 90 sec (EEG-gated + fallback) |

---

## 5. Aphantasia-Safe Prompt Templates

### Emergence prompts (one per emergence, no stacking)

| # | Prompt | Modality |
|---|--------|----------|
| 1 | "Notice where your body meets the surface beneath you." | Somatic (tactile) |
| 2 | "Feel the temperature of the air on your skin." | Somatic (thermal) |
| 3 | "Hear the sounds in the room — just for a moment." | Auditory |
| 4 | "Notice the weight of your hands." | Somatic (proprioceptive) |
| 5 | "Feel your breath, just the physical sensation of it." | Somatic (respiratory) |

### Re-induction prompts (use same prompt across cycles in one session)

| # | Prompt | Mechanism |
|---|--------|-----------|
| 1 | "And you can let that go now... sinking back..." | Release cue + keyword |
| 2 | "The weight returns... heavier than before..." | Somatic anchor + progression |
| 3 | "Each breath pulling you back down... easier this time..." | Respiratory pacing + ease |
| 4 | "You know the way now... let yourself follow it..." | Familiarity reinforcement |
| 5 | "Settling... deeper than before... effortless..." | Kinesthetic + depth framing |

### Never use

"Imagine..." / "Picture..." / "See yourself..." / "Visualize..." / "Watch as..." / Staircases / Elevators / Beaches / Gardens / Any scene-setting. These are inert for aphantasia.

> **Note**: Expose prompt templates as config, not hardcoded strings. the user will want to customize them.

---

## 6. Session YAML Example (30 min, 3 cycles)

```yaml
# fractionation_30min.yaml
session:
  name: "Fractionation Training — 30 min"
  duration_minutes: 30
  protocol: fractionation
  fractionation_cycles: 3
  emergence_duration_sec: 30

timeline:
  - t: "00:00"
    beat_freq: 10.0
    note: "Baseline. Agent reads resting theta/alpha."

  - t: "01:00"              # Cycle 1 Induction
    beat_freq: 10.0
    ramp_to: 6.5
    ramp_duration: 240

  - t: "05:00"              # Cycle 1 Hold
    beat_freq: 6.5

  - t: "08:00"              # Cycle 1 Emergence (+freq lift)
    beat_freq: 6.5
    ramp_to: 9.0
    ramp_duration: 15

  - t: "08:30"              # Cycle 1 Re-induction
    beat_freq: 9.0
    ramp_to: 5.5
    ramp_duration: 90

  - t: "10:00"              # Cycle 2 Hold (therapeutic window)
    beat_freq: 5.5

  - t: "14:00"              # Cycle 2 Emergence
    beat_freq: 5.5
    ramp_to: 8.5
    ramp_duration: 15

  - t: "14:30"              # Cycle 2 Re-induction (faster)
    beat_freq: 8.5
    ramp_to: 5.0
    ramp_duration: 60

  - t: "15:30"              # Cycle 3 Hold (deepest therapeutic window)
    beat_freq: 5.0

  - t: "20:00"              # Cycle 3 Emergence (brief)
    beat_freq: 5.0
    ramp_to: 8.0
    ramp_duration: 15

  - t: "20:30"              # Cycle 3 Re-induction (fastest)
    beat_freq: 8.0
    ramp_to: 4.5
    ramp_duration: 45

  - t: "21:15"              # Final Deep Hold
    beat_freq: 4.5

  - t: "27:00"              # Session Emergence
    beat_freq: 4.5
    ramp_to: 10.0
    ramp_duration: 180

  - t: "30:00"
    beat_freq: 10.0
    volume: 0.0
```

---

## References

| Source | Year | Relevance |
|--------|------|-----------|
| Vogt, O. | 1890s | Originator. Observed the ratchet effect. |
| Jack, C. | — | Fractionation trains transitions, not depth. |
| Fehrlin, T. et al. | 2023 | Alpha anteriorization as hypnotic deepening hallmark. |
| Jensen, M.P. & Barrett, D. | 2024 | Slow wave hypothesis: theta/alpha facilitate hypnotic responsivity. |
| Obukhov, Y. et al. | 2023 | Passive BCI depth estimation, 82% accuracy using 4–15 Hz. Individual calibration essential. |
| Zech, N. et al. | 2023 | BIS drops 97.7→86.4 at induction. CSI drops 94.6→77.7. |
