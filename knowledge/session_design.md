# Somna Session Design — Authoring Guide

## Overview

A Somna session is two files in `sessions/<name>/`:

- `session.yaml` — timeline of parameter keyframes with easing
- `affirmations.txt` — tagged phrase pools for veil + center-flash layers

Optional: `images/` folder (PNG/JPG/GIF/WebP/WebM), `fonts/` folder (.ttf/.otf session-specific overrides).

This document is the practical authoring reference. For the runtime contract, see `SESSION_TIMELINE.md`. For the canonical design spec, see Somna Bible Ch.4.

**Live reload:** `affirmations.txt` is reloaded by `phrase_pool.py` whenever its `mtime` changes. Edit the file during a running session — changes take effect within the next render frame. No restart required.

---

## The Two-Layer Model

When a session is running, there are two independent directors for parameter writes:

- **Timeline runner** — writes keyframes to `live_control.json` via `patch_live()`
- **Conductor FSM** — if active, owns `CONDUCTOR_OWNED_PARAMS` (beat_frequency, spiral_chaos, trail_decay, veil_mode, spiral_style, etc.) and will override timeline values during CALIBRATION/INDUCTION/DEEPENING/MAINTENANCE phases

**User slider drag wins over both.** Any param touched by a slider enters `timeline_locked_params` and the runner and Conductor both skip it until session restart.

**Implication for authoring:** when you write a session YAML, you are writing the "script" the runner follows when the Conductor is not active OR when the Conductor yields to timeline values during specific phases. Sessions with `conductor: disabled` in defaults run pure timeline mode.

---

## The Standard Session Arc

Most sessions follow a five-phase skeleton. These are authoring heuristics that predate the Conductor FSM but still map cleanly onto its phases:

```
Authoring Phase       Time %     Conductor FSM equivalent
──────────────────   ────────   ──────────────────────────
1. Orient             0–15%     CALIBRATION → early INDUCTION
2. Descent            15–40%    INDUCTION → DEEPENING
3. Work               40–75%    MAINTENANCE
4. Soak               75–85%    MAINTENANCE (late)
5. Return             85–100%   SESSION_END ramp
```

Exact percentages are guidelines. A 10-minute session compresses phases 1–2. A 90-minute session extends soak. Dedicated induction sessions skip soak; sleep sessions extend soak indefinitely.

---

## Parameter Guidance by Phase

### Phase 1 — Orient

**Goal:** Settle the user, establish the sound environment, prime expectations. Brain is alert.

| Parameter | Target | Reasoning |
|-----------|--------|-----------|
| `beat_frequency` | 9–12 Hz | Alpha. Entrainment begins here. |
| `beat_type` | `binaural` | Standard. Save experimental types for later phases. |
| `carrier_frequency` | 200–220 Hz | Neutral, comfortable. |
| `volume` | 60–70% | User may not have adjusted headphones yet. |
| `spiral_style` | fermat, archimedean, tunnel_dream | Calm, mathematical. |
| `spiral_speed_multiplier` | 0.3–0.6 | Slow. Faster is arousing. |
| `spiral_opacity` | 30–50% | Subtle. Not the focus yet. |
| `veil_opacity` | 0–20% | Barely visible. |
| `veil_mode` | `scroll` or `drift` | Gentle motion. Avoid `converge`/`tunnel`. |
| `center_flash_on_time` | 150–300 ms | Consciously readable. |
| `entrainment_strength` | 0.0 | Free-running spiral. |
| `trail_decay` | 0.0 | No trails at entry. |
| `phrases` | `orient` tag | Welcoming, safety, grounding. |

**Avoid:** Fast spirals, high veil opacity, subliminal flash timing, strobe mode, FM beat type.

---

### Phase 2 — Descent

**Goal:** Guide alpha → theta. Body dissociation threshold happens here.

| Parameter | Target | Reasoning |
|-----------|--------|-----------|
| `beat_frequency` | 6–9 Hz (descending) | Max 2 Hz drop per 5-minute keyframe. |
| `volume` | 65–75% | Slightly fuller as entrainment deepens. |
| `spiral_style` | galaxy, tunnel_dream, vortex, liminal | More immersive styles. |
| `spiral_speed_multiplier` | 0.4–0.8 | Increasing but measured. |
| `spiral_opacity` | 50–70% | More present. |
| `veil_opacity` | 20–40% | Building presence. |
| `veil_mode` | `drift` | Variable phrase speed appropriate. |
| `center_flash_on_time` | 80–150 ms | Transitioning toward subliminal. |
| `shadow_opacity` | 20–40% | Peripheral darkening begins. |
| `trail_decay` | 0.3–0.5 | Soft trails introduce visual persistence. |
| `feedback_mode` | `alpha_decay` or `none` | Alpha decay = fade-persistence. |
| `feedback_strength` | 0.3–0.5 | Conservative for busier styles. |
| `phrases` | `relax` tag | Somatic, body-scan language. |

**Transition note:** The shift from orient to descent phrasing is itself an induction deepener — the language change signals state change.

---

### Phase 3 — Work

**Goal:** Deliver core content at reduced critical faculty. Maintain depth without pushing deeper.

| Parameter | Target | Reasoning |
|-----------|--------|-----------|
| `beat_frequency` | 4–6 Hz | Stable theta. Hold here unless soak is next. |
| `beat_type` | `binaural`, `isochronic`, or `fm` | FM introduces sustained cortical tracking. |
| `fm_mod_depth` | 6–12 Hz | Only if `beat_type: fm`. Narrow = subtle warble. |
| `carrier_frequency` | 160–200 Hz | Can drop for somatic reinforcement. |
| `spiral_style` | kaleidoscope, interference, rose, moire, sacred_geometry | Mandala-adjacent. Supports phosphene cascade. |
| `spiral_speed_multiplier` | 0.3–0.7 | Moderate. Still hypnotic, not stimulating. |
| `spiral_chaos` | 0.08–0.20 | Slight organic distortion. |
| `spiral_opacity` | 70–90% | Primary visual field. |
| `veil_opacity` | 40–70% | Prominent but not blinding. |
| `veil_mode` | `converge` or `drift` | Converge suggests inevitability. |
| `center_flash_on_time` | 20–80 ms | Subliminal-to-barely-visible. |
| `center_flash_off_time` | 200–500 ms | Longer off than on. |
| `shadow_opacity` | 40–60% | Deep peripheral darkening. |
| `trail_decay` | 0.5–0.7 | Active range. **Safety cap: 0.80.** Above 0.80 causes additive blowout. |
| `feedback_mode` | `alpha_decay`, `rotational_smear`, `radial_zoom` | Spiral persistence cues depth. |
| `feedback_strength` | 0.5–0.8 | Use 0.5–0.7 for dense spiral centers (galaxy, vortex). |
| `entrainment_strength` | 0.03–0.08 | Subtle phase-lock to beat. Max 0.10. |
| `bilateral_panning` | true (optional) | Engages interhemispheric communication. |
| `bilateral_rate` | = `beat_frequency` | Match for spatial entrainment. |
| `bilateral_depth` | 0.3–0.6 | Moderate L/R alternation. |
| `bilateral_mode` | `smooth` | Sinusoidal pan. |
| `phrases` | session-specific deep tag | Core identity/therapeutic content. |

**Critical rule:** Do not introduce new spiral styles rapidly here. Pick one and hold it. Novelty is arousing.

---

### Phase 4 — Soak

**Goal:** Absorption at maximum depth. No novelty.

| Parameter | Target | Reasoning |
|-----------|--------|-----------|
| `beat_frequency` | 3–4.5 Hz | Deepest reliable active-mind state. |
| `spiral_speed_multiplier` | 0.2–0.4 | Very slow. Almost meditative. |
| `spiral_opacity` | 50–70% | Spiral should breathe, not demand. |
| `spiral_chaos` | 0.05–0.10 | Geometric order is more hypnotic at depth than chaos. |
| `veil_opacity` | 40–60% | Present but not heavy. |
| `veil_mode` | `drift` (slow) | Calm scatter. Avoid aggressive `converge`. |
| `center_flash_on_time` | 10–40 ms | Pure subliminal. |
| `center_flash_off_time` | 300–600 ms | Very slow cadence. |
| `trail_decay` | 0.55–0.65 | Persistent trails, not aggressive. |
| `feedback_mode` | `alpha_decay` | Minimal — don't disturb the soak. |
| `feedback_strength` | 0.5–0.7 | Stable. |
| `phrases` | session-specific soak tag (often `:seq`) | Core reinforcement. Short. Repeated. |
| `bg_mode` | unchanged | Do NOT change background. Novelty = disruption. |

**The soak phase is silent.** No new instructions. Just the phrases that have been building all session.

---

### Phase 5 — Return

**Goal:** Bring user to C1 safely. Integrate. Anchor.

| Parameter | Target | Reasoning |
|-----------|--------|-----------|
| `beat_frequency` | 8–12 Hz (ascending) | Match descent curve in reverse. |
| `spiral_speed_multiplier` | 0.5–0.8 | Gradually brightening. |
| `spiral_opacity` | 40–60% | Fading back. |
| `veil_opacity` | 15–30% | Tapering. |
| `veil_mode` | `scroll` | Simple, neutral. |
| `center_flash_on_time` | 100–200 ms | Return to readable. |
| `shadow_opacity` | 10–25% | Peripheral lightening. |
| `trail_decay` | 0.0–0.2 | Trails fading out. |
| `feedback_mode` | `none` | Stop persistence effects. |
| `entrainment_strength` | 0.0 | Release phase-lock. |
| `bilateral_panning` | false | Return to center. |
| `phrases` | `return` tag (often `:seq`) | Integration, grounding. |
| `volume` | 55–65% | Gently reducing. |

---

## Canonical Spiral Styles (26 + aliases)

Source of truth: `STYLE_MAP` in `layers/spirals_opengl.py`.

| Index | Style | Character |
|-------|-------|-----------|
| 0 | tunnel_dream | Classic depth cue |
| 1 | galaxy | Rotating arms, suppresses analytical engagement |
| 2 | archimedean | Even, non-hypnotic — grounding |
| 3 | kaleidoscope | Mandala, Level 3 phosphene support |
| 4 | interference | Wave interference pattern |
| 6 | vortex | Wide swirling descent |
| 7 | dna | Double helix |
| 9 | rose | Rosette pattern |
| 10 | moire | Interference stripes |
| 11 | spirograph | Epicycle-style |
| 12 | fermat | Golden-ratio packing, mathematical |
| 13 | superformula | Parametric geometric family |
| 14 | liminal | Threshold/transition feel |
| 16 | nebula | Diffuse cloud |
| 18 | cobwebs | Irregular radial threads |
| 19 | strange_attractor | Lorenz-like swirling trails |
| 20 | flow_field | Curl-noise organic streams |
| 21 | sacred_geometry | Flower of Life, concentric forms |
| 22 | recursive_fractal | Self-similar branching |
| 23 | potter_tunnel | Depth-layered tunnel |
| 24 | fractal_scale | Fractal scaling pattern |
| 25 | neuro_vortex | Independent-oscillator vortex |
| 26 | ojascki | Noise spiral |
| 27 | tunnel_warp | Time-bent radial interference |
| 28 | ganzflicker | Ganzfeld-compatible flicker |
| 29 | galaxy_morph | FBM morphing galaxy |

**Aliases:** `galaxy_arms` → galaxy, `bloom` → rose. Legacy names (`zyntaks_hybrid`, `fan_blade`, `star_polygon`, `dense_web`, `wide_vortex`, `interlocked`, `radiating_pulse`) still resolve but should not be used in new YAML.

**Not in STYLE_MAP (silent fallback to index 0):** `fibonacci`. Legacy sessions using this name have been silently playing tunnel_dream. Do not use in new YAML.

**Canonical veil modes:** `scroll`, `rain`, `drift`, `converge`, `strobe`, `tunnel`. (`mirror` was removed — do not reference.)

---

## YAML Structure Reference

```yaml
name: "Session Name"
description: >
  One to three sentences. Intent, target depth, special design notes.
duration: 2700           # total seconds
category: entrainment    # Induction | Focus | Sleep | Maintenance | Archive

defaults:
  carrier_frequency: 210.0
  volume: 70.0
  noise_color: pink
  noise_volume: 22
  tts_enabled: true
  tts_subliminal: false
  # Any parameter set here applies from t=0 until a keyframe changes it.

timeline:
  - t: 0
    label: orient
    ease: linear
    params:
      beat_frequency: 10.0
      spiral_style: fermat
      phrases: orient
      trail_decay: 0.0

  - t: 480
    label: descent
    ease: ease_in_out
    params:
      beat_frequency: 5.5
      # only include params that change at this keyframe
```

**Easing modes (case-sensitive strings):**

| Mode | Curve |
|------|-------|
| `linear` | Steady interpolation |
| `ease_in` | Slow start, fast end |
| `ease_out` | Fast start, slow end |
| `ease_in_out` | Smoothstep — most natural for most params |
| `instant` | Cut to value at keyframe time |

**No `step` mode.** If you write `ease: step`, it silently falls through to `linear`.

String and bool parameters are cut at keyframe boundaries regardless of easing. `spiral_style`, `veil_mode`, `phrases`, `bg_mode`, `beat_type`, `bilateral_mode`, `feedback_mode` should always use `ease: instant` for clarity.

**Keyframe format:** the preferred format uses a `params:` sub-key on each keyframe (nested). Flat keys directly on the keyframe are also merged, but `params:` wins on conflict.

---

## Affirmations File Structure

### Basic syntax

```
# [tag_name]
phrase one
phrase two
short phrase

# [next_tag]
...
```

The `phrases:` parameter in a keyframe tells the runner which `# [tag]` block to draw from. Untagged phrases (before any `# [tag]` header) are always active.

### Variant selection: `|` pipe

```
the weight is growing | you feel the weight growing | heaviness arrives
```

The `|` splits a single line into multiple independent phrase entries, each equally likely to be selected randomly.

### Sequential chains: `>>` double arrow

```
let go >> deeper >> gone
remember the sound >> remember the feeling >> remember the taste
```

When a chain is picked, subsequent `pick()` calls return the next chain element in order, consecutively, until the chain is exhausted. Then random selection resumes.

**Use case:** thought progressions that only make sense in order. "Remember X → remember Y → remember Z" delivers as a narrative arc, not three disconnected fragments.

### Sequential tag mode: `:seq` suffix

```
# [arrive:seq]
you are already here
the work has already begun
this is the place you kept coming back to
```

The `:seq` flag makes the entire tag play in written order (looping on exhaust) instead of random selection. The timeline runner writes `affirmations_mode: "sequential"` to `live_control.json` when the active tag has `:seq`.

**Chains inside `:seq` tags work correctly** — chains expand in place, each chain element taking its own cursor position.

**Use case:** any section where the order of delivery matters — openings, recon retrieve/update arcs, closing lines, conditioning windows with a build structure.

### Shadow words: `# [shadows]`

```
# [shadows]
empty
open
gone
soft | small | quiet
```

Single-word entries in the `# [shadows]` section are excluded from the main phrase pool and used exclusively by `pick_shadow()` for the subliminal shadow layer. `|` variants are supported.

### Semantic selector sub-pools: `# [pool_id.X]`

```
# [grounding.shadows]
still
rooted
here

# [grounding.center]
you are safe
you are grounded
```

Dotted tag names (`pool_id.shadows`, `pool_id.center`) are handled by `semantic_selector.py`, not the base phrase pool. These are used by advanced session patterns to supply separate content per layer within a named semantic pool. Most sessions do not need these.

### Phase-to-tag naming convention

Recommended, not required:

| Session Phase | Recommended Tag |
|---------------|-----------------|
| Orient | `orient` |
| Descent | `relax` or `descent` |
| Work | session-specific (`deep`, `identity`, `surrender`) |
| Soak | `soak` or session-specific (`good_girl`, `receive`) |
| Return | `return` |
| Recon retrieve | `recon_retrieve_<trace>` (matched exactly by agent) |
| Recon update | `recon_update_<trace>` (matched exactly by agent) |

---

## Common Authoring Mistakes

1. **Starting too deep.** Beginning at 4 Hz before the brain has synchronized. Use 9–10 Hz for 5–8 minutes first.

2. **Descent rate too fast.** Dropping more than 2 Hz per 5 minutes. The result is jarred, not deepened.

3. **Forgetting the return.** Ending at 4 Hz causes disorientation or headache. Always ascend to 8+ Hz before session end.

4. **Too much visual novelty at depth.** Changing spiral styles, switching veil modes, or altering background during work/soak. Novelty = arousal = shallower state.

5. **Phrases too long for depth.** Sentence-length affirmations during the 4 Hz soak do not process. The brain at theta is not parsing grammar. Soak-phase phrases: 1–5 words.

6. **Not matching phrase tag to keyframe.** Failing to include a `phrases:` change when the phase changes leaves orient-language playing during deep work. Always update `phrases:` at each major transition.

7. **High flash rate at depth.** `center_flash_off_time` below 100 ms during soak is arousing, not deepening. At depth, use 300–600 ms off-time.

8. **`trail_decay` above 0.80.** Safety cap. Above 0.80 causes additive blowout — dense spiral centers (galaxy, vortex) accumulate into a white blob. Effect compounds with `feedback_strength`.

9. **`entrainment_strength` above 0.10.** Agent-set values are capped here. Session YAML can technically go higher but visual flicker becomes excessive.

10. **Using `fibonacci` for `spiral_style`.** Not in STYLE_MAP. Silently falls back to tunnel_dream.

11. **Using `ease: step`.** Not a valid mode. Silently falls through to linear. Use `ease: instant`.

12. **Writing sequential content without `:seq` or `>>`.** A section that reads as an ordered progression in the file will be shuffled at runtime unless marked. Add the flag.

13. **Writing `recon_retrieve_<trace>` without a matching `recon_update_<trace>`.** The agent's `_recon_tick` requires both tags to arm the reconsolidation FSM. Orphan tags are ignored.

---

## Multi-Session and Returning User Considerations

- **Shorten descent for returning users.** The orient phase can compress to 3–5 minutes, descent to 5 minutes. Returning users reach depth faster via fractionation across sessions.
- **Anchor phrase consistency.** Conditioned triggers (e.g., "good girl") must appear in the same phase context across sessions, not randomly.
- **Progressive deepening across sessions.** Design session series: session 1 targets Focus 10 entry, session 2 reaches Focus 10 hold, session 3 reaches work window. Each session begins with a brief callback to the previous.

---

## Cross-References

- **Runtime contract:** `SESSION_TIMELINE.md` — how the runner consumes the YAML
- **Authoring spec:** `SESSION_AUTHORING.md` — deeper walkthrough
- **Conductor FSM:** `knowledge/conductor_fsm.md` — when the FSM is active, it owns the listed `CONDUCTOR_OWNED_PARAMS`
- **Reconsolidation:** `knowledge/reconsolidation_protocol.md` — recon tag conventions and FSM
- **Somatic palette:** `knowledge/somatic_palette.md` — chord evaluation and recording
- **Bible Ch.4:** `knowledge/bible_ch4_session_architecture.md` — canonical design spec
