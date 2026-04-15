# Somna

**Somna** is a personal hypnotic entrainment and subliminal affirmation engine. It runs as a borderless fullscreen visual display paired with a separate control panel, and can be fully driven in real time by an LLM agent via `live_control.json`.

---

## Quick Start

```bash
pip install -r requirements.txt
python main_imgui.py      # Dear ImGui panel (active development)
# python main.py          # legacy Tkinter panel (still functional)
```

The control panel opens. Use the **Session** panel to build a playlist, then press **Start Session** to launch the display on your primary monitor. Press **Start Agent** to run the LLM session agent alongside it.

---

## Architecture

```
main_imgui.py  (active)   OR   main.py  (legacy Tkinter)
  └── control_panel_imgui.py / control_panel.py
        ├── ipc/state_server.py         single-writer IPC daemon (TCP 6789)
        ├── engines/audio_engine.py     7-channel audio (binaural/noise/TTS/TMR/sleep burst)
        ├── content/tts_engine.py       pre-synthesis TTS (Edge / OpenAI / local + SSB)
        ├── agent/somna_agent.py        LLM agent (onboarding, interactive/observe, idle planning)
        ├── eeg/eeg_engine.py           BrainFlow — Muse 2/S, band powers, depth estimation
        ├── session/conductor.py        EEG FSM (calibration→induction→deepening→maintenance)
        ├── session/timeline_runner.py  keyframe playback, seek, playlist, user locks
        └── visual_display_runner.py  → visual_display.py  (display subprocess)
              └── layers/
                    ├── background_layer.py     image slideshow
                    ├── veil_layer.py           scrolling affirmation veil (7 modes)
                    ├── spiral_layer.py         GPU spiral renderer (ModernGL, 14 styles)
                    ├── shadows_layer.py        subliminal drifting word shadows
                    └── centertext_layer.py     flashing center affirmations

ipc/state_server.py     single-writer TCP daemon — the only sanctioned write path
ipc/__init__.py         exports patch_live(updates) — call this to write any live param
session/session_db.py   SQLite backend (sessions, conductor_decisions, content_cascades)
content_tools/          content pool editor, session editor
knowledge/              Markdown knowledge base + Somna Bible (11 chapters)
```

All inter-process communication flows through `live_control.json` via the **IPC StateServer**. Do not write `live_control.json` directly — use `from ipc import patch_live` and call `patch_live({"key": value})`. The StateServer serializes all writes atomically through a loopback TCP socket on port 6789, preventing race conditions between the agent, Conductor, timeline runner, and control panel.

---

## Control Panel

The control panel is a two-column Tkinter window:

**Left column — Session & Audio**
- **Session**: library browser with filter, queue/playlist builder, transport bar (seek, ⏮ ⏭ 🔀 🔁 ⏸ 🔊), Start Agent / Start Session
- **Binaural Beats**: carrier + beat frequency sliders, brainwave band presets, live waveform preview
- **Window / Overlay**: always-on-top, click-through, opacity
- **Voice (TTS)**: backend, voice, volume, subliminal SSB layer

**Right column — Visuals**
- **Visual Presets**: one-click preset buttons (each tinted to its own text color)
- **Veil & Background**: veil opacity, BG slideshow speed, veil mode, transparent background toggle
- **Affirmation Engine**: flash timing, sync-to-beat, duty cycle, variance
- **Subliminal Shadows**: opacity, flash timing
- **Spirals**: style, color, count, tightness, thickness, speed, chaos, opacity, color mode

### Transport bar

The session transport runs along the bottom of the Session panel:

```
🗑  [────seek────────────]  2:30 / 8:30  ⏮  ⏭  🔀  🔁  ⏸  🔊
```

- **Seek bar** — drag to scrub; releases a `seek` command to the timeline runner
- **⏮ / ⏭** — previous / next in playlist
- **🔀** — shuffle toggle
- **🔁 / 🔂** — loop modes (off → loop all → loop one)
- **⏸ / ▶** — pause / resume
- **🔊 / 🔇** — global audio mute (binaural + TTS)
- **🗑** — remove selected item from queue
- The queue divider doubles as a status indicator: `— queue —` at idle, `— now playing —` during playback

### Window / Overlay mode

`window_always_on_top + window_click_through` enables passive overlay: the display floats above all other windows and mouse events pass through to whatever is behind it. The window disappears from the taskbar and cannot steal keyboard focus. `window_opacity` sets transparency (10 = barely visible, 100 = opaque). Transparent background mode (`bg_mode: none`) clears the GL buffer to fully transparent so only spirals and text float over the desktop.

---

## Layer Stack (bottom → top)

| # | Layer | Description |
|---|-------|-------------|
| 1 | **Background** | Mirrored image slideshow. Supports PNG, JPG, GIF, WebP, WebM. Async preloading. |
| 2 | **Veil** | Dense scrolling affirmation layer. Modes: `scroll`, `rain`, `drift`, `converge`, `strobe`, `tunnel`. |
| 3 | **Spiral** | GPU-rendered (ModernGL / GLSL) beat-synced spiral. 14 styles. |
| 4 | **Shadows** | Large semi-transparent affirmations drifting slowly across the screen. |
| 5 | **Center Text** | Hard on/off flashing affirmations at screen center. Word-wraps long phrases. |

---

## Spiral Styles

| ID | Style | Description |
|----|-------|-------------|
| `tunnel_dream` | Tunnel | Receding tunnel illusion |
| `galaxy` | Galaxy | Multi-arm galaxy |
| `archimedean` | Archimedean | Classic evenly-spaced spiral |
| `kaleidoscope` | Kaleidoscope | Radially symmetric kaleidoscope |
| `interference` | Interference | Two-spiral interference pattern |
| `electric` | Electric | High-frequency electric arc |
| `vortex` | Vortex | Tight converging vortex |
| `dna` | DNA | Double helix strand |
| `fibonacci` | Fibonacci | Sunflower dot-packing pattern |
| `rose` | Rose | Four counter-rotating petal layers |
| `moire` | Moiré | Two counter-rotating spirals |
| `spirograph` | Spirograph | Hypotrochoid (inner-gear spirograph) |
| `fermat` | Fermat | Fermat / sunflower spiral, dense center |
| `superformula` | Superformula | Gielis superformula shape |

All styles: seamless color cycling, beat-synced rotation, `rainbow` / `solid` color modes, controllable opacity / tightness / chaos / thickness.

---

## Binaural Beat Engine

Streaming phase-tracked sine wave generator. Two channels for click-free crossfade on frequency changes. Parameters are debounced to prevent zipper noise.

| Param | Range | Default |
|-------|-------|---------|
| `carrier_frequency` | 80–400 Hz | 200 Hz |
| `beat_frequency` | 0.5–40 Hz | 10 Hz |
| `volume` | 0–100 | 75 |

**Presets** (control panel buttons): Delta (2 Hz), Theta (6 Hz), Alpha (10 Hz), Beta (20 Hz), Gamma (40 Hz).

---

## TTS Engine

Pre-synthesis pipeline: a background worker renders phrases ahead of time so there is no latency at display time.

- **Edge (free)** — Microsoft Edge neural TTS via `edge-tts`. No API key required.
- **OpenAI** — Compatible with OpenAI TTS API.
- **Local** — Any OpenAI-compatible local server (Kokoro-FastAPI, etc.).

Audio is decoded and resampled to exactly match the pygame mixer format (44100 Hz stereo s16) using `miniaudio`'s sinc resampler before playback.

**SSB subliminal layer**: when enabled, each phrase is also processed through a single-sideband AM modulator at a user-selected carrier frequency (14–20 kHz, default 17.5 kHz). The SSB version plays simultaneously with the audible voice on a separate mixer channel. Requires `scipy` and `miniaudio`.

---

## Session System

Sessions live in `sessions/<name>/` and are self-contained:

```
sessions/my_session/
  session.yaml        timeline, defaults, loop points
  affirmations.txt    phrase pool with optional tag groups
  images/             background images (PNG, JPG, GIF, WebP, WebM)
  fonts/              .ttf / .otf files
```

The timeline runner interpolates numeric parameters smoothly between keyframes and switches string/bool parameters hard at keyframe boundaries. User slider overrides take priority over the timeline and are **permanently locked** until the session is restarted, seeked, or a new session is loaded — locks do not expire at keyframe boundaries. See **SESSION_AUTHORING.md** for the YAML format and **SESSION_TIMELINE.md** for the technical specification.

### Playlist

Playlists are ordered lists of session folder names, stored in `live_control.json`:

```json
"playlist":       ["session_a", "session_b"],
"playlist_mode":  "loop",
"playlist_index": 0
```

| Mode | Behaviour |
|------|-----------|
| `sequential` | Play each session in order, stop at end |
| `loop` | Repeat the full playlist indefinitely |
| `loop_one` | Loop the current session indefinitely |
| `shuffle` | Pick a random next session each time |

---

## Live Control — `live_control.json`

Every controllable parameter is a key in `live_control.json`. The config watcher polls the file every 100 ms using `os.stat()` for efficiency.

| Key | Type | Description |
|-----|------|-------------|
| `beat_frequency` | float | Binaural beat Hz |
| `carrier_frequency` | float | Carrier tone Hz |
| `volume` | float | Binaural volume 0–100 |
| `audio_muted` | bool | Global audio mute (binaural + TTS) |
| `spiral_style` | str | See spiral styles table |
| `spiral_count` | int | Number of arms |
| `spiral_tightness` | float | Coil tightness |
| `spiral_chaos` | float | Distortion amount |
| `spiral_opacity` | int | 0–100 |
| `spiral_speed_multiplier` | float | Speed multiplier |
| `spiral_color_mode` | str | `rainbow` or `solid` |
| `veil_opacity` | float | 0–100 |
| `veil_mode` | str | `scroll`, `rain`, `drift`, `converge`, `strobe`, `tunnel`, or `null` (auto-rotate) |
| `center_flash_on_time` | int | On time in ms |
| `center_flash_off_time` | int | Off time in ms |
| `center_flash_sync_to_beat` | bool | Sync flash rate to beat |
| `shadow_opacity` | int | 0–100 |
| `font_switch_mode` | str | `intelligent` (5–12 s) or `rapid` (0.15–0.45 s) |
| `phrases` | str/null | Active affirmation tag group |
| `slideshow_interval` | float | Seconds between background images |
| `bg_mode` | str/null | `null` = image slideshow, `"none"` = transparent background |
| `tts_enabled` | bool | Master TTS on/off |
| `tts_backend` | str | `edge`, `openai`, `local` |
| `tts_voice` | str | Voice name |
| `tts_volume` | float | 0–100 |
| `tts_subliminal` | bool | SSB subliminal layer on/off |
| `tts_subliminal_vol` | float | SSB channel volume 0–100 |
| `tts_subliminal_hz` | float | SSB carrier frequency 14000–20000 |
| `window_always_on_top` | bool | Float display above all other windows |
| `window_click_through` | bool | Pass mouse events to apps behind the display |
| `window_opacity` | int | Window opacity 10–100% |
| `_timeline_cmd` | str | `pause`, `resume`, `restart`, `load`, `seek`, `playlist_next`, `playlist_prev` |
| `seek_time` | float | Target time in seconds for `seek` command |
| `playlist` | list | Ordered list of session folder names |
| `playlist_mode` | str | `sequential`, `loop`, `loop_one`, `shuffle` |
| `playlist_index` | int | Current playlist position (read-only, written by timeline runner) |
| `session_time` | float | Current playback position in seconds (read-only) |
| `session_duration` | float | Total session duration in seconds (read-only) |
| `timeline_locked_params` | list | Params currently user-locked (gold labels in control panel) |
| `noise_color` | str | `white`, `pink`, `brown`, `blue`, `violet`, `grey`, `off` (user-only) |
| `noise_volume` | float | Colored noise volume 0–100 |
| `agent_message` | dict | Unified agent output — `text`, `ts`, `needs_response`, `via`, `style`, `timeout_s` |
| `user_response` | str/null | User's reply after `needs_response: true` |
| `response_timestamp` | float/null | Wall time when `user_response` was written |
| `user_console_input` | str | Last message typed in the agent console |
| `user_console_ts` | float | Timestamp of `user_console_input` (agent deduplicates by this) |
| `agent_mode` | str | `interactive` or `observe` — live override of agent's configured mode |
| `agent_conductor_hints` | dict | Agent-written guidance for Conductor: `depth_patience`, `request_fractionation`, `target_floor_hz`, `note` |
| `conductor_phase` | str | Current Conductor phase written each tick: `calibration`, `induction`, `deepening`, `maintenance`, etc. |
| `image_filter_override` | dict | `{tag, expires_at}` — temporarily locks background image pool to images matching tag |
| `trail_decay` | float | Spiral trail persistence 0–0.99; 0=no trails, 0.85–0.98=deep trance range |
| `sr_noise_level` | float | Stochastic resonance noise on subliminal text alpha; 0=off, 0.5–1.5=active range |
| `beat_type` | str | `binaural`, `isochronic`, or `both` |
| `breath_mod` | bool | Carrier AM modulation at breathing rate |
| `breath_rate` | float | Breathing modulation rate Hz (default 0.1 = 6 bpm) |
| `breath_depth` | float | AM modulation depth 0–0.5 |
| `display_active` | bool | `true` while the display process is running; cleared on exit |

---

## LLM Control

Use `llm_driver.py` to drive Somna from a custom agent or script:

```python
from llm_driver import send, read_state, apply_preset, describe, prompt_user

# Inspect everything
print(describe())

# Read current state
state = read_state()

# Apply a brainwave preset
apply_preset("theta")

# Fine-grained control
send({
    "beat_frequency":   6.0,
    "spiral_style":     "fibonacci",
    "veil_opacity":     65,
})

# Transport commands
send({"_timeline_cmd": "pause"})
send({"_timeline_cmd": "resume"})
send({"_timeline_cmd": "seek", "seek_time": 120.0})

# Ask the user a question (shows overlay dialog, blocks until answered)
prompt_user("How does your body feel right now?", timeout_s=60)
```

---

## LLM Session Agent (`somna_agent.py`)

`somna_agent.py` is an always-on companion agent. It runs independently of the display — configure it via `agent_config.yaml` and launch it from the control panel's **Start Agent** button, or directly:

```bash
# Local model (recommended — configure base_url in agent_config.yaml)
python somna_agent.py

# Override model / mode on the command line
python somna_agent.py --mode interactive --interval 60 --base-url http://localhost:11434/v1
```

### First-run onboarding

On first launch (empty profile), the agent conducts a short console conversation before the main loop begins: it introduces itself, asks what to call you, what you're looking for here, and any preferences. Responses are parsed and stored in `user_profile.json`. This runs without the display — TTS is available if the display is open, or the agent will speak through its own standalone audio channel.

### Modes

| Mode | Behaviour |
|------|-----------|
| `observe` | Silently evaluates session state and adjusts parameters. No user prompts. Best for passive overlay sessions. |
| `interactive` | Periodically asks sensation-focused questions via the control panel console and overlay. Adapts parameters based on responses. |

The active mode can be overridden at runtime by setting `agent_mode` in `live_control.json` (`"interactive"` or `"observe"`).

### Agent console

The control panel's **Agent** tab has a two-way text console. Type commands or messages to the agent; it responds in character. Key phrases the agent understands:

- `start session` / `start a session` — launches the display and starts a session
- `make me a session about <intent>` — runs the full session creation pipeline in the background
- Anything else — the agent responds as a conversational companion

### Unified messaging — `agent_message`

All agent output flows through a single key:

```json
"agent_message": {
  "text":           "How do you feel?",
  "ts":             1712345678.4,
  "needs_response": true,
  "via":            ["console", "overlay", "tts"],
  "style":          {"zoom_speed": "slow", "intensity": "soft"},
  "timeout_s":      120
}
```

`via` controls which channels the message appears on. The control panel, display overlay, and TTS engine each read this key independently. When `needs_response` is true, the control panel opens an input dialog; the user's reply is written to `user_response`.

### Standalone TTS

The agent initialises its own `pygame.mixer` instance so it can speak to you even when the display is not open. When the display is running, it sets `display_active: true` in `live_control.json` and the agent defers TTS playback to the display's engine, avoiding double audio.

### Idle mode

When no session is active the agent runs a planning cycle every `idle_planning_interval_min` minutes. It reviews session logs, checks whether phrase pools are sparse, and can generate new session content. It will also issue a nudge if `nudge_after_days` has elapsed since your last session. Post-session planning annotates `somna.db` with a brief LLM observation about the session.

### Session creation pipeline

Ask the agent to "make a session about X" and it runs a multi-step LLM pipeline:

1. **Brief** — writes a structured creative brief from your intent
2. **Design** — generates a complete `session.yaml` from the brief
3. **Populate** — writes `affirmations.txt` (all phase tag groups)
4. **Review** — scores the session on arc coherence, technical validity, phrase quality, and conditioning effectiveness (≥ 4/5 structural, ≥ 3/5 content to pass). Retries once on failure.
5. **Commit** — writes files to `sessions/<slug>_MMDD/`

The build runs in a background thread — the agent stays responsive while it works.

### Knowledge base

The agent system prompt is augmented by Markdown files in `knowledge/`:

| File | Content |
|------|---------|
| `gateway_process.md` | Focus Level map, frequency protocol, phase timing |
| `session_design.md` | Parameter guidance per phase, what to change when |
| `veil_and_spirals.md` | Visual vocabulary — spiral/veil experiential reference |
| `hypnosis_theory.md` | Three-layer voice model (guide / fill / inscribe); depth language patterns |
| `conductor_fsm.md` | Conductor phase meanings; injected for active session context |
| `binaural_research.md` | Research context |

Override which files are injected by setting `knowledge_files` in `agent_config.yaml`. The idle planning cycle loads a separate set: `session_effectiveness_scoring.md`, `session_design.md`, `training_mode.md`, `conductor_fsm.md`, `hypnosis_theory.md`.

### Session logs

Every agent tick is appended as one JSON line to `session_logs/<session>_<YYYYMMDD>.jsonl`. The agent loads today's log on startup, preserving context across restarts within the same day.

### LLM output format

```json
{
  "reasoning": "User seems deeply relaxed; deepening.",
  "adjustments": {"beat_frequency": 4.5, "spiral_style": "tunnel_dream"},
  "next_prompt": "Where do you feel the most relaxed right now?",
  "transitions": {"beat_frequency": 90},
  "next_affirmation": "sinking deeper",
  "image_filter_override": {"tag": "surrender", "duration_s": 300},
  "profile_updates": {"notes": ["goes deep quickly"]},
  "tool_call": {"tool": "read_session_log", "args": {"session_name": "default"}}
}
```

The agent never overrides `timeline_locked_params`. `transitions` triggers a smooth ramp via the `RampEngine` background thread rather than an instant jump. One optional `tool_call` per tick is supported; the result is injected into the next LLM context.

---

## File Reference

| File | Purpose |
|------|---------|
| `main.py` | Entry point |
| `control_panel.py` | Tkinter control panel UI |
| `visual_display.py` | Render loop and layer orchestration |
| `visual_display_runner.py` | Subprocess wrapper for display window |
| `audio_engine.py` | Binaural beat generator |
| `tts_engine.py` | TTS pre-synthesis pipeline |
| `timeline_runner.py` | Session timeline playback thread |
| `config.py` | `live_control.json` watcher |
| `llm_driver.py` | LLM control API for external scripts |
| `somna_agent.py` | Always-on LLM companion agent |
| `content_agent.py` | CLI content studio — interactive session/image authoring |
| `conductor.py` | Conductor FSM — EEG-driven session phase orchestration |
| `session_editor.py` | Visual session timeline editor |
| `agent_config.yaml` | Agent configuration (LLM backend, intervals, knowledge files) |
| `user_profile.json` | Persistent user profile — name, goals, preferences, history |
| `live_control.json` | Real-time parameter bridge |
| `somna.db` | SQLite database — image tags, generation log, session quality scores |
| `shaders/spiral.glsl` | GLSL fragment shader (14 spiral styles) |
| `layers/background.py` | Background layer |
| `layers/veil.py` | Veil affirmation layer |
| `layers/spirals_opengl.py` | Spiral layer (ModernGL) |
| `layers/shadows.py` | Shadow affirmation layer |
| `layers/center_text.py` | Center text layer |
| `layers/agent_prompt.py` | In-display agent message overlay (zooming text) |
| `layers/font_manager.py` | Font loading and caching |
| `layers/phrase_pool.py` | Phrase selection with tag group support |
| `content_tools/__init__.py` | Tool registry and `dispatch()` for agent tool calls |
| `content_tools/sessions.py` | Session YAML read/write |
| `content_tools/affirmations.py` | Affirmations file read/write/generate |
| `content_tools/images.py` | KoboldCpp/FLUX image generation |
| `content_tools/image_tags.py` | Vision-model tagging, caption harvest |
| `content_tools/somna_db.py` | SQLite backend for image metadata and quality scores |
| `content_tools/session_pipeline.py` | Self-reviewing session creation pipeline |
| `knowledge/` | Markdown files injected into agent system prompt |
| `session_logs/` | Per-session JSONL agent response history |
| `sessions/` | Session folders — `session.yaml`, `affirmations.txt`, `images/`, `fonts/` |
| `tests/test_smoke.py` | Smoke tests — `pytest tests/` |
| `SESSION_AUTHORING.md` | Session authoring guide |
| `SESSION_TIMELINE.md` | Technical timeline specification |

---

## Dependencies

```
pygame>=2.6.0
pyyaml
pillow
moderngl
numpy
opencv-python
edge-tts
scipy          # optional: SSB subliminal processing
miniaudio      # required for TTS resampling + SSB
openai         # optional: required only for somna_agent.py
```
