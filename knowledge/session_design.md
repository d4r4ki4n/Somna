# Somna Session Design — Keyframe Arc Patterns and Parameter Guidance

## Overview

A Somna session is a `session.yaml` file plus an `affirmations.txt` file. The YAML defines a timeline of keyframes; the runner interpolates between them. The affirmations file provides the phrase pool for the veil and center-flash layers.

This document is the practical authoring guide: how to structure a session arc, which parameters to change at which phases, and what the common mistakes are.

---

## The Standard Session Arc

Every session should follow this five-phase skeleton:

```
Phase 1 — Orient       (0–15%)    Alpha entry. Full awareness. Set expectations.
Phase 2 — Descent      (15–40%)   Alpha → Theta. Somatic relaxation. Deepening.
Phase 3 — Work         (40–75%)   Deep Theta. Core content delivery. Hold the depth.
Phase 4 — Soak         (75–85%)   Deepest point. Repetition only. No new content.
Phase 5 — Return       (85–100%)  Ascent. Grounding. Integration.
```

The exact time percentages are guidelines, not rules. A 10-minute session can compress phases 1 and 2. A 90-minute session should extend the soak.

---

## Parameter Guidance by Phase

### Phase 1 — Orient

**Goal**: Settle the user, establish the sound environment, prime expectations.

| Parameter | Target | Reasoning |
|-----------|--------|-----------|
| `beat_frequency` | 9–12 Hz | Alpha. Brain is alert. Synchronization begins here. |
| `carrier_frequency` | 200–220 Hz | Neutral, comfortable. |
| `volume` | 60–70% | Not too loud — user may not have adjusted to the headphones yet. |
| `spiral_style` | fermat, archimedean, fibonacci | Calm, mathematical. Non-threatening. |
| `spiral_speed_multiplier` | 0.3–0.6 | Slow. Anything faster at this phase is arousing. |
| `spiral_opacity` | 30–50% | Subtle. Not the focus yet. |
| `veil_opacity` | 0–20% | Barely visible. Just enough to set the phrase pool. |
| `veil_mode` | scroll or drift | Gentle motion. Not converge — too stimulating. |
| `center_flash_on_time` | 150–300 ms | Consciously readable. Users should be reading these. |
| `phrases` tag | orient | Welcoming, safety, grounding language. |

**Avoid**: Fast spirals, high veil opacity, subliminal flash timing, strobe mode.

---

### Phase 2 — Descent

**Goal**: Guide the user from alpha relaxation into theta. The body dissociation threshold happens here.

| Parameter | Target | Reasoning |
|-----------|--------|-----------|
| `beat_frequency` | 6–9 Hz (descending) | Gradual. Max 2 Hz drop per 5-minute keyframe. |
| `volume` | 65–75% | Slightly fuller as entrainment deepens. |
| `spiral_style` | galaxy, tunnel_dream, vortex | More immersive styles. |
| `spiral_speed_multiplier` | 0.4–0.8 | Increasing, but still measured. |
| `spiral_opacity` | 50–70% | More present as dissociation begins. |
| `veil_opacity` | 20–40% | Building presence. |
| `veil_mode` | drift | Speed variance on individual messages is appropriate. |
| `center_flash_on_time` | 80–150 ms | Transitioning toward subliminal. |
| `shadow_opacity` | 20–40% | Darkening the peripheral field begins here. |
| `phrases` tag | relax | Somatic, body-scan language. Heaviness, sinking. |

**Transition note**: The shift from orient to descent phrasing is a signal to the user's body. The language change itself acts as an induction deepener.

---

### Phase 3 — Work

**Goal**: Deliver core session content at reduced critical faculty. Maintain the depth without pushing deeper.

| Parameter | Target | Reasoning |
|-----------|--------|-----------|
| `beat_frequency` | 4–6 Hz | Stable theta. Do not descend further unless soak is the immediate next phase. |
| `carrier_frequency` | 180–210 Hz | Can drop slightly for somatic reinforcement. |
| `spiral_style` | kaleidoscope, interference, rose, moire | Mandala-adjacent. Supports the Level 3–4 phosphene cascade. |
| `spiral_speed_multiplier` | 0.5–1.0 | Moderate. Still slow enough to be hypnotic, not stimulating. |
| `spiral_chaos` | 0.1–0.3 | Slight organic distortion adds depth without randomness. |
| `spiral_opacity` | 60–80% | The spiral is now the primary visual field. |
| `veil_opacity` | 40–60% | Phrases prominent but not blinding. |
| `veil_mode` | converge or drift | Converge is powerful here — phrases colliding at center suggest inevitability. |
| `center_flash_on_time` | 20–80 ms | Subliminal-to-barely-visible. The exact range depends on depth. |
| `center_flash_off_time` | 200–500 ms | Longer off-time than on. |
| `shadow_opacity` | 40–60% | Deep peripheral darkening encourages center focus. |
| `phrases` tag | session-specific deep content | Core identity or therapeutic content goes here. |
| `window_opacity` | 85–95% | Near-opaque if using overlay mode. |

**Critical rule**: Do not introduce new spiral styles rapidly here. Pick one and hold it. Novelty is arousing.

---

### Phase 4 — Soak

**Goal**: Absorption at maximum depth. No novelty. Repeat, repeat, repeat.

| Parameter | Target | Reasoning |
|-----------|--------|-----------|
| `beat_frequency` | 3–4.5 Hz | Deepest reliable active-mind state. |
| `spiral_speed_multiplier` | 0.3–0.5 | Very slow. Almost meditative. |
| `spiral_opacity` | 50–70% | Reduce slightly from work phase — the spiral should breathe, not demand. |
| `veil_opacity` | 30–50% | Present but not heavy. |
| `veil_mode` | drift (slow) | Calm scatter. No aggressive converge. |
| `center_flash_on_time` | 10–40 ms | Pure subliminal. Not consciously readable. |
| `center_flash_off_time` | 300–600 ms | Very slow cadence. |
| `phrases` tag | soak / good_girl / deep | Core reinforcement phrases. Short. Repeated. |
| `bg_mode` | null (image) or keep constant | Do NOT change the background here. Any novelty is a disruption. |

**The soak phase is silent**. No new instructions in the affirmations. No narrative. Just the phrases that have been building all session, arriving again and again.

---

### Phase 5 — Return

**Goal**: Bring the user back to C1 safely. Integrate the session. Anchor the experience.

| Parameter | Target | Reasoning |
|-----------|--------|-----------|
| `beat_frequency` | 8–12 Hz (ascending) | Match the descent curve in reverse. |
| `spiral_speed_multiplier` | 0.5–0.8 | Gradually brightening/quickening. |
| `spiral_opacity` | 40–60% | Fading back. |
| `veil_opacity` | 15–30% | Tapering to near-invisible. |
| `veil_mode` | scroll | Simple, neutral. |
| `center_flash_on_time` | 100–200 ms | Return to readable. The user should read these. |
| `shadow_opacity` | 10–25% | Peripheral field lightening. |
| `phrases` tag | return | Integration, grounding, carrying forward. Pride phrases. |
| `volume` | 55–65% | Gently reducing. |

---

## YAML Structure Reference

```yaml
name: "Session Name"
description: >
  One to three sentences. Describe intent, target depth, and any special design notes.
duration: 2700           # total seconds

defaults:
  carrier_frequency: 210.0
  volume: 70.0
  # Any parameter set here applies from t=0 until a keyframe changes it.
  # Defaults are useful for parameters that won't change much (carrier, font mode, etc.)

timeline:
  - t: 0
    label: "c1_orient"
    ease: linear          # or: ease_in, ease_out, ease_in_out, instant
    params:
      beat_frequency: 10.0
      spiral_style: "fermat"
      phrases: "orient"
      # ...

  - t: 480
    label: "focus10_entry"
    ease: ease_in
    params:
      beat_frequency: 5.5
      # only include params that change at this keyframe
```

**Easing modes**:
- `linear`: steady interpolation from previous keyframe value to this one.
- `ease_in`: slow start, fast end (parameters accelerate toward their target).
- `ease_out`: fast start, slow end (parameters coast into position — good for relaxation metaphors).
- `ease_in_out`: slow at both ends, fast in the middle (smoothstep — the most natural-feeling curve for most params).
- `instant`: cut to value at keyframe time. Use for `spiral_style`, `veil_mode`, `phrases` — anything that doesn't make sense to interpolate.

**Important**: `spiral_style`, `veil_mode`, `phrases`, and `bg_mode` should always use `ease: instant` — interpolation is not meaningful for categorical values. String and bool parameters are cut regardless, but making it explicit is good practice.

---

## Affirmations File Structure

The `affirmations.txt` file for any session uses tagged sections:

```
# [tag_name]

phrase one.
phrase two. | alternate variant of phrase two.
short phrase.

# [next_tag]
...
```

The `phrases:` parameter in a keyframe tells the runner which `# [tag]` block to draw from. The `|` pipe character provides random variant selection — both sides are equally likely to be shown.

**Phase-to-tag naming convention** (recommended, not required):

| Session Phase | Recommended Tag |
|---------------|-----------------|
| Orient | `orient` |
| Descent/relax | `relax` |
| Focus 10 entry | `focus10` |
| Work window | `deep` |
| Soak | `soak` or session-specific (e.g., `good_girl`) |
| Return | `return` |

---

## Common Authoring Mistakes

1. **Starting too deep**: Beginning at 4 Hz before the brain has had time to synchronize. Use 9–10 Hz for the first 5–8 minutes.

2. **Descent rate too fast**: Dropping more than 2 Hz per 5 minutes. The brain can't follow that fast. The result is the user feeling jarred rather than deepened.

3. **Forgetting the return**: Ending at 4 Hz is disorienting and can cause a headache. Always ascend to 8+ Hz before the session ends.

4. **Too much visual novelty at depth**: Changing spiral styles, switching veil modes, or altering background images during the work/soak phases. Novelty = arousal = shallower state.

5. **Phrases too long for the depth**: Long, sentence-length affirmations during the 4 Hz soak phase will not be processed effectively. The brain at 4 Hz is not parsing grammar. Keep soak-phase phrases to 1–5 words.

6. **Not matching phrase tag to keyframe**: Failing to include a `phrases:` parameter change when the phase changes means the user is hearing orient-phase language during the deep work window. Always include a `phrases` parameter update at each major phase transition.

7. **High flash rate at depth**: `center_flash_off_time` set below 100 ms during the soak phase is arousing, not deepening. At depth, the flash should be slow — 300–600 ms between flashes.

---

## Multi-Session and Returning User Considerations

- **Shorten descent**: If a session is explicitly designed for returning users, the orient phase can be compressed to 3–5 minutes and the descent to 5 minutes.
- **Anchor phrase consistency**: If you want a specific phrase (e.g., "good girl") to serve as a conditioned trigger across sessions, it must appear in the same phase context across multiple sessions, not randomly across phases.
- **Progressive deepening across sessions**: Design a session series where session 1 targets Focus 10 entry, session 2 reaches Focus 10 hold, session 3 reaches the work window. Each session in the series should begin with a brief fractionation callback to the previous session.
