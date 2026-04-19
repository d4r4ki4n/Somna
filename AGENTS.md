\# Somna — Agent & AI Contributor Conventions

This file captures implementation details, coding conventions, and codebase patterns that an AI coding agent needs to work effectively in this repo. Read it before making changes.

\> \*\*The Somna Bible\*\* (11 chapters, 22 documents) is the canonical design specification. This file covers implementation — things the Bible deliberately does not specify. When this file and the Bible disagree on design intent, \*\*the Bible wins\*\*. When this file specifies implementation behavior the Bible doesn't cover, \*\*this file wins\*\*.

| Bible Chapter | Coverage |

|---|---|

| Ch.1 — Processing Stack | Layer model, config pipeline, live_control.json design rationale |

| Ch.2 — Biosignal Science | EEG/PPG/IMU architecture, band powers, trance scoring, calibration |

| Ch.3 — Audio and Entrainment | Binaural/isochronic synthesis, breath mod, crossmodal gain, freq leading |

| Ch.4 — Session Architecture | Timeline runner, Conductor FSM, fractionation, session lifecycle |

| Ch.5 — Agent Intelligence | Somna agent, idle planning, nudge system, tool calling, personality |

| Ch.6 — Conditioning and Content | Affirmations, SSB, image pipeline, habituation, training mode |

| Ch.7 — Sleep Architecture | Sleep classification, spindle/SWE, TMR, HTW, sleep training |

| Ch.8 — Visual and VR | SSB compositor, VR pipeline, Ganzfeld, photic driving, vection |

| Ch.9 — Console UI | ImGui target architecture, widget taxonomy, telemetry dashboard |

| Ch.10 — Onboarding and FTUE | Session Zero, calibration flows, progressive complexity |

| Ch.11 — Master Overview | Architectural patterns, unified schema, safety, roadmap |

\---

\## Project identity

The project is called \*\*Somna\*\*. The control panel entry point is \`main_imgui.py\` (Dear ImGui panel). The display window is spawned as a subprocess via \`visual_display_runner.py\`. All communication between processes flows through a single JSON file: \`live_control.json\`.

\---

\## File ownership

| File / folder | Owns |

|---------------|------|

| \`ipc/state_server.py\` | Single-writer daemon for \`live_control.json\`; started by \`control_panel_imgui.py\`; serialises all writes via loopback TCP port 6789 |

| \`ipc/state_client.py\` | Per-process client; exports \`patch_live(updates)\` and \`write_live(data)\`; auto-reconnects; fire-and-forget queue |

| \`ipc/\__init_\_.py\` | Re-exports \`patch_live\`, \`write_live\`, \`StateServer\`, \`PORT\` |

| \`control_panel_imgui.py\` | Dear ImGui control panel (\`ControlPanelImGui\`); session management; starts \`StateServer\` in \`__init__\`; reads state via \`ConfigManager.update()\` every frame; all live writes via \`patch_live()\`; launched via \`main_imgui.py\` |

| \`main_imgui.py\` | Entry point for the ImGui panel; \`python main_imgui.py\` to launch |

| \`ui/\__init_\_.py\` | \`ui\` package — Dear ImGui panel helper modules |

| \`ui/panel_theme.py\` | \`apply_somna_theme()\` + \`load_somna_fonts()\` + all \`COLORS\` token tables + badge color tables (Bible Ch.9) |

| \`ui/panel_widgets.py\` | Custom Dear ImGui drawing primitives: \`draw_badge\`, \`draw_gauge\`, \`draw_sparkline\`, \`draw_gate_indicator\`, \`draw_phase_ring\`, \`draw_alert_badge\`, \`draw_composite_gate_badge\`, \`draw_dot_indicator\`, \`draw_lock_icon\` |

| \`visual_display.py\` | Render loop; reads \`live_control.json\` every frame via \`config.py\` |

| \`session/timeline_runner.py\` | Session timeline playback; the authoritative writer of session-managed keys |

| \`somna_agent.py\` | Always-on LLM agent; active mode (interactive session ticks) + idle mode (planning, nudge, console); never overrides user-locked params |

| \`content_agent.py\` | CLI content studio; interactive LLM authoring of sessions, affirmations, images |

| \`engines/audio_engine.py\` | Binaural beat generation; reads \`live_control.json\` |

| \`engines/tts_engine.py\` | TTS pre-synthesis and playback; reads \`live_control.json\` |

| \`config.py\` | Thin watcher: \`os.stat()\` poll at 100 ms, full JSON read only on mtime/size change |

| \`llm_driver.py\` | Helper API for external agents: \`send()\`, \`read_state()\`, \`prompt_user()\` etc. |

| \`session/conductor.py\` | Session Conductor FSM (Bible Ch.4); instantiated per session by \`somna_agent.py\`; owns structural params when active |

| \`engines/freq_leader.py\` | Adaptive frequency leading (meet-and-lead); mirrors user's brainwave dominant frequency then leads it toward target; runs as background thread inside agent process |

| \`session/session_scorer.py\` | Session effectiveness scoring; triggered by \`control_panel_imgui.py\` when display stops; writes to \`somna.db\` \`session_metrics\` table |

| \`eeg/\` | EEG acquisition and signal processing package (\`from eeg.eeg_engine import EEGEngine\`) |

| \`eeg/eeg_engine.py\` | EEG acquisition via BrainFlow; SQI pipeline, band powers, ASSR, FAA, SEF95; background thread; writes EEG keys to \`live_control.json\`; hosts PhaseTracker, RespiratoryTracker, PACEstimator as always-on plugins |

| \`eeg/phase_tracker.py\` | \`PhaseTracker\`; endpoint-corrected Hilbert; real-time alpha/theta phase at ~10 Hz; writes \`alpha_phase\`, \`alpha_at_trough\`, \`alpha_phase_confidence\`, \`theta_phase\` (Bible Ch.2) |

| \`eeg/respiratory_tracker.py\` | \`RespiratoryTracker\`; synthetic breath phase from \`breath_rate\`; adaptive hot window per Conductor FSM phase; agent override support (Bible Ch.2) |

| \`eeg/pac_estimator.py\` | \`PACEstimator\`; Tort et al. MI for ISA-alpha / theta-gamma / alpha-gamma; \`cascade_integrity\` weighted mean at ~0.5 Hz (Bible Ch.2) |

| \`eeg/delivery_gate.py\` | \`DeliveryGate\`; AND gate for phase-gated affirmation delivery; three graceful degradation levels + motion-artifact block (\`imu_motion_contaminated\`); read by \`layers/center_text.py\` (Bible Ch.2) |

| \`eeg/calibration_manager.py\` | \`CalibrationManager\`; first-10-sessions calibration protocol; personal threshold lookups with population defaults fallback; gates Conductor transitions (Bible Ch.2) |

| \`eeg/depth_features.py\` | Spectral slope, interhemispheric coherence, beta envelope correlation, coherence depth indicator, three-axis \`enhanced_trance_score\`, \`convergent_check\` (Bible Ch.2) |

| \`eeg/sleep_classifier.py\` | Threshold decision-tree sleep stage classifier (WAKE/N1/N2/N3/REM); hysteresis; per-user threshold calibration (Bible Ch.7) |

| \`eeg/spindle_detector.py\` | Real-time 11–16 Hz spindle detection on AF7/AF8 via Butterworth + Hilbert; 30-s rolling density (Bible Ch.7) |

| \`eeg/slow_wave_enhancer.py\` | Phase-locked pink noise burst scheduler; ISI enforcement; SWA tracking relative to baseline (Bible Ch.7) |

| \`engines/crossmodal_gain.py\` | \`CrossmodalGainEngine\`; five-channel gain manifold; depth_gain_scalar from spectral slope; SR inverted-U coupling; carrier-noise protection; \`SLEEP_GAIN_PROFILES\` (sleep_approach/onset/maintain/sleep_training); \`gain_mode\` dispatch; \`SRCalibrationSweep\`; \`spectral_occupancy_check\` (Bible Ch.3, Ch.7) |

| \`session/tmr_cue_manager.py\` | \`CueManager\`; deterministic tonal cue generation from MD5 hash; \`POOL_SIGNATURES\` (six pools); \`pool_for_label()\` keyword mapper; LRU cache up to 64 entries; no audio files required (Bible Ch.7) |

| `session/tmr_engine.py` | `TMREngine` + `ConsolidationScheduler`; trance encoding hooks; NREM replay scheduling; inverted-U priority model; hourly budget; SWE lockout coordination; EEG-loss shutdown (Bible Ch.7) |

| `session/edison_mode.py` | `EdisonModeManager`; state-driven N1-interception protocol; 6-state machine (PREPARATION→SEED_DELIVERY→MONITORING→N1_HOLD→CAPTURE→CYCLE_COMPLETE); alpha/theta ratio fast-path; captures persisted to `edison_captures` DB table (Bible Ch.7 §29) |

| `content_tools/sleep_report.py` | `read_sleep_report(session_id)` — aggregates sleep_stage_log, tmr_cue_registry, tmr_replay_log, sleep_training_log into a planning report; returns recommended focus pool + under-reinforced phrases; callable as agent tool (Bible Ch.7) |

| \`eeg/ppg_engine.py\` | \`PPGEngine\`; reads Muse 2 ANCILLARY_PRESET (~64 Hz PPG IR); R-peak detection; IBI → heart rate + RMSSD; RSA spectral method → \`ppg_breath_rate\` + \`ppg_breath_phase\`; feeds \`RespiratoryTracker.update_ppg_phase()\` (Bible Ch.2) |

| \`eeg/imu_engine.py\` | \`IMUEngine\`; reads Muse 2 AUXILIARY_PRESET (~52 Hz accel); rolling RMS deviation from 1 g → \`imu_motion_contaminated\` + \`imu_stillness_index\`; Y-axis forward pitch → \`imu_head_nod_detected\` (Bible Ch.2) |

| \`vr/\` | VR headset rendering pipeline package (\`from vr.vr_freq_table import build_session_table\`) |

| \`vr/vr_display_runner.py\` | OpenXR headset subprocess; launched by control panel “Launch OpenXR” (Tk) or Essential / Advanced → OpenXR (ImGui); renders per-eye flicker/Ganzfeld; adds Somna root to \`sys.path\` at startup for package resolution |

| \`vr/vr_flicker_engine.py\` | \`DichopticFlickerEngine\`; per-eye luminance; modes: ganzfeld / photic_bilateral / dichoptic_rivalry / dichoptic_ssvep; smoothstep transitions; imports from \`vr.vr_safety\` |

| \`vr/vr_ssvep_detector.py\` | \`SSVEPDetector\`; EEGEngine plugin; Welch PSD + 1/f correction; SNR, intermodulation products, binocular index, switch rate; writes \`ssvep_\*\` keys |

| \`vr/vr_safety.py\` | \`SafetyEnforcer\`; non-overridable safety layer; danger zone depth cap; first-session ramp; paroxysmal EEG kill switch |

| \`vr/vr_freq_table.py\` | \`FrequencyAllocationTable\`; harmonic collision detection up to 3rd harmonic; \`build_session_table()\` called by Conductor at VR activation |

| \`vr/vr_ganzfeld.py\` | \`GanzfeldProtocol\`; three-phase onset ramp / equilibration / ganzflicker |

| \`vr/vr_vection.py\` | \`VectionRenderer\`; 3D particle tunnel optic flow; session-capped speed; cybersickness mitigations |

| \`vr/vr_subliminal.py\` | \`SubLiminalRenderer\`; per-eye SOA state machine; three stereoscopic depth planes; VAC mitigation; GLUT font with graceful fallback |

| \`ui/interference_graph.py\` | \`InterferenceGraph\` data model; channel nodes, tether detection, spread math, preset stamps (GENUS, Somna Deep, Theta Weaver, etc.); pure Python — no ImGui |

| \`ui/interference_graph_panel.py\` | \`InterferenceGraphPanel\`; ImGui canvas renderer for the Somatic Palette Mixer; draggable nodes, bezier tethers, glow effects, band axis, preset row, hardware-dimming |

| `ui/interference_graph_integration.py` | `install_interference_graph(panel_manager)`; single entry point that wires the graph into `ControlPanelManager` via `set_section_extra("SomaticPalette", ...)`; no panel_config.json edits required |

| `ui/biosignal_dashboard.py` | `BiosignalDashboard`; four-tab ImPlot telemetry window (EEG Overview, Alpha Detail, Cardiac, Respiratory); device status strip; 10-second rolling buffers at 10 Hz; reads `eeg_*` and `ppg_*` keys from `live_control.json`; registered as a hello_imgui `DockableWindow` in `control_panel_imgui.py` |

| `control_panel_imgui.py` (Settings modal) | 5-tab modal popup opened by gear icon (⚙) in console bar: Profile (name, aphantasia, modality pref, notes, goals), Agent (LLM endpoint/key/model + test connection), Display (always-on-top, click-through, opacity), Audio (TTS voice), Advanced (reset onboarding, recalibrate IAF). Absorbs the old Memory modal. Agent tab edits `agent_config.yaml` via line-level replacement to preserve YAML comments |

| `control_panel_imgui.py` (Welcome wizard) | 5-step first-run modal for new users: Welcome → Name + free-text goals → Hardware scan → LLM setup with test connection → Ready. Triggers when `engagement.onboarding_complete` is not set in `user_profile.json`. Writes profile + agent config on finish. Testable via Settings → Advanced → Reset Onboarding |

| `control_panel_imgui.py` (Session Zero modal) | Pre-first-session safety/consent ImGui modal. Photosensitive screening (checkbox + risk acceptance), SSB consent (opt-in), safety acknowledgment (mandatory). Triggers when `session_zero_status` absent from profile and session launch is attempted. Writes `session_zero_status: "complete_minimal"` + `safety_consent` dict to profile. If photosensitive risk accepted, writes `photic_driving_disabled: True` to `live_control.json` |

| \`engines/device_safety.py\` | \`DeviceSafetyEnforcer\`; shared non-overridable safety layer for BLE output devices; intensity ceilings, ramp rates, sleep-stage gating, emergency stop, unlock tiers |

| \`engines/haptic_engine.py\` | \`HapticEngine\`; Lovense BLE vibrotactile output; buttplug-py protocol; pattern generation (continuous/pulse/wave/ramp/fractionation/tmr_cue/conditioned_anchor); safety-capped output; comfort calibration; sleep gating; background thread |

| \`engines/tavns_engine.py\` | \`TavnsEngine\`; DG Labs Coyote BLE taVNS output; pydglab-v3 protocol; impedance monitoring; waveform types (sine/square/biphasic); mandatory pre-session impedance check; instant shutoff on contact loss; sleep disable; background thread |

\---

## Onboarding architecture (Bible Ch.10 — implementation decisions)

The Bible specifies a 33-state Master Onboarding State Machine, 8-page wizard, 12-step FTUE walkthrough, tutorial overlay system, and onboarding metrics. **The implemented design is a pragmatic subset** — agent-driven where possible, minimal new UI infrastructure.

### What shipped

**Static welcome wizard** (`control_panel_imgui.py` — `_render_welcome_wizard`). 5-step modal that runs without LLM:
1. Welcome — brand intro
2. Name + free-text goals (comma-separated, agent interprets)
3. Hardware scan (checks BrainFlow availability; skippable)
4. LLM setup — endpoint/key/model + test connection (skippable with deliberate "Skip for now")
5. Ready — summary with pointers

Sets `engagement.onboarding_complete: True` in `user_profile.json`. If LLM was configured, saves to `agent_config.yaml` via line-level replacement (preserves comments).

**Settings modal** (`control_panel_imgui.py` — `_render_settings_modal`). Gear icon (⚙) in console bar, replaces old "Memory" button. 5 tabs: Profile, Agent, Display, Audio, Advanced. Absorbs the old Memory modal content into the Profile tab.

### What didn't ship (intentionally)

- **33-state MOSM** — over-engineered for a single-user desktop app. Session count from `engagement.total_sessions` handles progressive unlocks implicitly.
- **Tutorial overlay system** — z-ordered ImGui windows with priority queues. Hundreds of lines of infrastructure for tooltips users click through once. The agent console handles "what does this do?" questions better.
- **FTUE walkthrough** — 12-step guided tour. ImGui panel layout is self-explanatory.
- **Widget tier gating** — `panel_config.json` already has Essential/Advanced/Debug layers. The Debug layer was accidentally lost in the ImGui overhaul and needs restoring separately.
- **Onboarding metrics** — funnel analytics, TTFST tracking, satisfaction surveys. Product analytics for a single user.
- **Wizard checkpoint/resume** — crash recovery for a 60-second flow. Just redo it.
- **Multi-profile support** — not needed.
- **Vesper onboarding personality** — scripted encouragement milestones. The agent adapts naturally.

### Session Zero — calibration-in-disguise (IMPLEMENTED)

Session Zero is the first real session — the user experiences a normal induction while the agent silently collects EEG baselines. There is no separate calibration step.

**Pre-session gate (ImGui modal)** — `control_panel_imgui.py`:
- `_render_session_zero_modal()` — one-time safety/consent popup triggered before first session launch
- Intercepted in `_launch_display()` and `_agent_launch_display` path via `_needs_session_zero()`
- Three sections: photosensitive screening (checkbox + risk acceptance), SSB consent (opt-in), safety acknowledgment (mandatory)
- On accept, writes `session_zero_status: "complete_minimal"` and `safety_consent` dict to `user_profile.json`
- If photosensitive risk accepted, writes `photic_driving_disabled: True` to `live_control.json`
- Re-checks profile on each launch; skips modal once `session_zero_status` is present

**Agent calibration-in-disguise** — `somna_agent.py`:
- `_startup_sequence()` detects no `eeg_baselines` in profile + EEG connected → activates `_sz_active`
- `_session_zero_tick()` runs during `_interactive_tick` instead of normal LLM probe
- Phase sequence (timed, invisible to user):
  - `orient` (0:00–1:00) — eyes open, relaxed, agent narrates settling in
  - `eyes_open` (1:00–2:00) — quiet, agent says "soft focus, just looking"
  - `eyes_closed` (2:00–3:00) — agent guides eyes closed, records alpha spike
  - `breathing` (3:00–4:30) — 6 BPM breath modulation enabled, records relaxation response
  - `complete` — `_finalize_session_zero()` writes baselines, normal session resumes
- Each phase collects EEG snapshots (delta/theta/alpha/beta/trance_score/sef95) from `live_control.json` every tick
- Output: `eeg_baselines` dict in profile with per-phase band powers, alpha reactivity ratio, relaxation response score, trance susceptibility classification
- Breathing phase enables `breath_mod_enabled` with `breath_rate_bpm: 6.0`; cleared on finalize

**What was cut** (intentionally):
- SessionZeroController sub-FSM — agent tracks phase with simple string state
- Dedicated session YAML — test drive IS the default session with agent-controlled params
- Full audio stimulus survey — deferred to Settings modal or agent observation over sessions
- Visual calibration — display detection is self-evident from whether it works
- NWI baseline — deferred to first real session's natural TTS delivery
- Hardware discovery — already handled by welcome wizard step 3
- Checkpoint/resume — redo the 5-minute flow if interrupted; no crash recovery needed
- Separate test drive phase — the entire first session IS the test drive

### YAML comment preservation

Both the Settings Agent tab and the Welcome wizard step 4 edit `agent_config.yaml` via **line-level string replacement**, not `yaml.dump()`. PyYAML's dump strips all comments and reformats the entire file. The replacement pattern matches `base_url:`, `api_key:`, `model:` at the start of a line and replaces the value while leaving everything else intact.

---

\## Communication bus: \`live_control.json\`

\`live_control.json\` is the single source of truth for all runtime state. \*\*Do not invent new inter-process communication mechanisms.\*\* If you need to pass data between any two components, put it in \`live_control.json\`.

\### Writer priority (highest wins)

\`\`\`

User slider drag > LLM agent > timeline_runner > config defaults

\`\`\`

When the user moves a slider, the touched param is added to \`timeline_locked_params\` and the timeline runner skips writing it on every tick until the session is restarted or seeked.

\### Key categories

\*\*Audio / visual params\*\* — plain keys like \`beat_frequency\`, \`veil_opacity\`, \`spiral_style\`. The timeline runner interpolates these between keyframes.

\*\*Session metadata (read-only from UI)\*\* — written only by \`timeline_runner.py\`:

\- \`session_time\` — current playback position in seconds

\- \`session_duration\` — total session length

\- \`session_name\`, \`session_folder\` — loaded session

\- \`timeline_label\` — current keyframe segment label

\- \`timeline_paused\` — bool

\- \`timeline_locked_params\` — list of param names the user has overridden

\- \`playlist_index\` — current position in the playlist

\*\*Commands\*\* — written by control panel or agent, consumed and cleared by \`timeline_runner.py\`:

\- \`\_timeline_cmd\` — \`"pause"\` / \`"resume"\` / \`"restart"\` / \`"load"\` / \`"seek"\` / \`"playlist_next"\` / \`"playlist_prev"\`

\- \`seek_time\` — float seconds, used with \`\_timeline_cmd: "seek"\`

\- \`session_folder\` — set before sending \`\_timeline_cmd: "load"\`

\*\*Agent display commands\*\* — written by \`somna_agent.py\`, consumed by \`control_panel_imgui.py\` in \`\_poll_session_state()\`:

\- \`\_agent_stop_display\` — bool; when \`True\`, \`control_panel_imgui.py\` calls \`\_stop_display()\` and clears the key. Used by \`\_nudge_advance()\` when a nudge session exceeds \`nudge_max_session_minutes\`. Never set by timeline_runner — this is an agent-to-panel command only.

\*\*Agent prompt/response loop\*\* — used between \`somna_agent.py\` and \`control_panel_imgui.py\`:

\- \`agent_message\` — \*\*unified channel\*\* written by \`SomnaAgent.\_say()\`; dict with keys:

\- \`text\` — the message string

\- \`ts\` — \`time.time()\` float; used by all consumers for dedup

\- \`needs_response\` — bool; if True, control panel opens input dialog

\- \`via\` — list of active channels: \`\["console", "overlay", "tts"\]\` (any subset)

\- \`style\` — dict with keys: \`colors\`, \`font\`, \`zoom_speed\`, \`intensity\`, \`voice_mode\`, \`needs_response\`

\- \`timeout_s\` — float or null; dialog countdown / overlay dwell

\- \`user_response\` — control panel writes answer here after user submits

\- \`response_timestamp\` — float, written alongside \`user_response\`

\*\*Flags\*\*:

\- \`audio_muted\` — bool; silences binaural beats + colored noise only. \*\*Does not affect TTS.\*\* \`TTSEngine\` ignores this flag — TTS is gated by \`tts_enabled\` and \`tts_subliminal\` instead.

\- \`bg_mode\` — \`null\` (image slideshow) or \`"none"\` (transparent background)

\- \`agent_mode\` — \`"interactive"\` or \`"observe"\`; overrides the agent's configured mode live

\- \`agent_conductor_hints\` — dict written by the agent at session start; read by the Conductor every tick. See Conductor section for schema.

\- \`eeg_signal_lost\` — bool; written \`True\` by \`eeg_engine.py\` when SQI confidence is \`"none"\`, \`False\` when signal recovers. Conductor also sets it in \`\_handle_sqi_failure()\`. Consumed by \`TMREngine.tick()\` and \`SlowWaveEnhancer.tick()\` as a hard safety gate.

\*\*TMR commands\*\* (Bible Ch.7):

\- \`tmr_cue_cmd\` — dict written by \`TMREngine\` (sleep replay) or \`Conductor.\_deliver_affirmation_with_tmr()\` (trance encoding). Keys: \`pool\` (str), \`content_hash\` (str), \`gain\` (float 0–1), \`ts\` (float). Audio engine reads this, generates the cue array via \`CueManager\`, and plays on channel 6 with 200 ms dedup window.

\- \`tmr_lockout_until\` — float POSIX timestamp; \`SlowWaveEnhancer.tick()\` skips if \`now < tmr_lockout_until\`. Written by \`TMREngine.tick()\` after each replay cue, \`TMREngine.eeg_loss_shutdown()\` (5-minute lockout), and \`Conductor.\_enter_sleep_training()\` (HTW duration + 60 s).

\*\*PPG / IMU sensor keys\*\* (Bible Ch.2) — written by \`ppg_engine.py\` and \`imu_engine.py\`; absent on synthetic board:

\- \`ppg_available\` — bool; True when PPG buffer is warm and producing valid R-peaks.

\- \`ppg_heart_rate\` — float BPM; instantaneous heart rate from last 16 s of IBIs.

\- \`ppg_hrv_rmssd\` — float ms; RMSSD over last 16 s IBIs. Rising value = deepening parasympathetic dominance. Usable as a fourth convergent depth axis alongside \`eeg_trance_score\`.

\- \`ppg_breath_rate\` — float Hz (cycles per second); RSA-derived respiratory rate. Replaces synthetic clock in \`RespiratoryTracker\` when available.

\- \`ppg_breath_phase\` — float 0.0–1.0; real-time respiratory phase driven by \`ppg_breath_rate\`. Consumed by \`RespiratoryTracker.update_ppg_phase()\`.

\- \`respiratory_mode\` — \`"synthetic"\` or \`"ppg"\`; written by \`RespiratoryTracker.state_dict()\` so the agent and Conductor know which source is active.

\- \`imu_motion_rms\` — float g; RMS deviation of accelerometer magnitude from 1 g over the last 1 s.

\- \`imu_stillness_index\` — float 0.0–1.0 (EMA-smoothed); 1.0 = perfectly still. Convergent depth confirmation signal.

\- \`imu_motion_contaminated\` — bool; True when \`imu_motion_rms\` > 0.04 g. \*\*Checked by \`DeliveryGate\` before firing any stimulus.\*\* Defaults to False when IMU is absent.

\- \`imu_head_nod_detected\` — bool; True when Y-axis (pitch) shows a sustained forward drop over 3 s. Behavioral marker of N1 sleep onset — supplements \`eeg_sleep_stage\` for sleep detection.

\*\*HTW / TTS pre-synthesis\*\* (Bible Ch.7):

\- \`tts_presynth_phrases\` — list\[str\]; written by \`Conductor.\_presynth_training_phrases()\` while still in \`SLEEP_MAINTAIN\`. The TTS worker synthesizes these phrases into \`\_presynth_ready\` using the \`tts_pool_style\` overrides. Cleared by \`\_exit_sleep_training()\`.

\- \`tts_use_presynth\` — bool; when \`True\`, \`TTSEngine.poll_ready()\` serves audio from \`\_presynth_ready\` instead of the normal \`\_ready\` buffer. Set by \`\_enter_sleep_training()\`, cleared by \`\_exit_sleep_training()\`.

\- \`tts_pool_style\` — dict; pitch/rate overrides passed to \`\_build_backend()\` during pool synthesis and pre-synthesis. Set to \`{"pitch": "-10Hz", "rate": "-30%"}\` during HTW. Cleared on exit.

\- \`agent_sleep_plan\` — dict; written by \`SomnaAgent.\_sleep_planning_tick()\` during \`SLEEP_MAINTAIN\`. Keys: \`focus_pool\` (str), \`phrases\` (list\[str\] up to 6), \`ts\` (float). Consumed by \`Conductor.\_select_training_phrases()\` for phrase selection. Cleared to \`{}\` when a sleep session ends.

\*\*Edison Mode keys\*\* (Bible Ch.7 §29) — written by \`session/edison_mode.py\` via Conductor:

\- \`edison_active\` — bool; \`True\` when an Edison Mode session is running.

\- \`edison_state\` — \`"PREPARATION"\` | \`"SEED_DELIVERY"\` | \`"MONITORING"\` | \`"N1_HOLD"\` | \`"CAPTURE"\` | \`"CYCLE_COMPLETE"\` | \`"SESSION_END"\`; current state machine position.

\- \`edison_seed_topic\` — str; the creative seed phrase for this session. Set from session YAML \`edison_seed_topic\` or agent-provided.

\- \`edison_cycle_count\` — int; number of completed capture cycles.

\- \`edison_n1_hold_seconds\` — float; configured N1 hold duration before wake cue (default 60).

\- \`edison_n1_entry_timestamp\` — float or null; POSIX timestamp when N1 was detected for the current cycle.

\- \`edison_user_ready\` — one-shot bool; written by UI "Ready" button during PREPARATION, consumed and cleared by EdisonModeManager.

\- \`edison_continue\` — one-shot bool; written by UI "Another cycle" button during CYCLE_COMPLETE, consumed and cleared.

\- \`edison_end_session\` — one-shot bool; written by UI "End session" button during CYCLE_COMPLETE, consumed and cleared.

\*\*Haptic / taVNS device keys\*\* (Bible Ch.1 §8, Ch.2 §12-13) — written by \`engines/haptic_engine.py\` and \`engines/tavns_engine.py\`:

\- \`haptic_connected\` — bool; \`True\` when Lovense BLE device is connected and responding.

\- \`haptic_device_name\` — str; discovered device name (e.g. "LVS-XXX").

\- \`haptic_motor_count\` — int; number of motors detected on the connected device.

\- \`haptic_intensity\` — float 0–100; user/agent-set target intensity. Gain-adjusted by \`crossmodal_gain.py\` when connected.

\- \`haptic_actual_intensity\` — float 0–100; safety-capped intensity currently being sent to the device. May differ from \`haptic_intensity\` due to unlock tier, comfort ceiling, sleep gating, or ramp rate limits.

\- \`haptic_frequency_hz\` — float; vibration frequency set by the Interference Graph node position or presets.

\- \`haptic_pattern\` — \`"continuous"\` | \`"pulse"\` | \`"wave"\` | \`"ramp"\` | \`"fractionation"\` | \`"tmr_cue"\` | \`"conditioned_anchor"\`; controls the vibration modulation pattern.

\- \`haptic_pattern_speed\` — float 0.1–10.0; pattern cycle speed multiplier.

\- \`haptic_safety_state\` — dict; full \`DeviceSafetyEnforcer.status_dict()\` output for debugging.

\- \`haptic_sleep_enabled_n1n2\` — bool; user preference to allow haptics during N1/N2 sleep for TMR cueing. N3/REM haptics are always disabled.

\- \`haptic_comfort_ceiling\` — float; per-user max intensity set during comfort calibration (sessions 5+).

\- \`tavns_connected\` — bool; \`True\` when DG Labs Coyote BLE device is connected.

\- \`tavns_device_name\` — str; device identifier.

\- \`tavns_intensity\` — float 0–100; user/agent-set target stimulation intensity. Gain-adjusted by \`crossmodal_gain.py\`.

\- \`tavns_current_ua\` — float; gain-adjusted current in microamps. Written by \`crossmodal_gain.py\` as the target for the engine.

\- \`tavns_actual_current_ua\` — float 0–500; safety-capped current currently being delivered.

\- \`tavns_impedance_ok\` — bool; \`True\` when electrode contact impedance is below 5 kOhm. Mandatory pre-session check — session cannot start stimulation if \`False\`.

\- \`tavns_impedance_ohm\` — float; last measured electrode impedance.

\- \`tavns_waveform\` — \`"sine"\` | \`"square"\` | \`"biphasic"\`; stimulation waveform type.

\- \`tavns_safety_state\` — dict; full safety enforcer status.

\- \`electrode_comfort_ceiling\` — float; per-user max intensity step set during electrode comfort calibration (sessions 7+).

\- \`hardware_channels_connected\` — list\[str\]; channel names currently connected. Contains \`"haptic"\` and/or \`"tavns"\` when devices are active. Read by \`crossmodal_gain.py\` to gate hardware channel gain computation, and by \`interference_graph.py\` to toggle node interactivity.

\*\*Background opacity\*\* — agent and user control:

\- \`bg_opacity\` — float 0–100; default 100. Controls background image alpha via a dedicated GL fragment shader (\`u_opacity\` uniform). At 0, the background draw is skipped entirely — identical to \`bg_mode = "none"\`. At 1–99, the image composites against the cleared (transparent) framebuffer with DWM glass active. Do \*\*not\*\* implement this via \`pygame.Surface.set_alpha()\` — that blends against a black fill, not transparency. The shader approach is the only correct implementation.

\*\*Colored noise\*\* — user-facing controls; audio engine reads on every chunk:

\- \`noise_color\` — \`"white"\` | \`"pink"\` | \`"brown"\` | \`"blue"\` | \`"violet"\` | \`"grey"\` | \`"off"\`. Set exclusively by the user via the control panel color buttons. \*\*Do not write this key from agent code.\*\*

\- \`noise_volume\` — float 0–100; default 30. Written by user slider; agent may also write it. Setting to 0 is the "off" state — no separate enable flag exists.

\- \`trail_decay\` — float 0.0–0.99; default 0.0. Trail persistence for spiral layer. 0=no trails; 0.85–0.98=active range. Agent modulates this as a trance depth cue (longer trails = deeper). Snap to 0 during fractionation drop.

\- \`sr_noise_level\` — float 0.0–2.0; default 0.0. Stochastic resonance noise amplitude for subliminal text alpha in overlay. 0=off; active sweet spot ~0.5–1.5 (individual-specific). Start conservative at 0.3–0.5. Too high degrades detection.

\*\*Beat type and breath modulation\*\* — audio engine parameters:

\- \`beat_type\` — \`"binaural"\` | \`"isochronic"\` | \`"both"\`; default \`"binaural"\`. Controls audio generation mode; agent and session YAML can set this.

\- \`breath_mod_enabled\` — bool; default \`false\`. When true, applies sinusoidal AM envelope to the binaural beat chunk at the breath rate.

\- \`breath_rate_bpm\` — float; default 6.0. Breathing rate in breaths per minute (4–12 BPM range).

\- \`breath_depth\` — float 0.0–1.0; default 0.5. Amplitude modulation depth; 1.0 = full silence on exhale, 0.0 = no modulation.

\*\*Audio duck / pattern interrupt\*\* — written by agent/timeline, consumed by \`audio_engine.py\`:

\- \`tts_duck_ms\` — int 0–200; default 0 (disabled). Duration of audio duck on channels 0–2 when TTS fires. 50–150 = active range. Hardcoded ceiling at 200 ms. Rate-limited to 1 duck per 30 seconds.

\- \`tts_duck_trigger\` — str null|\"next\"; one-shot command. Agent writes \`\"next\"\` to arm the duck; audio engine clears to null after the next TTS fire. Used to time ducks to specific phrases.

\*\*Fractionation state\*\* — written by \`timeline_runner.py\` fractionation state machine:

\- \`fractionation_active\` — bool; true while a fractionation cycle is running.

\- \`fractionation_phase\` — str; canonical phase names: \`"INDUCTION"\` / \`"HOLD"\` / \`"EMERGE"\` / \`"EMERGE_HOLD"\` / \`"REINDUCE"\` / \`"DEEP_N"\` (where N is cycle count). Old names \`ascending/holding/descending/pausing\` are removed — do not use them.

\- \`fractionation_count\` — int; number of completed fractionation cycles in the current session.

\*\*Frequency leader state\*\* — written by \`freq_leader.py\` background thread:

\- \`freq_lead_phase\` — str; \`"meet"\` | \`"lead"\` | \`"idle"\`. Current meet-and-lead phase.

\- \`freq_lead_current\` — float; current frequency being led toward the target.

\- \`freq_lead_steps\` — int; number of lead steps completed.

\- \`freq_lead_holds\` — int; number of hold periods completed.

\*\*Conductor FSM state\*\* — written by \`Conductor.tick()\` on every tick, merged into the same \`\patch_live()\` call as parameter updates (one file write, not two):

\- \`conductor_state\` — dict; always present when a Conductor is active. Keys: \`phase\` (str), \`timer_mode\` (bool), \`iaf_hz\` (float|null), \`target_freq_hz\` (float|null), \`trance_score\` (float|null), \`assr_strength\` (float|null), \`assr_conf\` (str|null), \`sqi\` (str), \`frac_count\` (int), \`frac_max\` (int), \`ts\` (float). Read by the control panel for display and by the agent's \`\_state_summary()\` as context for the LLM. Do not write this key from agent code — it is owned exclusively by the Conductor.

\*\*FAA calibration handoff\*\* — one-shot flag:

\- \`eeg_faa_baseline_ready\` — bool; set \`true\` by \`eeg_engine.py\` when the resting FAA baseline is ready to be persisted. \`control_panel_imgui.py\` reads it in \`\_poll_eeg_status\`, saves to \`user_profile.json\`, and clears the flag.

\*\*Agent console\*\* — bidirectional text channel between control panel and agent:

\- \`user_console_input\` — str; written by control panel Send button; agent clears it after handling.

\- \`user_console_ts\` — float timestamp written alongside \`user_console_input\`; agent uses this to detect new messages.

\*\*Agent gradual transitions\*\* — written by \`RampEngine\` background thread in \`somna_agent.py\`:

\- \`transitions\` — dict in LLM JSON response; maps param name to ramp duration in seconds: \`{"beat_frequency": 90, "veil_opacity": 30}\`. RampEngine interpolates at 1 Hz and writes intermediate values to \`live_control.json\`. An entry in \`adjustments\` with a matching \`transitions\` key means "ramp to this value over N seconds".

\*\*Beat phase\*\* — written by \`BinauralAudioEngine\` background thread:

\- \`beat_phase\` — float 0.0–1.0; position in the current beat cycle, updated every ~100ms. Written by \`audio_engine.py\`. Read by visual layers (\`spirals_opengl.py\`, \`veil.py\`) to phase-lock animation to the audio waveform. Do not write this key from agent or session code.

\*\*Display lifecycle\*\* — written by \`visual_display.py\`:

\- \`display_active\` — bool; \`True\` when the display render loop is running, \`False\` after it exits. Written via a minimal \`\patch_live()\` helper inside \`visual_display.py\`. Consumed by \`somna_agent.py\` to detect session start/end edges (post-session summary trigger, staleness detection) and by \`\_poll_audio()\` in \`control_panel_imgui.py\` to gate TTS affirmation playback to active sessions.

\- \`tts_playing\` — str or null; phrase currently being spoken by \`TTSEngine\`. Written by \`control_panel_imgui.py\` \`\_poll_audio()\` when a phrase is popped and sent to the channel. Read by \`CenterTextLayer\` in the display for phrase-sync text display (replaces the old \`poll_ready()\` call from the render loop).

\---
---

\## User lock system

When the user moves a slider, \`\_update()\` in \`control_panel_imgui.py\` writes only the changed key(s) to \`live_control.json\` and timestamps \`\_last_user_interaction\`. The \`timeline_runner.py\` detects the change via \`\_detect_user_locks()\` — if a param's current live value differs from what the runner last wrote, it adds that param to \`\_user_locks\`. On each tick, \`\_user_locks\` params are stripped from the values dict before writing.

\*\*Locks are permanent within a session\*\* — they do not expire tick-by-tick. They are cleared on \`restart\`, \`seek\`, or \`load\` commands.

\*\*\`noise_volume\` and \`noise_color\` are lock-eligible\*\* — \`noise_volume\` is in \`INTERPOLATABLE\` and \`noise_color\` is in \`INSTANT_ONLY\` in \`timeline_runner.py\`. This means moving the noise volume slider or clicking a noise color button correctly engages the user lock system and prevents the timeline from overriding those values.

\*\*The agent also respects locks\*\* — \`SomnaAgent.\_write_live()\` filters out any key in \`timeline_locked_params\` before writing.

\*\*Gold labels\*\* in the control panel indicate locked params. \`\_poll_session_state()\` reads \`timeline_locked_params\` from live state and calls \`.config(fg=RP\["gold"\])\` on the corresponding \`\_param_labels\` entries.

\---

\## Session authoring

Sessions live in \`sessions/&lt;name&gt;/\`:

\- \`session.yaml\` — timeline + defaults. See \`SESSION_AUTHORING.md\`.

\- \`affirmations.txt\` — phrase pool with optional \`# \[tag\]\` groups. Untagged phrases are always active. Tagged groups are activated by the timeline via the \`phrases\` key. \*\*Live reload:\*\* \`layers/phrase_pool.py\` uses the file's \`mtime\` as part of the pool identity key. Edits to \`affirmations.txt\` take effect within the next render frame with no session restart required.

\- \`images/\` — background images (PNG, JPG, GIF, WebP, WebM)

\- \`fonts/\` — \`.ttf\` / \`.otf\` files (session-specific; overrides project defaults)

Project-level fonts live in the top-level \onts/\ folder. Font discovery uses a three-tier fallback chain:

1. \sessions/<session>/fonts/*.ttf\ + \*.otf\ (session-specific, highest priority)
2. \onts/*.ttf\ + \*.otf\ (project-level defaults)
3. System fonts (Arial Black / Georgia)

All font loading is consolidated in \layers/font_manager.py\ via \discover_fonts(session)\ and \make_font(path, size)\. Do not duplicate font discovery logic in individual layers.

\*\*Font switching modes\*\* — \ont_switch_mode\ in session YAML or live_control.json:

| Mode | Behavior |
|------|----------|
| \intelligent\ | Font changes every 5-12 s (calm, dwell-heavy). Default. |
| apid\ | Font changes every 0.15-0.45 s (strobing overload effect). |
| \eat_sync\ | Font changes on every beat_phase downstroke (phase crosses 0). Switches locked to the entrainment rhythm. |
| \reathe_sync\ | Font changes on every exhale transition (respiratory_phase crosses 0.5). Switches locked to the breath cycle. Uses \ppg_breath_phase\ when available, falls back to espiratory_phase\. |
| \depth_adaptive\ | Switching speed scales with \eeg_trance_score\. At score 0 the interval is ~10 s; at 1.0 it drops to ~0.5 s. The deeper you go, the faster fonts cycle. |

Do not add font loading logic outside \ont_manager.py\. All layers should use \FontManager\, \discover_fonts()\, or \make_font()\.

The timeline runner (\`TimelineRunner\` in \`timeline_runner.py\`) reads \`session.yaml\` via the \`Session\` dataclass. It interpolates numeric params between keyframes using easing curves and hard-switches string/bool params at keyframe boundaries. See \`SESSION_TIMELINE.md\` for the full spec.

\*\*YAML keyframe format\*\* — the preferred format uses a \`params:\` sub-key on each keyframe (nested format). Flat keys directly on the keyframe are also supported (the runner merges both), but \`params:\` wins on conflict. The \`session_pipeline.py\` \`FORMAT_REFERENCE\` doc block was corrected to reflect this; \`params:\` is canonical.

\*\*Session editor (\`session_editor.py\`)\*\* — supports Ctrl+Z undo (snapshot-based, 20-level stack) and a dirty flag (\`\*\` in title bar when unsaved). The correct param names for the editor's \`\_PARAM_ORDER\` are \`shadow_flash_on_time\`, \`shadow_flash_off_time\`, and \`slideshow_interval\` — the old incorrect names \`shadow_on_time\`, \`shadow_off_time\`, \`bg_speed\` are gone. The Delete key shortcut fires when focus is not on an Entry/Combobox/Text widget (canvas focus is set on press). Valid easing modes are \`linear\`, \`ease_in\`, \`ease_out\`, \`ease_in_out\`, \`instant\` — there is no \`step\` mode (\`step\` silently falls through to \`linear\`).

\---

\## Veil modes

Current valid \`veil_mode\` values: \`scroll\`, \`rain\`, \`drift\`, \`converge\`, \`strobe\`, \`tunnel\`, \`null\`.

\*\*\`mirror\` is removed\*\* — it was deleted from \`layers/veil.py\`. Do not reference it anywhere. The \`\_ADJUSTABLE_PARAMS\` dict in \`somna_agent.py\` and the combobox in \`control_panel_imgui.py\` both use the current list.

\`null\` means auto-rotate through modes on a timer (excluding \`strobe\` and \`tunnel\` which are excluded from random rotation).

\---

\## Adding a new \`\_timeline_cmd\`

1\. Add the \`elif cmd == "your_cmd":\` block to \`\_handle_commands()\` in \`timeline_runner.py\`

2\. Consume the command by setting \`data\["\_timeline_cmd"\] = None\` and writing back (already done in the shared consume block at the end)

3\. Add a corresponding method in \`control_panel_imgui.py\` that writes \`{"\_timeline_cmd": "your_cmd"}\` via \`\_send_timeline_cmd()\` or by directly writing \`live_control.json\`

4\. Document the new key in \`README.md\`'s live control table

\---

\## Adding a new slider to the control panel

1\. Create a \`\_plabel\` + \`\_slider\` pair in the appropriate section in \`\_build_left_col\` or \`\_build_right_col\`

2\. Add the slider to \`\_bind_controls()\` with \`w.config(command=self.\_update)\`

3\. Add the param to \`\_get_all_widget_values()\` keyed by its \`live_control.json\` name

4\. Add a \`.set(d.get(...))\` call in \`\_load_current_values()\`

5\. Add a \`.set(d.get(...))\` call in \`\_poll_ui_sync()\` so it tracks timeline interpolation

\---

\## Adding a new veil mode

1\. Add \`\_init_&lt;mode&gt;\`, \`\_update_&lt;mode&gt;\`, \`\_draw_&lt;mode&gt;\` methods to \`VeilLayer\` in \`layers/veil.py\`

2\. Add the mode name to \`\_MODES\` list (if it should participate in auto-rotation)

3\. Add init/update/draw dispatch in the \`\__init_\_\` / \`update\` / \`draw\` methods

4\. Add to the \`veil_mode\` combobox values in \`\_build_right_col\` in \`control_panel_imgui.py\`

5\. Add to \`\_ADJUSTABLE_PARAMS\` in \`somna_agent.py\`

6\. Update the \`veil_mode\` row in \`README.md\`

\---

\## VR overlay pipeline (vr_overlay.py + visual_display.py)

The VR overlay is an optional SteamVR overlay that runs alongside the normal desktop window.

\### Activation

\- CLI: \`python visual_display_runner.py --vr\`

\- Config: \`vr_mode: true\` in \`live_control.json\` at launch time

\- Control panel: 🥽 toggle button in the transport bar (sets \`\_vr_mode\`, passes \`--vr\` to the subprocess)

\### Render pipeline change (VR mode only)

When VR mode is active, every render frame is redirected into \`\_vr_fbo\` (an off-screen \`moderngl.Framebuffer\`) instead of writing directly to \`ctx.screen\`. After all layers are composited:

1\. \`VROverlayManager.push_frame(\_vr_fbo_tex)\` — calls \`glFinish()\` then \`setOverlayTexture()\` to push the GPU texture to SteamVR

2\. \`ctx.copy_framebuffer(ctx.screen, \_vr_fbo)\` — blit to the desktop preview window

\*\*Do not change the bind order.\*\* \`\_vr_fbo.use()\` must be called before \`ctx.clear()\` and before any layer draw call. \`ctx.screen.use()\` + \`copy_framebuffer\` must happen \*after\* \`push_frame\`, not before.

\*\*Non-VR code paths are unchanged.\*\* When \`\_vr_fbo\` is \`None\` (no VR), \`ctx.screen\` is always the bound framebuffer and the render loop is identical to the pre-VR implementation.

\*\*FBO trail system\*\* — ping-pong framebuffer pair (\`\_trail_fbos\[2\]\`, \`\_trail_texs\[2\]\`, \`\_trail_index\`) composites the spiral layer with a decay factor each frame. The composite shader blends the current frame's spiral render with the previous trail texture at weight \`trail_decay\`. \`\_init_trail_fbos()\` creates the FBOs and must be called from \`\_make_textures()\` so they are recreated on window resize. The trail index swap happens after the blit: \`self.\_trail_index = 1 - self.\_trail_index\`.

\*\*SR overlay\*\* — a dedicated \`\_sr_prog\` program blits the overlay surface (shadows + affirmations text) with per-pixel per-frame Gaussian noise injected into the alpha channel of non-transparent pixels. The noise amplitude is \`sr_noise_level\`. Separate from the trail system; runs after the trail blit in the same frame.

\### VROverlayManager

Lives in \`vr_overlay.py\`. Initialises \`VRApplication_Overlay\` (not \`VRApplication_Scene\`). The overlay is a floating world-locked panel attached to the HMD via \`setOverlayTransformTrackedDeviceRelative\`. Key constants at the top of the file: \`OVERLAY_WIDTH_M\`, \`OVERLAY_DIST_M\`, \`OVERLAY_CURVATURE\`.

\### Texture handoff

\`mgl_texture.glo\` is the raw OpenGL texture name (integer). OpenVR's \`Texture_t.handle\` must receive this integer \*\*as a pointer value\*\*, not a pointer to it:

\`\`\`python

tex.handle = ctypes.c_void_p(mgl_texture.glo) # correct

tex.handle = ctypes.byref(ctypes.c_int(glo)) # WRONG — passes address of variable

\`\`\`

\### pyopenvr return values

\`findOverlay()\` and \`createOverlay()\` may return a bare handle OR a \`(error_code, handle)\` tuple depending on pyopenvr version. \`vr_overlay.py\` wraps both forms via the internal \`\_unwrap()\` helper. Do not call these methods directly without unwrapping.

\---

\## Windows overlay (visual_display.py)

The display window uses Win32 extended styles for transparency and click-through:

\- \`WS_EX_LAYERED\` — enables DWM alpha compositing

\- \`WS_EX_TRANSPARENT\` — routes mouse events to the window behind

\- \`WS_EX_NOACTIVATE\` — prevents the window from stealing focus (required for DWM to composite it while unfocused)

\- \`DwmExtendFrameIntoClientArea(-1,-1,-1,-1)\` — extends the desktop compositor frame to the full client area; GL pixels with alpha=0 become fully transparent

\- \`pygame.mouse.set_visible(overlay_mode)\` — shows/hides the OS cursor; SDL2 manages cursor visibility so this is the only reliable call (Win32 \`ShowCursor\` is not equivalent)

\`\_apply_window_flags()\` is throttled to every 30 frames and re-applies flags unconditionally so DWM or SDL resets are immediately corrected.

\---

\## User profile schema (\`user_profile.json\`)

All three agent scripts read and write this file. \*\*Always use \`update_profile()\` from \`somna_agent.py\` to write — never write the file directly.\*\* It reloads from disk before saving to prevent concurrent write races.

\`\`\`json

{

"name": "string or null",

"designations": \["list of strings"\],

"notes": \["list of strings — last 5 shown in context"\],

"goals": \[{"id": "slug", "title": "...", "description": "...", "progress_notes": \[...\]}\],

"responsive_themes": \["themes user goes deep with — agent accumulates these"\],

"effective_moments": \[

{

"ts": "ISO timestamp", "beat": 4.0, "spiral": "tunnel_dream",

"label": "work_window", "affirmation": "empty and open", "complexity": 0.05

}

\],

"last_session": {

"date": "YYYY-MM-DD", "deepest_beat": 3.5, "best_complexity": 0.08,

"phase": "work_window", "phrases": \["phrase1", "phrase2"\]

},

"preferences": {"session_interval_target_days": 1, "preferred_time_of_day": null},

"engagement": {"last_session_date": "YYYY-MM-DD", "total_sessions": 0,

"pending_nudge": null},

"iaf_hz": 9.7,

"iaf_confidence": 0.712,

"iaf_calibrated_at": "2026-04-01T14:30:00",

"iaf_method": "paf_with_cog_fallback",

"iaf_band_boundaries": {

"delta": \[0.5, 3.7\], "theta": \[3.7, 7.7\], "alpha": \[7.7, 11.7\],

"beta": \[11.7, 30.0\], "gamma": \[30.0, 100.0\]

},

"session_zero_status": "complete_minimal",

"session_zero_completed_utc": "2026-04-16T18:00:00",

"safety_consent": {"photosensitive_risk": "normal", "ssb_enabled": true, "safety_acknowledged": true, "acknowledged_utc": "2026-04-16T18:00:00"},

"eeg_baselines": {"eyes_open": {"band_power": {...}}, "eyes_closed": {...}, "breathing": {...}, "alpha_reactivity_ratio": 2.76, "relaxation_response_score": 0.58, "trance_susceptibility": "moderate", "calibrated_utc": "...", "sample_count": 54}

}

}

}

\`\`\`

\`effective_moments\` is capped at 30 entries (FIFO). \`last_session\` is written at the start of each fresh session. \`last_session_date\` is updated by \`somna_agent.py\` on every active tick so the nudge threshold works correctly.

IAF keys (\`iaf_hz\`, \`iaf_confidence\`, \`iaf_calibrated_at\`, \`iaf_method\`, \`iaf_band_boundaries\`) are written by \`control_panel_imgui.py\` via \`\_save_iaf_to_profile()\` after calibration completes. That function does a reload-first merge — it does NOT call \`update_profile()\` because \`control_panel_imgui.py\` runs in a different process. Follow the same pattern for any future writes from the panel process.

\`update_profile()\` reloads from disk before saving to prevent concurrent write races between \`somna_agent.py\` and \`control_panel_imgui.py\`. Never write the file without reloading first.

\---

\## Agent tool-calling pattern

\`somna_agent.py\` supports an optional \`tool_call\` field in the LLM output JSON (both active and idle planning turns):

\`\`\`json

"tool_call": {"tool": "tag_stats", "args": {"session_name": "default"}}

\`\`\`

When present, \`dispatch(tool_name, args)\` is called from \`content_tools/\__init_\_.py\`. The result is injected back as a second LLM call so the model can make a decision with the information. Only one tool call per turn. The loop does not recurse — if the second response also contains \`tool_call\`, it is ignored.

All tools in \`content_tools/TOOLS\` are available. Currently:

\`tag_stats\`, \`images_for_tag\`, \`read_session_log\`, \`read_session_content\`, \`list_sessions\`, \`cull_session\`, \`write_affirmations_batch\`, \`generate_images\`, \`harvest_captions\`, \`auto_tag_session\`, \`write_affirmations\`, \`generate_image\`, \`write_session_yaml\`, \`image_pipeline_cycle\`, \`query_session_performance\`, \`find_images_by_theme\`, \`audit_affirmations\`.

\*\*\`query_session_performance\`\*\* — queries \`somna.db\` for longitudinal effectiveness data: recent session rows, a trend direction for a chosen metric, and the best-performing config for a session preset. Use in idle planning to decide whether to deepen goals, adjust content strategy, or annotate effective configurations.

\*\*\`find_images_by_theme\`\*\* — searches \`somna.db\` across all sessions for images matching a list of tags (both controlled and open_tags). Use to discover existing visuals before generating new ones, or to surface cross-session aesthetic continuity for a new session's image folder.

\*\*\`next_affirmation\` injection\*\* — the LLM response JSON may include \`"next_affirmation": "phrase"\` to inject a single phrase into the live affirmation pool. \`affirmations_pool\` is \*\*not\*\* in \`\_ADJUSTABLE_PARAMS\`; the LLM cannot replace the whole pool via \`adjustments\`. Use \`next_affirmation\` for one-off injections.

\*\*LLM response robustness\*\* — \`\_extract_json()\` in \`somna_agent.py\` is used for all JSON parsing. It strips \`&lt;think&gt;…&lt;/think&gt;\` blocks, markdown code fences, and text prefixes, then does a backward balanced-brace scan to find the last complete JSON object. Do not use \`response_format={"type": "json_object"}\` in LLM API calls — local models (e.g., Qwen) sometimes return a list wrapping the dict; unwrap with \`data = data\[0\] if isinstance(data, list) else data\`.

\*\*\`action\` field\*\* — the interactive-tick JSON schema includes an optional \`"action": "none" | "fractionate"\` field. When \`"fractionate"\` is returned, \`\_apply()\` triggers \`timeline_runner.py\`'s fractionation state machine via \`\_timeline_cmd\`. Rules: beats ≤ 7 Hz, session ≥ 10 min, complexity ≤ 0.25, \`fractionation_active\` false, not in the opening window.

\*\*\`\_deep_window_tick\`\*\* — when \`fractionation_phase\` starts with \`"DEEP"\`, \`\_interactive_tick\` routes to a dedicated \`\_deep_window_tick\` method. This handler forces suggestion-delivery mode: no dialog prompts, subdued display-only affirmations, explicit \`extra_instruction\` to the LLM preventing clarifying questions.

\*\*\`reinforce_response\` tool\*\* — callable via \`tool_call\` during active sessions. Injects the user's own phrases back into the affirmation pool. Training mode auto-injection was removed from \`\_call_llm\`; \`\_reinforce_response\` is now an explicit opt-in tool the LLM can call when it judges the user is responding well.

\*\*Training mode\*\* (\`agent_config.yaml\` keys: \`training_mode: true\`, \`training_target: 0.15\`) — the agent still tracks \`\_score_complexity()\` and passes the trend in context, but no longer auto-injects training notes into user messages. Use \`reinforce_response\` tool explicitly instead.

\`image_pipeline_cycle\` is the self-improving idle-time image generation tool. One call = one full cycle: pick untagged reference → vision-analyse + tag → LLM engineers verbose prompt → generate → vision-review → promote to \`images/\` or discard. Generated images land in \`sessions/&lt;name&gt;/images/generated/\` before review; promoted images move to \`sessions/&lt;name&gt;/images/\` with tags. All metadata and attempt history are written to \`somna.db\` via \`content_tools.somna_db\`. Harvested reference captions are written with \`write_affirmations()\` to thematic tags derived from the reference image's own tags. Call on successive idle turns to iterate.

\---

\## Image tagging system

\`content_tools/image_tags.py\` manages vision-model tagging of session images. All metadata is stored in \`somna.db\` via \`content_tools.somna_db\` — there are no per-session \`tags.json\` files.

\- Image metadata stored in \`somna.db\` \`images\` table — one row per \`(session, filename)\`

\- Each row: \`tags\`, \`open_tags\`, \`caption_text\`, \`quality\` (\`keep\`|\`cull\`), \`style\`, \`conditioning_hook\`, \`gen_scores\`

\- \*\*\`tags\`\*\*: controlled vocabulary (conditioning theme, explicitness, style)

\- \*\*\`open_tags\`\*\*: free-form folksonomy — model assigns anything it observes (body parts, props, aesthetics, settings). Searchable via \`images_for_tag()\` alongside controlled tags.

\- \`background.py\` uses \`\_tag_map\` (loaded from \`somna_db.load_tags\`) to filter the image pool to match \`timeline_label\`. Matches both \`tags\` and \`open_tags\` via substring.

\- Culled images (quality='cull') are always excluded from the display pool.

\- \`read_tags\` and \`write_tags\` in \`image_tags.py\` are backward-compat aliases for \`somna_db.load_tags\` / \`somna_db.save_tags\`.

CLI: \`python -m content_tools.image_tags tag &lt;session&gt; --batch 20 \[--harvest\]\`

\---

\## Session registry (\`content_tools/somna_db.py\` — \`sessions\` table)

\`somna.db\` now includes a \`sessions\` table as a registry for all sessions:

\- Columns: \`name\`, \`description\`, \`image_tags\`, \`duration_s\`, \`category\`, \`is_favorite\`, \`created_at\`, \`last_played\`, \`play_count\`

\- \`SESSION_CATEGORIES\` = \`\["Induction", "Focus", "Sleep", "Maintenance", "Archive"\]\`

\- Functions: \`upsert_session()\`, \`get_session_meta()\`, \`record_session_played()\`, \`get_suggestions()\`, \`list_sessions_with_meta()\`

\- \`record_session_played()\` uses SQLite \`datetime('now')\` (UTC) — when computing age in Python use \`datetime.utcnow()\` not \`datetime.now()\` to avoid timezone sign errors.

**Session list** — ImGui selectable list backed by `_session_names` and `_selected_session_idx` in `control_panel_imgui.py`. The list index maps directly to `_session_names[idx]` — the raw session folder name.

**Mode strip** — quick-launch preset buttons in the session sidebar. Selecting a mode loads the corresponding session immediately.

\*\*Session scoring\*\* — \`session_scorer.py\` / \`SessionScorer\` is triggered by \`control_panel_imgui.py\` when it detects the display subprocess has stopped (not from the agent process — the agent is a subprocess with no EEGEngine reference). \`\_trigger_eeg_scoring()\` in \`control_panel_imgui.py\` reads FreqLeader state from \`live_control.json\` at stop time and passes it to the scorer.

\*\*\`session_quality\` table\*\* — stores content pipeline quality scores from \`session_pipeline.py\`. Written via \`save_session_quality()\` after each pipeline run. Tracks structural and content review scores per session.

\*\*\`delivery_log\` table\*\* — added for Bible Ch.2 delivery tracking. Logs each stimulus delivery event with phase, gate state, and cardiac/IMU context. Created fresh in the schema; existing databases receive it via the Bible Ch.2 migration block.

\---

\## User settings persistence (\`user_settings.json\`)

\`user_settings.json\` stores UI preferences that must survive concurrent \`live_control.json\` write races:

\- \`window_always_on_top\` — bool

\- \`window_click_through\` — bool

\- \`tts_voice\` — str

\- \`window_geometry\` — str (Tk geometry string, e.g. \`"1200x1050+320+80"\`)

\*\*Read order\*\* — \`\_load_current_values()\` prefers values from \`user_settings.json\` for these keys, overriding whatever \`live_control.json\` has. After \`\_load_current_values()\` returns, all user settings are flushed back to \`live_control.json\` so the display subprocess reads consistent values.

\*\*Write path\*\* — \`\_update()\` detects changes to \`\_USER_SETTINGS_KEYS\` and calls \`\_save_settings()\`. Window geometry is saved via a debounced \`&lt;Configure&gt;\` binding (500 ms delay). Never rely on \`live_control.json\` alone to persist these preferences.

\---

\## Audio channel assignments

| Channels | Owner |

|----------|-------|

| 0, 1 | \`BinauralAudioEngine\` — left and right binaural beats |

| 2 | Colored noise — independent, plays looping 10 s buffer |

| 3 | Sleep burst channel — 70 ms pink noise bursts (alpha anti-phase + SWE); commanded by \`sleep_burst_cmd_ts\` in \`live_control.json\` |

| 4, 5 | \`TTSEngine\` — TTS playback |

| 6 | TMR cue channel — tonal cues from \`CueManager\`; commanded by \`tmr_cue_cmd\` in \`live_control.json\` |

\*\*TTS cook thread sync\*\* — the TTS cook thread must call \`self.\_pool.update(config)\` before each \`pick()\` call. \`PhrasePool\` does not self-update; if \`update()\` is never called the pool is frozen at engine startup and will return phrases from the initial \`live_control.json\` state indefinitely — including phrases from a session that has since changed. Additionally, when \`session_folder\` changes in config the cook thread must clear the \`\_ready\` deque immediately to prevent stale pre-cooked phrases from playing in the new session.

\*\*Audio ownership\*\* — \`pygame.mixer\` is initialised and owned exclusively by \`control_panel_imgui.py\`. \`visual_display.py\` sets \`os.environ\['SDL_AUDIODRIVER'\] = 'dummy'\` before \`pygame.init()\` and never touches the mixer. \`BinauralAudioEngine\` and \`TTSEngine\` are instantiated inside the control panel process. The agent process has no audio at all.

\*\*Crash recovery\*\* — \`BinauralAudioEngine.\_audio_loop\` catches exceptions and reinitialises its own channels (0, 1, 2) on 5 consecutive errors. It does \*\*not\*\* call \`pygame.mixer.quit()\` — that would destroy the TTS channels owned by the same mixer instance. Channel objects are recreated via \`pygame.mixer.Channel(n)\`.

\*\*Binaural crossfade\*\* — for changes ≥ 2 Hz combined (carrier + beat), \`\_crossfade()\` hard-stops the old channel and starts the new one immediately. For smaller changes the \`current_carrier\`/\`current_beat\` values update silently and the next generated chunk picks them up at the chunk boundary — no stop, no click.

\*\*\`pygame.mixer.pre_init(44100, -16, 2, 512)\`\*\* must be called before \`pygame.init()\` and is done in \`control_panel_imgui.py\` at startup. Do not move it into \`BinauralAudioEngine.\__init_\_\` — the mixer is already initialised by the time the engine is created.

\---

\## Background layer behavior (\`layers/background.py\`)

\`background.py\` has two methods called every frame:

\- \*\*\`tick(cfg)\`\*\* — always runs before \`bg_none\` is evaluated in \`visual_display.py\`; detects session-folder changes and calls \`\_reload_session()\`. Runs even when \`bg_mode = "none"\`.

\- \*\*\`draw(surf, cfg)\`\*\* — only runs when \`not bg_none\`; blits the current image.

\*\*Auto bg_mode\*\* — when \`\_reload_session()\` finds images it writes \`bg_mode = "slideshow"\` to \`live_control.json\`; when no images exist it writes \`bg_mode = "none"\`. The UI checkbox stays in sync via \`\_poll_ui_sync()\`.

\*\*\`has_images\` property\*\* — \`True\` when \`\_all_paths\` is non-empty. Used by \`visual_display.py\` to force \`bg_none = True\` automatically when a session has no images.

\*\*Image pool\*\* — \`\_MAX_IMAGES = 200\`. \`\_all_paths\` holds the full directory scan (path objects only). \`\_resample()\` picks a fresh random 200 from \`\_all_paths\` every 100 image switches; old cached \`pygame.Surface\` objects are evicted.

\*\*Supported formats\*\* — PNG, JPG, GIF, WebP, WebM, AVIF, APNG. MP4 is \*\*not\*\* supported (OpenCV on Windows cannot decode H.264 without FFMPEG).

\*\*Tag-based filtering\*\* — \`\_resample()\` filters \`\_all_paths\` to match \`timeline_label\` using \`\_tag_map\` loaded from \`somna_db.load_tags\`. Culled images (\`quality='cull'\`) are always excluded.

\*\*Image scaling\*\* — contain + tile mode: the image is scaled to fit within the display (preserving aspect ratio); any remaining margin area is tiled with unblurred copies of the same surface. Do not blur the tile copies — the blur experiment was reverted; the current \`self.current_surf\` is used directly for margin tiles.

\---

\## Idle planning and ghost nudge (\`somna_agent.py\`)

\> \*\*Design spec: Bible Ch.5 — Agent Intelligence.\*\* This section covers implementation details only.

All between-session logic lives inside \`somna_agent.py\`'s idle loop — there is no separate heartbeat daemon.

\*\*Idle planning startup guard\*\* — \`\_idle_last_plan\` must be initialized to \`time.time()\` (not \`0.0\`) so the first planning cycle waits the full \`idle_planning_interval_min\` rather than firing immediately on agent startup. Immediate planning on startup can trigger heavy LLM + GPU operations before the user has interacted with anything.

\*\*Stale nudge clearing\*\* — on agent startup, \`pending_nudge\` in \`user_profile.json\` must be checked for staleness (compare its timestamp against \`time.time()\`). If the agent process was killed mid-nudge the previous run, the stale \`pending_nudge\` entry will fire a nudge invitation immediately on restart with an incorrect elapsed time. Clear it with a log line before entering the main loop.

\*\*Idle planning cycles\*\* are triggered in two ways:

\- \*\*Post-session\*\* (immediate): fires as soon as a session closes (\`\_post_session_pending = True\`), runs \`\_idle_planning_cycle(mode="post_session")\`. Focuses on goal updates and content gaps while the session is fresh.

\- \*\*Scheduled\*\* (every \`idle_planning_interval_min\` minutes, default 30): runs \`\_idle_planning_cycle(mode="idle")\`. Reviews the longer arc, checks if a nudge is warranted.

Both modes build a planning prompt via \`\_build_planning_prompt(mode)\` that includes:

\- Session effectiveness scores from \`somna.db\` via \`SessionAnalyzer.get_recent_scores()\`

\- Content gap analysis (sessions with < 8 phrases in a tag) via \`tag_stats\`

\- Goals, responsive themes, effective moments, and recent logs

The LLM may return multiple actions in a single response via the \`"actions"\` list.

\*\*Idle-time knowledge injection\*\* — \`\_idle_planning_cycle\` uses \`\_load_idle_knowledge()\` (not \`\_load_knowledge_for_agent()\`). The idle knowledge set is intentionally different from the session-time set, focused on planning and longitudinal reasoning:

| File | Reason injected at idle time |

|------|------------------------------|

| \`session_effectiveness_scoring.md\` | Score semantics, composite weights, auto-optimization protocol |

| \`session_design.md\` | Session structure needed for content generation and new session creation |

| \`training_mode.md\` | Training context for goal update decisions |

| \`conductor_fsm.md\` | Phase meanings, since \`conductor_state\` is now included in the planning prompt |

| \`aphantasia.md\` | \*\*Conditional\*\* — injected only when \`user_profile.aphantasia\` is \`"none"\` or \`"minimal"\` (or unset). Skipped for \`"moderate"\` / \`"vivid"\` imagers so the LLM can write expressive, imagery-rich content freely. |

Session-time files (\`veil_and_spirals.md\`, \`gateway_process.md\`, \`eeg_entrainment.md\`, etc.) are \*\*not\*\* injected at idle time — they consume context window without adding planning value.

\*\*Ghost nudge\*\*: when the scheduled cycle decides \`action="nudge"\` and \`days_since_last >= nudge_after_days\`, \`\_nudge_start()\` launches the display at 5% opacity / volume 3 / noise 0, then \`RampEngine\` smoothly ramps all three toward 60% opacity / volume 45 / noise 20 over \`nudge_fade_minutes\` minutes (default 20). At ramp end an LLM-generated invitation is delivered via overlay + TTS. The nudge session is capped at \`nudge_max_session_minutes\` (default 45); on timeout \`\_agent_stop_display: True\` is written; on response the display transitions to full opacity over 90 s and the agent resumes a normal session.

\*\*Display-active staleness detection\*\*: \`session_time\` is compared tick-to-tick with a 60 s wall-clock guard. If \`session_time\` hasn't advanced and the timeline is not paused, the display is declared closed. This prevents stale \`live_control.json\` values from a crashed display from keeping the agent in active mode indefinitely.

\---

\## Image generation (\`content_tools/images.py\`)

KoboldCpp uses the \*\*A1111-compatible endpoint\*\*: \`POST /sdapi/v1/txt2img\`. Do not use \`/api/extra/generate_picture\` — that endpoint does not exist in KoboldCpp.

FLUX-specific defaults are in the \`image_gen:\` section of \`agent_config.yaml\`. \`build_conditioning_prompt()\` generates conditioning-themed hypnotic prompts. \*\*FLUX requires narrative prose prompts, not SDXL keyword tag soup.\*\* Output should be a coherent descriptive sentence or short paragraph (e.g. "a figure dissolving into soft golden light, barely visible against a field of warm amber haze") — never comma-separated keyword lists. Do not include text/caption instructions in the prompt — diffusion models cannot reliably render readable text, and Somna overlays text dynamically via the veil/affirmations layer.

\*\*Auto image generation\*\* — disabled by default. \`image_pipeline_cycle\` must never be called automatically from the idle planning tick; it is a heavy GPU operation. Enable via \`auto_image_gen: true\` in \`agent_config.yaml\`. When \`False\`, \`\_check_content_needs\` skips the generate-and-tag step.

\---

\## VR overlay notes (supplement)

\*\*Entry point\*\* — use \`python visual_display_runner.py --vr\`. Running \`python visual_display.py --vr\` directly does nothing useful — \`visual_display.py\` has no \`\__main_\_\` block.

\*\*Y-flip\*\* — the \`BLIT_VERT\` shader already flips the Y coordinate when writing to the FBO. Do not add an additional V-flip via \`setOverlayTextureBounds\` (i.e., do not set \`vMin=1 / vMax=0\`); this would invert the image.

\*\*\`\_get_gl_finish()\` scoping\*\* — if you need to \`import ctypes.util\` inside a function that also uses the top-level \`ctypes\` module, use \`import ctypes.util as \_cu\` to avoid shadowing the module-level \`ctypes\` reference.

\*\*\`OVERLAY_WIDTH_M = 4.0\`\*\* — 90° angular width at 2 m distance; fits inside a typical HMD FOV. \`VR_TARGET_FPS = 90\` caps the render loop when VR is active to match the compositor cycle.

\---

\## VR headset pipeline (vr/vr_display_runner.py — OpenXR per-eye rendering)

This is a \*\*separate system\*\* from the SteamVR overlay above. It renders

independent content to each eye of an OpenXR-compatible headset (Meta Quest,

Valve Index, Vive, etc.) via \`pyopenxr\`.

\### Entry point and lifecycle

\- Launched by control panel “Launch OpenXR” (Tk) or ImGui OpenXR controls: \`subprocess.Popen(\[python, "vr/vr_display_runner.py"\])\`

\- Writes \`vr_headset_active: true\` on startup, \`false\` on exit

\- Exits when \`vr_headset_enabled\` is set to \`false\` in \`live_control.json\`

\- Does NOT use \`visual_display_runner.py\` — completely independent render process

\### Render modes and key live_control.json keys

\`\`\`

vr_render_mode "ganzfeld" | "photic" | "rivalry" | "dichoptic_ssvep"

vr_background_lum float 0–1 (Ganzfeld grey level, default 0.5)

vr_rivalry_left_hz float (left-eye rivalry/ssvep tag Hz)

vr_rivalry_right_hz float (right-eye rivalry/ssvep tag Hz)

vr_rivalry_depth float 0–1 (modulation depth; safety-clamped)

vr_photic_hz float (bilateral photic frequency; auto-adjusted by Conductor)

vr_photic_depth float 0–1

vr_vection_enabled bool (optic flow particle tunnel overlay)

vr_vection_speed float 0–1

vr_subliminal_enabled bool (depth-plane subliminal delivery)

vr_ganzfeld_ramp_s float (onset ramp duration; default 120 s)

vr_ganzfeld_hold_s float (equilibration hold; default 120 s)

vr_ganzfeld_flicker_hz float (0 = no flicker; 2–4 Hz = ganzflicker)

\`\`\`

\### SSVEP outputs (written by SSVEPDetector via EEGEngine plugin)

\`\`\`

ssvep_binocular_index float 0–1 (binocular integration strength)

ssvep_switch_rate_hz float (rivalry dominance switch rate)

ssvep_dominance_raw float -1..+1 (positive = left dominant)

ssvep_left_snr float dB (left-eye tag SNR)

ssvep_right_snr float dB

ssvep_im_f1_plus_f2 float dB (intermodulation at f_L + f_R)

ssvep_im_f1_minus_f2 float dB

\`\`\`

\### Safety architecture

All VR safety is enforced at the renderer level — Conductor cannot override it.

\- \`SafetyEnforcer\` in \`vr/vr_safety.py\` wraps every depth/frequency value

\- \`vr/vr_freq_table.py\` validates harmonic collisions at session start (called by Conductor)

\- Paroxysmal kill: \`eeg_raw_af7_last_256\` (written by EEGEngine each tick when VR active) feeds \`check_paroxysmal()\` inside the VR render loop

\- \`vr_safety_kill: true\` is written on paroxysmal event — permanently halts stimulation for that session

\### Conductor integration

\- \`binocular_index > 0.5\` acts as a secondary ASSR-equivalent for INDUCTION lock

\- \`binocular_index > 0.6\` + \`switch_rate_hz > 0.10\` corroborates \`ts_ok\` in DEEPENING

\- Closed-loop photic: every tick, Conductor checks SSVEP SNR and nudges \`vr_photic_hz\` ±0.5 Hz toward IAF if SNR < 3 dB for 60 s

\- Frequency collision check runs when \`vr_headset_active\` first becomes True; warnings written to \`vr_freq_warnings\`

\### Subliminal depth-plane routing

Agent's \`next_affirmation\` injections are automatically distributed to three VR depth planes

(far/mid/near, 4:4:1 ratio) when \`vr_headset_active\` is True — no code changes required.

Near-plane exposure is VAC-capped at 25% of total subliminal time; 20-minute session maximum.

\### Dependencies

\`\`\`

pip install pyopenxr PyOpenGL PyOpenGL_accelerate

\`\`\`

Graceful degradation: if either package is missing, the subprocess prints instructions and exits cleanly.

\---

\## Modular shader architecture (Phase 1)

The spiral renderer uses a modular shader system. The monolith \spiral.glsl\ is still present as a fallback, but the primary path assembles the shader from:

- \shaders/common.glsl\ — shared uniforms, helpers, noise functions, arm distance field, curl noise, Oklab color space
- \shaders/styles/style_<name>.glsl\ — 23 per-style files, each implementing \ec4 style_<name>(vec2 p)\
- Dispatch in \spirals_opengl.py\ \_assemble_shader()\ — appends main() with if/else chain

**Assembly flow:** \SpiralsLayer._load_shader()\ checks if \common.glsl\ and \styles/\ dir exist. If yes, assembles from modules. If no, falls back to monolith \spiral.glsl\.

**Post-processing pipeline** (Bible Ch.3 §3.7):
- \pp_ca.glsl\ — chromatic aberration (radial RGB split)
- \pp_bloom_threshold.glsl\ — bright pixel extraction for bloom
- \pp_blur.glsl\ — separable Gaussian blur (5-tap)
- \pp_composite.glsl\ — bloom composite + vignette + IAF modulation + ACES tonemapping + film grain
- All wired in \isual_display.py\ \_run_post_processing()\

**New Phase 2 uniforms in pp_composite.glsl:**
- \pp_tonemap\ (int, 0=off, 1=ACES) — ACES filmic tonemapping
- \pp_film_grain\ (float 0.0–0.15) — per-frame luminance noise
- \u_time\ (float) — wall clock for grain animation

**Oklab color space** is available in \common.glsl\ as \
gbToOklab()\, \oklabToRgb()\, \mixOklab()\. Not yet used by any style — ready for Phase 2 color pass integration.

**Phase 3 — Feedback modes** (\pp_feedback.glsl\): six spiral persistence/feedback effects wired as an additional FBO pass in the render loop before post-processing:
- \alpha_decay\ — fade previous frame with configurable decay
- \radial_zoom\ — zoom from center with persistence
- \rotational_smear\ — angular smear creating motion trails
- \directional_blur\ — horizontal streak persistence
- \reaction_diffusion\ — organic pattern evolution
- \kaleidoscopic_fold\ — mirrored symmetry persistence
Live key: \feedback_mode\ (str, one of the above or \none\). Live key: \feedback_strength\ (float 0.0–1.0).

**Phase 4 — Five new styles** (23 total, indices 18–22):
- \cobwebs\ (18) — irregular radial threads with structural variation
- \strange_attractor\ (19) — Lorenz-like swirling particle trails
- \flow_field\ (20) — organic curl-noise-driven streams
- \sacred_geometry\ (21) — concentric geometric forms (Flower of Life, Metatron)
- \recursive_fractal\ (22) — nested self-similar branching patterns

**PP pipeline vertex shader** — PP passes use \_PP_VERT\ (straight UV, no Y-flip). \copy_framebuffer\ preserves GL orientation, so using \_BLIT_VERT\ (which flips Y) caused a double-flip. \pp_composite.glsl\ also passes scene alpha through instead of forcing 1.0, preserving desktop transparency.

**Regression test:** \	ests/test_spiral_shader_assembly.py\ — pixel-diff test comparing assembled vs monolith for all 23 styles. Run with \pytest tests/test_spiral_shader_assembly.py -v\.

---

## GLSL spiral seam patterns to avoid

\- \*\*\`atan(y, x)\` discontinuity\*\* — the function returns values in \`\[-π, +π\]\` with a jump on the negative x-axis. Never use raw \`angle\` in a phase formula without ensuring the phase jump at the seam is an exact integer multiple of the period.

\- \*\*Non-integer angular coefficient\*\* — \`angle \* count \* 0.5\` with odd \`count\` creates a non-integer period multiplier → seam. Use \`round(count \* 0.5)\` or \`angle \* count\` (integer).

\- \*\*Golden angle in phyllotaxis dot patterns\*\* — \`angle / golden_angle\` is never 2π-periodic because \`golden_angle / (2π)\` is irrational. Replace with a radial center glow or a formula based on integer multiples of \`angle\`.

\- \*\*Double-smoothstep arm profiles\*\* — \`smoothstep(w,0,d) + smoothstep(w\*N,0,d)\*X\` creates a slope discontinuity at \`d = w\` → visible concentric stripes at wide arm settings. Use \`arm_core + arm_glow \* (1 - arm_core)\` to blend so the glow only fills where the core isn't.

\- \*\*Color seams via \`arm_color\`\*\* — if the cosine palette \`c\` vector has non-integer components (e.g., \`vec3(1.0, 0.9, 0.8)\`), the palette is not periodic in \[0,1\] and produces a visible color jump at the wrap. Use \`vec3(1.0, 1.0, 1.0)\` for a seam-free full-spectrum rainbow.

\- \*\*Shader file encoding\*\* — \`spiral.glsl\` must be read as UTF-8. Open with \`open(path, encoding="utf-8")\`.

\---

\## Reconsolidation Protocol Engine

Lives entirely in \`agent/somna_agent.py\`. All recon logic is agent-driven — no new Conductor phases, no dedicated engine file.

\*\*Runtime state\*\* — the \`_ReconState\` dataclass tracks a single sequence (one trace per session). Phases: \`idle → retrieve → labilize → update → lockout → complete\`. Reset on every fresh start; persists across silent resumes.

\*\*Content authoring\*\* — retrieve and update phrases are written to \`affirmations.txt\` during idle planning via \`_author_recon_content()\`. Tags: \`recon_retrieve_<trace>\` and \`recon_update_<trace>\`. The agent arms a \`_ReconState\` at \`_startup_sequence\` by scanning the loaded session's affirmations for these tag pairs. Do not improvise recon content in-session — it must be premeditated in idle planning.

\*\*Live keys\*\* written by the agent during a sequence:
\- \`recon_active_trace\` — trace name string, or \`null\` in lockout
\- \`recon_sub_phase\` — current sub-phase string for display/debugging
\- \`recon_trace_lockouts\` — dict: \`{trace: unlock_walltime}\`; written on lockout entry
\- \`recon_locked_phrases\` — list of retrieve phrase strings; Conductor checks this to skip TMR delivery of old-trace phrases during the lockout window

\*\*Timing\*\* — retrieve window ≤5 min, labilize 12 min, update ≤8 min, lockout 45 min. One sequence per session maximum. The process is invisible to the user (no dedicated overlay state, phrases delivered via standard TTS+overlay path).

\*\*DB\*\* — events logged to \`recon_events\` table in \`somna.db\` via \`content_tools.somna_db.log_recon_event()\`. Query with \`read_recon_events()\`.

\*\*Conductor integration\*\* — \`conductor.py\` \`_should_deliver_affirmation()\` reads \`recon_locked_phrases\` and skips TMR encoding for any phrase matching the lockout list. No other Conductor changes.

\*\*Knowledge file\*\* — \`knowledge/reconsolidation_protocol.md\` is injected into the agent system prompt and provides neuroscience rationale, exact tagging conventions, and authoring guidance for the LLM.

\---

\## Somatic Palette System

Lives in \`agent/somna_agent.py\` (chord monitoring + selection + recording) and \`content_tools/somna_db.py\` (persistence). No separate engine file.

\*\*Core concept\*\* — a palette entry records one cross-modal configuration (chord) + entry context → outcome for this user. Multiple chords can be tested within a single session via fractionation re-drops. Over sessions the DB accumulates a personal response map navigable by desired state family.

\*\*Runtime state\*\* — \`_PaletteChordState\` dataclass tracks the active chord: config snapshot (\`beat_frequency\`, \`carrier_waveform\`, \`noise_color\`, \`noise_volume\`, \`spiral_style\`, \`veil_mode\`), eval window timing, accumulated trance/FAA readings, and failure trackers. Reset on every fresh session start.

\*\*Chord evaluation\*\* — \`_palette_chord_tick()\` runs on a 30 s cadence in \`_interactive_tick\`. Opens a 12–15 min eval window on first MAINTENANCE entry. Three failure conditions (any single triggers abandon): trance_score ceiling < 0.40 after 8 min; FAA persistently negative > 6 min; depth composite declining. Max 3 chord switches per session. After each failure the agent requests fractionation via \`agent_conductor_hints.request_fractionation = True\` and waits for FRAC_REDROP → MAINTENANCE re-entry before opening the next window (3 min cooldown).

\*\*Chord selection on switch\*\* — \`_palette_select_next_chord()\` queries \`best_palette_for_family()\` and scores candidates by \`outcome_score + 1/(n_obs + 1)\` (high score AND high uncertainty wins). Falls back to stepping through predefined beat frequency / waveform combinations when history is sparse.

\*\*Recording\*\* — \`_palette_record(pc, abandoned)\` is called after every closed window (pass or fail). Writes to \`palette_entries\` table, appends row id to \`self._session_palette_entry_ids\`.

\*\*Session-start recommendation\*\* — \`_palette_recommend()\` is called from \`_write_conductor_hints()\` at session start. Queries the densest annotated family for the current hour and merges best-chord params into \`agent_conductor_hints.palette_recommendation\`.

\*\*Post-session LLM annotation\*\* — the \`_idle_planning_cycle\` post-session prompt includes all chord ids + configs + outcomes for the ended session. The LLM outputs \`palette_annotations\` list (one per chord: \`id\`, \`family\`, \`state_type\`, \`notes\`). The cycle calls \`annotate_palette_entry()\` for each.

\*\*Palette families\*\* (LLM-assigned): \`grounding\`, \`depth_charge\`, \`focus\`, \`emotional\`, \`creative\`.

\*\*DB helpers\*\* in \`content_tools.somna_db\`: \`log_palette_entry()\`, \`annotate_palette_entry()\`, \`best_palette_for_family(family, entry_hour, top_n)\`, \`get_palette_summary()\`.

\*\*Knowledge file\*\* — \`knowledge/somatic_palette.md\` is injected into the agent system prompt and covers family descriptions, state types, chord testing protocol, and the optimization principle.

\*\*Do not\*\*: do not write \`palette_family\` or \`state_type\` directly from \`_palette_chord_tick\` — annotation is exclusively a post-session LLM step. Do not trigger palette chord switches outside \`_palette_chord_tick\` / \`_palette_abandon_chord\`. Do not add palette keys to \`live_control.json\` — all palette state is internal to the agent process and the DB.

\---

\## Do not

\- Do not invent new IPC mechanisms — use \`live_control.json\` via \`patch_live()\`

\- Do not write \`live_control.json\` directly (no \`write_text\`, no \`json.dumps\` + path write) — always call \`from ipc import patch_live\` and use \`patch_live(updates)\`. The \`StateServer\` in \`ipc/\` is the single writer; direct writes bypass serialisation and reintroduce race conditions

\- Do not add a new \`\_patch_live\` function anywhere — the pattern is retired; all call sites use the module-level \`patch_live\` from \`ipc\`

\- Do not add \`print()\` debug statements to production code paths

\- Do not use \`os.system()\` or \`subprocess.run()\` for file operations

\- Do not hardcode color values — always use \`RP\["..."\]\`

\- Do not hardcode font tuples — always use \`FONT_\*\` constants

- Use `_row_slider()` helper for ImGui sliders — ensures consistent styling and value binding

\- Do not reference \`veil_mode = "mirror"\` anywhere — it is removed

\- Do not write to \`timeline_locked_params\` from the agent — it is written only by \`timeline_runner.py\`

\- Do not render directly to \`ctx.screen\` in VR mode — always check \`\_vr_fbo\` is unbound before adding new render calls

\- Do not change the init order in \`VisualDisplay.\__init_\_\` — VR init happens after \`\_open_window()\` because the GL context must exist first

\- Do not bypass \`SafetyEnforcer\` for VR depth/frequency values — always call \`safe_depth()\` and \`safe_freq()\` before writing to the renderer

\- Do not write \`vr_photic_hz\` directly from agent code — the Conductor's closed-loop manages it; write \`agent_conductor_hints\` instead to suggest a target

\- Do not call \`GLUT.glutInit()\` on every render frame — \`vr_subliminal.py\` uses a module-level \`\_GLUT_AVAILABLE\` flag; one-time init only

\- Do not add a second BrainFlow board connection for the VR subprocess — raw EEG reaches the VR process via \`eeg_raw_af7_last_256\` in \`live_control.json\`

\- Do not pack \`agent_status_lbl\` — that widget was removed from the layout

\- Do not reference the old "Memory" button or \`_memory_*\` state variables — they were replaced by the Settings modal (\`_settings_*\` state) with a gear icon (⚙) in the console bar

\- Do not use \`yaml.dump()\` to write \`agent_config.yaml\` — it strips all comments. Use line-level string replacement matching \`base_url:\`, \`api_key:\`, \`model:\` at the start of a line

\- Do not write any messaging key directly from agent code — always call \`SomnaAgent.\_say()\` so \`agent_message\` is written and all consumers stay in sync

\- Do not write \`user_profile.json\` directly — always use \`update_profile()\` from \`somna_agent.py\`

\- Do not duplicate \`\_load_profile()\` in new scripts — import from \`somna_agent\` to keep the schema in one place

\- Do not add new LLM configuration env vars — all three agent scripts read \`agent_config.yaml\`; extend that file instead

\- Do not read or write \`tags.json\` or \`gen_log.json\` directly — both are replaced by \`somna.db\`; use \`content_tools.somna_db\` instead

\- Do not import \`sqlite3\` directly outside \`content_tools/somna_db.py\` — all DB access goes through that module

\- Do not use \`response_format={"type": "json_object"}\` in LLM API calls — local models often fail or wrap the dict in a list; use \`\_extract_json()\` to parse robustly instead

\- Do not write \`affirmations_pool\` via agent \`adjustments\` — it is not in \`\_ADJUSTABLE_PARAMS\`; use \`next_affirmation\` for single-phrase injection or \`write_affirmations_batch\` tool for bulk writes

\- Do not call \`\_expire_locks()\` — it was removed; user locks are permanent within a session and cleared only on restart/seek/load

\- Do not use \`threading.Lock()\` in \`timeline_runner.py\` — the lock is \`threading.RLock()\` (reentrant) because \`\_handle_commands\` and \`load_session\` both acquire it from the same thread

\- Do not run \`python visual_display.py --vr\` directly — there is no \`\__main_\_\` block; the entry point is \`visual_display_runner.py\`

\- Do not add a V-flip via \`setOverlayTextureBounds\` (vMin=1, vMax=0) — the BLIT_VERT shader already flips Y and the image will appear upside-down

\- Do not use \`import ctypes.util\` inside a function that also references the top-level \`ctypes\` module — it shadows the outer name; use \`import ctypes.util as \_cu\`

\- Do not use \`/api/extra/generate_picture\` for KoboldCpp image generation — the correct endpoint is \`/sdapi/v1/txt2img\` (A1111-compatible)

\- Do not hardcode \`True\` as the default when reading \`audio_muted\` from \`live_control.json\` — use \`self.\_beats_muted\` so a failed JSON read preserves the current state rather than killing the waveform

\- Do not set \`width=\` on the three launch buttons (Start Agent / Start Session / Start Beats) — \`uniform="btns"\` grid sizing handles equal width; a \`width=\` constraint fights it and causes text clipping

\- Do not add new panels to the session sidebar column (\`\_col_sessions\`) — it has \`pack_propagate(False)\` and a fixed width; adding content that exceeds the width will not expand the column, it will just clip

\- Do not write \`CONDUCTOR_OWNED_PARAMS\` from LLM \`adjustments\` while the Conductor is active — \`somna_agent.py\` strips them automatically, but adding them to \`\_ADJUSTABLE_PARAMS\` while the Conductor is running will cause confusing no-op writes

\- Do not initialize \`\_idle_last_plan\` to \`0.0\` — initialize to \`time.time()\` to prevent an immediate planning cycle (and potential GPU crash) on agent startup.

\- Do not call \`image_pipeline_cycle\` automatically from idle planning ticks — it is a heavy GPU operation; it must remain explicitly opt-in via \`auto_image_gen: true\` in \`agent_config.yaml\`.

\- Do not implement \`bg_opacity\` via \`pygame.Surface.set_alpha()\` — that blends against black, not transparency. Use the GL fragment shader \`u_opacity\` uniform approach so partial opacity composites correctly against the transparent framebuffer.

\- Do not skip the \`pending_nudge\` staleness check on agent startup — a previous agent process killed mid-nudge leaves a stale \`pending_nudge\` that fires immediately on next start with an incorrect timeout.

\- Do not use SDXL keyword tag soup in FLUX image generation prompts — \`build_conditioning_prompt()\` must output narrative prose sentences, not comma-separated keyword lists.

\- Do not skip \`self.\_pool.update(config)\` before each \`pick()\` in the TTS cook thread — the pool does not self-update and will serve stale phrases indefinitely without an explicit sync call.

\- Do not use \`dict\[str, X\]\`, \`list\[X\]\`, or \`X | Y\` type annotations in runtime positions (method bodies, function signatures) without \`from \__future__ import annotations\` — these fail on Python 3.8/3.9. Use plain \`dict\`, \`list\`, or \`Optional\[X\]\` from \`typing\` instead, or omit annotations entirely.

\- Do not write \`user_settings.json\` keys (\`window_always_on_top\`, \`window_click_through\`, \`tts_voice\`, \`window_geometry\`) only to \`live_control.json\` — they must also be written to \`user_settings.json\` via \`\_save_settings()\` so they survive concurrent write races and restarts.

\- Do not use \`fractionation_phase\` values \`ascending\`, \`holding\`, \`descending\`, or \`pausing\` — the fractionation state machine was rewritten; canonical values are \`INDUCTION\`, \`HOLD\`, \`EMERGE\`, \`EMERGE_HOLD\`, \`REINDUCE\`, and \`DEEP_N\`.

\- Do not trigger \`session_scorer.py\` from \`somna_agent.py\` — the agent is a subprocess with no \`EEGEngine\` reference; scoring must be triggered from \`control_panel_imgui.py\` in \`\_trigger_eeg_scoring()\`.

\- Do not use \`start_stream(buffer_size=450_000)\` keyword form in BrainFlow — newer versions require it as a positional arg: \`start_stream(450_000)\`.

\- Do not call \`EEGEngine.stop()\` synchronously from the UI thread — it joins the BrainFlow thread and will freeze the UI. Use the non-blocking wrapper in \`\_stop_eeg()\` which offloads the join to a background thread.

\- Do not use \`datetime.now()\` when comparing against SQLite \`datetime('now')\` values — SQLite stores UTC; use \`datetime.utcnow()\` to avoid timezone sign errors (e.g. showing −1 days).

\- Do not use \`os.replace()\` for atomic writes to \`live_control.json\` on Windows — when any other process has the file open, \`os.replace()\` silently fails with \`PermissionError\` and the write is lost. Use direct \`open(..., 'w') + json.dump()\` instead.

\- Do not read \`audio_muted\` from \`live_control.json\` inside \`\_toggle_audio_mute\` — use the in-memory \`self.\_beats_muted\` flag instead. Reading from the file inside a toggle introduces a race with the writer thread and can produce incorrect state.

\- Do not add new content to the session sidebar column (\`\_col_sessions\`) beyond the session section — it is \`pack_propagate(False)\` with a fixed \`width\`; adding taller content does not expand the column.

\- Do not write \`user_profile.json\` from \`control_panel_imgui.py\` without doing a reload-first merge (same pattern as \`update_profile()\`) — the agent may be writing concurrently. \`\_save_iaf_to_profile()\` in \`control_panel_imgui.py\` already does this correctly; follow that pattern.

\- Do not write \`eeg_\*\` keys to \`live_control.json\` from anywhere other than \`eeg/eeg_engine.py\` — those keys are owned by the EEG engine exclusively.

\- Do not initialize \`pygame.mixer\` in the display process or the agent process — the mixer is owned exclusively by \`control_panel_imgui.py\`. \`visual_display.py\` sets \`os.environ\['SDL_AUDIODRIVER'\] = 'dummy'\` before \`pygame.init()\`. Adding a second mixer init causes audio clipping and channel conflicts.

\- Do not call \`pygame.mixer.quit()\` from \`BinauralAudioEngine.\_audio_loop\` crash recovery or from \`\_stop_audio\` in \`control_panel_imgui.py\` — that destroys the TTS channels owned by the same mixer instance. Only recreate the specific channels via \`pygame.mixer.Channel(n)\`.

\- Do not check \`audio_muted\` inside \`TTSEngine.poll_ready()\` — TTS is gated only by \`tts_enabled\` and \`tts_subliminal\`. \`audio_muted\` controls binaural + noise only.

\- Do not re-add \`\_check_pending_nudge()\` to \`control_panel_imgui.py\` — the nudge popup that showed raw LLM reasoning verbatim has been intentionally removed. The ghost nudge mechanism in \`somna_agent.py\` still works; only the confusing raw-text dialog is gone.

\- Do not use \`ease: step\` in session YAML — it is not a valid easing mode and silently falls through to \`linear\`. The correct instant-switch value is \`ease: instant\`.

\- Do not trigger Session Zero calibration from a separate sub-FSM or session YAML — it runs inside \`_session_zero_tick()\` in \`somna_agent.py\` as part of the normal first session. The agent manages phase transitions with a simple string state (\`_sz_phase\`).

\- Do not show a TTS-read safety script during Session Zero — the pre-session safety/consent modal is an on-screen ImGui popup (\`_render_session_zero_modal()\`), not a spoken narration. Users tune out long TTS safety briefings.

\---

\## Conductor FSM (\`conductor.py\`)

\> \*\*Design spec: Bible Ch.4 — Session Architecture.\*\* This section covers implementation details only.

\`conductor.py\` implements the Session Conductor FSM. Instantiated by \`somna_agent.py\` at session start, ticked every \`get_tick_rate()\` seconds from the agent's active loop.

\*\*Activation\*\* — \`somna_agent.py\` instantiates \`Conductor\` in \`\_startup_sequence()\` when \`conductor.py\` is importable. If the import fails (e.g., missing dependency) \`\_CONDUCTOR_AVAILABLE\` stays \`False\` and the agent operates without it.

\*\*Parameter ownership\*\* — when the Conductor is active and not in \`session_end\` phase, it is the sole writer of \`CONDUCTOR_OWNED_PARAMS\`:

\`\`\`python

CONDUCTOR_OWNED_PARAMS = frozenset({

"beat_frequency", "veil_mode", "spiral_style",

"shadow_opacity_target", "sr_noise_level", ...

})

\`\`\`

The agent strips these keys from any LLM \`adjustments\` dict before writing. Do not add these params to \`\_ADJUSTABLE_PARAMS\` in a way that lets the LLM write them while the Conductor is active.

\*\*Phases\*\* — \`ConductorPhase\` enum; core arc: \`CALIBRATION\` → \`INDUCTION\` → \`DEEPENING\` → \`MAINTENANCE\`. Fractionation sub-cycle: \`FRAC_EMERGE\` → \`FRAC_EMERGE_HOLD\` → \`FRAC_REDROP\`. Sleep path: \`SLEEP_APPROACH\` → \`SLEEP_ONSET\` → \`SLEEP_MAINTAIN\` → \`SLEEP_TRAINING\` → \`SLEEP_WAKE\`. Phase transitions are written to \`live_control.json\` as \`conductor_phase\` for the UI and agent to read.

\*\*EEG integration\*\* — the Conductor reads \`eeg_\*\` keys from \`live_control.json\` on every tick. Without EEG it falls back to a timer-based schedule. Degraded mode activates when \`eeg_confidence = "none"\` for all channels.

\*\*Decision log\*\* — all Conductor decisions are accumulated in \`\_decision_log\` and flushed to \`somna.db\` via \`write_conductor_decisions_batch()\` on \`finalize()\`. Call \`conductor.finalize()\` in the agent's session teardown.

\*\*\`conductor_summary\`\*\* — written to \`live_control.json\` by the agent after each Conductor tick as a dict for downstream consumers (UI, LLM context).

\*\*\`agent_conductor_hints\`\*\* — written to \`live_control.json\` by \`SomnaAgent.\_write_conductor_hints()\` at session start. Read by the Conductor on every tick. Fields:

\- \`depth_patience\` (float, default 1.0) — multiplier applied to all \`\_hold_met()\` thresholds. Derived from \`trend_metric("transition_speed_sec")\`: if the user historically takes 240 s to transition, patience ≈ 1.25; if 120 s, patience ≈ 0.75. Clamped to \[0.25, 2.5\].

\- \`request_fractionation\` (bool) — if True and fractionation is otherwise eligible (elapsed > 180 s, count < max, DEEPENING/MAINTENANCE phase), the Conductor triggers a fractionation immediately and clears the flag. The agent sets this when it detects depth signals in console input (keywords: "deep", "gone", "under", "floating", "blank", etc.).

\- \`target_floor_hz\` (float | null) — preferred MAINTENANCE beat frequency. The Conductor nudges toward this at 0.1 Hz/tick when no \`nudge_frequency\` adjustment is active. Clamped to \[3.5, 8.0\].

\- \`note\` (str) — appended to the rationale field of every conductor decision log entry for this session.

\*\*Post-session agent annotation\*\* — after \`\_idle_planning_cycle(mode="post_session")\` runs, the LLM's \`reasoning\` field is written to the \`agent_notes\` column of the most recent \`session_metrics\` row for that session via \`somna_db.update_latest_session_notes()\`. No-op if no EEG session row exists.

\---

\## Adaptive frequency leading (\`freq_leader.py\`)

\> \*\*Design spec: Bible Ch.3 — Audio and Entrainment.\*\* This section covers implementation details only.

\`FreqLeader\` implements the meet-and-lead protocol. Runs as a background thread inside \`somna_agent.py\`. Reads \`eeg_dominant_band\` and \`eeg_trance_score\` from \`live_control.json\`; falls back to timer-based schedule when EEG is unavailable.

\*\*Live keys written:\*\* \`freq_lead_phase\`, \`freq_lead_current\`, \`freq_lead_steps\`, \`freq_lead_holds\`. These are read by \`control_panel_imgui.py\` at session stop time for scoring and by the agent's state summary.

\*\*Session scoring\*\* (\`session_scorer.py\`) — \`SessionScorer\` takes \`eeg_session_data\` from \`EEGEngine.get_session_data_for_scoring()\` and \`freq_lead_data\` from the FreqLeader live keys. It writes a row to \`somna.db\` \`session_metrics\` table and \`conductor_decisions\` table. Triggered by \`control_panel_imgui.py\` → \`\_trigger_eeg_scoring()\` when display stops.

\---

\## Session / beats lifecycle

\`\_launch_display()\` and \`\_stop_display()\` in \`control_panel_imgui.py\` own the session lifecycle.

\*\*Beats on session start\*\* — \`audio_muted\` is in \`timeline_runner.py\`'s \`APP_DEFAULTS\` as \`False\`. When a session loads, the timeline runner writes \`audio_muted: False\` on the first tick, which starts the beats. Starting a session always starts the beats unless a session keyframe overrides it.

\*\*Beats on session stop\*\* — \`\_stop_display()\` writes \`audio_muted: True\` and calls \`\_refresh_mute_btn()\`. Stopping a session always silences the beats.

- **"Start Beats" / "Stop Beats" button** — an ImGui button in the transport bar. It is the sole user-facing binaural on/off control, replacing the old transport-bar 🔊 icon. `_toggle_audio()` toggles the `audio_muted` key. The underlying key is `audio_muted` in `live_control.json`.

\*\*TTS is independent of \`audio_muted\`\*\* — \`TTSEngine.poll_ready()\` ignores \`audio_muted\`; it only gates on \`tts_enabled\` and \`tts_subliminal\`. Muting binaural beats never silences the agent's voice.

\*\*\`poll_ready(session_active)\` parameter\*\* — \`control_panel_imgui.py\`'s \`\_poll_audio()\` passes \`session_active\` based on whether \`display_active\` is True. When \`session_active=False\`, the regular affirmation pool is not drained; one-shot agent prompts (\`\_prompt_ready\`) still play regardless. This prevents TTS from reading affirmations when no session is running.

\*\*\`audio_muted\` default safety\*\* — \`\_refresh_mute_btn()\` and \`\_load_current_values()\` both use \`self.\_beats_muted\` as the fallback when \`audio_muted\` is absent from the JSON (e.g., during a mid-write race). Never use a hardcoded \`True\` default for this key in either function — that would kill the waveform any time the JSON is momentarily unreadable.

\---

\## EEG Engine (\`eeg/eeg_engine.py\`)

\> \*\*Design spec: Bible Ch.2 — Biosignal Science.\*\* This section covers implementation details only.

Acquires EEG via BrainFlow, processes band powers, and writes results to \`live_control.json\` as read-only keys. Import as \`from eeg.eeg_engine import EEGEngine\`.

\*\*Pattern:\*\* Same as \`timeline_runner.py\` — background thread started from \`control_panel_imgui.py\` via the "Connect EEG" button, writes to \`live_control.json\` via \`\patch_live()\`.

\*\*Secondary thread state publication\*\* — secondary threads inside \`eeg_engine.py\` (e.g., the calibration thread) must NOT call \`\patch_live()\` directly. Instead they write into an in-memory dict (\`self.\_cal_state\`). The main EEG loop merges \`self.\_cal_state\` into every tick write via a single \`\patch_live()\` call. This is the correct pattern for any background thread that needs to publish state — it keeps all file I/O on a single thread and prevents concurrent write collisions.

\*\*\`json.dump\` indent\*\* — all EEG engine writes to \`live_control.json\` use \`indent=2\` for consistency with the rest of the codebase. Any new \`\patch_live()\` or direct JSON write in \`eeg_engine.py\` must use \`indent=2\`.

\*\*SQI warmup\*\* — \`SQITracker\` has an 8-second post-connect warmup period (\`\_warmup_ticks\`). During warmup, quality is reported as \`"warming"\` instead of the normal confidence tier. The warmup counter resets on each reconnect. This prevents false "unusable" quality immediately after BLE connection before the signal settles. The composite SQI is a plain mean of all four channel SQIs — a trimmed-mean approach was tried and reverted because masking the worst channel hides real signal problems without fixing the underlying noise.

\*\*Phase 0:\*\* \`SYNTHETIC_BOARD (-1)\` — generates synthetic alpha at ~10 Hz. No hardware needed. Set \`eeg.synthetic: true\` in \`agent_config.yaml\` (default).

\*\*Board IDs:\*\*

\- \`38\` = \`MUSE_2_BOARD\` — native BLE, no dongle

\- \`39\` = \`MUSE_S_BOARD\` — soft sleep headband, recommended for lying-down sessions

\- Never use \`22\` (\`MUSE_2_BLED_BOARD\`) — requires a $30 BLED112 USB dongle

\*\*EEG keys written to \`live_control.json\` (read-only, owned by \`eeg/eeg_engine.py\`):\*\*

| Key | Type | Description |

|-----|------|-------------|

| \`eeg_connected\` | bool | Board session active |

| \`eeg_quality\` | str | \`"good"\` / \`"poor"\` / \`"unusable"\` (legacy compat; derived from \`eeg_confidence\`) |

| \`eeg_confidence\` | str | SQI confidence gate: \`"full"\` / \`"reduced"\` / \`"low"\` / \`"none"\` — trust level for all metrics |

| \`eeg_sqi_tp9\` | float | SQI 0–1 for TP9 channel (EMA smoothed, alpha=0.3) |

| \`eeg_sqi_af7\` | float | SQI 0–1 for AF7 channel |

| \`eeg_sqi_af8\` | float | SQI 0–1 for AF8 channel |

| \`eeg_sqi_tp10\` | float | SQI 0–1 for TP10 channel |

| \`eeg_sqi_composite\` | float | Mean of four channel SQIs; > 0.7 = clean signal |

| \`eeg_sqi_usable_channels\` | int | Count of channels with SQI ≥ 0.5 |

| \`eeg_dominant_band\` | str | \`"delta"\` / \`"theta"\` / \`"alpha"\` / \`"beta"\` / \`"gamma"\` |

| \`eeg_delta\` | float | Delta proportion (0.5–4 Hz), 0.0–1.0 |

| \`eeg_theta\` | float | Theta proportion (4–8 Hz), 0.0–1.0 |

| \`eeg_alpha\` | float | Alpha proportion (8–13 Hz), 0.0–1.0 |

| \`eeg_beta\` | float | Beta proportion (13–30 Hz), 0.0–1.0 |

| \`eeg_gamma\` | float | Gamma proportion (30–50 Hz), 0.0–1.0 |

| \`eeg_gamma_40hz\` | float | Narrow 38–42 Hz power (GENUS monitoring) |

| \`eeg_alpha_theta_ratio\` | float | Alpha/theta — wakeful indicator |

| \`eeg_beta_alpha_ratio\` | float | Beta/alpha — alertness indicator |

| \`eeg_frontal_asymmetry\` | float | ln(AF8_alpha) − ln(AF7_alpha) |

| \`eeg_trance_score\` | float | 0.0–1.0 composite depth index (SEF95 40% + spectral slope 30% + theta/alpha 30%) |

| \`eeg_state\` | str | \`"awake"\` / \`"relaxed"\` / \`"trance"\` / \`"n1_entry"\` / \`"n1"\` / \`"n2_warning"\` |

| \`eeg_sef95\` | float or null | Spectral Edge Frequency 95% in Hz (EMA smoothed, tau≈4s); high=alert, low=deep |

| \`eeg_spectral_slope\` | float or null | 1/f power spectrum slope (negative; steeper=deeper, e.g. −2.5 = trance) |

| \`eeg_iaf_hz\` | float or null | Individual Alpha Frequency (null until calibrated) |

| \`eeg_needs_iaf_calibration\` | bool | Set true when IAF is unknown at startup |

| \`eeg_entrainment_strength\` | float | Coherence-augmented ASSR locking strength 0–1 (0.70×power + 0.30×coherence; 0.1=emerging, 0.3=established, 0.6=strong) |

| \`eeg_entrainment_power_strength\` | float | Power-only component of ASSR before coherence blending |

| \`eeg_entrainment_coherence\` | float | Mean inter-channel coherence at beat frequency (TP9↔TP10 and AF7↔AF8 averaged) |

| \`eeg_entrainment_coherence_tp\` | float or null | TP9↔TP10 coherence at beat frequency (null when SQI < full) |

| \`eeg_entrainment_coherence_af\` | float or null | AF7↔AF8 coherence at beat frequency (null when SQI < full) |

| \`eeg_entrainment_confidence\` | str | \`"active"\` / \`"alpha_overlap"\` / \`"unavailable"\` |

| \`eeg_entrainment_trend\` | str | \`"rising"\` / \`"stable"\` / \`"declining"\` / \`"absent"\` / \`"insufficient_data"\` |

| \`eeg_entrainment_beat_freq\` | float | Beat frequency used for the last ASSR measurement |

| \`eeg_entrainment_channel_agreement\` | str | \`"high"\` / \`"moderate"\` / \`"low"\` / \`"insufficient_channels"\` |

| \`eeg_entrainment_recommend_modality\` | str or null | Set by engine when binaural ASSR absent 2× → \`"isochronic"\`; agent acts on it |

| \`eeg_entrainment_recommend_reason\` | str or null | Human-readable explanation of modality recommendation |

| \`eeg_timestamp\` | float | Wall time of last valid EEG update |

\*\*Calibration microfeedback keys\*\* — written by \`run_iaf_calibration()\` every 5 s during calibration and cleared on completion:

| Key | Values |

|-----|--------|

| \`calibration_status\` | \`"recording"\` / \`"extending"\` / \`"done"\` / \`"failed"\` |

| \`calibration_iaf_hz\` | float or null — running IAF candidate |

| \`calibration_iaf_confidence\` | float 0–1 |

| \`calibration_channel_sqi\` | dict \`{tp9, af7, af8, tp10}\` smoothed SQI values |

| \`calibration_hint\` | str — actionable text or \`""\` |

| \`calibration_time_remaining_s\` | int |

\*\*IAF calibration\*\* — \`EEGEngine.run_iaf_calibration(duration_s=30.0)\` runs a progressive confidence-gated loop that ticks every 5 s. \`detect_iaf_with_confidence()\` returns \`(iaf_hz, confidence, detail)\` where \`confidence\` is a weighted blend of peak prominence (25%), inter-channel agreement (40%), and temporal stability half-vs-full window (35%). At the end of the initial window: conf ≥ 0.65 → accept; 0.35–0.64 → extend 15 s; < 0.35 → fallback. After the extension the loop runs to max_duration and accepts the best candidate. Results are saved to \`user_profile.json\` via \`\_save_iaf_to_profile()\` in \`control_panel_imgui.py\` — includes \`iaf_hz\`, \`iaf_confidence\`, \`iaf_calibrated_at\`, and \`iaf_band_boundaries\`. Do NOT call \`update_profile()\` from \`control_panel_imgui.py\` directly (different process).

\*\*Agent integration\*\* — \`\_state_summary()\` in \`somna_agent.py\` appends EEG state when \`eeg_connected\` is true. The agent sees \`iaf=X.XX(cal_conf=0.72)\` in the state line; when \`iaf_confidence < 0.50\` a warning is added so the agent knows band boundaries are estimates only. \`eeg_entrainment_recommend_modality\` is surfaced with a warning symbol when non-null so the agent knows to act.

\*\*SQI gating\*\* — \`eeg_confidence\` must be \`"full"\` or \`"reduced"\` for band power metrics to be written. At \`"none"\`, only the SQI keys are written. All SEF95/slope computations require \`"reduced"\` or better. ASSR computation requires \`"full"\` only. Coherence components are only computed at \`"full"\` SQI (all 4 channels clean). The EEG engine automatically prompts the user to adjust the headband (via \`agent_message\`) after 60 consecutive seconds of \`"none"\` quality.

\*\*ASSR timing\*\* — first result available at 60 s into session; subsequent updates every 30 s when SQI is \`"full"\`. The engine uses frontal-weighted channel averaging (AF7/AF8 weighted at 0.35 each, TP9/TP10 at 0.15). Beat-frequency alpha overlap is flagged in \`eeg_entrainment_confidence\` as \`"alpha_overlap"\` and applies a 30% composite penalty — normal; don't alarm on it.

\*\*\`agent_config.yaml\` \`eeg:\` block:\*\*

\`\`\`yaml

eeg:

enabled: true # set false to run without EEG hardware or synthetic board

synthetic: true # SYNTHETIC_BOARD for dev; false = real hardware

board_id: 39 # 39=MUSE_S, 38=MUSE_2

auto_connect: false

\`\`\`

\`eeg.enabled\` propagates to \`AgentConfig.eeg_enabled\` and is passed to \`Conductor.\__init_\_\`. When \`False\`, the Conductor immediately sets \`\_timer_mode = True\` so it never waits for EEG data that will not arrive. When \`True\`, \`\_build_knowledge_files()\` also appends \`eeg_entrainment.md\`, \`faa_receptivity.md\`, and \`adaptive_frequency_leading.md\` to the session-time knowledge list.

\---

\## Imagery detection (\`somna_agent.py\` — \`\_imagery_detection_flow\`)

One-time console question that discovers whether the user has voluntary mental imagery (aphantasia screening). Fires:

1\. At the end of first-run \`\_onboarding_flow()\`

2\. At the start of \`run()\` for any existing user whose profile lacks the \`aphantasia\` key

Uses accessible language (no clinical jargon). The response is passed through a second LLM extraction call that maps free text to \`{"imagery_status": "none"|"minimal"|"moderate"|"vivid"}\`. Result is written to \`user_profile.json\` under the \`aphantasia\` key via \`\_update_profile()\`.

The condition is self-healing: deleting or resetting \`user_profile.json\` will cause the question to re-fire on next run and reconstruct the block.

\---

\## Learned User Preferences

\- The user has aphantasia (\`aphantasia: "none"\` in \`user_profile.json\`); always follow \`knowledge/aphantasia.md\` — no imagery-based inductions, sensation anchors only, descriptive language instead of visual metaphors.

\- The user prefers surgical targeted edits over full-file rewrites; match fix scope to the actual problem.

\- The user gives accurate bug reports — if they say "it only happens when I click X first", treat that as ground truth, not coincidence.

\- The user tests immediately and reports results concisely; act on feedback without re-explaining the previous fix.

\- After completing a task, always think through what logically follows and surface it — don't just report completion. Consider: what's the next high-value gap? What did the work just done reveal? What would break in production? Name a concrete next direction and either start it or ask if that's where the user wants to go.

\- PII (name, designation) has been deliberately scrubbed from all knowledge files and docs; use "the user" in any new documentation or knowledge file content.

\## Learned Workspace Facts

\- The project was previously named \*\*HypnoSlide\*\* before being renamed to \*\*Somna\*\*; the ported HypnoSlide transcript is available as \`f585d737-7913-4141-8793-c8b5913dfd70\` in agent-transcripts.

\- \`ui/panel_theme.py\` exports \`token_rgba(name)\` which looks up \`COLOR_TOKENS\`, not the raw \`RP\` palette dict. Do not pass raw RP keys like \`"text"\` or \`"iris"\` — use the semantic token names. The complete valid set is: \`"app_bg"\`, \`"panel_bg"\`, \`"panel_bg_solid"\`, \`"section_header_bg"\`, \`"section_header_bg_hovered"\`, \`"section_header_bg_active"\`, \`"widget_frame_bg"\`, \`"widget_frame_bg_hovered"\`, \`"widget_frame_bg_active"\`, \`"separator"\`, \`"scrollbar_bg"\`, \`"scrollbar_grab"\`, \`"scrollbar_grab_hovered"\`, \`"scrollbar_grab_active"\`, \`"tooltip_bg"\`, \`"tooltip_border"\`, \`"text_primary"\`, \`"text_muted"\`, \`"text_disabled"\`, \`"text_label"\`, \`"text_value"\`, \`"text_section_summary"\`, \`"slider_grab"\`, \`"slider_grab_hovered"\`, \`"slider_grab_active"\`, \`"checkbox_check"\`, \`"button_bg"\`, \`"button_bg_hovered"\`, \`"button_bg_active"\`, \`"progress_bar_fill"\`, \`"alert_red"\`, \`"alert_red_bg"\`, \`"warning_amber"\`, \`"warning_amber_bg"\`, \`"success_green"\`, \`"status_strip_bg"\`, \`"debug_banner_bg"\`, \`"debug_banner_text"\`, \`"source_agent"\`, \`"source_director"\`, \`"source_user_lock"\`, \`"gauge_low"\`, \`"gauge_mid"\`, \`"gauge_high"\`, \`"gauge_track"\`. Raw RP keys (\`RP["text"]\`, \`RP["iris"]\`, etc.) are only valid when used directly, e.g. in Tkinter code or raw \`imgui.ImVec4\` calls via \`hex_to_rgba\`.

\- ImGui flag names to remember: \`ChildFlags_.borders\` (not \`border\`), \`SelectableFlags_.none\`, \`HoveredFlags_.delay_short\`, \`WindowFlags_.no_resize\`. Always introspect unknown flags with \`python -c "from imgui_bundle import imgui; print([x for x in dir(imgui.XFlags_) if not x.startswith('__')])"\` before using them.

\- \`peek.py\` and \`patch.py\` exist in the project root as live testing helpers — \`peek.py\` prints key live_control.json values, \`patch.py\` has commented blocks for injecting test values into a running session.

\- \`smoke_test.py\` at the project root runs 153 automated checks covering Bible Ch.2–Ch.8; run from \`F:\\Somna\` before any hardware testing session to catch regressions.

\- TMR pool names in \`tmr_cue_manager.py\` are UPPERCASE (\`IDENTITY\`, \`RELEASE\`, \`POTENTIAL\`, \`SOMATIC\`, \`PURPOSE\`, \`TRANSITION\`); passing a lowercase string silently falls back to \`POOL_SIGNATURES\["IDENTITY"\]\`.

\- The \`sessions\` DB table uses \`name\` as TEXT PRIMARY KEY (not \`session_id\`); all cross-table references (\`conductor_decisions\`, \`session_metrics\`, \`content_cascades\`, etc.) use \`session_id TEXT NOT NULL\` without FK constraints — follow this pattern for all new tables.

\- The **Interference Graph / Somatic Palette Mixer** lives in three files: \`ui/interference_graph.py\` (pure data model — no ImGui), \`ui/interference_graph_panel.py\` (ImGui renderer), and \`ui/interference_graph_integration.py\` (wiring). Call \`install_interference_graph(panel_manager)\` once after creating the \`ControlPanelManager\` — that is the single entry point; no JSON config edits required. It returns \`(graph, ig_panel)\` for direct access.

\- \`ControlPanelManager.set_section_extra(section_name, fn)\` registers a canvas-only render callback for a named section. Sections that have a \`set_section_extra\` entry but **no widgets** are now surfaced via \`sections.setdefault(_sec, [])\` in both \`_render_sections\` and \`_render_spill_sections\` so they get a header row and their canvas rendered without any dummy widget in \`panel_config.json\`.

\- Interference Graph drag state is instance-level (stored on \`InterferenceGraphPanel\`), not module-level. Node dragging uses \`imgui.is_mouse_dragging\` / \`imgui.get_mouse_drag_delta\` keyed to the node's channel; always reset delta with \`imgui.reset_mouse_drag_delta\` at the start of each drag frame to avoid accumulated drift.

\- Spread in the Interference Graph applies a per-channel offset **on top of each channel's individual base frequency**, not on top of a shared center. Changing spread does not move the chord root.

\- Bezier tether "bow" in the Interference Graph panel uses a mid-point control offset proportional to distance so close nodes get a subtle arc and distant nodes get a pronounced curve — do not use a fixed bow constant.

\- Glow render order in the Interference Graph: draw the glow stroke (wide, low alpha) **before** the solid line stroke (narrow, full alpha) so the glow doesn't overdraw the line.

\- Unavailable hardware channels (Haptic, VNS) in the Interference Graph are rendered at reduced opacity and block drag interaction; their nodes are still tracked in the data model for future hardware integration without schema changes.