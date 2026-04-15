# Somna Doc 47 — Visual & Audio Enhancement Architecture

**Ganzfeld Background Layer, Post-Processing Shader Pipeline, Spatial Audio Engine**

**Status:** Specification — ready for implementation

**Version:** 1.0 | **Date:** 2026-04-05 | **Author:** Ed

**Depends on:** Doc 35 (DeliveryGate), Doc 37 (gain manifold), Doc 42 (PPG breath phase, cardiac phase), Doc 43 (conditioning), Doc 44 (IAF, fractal edge modulation, MAE cycles), Doc 45 (habituation/novelty engine)

# 1  Overview

This document specifies three new subsystems and a GLSL post-processing shader pipeline that exploit well-evidenced perceptual phenomena to deepen trance, accelerate sleep onset, and enhance crossmodal integration across Somna's existing architecture. Every technique described here has published neural or perceptual evidence supporting its efficacy.

### New Modules

| **Module** | **Description** |
| --- | --- |
| background_layer.py | Ganzfeld-like perceptual deprivation field, color temperature management, radial looming/receding pulse |
| --- | --- |
| spatial_audio.py | Stereo spatial panning, ASMR-adjacent textures, looming audio synchronization, Shepard tone generator |
| --- | --- |
| visual_display.py (extension) | Post-processing shader pipeline — 6 new GLSL fragment shader passes |
| --- | --- |

### Design Principles

1.  All new visual effects feed through Doc 37's gain manifold via a new visual_enhancement gain channel.
2.  All new audio effects feed through Doc 37's gain manifold via a new spatial_audio gain channel.
3.  All depth-modulated parameters read trance_score_v2 from live_control.json.
4.  Respiratory coupling reads ppg_breath_phase from live_control.json (Doc 42 / ppg_engine.py).
5.  Habituation tracking integrates with Doc 45's novelty engine — each new stimulus type registers as a trackable stimulus.
6.  Conditioning integration via Doc 43 — progressive perceptual shifts (blur, chromatic aberration, vignette) become conditioned stimuli for depth state.

# 2  Background Layer Engine — background_layer.py

## 2.1  Module Architecture

Create a new class BackgroundLayer instantiated by visual_display.py during initialization. Renders a fullscreen quad **behind** the spiral layer (depth test: background at z=0.0, spiral at z=0.1). Uses a dedicated ModernGL program with its own vertex/fragment shader pair.

class BackgroundLayer: """ Fullscreen background field combining Ganzfeld-like uniform color, color temperature management, and radial looming gradient. Instantiated once in VisualDisplay.\__init_\_(). Called every frame in VisualDisplay.render() BEFORE spiral rendering. Reads from live_control.json: ppg_breath_phase (float 0.0-1.0) — from ppg_engine via Doc 42 trance_score_v2 (float 0.0-1.0) — from eeg_engine via Doc 38 conductor_phase (str) — current FSM phase bg_ganzfeld_gain (float 0.0-1.0) — gain manifold output bg_looming_gain (float 0.0-1.0) — gain manifold output bg_color_temp_k (int) — current color temperature target Writes to live_control.json: bg_looming_phase (float 0.0-1.0) — current looming expansion phase (read by spatial_audio for multisensory synchronization) """ def \__init_\_(self, ctx: moderngl.Context) -> None: ... def update(self, dt: float, live: dict) -> None: ... def render(self) -> None: ...

## 2.2  Ganzfeld Breathing Field

**Scientific basis:** Pistolas et al. 2025 (_Open Mind_, MIT Press) demonstrated that Ganzfeld conditions induce altered states of consciousness including bodily effects, with increased theta preceding perceptual decays and increased alpha during decays. Shenyan et al. 2024 (_Nature Scientific Reports_) showed Ganzfeld and Ganzflicker share a common visual cortex excitability mechanism. A monitor cannot replicate a true Ganzfeld sphere, but a uniform color field filling the entire screen behind the spiral approximates the critical property: spatially uniform, low-information visual input that promotes perceptual deprivation in the periphery.

### Implementation

The background renders as a uniform color field. No texture, no pattern, no gradient (except the radial looming component specified in §2.4). The color is specified in HSV space for intuitive parameter control.

**Base color (HSV):**

- Hue: 25° (warm amber)
- Saturation: 0.25 (desaturated — avoids strong chromatic stimulation)
- Value (brightness): 0.45 (moderate — not so bright as to prevent sleep approach)

**Respiratory brightness modulation:**

- The Value component modulates sinusoidally with ppg_breath_phase.
- Modulation amplitude: ±12% of base Value (i.e., V oscillates between 0.396 and 0.504 at base).
- Phase mapping: V_mod = base_V \* (1.0 + amplitude \* sin(2π \* ppg_breath_phase + π)) — this places brightness **peak** at exhale midpoint (phase ≈ 0.75) and brightness **nadir** at inhale midpoint (phase ≈ 0.25). Exhale = parasympathetic dominance = warm glow increase.
- When ppg_available is False: fall back to synthetic breath clock at 0.2 Hz (12 breaths/min default), read from respiratory_rate_hz in live_control.json.

**Respiratory coupling evidence:** Tort et al. 2025 (_Nature Reviews Neuroscience_) comprehensively reviewed how breathing rhythm globally coordinates brain activity — nasal airflow evokes waves of sensory activity that synchronize neuronal populations to the breathing cycle. Stetza et al. 2025 (_Journal of Neuroscience_) showed respiratory phase directly modulates task-related neural representations of visual stimuli, with respiratory phase influencing sensory evidence ~200–300ms prior to behavioral responses. Coupling visual luminance to breath phase exploits this endogenous neural rhythm.

**Gain integration:** Final Ganzfeld modulation amplitude is scaled by bg_ganzfeld_gain from the gain manifold (Doc 37). When gain = 0, background is static at base color.

## 2.3  Color Temperature Gradient Descent

**Scientific basis:** Blume et al. 2024 (_Nature Human Behaviour_) demonstrated that melanopsin (ipRGC) drive is the primary mechanism for circadian light effects, not cone-mediated color pathways. Warm light (lower correlated color temperature, CCT) reduces melanopic equivalent daylight illuminance (melanopic EDI), promoting melatonin onset. The background layer implements a session-long imperceptible color temperature descent that tracks the user's progression from alert engagement toward sleep.

### Implementation

Color temperature is specified in Kelvin and converted to RGB using the Planckian locus approximation (Tanner Helland algorithm or equivalent lookup table). The conversion maps CCT → (R, G, B) normalized floats which multiply the Ganzfeld base color.

**Phase-locked CCT targets:**

| **Conductor Phase** | **Target CCT (K)** | **Transition Rate** | **Rationale** |
| --- | --- | --- | --- |
| CALIBRATION | 4500 | Instant | Neutral warm — baseline measurement |
| --- | --- | --- | --- |
| INDUCTION | 3800 | 50 K per 5 min | Gentle warmth — session onset |
| --- | --- | --- | --- |
| DEEPENING | 3200 | 50 K per 5 min | Warm amber — relaxation promotion |
| --- | --- | --- | --- |
| MAINTENANCE | 2700 | 50 K per 5 min | Incandescent warmth — deep trance |
| --- | --- | --- | --- |
| SLEEP_APPROACH | 2200 | 80 K per 5 min | Deep amber — melatonin-permissive |
| --- | --- | --- | --- |
| SLEEP_ONSET | 1800 | 100 K per 5 min | Candlelight — minimal melanopic EDI |
| --- | --- | --- | --- |
| SLEEP_MAINTAIN | 1800 | Hold | Maintained — screen fading to black |
| --- | --- | --- | --- |
| SLEEP_TRAINING | 1800 | Hold | Maintained |
| --- | --- | --- | --- |
| SLEEP_WAKE | 3200 | 200 K per min | Rapid warm-up — gentle arousal |
| --- | --- | --- | --- |

The transition is implemented as exponential smoothing toward the target: current_cct += (target_cct - current_cct) \* alpha \* dt, where alpha is derived from the transition rate. The change must be imperceptible — the user should never notice the shift occurring.

## 2.4  Radial Looming / Receding Pulse

**Scientific basis:** Cappe et al. 2012 (_Journal of Neuroscience_) demonstrated that looming signals reveal synergistic principles of multisensory integration, with nonlinear audio-visual interactions at ~75ms post-stimulus onset. Neural loci included right claustrum/insula extending into amygdala, plus bilateral cuneus. Looming signals receive preferential perceptual treatment — they activate threat/attention circuits even at low intensity. In the trance context, slow, gentle looming creates a sense of environmental approach/recession that deepens immersion without triggering alarm (intensity must stay well below startle threshold).

### Implementation

A radial gradient is composited over the uniform Ganzfeld field. Center = slightly brighter (+8% Value), edges = slightly darker (−8% Value). The gradient center radius expands and contracts with respiratory phase, creating a slow "breathing" expansion/contraction of the light field.

**Parameters:**

- **Gradient function:** brightness_offset = amplitude \* exp(-r² / (2 \* sigma²)) where r is normalized distance from screen center (0.0 = center, 1.0 = corner)
- **sigma (gradient spread):** 0.6 (covers ~60% of screen at half-amplitude)
- **Expansion/contraction:** sigma modulates ±15% with ppg_breath_phase
- **Phase mapping:** exhale = expansion (sigma increases, light spreads outward = loom toward viewer); inhale = contraction (sigma decreases, light concentrates = recede from viewer)
- **Looming phase output:** write bg_looming_phase to live_control.json for audio synchronization (§4.4)
- **Temporal offset:** visual looming **leads** audio looming by 75ms (Cappe 2012 optimal binding window). Achieved by the audio engine reading bg_looming_phase with a 75ms delay buffer.

**Gain integration:** Looming amplitude scaled by bg_looming_gain from gain manifold. When gain = 0, background is flat uniform color (no radial gradient).

## 2.5  Troxler Fading Exploitation

**Scientific basis:** The Troxler effect causes unchanging peripheral stimuli to fade and disappear when a viewer fixates on a central point. Neural adaptation in peripheral retinal fields reduces signal transmission. The effect is enhanced when peripheral stimuli are low-contrast, blurred, or far from fixation. Microsaccades counteract fading; decreased microsaccade rate precedes fading episodes.

**Design strategy:** The spiral serves as the central fixation target. The Ganzfeld background is deliberately designed to **maximize** Troxler fading:

- Uniform color (no spatial features to anchor peripheral attention)
- Low contrast relative to spiral
- Progressive blur applied to background only (§3.1)
- Vignette darkens periphery (§3.3), accelerating peripheral adaptation

**Result:** Over 30–60 seconds of fixation, the background perceptually disappears. The spiral becomes the only perceived stimulus — a natural tunnel-vision effect that mirrors hypnotic attentional narrowing. This effect deepens over time without any instruction or effort from the user.

**Troxler reset mechanism:** When Doc 45's novelty engine signals that the GANZFELD stimulus has reached a dishabituation trigger threshold, a brief Troxler-breaking event fires:

- Spiral position micro-jitter: <1px displacement for 100ms (triggers microsaccade)
- Background contrast briefly increases by 20% for 200ms then fades back over 1s
- The fade-return-fade cycle is itself a deepening technique — the act of peripheral content vanishing again reinforces the tunnel-vision experience
- Register GANZFELD_TROXLER as a stimulus in Doc 45's habituation tracker with micro timescale = 45s, meso timescale = 300s

# 3  Post-Processing Shader Pipeline

All post-processing effects are implemented as fragment shader passes applied **after** scene compositing (background + spiral + text layers). The pipeline runs in this fixed order:

| **Pass** | **Operation** | **Output** |
| --- | --- | --- |
| 1   | Scene composite (background behind spiral behind text) | FBO_scene |
| --- | --- | --- |
| 2   | Gaussian blur (background region only, via stencil or separate FBO) | FBO_blur |
| --- | --- | --- |
| 3   | Re-composite (blurred background + sharp spiral/text) | FBO_composite |
| --- | --- | --- |
| 4   | Chromatic aberration pass | FBO_ca |
| --- | --- | --- |
| 5   | Bloom extraction + blur + composite | FBO_bloom |
| --- | --- | --- |
| 6   | Vignette pass | FBO_vig |
| --- | --- | --- |
| 7   | IAF luminance modulation | Final output |
| --- | --- | --- |

Each pass uses a fullscreen quad with a dedicated fragment shader. All parameters are uploaded as uniforms updated per frame from live_control.json values.

## 3.1  Progressive Gaussian Blur

**Scientific basis:** Cholewiak et al. 2019 (_Journal of Vision / ARVO_) demonstrated that real-time blur with longitudinal chromatic aberration drives accommodation changes and depth perception as effectively as real optical distance changes. Progressive blur simulates accommodation relaxation — the eyes releasing focal effort as trance deepens. Applied **only** to the background layer; the spiral remains sharp as the fixation anchor.

**Implementation:** Two-pass separable Gaussian blur (horizontal then vertical).

**GLSL fragment shader (single pass direction):**

#version 330 core uniform sampler2D u_texture; uniform vec2 u_direction; // (1.0/width, 0) or (0, 1.0/height) uniform float u_blur_radius; // pixels, from live_control uniform vec2 u_texel_size; // 1.0 / resolution in vec2 v_uv; out vec4 frag_color; void main() { float weights\[5\] = float\[\](0.227027, 0.194596, 0.121622, 0.054054, 0.016216); vec3 result = texture(u_texture, v_uv).rgb \* weights\[0\]; for (int i = 1; i < 5; i++) { vec2 offset = u_direction \* u_blur_radius \* float(i); result += texture(u_texture, v_uv + offset).rgb \* weights\[i\]; result += texture(u_texture, v_uv - offset).rgb \* weights\[i\]; } frag_color = vec4(result, 1.0); }

**Depth-modulated blur radius:**

| **Conductor Phase** | **Blur Radius (px)** | **Transition** |
| --- | --- | --- |
| CALIBRATION | 0.0 | Instant |
| --- | --- | --- |
| INDUCTION | 0.5 | Linear ramp over phase duration |
| --- | --- | --- |
| DEEPENING | 2.0 | Linear ramp |
| --- | --- | --- |
| MAINTENANCE | 4.0 | Linear ramp |
| --- | --- | --- |
| SLEEP_APPROACH | 6.0 | Linear ramp |
| --- | --- | --- |
| SLEEP_ONSET | 8.0 | Linear ramp (screen fading) |
| --- | --- | --- |
| SLEEP_MAINTAIN | 8.0 | Hold |
| --- | --- | --- |
| SLEEP_TRAINING | 8.0 | Hold |
| --- | --- | --- |
| SLEEP_WAKE | 1.0 | Fast ramp (2s) |
| --- | --- | --- |

**live_control.json key:** pp_blur_radius (float, pixels)

## 3.2  Chromatic Aberration

**Scientific basis:** Chromatic aberration (longitudinal chromatic aberration / LCA) occurs naturally in the human eye and in optical systems. Cholewiak et al. 2019 showed that adding LCA cues to blur significantly improves depth ordering judgments and drives accommodation. In a trance context, progressive chromatic aberration creates a visual quality associated with dreaming, altered states, and perceptual "unreality" — a quality that becomes a conditioned stimulus for depth via Doc 43's conditioning architecture.

**Implementation:** Per-channel UV offset in fragment shader. Red channel shifts outward from center, blue channel shifts inward, green stays centered. This produces radially increasing color fringing that simulates lens distortion.

**GLSL fragment shader:**

#version 330 core uniform sampler2D u_texture; uniform float u_ca_strength; // 0.0 to 0.01, from live_control uniform vec2 u_resolution; in vec2 v_uv; out vec4 frag_color; void main() { vec2 center = vec2(0.5); vec2 dir = v_uv - center; float dist = length(dir); vec2 offset = dir \* u_ca_strength \* dist; // radial: stronger at edges float r = texture(u_texture, v_uv + offset).r; float g = texture(u_texture, v_uv).g; float b = texture(u_texture, v_uv - offset).b; frag_color = vec4(r, g, b, 1.0); }

**Depth-modulated CA strength:**

| **Conductor Phase** | **u_ca_strength** | **Notes** |
| --- | --- | --- |
| CALIBRATION | 0.000 | None — clean baseline |
| --- | --- | --- |
| INDUCTION | 0.001 | Barely perceptible edge fringing |
| --- | --- | --- |
| DEEPENING | 0.003 | Subtle — noticeable if looked for |
| --- | --- | --- |
| MAINTENANCE | 0.006 | Dreamlike quality emerging |
| --- | --- | --- |
| SLEEP_APPROACH | 0.008 | Strong unreality cue |
| --- | --- | --- |
| SLEEP_ONSET | 0.010 | Maximum — paired with blur and vignette |
| --- | --- | --- |
| SLEEP_MAINTAIN | 0.010 | Maintained |
| --- | --- | --- |
| SLEEP_TRAINING | 0.010 | Maintained |
| --- | --- | --- |
| SLEEP_WAKE | 0.003 | Rapid reduction |
| --- | --- | --- |

**Conditioning Integration (Doc 43)**

Progressive CA is registered as a compound conditioned stimulus alongside blur and vignette. The triad of increasing blur + CA + vignette narrowing becomes associated with depth state, such that merely seeing the visual quality shift at session start triggers anticipatory depth-state neural patterns — priming for faster induction. Register VISUAL_DEPTH_TRIAD as an occasion-setting compound CS in Doc 43's AssociationRegistry.

**live_control.json key:** pp_ca_strength (float, 0.0–0.01)

## 3.3  Dynamic Vignette

**Scientific basis:** VR comfort research confirms peripheral darkening reduces awareness of peripheral visual information and concentrates attention centrally. The effect aligns with tunnel-vision phenomenology reported in deep trance and hypnosis. The vignette works synergistically with Troxler fading — darker periphery accelerates peripheral neural adaptation.

**Implementation:** Gaussian radial falloff multiplied onto the scene.

**GLSL fragment shader:**

#version 330 core uniform sampler2D u_texture; uniform float u_vignette_sigma; // 0.25 to 0.80, from live_control uniform float u_vignette_intensity; // 0.0 to 1.0, overall strength in vec2 v_uv; out vec4 frag_color; void main() { vec2 center = vec2(0.5); float dist = length(v_uv - center); float vignette = exp(-dist \* dist / (2.0 \* u_vignette_sigma \* u_vignette_sigma)); vignette = mix(1.0, vignette, u_vignette_intensity); vec3 color = texture(u_texture, v_uv).rgb \* vignette; frag_color = vec4(color, 1.0); }

**Depth-modulated vignette sigma** (smaller = tighter tunnel):

| **Conductor Phase** | **u_vignette_sigma** | **u_vignette_intensity** | **Notes** |
| --- | --- | --- | --- |
| CALIBRATION | 0.80 | 0.30 | Wide, subtle |
| --- | --- | --- | --- |
| INDUCTION | 0.65 | 0.50 |     |
| --- | --- | --- | --- |
| DEEPENING | 0.50 | 0.70 |     |
| --- | --- | --- | --- |
| MAINTENANCE | 0.35 | 0.85 |     |
| --- | --- | --- | --- |
| SLEEP_APPROACH | 0.30 | 0.90 |     |
| --- | --- | --- | --- |
| SLEEP_ONSET | 0.25 | 0.95 | Tight tunnel |
| --- | --- | --- | --- |
| SLEEP_MAINTAIN | 0.25 | 0.95 |     |
| --- | --- | --- | --- |
| SLEEP_TRAINING | 0.25 | 0.95 |     |
| --- | --- | --- | --- |
| SLEEP_WAKE | 0.60 | 0.40 |     |
| --- | --- | --- | --- |

**live_control.json keys:** pp_vignette_sigma (float), pp_vignette_intensity (float)

## 3.4  Bloom / Soft Glow

**Scientific basis:** Bloom creates a soft halo around bright elements (primarily the spiral edges and center text), producing a dreamlike, ethereal visual quality. Like chromatic aberration, progressive bloom contributes to the "unreality" visual signature that becomes a conditioned depth cue.

**Implementation:** Three-pass process:

1.  **Threshold extraction:** Extract pixels above luminance threshold into bloom buffer.
2.  **Blur:** Apply separable Gaussian blur to bloom buffer (reuse §3.1 blur shader with larger radius).
3.  **Additive composite:** Add blurred bloom back to scene.

**GLSL — Threshold extraction:**

#version 330 core uniform sampler2D u_texture; uniform float u_bloom_threshold; // 0.7 default in vec2 v_uv; out vec4 frag_color; void main() { vec3 color = texture(u_texture, v_uv).rgb; float brightness = dot(color, vec3(0.2126, 0.7152, 0.0722)); if (brightness > u_bloom_threshold) frag_color = vec4(color, 1.0); else frag_color = vec4(0.0, 0.0, 0.0, 1.0); }

**GLSL — Additive composite:**

#version 330 core uniform sampler2D u_scene; uniform sampler2D u_bloom; uniform float u_bloom_intensity; // from live_control in vec2 v_uv; out vec4 frag_color; void main() { vec3 scene = texture(u_scene, v_uv).rgb; vec3 bloom = texture(u_bloom, v_uv).rgb; frag_color = vec4(scene + bloom \* u_bloom_intensity, 1.0); }

**Depth-modulated bloom intensity:**

| **Conductor Phase** | **u_bloom_intensity** | **u_bloom_threshold** | **Notes** |
| --- | --- | --- | --- |
| CALIBRATION | 0.00 | 0.80 | Off |
| --- | --- | --- | --- |
| INDUCTION | 0.08 | 0.75 |     |
| --- | --- | --- | --- |
| DEEPENING | 0.20 | 0.70 |     |
| --- | --- | --- | --- |
| MAINTENANCE | 0.40 | 0.65 | Prominent ethereal glow |
| --- | --- | --- | --- |
| SLEEP_APPROACH | 0.25 | 0.70 |     |
| --- | --- | --- | --- |
| SLEEP_ONSET | 0.10 | 0.75 | Fading with display |
| --- | --- | --- | --- |
| SLEEP_MAINTAIN | 0.00 | 0.80 | Off |
| --- | --- | --- | --- |
| SLEEP_TRAINING | 0.00 | 0.80 | Off |
| --- | --- | --- | --- |
| SLEEP_WAKE | 0.10 | 0.75 |     |
| --- | --- | --- | --- |

**live_control.json keys:** pp_bloom_intensity (float), pp_bloom_threshold (float)

## 3.5  Sub-Threshold IAF Luminance Modulation

**Scientific basis:** Amaya et al. 2023 (_PLOS ONE_) systematically demonstrated that 10 Hz rhythmic stimulation produces the highest-intensity geometric pattern hallucinations and dynamics, and — critically — that frequency-matched **arrhythmic** flicker strongly reduces subjective effects compared to rhythmic flicker. This proves neural entrainment (not mere frequency content) drives the phenomenal experience. Labecki et al. 2024 (_Scientific Reports_) showed SSVEP at 5 Hz progressively **increases** over time, while higher frequencies (10, 15, 20, 40 Hz) show initial increase then continuous decline. This has direct implications for modulation strategy.

**Implementation:** Whole-screen luminance modulation at the user's individual alpha frequency (IAF, from eeg_engine.py). The modulation is **sub-threshold** — amplitude small enough that the user does not consciously perceive flicker, but large enough to drive cortical SSVEP entrainment.

**GLSL fragment shader:**

#version 330 core uniform sampler2D u_texture; uniform float u_iaf_mod_amplitude; // 0.0 to 0.05 uniform float u_iaf_mod_phase; // 0.0 to 2\*PI, updated per frame in vec2 v_uv; out vec4 frag_color; void main() { vec3 color = texture(u_texture, v_uv).rgb; float modulation = 1.0 + u_iaf_mod_amplitude \* sin(u_iaf_mod_phase); frag_color = vec4(color \* modulation, 1.0); }

**Phase update (Python, per frame):**

iaf_phase += 2.0 \* math.pi \* iaf_hz \* dt iaf_phase %= (2.0 \* math.pi)

Where iaf_hz is read from eeg_iaf_hz in live_control.json (computed by eeg_engine per Doc 44).

### SSVEP Habituation Management (Labecki 2024 integration with Doc 45)

- **If iaf_hz > 8.0 Hz** (alpha band): SSVEP habituates. Run modulation for 30s, pause for 2s, resume. Register IAF_LUMINANCE_MOD as a stimulus in Doc 45's habituation tracker. The 2s pause resets V5/MT adaptation.
- **If iaf_hz ≤ 8.0 Hz** (theta-adjacent): SSVEP builds over time. Run continuously — no pauses needed. The longer it runs, the stronger the entrainment response.
- **Rhythmicity is critical** (Amaya 2023). The sinusoidal waveform must be phase-locked and jitter-free. Use a **monotonic clock source**, NOT frame-dependent timing (frame drops would introduce arrhythmicity).

**Depth-modulated IAF amplitude:**

| **Conductor Phase** | **u_iaf_mod_amplitude** | **Notes** |
| --- | --- | --- |
| CALIBRATION | 0.00 | Off — clean baseline EEG measurement |
| --- | --- | --- |
| INDUCTION | 0.02 | Gentle sub-threshold drive |
| --- | --- | --- |
| DEEPENING | 0.03 | Increasing |
| --- | --- | --- |
| MAINTENANCE | 0.04 | Near-maximum sub-threshold |
| --- | --- | --- |
| SLEEP_APPROACH | 0.02 | Reducing — sleep phases don't need visual entrainment |
| --- | --- | --- |
| SLEEP_ONSET and beyond | 0.00 | Off — screen dark |
| --- | --- | --- |

**live_control.json keys:** pp_iaf_mod_amplitude (float), pp_iaf_mod_phase (float, written per frame by visual_display.py)

# 4  Spatial Audio Engine — spatial_audio.py

## 4.1  Module Architecture

class SpatialAudioEngine: """ Generates spatial audio effects mixed into audio_engine.py's output bus. NOT a replacement for audio_engine — an additive layer. audio_engine calls SpatialAudioEngine.render_block(n_frames) each audio callback and mixes the returned stereo buffer into its master output before final gain. Components: - StereoPanner: applies spatial panning to existing audio channels - ASMRTextureGen: generates soft textural sound events - LoomingSync: modulates audio gain/position with visual looming phase - ShepardToneGen: generates continuous descending Shepard tone Reads from live_control.json: bg_looming_phase (float) — from background_layer.py trance_score_v2 (float) — depth conductor_phase (str) — current phase spatial_panning_gain (float) — gain manifold output spatial_asmr_gain (float) — gain manifold output spatial_shepard_gain (float) — gain manifold output entrainment_freq_hz (float) — current target entrainment frequency """ def \__init_\_(self, sample_rate: int = 44100) -> None: ... def render_block(self, n_frames: int, live: dict) -> np.ndarray: ... # returns (n_frames, 2) float32

## 4.2  Stereo Spatial Panning

**Scientific basis — the key finding:** Sudre et al. 2024 (_PLOS ONE_) tested binaural beats, panning sounds, and alternate beeps at 6 Hz and 40 Hz. Their critical conclusion: _"the impact of auditory stimulation lies in the spatial attributes rather than the sensation of beating itself."_ All spatially moving sounds produced more pronounced EEG effects and relaxation improvement than control — at **both** 6 Hz and 40 Hz. This means the entrainment benefit of binaural beats may come primarily from perceived spatial movement of sound, not the specific binaural interference pattern. Panning is implementable in stereo without headphone requirements (unlike binaural beats which require headphones).

**Implementation:** Apply sinusoidal stereo panning to the existing audio channels (pink noise, binaural carrier, isochronic tones). The panning cycle rate matches the current entrainment frequency.

class StereoPanner: """ Applies sinusoidal stereo panning to a mono or stereo input signal. pan_position oscillates at entrainment_freq_hz: pan = sin(2 \* pi \* freq \* t) \* depth Left gain = cos((pan + 1) \* pi / 4) # constant-power panning law Right gain = sin((pan + 1) \* pi / 4) """ def \__init_\_(self, sample_rate: int) -> None: self.\_phase: float = 0.0 def process(self, mono_input: np.ndarray, freq_hz: float, depth: float = 0.7) -> np.ndarray: """ Args: mono_input: (n_frames,) float32 freq_hz: panning cycle rate (= entrainment frequency) depth: 0.0 = center (no panning), 1.0 = full hard-pan Default 0.7 — avoids jarring full-stereo sweeps Returns: (n_frames, 2) float32 stereo output """

**Parameters:**

- **Panning depth:** 0.7 (soft panning, not hard L/R — Sudre used moderate panning)
- **Panning frequency:** reads entrainment_freq_hz from live_control.json
- **Panning law:** constant-power (equal-loudness across pan positions)
- **Applied to:** pink noise channel, binaural beat carrier, isochronic tone channel
- **NOT applied to:** TTS voice (voice stays centered for intelligibility), SSB subliminal channel

**Gain integration:** Overall panning effect depth scaled by spatial_panning_gain from gain manifold.

## 4.3  ASMR-Adjacent Textural Layer

**Scientific basis:** Lin and Kondo 2024 (_Philosophical Transactions of the Royal Society B_) showed that ASMR produces reduced connectivity in the salience network plus activations for social cognition, emotion regulation, and empathy. Increased insular cortex activation combined with reduced salience/default mode network connectivity accounts for relaxation and flow states. Common triggers include whispering, soft sounds, and low-pitched dark timbre. Sakurai et al. 2023 (_Frontiers in Neuroscience_) showed audio-only ASMR activated bilateral insular cortices, and even non-tingling participants reported relaxation.

**Implementation:** Generate sparse, irregular soft textural sound events — filtered pink noise micro-bursts with ASMR-like spectral characteristics.

class ASMRTextureGen: """ Generates sparse soft-textural sound events at irregular intervals. Each event is a filtered pink noise burst with: - Low-pass cutoff: 2000 Hz (dark timbre) - High-pass cutoff: 80 Hz (remove rumble) - Attack: 50 ms raised-cosine - Sustain: 80-150 ms (randomized) - Decay: 200 ms raised-cosine - Total event duration: 330-400 ms Event timing: Poisson-distributed with mean interval dependent on depth. - INDUCTION: disabled - DEEPENING: mean interval 4.0 s - MAINTENANCE: mean interval 2.0 s - SLEEP phases: mean interval 5.0 s (sparse, very quiet) Spatial placement: each event randomly panned L/R within ±0.4 depth (gentle spatial variation, not dramatic sweeps). """ def \__init_\_(self, sample_rate: int) -> None: ... def render(self, n_frames: int, depth: float) -> np.ndarray: ...

**Spectral characteristics:**

- Target spectral profile: −3 dB/octave (pink) with 2 kHz brick-wall LPF and 80 Hz HPF
- This produces the "dark, warm" timbre characteristic of ASMR triggers
- Pink noise generation: Voss-McCartney algorithm (already in audio_engine) or pre-generated buffer

**Gain:** Very low base gain — 3% of master as starting point, scaled by spatial_asmr_gain from gain manifold. Must **not** be perceptually prominent; it should be subliminal/ambient.

## 4.4  Looming Audio Synchronization

**Scientific basis:** Cappe et al. 2012 demonstrated synergistic multisensory integration for looming signals with neural interactions at ~75ms post-stimulus, activating amygdala/insula circuits. Brozova et al. 2025 (_Frontiers in Neuroscience_) showed that cross-modal congruency enhances sensory encoding at the neural level — congruent audiovisual stimulation quantifiably improves the accumulation of sensory evidence. Synchronized audio-visual looming creates a unified percept of environmental approach/recession.

**Implementation:** Audio gain envelope tracks visual looming phase (from bg_looming_phase in live_control.json) with a 75ms delay for optimal multisensory temporal binding.

class LoomingSync: """ Modulates master audio gain to synchronize with visual looming. Reads bg_looming_phase (0.0-1.0) from live_control.json. Applies a 75ms delay buffer (Cappe 2012 optimal binding window). Gain modulation: ±1.5 dB (subtle, not dramatic) looming (expansion) = +1.5 dB receding (contraction) = -1.5 dB Linear interpolation: gain_factor = 1.0 + 0.17 \* sin(2\*pi\*delayed_phase) (0.17 ≈ 10^(1.5/20) - 1) """ def \__init_\_(self, sample_rate: int) -> None: self.\_delay_samples = int(0.075 \* sample_rate) # 75ms self.\_phase_buffer = np.zeros(self.\_delay_samples + 1) def get_gain_envelope(self, n_frames: int, looming_phase: float) -> np.ndarray: ...

The gain envelope is applied as a per-sample multiplier to the mixed audio output (all channels except TTS, which maintains stable intelligibility gain).

## 4.5  Descending Shepard Tone Generator

**Scientific basis:** A Shepard tone is a superposition of sine waves separated by octaves, with amplitudes weighted by a Gaussian spectral envelope, creating the auditory illusion of continuously ascending or descending pitch. For trance applications, a very slow descending Shepard tone creates a subliminal sense of continuous descent/deepening — it is a purely auditory metaphor processed pre-attentively.

**Caution**

Shepard tones can cause anxiety or nausea at high intensity or fast rates. Must stay sub-perceptual as a background element.

**Implementation:**

class ShepardToneGen: """ Generates a continuously descending Shepard tone. Components: 6 sine waves at octave intervals (C1 through C6 equivalent) Each component amplitude = gaussian(log2(freq), center=log2(440), sigma=2.0) Descent rate: 1 semitone per 30 seconds (VERY slow — imperceptible pitch change). Fundamental frequency range: wraps logarithmically (as one component descends below audible range, a new one fades in at the top). Output: mono float32, mixed to center stereo position """ \_N_COMPONENTS = 6 \_GAUSSIAN_CENTER = np.log2(440.0) # Hz, center of spectral envelope \_GAUSSIAN_SIGMA = 2.0 # octaves \_DESCENT_RATE = 1.0 / 30.0 # semitones per second def \__init_\_(self, sample_rate: int) -> None: self.\_base_semitone: float = 0.0 # current position in semitone space self.\_phases = np.zeros(self.\_N_COMPONENTS) def render(self, n_frames: int) -> np.ndarray: ...

**Parameters:**

- **Number of octave components:** 6 (C1 ≈ 32.7 Hz through C6 ≈ 1046.5 Hz)
- **Spectral envelope:** Gaussian centered at A4 (440 Hz) with sigma = 2 octaves
- **Descent rate:** 1 semitone per 30 seconds — the user should never consciously perceive pitch change
- **Base gain:** 1% of master output — barely audible, subliminal depth metaphor
- **Gain scaling:** spatial_shepard_gain from gain manifold

**Phase activation:**

| **Conductor Phase** | **Shepard Active** | **Gain Multiplier** |
| --- | --- | --- |
| CALIBRATION | No  | 0.0 |
| --- | --- | --- |
| INDUCTION | No  | 0.0 |
| --- | --- | --- |
| DEEPENING | Yes | 0.3 |
| --- | --- | --- |
| MAINTENANCE | Yes | 0.5 |
| --- | --- | --- |
| SLEEP_APPROACH | Yes | 0.3 |
| --- | --- | --- |
| SLEEP_ONSET | No  | 0.0 |
| --- | --- | --- |
| SLEEP_MAINTAIN | No  | 0.0 |
| --- | --- | --- |
| SLEEP_TRAINING | No  | 0.0 |
| --- | --- | --- |
| SLEEP_WAKE | No  | 0.0 |
| --- | --- | --- |

# 5  Cross-Layer Coordination

## 5.1  Respiratory-Visual-Audio Coupling Chain

The respiratory cycle serves as the master clock for cross-layer synchronization:

1.  ppg_engine.py derives breath phase from RSA (Doc 42) and writes ppg_breath_phase to live_control.json.
2.  BackgroundLayer reads ppg_breath_phase and modulates: Ganzfeld brightness (§2.2), radial looming expansion (§2.4).
3.  BackgroundLayer writes bg_looming_phase to live_control.json.
4.  SpatialAudioEngine reads bg_looming_phase with 75ms delay and modulates audio gain envelope (§4.4).
5.  DeliveryGate (Doc 35) reads ppg_breath_phase for exhale-window gating of content delivery.
6.  **Net effect:** visual brightness, visual spatial expansion, audio gain, and content delivery are all phase-locked to the user's breathing — creating a unified multisensory environment that breathes with the user.

**Fallback:** When ppg_available is False, the entire chain runs on the synthetic RespiratoryTracker oscillator at the default 0.2 Hz rate. The coupling is identical; only the clock source changes. No downstream consumer needs to know whether the breath clock is physiological or synthetic.

## 5.2  SSVEP Habituation-Aware Modulation Cycling

Integration between Doc 45 (habituation engine) and §3.5 (IAF luminance modulation):

- IAF_LUMINANCE_MOD is registered as a stimulus in Doc 45's NoveltyStimulusTracker.
- **When the novelty engine reports meso-timescale habituation:**
    - Modulation pauses for 3s (longer than the 2s minimum reset).
    - On resume, amplitude increases by 10% (within the maximum ceiling of 0.05).
    - This amplitude bump decays back to baseline over 60s.
- **When macro-timescale habituation is flagged:**
    - Modulation enters COOLING state per Doc 45's rotation engine.
    - Alternative: shift modulation frequency from IAF to IAF/2 (sub-harmonic) for the cooling period.
    - Sub-harmonic modulation provides a novel stimulus while maintaining alpha-band relationship.

## 5.3  Multisensory Temporal Binding Windows

All cross-modal synchronization respects the temporal binding windows established in the literature:

| **Modality Pair** | **Binding Window** | **Implementation** |
| --- | --- | --- |
| Visual–Audio (looming) | 75ms visual lead | bg_looming_phase delay buffer in LoomingSync |
| --- | --- | --- |
| Visual–Subliminal Text | 200ms offset minimum | Doc 36's Shadows-to-CenterText offset (already implemented) |
| --- | --- | --- |
| Audio–Respiratory | 0ms (real-time) | Direct phase-lock to ppg_breath_phase |
| --- | --- | --- |
| Visual–Respiratory | 0ms (real-time) | Direct Ganzfeld brightness modulation |
| --- | --- | --- |
| Content–Cardiac | Systole guard | Doc 42's 350ms systole exclusion window in DeliveryGate |
| --- | --- | --- |

## 5.4  Motion Aftereffect Enhancement

Integration with Doc 44's 35s rotation + 2s pause MAE exploitation cycle:

**During the 2s rotation pause:**

- Background layer shifts looming **inward** (slight contraction) — enhances perceived expansion of the MAE on the static spiral.
- Post-processing blur reduces by 30% momentarily — sharper static spiral makes MAE more vivid.
- Bloom intensity increases by 20% — the stationary spiral appears to glow and expand.
- After 2s, rotation resumes and all values return to their depth-determined baselines.

This makes the MAE pause a multimodal deepening event rather than just a visual trick. Register MAE_PAUSE as a compound stimulus in Doc 45's habituation tracker to prevent it from losing impact over sessions.

# 6  Gain Manifold Integration (Doc 37 Extension)

Doc 37 specifies a 5-channel coupled gain manifold with crossmodal stochastic resonance calibration and depth-dependent whole-system fadedown. Doc 47 adds two new top-level gain channels and four sub-channels.

## 6.1  New Gain Channels

**Channel 6: visual_enhancement**

| **Sub-Channel** | **Description** |
| --- | --- |
| bg_ganzfeld_gain | Ganzfeld breathing amplitude |
| --- | --- |
| bg_looming_gain | Radial looming amplitude |
| --- | --- |
| pp_effect_gain | Post-processing master (scales blur, CA, vignette, bloom uniformly) |
| --- | --- |

**Channel 7: spatial_audio**

| **Sub-Channel** | **Description** |
| --- | --- |
| spatial_panning_gain | Stereo panning depth |
| --- | --- |
| spatial_asmr_gain | ASMR texture event gain |
| --- | --- |
| spatial_shepard_gain | Shepard tone gain |
| --- | --- |
| spatial_looming_gain | Looming audio sync amplitude |
| --- | --- |

## 6.2  Depth-Dependent Fadedown

Both new channels participate in Doc 37's whole-system depth-dependent fadedown. As trance deepens beyond the MAINTENANCE plateau, all stimulation gradually reduces. The fadedown applies multiplicatively to all sub-channel gains:

effective_gain = sub_channel_gain \* channel_master \* depth_fadedown_factor

The depth fadedown factor follows the same curve specified in Doc 37 for existing channels.

## 6.3  Crossmodal Stochastic Resonance

The new channels participate in Doc 37's SR calibration sweep protocol. During the CALIBRATION phase, the SR sweep includes:

- Visual enhancement stimuli at ascending gain levels
- Spatial audio stimuli at ascending gain levels
- EEG response monitoring identifies the sub-threshold resonance peak for each new channel
- Optimal SR gain is stored per-user in somna_db.py

## 6.4  Spectral Occupancy Coordination

Doc 37's spectral occupancy map must be extended to include:

- **ASMR texture events:** 80–2000 Hz band, sparse temporal occupancy
- **Shepard tone:** full spectrum (32–1047 Hz) but low amplitude, continuous
- **Spatial panning:** does NOT add new spectral content — it redistributes existing content across L/R channels

The spectral occupancy map prevents masking conflicts: ASMR events should **not** fire when TTS voice is active (both occupy similar spectral bands). Implement as a spectral clearance check in ASMRTextureGen.render() that reads tts_active from live_control.json.

# 7  Phase Activation Summary Table

Master reference table for all Doc 47 effects across Conductor phases. All values represent the **targets** that the gain manifold and post-processing parameter interpolators converge toward when entering each phase. Percentage gains are relative to the SR-calibrated optimal gain for that channel (Doc 37 §calibration). Post-processing values are direct parameter values.

| **Effect** | **CAL** | **IND** | **DEEP** | **MAINT** | **SLP_APP** | **SLP_ONS** | **SLP_MN** | **SLP_TR** | **SLP_WK** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Ganzfeld breathing amp | 0%  | 30% | 70% | 100% | 60% | 30% | 20% | 20% | 0%  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Color temperature (K) | 4500 | 3800 | 3200 | 2700 | 2200 | 1800 | 1800 | 1800 | 3200 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Radial looming amp | 0%  | 20% | 60% | 100% | 40% | 0%  | 0%  | 0%  | 0%  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Gaussian blur (px) | 0   | 0.5 | 2.0 | 4.0 | 6.0 | 8.0 | 8.0 | 8.0 | 1.0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Chromatic aberration | 0   | .001 | .003 | .006 | .008 | .010 | .010 | .010 | .003 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Vignette sigma | 0.80 | 0.65 | 0.50 | 0.35 | 0.30 | 0.25 | 0.25 | 0.25 | 0.60 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Vignette intensity | 0.30 | 0.50 | 0.70 | 0.85 | 0.90 | 0.95 | 0.95 | 0.95 | 0.40 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Bloom intensity | 0   | 0.08 | 0.20 | 0.40 | 0.25 | 0.10 | 0   | 0   | 0.10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IAF luminance mod | 0   | 0.02 | 0.03 | 0.04 | 0.02 | 0   | 0   | 0   | 0   |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stereo panning depth | 0   | 0.30 | 0.50 | 0.70 | 0.40 | 0.20 | 0.15 | 0.15 | 0   |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ASMR texture gain | 0   | 0   | 0.03 | 0.06 | 0.04 | 0.02 | 0.01 | 0.01 | 0   |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Looming audio sync | 0   | 0.30 | 0.60 | 1.00 | 0.40 | 0   | 0   | 0   | 0   |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Shepard tone gain | 0   | 0   | .003 | .005 | .003 | 0   | 0   | 0   | 0   |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

# 8  live_control.json Key Registry

All new keys introduced by Doc 47:

| **Key** | **Type** | **Range** | **Writer** | **Reader(s)** | **Description** |
| --- | --- | --- | --- | --- | --- |
| bg_ganzfeld_gain | float | 0.0–1.0 | gain_manifold | background_layer | Ganzfeld breathing modulation depth |
| --- | --- | --- | --- | --- | --- |
| bg_looming_gain | float | 0.0–1.0 | gain_manifold | background_layer | Radial looming modulation depth |
| --- | --- | --- | --- | --- | --- |
| bg_looming_phase | float | 0.0–1.0 | background_layer | spatial_audio | Current visual looming expansion phase |
| --- | --- | --- | --- | --- | --- |
| bg_color_temp_k | int | 1800–4500 | conductor | background_layer | Target color temperature in Kelvin |
| --- | --- | --- | --- | --- | --- |
| pp_blur_radius | float | 0.0–8.0 | conductor/interpolator | visual_display | Gaussian blur radius in pixels |
| --- | --- | --- | --- | --- | --- |
| pp_ca_strength | float | 0.0–0.01 | conductor/interpolator | visual_display | Chromatic aberration UV offset |
| --- | --- | --- | --- | --- | --- |
| pp_vignette_sigma | float | 0.25–0.80 | conductor/interpolator | visual_display | Vignette Gaussian sigma |
| --- | --- | --- | --- | --- | --- |
| pp_vignette_intensity | float | 0.0–1.0 | conductor/interpolator | visual_display | Vignette overall strength |
| --- | --- | --- | --- | --- | --- |
| pp_bloom_intensity | float | 0.0–0.5 | conductor/interpolator | visual_display | Bloom additive intensity |
| --- | --- | --- | --- | --- | --- |
| pp_bloom_threshold | float | 0.6–0.9 | conductor/interpolator | visual_display | Bloom luminance threshold |
| --- | --- | --- | --- | --- | --- |
| pp_iaf_mod_amplitude | float | 0.0–0.05 | conductor/interpolator | visual_display | IAF luminance modulation amplitude |
| --- | --- | --- | --- | --- | --- |
| pp_iaf_mod_phase | float | 0.0–2π | visual_display (per-frame) | internal | Current IAF modulation phase |
| --- | --- | --- | --- | --- | --- |
| spatial_panning_gain | float | 0.0–1.0 | gain_manifold | spatial_audio | Stereo panning depth multiplier |
| --- | --- | --- | --- | --- | --- |
| spatial_asmr_gain | float | 0.0–0.1 | gain_manifold | spatial_audio | ASMR texture event gain |
| --- | --- | --- | --- | --- | --- |
| spatial_shepard_gain | float | 0.0–0.01 | gain_manifold | spatial_audio | Shepard tone gain |
| --- | --- | --- | --- | --- | --- |
| spatial_looming_gain | float | 0.0–1.0 | gain_manifold | spatial_audio | Looming audio sync amplitude |
| --- | --- | --- | --- | --- | --- |
| tts_active | bool | true/false | audio_engine | spatial_audio | Whether TTS is currently playing (spectral clearance) |
| --- | --- | --- | --- | --- | --- |

All keys follow the existing live_control.json convention: written via \_patch_live() (read-modify-write), reader priority = user slider > LLM agent > timeline_runner > config defaults.

# 9  Doc 45 Habituation Registry Entries

New stimuli to register with Doc 45's NoveltyStimulusTracker:

| **Stimulus ID** | **Micro (s)** | **Meso (s)** | **Macro (sessions)** | **Dishabituation Triggers** |
| --- | --- | --- | --- | --- |
| GANZFELD_FIELD | 60  | 600 | 5   | Troxler reset event; color temperature jump |
| --- | --- | --- | --- | --- |
| GANZFELD_TROXLER | 45  | 300 | 3   | Automatic (built into fade-return-fade cycle) |
| --- | --- | --- | --- | --- |
| RADIAL_LOOMING | 90  | 450 | 4   | Looming amplitude change; phase inversion |
| --- | --- | --- | --- | --- |
| PP_BLUR | 120 | 900 | 8   | Blur radius step change |
| --- | --- | --- | --- | --- |
| PP_CA | 120 | 900 | 8   | CA strength step change |
| --- | --- | --- | --- | --- |
| PP_VIGNETTE | 120 | 900 | 8   | Sigma step change |
| --- | --- | --- | --- | --- |
| PP_BLOOM | 90  | 600 | 5   | Threshold change; intensity spike |
| --- | --- | --- | --- | --- |
| IAF_LUMINANCE_MOD | 30  | 180 | 3   | Frequency shift to IAF/2; amplitude bump; 3s pause |
| --- | --- | --- | --- | --- |
| STEREO_PANNING | 60  | 360 | 4   | Panning depth change; panning direction reversal |
| --- | --- | --- | --- | --- |
| ASMR_TEXTURE | 45  | 300 | 3   | Spectral filter cutoff variation; event duration variation |
| --- | --- | --- | --- | --- |
| SHEPARD_TONE | 180 | 1200 | 10  | Descent rate change; octave range shift |
| --- | --- | --- | --- | --- |
| MAE_PAUSE | 35  | 420 | 5   | Pause duration variation; background contrast shift |
| --- | --- | --- | --- | --- |

# 10  Doc 43 Conditioning Registry Entries

New conditioned stimuli and associations to register with Doc 43's AssociationRegistry.

## 10.1  VISUAL_DEPTH_TRIAD — Compound CS

The simultaneous progression of blur + chromatic aberration + vignette narrowing forms a compound conditioned stimulus for depth state. As these three effects increase together across sessions, they become associated with the depth-state neural fingerprint (Doc 43 §6D fingerprint). Eventually, seeing the visual quality shift at the **start** of a session will trigger anticipatory depth-state neural patterns — priming for faster induction.

| **Property** | **Value** |
| --- | --- |
| CS type | Compound (3 elements) |
| --- | --- |
| Components | pp_blur_radius > 1.0 AND pp_ca_strength > 0.002 AND pp_vignette_sigma < 0.55 |
| --- | --- |
| US  | trance_score_v2 > 0.6 (genuine depth state) |
| --- | --- |
| Association tracking | Rescorla-Wagner per Doc 43 |
| --- | --- |
| Expected timeline | Strength builds across 5–10 sessions; occasion-setting by DEEPENING phase onset |
| --- | --- |

## 10.2  GANZFELD_WARMTH — Classical Association

The warm, breathing Ganzfeld field becomes associated with relaxation/depth through classical conditioning (pairing with the parasympathetic state).

| **Property** | **Value** |
| --- | --- |
| CS type | Simple |
| --- | --- |
| CS  | bg_ganzfeld_gain > 0.5 AND bg_color_temp_k < 3000 |
| --- | --- |
| US  | ppg_hrv_rmssd > session_baseline × 1.3 (parasympathetic shift) |
| --- | --- |

## 10.3  SHEPARD_DESCENT — State-Dependent Association

The Shepard tone becomes a state-dependent cue: it is only present during DEEPENING and MAINTENANCE, so it becomes exclusively associated with depth states.

| **Property** | **Value** |
| --- | --- |
| CS type | State-dependent |
| --- | --- |
| Context | conductor_phase in (DEEPENING, MAINTENANCE) |
| --- | --- |
| CS  | spatial_shepard_gain > 0 |
| --- | --- |
| US  | Depth state (trance_score_v2 > 0.5) |
| --- | --- |

# 11  Implementation Notes

## 11.1  ModernGL Pipeline Setup

The post-processing pipeline requires:

- 7 FBO textures (scene, blur_h, blur_v, composite, ca, bloom_extract, bloom_blur, final) — some can be reused via ping-pong
- 5 shader programs (blur, ca, bloom_threshold, bloom_composite+vignette, iaf_mod)
- Combine bloom composite and vignette into a single pass to save one FBO:

// Combined bloom composite + vignette pass vec3 scene = texture(u_scene, v_uv).rgb; vec3 bloom = texture(u_bloom, v_uv).rgb; vec3 combined = scene + bloom \* u_bloom_intensity; vec2 center = vec2(0.5); float dist = length(v_uv - center); float vignette = exp(-dist \* dist / (2.0 \* u_vignette_sigma \* u_vignette_sigma)); vignette = mix(1.0, vignette, u_vignette_intensity); frag_color = vec4(combined \* vignette, 1.0);

This reduces the pipeline to 6 passes total (blur_h, blur_v, ca, bloom_extract, bloom_blur, composite+vignette+iaf). The IAF modulation can be folded into the final composite pass as well, reducing to **5 passes**.

## 11.2  Background Layer Rendering Order

1.  Clear framebuffer
2.  Render BackgroundLayer fullscreen quad (Ganzfeld color + radial gradient)
3.  Render spiral (existing)
4.  Render subliminal text / center text (existing)
5.  Run post-processing pipeline on the composited scene
6.  Apply blur **only** to background pixels — use either:
    - **Option A:** Render background to separate FBO, blur it, then composite with sharp foreground layers
    - **Option B:** Render a depth/mask buffer identifying background vs foreground pixels, use mask in blur shader to selectively blur

**Recommendation**

Option A (simpler, cleaner separation). The background is already rendered as a separate fullscreen quad, so routing it through a dedicated blur FBO adds minimal complexity.

## 11.3  SpatialAudioEngine Integration with audio_engine.py

\# In audio_engine.py callback: def \_audio_callback(self, outdata, frames, time_info, status): # ... existing audio generation ... # Mix in spatial audio layer spatial_block = self.\_spatial_engine.render_block(frames, self.\_live) outdata\[:\] += spatial_block \* self.\_live.get('spatial_audio_master', 0.0) # Apply looming gain envelope to everything except TTS if not self.\_live.get('tts_active', False): looming_env = self.\_spatial_engine.get_looming_envelope(frames) outdata\[:\] \*= looming_env

## 11.4  Parameter Interpolation

All post-processing and background parameters that change with Conductor phase transitions must be smoothly interpolated — **never step-change**. Use exponential smoothing:

current_value += (target_value - current_value) \* smoothing_alpha \* dt

Where smoothing_alpha gives a time constant of approximately **3 seconds** for visual parameters (imperceptible transition) and **1 second** for audio parameters (faster but still smooth). The exception is SLEEP_WAKE transitions, which use a faster time constant of **0.5 seconds**.

## 11.5  Performance Budget

The post-processing pipeline adds 5 fullscreen fragment shader passes per frame. At 1920×1080 and 60 FPS:

- 5 passes × 2M pixels × 60 FPS = 600M fragment operations/second
- Well within the budget of any discrete GPU or modern integrated GPU
- The Gaussian blur is the most expensive pass (two passes, 9 texture lookups each)
- **If performance is tight:** reduce blur to 3-tap kernel (weights: 0.4, 0.25, 0.05)

SpatialAudioEngine adds negligible CPU load — all operations are simple per-sample multiplications and sine generation on the audio callback thread.

# 12  Safety Considerations

## 12.1  Photosensitive Epilepsy

The IAF luminance modulation (§3.5) operates in the alpha band (8–12 Hz), which overlaps with the photosensitive epilepsy danger zone (3–60 Hz, peak sensitivity 15–25 Hz). Mitigations:

- **Maximum modulation amplitude is 5%** — well below the threshold for pattern-sensitive seizures (which typically require >30% contrast modulation).
- The modulation is whole-screen uniform (no spatial pattern) — spatially uniform flicker is less epileptogenic than patterned flicker.
- **First-run warning:** the application must display a photosensitivity warning during initial setup.
- **User-configurable:** pp_iaf_mod_amplitude ceiling can be set to 0.0 in config to disable entirely.

## 12.2  Motion Sickness

Radial looming (§2.4) and chromatic aberration (§3.2) can cause motion discomfort in susceptible individuals. Mitigations:

- All parameters start at zero and ramp slowly.
- User can cap any parameter via config.
- Looming amplitude is respiratory-locked (slow, ~0.2 Hz) — well below the vection-inducing frequency range.

## 12.3  Shepard Tone Anxiety

Shepard tones can induce anxiety or unease at moderate-to-high gain. Mitigations:

- Maximum gain is 0.5% of master (barely audible).
- Descent rate is 1 semitone per 30 seconds (imperceptible).
- Disabled in all sleep phases and wake phases — only active during DEEPENING and MAINTENANCE.

# 13  References

1.  Amaya, S. et al. (2023). Frequency and rhythmicity modulate the phenomenal, neural, and computational effects of stroboscopic flicker. _PLOS ONE_.
2.  Blume, C. et al. (2024). Effects of calibrated blue-yellow changes in light on the human circadian clock. _Nature Human Behaviour_.
3.  Brozova, K. et al. (2025). Cross-modal congruency modulates evidence accumulation. _Frontiers in Neuroscience_.
4.  Cappe, C. et al. (2012). Looming signals reveal synergistic principles of multisensory integration. _Journal of Neuroscience_, 32(4), 1171–1182.
5.  Cholewiak, S. et al. (2019). Chromatic and blur in real-time blur drives accommodation. _Journal of Vision / ARVO_.
6.  Labecki, M. et al. (2024). SSVEP amplitudes are not stable over time. _Scientific Reports_.
7.  Lin, M.Y. & Kondo, H.M. (2024). ASMR as a multisensory phenomenon. _Philosophical Transactions of the Royal Society B_.
8.  Pistolas, D. et al. (2025). Full Ganzfeld immersion study. _Open Mind_, MIT Press.
9.  Rees, G. (2001). Neuroimaging of visual awareness in patients and normal subjects — V5/MT and motion aftereffect. _Neuron_.
10. Sakurai, N. et al. (2023). Brain function and ASMR. _Frontiers in Neuroscience_.
11. Shenyan, L. et al. (2024). Ganzflicker vs Ganzfeld hallucinations. _Nature Scientific Reports_.
12. Stetza, L. et al. (2025). Respiration modulates task-related neural representations. _Journal of Neuroscience_.
13. Sudre, G. et al. (2024). Spatially moving sounds vs binaural beats. _PLOS ONE_.
14. Tort, A.B.L. et al. (2025). Breathing as a global brain coordinator. _Nature Reviews Neuroscience_.

Somna Doc 47 v1.0 — Visual & Audio Enhancement Architecture — 2026-04-05 — End of document