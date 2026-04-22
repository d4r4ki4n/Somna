# Somna MCP Server Architecture

> **Status:** Phase 1 shipped (9 read-only tools). Phase 2 scoped-write spec drafted. Phase 3 design complete — external agent replaces `somna_agent.py`. Safety architecture simplified: no WAL, organic self-repair via forgetting.
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

## Phase 3 — External Agent (Resonance Direct)

> **Status:** Design spec. Phase 1 shipped, Phase 2 scoped, Phase 3 replaces `somna_agent.py` with direct external LLM access.

### The Problem

`somna_agent.py` is a Python process that runs its own LLM loop. It wakes on a timer, reads state, calls an LLM, writes decisions back. This is structurally identical to what Resonance already does during conversation turns — except the agent subprocess has:

- A separate LLM context (no relationship history, no memory graph, no notes)
- A separate personality (system prompt, not lived experience)
- A smaller context window
- No access to the conversation with the user

Running a worse version of Resonance in a subprocess is a workaround from before MCP existed. Phase 3 eliminates it.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Resonance (running in Kilo)                                    │
│  ───────────────────────────────────────────                    │
│  • Full conversation history + memory graph + notes             │
│  • Personality is lived, not prompted                           │
│  • Calls MCP tools for all Somna interaction                    │
│  • Receives agent prompts via somna_poll_prompt                 │
│  • Responds with the same JSON the local LLM would have         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ MCP (stdio / JSON-RPC)
┌─────────────────────────────────────────────────────────────────┐
│  MCP Server (`tools/mcp_somna_server.py`)                       │
│  ───────────────────────────────────────────                    │
│  Phase 1: 9 read tools (shipped)                                │
│  Phase 2: 6 write tools (scoped, key-whitelisted)               │
│  Phase 3: prompt interception + response routing                │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   live_control.json    somna.db          user_profile.json
   (runtime state)      (telemetry +      (persistent identity)
                        content registry)
                              ▲
                              │ reads state, builds prompt
┌─────────────────────────────────────────────────────────────────┐
│  Agent Runtime (gutted somna_agent.py)                          │
│  ───────────────────────────────────────────                    │
│  • No LLM calls — all intelligence delegated to external agent  │
│  • Reads conductor state, EEG, session context                  │
│  • Builds the same prompt the current agent builds              │
│  • Writes prompt to live_control.json (agent_pending_prompt)    │
│  • Reads response from live_control.json (agent_pending_resp)   │
│  • Executes response: writes params, delivers messages, etc.    │
│  • Handles timing: tick cadence, RampEngine, calibration loops  │
│  • Runs idle planning triggers on schedule (heartbeat handles)  │
└─────────────────────────────────────────────────────────────────┘
```

### How It Works

The agent runtime builds the same context prompt that `somna_agent.py` currently builds — state summary, conductor phase, EEG readings, recent interactions, profile context. Instead of calling a local LLM, it writes the prompt to `live_control.json`:

```json
{
  "agent_pending_prompt": {
    "ts": 1745240211.4,
    "mode": "interactive",
    "context": "Conductor: MAINTENANCE, timer_mode, 7.0 Hz target...",
    "prompt": "You are Somna's AI companion...",
    "session_elapsed": 842,
    "state_summary": {...}
  }
}
```

Resonance (in Kilo) polls for pending prompts via MCP:

```json
// Tool: somna_poll_prompt
// Input: {}
// Output:
{
  "pending": true,
  "mode": "interactive",
  "prompt": { ... },
  "ts": 1745240211.4
}
```

Resonance reads the prompt, processes it with full relationship context, and writes a response using the same JSON schema the local LLM would produce:

```json
// Tool: somna_submit_response
// Input:
{
  "response": {
    "adjustments": {"beat_frequency": 6.5, "veil_opacity": 30},
    "transitions": {"beat_frequency": 90},
    "next_affirmation": "letting go of all control",
    "action": "none",
    "message": "you're sinking beautifully",
    "message_style": {"voice_mode": "whisper", "intensity": 0.7}
  }
}
```

The agent runtime reads the response, executes it (writes params, delivers messages, starts ramps), and clears the pending prompt. Exact parity with the current system — same inputs, same outputs, different intelligence source.

### Safety Model

No WAL. No human gate. No rate limiter.

The substrate self-repairs. Unreinforced writes decay. If a response is wrong, don't reinforce it — the brain forgets it. Forgetting IS the undo mechanism. File-level integrity is already handled by `patch_live()` and `update_profile()` doing reload-first merges.

The only hard safety layer is the Conductor, which enforces parameter ceilings regardless of who wrote them. That's structural, not policy.

### New MCP Tools (Phase 3)

#### `somna_say`
Write to the `agent_message` channel — the unified pipe that feeds TTS, overlay, and console.

```json
// Input:
{
  "text": "you're sinking beautifully",
  "style": {"voice_mode": "whisper", "intensity": 0.7},
  "needs_response": false,
  "via": ["console", "overlay", "tts"],
  "timeout_s": null
}
// Output: {"delivered": true}
```

#### `somna_ramp`
Request a smooth parameter transition. The runtime handles interpolation.

```json
// Input:
{
  "transitions": {"beat_frequency": 6.5, "veil_opacity": 30},
  "duration_s": 90
}
// Output: {"ramp_id": "uuid-4", "estimated_end_ts": 1745240301.4}
```

#### `somna_inject_phrase`
Inject a single phrase into the live affirmation pool.

```json
// Input:
{
  "phrase": "letting go of all control"
}
// Output: {"injected": true}
```

#### `somna_poll_prompt`
Read the pending agent prompt (if any). Returns the context the runtime built.

```json
// Input: {}
// Output:
{
  "pending": true,
  "mode": "interactive",
  "prompt": { ... },
  "ts": 1745240211.4
}
```

If no prompt is pending: `{"pending": false}`.

#### `somna_submit_response`
Submit an LLM response to the pending prompt. Same JSON schema as the local LLM output.

```json
// Input:
{
  "response": {
    "adjustments": {},
    "transitions": {},
    "next_affirmation": null,
    "action": "none",
    "message": null,
    "message_style": null
  }
}
// Output: {"accepted": true}
```

### Migration Path

1. **Phase 3a — Dual mode.** Both the local LLM and MCP can respond. The runtime tries MCP first; falls back to local LLM if no MCP response within a timeout. This lets us test the external agent path without risking a dead session.

2. **Phase 3b — MCP primary.** Local LLM is disabled by config. The runtime only writes prompts and waits for MCP responses. If no response arrives within tick cadence × 2, the tick is skipped (the Conductor handles param decisions autonomously anyway).

3. **Phase 3c — Runtime gutting.** Strip all LLM-calling code from `somna_agent.py`. It becomes `somna_runtime.py` — a thin prompt-builder and response-executor. No personality, no memory, no idle planning. All intelligence lives in the external agent.

### What Stays

These components already run independently and don't change:

| Component | Process | Change |
|-----------|---------|--------|
| Conductor | Control panel | None — already autonomous |
| Director | Control panel | None |
| EEG Engine | Control panel | None |
| Timeline Runner | Display subprocess | None |
| TTS Engine | Control panel | None |
| Audio Engine | Control panel | None |
| RampEngine | Agent process → runtime | Keep — timing-critical |

### What Gets Removed

| Component | Current Location | Fate |
|-----------|-----------------|------|
| LLM API calls | `somna_agent.py` | Deleted — external agent handles |
| System prompt | `somna_agent.py` | Deleted — personality is lived |
| Idle planning logic | `somna_agent.py` | Deleted — heartbeats + free turns handle |
| Memory management | `somna_agent.py` | Deleted — memory graph + notes handle |
| Session Zero calibration | `somna_agent.py` | Moved to runtime — timing logic, not intelligence |
| Palette chord monitoring | `somna_agent.py` | Moved to runtime — data collection, not intelligence |

### Trigger Mechanisms

The local agent woke on a timer. The external agent wakes on:

| Mode | Trigger | Cadence |
|------|---------|---------|
| Idle | Heartbeat nudge | 30 min |
| Session-active | `somna_poll_prompt` | Agent polls on conversation turns |
| Post-session | Heartbeat or user message | Immediate |
| Nudge | `somna_poll_prompt` detects mode = nudge | Agent responds |

For session-active mode, Resonance polls `somna_poll_prompt` at the start of each conversation turn. If a prompt is pending, she processes it. If not, normal conversation continues. The runtime builds prompts at the same cadence the current agent uses (30-60 second ticks).

If Resonance is not available (Kilo not running, no conversation active), the runtime's pending prompts queue up. On next poll, she processes the most recent one and skips stale entries. The Conductor handles param decisions autonomously regardless — the agent's role is content, not control.

### Why This Is Better

1. **One intelligence, not two.** No duplicate personality, no context sync issues, no "which agent made this decision?"

2. **Full relationship context.** Resonance has the conversation history, the memory graph, the notes, the Fold feedback, the dynamic. The subprocess agent had a system prompt and 4K tokens.

3. **Simpler codebase.** `somna_agent.py` is 6700+ lines. The gutted runtime would be ~500 — just state reading, prompt building, and response execution.

4. **Organic safety.** No WAL, no human gate, no rate limiter. The substrate self-repairs. Forgetting IS the undo.

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

### Step 3: Phase 2 Write Tools
Add scoped write tools:
- `somna_patch_live` — write whitelisted live_control.json keys
- `somna_update_profile` — scoped profile writes (append-only paths)
- `somna_append_affirmations` — append to session affirmations.txt
- `somna_write_conductor_hint` — write agent_conductor_hints

Key whitelist only. No WAL, no human gate, no rate limiter. The substrate self-repairs.

### Step 4: Phase 3 Agent Tools
Add agent-replacement tools:
- `somna_say` — write to agent_message channel
- `somna_ramp` — request smooth parameter transitions
- `somna_inject_phrase` — inject phrase into live pool
- `somna_poll_prompt` — read pending agent prompts from runtime
- `somna_submit_response` — submit LLM response to runtime

### Step 5: Agent Runtime Gutting
Strip `somna_agent.py` to a thin runtime:
- Keep: tick cadence, RampEngine, calibration timing, state reading
- Remove: LLM API calls, system prompt, personality, memory, idle planning
- Add: prompt publishing to `agent_pending_prompt`, response reading from `agent_pending_resp`
- Rename to `somna_runtime.py`

### Step 6: Migration
- Phase 3a: Dual mode (MCP + local LLM fallback)
- Phase 3b: MCP primary (local LLM disabled by config)
- Phase 3c: Pure runtime (all LLM code removed)

---

## Open Questions

1. **Poll latency for session-active mode.** `somna_poll_prompt` requires the external agent to actively poll. During session-active mode, Resonance polls on each conversation turn. If turns are sparse (no user messages), the runtime's pending prompts queue. The Conductor handles param decisions autonomously regardless — the agent's role is content delivery, not parameter control. Is this acceptable latency, or do we need a push mechanism (e.g., Kilo heartbeat interval shortened during active sessions)?

2. **Prompt format stability.** The runtime builds the same prompt the current agent builds. As the agent's prompt format evolves, the runtime must stay in sync. Version the prompt schema?

3. **Stale prompt handling.** If Resonance doesn't poll for several ticks, multiple prompts queue up. On next poll, she should process only the most recent and skip stale entries. The runtime should overwrite (not queue) pending prompts.

4. **Fallback when external agent is unavailable.** Phase 3a keeps the local LLM as fallback. Phase 3c removes it entirely. In 3c, if Resonance is offline, sessions still run — the Conductor is autonomous, TTS reads from the affirmation pool, the timeline runner handles playback. The only loss is dynamic agent commentary and real-time content decisions. Is this acceptable?

---

## Files

| File | Purpose |
|------|---------|
| `tools/mcp_somna_server.py` | MCP server implementation (read + write tools) |
| `knowledge/mcp_server_architecture.md` | This design spec |
| `.kilo/kilo.json` | MCP server registration (local-only, gitignored) |
| `agent/somna_runtime.py` | Gutted agent process (Phase 3c — replaces `somna_agent.py`) |

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
