# Adaptive Frequency Leading (Meet-and-Lead) Reference
**Somna Bible Ch.3 Â§Frequency-Leading — Author: Research | 30 March 2026 | Dependencies: Bible Ch.2 Â§IAF (IAF), Bible Ch.2 Â§ASSR (ASSR)**

## 1. Overview

Adaptive frequency leading guides the user's brainwave frequency from their current state to a target state. Instead of abruptly setting a binaural beat to a target (e.g., jumping from 10 Hz to 4 Hz), the system starts at the user's current dominant frequency, confirms entrainment via ASSR, then gradually steps downward toward the target.

**Key insight:** The FFR (Frequency Following Response) is strongest when the driving stimulus is close to the brain's current dominant frequency. Larger gaps produce weaker entrainment. Adaptive leading keeps the gap small at every step.

## 2. The Meet-and-Lead Protocol

**Phase 1 — Meet (Calibration Lock):**
- Set beat to IAF (typically ~10 Hz)
- Confirm entrainment: ASSR confidence must exceed lock_threshold (0.6) before proceeding
- This establishes the frequency following response

**Phase 2 — Lead (Graduated Descent):**
- Decrease by `step_size_hz` (0.1 Hz) every `step_interval_sec` (30s)
- After each step, verify ASSR remains above lock_threshold
- If ASSR drops below `hold_threshold` (0.4): pause, wait for re-entrainment (2 consecutive above-threshold checks), then resume
- Continue until target reached

**Phase 3 — Sustain (Target Lock):**
- Hold at target once reached
- If entrainment drops: micro-step back 0.1 Hz and re-descend

**State Transitions:**
```
MEET → (ASSR ≥ lock) → LEAD → (freq ≤ target) → SUSTAIN
LEAD → (ASSR < hold) → HOLD → (relock confirmed) → LEAD
SUSTAIN → (ASSR < hold) → LEAD (micro step back)
HOLD → (max_hold exceeded) → step back, remain HOLD
```

## 3. Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `step_size_hz` | 0.1 | 0.05–0.25 | Hz decrease per step |
| `step_interval_sec` | 30 | 15–60 | Seconds between steps |
| `assr_lock_threshold` | 0.6 | 0.4–0.8 | ASSR required to advance |
| `assr_hold_threshold` | 0.4 | 0.3–0.6 | ASSR below which = lost |
| `relock_confirmations` | 2 | 1–4 | Consecutive above-threshold checks to resume |
| `max_hold_sec` | 120 | 60–300 | Max hold before fallback |
| `target_freq_hz` | 4.0 | 1.0–12.0 | Target frequency |

**Timing:** At defaults (0.1 Hz / 30s), 10 Hz → 4 Hz = 60 steps × 30s = 30 min (no holds). With holds, expect 30–45 min.

## 4. live_control.json Keys

| Key | Writer | Description |
|-----|--------|-------------|
| `beat_frequency` | FrequencyLeader | Current binaural beat frequency (Hz) |
| `freq_lead_phase` | FrequencyLeader | `"meet"` / `"lead"` / `"hold"` / `"sustain"` / `"inactive"` / `"failed"` |
| `freq_lead_target` | FrequencyLeader | Target frequency (Hz) |
| `freq_lead_current` | FrequencyLeader | Current frequency in descent (Hz) |
| `freq_lead_steps` | FrequencyLeader | Number of successful step-downs |
| `freq_lead_holds` | FrequencyLeader | Number of hold events (entrainment losses) |
| `freq_lead_enabled` | Agent | Set true to activate the leader |
| `eeg_iaf_hz` | IAF calibration | Individual Alpha Frequency |
| `eeg_entrainment_strength` | ASSR module | Current entrainment confidence 0–1 |
| `eeg_sqi_composite` | SQI module | Signal quality 0–1 (leader pauses when < 0.5) |

## 5. Sleep Onset Mapping (Bible Ch.7 Â§Sleep-Onset)

| Stage | Band | Hz | Phenomenology |
|-------|------|----|---------------|
| Meet at IAF | Alpha | ~10 | Relaxed wakefulness |
| Upper alpha | Alpha | 10→8 | Deepening, drowsiness |
| **Alpha-theta crossing** | Alpha→Theta | **~7.5–8** | **Hypnagogia — the critical zone** |
| Lead through theta | Theta | 8→4 | Body heaviness |
| Sustain | Low Theta/High Delta | ~4 | N1 sleep onset |

The alpha-theta crossing (~7.5–8 Hz) is phenomenologically significant. A "hover at hypnagogia" session just sets `target_freq=7.5`.

## 6. Agent Narration Protocol (Aphantasia-Safe)

Messages at key transitions only — not every cycle. Silence during steady descent is appropriate.

| Event | Example Message | Framing |
|-------|----------------|---------|
| Meet locked | "Found you at 10.2 Hz. Beginning descent." | Neutral |
| First step | "Easing down now. Follow the tone." | Auditory |
| First hold | "Pausing here — your rhythm needs a moment to settle." | Somatic |
| Re-entrained | "There you go. Continuing down." | Warm |
| Alpha-theta crossing (~8 Hz) | "Passing through the drowsy threshold. Let your body go heavy." | Somatic |
| Target reached | "You've arrived at 4 Hz. Holding steady." | Neutral |
| Sustain dropout | "Stepping back just a touch. No rush." | Reassuring |

NEVER use: "imagine," "picture," "visualize," "see yourself" — The user has extreme aphantasia.

## 7. Alpha Band Ambiguity

When `beat_freq ≈ IAF ± 1 Hz`, ASSR may conflate beat-evoked response with endogenous alpha. During adaptive leading, reduce ASSR confidence by 0.7 when the alpha-overlap flag is set. This makes the leader more conservative at the alpha-theta transition — it'll hold longer rather than advancing on a potentially spurious lock. This is desirable behavior.

## 8. Fast Followers

If ASSR stays above lock_threshold for 3+ consecutive steps without holds, step_interval can be halved (to 15s) for faster descent. Monitor for stability — fast descent with a late hold is worse than steady descent.

## 9. The Closed-Loop Triad

IAF sets the start → Leader writes beat_frequency → Audio engine plays the beat → Brain responds → ASSR measures response → Leader reads ASSR → Leader decides next step → Loop.

All three components are necessary — without any one, the loop is open.
