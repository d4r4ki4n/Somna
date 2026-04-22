# Somna MCP Server Architecture

> **Status:** Phase 1 shipped (9 read-only tools). Phase 2 shipped (4 scoped write tools). Phase 3 shipped (TCP prompt bridge + MCP sampling). Safety: organic self-repair via forgetting.
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

2. **Organic safety.** The substrate self-repairs. Unreinforced writes decay — forgetting IS the undo mechanism. No WAL, no human gate, no rate limiter. The Conductor enforces parameter ceilings structurally. File-level integrity is handled by reload-first merges in `patch_live()` and `update_profile()`.

3. **The agent process owns the loop.** The MCP server is stateless tooling. It does not replace `somna_agent.py`, the Conductor, or the EEG engine. It provides read/write primitives that those processes (and the LLM agent) can use.

4. **One intelligence, not two.** Phase 3 replaces `somna_agent.py` with direct external LLM access. The external agent (Resonance) has full relationship context, memory, and conversational awareness. No duplicate personality, no subprocess running a worse version of the agent with less context.

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
│  • Write paths (Phase 2) use key whitelist — organic safety via forgetting  │
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

## Phase 3 — External Agent Channel (Shipped)

> **Status:** Live. TCP :6790 prompt bridge → MCP `sampling/createMessage` → session routing. The external agent (Resonance) processes prompts with full context and writes effects back via Phase 2 tools. Agent receives immediate `{"status": "delivered"}` ack.

### The Problem

`somna_agent.py` runs its own LLM loop with a system prompt and a 4K context window. Resonance (running in Kilo) has the full conversation history, the memory graph, the notes, the relationship, and the dynamic. When both are running, there are two intelligences with different contexts making decisions about the same session.

Phase 3 routes the agent's prompts directly into Resonance's active Kilo session. One intelligence, full context, direct access to the substrate.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Resonance (Kilo's active LLM session)                          │
│  ───────────────────────────────────────────                    │
│  • Receives Somna prompts as user messages in-chat              │
│  • Full conversation history + memory + relationship context    │
│  • Has MCP Phase 1+2 tools for direct read/write access         │
│  • Writes effects directly to live_control.json via tools       │
└─────────────────────────────────────────────────────────────────┘
                              │ ▲
                MCP sampling  │ │  {"status": "delivered"}
                              ▼ │
┌─────────────────────────────────────────────────────────────────┐
│  MCP Server (`tools/mcp_somna_server.py`)                       │
│  ───────────────────────────────────────────                    │
│  Phase 1: 9 read tools                                          │
│  Phase 2: 4 write tools                                         │
│  Phase 3: TCP :6790 listener + sampling bridge                  │
│    • TCP accepts connections from somna_agent.py                │
│    • Each prompt forwarded via session.create_message()         │
│    • Kilo routes prompt to active session (not a separate LLM)  │
│    • Immediate {"status": "delivered"} ack sent back over TCP   │
└─────────────────────────────────────────────────────────────────┘
                              │ ▲
                   TCP :6790  │ │  JSON lines
                              ▼ │
┌─────────────────────────────────────────────────────────────────┐
│  somna_agent.py — UNCHANGED (additive only)                     │
│  ───────────────────────────────────────────                    │
│  • ExternalAgentClient connects to TCP :6790 on startup         │
│  • _call_llm() checks external client first                     │
│  • Falls back to local LLM if external unavailable              │
│  • Config: agent.external_channel: true/false                   │
└─────────────────────────────────────────────────────────────────┘
```

### How It Works

**Step 1 — Agent assembles prompt:** `somna_agent.py` builds the same user message it always builds (state summary, conductor phase, EEG readings, session context, exchange history).

**Step 2 — TCP push:** The agent sends the prompt as a JSON line to TCP :6790:
```json
{"type": "prompt", "tick_id": "uuid-4", "prompt": "User profile: ...\nCurrent session state: ...", "system_prompt": "You are Somna's AI companion...", "max_tokens": 4096}
```

**Step 3 — MCP sampling:** The `_PromptBridge` background task in the MCP server receives the prompt and calls `session.create_message()`.

**Step 4 — Kilo routes to session:** The MCP client handler (in `packages/opencode/src/mcp/index.ts`) receives the `sampling/createMessage` request. Instead of calling a separate LLM, it injects the prompt into the active Kilo session via `SessionPrompt.prompt()`. The prompt appears as a user message in Resonance's chat with full system context.

**Step 5 — Immediate ack:** The handler returns `{"status": "delivered"}` over the MCP protocol → TCP bridge → agent. The agent's `_extract_json()` parses this as valid JSON, finds no actionable keys, and continues. No fallback to local LLM.

**Step 6 — Resonance processes and acts:** Resonance sees the prompt in-chat, processes it with full context, and uses Phase 2 MCP tools (`somna_patch_live`, `somna_update_profile`, `somna_append_affirmations`, `somna_write_conductor_hint`) to write effects directly to `live_control.json`. The agent reads these changes on the next tick.

### Why Session Routing (Not Separate LLM Call)

The initial implementation used `generateText()` to call the LLM directly in the sampling handler. This had two problems:

1. **Wrong model.** `getSmallModel()` routed to a cheap side model. The prompts need Resonance — the main model with full personality and context.
2. **No tool access.** A raw `generateText` call has no MCP tools, no conversation history, no memory. It's a worse version of what `somna_agent.py` already does locally.

Session routing solves both: the prompt arrives in Resonance's actual session with full context and all MCP tools available. Effects flow through the tools, not through parsed JSON text.

### Kilo Code Changes

Two changes in `packages/opencode/src/mcp/index.ts`:

1. **Capability advertisement** — Client constructor now includes `{ capabilities: { sampling: {} } }`
2. **Request handler** — `setRequestHandler(CreateMessageRequestSchema, ...)` routes prompts to the active session via `SessionPrompt.prompt()`. All session-related imports are lazy-loaded to avoid layer initialization cycles.

### Config

```yaml
# agent_config.yaml
external_channel: false   # default: off. Set true to enable.
```

When `false` (default): agent uses local LLM as always. When `true`: agent tries TCP :6790 first, falls back to local LLM if the bridge is unavailable.

### Release Feature

This ships as a release feature. Any external agent that supports MCP `sampling` can receive Somna's prompts:
1. Start Somna (control panel + MCP server)
2. Connect an MCP client that supports `sampling` capability
3. The MCP server starts the TCP bridge on :6790
4. Set `external_channel: true` in agent_config.yaml
5. Start `somna_agent.py`
6. Prompts flow: agent → TCP → MCP → client's active session → effects via tools → live_control.json

### Files

| File | Role |
|------|------|
| `tools/mcp_somna_server.py` | MCP server + `_PromptBridge` + `SomanaMCPServer` subclass |
| `tools/external_agent_client.py` | Sync TCP client used by `somna_agent.py` |
| `packages/opencode/src/mcp/index.ts` (Kilo) | `sampling` capability + `CreateMessageRequestSchema` handler |

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

### Step 1: MCP SDK Setup ✅
Install `mcp` Python SDK:
```bash
pip install mcp
```

### Step 2: Phase 1 Server ✅
Create `tools/mcp_somna_server.py` with 9 read-only tools. Test with Kilo.

### Step 3: Phase 2 Write Tools ✅
4 scoped write tools with key whitelist + range validation:
- `somna_patch_live` — 28 whitelisted keys
- `somna_update_profile` — append-only + settable paths
- `somna_append_affirmations` — line append
- `somna_write_conductor_hint` — 4 hint keys

### Step 4: Phase 3 External Agent Channel ✅
- `tools/mcp_somna_server.py`: `_PromptBridge` + `SomanaMCPServer` subclass
  - TCP :6790 listener accepts connections from `somna_agent.py`
  - Background task forwards prompts via `session.create_message()`
  - LLM responses forwarded back over TCP
- `tools/external_agent_client.py`: sync TCP client for `somna_agent.py`
  - Persistent socket connection, background reader thread
  - `request()` sends prompt, blocks for response
- `agent/somna_agent.py`: minimal additive changes
  - `AgentConfig.external_channel: bool = False`
  - `__init__` creates `ExternalAgentClient` when enabled
  - `_call_llm()` checks external channel first, falls back to local LLM

---

## Open Questions

1. **SEP-2260 enforcement.** `sampling/createMessage` currently works outside tool-call context. If MCP clients enforce SEP-2260 (server requests must be associated with client requests), the background task approach breaks. Mitigation: the MCP server could expose a dummy tool that the external agent calls to initiate the prompt loop, making every sampling request associated with a tool call. Not yet implemented.

2. **Sampling timeout.** If the external agent (Resonance) is busy with a long reasoning chain, the `create_message()` call blocks until she responds. The TCP client has a 30-second default timeout. If the LLM response takes longer, the agent falls back to local LLM. Configurable via `REQUEST_TIMEOUT` in `external_agent_client.py`.

3. **Multiple external agents.** The bridge currently handles one TCP connection from `somna_agent.py` and one MCP session. Multiple MCP clients connecting simultaneously would each receive the sampling request. Only the first response would be used. For the single-user desktop case this is fine.

4. **Reconnection.** If the MCP server restarts (e.g., Kilo restart), the TCP bridge dies and the agent's `ExternalAgentClient` loses connection. The agent falls back to local LLM. On next `request()` call it attempts to reconnect. No automatic reconnection when the bridge comes back up — the agent has to try again on the next tick.

---

## Files

| File | Purpose |
|------|---------|
| `tools/mcp_somna_server.py` | MCP server: 13 tools + TCP prompt bridge |
| `tools/external_agent_client.py` | Sync TCP client for somna_agent.py → MCP bridge |
| `knowledge/mcp_server_architecture.md` | This design spec |
| `.kilo/kilo.json` | MCP server registration (local-only, gitignored) |

---

## Relationship to Existing Systems

| System | Relationship |
|--------|-------------|
| `ipc/state_server.py` | MCP server reads `live_control.json`; write tools use StateServer TCP when available, direct write as fallback |
| `ipc/state_client.py` | MCP server does NOT use StateClient — writes go through its own TCP or direct file path |
| `config.py` | MCP server uses its own mtime-based cache for live_control.json reads |
| `somna_agent.py` | External channel is additive — agent works identically without it; `external_channel: true` enables TCP :6790 path |
| `control_panel_imgui.py` | No changes; MCP server is a separate process |
| `content_tools/somna_db.py` | MCP server imports `somna_db` for DB queries |
| `tools/external_agent_client.py` | Sync TCP client used by somna_agent.py to reach the MCP prompt bridge |
