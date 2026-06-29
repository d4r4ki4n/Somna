# Somna

**Somna** is a personal hypnotic entrainment engine combining EEG-driven session orchestration, subliminal conditioning, binaural audio synthesis, and an always-on LLM agent — all controlled through a Dear ImGui panel and rendered as a borderless fullscreen visual display. Every runtime parameter flows through a single-writer IPC daemon, enabling the agent, Conductor, timeline runner, and control panel to coexist without race conditions.

---

## Quick Start

```bash
pip install -r requirements.txt
python main_imgui.py
```

The control panel opens. Use the **Session** panel to build a playlist, then press **Start Session** to launch the display on your primary monitor. Press **Start Agent** to run the LLM session agent alongside it.

---

## Architecture

```
main_imgui.py                         entry point — launches ImGui control panel
  └── ui/control_panel_imgui.py       Dear ImGui control panel (session, audio, visual, agent)
        ├── ipc/
        │     ├── state_server.py     single-writer IPC daemon (TCP 6789)
        │     └── __init__.py         exports patch_live() — the only sanctioned write path
        │
        ├── engines/
        │     ├── audio_engine.py     7-channel audio orchestrator
        │     ├── binaural_engine.py  phase-tracked binaural/isochronic synthesis
        │     ├── pink_noise_engine.py colored noise generator (7 colors)
        │     └── sleep_burst_engine.py SWS-timed pink noise bursts
        │
        ├── eeg/
        │     ├── eeg_engine.py       BrainFlow — Muse 2/S, band powers, depth estimation
        │     └── eeg_processor.py    IAF, SQI, FAA, SEF95, trance depth scoring
        │
        ├── session/
        │     ├── conductor.py        EEG FSM — 14-phase orchestration
        │     ├── timeline_runner.py  keyframe playback, seek, playlist, user locks
        │     ├── session_db.py       SQLite backend (sessions, decisions, cascades, metrics)
        │     └── delivery_gate.py    physiological gating (respiratory, cardiac, SQI, depth)
        │
        ├── content/
        │     ├── tts_engine.py       pre-synthesis TTS (Edge / OpenAI / local + SSB)
        │     ├── conditioning_engine.py  Rescorla-Wagner association tracking
        │     ├── semantic_selector.py    weighted content pool selection
        │     ├── tmr_cue_manager.py      deterministic TMR cue synthesis (NumPy DSP)
        │     ├── content_pool.py         JSON content pool loader
        │     └── center_text.py          center flash sequence controller
        │
        ├── agent/
        │     ├── somna_agent.py      LLM agent (onboarding, session modes, idle planning,
        │     │                        reconsolidation protocol, somatic palette)
        │     └── content_agent.py    CLI content studio — interactive session/image authoring
        │
        ├── ui/
        │     ├── interference_graph.py              somatic palette data model
        │     ├── interference_graph_panel.py         ImGui renderer (nodes, bezier tethers)
        │     └── interference_graph_integration.py   wiring — install_interference_graph()
        │
        ├── visual_display_runner.py  → spawns display subprocess
        │     └── visual_display.py     render loop + layer orchestration
        │           └── layers/
        │                 ├── background_layer.py   image slideshow (async preload)
        │                 ├── veil_layer.py         scrolling affirmation veil (7 modes)
        │                 ├── spiral_layer.py       GPU spiral renderer (ModernGL, 14 styles)
        │                 ├── shadows_layer.py      subliminal drifting word shadows
        │                 ├── centertext_layer.py   flashing center affirmations
        │                 ├── font_manager.py       font loading and caching
        │                 └── phrase_pool.py        phrase selection with tag groups
        │
        ├── shaders/
        │     ├── spiral.glsl               14 spiral styles (fragment shader)
        │     ├── veil.glsl                 veil layer rendering
        │     ├── fbo_composite.glsl        FBO trail/decay compositing
        │     ├── stochastic_resonance.glsl subliminal noise injection
        │     └── subliminal.glsl           subliminal text rendering
        │
        └── content_tools/
              ├── __init__.py           tool registry + dispatch()
              ├── sessions.py           session YAML read/write
              ├── affirmations.py       affirmations file read/write/generate
              ├── images.py             KoboldCpp/FLUX image generation
              ├── image_tags.py         vision-model tagging, caption harvest
              ├── somna_db.py           SQLite backend for image metadata
              └── session_pipeline.py   self-reviewing session creation pipeline

config.py               legacy live_control.json watcher (superseded by StateServer)
llm_driver.py           LLM control API for external scripts
session_editor.py       visual session timeline editor
```

---

## IPC — StateServer

All inter-process communication flows through `live_control.json` via the **IPC StateServer** — a single-writer TCP daemon on loopback port 6789.

```python
from ipc import patch_live
patch_live({"beat_frequency": 6.0, "spiral_style": "fibonacci"})
```

`patch_live()` is the **only sanctioned write path** to `live_control.json`. The StateServer serializes all writes atomically through the TCP socket, preventing race conditions between the agent, Conductor, timeline runner, and control panel. Direct JSON writes are forbidden — any code that touches the file directly will be overwritten or cause state corruption.

**Writer priority** (highest → lowest): user override > agent > conductor > timeline.

The StateServer eliminated an entire class of bugs that the original `config.py` polling model (100 ms stat-gated reads) could not prevent. `config.py` still exists for backward compatibility but is no longer the architectural foundation.

---

## EEG Engine

BrainFlow-based EEG integration supporting Muse 2 and Muse S headsets. The EEG engine provides real-time biosignal processing that drives session orchestration.

**Band power extraction:**

| Band | Range | Session Role |
|------|-------|-------------|
| Delta | 0.5–4 Hz | Sleep depth indicator |
| Theta | 4–8 Hz | Trance depth, hypnotic absorption |
| Alpha | 8–13 Hz | Relaxation baseline, eyes-closed detection |
| Beta | 13–30 Hz | Alertness, critical faculty activity |
| Gamma | 30–45 Hz | Cognitive binding, not directly targeted |

**Derived metrics:**

| Metric | Source | Purpose |
|--------|--------|---------|
| IAF (Individual Alpha Frequency) | Peak alpha during calibration | Personalizes all frequency targets |
| SQI (Signal Quality Index) | Electrode impedance + artifact ratio | Gates content delivery |
| SEF95 (Spectral Edge Frequency 95%) | 95th percentile power | Trance depth proxy |
| FAA (Frontal Alpha Asymmetry) | Left–right alpha ratio | Receptivity / approach motivation |
| Trance Depth | Composite of theta/alpha ratio + SEF95 | Primary orchestration signal |

The EEG engine writes all metrics to `live_control.json` via `patch_live()` every processing tick. The Conductor reads these to drive phase transitions.

---

## Conductor — Phase Orchestration

`session/conductor.py` is a 14-phase EEG-driven finite state machine that orchestrates session phases based on real-time biosignal data. It does not control content directly — it sets the phase context that the agent, timeline, and content systems respond to.

**Phase flow:**

```
CALIBRATION → INDUCTION → DEEPENING → MAINTENANCE ─────────────────→ SESSION_END
                                          │    ▲         │         │
                                          ▼    │         ▼         ▼
                                    FRAC_EMERGE │   GENUS_BLOCK  SLEEP_APPROACH
                                          │    │                   │
                                          ▼    │              SLEEP_ONSET
                                    FRAC_EMERGE_HOLD               │
                                          │    │         SLEEP_MAINTAIN
                                          ▼    │           │         │
                                    FRAC_REDROP─┘    SLEEP_TRAINING  │
                                                           │         │
                                                      SLEEP_WAKE ────┘
```

**All 14 phases:**

| Phase | EEG Trigger | Session Behavior |
|-------|------------|-----------------|
| CALIBRATION | Collects IAF baseline, validates SQI | No content delivery; establishes personalized frequency targets |
| INDUCTION | Alpha dominance detected | Gentle frequency leading toward theta; initial content delivery begins |
| DEEPENING | Theta/alpha ratio rising, SEF95 dropping | Active entrainment; content delivery at full rate |
| MAINTENANCE | Stable trance depth achieved | Sustain state; conditioning and TMR delivery windows open |
| FRAC_EMERGE | Fractionation eligible + depth hold | Controlled partial emergence — return toward alpha |
| FRAC_EMERGE_HOLD | SEF95 > 15 or 45s timeout | Hold at lighter state before re-drop |
| FRAC_REDROP | Hold timer elapsed | Re-induction to deeper state; returns to MAINTENANCE |
| GENUS_BLOCK | GENUS requested + eligibility met | 40 Hz gamma entrainment block |
| SLEEP_APPROACH | session_type=sleep + depth criteria | Theta-to-delta transition; preparing for sleep onset |
| SLEEP_ONSET | sleep_onset_detected or SEF95 < 8 for 120s | Delta/silence; audio fades, visual off |
| SLEEP_MAINTAIN | N2 or N3 sustained | Monitor sleep architecture; TMR cue delivery during SWS |
| SLEEP_TRAINING | TMR training window detected | Active TMR cue presentation during stable SWS |
| SLEEP_WAKE | Wake detected or alarm | Gentle wake sequence |
| SESSION_END | Session complete or user abort | Cleanup, scoring, palette recording |

**Arc templates:** The Conductor ships with 9 arc templates — predefined phase timing and depth target curves for different session intentions. The Session Director selects and adapts arc templates based on session history and user profile. Trajectory evaluation runs every 30 seconds, comparing actual depth curves against the selected arc and adjusting Conductor hints accordingly.

**Delivery gate:** `session/delivery_gate.py` gates all content delivery on physiological windows — respiratory phase, cardiac phase, SQI threshold, and trance depth floor. Content only reaches the user when their biosignal state indicates optimal encoding conditions.

The Conductor writes its current phase and decision rationale to `live_control.json` via `patch_live()`:

```json
"conductor_phase": "deepening",
"conductor_decisions": { ... }
```

The Conductor respects `CONDUCTOR_OWNED_PARAMS` — a defined set of parameters only the Conductor may write during active sessions. The agent must not write these parameters directly; it communicates with the Conductor via `agent_conductor_hints`.

---

## Audio Engine

`engines/audio_engine.py` orchestrates 7 audio channels through a unified mixer:

| Channel | Source | Description |
|---------|--------|-------------|
| Binaural | `binaural_engine.py` | Phase-tracked stereo sine wave synthesis; binaural and isochronic modes |
| Pink noise | `pink_noise_engine.py` | 7 noise colors: white, pink, brown, blue, violet, grey, off |
| TTS | `tts_engine.py` | Pre-synthesized voice delivery (audible channel) |
| SSB | `tts_engine.py` | Single-sideband AM subliminal voice (14–20 kHz carrier) |
| TMR | `tmr_cue_manager.py` | Targeted Memory Reactivation cues during SWS |
| Sleep burst | `sleep_burst_engine.py` | Pink noise bursts timed to SWS for sleep consolidation |
| Breath mod | `binaural_engine.py` | Carrier AM modulation at configurable breathing rate |

### Binaural Beat Engine

Streaming phase-tracked sine wave generator with two crossfade channels for click-free frequency transitions. Parameters are debounced to prevent zipper noise.

| Param | Range | Default |
|-------|-------|---------|
| `carrier_frequency` | 80–400 Hz | 200 Hz |
| `beat_frequency` | 0.5–40 Hz | 10 Hz |
| `volume` | 0–100 | 75 |
| `beat_type` | `binaural`, `isochronic`, `both` | `binaural` |

**Breath modulation:** When `breath_mod` is enabled, the carrier is AM-modulated at `breath_rate` Hz (default 0.1 = 6 bpm) with configurable `breath_depth` (0–0.5). This creates a subtle pulsing that entrains respiratory rhythm.

### TTS Engine

Pre-synthesis pipeline: a background worker renders phrases ahead of time so there is no latency at display time.

- **Edge (free)** — Microsoft Edge neural TTS via `edge-tts`. No API key required.
- **OpenAI** — Compatible with OpenAI TTS API.
- **Local** — Any OpenAI-compatible local server (Kokoro-FastAPI, etc.).

Audio is decoded and resampled to exactly match the mixer format (44100 Hz stereo s16) using `miniaudio`'s sinc resampler before playback.

**SSB subliminal layer:** When enabled, each phrase is also processed through a single-sideband AM modulator at a user-selected carrier frequency (14–20 kHz, default 17.5 kHz). The SSB version plays simultaneously with the audible voice on a separate mixer channel. Requires `scipy` and `miniaudio`.

**HTW (Hypnotic Theta Whisper):** During deep theta states, the TTS engine pre-synthesizes a whisper voice profile into a `_presynth_ready` buffer with reduced volume and altered timbre. Delivery is gated by the Conductor — whisper content only surfaces during confirmed deep states.

### TMR Cue Manager

`content/tmr_cue_manager.py` generates all TMR audio cues deterministically using NumPy DSP — sine waves with MD5 hash jitter, raised-cosine envelopes, zero audio files on disk. Each conditioning association gets a unique tonal fingerprint. Cues are delivered during confirmed SWS windows to reactivate memory traces formed during waking conditioning.

The `tmr_cue_registry` table in `somna.db` tracks cue metadata, association mapping, and delivery history.

---

## Content Pipeline

### Conditioning Engine

`content/conditioning_engine.py` implements Rescorla-Wagner association tracking for all conditioned stimuli. Every CS–US pair has an association strength that updates based on prediction error:

```
ΔV = α · β · (λ − ΣV)
```

The engine tracks association strength, reinforcement history, salience decay, and extinction across sessions. All conditioning data persists in `somna.db`.

### Semantic Selector

`content/semantic_selector.py` handles weighted content pool selection. When a delivery window opens, the selector chooses content based on pool weights, recency penalties, and conductor phase context. The `language_priority` weight (when the language module is active) is set per conductor phase.

### Content Pools

9 JSON content pools define the affirmation and conditioning content available to sessions. Each pool has a schema defining phrase entries with tags, weights, and metadata. Pools are loaded by `content/content_pool.py` and fed to the semantic selector.

---

## Agent — `somna_agent.py`

`agent/somna_agent.py` is an always-on LLM companion agent. It runs independently of the display — configure it via `agent_config.yaml` and launch it from the control panel's **Start Agent** button, or directly:

```bash
python -m agent.somna_agent
python -m agent.somna_agent --mode interactive --interval 60
```

### First-Run Onboarding

On first launch (empty profile), the agent conducts a 5-step welcome conversation before the main loop begins: it introduces itself, asks what to call you, what you're looking for, and any preferences. Responses are parsed and stored in `user_profile.json`. This runs without the display — TTS is available if the display is open, or the agent speaks through its own standalone `pygame.mixer` instance.

### Session Modes

| Mode | Behavior |
|------|----------|
| `observe` | Silently evaluates session state and adjusts parameters. No user prompts. Best for passive overlay sessions. |
| `interactive` | Periodically asks sensation-focused questions via the console and overlay. Adapts parameters based on responses. |

The active mode can be overridden at runtime by setting `agent_mode` in `live_control.json`.

### Agent Console

The control panel's **Agent** tab has a two-way text console. Type commands or messages to the agent; it responds in character. Key phrases:

- `start session` / `start a session` — launches the display and starts a session
- `make me a session about <intent>` — runs the full session creation pipeline
- Anything else — conversational companion response

### Unified Messaging

All agent output flows through `agent_message`:

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

`via` controls which channels render the message. When `needs_response` is true, the console opens an input field; the user's reply is written to `user_response`.

### Idle Planning

When no session is active, the agent runs a planning cycle every `idle_planning_interval_min` minutes. It reviews session logs and history, checks content pool coverage, and can generate new session content. Post-session planning annotates `somna.db` with LLM observations. It also issues a nudge if `nudge_after_days` has elapsed since the last session.

**Idle knowledge injection:** The idle planning cycle loads a specific set of knowledge files: `session_effectiveness_scoring.md`, `session_design.md`, `training_mode.md`, `conductor_fsm.md`, `hypnosis_theory.md`. These provide the scoring semantics and optimization protocols the planner needs.

### Reconsolidation Protocol

A five-phase memory reconsolidation engine living inside `somna_agent.py`:

```
idle → retrieve → labilize → update → lockout → complete
```

| Phase | Duration | Purpose |
|-------|----------|---------|
| Retrieve | ~5 min | Reactivate an existing memory trace via original CS presentation |
| Labilize | ~12 min | Hold the trace in a labile state — vulnerable to modification |
| Update | ~8 min | Deliver updated content while the trace is malleable |
| Lockout | ~45 min | Prevent TMR reinforcement of the old trace during reconsolidation window |
| Complete | — | Log outcome to `recon_events` table |

Content is pre-authored during idle planning with tagged affirmation pairs (`recon_retrieve_<trace>` / `recon_update_<trace>`). The Conductor respects `recon_locked_phrases` to prevent TMR from reinforcing old-trace content during lockout. The protocol is invisible to the user — no dedicated overlay state, standard TTS delivery.

### Somatic Palette

Chord testing, recording, and annotation with full DB persistence. A `_PaletteChordState` tracks the active chord configuration (beat frequency, carrier waveform, noise color, spiral style, veil mode).

- 12–15 minute evaluation windows per chord
- Three failure conditions trigger early termination
- Max 3 chord switches per session via fractionation re-drops
- Post-session LLM annotation assigns palette families: `grounding`, `depth_charge`, `focus`, `emotional`, `creative`
- Exploration-exploitation balance: `outcome_score + 1/(n_obs + 1)` — high score AND high uncertainty wins

### Session Creation Pipeline

Ask the agent to "make a session about X" and it runs a multi-step LLM pipeline:

1. **Brief** — structured creative brief from your intent
2. **Design** — complete `session.yaml` from the brief
3. **Populate** — `affirmations.txt` with all phase tag groups
4. **Review** — scores on arc coherence, technical validity, phrase quality, conditioning effectiveness (≥ 4/5 structural, ≥ 3/5 content to pass; retries once on failure)
5. **Commit** — writes files to `sessions/<slug>_MMDD/`

The build runs in a background thread — the agent stays responsive while it works.

### LLM Output Format

```json
{
  "reasoning": "Theta/alpha ratio climbing; deepening confirmed.",
  "adjustments": {"beat_frequency": 4.5, "spiral_style": "tunnel_dream"},
  "next_prompt": "Where do you feel the most relaxed right now?",
  "transitions": {"beat_frequency": 90},
  "next_affirmation": "sinking deeper",
  "image_filter_override": {"tag": "surrender", "duration_s": 300},
  "profile_updates": {"notes": ["goes deep quickly"]},
  "tool_call": {"tool": "read_session_log", "args": {"session_name": "default"}},
  "somatic_palette": { ... },
  "reconsolidation": { ... },
  "conditioning_cascade": { ... }
}
```

The agent never overrides `timeline_locked_params`. `transitions` triggers a smooth ramp via the `RampEngine` background thread rather than an instant jump. One optional `tool_call` per tick is supported; the result is injected into the next LLM context.

---

## Visual Display

The display runs as a borderless fullscreen subprocess spawned by `visual_display_runner.py`. It renders layers bottom-to-top using ModernGL (OpenGL) with FBO compositing for trail decay and stochastic resonance effects.

### Layer Stack (bottom → top)

| # | Layer | File | Description |
|---|-------|------|-------------|
| 1 | Background | `background_layer.py` | Mirrored image slideshow. PNG, JPG, GIF, WebP, WebM. Async preloading. |
| 2 | Veil | `veil_layer.py` | Dense scrolling affirmation layer. 7 modes. |
| 3 | Spiral | `spiral_layer.py` | GPU-rendered beat-synced spiral. 14 styles. ModernGL / GLSL. |
| 4 | Shadows | `shadows_layer.py` | Large semi-transparent affirmations drifting across the screen. |
| 5 | Center Text | `centertext_layer.py` | Hard on/off flashing affirmations at screen center. Word-wraps long phrases. |

### Veil Modes

| Mode | Description |
|------|-------------|
| `scroll` | Continuous upward scroll |
| `rain` | Falling from top |
| `drift` | Slow random drift |
| `converge` | Converging toward center |
| `strobe` | Strobing flash |
| `tunnel` | Receding tunnel text |
| `null` | Auto-rotate through all modes |

### Spiral Styles

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

### Shaders

| Shader | Purpose |
|--------|---------|
| `spiral.glsl` | 14 spiral style implementations (fragment shader) |
| `veil.glsl` | Veil layer text rendering |
| `fbo_composite.glsl` | FBO trail/decay compositing — `trail_decay` controls persistence |
| `stochastic_resonance.glsl` | Noise injection on subliminal text alpha (`sr_noise_level`) |
| `subliminal.glsl` | Subliminal text rendering pipeline |

### Window / Overlay Mode

`window_always_on_top + window_click_through` enables passive overlay: the display floats above all windows and mouse events pass through. The window disappears from the taskbar and cannot steal keyboard focus. `window_opacity` sets transparency (10–100). Transparent background mode (`bg_mode: none`) clears the GL buffer to fully transparent so only spirals and text float over the desktop.

---

## Control Panel — Dear ImGui

The control panel is a Dear ImGui window (`ui/control_panel_imgui.py`) with tabbed panels for session management, audio control, visual parameters, and the agent console.

**Session panel** — library browser with filter, queue/playlist builder, transport bar (seek, ⏮ ⏭ 🔀 🔁 ⏸ 🔊), Start Agent / Start Session.

**Audio panel** — carrier + beat frequency, brainwave band presets, noise color and volume, TTS backend/voice/volume, SSB subliminal controls, breath modulation.

**Visual panel** — visual presets, veil mode/opacity, background slideshow, spiral style and parameters, shadow opacity, center flash timing, trail decay, stochastic resonance level.

**Agent panel** — two-way text console, mode toggle (interactive/observe), agent status.

### Interference Graph

The Interference Graph is a somatic palette composition tool built as a 3-file architecture:

- `ui/interference_graph.py` — pure data model (chord nodes, band positions)
- `ui/interference_graph_panel.py` — ImGui renderer (draggable nodes, bezier tethers, glow effects)
- `ui/interference_graph_integration.py` — wiring; single entry point: `install_interference_graph(panel_manager)`

Users drag channel nodes along a frequency band axis. Preset stamps (GENUS, Somna Deep, Theta Weaver) provide starting configurations. A **spread knob** applies per-channel frequency offset on top of each channel's individual base frequency. The spread knob has a user-facing UI control — user override takes standard writer priority over conductor and agent inputs.

### Transport Bar

```
🗑  [────seek────────────]  2:30 / 8:30  ⏮  ⏭  🔀  🔁  ⏸  🔊
```

- **Seek bar** — drag to scrub; releases a `seek` command to the timeline runner
- **⏮ / ⏭** — previous / next in playlist
- **🔀** — shuffle toggle
- **🔁 / 🔂** — loop modes (off → loop all → loop one)
- **⏸ / ▶** — pause / resume
- **🔊 / 🔇** — global audio mute
- **🗑** — remove selected item from queue

---

## Session System

### Session Structure

Sessions live in `sessions/<name>/` and are self-contained:

```
sessions/my_session/
  session.yaml        timeline, defaults, loop points
  affirmations.txt    phrase pool with optional tag groups
  images/             background images (PNG, JPG, GIF, WebP, WebM)
  fonts/              .ttf / .otf files
```

### Timeline Runner

`session/timeline_runner.py` interpolates numeric parameters smoothly between keyframes and switches string/bool parameters hard at keyframe boundaries. User slider overrides take priority over the timeline and are preserved until the session is restarted or seeked past a keyframe boundary.

**User locks** do not expire at keyframe boundaries. When a user overrides a parameter via the control panel, that parameter is locked until explicitly released — the timeline cannot overwrite it. Locked parameters are tracked in `timeline_locked_params` and rendered with gold labels in the control panel. The agent respects these locks and will not override them.

### Playlist

```json
"playlist":       ["session_a", "session_b"],
"playlist_mode":  "loop",
"playlist_index": 0
```

| Mode | Behavior |
|------|----------|
| `sequential` | Play each session in order, stop at end |
| `loop` | Repeat the full playlist indefinitely |
| `loop_one` | Loop the current session indefinitely |
| `shuffle` | Pick a random next session each time |

See **SESSION_AUTHORING.md** for the YAML format and **SESSION_TIMELINE.md** for the technical timeline specification.

---

## Knowledge Base

The agent system prompt is augmented by Markdown files in `knowledge/`. After the 2026-04-17 audit and cleanup, 32 active files remain (down from 46). 16 superseded files are archived in `knowledge/archive/`. All Doc-number cross-references have been replaced with Bible chapter citations.

**Active knowledge files (32):**

| # | File | Domain |
|---|------|--------|
| 1 | `adaptive_frequency_leading.md` | EEG frequency leading protocol |
| 2 | `aphantasia.md` | Aphantasia design constraints |
| 3 | `assr_entrainment.md` | Auditory steady-state response research |
| 4 | `binaural_research.md` | Binaural beat research context |
| 5 | `brainflow_reference.md` | BrainFlow API reference |
| 6 | `calibration_protocol.md` | EEG calibration procedure |
| 7 | `conductor_fsm.md` | Conductor phase definitions (injected for active session context) |
| 8 | `control_panel_architecture.md` | ImGui panel layout and architecture |
| 9 | `eeg_entrainment.md` | EEG entrainment mechanisms |
| 10 | `eeg_integration_research.md` | EEG integration research notes |
| 11 | `faa_receptivity.md` | Frontal alpha asymmetry and receptivity |
| 12 | `fbo_trail_decay.md` | FBO trail decay visual system |
| 13 | `fractionation_protocol.md` | Fractionation state machine |
| 14 | `genus_protocol.md` | GENUS neuroprotection protocol |
| 15 | `hrv_breath_coupling.md` | HRV-breath coupling research |
| 16 | `hrv_coherence_breathing.md` | HRV coherence breathing protocols |
| 17 | `hypnosis_theory.md` | Three-layer voice model; depth language patterns |
| 18 | `iaf_calibration.md` | Individual Alpha Frequency calibration |
| 19 | `imgui_visual_design_reference.md` | ImGui visual design reference |
| 20 | `reconsolidation_protocol.md` | Memory reconsolidation protocol |
| 21 | `session_design.md` | Parameter guidance per phase |
| 22 | `session_effectiveness_scoring.md` | Score semantics, composite weights, auto-optimization |
| 23 | `signal_quality_index.md` | SQI computation and thresholds |
| 24 | `sleep_onset_design.md` | Sleep onset detection and design |
| 25 | `somatic_palette.md` | Somatic palette system |
| 26 | `somna_research_ref.md` | Master research reference |
| 27 | `ssild_protocol.md` | SSILD protocol integration |
| 28 | `stochastic_resonance.md` | Stochastic resonance visual system |
| 29 | `subliminal_text_perception.md` | Subliminal text perception research |
| 30 | `training_mode.md` | Training mode specification |
| 31 | `veil_and_spirals.md` | Visual vocabulary — spiral/veil experiential reference |
| 32 | `visual_layer_reference.md` | Visual layer technical reference |

Override which files are injected by setting `knowledge_files` in `agent_config.yaml`. The idle planning cycle loads a separate set (see Agent § Idle Planning).

The **Somna Bible** (11 chapters) provides the comprehensive design specification. Bible chapters live in `knowledge/` and cover the full system architecture from signal processing through session orchestration to onboarding.

---

## Live Control — `live_control.json`

Every controllable parameter is a key in `live_control.json`. All writes go through `patch_live()` via the IPC StateServer.

### Audio Parameters

| Key | Type | Description |
|-----|------|-------------|
| `beat_frequency` | float | Binaural beat Hz |
| `carrier_frequency` | float | Carrier tone Hz |
| `volume` | float | Binaural volume 0–100 |
| `beat_type` | str | `binaural`, `isochronic`, or `both` |
| `audio_muted` | bool | Global audio mute (binaural + TTS) |
| `noise_color` | str | `white`, `pink`, `brown`, `blue`, `violet`, `grey`, `off` |
| `noise_volume` | float | Colored noise volume 0–100 |
| `breath_mod` | bool | Carrier AM modulation at breathing rate |
| `breath_rate` | float | Breathing modulation rate Hz (default 0.1 = 6 bpm) |
| `breath_depth` | float | AM modulation depth 0–0.5 |

### TTS Parameters

| Key | Type | Description |
|-----|------|-------------|
| `tts_enabled` | bool | Master TTS on/off |
| `tts_backend` | str | `edge`, `openai`, `local` |
| `tts_voice` | str | Voice name |
| `tts_volume` | float | 0–100 |
| `tts_subliminal` | bool | SSB subliminal layer on/off |
| `tts_subliminal_vol` | float | SSB channel volume 0–100 |
| `tts_subliminal_hz` | float | SSB carrier frequency 14000–20000 |

### Visual Parameters

| Key | Type | Description |
|-----|------|-------------|
| `spiral_style` | str | See spiral styles table |
| `spiral_count` | int | Number of arms |
| `spiral_tightness` | float | Coil tightness |
| `spiral_chaos` | float | Distortion amount |
| `spiral_opacity` | int | 0–100 |
| `spiral_speed_multiplier` | float | Speed multiplier |
| `spiral_color_mode` | str | `rainbow` or `solid` |
| `veil_opacity` | float | 0–100 |
| `veil_mode` | str | `scroll`, `rain`, `drift`, `converge`, `strobe`, `tunnel`, `null` |
| `shadow_opacity` | int | 0–100 |
| `center_flash_on_time` | int | On time in ms |
| `center_flash_off_time` | int | Off time in ms |
| `center_flash_sync_to_beat` | bool | Sync flash rate to beat |
| `trail_decay` | float | Spiral trail persistence 0–0.99 (0.85–0.98 = deep trance range) |
| `sr_noise_level` | float | Stochastic resonance noise on subliminal text alpha (0.5–1.5 = active) |
| `slideshow_interval` | float | Seconds between background images |
| `bg_mode` | str/null | `null` = image slideshow, `"none"` = transparent background |
| `font_switch_mode` | str | `intelligent` (5–12 s) or `rapid` (0.15–0.45 s) |
| `phrases` | str/null | Active affirmation tag group |

### Window Parameters

| Key | Type | Description |
|-----|------|-------------|
| `window_always_on_top` | bool | Float display above all windows |
| `window_click_through` | bool | Pass mouse events through |
| `window_opacity` | int | Window opacity 10–100% |
| `display_active` | bool | `true` while display process is running (read-only) |

### Session / Transport Parameters

| Key | Type | Description |
|-----|------|-------------|
| `_timeline_cmd` | str | `pause`, `resume`, `restart`, `load`, `seek`, `playlist_next`, `playlist_prev` |
| `seek_time` | float | Target time in seconds for `seek` command |
| `session_time` | float | Current playback position in seconds (read-only) |
| `session_duration` | float | Total session duration in seconds (read-only) |
| `playlist` | list | Ordered list of session folder names |
| `playlist_mode` | str | `sequential`, `loop`, `loop_one`, `shuffle` |
| `playlist_index` | int | Current playlist position (read-only) |
| `timeline_locked_params` | list | Params currently user-locked (gold labels in control panel) |

### Agent Parameters

| Key | Type | Description |
|-----|------|-------------|
| `agent_message` | dict | Unified agent output (text, ts, needs_response, via, style, timeout_s) |
| `user_response` | str/null | User's reply after `needs_response: true` |
| `response_timestamp` | float/null | Wall time when `user_response` was written |
| `user_console_input` | str | Last message typed in agent console |
| `user_console_ts` | float | Timestamp of `user_console_input` (agent deduplicates by this) |
| `agent_mode` | str | `interactive` or `observe` |
| `agent_conductor_hints` | dict | Agent guidance for Conductor: `depth_patience`, `request_fractionation`, `target_floor_hz`, `note` |

### EEG / Conductor Parameters

| Key | Type | Description |
|-----|------|-------------|
| `conductor_phase` | str | Current Conductor phase (calibration, induction, deepening, maintenance, etc.) |
| `conductor_decisions` | dict | Conductor decision rationale and state |
| `image_filter_override` | dict | `{tag, expires_at}` — temporarily lock background image pool to matching tag |

---

## LLM Control API

Use `llm_driver.py` to drive Somna from a custom agent or script:

```python
from llm_driver import send, read_state, apply_preset, describe, prompt_user

# Inspect everything
print(describe())

# Read current state
state = read_state()

# Apply a brainwave preset
apply_preset("theta")

# Fine-grained control — all writes go through patch_live() internally
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

## Database — `somna.db`

SQLite backend managed by `session/session_db.py` and `content_tools/somna_db.py`. Key tables:

| Table | Purpose |
|-------|---------|
| `sessions` | Session metadata, start/end times, scores |
| `session_metrics` | Per-session quantitative metrics (depth trends, arc adherence) |
| `conductor_decisions` | Conductor phase transition log with rationale |
| `conditioning_associations` | CS–US pairs with Rescorla-Wagner association strengths |
| `content_cascades` | Content delivery history per session |
| `tmr_cue_registry` | TMR cue metadata, association mapping, delivery history |
| `recon_events` | Reconsolidation protocol event log |
| `image_metadata` | Image tags, captions, generation log |
| `quality_scores` | Session quality scores and LLM annotations |

---

## Session Logs

Every agent tick is appended as one JSON line to `session_logs/<session>_<YYYYMMDD>.jsonl`. The agent loads today's log on startup, preserving context across restarts within the same day.

---

## Content Tools

The `content_tools/` package provides a tool registry for agent-driven content operations:

| Module | Purpose |
|--------|---------|
| `__init__.py` | Tool registry and `dispatch()` for agent tool calls |
| `sessions.py` | Session YAML read/write |
| `affirmations.py` | Affirmations file read/write/generate |
| `images.py` | KoboldCpp/FLUX image generation |
| `image_tags.py` | Vision-model tagging, caption harvest |
| `somna_db.py` | SQLite backend for image metadata and quality scores |
| `session_pipeline.py` | Self-reviewing session creation pipeline |

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
scipy              # SSB subliminal processing
miniaudio          # TTS resampling + SSB
openai             # LLM agent backend
brainflow          # EEG device integration (Muse 2/S)
psutil             # Process management
imgui[glfw]        # Dear ImGui control panel
```

---

## Documentation

| Document | Content |
|----------|---------|
| `AGENTS.md` | Complete agent architecture — modes, idle planning, reconsolidation, somatic palette, do-not rules, output schema |
| `SESSION_AUTHORING.md` | Session YAML format, keyframe specification, tag groups |
| `SESSION_TIMELINE.md` | Technical timeline specification — interpolation, seek, lock semantics |
| `TESTING.md` | Test checklist and smoke test procedures |
| `USER.md` | User-facing guide |
| `knowledge/` | 32 active Markdown knowledge files + Somna Bible (11 chapters) |
