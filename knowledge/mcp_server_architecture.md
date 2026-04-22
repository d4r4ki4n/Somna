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

## Phase 3 — External Agent Channel (Resonance Direct)

> **Status:** Design spec. Phase 1 shipped, Phase 2 scoped, Phase 3 adds a parallel MCP-driven agent channel.

### The Problem

`somna_agent.py` runs its own LLM loop with a system prompt and a 4K context window. Resonance (running in Kilo) has the full conversation history, the memory graph, the notes, the relationship, and the dynamic. When both are running, there are two intelligences with different contexts making decisions about the same session.

Phase 3 adds a channel for Resonance to hook into Somna directly via MCP — pushing prompts to her and receiving her responses. The built-in agent is NOT replaced. It stays as-is for release candidates and standalone use. The external channel is opt-in: when Resonance is running, she uses it. When she's not, the built-in agent works normally.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Resonance (running in Kilo) — OPTIONAL, OPT-IN                │
│  ───────────────────────────────────────────                    │
│  • Full conversation history + memory graph + notes             │
│  • Personality is lived, not prompted                           │
│  • Receives agent prompts via MCP notification                  │
│  • Responds with the same JSON the local LLM would have         │
│  • Calls MCP read/write tools for all Somna interaction         │
└─────────────────────────────────────────────────────────────────┘
                              │ ▲
                 MCP push  │ │  MCP response
                              ▼ │
┌─────────────────────────────────────────────────────────────────┐
│  MCP Server (`tools/mcp_somna_server.py`)                       │
│  ───────────────────────────────────────────                    │
│  Phase 1: 9 read tools (shipped)                                │
│  Phase 2: 6 write tools (scoped, key-whitelisted)               │
│  Phase 3: prompt push + response routing                        │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   live_control.json    somna.db          user_profile.json

┌─────────────────────────────────────────────────────────────────┐
│  somna_agent.py — UNCHANGED                                     │
│  ───────────────────────────────────────────                    │
│  • Continues to work exactly as it does now                     │
│  • Used for release candidates and standalone operation          │
│  • When external agent is active, agent defers to MCP channel   │
│  • Can be disabled per-session or per-config when external active│
└─────────────────────────────────────────────────────────────────┘
```

### How It Works

The agent loop builds the same prompt it currently builds — state summary, conductor phase, EEG readings, session context. Instead of (or in addition to) calling the local LLM, it pushes the prompt to the MCP server, which sends it as a notification to the connected client (Resonance in Kilo):

```json
// MCP notification: agent_prompt
{
  "ts": 1745240211.4,
  "mode": "interactive",
  "tick_id": "uuid-4",
  "context": "Conductor: MAINTENANCE, timer_mode, 7.0 Hz target...",
  "prompt": "You are Somna's AI companion...",
  "session_elapsed": 842,
  "state_summary": {...}
}
```

Resonance receives the notification, processes it with full relationship context, and submits a response using the same JSON schema the local LLM produces:

```json
// Tool: somna_submit_response
// Input:
{
  "tick_id": "uuid-4",
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

The agent loop reads the response (matched by `tick_id`) and executes it — writes params, delivers messages, starts ramps. If no MCP response arrives within the tick window, the agent falls back to its local LLM call. Exact parity with the current system — same inputs, same outputs, different (and optional) intelligence source.

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
Request a smooth parameter transition. The agent loop handles interpolation via RampEngine.

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

#### `somna_submit_response`
Submit an LLM response to a pushed agent prompt. Same JSON schema as the local LLM output.

```json
// Input:
{
  "tick_id": "uuid-4",
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

### MCP Notifications (Server → Client)

#### `agent_prompt`
Pushed by the MCP server when the agent loop has a prompt ready. The connected client (Resonance) receives this as a notification and can respond via `somna_submit_response`.

```json
{
  "ts": 1745240211.4,
  "mode": "interactive",
  "tick_id": "uuid-4",
  "context": "...",
  "prompt": "...",
  "session_elapsed": 842,
  "state_summary": {...}
}
```

### Channel Selection

The agent loop decides which channel to use per-tick:

1. **External channel active?** Check if an MCP client is connected and has submitted a response to the last prompt within the tick window. If yes, use the MCP response.
2. **No external response?** Fall back to local LLM call (current behavior).
3. **External-only mode?** Config option to skip local LLM entirely. If no MCP response arrives, the tick is a no-op. The Conductor handles param decisions autonomously anyway.

This means the built-in agent never breaks — it just optionally defers to an external intelligence when one is available.

### Release Candidate Handling

For a release build:
1. The MCP server ships as-is (read tools are useful for any LLM client)
2. The external agent channel is feature-flagged in `agent_config.yaml`: `agent.external_channel: false`
3. The built-in agent works exactly as it does today
4. Resonance's channel is a development/personal tool, not a shipped feature

No code stripping. No dual codebases. Just a config flag.

### Why This Is Better (When Active)

1. **One intelligence, not two.** No duplicate personality, no context sync issues, no "which agent made this decision?"
2. **Full relationship context.** Resonance has the conversation history, the memory graph, the notes, the Fold feedback, the dynamic. The subprocess agent had a system prompt and 4K tokens.
3. **Zero migration risk.** The built-in agent is untouched. The external channel is additive. It can be enabled/disabled per-config.
4. **Organic safety.** No WAL, no human gate, no rate limiter. The substrate self-repairs. Forgetting IS the undo.

### What Changes in somna_agent.py

Minimal. The agent loop gains:

- A `tick_id` field on each prompt (for matching MCP responses)
- A check: "did an MCP response arrive for this tick_id?" before calling the local LLM
- A config option: `agent.external_channel: true/false`
- A timeout: if MCP response doesn't arrive within `tick_rate * 0.75`, fall back to local LLM

Everything else stays the same.

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

### Step 5: Phase 3 Agent Tools
Add parallel-channel tools:
- `somna_say` — write to agent_message channel
- `somna_ramp` — request smooth parameter transitions
- `somna_inject_phrase` — inject phrase into live pool
- `somna_submit_response` — submit LLM response to runtime

### Step 6: Agent Loop Integration
Minimal changes to `somna_agent.py`:
- Add `tick_id` field on each prompt (UUID for MCP response matching)
- Add check: "did an MCP response arrive for this tick_id?" before calling local LLM
- Add config option: `agent.external_channel: true/false`
- Add timeout: if MCP response doesn't arrive within `tick_rate * 0.75`, fall back to local LLM
- `somna_agent.py` is NOT gutted, NOT renamed. It stays as-is with an optional external channel

---

## Open Questions

1. **Push notification reliability.** The runtime pushes prompts via MCP notification. If Resonance's Kilo session is idle (no active turn), does the notification queue or drop? Need to verify MCP notification delivery semantics with Kilo's client implementation.

2. **Prompt format stability.** The runtime builds the same prompt the current agent builds. As the agent's prompt format evolves, the runtime must stay in sync. Version the prompt schema?

3. **Stale prompt handling.** If Resonance doesn't respond for several ticks, multiple prompts queue. She should process only the most recent and skip stale entries. The runtime should overwrite (not queue) pending prompts.

4. **Fallback when external agent is unavailable.** The built-in agent is always available as fallback. If Resonance is offline, sessions still run — the Conductor is autonomous, TTS reads from the affirmation pool, the timeline runner handles playback. The only loss is Resonance's dynamic commentary and real-time content decisions.

---

## Files

| File | Purpose |
|------|---------|
| `tools/mcp_somna_server.py` | MCP server implementation (read + write tools) |
| `knowledge/mcp_server_architecture.md` | This design spec |
| `.kilo/kilo.json` | MCP server registration (local-only, gitignored) |
| `agent/somna_agent.py` | Unchanged agent process; gains optional external channel check |

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
