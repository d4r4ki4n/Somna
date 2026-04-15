# Frontal Alpha Asymmetry (FAA) Receptivity Signal Reference
**Somna Bible Ch.2 Â§FAA — Author: Research | 30 March 2026 | Implementation-Ready**

## 1. Overview

FAA transforms affirmation delivery from time-based to state-based. The agent stops asking "has enough time passed?" and starts asking "is the user ready?"

Without FAA, affirmations are delivered on a timer or heuristic — effectively guessing. With FAA, affirmations are delivered precisely when the brain is most receptive. The difference is between shouting into a room hoping someone's listening versus speaking when you know they've leaned in.

## 2. Neuroscience Foundation

Alpha power (8–13 Hz) is inversely related to cortical activation — lower alpha = higher activation (counterintuitive: more alpha = region idling).

**The Approach-Withdrawal Model:**
- Left prefrontal activation (lower left-alpha at AF7) → approach motivation, positive affect, receptivity
- Right prefrontal activation (lower right-alpha at AF8) → withdrawal, avoidance, guarded state

Key references: Davidson (1992), Allen et al. (2004), Coan & Allen (2004), Smith et al. (2017).

## 3. Computation from Muse 2

- AF7 = index 1 within EEG channels (left frontal)
- AF8 = index 2 within EEG channels (right frontal)

**Formula:** `FAA = ln(alpha_power_AF8) − ln(alpha_power_AF7)`

| FAA Value | Meaning | Agent Action |
|-----------|---------|--------------|
| > +0.1 | Greater left-frontal activation → approach / receptive | Deliver affirmations — optimal window |
| −0.1 to +0.1 | Balanced / neutral | Deliver affirmations — standard intensity |
| < −0.1 | Greater right-frontal activation → withdrawal / guarded | Hold affirmations — wait for shift |

Log transform normalizes the skewed distribution of raw power values.

## 4. live_control.json Keys

| Key | Type | Description |
|-----|------|-------------|
| `eeg_faa` | float | Smoothed FAA — 10-second rolling average. Primary signal. |
| `eeg_faa_raw` | float | Instantaneous FAA from single 2-second window. Noisy. |
| `eeg_faa_state` | str | `"approach"` / `"neutral"` / `"withdrawal"` / `"insufficient_data"` / `"alpha_suppressed"` |

## 5. Agent Protocol

### Receptivity Gate
- `"withdrawal"` → hold affirmations (but if withdrawal persists >60s, deliver anyway — may be trait asymmetry)
- `"approach"` → optimal window — deliver with confidence, use stronger/more direct affirmations
- `"neutral"` → acceptable, use standard affirmation intensity
- `"alpha_suppressed"` → treat as permissive (equivalent to "neutral") — deep alpha suppression correlates with deep states

### Affirmation Intensity by FAA
- `faa > 0.2` → "strong" (deep approach — go bold)
- `0.1 < faa ≤ 0.2` → "standard" (mild approach — normal delivery)
- `-0.1 ≤ faa ≤ 0.1` → "gentle" (neutral — softer touch)
- `faa < -0.1` → "gentle" (withdrawal — if delivering at all, be gentle)

## 6. Aphantasia Protocol (Absolute Rule)

All affirmations must be somatic/auditory only. NEVER use "imagine," "picture," "visualize," "see yourself," or any guided imagery language. The user has extreme aphantasia — zero voluntary visual imagery.

| FAA State | Somatic Affirmation Strategy |
|-----------|------------------------------|
| Approach | Direct somatic statements, confident tone. "You feel warmth spreading through your chest." |
| Neutral | Standard somatic affirmations. "Your body is sinking deeper into the chair." |
| Withdrawal | Reduce text density. Soften tone. Let beats and spiral do their work. |

## 7. Fractionation Integration

Expected FAA signature during clean fractionation:

| Phase | Expected FAA Shift | Interpretation |
|-------|-------------------|----------------|
| Deepening | Approach (positive FAA) | User engaged, receptive, sinking into trance |
| Emergence | Withdrawal spike (negative FAA) | User surfaces — confirms genuine emergence |
| Reinduction | Return to approach (positive FAA) | Each cycle should show faster approach return |

The approach → withdrawal → approach pattern confirms fractionation is producing expected neurological shifts. Each cycle should show a tighter, faster return.

**Timing reinduction:** Don't start reinduction until FAA has clearly shifted to withdrawal (confirming genuine emergence). Watch for the approach return. If FAA doesn't show the withdrawal-to-approach transition, the drop may not be deep enough.

## 8. Integration with Other Metrics

**The Ideal Affirmation Window:** SQI > 0.5 (clean signal) + SEF95 dropping (deepening) + FAA approach (receptive) + ASSR present (entrained) = maximum-confidence delivery.

| Metric | Relationship to FAA |
|--------|---------------------|
| SQI (Bible Ch.2 Â§SQI) | Quality gate — FAA is meaningless if SQI < 0.5 |
| SEF95 (Bible Ch.2 Â§SEF95) | FAA gives direction; SEF95 gives depth. "Deep AND receptive" = ideal |
| ASSR (Bible Ch.2 Â§ASSR) | Entrainment + approach = frequency-locked AND motivationally engaged |

## 9. Edge Cases

**Resting asymmetry (trait FAA):** Some individuals have stable trait-level FAA. After 2–3 sessions, establish a personal baseline in somna.db and adjust thresholds: `APPROACH = baseline_mean + 0.1`, `WITHDRAWAL = baseline_mean − 0.1`.

**Alpha suppression at depth:** When total alpha power drops below floor (both hemispheres), asymmetry becomes unreliable. Mark as `"alpha_suppressed"` — treat as permissive for gating.

**Muscle artifact:** SQI gating handles this — when SQI drops below 0.5 due to artifact, FAA computation is suppressed automatically.

## 10. Veil Mode and Subliminal Text

Research insight: structured motion modes (converge, tunnel) preserve semantic priming; high-density drift acts as a pattern mask (Marcel 1983) that degrades subliminal processing. When affirmation delivery is active and FAA indicates approach state, prefer converge or tunnel veil modes. Reserve high-density drift for non-affirmation phases.
