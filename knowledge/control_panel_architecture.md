# Somna Bible Ch.9 Â§Control-Panel — Control Panel Architecture

Technical Specification — Subsystem v51

**Status:** Specification

**Author:** Ed

**Date:** 6 April 2026

**Stack:** Python / ModernGL / BrainFlow / Muse 2 EEG / Dear ImGui

**Depends on:** Bible Ch.4 Â§DeliveryGate (DeliveryGate / live_control.json IPC), Bible Ch.7 Â§Sleep-Staging (Sleep Stages), Bible Ch.6 Â§TMR (TMR), Bible Ch.7 Â§HTW (HTW), Bible Ch.1 Â§Autonomic (Cardiac-Phase Gating), Bible Ch.6 Â§Conditioning (Conditioning), Bible Ch.6 Â§Stimulus-Techniques (Stimulus Techniques), Bible Ch.6 Â§Habituation (Habituation), Bible Ch.5 Â§Agent (Content Design), Bible Ch.8 Â§Enhancement (Visual/Audio Enhancement), Bible Ch.5 Â§Session-Director (Session Director), Bible Ch.4 Â§Session-Planner (Induction Strategy Library), Bible Ch.6 Â§SOC (GENUS Integration)

# 1  Overview

Somna's subsystem stack (Docs 28–50) has grown to produce 100+ live_control.json keys spanning 12 subsystems. Exposing all of these as raw controls would create an unusable wall of knobs. This document specifies a control panel architecture that solves the complexity problem through three mechanisms:

1. **Progressive disclosure** — three visibility layers (Essential, Advanced, Debug) so the user sees only what they need.
2. **Session-type awareness** — the panel layout changes based on the active session mode (Trance, GENUS, Sleep, Cue-Test), showing only contextually relevant controls.
3. **Authority integration** — when the user touches a control, it locks that parameter for the session via source tagging, and the SessionDirector (Bible Ch.5 Â§Session-Director) and LLM agent compensate through other unlocked parameters.

The control panel is implemented as Dear ImGui windows integrated into Somna's existing ModernGL render loop. ImGui is immediate-mode, GPU-accelerated, and requires no additional windowing framework.

# 2  The Complexity Problem

Docs 28–38 established approximately 20 live_control.json keys: gain sliders for each audio layer (master, TTS, SSB, music, nature, isochronic, binaural), entrainment and beat frequency targets, trance_score telemetry, EEG signal quality, and conductor phase state. These were manageable as a flat panel. A single-column list of labeled sliders and indicators fit on one screen, and users could absorb the full parameter space at a glance.

Docs 39–50 changed the calculus. Sleep staging (Bible Ch.7 Â§Sleep-Staging) added stage classification, SWE parameters, and cycle tracking. TMR (Bible Ch.6 Â§TMR) added cue volume, phase-locking state, and consolidation priority. HTW (Bible Ch.7 Â§HTW) added eligibility flags and micro-gain overrides. Cardiac-phase gating (Bible Ch.1 Â§Autonomic) added PPG heart rate, HRV, breath rate, IMU motion telemetry, and the quad-gate status array. Conditioning (Bible Ch.6 Â§Conditioning) added paradigm selectors, Rescorla-Wagner association strength, VR schedule state, and shaping percentiles. Stimulus optimization (Bible Ch.6 Â§Stimulus-Techniques), habituation management (Bible Ch.6 Â§Habituation), content design (Bible Ch.5 Â§Agent), and visual/audio enhancement (Bible Ch.8 Â§Enhancement) each contributed their own parameter clusters. The Session Director (Bible Ch.5 Â§Session-Director) added phase tracking, arc selection, authority levels, and user model telemetry. The Induction Strategy Library (Bible Ch.4 Â§Session-Planner) added strategy selectors and effectiveness metrics. GENUS integration (Bible Ch.6 Â§SOC) added frequency control, gamma verification, and arc management. The net addition: approximately 90 new keys.

The total now exceeds 100 keys. A flat panel would be incomprehensible — a scrolling wall of unlabeled sliders where the user cannot distinguish "things I should touch" from "things the system manages" from "things that are just telemetry." The solution must balance four competing requirements: *accessibility* (new users see a simple, intuitive surface), *power* (advanced users access deep tuning without friction), *safety* (certain parameters — gate thresholds, conditioning timing, GENUS frequency — should not be casually adjusted), and *transparency* (the user should always be able to see what the system is doing via telemetry, even when they cannot control it directly).

The architecture specified below addresses all four requirements through a classification system that assigns every key a visibility tier, an interaction model, and a session-mode scope. The panel is data-driven: a single panel_config.json file defines the entire widget registry, so adding new keys in future docs requires only a config entry, not a code change.

# 3  Key Classification System

Every live_control.json key is assigned exactly one classification that determines its panel visibility and interaction model.


| **Classification** | **Visibility**                                         | **Interaction**                                        | **Description**                                                                                                                                      |
| ------------------ | ------------------------------------------------------ | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| USER_CONTROL       | Essential or Advanced layer                            | Read-write slider / toggle / dropdown                  | Parameters the user is expected to adjust. When touched, tagged with source: "user" and locked for the session.                                      |
| ---                | ---                                                    | ---                                                    | ---                                                                                                                                                  |
| AGENT_TUNABLE      | Advanced layer (read-only) or Debug layer (read-write) | Read-only indicator at Advanced; full control at Debug | Parameters the LLM agent and SessionDirector adjust. Visible as indicators so the user can see what the agent is doing. Editable only in Debug mode. |
| ---                | ---                                                    | ---                                                    | ---                                                                                                                                                  |
| TELEMETRY          | All layers (read-only)                                 | Read-only indicator, sparkline, or status badge        | Sensor readings and computed metrics. Never writable from the panel. Always visible as compact indicators.                                           |
| ---                | ---                                                    | ---                                                    | ---                                                                                                                                                  |
| INTERNAL           | Debug layer only                                       | Read-only                                              | Implementation plumbing (gate timers, relaxation counters, phase accumulators). Hidden unless Debug mode is active.                                  |
| ---                | ---                                                    | ---                                                    | ---                                                                                                                                                  |


# 4  Complete Key Inventory

The following subsections enumerate every live_control.json key, organized by subsystem domain. Each table specifies the key name, data type, valid range or value set, classification, disclosure layer, and widget type.

## 4.1  Core Conductor (Pre-Bible Ch.7 Â§Sleep-Staging Legacy)


| **Key**               | **Type** | **Range / Values**                             | **Classification** | **Layer** | **Widget**        |
| --------------------- | -------- | ---------------------------------------------- | ------------------ | --------- | ----------------- |
| gain_master           | float    | 0.0–1.0                                        | USER_CONTROL       | Essential | Slider            |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| gain_tts              | float    | 0.0–1.0                                        | USER_CONTROL       | Essential | Slider            |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| gain_ssb              | float    | 0.0–1.0                                        | USER_CONTROL       | Advanced  | Slider            |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| gain_music            | float    | 0.0–1.0                                        | USER_CONTROL       | Essential | Slider            |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| gain_nature           | float    | 0.0–1.0                                        | USER_CONTROL       | Essential | Slider            |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| gain_isochronic       | float    | 0.0–1.0                                        | USER_CONTROL       | Advanced  | Slider            |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| gain_binaural         | float    | 0.0–1.0                                        | USER_CONTROL       | Advanced  | Slider            |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| entrainment_frequency | float    | 1.0–14.0 Hz                                    | USER_CONTROL       | Advanced  | Slider            |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| beat_frequency        | float    | 0.5–40.0 Hz                                    | AGENT_TUNABLE      | Advanced  | Indicator         |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| conductor_phase       | str      | IDLE / ACTIVE / DEEPENING / SLEEP_APPROACH / … | TELEMETRY          | Essential | Badge             |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| trance_score          | float    | 0.0–1.0                                        | TELEMETRY          | Essential | Gauge + Sparkline |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| eeg_signal_quality    | float    | 0.0–1.0                                        | TELEMETRY          | Essential | Indicator         |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| eeg_signal_lost       | bool     | true / false                                   | TELEMETRY          | Essential | Alert Badge       |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |
| session_elapsed       | float    | seconds                                        | TELEMETRY          | Essential | Timer             |
| ---                   | ---      | ---                                            | ---                | ---       | ---               |


## 4.2  Sleep Architecture (Bible Ch.7 Â§Sleep-Staging)


| **Key**                | **Type** | **Range / Values**                                                          | **Classification** | **Layer**         | **Widget** |
| ---------------------- | -------- | --------------------------------------------------------------------------- | ------------------ | ----------------- | ---------- |
| sleep_stage            | str      | WAKE / N1 / N2 / N3 / REM                                                   | TELEMETRY          | Essential (Sleep) | Badge      |
| ---                    | ---      | ---                                                                         | ---                | ---               | ---        |
| sleep_stage_confidence | float    | 0.0–1.0                                                                     | TELEMETRY          | Advanced          | Indicator  |
| ---                    | ---      | ---                                                                         | ---                | ---               | ---        |
| sleep_phase            | str      | SLEEP_APPROACH / SLEEP_ONSET / SLEEP_MAINTAIN / SLEEP_TRAINING / SLEEP_WAKE | TELEMETRY          | Essential (Sleep) | Badge      |
| ---                    | ---      | ---                                                                         | ---                | ---               | ---        |
| swe_frequency          | float    | 0.5–2.0 Hz                                                                  | AGENT_TUNABLE      | Advanced          | Indicator  |
| ---                    | ---      | ---                                                                         | ---                | ---               | ---        |
| swe_amplitude          | float    | 0.0–1.0                                                                     | AGENT_TUNABLE      | Advanced          | Indicator  |
| ---                    | ---      | ---                                                                         | ---                | ---               | ---        |
| sleep_time_n2_n3       | float    | seconds (cumulative)                                                        | TELEMETRY          | Essential (Sleep) | Timer      |
| ---                    | ---      | ---                                                                         | ---                | ---               | ---        |
| sleep_cycle_count      | int      | 0–10                                                                        | TELEMETRY          | Essential (Sleep) | Counter    |
| ---                    | ---      | ---                                                                         | ---                | ---               | ---        |


## 4.3  Targeted Memory Reactivation (Bible Ch.6 Â§TMR)


| **Key**                    | **Type** | **Range / Values** | **Classification** | **Layer**         | **Widget** |
| -------------------------- | -------- | ------------------ | ------------------ | ----------------- | ---------- |
| tmr_enabled                | bool     | true / false       | USER_CONTROL       | Essential (Sleep) | Toggle     |
| ---                        | ---      | ---                | ---                | ---               | ---        |
| tmr_active                 | bool     | true / false       | TELEMETRY          | Essential (Sleep) | Badge      |
| ---                        | ---      | ---                | ---                | ---               | ---        |
| tmr_cue_volume             | float    | 0.0–0.3            | USER_CONTROL       | Advanced (Sleep)  | Slider     |
| ---                        | ---      | ---                | ---                | ---               | ---        |
| tmr_target_pool            | str      | pool name          | TELEMETRY          | Advanced          | Badge      |
| ---                        | ---      | ---                | ---                | ---               | ---        |
| tmr_phase_locked           | bool     | true / false       | TELEMETRY          | Advanced          | Indicator  |
| ---                        | ---      | ---                | ---                | ---               | ---        |
| tmr_spindle_gated          | bool     | true / false       | TELEMETRY          | Debug             | Indicator  |
| ---                        | ---      | ---                | ---                | ---               | ---        |
| tmr_cue_count              | int      | 0+                 | TELEMETRY          | Advanced          | Counter    |
| ---                        | ---      | ---                | ---                | ---               | ---        |
| tmr_consolidation_priority | str      | pool name          | AGENT_TUNABLE      | Debug             | Indicator  |
| ---                        | ---      | ---                | ---                | ---               | ---        |


## 4.4  Hypnagogic Training Window (Bible Ch.7 Â§HTW)


| **Key**      | **Type** | **Range / Values** | **Classification** | **Layer**         | **Widget** |
| ------------ | -------- | ------------------ | ------------------ | ----------------- | ---------- |
| htw_enabled  | bool     | true / false       | USER_CONTROL       | Advanced (Sleep)  | Toggle     |
| ---          | ---      | ---                | ---                | ---               | ---        |
| htw_active   | bool     | true / false       | TELEMETRY          | Essential (Sleep) | Badge      |
| ---          | ---      | ---                | ---                | ---               | ---        |
| htw_eligible | bool     | true / false       | TELEMETRY          | Advanced          | Indicator  |
| ---          | ---      | ---                | ---                | ---               | ---        |
| htw_count    | int      | 0–3                | TELEMETRY          | Advanced          | Counter    |
| ---          | ---      | ---                | ---                | ---               | ---        |
| htw_gain_tts | float    | 0.0–0.10           | AGENT_TUNABLE      | Debug             | Indicator  |
| ---          | ---      | ---                | ---                | ---               | ---        |
| htw_gain_ssb | float    | 0.0–0.20           | AGENT_TUNABLE      | Debug             | Indicator  |
| ---          | ---      | ---                | ---                | ---               | ---        |


## 4.5  Cardiac-Phase Gating & Autonomic Integration (Bible Ch.1 Â§Autonomic)

### 4.5.1  PPG Engine


| **Key**          | **Type** | **Range / Values** | **Classification** | **Layer** | **Widget**        |
| ---------------- | -------- | ------------------ | ------------------ | --------- | ----------------- |
| ppg_available    | bool     | true / false       | TELEMETRY          | Essential | Indicator         |
| ---              | ---      | ---                | ---                | ---       | ---               |
| ppg_heart_rate   | float    | 40–180 BPM         | TELEMETRY          | Essential | Value + Sparkline |
| ---              | ---      | ---                | ---                | ---       | ---               |
| ppg_hrv_rmssd    | float    | 0–200 ms           | TELEMETRY          | Advanced  | Value + Sparkline |
| ---              | ---      | ---                | ---                | ---       | ---               |
| ppg_breath_rate  | float    | 0.10–0.50 Hz       | TELEMETRY          | Advanced  | Value             |
| ---              | ---      | ---                | ---                | ---       | ---               |
| ppg_breath_phase | float    | 0.0–1.0            | TELEMETRY          | Debug     | Phase Ring        |
| ---              | ---      | ---                | ---                | ---       | ---               |


### 4.5.2  IMU Engine


| **Key**                 | **Type** | **Range / Values** | **Classification** | **Layer** | **Widget**  |
| ----------------------- | -------- | ------------------ | ------------------ | --------- | ----------- |
| imu_motion_rms          | float    | 0.0–1.0 g          | TELEMETRY          | Advanced  | Indicator   |
| ---                     | ---      | ---                | ---                | ---       | ---         |
| imu_stillness_index     | float    | 0.0–1.0            | TELEMETRY          | Advanced  | Indicator   |
| ---                     | ---      | ---                | ---                | ---       | ---         |
| imu_motion_contaminated | bool     | true / false       | TELEMETRY          | Essential | Alert Badge |
| ---                     | ---      | ---                | ---                | ---       | ---         |
| imu_head_nod_detected   | bool     | true / false       | TELEMETRY          | Debug     | Indicator   |
| ---                     | ---      | ---                | ---                | ---       | ---         |


### 4.5.3  DeliveryGate (Quad-Gate)


| **Key**               | **Type** | **Range / Values**                                  | **Classification** | **Layer** | **Widget**           |
| --------------------- | -------- | --------------------------------------------------- | ------------------ | --------- | -------------------- |
| gate_respiratory_hot  | bool     | true / false                                        | TELEMETRY          | Advanced  | Gate Indicator       |
| ---                   | ---      | ---                                                 | ---                | ---       | ---                  |
| gate_alpha_at_trough  | bool     | true / false                                        | TELEMETRY          | Advanced  | Gate Indicator       |
| ---                   | ---      | ---                                                 | ---                | ---       | ---                  |
| gate_cardiac_diastole | bool     | true / false                                        | TELEMETRY          | Advanced  | Gate Indicator       |
| ---                   | ---      | ---                                                 | ---                | ---       | ---                  |
| gate_sqi_ok           | bool     | true / false                                        | TELEMETRY          | Advanced  | Gate Indicator       |
| ---                   | ---      | ---                                                 | ---                | ---       | ---                  |
| gate_all_clear        | bool     | true / false                                        | TELEMETRY          | Essential | Composite Gate Badge |
| ---                   | ---      | ---                                                 | ---                | ---       | ---                  |
| gate_relaxation_level | int      | 0–3 (0=full, 1=no cardiac, 2=no alpha, 3=resp only) | TELEMETRY          | Debug     | Indicator            |
| ---                   | ---      | ---                                                 | ---                | ---       | ---                  |
| gate_relaxation_timer | float    | 0–40 s                                              | INTERNAL           | Debug     | Timer                |
| ---                   | ---      | ---                                                 | ---                | ---       | ---                  |
| gate_fire_count       | int      | 0+ (session total)                                  | TELEMETRY          | Debug     | Counter              |
| ---                   | ---      | ---                                                 | ---                | ---       | ---                  |


## 4.6  Conditioning & Reinforcement (Bible Ch.6 Â§Conditioning)


| **Key**                      | **Type** | **Range / Values**                                                                    | **Classification** | **Layer** | **Widget** |
| ---------------------------- | -------- | ------------------------------------------------------------------------------------- | ------------------ | --------- | ---------- |
| conditioning_active_paradigm | str      | CLASSICAL / EVALUATIVE / OPERANT / STATE_DEPENDENT / OCCASION_SETTING / INTEROCEPTIVE | AGENT_TUNABLE      | Advanced  | Badge      |
| ---                          | ---      | ---                                                                                   | ---                | ---       | ---        |
| conditioning_active_pool     | str      | pool name                                                                             | AGENT_TUNABLE      | Advanced  | Badge      |
| ---                          | ---      | ---                                                                                   | ---                | ---       | ---        |
| association_strength_current | float    | 0.0–1.0 (Rescorla-Wagner)                                                             | TELEMETRY          | Advanced  | Gauge      |
| ---                          | ---      | ---                                                                                   | ---                | ---       | ---        |
| vr_schedule                  | str      | CRF / VR-2 / VR-4 / VR-6                                                              | AGENT_TUNABLE      | Advanced  | Badge      |
| ---                          | ---      | ---                                                                                   | ---                | ---       | ---        |
| vr_reinforcement_ratio       | float    | 0.0–1.0                                                                               | TELEMETRY          | Debug     | Indicator  |
| ---                          | ---      | ---                                                                                   | ---                | ---       | ---        |
| shaping_target_percentile    | float    | 30–70                                                                                 | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                          | ---      | ---                                                                                   | ---                | ---       | ---        |
| conditioning_trial_count     | int      | 0+                                                                                    | TELEMETRY          | Debug     | Counter    |
| ---                          | ---      | ---                                                                                   | ---                | ---       | ---        |


## 4.7  Stimulus Techniques & Optimization (Bible Ch.6 Â§Stimulus-Techniques)


| **Key**                  | **Type** | **Range / Values**        | **Classification** | **Layer** | **Widget** |
| ------------------------ | -------- | ------------------------- | ------------------ | --------- | ---------- |
| spiral_rotation_rate     | float    | 0.05–0.5 Hz (IAF-matched) | AGENT_TUNABLE      | Advanced  | Indicator  |
| ---                      | ---      | ---                       | ---                | ---       | ---        |
| spiral_phi_enabled       | bool     | true / false              | USER_CONTROL       | Advanced  | Toggle     |
| ---                      | ---      | ---                       | ---                | ---       | ---        |
| fractal_dimension        | float    | 1.1–1.5 (target ~1.3)     | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                      | ---      | ---                       | ---                | ---       | ---        |
| fractal_fbm_h            | float    | 0.5–0.9 (target 0.7)      | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                      | ---      | ---                       | ---                | ---       | ---        |
| motion_aftereffect_cycle | float    | 20–50 s (target 35)       | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                      | ---      | ---                       | ---                | ---       | ---        |
| isochronic_am_depth      | float    | 0.0–1.0                   | AGENT_TUNABLE      | Advanced  | Indicator  |
| ---                      | ---      | ---                       | ---                | ---       | ---        |
| binaural_offset          | float    | 0.5–40.0 Hz               | AGENT_TUNABLE      | Advanced  | Indicator  |
| ---                      | ---      | ---                       | ---                | ---       | ---        |
| spectral_tilt_target     | float    | 2.0–0.0 dB/oct            | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                      | ---      | ---                       | ---                | ---       | ---        |
| trace_conditioning_gap   | float    | 0.5–3.0 s (target 1.5)    | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                      | ---      | ---                       | ---                | ---       | ---        |
| compound_cs_window       | float    | 100–300 ms (target 200)   | INTERNAL           | Debug     | Indicator  |
| ---                      | ---      | ---                       | ---                | ---       | ---        |


## 4.8  Habituation & Novelty Management (Bible Ch.6 Â§Habituation)


| **Key**                  | **Type** | **Range / Values**                            | **Classification** | **Layer** | **Widget** |
| ------------------------ | -------- | --------------------------------------------- | ------------------ | --------- | ---------- |
| novelty_score            | float    | 0.0–1.0                                       | TELEMETRY          | Advanced  | Gauge      |
| ---                      | ---      | ---                                           | ---                | ---       | ---        |
| novelty_budget_remaining | float    | 0.0–1.0                                       | TELEMETRY          | Debug     | Indicator  |
| ---                      | ---      | ---                                           | ---                | ---       | ---        |
| habituation_micro        | float    | 0.0–1.0                                       | TELEMETRY          | Debug     | Indicator  |
| ---                      | ---      | ---                                           | ---                | ---       | ---        |
| habituation_meso         | float    | 0.0–1.0                                       | TELEMETRY          | Debug     | Indicator  |
| ---                      | ---      | ---                                           | ---                | ---       | ---        |
| habituation_macro        | float    | 0.0–1.0                                       | TELEMETRY          | Debug     | Indicator  |
| ---                      | ---      | ---                                           | ---                | ---       | ---        |
| stimulus_lifecycle_state | str      | NOVEL / ACTIVE / COOLING / RETIRED / ARCHIVED | TELEMETRY          | Advanced  | Badge      |
| ---                      | ---      | ---                                           | ---                | ---       | ---        |
| dishabituation_cooldown  | float    | 0–300 s                                       | INTERNAL           | Debug     | Timer      |
| ---                      | ---      | ---                                           | ---                | ---       | ---        |


## 4.9  Content Design (Bible Ch.5 Â§Agent)


| **Key**                  | **Type** | **Range / Values**      | **Classification** | **Layer** | **Widget** |
| ------------------------ | -------- | ----------------------- | ------------------ | --------- | ---------- |
| content_active_pool      | str      | pool name               | AGENT_TUNABLE      | Advanced  | Badge      |
| ---                      | ---      | ---                     | ---                | ---       | ---        |
| content_semantic_density | str      | PRIME / BRIDGE / DEEPEN | AGENT_TUNABLE      | Debug     | Badge      |
| ---                      | ---      | ---                     | ---                | ---       | ---        |
| content_syllable_rate    | float    | 3.0–7.0 Hz              | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                      | ---      | ---                     | ---                | ---       | ---        |
| content_milton_pattern   | str      | pattern name            | AGENT_TUNABLE      | Debug     | Badge      |
| ---                      | ---      | ---                     | ---                | ---       | ---        |
| content_delivery_count   | int      | 0+                      | TELEMETRY          | Advanced  | Counter    |
| ---                      | ---      | ---                     | ---                | ---       | ---        |


## 4.10  Visual & Audio Enhancement (Bible Ch.8 Â§Enhancement)

### 4.10.1  Background Layer


| **Key**                  | **Type** | **Range / Values** | **Classification** | **Layer** | **Widget**            |
| ------------------------ | -------- | ------------------ | ------------------ | --------- | --------------------- |
| bg_color_temp            | float    | 1800–4500 K        | USER_CONTROL       | Advanced  | Slider (warm-to-cool) |
| ---                      | ---      | ---                | ---                | ---       | ---                   |
| bg_ganzfeld_breathe_rate | float    | 0.05–0.3 Hz        | AGENT_TUNABLE      | Advanced  | Indicator             |
| ---                      | ---      | ---                | ---                | ---       | ---                   |
| bg_looming_amplitude     | float    | 0.0–0.15           | AGENT_TUNABLE      | Debug     | Indicator             |
| ---                      | ---      | ---                | ---                | ---       | ---                   |
| bg_troxler_enabled       | bool     | true / false       | USER_CONTROL       | Advanced  | Toggle                |
| ---                      | ---      | ---                | ---                | ---       | ---                   |


### 4.10.2  Shader Pipeline


| **Key**                     | **Type** | **Range / Values**       | **Classification** | **Layer** | **Widget** |
| --------------------------- | -------- | ------------------------ | ------------------ | --------- | ---------- |
| shader_blur_radius          | float    | 0.0–20.0 px              | AGENT_TUNABLE      | Advanced  | Indicator  |
| ---                         | ---      | ---                      | ---                | ---       | ---        |
| shader_chromatic_aberration | float    | 0.0–5.0 px               | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                         | ---      | ---                      | ---                | ---       | ---        |
| shader_vignette_intensity   | float    | 0.0–1.0                  | AGENT_TUNABLE      | Advanced  | Indicator  |
| ---                         | ---      | ---                      | ---                | ---       | ---        |
| shader_bloom_intensity      | float    | 0.0–1.0                  | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                         | ---      | ---                      | ---                | ---       | ---        |
| shader_iaf_luminance_depth  | float    | 0.0–0.05 (sub-threshold) | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                         | ---      | ---                      | ---                | ---       | ---        |


### 4.10.3  Spatial Audio


| **Key**               | **Type** | **Range / Values**       | **Classification** | **Layer** | **Widget** |
| --------------------- | -------- | ------------------------ | ------------------ | --------- | ---------- |
| audio_panning_enabled | bool     | true / false             | USER_CONTROL       | Advanced  | Toggle     |
| ---                   | ---      | ---                      | ---                | ---       | ---        |
| audio_panning_rate    | float    | matches entrainment freq | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                   | ---      | ---                      | ---                | ---       | ---        |
| audio_asmr_enabled    | bool     | true / false             | USER_CONTROL       | Advanced  | Toggle     |
| ---                   | ---      | ---                      | ---                | ---       | ---        |
| audio_asmr_gain       | float    | 0.0–0.3                  | USER_CONTROL       | Advanced  | Slider     |
| ---                   | ---      | ---                      | ---                | ---       | ---        |
| audio_shepard_enabled | bool     | true / false             | USER_CONTROL       | Advanced  | Toggle     |
| ---                   | ---      | ---                      | ---                | ---       | ---        |
| audio_shepard_rate    | float    | 0.01–0.1 Hz              | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                   | ---      | ---                      | ---                | ---       | ---        |
| audio_looming_sync    | bool     | true / false             | AGENT_TUNABLE      | Debug     | Indicator  |
| ---                   | ---      | ---                      | ---                | ---       | ---        |


## 4.11  Session Director (Bible Ch.5 Â§Session-Director)


| **Key**                     | **Type** | **Range / Values**                                                               | **Classification** | **Layer** | **Widget**  |
| --------------------------- | -------- | -------------------------------------------------------------------------------- | ------------------ | --------- | ----------- |
| session_phase               | str      | ARRIVAL / INDUCTION / DEEPENING / WORK / CONSOLIDATION / EMERGENCE               | TELEMETRY          | Essential | Phase Badge |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |
| session_arc                 | str      | GENTLE_DESCENT / WAVE_PATTERN / DEEP_PLATEAU / CONDITIONING_FOCUS / SLEEP_BRIDGE | USER_CONTROL       | Essential | Dropdown    |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |
| session_intensity           | float    | 0.0–1.0                                                                          | AGENT_TUNABLE      | Essential | Gauge       |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |
| session_intensity_cycle     | str      | BUILD_UP / PEAK / RELAX                                                          | TELEMETRY          | Advanced  | Badge       |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |
| director_authority_level    | str      | MUST_DECIDE / SHOULD_DECIDE / MAY_DECIDE / SUGGEST_ONLY                          | TELEMETRY          | Debug     | Badge       |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |
| director_target_depth       | float    | 0.0–1.0                                                                          | AGENT_TUNABLE      | Advanced  | Indicator   |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |
| director_pace_before_lead   | bool     | true / false                                                                     | AGENT_TUNABLE      | Debug     | Indicator   |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |
| director_locked_param_count | int      | 0+                                                                               | TELEMETRY          | Advanced  | Counter     |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |
| user_model_responsiveness   | float    | 0.0–1.0                                                                          | TELEMETRY          | Debug     | Indicator   |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |
| user_model_preferred_depth  | float    | 0.0–1.0                                                                          | TELEMETRY          | Debug     | Indicator   |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |
| user_model_session_count    | int      | 0+                                                                               | TELEMETRY          | Debug     | Counter     |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |
| director_decision_log       | str      | last decision text                                                               | TELEMETRY          | Debug     | Text        |
| ---                         | ---      | ---                                                                              | ---                | ---       | ---         |


## 4.12  Induction Strategy Library (Bible Ch.4 Â§Session-Planner)


| **Key**                 | **Type** | **Range / Values**                                                                                                                             | **Classification** | **Layer**         | **Widget**   |
| ----------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ | ----------------- | ------------ |
| induction_strategy      | str      | ENTRAINMENT_HEAVY / SOMATIC_ANCHOR / BREATH_LEAD / PROGRESSIVE_RELAXATION / COGNITIVE_OVERLOAD / FRACTIONATION / FIXATION_FADE / PACE_AND_LEAD | USER_CONTROL       | Advanced (Trance) | Dropdown     |
| ---                     | ---      | ---                                                                                                                                            | ---                | ---               | ---          |
| induction_micro_phase   | str      | phase name                                                                                                                                     | TELEMETRY          | Advanced          | Badge        |
| ---                     | ---      | ---                                                                                                                                            | ---                | ---               | ---          |
| induction_progress      | float    | 0.0–1.0                                                                                                                                        | TELEMETRY          | Advanced          | Progress Bar |
| ---                     | ---      | ---                                                                                                                                            | ---                | ---               | ---          |
| induction_effectiveness | float    | 0.0–1.0                                                                                                                                        | TELEMETRY          | Advanced          | Gauge        |
| ---                     | ---      | ---                                                                                                                                            | ---                | ---               | ---          |
| strategy_auto_select    | bool     | true / false                                                                                                                                   | USER_CONTROL       | Advanced          | Toggle       |
| ---                     | ---      | ---                                                                                                                                            | ---                | ---               | ---          |


## 4.13  GENUS Integration (Bible Ch.6 Â§SOC)


| **Key**                    | **Type** | **Range / Values**                                             | **Classification** | **Layer**         | **Widget** |
| -------------------------- | -------- | -------------------------------------------------------------- | ------------------ | ----------------- | ---------- |
| genus_enabled              | bool     | true / false                                                   | USER_CONTROL       | Essential (GENUS) | Toggle     |
| ---                        | ---      | ---                                                            | ---                | ---               | ---        |
| genus_active               | bool     | true / false                                                   | TELEMETRY          | Essential (GENUS) | Badge      |
| ---                        | ---      | ---                                                            | ---                | ---               | ---        |
| genus_phase                | str      | RAMP_UP / ACTIVE / WIND_DOWN                                   | TELEMETRY          | Essential (GENUS) | Badge      |
| ---                        | ---      | ---                                                            | ---                | ---               | ---        |
| genus_frequency            | float    | 40.0 Hz (fixed)                                                | TELEMETRY          | Advanced          | Indicator  |
| ---                        | ---      | ---                                                            | ---                | ---               | ---        |
| genus_gamma_verified       | bool     | true / false                                                   | TELEMETRY          | Essential (GENUS) | Indicator  |
| ---                        | ---      | ---                                                            | ---                | ---               | ---        |
| genus_audio_only_window    | bool     | true / false                                                   | TELEMETRY          | Advanced          | Badge      |
| ---                        | ---      | ---                                                            | ---                | ---               | ---        |
| genus_transition_remaining | float    | 0–180 s                                                        | TELEMETRY          | Advanced          | Timer      |
| ---                        | ---      | ---                                                            | ---                | ---               | ---        |
| genus_arc                  | str      | GENUS_STANDALONE / GENUS_TRANCE_HYBRID / GENUS_NEUROPROTECTION | USER_CONTROL       | Essential (GENUS) | Dropdown   |
| ---                        | ---      | ---                                                            | ---                | ---               | ---        |
| genus_session_minutes      | float    | 0+                                                             | TELEMETRY          | Essential (GENUS) | Timer      |
| ---                        | ---      | ---                                                            | ---                | ---               | ---        |


# 5  Progressive Disclosure Layers

## 5.1  Essential Layer (Always Visible)

The Essential layer is the default view for all users. It contains approximately 12–18 controls depending on the active session mode. The fixed set includes: gain sliders (master, TTS, music, nature), the session arc dropdown, the trance_score gauge with sparkline, heart rate value with sparkline, EEG signal quality indicator, conductor phase badge, session phase badge, session intensity gauge, and the session elapsed timer. Mode-specific essentials are added dynamically: sleep stage and sleep phase badges in Sleep mode, the GENUS toggle and GENUS phase badge in GENUS mode, and so on.

Design principle: "Everything you need, nothing you don't." A first-time user should be able to run a complete session using only this layer. The Essential layer occupies the top section of the ImGui panel in a compact, single-column layout. All widgets are sized to fit within a 320px panel width without horizontal scrolling. Telemetry indicators use compact representations (badges, small gauges) to minimize vertical space.

The Essential layer never contains AGENT_TUNABLE parameters in editable form. It shows only USER_CONTROL widgets (sliders, toggles, dropdowns) and TELEMETRY widgets (badges, gauges, sparklines). This prevents new users from accidentally adjusting system-managed parameters.

## 5.2  Advanced Layer (Collapsible Sections)

The Advanced layer appears below the Essential layer as a series of expandable sections, organized by subsystem domain. Each section is rendered as an ImGui::CollapsingHeader with TreeNodeFlags. Collapsed by default. Section headers show a one-line summary of the subsystem's current state, providing information scent without requiring expansion. Examples:

- **Conditioning:** "VR-4, Classical, Pool: confidence"
- **Habituation:** "novelty 0.72, stimulus ACTIVE"
- **Induction:** "BREATH_LEAD, progress 0.45, effectiveness 0.68"
- **DeliveryGate:** "3/4 gates, relaxation L1"

Sections auto-expand when their subsystem is actively operating. The TMR section expands during SLEEP_MAINTAIN when TMR fires. The GENUS section expands when genus_active transitions to true. Auto-expansion is non-intrusive: it does not steal scroll position or collapse other sections.

Within each section, the Advanced layer contains two categories of widgets: USER_CONTROL parameters that are useful but not essential (e.g., entrainment frequency, color temperature, ASMR toggle, induction strategy selector), and AGENT_TUNABLE parameters displayed as read-only indicators so the user can observe what the agent and Director are doing. Read-only indicators use a muted text color (#aaaaaa) and show a small robot icon if the last writer was the agent, or a gear icon if the last writer was the Director.

## 5.3  Debug Layer (Full Access)

The Debug layer is activated via a toggle in the panel header or the keyboard shortcut Ctrl+Shift+D. It exposes all keys, including those classified as INTERNAL. All AGENT_TUNABLE keys become editable sliders or dropdowns (but touching them still triggers the standard lock protocol — the value is written with source: "user" and added to timeline_locked_params).

The Debug layer adds the following diagnostic panels:

- **Raw JSON Viewer:** A scrollable text panel showing the current live_control.json state, updated every tick. Keys are sorted alphabetically. Changed keys are highlighted for one second after modification.
- **Decision Log:** A scrollable list showing the last 50 SessionDirector decisions with timestamps. Each entry shows the decision type, target parameter, old and new values, and rationale string.
- **Gate Timing Visualization:** A horizontal bar showing the quad-gate state (respiratory, alpha, cardiac, SQI) with a trailing history of fire/miss events over the last 30 seconds. Green ticks for fires, red ticks for misses.

A warning banner is displayed at the top of the panel when Debug mode is active:

**Warning**

"Debug mode active — manual parameter changes may conflict with automated systems."

# 6  Session-Mode Panels

The control panel reconfigures its Essential layer and Advanced section ordering based on the active session mode. Mode is detected automatically from live_control.json state by the detect_session_mode() method.

## 6.1  Trance Panel

The default mode. The Essential layer shows: gain controls (master, TTS, music, nature), session arc dropdown, trance_score gauge with sparkline, heart rate with sparkline, EEG signal quality indicator, conductor phase badge, session phase badge, session intensity gauge, and session elapsed timer. If strategy_auto_select is off, the induction strategy dropdown is promoted to Essential.

Advanced sections are ordered: Induction > Visual/Audio > Stimulus > Conditioning > Habituation > Content > DeliveryGate > Physiological. This ordering places the most user-relevant tuning (induction strategy, visual/audio preferences) closest to the Essential layer, with increasingly internal subsystems further down.

## 6.2  GENUS Panel

Activated when the session includes a GENUS block (Bible Ch.6 Â§SOC). The Essential layer shows: GENUS toggle, GENUS arc selector, GENUS phase badge, gamma verification indicator, GENUS session timer, gain controls (audio only — visual gain controls are hidden during GENUS blocks), heart rate with sparkline, and EEG signal quality.

The Frequency Exclusivity rule from Bible Ch.6 Â§SOC is enforced in the panel: alpha/theta entrainment controls (entrainment_frequency, beat_frequency, gain_isochronic, gain_binaural) are disabled and rendered with 50% opacity. A tooltip on each disabled control reads: "Disabled during GENUS — 40 Hz gamma entrainment is mutually exclusive with alpha/theta entrainment."

Advanced sections are ordered: GENUS > Visual/Audio > Physiological. Conditioning, Habituation, Content, and Induction sections are hidden (not collapsed — fully removed from the panel) during GENUS-only arcs. They reappear during GENUS_TRANCE_HYBRID transitions.

## 6.3  Sleep Panel

Activated when the session crosses into SLEEP_APPROACH phase. The Essential layer shows: sleep stage badge (color-coded: N1 = light blue, N2 = blue, N3 = deep blue, REM = purple, WAKE = yellow), sleep phase badge, deep sleep timer (cumulative N2+N3 time in MM:SS), cycle count, TMR toggle, TMR active indicator, HTW active indicator, heart rate, and a reduced gain control set (master and nature only — TTS and music sliders are hidden to avoid accidental audio spikes during sleep).

Trance-specific controls (induction strategy, stimulus spiral, session arc) are hidden. The session arc is implicitly SLEEP_BRIDGE and cannot be changed during sleep. Advanced sections are ordered: TMR > HTW > DeliveryGate > Physiological > Content.

## 6.4  Cue-Test Panel (PRE)

Activated during Portable Response Evaluator sessions. This is a minimal measurement panel. The Essential layer shows: EEG signal quality, heart rate, HRV RMSSD, trance_score, association_strength_current gauge for the pool being tested, conditioning_trial_count, and a pool selector dropdown. No gain controls are shown because there is no audio output during cue-test measurement. The panel is narrower (240px) to minimize visual interference with the cue-test stimulus display.

Advanced sections: Conditioning > Physiological. All other sections are hidden.

## 6.5  Mode Transitions

When the session transitions between modes (e.g., Trance → Sleep via the SLEEP_BRIDGE arc, or Trance → GENUS via a hybrid arc), the panel reconfigures over a 2-second animation window. The mode_transition_alpha float drives the transition: controls being hidden fade to 0% opacity and collapse, while controls being revealed expand and fade to 100% opacity.

Any user-locked parameters remain locked and visible regardless of mode transition. Locked parameters that would normally be hidden by the new mode are pinned to a dedicated "Locked Parameters" section at the top of the Advanced area, immediately below the Essential layer. This ensures the user never loses sight of parameters they have explicitly taken control of. The lock icon and current value remain visible, and the user can unlock the parameter from this pinned section.

# 7  Authority Integration & Lock Protocol

## 7.1  The source Tag

Every key in live_control.json gets a companion metadata key: {key}source. This tag records which system component last wrote the value. Possible values:


| **Source Value** | **Writer**             | **Priority** | **Description**                                                                                     |
| ---------------- | ---------------------- | ------------ | --------------------------------------------------------------------------------------------------- |
| "config"         | Configuration defaults | Lowest       | Set during session initialization from config files. Baseline values.                               |
| ---              | ---                    | ---          | ---                                                                                                 |
| "conductor"      | Conductor tick logic   | Low          | Set by the Conductor's per-tick automation (entrainment tracking, gain ramping).                    |
| ---              | ---                    | ---          | ---                                                                                                 |
| "director"       | SessionDirector        | Medium       | Set by the SessionDirector's macro-level session management (arc progression, phase transitions).   |
| ---              | ---                    | ---          | ---                                                                                                 |
| "agent"          | LLM Agent              | High         | Set by the LLM agent via patch_live() calls. Reflects intelligent, context-aware parameter choices. |
| ---              | ---                    | ---          | ---                                                                                                 |
| "user"           | User via control panel | Highest      | Set when the user adjusts a widget. Locks the parameter for the session.                            |
| ---              | ---                    | ---          | ---                                                                                                 |


The writer priority chain from Bible Ch.4 Â§DeliveryGate applies: User > Agent > SessionDirector > Conductor > Config. A higher-priority writer can always overwrite a lower-priority writer's value. A lower-priority writer cannot overwrite a higher-priority writer's value while the higher-priority lock is active.

When the user adjusts a slider, toggle, or dropdown in the panel, the following sequence executes within a single frame:

1. The new value is written to live_control.json immediately via patch_live().
2. The companion {key}source is set to "user".
3. The key name is added to the timeline_locked_params set (Bible Ch.5 Â§Session-Director).
4. The widget renders a visual lock indicator — a small padlock icon to the left of the label — showing it is user-locked.
5. The SessionDirector receives the lock event on its next tick and marks this parameter as off-limits for the remainder of the session.

## 7.2  Unlocking

User-locked parameters can be unlocked through three mechanisms:

- **Manual unlock:** The user clicks the padlock icon on the widget. The source tag is reset to "director" (or "conductor" if the Director has no opinion on this key). The key is removed from timeline_locked_params. The Director is free to adjust this parameter on its next tick.
- **Session end:** All locks are cleared automatically when the session ends. The timeline_locked_params set is emptied.
- **Reset All Locks:** The user presses the "Reset All Locks" button in the panel header (or Ctrl+Shift+R). All locked parameters are unlocked simultaneously. A confirmation dialog is shown: "Unlock all N parameters? The session optimizer will resume full control."

There is no timeout-based unlock. If the user locks gain_master at 0.3, it stays at 0.3 until they unlock it or the session ends. The Director and agent must work around the constraint. This is intentional: the user's explicit choice is sovereign.

## 7.3  Lock Cascade Awareness

The ControlPanelManager tracks the number of user-locked parameters and writes director_locked_param_count to live_control.json every frame. This telemetry key is visible in the Advanced layer, giving both the user and the Director a real-time count of active constraints.

If the user locks contradictory parameters — for example, locking entrainment_frequency at 10 Hz while also locking beat_frequency at 4 Hz when the Director's current strategy requires them to be coupled — the panel displays an amber warning callout:

**Constraint Warning**

"Locked parameters may constrain session optimization. The Director has N fewer degrees of freedom."

The warning does not prevent the user from maintaining conflicting locks. It is informational, not prohibitive. The Director's decision log (visible in Debug mode) records every instance where it wanted to adjust a parameter but found it locked. Each log entry includes: the parameter name, the value the Director would have set, the current locked value, and the compensatory action taken (e.g., "Wanted to lower entrainment_frequency to 8 Hz for deepening, but it is user-locked at 10 Hz. Compensating by increasing gain_nature to 0.7 for additional relaxation pressure.").

If the user has locked more than 50% of the USER_CONTROL + AGENT_TUNABLE parameters for the current session mode, the agent may surface a contextual message: "You've locked a lot of parameters — the session optimizer has limited room to adapt. Consider unlocking some if you want the Director to handle optimization." This message appears at most once per session and is not repeated if dismissed.

## 7.4  Agent Source Tagging

When the LLM agent writes a key via patch_live(), it sets source to "agent". The panel renders agent-written values with a subtle robot icon (⚙ glyph, rendered in #6688cc) next to the value label. Director-written values show a gear icon. Config-written values show no icon (they are the default state).

This visual tagging lets the user see at a glance which parameters the agent has actively adjusted versus which are running on defaults or Director automation. It serves a transparency function: the user can observe the agent's work in real time without needing to enter Debug mode. If the user disagrees with an agent-written value, they can override it by adjusting the widget — this replaces "agent" with "user" and locks the parameter.

# 8  Widget Specifications

The following widget types are used across the control panel. Each maps to a specific Dear ImGui primitive or custom draw call.


| **Widget**     | **ImGui Primitive**            | **Description**                                                                                                       | **Used For**                           |
| -------------- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| Slider         | ImGui::SliderFloat             | Horizontal slider with value label and range. Snaps to 0.01 increments.                                               | Gain, frequency, amplitude controls    |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Toggle         | ImGui::Checkbox                | On/off switch.                                                                                                        | Feature enables (TMR, ASMR, Shepard)   |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Dropdown       | ImGui::Combo                   | Dropdown selector for enum values.                                                                                    | Arc, strategy, paradigm selection      |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Badge          | ImGui::TextColored + custom bg | Colored pill showing current enum state. Colors mapped per value (e.g., N3 = deep blue, REM = purple, WAKE = yellow). | Phase, stage, lifecycle state          |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Gauge          | Custom ImGui draw              | Arc-shaped gauge 0–100% with color gradient (red → yellow → green).                                                   | trance_score, association_strength     |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Sparkline      | Custom ImGui draw              | Miniature time-series plot (last 60 seconds). 80px wide, 20px tall.                                                   | Heart rate, HRV, trance_score          |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Indicator      | ImGui::Text                    | Simple value display with label. Read-only.                                                                           | Agent-tunable params at Advanced layer |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Counter        | ImGui::Text                    | Integer display with label.                                                                                           | Trial counts, cycle counts             |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Timer          | ImGui::Text                    | MM:SS or HH:MM:SS format.                                                                                             | Session elapsed, deep sleep time       |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Progress Bar   | ImGui::ProgressBar             | Horizontal fill bar 0–100%.                                                                                           | Induction progress                     |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Phase Ring     | Custom ImGui draw              | Circular indicator showing 0–1 phase position.                                                                        | Breath phase, cardiac phase            |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Gate Indicator | Custom ImGui draw              | 4 horizontal dots (resp, alpha, cardiac, SQI). Green = pass, red = fail. Compact quad-gate visualization.             | DeliveryGate status                    |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Alert Badge    | ImGui::TextColored             | Red pulsing badge for critical states.                                                                                | Signal lost, motion contaminated       |
| ---            | ---                            | ---                                                                                                                   | ---                                    |
| Text           | ImGui::TextWrapped             | Multi-line text display.                                                                                              | Decision log, debug info               |
| ---            | ---                            | ---                                                                                                                   | ---                                    |


# 9  ControlPanelManager Class

## 9.1  WidgetSpec Dataclass

from dataclasses import dataclass, field @dataclass class WidgetSpec: """ Declarative specification for a single control panel widget. Loaded from panel_config.json at startup. """ key: str widget_type: str # "slider", "toggle", "dropdown", "badge", # "gauge", "sparkline", "indicator", "counter", # "timer", "progress_bar", "phase_ring", # "gate_indicator", "alert_badge", "text" classification: str # "USER_CONTROL", "AGENT_TUNABLE", # "TELEMETRY", "INTERNAL" layer: str # "ESSENTIAL", "ADVANCED", "DEBUG" label: str # Human-readable label range_min: float | None = None range_max: float | None = None enum_values: liststr | None = None session_modes: liststr | None = None # None = all modes section: str = "General" badge_colors: dictstr, tuple | None = None # value -> (r, g, b) tooltip: str | None = None

## 9.2  ControlPanelManager

from *future*_ import annotations import json from collections import deque from enum import Enum, auto from typing import Any import imgui class SessionMode(Enum): TRANCE = auto() GENUS = auto() SLEEP = auto() CUE_TEST = auto() class DisclosureLayer(Enum): ESSENTIAL = auto() ADVANCED = auto() DEBUG = auto() class ControlPanelManager: """ Manages the Dear ImGui control panel for Somna. Instantiated once in the main render loop. Reads the live_control dict every frame. Writes user changes back via patch_live() with source: "user" tagging. """ # ---- construction ------------------------------------------------ def *init*(self, config_path: str = "panel_config.json"): self.widget_registry: dictstr, WidgetSpec = {} self.session_mode: SessionMode = SessionMode.TRANCE self.disclosure_layer: DisclosureLayer = DisclosureLayer.ESSENTIAL self.locked_params: setstr = set() self.sparkline_buffers: dictstr, deque = {} self.section_expanded: dictstr, bool = {} self.mode_transition_alpha: float = 1.0 self.previous_mode: SessionMode | None = None self.transition_timer: float = 0.0 self.load_config(config_path) def load_config(self, path: str) -> None: """Load widget definitions from panel_config.json.""" with open(path, "r") as f: data = json.load(f) for entry in data"widgets": spec = WidgetSpec( key=entry"key", widget_type=entry"widget", classification=entry"classification", layer=entry"layer", label=entry"label", range_min=entry.get("range", None, None)0, range_max=entry.get("range", None, None)1, enum_values=entry.get("enum"), session_modes=entry.get("modes"), section=entry.get("section", "General"), tooltip=entry.get("tooltip"), ) self.widget_registryspec.key = spec if spec.widget_type in ("sparkline", "gauge"): self.sparkline_buffersspec.key = deque(maxlen=60) # ---- public API -------------------------------------------------- def render(self, live_data: dictstr, Any) -> None: """Called every frame. Draws the entire control panel.""" self.detect_session_mode(live_data) self.update_sparklines(live_data) self.render_header(live_data) self.render_essential(live_data) if self.disclosure_layer in ( DisclosureLayer.ADVANCED, DisclosureLayer.DEBUG, ): self.render_advanced_sections(live_data) if self.disclosure_layer == DisclosureLayer.DEBUG: self.render_debug(live_data) self.write_panel_metadata(live_data) def set_disclosure_layer(self, layer: DisclosureLayer) -> None: """Switch the active disclosure layer.""" self.disclosure_layer = layer def unlock_param(self, key: str) -> None: """Remove a single user lock.""" self.locked_params.discard(key) # source reset handled by caller via patch_live() def unlock_all(self) -> None: """Remove all user locks.""" self.locked_params.clear() def get_locked_params(self) -> setstr: """Return the current set of user-locked parameter names.""" return set(self.locked_params) # ---- rendering (private) ----------------------------------------- def render_header(self, live_data: dict) -> None: """Panel title bar with layer toggle and Reset All Locks.""" ... def render_essential(self, live_data: dict) -> None: """Draw the Essential layer widgets for the current mode.""" ... def render_advanced_sections(self, live_data: dict) -> None: """Draw collapsible Advanced sections in mode-specific order.""" section_order = self.get_section_order() for section_name in section_order: keys = self.get_section_keys(section_name) self.render_advanced_section(section_name, keys, live_data) def render_advanced_section( self, section_name: str, keys: liststr, live_data: dict, ) -> None: """Draw one collapsible Advanced section.""" ... def render_debug(self, live_data: dict) -> None: """Draw Debug-only panels: raw JSON, decision log, gate viz.""" ... # ---- interaction ------------------------------------------------- def handle_user_change( self, key: str, old_value: Any, new_value: Any, ) -> None: """Lock parameter and write via patch_live().""" patch_live({key: new_value, f"{key}source": "user"}) self.locked_params.add(key) # ---- detection --------------------------------------------------- def detect_session_mode(self, live_data: dict) -> None: """Infer session mode from live_control state.""" prev = self.session_mode if live_data.get("genus_active"): self.session_mode = SessionMode.GENUS elif live_data.get("sleep_phase") in ( "SLEEP_APPROACH", "SLEEP_ONSET", "SLEEP_MAINTAIN", "SLEEP_TRAINING", ): self.session_mode = SessionMode.SLEEP elif live_data.get("cue_test_active"): self.session_mode = SessionMode.CUE_TEST else: self.session_mode = SessionMode.TRANCE if prev != self.session_mode: self.previous_mode = prev self.transition_timer = 2.0 # seconds # ---- sparklines -------------------------------------------------- def update_sparklines(self, live_data: dict) -> None: """Append current values to sparkline buffers (1 Hz).""" ... # ---- metadata writeback ------------------------------------------ def write_panel_metadata(self, live_data: dict) -> None: """Write panel state keys back to live_control.""" patch_live({ "panel_disclosure_layer": self.disclosure_layer.name, "panel_session_mode": self.session_mode.name, "panel_locked_count": len(self.locked_params), "timeline_locked_params": list(self.locked_params), }) # ---- helpers ----------------------------------------------------- def get_section_order(self) -> liststr: """Return section names in mode-appropriate order.""" orders = { SessionMode.TRANCE:  "Induction", "Visual/Audio", "Stimulus", "Conditioning", "Habituation", "Content", "DeliveryGate", "Physiological", , SessionMode.GENUS:  "GENUS", "Visual/Audio", "Physiological", , SessionMode.SLEEP:  "TMR", "HTW", "DeliveryGate", "Physiological", "Content", , SessionMode.CUE_TEST:  "Conditioning", "Physiological", , } return orders.get(self.session_mode, ordersSessionMode.TRANCE) def get_section_keys(self, section_name: str) -> liststr: """Return widget keys belonging to a section.""" return  k for k, v in self.widget_registry.items() if v.section == section_name 

## 9.3  Widget Registration Pattern

The ControlPanelManager is initialized with a list of WidgetSpec objects generated from panel_config.json. The widget layout is entirely data-driven — no widget is hardcoded in the render methods. Adding a new key in a future doc requires only a new entry in panel_config.json; no Python code changes are needed. The load_config() method parses the JSON, constructs WidgetSpec objects, populates the widget_registry dict, and initializes sparkline buffers for any widget type that requires time-series history.

The render methods iterate over the registry, filtering by layer, session_modes, and section to determine which widgets to draw. Widget type dispatch uses a dict mapping widget type strings to render functions, avoiding long if/elif chains.

# 10  live_control.json Schema Additions

The following metadata keys are added to live_control.json to support the control panel:


| **Key**                | **Type** | **Values**                                             | **Writer**          | **Description**                                                                                                          |
| ---------------------- | -------- | ------------------------------------------------------ | ------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| {key}source            | str      | "config" / "conductor" / "director" / "agent" / "user" | Any writer          | Source tag for every controllable key. Set automatically when any system component writes the companion key.             |
| ---                    | ---      | ---                                                    | ---                 | ---                                                                                                                      |
| panel_disclosure_layer | str      | "ESSENTIAL" / "ADVANCED" / "DEBUG"                     | ControlPanelManager | Current disclosure layer. Readable by the LLM agent to calibrate communication style.                                    |
| ---                    | ---      | ---                                                    | ---                 | ---                                                                                                                      |
| panel_session_mode     | str      | "TRANCE" / "GENUS" / "SLEEP" / "CUE_TEST"              | ControlPanelManager | Current detected session mode.                                                                                           |
| ---                    | ---      | ---                                                    | ---                 | ---                                                                                                                      |
| panel_locked_count     | int      | 0+                                                     | ControlPanelManager | Number of user-locked parameters.                                                                                        |
| ---                    | ---      | ---                                                    | ---                 | ---                                                                                                                      |
| timeline_locked_params | liststr  | parameter names                                        | ControlPanelManager | List of currently locked parameter names. Read by SessionDirector (Bible Ch.5 Â§Session-Director) to determine which parameters are off-limits. |
| ---                    | ---      | ---                                                    | ---                 | ---                                                                                                                      |


# 11  panel_config.json Schema

The panel_config.json file is the single source of truth for the widget registry. Its schema:

{ "version": 1, "widgets":  { "key": "gain_master", "widget": "slider", "classification": "USER_CONTROL", "layer": "ESSENTIAL", "label": "Master Volume", "range": 0.0, 1.0, "section": "Audio", "modes": null, "tooltip": "Overall output volume" }, { "key": "session_arc", "widget": "dropdown", "classification": "USER_CONTROL", "layer": "ESSENTIAL", "label": "Session Arc", "enum":  "GENTLE_DESCENT", "WAVE_PATTERN", "DEEP_PLATEAU", "CONDITIONING_FOCUS", "SLEEP_BRIDGE" , "section": "Session", "modes": "TRANCE", "tooltip": "Macro session shape — how the Director structures depth over time" }, { "key": "sleep_stage", "widget": "badge", "classification": "TELEMETRY", "layer": "ESSENTIAL", "label": "Sleep Stage", "enum": "WAKE", "N1", "N2", "N3", "REM", "section": "Sleep", "modes": "SLEEP", "badge_colors": { "WAKE": 255, 210, 63, "N1": 135, 206, 250, "N2": 70, 130, 200, "N3": 25, 50, 140, "REM": 148, 103, 189 }, "tooltip": "Current detected sleep stage" }  }

Schema rules:

- key (str, required): Must match the exact live_control.json key name.
- widget (str, required): One of the widget types defined in Section 8.
- classification (str, required): One of USER_CONTROL, AGENT_TUNABLE, TELEMETRY, INTERNAL.
- layer (str, required): One of ESSENTIAL, ADVANCED, DEBUG.
- label (str, required): Human-readable display label.
- range (listfloat, float, optional): For sliders. min, max.
- enum (liststr, optional): For dropdowns and badges. Valid value set.
- section (str, optional, default "General"): Subsystem grouping for Advanced layer sections.
- modes (liststr | null, optional): Session modes where this widget is visible. null = all modes.
- badge_colors (dictstr, listint, optional): For badges. Maps enum values to RGB triples.
- tooltip (str, optional): Hover text for the widget.

The full panel_config.json file is not included in this document — it will be generated from the key inventory tables in Section 4 during implementation. The schema definition above is the contract.

# 12  Emergent Properties

Several architectural properties emerge from the interaction between progressive disclosure, session-mode awareness, and the lock protocol. These are not additional features to implement — they are consequences of the design that should be recognized and preserved.

### 12.1  The Intent Surface

The disclosure layer the user operates at implicitly communicates their expertise and engagement level. A user who only touches Essential controls is delegating everything else to the Director and agent. A user who expands Advanced sections and adjusts color temperature is signaling visual sensitivity. A user in Debug mode tweaking fractal_dimension is asserting deep expertise. The agent can read panel_disclosure_layer from live_control.json and adjust its own communication style and parameter exploration aggressiveness accordingly. At Essential, the agent makes conservative, well-tested choices. At Debug, the agent can explore more aggressive parameter combinations, knowing the user is watching and capable of correcting.

### 12.2  Implicit Expertise Signaling

The set of locked parameters serves as a fingerprint of what the user cares about. If they consistently lock audio parameters but never touch visual ones, the agent learns (across sessions via the user_model in Bible Ch.5 Â§Session-Director) that this user is audio-sensitive and visual-indifferent. Future sessions can front-load audio optimization and use visual parameters as the primary compensatory degrees of freedom. The lock history, accumulated over sessions, becomes a richer signal than any explicit preference questionnaire.

### 12.3  The Observation Window

Even when the user cannot control a parameter (AGENT_TUNABLE or TELEMETRY), showing it creates an observation window. The user watches the agent work. This builds trust: "I can see it adjusting the spiral rate in response to my alpha power." It also provides feedback that helps the user make better decisions about which parameters to lock. A user who observes the agent consistently setting bg_color_temp to 2200 K might decide to lock it there, having learned that this value works well. The observation window turns passive telemetry into active learning.

### 12.4  Lock Pressure as Feedback

The director_locked_param_count metric creates a pressure signal. If the user has locked 15 parameters, the Director's degrees of freedom are severely constrained. The agent can surface this: "You've locked a lot of parameters — the session optimizer has limited room to adapt. Consider unlocking X if you want the Director to handle it." This is not a nag — it is actionable transparency. The user learns that their locks have consequences, and they can make an informed choice about which locks to release. Over time, users develop an intuitive sense of the right balance between personal control and system autonomy.

### 12.5  Mode Transitions as Narrative

The smooth panel reconfiguration during mode transitions (Trance → Sleep, Trance → GENUS) creates a visual narrative of the session's progression. Controls fading in and out reinforces the user's sense of journey — the session is going somewhere, not just looping. Sleep-specific controls appearing as the user descends toward sleep onset provides a tangible marker of progress. The panel becomes a secondary feedback channel, complementing the visual and audio experience with a structural representation of the session's arc.

# 13  Implementation Notes

- **ImGui integration:** Use pyimgui (imguiglfw) integrated into the existing ModernGL render loop. Call imgui.new_frame() at the start of each frame and imgui.render() at the end, before swap_buffers(). The ImGui renderer shares the OpenGL context with Somna's shader pipeline.
- **Performance:** The panel reads live_control.json once per frame (~60 fps). This is a dict lookup, not file I/O — the live_control dict is already in memory as part of the patch_live() infrastructure from Bible Ch.4 Â§DeliveryGate. No serialization or deserialization occurs during rendering.
- **Sparkline buffers:** Updated once per second (not every frame). A frame counter modulo 60 triggers the update. Each 60-entry deque holds the last 60 seconds of history. Sparkline rendering uses ImGui::PlotLines with a fixed-size buffer.
- **Color scheme:** Dark theme matching Somna's visual aesthetic. Background: #1a1a2e. Panel background: #16213e. Accent: #0f3460. Text: #e0e0e0. Alert: #e94560. The Ganzfeld background layer shows through the panel's semi-transparent background (alpha 0.85).
- **Panel position:** Right side of the screen, 320px wide, full height. Collapsible to a 40px tab on the screen edge. The main Somna visualization occupies the remaining screen space. The panel does not occlude the visual center point (fixation target).
- **Keyboard shortcuts:** Tab to toggle panel visibility. Ctrl+Shift+D to toggle Debug mode. Ctrl+Shift+R to reset all locks.

# 14  Database Tables

No new database tables are introduced. The panel is entirely session-scoped — locked parameters and disclosure state are not persisted across sessions (they reset at session start). The user_model in Bible Ch.5 Â§Session-Director's database already captures cross-session learning about user preferences, including which parameters the user tends to lock.

One column is added to Bible Ch.5 Â§Session-Director's session_history table:


| **Column**         | **Type** | **Description**                                                                                                                                                 |
| ------------------ | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| params_locked_peak | INTEGER  | Maximum number of simultaneously locked parameters during the session. Useful for understanding user engagement patterns and control style evolution over time. |
| ---                | ---      | ---                                                                                                                                                             |


— End of Bible Ch.9 Â§Control-Panel —