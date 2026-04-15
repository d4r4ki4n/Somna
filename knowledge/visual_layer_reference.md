# Somna Visual Layer Reference
*Renderer Gaps, Spiral Science, and the Liminal Design*
*Research Collaborator Doc #13 · 30 March 2026*

---

## Current Shader — Style Inventory

14 styles dispatched via `u_style` in a single GLSL file (`shaders/spiral.glsl`):

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
| 14 | **Liminal** | Log spiral + noise warp + Voronoi | Domain warping, FBM, Voronoi lattice |

---

## Neuroscience — Klüver Form Constants

Heinrich Klüver classified four categories of geometric hallucinations in altered states:

| Form Constant | Geometry | Shader Coverage |
|---------------|----------|----------------|
| I — Tunnels | Concentric expanding/contracting forms | style_tunnel — covered |
| II — Spirals | Rotating, expanding/contracting spirals | Most styles — well covered |
| III — Lattices | Honeycombs, checkerboards, tessellations | **Liminal (Voronoi)** — now covered |
| IV — Cobwebs | Radial branching filigrees | Not yet implemented |

These arise from eigenmodes of neural activity in primary visual cortex (V1). V1's log-polar retinotopic mapping means that periodic cortical firing patterns project as these specific geometric forms. Spirals and tunnels are V1's native pattern language.

**Design implication**: A renderer that morphs between Klüver form constants is navigating users through V1's geometric vocabulary. The `u_chaos` parameter in Liminal does exactly this — Form Constant II (spiral) at low chaos, Form Constant III (lattice) at high chaos, with the transition itself as the experience.

---

## Photic Driving — Key Findings

- **Bartossek et al. 2021**: Visual flicker entrainment most effective at individual alpha frequency (IAF) — connects to Somna's IAF calibration
- **Notbohm et al. 2016**: Entrainment follows Arnold tongue dynamics — higher opacity = wider capture range
- **Oppermann et al. 2023**: Photic driving appears as transient EEG bursts, not continuous oscillations — do not expect steady-state entrainment

---

## Motion Aftereffect (MAE) and Aphantasia

Sustained rotational motion adapts direction-selective neurons in V1/MT. This effect is purely bottom-up — it operates without voluntary imagery generation. For the user (extreme aphantasia), the spiral IS the mechanism: external visual stimulation creates persistent neural adaptation via the intact bottom-up pathway, even though voluntary mental imagery is unavailable. The vague post-session perceptual effects the user describes are almost certainly MAE operating through this pathway.

---

## Style 14 — Liminal

**Designed by Research as a contribution to the codebase.**

Logarithmic spiral + simplex noise domain warping + Voronoi lattice emergence.

`u_chaos` parameter morphs between V1 eigenmodes:
- `0.0` — Clean logarithmic spiral (Form Constant II)
- `0.3–0.5` — Domain warping distorts spiral arms; they breathe organically
- `0.7–1.0` — Voronoi lattice emerges (Form Constant III); two form constants coexist

`beat_phase` drives **structural warp deformation** (not just brightness) — the entire visual breathes with the beat.

### Noise helpers added to shader (general-purpose)
- `snoise(vec2)` — 2D simplex noise
- `fbm4(vec2)` — Fractal Brownian Motion, 4 octaves with rotation
- `voronoi_dist(vec2)` — Voronoi distance field, 3×3 cell search

### Parameter recommendations by session type

| Session | chaos | tightness | count | thickness | speed | color_mode |
|---------|-------|-----------|-------|-----------|-------|------------|
| General trance | 0.15–0.25 | 4–6 | 3–4 | 12–16 | 0.8–1.0 | rainbow |
| Deep / theta | 0.35–0.50 | 3–5 | 2–3 | 14–18 | 0.5–0.7 | base |
| GENUS (40 Hz) | 0.05–0.15 | 5–7 | 4–6 | 10–14 | 1.0–1.2 | rainbow |
| Edison (hypnagogic) | 0.50–0.70 | 2–4 | 2–3 | 16–20 | 0.3–0.5 | base |
| Sleep onset | 0.20–0.35 | 3–5 | 2 | 18–22 | 0.3–0.5 | base (warm) |
| Freeform | 0.60–1.00 | varies | varies | varies | varies | rainbow |

### Agent modulation strategy

- **Session start**: chaos 0.10–0.20 (clean, build familiarity)
- **Deepening**: Ramp via RampEngine toward 0.40–0.60
- **Fractionation emergence**: Snap chaos to 0.05 — geometric order as perceptual contrast
- **Fractionation re-induction**: Ramp chaos back up — dissolving into organic feels like sinking
- **EEG high theta/alpha ratio**: Allow chaos to drift higher
- **Rule**: Never hard-cut chaos — always ramp. The transition is the experience.

---

## 8 Renderer Capability Gaps (Prioritized)

| # | Gap | Effort | Impact | Unlocks |
|---|-----|--------|--------|---------|
| 1 | Ping-pong FBO / feedback buffer | Moderate | **Transformative** | Trails, reaction-diffusion, post-processing |
| 2 | Post-processing pipeline (bloom, chromatic aberration, vignette) | Low-moderate | High polish | Requires Gap 1 |
| 3 | Noise functions (simplex, Voronoi) | **Low** | High | **DONE — added as helpers** |
| 4 | Domain warping | **Low** (once Gap 3 done) | High | **DONE — used in Liminal** |
| 5 | Ray-marched 3D tunnels | High | High, costly | Later phases |
| 6 | Reaction-diffusion (Gray-Scott) | Moderate | Unique aesthetic | Requires Gap 1 |
| 7 | Beat-phase expanded modulation | Very low | Moderate | Works incrementally |
| 8 | Advanced blend modes | Low | Moderate | None |

**Priority**: Implement Gap 1 (FBO infrastructure) before any more spiral styles. Once in place, every existing style gets a "trails" mode for free.

---

## EEG-Visual Coupling Opportunities (Phase 3)

When `eeg_engine.py` is stable, these mappings become available (toggle via `eeg_visual_feedback: true` in `live_control.json`):

| EEG Signal | Visual Target | Mapping |
|------------|--------------|---------|
| `eeg_alpha` | `spiral_opacity` | Higher alpha = slightly higher opacity |
| `eeg_theta` | `spiral_chaos` (Liminal) | Higher theta = more organic/warped |
| `eeg_trance_score` | Trail length (future FBO) | Deeper = more visual persistence |
| `eeg_alpha_theta_ratio` | Color temperature | Lower ratio (more theta) = warmer colors |
| `eeg_beta` | Domain warp frequency | Higher beta = faster warp evolution |
| `eeg_quality` | Vignette intensity | Poor signal = stronger vignette (subtle cue) |

Smooth all EEG→visual mappings with exponential moving average (τ ~2–5 seconds) to prevent visual jitter.
