# Spiral Authoring Guide — Visual Parameter Reference for Session Design

**Status:** Specification (v1)

**Author:** Ed / Reese

**Date:** 18 April 2026

**Loaded by:** `_load_idle_knowledge()` during idle planning for session authoring; active session ticks when agent adjusts visual parameters

**Authority:** This file is the operational reference for the LLM agent. The authoritative design specifications live in the Somna Bible Chapter 8 — Visual & VR, the visual_layer_reference.md (renderer architecture), and the Next-Gen Spiral Renderer spec (multi-pass pipeline). When this file and those documents disagree, they win.

---

## 1. What This File Is For

This file tells the agent **how to use spirals in sessions** — which styles to select, which parameters to adjust, how they interact with session phase and EEG state, and what mistakes to avoid.

This file does NOT cover:
- Shader implementation details (see visual_layer_reference.md)
- Render pipeline architecture (see Next-Gen Spiral Renderer spec)
- Veil text overlay (see session_design.md §Content Authoring)
- Stochastic resonance noise layer (see visual_layer_reference.md §Stochastic Resonance)

The agent selects and adjusts spiral parameters via:

```python
from ipc import patch_live
patch_live({
    "spiral_style": "tunnel_dream",
    "spiral_speed": 0.8,
    "spiral_chaos": 0.2,
    "spiral_tightness": 5,
    "spiral_count": 3,
    "spiral_thickness": 14,
    "spiral_feedback_mode": "alpha_decay",
    "bloom_intensity": 0.3,
    "color_temperature_bias": 0.0
})
```

Do NOT use `_patch_live()` (deprecated). Do NOT write `live_control.json` directly.

---

## 2. The 20 Spiral Styles

### 2.1 Style Inventory

Every style has an integer index (`u_style` uniform) and a string name used in `live_control.json` and `session.yaml`. Always use the string name in agent code and session files.

| Index | Name | Mathematical Type | Klüver FC | Visual Character |
|-------|------|-------------------|-----------|-----------------|
| 0 | `tunnel_dream` | Polar log-depth | I — Tunnel | Concentric rings with twisted spokes. Classic tunnel. Steady, hypnotic, reliable. |
| 1 | `galaxy_arms` | Logarithmic spiral | II — Spiral | Log-polar arm field with glowing core. Expansive, slow, cosmic. |
| 2 | `archimedean` | Archimedean r∝θ | II — Spiral | Evenly spaced arms. Clean, mathematical, predictable. |
| 3 | `kaleidoscope` | Angular folding | III — Lattice | Sector mirroring with dual sine modulation. Symmetric, complex, meditative. |
| 4 | `interference` | Dual-source wave | II — Spiral | Two wave origins creating moiré beating. Rhythmic, pulsing, organic. |
| 5 | `electric` | Archimedean + noise | II — Spiral | 5-octave sine noise with spark overlay. Energetic, crackling, alert. |
| 6 | `vortex` | Hyperbolic 1/r | I — Tunnel | Turbulent singularity core. Intense, pulling, deep. |
| 7 | `dna` | Counter-rotating helices | II — Spiral | Double helix with rungs. Structured, biological, rhythmic. |
| 8 | `fibonacci` | Golden-ratio logarithmic | II — Spiral | Phi-scaled growth with petal width. Natural, organic, calming. |
| 9 | `bloom` | Polar rose r=cos(k·θ) | II — Spiral | 4 counter-rotating petal layers. Floral, breathing, gentle. |
| 10 | `moire` | Dual counter-rotating | II — Spiral | CW+CCW spirals with crossing flares. Complex, shimmering, hypnotic. |
| 11 | `spirograph` | Hypotrochoid | II — Spiral | Parametric curves, min-distance field. Precise, playful, intricate. |
| 12 | `fermat` | r∝√θ | II — Spiral | Dense center, sunflower pattern. Organic, dense, grounding. |
| 13 | `superformula` | Gielis superformula | II — Spiral | Pointy exponent, 3 nested copies. Alien, sharp, unusual. |
| 14 | `liminal` | Log spiral + noise warp + Voronoi | II→III morphing | Domain warping + Voronoi lattice emergence. Chaos-dependent: clean spiral at low chaos, lattice at high chaos. The transition IS the experience. |
| 15 | `cobwebs` | DLA-inspired radial branching | IV — Cobweb | Radial branching filigrees. Completes Klüver FC IV. Delicate, fractal, organic. |
| 16 | `strange_attractor` | Rössler/Lorenz density | II — Spiral | Chaotic attractor trajectory projection. Never-repeating, alive, unpredictable. |
| 17 | `flow_field` | Curl noise advection | II — Spiral | Visual smoke/fluid currents. Coherent but unpredictable. Soft, flowing, dreamlike. |
| 18 | `sacred_geometry` | Hex/triangular tiling | III — Lattice | Precise tessellation with phase-locked tile fills. Geometric, meditative, structured. Supports per-tile 40Hz flicker for GENUS. |
| 19 | `recursive_fractal` | Self-similar infinite zoom | I — Tunnel | Continuous forward motion through fractal geometry. FC-I tunnel on steroids. Absorbing, infinite, deep. |

### 2.2 Klüver Form Constant Coverage

| Form Constant | Geometry | Covered By |
|---------------|----------|-----------|
| I — Tunnels | Concentric expanding/contracting | `tunnel_dream`, `vortex`, `recursive_fractal` |
| II — Spirals | Rotating, expanding/contracting | `galaxy_arms`, `archimedean`, `interference`, `electric`, `fibonacci`, `bloom`, `moire`, `spirograph`, `fermat`, `superformula`, `dna`, `liminal` (low chaos), `strange_attractor`, `flow_field` |
| III — Lattices | Honeycombs, tessellations | `kaleidoscope`, `liminal` (high chaos), `sacred_geometry` |
| IV — Cobwebs | Radial branching filigrees | `cobwebs` |

**Why this matters:** These four categories are the eigenmodes of V1 neural activity. A renderer that moves between them is navigating the brain's native geometric vocabulary. Style selection isn't aesthetic preference — it's selecting which V1 eigenmode to activate.

### 2.3 Session-Type Style Recommendations

| Session Type | Recommended Styles | Avoid | Reasoning |
|-------------|-------------------|-------|-----------|
| **Standard trance** | `tunnel_dream`, `galaxy_arms`, `fibonacci`, `bloom`, `moire`, `liminal`, `flow_field` | `electric`, `superformula` | Smooth, rhythmic patterns support theta descent. Avoid stimulating or sharp forms. |
| **Deep theta / extended** | `vortex`, `liminal` (chaos 0.35–0.50), `flow_field`, `recursive_fractal` | `electric`, `spirograph`, `dna` | Absorbing, pulling patterns. Avoid anything structured enough to engage analytical processing. |
| **Sleep onset** | `tunnel_dream`, `fibonacci`, `bloom`, `flow_field` | `electric`, `strange_attractor`, `cobwebs`, `sacred_geometry` | Gentle, slow, warm. Visual tapers to black by minute 10. Avoid anything stimulating or complex. |
| **GENUS (40 Hz)** | `sacred_geometry`, `kaleidoscope`, `interference` | `flow_field`, `bloom`, `cobwebs` | Per-tile or per-element flicker for isochronic stimulation. Need discrete visual elements for 40Hz modulation. |
| **Edison (hypnagogia)** | `liminal` (chaos 0.50–0.70), `strange_attractor`, `cobwebs` | `tunnel_dream`, `archimedean` | Organic, unpredictable patterns that mirror hypnagogic imagery. Avoid regular patterns that anchor attention. |
| **Fractionation** | Start: current style. Emerge: snap to `archimedean` or `tunnel_dream` (clean, ordered). Redrop: return to previous or advance to next chord style. | Hard-cutting to `liminal` or `strange_attractor` on emergence | Emergence needs geometric order as perceptual contrast. The contrast between organic depth and clean emergence IS the fractionation experience. |
| **Training mode** | Same as standard trance. Agent adjusts parameters as operant pressure, not style switches. | Frequent style switches | Training mode uses parameter adjustment (speed, chaos, tightness) as deepening pressure. Style stability provides baseline. |
| **Calibration (sessions 1–10)** | `tunnel_dream` (sessions 1–3), broaden to `galaxy_arms`, `fibonacci`, `liminal` (sessions 4–7), full range (sessions 8–10) | Anything complex before session 4 | Progressive introduction. User needs to build familiarity before complex styles are meaningful. |

---

## 3. Core Visual Parameters

These are the parameters the agent controls during sessions. All are written via `patch_live()`.

### 3.1 Parameter Table

| Parameter | Key | Type | Range | Default | What It Controls |
|-----------|-----|------|-------|---------|-----------------|
| Style | `spiral_style` | string | See §2.1 | `tunnel_dream` | Which mathematical form is rendered |
| Speed | `spiral_speed` | float | 0.0–2.0 | 1.0 | Animation rate. 0 = frozen. 2 = fast. |
| Chaos | `spiral_chaos` | float | 0.0–1.0 | 0.15 | Domain warping / organic distortion. Low = clean math. High = organic. Style-dependent effect. |
| Tightness | `spiral_tightness` | float | 1.0–10.0 | 5.0 | Spiral arm density. Low = wide spacing. High = dense coils. |
| Count | `spiral_count` | int | 1–8 | 3 | Number of spiral arms or repeated elements. |
| Thickness | `spiral_thickness` | float | 4.0–30.0 | 14.0 | Arm width in pixels (scaled to resolution). |
| Opacity | `spiral_opacity` | float | 0.0–1.0 | 0.85 | Overall spiral visibility. Controls entrainment capture range (Arnold tongue). |
| Feedback Mode | `spiral_feedback_mode` | string | See §4 | `alpha_decay` | How previous frames persist into current frame. |
| Bloom | `bloom_intensity` | float | 0.0–1.0 | 0.0 | Glow around bright elements. Simulates phosphene perception at high values. |
| Color Temp Bias | `color_temperature_bias` | float | -1.0–1.0 | 0.0 | Shifts palette warm (positive) or cool (negative). Derived from Rosé Pine Moon palette. |
| Chromatic Aberration | `chromatic_aberration` | float | 0.0–1.0 | 0.0 | RGB channel separation at edges. Prevents analytical visual processing. |
| Film Grain | `film_grain` | float | 0.0–1.0 | 0.0 | Organic noise overlay. Breaks up digital precision. |
| Vignette | `vignette_intensity` | float | 0.0–1.0 | 0.3 | Edge darkening. Narrows attentional focus to center. |
| Entrainment Strength | `visual_entrainment_strength` | float | 0.0–1.0 | 0.5 | How strongly the visual flickers at the entrainment frequency. 0 = no flicker. 1 = full on/off. |

### 3.2 Parameter Interaction Rules

- **Speed and entrainment are independent.** `spiral_speed` controls pattern animation (rotation, expansion). `visual_entrainment_strength` controls brightness flicker at the target frequency. They operate on different visual channels.
- **Chaos has style-dependent meaning.** On `liminal`: morphs between FC-II spiral and FC-III lattice. On `flow_field`: turbulence intensity. On `tunnel_dream`: spoke distortion. On styles without explicit chaos support: subtle domain warp applied universally.
- **Opacity controls entrainment capture range.** Per Arnold tongue dynamics (Notbohm et al. 2016): higher opacity = wider frequency range that achieves neural phase-lock. During INDUCTION when entrainment lock is critical, keep opacity ≥ 0.7. During MAINTENANCE when lock is established, opacity can drop for comfort.
- **Bloom simulates phosphenes.** At bloom_intensity > 0.5, bright spiral elements bleed into surrounding space in a way that mimics closed-eye phosphene perception. This is useful during deep theta where the visual should feel internal, not external.
- **Chromatic aberration prevents analytical processing.** The RGB split makes edges impossible to fixate on precisely, which discourages the left-hemisphere pattern analysis that fights entrainment. Use sparingly (0.1–0.3) — too much causes nausea.

---

## 4. Feedback Modes

The feedback system controls how previous frames persist into the current frame. This is the single most powerful visual parameter for creating depth and absorption. Each mode transforms simple mathematical forms into living visual fields.

### 4.1 Mode Table

| Mode | Key Value | Visual Effect | Best For |
|------|-----------|--------------|----------|
| `alpha_decay` | `"alpha_decay"` | Simple fade. Previous frames dim uniformly. | Default. Clean, predictable. All session types. |
| `directional_blur` | `"directional_blur"` | Motion trails along spiral arm direction. | Deep trance. Creates sense of flow and movement. |
| `radial_zoom` | `"radial_zoom"` | Tunnel zoom feedback — previous frames expand outward. | Tunnel styles (`tunnel_dream`, `vortex`, `recursive_fractal`). Amplifies forward motion. |
| `rotational_smear` | `"rotational_smear"` | Angular persistence — rotation leaves arc trails. | Rotational styles (`galaxy_arms`, `bloom`, `moire`). Creates continuous motion field. |
| `reaction_diffusion` | `"reaction_diffusion"` | Gray-Scott reaction-diffusion on the feedback buffer. Previous frames evolve organically. | `liminal`, `cobwebs`, `flow_field`. Organic emergence — patterns grow, split, decay. |
| `kaleidoscopic_fold` | `"kaleidoscopic_fold"` | Angular folding applied to feedback — creates recursive symmetry from any style. | `kaleidoscope`, `sacred_geometry`. Meditative depth through symmetry. |

### 4.2 Feedback Mode Selection Rules

1. **Default to `alpha_decay`** unless there's a specific reason to use another mode. It's predictable and works with every style.
2. **Match feedback to style geometry.** `radial_zoom` with tunnel styles. `rotational_smear` with rotational styles. `reaction_diffusion` with organic styles. Mismatched feedback creates visual incoherence.
3. **Feedback mode is a chord parameter.** When the somatic palette evaluates chords, the feedback mode is part of the chord fingerprint. Different users respond differently to different feedback modes — the palette learns this over time.
4. **Never switch feedback modes mid-phase.** The visual transition is jarring and breaks absorption. Switch only at fractionation boundaries or keyframe transitions with a brief (2–3 second) crossfade via opacity dip.
5. **`reaction_diffusion` is the most powerful and most dangerous mode.** At high feedback gain, patterns grow autonomously and can become overwhelming. Start with low feedback gain (0.3–0.4) and let the palette calibrate.
6. **Sleep sessions: `alpha_decay` only.** Other modes maintain visual complexity that fights sleep onset. The visual should fade to nothing, not evolve.

---

## 5. Phase-by-Phase Visual Authoring

This section maps the five-phase session arc (from session_design.md) to visual parameter progressions.

### 5.1 Phase 1 — Orient (0–15%)

**Goal:** Establish visual anchor. Clean, familiar, non-threatening.

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| Style | Session default (typically `tunnel_dream` or `galaxy_arms`) | Familiarity. Don't surprise. |
| Speed | 0.8–1.0 | Medium animation. Not sluggish, not rushed. |
| Chaos | 0.05–0.15 | Clean mathematical form. No distortion. |
| Opacity | 0.7–0.85 | High enough for entrainment capture (Arnold tongue). |
| Feedback | `alpha_decay` | Simple, predictable persistence. |
| Bloom | 0.0–0.1 | Minimal. Sharp edges feel awake and present. |
| Color temp | 0.0 (neutral) | No bias. Default Rosé Pine Moon Iris. |
| Entrainment | 0.3–0.5 | Gentle flicker at IAF. Not aggressive. |
| Vignette | 0.2–0.3 | Light framing. Don't close in yet. |

### 5.2 Phase 2 — Descent (15–40%)

**Goal:** Progressive deepening. Visual becomes softer, slower, warmer.

| Parameter | Progression | Reasoning |
|-----------|------------|-----------|
| Speed | 1.0 → 0.6 | Gradual deceleration. Step-ramp, not smooth slide. |
| Chaos | 0.15 → 0.30 | Forms begin to breathe. Math dissolves into organic. |
| Opacity | 0.85 → 0.75 | Slight reduction. Entrainment lock is establishing. |
| Bloom | 0.1 → 0.3 | Edges soften. Visual shifts from external screen to internal field. |
| Color temp | 0.0 → +0.2 | Subtle warm shift. Theta is warm. |
| Entrainment | 0.5 → 0.6 | Slightly stronger as target frequency drops toward theta. |
| Vignette | 0.3 → 0.4 | Peripheral darkening increases. Attentional funnel narrows. |

**Style transition:** If the session plan calls for a style change (e.g., `tunnel_dream` → `liminal`), the Descent-to-Work boundary is the best transition point. Use a 3–5 second opacity dip to 0.3 during the switch.

### 5.3 Phase 3 — Work (40–75%)

**Goal:** Hold depth. Visual supports sustained theta. Content delivery is active — visual must not compete.

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| Speed | 0.4–0.7 | Slow, steady. Theta rhythm. |
| Chaos | 0.25–0.50 | Style-dependent. Organic enough to prevent analytical fixation. |
| Opacity | 0.65–0.80 | Moderate. Entrainment is established; don't overwhelm. |
| Feedback | Style-appropriate (see §4.2) | This is where feedback mode matters most. |
| Bloom | 0.3–0.5 | Significant softening. Phosphene territory. |
| Color temp | +0.1–+0.3 | Warm. Deep theta feels warm. |
| Entrainment | 0.5–0.7 | Moderate-strong. Maintaining theta lock. |
| Vignette | 0.4–0.5 | Strong peripheral darkening. Tunnel vision. |
| Chromatic aberration | 0.05–0.15 | Very subtle. Just enough to prevent edge fixation. |
| Film grain | 0.05–0.10 | Subtle organic texture. Breaks digital precision. |

**Visual must not compete with content.** During Work phase, TTS phrases, center flash, veil text, and language items are all being delivered. The visual is a sustaining field, not the focus. If the user's trance_score drops when content is delivered, the visual may be too attention-demanding — reduce speed and opacity.

**Somatic palette chord:** During Work phase, the palette is evaluating chords. The spiral style + feedback mode + chaos level are chord parameters. The agent should not adjust these independently of the palette during active chord evaluation windows (12–15 minutes per chord). Adjustments outside chord parameters (bloom, grain, vignette) are fine.

### 5.4 Phase 4 — Soak (75–85%)

**Goal:** Deepest point. No new content. Visual at its most absorbing.

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| Speed | 0.3–0.5 | Very slow. Near-stillness. |
| Chaos | 0.40–0.60 | High organic. Forms breathe and shift. |
| Opacity | 0.60–0.75 | Moderate. The visual is a presence, not a demand. |
| Bloom | 0.4–0.6 | Heavy softening. The screen should feel like closed-eye phosphenes. |
| Color temp | +0.2–+0.4 | Warm. Deepest = warmest. |
| Entrainment | 0.4–0.6 | Moderate. Lock is deep; reduce intensity to prevent overstimulation. |
| Vignette | 0.5–0.6 | Strong. Almost a portal. |
| Film grain | 0.10–0.15 | Present. Organic warmth. |

**Soak means no visual changes.** Ramp parameters into Soak range during late Work phase and hold them. No parameter adjustments during Soak unless responding to EEG signals (depth drop, SQI failure).

**Exception:** Reconsolidation LOCKOUT phase may overlap with Soak. Visual parameters hold steady — the lockout is a content restriction, not a visual change.

### 5.5 Phase 5 — Return (85–100%)

**Goal:** Ascent. Visual becomes cleaner, cooler, brighter. Re-engage external awareness.

| Parameter | Progression | Reasoning |
|-----------|------------|-----------|
| Speed | 0.5 → 0.8 | Gradual acceleration. Waking rhythm. |
| Chaos | 0.40 → 0.10 | Return to clean mathematical form. Order = waking. |
| Opacity | 0.70 → 0.85 | Brighten. External world reasserting. |
| Bloom | 0.5 → 0.1 | Sharpen edges. Screen feels like a screen again. |
| Color temp | +0.3 → 0.0 | Cool toward neutral. Theta warmth dissipates. |
| Entrainment | 0.5 → 0.3 → 0.0 | Reduce to zero. Release entrainment lock. |
| Vignette | 0.5 → 0.2 | Open peripheral field. Widen attention. |
| Chromatic aberration | → 0.0 | Remove entirely. Sharp, clear vision. |
| Film grain | → 0.0 | Remove entirely. Clean, digital, awake. |

**Style transition:** If the session used `liminal`, `flow_field`, or another organic style during Work/Soak, snap back to `tunnel_dream` or `archimedean` early in Return. Clean geometry = waking cognition.

**Do NOT skip Return.** Cutting from Soak-depth visuals to a blank screen is visually jarring and can cause disorientation. The visual Return should take at least 3–5 minutes.

---

## 6. Sleep Session Visual Arc

Sleep sessions diverge from trance sessions at Phase 3. The visual tapers to black instead of holding.

| Time | Visual State | Key Difference from Trance |
|------|-------------|---------------------------|
| 0:00–5:00 | Orient. Same as trance Phase 1. | Identical. |
| 5:00–10:00 | Descent. Slower speed, warmer color. | Slightly faster parameter descent than trance. |
| 10:00–15:00 | **Taper begins.** Opacity 0.6 → 0.3. Speed 0.5 → 0.2. Bloom 0.3 → 0.5. | Trance would hold. Sleep tapers. |
| 15:00–20:00 | **Near-dark.** Opacity 0.1–0.2. Speed 0.1. Maximum bloom (0.6+). | Visual is a faint warm glow, not a pattern. |
| 20:00+ | **Black.** Opacity 0.0. Renderer idle. | Entrainment stimulation is done. TMR and sleep bursts take over (audio only). |

**Feedback mode:** `alpha_decay` only for sleep sessions. No other feedback mode — complexity fights sleep onset.

**Style:** `tunnel_dream`, `fibonacci`, or `bloom` only. Gentle, slow, warm. No `electric`, no `strange_attractor`, no `cobwebs`.

**Do NOT resume visuals after taper.** Once opacity hits 0.0, the visual layer is done for the session. TMR cues and sleep burst engine operate in audio only during N2+ and N3.

---

## 7. EEG-Reactive Visual Mappings

When `eeg_visual_feedback` is enabled in `live_control.json`, the following EEG signals modulate visual parameters in real time. All mappings use exponential moving average smoothing (τ = 3 seconds) to prevent visual jitter.

| EEG Signal | Visual Target | Mapping | Direction | Notes |
|------------|--------------|---------|-----------|-------|
| `trance_score` | `bloom_intensity` | 0.0–0.8 trance → 0.0–0.6 bloom | Deeper = more bloom | Deeper trance = more phosphene-like visual |
| `trance_score` | Feedback trail length | 0.0–0.8 trance → 0.3–0.9 feedback gain | Deeper = longer trails | Deeper trance = more visual persistence |
| `faa_value` | `color_temperature_bias` | FAA -0.3–+0.3 → temp -0.2–+0.3 | Approach = warmer | Positive FAA (approach) = warm palette |
| `eeg_alpha` | `spiral_opacity` | Relative to baseline | Higher alpha = slightly higher opacity | Reinforces alpha entrainment during INDUCTION |
| `eeg_theta` | `spiral_chaos` | Relative to baseline | Higher theta = more chaos | Organic distortion mirrors theta-dominant internal state |
| `eeg_beta` | Domain warp frequency | Relative to baseline | Higher beta = faster warp | Reflects cognitive activation — visual mirrors mental busyness |
| `pac_encoding_quality` | Pattern complexity | 0.0–0.4 PAC → style complexity | Higher PAC = allow more complex visuals | Good encoding state can handle visual complexity without disruption |
| `eeg_quality` (SQI) | `vignette_intensity` | Inverted | Poor signal = stronger vignette | Subtle visual cue that something is wrong with contact |

### 7.1 Safety Rules for EEG-Reactive Mapping

1. **EEG mappings are modulations, not overrides.** They adjust the session.yaml baseline within a bounded range. They never replace the agent's phase-appropriate parameter settings.
2. **Smoothing is mandatory.** τ = 3 seconds minimum. Raw EEG-to-visual mapping causes epileptogenic flickering and user distress.
3. **Disable during CALIBRATION.** The first 10 sessions need stable visual parameters to establish EEG baselines. EEG-reactive visuals during calibration create a feedback loop that contaminates the baselines.
4. **Disable during sleep sessions.** Visual is tapering to black. EEG-reactive increases in opacity or complexity fight sleep onset.
5. **Conductor-owned parameters take precedence.** If the Conductor owns `visual_entrainment_strength` during GENUS or INDUCTION, EEG-reactive mappings do not modify it.

---

## 8. Spiral Parameters as Chord Components

The somatic palette evaluates cross-modal configurations (chords) during MAINTENANCE. The following visual parameters are part of the chord fingerprint:

| Chord Parameter | Source | Notes |
|-----------------|--------|-------|
| `spiral_style` | Session.yaml default or palette override | Core identity of the chord's visual component |
| `spiral_chaos` | Session.yaml or palette override | How organic the visual field is |
| `spiral_speed` | Session.yaml or palette override | Animation rhythm |
| `spiral_feedback_mode` | Session.yaml or palette override | Temporal persistence mode |
| `bloom_intensity` | Session.yaml or palette override | Phosphene simulation level |
| `color_temperature_bias` | Session.yaml or palette override | Warm/cool palette shift |

### 8.1 What This Means for the Agent

- **During active chord evaluation (12–15 min window):** Do not adjust chord parameters independently. The palette is measuring the user's response to this specific configuration. Changing the visual mid-evaluation invalidates the measurement.
- **Between chord evaluations (3-min cooldown after fractionation re-entry):** The agent can adjust chord parameters to set up the next chord.
- **Non-chord visual parameters** (`vignette_intensity`, `film_grain`, `chromatic_aberration`) are NOT part of the chord. The agent can adjust these freely at any time for comfort or phase-appropriate atmosphere.

### 8.2 Palette Cold Start — Visual Preferences

During the first 5 sessions (< 5 palette entries), the agent should present a range of visual styles across chord evaluations:
- Session 1–2: `tunnel_dream` and `galaxy_arms` (safe, familiar FC-I and FC-II)
- Session 3: `liminal` (introduce FC-III via chaos ramp)
- Session 4: `fibonacci` or `bloom` (organic FC-II variants)
- Session 5: `flow_field` or `cobwebs` (introduce newer styles)

This builds a visual preference profile alongside the overall chord preference profile. Some users respond strongly to specific styles — the palette discovers this through chord evaluation.

---

## 9. GENUS Session Visual Requirements

GENUS (Gamma ENtrainment Using Sensory stimulation) sessions use 40Hz visual flicker for gamma entrainment. The visual requirements are distinct from trance sessions.

| Parameter | GENUS Value | Reasoning |
|-----------|------------|-----------|
| Style | `sacred_geometry`, `kaleidoscope`, or `interference` | Need discrete visual elements for per-element flicker. Continuous styles can't do isochronic 40Hz. |
| Entrainment strength | 0.7–1.0 | Strong flicker. Gamma entrainment requires higher amplitude than alpha/theta. |
| Speed | 1.0–1.2 | Normal to slightly elevated. GENUS is not a deepening protocol. |
| Chaos | 0.05–0.15 | Clean, precise geometry. Gamma entrainment needs sharp edges. |
| Feedback | `alpha_decay` | Short trail. Feedback would smear the 40Hz temporal precision. |
| Bloom | 0.0–0.1 | Minimal. Sharp edges needed for flicker precision. |
| Opacity | 0.8–1.0 | High. Maximum entrainment capture range. |

**No subliminal content during GENUS.** Veil text is disabled. The visual is purely for gamma entrainment, not content delivery.

**`sacred_geometry` tile flicker:** Each tile in the tessellation can flicker independently at 40Hz with phase offsets. This creates a spatially distributed 40Hz stimulus that drives gamma entrainment more effectively than whole-field flicker.

---

## 10. Visual Safety Constraints

### 10.1 Photosensitive Epilepsy Prevention

- **Flicker rate:** Visual entrainment strength must be 0.0 when the entrainment frequency is in the 15–25Hz danger band. This is enforced by the render pipeline, but the agent should also not author session.yaml keyframes that set high entrainment strength at these frequencies.
- **Contrast transitions:** Never hard-cut from dark to full brightness. All opacity transitions ≥ 0.3 magnitude must take at least 1 second.
- **Red flicker:** The Rosé Pine Moon palette avoids saturated red. Do not override base color to pure red — red flicker is the highest epilepsy risk.

### 10.2 Nausea and Disorientation Prevention

- **Chromatic aberration:** Cap at 0.3. Above this, peripheral vision distortion causes motion sickness in some users.
- **`radial_zoom` feedback:** Cap feedback gain at 0.7. High gain creates an accelerating tunnel rush effect that can cause vestibular discomfort.
- **`reaction_diffusion` feedback:** Cap feedback gain at 0.6. High gain causes autonomous pattern growth that can become visually overwhelming and anxiety-inducing.
- **Rotational speed:** `spiral_speed` above 1.5 with `rotational_smear` feedback can cause persistent motion aftereffect (MAE) that lasts minutes after session end. This is acceptable for trance purposes but should not appear in sleep sessions.

### 10.3 Return Phase Safety

- Entrainment strength must reach 0.0 before session ends. Residual entrainment flicker after session end is disorienting.
- Bloom and grain must reach 0.0 by session end. Lingering post-processing effects make the UI feel broken.
- Chromatic aberration must reach 0.0 by session end.

---

## 11. Common Mistakes

### 11.1 Style Switching During Chord Evaluation

**Wrong:** Agent detects declining trance_score during a palette chord evaluation and switches spiral style.
**Why it's wrong:** The style is a chord parameter. Changing it mid-evaluation invalidates the palette measurement. The trance_score decline might be unrelated to the visual.
**Right:** Let the chord evaluation complete. If the chord fails (trance_score never exceeds 0.40 after 8 minutes), request fractionation. The next chord after re-entry uses the new style.

### 11.2 Maximum Bloom + Maximum Entrainment

**Wrong:** Setting bloom_intensity 0.8 + visual_entrainment_strength 0.9 simultaneously.
**Why it's wrong:** Bloom softens edges, which smears the temporal precision of the entrainment flicker. The two effects work against each other. High bloom = gentle phosphene feel. High entrainment = sharp periodic flicker. Pick one.
**Right:** During INDUCTION (entrainment lock is critical): high entrainment, low bloom. During deep MAINTENANCE (lock is established): reduce entrainment, increase bloom.

### 11.3 Complex Style for Sleep

**Wrong:** Selecting `strange_attractor` or `liminal` (high chaos) for a sleep onset session.
**Why it's wrong:** Complex, unpredictable visual patterns engage curiosity and analytical processing — both are arousing. Sleep onset needs boring, predictable, gentle patterns.
**Right:** `tunnel_dream`, `fibonacci`, or `bloom` at low chaos. Let the user fall asleep to a warm, slow, fading spiral.

### 11.4 Skipping the Opacity Dip on Style Switch

**Wrong:** Hard-cutting `spiral_style` from one style to another without an opacity transition.
**Why it's wrong:** Abrupt style changes create a visual discontinuity that triggers orienting response — the exact opposite of trance maintenance.
**Right:** Dip opacity to 0.2–0.3 over 2 seconds, switch style, ramp opacity back up over 2 seconds. Total transition: ~5 seconds.

### 11.5 EEG-Reactive During Calibration

**Wrong:** Enabling `eeg_visual_feedback` during the first 10 calibration sessions.
**Why it's wrong:** EEG-reactive visuals create a feedback loop. The visual changes because of EEG → the EEG changes because of the visual → the baseline is contaminated. Calibration requires stable visual parameters to isolate neurophysiological baselines.
**Right:** Disable `eeg_visual_feedback` entirely during calibration. Enable after session 10 when personal baselines are established.

### 11.6 Feedback Mode Mismatch

**Wrong:** Using `radial_zoom` feedback with `bloom` (polar rose) style.
**Why it's wrong:** `radial_zoom` creates outward expansion trails. `bloom` rotates inward with petal layers. The feedback direction contradicts the style's natural motion, creating visual incoherence.
**Right:** Match feedback mode to style geometry. `rotational_smear` for rotational styles. `radial_zoom` for tunnel styles. `reaction_diffusion` for organic styles. See §4.2.

### 11.7 Forgetting the Aphantasia Constraint

**Wrong:** Agent selects a style and narrates it verbally: "The spiral is shifting into a flowing river of light."
**Why it's wrong:** The user has extreme aphantasia. Describing what the visual "looks like" or "feels like" using imagery language is useless and annoying. The visual IS the experience — it doesn't need narration.
**Right:** Adjust visual parameters silently. The user sees the result directly. If the agent needs to reference the visual in a prompt, use functional language: "Let it carry you" not "See the light pulling you deeper."

---

## 12. Do Not

1. **Do not use `_patch_live()`.** Deprecated. Use `from ipc import patch_live`.
2. **Do not write `live_control.json` directly.** Always go through `patch_live()`.
3. **Do not switch styles during chord evaluation windows.** Style is a chord parameter. See §8.1 and §11.1.
4. **Do not switch feedback modes mid-phase.** Use opacity dip transitions at phase boundaries only. See §4.2.
5. **Do not set entrainment strength > 0 in the 15–25Hz frequency band.** Photosensitive epilepsy risk. See §10.1.
6. **Do not enable EEG-reactive visual mappings during calibration sessions (1–10).** Feedback loops contaminate baselines. See §7.1 and §11.5.
7. **Do not use any spiral style not in the §2.1 table.** If a style name is not listed, it does not exist.
8. **Do not use visualization narration.** The user has extreme aphantasia. See §11.7.
9. **Do not resume visuals after sleep taper.** Once opacity hits 0.0 in a sleep session, the visual layer is done. See §6.
10. **Do not hard-cut opacity changes ≥ 0.3 magnitude.** Minimum 1-second transition. See §10.1.
11. **Do not use `ease: step` for visual parameter keyframes.** Use `ease: instant` when a discrete jump is needed. `step` is not a valid ease type.
12. **Do not combine maximum bloom with maximum entrainment strength.** They work against each other. See §11.2.
