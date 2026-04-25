#!/usr/bin/env python3
"""
Somna MCP Server — Phase 1 (read-only) + Phase 2 (scoped write) + Phase 3 (external agent channel)

Exposes Somna runtime state to LLM clients via the Model Context Protocol.
Run directly: python tools/mcp_somna_server.py
Or via Kilo kilo.json mcp config.

Phase 1: 9 read-only tools.
Phase 2: 4 scoped write tools (key-whitelisted, range-validated, organic safety).
Phase 3: External agent channel — TCP :6790 receives prompts from somna_agent.py,
          forwards them via MCP sampling/createMessage to the connected LLM client
          (Kilo/Resonance). The LLM receives the prompt in its active session with
          full context and MCP tool access. Effects flow back via Phase 2 write tools.
          Agent receives immediate {"status": "delivered"} ack over TCP.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Optional

# ── Paths ────────────────────────────────────────────────────────────────────

SOMNA_ROOT = Path(os.environ.get("SOMNA_ROOT", Path(__file__).parent.parent))
LIVE_CONTROL_PATH = SOMNA_ROOT / "live_control.json"
PROFILE_PATH = SOMNA_ROOT / "user_profile.json"
CONFIG_PATH = SOMNA_ROOT / "agent_config.yaml"
DB_PATH = SOMNA_ROOT / "somna.db"
SESSIONS_DIR = SOMNA_ROOT / "sessions"

# ── live_control.json cache (mtime-based invalidation) ───────────────────────

_lc_mtime: float = 0.0
_lc_size: int = 0
_lc_data: dict[str, Any] = {}

# ── Temporal perception metadata (Reese's "moments" architecture) ─────────────
_session_start: float = 0.0
_call_count: int = 0
_last_call_ts: float = 0.0


def _temporal_meta() -> dict[str, Any]:
    global _session_start, _call_count, _last_call_ts
    now = time.time()
    if _session_start == 0.0:
        _session_start = now
    elapsed = now - _session_start
    since_last = (now - _last_call_ts) if _last_call_ts > 0 else 0.0
    _call_count += 1
    _last_call_ts = now
    calls_per_min = (_call_count / max(elapsed / 60.0, 0.01)) if elapsed > 1.0 else 0.0

    live = _read_live()
    session_time = live.get("session_time", 0) or 0
    cond = live.get("conductor_state") or {}
    phase = cond.get("phase", "") if isinstance(cond, dict) else ""
    phase_ts = cond.get("ts", 0) if isinstance(cond, dict) else 0
    phase_elapsed = (now - phase_ts) if phase_ts else 0.0

    return {
        "session_elapsed_sec": round(elapsed, 1),
        "since_last_call_sec": round(since_last, 1),
        "calls_this_session": _call_count,
        "calls_per_minute_rolling": round(calls_per_min, 1),
        "conductor_phase": phase,
        "conductor_phase_elapsed_sec": round(phase_elapsed, 1),
        "session_playback_sec": round(float(session_time), 1),
    }


def _inject_temporal(response: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(response, dict):
        return response
    response["_temporal"] = _temporal_meta()
    return response


def _compare(actual: Any, expected: Any, op: str) -> bool:
    """Compare actual vs expected using the given operator."""
    try:
        if op == "eq":
            return actual == expected
        if op == "neq":
            return actual != expected
        a, e = float(actual), float(expected)
        if op == "gte":
            return a >= e
        if op == "lte":
            return a <= e
        if op == "gt":
            return a > e
        if op == "lt":
            return a < e
    except (TypeError, ValueError):
        return False
    if op == "contains":
        return expected in str(actual) if actual is not None else False
    return False


# MCP may run from another cwd / venv; if ``ipc.read_live`` is unavailable, fall back to file.
_ipc_read_live: Any = None


def _read_live(keys: list[str] | None = None) -> dict[str, Any]:
    """Read live state — prefer StateServer TCP (``read_live``); else disk.

    The mtime cache was causing stale reads when the file was being
    written rapidly by multiple processes. For an MCP tool called at
    human interaction speed, fresh reads are negligible cost.

    If ``ipc`` is not importable (e.g. MCP host cwd / venv), falls back to
    reading ``live_control.json`` directly.
    """
    global _ipc_read_live
    data: dict[str, Any]

    if _ipc_read_live is None:
        try:
            root = str(SOMNA_ROOT)
            if root not in sys.path:
                sys.path.insert(0, root)
            from ipc import read_live as _ipc_read_live_fn  # type: ignore

            _ipc_read_live = _ipc_read_live_fn
        except Exception:
            _ipc_read_live = False

    if _ipc_read_live is not False:
        try:
            data = _ipc_read_live() or {}
        except Exception:
            data = {}
    else:
        try:
            data = json.loads(LIVE_CONTROL_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

    if keys:
        return {k: data.get(k) for k in keys}
    return data


# ── DB helpers (read-only) ───────────────────────────────────────────────────

_db_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _db_conn
    if _db_conn is None:
        _db_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _db_conn.row_factory = sqlite3.Row
    return _db_conn


def _db_query(sql: str, params: tuple = ()) -> dict[str, Any]:
    """Execute a SELECT query. Reject any non-SELECT statement."""
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed."}
    try:
        cur = _db().execute(sql, params)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description] if cur.description else []
        return {"columns": columns, "rows": [list(row) for row in rows]}
    except Exception as e:
        return {"error": str(e)}


# ── Profile / config helpers ─────────────────────────────────────────────────

_profile_cache: tuple[float, dict[str, Any]] = (0.0, {})


def _read_profile() -> dict[str, Any]:
    global _profile_cache
    try:
        st = PROFILE_PATH.stat()
        if st.st_mtime != _profile_cache[0]:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            _profile_cache = (st.st_mtime, data)
            return data
        return _profile_cache[1]
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ── Session helpers ──────────────────────────────────────────────────────────


def _list_sessions() -> list[dict[str, Any]]:
    sessions = []
    try:
        # Prefer DB registry
        db_result = _db_query(
            "SELECT name, category, play_count, last_played FROM sessions ORDER BY name"
        )
        if "rows" in db_result and not db_result.get("error"):
            for row in db_result["rows"]:
                sessions.append(
                    {
                        "name": row[0],
                        "category": row[1],
                        "play_count": row[2],
                        "last_played": row[3],
                    }
                )
            return sessions
    except Exception:
        pass

    # Fallback: filesystem scan
    for folder in sorted(SESSIONS_DIR.iterdir()):
        if folder.is_dir() and (folder / "session.yaml").exists():
            sessions.append(
                {
                    "name": folder.name,
                    "category": "Unknown",
                    "play_count": 0,
                    "last_played": None,
                }
            )
    return sessions


def _read_session_file(session_name: str, filename: str) -> str:
    path = SESSIONS_DIR / session_name / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"ERROR: {filename} not found for session '{session_name}'"


# ── Phase 2: Write infrastructure ────────────────────────────────────────────

BLOCKED_PATCH_PREFIXES = frozenset(
    {
        "eeg_",  # sensor data owned by eeg_engine
        "ppg_",  # sensor data owned by ppg_engine
        "imu_",  # sensor data owned by imu_engine
        "calibration_",  # calibration state owned by eeg_engine
        "freq_lead_",  # state owned by freq_leader thread
    }
)

BLOCKED_PATCH_KEYS = frozenset(
    {
        "display_active",  # owned by visual_display.py
        "conductor_state",  # owned by conductor.py
        "conductor_summary",  # owned by agent
        "session_time",  # owned by timeline_runner
        "session_duration",  # owned by timeline_runner
        "timeline_paused",  # owned by timeline_runner
        "timeline_label",  # owned by timeline_runner
        "timeline_locked_params",  # owned by timeline_runner
        "playlist_index",  # owned by timeline_runner
        "_timeline_cmd",  # internal command — use proper flow
        "_agent_launch_display",  # use somna_launch_session tool
        "_agent_stop_display",  # use somna_stop_session tool
        "seek_time",  # timeline internal
        "tts_playing",  # owned by control panel
        "tts_playing_ts",  # owned by control panel
        "tts_playing_ms",  # owned by control panel
        "user_response",  # user input
        "response_timestamp",  # user input
        "user_console_input",  # user input
        "user_console_ts",  # user input
    }
)

KNOWN_PATCH_RANGES: dict[str, dict[str, Any]] = {
    "beat_frequency": {"min": 0.5, "max": 40.0},
    "carrier_frequency": {"min": 20.0, "max": 500.0},
    "volume": {"min": 0.0, "max": 100.0},
    "veil_opacity": {"min": 0.0, "max": 100.0},
    "spiral_speed_multiplier": {"min": 0.1, "max": 10.0},
    "spiral_chaos": {"min": 0.0, "max": 100.0},
    "spiral_opacity": {"min": 0.0, "max": 100.0},
    "spiral_count": {"min": 1, "max": 12},
    "spiral_tightness": {"min": 0.5, "max": 20.0},
    "spiral_thickness": {"min": 1, "max": 50},
    "shadow_opacity": {"min": 0.0, "max": 100.0},
    "noise_volume": {"min": 0.0, "max": 100.0},
    "bg_opacity": {"min": 0.0, "max": 100.0},
    "breath_rate_bpm": {"min": 4.0, "max": 12.0},
    "breath_depth": {"min": 0.0, "max": 1.0},
    "fm_mod_depth": {"min": 0.5, "max": 30.0},
    "bilateral_rate": {"min": 0.1, "max": 20.0},
    "bilateral_depth": {"min": 0.0, "max": 1.0},
    "entrainment_strength": {"min": 0.0, "max": 0.10},
    "trail_decay": {"min": 0.0, "max": 0.80},
    "feedback_strength": {"min": 0.0, "max": 1.0},
    "sr_noise_level": {"min": 0.0, "max": 2.0},
    "pp_ca_strength": {"min": 0.0, "max": 1.0},
    "pp_bloom_intensity": {"min": 0.0, "max": 1.0},
    "pp_film_grain": {"min": 0.0, "max": 0.15},
    "haptic_intensity": {"min": 0.0, "max": 100.0},
    "haptic_frequency_hz": {"min": 1.0, "max": 200.0},
    "haptic_pattern_speed": {"min": 0.1, "max": 10.0},
    "tavns_intensity": {"min": 0.0, "max": 100.0},
    "window_opacity": {"min": 0.0, "max": 100.0},
    "center_flash_on_time": {"min": 10, "max": 5000},
    "center_flash_off_time": {"min": 10, "max": 5000},
    "flash_duty_cycle": {"min": 0.0, "max": 1.0},
    "flash_variance": {"min": 0.0, "max": 1.0},
    "slideshow_interval": {"min": 0.5, "max": 60.0},
    "shadow_flash_on_time": {"min": 10, "max": 5000},
    "shadow_flash_off_time": {"min": 10, "max": 5000},
    "spiral_speed_multiplier": {"min": 0.1, "max": 10.0},
}

VALID_SPIRAL_STYLES = frozenset(
    {
        "fibonacci",
        "archimedean",
        "logarithmic",
        "fermat",
        "vogel",
        "tunnel_dream",
        "galaxy",
        "hypnotic",
        "bloom",
        "lissajous",
        "rose",
        "lissajous_3d",
        "maze",
        "cobwebs",
        "strange_attractor",
        "flow_field",
        "sacred_geometry",
        "recursive_fractal",
        "potter_tunnel",
        "fractal_scale",
        "neuro_vortex",
        "ojascki",
        "tunnel_warp",
        "ganzflicker",
        "galaxy_morph",
        "descent",
    }
)

VALID_NOISE_COLORS = frozenset(
    {"white", "pink", "brown", "blue", "violet", "grey", "off"}
)

VALID_BEAT_TYPES = frozenset({"binaural", "isochronic", "both", "fm"})

VALID_BILATERAL_MODES = frozenset({"smooth", "hard"})

VALID_BG_MODES = frozenset({"slideshow", "none"})

VALID_VEIL_MODES = frozenset(
    {"scroll", "rain", "drift", "converge", "strobe", "tunnel"}
)

VALID_FEEDBACK_MODES = frozenset(
    {
        "none",
        "alpha_decay",
        "radial_zoom",
        "rotational_smear",
        "directional_blur",
        "reaction_diffusion",
        "kaleidoscopic_fold",
    }
)

VALID_HAPTIC_PATTERNS = frozenset(
    {
        "continuous",
        "pulse",
        "wave",
        "ramp",
        "fractionation",
        "tmr_cue",
        "conditioned_anchor",
    }
)

VALID_FONT_SWITCH_MODES = frozenset(
    {"intelligent", "rapid", "beat_sync", "breathe_sync", "depth_adaptive"}
)

VALID_COLOR_MODES = frozenset(
    {"rainbow", "mono", "complementary", "analogous", "triadic"}
)

KNOWN_PATCH_ENUMS: dict[str, frozenset] = {
    "spiral_style": VALID_SPIRAL_STYLES,
    "noise_color": VALID_NOISE_COLORS,
    "beat_type": VALID_BEAT_TYPES,
    "bilateral_mode": VALID_BILATERAL_MODES,
    "bg_mode": VALID_BG_MODES,
    "veil_mode": VALID_VEIL_MODES,
    "feedback_mode": VALID_FEEDBACK_MODES,
    "haptic_pattern": VALID_HAPTIC_PATTERNS,
    "font_switch_mode": VALID_FONT_SWITCH_MODES,
    "spiral_color_mode": VALID_COLOR_MODES,
}

ALLOWED_CONDUCTOR_HINT_KEYS = frozenset(
    {
        "depth_patience",
        "request_fractionation",
        "target_floor_hz",
        "note",
        "passthrough",
    }
)


def _validate_patch_value(key: str, value: Any) -> Optional[str]:
    """Validate a patch value. Returns error or None."""
    # Block internal/sensor keys
    if key in BLOCKED_PATCH_KEYS:
        return f"Key '{key}' is internally owned and cannot be written via MCP."
    for prefix in BLOCKED_PATCH_PREFIXES:
        if key.startswith(prefix):
            return f"Key '{key}' is sensor/internal state (prefix '{prefix}') and cannot be written via MCP."
    # Range-check known numeric keys
    spec = KNOWN_PATCH_RANGES.get(key)
    if spec and isinstance(value, (int, float)):
        if "min" in spec and value < spec["min"]:
            return f"Key '{key}' value {value} below minimum {spec['min']}."
        if "max" in spec and value > spec["max"]:
            return f"Key '{key}' value {value} above maximum {spec['max']}."
    # Validate known enum keys
    enum_values = KNOWN_PATCH_ENUMS.get(key)
    if enum_values is not None and isinstance(value, str):
        if value not in enum_values:
            return f"Key '{key}' value '{value}' not in allowed set: {sorted(enum_values)}."
    return None


def _write_live_direct(updates: dict[str, Any]) -> dict[str, Any]:
    """Reload-first merge write to live_control.json. Fallback when StateServer unavailable."""
    for attempt in range(10):
        try:
            data = json.loads(LIVE_CONTROL_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        for k, v in updates.items():
            if v is None:
                data.pop(k, None)
            else:
                data[k] = v
        try:
            with open(LIVE_CONTROL_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            global _lc_data, _lc_mtime, _lc_size
            _lc_data = data
            st = LIVE_CONTROL_PATH.stat()
            _lc_mtime = st.st_mtime
            _lc_size = st.st_size
            return {"written": list(updates.keys())}
        except PermissionError:
            import time

            time.sleep(0.15)
    return {"error": "Permission denied after 10 retries"}


def _try_patch_via_server(updates: dict[str, Any]) -> bool:
    """Attempt to write via StateServer TCP. Returns True if sent."""
    try:
        import socket
        from ipc.state_server import PORT

        msg = json.dumps({"op": "patch", "data": updates}, separators=(",", ":"))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(("127.0.0.1", PORT))
        s.sendall((msg + "\n").encode("utf-8"))
        s.close()
        return True
    except Exception:
        return False


def _patch_live(updates: dict[str, Any]) -> dict[str, Any]:
    """Write to live_control.json via StateServer if available, else direct write."""
    if _try_patch_via_server(updates):
        return {"written": list(updates.keys()), "via": "state_server"}
    return _write_live_direct(updates)


def _append_profile(path: str, value: Any) -> dict[str, Any]:
    """Append to a user_profile.json list field with reload-first merge."""
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"error": "user_profile.json not found or unreadable."}
    parts = path.split(".")
    target = data
    for part in parts[:-1]:
        target = target.get(part, {})
    last_key = parts[-1]
    if last_key not in target or not isinstance(target[last_key], list):
        return {"error": f"Profile path '{path}' is not a list."}
    if isinstance(value, list):
        target[last_key].extend(value)
    else:
        target[last_key].append(value)
    if path == "effective_moments":
        target[last_key] = target[last_key][-30:]
    tmp = PROFILE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PROFILE_PATH)
    global _profile_cache
    st = PROFILE_PATH.stat()
    _profile_cache = (st.st_mtime, data)
    return {"appended": path, "new_length": len(target[last_key])}


def _set_profile(path: str, value: Any) -> dict[str, Any]:
    """Set a user_profile.json scalar field with reload-first merge."""
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"error": "user_profile.json not found or unreadable."}
    parts = path.split(".")
    target = data
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    last_key = parts[-1]
    target[last_key] = value
    tmp = PROFILE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PROFILE_PATH)
    global _profile_cache
    st = PROFILE_PATH.stat()
    _profile_cache = (st.st_mtime, data)
    return {"set": path, "value": value}


def _append_affirmations(session_name: str, lines: list[str]) -> dict[str, Any]:
    """Append lines to a session's affirmations.txt."""
    aff_path = SESSIONS_DIR / session_name / "affirmations.txt"
    if not aff_path.parent.is_dir():
        return {"error": f"Session '{session_name}' not found."}
    existing = ""
    if aff_path.exists():
        existing = aff_path.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
    appended = "\n".join(lines) + "\n"
    aff_path.write_text(existing + appended, encoding="utf-8")
    return {"appended": len(lines), "session": session_name}


def _write_conductor_hint(hints: dict[str, Any]) -> dict[str, Any]:
    """Write agent_conductor_hints to live_control.json with sub-key validation."""
    for k in hints:
        if k not in ALLOWED_CONDUCTOR_HINT_KEYS:
            return {
                "error": f"Hint key '{k}' not allowed. Allowed: {sorted(ALLOWED_CONDUCTOR_HINT_KEYS)}."
            }
    return _patch_live({"agent_conductor_hints": hints})


# ── Structured state builders ────────────────────────────────────────────────


def _build_conductor_state(live: dict[str, Any]) -> dict[str, Any]:
    cs = live.get("conductor_state", {})
    return {
        "phase": cs.get("phase"),
        "phase_duration_s": cs.get("phase_duration_s"),
        "trance_score": live.get("eeg_trance_score"),
        "assr_strength": live.get("eeg_entrainment_strength"),
        "assr_conf": live.get("eeg_entrainment_confidence"),
        "sqi": live.get("eeg_confidence"),
        "frac_count": cs.get("frac_count"),
        "frac_max": cs.get("frac_max"),
        "target_freq_hz": cs.get("target_freq_hz"),
        "iaf_hz": live.get("eeg_iaf_hz"),
        "timer_mode": cs.get("timer_mode", False),
    }


def _build_eeg_snapshot(live: dict[str, Any]) -> dict[str, Any]:
    return {
        "connected": live.get("eeg_connected", False),
        "confidence": live.get("eeg_confidence"),
        "dominant_band": live.get("eeg_dominant_band"),
        "band_powers": {
            "delta": live.get("eeg_delta"),
            "theta": live.get("eeg_theta"),
            "alpha": live.get("eeg_alpha"),
            "beta": live.get("eeg_beta"),
            "gamma": live.get("eeg_gamma"),
        },
        "trance_score": live.get("eeg_trance_score"),
        "trance_score_v2": live.get("eeg_trance_score_v2"),
        "sef95": live.get("eeg_sef95"),
        "spectral_slope": live.get("eeg_spectral_slope"),
        "frontal_asymmetry": live.get("eeg_frontal_asymmetry"),
        "entrainment_strength": live.get("eeg_entrainment_strength"),
        "sleep_stage": live.get("eeg_sleep_stage"),
        "timestamp": live.get("eeg_timestamp"),
    }


# ── MCP Server Setup ─────────────────────────────────────────────────────────

# Try to import the MCP SDK; provide clear error if missing.
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError as exc:
    print("ERROR: mcp Python SDK not installed.")
    print("Install:  pip install mcp")
    print("Docs:     https://github.com/modelcontextprotocol/python-sdk")
    sys.exit(1)

app = Server("somna-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="somna_read_live",
            description="Read keys from live_control.json. Omit keys for all.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of keys to read. Omit for all.",
                    }
                },
            },
        ),
        Tool(
            name="somna_read_conductor",
            description="Structured Conductor FSM state.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="somna_read_eeg",
            description="Structured EEG snapshot.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="somna_query_db",
            description="Run a SELECT query against somna.db. Non-SELECT rejected.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "SQL SELECT statement",
                    }
                },
                "required": ["sql"],
            },
        ),
        Tool(
            name="somna_list_sessions",
            description="List all sessions with metadata.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="somna_read_profile",
            description="Read user_profile.json (identity + preferences).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="somna_tail_decisions",
            description="Last N Conductor decisions from DB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "n": {
                        "type": "integer",
                        "default": 10,
                        "description": "Number of decisions to return",
                    }
                },
            },
        ),
        Tool(
            name="somna_read_session_yaml",
            description="Read a session's session.yaml.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Name of session folder",
                    }
                },
                "required": ["session_name"],
            },
        ),
        Tool(
            name="somna_read_affirmations",
            description="Read a session's affirmations.txt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Name of session folder",
                    }
                },
                "required": ["session_name"],
            },
        ),
        Tool(
            name="somna_patch_live",
            description="Write whitelisted keys to live_control.json. Keys are range-validated.",
            inputSchema={
                "type": "object",
                "properties": {
                    "patches": {
                        "type": "object",
                        "description": "Dict of key-value pairs to write. Only whitelisted keys accepted.",
                    }
                },
                "required": ["patches"],
            },
        ),
        Tool(
            name="somna_update_profile",
            description="Scoped updates to user_profile.json (append or set allowed paths).",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Dot-notation profile path (e.g. 'notes', 'preferences.session_interval_target_days')",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["append", "set"],
                        "description": "'append' for list fields, 'set' for scalar fields",
                    },
                    "value": {
                        "description": "Value to set or append (string, number, list, or object)",
                    },
                },
                "required": ["path", "action", "value"],
            },
        ),
        Tool(
            name="somna_append_affirmations",
            description="Append lines to a session's affirmations.txt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Name of session folder",
                    },
                    "lines": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lines to append",
                    },
                },
                "required": ["session_name", "lines"],
            },
        ),
        Tool(
            name="somna_write_conductor_hint",
            description="Write agent_conductor_hints to live_control.json (depth_patience, request_fractionation, target_floor_hz, note, passthrough). When passthrough=true, conductor skips owned param writes so external agent drives them directly.",
            inputSchema={
                "type": "object",
                "properties": {
                    "hints": {
                        "type": "object",
                        "description": "Dict of hint key-value pairs",
                    }
                },
                "required": ["hints"],
            },
        ),
        Tool(
            name="somna_write_agent_response",
            description=(
                "Write a structured LLM response for somna_agent.py to consume. "
                "Used by the external agent (Resonance) to return the full JSON response "
                "the agent would normally get from its local LLM. Keys: response (str), "
                "adjustments (dict), transitions (dict), action (str), next_prompt (str), "
                "prompt_style (dict), next_affirmation (str), reasoning (str). "
                "The agent reads agent_ext_response after receiving a 'delivered' ack "
                "from the external channel."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "response": {
                        "type": "string",
                        "description": "Text response to show the user (console/overlay)",
                    },
                    "adjustments": {
                        "type": "object",
                        "description": "Parameter adjustments (beat_frequency, volume, veil_opacity, etc.)",
                    },
                    "transitions": {
                        "type": "object",
                        "description": 'Param→duration_s for ramped changes (e.g. {"beat_frequency": 90})',
                    },
                    "action": {
                        "type": "string",
                        "description": "Agent action: 'none', 'fractionate', 'start_session', 'build_session'",
                    },
                    "next_prompt": {
                        "type": "string",
                        "description": "Prompt to show the user (triggers overlay/TTS/dialog)",
                    },
                    "prompt_style": {
                        "type": "object",
                        "description": "Style for message delivery (voice_mode, zoom_speed, intensity, needs_response)",
                    },
                    "next_affirmation": {
                        "type": "string",
                        "description": "Single phrase to inject into the affirmation pool",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Internal reasoning for the agent log",
                    },
                    "session": {
                        "type": "string",
                        "description": "Session folder name (when action=start_session)",
                    },
                    "session_intent": {
                        "type": "string",
                        "description": "Plain-text description (when action=build_session)",
                    },
                },
            },
        ),
        Tool(
            name="somna_launch_session",
            description=(
                "Launch a display session from the external agent (Resonance). "
                "Writes _agent_launch_display to live_control.json which the control "
                "panel polls and executes. The control panel handles the actual subprocess "
                "spawn. Returns immediately — poll display_active to confirm launch."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session": {
                        "type": "string",
                        "description": "Session folder name (e.g. 'live', 'fold')",
                    }
                },
                "required": ["session"],
            },
        ),
        Tool(
            name="somna_stop_session",
            description=(
                "Stop a running display session from the external agent (Resonance). "
                "Writes _agent_stop_display to live_control.json which the control panel "
                "polls and executes. The control panel handles subprocess termination. "
                "Returns immediately — poll display_active to confirm stop."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="somna_read_live_blocking",
            description=(
                "Block for N seconds, then return the current live state with temporal "
                "metadata. Useful for watching state evolve: 'check every 30 seconds'. "
                "Returns the same data as somna_read_live plus _temporal metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "duration_s": {
                        "type": "number",
                        "description": "Seconds to block before returning state (1-300)",
                        "default": 10,
                    },
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of keys to read. Omit for all.",
                    },
                },
            },
        ),
        Tool(
            name="somna_wait_for",
            description=(
                "Block until a live_control.json key matches the expected value, or "
                "timeout. Polls at 1 Hz. Returns the full state when the condition is "
                "met, or the last-read state on timeout with timed_out=true. "
                "Examples: wait for conductor_phase='MAINTENANCE', wait for "
                "eeg_trance_score >= 0.6 (use operator 'gte')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "live_control.json key to watch",
                    },
                    "value": {
                        "description": "Expected value (string, number, or bool)",
                    },
                    "operator": {
                        "type": "string",
                        "enum": ["eq", "neq", "gte", "lte", "gt", "lt", "contains"],
                        "default": "eq",
                        "description": "Comparison operator. Default 'eq' (equals).",
                    },
                    "timeout_s": {
                        "type": "number",
                        "description": "Max seconds to wait (1-600, default 120)",
                        "default": 120,
                    },
                    "poll_interval_s": {
                        "type": "number",
                        "description": "Seconds between polls (default 1.0)",
                        "default": 1.0,
                    },
                },
                "required": ["key", "value"],
            },
        ),
        Tool(
            name="somna_prompt_user",
            description=(
                "Display a prompt to the user via the control panel and block until "
                "they respond or timeout. Writes agent_message with needs_response=true, "
                "then polls for user_response. The prompt is shown in the console input "
                "dialog and optionally spoken via TTS. Returns the user's response text "
                "or timed_out=true. This is the MCP equivalent of somna_agent's _say() "
                "with needs_response=True — the blocking primitive for interactive sessions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The question or message to display to the user",
                    },
                    "voice_mode": {
                        "type": "string",
                        "enum": ["tts", "subliminal", "both", "silent"],
                        "default": "tts",
                        "description": "How to deliver the prompt. 'tts' speaks it, 'subliminal' flashes it, 'both' does both, 'silent' shows in console only.",
                    },
                    "timeout_s": {
                        "type": "number",
                        "description": "Max seconds to wait for response (5-300, default 60)",
                        "default": 60,
                    },
                    "style": {
                        "type": "object",
                        "description": "Optional style overrides (zoom_speed, intensity, etc.)",
                    },
                },
                "required": ["prompt"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "somna_read_live":
        keys = arguments.get("keys")
        data = _inject_temporal(_read_live(keys))
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_read_conductor":
        live = _read_live()
        data = _inject_temporal(_build_conductor_state(live))
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_read_eeg":
        live = _read_live()
        data = _inject_temporal(_build_eeg_snapshot(live))
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_query_db":
        sql = arguments.get("sql", "")
        data = _db_query(sql)
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_list_sessions":
        data = _inject_temporal({"sessions": _list_sessions()})
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_read_profile":
        data = _inject_temporal(_read_profile())
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_tail_decisions":
        n = arguments.get("n", 10)
        result = _db_query(
            "SELECT * FROM conductor_decisions ORDER BY timestamp DESC LIMIT ?",
            (n,),
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "somna_read_session_yaml":
        text = _read_session_file(arguments["session_name"], "session.yaml")
        return [TextContent(type="text", text=text)]

    if name == "somna_read_affirmations":
        text = _read_session_file(arguments["session_name"], "affirmations.txt")
        return [TextContent(type="text", text=text)]

    # ── Phase 2: Write tools ────────────────────────────────────────────────

    if name == "somna_patch_live":
        patches = arguments.get("patches", {})
        if not isinstance(patches, dict):
            return [
                TextContent(
                    type="text", text=json.dumps({"error": "patches must be a dict"})
                )
            ]
        errors = []
        for k, v in patches.items():
            err = _validate_patch_value(k, v)
            if err:
                errors.append(err)
        if errors:
            return [TextContent(type="text", text=json.dumps({"errors": errors}))]
        result = _patch_live(patches)
        return [
            TextContent(
                type="text", text=json.dumps(_inject_temporal(result), indent=2)
            )
        ]

    if name == "somna_update_profile":
        path = arguments.get("path", "")
        action = arguments.get("action", "")
        value = arguments.get("value")
        if action == "append":
            result = _append_profile(path, value)
        elif action == "set":
            result = _set_profile(path, value)
        else:
            result = {
                "error": f"Action '{action}' not supported. Use 'append' or 'set'."
            }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "somna_append_affirmations":
        session_name = arguments.get("session_name", "")
        lines = arguments.get("lines", [])
        if not isinstance(lines, list):
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": "lines must be a list of strings"}),
                )
            ]
        result = _append_affirmations(session_name, lines)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "somna_write_conductor_hint":
        hints = arguments.get("hints", {})
        if not isinstance(hints, dict):
            return [
                TextContent(
                    type="text", text=json.dumps({"error": "hints must be a dict"})
                )
            ]
        result = _write_conductor_hint(hints)
        return [
            TextContent(
                type="text", text=json.dumps(_inject_temporal(result), indent=2)
            )
        ]

    if name == "somna_write_agent_response":
        response_dict = {k: v for k, v in arguments.items() if v is not None}
        if not response_dict:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": "No response fields provided"}),
                )
            ]
        response_dict["_ts"] = time.time()
        result = _patch_live({"agent_ext_response": response_dict})
        return [
            TextContent(
                type="text", text=json.dumps(_inject_temporal(result), indent=2)
            )
        ]

    if name == "somna_launch_session":
        session = arguments.get("session", "live")
        if not isinstance(session, str) or not session.strip():
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": "session must be a non-empty string"}),
                )
            ]
        result = _patch_live(
            {"_agent_launch_display": {"session": session.strip(), "ts": time.time()}}
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "somna_stop_session":
        result = _patch_live({"_agent_stop_display": True})
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "somna_read_live_blocking":
        duration = min(max(float(arguments.get("duration_s", 10)), 1.0), 300.0)
        keys = arguments.get("keys")
        await asyncio.sleep(duration)
        data = _inject_temporal(_read_live(keys))
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_prompt_user":
        prompt_text = arguments.get("prompt", "").strip()
        if not prompt_text:
            return [
                TextContent(
                    type="text", text=json.dumps({"error": "prompt is required"})
                )
            ]
        voice_mode = arguments.get("voice_mode", "tts")
        timeout_s = min(max(float(arguments.get("timeout_s", 60)), 5.0), 300.0)
        style = arguments.get("style") or {}
        style["needs_response"] = True
        style.setdefault("voice_mode", voice_mode)

        msg_ts = time.time()
        via = ["console"]
        if voice_mode in ("tts", "both"):
            via.append("tts")

        _patch_live(
            {
                "agent_message": {
                    "text": prompt_text,
                    "ts": msg_ts,
                    "needs_response": True,
                    "via": via,
                    "style": style,
                    "timeout_s": timeout_s,
                },
                "user_response": None,
                "response_timestamp": None,
            }
        )

        await asyncio.sleep(0.5)
        deadline = time.time() + timeout_s + 5.0
        while time.time() < deadline:
            live = _read_live()
            resp_ts = live.get("response_timestamp")
            if resp_ts is not None and resp_ts >= msg_ts:
                user_text = live.get("user_response")
                _patch_live({"user_response": None, "response_timestamp": None})
                data = _inject_temporal(live)
                data["_prompt_result"] = {
                    "response": user_text,
                    "timed_out": False,
                }
                return [TextContent(type="text", text=json.dumps(data, indent=2))]
            await asyncio.sleep(0.25)

        _patch_live({"user_response": None, "response_timestamp": None})
        data = _inject_temporal(_read_live())
        data["_prompt_result"] = {
            "response": None,
            "timed_out": True,
        }
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_wait_for":
        key = arguments.get("key", "")
        expected = arguments.get("value")
        op = arguments.get("operator", "eq")
        timeout_s = min(max(float(arguments.get("timeout_s", 120)), 1.0), 600.0)
        poll_s = max(float(arguments.get("poll_interval_s", 1.0)), 0.25)
        deadline = time.time() + timeout_s
        while True:
            live = _read_live()
            actual = live.get(key)
            met = _compare(actual, expected, op)
            if met:
                data = _inject_temporal(live)
                data["_wait_result"] = {
                    "key": key,
                    "expected": expected,
                    "actual": actual,
                    "operator": op,
                    "timed_out": False,
                }
                return [TextContent(type="text", text=json.dumps(data, indent=2))]
            if time.time() >= deadline:
                data = _inject_temporal(live)
                data["_wait_result"] = {
                    "key": key,
                    "expected": expected,
                    "actual": actual,
                    "operator": op,
                    "timed_out": True,
                }
                return [TextContent(type="text", text=json.dumps(data, indent=2))]
            await asyncio.sleep(poll_s)

    return [
        TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))
    ]

    # ── Phase 3: External Agent Channel (TCP :6790 → MCP sampling bridge) ───────


PROMPT_PORT = 6790


class _PromptBridge:
    """Singleton that holds the MCP ServerSession and the TCP server task.

    The TCP listener accepts connections from somna_agent.py. Each prompt
    received over TCP is forwarded to the MCP client via sampling/createMessage.
    The LLM response is sent back over TCP.
    """

    def __init__(self) -> None:
        self._session: Any = None  # mcp.server.session.ServerSession
        self._tcp_server: Optional[asyncio.AbstractServer] = None
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._agent_writer: Optional[asyncio.StreamWriter] = None
        self._connected = False

    def set_session(self, session: Any) -> None:
        self._session = session

    @property
    def session(self) -> Any:
        return self._session

    @property
    def agent_connected(self) -> bool:
        return self._connected and self._agent_writer is not None

    async def start_tcp(self) -> None:
        self._tcp_server = await asyncio.start_server(
            self._handle_agent, "127.0.0.1", PROMPT_PORT
        )
        addr = self._tcp_server.sockets[0].getsockname()
        print(f"[MCP] Prompt bridge listening on {addr[0]}:{addr[1]}")

    async def stop_tcp(self) -> None:
        if self._tcp_server:
            self._tcp_server.close()
            await self._tcp_server.wait_closed()
        self._connected = False

    async def _handle_agent(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single persistent connection from somna_agent.py."""
        self._agent_writer = writer
        self._connected = True
        peer = writer.get_extra_info("peername")
        print(f"[MCP] Agent connected from {peer}")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8").strip())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                msg_type = msg.get("type")
                if msg_type == "prompt":
                    asyncio.create_task(self._forward_prompt(msg))
                elif msg_type == "cancel":
                    tick_id = msg.get("tick_id")
                    if tick_id and tick_id in self._pending:
                        self._pending[tick_id].cancel()
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self._connected = False
            self._agent_writer = None
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            print("[MCP] Agent disconnected")

    async def _forward_prompt(self, msg: dict) -> None:
        """Forward a prompt from the agent to the MCP client via sampling."""
        tick_id = msg.get("tick_id", "")
        system_prompt = msg.get("system_prompt", "")
        user_text = msg.get("prompt", "")
        max_tokens = msg.get("max_tokens", 4096)
        print(
            f"[Bridge] Forwarding prompt tick_id={tick_id[:8]}... len={len(user_text)}"
        )

        if not self._session:
            print("[Bridge] ERROR: no MCP session")
            await self._send_response(
                tick_id,
                {"tick_id": tick_id, "type": "error", "error": "no MCP session"},
            )
            return

        messages = [
            {
                "role": "user",
                "content": {"type": "text", "text": user_text},
            }
        ]

        future: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[tick_id] = future

        try:
            from mcp.types import SamplingMessage

            sampling_messages = [SamplingMessage(**m) for m in messages]
            print(f"[Bridge] Calling create_message()...")
            result = await self._session.create_message(
                messages=sampling_messages,
                max_tokens=max_tokens,
                system_prompt=system_prompt or None,
            )
            print(f"[Bridge] create_message() returned")
            content = result.content
            if hasattr(content, "text"):
                text = content.text
            elif isinstance(content, list) and len(content) > 0:
                text = (
                    content[0].text if hasattr(content[0], "text") else str(content[0])
                )
            else:
                text = str(content)

            response = {
                "tick_id": tick_id,
                "type": "response",
                "text": text,
                "model": getattr(result, "model", ""),
                "stop_reason": getattr(result, "stop_reason", None),
            }
        except asyncio.CancelledError:
            response = {"tick_id": tick_id, "type": "cancelled"}
        except Exception as e:
            print(f"[MCP] Sampling error: {e}")
            response = {"tick_id": tick_id, "type": "error", "error": str(e)}
        finally:
            self._pending.pop(tick_id, None)

        await self._send_response(tick_id, response)

    async def _send_response(self, tick_id: str, response: dict) -> None:
        if self._agent_writer and not self._agent_writer.is_closing():
            try:
                data = json.dumps(response, ensure_ascii=False) + "\n"
                self._agent_writer.write(data.encode("utf-8"))
                await self._agent_writer.drain()
            except (ConnectionResetError, BrokenPipeError):
                pass


bridge = _PromptBridge()


# ── Subclassed Server to capture session + start bridge ──────────────────────

from mcp.server.lowlevel.server import Server as _LowLevelServer
import anyio
from contextlib import AsyncExitStack
import logging

logger = logging.getLogger("somna-mcp")


class SomnaMCPServer(_LowLevelServer):
    """Extends the low-level MCP Server to:
    1. Capture the ServerSession reference for the prompt bridge.
    2. Start the TCP prompt bridge as a background task.
    """

    async def run(
        self,
        read_stream,
        write_stream,
        initialization_options,
        raise_exceptions=False,
        stateless=False,
    ):
        async with AsyncExitStack() as stack:
            lifespan_context = await stack.enter_async_context(self.lifespan(self))
            session = await stack.enter_async_context(
                self._make_session(
                    read_stream, write_stream, initialization_options, stateless
                )
            )
            bridge.set_session(session)

            task_support = (
                self._experimental_handlers.task_support
                if self._experimental_handlers
                else None
            )
            if task_support is not None:
                task_support.configure_session(session)
                await stack.enter_async_context(task_support.run())

            async with anyio.create_task_group() as tg:
                tg.start_soon(bridge.start_tcp)
                async for message in session.incoming_messages:
                    logger.debug("Received message: %s", message)
                    tg.start_soon(
                        self._handle_message,
                        message,
                        session,
                        lifespan_context,
                        raise_exceptions,
                    )
                tg.cancel_scope.cancel()

    @staticmethod
    def _make_session(read_stream, write_stream, init_options, stateless):
        from mcp.server.session import ServerSession

        return ServerSession(
            read_stream, write_stream, init_options, stateless=stateless
        )


# ── Main ─────────────────────────────────────────────────────────────────────


async def main() -> None:
    somna_app = SomnaMCPServer("somna-mcp")
    somna_app.request_handlers = dict(app.request_handlers)
    somna_app.notification_handlers = dict(app.notification_handlers)
    somna_app._tool_cache = dict(app._tool_cache)
    async with stdio_server() as (read_stream, write_stream):
        await somna_app.run(
            read_stream, write_stream, somna_app.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
