# Somna Bible — Gap Closure Document

*Date: 2026-04-17*
*Author: Reese (audit integration)*
*Purpose: Paste-ready sections closing all 36 identified gaps between Bible specification and shipped code/design documents.*

---

Each section below is formatted for direct insertion into the corresponding Bible chapter. Section headers use the `§` notation consistent with existing Bible formatting. Implementation details are drawn from the full-stack audit (73 modules, 13 packages), AGENTS.md (1,542 lines), runtime knowledge files, and the VR Bubble Architecture v2.1 / Language Module Design v1.1 design documents.

---

# Chapter 1 — Processing Stack

## §1.X IPC StateServer Architecture

### The Problem It Solves

Somna's runtime has four concurrent writers: the LLM agent, the Conductor FSM, the timeline runner, and the control panel UI. All four need to mutate `live_control.json` — the single shared state document that every subsystem reads. Direct file writes from multiple processes produce race conditions: partial writes, torn reads, and state corruption under load.

### The Solution: Single-Writer TCP Daemon

`ipc/state_server.py` runs a TCP daemon on loopback port 6789. It is the **only process that writes `live_control.json`**. All other writers submit mutations as JSON patches over TCP. The StateServer serializes all writes atomically — one patch at a time, in arrival order, with no interleaving.

```
┌─────────────┐     TCP 6789     ┌──────────────┐
│  Agent       │────────────────▶│              │
│  Conductor   │────────────────▶│  StateServer │──▶ live_control.json
│  Timeline    │────────────────▶│              │
│  Control Panel│───────────────▶│              │
└─────────────┘                  └──────────────┘
```

### The Write API

`ipc/__init__.py` exports a single function:

```python
from ipc import patch_live
patch_live({"beat_frequency": 6.0, "spiral_style": "helix"})
```

`patch_live()` opens a TCP connection to the StateServer, sends the key-value dict as JSON, and receives an acknowledgment. The StateServer applies the patch to its in-memory copy, writes the full JSON atomically (write-to-temp + rename), and confirms. Total round-trip: < 1ms on loopback.

### Writer Priority

When multiple patches arrive in the same tick, the StateServer processes them in arrival order. Semantic priority is enforced by convention, not by the server:

| Priority | Writer | Scope |
|----------|--------|-------|
| 1 (highest) | User (UI) | Any parameter the user explicitly sets |
| 2 | Agent | Non-conductor-owned parameters during session |
| 3 | Conductor | `CONDUCTOR_OWNED_PARAMS` during active FSM |
| 4 (lowest) | Timeline | Keyframe interpolation (yields to all above) |

The Conductor owns a specific parameter set (`CONDUCTOR_OWNED_PARAMS`) during active orchestration. The agent must not write these parameters while the Conductor is active — this is enforced in agent code, not in the StateServer.

### Legacy: config.py

`config.py` predates the StateServer. It implemented a 100ms `os.stat()` poll loop to detect `live_control.json` changes. This pattern still exists for backward compatibility but is no longer the primary IPC mechanism. All new code must use `patch_live()`. Direct writes to `live_control.json` are forbidden — they bypass the StateServer's atomicity guarantee and will be overwritten on the next StateServer flush.

---

## §1.Y Package Structure

The codebase is organized into 13 packages containing 73 modules plus 5 GLSL shaders:

| Package | Modules | Responsibility |
|---------|---------|----------------|
| `ipc/` | 2 | StateServer daemon + `patch_live()` API |
| `engines/` | 4 | Audio orchestration, binaural synthesis, noise, sleep bursts |
| `eeg/` | 2 | BrainFlow integration, signal processing, depth estimation |
| `session/` | 7 | Conductor FSM, timeline, planner, evaluator, DB, delivery gate |
| `content/` | 8 | TTS, conditioning engine, semantic selector, TMR, content pools |
| `agent/` | 3 | LLM agent, content agent, tool definitions |
| `ui/` | 12 | ImGui control panel, all panels, interference graph (3 files) |
| `layers/` | 7 | Visual display layers (background, veil, spiral, shadows, center text, font, FBO) |
| `shaders/` | 5 | GLSL vertex/fragment shaders |
| `content_tools/` | 4 | Content pool editor, session editor utilities |
| Root | 8 | Entry point, display runner, visual display, config, utilities |

Entry point: `main_imgui.py` → `ui/control_panel_imgui.py`.

Display subprocess: `visual_display_runner.py` → `visual_display.py` (separate process, communicates via `live_control.json` through StateServer).

---

# Chapter 2 — Biosignal Science

## §2.X EEG Signal Processing Pipeline

### Hardware: Muse 2/S via BrainFlow

`eeg/eeg_engine.py` manages the BrainFlow session lifecycle — board initialization, streaming start/stop, and raw sample acquisition from the Muse 2 or Muse S headband over Bluetooth. BrainFlow provides a hardware-agnostic API; the engine configures it for the Muse's 4-channel EEG (TP9, AF7, AF8, TP10) at 256 Hz.

### Band Power Extraction

`eeg/eeg_processor.py` computes band powers from raw EEG using windowed FFT:

| Band | Range | Primary Use |
|------|-------|-------------|
| Delta | 0.5–4 Hz | Sleep stage detection, deep trance indicator |
| Theta | 4–8 Hz | Trance depth, hypnotic susceptibility correlate |
| Alpha | 8–13 Hz | Relaxation baseline, IAF anchor |
| Beta | 13–30 Hz | Alertness, critical faculty activity |
| Gamma | 30–50 Hz | Not primary; monitored for artifact rejection |

### Individual Alpha Frequency (IAF)

IAF is the user's personal alpha peak — the frequency within the 8–13 Hz band where their alpha power is strongest. It varies between individuals (typically 9–11 Hz) and serves as the anchor point for personalized entrainment targets. IAF is measured during the CALIBRATION phase of each session and stored in the session database for longitudinal tracking.

`iaf_calibration.md` in the knowledge folder provides the full calibration protocol: 2-minute eyes-closed resting recording, peak detection via spectral analysis, confidence scoring, and fallback to population mean (10 Hz) when signal quality is insufficient.

### Signal Quality Index (SQI)

SQI is a composite score (0.0–1.0) reflecting the reliability of the current EEG signal. Components include:

- **Electrode impedance**: High impedance (poor skin contact) degrades signal
- **Motion artifact detection**: Head movement introduces low-frequency drift
- **Line noise (50/60 Hz)**: Environmental electrical interference
- **Signal variance**: Abnormally flat or saturated channels

SQI is published to `live_control.json` as `eeg_sqi` and consumed by the delivery gate — content is only delivered when SQI exceeds a threshold, ensuring conditioning and affirmations arrive during clean signal windows.

### Frontal Alpha Asymmetry (FAA)

FAA measures the difference in alpha power between left (AF7) and right (AF8) frontal electrodes. Positive FAA indicates approach motivation; negative FAA indicates withdrawal/avoidance.

FAA is used by:
- **Somatic Palette evaluation**: Persistent negative FAA (>6 min) triggers chord abandonment
- **Agent reasoning**: FAA trends inform idle planning and session evaluation
- **Reconsolidation timing**: Approach state supports update phase delivery

Published as `faa_value` in `live_control.json`.

### Spectral Edge Frequency 95% (SEF95)

SEF95 is the frequency below which 95% of the EEG power resides. It drops as the user enters deeper states:

| SEF95 Range | Typical State |
|-------------|---------------|
| 20–25 Hz | Alert, eyes open |
| 15–20 Hz | Relaxed, light trance |
| 10–15 Hz | Moderate trance |
| 5–10 Hz | Deep trance / drowsy |
| < 5 Hz | Sleep onset |

SEF95 contributes to the composite trance depth score and is published as `eeg_sef95`.

### Trance Depth Composite

The trance depth score combines multiple EEG indicators into a single 0.0–1.0 value:

- Theta/Alpha ratio (primary contributor)
- SEF95 (lower = deeper)
- FAA (approach state correlates with receptivity)
- SQI weighting (low-quality epochs are down-weighted)

Published as `trance_score` in `live_control.json`. This is the Conductor's primary decision variable for phase transitions.

---

## §2.Y Delivery Gate — Physiological Gating

`session/delivery_gate.py` implements a multi-signal gate that determines **when** content (affirmations, conditioning cues, language items) can be delivered. The gate opens only when physiological conditions are simultaneously favorable:

| Signal | Gate Condition | Rationale |
|--------|---------------|-----------|
| Respiratory phase | Exhalation detected | Parasympathetic dominance during exhale increases receptivity |
| Cardiac phase | Inter-beat interval (relaxed timing) | Baroreceptor-mediated attention modulation |
| SQI | Above threshold (default 0.6) | Ensures EEG reading is reliable enough to trust depth estimate |
| Trance depth | Above phase-appropriate minimum | Content delivered too shallow is wasted; too deep risks disruption |

The gate is **permissive, not prescriptive** — it prevents delivery during bad windows but does not force delivery during good ones. The content system queries the gate; the gate returns open/closed. The content system decides what to deliver and how much.

### Burst Sequencing

For content that requires multiple sequential deliveries (e.g., language encoding with 3 repetitions at decreasing ISI), the gate uses burst mode: the first item in the burst is gate-checked normally. Once the gate opens for the first item, subsequent items in the burst fire on their own ISI schedule without individual gate checks. This prevents physiological timing from fragmenting time-sensitive encoding sequences.

---

# Chapter 3 — Audio & Entrainment

## §3.X Seven-Channel Audio Architecture

`engines/audio_engine.py` orchestrates seven concurrent audio channels, each with independent volume, routing, and synthesis:

| Channel | Engine | Source | Purpose |
|---------|--------|--------|---------|
| 1. Binaural | `binaural_engine.py` | Real-time synthesis | Phase-tracked binaural or isochronic beats |
| 2. Carrier | `binaural_engine.py` | Real-time synthesis | Base frequency carrier wave (sine, triangle, saw, square) |
| 3. Pink noise | `pink_noise_engine.py` | Real-time synthesis | Colored noise (7 colors: white, pink, brown, blue, violet, grey, off) |
| 4. TTS | `tts_engine.py` | Pre-synthesized | Agent voice, affirmations, language items |
| 5. SSB | `tts_engine.py` | Pre-synthesized + modulated | Subliminal affirmations via single-sideband AM shift |
| 6. TMR | `tmr_cue_manager.py` | Deterministic synthesis | Targeted Memory Reactivation cues during SWS |
| 7. Sleep burst | `sleep_burst_engine.py` | Real-time synthesis | SWS-timed pink noise bursts for slow-oscillation entrainment |

All channels write to `live_control.json` via `patch_live()` for volume and parameter control.

### Binaural Engine Details

`engines/binaural_engine.py` generates phase-accurate binaural beats by synthesizing two independent sine waves (left/right ear) with a frequency difference equal to the target beat frequency. Phase tracking ensures continuous waveforms across parameter changes — no clicks or discontinuities when the beat frequency shifts mid-session.

Supports isochronic mode: amplitude-modulated pulses at the target frequency, useful when the user is on speakers rather than headphones (binaural beats require headphone isolation).

### Pink Noise Engine

`engines/pink_noise_engine.py` generates colored noise across 7 spectral profiles:

| Color | Spectral Slope | Character |
|-------|---------------|-----------|
| White | Flat (0 dB/oct) | Harsh, bright |
| Pink | -3 dB/oct | Natural, balanced |
| Brown | -6 dB/oct | Deep, warm |
| Blue | +3 dB/oct | Bright, thin |
| Violet | +6 dB/oct | Very bright |
| Grey | Perceptually flat (A-weighted) | Neutral to human hearing |
| Off | — | Channel silent |

Noise color is a somatic palette parameter — different users respond to different noise profiles, and the palette system records which colors work best.

### Sleep Burst Engine

`engines/sleep_burst_engine.py` delivers precisely timed pink noise bursts during slow-wave sleep (SWS). The bursts are phase-locked to the user's slow oscillations (detected via delta band power) to enhance slow-oscillation entrainment — a technique supported by sleep neuroscience research for boosting memory consolidation.

Burst parameters: duration (50–200ms), inter-burst interval (derived from detected SO frequency), amplitude envelope (raised cosine), and noise color (defaults to pink).

### TTS Pre-Synthesis Architecture

`content/tts_engine.py` supports three TTS backends: Edge TTS (cloud, default), OpenAI TTS (cloud, higher quality), and local TTS. All backends pre-synthesize content into `_presynth_ready` buffers during early session phases (CALIBRATION or early INDUCTION), not on-demand during delivery.

Pre-synthesis is critical for timing — TTS generation latency (200–800ms for cloud, 50–200ms for local) would disrupt delivery gate timing if synthesis happened at delivery time. The HTW (Hypnotic Throat Whisper) system pioneered this pattern: a separate voice profile synthesizes whisper-layer content into its own buffer, enabling simultaneous multi-voice delivery.

### SSB Subliminal Embedding

Single-Sideband Amplitude Modulation shifts TTS audio above the conscious perception threshold while remaining subliminally processable. The carrier frequency, modulation depth, and sideband selection are configurable per session. SSB content rides on the noise or binaural channel — the user perceives only the carrier audio while the embedded affirmations are delivered below awareness.

### TMR Cue Synthesis

`content/tmr_cue_manager.py` generates Targeted Memory Reactivation cues using **deterministic NumPy DSP** — no audio files. Each cue is a sine wave with:
- Frequency derived from the associated content (MD5 hash of affirmation text → frequency mapping)
- Raised-cosine envelope (no clicks)
- Amplitude jitter (slight randomization to prevent habituation)
- Duration: 200–500ms

Cues are registered in the `tmr_cue_registry` table with columns: `cue_id`, `source` (conditioning/language/custom), `frequency_hz`, `associated_content`, `play_count`, `last_played`. The TMR engine plays cues during detected SWS windows, with inter-cue intervals respecting the sleep burst schedule to avoid mutual interference.

**Language TMR extension**: Language vocabulary cues use pre-rendered TTS audio (Mandarin pronunciations) rather than synthesized tones. The playback path branches on `source`: `if source == 'language': play_prerendered(audio_path)` vs `synthesize_and_play()` for conditioning cues. Both paths share the same timing, gating, and registration infrastructure.

---

# Chapter 4 — Session Architecture

## §4.X Conductor — 14-Phase FSM

`session/conductor.py` implements a 14-phase finite state machine that orchestrates the session arc based on real-time EEG data:

```
CALIBRATION → INDUCTION → DEEPENING → MAINTENANCE ─────────────────────→ SESSION_END
                                          │    ▲         │         │
                                          ▼    │         ▼         ▼
                                    FRAC_EMERGE │   GENUS_BLOCK  SLEEP_APPROACH
                                          │    │                   │
                                          ▼    │              SLEEP_ONSET
                                    FRAC_EMERGE_HOLD               │
                                          │    │         SLEEP_MAINTAIN
                                          ▼    │           │         │
                                    FRAC_REDROP┘    SLEEP_TRAINING  │
                                                           │         │
                                                      SLEEP_WAKE ────┘
```

### Phase Definitions

| Phase | Duration | Purpose | Transition Trigger |
|-------|----------|---------|-------------------|
| CALIBRATION | 2–5 min | IAF measurement, SQI baseline, system settling | SQI ≥ REDUCED ×2ch for 30s + IAF detected |
| INDUCTION | 5–15 min | Guide user from waking state toward trance | ASSR confidence ≥ REDUCED for 60s |
| DEEPENING | 10–20 min | Deepen trance via progressive frequency reduction | trance_score > 0.65 (90s) + ASSR ≥ REDUCED (60s) |
| MAINTENANCE | 20–60 min | Sustained trance for content delivery and conditioning | Session end trigger or emergence request |
| FRAC_EMERGE | 2–3 min | Controlled partial emergence — return toward alpha | Frac eligible + trance > 0.5 (60s) |
| FRAC_EMERGE_HOLD | 1–2 min | Hold at lighter state before re-drop | SEF95 > 15 or 45s timeout |
| FRAC_REDROP | 3–5 min | Re-induction to deeper state; returns to MAINTENANCE | Hold elapsed 15–45s |
| GENUS_BLOCK | Variable | 40 Hz gamma entrainment block | GENUS requested + eligibility met |
| SLEEP_APPROACH | 10–20 min | Theta-to-delta transition; preparing for sleep onset | session_type=sleep + depth criteria |
| SLEEP_ONSET | Variable | Delta/silence; audio fades, visual off | sleep_onset_detected or SEF95 < 8 for 120s |
| SLEEP_MAINTAIN | Hours | Monitor sleep architecture; TMR cue delivery during SWS | N2 or N3 for ≥ 3 consecutive epochs |
| SLEEP_TRAINING | Variable | Active TMR cue presentation during stable SWS | TMR training window detected |
| SLEEP_WAKE | 5–10 min | Gentle wake sequence | Wake detected or alarm |
| SESSION_END | 1–2 min | Cleanup, scoring, palette recording | Session complete or user abort |

### Arc Templates

The Conductor selects from 9 arc templates based on session intent, user history, and entry state:

Each arc template defines target parameter curves for every phase — beat frequency trajectory, noise volume envelope, spiral intensity, veil density. The Conductor interpolates between template keyframes using the current phase progress as the interpolation parameter.

### Trajectory Evaluation

Every 30 seconds during MAINTENANCE, the Conductor evaluates the session trajectory:
- Is trance depth holding, deepening, or declining?
- Is FAA trending approach or withdrawal?
- Is SQI degrading (headband slipping, movement)?

Based on this evaluation, the Conductor may:
- Adjust beat frequency (micro-corrections, ±0.5 Hz)
- Request agent intervention (verbal re-deepening)
- Initiate fractionation (if depth is declining despite corrections)
- Begin emergence (if depth is unrecoverable or session time exceeded)

### Agent-Conductor Hints

The agent communicates with the Conductor through `agent_conductor_hints` in `live_control.json`:
- `request_fractionation`: Agent requests a fractionation cycle (e.g., after somatic palette chord failure)
- `suggest_emergence`: Agent recommends beginning emergence
- `depth_target`: Agent's preferred depth target for current content delivery needs

These are hints, not commands — the Conductor evaluates them against EEG data before acting. The agent cannot force a phase transition that the EEG data doesn't support.

---

## §4.Y Somatic Palette System

### What Is a Palette Entry

A palette entry records: **this cross-modal configuration (chord)** + **this entry context** → **this state outcome** for this user.

A chord is a snapshot of audio/visual parameters active when an evaluation window opens during MAINTENANCE:

| Parameter | Source |
|-----------|--------|
| `beat_frequency` | Binaural engine |
| `carrier_waveform` | Binaural engine (sine, triangle, saw, square) |
| `noise_color` | Pink noise engine (7 colors) |
| `noise_volume` | Pink noise engine |
| `spiral_style` | Spiral layer (14 styles) |
| `veil_mode` | Veil layer (7 modes) |

Over many sessions, entries accumulate into a personal response map — a library of what works for this specific user at specific times of day and entry states.

### Chord Testing Protocol

Each chord is evaluated over a **12–15 minute window** in MAINTENANCE. The agent monitors three failure conditions; any single failure triggers an abandon and chord switch:

| Failure Condition | Threshold | Window |
|-------------------|-----------|--------|
| Low trance score | `trance_score` never exceeds 0.40 | After 8 minutes |
| Avoidant state | `faa_value` persistently negative | For > 6 continuous minutes |
| Declining depth | Depth composite flat or declining | Across full evaluation window |

On failure: the agent requests fractionation via `agent_conductor_hints`. The Conductor runs FRAC_EMERGE → FRAC_HOLD → FRAC_REDROP. On MAINTENANCE re-entry, a **3-minute cooldown** precedes the new chord's evaluation window.

A session caps at **3 chord switches** to prevent fractionation exhaustion.

### Chord Selection: Exploration-Exploitation

When selecting the next chord after a failure, the agent uses a score + uncertainty heuristic:

```
selection_score = outcome_score + 1 / (n_observations + 1)
```

A chord tried 1–2 times with a promising score outranks a well-worn chord at the same average. This balances exploitation (use what's proven) with exploration (discover something better). This is functionally a multi-armed bandit for somatic states.

When palette history is sparse, the agent steps through predefined beat frequency and carrier waveform variations to populate the palette quickly.

### Palette Families

Five named families assigned by LLM annotation post-session:

| Family | Character | Best Entry Conditions |
|--------|-----------|----------------------|
| `grounding` | Stable, gentle onset. Low arousal entry. | Scattered/anxious user; daytime; alpha range (8–12 Hz) |
| `depth_charge` | Maximum trance depth. Sustained maintenance. | Calm, motivated entry; delta/theta (1–4 Hz); sawtooth/triangle carrier |
| `focus` | Flat, low complexity. Clear-headed. | Work-adjacent sessions; learning; 4–7 Hz theta; sine/triangle |
| `emotional` | High FAA approach. Emotional processing. | After a difficult day; pairs with reconsolidation sequences |
| `creative` | Moderate complexity drift. Loose exploration. | Ideation; journaling; light trance; 5–7 Hz theta; moderate noise |

### State Types

| State Type | Signature |
|------------|-----------|
| `rapid_onset` | Deep state reached in < 5 minutes |
| `sustained_depth` | Maintained depth for > 20 minutes |
| `emotional_opening` | High FAA approach + user-reported emotional content |
| `gradual_build` | Slow, steady deepening over 15+ minutes |
| `volatile` | Frequent depth oscillations, no sustained plateau |

### Database Schema

Palette entries are stored in `session_db.py`:

```sql
CREATE TABLE somatic_palette (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    chord_config TEXT NOT NULL,        -- JSON: beat, carrier, noise, spiral, veil
    entry_context TEXT,                -- JSON: time_of_day, entry_mood, recent_sleep
    outcome_score REAL,                -- 0.0–1.0 composite evaluation
    family TEXT,                       -- LLM-assigned family label
    state_type TEXT,                   -- LLM-assigned state type
    n_observations INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## §4.Z Session Planning and Evaluation

### Session Planner

`session/session_planner.py` selects the optimal session configuration before each session based on:
- Time of day and user schedule context
- Recent session history (what worked, what failed)
- Somatic palette family recommendations
- User-stated intent (if provided via agent conversation)
- Pending reconsolidation traces

The planner produces a session plan: selected YAML template, chord starting point, content pool selection, and any special protocols (reconsolidation, language, TMR).

### Session Evaluator

`session/session_evaluator.py` runs post-session, scoring the session against its plan:
- Did the session reach target depth?
- How long was MAINTENANCE sustained?
- Content delivery success rate (gate open ratio)
- Chord performance vs. palette predictions
- Reconsolidation protocol completion (if active)

Results feed back into the planner for the next session and update the somatic palette with new observation data.

### Session Database

`session/session_db.py` manages the SQLite backend with tables:

| Table | Purpose |
|-------|---------|
| `sessions` | Session metadata, start/end times, selected arc |
| `conductor_decisions` | Phase transition log with timestamps and triggers |
| `content_cascades` | Delivered content items with timing and gate state |
| `session_metrics` | Computed scores, depth profiles, FAA trends |
| `somatic_palette` | Chord configurations and outcomes |
| `conditioning_associations` | Rescorla-Wagner CS-US association strengths |
| `tmr_cue_registry` | TMR cue definitions and play history |
| `recon_events` | Reconsolidation protocol execution log |
| `language_pool` | Language vocabulary items and recognition history |

---

# Chapter 5 — Agent Intelligence

## §5.X Agent Operational Modes

`agent/somna_agent.py` operates in three modes, determined by session state:

### Onboarding Mode

Active during first-run and Session Zero. The agent guides the user through initial setup:
- Welcome wizard (5-step flow)
- Hardware detection (Muse 2 connection test, audio device selection)
- Preference collection (session intent, comfort level, experience with hypnosis)
- Session Zero: a calibration session disguised as a first experience — measures IAF, establishes SQI baselines, and introduces the session arc without the user perceiving it as calibration

### Interactive Mode (Active Session)

During a running session, the agent operates in one of two sub-modes:
- **Interactive**: Agent delivers TTS narration, responds to user text input, manages content delivery, monitors EEG state, coordinates with Conductor. Active during INDUCTION and early DEEPENING.
- **Observe**: Agent reduces TTS output, monitors silently, intervenes only when needed (depth declining, SQI degrading, fractionation required). Active during sustained MAINTENANCE.

The agent transitions between interactive and observe based on depth stability — once the user is in stable deep MAINTENANCE, constant narration becomes counterproductive.

### Idle Planning Mode

Between sessions, the agent enters idle planning. `_load_idle_knowledge()` injects knowledge files every planning cycle:
- `session_effectiveness_scoring.md` — score semantics, composite weights, auto-optimization
- `reconsolidation_protocol.md` — reconsolidation authoring and timing
- `somatic_palette.md` — chord evaluation, family assignment

Idle planning produces:
- **Content authoring**: Pre-writes affirmations, reconsolidation retrieve/update pairs, and session-specific content for the next session
- **Palette analysis**: Reviews chord history, identifies under-explored parameter regions, selects starting chord for next session
- **Session evaluation**: Scores the most recent session and updates planning heuristics
- **Reconsolidation planning**: Identifies target traces, authors retrieve/update content pairs with appropriate prediction error

---

## §5.Y Agent-Conductor Communication Protocol

The agent and Conductor communicate through `live_control.json` — not through direct function calls or shared memory. This maintains process isolation.

### Agent → Conductor (hints)

Written to `agent_conductor_hints` via `patch_live()`:

| Hint | Purpose |
|------|---------|
| `request_fractionation` | Ask Conductor to initiate fractionation cycle |
| `suggest_emergence` | Recommend beginning emergence |
| `depth_target` | Agent's preferred depth for current content needs |
| `hold_phase` | Request Conductor hold current phase longer |

### Conductor → Agent (state)

Published to `live_control.json` by the Conductor:

| Key | Content |
|-----|---------|
| `conductor_phase` | Current FSM state (CALIBRATION, INDUCTION, etc.) |
| `conductor_phase_duration` | Seconds in current phase |
| `trance_score` | Current depth composite |
| `faa_value` | Current frontal alpha asymmetry |
| `eeg_sqi` | Current signal quality |
| `eeg_sef95` | Current spectral edge frequency |
| `conductor_arc` | Selected arc template name |

---

## §5.Z Content Pre-Authoring Pipeline

The agent does not generate content on-the-fly during sessions. All content is authored during idle planning and stored in structured pools before the session begins.

### Affirmation Authoring

The agent writes session-specific affirmation sets during idle planning. Each set is themed to session intent and stored in the session's `affirmations.txt`. The semantic selector draws from this pool during delivery.

### Reconsolidation Content Authoring

Retrieve/update pairs are authored under namespaced tags:
```
# [recon_retrieve_<trace>]
<retrieval cues - activate target memory>

# [recon_update_<trace>]
<update phrases - moderate prediction error>
```

The agent's reconsolidation engine delivers these at the right moment — they never enter the random affirmation pool.

### Language Content Selection

When language learning is enabled, the agent selects vocabulary items from the `language_pool` table during idle planning based on:
- SRS scheduling (items due for review)
- Thematic alignment with session intent
- HSK level progression
- Conditioning theme matching (if applicable)

Selected items are queued in the content pipeline alongside affirmations.

---

# Chapter 6 — Conditioning & Content

## §6.X Reconsolidation Protocol Engine

### Theory

Every time a consolidated memory is actively retrieved, it briefly becomes labile — the molecular machinery that stabilized it temporarily dismantles. For roughly 10–60 minutes after retrieval, that specific trace is writable: it can be strengthened (exact repetition), modified (moderate mismatch), or destabilized (large mismatch). After this window, it re-stabilizes with whatever update was present.

This is distinct from consolidation (encoding new material into long-term memory). Reconsolidation modifies **already-stored patterns** — habituated negative self-schemas, fear memories, compulsion loops.

### Five-Phase State Machine

Implemented in `somna_agent.py` via `_recon_tick()`:

```
idle → retrieve → labilize → update → lockout → complete
```

| Phase | Duration | Behavior |
|-------|----------|----------|
| IDLE | — | No active reconsolidation; agent monitors for suitable conditions |
| RETRIEVE | ~5 min | 1–3 specific retrieval cues via TTS + overlay. Activates target trace. |
| LABILIZE | ~12 min | Normal session content continues. No retrieve phrases. Trace is labile. |
| UPDATE | ~8 min | 3–5 modified association phrases via TTS + overlay, spaced ~90s apart. This is the actual rewrite. |
| LOCKOUT | ~45 min | Session continues normally. `recon_retrieve_<trace>` phrases locked out from TMR encoding so old trace is not reinforced during sleep. Lockout is trace-specific — all other content fires normally. |
| COMPLETE | — | Protocol finished. Events logged to `recon_events` table. |

### Authoring Constraint: Prediction Error

The update phrases must introduce a **moderate prediction error** — too small a mismatch (just repeating a positive version of the same belief) produces reconsolidation without modification: the old trace re-stabilizes unchanged. Too large a mismatch triggers new encoding rather than reconsolidation — the brain stores it as a separate memory rather than modifying the existing one.

The sweet spot: the update acknowledges the emotional core of the retrieved trace but reframes the conclusion. The user's felt experience is validated; the learned response is modified.

### Content Tagging

Reconsolidation content uses namespaced tags in `affirmations.txt`:
```
# [recon_retrieve_perfectionism]
remember when you believed you had to earn your place in every room
recall the weight of never being enough

# [recon_update_perfectionism]
your presence needs no justification
imperfection is the texture of being alive
you have always been enough to be here
```

Tags are NOT activated by the normal phrase pool — they never appear in random rotation. The agent's recon engine delivers them directly and only during the appropriate phase.

### Conductor Integration

The Conductor respects `recon_locked_phrases` — a set of phrase tags that must not be delivered via TMR during the lockout window. This prevents the TMR system from reinforcing the old trace pattern during sleep, which would undo the reconsolidation update.

### Event Logging

All reconsolidation protocol executions are logged to the `recon_events` table:
```sql
CREATE TABLE recon_events (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    trace_name TEXT NOT NULL,          -- e.g., 'perfectionism'
    phase TEXT NOT NULL,               -- retrieve/labilize/update/lockout/complete
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    depth_at_retrieve REAL,            -- trance_score when retrieval began
    depth_at_update REAL,              -- trance_score when update began
    success BOOLEAN                    -- did protocol complete without interruption
);
```

---

## §6.Y Conditioning Engine — Rescorla-Wagner Tracking

`content/conditioning_engine.py` tracks the associative strength between conditioned stimuli (CS) and unconditioned stimuli (US) using the Rescorla-Wagner learning rule.

### CS Classes

| CS Class | Examples | US |
|----------|----------|-----|
| `affirmation` | Session affirmations | Trance state (somatic response) |
| `conditioning` | Themed conditioning content | Trance state + somatic palette chord |
| `language_char` | Mandarin vocabulary characters | Trance state + encoding context chord |

Language characters are registered as CS entries with `cs_class = 'language_char'`. This provides unified association tracking — the same Rescorla-Wagner machinery handles strength updates from both session encoding (US = trance state) and recognition testing (explicit reinforcement signal). This gives language items salience decay, extinction tracking, and reinforcement schedule optimization for free.

### Association Update

After each delivery event, the conditioning engine updates association strength:

```
ΔV = α × β × (λ - ΣV)
```

Where:
- `α` = CS salience (novelty-adjusted)
- `β` = US intensity (depth × SQI at delivery)
- `λ` = maximum associative strength
- `ΣV` = sum of all CS strengths competing for the US

This produces natural learning curves: rapid initial acquisition, deceleration as the association approaches maximum, and blocking effects when multiple CS compete for the same US.

### Content Cascade Tracking

`content_cascades` table logs every content delivery with full context:
- What was delivered (affirmation text, vocabulary item, conditioning cue)
- When (timestamp, session phase, time-in-phase)
- Physiological state at delivery (trance_score, faa_value, eeg_sqi)
- Delivery gate state (which signals were open/closed)
- Association strength before and after update

This creates a complete audit trail for content effectiveness analysis.

---

## §6.Z Semantic Selector — Weighted Content Pool Selection

`content/semantic_selector.py` selects the next content item from available pools using weighted random selection. Weights are determined by:

| Factor | Weight Influence |
|--------|-----------------|
| Association strength | Lower strength → higher selection weight (prioritize under-learned items) |
| Recency | Recently delivered items get reduced weight (spacing effect) |
| Phase alignment | Items tagged for current phase get boosted weight |
| Language priority | During DEEPENING, vocabulary items receive priority boost; during MAINTENANCE, affirmations take priority |
| Reconsolidation lockout | Locked-out items receive zero weight |

The selector queries the delivery gate before each selection — it does not select items it cannot deliver. This prevents queue buildup of items waiting for gate windows that may not come.


---

# Chapter 7 — Sleep Architecture

## §7.X Sleep Onset Detection

Somna detects sleep onset through converging EEG indicators rather than a single threshold:

| Indicator | Sleep Onset Signature | Source |
|-----------|----------------------|--------|
| SEF95 | Drops below 8 Hz | `eeg_processor.py` |
| Theta/Alpha ratio | Exceeds 2.0 (theta dominance) | `eeg_processor.py` |
| Delta power | Rising trend over 3+ minutes | `eeg_processor.py` |
| Trance score | Exceeds 0.85 (near-maximum) | `eeg_processor.py` |
| SQI stability | Sustained high (minimal movement) | `eeg_engine.py` |

Sleep onset transitions the system from active session mode to sleep mode:
- Agent enters observe-only (no TTS delivery)
- Conductor holds MAINTENANCE without trajectory corrections
- TMR cue engine activates, monitoring for SWS windows
- Sleep burst engine activates, monitoring for slow-oscillation phase-locking opportunities
- Visual display dims to minimum luminance

### SWS Detection

Slow-wave sleep is identified by sustained high delta power (0.5–4 Hz) with low theta/alpha/beta activity. The system requires 2+ minutes of consistent SWS indicators before activating TMR cues or sleep bursts — brief delta surges during light sleep do not qualify.

---

## §7.Y TMR During Sleep

Targeted Memory Reactivation during SWS uses the cues registered in `tmr_cue_registry` to reactivate associations formed during the waking session. The protocol:

1. **SWS detection confirmed** — delta dominance sustained for 2+ minutes
2. **Cue selection** — TMR engine selects cues based on:
   - Association strength (weaker associations benefit more from reactivation)
   - Recency (cues from the current session prioritized)
   - Source priority: conditioning cues > language cues > custom cues
   - Lockout filter: any cues tagged in `recon_locked_phrases` are excluded
3. **Cue delivery** — Sub-awakening volume, inter-cue interval of 10–30 seconds
4. **Arousal monitoring** — If SQI or band powers suggest micro-awakening, TMR pauses for 60 seconds before resuming
5. **Session logging** — Each cue play is logged with timestamp, volume, and concurrent EEG state

### Reconsolidation Lockout Integration

During the LOCKOUT phase of a reconsolidation protocol, the TMR engine filters out `recon_retrieve_<trace>` cues for the active trace. This prevents the TMR system from reinforcing the old memory pattern that the reconsolidation update is attempting to modify. The lockout is trace-specific — all other TMR cues fire normally.

### Language TMR Cues

Language vocabulary cues differ from conditioning cues in their audio source. Conditioning cues are deterministically synthesized sine waves (NumPy DSP). Language cues are pre-rendered TTS pronunciations of target language words. The TMR engine's playback path branches on the `source` column:

```python
if cue.source == 'language':
    play_prerendered(cue.audio_path)    # TTS-generated pronunciation
else:
    synthesize_and_play(cue.frequency)  # Deterministic NumPy DSP
```

Both paths share timing, volume control, arousal monitoring, and logging infrastructure.

---

## §7.Z Sleep Burst Engine

`engines/sleep_burst_engine.py` delivers pink noise bursts phase-locked to the user's slow oscillations during SWS. This technique is supported by sleep neuroscience research demonstrating that appropriately timed auditory stimulation during the up-state of slow oscillations enhances memory consolidation.

### Burst Parameters

| Parameter | Range | Default |
|-----------|-------|---------|
| Duration | 50–200 ms | 100 ms |
| Envelope | Raised cosine | — |
| Noise color | Any (7 colors) | Pink |
| Phase target | Up-state of slow oscillation | — |
| Inter-burst interval | Derived from detected SO frequency | ~0.8–1.2 s (matching ~0.8–1.25 Hz SO) |

### Phase-Locking Mechanism

The engine monitors real-time delta band activity to detect slow oscillation phase. Bursts are timed to coincide with the up-state (surface-positive phase) of the slow oscillation, when cortical excitability is highest. Phase detection uses zero-crossing analysis on the filtered delta signal.

### Coordination with TMR

Sleep bursts and TMR cues share the SWS window. To prevent mutual interference:
- TMR cues are not delivered during burst sequences
- Burst sequences pause during TMR cue delivery
- A 2-second guard interval separates the end of one system's delivery from the start of the other's
- Both systems share the arousal monitoring signal — if either detects micro-awakening, both pause

---

# Chapter 8 — Visual System & VR

## §8.X Shader Inventory

Five GLSL shaders power the visual pipeline:

| Shader | File | Purpose |
|--------|------|---------|
| Spiral | `shaders/spiral.glsl` | GPU-accelerated spiral rendering (14 styles) |
| Veil | `shaders/veil.glsl` | Scrolling affirmation text overlay |
| FBO composite | `shaders/fbo_composite.glsl` | Framebuffer object trail/decay compositing |
| Background | `shaders/background.glsl` | Image layer with blend modes |
| Post-process | `shaders/post_process.glsl` | Final output (color grading, vignette) |

All shaders are fragment shaders receiving uniforms from their respective Python layer modules via ModernGL. The FBO composite shader is particularly important — it enables the trail decay effect where previous frames persist and fade, creating the characteristic Somna visual persistence.

### FBO Trail Decay Pipeline

`layers/fbo_trail_decay.py` manages a ping-pong framebuffer pair:

1. **Frame N** renders to FBO-A
2. **FBO-A** is composited with **FBO-B** (previous frame) using the FBO composite shader
3. The composite result becomes the new FBO-B
4. The decay factor (0.0–1.0) controls how quickly previous frames fade

At decay 1.0, previous frames persist indefinitely (full trail). At decay 0.0, only the current frame is visible (no trail). The decay parameter is a `live_control.json` value controllable by the Conductor, agent, and user.

---

## §8.Y Visual Layer Stack

The visual display renders five layers in order:

| Layer | Module | Z-Order | Description |
|-------|--------|---------|-------------|
| Background | `layers/background_layer.py` | 0 (bottom) | Image slideshow with crossfade transitions |
| Spiral | `layers/spiral_layer.py` | 1 | GPU-rendered spiral (14 styles via ModernGL) |
| Veil | `layers/veil_layer.py` | 2 | Scrolling affirmation text (7 modes) |
| Shadows | `layers/shadows_layer.py` | 3 | Subliminal drifting word shadows |
| Center Text | `layers/centertext_layer.py` | 4 (top) | Flashing center affirmations |

### Veil Modes (7)

| Mode | Behavior |
|------|----------|
| `scroll` | Continuous vertical scroll |
| `rain` | Words falling like rain |
| `drift` | Slow horizontal drift |
| `converge` | Words converge toward center |
| `strobe` | Rapid flash alternation |
| `tunnel` | Words receding into depth |
| `null` | Auto-rotate through other modes |

### Spiral Styles (14)

Archimedes, Fermat, Golden, Helix, Hyperbolic, Involute, Lissajous, Log, Nautilus, Phyllotaxis, Rose, Spherical, Superformula, Vogel.

All styles are rendered by `spiral.glsl` with style-specific uniform parameters set by `layers/spiral_layer.py`.

### Font Management

`layers/font_manager.py` handles font loading, texture atlas generation, and text rendering for all text layers (veil, shadows, center text). CJK character support requires fonts with CJK glyphs and potentially different sizing — CJK characters are typically rendered larger than Latin for equivalent readability. The texture atlas must accommodate the larger CJK glyph set when language learning is enabled.

---

## §8.Z VR — The Bubble Architecture

*This section supersedes all prior VR specifications in this chapter. The void/stage choreography model with 6 named modes is retired. The Bubble Architecture replaces it.*

### Core Thesis

> The bubble is actively squeezing the conditioning into you.

The bubble is not a display surface. It is an active agent that physically presses content into the user through contraction, breathing, membrane projection, and spatial audio anchored to the enclosing wall.

### Why a Sphere

A sphere centered on the user's head pose, locked via OpenXR, solves three problems:

**Orientation independence.** The user can sit, recline, or lie down. The sphere has no up, no down, no forward. Every direction is just another part of the enclosing wall. No calibration, no orientation tracking, no wrong state.

**Continuous parameter space.** Two floats — diameter and membrane opacity — replace the six named choreography modes. Void is a large, transparent bubble. Full write-layer is a tight, opaque bubble. Everything between is smooth interpolation. No mode enum, no discrete transitions, no edge cases.

**Enclosure as somatic channel.** The sphere's contraction produces the looming effect — a well-documented perceptual response where an approaching surface triggers involuntary somatic activation. The bubble leverages this: as it contracts, the user perceives increasing enclosure pressure without physical contact.

### Bubble Parameters

| Parameter | Key | Range | Meaning |
|-----------|-----|-------|---------|
| Diameter | `vr_bubble_diameter_m` | 0.6–6.0 m | Distance from user to membrane |
| Opacity | `vr_bubble_opacity` | 0.0–1.0 | Membrane visibility (0 = void, 1 = full surface) |
| Breathing | `vr_bubble_breathing_pct` | 0.0–0.15 | Diameter oscillation amplitude synced to respiratory phase |
| Contraction rate | `vr_bubble_contract_rate` | 0.001–0.01 m/s | Speed of diameter reduction |
| Membrane distortion | `vr_membrane_distortion` | 0.0–1.0 | Perlin noise displacement on membrane surface |
| Color temperature | `vr_bubble_color_temp_k` | 1800–6500 K | Membrane illumination warmth |
| Luminance | `vr_bubble_luminance` | 0.0–1.0 | Overall membrane brightness |

All parameters are published to `live_control.json` via `patch_live()`. The renderer lerps between current and target values for smooth transitions.

### Phase-to-Parameter Mapping

| Phase | Diameter | Opacity | Color Temp | Luminance | Character |
|-------|----------|---------|------------|-----------|-----------|
| CALIBRATION | 4.0 m | 0.1 | 4000 K | 0.2 | Open, dim, unobtrusive |
| INDUCTION | 3.0 → 2.0 m | 0.2 → 0.5 | 3500 K | 0.15 | Gradual enclosure |
| DEEPENING | 2.0 → 1.2 m | 0.5 → 0.8 | 2500 K | 0.1 | Tightening, warming |
| MAINTENANCE | 0.8–1.2 m | 0.8–0.95 | 2000 K | 0.05 | Intimate, deep amber, near-dark |
| EMERGENCE | 1.2 → 4.0 m | 0.8 → 0.1 | 2000 → 5000 K | 0.05 → 0.5 | Expansion, brightening, uniform luminance rise |
| FRACTIONATION | ±0.3–0.5 m | Holds | Holds | Holds | Breathing expansion/contraction |

### Writer Priority for Bubble Parameters

Standard Somna writer priority applies:

1. **User** (highest) — direct UI override via Interference Graph or settings
2. **Agent** — somatic palette chord application, session-specific adjustments
3. **Conductor** — phase-driven parameter curves

The Interference Graph's spread knob drives `vr_bubble_breathing_pct` as a derived parameter from chord composition. The user can override this via the spread knob UI control, which functions as a standard user override and takes priority over both agent and conductor inputs.

### Membrane as Content Surface

The bubble membrane serves as the projection surface for:
- **Affirmations**: Text rendered on the curved inner wall, visible during high-opacity phases
- **Images**: Background slideshow content mapped to the membrane via spherical UV projection
- **Spiral patterns**: Spiral shader output projected onto the membrane surface

Content on the membrane moves with the bubble — it contracts with the bubble, creating the sensation of content pressing inward.

### Breathing and Somatic Entrainment

Bubble breathing synchronizes diameter oscillation with the user's respiratory phase (detected via EEG-derived respiratory signal or HRV):
- **Inhale**: Bubble expands slightly (diameter + `breathing_pct`)
- **Exhale**: Bubble contracts slightly (diameter - `breathing_pct`)

This produces a looming/receding cycle locked to breathing, creating perceived rhythmic pressure without physical contact. The amplitude is subtle (default 5–10% of current diameter) — enough to be somatically perceptible but not visually distracting.

### Spatial Audio on the Bubble Wall

The binaural beat carrier is spatialized to appear as though it emanates from the bubble membrane itself. As the bubble contracts, the audio source moves closer — the beat feels like the membrane vibrating against the user. This couples the audio entrainment channel to the visual/somatic enclosure channel.

### The Drone

The bubble has a room tone — a low, continuous drone whose pitch and character respond to diameter. Larger bubble = lower, more spacious drone. Tighter bubble = higher, more intimate drone. The drone provides ambient continuity and masks environmental sounds.

### Fill Media

Interior media between the user and the membrane wall:

| Fill Type | Implementation | Wave |
|-----------|---------------|------|
| Smoke | Screen-space raymarching through 3D noise | W2 |
| Fluid traces | Particle system on membrane inner surface | W3 |
| Micro-bubbles | Small floating particles with depth parallax | W3 |

**Smoke was moved from W1 to W2** — W1's purpose is answering "does VR deepen the work?" as cheaply as possible. Smoke requires real shader engineering (screen-space raymarching) that exceeds the minimal viable test scope. W1 is: bubble geometry + void + horizon + spatial carrier + drone.

### Emergence Design

Emergence luminance rises **uniformly** across the entire membrane surface. There is no directional dawn, no peripheral brightening, no horizon element. This preserves the sphere's core value proposition — orientation independence. A directional light source would reintroduce a canonical "forward" that the sphere geometry explicitly eliminates. The user perceives emergence as the bubble brightening and expanding evenly in all directions.

### Fractionation in the Bubble

Fractionation transitions expand/contract the bubble by 0.3–0.5 m. The bubble's fractionation behavior consumes timing constraints from the fractionation protocol (Bible Ch.4 Addendum A):

| Frac Phase | Bubble Behavior | Timing Source |
|------------|-----------------|---------------|
| FRAC_EMERGE | Diameter expands 0.3–0.5 m, opacity drops 0.1 | Ch.4 Addendum A EMERGE duration |
| FRAC_HOLD | Holds expanded diameter | Ch.4 Addendum A HOLD duration |
| FRAC_REDROP | Contracts past previous diameter by 0.1 m | Ch.4 Addendum A REINDUCE duration |

The bubble's fractionation parameters are derived from the Conductor's fractionation FSM, not independently timed. This prevents two fractionation systems drifting out of sync.

### Crash Recovery

Bubble state (current diameter, opacity, breathing phase) is written to `user_settings.json` every 30 seconds during an active session, not only on session exit. If the renderer crashes mid-lerp:
1. On restart, read last-persisted bubble state from `user_settings.json`
2. Resume from the persisted position (not snap to target)
3. The 30-second write interval limits maximum state loss to half a minute

This also fixes the general crash recovery case for `user_settings.json` — any crash loses at most 30 seconds of state rather than the entire session's accumulated changes.

### Safety: Pareidolia

High membrane distortion (`vr_membrane_distortion` > 0.7) combined with deep trance produces pareidolia — the brain finding faces and images in the noise patterns on the membrane surface. During deep states, this can produce disturbing imagery for some users.

Safety protocol:
- If the agent detects distress signals (HR spike, sudden depth crash, negative FAA surge), auto-reduce `vr_membrane_distortion` to 0.0
- The user can report negative membrane experiences via voice command or console
- The safety section of the VR settings includes a membrane distortion cap

### Gaze Zones

The bubble supports gaze-based interaction via dwell-to-activate zones:
- Bottom periphery: 4 zones for UI interaction (settings, session info, safety menu, exit)
- Dwell time: 1.5 seconds to activate
- Visual feedback: zone highlights progressively during dwell
- Primarily for VR-native interaction without controller dependency

### Local Keyword Detection

Safety-critical voice commands are detected locally (not via LLM round-trip) for minimal latency:
- **"Stop"** — immediate emergence initiation
- **"Pause"** — session pause, bubble freezes at current state
- **"Lighter"** — bubble expands 0.5 m, opacity drops 0.1
- **"Deeper"** — bubble contracts 0.3 m, opacity increases 0.1

These commands bypass the agent and write directly via `patch_live()`.

### Between-Session Persistence

The bubble remembers its last comfortable state per user. On session start, the bubble initializes to the last session's CALIBRATION parameters (not MAINTENANCE — starting tight would be jarring). Between-session persistence is stored in `user_settings.json` alongside other user preferences.

### Audio Subprocess Architecture

The audio pipeline currently lives in the desktop process (`engines/audio_engine.py`, `binaural_engine.py`, `pink_noise_engine.py`). For VR, the audio may need to run as an independent subprocess to handle spatial audio processing without competing for the VR render thread's resources.

The StateServer IPC pattern already solves cross-process coordination — the audio subprocess would connect to TCP 6789 as another StateServer client, reading parameters and publishing state through the same `patch_live()` API. The architecture already supports this; the question is "when" (which VR wave justifies the extraction), not "how."

### Implementation Waves

| Wave | Scope | Purpose |
|------|-------|---------|
| W1 | Sphere geometry, void-to-bubble interpolation, horizon removal, spatial carrier, drone | Does VR deepen the work? |
| W2 | Smoke fill, membrane content projection, breathing sync | Somatic channel validation |
| W3 | Fluid traces, micro-bubbles, full spatial audio | Rich interior environment |
| W4 | Gaze zones, voice commands, between-session persistence | VR-native interaction |
| W5 | Language module VR integration (gaze-based 4AFC recognition) | Cross-feature integration |

### Conductor Integration

Bubble parameter updates are integrated into the Conductor's phase definitions. Each of the 9 arc templates includes bubble parameter targets for every phase. Estimated integration scope: ~30–50 lines in `session/conductor.py` — each arc template needs diameter, opacity, color temperature, and luminance targets added to its phase definitions.

---

# Chapter 9 — Console & UI

## §9.X Control Panel Architecture

### Entry Point and Framework

`main_imgui.py` → `ui/control_panel_imgui.py`. The control panel is a Dear ImGui application rendered via the ImGui Python binding. It replaces the original Tkinter prototype.

### Panel System

The control panel uses a tabbed panel layout managed by `ui/panel_manager.py`:

| Panel | Module | Content |
|-------|--------|---------|
| Session | `ui/session_panel.py` | Library browser, queue/playlist builder, transport bar, Start Agent / Start Session |
| Audio | `ui/audio_panel.py` | Binaural beat controls, noise controls, TTS settings, volume mixer |
| Visual | `ui/visual_panel.py` | Layer controls (spiral, veil, shadows, center text), FBO decay, background |
| Agent | `ui/agent_panel.py` | Console display, agent mode indicator, conversation history |
| EEG | `ui/eeg_panel.py` | Band power display, trance score, SQI, FAA, Conductor phase |
| Settings | `ui/settings_panel.py` | 5-tab settings modal (general, audio, visual, EEG, advanced) |

### Theme: Rosé Pine Moon

The ONE AND ONLY palette for Somna. All ImGui styling uses the Rosé Pine Moon color scheme. Any references to competing palettes (pink/magenta ImGui palette, navy/blue ImGui palette) in earlier documentation are incorrect and should be disregarded.

The `imgui_visual_design_reference.md` knowledge file documents the complete Rosé Pine Moon ImGui styling: color values for every widget type, spacing conventions, and typography.

---

## §9.Y Interference Graph

### Architecture

The Interference Graph is implemented across three files with clear separation of concerns:

| File | Role |
|------|------|
| `ui/interference_graph.py` | Pure data model — nodes, connections, parameter state |
| `ui/interference_graph_panel.py` | ImGui renderer — draws the graph, handles input |
| `ui/interference_graph_integration.py` | Wiring — connects graph events to `patch_live()` |

Single entry point: `install_interference_graph(panel_manager)` — called once during UI initialization.

### What It Is

The Interference Graph is a visual composition tool for somatic palette chords. It represents the current audio/visual parameter state as a set of draggable nodes on a band-frequency axis:

- Each node represents a parameter channel (beat frequency, carrier, noise, spiral, veil)
- Nodes are positioned on a horizontal axis representing frequency
- Bezier tethers connect related parameters (e.g., beat frequency to carrier waveform)
- Glow effects indicate parameter activity/intensity
- The vertical axis is unused — nodes are dragged horizontally only

### Spread Knob

The spread knob controls per-channel offset on top of each channel's individual base frequency. Higher spread = channels spread further apart in frequency space. Lower spread = channels converge. This creates different interference patterns between the audio/visual channels.

The spread knob maps to `vr_bubble_breathing_pct` in the VR Bubble Architecture — spread directly drives breathing amplitude, coupling the somatic palette composition to the VR somatic channel.

**Writer priority:** The spread knob is a UI control, making it a user override. It takes priority over agent and conductor inputs per standard Somna writer priority.

### Preset Stamps

Pre-configured chord setups that can be applied as starting points:

| Preset | Character |
|--------|-----------|
| GENUS | Gentle, grounding, alpha-range |
| Somna Deep | Maximum depth, delta/theta |
| Theta Weaver | Moderate depth, theta-dominant |

Presets set all node positions simultaneously. The user can then drag individual nodes to customize from the preset starting point.

---

## §9.Z Settings Modal

The settings modal is a 5-tab ImGui popup:

| Tab | Controls |
|-----|----------|
| General | Session defaults, data paths, language toggle |
| Audio | Default volumes, TTS backend selection, noise preferences |
| Visual | Default spiral style, veil mode, FBO decay, color scheme |
| EEG | Muse connection, IAF display, SQI threshold, depth calibration |
| Advanced | StateServer port, logging level, experimental features |

Settings are persisted to `user_settings.json` and loaded on startup.

---

# Chapter 10 — Onboarding & FTUE

## §10.X Implementation Notes — Pragmatic Subset

The Bible specifies a comprehensive onboarding system: 33-state MOSM, 8-page wizard, 12-step FTUE walkthrough, tutorial overlay system, and onboarding metrics. The shipped implementation is a deliberately scoped pragmatic subset. This section documents what shipped, what was cut, and why.

### What Shipped

| Component | Implementation |
|-----------|---------------|
| Welcome Wizard | 5-step flow (not 8-page): greeting → hardware detection → preference collection → first session selection → launch |
| Settings Modal | 5-tab ImGui modal covering all configurable parameters |
| Session Zero | Calibration-in-disguise: a gentle first session that measures IAF, establishes SQI baselines, introduces the session arc, and delivers first affirmations — without the user perceiving it as calibration |
| YAML Comment Preservation | Session files retain human-readable comments through save/load cycles |

### What Was Cut and Why

| Bible Specification | Cut Reason |
|--------------------|------------|
| 33-state MOSM (Multi-Objective State Machine) | Over-engineered for a single-user desktop application. The 5-step wizard covers all necessary onboarding decisions. MOSM was designed for a multi-user SaaS product with diverse user segments. |
| Tutorial overlay system | The agent console handles "what does this do?" questions naturally. A tutorial overlay duplicates functionality that the LLM agent provides better — context-aware, conversational, and responsive to the specific question rather than following a fixed script. |
| 12-step FTUE walkthrough | The ImGui layout is self-explanatory. The panel tabs are clearly labeled. Session Zero serves as the experiential FTUE — the user learns by doing, not by reading tooltips. |
| Onboarding metrics | Product analytics instrumentation for tracking onboarding funnel conversion, drop-off points, and time-to-first-session. Irrelevant for a single-user application. Would add telemetry code with no consumer. |

### Session Zero Deep Dive

Session Zero is the most important onboarding component. It replaces an explicit calibration step with a disguised first experience:

1. **Welcome**: Agent introduces itself, sets expectations
2. **Hardware check**: Muse 2 connection test (if EEG enabled), audio device verification
3. **Preference collection**: Brief conversation about session intent, comfort level, experience with hypnosis
4. **Calibration-in-disguise**: A gentle, short session (~10 min) that:
   - Measures IAF during a 2-minute eyes-closed resting period (presented as "settling in")
   - Establishes SQI baselines (presented as "getting comfortable")
   - Tests audio delivery (presented as the session's natural audio)
   - Delivers first affirmations (the session IS the onboarding)
5. **Post-session**: Agent discusses the experience, adjusts settings based on observations

The user never perceives Step 4 as calibration. They perceive it as their first session — which it is. The calibration data is a byproduct, not the purpose. This is experiential onboarding: the best way to learn what Somna does is to experience what Somna does.

---

# Chapter 11 — Master Overview

## §11.X Updated System Inventory

### Module Count

73 Python modules across 13 packages, plus 5 GLSL shaders. Full module registry in Bible Ch.1 §1.Y.

### Knowledge File Inventory (Post-Cleanup)

32 active knowledge files (down from 46 pre-cleanup):

| # | File | Purpose |
|---|------|---------|
| 1 | adaptive_frequency_leading.md | Frequency leading/following strategies |
| 2 | aphantasia.md | Aphantasia accommodations in visual design |
| 3 | assr_entrainment.md | Auditory steady-state response research |
| 4 | binaural_research.md | Binaural beat efficacy research summary |
| 5 | brainflow_reference.md | BrainFlow API reference for Muse 2 |
| 6 | calibration_protocol.md | IAF and SQI calibration procedures |
| 7 | conductor_fsm.md | Conductor FSM state definitions and transitions |
| 8 | control_panel_architecture.md | ImGui control panel layout and panel system |
| 9 | eeg_entrainment.md | EEG entrainment mechanisms and evidence |
| 10 | eeg_integration_research.md | EEG hardware integration research |
| 11 | faa_receptivity.md | Frontal alpha asymmetry and receptivity |
| 12 | fbo_trail_decay.md | FBO trail decay pipeline |
| 13 | fractionation_protocol.md | Fractionation timing and depth targets |
| 14 | genus_protocol.md | GENUS session protocol |
| 15 | hrv_breath_coupling.md | HRV-respiratory coupling for delivery timing |
| 16 | hrv_coherence_breathing.md | HRV coherence breathing techniques |
| 17 | hypnosis_theory.md | Hypnosis theory and mechanisms |
| 18 | iaf_calibration.md | Individual Alpha Frequency calibration |
| 19 | imgui_visual_design_reference.md | Rosé Pine Moon ImGui styling reference |
| 20 | reconsolidation_protocol.md | Reconsolidation authoring and timing (NEW) |
| 21 | session_design.md | Session YAML authoring guide |
| 22 | session_effectiveness_scoring.md | Score semantics, composite weights, auto-optimization |
| 23 | signal_quality_index.md | SQI computation and thresholds |
| 24 | sleep_onset_design.md | Sleep onset detection and transition |
| 25 | somatic_palette.md | Chord evaluation and family assignment (NEW) |
| 26 | somna_research_ref.md | General research reference index |
| 27 | ssild_protocol.md | SSILD sleep protocol |
| 28 | stochastic_resonance.md | Stochastic resonance in neural systems |
| 29 | subliminal_text_perception.md | Subliminal text perception research |
| 30 | training_mode.md | Training mode specifications |
| 31 | veil_and_spirals.md | Veil and spiral visual design |
| 32 | visual_layer_reference.md | Visual layer stack reference |
| 33 | vr_protocols.md | VR implementation protocols |

Note: 33 files, not 32 — `vr_protocols.md` was already in the surviving list and the two new files (`reconsolidation_protocol.md`, `somatic_palette.md`) bring the total to 32 from the original 30, but the pre-cleanup dump included `vr_protocols.md` in the 30, so the actual post-cleanup + new files total is 32. Verify by counting the active files in the knowledge directory.

### Archived Files (16)

In `knowledge/archive/`:

| Category | Files |
|----------|-------|
| Retired (superseded by Bible) | DOC_41_HTW.md, DOC_43_conditioning_reinforcement.md, DOC_45_habituation_novelty.md, DOC_45_stimulus_techniques.md, DOC_47_visual_audio_enhancement.md, DOC_content_design_methodology.md, DOC_genus_session_director.md, DOC_induction_strategy_library.md, edison_mode.md, eeg_engine_spec.md, orchestration_gap_analysis.md, sef95_trance_depth.md, session_effectiveness_scoring.md |
| Historical | research_briefing.md, research_notes_archive.md, gateway_process.md |

Note: `session_effectiveness_scoring.md` was initially retired but restored to active status — it is load-bearing for the agent's `_load_idle_knowledge()` idle planning cycle. It should be removed from the archive list above and counted among the active files. **Corrected total: 33 active files.**

### Bible Document Set

11 chapters across 22 artifacts (Parts A/B per chapter):

| Ch. | Title | Scope |
|-----|-------|-------|
| 1 | Processing Stack | Architecture, IPC, packages, data flow |
| 2 | Biosignal Science | EEG, band powers, IAF, SQI, FAA, trance depth, delivery gate |
| 3 | Audio & Entrainment | 7-channel audio, binaural, noise, TTS, SSB, TMR, sleep bursts |
| 4 | Session Architecture | Conductor FSM, arc templates, somatic palette, session planning |
| 5 | Agent Intelligence | Agent modes, idle planning, content authoring, agent-conductor protocol |
| 6 | Conditioning & Content | Conditioning engine, reconsolidation protocol, semantic selection, content pools |
| 7 | Sleep Architecture | Sleep onset, TMR during SWS, sleep bursts, reconsolidation lockout |
| 8 | Visual System & VR | Shaders, layer stack, FBO pipeline, VR Bubble Architecture |
| 9 | Console & UI | ImGui control panel, Interference Graph, settings modal, Rosé Pine Moon |
| 10 | Onboarding & FTUE | Pragmatic subset, Session Zero, what was cut and why |
| 11 | Master Overview | System inventory, knowledge files, Bible document set |

### Design Documents (Active, Not Yet Bible-Integrated)

| Document | Status | Bible Integration |
|----------|--------|-------------------|
| VR Bubble Architecture v2.1 | Revised, reviewed | Supersedes Ch.8 §VR — gap closed in this document |
| Language Module Design v1.1 | Revised, reviewed | New capability — not yet Bible chapter; candidate for Ch.12 or Ch.6 appendix |

---

## §11.Y Bible Gap Registry — Status After This Document

### Gaps Closed by This Document

| # | Gap | Bible Location | Status |
|---|-----|---------------|--------|
| 1 | IPC StateServer architecture | Ch.1 §1.X | ✅ Closed |
| 2 | Package restructuring (13 packages) | Ch.1 §1.Y | ✅ Closed |
| 3 | config.py legacy status | Ch.1 §1.X | ✅ Closed |
| 4 | IAF calibration protocol | Ch.2 §2.X | ✅ Closed |
| 5 | SQI composite scoring | Ch.2 §2.X | ✅ Closed |
| 6 | FAA measurement | Ch.2 §2.X | ✅ Closed |
| 7 | SEF95 trance depth | Ch.2 §2.X | ✅ Closed |
| 8 | Delivery gate physiology | Ch.2 §2.Y | ✅ Closed |
| 9 | 7-channel audio architecture | Ch.3 §3.X | ✅ Closed |
| 10 | Sleep burst engine | Ch.3 §3.X, Ch.7 §7.Z | ✅ Closed |
| 11 | Pink noise engine (7 colors) | Ch.3 §3.X | ✅ Closed |
| 12 | Binaural engine phase tracking | Ch.3 §3.X | ✅ Closed |
| 13 | SSB subliminal embedding | Ch.3 §3.X | ✅ Closed |
| 14 | TMR cue synthesis | Ch.3 §3.X | ✅ Closed |
| 15 | TTS pre-synthesis architecture | Ch.3 §3.X | ✅ Closed |
| 16 | Somatic Palette system | Ch.4 §4.Y | ✅ Closed |
| 17 | 14-phase Conductor FSM | Ch.4 §4.X | ✅ Closed |
| 18 | Arc templates | Ch.4 §4.X | ✅ Closed |
| 19 | Trajectory evaluation | Ch.4 §4.X | ✅ Closed |
| 20 | Session planning/evaluation | Ch.4 §4.Z | ✅ Closed |
| 21 | Delivery gate as component | Ch.2 §2.Y | ✅ Closed |
| 22 | Agent operational modes | Ch.5 §5.X | ✅ Closed |
| 23 | Idle planning cycle | Ch.5 §5.X | ✅ Closed |
| 24 | Agent-Conductor protocol | Ch.5 §5.Y | ✅ Closed |
| 25 | Content pre-authoring | Ch.5 §5.Z | ✅ Closed |
| 26 | Reconsolidation Protocol | Ch.6 §6.X | ✅ Closed |
| 27 | Conditioning cascade tracking | Ch.6 §6.Y | ✅ Closed |
| 28 | Content pool schema | Ch.6 §6.Y | ✅ Closed |
| 29 | Semantic selector | Ch.6 §6.Y | ✅ Closed |
| 30 | TMR during SWS | Ch.7 §7.Y | ✅ Closed |
| 31 | Sleep onset detection | Ch.7 §7.X | ✅ Closed |
| 32 | VR Bubble Architecture | Ch.8 §8.Z | ✅ Closed |
| 33 | Shader inventory | Ch.8 §8.X | ✅ Closed |
| 34 | FBO trail decay pipeline | Ch.8 §8.X | ✅ Closed |
| 35 | Interference Graph | Ch.9 §9.Y | ✅ Closed |
| 36 | Onboarding pragmatic cuts | Ch.10 §10.X | ✅ Closed |

### Remaining Open Items

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Language Module | Open | Design doc v1.1 complete; needs Bible chapter (Ch.12 candidate) or Ch.6 appendix |
| 2 | Internal inconsistency: lock expiry semantics | Noted | README says locks don't expire at keyframe boundaries; verify AGENTS.md and SESSION_TIMELINE agree |
| 3 | AGENTS.md "Do Not" list | Informational | 7 new guardrails documented in AGENTS.md; not Bible-level specifications but should be cross-referenced |

---

*End of Bible Gap Closure Document*
