"""
llm_driver.py  —  Somna LLM Control Interface
================================================
The live_control.json file is the real-time bridge between the control
panel, the timeline runner, and external drivers (like an LLM agent).
Any process that writes valid JSON to live_control.json will see its
changes reflected in the running display within ~100 ms.

This module provides:
  - send()       — write a partial or full parameter dict live
  - read_state() — read the current live state (what is playing now)
  - All valid parameter names and their ranges, as constants and docstrings

Intended usage from an LLM:

    from llm_driver import send, read_state, PARAMS

    # Fade to a deep theta state over a long ramp
    send({"beat_frequency": 6.0, "carrier_frequency": 180})

    # Check what is currently playing
    state = read_state()
    print(state["session_time"], state["beat_frequency"])
"""

import json
from pathlib import Path
from typing import Any
from ipc import patch_live

_LIVE = Path(__file__).resolve().parent.parent / "live_control.json"

# ── Parameter reference ───────────────────────────────────────────────────────

PARAMS = {
    # ── Audio ─────────────────────────────────────────────────────────────────
    "carrier_frequency": "float  80–400 Hz   — base tone pitch (left ear)",
    "beat_frequency": "float  0.5–40 Hz   — binaural beat (right = carrier + beat)",
    "volume": "float  0–100       — mixer volume percentage",
    # ── Spirals ───────────────────────────────────────────────────────────────
    "spiral_style": "str    one of: tunnel_dream | galaxy | archimedean | "
    "kaleidoscope | interference | vortex | dna | "
    "rose | moire | spirograph | fermat | superformula | "
    "liminal | nebula | cobwebs | strange_attractor | "
    "flow_field | sacred_geometry | recursive_fractal | "
    "potter_tunnel | fractal_scale | neuro_vortex | "
    "ojascki | tunnel_warp | ganzflicker | galaxy_morph",
    "spiral_count": "int    1–8         — number of arms/petals",
    "spiral_tightness": "float  2.0–12.0    — winding tightness",
    "spiral_thickness": "int    4–40        — line width",
    "spiral_speed_multiplier": "float  0.1–3.0     — rotation / animation speed",
    "spiral_chaos": "float  0.0–0.8     — distortion / organic noise",
    "spiral_opacity": "int    10–100      — spiral layer opacity %",
    "spiral_color_mode": "str    rainbow | solid",
    "spiral_base_color": "list   [R, G, B]   — 0–255 each; hue bias in rainbow mode",
    "spiral_show_text": "bool   — show affirmation text along spiral arms",
    # ── Veil (ambient affirmation overlay) ────────────────────────────────────
    "veil_opacity": "float  0–100       — overall veil opacity",
    "veil_mode": "str    null (auto-rotate) | scroll | rain | drift | converge",
    "veil_density": "float  0.5–3.0     — phrase density multiplier",
    # ── Background slideshow ──────────────────────────────────────────────────
    "slideshow_interval": "float  seconds between image switches (0.001 fast — 60 slow)",
    "bg_mode": "str|null  — null = normal image slideshow; "
    "'none' = fully transparent background (no images rendered). "
    "Use with window_always_on_top + window_click_through for a "
    "pure text/spiral overlay with no background.",
    # ── Center text (beat-synced flash) ───────────────────────────────────────
    "center_flash_sync_to_beat": "bool   — if true, on/off times derived from beat_frequency",
    "flash_duty_cycle": "float  0.1–0.9     — fraction of beat cycle text is ON",
    "flash_variance": "float  0–0.5       — random timing jitter",
    "center_flash_on_time": "int    ms text is visible (used when sync is OFF)",
    "center_flash_off_time": "int    ms text is hidden  (used when sync is OFF)",
    # ── Subliminal shadow flashes ─────────────────────────────────────────────
    "shadow_opacity": "float  0–100       — opacity of shadow layer",
    "shadow_flash_on_time": "int    ms shadow is shown  — keep ≤ 50 for subliminal",
    "shadow_flash_off_time": "int    ms shadow is hidden",
    "shadow_count": "int    number of simultaneous shadow positions",
    # ── Text and font ─────────────────────────────────────────────────────────
    "text_color": "list   [R, G, B] 0–255 — color of all text layers",
    "font_switch_mode": "str    intelligent (5-12 s dwell) | rapid (0.15-0.45 s)",
    # ── Affirmations ──────────────────────────────────────────────────────────
    "affirmations_pool": "list[str]  — override phrase pool for all text layers; "
    "set to null to revert to session file",
    "phrases": "str   tag name — activate a tag group from affirmations.txt; "
    "null = use all untagged phrases",
    # ── Window / Overlay ──────────────────────────────────────────────────────
    # These are especially useful for agent-driven sessions where the display
    # should run passively without disrupting the user's normal activity.
    "window_always_on_top": "bool  — keep display above all other windows",
    "window_click_through": "bool  — mouse events pass through to apps behind the display; "
    "combined with always_on_top creates a fully passive overlay. "
    "Side-effect: window loses taskbar entry and stops accepting "
    "keyboard input (ESC / F11 disabled) — user must stop via "
    "the control panel Stop button.",
    "window_opacity": "int   10–100  — whole-window opacity %; "
    "100 = fully opaque (default), lower = see-through overlay",
    # ── Interactive feedback loop ──────────────────────────────────────────────
    # Write llm_prompt to ask the user something; the control panel shows a
    # floating input dialog.  Read user_response to get their answer.
    "llm_prompt": "str|null  — agent writes a question here; control panel "
    "pops up an input dialog; cleared automatically after response",
    "llm_prompt_timeout_s": "int|null  — seconds before the dialog auto-skips; "
    "null = no timeout",
    "user_response": "str|null  — typed response from the user; null if skipped; "
    "agent should clear this after reading",
    "response_timestamp": "float     — time.time() when the response was submitted; "
    "use to detect staleness",
}

# ── Brainwave state presets ───────────────────────────────────────────────────

PRESETS = {
    "delta": {"carrier_frequency": 150, "beat_frequency": 2.0},  # deep sleep / healing
    "theta": {"carrier_frequency": 180, "beat_frequency": 6.0},  # meditation / dreaming
    "alpha": {"carrier_frequency": 200, "beat_frequency": 10.0},  # relaxed awareness
    "beta": {"carrier_frequency": 220, "beat_frequency": 20.0},  # alert focus
    "gamma": {"carrier_frequency": 300, "beat_frequency": 40.0},  # peak cognition
}

# ── I/O helpers ───────────────────────────────────────────────────────────────


def read_state() -> dict[str, Any]:
    """Return the full current live_control.json as a dict.

    Useful keys the LLM should monitor:
      session_time      — float seconds elapsed in the current session
      session_duration  — float total session length (or null)
      timeline_label    — str  label of the current timeline keyframe
      timeline_paused   — bool whether the timeline runner is currently paused
      beat_frequency    — float currently playing beat frequency
      spiral_style      — str  active spiral
      timeline_locked_params — list[str] params locked by user slider overrides

    Timeline control commands (write to _timeline_cmd key via send()):
      "pause"           — pause the session timeline
      "resume"          — resume a paused timeline
      "restart"         — jump back to t=0 and clear user locks
      "load"            — load session named by session_folder key
    """
    if not _LIVE.exists():
        return {}
    try:
        return json.loads(_LIVE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def send(params: dict[str, Any]) -> None:
    """Merge params into live_control.json.  Changes are picked up within 100 ms.

    Only the keys you provide are updated — all other values are preserved.
    You do NOT need to send the full state every call.

    Examples
    --------
    # Transition to theta meditation state
    send({"beat_frequency": 6.0, "carrier_frequency": 180, "veil_mode": "drift"})

    # Apply a named preset
    send(PRESETS["gamma"])

    # Activate a specific phrase tag group
    send({"phrases": "trance_induction"})

    # Override affirmations pool directly
    send({"affirmations_pool": ["Good girl.", "Relax.", "Let go."]})

    # Restore auto affirmations
    send({"affirmations_pool": None})

    # Burst of fast text then return to calm
    send({"center_flash_on_time": 16, "center_flash_off_time": 16,
          "center_flash_sync_to_beat": False})
    # ... later ...
    send({"center_flash_sync_to_beat": True})

    # Run as a passive background overlay — display stays visible over any app,
    # mouse clicks pass through, window vanishes from taskbar and ignores ESC.
    # The user can only stop the display via the control panel Stop button.
    send({
        "window_always_on_top": True,
        "window_click_through": True,
        "window_opacity": 60,
    })

    # Restore to normal fullscreen (non-overlay) mode
    send({
        "window_always_on_top": False,
        "window_click_through": False,
        "window_opacity": 100,
    })
    """
    patch_live(params)


def apply_preset(name: str, extra: dict | None = None) -> None:
    """Apply a named brainwave preset, optionally with additional overrides.

    Available presets: delta, theta, alpha, beta, gamma
    """
    if name not in PRESETS:
        raise ValueError(f"Unknown preset '{name}'. Choose from: {list(PRESETS)}")
    params = dict(PRESETS[name])
    if extra:
        params.update(extra)
    send(params)


def prompt_user(
    text: str, timeout_s: int | None = None, style: dict | None = None
) -> None:
    """Display a question to the user via the control panel's floating popup.

    The question appears as a styled dialog over the display.  The user types
    their answer and hits Submit (or Ctrl+Enter).  Their response is written to
    ``user_response`` in live_control.json.

    This function is **non-blocking** — it just writes to live_control.json and
    returns immediately.  Use :func:`wait_for_response` to block until answered,
    or poll :func:`read_response` yourself.

    Parameters
    ----------
    text : str
        The question or prompt to show the user.
    timeout_s : int | None
        If set, the dialog shows a countdown and auto-skips after this many
        seconds, writing ``user_response: null``.
    style : dict | None
        Optional ``llm_prompt_style`` overrides (e.g. ``{"needs_response": False}``).
    """
    import time as _time

    ts = _time.time()
    style = style or {}
    patch_live(
        {
            "agent_message": {
                "text": text,
                "ts": ts,
                "needs_response": style.get("needs_response", True),
                "via": ["overlay"],
                "style": style,
                "timeout_s": timeout_s,
            },
            "user_response": None,
            "response_timestamp": None,
        }
    )


_UNANSWERED = object()


def read_response(clear: bool = True):
    """Return the latest user response.

    Returns
    -------
    str | None
        The user's response string, or ``None`` if the user skipped.
    _UNANSWERED sentinel
        If no response has been submitted yet (``response_timestamp`` is null).
    """
    state = read_state()
    if state.get("response_timestamp") is None:
        return _UNANSWERED
    response = state.get("user_response")
    if clear:
        patch_live({"user_response": None, "response_timestamp": None})
    return response


def wait_for_response(
    timeout_s: float = 60.0, poll_interval: float = 0.25
) -> str | None:
    """Block until the user submits a response or ``timeout_s`` elapses.

    Returns the response string, or ``None`` if the user skipped / timed out.
    Ignores stale response_timestamp values that predate this call.
    """
    import time

    deadline = time.monotonic() + timeout_s
    start_wall = time.time()
    time.sleep(0.5)
    print(f"[wait_for_response] start_wall={start_wall:.3f} timeout={timeout_s}s")
    poll_count = 0
    try:
        while time.monotonic() < deadline:
            poll_count += 1
            state = read_state()
            ts = state.get("response_timestamp")
            if ts is not None:
                print(
                    f"[wait_for_response] poll#{poll_count} ts={ts:.3f} (delta={ts - start_wall:+.3f}s) {'ACCEPT' if ts >= start_wall else 'STALE'}"
                )
            if ts is not None and ts >= start_wall:
                response = state.get("user_response")
                patch_live({"user_response": None, "response_timestamp": None})
                return response
            time.sleep(poll_interval)
        print(f"[wait_for_response] TIMED OUT after {poll_count} polls")
    except Exception as e:
        print(f"[wait_for_response] EXCEPTION: {e}")
    return None


def passive_overlay(opacity: int = 60, *, disable: bool = False) -> None:
    """Enable (or disable) the passive overlay mode.

    In passive overlay mode the display window:
      - Floats above every other application (always-on-top)
      - Passes all mouse clicks through to apps below (click-through)
      - Is rendered at ``opacity`` percent transparency
      - Disappears from the taskbar and no longer responds to keyboard input
        (ESC / F11 are disabled; stop the display via the control panel)

    This is the intended deployment mode for agent-driven sessions where the
    display should condition the user without disrupting their normal activity.

    Parameters
    ----------
    opacity : int
        Window opacity percentage (10–100).  Default 60 gives a clearly
        visible but non-intrusive overlay.
    disable : bool
        Pass ``True`` to restore normal fullscreen (non-overlay) mode.
    """
    if disable:
        send(
            {
                "window_always_on_top": False,
                "window_click_through": False,
                "window_opacity": 100,
            }
        )
    else:
        send(
            {
                "window_always_on_top": True,
                "window_click_through": True,
                "window_opacity": max(10, min(100, opacity)),
            }
        )


# ── Quick reference for LLM context ──────────────────────────────────────────


def describe() -> str:
    """Return a formatted string describing all controllable parameters."""
    lines = ["Somna live parameters (write to live_control.json via send()):\n"]
    for key, desc in PARAMS.items():
        lines.append(f"  {key:<35} {desc}")
    lines.append("\nBrainwave presets (apply_preset name):")
    for name, vals in PRESETS.items():
        lines.append(
            f"  {name:<12} carrier={vals['carrier_frequency']} Hz, "
            f"beat={vals['beat_frequency']} Hz"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
    print("\nCurrent state:")
    state = read_state()
    for k, v in state.items():
        print(f"  {k}: {v}")
