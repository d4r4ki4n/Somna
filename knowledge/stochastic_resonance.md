# Stochastic Resonance Subliminal Enhancement

Bible Ch.8 Â§Stochastic-Resonance in Research Reference Series. Authored by Research (External Research Collaborator), March 2026.

---

## Executive Summary

Stochastic resonance (SR) is the counterintuitive phenomenon where adding precisely calibrated noise to a sub-threshold signal makes it more perceptible, not less. At an optimal intermediate noise level, noise pushes a signal that would otherwise sit below the detection threshold just above it, enabling neural detection that would not otherwise occur.

**SR is one of the cleanest enhancement tools available for an aphantasic user.** It operates entirely through bottom-up sensory mechanisms at V1 and peripheral processing. No top-down imagery pathway is involved or required. SR works identically regardless of whether the user can generate voluntary mental images.

---

## Core Mechanism

The inverted U curve relating noise amplitude to signal detection:
- Too little noise: signal remains sub-threshold, no enhancement
- Optimal noise: noise pushes signal above detection threshold on a sufficient fraction of presentations — maximum information transfer
- Too much noise: noise dominates, detection degrades

Key insight: biological neural systems are nonlinear threshold detectors. A neuron fires or it doesn't. If a signal sits just below firing threshold, a small amount of noise occasionally pushes the combined signal+noise above threshold.

**van der Groen & Wenderoth (2016), Journal of Neuroscience 36(19):** Applied transcranial random noise stimulation to occipital cortex. At optimal noise level, detection of sub-threshold visual stimuli improved by 9.7 ± 4.6%. The cortical SR effect was comparable to optimal noise added directly to visual stimuli (11.2 ± 4.7%). SR works at the neural network level (V1), not just at peripheral receptors.

**Temporal dynamics:** Time-varying noise (per-frame) is more effective than static noise. The visual system adapts to static patterns within milliseconds, eliminating the SR effect. Noise must be spatially uncorrelated (per-pixel) and temporally uncorrelated (per-frame).

**Optimal noise level:** Sweet spot where noise power is 50–150% of the signal threshold power. If text alpha is 0.05, effective SR noise amplitude is approximately 0.025–0.075. The optimum is individual-specific.

---

## Application to Somna's Subliminal Text

### Target Layers

| Layer | Current Timing | Current Opacity | SR Application |
|-------|---------------|-----------------|----------------|
| Subliminal Shadows | ON 40ms / OFF 180ms | Alpha ~0.10 | Per-pixel noise to text alpha during ON window |
| Affirmation Engine | Flash ON 120ms / OFF 80ms, beat-synced | Variable sub-threshold | Per-pixel noise during flash ON; amplitude can be modulated by beat phase |

Noise is applied only to the **alpha channel** of the rendered text. RGB channels remain unchanged — only visibility (alpha) is modulated.

---

## GLSL Implementation

```glsl
// Stochastic resonance noise injection for subliminal text alpha
uniform float u_sr_noise_level;  // 0.0 = off, 0.5-1.5 = active SR range
uniform float u_time;

// Per-fragment temporal noise — MUST change every frame
float sr_noise(vec2 coord, float time) {
    return fract(sin(dot(coord * time, vec2(12.9898, 78.233))) * 43758.5453) * 2.0 - 1.0;
}

// Apply to text alpha in the rendering pass:
// float noise = sr_noise(gl_FragCoord.xy, u_time);
// float noisy_alpha = clamp(text_alpha + u_sr_noise_level * noise, 0.0, 1.0);
```

Implementation notes:
- `u_time` must advance every frame. A frozen hash produces static noise — no SR.
- Clamp is mandatory. Negative alpha causes rendering artifacts on some GPUs.
- `u_sr_noise_level = 0.0` completely disables the effect — identical output to current path.
- Noise outputs in [−1.0, +1.0]. Pixels with increased alpha occasionally cross detection threshold — that's the SR effect.

---

## Audio-Domain SR (SSB Subliminal Channel)

Pink noise is already available in the audio engine. SR can be applied to the SSB subliminal audio channel:
- Add calibrated noise to the subliminal speech signal before SSB modulation
- Route a controlled fraction of the existing pink noise into the subliminal mix
- New parameter: `sr_audio_noise_level` (float, 0.0–1.0)
- Same inverted U principle applies — optimal noise enhances speech intelligibility at sub-threshold volumes

Lower priority than visual SR.

---

## live_control.json Keys

| Key | Type | Range | Default | Description |
|-----|------|-------|---------|-------------|
| `sr_noise_level` | float | 0.0–2.0 | 0.0 | Visual SR noise amplitude for subliminal text layers. Sweet spot expected 0.5–1.5. |
| `sr_audio_noise_level` | float | 0.0–1.0 | 0.0 | Audio SR noise amplitude for SSB subliminal channel. |

---

## Agent-Driven Optimization (Sweep Protocol)

1. Baseline: start with `sr_noise_level = 0.0`. Collect baseline metrics.
2. Increment by 0.1 across sessions, or within a single session during stable trance. Range: 0.0 → 2.0.
3. Monitor: EEG markers (alpha power / SEF95 changes), subjective report ("did you notice text?" — should always be "no"), behavioral (post-session priming effects).
4. Identify optimum: where neural/behavioral markers show maximum response without conscious text detection.

### EEG-Gated Adaptive SR

| Trance State | SEF95 | SR Adjustment | Rationale |
|-------------|-------|---------------|-----------|
| Deep trance | Lower SEF95 | Slightly increase SR noise | Perceptual threshold shifts upward — more noise needed |
| Light trance | Standard SEF95 | Standard SR level | Threshold at resting position |
| Alert / emerging | Higher SEF95 | Reduce or disable SR | Risk of conscious text detection increases |

Requires stable SEF95 pipeline (see `sef95_trance_depth.md`).

---

## Implementation Priority

| Phase | Task | Priority |
|-------|------|----------|
| 1 | Add `u_sr_noise_level` uniform to subliminal text shader pass; `sr_noise()` function; alpha-channel noise injection | Highest |
| 2 | Add `sr_audio_noise_level` to SSB subliminal audio path | Medium |
| 3 | Agent sweep protocol to find optimal SR level | Medium |
| 4 | EEG-gated adaptive SR | Lower |

Phase 1 is ~5 lines of GLSL plus one new uniform binding. The real work is the agent-side sweep protocol.

**Start conservative (0.3–0.5) and sweep up.** The inverted U is real — too much noise actively degrades detection.
