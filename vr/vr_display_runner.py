"""
vr_display_runner.py — Somna VR Headset Subprocess (Docs 29–33)
================================================================
Launched from the control panel (Tk or ImGui) when the user starts the
OpenXR headset flow: the panel sets vr_headset_enabled True and spawns this
file as a subprocess.  This process is not auto-started by the Conductor.

Renders per-eye content to an OpenXR headset (Meta Quest, Valve Index, etc.)
via pyopenxr.  This path is separate from the SteamVR overlay mirror
(visual_display --vr).

Architecture mirrors visual_display_runner.py:
  - Subprocess only; no __main__ guard bypass
  - live_control.json is the sole IPC channel
  - Exits cleanly when live_control.json sets vr_headset_enabled = false
    or when the process receives a shutdown signal

Render modes (controlled by vr_render_mode in live_control.json):
  "ganzfeld"        — uniform grey per eye (Bible Ch.8 §8.3)
  "photic"          — bilateral same-frequency flicker (Bible Ch.8 §8.4)
  "rivalry"         — per-eye independent rivalry tag flicker (Bible Ch.8 §8.2)
  "dichoptic_ssvep" — per-eye SSVEP measurement tags (Bible Ch.8 §8.1)

Live control keys read:
  vr_headset_enabled      bool   — master on/off switch
  vr_render_mode          str    — see above
  vr_background_lum       float  — 0–1 Ganzfeld grey level (default 0.5)
  vr_photic_hz            float  — bilateral photic frequency
  vr_photic_depth         float  — bilateral photic depth (0–1)
  vr_photic_waveform      str    — "sine"|"square"|"sawtooth"
  vr_rivalry_left_hz      float  — left eye rivalry tag
  vr_rivalry_right_hz     float  — right eye rivalry tag
  vr_rivalry_depth        float  — rivalry tag depth
  vr_ssvep_left_hz        float  — left eye SSVEP measurement tag
  vr_ssvep_right_hz       float  — right eye SSVEP measurement tag
  vr_ssvep_depth          float  — SSVEP tag depth

Live control keys written:
  vr_headset_active       bool   — True while this process is running
  vr_frame_count          int    — total frames rendered
  vr_safety_kill          bool   — True if paroxysmal kill was triggered

SSVEP metrics (ssvep_* keys) are written by vr_ssvep_detector.SSVEPDetector
running inside the EEG acquisition process when hardware is connected —
not by this subprocess.

Entry point: python vr_display_runner.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from ipc import patch_live, read_live

# Ensure the Somna root (parent of this vr/ package) is on sys.path so that
# both `from vr.vr_flicker_engine import ...` and `from eeg.eeg_engine import ...`
# resolve correctly when this file is launched as a subprocess.
_PKG_ROOT = Path(__file__).parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

_ROOT = _PKG_ROOT  # live_control.json lives at Somna root

# ── Optional dependencies with graceful fallback ──────────────────────────────

try:
    import pyopenxr as xr

    _XR_AVAILABLE = True
except ImportError:
    _XR_AVAILABLE = False

try:
    from OpenGL import GL

    _GL_AVAILABLE = True
except ImportError:
    _GL_AVAILABLE = False


# ── IPC helpers ───────────────────────────────────────────────────────────────


def _read_live() -> dict:
    try:
        return read_live()
    except Exception:
        return {}


def run_vr_session() -> None:
    """Open an OpenXR session and run the per-eye render loop.

    Exits when vr_headset_enabled is False or on error.
    """
    from vr.vr_flicker_engine import DichopticFlickerEngine, FlickerMode
    from vr.vr_safety import SafetyEnforcer, check_paroxysmal, PHOTOSENSITIVITY_WARNING

    safety = SafetyEnforcer()
    flicker = DichopticFlickerEngine(safety=safety)

    if not safety.warning_acknowledged:
        print(PHOTOSENSITIVITY_WARNING)
        print("[VR] Recording acknowledgment automatically for subprocess launch.")
        safety.record_acknowledgment()

    print("[VR] Initialising OpenXR session…")
    patch_live({"vr_headset_active": True, "vr_safety_kill": False})

    try:
        with xr.ContextObject(
            instance_create_info=xr.InstanceCreateInfo(
                enabled_extension_names=[xr.KHR_OPENGL_ENABLE_EXTENSION_NAME],
            ),
        ) as context:
            _run_frame_loop(context, flicker, safety)
    except Exception as exc:
        print(f"[VR] OpenXR session error: {exc}")
    finally:
        patch_live({"vr_headset_active": False})
        if not safety.killed:
            safety.advance_ramp_for_next_session()
        print("[VR] Session ended.")


def _run_frame_loop(context, flicker, safety) -> None:
    """Inner frame loop — separated so cleanup in run_vr_session() always runs."""
    from vr.vr_flicker_engine import FlickerMode
    from vr.vr_safety import check_paroxysmal
    from vr.vr_ganzfeld import GanzfeldProtocol, GanzfeldFlicker
    from vr.vr_vection import VectionRenderer
    from vr.vr_subliminal import SubLiminalRenderer
    from vr.vr_ssvep_detector import SSVEPDetector

    frame_count = 0
    last_cfg_ts = 0.0
    last_ssvep_s = 0.0
    cfg = _read_live()
    _apply_cfg(flicker, cfg)
    ssvep_detector = SSVEPDetector(fs=256)

    ganzfeld_proto = GanzfeldProtocol()
    _ganzfeld_started = False

    vection = VectionRenderer(n_particles=int(cfg.get("vr_vection_density", 800)))
    _vection_was_enabled = False

    subliminal = SubLiminalRenderer()
    subliminal.update_cfg(cfg)
    _subliminal_was_active = False

    # Rolling buffer for paroxysmal detection (AF7 channel, 5 s at 256 Hz)
    import numpy as np

    _eeg_buffer: list[float] = []
    _EEG_BUF_MAX = 256 * 5

    for frame_state in context.frame_loop():
        now = time.time()
        cfg = _read_live()

        if not cfg.get("vr_headset_enabled", True):
            print("[VR] vr_headset_enabled → False, shutting down.")
            break

        if safety.killed:
            patch_live({"vr_safety_kill": True})

        # Refresh flicker params every 0.2 s to be responsive without hammering disk
        if now - last_cfg_ts > 0.2:
            _apply_cfg(flicker, cfg)
            last_cfg_ts = now

        # Ganzfeld protocol management
        mode = cfg.get("vr_render_mode", "ganzfeld")
        if mode == "ganzfeld":
            if not _ganzfeld_started:
                ganzfeld_proto.start(timestamp=now, cfg=cfg)
                _ganzfeld_started = True
                patch_live({"vr_ganzfeld_phase": "onset_ramp"})
        else:
            if _ganzfeld_started:
                ganzfeld_proto.stop()
                _ganzfeld_started = False

        # Paroxysmal kill check + SSVEP buffer feed — both use raw EEG from live_control.json
        # (populated by EEGEngine when running; gracefully skipped when unavailable)
        raw_af7 = cfg.get("eeg_raw_af7_last_256")
        raw_af8 = cfg.get("eeg_raw_af8_last_256")
        if raw_af7 and len(raw_af7) == 256:
            if not safety.killed:
                _eeg_buffer.extend(raw_af7)
                if len(_eeg_buffer) > _EEG_BUF_MAX:
                    _eeg_buffer = _eeg_buffer[-_EEG_BUF_MAX:]
                if check_paroxysmal(np.array(_eeg_buffer), fs=256.0):
                    safety.trigger_paroxysmal_kill()
                    flicker.fade_out(duration_s=2.0, timestamp=now)

            # Feed SSVEP detector whenever in dichoptic mode
            if (
                cfg.get("vr_render_mode") == "dichoptic_ssvep"
                and raw_af8
                and len(raw_af8) == 256
            ):
                ssvep_detector.update_batch(np.array(raw_af7), np.array(raw_af8))
                if now - last_ssvep_s >= 1.0:
                    f_left = float(cfg.get("vr_ssvep_left_hz", 7.5))
                    f_right = float(cfg.get("vr_ssvep_right_hz", 12.0))
                    ssvep_detector.detect(f_left, f_right)
                    last_ssvep_s = now

        # Vection: start/stop based on vr_vection_enabled flag
        vection_enabled = (
            bool(cfg.get("vr_vection_enabled", False)) and not safety.killed
        )
        if vection_enabled and not _vection_was_enabled:
            vection.update_cfg(cfg)
            vection.start()
            _vection_was_enabled = True
        elif not vection_enabled and _vection_was_enabled:
            vection.stop()
            _vection_was_enabled = False
        if vection_enabled:
            vection.simulate()

        for eye_index, view in enumerate(context.view_loop(frame_state)):
            if _ganzfeld_started and mode == "ganzfeld":
                luminance = ganzfeld_proto.get_luminance(eye_index, now)
            else:
                luminance = flicker.get_luminance(eye_index, now)

            # Safety override: kill leaves everything at background grey
            if safety.killed:
                luminance = 0.5

            GL.glClearColor(luminance, luminance, luminance, 1.0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

            if vection_enabled:
                # Query swapchain image dimensions from the view
                w = getattr(getattr(view, "sub_image", None), "image_rect", None)
                vw = w.extent.width if w else 1280
                vh = w.extent.height if w else 1280
                vection.render_eye(eye_index, vw, vh)

            if subliminal.should_be_active(cfg) and not safety.killed:
                if not _subliminal_was_active:
                    subliminal.start()
                    _subliminal_was_active = True
                subliminal.render_eye(eye_index, now, cfg)
            elif _subliminal_was_active:
                subliminal.stop()
                _subliminal_was_active = False

        frame_count += 1
        if frame_count % 600 == 0:  # update status every ~10 s at 60 fps
            patch_live({"vr_frame_count": frame_count})


def _apply_cfg(flicker, cfg: dict) -> None:
    """Push live_control.json parameters into the flicker engine."""
    from vr.vr_flicker_engine import FlickerMode

    mode_str = cfg.get("vr_render_mode", "ganzfeld").lower()

    if mode_str == "ganzfeld":
        bg = float(cfg.get("vr_background_lum", 0.5))
        flicker.set_ganzfeld(background=bg)
        flicker.set_mode(FlickerMode.GANZFELD)

    elif mode_str == "photic":
        hz = float(cfg.get("vr_photic_hz", 10.0))
        depth = float(cfg.get("vr_photic_depth", 0.20))
        waveform = str(cfg.get("vr_photic_waveform", "sine"))
        flicker.set_photic_bilateral(hz, depth, waveform)
        flicker.set_mode(FlickerMode.PHOTIC_BILATERAL)

    elif mode_str == "rivalry":
        left_hz = float(cfg.get("vr_rivalry_left_hz", 7.5))
        right_hz = float(cfg.get("vr_rivalry_right_hz", 12.0))
        depth = float(cfg.get("vr_rivalry_depth", 0.20))
        try:
            flicker.set_rivalry_pair(left_hz, right_hz, depth)
            flicker.set_mode(FlickerMode.DICHOPTIC_RIVALRY)
        except ValueError as e:
            print(f"[VR] Rivalry config error: {e} — falling back to ganzfeld.")
            flicker.set_ganzfeld()

    elif mode_str == "dichoptic_ssvep":
        left_hz = float(cfg.get("vr_ssvep_left_hz", 7.5))
        right_hz = float(cfg.get("vr_ssvep_right_hz", 12.0))
        depth = float(cfg.get("vr_ssvep_depth", 0.20))
        try:
            flicker.set_ssvep_pair(left_hz, right_hz, depth)
            flicker.set_mode(FlickerMode.DICHOPTIC_SSVEP)
        except Exception as e:
            print(f"[VR] SSVEP config error: {e} — falling back to ganzfeld.")
            flicker.set_ganzfeld()

    else:
        print(f"[VR] Unknown vr_render_mode '{mode_str}' — using ganzfeld.")
        flicker.set_ganzfeld()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not _XR_AVAILABLE:
        print(
            "[VR] pyopenxr is not installed.  Run:\n"
            "  pip install pyopenxr\n"
            "Then restart the VR display runner."
        )
        sys.exit(1)

    if not _GL_AVAILABLE:
        print(
            "[VR] PyOpenGL is not installed.  Run:\n"
            "  pip install PyOpenGL PyOpenGL_accelerate\n"
            "Then restart the VR display runner."
        )
        sys.exit(1)

    run_vr_session()
