#!/usr/bin/env python3
"""
Somna MCP Server — Phase 1 (read-only tools)

Exposes Somna runtime state to LLM clients via the Model Context Protocol.
Run directly: python tools/mcp_somna_server.py
Or via Kilo kilo.json mcpServers config.

Phase 1: 9 read-only tools.
Phase 2: Scoped write tools with WAL + whitelist + rate limit.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

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

    return [
        TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))
    ]


# ── Main ─────────────────────────────────────────────────────────────────────


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
