import json
import os
import sys
import ctypes
import pygame
import moderngl
import numpy as np
from pathlib import Path
from ipc import patch_live
from config import ConfigManager
from layers.background import BackgroundLayer
from layers.center_text import CenterTextLayer
from layers.eeg_visual_coupler import apply as _eeg_visual_apply
from layers.shadows import ShadowsLayer
from layers.spirals_opengl import SpiralsLayer
from layers.veil import VeilLayer


_LIVE = Path(__file__).parent / "live_control.json"

_BLIT_VERT = """
#version 330 core
in  vec2 in_vert;
out vec2 uv;
void main() {
    gl_Position = vec4(in_vert, 0.0, 1.0);
    uv = vec2(in_vert.x * 0.5 + 0.5, 1.0 - (in_vert.y * 0.5 + 0.5));
}
"""
_BLIT_FRAG = """
#version 330 core
uniform sampler2D tex;
in  vec2 uv;
out vec4 fragColor;
void main() {
    fragColor = texture(tex, uv);
}
"""

# PP vertex shader — straight UV mapping (no Y-flip).
# copy_framebuffer preserves GL orientation, so PP passes must not flip.
_PP_VERT = """
#version 330 core
in  vec2 in_vert;
out vec2 uv;
void main() {
    gl_Position = vec4(in_vert, 0.0, 1.0);
    uv = vec2(in_vert.x * 0.5 + 0.5, in_vert.y * 0.5 + 0.5);
}
"""

# Overlay blit with optional stochastic resonance noise on text alpha.
# sr_noise_level = 0 → identical to plain blit_prog (no perf difference).
_OVERLAY_SR_FRAG = """
#version 330 core
uniform sampler2D tex;
uniform float     u_sr_noise_level;
uniform float     u_time;
in  vec2 uv;
out vec4 fragColor;

float sr_hash(vec2 coord, float t) {
    return fract(sin(dot(coord * t, vec2(12.9898, 78.233))) * 43758.5453) * 2.0 - 1.0;
}

void main() {
    vec4 c = texture(tex, uv);
    if (u_sr_noise_level > 0.001 && c.a > 0.001) {
        float noise = sr_hash(gl_FragCoord.xy, u_time);
        c.a = clamp(c.a + u_sr_noise_level * noise, 0.0, 1.0);
    }
    fragColor = c;
}
"""

# Trail persistence composite: additive blend with decay
_TRAIL_FRAG = """
#version 330 core
in  vec2 uv;
out vec4 fragColor;
uniform sampler2D u_current;
uniform sampler2D u_previous;
uniform float     u_trail_decay;
void main() {
    vec4 curr = texture(u_current,  uv);
    vec4 prev = texture(u_previous, uv);
    vec4 trailed = prev * u_trail_decay;
    fragColor = vec4(
        min(curr.r + trailed.r, 1.0),
        min(curr.g + trailed.g, 1.0),
        min(curr.b + trailed.b, 1.0),
        min(curr.a + trailed.a, 1.0)
    );
}
"""

# GENUS 40 Hz flicker: full-screen black quad, alpha = u_darkness * u_depth
_GENUS_FLICKER_FRAG = """
#version 330 core
uniform float u_darkness;
uniform float u_depth;
out vec4 fragColor;
void main() {
    fragColor = vec4(0.0, 0.0, 0.0, u_darkness * u_depth);
}
"""


def _build_genus_flicker_pattern(refresh_hz: int, target_hz: float = 40.0) -> list[int]:
    """
    Pre-compute a per-frame dark/light pattern that averages *target_hz* Hz
    at the given display refresh rate (genus_protocol.md §2.2, frame-dither table).

    Returns a list of 0/1 values (0=light/ON, 1=dark/OFF).  Duty cycle is 50%.

    Implementation: sample a 40 Hz square wave at the display's frame times.
    The period length is chosen as the smallest integer L such that
    L * target_hz / refresh_hz is an integer (i.e. L contains a whole number of
    40 Hz cycles).  For 144 Hz this gives L=18 (exactly 5 cycles of 40 Hz).
    """
    if refresh_hz < 80:
        return []  # visual flicker not supported; audio-only

    from math import gcd

    # LCM gives the exact period that contains a whole number of both frames
    # and 40 Hz cycles.  To keep it short, use refresh_hz / gcd(refresh_hz, round(target_hz)).
    g = gcd(refresh_hz, round(int(target_hz)))
    period_frames = refresh_hz // g  # e.g. gcd(144,40)=8 → 144/8=18 frames = 5 cycles

    # Sample a 40 Hz square wave (50% duty cycle) at each frame's midpoint.
    # phase = (frame_index / refresh_hz) * target_hz mod 1.0
    # ON (0=light) when phase < 0.5, OFF (1=dark) when phase >= 0.5
    pattern = []
    for i in range(period_frames):
        phase = (i * target_hz / refresh_hz) % 1.0
        pattern.append(0 if phase < 0.5 else 1)
    return pattern


# Windowed size used when not fullscreen (good for testing alongside control panel)
WINDOWED_W = 1280
WINDOWED_H = 720


class VisualDisplay:
    def __init__(self):
        # Pin to primary monitor (0,0) before pygame creates any window.
        # Without this the window follows the cursor onto whichever monitor the
        # control panel subprocess was launched from.
        os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        pygame.display.init()
        pygame.font.init()
        self.config_mgr = ConfigManager()
        self.fullscreen = True
        self.clock = pygame.time.Clock()
        self.running = True

        # VR state — initialised after the GL context exists
        self._vr_mgr = None
        self._vr_fbo = None
        self._vr_fbo_tex = None

        # Trail FBO state — initialised in _init_trail_fbos() via _make_textures()
        self._trail_spiral_fbo = None
        self._trail_spiral_tex = None
        self._trail_hist_fbos = [None, None]
        self._trail_hist_texs = [None, None]
        self._trail_index = 0

        # Bible Ch.3 §3.7 — post-processing FBOs and shader state
        self._pp_blur_tex = None
        self._pp_blur_fbo = None
        self._pp_bloom_tex = None
        self._pp_bloom_fbo = None
        self._pp_out_tex = None
        self._pp_out_fbo = None
        self._pp_iaf_phase = 0.0
        self._pp_error_logged = False

        # TMR phrase tracking — write current_phrase to live_control.json on change
        # so the Conductor process can read it for TMR encoding (Bible Ch.7 §7.5).
        self._last_phrase_written: str = ""

        # GENUS 40 Hz flicker state (genus_protocol.md §5.2)
        self._genus_flicker_prog = None
        self._genus_flicker_vao = None
        self._genus_frame_idx = 0
        self._genus_pattern: list[int] = []  # pre-computed per-frame dark/light pattern
        self._genus_refresh_rate: int = 60

        self._open_window()

        # Attempt VR overlay init if requested via CLI flag or live config
        vr_requested = "--vr" in sys.argv or bool(
            self.config_mgr.config.get("vr_mode", False)
        )
        if vr_requested:
            try:
                from vr.vr_overlay import VROverlayManager

                self._vr_mgr = VROverlayManager(self.W, self.H)
                self._init_vr_fbo()
            except Exception as exc:
                import traceback

                print(f"[VR] Overlay init failed — continuing without VR: {exc}")
                traceback.print_exc()

        self._win_flag_tick = 0  # throttle overlay-flag updates to every 30 frames
        # Apply window flags immediately so opacity/AoT take effect before
        # the first 30-frame throttle period expires.
        self._apply_window_flags(self.config_mgr.config)

    # ── Windows overlay helpers ───────────────────────────────────────────────

    # Win32 constants
    _GWL_EXSTYLE = -20
    _WS_EX_LAYERED = 0x00080000
    _WS_EX_TRANSPARENT = 0x00000020
    _WS_EX_NOACTIVATE = 0x08000000  # prevents window from stealing focus
    _SWP_NOMOVE = 0x0002
    _SWP_NOSIZE = 0x0001
    _SWP_NOACTIVATE = 0x0010
    _LWA_ALPHA = 0x02

    class _MARGINS(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth", ctypes.c_int),
            ("cxRightWidth", ctypes.c_int),
            ("cyTopHeight", ctypes.c_int),
            ("cyBottomHeight", ctypes.c_int),
        ]

    def _get_hwnd(self):
        try:
            return pygame.display.get_wm_info().get("window")
        except Exception:
            return None

    def _apply_window_flags(self, cfg):
        """Apply always-on-top, click-through, and opacity from live config.

        Only available on Windows; silently skipped on other platforms.
        Throttled to once every 30 frames; applied unconditionally each time
        so that SDL or DWM resets (e.g. on focus change) are immediately
        corrected on the next tick.

        Opacity note: WS_EX_LAYERED / LWA_ALPHA is applied by DWM while the
        window is NOT focused.  To keep the alpha visible at all times we add
        WS_EX_NOACTIVATE whenever opacity < 100 or click-through is on, so
        the window never steals focus and DWM always composites it.
        """
        if sys.platform != "win32":
            return

        hwnd = self._get_hwnd()
        if not hwnd:
            return

        topmost = bool(cfg.get("window_always_on_top", False))
        clickthrough = bool(cfg.get("window_click_through", False))
        opacity_pct = int(cfg.get("window_opacity", 100))
        _bg_mode = cfg.get("bg_mode", "")
        # "ganzfeld" is an opaque solid-field mode — never transparent.
        bg_none = _bg_mode == "none" or (
            _bg_mode != "ganzfeld" and not self.bg.has_images
        )
        # overlay_mode drives WS_EX_LAYERED / DWM glass.  bg_none (no images)
        # no longer implies transparency on its own — only explicit user intent
        # (click-through on, or opacity < 100) enables the glass pipeline.
        overlay_mode = clickthrough or opacity_pct < 100

        # While the LLM prompt dialog is visible, yield TOPMOST so the Tkinter
        # input box can stay above this window without a z-order race.
        if cfg.get("llm_dialog_active"):
            topmost = False

        try:
            user32 = ctypes.windll.user32
            # Explicit argument types so ctypes handles pointer-sized values
            # correctly on both 32-bit and 64-bit Windows.
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.GetWindowLongW.restype = ctypes.c_long
            user32.SetWindowLongW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_long,
            ]

            # ── Always on top ──────────────────────────────────────────────
            # HWND_TOPMOST = -1, HWND_NOTOPMOST = -2  (cast to void* below)
            insert_after = ctypes.c_void_p(-1 if topmost else -2)
            user32.SetWindowPos(
                hwnd,
                insert_after,
                0,
                0,
                0,
                0,
                self._SWP_NOMOVE | self._SWP_NOSIZE | self._SWP_NOACTIVATE,
            )

            # ── Extended styles ────────────────────────────────────────────
            ex_style = user32.GetWindowLongW(hwnd, self._GWL_EXSTYLE)

            if overlay_mode:
                # LAYERED enables DWM alpha; NOACTIVATE keeps focus away so
                # DWM never hands the window direct rendering (which bypasses
                # the alpha).
                ex_style |= self._WS_EX_LAYERED | self._WS_EX_NOACTIVATE
                if clickthrough:
                    ex_style |= self._WS_EX_TRANSPARENT
                else:
                    ex_style &= ~self._WS_EX_TRANSPARENT
            else:
                ex_style &= ~(
                    self._WS_EX_LAYERED
                    | self._WS_EX_TRANSPARENT
                    | self._WS_EX_NOACTIVATE
                )

            user32.SetWindowLongW(hwnd, self._GWL_EXSTYLE, ex_style)

            if overlay_mode:
                # Force-defocus so DWM compositing applies immediately
                # instead of waiting for user to click elsewhere.
                user32.SetWindowPos(
                    hwnd,
                    ctypes.c_void_p(-1 if topmost else -2),
                    0,
                    0,
                    0,
                    0,
                    self._SWP_NOMOVE | self._SWP_NOSIZE | self._SWP_NOACTIVATE,
                )

            # ── Per-pixel alpha (DWM glass) / flat alpha ───────────────────
            if bg_none:
                # DWM glass extension: extend the desktop compositor frame into
                # the entire client area so it uses the GL framebuffer's alpha
                # channel for per-pixel transparency.  Alpha=0 pixels (the clear
                # background) show the desktop; glow/spiral pixels retain their
                # colour and alpha untouched — no color-key artifacts.
                try:
                    m = self._MARGINS(-1, -1, -1, -1)
                    ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
                        hwnd, ctypes.byref(m)
                    )
                except Exception as _de:
                    print(f"[Overlay] DWM glass error: {_de}")
                alpha = (
                    max(26, min(255, int(opacity_pct * 255 / 100)))
                    if opacity_pct < 100
                    else 255
                )
                user32.SetLayeredWindowAttributes(hwnd, 0, alpha, self._LWA_ALPHA)
            elif overlay_mode and opacity_pct < 100:
                alpha = max(26, min(255, int(opacity_pct * 255 / 100)))
                user32.SetLayeredWindowAttributes(hwnd, 0, alpha, self._LWA_ALPHA)
            elif overlay_mode:
                # Click-through only — full opacity, just needs LAYERED flag
                user32.SetLayeredWindowAttributes(hwnd, 0, 255, self._LWA_ALPHA)

        except Exception as e:
            print(f"[Overlay] Window flag error: {e}")

        # SDL2 manages cursor visibility via SetCursor()/SetCursor(NULL), not
        # ShowCursor().  The only reliable way to show/hide it is through pygame's
        # own API so SDL's WM_SETCURSOR handler stays consistent.
        pygame.mouse.set_visible(overlay_mode)

    # ── Window / GL bootstrap (called on init and every F11) ──────────────────

    def _open_window(self):
        if self.fullscreen:
            # Use the primary monitor's resolution. get_desktop_sizes()[0] is
            # the primary display; fall back to display.Info() on older pygame.
            os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"
            try:
                self.W, self.H = pygame.display.get_desktop_sizes()[0]
            except (AttributeError, IndexError):
                info = pygame.display.Info()
                self.W, self.H = info.current_w, info.current_h
            flags = pygame.NOFRAME | pygame.OPENGL | pygame.DOUBLEBUF
        else:
            self.W = WINDOWED_W
            self.H = WINDOWED_H
            flags = pygame.RESIZABLE | pygame.OPENGL | pygame.DOUBLEBUF

        # Ensure the GL framebuffer has an alpha channel so DWM glass can
        # use per-pixel alpha for bg_none transparency.
        # GL_SWAP_CONTROL=1 enables vsync — on a 144 Hz display this gives
        # hardware-timed frame delivery instead of a software sleep cap.
        pygame.display.gl_set_attribute(pygame.GL_SWAP_CONTROL, 1)
        pygame.display.gl_set_attribute(pygame.GL_ALPHA_SIZE, 8)
        pygame.mouse.set_visible(False)
        self.screen = pygame.display.set_mode((self.W, self.H), flags)
        pygame.display.set_caption("Somna")

        # Detect refresh rate for GENUS 40 Hz dither pattern.
        # pygame.display.Info().current_refresh is unreliable (often 0).
        # Win32 GetDeviceCaps(VREFRESH) reads straight from the display driver.
        try:
            if sys.platform == "win32":
                _VREFRESH = 116
                dc = ctypes.windll.user32.GetDC(0)
                self._genus_refresh_rate = (
                    int(ctypes.windll.gdi32.GetDeviceCaps(dc, _VREFRESH)) or 60
                )
                ctypes.windll.user32.ReleaseDC(0, dc)
            else:
                info = pygame.display.Info()
                self._genus_refresh_rate = int(info.current_refresh) or 60
        except Exception:
            self._genus_refresh_rate = 60
        if self._genus_refresh_rate < 80:
            patch_live({"genus_visual_display_capable": False})
        else:
            patch_live(
                {
                    "genus_visual_display_capable": True,
                    "genus_display_refresh_hz": self._genus_refresh_rate,
                }
            )
        self._genus_pattern = _build_genus_flicker_pattern(self._genus_refresh_rate)
        self._genus_frame_idx = 0

        # Every set_mode with OPENGL gives a fresh GL context — reinit everything
        self._init_gl()
        self._init_layers()
        self._make_textures()

    def _init_gl(self):
        self.ctx = moderngl.create_context()
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)

        verts = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4")
        vbo = self.ctx.buffer(verts)

        self.blit_prog = self.ctx.program(
            vertex_shader=_BLIT_VERT,
            fragment_shader=_BLIT_FRAG,
        )
        self.blit_vao = self.ctx.vertex_array(self.blit_prog, [(vbo, "2f", "in_vert")])

        # Trail/feedback composite — prefer external shader, fallback to inline
        _feedback_path = Path(__file__).parent / "shaders" / "pp_feedback.glsl"
        if _feedback_path.exists():
            try:
                _feedback_src = _feedback_path.read_text(encoding="utf-8")
                self.trail_prog = self.ctx.program(
                    vertex_shader=_BLIT_VERT, fragment_shader=_feedback_src
                )
            except Exception as _e:
                print(f"[Display] Feedback shader failed, using inline: {_e}")
                self.trail_prog = self.ctx.program(
                    vertex_shader=_BLIT_VERT, fragment_shader=_TRAIL_FRAG
                )
        else:
            self.trail_prog = self.ctx.program(
                vertex_shader=_BLIT_VERT, fragment_shader=_TRAIL_FRAG
            )
        self.trail_vao = self.ctx.vertex_array(
            self.trail_prog, [(vbo, "2f", "in_vert")]
        )

        self.overlay_sr_prog = self.ctx.program(
            vertex_shader=_BLIT_VERT,
            fragment_shader=_OVERLAY_SR_FRAG,
        )
        self.overlay_sr_vao = self.ctx.vertex_array(
            self.overlay_sr_prog, [(vbo, "2f", "in_vert")]
        )

        # ── Bible Ch.3 §3.7 — Post-processing shaders ─────────────────────────────────
        _shaders = Path(__file__).parent / "shaders"

        def _load_pp(name: str):
            try:
                src = (_shaders / name).read_text(encoding="utf-8")
                prog = self.ctx.program(vertex_shader=_PP_VERT, fragment_shader=src)
                vao = self.ctx.vertex_array(prog, [(vbo, "2f", "in_vert")])
                return prog, vao
            except Exception as _e:
                print(f"[Display] PP shader {name} load failed: {_e}")
                return None, None

        self._pp_blur_prog, self._pp_blur_vao = _load_pp("pp_blur.glsl")
        self._pp_ca_prog, self._pp_ca_vao = _load_pp("pp_ca.glsl")
        self._pp_bloom_t_prog, self._pp_bloom_t_vao = _load_pp(
            "pp_bloom_threshold.glsl"
        )
        self._pp_composite_prog, self._pp_composite_vao = _load_pp("pp_composite.glsl")
        self._pp_iaf_phase: float = 0.0  # accumulated IAF phase for luminance mod

        # GENUS 40 Hz flicker overlay (genus_protocol.md §5.2)
        try:
            self._genus_flicker_prog = self.ctx.program(
                vertex_shader=_BLIT_VERT,
                fragment_shader=_GENUS_FLICKER_FRAG,
            )
            self._genus_flicker_vao = self.ctx.vertex_array(
                self._genus_flicker_prog, [(vbo, "2f", "in_vert")]
            )
        except Exception as _ge:
            print(f"[GENUS] Flicker shader init failed: {_ge}")
            self._genus_flicker_prog = None
            self._genus_flicker_vao = None

    def _init_layers(self):
        cfg = self.config_mgr.config
        self.bg = BackgroundLayer(cfg)
        self.veil = VeilLayer(cfg)
        self.spirals = SpiralsLayer(cfg, self.ctx)  # needs fresh ctx
        # TTS and binaural audio are owned by the control panel process.
        # CenterTextLayer syncs phrase display via tts_playing in live_control.json.
        self.center = CenterTextLayer(cfg, tts_engine=None)
        self.shadows = ShadowsLayer(cfg)

    def _make_textures(self):
        self.bg_surf = pygame.Surface((self.W, self.H))
        self.overlay_surf = pygame.Surface((self.W, self.H), pygame.SRCALPHA)

        self.bg_tex = self.ctx.texture((self.W, self.H), 3)
        self.overlay_tex = self.ctx.texture((self.W, self.H), 4)
        for t in (self.bg_tex, self.overlay_tex):
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)

        self._init_trail_fbos()
        self._init_pp_fbos()

        # Re-create VR FBO if one was active (called after fullscreen toggle)
        if getattr(self, "_vr_mgr", None):
            self._init_vr_fbo()

    def _init_trail_fbos(self):
        """Create (or recreate) the ping-pong trail FBO set at current resolution."""

        def _release(obj):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass

        _release(self._trail_spiral_fbo)
        _release(self._trail_spiral_tex)
        for i in range(2):
            _release(self._trail_hist_fbos[i])
            _release(self._trail_hist_texs[i])

        size = (self.W, self.H)
        self._trail_spiral_tex = self.ctx.texture(size, 4)
        self._trail_spiral_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._trail_spiral_fbo = self.ctx.framebuffer(
            color_attachments=[self._trail_spiral_tex]
        )
        for i in range(2):
            t = self.ctx.texture(size, 4)
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._trail_hist_texs[i] = t
            fbo = self.ctx.framebuffer(color_attachments=[t])
            fbo.use()
            self.ctx.clear(0.0, 0.0, 0.0, 0.0)
            self._trail_hist_fbos[i] = fbo
        self._trail_index = 0

    def _init_pp_fbos(self):
        """Create (or recreate) post-processing FBOs at current resolution."""

        def _release(obj):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass

        size = (self.W, self.H)
        # pp_blur_tex / fbo — for blur pass output
        # pp_bloom_tex / fbo — for bloom bright-extract + blur
        # pp_out_tex / fbo — for CA + composite output before final blit
        for attr in (
            "_pp_blur_tex",
            "_pp_bloom_tex",
            "_pp_out_tex",
            "_pp_blur_fbo",
            "_pp_bloom_fbo",
            "_pp_out_fbo",
        ):
            _release(getattr(self, attr, None))

        def _make_fbo(size):
            tex = self.ctx.texture(size, 4)
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            fbo = self.ctx.framebuffer(color_attachments=[tex])
            return tex, fbo

        self._pp_blur_tex, self._pp_blur_fbo = _make_fbo(size)
        self._pp_bloom_tex, self._pp_bloom_fbo = _make_fbo(size)
        self._pp_out_tex, self._pp_out_fbo = _make_fbo(size)

    def _init_vr_fbo(self):
        """Create (or recreate) the off-screen FBO used to feed the VR overlay."""
        if self._vr_fbo is not None:
            self._vr_fbo_tex.release()
            self._vr_fbo.release()
        self._vr_fbo_tex = self.ctx.texture((self.W, self.H), 4)
        self._vr_fbo_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._vr_fbo = self.ctx.framebuffer(color_attachments=[self._vr_fbo_tex])
        if self._vr_mgr:
            self._vr_mgr.update_size(self.W, self.H)

    # ── Post-processing pipeline (Bible Ch.3 §3.7 §3) ─────────────────────────────────

    def _run_post_processing(self, cfg: dict, dt: float) -> None:
        """
        Bible Ch.3 §3.7 post-processing: CA → bloom → vignette + IAF modulation.

        Reads the current screen framebuffer into a texture, applies passes,
        writes the result back to screen (or VR FBO).  Only runs when any
        pp_* parameter is non-zero and all shader programs loaded successfully.
        """
        if self._pp_ca_prog is None or self._pp_composite_prog is None:
            return  # shaders didn't compile

        ca_strength = float(cfg.get("pp_ca_strength", 0.0) or 0.0)
        bloom_intensity = float(cfg.get("pp_bloom_intensity", 0.0) or 0.0)
        bloom_threshold = float(cfg.get("pp_bloom_threshold", 0.75) or 0.75)
        vignette_sigma = float(cfg.get("pp_vignette_sigma", 0.5) or 0.5)
        vignette_int = float(cfg.get("pp_vignette_intensity", 0.0) or 0.0)
        iaf_amp = float(cfg.get("pp_iaf_mod_amplitude", 0.0) or 0.0)
        film_grain = float(cfg.get("pp_film_grain", 0.0) or 0.0)
        tonemap = int(cfg.get("pp_tonemap", 0))

        # Check if any PP effect is active
        if (
            ca_strength < 1e-4
            and bloom_intensity < 1e-4
            and vignette_int < 1e-4
            and iaf_amp < 1e-4
            and film_grain < 1e-4
            and tonemap == 0
        ):
            return

        if not getattr(self, "_pp_diag_logged", False):
            self._pp_diag_logged = True
            print(
                f"[Display] PP active: ca={ca_strength:.3f} bloom={bloom_intensity:.3f} "
                f"grain={film_grain:.3f} vignette={vignette_int:.3f} tonemap={tonemap}"
            )

        # Advance IAF luminance phase
        iaf_hz = float(cfg.get("eeg_iaf_hz") or 10.0)
        self._pp_iaf_phase = (self._pp_iaf_phase + 2.0 * 3.14159 * iaf_hz * dt) % (
            2.0 * 3.14159
        )
        patch_live({"pp_iaf_mod_phase": round(self._pp_iaf_phase, 4)})

        target = self._vr_fbo if self._vr_fbo is not None else self.ctx.screen

        try:
            # ── Step 1: Capture current scene into _pp_out_fbo ───────────────
            self.ctx.copy_framebuffer(self._pp_out_fbo, target)

            # ── Step 2: Chromatic aberration → _pp_blur_fbo ──────────────────
            if ca_strength > 1e-4 and self._pp_ca_prog is not None:
                self._pp_blur_fbo.use()
                self.ctx.clear(0.0, 0.0, 0.0, 1.0)
                self._pp_out_tex.use(0)
                self._pp_ca_prog["u_texture"].value = 0
                self._pp_ca_prog["u_ca_strength"].value = ca_strength
                self._pp_ca_prog["u_resolution"].value = (float(self.W), float(self.H))
                self._pp_ca_vao.render(moderngl.TRIANGLE_STRIP)
                # Swap: use blur output as scene for next pass
                self.ctx.copy_framebuffer(self._pp_out_fbo, self._pp_blur_fbo)

            # ── Step 3: Bloom bright-extract → _pp_bloom_fbo ─────────────────
            if bloom_intensity > 1e-4 and self._pp_bloom_t_prog is not None:
                self._pp_bloom_fbo.use()
                self.ctx.clear(0.0, 0.0, 0.0, 1.0)
                self._pp_out_tex.use(0)
                self._pp_bloom_t_prog["u_texture"].value = 0
                self._pp_bloom_t_prog["u_bloom_threshold"].value = bloom_threshold
                self._pp_bloom_t_vao.render(moderngl.TRIANGLE_STRIP)

                # Optionally blur the bright extract (reuse pp_blur if available)
                if self._pp_blur_prog is not None:
                    # Horizontal blur
                    self._pp_blur_fbo.use()
                    self.ctx.clear(0.0, 0.0, 0.0, 1.0)
                    self._pp_bloom_tex.use(0)
                    self._pp_blur_prog["u_texture"].value = 0
                    self._pp_blur_prog["u_direction"].value = (1.0 / self.W, 0.0)
                    self._pp_blur_prog["u_blur_radius"].value = float(
                        cfg.get("pp_blur_radius", 2.0) or 2.0
                    )
                    self._pp_blur_prog["u_texel_size"].value = (
                        1.0 / self.W,
                        1.0 / self.H,
                    )
                    self._pp_blur_vao.render(moderngl.TRIANGLE_STRIP)
                    # Copy blurred bloom back
                    self.ctx.copy_framebuffer(self._pp_bloom_fbo, self._pp_blur_fbo)

            # ── Step 4: Composite (bloom + vignette + IAF + ACES + grain) → target ──
            target.use()
            self._pp_out_tex.use(0)
            self._pp_bloom_tex.use(1)
            self._pp_composite_prog["u_scene"].value = 0
            self._pp_composite_prog["u_bloom"].value = 1
            self._pp_composite_prog["u_bloom_intensity"].value = bloom_intensity
            self._pp_composite_prog["u_vignette_sigma"].value = vignette_sigma
            self._pp_composite_prog["u_vignette_intensity"].value = vignette_int
            self._pp_composite_prog["u_iaf_mod_amplitude"].value = iaf_amp
            self._pp_composite_prog["u_iaf_mod_phase"].value = self._pp_iaf_phase
            # Phase 2 — ACES tonemapping + film grain
            if "u_tonemap" in self._pp_composite_prog:
                self._pp_composite_prog["u_tonemap"].value = int(
                    cfg.get("pp_tonemap", 0)
                )
            if "u_film_grain" in self._pp_composite_prog:
                self._pp_composite_prog["u_film_grain"].value = float(
                    cfg.get("pp_film_grain", 0.0) or 0.0
                )
            if "u_time" in self._pp_composite_prog:
                self._pp_composite_prog["u_time"].value = (
                    float(pygame.time.get_ticks()) / 1000.0
                )
            self._pp_composite_vao.render(moderngl.TRIANGLE_STRIP)

        except Exception as _pe:
            # Non-fatal: restore target and log once
            if not getattr(self, "_pp_error_logged", False):
                print(f"[Display] Post-processing error (will not repeat): {_pe}")
                self._pp_error_logged = True
            try:
                target.use()
            except Exception:
                pass

    # ── Upload a pygame surface and blit it as a fullscreen quad ──────────────

    def _blit_surface(self, tex, surf, fmt):
        tex.write(pygame.image.tobytes(surf, fmt, False))
        tex.use(0)
        self.blit_prog["tex"].value = 0
        self.blit_vao.render(moderngl.TRIANGLE_STRIP)

    # ── Toggle ────────────────────────────────────────────────────────────────

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        # _open_window fully reinitialises GL context + all layers.
        # _make_textures() inside will rebuild the VR FBO if _vr_mgr is set.
        self._open_window()

    # ── GENUS 40 Hz flicker (genus_protocol.md §5.2) ─────────────────────────

    def _apply_genus_flicker(self, cfg: dict) -> None:
        """
        Apply one frame of the 40 Hz flicker pattern over the composited scene.

        When genus_active and genus_visual_enabled are True and the display is
        capable (≥ 80 Hz), this method either:
          - does nothing on a "light" frame (no draw call), or
          - draws a full-screen black quad at u_darkness=1.0 on a "dark" frame.

        The per-frame pattern is pre-computed in _build_genus_flicker_pattern().
        AV sync: the pattern is advanced every frame independent of beat_phase —
        both the audio click train and the visual pattern run at 40 Hz from the
        same GPU vsync cadence, providing temporal alignment within one frame (~7 ms
        at 144 Hz), well within the < 5 ms jitter target.
        """
        if not bool(cfg.get("genus_active", False)):
            self._genus_frame_idx = 0
            return
        if not bool(cfg.get("genus_visual_enabled", True)):
            return
        if self._genus_refresh_rate < 80:
            return
        if self._genus_flicker_prog is None or not self._genus_pattern:
            return

        pattern = self._genus_pattern
        dark_flag = pattern[self._genus_frame_idx % len(pattern)]
        self._genus_frame_idx = (self._genus_frame_idx + 1) % len(pattern)

        if dark_flag == 0:
            return  # light frame — no draw call needed

        # Dark frame: draw full-screen black quad blended over everything
        depth = float(cfg.get("genus_modulation_depth", 1.0) or 1.0)
        self._genus_flicker_prog["u_darkness"].value = 1.0
        self._genus_flicker_prog["u_depth"].value = depth
        self._genus_flicker_vao.render(moderngl.TRIANGLE_STRIP)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        patch_live({"display_active": True})
        last_time = pygame.time.get_ticks()

        while self.running:
            dt = (pygame.time.get_ticks() - last_time) / 1000.0
            last_time = pygame.time.get_ticks()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_F11:
                        self.toggle_fullscreen()

            cfg = self.config_mgr.update()
            cfg = _eeg_visual_apply(cfg)
            beat = cfg.get("beat_frequency", 10.0)

            # When paused, clear to transparent and skip all rendering
            if cfg.get("timeline_paused", False):
                self.ctx.clear(0.0, 0.0, 0.0, 0.0)
                pygame.display.flip()
                continue

            # Apply overlay flags every 30 frames (only when values change)
            self._win_flag_tick += 1
            if self._win_flag_tick >= 30:
                self._win_flag_tick = 0
                self._apply_window_flags(cfg)

            # ── VR: redirect all rendering into the off-screen FBO ─────────
            # When VR is inactive this block is skipped and ctx.screen remains
            # bound — behaviour is identical to the non-VR path.
            if self._vr_fbo is not None:
                self._vr_fbo.use()

            # Always tick the background layer so session-change detection
            # runs even while bg_mode='none' — this lets switching to a
            # session with images flip bg_mode back to 'slideshow'.
            self.bg.tick(cfg)

            # bg_none: skip background layer entirely (transparent).
            # "ganzfeld" is always opaque regardless of whether images exist.
            _bg_mode = cfg.get("bg_mode", "")
            bg_none = _bg_mode == "none" or (
                _bg_mode != "ganzfeld" and not self.bg.has_images
            )

            # Transparent clear only when the user has actually opted into
            # transparency (click-through on, or opacity < 100).  A session
            # that simply has no images should still render opaque at full
            # opacity — otherwise the spiral/veil always show the desktop
            # through them regardless of the opacity slider.
            clickthrough = bool(cfg.get("window_click_through", False))
            opacity_pct = int(cfg.get("window_opacity", 100))
            wants_glass = bg_none and (clickthrough or opacity_pct < 100)

            if wants_glass:
                self.ctx.clear(0.0, 0.0, 0.0, 0.0)
            else:
                self.ctx.clear(0.0, 0.0, 0.0, 1.0)

            # Layer 1 — background (skipped in imageless/no-bg mode so the GL
            # framebuffer stays transparent for DWM glass).
            if not bg_none:
                self.bg.draw(self.bg_surf, cfg)
                self._blit_surface(self.bg_tex, self.bg_surf, "RGB")

            # Layer 2 — spirals via ping-pong trail FBO
            try:
                # Step 1: render fresh spiral into the isolated spiral FBO
                trail_decay = max(0.0, min(0.99, float(cfg.get("trail_decay", 0.0))))
                self._trail_spiral_fbo.use()
                self.ctx.clear(0.0, 0.0, 0.0, 0.0)
                self.spirals.update(dt, beat, cfg)
                self.spirals.draw(cfg)

                # Step 2: composite spiral + previous history → current history FBO
                curr_hist_fbo = self._trail_hist_fbos[self._trail_index]
                prev_hist_tex = self._trail_hist_texs[1 - self._trail_index]
                curr_hist_fbo.use()
                self.ctx.clear(0.0, 0.0, 0.0, 0.0)
                self._trail_spiral_tex.use(0)
                prev_hist_tex.use(1)
                self.trail_prog["u_current"].value = 0
                self.trail_prog["u_previous"].value = 1
                self.trail_prog["u_trail_decay"].value = trail_decay
                # Feedback mode uniforms (pp_feedback.glsl Phase 3)
                if "u_feedback_mode" in self.trail_prog:
                    mode_map = {
                        "alpha_decay": 0,
                        "radial_zoom": 1,
                        "rotational_smear": 2,
                        "directional_blur": 3,
                        "reaction_diffusion": 4,
                        "kaleidoscopic_fold": 5,
                    }
                    mode = mode_map.get(cfg.get("feedback_mode", "alpha_decay"), 0)
                    self.trail_prog["u_feedback_mode"].value = mode
                    self.trail_prog["u_feedback_strength"].value = float(
                        cfg.get("feedback_strength", 1.0) or 1.0
                    )
                    self.trail_prog["u_zoom_speed"].value = float(
                        cfg.get("feedback_zoom_speed", 0.01)
                    )
                    self.trail_prog["u_rotation_speed"].value = float(
                        cfg.get("feedback_rotation_speed", 0.02)
                    )
                    self.trail_prog["u_flow_speed"].value = float(
                        cfg.get("feedback_flow_speed", 0.01)
                    )
                    self.trail_prog["u_fold_sectors"].value = float(
                        cfg.get("feedback_fold_sectors", 6.0)
                    )
                    self.trail_prog["u_time"].value = (
                        float(pygame.time.get_ticks()) / 1000.0
                    )
                    self.trail_prog["u_resolution"].value = (
                        float(self.W),
                        float(self.H),
                    )
                self.trail_vao.render(moderngl.TRIANGLE_STRIP)

                # Step 3: blit accumulated trail to main framebuffer.
                # Pre-multiplied alpha composite — spiral FBO already has alpha baked into RGB.
                if self._vr_fbo is not None:
                    self._vr_fbo.use()
                else:
                    self.ctx.screen.use()
                self._trail_hist_texs[self._trail_index].use(0)
                self.blit_prog["tex"].value = 0
                self.ctx.blend_func = (moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA)
                self.blit_vao.render(moderngl.TRIANGLE_STRIP)
                self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)

                self._trail_index = 1 - self._trail_index
                self._spiral_error_count = 0
            except Exception as _se:
                # Restore main framebuffer so subsequent layers still render.
                try:
                    if self._vr_fbo is not None:
                        self._vr_fbo.use()
                    else:
                        self.ctx.screen.use()
                except Exception:
                    pass
                self._spiral_error_count = getattr(self, "_spiral_error_count", 0) + 1
                if self._spiral_error_count <= 3:
                    print(
                        f"[Display] Spiral render error (#{self._spiral_error_count}): {_se}"
                    )

            # ── Bible Ch.3 §3.7 — Post-processing passes (CA, bloom, vignette, IAF) ──
            # Runs BEFORE overlay blit so PP affects spirals+background only,
            # not the text layer. This prevents grain/CA from corrupting text.
            self._run_post_processing(cfg, dt)

            # Layers 3-5 — veil + shadows + center text composited on one surface
            self.overlay_surf.fill((0, 0, 0, 0))

            self.veil.update(dt, beat)
            self.veil.draw(self.overlay_surf, beat)

            self.shadows.update(dt)
            self.shadows.draw(self.overlay_surf)

            self.center.update(dt, beat)
            # Publish the currently-shown phrase for TMR encoding (Bible Ch.7 §7.5).
            # Written only on change and only while visible, so live_control.json
            # write pressure is negligible (one write per new phrase flash).
            if self.center.visible and self.center.current:
                if self.center.current != self._last_phrase_written:
                    self._last_phrase_written = self.center.current
                    patch_live({"current_phrase": self.center.current})
            cs = self.center.get_surface()
            self.overlay_surf.blit(
                cs,
                ((self.W - cs.get_width()) // 2, (self.H - cs.get_height()) // 2),
            )

            # Layer 3-6 overlay blit — with optional SR noise on text alpha
            self.overlay_tex.write(
                pygame.image.tobytes(self.overlay_surf, "RGBA", False)
            )
            self.overlay_tex.use(0)
            sr_level = float(cfg.get("sr_noise_level", 0.0))
            self.overlay_sr_prog["tex"].value = 0
            self.overlay_sr_prog["u_sr_noise_level"].value = sr_level
            self.overlay_sr_prog["u_time"].value = (
                float(pygame.time.get_ticks()) / 1000.0
            )
            self.overlay_sr_vao.render(moderngl.TRIANGLE_STRIP)

            # ── GENUS 40 Hz flicker overlay (genus_protocol.md §5.2) ──────
            self._apply_genus_flicker(cfg)

            # ── VR: push FBO texture to headset, then copy to screen ───────
            if self._vr_mgr is not None and self._vr_fbo is not None:
                self._vr_mgr.push_frame(self._vr_fbo_tex)
                # Copy the VR FBO to the pygame window so the desktop shows
                # a preview of what's in the headset.
                self.ctx.screen.use()
                self.ctx.copy_framebuffer(self.ctx.screen, self._vr_fbo)

            pygame.display.flip()
            # When VR is active, pace to the compositor's refresh cycle.
            # Running at 144 Hz against a 90 Hz compositor creates hitches
            # because setOverlayTexture syncs with the compositor cycle.
            if self._vr_mgr is not None:
                try:
                    from vr.vr_overlay import VR_TARGET_FPS

                    self.clock.tick(VR_TARGET_FPS)
                except ImportError:
                    self.clock.tick(90)
            else:
                # Sleep power-efficiency: drop to 1 FPS when all visual
                # gain channels are at zero (e.g. during SLEEP_MAINTAIN).
                # Prevents wasting GPU/CPU over long 8-hour sleep sessions.
                all_zero = (
                    not cfg.get("spiral_opacity", 0)
                    and not cfg.get("veil_opacity", 0)
                    and not cfg.get("shadow_opacity_target", 0)
                    and not cfg.get("center_flash_on_time", 0)
                    and bg_none
                )
                self.clock.tick(1 if all_zero else 144)

        patch_live({"display_active": False})
        if self._vr_mgr is not None:
            self._vr_mgr.close()
        pygame.quit()


if __name__ == "__main__":
    VisualDisplay().run()
