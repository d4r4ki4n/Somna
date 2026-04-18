# Somna Visual Layer Reference

*Renderer Architecture, Spiral Science, and the Liminal Design*

**Status:** Specification (v2 — updated with stochastic resonance shader, FBO status, IPC fix)

**Author:** Ed / Reese

**Date:** 17 April 2026

**Loaded by:** Active session ticks when agent adjusts visual parameters; idle planning for session authoring

**Authority:** This file is the operational reference for the LLM agent. The authoritative design specification lives in the Somna Bible, Chapter 8 — Visual & VR. When this file and the Bible disagree, the Bible wins.

---

## 1. Current Shader — Style Inventory

15 styles dispatched via `u_style` in a single GLSL file (`shaders/spiral.glsl`):

| u_style | Name | Type | Key Technique |
|---------|------|------|---------------|
| 0 | Tunnel Dream | Polar log-depth | Concentric rings + twisted spokes |
| 1 | Galaxy Arms | Logarithmic | Log-polar arm field, core glow |
| 2 | Archimedean | Archimedean r∝θ | Shared archimedean_field() helper |
| 3 | Kaleidoscope | Angular folding | Sector mirroring + dual sine |
| 4 | Interference | Dual-source wave | Two origins, moiré beating |
| 5 | Electric | Archimedean + pseudo-noise | 5-octave sine noise, spark overlay |
| 6 | Vortex | Hyperbolic 1/r | Turbulence, singularity core |
| 7 | DNA | Counter-rotating helices | Double helix with rungs |
| 8 | Fibonacci | Golden-ratio logarithmic | Phi growth, petal width scaling |
| 9 | Bloom | Polar rose r=cos(k·θ) | 4 counter-rotating petal layers |
| 10 | Moiré | Dual counter-rotating | CW+CCW spirals, crossing flares |
| 11 | Spirograph | Hypotrochoid | Parametric, min-distance field |
| 12 | Fermat | r∝√θ | Dense center, sunflower |
| 13 | Superformula | Gielis superformula | Pointiness exponent, 3 nested copies |
| 14 | Liminal | Log spiral + noise warp + Voronoi | Domain warping, FBM, Voronoi lattice. Chaos-dependent: low chaos = spiral (Form Constant II), high chaos = lattice (Form Constant III). **Implemented.** |

---

## 2. Neuroscience — Klüver Form Constants

Heinrich Klüver classified four categories of geometric hallucinations in altered states:

| Form Constant | Geometry | Shader Coverage |
|---------------|----------|----------------|
| I — Tunnels | Concentric expanding/contracting forms | Tunnel Dream (style 0) — covered |
| II — Spirals | Rotating, expanding/contracting spirals | Most styles — well covered |
| III — Lattices | Honeycombs, checkerboards, tessellations | Liminal (style 14, Voronoi at high chaos) — covered |
| IV — Cobwebs | Radial branching filigrees | Not yet implemented |

These arise from eigenmodes of neural activity in primary visual cortex (V1). V1's log-polar retinotopic mapping means that periodic cortical firing patterns project as these specific geometric forms. Spirals and tunnels are V1's native pattern language.

**Design implication**: A renderer that morphs between Klüver form constants is navigating users through V1's geometric vocabulary. The `u_chaos` parameter in Liminal does exactly this — Form Constant II (spiral) at low chaos, Form Constant III (lattice) at high chaos, with the transition itself as the experience.

---

## 3. Photic Driving — Key Findings

- **Bartossek et al. 2021**: Visual flicker entrainment most effective at individual alpha frequency (IAF) — connects to Somna's IAF calibration
- **Notbohm et al. 2016**: Entrainment follows Arnold tongue dynamics — higher opacity = wider capture range
- **Oppermann et al. 2023**: Photic driving in the alpha band enhances visual cortex excitability, supporting the use of alpha-frequency spiral rotation during INDUCTION
- **Schwab et al. 2006**: EEG photic driving response correlates with hypnotic susceptibility — subjects with stronger driving response show deeper trance

**Practical implication for Somna**: `spiral_speed_multiplier` should approximate the user's IAF during INDUCTION (8–13 Hz range). The Conductor manages this automatically when EEG is active.

---

## 4. Shader Architecture

### 4.1 Primary Spiral Shader (`shaders/spiral.glsl`)

Single GLSL fragment shader dispatching all 15 styles via `u_style` uniform integer. Key uniforms:

| Uniform | Type | Range | Description |
|---------|------|-------|-------------|
| `u_style` | int | 0–14 | Style selector |
| `u_time` | float | 0+ | Elapsed time in seconds |
| `u_speed` | float | 0.1–3.0 | Rotation/animation speed multiplier |
| `u_chaos` | float | 0.0–1.0 | Complexity/distortion parameter. Per-style interpretation. |
| `u_color_shift` | float | 0.0–1.0 | Hue rotation offset |
| `u_base_color` | vec3 | RGB | Base color for the spiral. Default derives from Rosé Pine Moon Iris (`#c4a7e7` = vec3(0.769, 0.655, 0.906)). |
| `u_opacity` | float | 0.0–1.0 | Layer opacity (composited in the layer stack) |
| `u_resolution` | vec2 | px | Viewport resolution |

### 4.2 Stochastic Resonance Shader (`shaders/stochastic_resonance.glsl`)

Adds calibrated noise to subliminal visual stimuli to enhance detection via stochastic resonance — the phenomenon where adding noise to a sub-threshold signal can push it above the detection threshold.

| Uniform | Type | Range | Description |
|---------|------|-------|-------------|
| `u_sr_noise_level` | float | 0.0–1.0 | Noise intensity. Optimal level is signal-dependent; the Conductor tunes this. |
| `u_sr_enabled` | bool | — | Toggle. Disabled during sleep sessions and GENUS_BLOCK. |

The stochastic resonance shader is applied as a post-processing pass on the veil and center-flash layers — it does not affect the spiral layer. This is deliberate: the spiral is a conscious entrainment stimulus, while SR enhances subliminal text perception.

See `knowledge/stochastic_resonance.md` for the neuroscience and `knowledge/subliminal_text_perception.md` for the perceptual model.

### 4.3 FBO Trail Decay Shader (`shaders/trail_decay.glsl`)

**Status: Implemented.** Uses framebuffer object (FBO) feedback to create persistence-of-vision trails on the spiral layer.

| Uniform | Type | Range | Description |
|---------|------|-------|-------------|
| `u_trail_decay` | float | 0.0–1.0 | Decay rate. 0.0 = instant clear (no trails). 1.0 = permanent (full paint mode). |
| `u_trail_color_shift` | float | 0.0–1.0 | Hue rotation applied to decaying trails |

The previous frame is composited with the current frame at `u_trail_decay` opacity, creating a temporal smear effect. At high values (0.8+), the display becomes a paint-like accumulation of spiral paths. The Conductor owns `trail_decay` during active sessions.

See `knowledge/fbo_trail_decay.md` for implementation details.

### 4.4 Additional Shaders

| Shader | File | Purpose |
|--------|------|---------|
| Background layer | `shaders/background.glsl` | Image slideshow compositing with fade transitions |
| Veil text | `shaders/veil.glsl` | Scrolling text rendering with per-mode motion (7 modes) |

---

## 5. Renderer Gap Analysis — Current Status

The original gap analysis identified 8 capabilities missing from the renderer. Updated status:

| # | Gap | Status | Notes |
|---|-----|--------|-------|
| 1 | FBO / feedback buffers | ✅ **Closed** | `shaders/trail_decay.glsl` implemented. `u_trail_decay` uniform active. See `fbo_trail_decay.md`. |
| 2 | Form Constant III (lattice) | ✅ **Closed** | Liminal style (index 14) implements Voronoi lattice at high `u_chaos`. |
| 3 | Form Constant IV (cobwebs) | ❌ Open | Radial branching filigrees. No shader implementation yet. |
| 4 | Temporal frequency modulation | ❌ Open | Flicker at specific frequencies (alpha, theta) independent of rotation speed. Would require a temporal modulation uniform. |
| 5 | Depth-of-field simulation | ❌ Open | Simulated focal plane to create depth perception without stereoscopy. |
| 6 | Color temperature shifting | ❌ Open | Warm→cool color progression correlated with depth. Currently only `u_color_shift` (hue rotation). |
| 7 | Multi-layer spiral compositing | ❌ Open | Multiple spiral styles rendered simultaneously at different opacities. Currently single-style dispatch. |
| 8 | Stochastic resonance noise | ✅ **Closed** | `shaders/stochastic_resonance.glsl` implemented. `u_sr_noise_level` uniform active. |

**3 of 8 gaps closed.** 5 remain open as future development targets.

---

## 6. Liminal Style — Deep Dive

Liminal (style 14) was designed as a proof-of-concept addressing three specific gaps: Form Constant III coverage, organic/non-geometric visual language, and chaos-driven morphing between form constant classes.

### 6.1 Architecture

Three layered techniques composited in a single shader pass:

1. **Base spiral**: Logarithmic spiral field (`log(r)` radial, linear angular). This is the Form Constant II foundation.
2. **Domain warping**: Simplex noise FBM (fractal Brownian motion) applied as UV offset before spiral evaluation. Creates organic distortion that increases with `u_chaos`.
3. **Voronoi lattice**: Voronoi cell distance field overlaid at opacity proportional to `u_chaos`. At high chaos, the Voronoi pattern dominates — Form Constant III.

### 6.2 The Chaos Parameter in Liminal

| u_chaos | Visual | Form Constant | Session Phase |
|---------|--------|---------------|---------------|
| 0.0–0.2 | Clean logarithmic spiral with subtle breathing | II (spiral) | INDUCTION — familiar, non-threatening |
| 0.2–0.5 | Spiral with organic warping, edges soften | II → III transition | DEEPENING — increasing complexity |
| 0.5–0.8 | Lattice emerging through warped spiral | III (lattice) | MAINTENANCE — full complexity |
| 0.8–1.0 | Dominant Voronoi lattice, spiral barely visible | III (lattice, dominant) | Deep MAINTENANCE — maximum visual complexity |

### 6.3 Helper Functions

Liminal uses three helper functions shared across the shader:

- `simplex3d(vec3 p)` — 3D simplex noise for domain warping
- `fbm(vec3 p, int octaves)` — Fractal Brownian motion (4 octaves default)
- `voronoi(vec2 p)` — Returns (cell_distance, cell_id) for lattice rendering

### 6.4 Per-Session-Type Recommendations

| Session Type | Liminal u_chaos Range | Reasoning |
|-------------|----------------------|-----------|
| Trance | 0.2–0.8 (Conductor-driven) | Full chaos range. Conductor ramps with depth. |
| Sleep | 0.0–0.3 (then fade to 0% opacity) | Gentle only. Liminal at high chaos is too stimulating for sleep onset. |
| GENUS | Not recommended | GENUS uses interference/kaleidoscope for 40 Hz flicker compatibility. |
| Training | 0.3–0.6 (hold steady) | Moderate complexity. Don't distract from the operant loop. |

---

## 7. Layer Stack

The visual display composites 5 layers in painter's order (back to front):

| Layer | File | z-order | Content |
|-------|------|---------|---------|
| Background | `layers/background_layer.py` | 0 (back) | Image slideshow with fade transitions |
| Spiral | `layers/spiral_layer.py` | 1 | GPU-rendered spiral (15 styles, ModernGL) |
| Shadows | `layers/shadows_layer.py` | 2 | Subliminal drifting word shadows |
| Veil | `layers/veil_layer.py` | 3 | Scrolling affirmation text (7 modes) |
| Center Text | `layers/centertext_layer.py` | 4 (front) | Flashing center affirmations |

### 7.1 Veil Modes

7 modes controlling how affirmation text moves across the display:

| Mode | Behavior |
|------|----------|
| `scroll` | Continuous horizontal scroll, constant speed |
| `rain` | Vertical fall, randomized horizontal position |
| `drift` | Slow wandering motion with per-message speed variance |
| `converge` | Messages move toward screen center from edges |
| `strobe` | Full-screen flash — all messages appear simultaneously, brief duration |
| `tunnel` | Messages scale from small (distant) to large (close), simulating depth |
| `null` | Auto-rotate through other modes on a timer. The 7th "mode" is a meta-mode. |

---

## 8. Agent Modulation of Visual Parameters

The agent adjusts visual parameters via the IPC StateServer:

```python
from ipc import patch_live
patch_live({
    "spiral_style": "liminal",
    "spiral_chaos": 0.4,
    "spiral_opacity": 0.6,
    "veil_mode": "drift",
    "veil_opacity": 0.3
})
```

Do NOT use `_patch_live()` (deprecated). Do NOT write `live_control.json` directly.

### 8.1 Parameter Ownership During Sessions

| Parameter | Owner | Agent Can Adjust? |
|-----------|-------|-------------------|
| `spiral_style` | Conductor / Palette | Only when no active palette chord |
| `spiral_chaos` | Conductor | NO — Conductor drives chaos based on depth |
| `spiral_opacity` | Agent | YES |
| `spiral_speed_multiplier` | Agent | YES |
| `trail_decay` | Conductor | NO — Conductor drives trail based on depth |
| `sr_noise_level` | Conductor | NO — Conductor tunes SR level |
| `veil_mode` | Conductor / Palette | Only when no active palette chord |
| `veil_opacity` | Agent | YES |
| `shadow_opacity_target` | Conductor | NO |
| `center_flash_on_time` | Agent | YES |

### 8.2 EEG-Reactive Visual Mappings

The Conductor implements several EEG-to-visual parameter mappings:

| EEG Metric | Visual Parameter | Mapping | Status |
|------------|-----------------|---------|--------|
| trance_score | `spiral_chaos` | Higher depth → higher chaos (Liminal: more lattice) | Implemented |
| trance_score | `trail_decay` | Higher depth → longer trails | Implemented |
| trance_score | `shadow_opacity_target` | Higher depth → more visible subliminal shadows | Implemented |
| SQI | `sr_noise_level` | Lower SQI → reduce SR (unreliable depth data) | Implemented |
| FAA (approach) | `veil_opacity` | Positive FAA → slightly increase veil visibility | Planned |

---

## 9. Rosé Pine Moon — Visual Context

The UI control panel uses Rosé Pine Moon exclusively (see `imgui_visual_design_reference.md`). The visual display's procedural colors are independent of the UI palette, but the default `u_base_color` for the spiral shader derives from the Iris token (`#c4a7e7`) to maintain visual coherence when the control panel overlays the display.

The `u_color_shift` uniform rotates hue from this base. A shift of 0.0 = pure Iris purple. The full hue wheel is available for session-specific color theming.

---

## 10. Research Citations

| Source | Contribution |
|--------|-------------|
| Klüver 1966 | Form constant classification (I–IV) |
| Bressloff et al. 2001 | Mathematical model of V1 pattern formation and log-polar retinotopic mapping |
| Bartossek et al. 2021 | Visual flicker entrainment at IAF |
| Notbohm et al. 2016 | Arnold tongue dynamics for entrainment capture range |
| Oppermann et al. 2023 | Photic driving enhances visual cortex excitability |
| Schwab et al. 2006 | Photic driving response correlates with hypnotic susceptibility |
| Moss et al. 2004 | Stochastic resonance in biological signal detection |
