"""
vr_vection.py — Vection / Optic Flow Renderer (Bible Ch.8 §8.5)
=======================================================
Generates a 3D particle field rendered in each eye's per-eye OpenGL
framebuffer.  The particles move from far to near (positive Z toward
camera) creating the illusory sensation of forward self-motion (vection).

Vection induces somatic dissociation: the mismatch between perceived
motion (optic flow) and vestibular stillness floods parietal prediction
with errors, weakening the sense of a situated body.  Bible Ch.8 §8.5 §3 notes
that even 8–10% of the visual field covered by coherent dots is
sufficient to trigger partial vection.

EEG signature: P600 positive (parietal, motion processing) and frontal
negative (anterior N2, prediction error cancellation).  The Conductor
detects this pattern via the FAA and trance metrics as a secondary
dissociation signal.

Cybersickness mitigations (Bible Ch.8 §8.5 §8):
  - No yaw or roll rotation — purely axial (forward) flow
  - Fixed horizon reference: sparse stationary stars at maximum Z
  - First-session speed cap: speed ramps up over 3 sessions
  - Adaptive vection: if binocular index rises rapidly, reduce speed
    to prevent overstimulation
  - Speed range: 0.02–0.35 scene units/frame; session 1 cap = 0.10

live_control.json keys read:
  vr_vection_enabled     bool    master on/off
  vr_vection_speed       float   0–1 (maps to 0.02–0.35 units/frame)
  vr_vection_density     int     particle count 200–2000 (default 800)
  vr_vection_star_size   float   point size in pixels (default 2.0)
  vr_vection_color_r/g/b float   star colour 0–1 (default 0.9/0.9/0.9)

live_control.json keys written:
  vr_vection_active      bool    True while rendering
  vr_vection_phase_s     float   seconds since vection started
"""

from __future__ import annotations

import math
import random
import time

import numpy as np
from ipc import patch_live, read_live

# ── Scene constants ────────────────────────────────────────────────────────────
_Z_NEAR = 0.5  # particles disappear when Z < _Z_NEAR (just past camera)
_Z_FAR = 80.0  # particles spawn here
_XY_SPREAD = 8.0  # random X/Y extent at spawn; feels like a wide tunnel

# Speed schedule: speed_cap per session count (session number → cap)
_SESSION_SPEED_CAP = {
    0: 0.10,
    1: 0.10,
    2: 0.18,
    3: 0.27,
    4: 0.35,  # full speed from session 4 onward
}
_DEFAULT_SPEED_UNITS = 0.12  # units/frame at speed=1.0 raw; scaled by vr_vection_speed


def _read_live() -> dict:
    try:
        return read_live()
    except Exception:
        return {}


class VectionRenderer:
    """CPU-side optic flow particle simulation + OpenGL point rendering.

    Designed for use inside the pyopenxr per-eye loop.  Call
    render_eye() once per eye per frame.  The simulation runs
    frame-rate-independent (delta-time based).

    The renderer uses a simple perspective projection matrix and
    OpenGL immediate mode for maximum compatibility across headsets
    without requiring GLSL shader compilation on the target machine.
    In the future, this can be upgraded to a VAO/VBO approach for
    Quest 3 / PC VR without changing the public interface.
    """

    def __init__(self, n_particles: int = 800):
        self._n = n_particles
        self._pos: np.ndarray = self._spawn_all()  # (n, 3) — X, Y, Z

        # Horizon anchors — stationary sparse stars at Z_FAR (Bible Ch.8 §8.5 §8.3)
        n_horizon = max(20, n_particles // 40)
        self._horizon: np.ndarray = np.zeros((n_horizon, 3), dtype=np.float32)
        self._horizon[:, 0] = np.random.uniform(
            -_XY_SPREAD * 2, _XY_SPREAD * 2, n_horizon
        )
        self._horizon[:, 1] = np.random.uniform(
            -_XY_SPREAD * 2, _XY_SPREAD * 2, n_horizon
        )
        self._horizon[:, 2] = _Z_FAR * np.ones(n_horizon, dtype=np.float32)

        self._start_ts = time.time()
        self._last_ts = time.time()
        self._vection_active = False

        self._speed = 0.12  # units/frame
        self._color = (0.9, 0.9, 0.9)
        self._pt_size = 2.0
        self._fov_deg = 90.0  # matched to typical HMD horizontal FOV
        self._session_count = 0

    # ── Public interface ───────────────────────────────────────────────────────

    def start(self) -> None:
        self._start_ts = time.time()
        self._last_ts = time.time()
        self._vection_active = True
        patch_live({"vr_vection_active": True, "vr_vection_phase_s": 0.0})

    def stop(self) -> None:
        self._vection_active = False
        patch_live({"vr_vection_active": False})

    def update_cfg(self, cfg: dict) -> None:
        """Pull latest parameters from live_control.json snapshot."""
        raw_speed = float(cfg.get("vr_vection_speed", 0.5))
        n_new = int(cfg.get("vr_vection_density", 800))
        cap = _SESSION_SPEED_CAP.get(min(self._session_count, 4), _SESSION_SPEED_CAP[4])
        self._speed = min(raw_speed * _DEFAULT_SPEED_UNITS * 2, cap)
        self._pt_size = float(cfg.get("vr_vection_star_size", 2.0))
        self._color = (
            float(cfg.get("vr_vection_color_r", 0.90)),
            float(cfg.get("vr_vection_color_g", 0.90)),
            float(cfg.get("vr_vection_color_b", 0.92)),
        )
        # Adaptive: if binocular integration is rising fast, reduce speed
        bi = float(cfg.get("ssvep_binocular_index") or 0.0)
        if bi > 0.7:
            self._speed *= 0.6  # throttle to 60% when strongly integrated

        if n_new != self._n:
            self._n = n_new
            self._pos = self._spawn_all()

    def simulate(self) -> None:
        """Advance particle positions by one frame (delta-time corrected)."""
        if not self._vection_active:
            return
        now = time.time()
        dt = min(now - self._last_ts, 0.05)  # cap at 50 ms to avoid spiral on stall
        self._last_ts = now

        # Advance all particles toward camera (decreasing Z)
        self._pos[:, 2] -= self._speed * dt * 60.0  # normalised to 60 fps

        # Respawn particles that passed the near plane
        expired = self._pos[:, 2] < _Z_NEAR
        n_expired = int(expired.sum())
        if n_expired > 0:
            new = self._spawn_n(n_expired)
            self._pos[expired] = new

        if now - self._start_ts > 0:
            patch_live({"vr_vection_phase_s": round(now - self._start_ts, 1)})

    def render_eye(self, eye_index: int, viewport_w: int, viewport_h: int) -> None:
        """Render the particle field into the currently bound eye framebuffer.

        Uses OpenGL immediate mode for broad compatibility.  Particles are
        projected using a simple perspective transform matching the
        OpenXR FoV for this eye.
        """
        try:
            from OpenGL import GL
        except ImportError:
            return

        if not self._vection_active:
            return

        # Set up perspective projection
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        _perspective(
            self._fov_deg,
            viewport_w / max(viewport_h, 1),
            z_near=0.1,
            z_far=_Z_FAR + 10.0,
        )

        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glPointSize(self._pt_size)

        r, g, b = self._color

        # Draw flowing particles
        GL.glBegin(GL.GL_POINTS)
        for x, y, z in self._pos:
            # Fade out near the near-plane so there's no pop-in
            alpha = min(1.0, (z - _Z_NEAR) / 5.0)
            GL.glColor4f(r, g, b, alpha)
            GL.glVertex3f(
                float(x), float(y), -float(z)
            )  # OpenGL z is into screen (negative)
        GL.glEnd()

        # Draw horizon anchors (dim and small — just a visual anchor)
        GL.glPointSize(max(1.0, self._pt_size * 0.6))
        GL.glBegin(GL.GL_POINTS)
        GL.glColor4f(r * 0.4, g * 0.4, b * 0.4, 0.5)
        for x, y, z in self._horizon:
            GL.glVertex3f(float(x), float(y), -float(z))
        GL.glEnd()

        GL.glDisable(GL.GL_DEPTH_TEST)

    # ── Private ────────────────────────────────────────────────────────────────

    def _spawn_all(self) -> np.ndarray:
        pos = np.zeros((self._n, 3), dtype=np.float32)
        pos[:, 0] = np.random.uniform(-_XY_SPREAD, _XY_SPREAD, self._n)
        pos[:, 1] = np.random.uniform(-_XY_SPREAD, _XY_SPREAD, self._n)
        pos[:, 2] = np.random.uniform(_Z_NEAR * 2, _Z_FAR, self._n)
        return pos

    def _spawn_n(self, n: int) -> np.ndarray:
        """Spawn n particles at the far plane with random XY."""
        pts = np.zeros((n, 3), dtype=np.float32)
        pts[:, 0] = np.random.uniform(-_XY_SPREAD, _XY_SPREAD, n)
        pts[:, 1] = np.random.uniform(-_XY_SPREAD, _XY_SPREAD, n)
        pts[:, 2] = np.random.uniform(_Z_FAR * 0.8, _Z_FAR, n)
        return pts


def _perspective(fov_deg: float, aspect: float, z_near: float, z_far: float) -> None:
    """Apply a perspective projection matrix via glMultMatrixf."""
    try:
        from OpenGL import GL

        f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
        m = [
            f / aspect,
            0,
            0,
            0,
            0,
            f,
            0,
            0,
            0,
            0,
            (z_far + z_near) / (z_near - z_far),
            -1,
            0,
            0,
            (2 * z_far * z_near) / (z_near - z_far),
            0,
        ]
        GL.glMultMatrixf(m)
    except Exception:
        pass
