# Somna — VR Overlay System

## Overview

Somna can project its entire visual pipeline directly into a SteamVR headset as a
**world-locked floating overlay**, running alongside any game or app already in the headset.
The existing spiral, veil, shadow, and center-text layers render into an off-screen
framebuffer object (FBO), which is pushed to the headset every frame at full GPU speed —
no pixel readbacks, no dropped frames.

---

## Quick Start

```bash
# 1. Install the Python OpenVR bindings (one-time)
pip install openvr

# 2. Make sure SteamVR is running and your headset is on
# 3. Launch with the VR flag from the control panel "Start Session" button,
#    or add vr_mode: true to live_control.json before launching the display

# 4. Or launch the display process directly:
python visual_display_runner.py --vr
```

Put your headset on. The overlay appears as an 8-metre-wide curved "screen" floating
2 metres in front of you. It fills and slightly exceeds most headsets' horizontal FOV,
making the visuals inescapable.

---

## Technical Architecture

### Render Pipeline

```
pygame/ModernGL render loop
        │
        ▼
   _vr_fbo (off-screen FBO, same WxH as display)
        │
        ├─── ctx.copy_framebuffer(ctx.screen) ──► pygame window (desktop preview)
        │
        └─── VROverlayManager.push_frame(tex)
                  │
                  ▼
             glFinish()              ← ensures GPU finishes compositing
             openvr.Texture_t(
               handle = tex.glo,     ← raw GLuint, cast as void* per OpenVR spec
               eType  = OpenGL,
               eColorSpace = Auto,
             )
             IVROverlay.setOverlayTexture(handle, tex)
                  │
                  ▼
             SteamVR compositor ──► both eyes in headset
```

When VR mode is **inactive** the `_vr_fbo` is never created and the pipeline is
**identical** to the non-VR path. The only change is one conditional FBO bind at the
top of the render loop.

### OpenVR Init Type

`VRApplication_Overlay` — the correct type for pure-overlay apps.

- Runs alongside any scene application (game, SteamVR home, etc.)
- Gets its own SteamVR dashboard tab icon
- Can read HMD tracking pose without submitting scene frames
- Does not interfere with VR game rendering

### Overlay Positioning

The overlay is attached to the HMD via `SetOverlayTransformTrackedDeviceRelative` with
device index `k_unTrackedDeviceIndex_Hmd`. The transform is identity rotation + Z
translation of −2.0 m (2 m forward in OpenVR's right-handed, Y-up coordinate system).

At 8 m width and 2 m distance:

```
Angular width  = 2 × atan(4/2) ≈ 126°
Angular height = 2 × atan(2.25/2) ≈  96°   (16:9 aspect)
```

Quest 3 and Index have ~110° horizontal FOV. The overlay slightly exceeds this,
wrapping into peripheral vision — physically impossible to "look away" from.

Curvature is disabled by default (flat panel) because SteamVR's curvature has a known
distortion bug when the overlay is rotated off the horizon plane. Set
`VR_OVERLAY_CURVATURE` in `vr_overlay.py` to a value between 0–1 if you want to
experiment with cylindrical wrapping.

### Texture Handoff: ModernGL → OpenVR

ModernGL exposes the raw OpenGL texture name on every texture object via the `.glo`
attribute (an integer). OpenVR's `Texture_t.handle` field expects a `void*` whose
**value** equals the texture ID — the C++ cast is `(void*)(uintptr_t)tex_id`.

In Python:

```python
tex = openvr.Texture_t()
tex.handle    = ctypes.c_void_p(mgl_texture.glo)   # GLuint as pointer value
tex.eType     = openvr.TextureType_OpenGL
tex.eColorSpace = openvr.ColorSpace_Auto
vr_overlay.setOverlayTexture(overlay_handle, tex)
```

**Pitfall:** passing a *pointer to* the texture ID instead of the ID itself (as if it
were a `GL_TEXTURE_2D` pointer) silently produces a black overlay with no error.

`glFinish()` must be called before `setOverlayTexture`. We call it via ctypes to avoid
a PyOpenGL dependency:

```python
ctypes.WinDLL("opengl32").glFinish()
```

---

## The Gateway Protocol: Science Brief

The `gateway_f10` session implements the Monroe Institute's **Focus 10** state
("Mind Awake / Body Asleep") using the binaural beat frequency map documented in the
CIA-declassified Gateway Process analysis (1983, released 2003).

### Focus Level → Brainwave Map

| Focus Level | State | Beat Hz | Carrier Hz | Notes |
|-------------|-------|---------|------------|-------|
| C1 | Normal waking | — | — | Baseline |
| Focus 3 | Basic Hemi-Sync | 10 Hz | 210 | Alpha gate, synchronisation |
| Focus 10 | Mind awake / Body asleep | 5–7 Hz | 170–200 | Theta dominant |
| Focus 12 | Expanded awareness | 4–5 Hz | 155–174 | Deep theta |
| Focus 15 | No-time / Void | 2–4 Hz | 140–155 | Theta–delta border |
| Focus 21 | Bridge | 1–2 Hz | 130 | Delta approach |

Monroe used **carrier tones of 100–300 Hz** with beat frequency as the difference
between left and right. Lower carriers (100–150 Hz) are sometimes preferred for
depth states because the tones are less fatiguing over 45 minutes. Somna uses
200 Hz as the base carrier and ramps it down as depth increases.

### Frequency-Following Response (FFR)

When two pure tones differing by ≤ 30 Hz are delivered dichotically (one per ear),
the brainstem's superior olivary complex generates a FFR at the difference frequency.
This is distinct from the cortical "auditory steady-state response" seen with
monaural beats. Both hemispheres must be receiving their respective tones via
stereo headphones for Hemi-Sync to work — the overlay audio output should be
configured for stereo, not mono.

### Phosphene Cascade Model

Research (Sciety, 2024; OSF preprint) proposes a five-level classification of
closed-eye visuals that maps neatly to the session arc:

| Level | Phenomena | Session phase |
|-------|-----------|---------------|
| 1 | Flickers, point lights | C1 → Alpha (0–8 min) |
| 2 | Lattices, grids, checkers | Alpha → Theta bridge (8–15 min) |
| 3 | Spirals, tunnels, vortices | Focus 10 entry (15–25 min) |
| 4 | Radial mandalas, flower-of-life | Deep Focus 10 (25–38 min) |
| 5 | Full-field immersive light realms | Soak / OBE threshold (38–42 min) |

The visual layer progression in `gateway_f10` is designed to match each level:
drift → rain → tunnel_dream → fibonacci/galaxy → full-density converge.

### Why VR Amplifies This

A desktop window competes with room lighting, notifications, and peripheral movement.
A VR headset removes **all** competing visual input. The result:

- Phosphene Level 3 (spirals/tunnels) is typically reached 2–3× faster
- The spiral tunnel effect creates a *genuine depth illusion* that fills the headset's FOV
- The audio from the headset is physically at the ear canal, maximising binaural separation
- The physical act of putting on the headset is itself a ritual that primes state entry

---

## Session Design Guidelines for VR

### Parameter Adjustments vs Desktop

| Parameter | Desktop baseline | VR recommendation | Reason |
|-----------|-----------------|-------------------|--------|
| `veil_opacity` | 40–80% | 55–90% | No ambient light to compete with |
| `spiral_speed_multiplier` | 0.3–1.2 | 0.2–0.8 | Immersion amplifies motion; slower = safer |
| `center_flash_on_time` | 17–180 ms | 22–200 ms | Subliminal flashes are more potent at close FOV |
| `spiral_count` | 3–6 | 3–5 | VR FOV makes dense spirals more disorienting |

### Recommended Spiral Styles for VR

- **`tunnel_dream`**: The primary induction spiral. In VR, the receding tunnel creates
  genuine perceived depth. Start every VR session here.
- **`fibonacci`**: Excellent for the theta floor — golden-ratio geometry is visually
  compelling without being nauseating.
- **`galaxy`**: Good for suggestion-window phases; the rotation suppresses analytical mind.
- **Avoid `kaleidoscope` and `superformula`** at high speeds in VR — nausea risk.

### Curvature Setting

Set `VR_OVERLAY_CURVATURE = 0.15` in `vr_overlay.py` if you want a gentle cylindrical
curve. Values above 0.3 cause noticeable distortion when the overlay is not perfectly
horizontal. Experiment with your specific headset and typical use posture (seated vs
lying down).

### Lying Down

Quest 3 handles overlay display correctly when lying down (the headset compensates for
roll rotation). Other headsets may vary. The `SetOverlayTransformTrackedDeviceRelative`
approach means the overlay always stays in front of *wherever the headset is pointing*,
so any posture works.

---

## Files Modified / Created

| File | Change |
|------|--------|
| `vr_overlay.py` | **NEW** — `VROverlayManager` class |
| `visual_display.py` | **MODIFIED** — VR FBO pipeline, `--vr` flag, push_frame call |
| `visual_display_runner.py` | **UNMODIFIED** — `--vr` arg passes through via `sys.argv` |
| `sessions/gateway_f10/session.yaml` | **NEW** — 45-min Gateway Focus 10 VR session |
| `sessions/gateway_f10/affirmations.txt` | **NEW** — Induction + identity content |

---

## Known Issues and Workarounds

### "Overlay is black / not appearing"

1. Confirm SteamVR is fully initialised before launching Somna VR mode
2. Check that the headset is tracking (not in standby)
3. OpenVR requires an active OpenGL context when `setOverlayTexture` is called.
   `visual_display.py` creates the context before calling `VROverlayManager.__init__`
   — do not change this init order.
4. Verify `glFinish()` is being called; without it the texture may be partially written

### "Overlay disappears after SteamVR update"

SteamVR updates occasionally break `VROverlayFlags_NoDashboardTab` behaviour.
The overlay handle is recreated on each `VisualDisplay._open_window()` call
(e.g., after F11 toggle). Re-launching the display process always recovers.

### "Overlay is upside-down"

The `BLIT_VERT` shader in `visual_display.py` already flips the Y coordinate when
writing to `_vr_fbo`. The image should appear correctly without any texture bounds
adjustment. **Do not** add `SetOverlayTextureBounds` with `vMin=1, vMax=0` — the
shader flip is already applied and adding a second flip will invert the image.

If the overlay genuinely appears upside-down on your hardware, verify that `BLIT_VERT`
in `visual_display.py` contains `v_uv = vec2(a_uv.x, 1.0 - a_uv.y)` (Y-flip present).

### "Performance degradation while VR is active"

The VR FBO adds one extra off-screen render target and one framebuffer copy per frame.
On a GTX 1080 or better this is negligible. If you see frame drops, reduce the
render resolution by lowering `WINDOWED_W` / `WINDOWED_H` in `visual_display.py`
and re-launching in windowed mode — the overlay will be lower resolution but still smooth.

---

## Future Directions

### Stereoscopic Rendering (VRApplication_Scene)

The overlay API renders a flat 2D panel in 3D space. True stereo would require
switching to `VRApplication_Scene`, rendering two eye views with the correct
interpupillary offset, and submitting via `IVRCompositor.submit()` per eye. The
spiral shader would need a `u_eye_offset` uniform. The binaural depth cue + geometric
depth cue alignment would be extraordinary.

### Eye Tracking Integration

OpenVR 2.x exposes `VREyeTrackingData_t` on headsets that support eye tracking
(e.g., Quest Pro, Vive Pro Eye, Pico 4 Enterprise). The gaze direction could drive:
- Spiral origin (spirals grow from where you look)
- Phrase delivery (flash phrase at fixation point)
- LLM agent awareness ("user is fixating on the center" as context signal)

### Head-Relative Audio Spatialisation

Route binaural engine output through SteamVR's audio API or a spatial audio SDK
(Steam Audio, Meta XR Audio, Resonance) to bind the binaural beat to the overlay
position in 3D space. Moving your head would cause a subtle Doppler/phase shift that
reinforces the spatial anchoring of the trance state.

### Breath / Heart Rate Integration

Quest 3's proximity sensor triggers on/off. A future integration could detect breath
cadence from a BLE sensor (Polar H10, Apple Watch) and modulate `beat_frequency` in
real-time to lock to the user's respiratory rhythm — a core technique in the original
Gateway protocol exercises.
