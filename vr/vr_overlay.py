"""
vr_overlay.py
=============
SteamVR overlay manager for Somna.

Wraps pyopenvr (pip install openvr) to project the entire rendered frame
directly into the user's VR headset as a world-locked floating overlay.

Architecture
------------
* Uses VRApplication_Overlay init type — runs alongside any game/app,
  gets a SteamVR dashboard tab, can read HMD pose.
* Overlay is positioned via SetOverlayTransformTrackedDeviceRelative
  (HMD-relative, 2 m forward) so it follows the user regardless of posture.
* Texture is a ModernGL off-screen FBO colour attachment.  The raw GLuint
  (texture.glo) is cast as a void* value, matching the C++ idiom:
      tex.handle = (void*)(uintptr_t) gl_tex_id;
* glFinish() is called before every setOverlayTexture to ensure the GPU has
  finished compositing the frame before the SteamVR compositor reads it.

Usage
-----
    mgr = VROverlayManager(display_width, display_height)
    # each frame:
    mgr.push_frame(moderngl_texture)
    # on shutdown:
    mgr.close()
"""

import ctypes
import sys

# ---------------------------------------------------------------------------
# Optional import — graceful failure if pyopenvr is not installed
# ---------------------------------------------------------------------------
try:
    import openvr
    _OPENVR_AVAILABLE = True
except ImportError:
    _OPENVR_AVAILABLE = False


# ---------------------------------------------------------------------------
# Tuning constants (edit these without touching class code)
# ---------------------------------------------------------------------------

# Unique key that identifies this overlay in SteamVR's registry.
# Changing this creates a new overlay slot; the old one persists until SteamVR restart.
OVERLAY_KEY  = "somna.main"
OVERLAY_NAME = "Somna"

# How wide the overlay appears in the VR world (metres).
# Angular width = 2 * arctan(WIDTH / (2 * DIST))
#   4 m @ 2 m  →  90°  (matches typical HMD horizontal FOV — fills vision comfortably)
#   4 m @ 3 m  →  67°  (cinema-like, comfortable with peripheral margin)
#   8 m @ 2 m  → 127°  (previous default — wider than FOV, edges invisible, vertigo)
# Recommended range: 3–5 m for entrainment; wider = more immersive but harder to view.
OVERLAY_WIDTH_M = 4.0

# Distance from HMD centre to overlay plane (metres, negative Z = forward).
# Closer feels more present; further feels more cinematic.
# Comfort zone: 0.75 m (min) → 20 m (max).  1.5–3 m is ideal for flat displays.
OVERLAY_DIST_M  = 2.0

# Curvature: 0 = flat, 1 = fully cylindrical.
# Values > 0.3 cause distortion when the overlay is not horizontal.
# SteamVR has a known bug with curvature + non-horizontal rotation — keep at 0
# unless experimenting.
OVERLAY_CURVATURE = 0.2

# Target render rate (Hz) when VR is active.
# Should match your headset's native refresh (90 for most, 120 for Quest 3, 144 for Index).
# Running at 144 Hz against a 90 Hz compositor causes frame-time hitches because
# the setOverlayTexture call synchronises with the compositor cycle.
VR_TARGET_FPS = 90


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_identity34(tz: float = 0.0) -> "openvr.HmdMatrix34_t":
    """Return an HmdMatrix34_t with identity rotation and Z translation tz."""
    m = openvr.HmdMatrix34_t()
    # Zero all elements first
    for r in range(3):
        for c in range(4):
            m.m[r][c] = 0.0
    # Identity diagonal
    m.m[0][0] = 1.0
    m.m[1][1] = 1.0
    m.m[2][2] = 1.0
    # Translation
    m.m[0][3] = 0.0
    m.m[1][3] = 0.0
    m.m[2][3] = tz
    return m


def _get_gl_finish():
    """Return a callable for glFinish() without requiring PyOpenGL.

    Note: do NOT do ``import ctypes.util`` inside this function — that would
    make Python treat ``ctypes`` as a local name throughout the whole function
    scope, breaking the ``ctypes.WinDLL`` reference above it.  Use the module
    that was already imported at the top of the file instead.
    """
    if sys.platform == "win32":
        try:
            return ctypes.WinDLL("opengl32").glFinish
        except OSError:
            pass
    try:
        import ctypes.util as _cu
        lib_name = _cu.find_library("GL") or _cu.find_library("OpenGL")
        if lib_name:
            return ctypes.CDLL(lib_name).glFinish
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class VROverlayManager:
    """
    Manages a single SteamVR floating overlay backed by a ModernGL texture.

    Parameters
    ----------
    width, height : int
        Pixel dimensions of the render texture (should match display resolution).

    Raises
    ------
    RuntimeError
        If pyopenvr is not installed or SteamVR is not running.
    """

    def __init__(self, width: int, height: int):
        if not _OPENVR_AVAILABLE:
            raise RuntimeError(
                "pyopenvr not installed.  Run:  pip install openvr"
            )

        self._width  = width
        self._height = height
        self._handle = None
        self._vr_overlay: "openvr.IVROverlay" = None

        # glFinish handle
        self._gl_finish = _get_gl_finish()

        # ── Init OpenVR ────────────────────────────────────────────────────
        try:
            self._vr_system = openvr.init(openvr.VRApplication_Overlay)
        except openvr.OpenVRError as exc:
            raise RuntimeError(f"SteamVR init failed: {exc}") from exc

        self._vr_overlay = openvr.IVROverlay()

        # ── Create or reclaim overlay ───────────────────────────────────────
        # pyopenvr versions differ on return conventions: some methods return
        # the handle directly (raising on error) while others return a
        # (error_code, handle) tuple.  _unwrap() handles both forms.
        def _unwrap(result):
            """Return the overlay handle from a bare value or (err, handle) tuple."""
            if isinstance(result, (tuple, list)):
                return result[-1]
            return result

        # If a previous Somna process crashed, the overlay key may still
        # exist.  findOverlay reclaims it; createOverlay makes a fresh one.
        try:
            self._handle = _unwrap(self._vr_overlay.findOverlay(OVERLAY_KEY))
        except openvr.OpenVRError:
            self._handle = _unwrap(
                self._vr_overlay.createOverlay(OVERLAY_KEY, OVERLAY_NAME)
            )

        # ── Configure ──────────────────────────────────────────────────────
        self._vr_overlay.setOverlayWidthInMeters(self._handle, OVERLAY_WIDTH_M)
        self._vr_overlay.setOverlayAlpha(self._handle, 1.0)

        if OVERLAY_CURVATURE > 0.0:
            try:
                self._vr_overlay.setOverlayCurvature(
                    self._handle, OVERLAY_CURVATURE
                )
            except (openvr.OpenVRError, AttributeError):
                pass  # SteamVR version may not support it

        # ── Position: HMD-relative, OVERLAY_DIST_M metres ahead ───────────
        transform = _make_identity34(tz=-OVERLAY_DIST_M)
        self._vr_overlay.setOverlayTransformTrackedDeviceRelative(
            self._handle,
            openvr.k_unTrackedDeviceIndex_Hmd,
            transform,
        )

        # The BLIT_VERT shader already flips Y (1.0 - y), so the FBO texture
        # is stored right-side up for SteamVR's top-left convention.
        # No setOverlayTextureBounds call needed — default is correct.

        self._vr_overlay.showOverlay(self._handle)

        print(
            f"[VR] Overlay ready — {width}×{height}, "
            f"{OVERLAY_WIDTH_M}m wide @ {OVERLAY_DIST_M}m"
        )

    # ── Frame delivery ─────────────────────────────────────────────────────

    def push_frame(self, mgl_texture) -> None:
        """
        Push a ModernGL Texture to the SteamVR overlay.

        The texture must be an RGBA colour attachment from a ModernGL
        Framebuffer.  Call this once per render frame, after all draw calls
        for that frame are complete.

        Parameters
        ----------
        mgl_texture : moderngl.Texture
            The off-screen FBO colour attachment holding the current frame.
        """
        if self._handle is None or self._vr_overlay is None:
            return

        # Flush GPU pipeline so the compositor reads a fully-composed frame.
        # Must happen before setOverlayTexture.
        if self._gl_finish:
            self._gl_finish()

        # Build the OpenVR texture descriptor.
        # Critical: tex.handle must be the GLuint *value* cast as a void*,
        # NOT a pointer to a variable holding the GLuint.
        # mgl_texture.glo is the raw OpenGL texture name (an integer).
        tex             = openvr.Texture_t()
        tex.handle      = ctypes.c_void_p(mgl_texture.glo)
        tex.eType       = openvr.TextureType_OpenGL
        # Use Gamma (sRGB) colour space — ModernGL outputs gamma-encoded pixels.
        # ColorSpace_Auto can fail to infer the format on some SteamVR builds.
        try:
            tex.eColorSpace = openvr.ColorSpace_Gamma
        except AttributeError:
            tex.eColorSpace = openvr.ColorSpace_Auto   # older pyopenvr fallback

        try:
            self._vr_overlay.setOverlayTexture(self._handle, tex)
        except openvr.OpenVRError as exc:
            print(f"[VR] setOverlayTexture error: {exc}")

    # ── Resize ─────────────────────────────────────────────────────────────

    def update_size(self, width: int, height: int) -> None:
        """
        Notify the manager of a resolution change (e.g. after F11 toggle).

        The overlay width-in-metres is unchanged; the texture aspect ratio
        update is handled automatically via the new FBO texture dimensions.
        """
        self._width  = width
        self._height = height

    # ── Cleanup ────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Destroy the overlay and shut down the OpenVR runtime."""
        if self._vr_overlay is not None and self._handle is not None:
            try:
                self._vr_overlay.destroyOverlay(self._handle)
            except openvr.OpenVRError:
                pass
            self._handle = None

        try:
            openvr.shutdown()
        except Exception:
            pass

        print("[VR] Overlay closed")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
