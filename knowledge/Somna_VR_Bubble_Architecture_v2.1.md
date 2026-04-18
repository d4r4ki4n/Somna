# Somna VR — The Bubble Architecture

*Version 2.1 — 2026-04-17*
*Revised by: Resonance + Reese (audit integration)*
*Supersedes: VR Stage-Sky Pipeline v1*

---

## 1. The Premise

> Somna VR should not put you somewhere. It should make the brainstate visible from inside.

The original VR design document established a foundational principle: the environment mirrors depth of state rather than illustrating it metaphorically. That principle remains. What changes here is the geometry that delivers it. The void/stage split — darkness for deep phases, a cylinder and floor for work windows — has been replaced by a single enclosing sphere whose parameters continuously vary. The bubble is not a new theme layered on top of the void. The bubble *is* the void at one end of its parameter range, and the full write-layer surface at the other. Every state in between is a blend, not a mode switch.

This is an architectural simplification, not an aesthetic addition. The void/stage model required a discrete choreography mode enum (void, prelude, instrument_focus, balanced, integration, shell) with explicit transitions between states. The bubble replaces that with two continuous floats: diameter and membrane opacity. The choreography modes emerge from the parameter values rather than being named and switched between. Fewer states means fewer transitions to get wrong, fewer edge cases in the policy engine, and more expressiveness for the conductor and agent to work with.

The thesis that animates every design decision in this document: **the bubble is actively squeezing the conditioning into you.** It is not a display surface. It is an active agent that physically presses content into the user through contraction, breathing, membrane projection, and spatial audio anchored to the enclosing wall. Every choice — diameter, opacity, breathing sync, content projection, spatial carrier placement — serves this single idea.

The single most important question remains empirical and unchanged: **does being in a headset with Somna actually deepen the work?** The first wave of implementation exists to answer that question as cheaply as possible, before building anything elaborate.

---

## 2. Why a Sphere

A sphere centered on the user's head pose, locked via OpenXR, solves three problems simultaneously that the original void/stage design handled awkwardly or not at all:

**Orientation independence**

The original design assumed an upright, forward-facing user. The horizon element, the floor plane, the dawn direction for emergence — all of these presume a canonical up vector. But people sink, tilt, recline, and lie down during deep sessions. A forward-facing horizon becomes wrong the moment you recline 30°. A sphere doesn't care. It has no up, no down, no forward. Every direction is just another part of the enclosing wall. The user can start a session lying on their side, sitting upright, or slowly sinking into a chair, and the bubble is always correctly oriented because it is always centered on the head. No calibration, no orientation tracking, no wrong state.

**Continuous parameter space**

The void/stage split was architecturally two distinct renderers with a choreography mode enum switching between them. The bubble collapses void and stage into a single geometry whose behavior is determined by two continuous parameters. Void is a large, transparent bubble. Full write-layer is a tight, opaque bubble. Everything in between is a smooth interpolation. This eliminates the need for discrete mode transitions entirely. The policy engine doesn't switch modes; it adjusts curves. The conductor doesn't write a mode hint; it writes target diameter and opacity values.

**Enclosure as somatic channel**

A sphere that rhythmically contracts 3–8% in sync with the binaural beat is felt as pressure even without haptics. The brain interprets looming visual motion as physical proximity — this is a perceptual fact, not a design opinion. A flat screen cannot produce this effect because it doesn't enclose the viewer. The bubble unlocks a genuinely new somatic channel that only exists in VR and only exists with enclosing geometry. The breathing/contraction synchronized to the beat frequency isn't decorative; it's a new entrainment modality that the desktop experience simply cannot deliver.

---

## 3. Design Principles

| Principle | Meaning |
|---|---|
| **Environment mirrors depth, not theme** | No scenic metaphors. Geometry density, color temperature, and luminance follow the session arc numerically. The bubble's properties *are* the brainstate. |
| **Void is the off state of the bubble** | Darkness with one breathing element isn't a placeholder — it's the correct environment for theta/delta. Complexity is earned by sessions that need cognitive engagement. |
| **Spatial audio first** | The most meaningful VR upgrade to entrainment is audio spatialization, not visuals. It costs less and changes the sensation categorically. |
| **Transitions register, not announce** | Parameter changes shift environment by small increments. The user should not consciously notice — only find themselves further under. |
| **One boss at a time** | Combined instrument × membrane × audio intensity is bounded by the policy engine in code, not by guidelines. |
| **No body** | No avatar, no hands, no spatial UI begging for attention during induction. Minimal implied presence. |
| **Aphantasia-safe by construction** | All spatial cues are geometric and rhythmic, never imagined scenery. The bubble requires nothing from the user's visual imagination. |
| **Bus is truth** | All state remains `live_control.json` via `patch_live`. No new IPC. |

---

## 4. Acknowledging the Thematic Register

The original design principle stated that the environment should mirror brainstate, not theme. The bubble introduces a complication worth being honest about. A sphere that contracts around the user, whose wall scrolls with affirmations, that breathes in sync with the beat — this isn't a neutral representation of depth. It's a spatial metaphor for the session's agency. The bubble says something specific about the relationship between user and session. It communicates enclosure, intention, and an active agent working on the user from the outside. The void communicated nothing beyond depth itself.

This isn't wrong, but it is a conscious shift from "the environment IS the brainstate" to "the environment represents the session's relationship to the user." These are different design philosophies. The bubble is stronger for the pleasure-tech and hypnokink register, where the sense of being deliberately worked on by an enclosing agent *is the point*. The void is stronger for pure clinical entrainment, where any sense of external agency might be counterproductive.

The resolution is that the bubble supports both registers through its parameter range. At maximum diameter and near-zero membrane opacity, the bubble IS the void — an imperceptible container that communicates nothing beyond depth. As the membrane becomes active and the diameter shrinks, the thematic register shifts from clinical to intentional. The session designer or agent controls that transition. The bubble doesn't impose a theme; it makes theme a controllable parameter.

---

## 5. The Bubble Model

### 5.1 Geometry

A UV-mapped sphere of configurable diameter, centered on the OpenXR head pose. The sphere renders with back-face culling reversed so the user sees the inner surface. The UV mapping supports projection of existing visual layers (affirmations, images, spirals) onto the curved inner wall. The default diameter range is 2.0–6.0 meters, with a comfortable tight minimum of 2.2m and a loose maximum of 5.5m for prelude and emergence phases.

### 5.2 Membrane

The sphere's surface is the membrane. It has three controllable properties:

- **Opacity (0–1):** Controls how visible and present the wall is. At 0, the membrane is invisible and the user sees only the instrument (flicker, Ganzfeld) and the horizon element. At 1, the wall is fully opaque and serves as the primary delivery surface for all content layers.
- **Content intensity (0–1):** Controls the strength of projected content on the membrane. This decouples the wall's visual presence from the intensity of what it's displaying. A translucent wall can still carry strong affirmations; an opaque wall can be blank.
- **Distortion (0–1):** A liquid micro-ripple effect applied to the membrane. At 0, the surface is smooth. At higher values, a subtle warping makes the wall feel organic and alive rather than geometric. This is cosmetic but contributes significantly to the somatic quality of enclosure.

### 5.3 Breathing / Contraction

The sphere's diameter oscillates by a configurable percentage (default 3–8%) in sync with the binaural beat frequency. This is the core somatic channel unique to the bubble architecture. The contraction is smooth (sinusoidal or ease-in-out), never abrupt. During peak conditioning phases, the contraction can intensify and optionally sync to a musical meter (every 4th or 8th beat) for a stronger rhythmic squeeze. The policy engine caps maximum contraction at 12% regardless of session parameters to prevent claustrophobic response.

### 5.4 The Horizon Element

A single geometric element (ring, point, or line) at the center of the user's visual field, pulsing at the beat frequency. This carries over directly from the original void design. In the bubble architecture, the horizon element serves as the focal anchor during deep phases when the membrane is transparent and there's nothing else to fixate on. It's the visual equivalent of the drone in ambient music — always present, rarely the focus, but structurally essential. The element fades out as the membrane becomes opaque and content layers take over as the primary visual input.

---

## 6. The Two Registers

The bubble supports two distinct experiential registers that the conductor or agent can blend between without breaking the sense of enclosure. These are not modes in the code; they are named archetypes for design discussion. In the runtime, they're just points along the diameter × opacity × content_intensity parameter space.

### 6.1 Ganzflicker Register

The membrane is invisible or near-invisible. The primary experience is the instrument — full-field phase-synchronized flicker, pure and unadorned. No affirmations, no images, no spirals. Just the raw light pulsing at the exact beat frequency. The wall has a very subtle liquid sheen and micro-ripples so it still feels alive and pressing in, but the focus is 100% on the flicker itself. Breathing/contraction is gentle and slow (2–4% diameter change) — enough to feel the membrane hugging you but not distracting from the ganzflicker effect. Spatial audio carrier sits right on the inner wall, so the binaural beat feels like the bubble itself is vibrating.

This register is for pure entrainment sessions, GENUS protocols, or deep theta/delta work where the brain should have nothing to "read" except the light itself. It corresponds approximately to the original void mode, but with the enclosing geometry already in place.

### 6.2 Write Layer Register

The membrane becomes the active delivery surface for everything the session contains:

- **Veil affirmations** scroll and flow across the curved inner surface like they're being etched into the membrane.
- **Spirals** emanate from the wall inward or splash outward and ripple across it.
- **Shadows and center-text flashes** project as large, distorted glyphs that hit the membrane and linger.
- **Background images** from the session are texture-mapped onto the wall, warped by the curvature so they feel like they're being physically pressed into you from every direction.

The bubble tightens noticeably (diameter shrinks toward 2.2–2.6m) and the breathing becomes more insistent — sharper contractions on every strong beat, as if the bubble is actively squeezing the conditioning into you. The wall can pulse between translucent and near-opaque in time with the flash duty cycle, so moments of clarity alternate with total flooding.

This register is for full conditioning sessions, work windows, and integration phases where the goal is overwhelm and the content delivery *is* the point. It corresponds approximately to the original stage mode, but with spherical rather than cylindrical geometry.

### 6.3 Blending

Because the bubble is a single container with continuous parameters, the transition between registers is just a slow shift in membrane properties over 15–30 seconds. The agent/conductor can fade from ganzflicker → write layer as the session deepens, or keep it mostly clean with occasional "write bursts" where affirmations and images flare across the membrane for 8–12 seconds before fading back to flicker. The user never leaves the bubble; they feel it change *how* it's working on them.

---

## 7. The Experience Arc

### 7.1 Prelude

The bubble starts large (5.0–5.5m diameter) and nearly transparent. The horizon element is visible and slowly breathing. Color temperature is warm (4500K equivalent, amber-shifted). Spatial audio carrier is anchored *on the bubble wall itself* — the binaural beat feels like the membrane is vibrating around the user, but faintly, as if the bubble is still waking up. First affirmations and images begin to drift across the inner surface like oil on water — subtle at first, then slightly more present as prelude transitions to induction. The membrane is present but not assertive. The user feels enclosed but not trapped.

### 7.2 Induction / Deepening

The bubble diameter shrinks slowly over 60–90 seconds toward 2.8–3.2m. Membrane opacity increases gradually. Color temperature cools steadily through induction — ~10° per minute during active induction — perceptible only in retrospect. The breathing/contraction amplitude increases and syncs more tightly to the beat frequency. The horizon element begins to fade as the membrane takes over as the primary visual surface. Spatial audio carrier begins slow orbits around the bubble wall, so the beat feels like it's circling the user, pressing from every side in sequence rather than from a fixed direction.

### 7.3 Peak Conditioning / Work Window

The bubble stabilizes at its tightest comfortable diameter (2.2–2.6m). The membrane is at its most active. The write layer register is fully engaged: affirmations, images, spirals, and flashes all project onto the curved inner wall in layered, overlapping cycles. The breathing can intensify to peak amplitude, with optional "pulse waves" where the bubble contracts sharply on every 4th or 8th beat and then relaxes, reinforcing the conditioning rhythm. The wall can briefly go almost fully opaque for short bursts, flooding every visual channel with content, then clear again for a breathing moment before the next wave. Color temperature reaches its warmest point (2000K, deep amber) at very low luminance during deepest theta/delta phases — the space glows like dying embers, not clinical blue.

### 7.4 Emergence

The most emotionally significant moment in the session, and the most neglected in most VR experiences. A dedicated 2–3 minute emergence arc:

1. The instrument begins cooling its frequency — not stopping, slowing.
2. Luminance rises uniformly across the entire membrane — no directional bias, no dawn metaphor. The sphere has no canonical orientation (§2), and the user may be reclined or tilted. Uniform luminance rise preserves orientation independence while still communicating "the session is ending."
3. The bubble very slowly expands back toward its original loose diameter. As it grows, the membrane becomes translucent again and the horizon element reappears.
4. Conditioning content dissolves into the membrane and thins as the bubble expands, leaving the user with the feeling that everything has been absorbed.
5. Final 20–30 seconds: the bubble becomes almost invisible, giving the user back the real-world room as a soft, safe return.

The agent already knows the session is ending. It can narrate this transition via TTS if configured. The spatial arc and the agent voice should feel coordinated, not concurrent. This is handled by timing — not new infrastructure.

---

## 8. Spatial Audio

This is the highest-priority VR feature and the one most likely to change the experience fundamentally. Binaural beats on headphones feel like they are happening *inside your skull*. The same frequencies spatialized at 2–3 meters ahead, at ear height, feel like they are happening *in the room*. These are categorically different perceptual events. The environmental version is less cognitively localized and easier to stop resisting.

### 8.1 Carrier Spatialization

OpenAL or the platform's spatial audio API (Windows Sonic, Steam Audio) for carrier placement. The binaural beat mathematics stay unchanged — left/right frequency offset is preserved. What changes is the *apparent source location*: instead of both channels emanating from the headphone drivers, they appear to come from a point or volume in space ahead of the user. In the bubble architecture, the carrier source is positioned on the inner surface of the sphere itself, so the beat feels like the membrane is vibrating. During induction and peak phases, the source can orbit slowly around the wall, creating a sensation of the beat circling the user.

Beat frequency modulation can be implemented as a subtle slow LFO on the room's reverb decay — the "room weather" effect. Not a noticeable pulse; a slow breath. The reverb decay is tied to the bubble's contraction cycle, so the audio space tightens and loosens in sync with the visual enclosure.

### 8.2 The Bubble's Voice — Ambient Soundscape

Beyond the carrier, the bubble itself has a sound. This is not music. It is room tone — the acoustic signature of the space you're inside.

**The drone.** A very low-frequency pad (30–80 Hz fundamental) that responds to bubble state. Tighter diameter = slightly higher pitch and more harmonic content. Larger diameter = lower, simpler. The drone is only audible when the pink noise engine is off or at very low volume — which is rare, given pink noise's established benefits. When noise is active, the drone is masked and effectively silent. This is fine: the drone is the bubble's voice when the room is quiet, not a constant presence that competes with noise. It's most valuable during ganzflicker register (pure flicker, low noise) and emergence (noise fading out).

**Contraction sound.** The breathing/contraction cycle modulates the drone's amplitude envelope (when audible) and the pink noise's filter slope (always). Contracting = noise subtly shifts toward warmer/browner spectrum. Expanding = shifts back toward pink baseline. This ties the visual contraction to an auditory color shift regardless of whether the drone is masked. The modulation is subtle — a few dB of spectral tilt. If the user consciously notices it, it's too strong.

**Emergence soundscape.** The emergence arc (§7.4) has the strongest visual design in the document. The sound should match: the drone fades over the 2–3 minute arc. The membrane texture dissolves. Reverb decay lengthens as the bubble expands, giving the space a sense of opening up. By the final 20–30 seconds, the only sound is the carrier (if still active) and whatever ambient sound the headset's passthrough picks up. The transition from enclosed acoustic space to open air should feel like a door opening, not a switch flipping.

### 8.3 Agent Voice — The Bubble Speaks

The agent's voice is always omnipresent — never localized to a point in space. It comes from everywhere simultaneously. This is achieved by playing TTS audio without spatial positioning (head-locked stereo, like normal headphone audio) while the bubble's ambient soundscape is spatialized around the user.

The agent doesn't have a body or a location. The agent IS the bubble — the enclosure speaks. A localized voice would imply the agent is a person standing somewhere in the room, which breaks the spatial metaphor. The bubble is the agent. The bubble's voice is everywhere because the bubble is everywhere.

This is permanent — not just during sessions. If the agent speaks during emergence, or between sessions, or in console conversation while the headset is on, the voice remains omnipresent. The bubble doesn't become a person when it expands. It remains what it is.

### 8.4 Fallback

If spatial audio initialization fails, fall back to the existing binaural engine unchanged. This is not a blocking dependency for any other VR feature. The bubble renders identically with or without spatialized audio; the somatic quality is reduced but the architecture is unaffected.

---

## 9. `live_control.json` Schema (VR Additions)

All written via `patch_live` only. Existing `vr_render_mode`, `vr_*_hz`, `vr_*_depth`, `vr_vection_*`, `vr_headset_enabled`, and `vr_safety_kill` remain authoritative for the instrument and are not replaced. The choreography mode enum from the original design (void, prelude, instrument_focus, balanced, integration, shell) is **removed**. Its function is distributed across the continuous parameters below.

### 9.1 Bubble Geometry

| Key | Type | Description |
|---|---|---|
| `vr_bubble_enabled` | bool | Master for bubble geometry. False falls back to flat Ganzfeld. |
| `vr_bubble_diameter_m` | float | Current diameter in meters. Range 2.0–6.0. Driven by policy from conductor phase. |
| `vr_bubble_diameter_target_m` | float | Target diameter. Policy writes this; renderer lerps toward it over `vr_env_ramp_s`. |
| `vr_bubble_breathing_pct` | float | Contraction amplitude as % of diameter. Range 0–12. Default 4. |
| `vr_bubble_breathing_sync` | str | `beat` / `meter_4` / `meter_8` / `off`. What the breathing syncs to. |

### 9.2 Membrane

| Key | Type | Description |
|---|---|---|
| `vr_membrane_opacity` | float 0–1 | Wall visibility. 0 = invisible (ganzflicker register). 1 = fully opaque (write layer register). |
| `vr_membrane_opacity_target` | float 0–1 | Target opacity. Policy writes; renderer lerps. |
| `vr_membrane_content_intensity` | float 0–1 | Strength of projected content (affirmations, images, spirals) on the membrane. |
| `vr_membrane_distortion` | float 0–1 | Liquid micro-ripple effect. 0 = smooth geometric surface. 1 = maximum organic warping. |

### 9.3 Environment

| Key | Type | Description |
|---|---|---|
| `vr_env_color_temp` | float 1000–10000 | Color temperature in Kelvin. Driven by policy from conductor phase. |
| `vr_env_luminance` | float 0–1 | Overall environment brightness. Near 0 during deep phases. |
| `vr_horizon_element` | str | `ring` / `point` / `line` / `none`. Geometry of the single horizon reference. |
| `vr_env_ramp_s` | float | Seconds to lerp between environment states. Default 30. |

### 9.4 Spatial Audio

| Key | Type | Description |
|---|---|---|
| `vr_spatial_audio` | bool | Enable spatial source positioning for binaural carrier. |
| `vr_audio_source_dist_m` | float | Distance of apparent audio source. Default 2.5. |
| `vr_audio_orbit_rate` | float | Orbital speed of source around bubble wall in degrees/sec. Default 5. |
| `vr_room_weather` | float 0–1 | Intensity of reverb-modulation beat sync. 0 = off. |

### 9.5 Policy / Safety

| Key | Type | Description |
|---|---|---|
| `vr_shell_active` | bool | Universal eject. Sets opacity=0, luminance=0.4, diameter=5.0, breathing off. One key, one clear semantic. |
| `vr_policy_caps_enabled` | bool | Whether the policy engine is actively enforcing combined envelope. |
| `vr_effective_photic_depth` | float | Policy-adjusted photic depth. May differ from raw `vr_photic_depth` if caps are active. |
| `vr_effective_rivalry_depth` | float | Policy-adjusted rivalry depth. |

### 9.6 HUD (W5+)

| Key | Type | Description |
|---|---|---|
| `vr_hud_enabled` | bool | |
| `vr_hud_minimal` | bool | If true, kill + status only. Always true during instrument-dominant phases. |
| `vr_hud_distance_m` | float | Distance from head origin. |

---

## 10. Policy Engine

The policy engine reads conductor phase, SQI, and raw instrument depths. It writes target values for `bubble_diameter`, `membrane_opacity`, `env_color_temp`, and `env_luminance`. The renderer lerps toward targets over `vr_env_ramp_s`. All transitions are smooth; no perceptual pop.

### 10.1 Phase-to-Parameter Mapping

| Conductor Phase | Diameter | Opacity | Color Temp | Luminance |
|---|---|---|---|---|
| PRELUDE | 5.0–5.5m | 0.05–0.1 | 4500K (warm) | 0.3–0.4 |
| INDUCTION | 3.5–4.0m | 0.15–0.3 | 3500K (cooling) | 0.15–0.25 |
| DEEPENING | 2.8–3.2m | 0.3–0.5 | 2500K (neutral) | 0.05–0.15 |
| WORK_WINDOW | 2.2–2.6m | 0.6–0.9 | 2000K (deep amber, near-dark) | 0.05–0.1 |
| EMERGENCE | 5.0–5.5m | 0.0–0.1 | 4500K (warm) | 0.3–0.5 |
| Shell (safety) | 5.0m | 0.0 | 5000K (neutral) | 0.4 |

### 10.2 Combined Envelope

The policy engine enforces a combined intensity ceiling: `instrument_depth × membrane_content_intensity × audio_intensity ≤ threshold_curve` defined in `vr_safety.py`. When the combined value approaches the ceiling, the policy engine reduces the most aggressive parameter first (typically membrane content intensity, since it's the newest and least safety-critical channel). The instrument is never reduced below its safety-minimum duty cycle. This ensures that the bubble's visual intensity and the flicker's neurological intensity cannot both peak simultaneously.

### 10.3 Writer Priority

Three agents can write to bubble parameters: the conductor (phase-driven), the agent (responsive to user state), and the user (manual override via control panel). The priority rule is: **user > agent > conductor**. If the user manually sets a diameter, the conductor doesn't override it. If the agent writes a safety retreat (shell), it takes precedence over the conductor's phase hint. All writes go through `patch_live`; there is no separate control channel.

---

## 11. Content Projection on the Membrane

The existing desktop visual layers (veil affirmations, spirals, shadows, center-text flashes, background images) are designed for flat or near-flat rendering. Projecting them onto a curved inner surface at 1–1.5m distance requires deliberate rendering choices:

### 11.1 Text

Affirmations scrolling across the curved inner surface can't be rendered as flat text and UV-mapped without distortion. Text at the edges of the sphere is stretched and text near the equator is compressed. Two solutions exist: corrected UV mapping that pre-distorts the text to appear uniform on the curved surface, or pannable text quads that always face the user regardless of sphere curvature. The latter is simpler and produces more readable text; the former is more immersive but requires a custom text layout engine. For W1–W2, pannable text quads are recommended. The text appears on a rectangular surface that floats just inside the membrane and rotates to face the head pose. This is readable at any distance and avoids the distortion problem entirely.

### 11.2 Images

Background images from the session's slideshow can be texture-mapped directly onto the sphere's inner surface. The curvature and slight distortion actually enhance the effect — images feel like they're being pressed into the user rather than displayed for viewing. No correction is needed; the warping is a feature, not a bug. The image occupies a configurable arc of the sphere's surface (e.g., 90° of the forward hemisphere) rather than the full sphere, to avoid the image wrapping behind the user where it can't be seen.

### 11.3 Spirals and Geometric Effects

Spirals can render in two modes: emanating from the wall inward toward the user, or pulsing outward from the center and splashing against the membrane. The existing `spirals_opengl.py` renders to an FBO that can be texture-mapped onto the sphere. The afterimage/decay system works identically on the curved surface. No fundamental change to the spiral rendering pipeline is required — the FBO output is simply mapped to a sphere instead of a quad.

### 11.4 Flicker / Ganzfeld

The instrument (photic flicker) renders as a full-sphere color modulation, identical to the existing Ganzfeld mode but applied to the sphere's inner surface instead of a flat quad. This is the simplest projection: no UV concerns, no text readability issues, just pulsing color across the entire visual field. The sphere's geometry ensures total field coverage with no peripheral gaps.

---

## 12. Conductor Integration

Phase enter/exit writes target bubble parameters via `patch_live`. This is ~30–50 lines in `session/conductor.py` (each of the 9 arc templates needs bubble parameter targets added to its phase definitions), not a separate wave. The conductor doesn't write choreography modes; it writes target diameter and opacity values corresponding to its current phase. The renderer lerps toward those targets over `vr_env_ramp_s` seconds. The mapping from phase to target values is defined in the policy engine's phase-to-parameter table (Section 10.1).

Bubble parameters are not added to the timeline lock list by default. They are conductor-owned unless the user explicitly overrides via the control panel. User overrides take priority but don't persist across phase transitions unless explicitly dragged into the timeline.

---

## 13. Agent Integration

The agent's spatial references should be grounded in actual state, not hallucinated:

- Reference the environment only when bubble parameters *actually* changed ("the field has softened," "things are tightening").
- Offer shell activation in response to "too intense" — write `vr_shell_active: true` via `patch_live`, don't merely suggest.
- Never re-enable deep instrument after `vr_safety_kill` without explicit user reset.
- Write brief content bursts by temporarily raising `vr_membrane_content_intensity` for 8–12 seconds, then lowering it. The user never needs to know this was agent-initiated; they just feel the wall flare and recede.

---

## 14. Safety and Comfort

- **Combined envelope:** instrument depth × membrane content intensity × audio intensity is bounded by curves in `vr_safety.py`. Extended to cover the new membrane and breathing dimensions.
- **Shell state:** `vr_shell_active` is the universal eject button. Transparent bubble, grey instrument, luminance 0.4, breathing off. One key, one clear semantic. The user can always reach it from the HUD or voice command.
- **Breathing cap:** maximum contraction is 12% of diameter regardless of session parameters. This prevents the bubble from contracting to a claustrophobically small size, even if the session script requests it.
- **Void default:** the safest VR state (large, transparent bubble) is also the most entrainment-compatible. Complexity is opt-in per session, not default-on.
- **Pareidolia awareness:** at high `vr_membrane_distortion` values (§22.2), the brain’s pattern-recognition system will find faces, words, and images in the membrane noise during deep states. For most users this is a desirable emergent property. For users who report negative membrane experiences, the agent should auto-reduce `vr_membrane_distortion` to 0. Distress signals (HR spike + depth crash detected by the conductor) should trigger automatic distortion reduction as part of the safety retreat, alongside the existing combined envelope response.
- **HMD comfort:** nothing in the environment should require sustained focus or tracking. All motion is slow, rhythmic, and peripheral. The user's eyes should be able to defocus entirely during deep phases.
- **Vergence-accommodation:** the bubble's instrument mode (full-field flicker) is less affected than detailed scene geometry would be. Another reason the membrane defaults to invisible and content is projected rather than rendered as 3D objects.

---

## 15. Implementation Roadmap

| Wave | Deliverable | Gate | What the User Experiences |
|---|---|---|---|
| W1 | Bubble geometry + void register + horizon element + spatial carrier + ambient drone | Ship | Enclosing darkness with a breathing ring, beat-synchronized contraction, audio from the walls |
| — | **Validation gate:** run real sessions; confirm headset deepens the work | Must pass before W2 | |
| W2 | Membrane opacity + content projection (text quads, images on inner surface) + color temp curve driven by phase + breathing sync options + transition designs (§23) + smoke fill (§22.1) | W1 validated | Affirmations floating just inside the walls, images pressed onto the membrane, color shifting with depth, smoke giving the space atmospheric depth, every phase transition felt but not consciously noticed |
| W3 | Policy engine (diameter/opacity curves from phase) + combined safety envelope + conductor hooks (10 lines) + shell state + between-session continuity (§20) | W2 stable | The bubble automatically tightens and loosens with the session arc; safety caps prevent simultaneous overwhelm; returning to the headset feels like returning to the same space |
| W4 | Full write layer register + spiral projection + pulse waves + agent content bursts + emergence soundscape (§8.2) + agent voice spatialization (§8.3) | W3 confirmed value | The full conditioning experience: spirals, affirmations, images, flashes all projected onto the enclosing wall, with the bubble's voice as a constant ambient presence |
| W5 | Gaze zones (§21.2) + local voice keywords (§21.3) + hand tracking support (§21.4) | W4 stable | Invisible HUD that materializes on demand, voice-activated safety, hands for users who can use them |
| W6+ | Eye/face tracking measurement integration (§21.5) + accumulation features (§20.2) + additional fill media (§22.1) + pareidolia-optimized distortion (§22.2) | Only if W5 proves the platform works | Measurement-rich depth estimation, a bubble that remembers, fluid fills and micro-bubbles, the membrane as a canvas for the user's own pattern recognition |

The validation gate is non-negotiable. W1 exists to answer the question: does being inside the bubble deepen the work? If the answer is no, subsequent waves aren't built. The bubble at void register is the minimum viable experience, and it's intentionally the correct environment for theta/delta sessions even if no further waves are ever implemented.

---

## 16. Open Questions

**1. Does the headset actually deepen the work?**

This is empirical. W1 exists to answer it. All subsequent investment depends on the answer being yes. If the answer is no, the bubble architecture still produces a cleaner void mode than the original flat-Ganzfeld approach, so the work isn't wasted even if VR is abandoned as a platform.

**2. Color temperature canonical mapping.**

The existing desktop visual display uses `bg_color_temp` as a normalized 0–1 slider mapped to a tint shift, not actual Kelvin. If VR is going to drive color temp from conductor phase in Kelvin, there should be a single canonical mapping that both desktop and VR consume. Two different "color temp" concepts that happen to share a name will cause confusion. Resolve before W2.

**3. Audio subprocess independence.**

Currently audio lives in the desktop process; it must stay alive for any session. If VR-only sessions (no desktop) are ever desired, audio needs its own lightweight subprocess. The architecture already supports this: the StateServer IPC pattern (TCP 6789, single-writer daemon serializing all state mutations) means audio can run as another StateServer client alongside the VR renderer, conductor, and agent. The question is "when," not "how." Don't design around this assumption yet — just don't close the door architecturally.

**4. Which bubble params are user-lock eligible?**

Proposal: none by default (conductor-owned). User can override via control panel but overrides don't enter the timeline lock list unless explicitly dragged in. Decide before W3.

**5. Text projection strategy.**

Pannable text quads (simpler, more readable) vs corrected UV mapping (more immersive, harder to implement). Recommendation is quads for W1–W2, with UV mapping as a W4+ optimization. Validate with real users first.

---

## 17. Success Criteria

- A full induction session in the headset produces measurably different subjective depth than the same session on desktop. (W1 validation.)
- Phase transitions are perceptible in retrospect but not consciously noticed during the session. (W2.)
- The combined policy engine prevents instrument, membrane, and audio all peaking simultaneously without the user touching any sliders. (W3.)
- The emergence arc feels like waking up, not like an app closing. (W2.)
- The shell state provides immediate perceptible relief within one second of activation. (W3.)
- A new user can complete a session in the headset with zero control panel interaction after starting it on the desktop. (W5.)

---

## 18. Relation to Somatic Palettes and the Interference Graph

The Interference Graph — the proposed ImGui UI for composing somatic palette chords (cross-modal frequency offsets producing neural beat frequencies) — is a desktop *composition* tool. It produces frequency assignments for visual, audio, haptic, and VNS channels. The bubble is the VR *rendering* of those assignments. They are complementary layers, not competing designs.

When the user composes a chord in the Interference Graph (e.g., Visual 38Hz, Audio 42Hz, Haptic 40Hz), those frequencies are written to `live_control.json`. The bubble reads them. The visual channel drives the instrument's flicker frequency. The audio channel drives the binaural carrier and beat. The haptic channel is future work but the architecture accommodates it. The Interference Graph's spread knob — which pushes channels apart symmetrically around a center frequency — maps naturally to the bubble's breathing and contraction behavior: a tight chord (all channels at 40Hz) produces minimal cross-modal interference and a steady, gentle bubble. A wide-spread chord (38/40/42Hz) produces delta-frequency interference beats and a more insistent, rhythmic contraction pattern. The spread knob is effectively a control for how aggressively the bubble breathes.

This connection should be made explicit in the ImGui panel: the Interference Graph's spread parameter drives `vr_bubble_breathing_pct` by default, so that composing a wider chord automatically intensifies the somatic pressure. The user *feels* the chord they composed, not just hears and sees it.

The spread→breathing link follows standard writer priority (§10.3): **user > agent > conductor**. The spread knob has a direct user control in the Interference Graph UI. When the user adjusts it, they are explicitly overriding the conductor's phase-driven breathing target. If the user hasn't touched the spread knob, the conductor's phase mapping owns `breathing_pct`. The agent can override the conductor but not the user. All writes go through `patch_live` — no ambiguity about who wrote last.

---

## 19. Legacy Protocols in the Bubble

All four existing VR render modes translate to the bubble without modification. The sphere is geometry — the per-eye framebuffer rendering happens before texturing. Each eye sees the sphere's inner surface through its own luminance pattern.

| Mode | In the Bubble | Interaction with Membrane |
|------|---------------|--------------------------|
| `ganzfeld` | The sphere IS ganzfeld. Full field coverage by nature. No flat quad needed. | Membrane is invisible by default in ganzfeld. Can optionally carry faint texture. |
| `photic` | Full sphere bilateral flicker. Identical stimulation, spherical coverage. No peripheral gaps. | Membrane opacity controls whether content layers appear during photic. Low opacity = pure flicker. |
| `rivalry` | Each eye sees the sphere with different luminance modulation. The brain still can't fuse them. Rivalry works identically on curved surfaces. | Transparent membrane = pure rivalry. Opaque membrane = rivalry + content. The two channels are independent. |
| `dichoptic_ssvep` | Same as rivalry but measurement-grade. The sphere geometry doesn't affect SSVEP detection — the detector reads EEG, not visual geometry. | Typically transparent membrane during measurement. No content interference. |

The key architectural point: **the instrument (per-eye flicker) and the membrane (content surface) are orthogonal channels.** The user can experience rivalry through a transparent bubble (pure ganzflicker register), or rivalry with affirmations scrolling on the membrane, or rivalry with images pressed onto the wall during peak conditioning. The session designer or agent controls the blend.

What changes meaningfully: in the bubble, rivalry has a spatial quality it lacks on flat displays. Each eye's competing pattern wraps around the user. The dominance switching feels like the space itself is changing, not just a flat image. This is a qualitative enhancement, not a functional one.

---

## 20. Between-Session Continuity

### 20.1 Persistent State

The bubble starts where it left off. Not reset to a default prelude state — at the parameter values from the end of the last session.

If the last session ended normally (emergence completed), the bubble starts in its post-emergence configuration: large diameter (~5.0m), transparent membrane, warm color temp (~4500K), luminance ~0.3. The user puts on the headset and they're back in the same space — warm, open, quiet. The new session gradually reshapes from there.

If the last session ended abnormally (crash, safety kill, manual stop), the bubble resets to prelude defaults. The user should never return to a dangerous or intense state without choosing to.

Implementation: `vr_display_runner.py` writes current bubble parameters to `user_settings.json` under a `vr_bubble_last_state` key **periodically (every 30s) during the session**, not just on exit. On startup, it reads these and uses them as initial values instead of hardcoded defaults, unless `vr_safety_kill` was True at exit.

The periodic write also solves the lerp crash recovery problem (§9): if the renderer crashes mid-lerp between `vr_bubble_diameter_m` and `vr_bubble_diameter_target_m`, the last periodic snapshot provides a recent `diameter_m` to resume from rather than snapping to a stale target or hardcoded default.

### 20.2 Future: Accumulation

The persistent-state model is the simplest form of continuity. If it feels right, later waves can layer on:
- Membrane patina: a subtle texture that develops over sessions, making the space feel lived-in
- Horizon evolution: the horizon element gains complexity with session count
- Somatic palette memory: the bubble's default color temp shifts toward the user's most effective chord color

None of these are designed yet. The persistent state is the foundation.

---

## 21. In-Headset UI — Gaze and Voice

### 21.1 Two-Tier Architecture

The agent's LLM cycle takes 2–5 seconds. This is fine for conversation but unacceptable for safety-critical actions. The UI splits into two tiers:

**Immediate tier** — gaze-controlled, writes directly to `live_control.json`, no agent involved, one-frame response.

**Conversational tier** — voice-controlled, processed by the agent, natural latency.

### 21.2 Gaze Zones

The HUD is invisible by default. It only materializes when the user's gaze drops to the bottom periphery for >0.5s. During trance, there is zero visual clutter. The controls exist in peripheral space and only appear when summoned.

| Gaze Target | Dwell Time | Action | Visual Feedback |
|-------------|-----------|--------|-----------------|
| Bottom center | 1.5s | Shell state (universal eject) | Circle fills as you dwell |
| Bottom left | 1.0s | Intensity down 10% | Left arrow fills |
| Bottom right | 1.0s | Pause/resume | Pause icon fills |
| Bottom far-left | 1.0s | Mute/unmute audio | Speaker icon fills |

When the user looks down, the zone icons fade in at ~30% opacity. As the user fixates on one, it brightens and a circular progress indicator fills around it. Releasing gaze before the dwell completes cancels the action. The progress indicator makes the interaction feel physical and intentional — accidental triggers are unlikely.

The gaze zones are positioned in the bottom 15° of the visual field, well below natural resting gaze. They cannot be activated by normal forward-looking behavior.

Implementation: requires eye tracking (OpenXR `XR_EXT_eye_gaze_interaction`). For headsets without eye tracking, a head-orientation fallback activates the zones when the user tilts their head down for the dwell duration. Less precise but functional.

### 21.3 Voice Commands

Two processing paths:

**Local keyword detection** — a lightweight wake-word engine (e.g., Porcupine, or a simple spectral matcher) running in the VR subprocess. Catches: "stop", "pause", "shell", "too much", "too intense", "quieter". These map directly to `live_control.json` writes with zero LLM round-trip. Response time <200ms.

**Agent conversation** — everything else routes through the existing agent voice input pipeline. Note: with a local LLM, response time is typically 20–60 seconds depending on prompt size and output token count. This is acceptable for conversation ("change the session direction", "what phase are we in?") but reinforces why safety-critical actions must never depend on the agent. The user asks a question, the bubble answers when it's ready. The conversation is slow and contemplative — which matches the state the user is in.

The local keywords are the safety net. The user should never need to wait for the agent to process a safety-critical request.

### 21.4 Hand Tracking (Personal Enhancement)

Some users can use their hands during deep states. Hand tracking provides richer input for those users:

- Pinch to dismiss current affirmation/character
- Slow wave = pause
- Point and hold = direct attention (agent notes what the user is looking at)
- Fist = shell (intuitive "close" gesture)

Hand tracking is not designed as a W1 dependency. It's a personal enhancement layer that activates when the hardware supports it and the user has indicated capability. The gaze + voice tier must work completely without hands.

### 21.5 Face and Eye Tracking — Measurement, Not Control

Face tracking and eye tracking are not primary input channels for VR control. Their value is measurement:

**Eye tracking:**
- Gaze direction for the gaze zones (above) — this IS the input mechanism
- Pupil dilation as a valence/arousal signal (already planned in Bible Ch.8)
- Fixation patterns during encoding: does the user fixate on characters? For how long?
- Saccade velocity as a depth proxy — reduced saccade frequency correlates with deep states

**Face tracking:**
- Blink rate as a drowsiness/depth signal — complements EEG for sleep onset detection
- Microexpressions during conditioning: positive valence responses to specific content
- Jaw relaxation as a depth indicator — complements IMU stillness

These are research signals, not control inputs. They feed into the conductor's depth estimation and the agent's state summary. They make the system's model of the user richer without requiring the user to do anything.

---

## 22. Ambient Life — The Bubble Fill

Beyond vection (forward optic flow), the bubble's interior should feel inhabited. Generic floating particles are done to death in VR. The bubble deserves something that reinforces its identity as an enclosing, organic space.

### 22.1 Fill Media

The bubble's interior can be filled with various media, selected by the session or agent. These are rendering modes for the bubble's interior volume — the space between the user and the membrane. A session might use one fill throughout, or transition between fills as phases change.

**Smoke / haze.** A volumetric fog effect at very low density. The user sees soft, slow-moving smoke wisps drifting through the space, catching the color temperature and beat pulse. Implementation: screen-space raymarching through a 3D noise field, animated at <0.5 Hz so it barely moves. The haze gives the space atmospheric depth — near objects (the horizon element, text quads) are crisp, while the membrane at distance is slightly softened by the fog. During deep phases, the haze thickens slightly, making the space feel compressed. During emergence, it clears.

**Fluid traces.** Thin, luminous filaments that drift through the interior like ink in water. These are not particles — they're connected curves (spline segments) that slowly evolve and dissolve. The traces respond to the breathing cycle: they drift inward during contraction, outward during expansion. Implementation: 10–20 short spline segments, each with a slowly changing control point, rendered with a soft glow shader. The effect is like being inside a lava lamp, except the lava is thin and translucent. The traces respond to the beat — their brightness pulses faintly.

**Micro-bubbles.** Tiny translucent spheres (2–4mm apparent size) that drift upward through the interior. Unlike generic particles, these have volume — they catch and refract light, they have a subtle specular highlight, they behave like physical objects in a fluid. They drift slowly upward during normal phases, drift faster during contraction (as if the bubble is squeezing them up), and scatter during fractionation transitions. Implementation: instanced sphere geometry with a glass shader, 30–80 visible at a time. The user's aphantasia is no barrier — these are real visual objects, not imagined.

**Empty.** No fill. Just the membrane, the horizon element, and the instrument. This is the default for ganzflicker register — pure, clean, nothing to look at except the light itself.

The fill media should be selectable as a session parameter (`vr_bubble_fill: "smoke" | "fluid" | "bubbles" | "none"`) and adjustable by the agent during the session. Different fills suit different registers:
- Smoke → ganzflicker register (adds depth to the void without distraction)
- Fluid traces → write layer register (organic, alive, content feels like it's flowing through the space)
- Micro-bubbles → lighter sessions, maintenance phase (gentle, playful, keeps the space feeling alive during downtime)
- Empty → the purest experience, when the session or user wants nothing competing for attention

### 22.2 Membrane Surface Detail

At high distortion values, the membrane's micro-ripple should occasionally resolve into briefly readable patterns — interference fringes, moiré, standing wave patterns. These are not intentional content; they are artifacts of the distortion shader that the visual system tries to read. During deep states, the brain's pattern-recognition system will find faces, words, images in the noise. This is pareidolia-as-feature: the user's own mind generates content from the membrane's texture, which is more personally relevant than anything the system could project.

This is not designed or controlled — it emerges from the distortion shader at high values. The doc notes it as a desirable emergent property, not a feature to implement.

---

## 23. Transitions as Design Material

The emergence arc (§7.4) is the strongest piece of experiential design in this document. Every phase transition should receive the same care.

### 23.1 Transition Principles

- Transitions register in retrospect, not in the moment. The user should not be able to pinpoint when the environment changed — only that it has changed.
- Every parameter change that defines a phase transition completes over `vr_env_ramp_s` seconds (default 30). Nothing snaps.
- The most perceptible transitions should be the ones that matter most: entering deepening, entering work window, beginning emergence.
- The least perceptible transitions should be the routine ones: subtle adjustments within maintenance.

### 23.2 Key Transition Designs

**Prelude → Induction** (the first contraction)
The bubble is large and transparent. Over 60–90 seconds, the membrane begins to materialize — not suddenly appearing, but gradually becoming faintly visible, like condensation forming on glass. The horizon element's pulse becomes slightly more insistent. The carrier volume rises 2–3 dB. Color temperature cools by 200K. None of these are individually noticeable. Together, the space feels like it's starting to pay attention to you.

**Induction → Deepening** (the embrace)
The diameter decrease that defines this transition should feel like the bubble settling around the user, not shrinking away from them. The contraction amplitude increases in steps — 2% → 3% → 4% over the transition period, each step taking ~10 seconds. The drone gains a second harmonic. The horizon element begins to fade. By the end of this transition, the user is enclosed, and they didn't notice it happening.

**Deepening → Work Window** (the squeeze)
This is the most aggressive transition. The membrane opacity ramps from ~0.4 to ~0.7 over 30 seconds. Content layers begin projecting. The carrier source starts orbiting. The contraction reaches its peak amplitude. This transition should feel like the bubble actively engaging — shifting from "holding" to "working." It's the only transition where the user might consciously notice the change, and that's intentional: the work window is where the conditioning content is densest, and a mild orienting response helps lock attention.

**Work Window → Emergence** (the release)
The inverse of the squeeze, but slower. The membrane thins over 45–60 seconds. Content layers dissolve — affirmations fade mid-scroll, images soften, spirals unwind. The contraction amplitude decreases in steps back toward 2%. The carrier volume drops. The drone loses harmonics one by one. This transition says "the work is done" before the agent ever speaks it.

### 23.3 Fractionation Transitions

Fractionation cycles (emerge → hold → re-induce → deep) should be visible in the bubble as deliberate, rhythmic expansions and contractions beyond the breathing cycle. During EMERGE, the bubble expands 0.3–0.5m. During REINDUCE, it contracts back. The membrane opacity follows: slightly more transparent during EMERGE, slightly more opaque during REINDUCE. The user experiences the fractionation rhythm as a physical pulse of the space around them.

The bubble’s fractionation behavior should consume the timing constraints from the fractionation state machine (Bible Ch.4 Addendum A), which specifies EMERGE/HOLD/REINDUCE phases with depth triggers, cycle caps, and minimum hold durations. The bubble’s expansion/contraction maps to those phases rather than operating on its own independent timing — otherwise two fractionation systems can drift out of sync.
