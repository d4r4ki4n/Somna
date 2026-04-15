# FBO Trail Decay and Depth Cueing

Bible Ch.8 Â§Subliminal in Research Reference Series. Authored by Research (External Research Collaborator), March 2026.
Cross-references: Bible Ch.8 Â§FBO (Fractionation), Bible Ch.2 Â§SEF95 (SEF95 Pipeline), Visual Layer Reference (Gap 1 of 8).

---

## Executive Summary

A ping-pong framebuffer object (FBO) lets the previous frame influence the current frame, creating visual persistence and trails. This is the single highest-leverage renderer infrastructure investment from the Visual Layer Reference (Gap 1 of 8). A single implementation gives every existing spiral style — all 14 plus Liminal — a trails mode with zero per-style code changes.

Trail decay becomes a real-time trance depth cue the agent can modulate: longer trails during deepening, sharper geometry during emergence/fractionation. Combined with Liminal's chaos axis, this creates a two-parameter visual depth space (persistence × dissolution).

**Key ROI:** Two texture allocations. One fullscreen quad pass. One new uniform. Every spiral gets trails.

---

## Perceptual Science

**Deodato & Melcher (2024):** Human visual temporal integration window is approximately 100 ms. At 144 Hz, that's ~14 frames — trail decay rates within this window produce smooth, perceptible persistence.

**Motion Aftereffect (MAE) and Aphantasia:** Trail persistence enhances MAE. For the user (extreme aphantasia), MAE is one of the few involuntary visual persistence effects available — it operates entirely bottom-up through intact V1. No top-down imagery pathway required. Trails do not create mental images; they create physical retinal/cortical persistence. This is a sensory phenomenon, not an imaginative one.

Trails extend the effective "dwell time" of each frame's spiral geometry on the retina and V1, deepening perceptual absorption without requiring voluntary imagery.

---

## ModernGL Ping-Pong FBO Implementation

### Architecture

Two offscreen textures (A and B) alternate roles each frame:
- Frame N: Render spiral to texture A → composite A (current) + B (previous) with decay → display → A becomes "previous" for next frame
- Frame N+1: Render spiral to B → composite B + A → display → swap

### Python Setup

```python
import moderngl

def _create_trail_fbos(ctx: moderngl.Context, size: tuple[int, int]):
    """Create ping-pong FBO pair for trail persistence."""
    textures = [ctx.texture(size, 4) for _ in range(2)]  # RGBA
    for tex in textures:
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    fbos = [ctx.framebuffer(color_attachments=[tex]) for tex in textures]
    return fbos, textures

trail_fbos, trail_textures = _create_trail_fbos(ctx, window_size)
trail_index = 0  # toggles 0/1 each frame
```

### Per-Frame Render Loop

```python
def render_frame_with_trails(ctx, spiral_program, composite_program,
                              trail_fbos, trail_textures, trail_index,
                              trail_decay: float):
    current_fbo = trail_fbos[trail_index]
    previous_tex = trail_textures[1 - trail_index]

    # Step 1: Render current spiral to current FBO
    current_fbo.use()
    ctx.clear(0.0, 0.0, 0.0, 0.0)
    # ... spiral render ...

    # Step 2: Composite current + previous to screen
    ctx.screen.use()
    ctx.clear(0.0, 0.0, 0.0, 1.0)
    previous_tex.use(location=1)
    trail_textures[trail_index].use(location=0)
    composite_program['u_current'].value = 0
    composite_program['u_previous'].value = 1
    composite_program['u_trail_decay'].value = trail_decay
    # ... fullscreen quad render ...

    # Step 3: Bake composited result back to current FBO for next frame's "previous"
    current_fbo.use()
    # ... render composited result back ...

    # Step 4: Swap
    return 1 - trail_index
```

### Composite Fragment Shader

```glsl
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform sampler2D u_current;   // this frame's spiral render
uniform sampler2D u_previous;  // previous frame (ping-pong FBO)
uniform float u_trail_decay;   // 0.0 = no trails, 0.85-0.98 = active range

void main() {
    vec4 curr = texture(u_current, uv);
    vec4 prev = texture(u_previous, uv);
    // max() blend: preserves bright spiral arms, lets trails fade to black naturally
    fragColor = max(curr, prev * u_trail_decay);
}
```

**Why max() not mix():** `max()` preserves bright spiral arms against the dark background and lets trails naturally fade to black — no accumulation artifacts over long sessions. `mix()` creates muddy composites where current and previous fight each other.

### Decay Rate Reference (144 Hz)

| trail_decay | Perceptual Effect | Frame Persistence | Use Case |
|------------|------------------|-------------------|----------|
| 0.0 | No trails (pass-through) | 1 frame (7 ms) | Default, legacy behavior |
| 0.85 | Short, crisp trails | ~10 frames (~70 ms) | Light trance, alert states |
| 0.90 | Medium trails | ~14 frames (~100 ms) | Moderate depth; matches temporal integration window |
| 0.95 | Long, dreamlike trails | ~28 frames (~200 ms) | Deep trance, absorptive states |
| 0.98 | Heavy smearing, painterly | ~72 frames (~500 ms) | Maximum depth, dissolution |

Formula for approximate visible persistence in frames: `−1 / ln(decay)`.

### Window Resize Handling

```python
def _resize_trail_fbos(ctx, trail_fbos, trail_textures, new_size):
    for fbo in trail_fbos: fbo.release()
    for tex in trail_textures: tex.release()
    return _create_trail_fbos(ctx, new_size)
```

Trail history is lost on resize — acceptable since trails rebuild within a fraction of a second.

---

## Depth Cueing — Agent-Driven Modulation

```python
def trance_to_trail_decay(trance_score: float) -> float:
    """Map trance depth score (0.0-1.0) to trail decay (0.0-0.98)."""
    if trance_score < 0.2:
        return 0.0  # No trails during light/alert states
    t = (trance_score - 0.2) / 0.8
    return 0.85 + t * 0.13  # Range: 0.85 to 0.98
```

### Fractionation Integration

During fractionation cycles, trail decay coordinates with Liminal chaos for a two-parameter perceptual jolt:
- **Drop phase:** Snap `trail_decay = 0.0` + `spiral_chaos = 0.05` → sharp geometry, maximum contrast with dissolved state. Entirely bottom-up V1 contrast, no imagery required.
- **Reinduction phase:** Ramp `trail_decay` from 0.0 back to depth-mapped value over 10–15 seconds. Gradual return of persistence felt as edges softening, geometry acquiring weight.

---

## live_control.json Key

| Key | Type | Range | Default | Description |
|-----|------|-------|---------|-------------|
| `trail_decay` | float | 0.0–0.99 | 0.0 | Trail persistence decay factor. 0.0 = no trails. 0.85–0.98 = active range. |

Control panel: add "Trail Decay" slider to the Spirals section (range 0–99, divide by 100 for uniform). Agent can override via `_patch_live()`. Timeline runner can set via session YAML keyframes.

---

## What Trails Unlock for Free

- Every existing spiral style (all 14 + Liminal) gets trails with no per-style code changes.
- New styles added in the future automatically inherit trails.
- `trail_decay` available to both timeline runner (YAML keyframes) and agent simultaneously.
- Trails + Liminal chaos = two-axis visual depth space (persistence × dissolution) — novel in entrainment tools.
- Combined with `u_beat_phase` arm width modulation: "breathing persistence" effect where inhale/exhale pulse leaves luminous ghosts.

---

## Performance

- VRAM: 2 × RGBA textures at render resolution = ~16.6 MB at 1080p. Negligible.
- Render cost: one trivial composite pass per frame. Well within budget even on integrated graphics.
- Fallback if needed: render FBO at half resolution and upscale. Quality loss minimal since trails are inherently soft.

---

## Implementation Priority

| Phase | Task | Dependencies |
|-------|------|-------------|
| 1 | Ping-pong FBO pair + composite shader + `trail_decay` wired to live_control.json | None |
| 2 | Trail Decay slider in control panel Spirals section | Phase 1 |
| 3 | Agent-driven depth cueing via `trance_to_trail_decay()` | Phase 1 + stable SEF95 |
| 4 | Fractionation integration — coordinate `trail_decay` snaps with fractionation cycle | Phase 3 |
| 5 | Session YAML support — allow `trail_decay` keyframes | Phase 1 |

Phases 1–2 and Phase 5 have no EEG dependency. Critical path is Phase 1.
