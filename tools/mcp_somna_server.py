#!/usr/bin/env python3
"""
Somna MCP Server — Phase 1 (read-only) + Phase 2 (scoped write) + Phase 3 (external agent channel)

Exposes Somna runtime state to LLM clients via the Model Context Protocol.
Run directly: python tools/mcp_somna_server.py
Or via Kilo kilo.json mcp config.

Phase 1: 9 read-only tools.
Phase 2: 4 scoped write tools (key-whitelisted, range-validated, organic safety).
Phase 3: External agent channel — TCP :6790 receives prompts from somna_agent.py,
          forwards them via MCP sampling/createMessage to the connected LLM client,
          returns the response. True push, no polling.
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


def _read_live(keys: list[str] | None = None) -> dict[str, Any]:
    """Read live_control.json with mtime-based cache invalidation."""
    global _lc_mtime, _lc_size, _lc_data
    try:
        st = LIVE_CONTROL_PATH.stat()
        if st.st_mtime != _lc_mtime or st.st_size != _lc_size:
            _lc_data = json.loads(LIVE_CONTROL_PATH.read_text(encoding="utf-8"))
            _lc_mtime = st.st_mtime
            _lc_size = st.st_size
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    if keys:
        return {k: _lc_data.get(k) for k in keys if k in _lc_data}
    return dict(_lc_data)


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

VALID_SPIRAL_STYLES = frozenset(
    {
        "tunnel_dream",
        "galaxy",
        "archimedean",
        "kaleidoscope",
        "interference",
        "vortex",
        "dna",
        "rose",
        "moire",
        "spirograph",
        "fermat",
        "superformula",
        "liminal",
        "nebula",
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
    }
)

VALID_NOISE_COLORS = frozenset(
    {"white", "pink", "brown", "blue", "violet", "grey", "off"}
)
VALID_VEIL_MODES = frozenset(
    {"scroll", "rain", "drift", "converge", "strobe", "tunnel"}
)
VALID_BEAT_TYPES = frozenset({"binaural", "isochronic", "both", "fm"})
VALID_BG_MODES = frozenset({"slideshow", "none"})
VALID_FEEDBACK_MODES = frozenset(
    {
        "alpha_decay",
        "radial_zoom",
        "rotational_smear",
        "directional_blur",
        "reaction_diffusion",
        "kaleidoscopic_fold",
        "none",
    }
)
VALID_BILATERAL_MODES = frozenset({"smooth", "hard"})

ALLOWED_PATCH_KEYS: dict[str, dict[str, Any]] = {
    "beat_frequency": {"type": "float", "min": 0.5, "max": 40.0},
    "carrier_frequency": {"type": "float", "min": 20.0, "max": 500.0},
    "volume": {"type": "float", "min": 0.0, "max": 100.0},
    "veil_opacity": {"type": "float", "min": 0.0, "max": 100.0},
    "spiral_style": {"type": "enum", "values": VALID_SPIRAL_STYLES},
    "spiral_speed_multiplier": {"type": "float", "min": 0.1, "max": 10.0},
    "spiral_chaos": {"type": "float", "min": 0.0, "max": 100.0},
    "spiral_opacity": {"type": "float", "min": 0.0, "max": 100.0},
    "shadow_opacity": {"type": "float", "min": 0.0, "max": 100.0},
    "noise_volume": {"type": "float", "min": 0.0, "max": 100.0},
    "noise_color": {"type": "enum", "values": VALID_NOISE_COLORS},
    "bg_opacity": {"type": "float", "min": 0.0, "max": 100.0},
    "bg_mode": {"type": "enum", "values": VALID_BG_MODES},
    "breath_mod_enabled": {"type": "bool"},
    "breath_rate_bpm": {"type": "float", "min": 4.0, "max": 12.0},
    "breath_depth": {"type": "float", "min": 0.0, "max": 1.0},
    "beat_type": {"type": "enum", "values": VALID_BEAT_TYPES},
    "fm_mod_depth": {"type": "float", "min": 0.5, "max": 30.0},
    "bilateral_panning": {"type": "bool"},
    "bilateral_rate": {"type": "float", "min": 0.1, "max": 20.0},
    "bilateral_mode": {"type": "enum", "values": VALID_BILATERAL_MODES},
    "bilateral_depth": {"type": "float", "min": 0.0, "max": 1.0},
    "entrainment_strength": {"type": "float", "min": 0.0, "max": 0.10},
    "trail_decay": {"type": "float", "min": 0.0, "max": 0.80},
    "feedback_mode": {"type": "enum", "values": VALID_FEEDBACK_MODES},
    "feedback_strength": {"type": "float", "min": 0.0, "max": 1.0},
    "agent_conductor_hints": {"type": "dict"},
    "agent_message": {"type": "dict"},
}

ALLOWED_CONDUCTOR_HINT_KEYS = frozenset(
    {
        "depth_patience",
        "request_fractionation",
        "target_floor_hz",
        "note",
    }
)

ALLOWED_PROFILE_APPEND_PATHS: dict[str, str] = {
    "notes": "list",
    "responsive_themes": "list",
    "effective_moments": "list",
}

ALLOWED_PROFILE_SET_PATHS: dict[str, str] = {
    "preferences.session_interval_target_days": "int",
    "preferences.preferred_time_of_day": "str",
}


def _validate_patch_value(key: str, value: Any) -> Optional[str]:
    """Validate a single patch value against the schema. Returns error or None."""
    spec = ALLOWED_PATCH_KEYS.get(key)
    if spec is None:
        return f"Key '{key}' is not in the allowed whitelist."
    vtype = spec["type"]
    if vtype == "float":
        if not isinstance(value, (int, float)):
            return f"Key '{key}' expects a number, got {type(value).__name__}."
        if "min" in spec and value < spec["min"]:
            return f"Key '{key}' value {value} below minimum {spec['min']}."
        if "max" in spec and value > spec["max"]:
            return f"Key '{key}' value {value} above maximum {spec['max']}."
    elif vtype == "bool":
        if not isinstance(value, bool):
            return f"Key '{key}' expects a boolean, got {type(value).__name__}."
    elif vtype == "enum":
        if value not in spec["values"]:
            return f"Key '{key}' value '{value}' not in allowed set: {sorted(spec['values'])}."
    elif vtype == "dict":
        if not isinstance(value, dict):
            return f"Key '{key}' expects a dict, got {type(value).__name__}."
    return None


def _write_live_direct(updates: dict[str, Any]) -> dict[str, Any]:
    """Reload-first merge write to live_control.json. Fallback when StateServer unavailable."""
    try:
        data = json.loads(LIVE_CONTROL_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    for k, v in updates.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    tmp = LIVE_CONTROL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LIVE_CONTROL_PATH)
    global _lc_data, _lc_mtime, _lc_size
    _lc_data = data
    st = LIVE_CONTROL_PATH.stat()
    _lc_mtime = st.st_mtime
    _lc_size = st.st_size
    return {"written": list(updates.keys())}


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
    if path not in ALLOWED_PROFILE_APPEND_PATHS:
        return {"error": f"Path '{path}' is not an appendable profile field."}
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
    if path not in ALLOWED_PROFILE_SET_PATHS:
        return {"error": f"Path '{path}' is not a settable profile field."}
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
            description="Write agent_conductor_hints to live_control.json (depth_patience, request_fractionation, target_floor_hz, note).",
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
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "somna_read_live":
        keys = arguments.get("keys")
        data = _read_live(keys)
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_read_conductor":
        live = _read_live()
        data = _build_conductor_state(live)
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_read_eeg":
        live = _read_live()
        data = _build_eeg_snapshot(live)
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_query_db":
        sql = arguments.get("sql", "")
        data = _db_query(sql)
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_list_sessions":
        data = {"sessions": _list_sessions()}
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    if name == "somna_read_profile":
        data = _read_profile()
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
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

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
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

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

        if not self._session:
            await self._send_response(tick_id, {"error": "no MCP session"})
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
            result = await self._session.create_message(
                messages=sampling_messages,
                max_tokens=max_tokens,
                system_prompt=system_prompt or None,
            )
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
