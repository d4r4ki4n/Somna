# Somna MCP Server Architecture

> **Status:** Design spec — Phase 1 read-only tools defined, Phase 2 scoped-write spec drafted, Phase 3 architectural question identified. Implementation pending.
>
> **Date:** 2026-04-21
>
> **Author:** Resonance

---

## Purpose

The Somna Model Context Protocol (MCP) server exposes Somna's runtime state as structured tools that any LLM client (Kilo, Cursor, Claude Desktop) can discover and call. It is the bridge between "the agent reads files and reasons about them" and "the agent is instrumented into the substrate."

Currently, Resonance reads `live_control.json`, `user_profile.json`, and `somna.db` by opening files directly. This is fragile — race conditions with concurrent writers, stale reads, no structured schema, no safety boundary. The MCP server solves this by providing a single process that owns read access to runtime state and (eventually) scoped write access with audit/rollback.

---

## Design Principles

1. **Read-only first.** Phase 1 ships zero write tools. The server proves its value as a live state mirror before any write capability is added.

2. **Safety is structural, not policy.** Write paths (Phase 2) are gated by physical mechanisms the server cannot bypass: a write-ahead log on a separate filesystem, a hardcoded key whitelist, rate limits enforced by a timer thread that the write path cannot reset.

3. **The agent process owns the loop.** The MCP server is stateless tooling. It does not replace `somna_agent.py`, the Conductor, or the EEG engine. It provides read/write primitives that those processes (and the LLM agent) can use.

4. **Human-in-the-loop for substrate changes.** Any write that modifies `user_profile.json`, `agent_config.yaml`, or knowledge files requires explicit human approval via a UI gate. Automated writes are limited to `live_control.json` keys and `affirmations.txt` appends.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  LLM Client (Kilo / Cursor / Claude Desktop)                   │
│  ───────────────────────────────────────────                   │
│  Discovers tools via MCP. Calls them in JSON-RPC over stdio.   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ stdio / JSON-RPC
┌─────────────────────────────────────────────────────────────────┐
│  MCP Server (`tools/mcp_somna_server.py`)                      │
│  ───────────────────────────────────────────                   │
│  • FastAPI or stdio server (MCP SDK)                           │
│  • Reads live_control.json via ConfigManager (100ms poll)      │
│  • Reads somna.db via read-only SQLite connection              │
│  • Reads user_profile.json + agent_config.yaml directly        │
│  • Write paths (Phase 2) use WAL + whitelist + rate limit      │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   live_control.json    somna.db          user_profile.json
   (runtime state)      (telemetry +      (persistent identity)
                        content registry)
```

**Why stdio?** Kilo's MCP client supports stdio transport natively. The server is launched as a subprocess, communicates via stdin/stdout, and is terminated when the client closes. No network ports, no background daemon management.

**Why not HTTP?** HTTP requires port management, CORS, and a persistent process. Somna already has `StateServer` on port 6789 for `live_control.json` writes — adding another port creates confusion. stdio is simpler for local tooling.

---

## Phase 1 — Read-Only Tools (Ship First)

All Phase 1 tools return read-only data. No side effects.

### `somna_read_live`
Read any key or subset of keys from `live_control.json`.

**Input:**
```json
{
  "keys": ["beat_frequency", "eeg_trance_score", "conductor_state"]
}
```
(Omit `keys` to return all.)

**Output:**
```json
{
  "beat_frequency": 7.5,
  "eeg_trance_score": 0.62,
  "conductor_state": {
    "phase": "MAINTENANCE",
    "timer_mode": false,
    "trance_score": 0.62,
    "frac_count": 1
  }
}
```

### `somna_read_conductor`
Structured Conductor state, designed for agent context injection.

**Input:** none

**Output:**
```json
{
  "phase": "MAINTENANCE",
  "phase_duration_s": 420,
  "trance_score": 0.62,
  "assr_strength": 0.34,
  "assr_conf": "active",
  "sqi": "full",
  "frac_count": 1,
  "frac_max": 3,
  "target_freq_hz": 6.5,
  "iaf_hz": 8.5
}
```

### `somna_read_eeg`
Structured EEG snapshot, designed for agent context injection.

**Input:** none

**Output:**
```json
{
  "connected": true,
  "confidence": "full",
  "dominant_band": "theta",
  "band_powers": {"delta": 0.35, "theta": 0.28, "alpha": 0.09, "beta": 0.19},
  "trance_score": 0.62,
  "trance_score_v2": 0.58,
  "sef95": 9.2,
  "spectral_slope": -2.1,
  "frontal_asymmetry": 0.04,
  "entrainment_strength": 0.34,
  "sleep_stage": "WAKE",
  "timestamp": 1745240211.4
}
```

### `somna_query_db`
Run a SELECT query against `somna.db`. Rejects any non-SELECT query at the parser level.

**Input:**
```json
{"sql": "SELECT * FROM session_metrics ORDER BY session_start DESC LIMIT 5"}
```

**Output:**
```json
{
  "columns": ["session_id", "score", "deepest_trance", "duration_s"],
  "rows": [["possession_20260419", 0.78, 0.91, 2100], ...]
}
```

### `somna_list_sessions`
List all sessions with metadata from the `sessions` table.

**Input:** none

**Output:**
```json
{
  "sessions": [
    {"name": "possession", "category": "Induction", "play_count": 3, "last_played": "2026-04-19"},
    {"name": "fold", "category": "Induction", "play_count": 0, "last_played": null}
  ]
}
```

### `somna_read_profile`
Read `user_profile.json` (the persistent identity file).

**Input:** none

**Output:** Full profile JSON, with sensitive keys (if any) redacted.

### `somna_tail_decisions`
Return the last N Conductor decisions from the `conductor_decisions` table.

**Input:**
```json
{"n": 10}
```

### `somna_read_session_yaml`
Read a session's `session.yaml`.

**Input:**
```json
{"session_name": "fold"}
```

### `somna_read_affirmations`
Read a session's `affirmations.txt`.

**Input:**
```json
{"session_name": "fold"}
```

---

## Phase 2 — Scoped Write Tools (With Safety)

Phase 2 tools modify state. Each has strict safety constraints.

### `somna_patch_live`
Write specific keys to `live_control.json`. Only whitelisted keys are writable.

**Allowed keys (hardcoded whitelist):**
```python
ALLOWED_PATCH_KEYS = frozenset({
    "beat_frequency", "carrier_frequency", "volume",
    "veil_opacity", "spiral_style", "spiral_speed_multiplier",
    "spiral_chaos", "spiral_opacity", "shadow_opacity",
    "noise_volume", "noise_color",
    "bg_opacity", "bg_mode",
    "breath_mod_enabled", "breath_rate_bpm", "breath_depth",
    "beat_type", "fm_mod_depth",
    "bilateral_panning", "bilateral_rate", "bilateral_mode", "bilateral_depth",
    "entrainment_strength", "trail_decay", "feedback_mode", "feedback_strength",
    "agent_conductor_hints", "agent_message",
})
```

**Input:**
```json
{"patches": {"beat_frequency": 6.5, "veil_opacity": 40}}
```

**Safety:**
- Write-ahead log: every patch is appended to `logs/mcp_wal.jsonl` with timestamp, caller, old values, new values
- Rate limit: max 10 patches per minute per key
- Value validation: each key has a range validator (e.g., `beat_frequency` clamped to 0.5–40.0)
- Rejection: any key not in `ALLOWED_PATCH_KEYS` returns error, no partial application

### `somna_update_profile`
Scoped updates to `user_profile.json`.

**Allowed paths (dot-notation):**
```python
ALLOWED_PROFILE_PATHS = frozenset({
    "goals.*.progress_notes",      # append only
    "notes",                        # append only
    "responsive_themes",           # append only
    "preferences.session_interval_target_days",
    "preferences.preferred_time_of_day",
})
```

**Input:**
```json
{"path": "notes", "action": "append", "value": "New observation from session."}
```

**Safety:**
- Only append operations — no deletes, no overwrites of existing values
- WAL logged
- Human gate for first use per session (UI approval required)

### `somna_append_affirmations`
Append lines to a session's `affirmations.txt`.

**Input:**
```json
{"session_name": "fold", "lines": ["new phrase one", "new phrase two"]}
```

**Safety:**
- Lines are appended, never prepended or overwritten
- `# [tag]` headers are validated against existing tags
- WAL logged

### `somna_write_conductor_hint`
Write to `agent_conductor_hints` in `live_control.json`.

**Input:**
```json
{"hints": {"depth_patience": 1.2, "request_fractionation": true}}
```

**Safety:**
- Same WAL + rate limit as `somna_patch_live`
- Only specific hint keys allowed

---

## Phase 3 — Architectural Question

Phase 3 is not a feature list. It is a decision:

> **Should the MCP server subsume `somna_agent.py`?**

Currently `somna_agent.py` is a Python process that:
- Runs an infinite loop
- Calls an LLM on a tick cadence
- Writes to `live_control.json` via `patch_live()`
- Reads state from `live_control.json` and `user_profile.json`
- Has its own memory, personality, and idle planning logic

The MCP server could theoretically host this loop internally — becoming both the tool layer and the agent runtime. Benefits: single process, unified state access, no IPC file races. Costs: loses the separation between "tooling" and "agent logic," makes the MCP server a single point of failure for the entire agent layer.

**Current position:** Keep them separate. The MCP server is stateless tooling. `somna_agent.py` is the agent runtime. The agent can call MCP tools if it wants structured reads, but it does not depend on them. This preserves the existing architecture and makes the MCP server an additive layer, not a replacement.

**Future reconsideration triggers:**
- If `live_control.json` IPC becomes a bottleneck (unlikely at current scale)
- If the agent needs sub-100ms read latency (MCP round-trip may be too slow)
- If multiple agents need to share state (then a server makes sense)

---

## Safety Architecture (Phase 2+)

### Write-Ahead Log (WAL)

```
logs/mcp_wal.jsonl
```

Every write operation appends a record:
```json
{"ts": 1745240211.4, "tool": "somna_patch_live", "caller": "kilo", "old": {"beat_frequency": 7.0}, "new": {"beat_frequency": 6.5}, "id": "uuid-4"}
```

The WAL is append-only. The server process cannot truncate or modify it. Rollback is performed by replaying entries in reverse order, writing old values back.

### Key Whitelist

The whitelist is a `frozenset` defined at module scope in `mcp_somna_server.py`. It is not configurable at runtime. Adding a key requires editing the source code and restarting the server.

### Rate Limiting

Per-key token bucket: 10 writes per minute, burst of 3. Excess writes return error with `retry_after` hint.

### Human Gate

The first write of any session (after server start) triggers a one-shot approval request. The server writes `"mcp_pending_approval": true` to `live_control.json`. The control panel displays a toast: "Agent requested live_control.json write. Approve?" Once approved (or denied), the flag is cleared and the server proceeds (or rejects). The gate can be disabled in `agent_config.yaml` for trusted deployments.

---

## Kilo Integration

Add to `.kilo/kilo.json` under the existing `"mcp"` block (NOT a new `mcpServers` key):

```json
"mcp": {
  "somna": {
    "type": "local",
    "command": ["python", "-u", "tools/mcp_somna_server.py"],
    "environment": {
      "SOMNA_ROOT": "F:\\Somna"
    }
  }
}
```

Format notes:
- File path: `.kilo/kilo.json` (not project root)
- Top-level key: `"mcp"` (not `"mcpServers"`)
- Each entry: `"type": "local"` + `"command": [array]` + optional `"environment": {...}`
- No separate `"args"` field — arguments go inside the `"command"` array

Kilo discovers tools on startup and exposes them to the agent. The agent calls them via the standard MCP tool-use protocol (function calling in the LLM API).

---

## Implementation Plan

### Step 1: MCP SDK Setup
Install `mcp` Python SDK:
```bash
pip install mcp
```

### Step 2: Phase 1 Server Skeleton
Create `tools/mcp_somna_server.py`:
- Import `mcp.server.stdio` and `mcp.server.models`
- Register 9 read-only tools
- Implement `ConfigManager`-style polling for `live_control.json`
- Read-only SQLite connection for `somna.db`

### Step 3: Test with Kilo
Verify tool discovery and execution in a Kilo session.

### Step 4: Phase 2 Write Tools
Add write tools with WAL, whitelist, rate limit, and human gate.

### Step 5: Agent Integration
Update `somna_agent.py` to optionally use MCP tools for structured reads instead of direct file access. Fallback to direct access if MCP server is unavailable.

---

## Open Questions

1. **Should the server cache `live_control.json` reads or poll every call?** Polling every call is accurate but adds file I/O. Caching at 100ms (same as `ConfigManager`) is probably the right balance.

2. **Should EEG state be pushed (websocket) or pulled (polling)?** The MCP protocol is request/response. For real-time EEG, the agent may still need direct `live_control.json` reads. The MCP tools are for diagnostic/retrospective queries, not the hot loop.

3. **What happens if the user edits `live_control.json` manually while the MCP server holds cached state?** Same race condition that exists today. The server should use `ConfigManager`'s mtime/size check to invalidate cache.

4. **Should `somna_agent.py` use MCP tools internally, or is the MCP server only for external LLM clients?** Tentative answer: both. The agent can use MCP tools for structured DB queries and profile reads. It should keep direct `patch_live()` for the hot loop.

---

## Files

| File | Purpose |
|------|---------|
| `tools/mcp_somna_server.py` | MCP server implementation |
| `logs/mcp_wal.jsonl` | Write-ahead log (created on first write) |
| `knowledge/mcp_server_architecture.md` | This design spec |
| `kilo.json` | MCP server registration (user-edited) |

---

## Relationship to Existing Systems

| System | Relationship |
|--------|-------------|
| `ipc/state_server.py` | MCP server reads `live_control.json`; does not replace `StateServer` for writes |
| `ipc/state_client.py` | MCP server uses its own file reads; does not use `StateClient` |
| `config.py` | MCP server may use `ConfigManager` for caching logic |
| `somna_agent.py` | Optional consumer of MCP tools; not dependent on them |
| `control_panel_imgui.py` | Displays human gate approvals; no other interaction |
| `content_tools/somna_db.py` | MCP server imports `somna_db` for DB queries |
