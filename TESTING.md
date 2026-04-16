# Somna — Testing Checklist

Bible chapters covered: Ch.2–Ch.11.  Three steps, in order:

1. `**python smoke_test.py`** — automated, no hardware, ~4 seconds, 153 checks.
2. **Session-required checks** — synthetic board (`eeg_board_id: -1`), no Muse 2 needed.
3. **Hardware validation** — Muse 2 required, block until hardware arrives.

**Legend:** `[ ]` not tested  `[x]` passed  `[!]` failed

---

## Step 1 — Run the smoke test

```
python smoke_test.py
```

That's it. All 153 pure-function and import-level checks run automatically and
print a green/red summary. If it exits with code 0, everything below marked
"automated" is already verified. If any check is red, fix it before moving on.

**[x] 153 passed, 0 failed, 0 skipped — 2026-03-27**

---

## Step 2 — Session-required checks (synthetic board, no hardware)

These need `python main_imgui.py` running with a sleep-type session and
`eeg_board_id: -1` in `agent_config.yaml`.

### Ad-hoc verified (2026-03-27, synthetic board, sleep_default session)

These were confirmed via console log inspection across multiple test runs this session:

```
[x] Conductor initialises on fresh session start
[x] Conductor initialises correctly after stop → start cycle (restart detection)
[x] Timer-mode phase progression: calibration → induction → deepening → maintenance → sleep_approach
[x] Timer-mode never regresses to an earlier phase (sleep_approach → maintenance regression fixed)
[x] FreqLeader activates with matching start/target Hz (no 4 Hz snap, no immediate deactivation)
[x] Agent session debounce: transient "default" session_folder no longer hijacks running session
[x] Background layer: imageless sessions load 0 images, no console spam from default session
[x] Click-through and always-on-top persist across stop → start cycles
[x] Audio: no static burst on session load when beats are muted
[x] Audio: no hitching when beats are muted (binaural channel stays alive at vol=0)
[x] EEG scoring summary: no double-post in agent console (2026-03-27 fix)
[x] Veil scroll: surface fills fully in all 5 layout patterns, no cutoff (2026-03-27 fix)
[x] Agent startup fires only once per session: false inactive detection fixed (session_time=0
    write removed; stale threshold raised 60s → 180s to accommodate LLM call duration)
[x] Noise color/volume sliders: sleep session responds correctly
[~] Fractionation: agent-triggered behavior confirmed working in prior session; full
    deliberate test deferred until fractionation gets the Reese design-doc overhaul
[x] TTS subliminal mode: phrases delivered correctly when active
[x] Agent console: bidirectional send/receive and dedup working
```

*Sleep staging checks require real N1/N2/N3 classifications from the sleep classifier,
which needs genuine EEG signal. The synthetic board produces calibration noise only —
not sleep-stage patterns. These checks have been moved to Step 3 (hardware required).*

---

## Step 3 — Hardware validation (requires Muse 2, board_id=38)

*Block on hardware arrival.*

**Sleep training / SESSION_END flow** (requires real sleep session reaching N2/N3):

```
[ ] Phase.SLEEP_TRAINING entered after 60+ min N2/N3 and a natural N1 window
[ ] On SLEEP_TRAINING entry: live_control.json has tts_use_presynth=true,
    gain_mode="sleep_training", beat_frequency=5.5, tts_volume=6
[ ] On SLEEP_TRAINING exit: gain_mode reverts to "sleep_maintain",
    tts_use_presynth=false, previous affirmations_pool restored
[ ] sleep_training_log has a new row in somna.db after exit
[ ] SESSION_END: pending_sleep_debrief key present in live_control.json,
    agent_sleep_plan cleared to {}
[ ] First console message after SESSION_END references stage distribution or HTW count
[ ] pending_sleep_debrief absent from live_control.json after that message
```

**Core biometrics** (verify after ~20s warmup at rest):

```
[ ] PPGEngine: ppg_heart_rate in [40, 130] BPM at rest after ~20s warmup
[ ] PPGEngine: ppg_hrv_rmssd changes with relaxation vs attention
[ ] PPGEngine: ppg_breath_rate in [0.15, 0.40] Hz (9-24 breaths/min) at rest
[ ] RespiratoryTracker: respiratory_mode switches to "ppg" within ~20s of start
    (verify live_control.json respiratory_mode key)
[ ] IMUEngine: imu_stillness_index > 0.90 while sitting still for 5s
[ ] IMUEngine: imu_motion_contaminated=True immediately on intentional movement
[ ] IMUEngine: imu_motion_contaminated=False within 2s of returning to rest
[ ] DeliveryGate: affirmation flashes stop during intentional head movement
[ ] Full sleep session: after 1hr N2/N3, SLEEP_TRAINING entered on natural N1
[ ] Full sleep session: pending_sleep_debrief written at session end
```

---

## Section 14 — Calibration Protocol (Bible Ch.2 §2.6)

*Automated (imports, thresholds, math): covered by `smoke_test.py`.*

Needs hardware (Muse 2 + real session):

```
[ ] advance_session() persists session_count correctly to user_profile.json
[ ] After 10 real sessions, calibration summary in user_profile.json contains
    "sef95_floor", "sef95_ceiling", "iaf_hz", "calibration_complete": True
[ ] Phase-gate thresholds visibly looser after calibration vs population defaults
    (compare session 1 vs session 11 phase transition speed)
```

---

## Section 15 — Three-axis depth estimation (Bible Ch.2 §2.8)

*Automated (all pure functions): covered by `smoke_test.py`.*

Needs hardware (real EEG signal):

```
[ ] eeg_spectral_slope published in live_control.json during a session
    (verify it's in range -1.0 to -3.0 and changes with relaxation)
[ ] eeg_trance_score_v2 increases during deepening vs baseline
[ ] Phase transitions using convergent_check (two-of-three rule) are
    slower / more stable than single-axis thresholds were
```

---

## Section 16 — Crossmodal gain manifold (Bible Ch.3 §3.8)

*Automated (engine instantiation, profiles, tick, SR math): covered by `smoke_test.py`.*

Needs hardware / live session:

```
[ ] crossmodal_gain_state key appears in live_control.json during a session
[ ] depth_gain_scalar visibly increases as EEG trance score rises
[ ] SR calibration sweep completes during CALIBRATION phase and writes
    sr_optimal_noise to user_profile.json
[ ] Verified in a session: noise near sr_optimal_noise noticeably improves
    text veil contrast vs noise at 0 or 80
```

---

## Section 17 — Semantic content selector (Bible Ch.6 §6.6)

*Automated (import): covered by `smoke_test.py`.*

Needs live session with affirmations:

```
[ ] Phrases from correct pool appear in visual layers during matching session phase
[ ] Pool weight bias observable over 10+ consecutive phrases (depth pool phrases
    appear more often at high trance score vs at baseline)
[ ] Priming cascade: shadow phrase fires before center phrase fires before voice
    fires — verify ordering in session_log JSONL
```

---

## Section 18 — Phase-cascade delivery gate (Bible Ch.4 §4.6 / Ch.2 §2.7)

*Automated (all gate logic, motion block, rate limiter, diagnostics): covered by `smoke_test.py`.*

Needs hardware (real EEG + respiratory signal):

```
[ ] phase_gate_hit_rate in live_control.json increases over a session
    as EEG and respiratory synchrony improves
[ ] Affirmation flash timing visibly aligns with breathing rhythm when
    phase_gate_enabled=True (compare to fixed duty cycle mode)
[ ] With Muse 2 and motion: imu_motion_contaminated=True appears in
    live_control.json during intentional head movement and delivery stops
```

---

## Section 19 — Sleep stage classifier (Bible Ch.7 §7.1)

*Automated (classify logic, threshold update, confidence): covered by `smoke_test.py`.*

Needs hardware (real overnight EEG signal):

```
[ ] sleep_stage key in live_control.json cycles through WAKE/N1/N2/N3 over
    a real sleep session (not stuck at WAKE)
[ ] stage confidence stays > 0.5 for > 80% of a clean signal epoch
[ ] Stage transitions match expected sleep architecture (WAKE -> N1 -> N2 -> N3
    within first 30 min for a typical sleeper)
```

---

## Section 20 — Spindle detector (Bible Ch.7 §7.2)

*Automated (import): covered by `smoke_test.py`.*

Needs hardware (real N2 sleep EEG):

```
[ ] spindle_density > 0 during confirmed N2 stage in a real sleep session
[ ] spindle_density == 0 during WAKE (no false positives on waking EEG)
[ ] Spindle events visible in sleep_stage_log in somna.db after a session
```

---

## Section 21 — Slow-wave enhancer (Bible Ch.7 §7.3–§7.4)

*Automated (import): covered by `smoke_test.py`.*

Needs hardware (real N3 sleep EEG):

```
[ ] slow_wave_active key appears in live_control.json during confirmed N3
[ ] Pink noise bursts audible on channel 3 during N3 (verify with audio monitor
    or by checking audio_engine channel 3 active flag)
[ ] SWE burst count visible in sleep_stage_log after a sleep session
[ ] No SWE bursts fire during WAKE or REM (slow_wave_active=False then)
```

---

## Section 22 — Targeted memory reactivation (Bible Ch.7 §7.5–§7.6)

*Automated (hash determinism, jitter ranges, envelope shape, audio generation, inverted-U math, empty scheduler): covered by `smoke_test.py`.*

Needs live session + hardware:

```
[ ] After a trance session with affirmations: tmr_cue_registry in somna.db
    has rows with encoding_count > 0
[ ] During sleep session (N2/N3): tmr_replay_log rows appear at ~30s intervals
[ ] TMR cue audible on channel 6 (use audio monitor or channel 6 active flag)
[ ] eeg_signal_lost=True in live_control.json causes TMR to stop firing
    (verify via tmr_replay_log timestamps — gap > 5 min after signal loss)
[ ] SWE and TMR lockouts don't overlap: no simultaneous burst + cue (verify
    via tmr_replay_log and slow_wave_active flag timestamps)
```

---

## Section 23 — VR safety enforcer (Bible Ch.8 §8.1–§8.4)

*Automated (enforce_depth, enforce_max_freq, check_paroxysmal, SafetyEnforcer instantiation and kill): covered by `smoke_test.py`.*

Needs VR headset:

```
[ ] First VR session: session_max_depth capped at 0.10 (not full depth)
[ ] After advance_ramp_for_next_session() × 7: depth reaches 0.40 ceiling
[ ] Photosensitivity warning displayed before first session
[ ] record_acknowledgment() required before stimulation starts
```

---

## Section 24 — VR frequency allocation table (Bible Ch.8 §8.1–§8.4)

*Automated (collision detection, validate(), build_session_table, safe pair suggestion): covered by `smoke_test.py`.*

Needs VR headset:

```
[ ] Session start with collision-prone freqs raises ValueError and prevents launch
[ ] build_session_table called at VR session start in vr_display_runner.py
    (verify via session log or by inserting a conflicting freq and watching it refuse)
```

---

## Section 25 — VR dichoptic flicker engine (Bible Ch.8 §8.1–§8.4)

*Automated (import): covered by `smoke_test.py`.*

Needs VR headset (visual confirmation):

```
[ ] Ganzfeld mode: both eyes see uniform flickering field at set frequency
[ ] Rivalry mode: left/right eyes see visibly alternating stimuli
[ ] SSVEP mode: frequency matches requested Hz (confirm with SSVEP detector SNR)
[ ] Mode transitions: no visible flash or discontinuity at switchover
```

---

## Section 26 — VR SSVEP detector (Bible Ch.8 §8.1–§8.4)

*Automated (_snr_at_freq, _correct_1f pure helpers): covered by `smoke_test.py`.*

Needs VR headset + Muse 2:

```
[ ] ssvep_detected=True appears in live_control.json during SSVEP stimulation
[ ] ssvep_snr > 6 dB at the driving frequency during confirmed entrainment
[ ] binocular_index > 0.5 during rivalry mode (both eyes driven)
[ ] switch_rate_hz > 0 during rivalry (perceptual alternation detected)
[ ] Binocular index corroborates Conductor INDUCTION phase transition
    (check conductor log for "ssvep_corroborated" transition reason)
```

---

## Section 27 — VR ganzfeld + vection (Bible Ch.8 §8.5–§8.6)

*Automated (import): covered by `smoke_test.py`.*

Needs VR headset (visual confirmation):

```
[ ] Ganzfeld onset: luminance ramps up smoothly over onset_duration_s (not instant)
[ ] Equilibration phase visible as steady uniform field before flicker starts
[ ] Vection tunnel: optic flow visible and speed feels manageable at session cap
[ ] Adaptive throttle: vection speed reduces when binocular_index is high
    (verify by watching vection_speed key in live_control.json)
```

---

## Section 28 — VR depth-plane subliminal (Bible Ch.8 §8.5–§8.6)

*Automated (import): covered by `smoke_test.py`.*

Needs VR headset (visual confirmation):

```
[ ] Phrases appear at three distinct apparent depths in the VR scene
[ ] Far-plane phrases have longer flash duration than near-plane (VAC mitigation)
[ ] agent next_affirmation is auto-routed 4:4:1 far:mid:near when VR active
    (verify via plane_state_dict in a debug run)
[ ] SOA flashes fire independently per plane (no synchronised triple flash)
```

---

## Known deferred items (waiting on Reese / hardware)

- **Cardiac phase gating (Bible Ch.2 §2.10)**: R-peak → systole/diastole segmentation →
fourth DeliveryGate condition. Requires literature validation of exact timing
parameters (systole duration vs heart rate curve). Hold until Reese returns.
- **HRV as convergent depth axis**: ppg_hrv_rmssd is already written to
live_control.json by PPGEngine. Not yet injected into agent context as a
depth signal or into CrossmodalGainEngine. Low-hanging fruit once hardware
confirms RMSSD tracking is reliable.
- **imu_head_nod_detected → sleep classifier boost**: flag is written to
live_control.json but not yet read by SleepStageClassifier or Conductor
transitions. One-line addition when hardware testing confirms the signal.

