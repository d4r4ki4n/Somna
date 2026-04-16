# Somna — Research Reference
*Canonical project brief. Supersedes all previous research_ref and research_briefing documents. Last updated April 11, 2026. Aligned with the Full-Stack Audit (bible_audit_fullstack.md).*
*Read this before writing any spec, plan, or implementation doc for Somna.*

---

## What Somna Is

Somna is a **Neural Write Interface** — a closed-loop neurostimulation platform that reads the user's physiological state across five measurement axes and responds with coordinated audio, visual, haptic, electrical, and linguistic stimuli to guide consciousness along a target trajectory. The conversational agent is named **Vesper**. The session orchestrator is the **Conductor**.

Target demographic: the hypnokink and altered-states community — people who actively seek trance, surrender, and deep altered states as skill. Somna engineers for that experience without sanitizing it.

**Primary user constraint:** Extreme aphantasia — zero voluntary visualization. All prompts, affirmations, and session designs must be somatic/auditory only. No "imagine," "picture," "visualize," "see yourself," staircases, beaches, or guided imagery of any kind.

---

## Architecture

### Process Topology

```
main_imgui.py (active)  OR  main.py (legacy Tkinter, still functional)
  └── control_panel_imgui.py / control_panel_imgui.py
        ├── ipc/state_server.py     (started here — TCP 6789, single-writer)
        ├── engines/audio_engine.py (7-channel audio)
        ├── content/tts_engine.py   (TTS, channels 4-5)
        ├── agent/somna_agent.py    (LLM agent thread)
        ├── eeg/eeg_engine.py       (BrainFlow acquisition)
        ├── session/conductor.py    (EEG FSM)
        ├── session/timeline_runner.py (keyframe playback)
        └── visual_display_runner.py → visual_display.py (subprocess)
              └── vr/vr_display_runner.py (optional --vr subprocess)
```

### IPC: The Only Sanctioned Write Path

All inter-process writes go through the IPC StateServer. Direct JSON file writes are **retired and forbidden**.

```python
from ipc import patch_live
patch_live({"beat_frequency": 6.0})   # atomic, fire-and-forget
```

`live_control.json` is a **read-only snapshot** (~7 KB, ~150 keys). Consumers (visual_display.py, layers, EEG subsystem) read it via polling. The StateServer serializes all writes to prevent race conditions.

---

## Module & File Structure (73 modules — as-audited April 2026)

```
Somna/
  main_imgui.py              Active entry point (Dear ImGui panel)
  main.py                    Legacy Tkinter entry point
  control_panel_imgui.py     Dear ImGui application class (57 KB, experimental/parallel)
  control_panel_imgui.py           Production Tkinter panel (214 KB — largest module)
  visual_display.py          ModernGL rendering engine — 5-layer compositor (40 KB)
  visual_display_runner.py   Thread wrapper for visual_display
  config.py                  Path constants, default values, app-wide config
  gen_panel_config.py        Generates panel_config.json from control_panel layout (38 KB)
  live_control.json          Runtime IPC bus (read-only snapshot)
  agent_config.yaml          LLM + EEG config (model, base_url, eeg.*, fractionation params)
  panel_config.json          Data-driven widget definitions for ImGui panel
  binaural_presets.json      40 presets: delta–gamma + Monroe Focus + Stargate protocols
  user_profile.json          Persistent cross-session user state (see schema below)
  user_settings.json         Window geometry + TTS prefs
  panel_geometry.json        ImGui panel layout state
  somna.db                   SQLite WAL (~1 MB): sessions, conductor_decisions,
                             content_cascades, session_metrics
  affirmations.txt           Root fallback pool (5 tag groups: shadows/relax/focus/affirm/open)
  requirements.txt

  agent/                     3 modules
    somna_agent.py           Main agent loop, LLM interface, onboarding, imagery detection,
                             tool registry (17+ tools), idle planning, ghost nudge.
                             Imports and orchestrates SessionPlanner/Director/Evaluator.
                             4830 lines / 58 methods. (Bible Ch.5)
    content_agent.py         CLI content studio — interactive session + image authoring
    llm_driver.py            LLM control API: send(), read_state(), prompt_user(), etc.

  content/                   4 modules
    content_selector.py      Semantic content selection from pools, PND-score depth matching
    tts_engine.py            edge-tts + SSB subliminal layer, pre-synthesis queuing
    affirmation_manager.py   Tag-based affirmation selection (shadows/relax/focus/affirm/open)
    tmr_cue_manager.py       TMR deterministic NumPy DSP — zero audio files. 6 pools:
                             IDENTITY, RELEASE, POTENTIAL, SOMATIC, PURPOSE, TRANSITION

  content_pools/             9 JSON pools (shared schema — see Data section)
    calm_anchoring.json      alpha band
    depth_descent.json       theta band
    somatic_release.json     theta band
    grounding_texture.json   alpha band
    dissolution.json         theta band
    stillness_emptiness.json delta band
    somatic_anchoring.json   alpha band
    warmth_comfort.json      alpha band
    identity.json            theta band

  content_tools/             2 modules
    content_pool_editor.py   CRUD for content pool JSON files
    session_editor.py        YAML session authoring with undo, validation

  eeg/                       9 modules
    eeg_engine.py            BrainFlow integration, Muse 2/S, band powers, SQI, artifact rejection
    depth_estimator.py       Three-axis depth (spectral slope + temporal coherence + autonomic)
    sleep_stage_classifier.py  Sleep staging: WAKE/N1/N2/N3/REM
    spindle_detector.py      Sleep spindle detection for TMR timing
    slow_wave_enhancer.py    Closed-loop slow-wave acoustic stimulation (delta up-state)
    calibration.py           IAF calibration, baseline recording, microfeedback keys
    faa_analyzer.py          Frontal Alpha Asymmetry — receptivity/valence tracking
    assr_detector.py         Auditory Steady-State Response — entrainment verification
    ssvep_detector.py        SSVEP detection (VR-specific; binocular index, switch rate)

  engines/                   4 modules
    audio_engine.py          7-channel audio: binaural (0,1), noise (2), sleep burst (3),
                             TTS (4,5), TMR (6). Miniaudio backend
    gain_manifold.py         Crossmodal gain: depth_gain_scalar, SR inverted-U,
                             5 active channels + haptic/tavns stubs (Phase 3)
    delivery_gate.py         Phase-cascade gating — blocks delivery until EEG confirms readiness
    frequency_leader.py      FreqLeader background thread — meet-and-lead protocol

  ipc/                       2 modules
    __init__.py              Re-exports patch_live, write_live, StateServer, PORT
    state_server.py          Single-writer TCP daemon, port 6789

  layers/                    5 modules
    background_layer.py      Bottom layer, color/opacity, image slideshow
    veil_layer.py            7 modes: scroll/rain/drift/converge/strobe/tunnel/null (mirror REMOVED)
    spiral_layer.py          14 spiral styles, GLSL shader dispatch
    shadows_layer.py         Subliminal word overlay; flash timing 200 ms → 16 ms
    centertext_layer.py      Center affirmation text display

  presets/                   1 module
    preset_manager.py        Loads and applies binaural_presets.json at runtime

  session/                   10 modules
    conductor.py             FSM: calibration→induction→deepening→maintenance→emerge.
                             EEG-gated phase transitions, fractionation, conductor_hints schema.
                             2546 lines / 55 methods. (Bible Ch.4)
    timeline_runner.py       100 ms tick interpolation, keyframe processing, user lock enforcement
    session_planner.py       Pre-session planning: arc template selection, session param generation,
                             history analysis, depth targeting. 601 lines. (Bible Ch.5)
    session_director.py      Intra-session steering: intensity cycles, trajectory evaluation,
                             redirect chains, sleep fork, emergency emergence. 1366 lines. (Bible Ch.5)
    session_evaluator.py     Post-session 6-component scoring, user profile learning feedback.
                             352 lines. (Bible Ch.5)
    session_scorer.py        SessionScorer + SessionAnalyzer: trend analysis, best-config
                             recommendation per preset. 330 lines.
    induction_runner.py      8 aphantasia-first induction strategies with session-count gating,
                             StrategySelector with contraindication filtering. 1237 lines. (Bible Ch.5)
    tmr_cue_manager.py       TMR deterministic NumPy DSP — zero audio files. 6 pools:
                             IDENTITY, RELEASE, POTENTIAL, SOMATIC, PURPOSE, TRANSITION
    tmr_engine.py            TMR session scheduling, inverted-U replay timing, spindle sync
    session_editor.py        YAML session authoring with undo, validation

  session_logs/              JSONL exchange logs: <session>_<YYYYMMDD>.jsonl

  sessions/                  11 session folders
    ok/                      Minimal smoke-test session (5 min, no timeline)
    live/                    Freeform — agent drives everything, no timeline (24 hr cap)
    first_light/             FTUE session (17 min, stops at theta 7 Hz, never subliminal)
    default/                 General trance baseline
    sleep_default/           Sleep (8 hr, conductor handoff at 10 min, delta floor at 30 min)
    edison_default/          Hypnagogic creativity capture, whisper dream capture (30 min)
    focus_flow/              Beta drive 14→22→13 Hz (8 min)
    gateway_f10/             Monroe Focus 10, Hemi-Sync frequency map (45 min)
    genus_default/           GENUS 40 Hz gamma, isochronic (60 min)
    ssild_default/           SSILD lucid dreaming, WBTB protocol (25 min)
    hollow/                  Most complex — 14 phases, fractionation at 21 min,
                             flash timing 200 ms→16 ms, conditioning window (35 min)
    fractionation_30min/     Vogt fractionation training (30 min)

  shaders/                   5 GLSL fragment shaders
    spiral_base.frag         archimedes, log, fermat, golden, lituus
    spiral_organic.frag      reaction_diffusion, voronoi, coral, mycelium
    spiral_minimal.frag      dot_field, line_weave
    spiral_flow.frag         ink_drop, smoke
    spiral_sacred.frag       sri_yantra, metatron

  ui/                        5 modules (Tkinter helpers for legacy panel)
    section_helper.py        Section frame builder with RP styling
    slider_helper.py         Slider with gold user-lock indicator (#f6c177)
    combobox_helper.py       Styled dropdown
    session_creator_wizard.py  5-step session creation wizard
    console_widget.py        Agent console with scrollback, colored output
    [+ ImGui helpers: control_panel_manager.py, panel_theme.py, panel_widgets.py,
       session_player.py, viz_registry.py, console.py]

  vr/                        3 modules
    vr_display_runner.py     OpenXR per-eye headset rendering, dichoptic flicker
    vr_overlay.py            SteamVR desktop overlay (separate from headset)
    vr_safety.py             Paroxysmal event detection, session abort

  knowledge/                 30 active docs + 16 archived + 20 Bible chapters (just added)
    bible_ch1_*.md … bible_ch11b_*.md   Somna Bible — 20 artifacts, canonical design spec
    bible_audit_fullstack.md            Full-stack audit, April 11 2026
    bible_migration_package.md          Doc→Bible citation crosswalk
    [+ 30 active knowledge docs injected into agent context — see AGENTS.md for list]
    archive/                            16 superseded Doc-XX-era documents
```

---

## Data Structures

### Content Pool Schema (9 pools, all identical)
```json
{
  "pool_id": "string",
  "shadows_words": ["25 single words for subliminal flash"],
  "centertext_templates": ["10 template strings"],
  "tts_templates": ["5-6 TTS scripts"],
  "synonym_rings": {"word": ["synonyms"]},
  "pnd_scores": {"word": 0.0},
  "frequency_band": "theta|delta|alpha",
  "vocabulary": ["full word list"]
}
```

### User Profile Schema (user_profile.json)
```json
{
  "user_name": "string",
  "aphantasia": "none|minimal|moderate|vivid",
  "vviq_score": "floor",
  "iaf_hz": 7.0,
  "iaf_calibrated": "ISO date",
  "total_sessions": 6,
  "designations": ["high_responder", "theta_ready", "deep_theta_responder"],
  "modality_preference": ["somatic", "auditory", "conceptual", "spatial", "motor"],
  "metaphor_avoidances": ["weight"],
  "vr_paroxysmal_event": {"date": "ISO date", "details": "..."},
  "session_history": [...]
}
```

### Agent Config (agent_config.yaml) Key Values
- LLM: HauhauCS_Qwen3.5-35B-A3B (uncensored), local at localhost:8000 (OpenAI-compatible API)
- EEG: Muse 2 board_id=38, Muse S=39, synthetic=-1
- Image gen: FLUX, 8 steps, 1024×1024, narrative prose prompts required
- Fractionation: 3 cycles, 35 s ascent, 15 s hold, 25 s descent, 25 s pause

---

## `live_control.json` Key Reference (~150 keys)

See AGENTS.md for the full taxonomy. Key categories:

**Audio:** `beat_frequency`, `carrier_frequency`, `beat_type`, `volume`, `noise_color`, `noise_volume`, `audio_muted`, `beat_phase`, `breath_mod`, `breath_rate`, `breath_depth`, `voice_volume`, `subliminal_volume`

**Visual:** `spiral_style`, `spiral_opacity`, `spiral_speed_multiplier`, `spiral_count`, `spiral_chaos`, `spiral_thickness`, `spiral_tightness`, `veil_opacity`, `veil_mode`, `shadow_opacity`, `center_flash_on_time`, `center_flash_off_time`, `bg_mode`

**Session/Timeline:** `session_folder`, `session_time`, `session_duration`, `timeline_label`, `timeline_paused`, `timeline_locked_params`

**Agent:** `agent_message`, `user_response`, `agent_mode`, `agent_conductor_hints`, `session_suggestion`, `user_console_input`, `user_console_ts`, `agent_console_response`, `image_filter_override`

**EEG:** `eeg_connected`, `eeg_alpha/theta/beta/delta/gamma`, `eeg_trance_score`, `eeg_trance_score_v2`, `eeg_quality`, `eeg_sqi_composite`, `eeg_iaf_hz`, `eeg_assr_confidence`, `eeg_sef95`, `eeg_signal_lost`, `eeg_spectral_slope`, `conductor_phase`

**Biometrics:** `ppg_heart_rate`, `ppg_hrv_rmssd`, `ppg_breath_rate`, `ppg_breath_phase`, `imu_motion_rms`, `imu_motion_contaminated`, `imu_head_nod_detected`

**Sleep:** `sleep_stage`, `spindle_density`, `slow_wave_active`, `tmr_cue_active`, `htw_active`

**VR:** `vr_active`, `binocular_index`, `switch_rate_hz`, `ssvep_detected`, `ssvep_snr`, `vection_speed`

---

## Agent JSON Response Schema

```json
{
  "reasoning": "1-2 sentences",
  "next_prompt": "message or null",
  "next_affirmation": "3-7 word phrase or null",
  "adjustments": {"param": value},
  "transitions": {"param": seconds},
  "prompt_style": {"voice_mode": "tts|subliminal|both|silent", "needs_response": true},
  "action": "none | fractionate",
  "profile_updates": {"note": "...", "responsive_themes": [], "designations": []},
  "tool_call": {"tool": "tool_name", "args": {}}
}
```

`transitions` triggers RampEngine — 1 Hz interpolation to `adjustments` target over N seconds.

**Never use `response_format: json_object`** — local models wrap dict in list. Use `_extract_json()`.

**17 agent tools:** send, read_state, apply_preset, prompt_user, get_profile, update_profile, get_session_metrics, query_session_performance, find_images_by_theme, audit_affirmations, write_affirmations_batch, write_session_yaml, generate_image, image_pipeline_cycle, tag_stats, images_for_tag, read_session_log

---

## Session YAML Structure

```yaml
name: "Human-readable name"
description: "One paragraph for session library UI"
category: general  # general|focus|sleep|entrainment|genus|edison|ssild|custom
duration: 3600

defaults:
  carrier_frequency: 200.0
  volume: 78.0
  beat_type: binaural

timeline:
  - t: 0
    label: phase_name
    ease: linear    # linear|ease_in|ease_out|ease_in_out|instant
    params:
      beat_frequency: 10.0
      phrases: relax    # activates affirmations.txt [relax] tag group
```

The `phrases` param drives per-phase content pool selection (hybrid content model — see hollow session as the canonical example with 14 phases).

---

## EEG / BrainFlow Reference

| Board | board_id |
|-------|---------|
| SYNTHETIC (dev) | -1 |
| Muse 2 | **38** (NOT 22) |
| Muse S | 39 |

IAF thresholds: Bible canonical = 0.70 / 0.40. Code currently uses 0.65 / 0.35 — will sync after hardware validation.

PPG: `config_board("p50")` enables Muse 2 PPG. `p61` unverified — cardiac phase gating deferred.

---

## What's Not Yet Implemented (Deferred)

| Feature | Status |
|---------|--------|
| Cardiac phase gating (Bible Ch.2 §2.10) | Deferred — awaiting Reese literature validation |
| HRV as convergent depth axis | ppg_hrv_rmssd written to live state; not yet in depth estimator |
| imu_head_nod_detected → sleep classifier boost | Flag written; not yet read by classifier |
| Haptic channel (Lovense BLE) | Stub in gain_manifold.py — Phase 3 |
| taVNS channel (DG Labs Coyote) | Stub in gain_manifold.py — Phase 3 |
| VR eye tracking | Phase 3 — OpenXR XR_EXT_eye_gaze_interaction |
| SDF font rendering in VR subliminal | Phase 3 |

---

## Internal Inconsistencies (Known)

1. **User lock behavior:** SESSION_TIMELINE.md §9 says locks expire at next keyframe. AGENTS.md says locks are permanent within a session (cleared only on restart/seek/load). **AGENTS.md is canonical.**
2. **IAF thresholds:** Bible says 0.70/0.40, code uses 0.65/0.35. **Bible is canonical — will sync after hardware testing.**
3. **README.md:** Documents pre-IPC architecture (direct JSON writes). Now stale. `patch_live()` via `ipc` module is the sole sanctioned write path.

---

## Architectural Decisions — Do Not Violate

| Decision | Reason |
|----------|--------|
| `patch_live()` from `ipc` module only | StateServer prevents race conditions; direct writes are retired |
| No new IPC mechanisms | StateServer on TCP 6789 is the only sanctioned channel |
| `update_profile()` for user profile writes | Reloads before saving to prevent concurrent write races |
| All DB access through `session/session_db.py` | No raw `sqlite3` outside that module |
| No `response_format: json_object` | Local models wrap dict in list; use `_extract_json()` |
| No `veil_mode: "mirror"` | Removed from veil_layer.py; use scroll/rain/drift/converge/strobe/tunnel/null |
| No expiring user locks | Locks permanent within session; cleared on restart/seek/load only |
| No `threading.Lock()` in timeline_runner | Uses `threading.RLock()` (reentrant) |
| Image gen endpoint: `/sdapi/v1/txt2img` | KoboldCpp A1111-compatible; NOT `/api/extra/generate_picture` |
| Image gen prompts: narrative prose | FLUX requires prose, not keyword soup |
| No `affirmations_pool` in agent adjustments | Not in adjustable params; use `next_affirmation` for injection |
| No `print()` in production paths | Prefixed diagnostics only: `[Agent]`, `[Panel]`, `[EEG]` |
| No Hz numbers in user-facing text | Qualitative only: alpha = "light and open", theta = "deep and slow" |
| No guided imagery/visualization | Extreme aphantasia — zero voluntary visualization |
| No "try to go deeper" prompts | Recruits analytical monitoring; use fractionation instead |
| Entry point: `main_imgui.py` | `main.py` (Tkinter) still functional but not the active UI |

---

## Code Conventions

- **Colors:** `RP["key"]` (Rosé Pine Moon). Never hardcode hex in UI code.
- **Fonts:** `FONT_LABEL`, `FONT_SMALL`, `FONT_HEADER`, `FONT_TITLE`, `FONT_LAUNCH`.
- **Citations:** All `Doc XX` references replaced with Bible chapter citations (Bible Ch.N §N.N).
- **Python version:** Targets 3.13. Avoid `X | Y` union syntax and `dict[str, X]` in signatures (linter); use `Optional[X]` and `Dict[str, X]`.

---

## The Somna Bible (Canonical Design Specification)

22 documents, 11 chapters. All live in `knowledge/` as `bible_ch*.md`. When AGENTS.md and the Bible disagree on **design intent**, the Bible wins. When AGENTS.md specifies **implementation behavior** the Bible doesn't cover, AGENTS.md wins.

| File | Coverage |
|------|---------|
| bible_ch1_processing_stack.md | Layer model, config pipeline, IPC design |
| bible_ch2_biosignal_science.md | EEG/PPG/IMU, band powers, trance scoring, calibration |
| bible_ch3_audio_entrainment.md | Binaural/isochronic, breath mod, crossmodal gain, freq leading |
| bible_ch4_session_architecture.md | Timeline runner, Conductor FSM, fractionation, session lifecycle |
| bible_ch4_addendum_a_genus.md | GENUS 40 Hz gamma protocol (4 variants) |
| bible_ch5_agent_intelligence.md | Vesper agent, idle planning, nudge, tools, personality |
| bible_ch6a_conditioning_engine.md | Conditioning methodology, habituation |
| bible_ch6b_content_delivery.md | Affirmations, SSB, image pipeline, content pools |
| bible_ch7a_sleep_architecture.md | Sleep classification, spindle/SWE, TMR |
| bible_ch7b_dream_engineering.md | HTW, sleep training, continuous conditioning |
| bible_ch8a_visual_rendering.md | SSB compositor, spiral/veil rendering |
| bible_ch8b_vr_immersive.md | VR pipeline, Ganzfeld, photic driving, vection |
| bible_ch9a_console_ui.md | ImGui target architecture, widget taxonomy |
| bible_ch9b_telemetry_agent_ui.md | Telemetry dashboard, agent UI |
| bible_ch10a_onboarding.md | Session Zero, calibration flows |
| bible_ch10b_ftue.md | FTUE console walkthrough, onboarding state machine |
| bible_ch11a_system_identity.md | Architectural patterns, five-layer stack, data flows |
| bible_ch11b_schema_safety_roadmap.md | Unified schema, safety architecture, open questions, roadmap |
| bible_audit_fullstack.md | Full-stack audit — 73 modules audited vs Bible |
| bible_migration_package.md | Doc→Bible citation crosswalk table |