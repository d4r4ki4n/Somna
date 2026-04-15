# \# Somna — Roadmap

Last updated: April 2026 — Somna Bible complete (11 chapters, 22 artifacts, 309 sections).

Authority rule:

The Somna Bible is the canonical design specification. This roadmap tracks implementation status against the Bible. For architectural rationale, design intent, or detailed specs, refer to the cited Bible chapter and section. This file tracks

what is built

and

what to build next

.

## \## ✅ Recently Shipped

### \### Core Runtime

_Design spec: Bible Ch.1 (Processing Stack), Ch.4 (Session Architecture)_

| **Feature** | **Notes** |
| --- | --- |
| Session transport redesign | Seek bar, emoji transport row, loop/shuffle/mute, queue divider as status |
| --- | --- |
| Timeline user locks | Slider overrides survive timeline ticks; gold label; clears on seek/restart |
| --- | --- |
| Playlist runner | sequential / loop / loop_one / shuffle; auto-advance; ◀◀ ▶▶ skip |
| --- | --- |
| Transparent overlay | bg_mode: none + WS_EX_LAYERED; per-pixel alpha; click-through |
| --- | --- |
| Veil: Tunnel mode | Phrases spawn at center, scale outward with perspective |
| --- | --- |
| Binaural audio gradient updates | < 2 Hz changes update in-place (no crossfade = no clicking) |
| --- | --- |
| Background image optimization | Session-aware lazy loading, 200-image cap, periodic resampling |
| --- | --- |
| Image presence detection | has_images property; bg_mode auto-toggles on session change |
| --- | --- |
| SteamVR overlay (vr_overlay.py) | OpenVR + ModernGL FBO; HMD-relative floating panel |
| --- | --- |
| SSB silent subliminals | Lowry SSB-AM at 14–20 kHz; independent of audible TTS |
| --- | --- |
| Session editor | Visual Tkinter timeline editor (session_editor.py) |
| --- | --- |
| Isochronic tones | Raised cosine AM; beat_type: isochronic or both |
| --- | --- |
| Breath modulation | Carrier AM at breathing rate; breath_mod / breath_rate / breath_depth keys |
| --- | --- |

### \### Hardware Output Channels

_Design spec: Bible Ch.1 §8, Ch.2 §12–§13, Ch.4 §9, Ch.6 §4–§8_

| **Feature** | **Notes** |
| --- | --- |
| Lovense BLE driver (haptic_engine.py) | buttplug-py protocol; BLE auto-discovery; 7 pattern types; background thread at 10 Hz; ping-back validation |
| --- | --- |
| DG Labs Coyote BLE driver (tavns_engine.py) | pydglab-v3; 2-channel A/B output; mandatory impedance check < 5 kOhm; continuous impedance monitoring; instant shutoff on contact loss |
| --- | --- |
| Shared safety enforcer (device_safety.py) | DeviceSafetyEnforcer: unlock tiers (sessions 5/7+), intensity ceilings, ramp rates, sleep-stage gating, emergency stop, comfort calibration |
| --- | --- |
| Haptic/taVNS gain channel activation | crossmodal_gain.py haptic+tavns entries in all 4 sleep gain profiles; gain drives actual device output |
| --- | --- |
| Conductor haptic/taVNS integration | Phase-aware intensity profiles for all 14 phases; INDUCTION conditioned anchor; fractionation patterns; emergence fade |
| --- | --- |
| Haptic conditioning delivery | Phase-gated vibrotactile reinforcement; TMR haptic cue alongside audio replay; conditioned anchor encoding at trance > 0.75 |
| --- | --- |
| live_control.json haptic/taVNS keys | 26 keys: haptic_connected, tavns_connected, intensities, patterns, waveforms, impedance, safety state, comfort ceilings |
| --- | --- |
| ImGui hardware controls | 13 widgets: Connect/Disconnect, intensity sliders, pattern/waveform dropdowns, impedance/ping buttons, sleep N1/N2 toggle |
| --- | --- |
| Interference Graph hardware nodes | Haptic/VNS nodes transition from dimmed to interactive when BLE devices connect |
| --- | --- |
| Agent param stripping | LLM adjustments for haptic/tavns params suppressed when Conductor active + hardware connected |

### \### Agent & AI Layer

_Design spec: Bible Ch.5 (Agent Intelligence), Ch.6 (Conditioning and Content)_

| **Feature** | **Notes** |
| --- | --- |
| LLM session agent (somna_agent.py) | observe + interactive modes, JSONL logs, profile, fresh-start logic |
| --- | --- |
| Agent skip streak tracking | Distinguishes user skips from agent silent turns in LLM context |
| --- | --- |
| Floating prompt overlay | AgentPromptLayer renders question in-display as zooming text |
| --- | --- |
| Per-prompt visual styling | llm_prompt_style: hex colors, font, intensity, zoom_speed |
| --- | --- |
| Per-prompt voice mode | voice_mode: tts / subliminal / both / silent |
| --- | --- |
| Pitch + rate control | edge-tts pitch / rate per agent prompt |
| --- | --- |
| Beat-frequency AM | beat_mod: true — voice amplitude pulses at entrainment freq |
| --- | --- |
| Simple reverb | reverb: true — 80 ms echo for spacious deepeners |
| --- | --- |
| Display-only messages | needs_response: false — overlay text, no dialog popup |
| --- | --- |
| Agent gradual transitions (RampEngine) | LLM declares transitions: {param: seconds}; 1 Hz ramp thread interpolates |
| --- | --- |
| Idle planning merged into agent | somna_heartbeat.py deleted; idle mode folded directly into somna_agent.py |
| --- | --- |
| Agent idle planning cycle | LLM planning cycle on configurable interval (default 30 min) when no session is active |
| --- | --- |
| Agent nudge system | Opacity-ramping nudge overlay; LLM-generated personalised invitation |
| --- | --- |
| Agent idle tool dispatch | Agent can call write_affirmations_batch, generate_images, tag_stats from idle mode |
| --- | --- |
| Live Agent Console | user_console_input / agent_console_response bus; session launch from console |
| --- | --- |
| Content generation studio (content_agent.py) | Interactive CLI for session/affirmation/image authoring |
| --- | --- |
| Content agent config unification | Reads base_url + model from agent_config.yaml; no env var setup needed |
| --- | --- |
| Knowledge base injection | Multiple knowledge files; active session and idle planning use separate sets |
| --- | --- |
| Agent→Conductor hints | agent_conductor_hints bus: depth_patience, target_floor_hz, request_fractionation |
| --- | --- |
| Conductor phase arc in agent context | phase_arc, phase_duration_s, trance_trend_per_min injected into agent state |
| --- | --- |
| image_filter_override conditioning hook | Agent can lock visual pool to a theme tag for a fixed duration; background.py hot-resamples |
| --- | --- |
| Post-session agent annotation | Agent writes a brief observation to somna.db session_metrics after each session |
| --- | --- |
| Hypnosis theory knowledge injection | Three-layer voice model (guide / fill / inscribe) in active + idle agent context |
| --- | --- |

### \### Memory & Profile

_Design spec: Bible Ch.5 (Agent Intelligence §13–§16)_

| **Feature** | **Notes** |
| --- | --- |
| User profile system | user_profile.json — name, designations, goals, notes, engagement |
| --- | --- |
| Cross-session memory: last_session | deepest beat, best complexity, phase, notable phrases — injected on next session |
| --- | --- |
| Cross-session memory: effective_moments | logs beat/spiral/label/affirmation at depth; injected as context |
| --- | --- |
| Cross-session memory: responsive_themes | agent accumulates themes user responds deeply to across sessions |
| --- | --- |
| profile_updates output field | LLM can write to profile mid-session in any turn |
| --- | --- |
| last_session_date tracking | Updated by somna_agent on every active tick; idle nudge threshold uses it |
| --- | --- |

### \### Image System

_Design spec: Bible Ch.6 (Conditioning and Content §14–§18)_

| **Feature** | **Notes** |
| --- | --- |
| Vision-model image tagging | content_tools/image_tags.py; KoboldCpp mmproj; somna.db storage |
| --- | --- |
| Controlled vocabulary tags | conditioning theme, explicitness, style |
| --- | --- |
| Open-tags folksonomy | Free-form tags (feet, nurse, latex, vr-headset…) — emerge from library organically |
| --- | --- |
| Caption text extraction | Vision model reads text overlays verbatim |
| --- | --- |
| Background tag filtering | background.py filters image pool by timeline_label + open_tags |
| --- | --- |
| Image generation (KoboldCpp FLUX) | A1111-compatible /sdapi/v1/txt2img; 8 visual templates; natural language prompts |
| --- | --- |
| Caption harvest to affirmations | Extracts caption text into affirmations.txt; noise filter rejects watermarks/URLs |
| --- | --- |
| image_pipeline_cycle | Self-improving idle-time loop: tag → prompt engineer → generate → vision review → promote |
| --- | --- |

### \### Agent Tool Calling

_Design spec: Bible Ch.5 (Agent Intelligence §8–§12)_

| **Tool** | **What it does** |
| --- | --- |
| tag_stats | Image library overview with top controlled + organic tags |
| --- | --- |
| images_for_tag | Filenames for any tag (controlled or organic) |
| --- | --- |
| read_session_log | Past exchanges N days back — structured summaries |
| --- | --- |
| read_session_content | Current session.yaml + affirmations.txt |
| --- | --- |
| list_sessions | All session folder names |
| --- | --- |
| cull_session | Images flagged low-quality |
| --- | --- |
| write_affirmations_batch | Batch-write custom phrases to a phase tag |
| --- | --- |
| generate_images | FLUX image generation on demand |
| --- | --- |
| harvest_captions | Harvest image captions to affirmations |
| --- | --- |
| auto_tag_session | Trigger vision tagging from agent context |
| --- | --- |
| write_session_yaml | Author or rewrite a session.yaml |
| --- | --- |
| write_affirmations | Write a full affirmations.txt |
| --- | --- |
| generate_image | Single-image generation with full conditioning prompt control |
| --- | --- |
| image_pipeline_cycle | One full self-improving generation + review cycle |
| --- | --- |
| query_session_performance | Longitudinal session metrics from somna.db; trend + best config |
| --- | --- |
| find_images_by_theme | Cross-session image search by tag across all sessions |
| --- | --- |
| audit_affirmations | LLM-powered phrase audit: cull weak, chain with >>, group with \|, retag |
| --- | --- |

### \### EEG Integration

_Design spec: Bible Ch.2 (Biosignal Science), Ch.4 (Session Architecture §8–§12)_

| **Feature** | **Notes** |
| --- | --- |
| BrainFlow acquisition (eeg_engine.py) | Muse 2 (board_id=38), Muse S (39), synthetic board for dev |
| --- | --- |
| Band power extraction | Alpha, theta, beta, delta, gamma relative powers at 1 Hz |
| --- | --- |
| IAF calibration | Resting eyes-open calibration; stored in user_profile.json |
| --- | --- |
| ASSR tracking | Auditory steady-state response — confirms entrainment at beat frequency |
| --- | --- |
| Trance score | Composite depth metric written to live_control.json as eeg_trance_score |
| --- | --- |
| Conductor FSM (conductor.py) | Phase-based session orchestration: calibration → induction → deepening → maintenance |
| --- | --- |
| EEG-driven phase transitions | Conductor advances phases based on trance score, ASSR confidence, hold timers |
| --- | --- |
| Fractionation protocol | Conductor can trigger fractionate → emerge → reinduce cycles |
| --- | --- |
| Session scoring | session_metrics in somna.db; composite score, depth, entrainment, receptivity |
| --- | --- |
| Calibration protocol | Bible Ch.2 §7–§9. First-10-sessions personal neurophysiological baseline; calibration_manager.py; gates phase transitions |
| --- | --- |
| SEF95 personal depth range | Calibration-derived SEF95 floor/ceiling replaces population defaults in scorer |
| --- | --- |
| SSVEP in-thread plugin | eeg_engine.py feeds raw AF7/AF8 to SSVEPDetector each tick; writes ssvep_\* keys |
| --- | --- |
| Phase-cascade delivery | Bible Ch.3 §6, Ch.4 §10. respiratory_hot AND alpha_at_trough gate; DeliveryGate degradation ladder; spiral convergence pulse |
| --- | --- |
| Semantic content selection | Bible Ch.6 §8–§10. Six EEG-state content pools; cross-layer priming cascade (shadow → center → voice); per-user pool weights |
| --- | --- |
| Three-axis depth estimation | Bible Ch.2 §4–§6. Spectral slope (aperiodic E/I proxy) + interhemispheric coherence + beta envelope correlation; eeg_trance_score_v2; convergent evidence rule for phase transitions; depth logged at 10 s intervals |
| --- | --- |
| Crossmodal gain manifold | Bible Ch.2 §12, Ch.6 §6. CrossmodalGainEngine; depth_gain_scalar scales all five channels as trance deepens; SR inverted-U boosts text opacity at optimal noise; carrier-noise protection; SR calibration sweep during CALIBRATION phase |
| --- | --- |
| Closed-loop sleep enhancement | Bible Ch.7 §3–§8. SleepStageClassifier (Butterworth+Hilbert decision tree, WAKE/N1/N2/N3/REM); SpindleDetector (sigma band, 30-s rolling density); SlowWaveEnhancer (phase-locked 50 ms pink noise bursts at delta up-state, Ngo 2013); alpha anti-phase disruption for sleep onset acceleration (Bressler 2024); SLEEP_MAINTAIN + SLEEP_WAKE Conductor phases; trance-to-sleep fork detection (convergent evidence); sleep gain profiles; 70 ms burst envelope on audio channel 3; 1 FPS visual idle; sleep_stage_log + sleep_calibration tables; sessions/sleep_default YAML |
| --- | --- |
| Targeted memory reactivation | Bible Ch.7 §9–§13. CueManager (six pool signatures; deterministic MD5 hash jitter; no audio files); TMREngine + ConsolidationScheduler (inverted-U priority model; 20 cues/hr budget; 30 s min interval; SWE lockout coordination); trance encoding hook in Conductor (150 ms cue-before-affirmation delay; DB upsert); NREM replay on N2/N3; EEG-loss safety shutdown (5-min lockout; clears sleep stimulation flags); audio channel 6 for TMR; eeg_signal_lost published by EEG engine; tmr_cue_registry + tmr_encoding_log + tmr_replay_log tables |
| --- | --- |
| Muse 2 PPG + IMU integration | Bible Ch.2 §10–§11. PPGEngine (ANCILLARY_PRESET IR channel; R-peak detection; IBI → HR + RMSSD; RSA spectral method → ppg_breath_rate + ppg_breath_phase); IMUEngine (AUXILIARY_PRESET accel; motion RMS + stillness EMA + head-nod Y-drift); RespiratoryTracker upgraded to PPG mode (update_ppg_phase(); respiratory_mode key); DeliveryGate motion-contamination block; both engines lazy-init on hardware board only — synthetic board unaffected |
| --- | --- |
| Hypnagogic Training Window | Bible Ch.7 §14–§16. Phase.SLEEP_TRAINING Conductor phase; HTW eligibility gate; \_htw_eligible() + \_select_training_phrases() + \_presynth_training_phrases() + \_enter_sleep_training() + \_exit_sleep_training(); TTS pre-synthesis buffer; tts_pool_style pitch/rate overrides for whisper synthesis; 5.5 Hz theta binaural; TTS whisper (6%) + SSB subliminal (14%) co-delivery; 4 s phrase dwell / 8 s off cycle; sleep_training gain profile; read_sleep_report content tool + \_sleep_planning_tick() in agent; sleep_training_log DB table; HTW metrics on session_metrics |
| --- | --- |

### \### VR Headset (OpenXR)

_Design spec: Bible Ch.8 (Visual and VR Architecture §18–§32)_

| **Feature** | **Notes** |
| --- | --- |
| OpenXR per-eye renderer (vr_display_runner.py) | pyopenxr subprocess; independent from SteamVR overlay; live_control.json IPC |
| --- | --- |
| Dichoptic flicker engine (vr_flicker_engine.py) | Per-eye luminance; ganzfeld / photic / rivalry / ssvep modes; smooth transitions |
| --- | --- |
| SSVEP detector (vr_ssvep_detector.py) | Welch PSD + 1/f correction; SNR, intermodulation, binocular index, switch rate |
| --- | --- |
| Safety enforcer (vr_safety.py) | Danger zone depth cap; waveform frequency ceilings; first-session ramp; paroxysmal kill |
| --- | --- |
| Frequency allocation table (vr_freq_table.py) | Harmonic collision detection up to 3rd harmonic; validated at VR session start |
| --- | --- |
| Ganzfeld protocol (vr_ganzfeld.py) | 3-phase onset ramp (sqrt curve) → equilibration → ganzflicker; GanzfeldFlicker modulator |
| --- | --- |
| Vection renderer (vr_vection.py) | 3D particle tunnel optic flow; session-capped speed; adaptive throttle on high binocular index |
| --- | --- |
| Depth-plane subliminal (vr_subliminal.py) | 3 independent stereo depth planes; SOA state machine; VAC mitigation |
| --- | --- |
| Conductor VR integration | Binocular index corroborates INDUCTION/DEEPENING transitions; closed-loop photic frequency nudge |
| --- | --- |
| VR panel controls | "VR Headset" section in control panel; launch/stop; render mode; rivalry Hz; vection; live SSVEP readout |
| --- | --- |
| Agent VR knowledge | knowledge/vr_protocols.md injected into agent prompt when headset active |
| --- | --- |
| Subliminal depth routing | Agent next_affirmation auto-routed to far/mid/near planes (4:4:1) when VR active |
| --- | --- |

## \## Phase 3 — Planned

Items are organized by priority tier. Each tier can proceed independently. Bible chapter citations point to the canonical spec for implementation. Within each tier, items are roughly ordered by dependency (build top items first).

### \### Tier 1 — Hardware Output Channels ✅ SHIPPED

_All items shipped April 2026. See "Hardware Output Channels" in Recently Shipped above._

| **Item** | **Status** |
| --- | --- |
| Lovense BLE driver | ✅ haptic_engine.py |
| --- | --- |
| DG Labs Coyote BLE driver | ✅ tavns_engine.py |
| --- | --- |
| Haptic/taVNS safety enforcer | ✅ device_safety.py |
| --- | --- |
| Haptic gain channel activation | ✅ crossmodal_gain.py |
| --- | --- |
| Conductor haptic/taVNS integration | ✅ conductor.py phase profiles |
| --- | --- |
| Haptic conditioning delivery | ✅ TMR cue + conditioned anchor |
| --- | --- |
| live_control.json haptic keys | ✅ 26 keys documented in AGENTS.md |
| --- | --- |

### \### Conditioning & Habituation

_Fully shipped — conditioning_engine.py (780 lines) + habituation_engine.py (530 lines). Includes: ConditioningEngine (7 sub-components), StrengthTracker (Rescorla-Wagner), ReinforcementScheduler (VR schedule progression), ShapingEngine (operant neurofeedback), SecondOrderTrainer, PortableResponseEvaluator, AssociationRegistry, NeuralStateFingerprint (6D SDL matching), HabituationEngine (4 sub-components), three-timescale novelty formula, NoveltyBudget, DishabituationScheduler, full stimulus rotation lifecycle. Design spec: Bible Ch.6._

| **Item** | **Bible Spec** | **Notes** |
| --- | --- | --- |
| ConditioningEngine class | Ch.6 §4–§8 | Centralized orchestration: receives depth/phase context from Conductor, selects conditioning paradigm, dispatches to all 5 output channels, logs to DB |
| --- | --- | --- |
| HabituationManager module | Ch.6 §9–§12 | Habituation curve modeling per stimulus; exposure tracking; rotation scheduling; novelty injection; cross-session persistence |
| --- | --- | --- |
| Stimulus rotation logic | Ch.6 §10 | Automatic rotation when habituation curve plateaus; affirmation pool cycling; image pool cycling; per-user rotation cadence |
| --- | --- | --- |
| Six-paradigm conditioning taxonomy | Ch.6 §5 | Classical, operant, evaluative, mere exposure, context-dependent, multi-modal — formalized as selectable paradigms in ConditioningEngine |
| --- | --- | --- |
| Content-conditioning closed loop | Ch.6 §13, Ch.11 §10 | ContentManager → ConditioningEngine → HabituationManager → ContentManager lifecycle as a formal pipeline |
| --- | --- | --- |

### \### Tier 2 — Sleep Architecture Expansion

_Core sleep detection and TMR are built. These are the novel session types and automation the Bible specifies._

| **Item** | **Bible Spec** | **Notes** |
| --- | --- | --- |
| Edison Mode protocol | Ch.7 §29 | Hypnagogic creativity capture; 6-state N1-interception FSM; alpha/theta ratio fast-path; verbal report capture; cycle support; `edison_captures` DB table |
| --- | --- | --- |
| SSILD protocol | Ch.7 §30–§31 | Senses-Initiated Lucid Dreaming: 8-step guided sensory protocol; automated cueing; practice mode; readiness assessment |
| --- | --- | --- |
| Dream Engineering / DREAM mode | Ch.7 §23–§25 | Stage Gate architecture; dual persistence model; technique taxonomy; full dream session type |
| --- | --- | --- |
| 24-hour continuous training automation | Ch.7 §32, Ch.11 §9 | Wake encoding → sleep consolidation as automated lifecycle; session handoff from active to sleep mode; TMR cue scheduling based on wake session content |
| --- | --- | --- |

### \### Tier 3 — Console Migration (Tkinter → ImGui)

_Tkinter panel is production-complete. ImGui migration is started but early-stage._

| **Item** | **Bible Spec** | **Notes** |
| --- | --- | --- |
| ImGui three-panel layout | Ch.9 §3–§5 | Replace two-column Tkinter layout with Bible-spec three-panel: control, telemetry, console |
| --- | --- | --- |
| Rosé Pine Moon ImGui theme | Ch.9 §6, Ch.8 §4 | Full imgui.push_style_color() implementation from RP palette dict; the ONLY palette |
| --- | --- | --- |
| Widget taxonomy implementation | Ch.9 §7–§8 | Sliders, combo boxes, transport bar, waveform display, session treeview — all ported to ImGui equivalents |
| --- | --- | --- |
| Telemetry dashboard | Ch.9 §19–§20 | Real-time biosignal display, trance score graph, sleep metrics panel, conditioning status |
| --- | --- | --- |
| Console bus migration | Ch.9 §26 | Agent↔console messaging ported from Tkinter text widget to ImGui console panel |
| --- | --- | --- |
| Sleep telemetry panel | Ch.7 §20, Ch.9 §20 | Sleep stage hypnogram, spindle density graph, SWE burst log, TMR cue timeline |
| --- | --- | --- |
| Edison Mode capture log viewer | Ch.7 §14, Ch.9 §14 | Hypnagogic capture history with playback and annotation |
| --- | --- | --- |
| Training mode panel | Ch.6 §11, Ch.9 §11 | Conditioning status, habituation curves, active paradigm, rotation schedule |
| --- | --- | --- |
| live_control.json visual keys | Ch.8 §9, Ch.9 §9 | Visual parameter controls exposed as ImGui widgets |
| --- | --- | --- |

### \### Tier 4 — Onboarding and FTUE

_Basic first-run onboarding exists. The Bible specifies a 14-state onboarding state machine with full FTUE._

| **Item** | **Bible Spec** | **Notes** |
| --- | --- | --- |
| OnboardingManager state machine | Ch.10 §23 | 14-state FSM: hardware discovery → calibration → Session Zero → progressive complexity; persistent state; parallel tracks |
| --- | --- | --- |
| Session Zero protocol | Ch.10 §4 | 8-phase first-session sequence: welcome → preference elicitation → safety briefing → mini trance → debrief |
| --- | --- | --- |
| Hardware discovery wizard | Ch.10 §3 | BLE scan → device identification → signal validation → pairing → graceful degradation for missing devices |
| --- | --- | --- |
| Trance depth calibration | Ch.10 §5 | 5-test calibration battery establishing personal depth baseline |
| --- | --- | --- |
| Biosignal calibration | Ch.10 §6 | HR/GSR/breath baselines; cross-modal correlation; quality scoring; recalibration triggers |
| --- | --- | --- |
| Audio preference detection | Ch.10 §7 | Survey + test stimuli + headphone detection + sensitivity flags |
| --- | --- | --- |
| Visual calibration flow | Ch.10 §8 | Display detection, photosensitive screening, comfort test, Ganzfeld compatibility |
| --- | --- | --- |
| NWI baseline establishment | Ch.10 §9 | Neural Write Interface concept introduction; first write attempt; receptivity scoring; depth estimation |
| --- | --- | --- |
| FTUE console walkthrough | Ch.10 §17 | 12-step guided tour of console UI; rendering pipeline; skip/replay; contextual re-triggering |
| --- | --- | --- |
| UI simplification mode | Ch.10 §18 | 3 visibility tiers: beginner (essential only) → intermediate → full; progressive reveal |
| --- | --- | --- |
| Tutorial overlay system | Ch.10 §19 | 4 overlay types; rendering pipeline; content schema; queue manager; session suppression |
| --- | --- | --- |
| Progressive complexity engine | Ch.10 §15–§16 | 5-tier unlock matrix across sessions 1–10; expert bypass; feature gating by session count and calibration quality |
| --- | --- | --- |
| Vesper onboarding personality | Ch.10 §22 | Warm/encouraging voice mode for first sessions; dialogue tree; adaptive pacing; transition to session Vesper |
| --- | --- | --- |
| First-run wizard | Ch.10 §20 | 8-page guided setup: name → preferences → hardware → consent → profile creation |
| --- | --- | --- |
| Returning user re-onboarding | Ch.10 §27 | 5 triggers for selective re-onboarding; recalibration; new feature introduction |
| --- | --- | --- |

### \### Tier 5 — VR Enhancements

_VR headset integration is shipped. These are the next-generation features._

| **Item** | **Bible Spec** | **Notes** |
| --- | --- | --- |
| Eye-tracking data integration | Ch.8 §25 | OpenXR XR_EXT_eye_gaze_interaction; per-eye gaze + pupil dilation as trance proxy |
| --- | --- | --- |
| Gaze-depth subliminal routing | Ch.8 §26 | Route affirmations to depth plane matching user's current gaze convergence depth |
| --- | --- | --- |
| Pupillometry | Ch.8 §27 | Pupil dilation as valence/arousal signal independent of EEG — complementary trance indicator |
| --- | --- | --- |
| Proactive rivalry probe | Ch.8 §28 | Agent requests 60-second dichoptic_ssvep burst mid-session; Conductor switches mode, collects measurement, logs, returns to prior mode |
| --- | --- | --- |
| VR metrics in session scoring | Ch.8 §29 | binocular_index and switch_rate_hz time-series → session_metrics alongside ASSR/SEF95 |
| --- | --- | --- |
| Agent VR mode suggestions | Ch.8 §30 | Agent detects plateau in trance_score and writes VR mode switch hints via agent_conductor_hints |
| --- | --- | --- |
| SDF font rendering | Ch.8 §31 | Replace GLUT bitmap fonts in vr_subliminal.py with SDF-based text for crisp VR text at all depths |
| --- | --- | --- |
| VAO/VBO vection renderer | Ch.8 §32 | Upgrade vr_vection.py from immediate mode GL to buffered geometry for Quest 3 / standalone headset performance |
| --- | --- | --- |

## \## Cross-Chapter Implementation Dependencies

Use this table to understand what must ship before what. Items in the same tier are largely independent, but cross-tier dependencies exist.

| **Dependency** | **Blocks** | **Reason** |
| --- | --- | --- |
| ~~Tier 1 (haptic drivers)~~ | ~~Tier 2 (ConditioningEngine 5-channel dispatch)~~ | ✅ Shipped — ConditioningEngine can now dispatch to all 5 channels |
| --- | --- | --- |
| Tier 2 (HabituationManager) | Tier 5 (initial habituation baseline in onboarding) | Onboarding seeds the habituation model |
| --- | --- | --- |
| Tier 4 (ImGui migration) | Tier 5 (FTUE console walkthrough) | Can't build a walkthrough for a UI that's about to change |
| --- | --- | --- |
| Tier 4 (sleep telemetry panel) | Tier 3 (Edison Mode UI) | Edison Mode needs its capture log viewer |
| --- | --- | --- |
| ~~Tier 1 (haptic drivers)~~ | ~~Tier 5 (hardware discovery wizard)~~ | ✅ Shipped — discovery wizard can now scan for haptic/taVNS devices |
| --- | --- | --- |

## \## Architecture Reference

| **System** | **Bible Chapter** | **Key Sections** |
| --- | --- | --- |
| Processing stack, state management, IPC | Ch.1 | §1–§12 |
| --- | --- | --- |
| Biosignal acquisition, EEG, PPG, IMU | Ch.2 | §1–§22 |
| --- | --- | --- |
| Audio engine, entrainment, TTS, SSB | Ch.3 | §1–§18 |
| --- | --- | --- |
| Session architecture, Conductor, timelines | Ch.4 | §1–§24 |
| --- | --- | --- |
| Agent intelligence, tools, memory, ASIA | Ch.5 | §1–§20 |
| --- | --- | --- |
| Conditioning, content, habituation | Ch.6 | §1–§36 |
| --- | --- | --- |
| Sleep architecture, TMR, HTW, dreams | Ch.7 | §1–§39 |
| --- | --- | --- |
| Visual rendering, VR, safety | Ch.8 | §1–§32 |
| --- | --- | --- |
| Console UI, ImGui, telemetry | Ch.9 | §1–§34 |
| --- | --- | --- |
| Onboarding, FTUE, Session Zero | Ch.10 | §1–§30 |
| --- | --- | --- |
| Master overview, patterns, schema, roadmap | Ch.11 | §1–§34 |
| --- | --- | --- |