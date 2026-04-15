"""
vr_subliminal.py — Stereoscopic Depth-Plane Subliminal Delivery (Bible Ch.8 §8.6)
=========================================================================
Delivers independent affirmation streams at three stereoscopic depth planes.

The mechanism exploits a fundamental property of backward masking in VR:
a mask only suppresses a target when both share the same binocular disparity
(depth plane).  Targets at different depths require separate masks, so we
can carry three independent subliminal streams without interference.

Depth planes (Bible Ch.8 §8.6 §3):
  NEAR   — disparity ~-2.0° (eye-crossing, foreground, ~0.5 m virtual)
  MID    — disparity ~0.0°  (screen plane, neutral)
  FAR    — disparity ~+1.5° (divergent, background, ~4 m virtual)

Each plane has its own:
  - Affirmation phrase pool (rotated from the global pool by the agent)
  - Independent on/mask timing (SOA = Stimulus Onset Asynchrony, default 33 ms)
  - Opacity envelope: target flash → rapid mask → hold black

Vergence-accommodation conflict (VAC) mitigation (Bible Ch.8 §8.6 §8):
  - Near plane exposure < 25% of total subliminal time
  - Total subliminal session < 20 minutes per session
  - Minimum 3-frame gap between exposures on any one plane
  - Text displayed only during MAINTENANCE and FRAC_EMERGE phases

live_control.json keys read:
  vr_subliminal_enabled     bool    master on/off
  vr_subliminal_near_pool   list    phrases for near plane
  vr_subliminal_mid_pool    list    phrases for mid plane
  vr_subliminal_far_pool    list    phrases for far plane
  vr_subliminal_soa_ms      float   stimulus onset asynchrony in ms (default 33)
  vr_subliminal_intensity   float   0–1 text brightness (default 0.8)
  conductor_phase           str     only active in maintenance/frac phases

live_control.json keys written:
  vr_subliminal_active         bool   True while delivering
  vr_subliminal_plane_counts   dict   delivered count per plane {near, mid, far}
  vr_subliminal_vac_minutes    float  accumulated near-plane exposure minutes
"""
from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from ipc import patch_live

_LIVE_PATH = Path(__file__).parent.parent / "live_control.json"

# ── Depth plane disparity parameters (in degrees; sign = crossed/uncrossed) ───
# These map to OpenGL horizontal translation offsets for each eye.
# Positive = divergent (far) — objects appear behind the screen.
# Negative = crossed (near) — objects appear in front of the screen.
_DISPARITY_DEG = {
    "near": -2.0,
    "mid":   0.0,
    "far":  +1.5,
}

# Disparity to horizontal eye-offset (at ~1 m viewing distance in HMD coords)
# offset_m ≈ ipd_m * sin(disparity_rad / 2)  ≈ disparity_rad * 0.032  (half-IPD)
_DEG_TO_OFFSET_SCALE = 0.032 / (180.0 / math.pi)   # m per degree at 0.5 m

# VAC mitigation: near plane limited to 25% of total subliminal time
_MAX_NEAR_FRACTION = 0.25
_MAX_SESSION_MINUTES = 20.0

# Subliminal SOA schedule (ms):
#   33 ms  — target display (approximately 2 frames @ 60 fps, 3 @ 90 fps)
#   17 ms  — blank inter-frame
#   83 ms  — visual noise mask
_DEFAULT_SOA_MS     = 33.0
_DEFAULT_MASK_MS    = 83.0
_DEFAULT_BLANK_MS   = 17.0

# Only deliver during these phases (from conductor_phase)
_ACTIVE_PHASES = {"maintenance", "frac_emerge", "frac_emerge_hold", "frac_redrop"}
def _read_live() -> dict:
    try:
        return json.loads(_LIVE_PATH.read_text(encoding="utf-8")) if _LIVE_PATH.exists() else {}
    except Exception:
        return {}


class PlaneState(Enum):
    IDLE    = "idle"
    TARGET  = "target"
    BLANK   = "blank"
    MASK    = "mask"


@dataclass
class DepthPlane:
    name:       str
    disparity:  float          # degrees; negative = near
    phrases:    list[str]      = field(default_factory=list)
    phrase_idx: int            = 0

    # Subliminal exposure state
    state:      PlaneState  = PlaneState.IDLE
    state_ts:   float       = 0.0
    current_phrase: str     = ""
    delivered_count: int    = 0
    min_frames_gap: int     = 3
    frames_since_mask: int  = 0

    def next_phrase(self) -> str:
        if not self.phrases:
            return ""
        p = self.phrases[self.phrase_idx % len(self.phrases)]
        self.phrase_idx = (self.phrase_idx + 1) % len(self.phrases)
        return p

    def disparity_offset(self) -> float:
        """Horizontal eye offset in metres for this plane's disparity."""
        return self.disparity * _DEG_TO_OFFSET_SCALE


class SubLiminalRenderer:
    """Per-eye stereoscopic subliminal text delivery.

    Call render_eye() once per frame per eye inside the pyopenxr view loop.
    The renderer manages the full SOA schedule independently per plane.

    Text rendering uses OpenGL bitmap fonts via GLUT (or falls back to dots
    if GLUT is unavailable) for maximum compatibility across headsets.
    """

    def __init__(self):
        self._planes: dict[str, DepthPlane] = {
            "near": DepthPlane("near", _DISPARITY_DEG["near"]),
            "mid":  DepthPlane("mid",  _DISPARITY_DEG["mid"]),
            "far":  DepthPlane("far",  _DISPARITY_DEG["far"]),
        }
        self._enabled          = False
        self._session_start    = 0.0
        self._near_exposure_s  = 0.0
        self._total_exposure_s = 0.0
        self._soa_ms           = _DEFAULT_SOA_MS
        self._mask_ms          = _DEFAULT_MASK_MS
        self._blank_ms         = _DEFAULT_BLANK_MS
        self._intensity        = 0.8
        self._last_cfg_ts      = 0.0
        self._delivered_counts = {"near": 0, "mid": 0, "far": 0}

    # ── Public interface ───────────────────────────────────────────────────────

    def start(self) -> None:
        self._enabled       = True
        self._session_start = time.time()
        patch_live({"vr_subliminal_active": True,
                     "vr_subliminal_plane_counts": self._delivered_counts})

    def stop(self) -> None:
        self._enabled = False
        patch_live({"vr_subliminal_active": False})

    def update_cfg(self, cfg: dict) -> None:
        """Pull phrase pools and timing from live_control.json snapshot."""
        self._soa_ms     = float(cfg.get("vr_subliminal_soa_ms",  _DEFAULT_SOA_MS))
        self._intensity  = float(cfg.get("vr_subliminal_intensity", 0.8))
        self._planes["near"].phrases = list(cfg.get("vr_subliminal_near_pool") or [])
        self._planes["mid"].phrases  = list(cfg.get("vr_subliminal_mid_pool")  or [])
        self._planes["far"].phrases  = list(cfg.get("vr_subliminal_far_pool")  or [])

    def should_be_active(self, cfg: dict) -> bool:
        """True if the conductor phase allows subliminal delivery."""
        if not cfg.get("vr_subliminal_enabled"):
            return False
        phase = (cfg.get("conductor_phase") or "").lower()
        return phase in _ACTIVE_PHASES

    def render_eye(self, eye_index: int, timestamp: float, cfg: dict) -> None:
        """Render all depth planes for this eye.

        eye_index: 0 = left, 1 = right
        The disparity offset is applied in opposite directions for each eye:
          left eye:  -offset  (shifts image left → convergent/near plane)
          right eye: +offset
        """
        if not self._enabled:
            return

        now = timestamp
        # Refresh cfg every 0.5 s to pick up new phrase pools without hammering disk
        if now - self._last_cfg_ts > 0.5:
            self.update_cfg(cfg)
            self._last_cfg_ts = now

        # Update VAC exposure counters
        self._total_exposure_s += 1.0 / 90.0   # assume 90 fps
        near_plane = self._planes["near"]
        if near_plane.state == PlaneState.TARGET:
            self._near_exposure_s += 1.0 / 90.0

        # VAC guard: disable near plane if exposure fraction too high
        near_fraction = (self._near_exposure_s /
                         max(self._total_exposure_s, 1.0))
        if near_fraction > _MAX_NEAR_FRACTION:
            near_plane.state = PlaneState.IDLE

        # Session time guard
        session_minutes = self._total_exposure_s / 60.0
        if session_minutes > _MAX_SESSION_MINUTES:
            self.stop()
            return

        try:
            from OpenGL import GL
        except ImportError:
            return

        for plane in self._planes.values():
            self._render_plane(plane, eye_index, now, GL)

        # Periodically report counts
        if int(now) % 10 == 0:
            patch_live({
                "vr_subliminal_plane_counts": self._delivered_counts,
                "vr_subliminal_vac_minutes":  round(self._near_exposure_s / 60.0, 3),
            })

    # ── Private ────────────────────────────────────────────────────────────────

    def _render_plane(self, plane: DepthPlane, eye_index: int,
                      now: float, GL) -> None:
        """Advance SOA state machine and draw text or mask for this plane."""
        if not plane.phrases:
            return

        plane.frames_since_mask += 1

        dt_ms = (now - plane.state_ts) * 1000.0

        if plane.state == PlaneState.IDLE:
            if plane.frames_since_mask >= plane.min_frames_gap:
                plane.current_phrase = plane.next_phrase()
                plane.state    = PlaneState.TARGET
                plane.state_ts = now
                plane.frames_since_mask = 0

        elif plane.state == PlaneState.TARGET:
            if dt_ms >= self._soa_ms:
                plane.state    = PlaneState.BLANK
                plane.state_ts = now

        elif plane.state == PlaneState.BLANK:
            if dt_ms >= self._blank_ms:
                plane.state    = PlaneState.MASK
                plane.state_ts = now

        elif plane.state == PlaneState.MASK:
            if dt_ms >= self._mask_ms:
                plane.state    = PlaneState.IDLE
                plane.state_ts = now
                plane.delivered_count += 1
                self._delivered_counts[plane.name] = plane.delivered_count

        # Render based on current state
        if plane.state == PlaneState.TARGET:
            self._draw_text(plane, eye_index, self._intensity, GL, mask=False)
        elif plane.state == PlaneState.MASK:
            self._draw_text(plane, eye_index, self._intensity * 0.6, GL, mask=True)

    def _draw_text(self, plane: DepthPlane, eye_index: int,
                   intensity: float, GL, mask: bool = False) -> None:
        """Draw text at the stereo depth position for this plane and eye."""
        # Compute horizontal disparity shift for this eye
        # Left eye (-1): positive disparity → move right (uncrossed/far)
        # Right eye (+1): positive disparity → move left
        eye_sign = -1 if eye_index == 0 else +1
        x_offset = eye_sign * plane.disparity_offset()

        text = plane.current_phrase if not mask else _noise_mask(plane.current_phrase)
        if not text:
            return

        GL.glPushMatrix()
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()

        # Position text in the centre of the field at the plane's virtual depth
        # Negative Z = in front of the camera in OpenGL convention
        z_depth = -1.5 if plane.name == "near" else (-3.0 if plane.name == "mid" else -6.0)
        GL.glTranslatef(x_offset - 0.15 * len(text) * 0.01,
                        -0.02, z_depth)

        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glColor4f(intensity, intensity, intensity, 0.9)

        _gl_draw_string(text, GL)

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glPopMatrix()


_GLUT_AVAILABLE: bool | None = None   # None = untested, True = ok, False = unavailable


def _gl_draw_string(text: str, GL) -> None:
    """Draw a string using GLUT bitmap fonts, with one-time init and graceful fallback.

    GLUT is initialised once on first call.  If it fails, all subsequent calls
    are no-ops so the per-frame path stays clean.  A future upgrade should
    replace this with SDF font rendering (Bible Ch.8 §8.6 §5) for production quality.
    """
    global _GLUT_AVAILABLE
    if _GLUT_AVAILABLE is False:
        return
    try:
        from OpenGL import GLUT
        if _GLUT_AVAILABLE is None:
            GLUT.glutInit()
            _GLUT_AVAILABLE = True
        for ch in text:
            GLUT.glutBitmapCharacter(GLUT.GLUT_BITMAP_HELVETICA_18, ord(ch))
    except Exception as e:
        if _GLUT_AVAILABLE is None:
            print(f"[VR Subliminal] GLUT unavailable ({e}) — text rendering disabled. "
                  f"Install freeglut or upgrade to SDF font rendering for production.")
        _GLUT_AVAILABLE = False


def _noise_mask(text: str) -> str:
    """Generate a visual noise mask that occludes subliminal text.

    The mask is a random string of the same length as the target,
    using uppercase letters and symbols to maximally disrupt letter
    recognition via lateral inhibition.
    """
    _mask_chars = "XOZR#@%&*+=-~|<>[]{}^"
    return "".join(random.choice(_mask_chars) for _ in text)


