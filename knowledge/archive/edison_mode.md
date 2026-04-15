# Edison Mode — Hypnagogic Creativity Capture
*Knowledge-Base Reference | v1.0 | 29 March 2026*

---

## The Science of Hypnagogia

### What Is Hypnagogia

The transitional state between wakefulness and sleep, corresponding to NREM Stage 1 (N1). Duration: typically 1–7 minutes.

Characterized by vivid dreamlike imagery, loosened associative thinking, and preserved partial awareness. The brain does not fall asleep at once — subcortical regions (thalamus, hippocampus) deactivate first, then drowsiness propagates cortex front-to-back. This phased descent can take up to 20 minutes (Lacaux et al. 2024, Trends in Neurosciences).

Critically: individuals can still respond to external stimuli during N1 while simultaneously having dream-like experiences. This is the property that makes Edison Mode possible.

### Historical Precedent

Thomas Edison, Salvador Dalí, and others used physical sleep-onset detection to harvest hypnagogic creativity. Edison held steel balls over metal pans — falling balls woke him at sleep onset, and he immediately recorded his ideas.

Somna's Edison Mode replaces the physical object with EEG detection, providing more precise timing and the ability to deliver seed prompts.

### Dormio and Targeted Dream Incubation (TDI)

MIT Dormio (Horowitz, Esfahany et al. 2023, Scientific Reports): Developed Targeted Dream Incubation (TDI) — auditory cues at sleep onset to introduce specific themes into hypnagogic dreams.

Key findings:
- N1 sleep enhanced creative performance compared to wakefulness
- Successful dream incubation (theme appearing in dream content) enhanced creativity more than N1 sleep alone
- **43% improvement** in creativity tasks when TDI was successful, with greater semantic distance in responses (more divergent, associative thinking)

This is the first controlled experiment demonstrating a direct role of incubated dream content in enhancing creative performance.

---

## EEG Markers of Hypnagogia

### N1 Entry: Alpha Dropout + Theta Surge

**This is one of the cleanest detection tasks in the entire EEG pipeline — it is a sharp state transition, not a gradual one.**

- Alpha rhythm dropout is the first reliable EEG sign of drowsiness (Lacaux et al. 2024)
- Theta power surges as alpha drops
- On Muse 2: AF7/AF8 (frontal channels — note: `get_eeg_names()` incorrectly returns Fp1/Fp2) are best positioned for alpha dropout detection. TP9/TP10 (temporal) provide supporting data.
- **Use IAF-personalized band boundaries** from `iaf_band_boundaries` in `user_profile.json` — the theta/alpha boundary at `IAF − 2` Hz is critical for accurate detection

### Detection Thresholds (Starting Points — Require Empirical Calibration)

| State | Alpha/Theta Ratio | Notes |
|-------|-------------------|-------|
| Wakefulness baseline | 1.5–3.0 | During relaxed eyes-closed |
| AWAKE (clear) | > 1.2 | |
| N1_ENTRY (transitional) | 0.8–1.2 | Alpha dropping but not yet theta-dominant |
| N1 (hypnagogia) | < 0.8, sustained 3+ seconds | **Capture window** |
| N2_WARNING | Sigma burst (11–16 Hz) present, theta sustained > 60s | Too deep — deliver wake cue |

### N2 Detection: The "Too Deep" Boundary

N2 sleep = content is lost. When N2 is detected, deliver a slightly louder wake cue.

N2 markers:
- Sleep spindles: transient sigma-band bursts (11–16 Hz, 0.5–2 seconds) — use `get_custom_band_powers([(12.0, 15.0)])` to monitor sigma
- Sustained theta without alpha recovery for > 60 seconds

### BrainFlow Detection Code

```python
from brainflow.data_filter import DataFilter

def detect_sleep_state(eeg_data, channels, sampling_rate, iaf_hz=10.0):
    """Classify: AWAKE | N1_ENTRY | N1 | N2_WARNING
    
    Uses IAF-personalized boundaries — pass iaf_hz from user_profile.json.
    iaf_band_boundaries["theta"] upper bound = IAF - 2 (theta/alpha boundary).
    """
    bands, stds = DataFilter.get_avg_band_powers(eeg_data, channels, sampling_rate, True)
    theta_power = bands[1]
    alpha_power = bands[2]

    sigma_bands = DataFilter.get_custom_band_powers(
        eeg_data, [(12.0, 15.0)], channels, sampling_rate, True
    )
    sigma_power = sigma_bands[0][0] if sigma_bands else 0.0

    ratio = alpha_power / max(theta_power, 1e-10)

    if ratio > 1.2:
        return "AWAKE"
    elif ratio < 0.8:
        if sigma_power > SIGMA_THRESHOLD:  # calibrate empirically per user
            return "N2_WARNING"
        return "N1"
    else:
        return "N1_ENTRY"
```

New `live_control.json` keys written by `eeg_engine.py`:
- `eeg_sleep_state` — `"AWAKE"` | `"N1_ENTRY"` | `"N1"` | `"N2_WARNING"`
- `eeg_alpha_theta_ratio` — float, current ratio
- `eeg_n1_entry_timestamp` — ISO timestamp when N1 was first detected

---

## Session Protocol

### Phase 1: Preparation (5 minutes)
- Visual dims to near-black (disable spirals, low brightness)
- Optional: low-amplitude delta/theta binaural beats to gently encourage drowsiness
- Agent TTS: "Edison Mode starting. Get comfortable. I'll guide you through creative capture. Close your eyes when ready."

### Phase 2: Seed Prompt Delivery (TDI component)
- Agent delivers creative seed via TTS: "As you drift, think about [topic]. Let it float. Don't hold on to anything."
- Seed topic: user-specified or agent-selected from context
- `voice_mode: "tts"` — must be audible, NOT subliminal
- After delivery, agent enters silent monitoring mode

### Phase 3: Descent Monitoring
- `eeg_engine.py` writes `eeg_sleep_state` every second
- `somna_agent.py` reads and tracks state transitions
- No TTS during descent — silence is essential

### Phase 4: Capture Wake
- After `edison_n1_hold_seconds` (default 60s) OR on N2_WARNING:
  - Normal: gentle TTS: "What were you just experiencing?"
  - N2 rescue: louder, assertive TTS: "Come back now. What did you see?"
  - Optional: brief display brightness pulse to assist waking

### Phase 5: Capture and Log
- Agent captures user's report via `user_console_input`
- Log the capture event to session JSONL:
```json
{
  "event": "edison_capture",
  "timestamp": "2026-04-01T23:15:30",
  "seed_topic": "fractal geometry",
  "n1_duration_seconds": 47,
  "alpha_theta_ratio_at_capture": 0.62,
  "user_report": "Saw crystalline structures growing from equations...",
  "dominant_band": "theta",
  "eeg_snapshot": {"delta": 0.31, "theta": 0.42, "alpha": 0.18, "beta": 0.06, "gamma": 0.03}
}
```
- Agent may ask follow-up questions to enrich the capture
- Cycle repeats automatically

### Phase 6: Session End
- After configured cycles (default 3–5) or user exit
- Agent summarizes all captures, saves full JSONL log

---

## Session YAML Template

```yaml
name: "Edison Mode — Creative Capture"
type: edison
description: "Hypnagogic creativity capture with EEG-guided wake timing"
duration_minutes: 30
settings:
  bg_mode: "none"
  bg_brightness: 0.05
  beat_type: "binaural"    # generation mode — binaural/isochronic/both
  carrier_hz: 200
  beat_hz: 4.0             # 4 Hz delta/theta boundary — assists descent
  volume: 0.15
  eeg_monitoring: true
  edison_mode: true
  edison_seed_topic: null  # set by agent or user
  edison_n1_hold_seconds: 60
  edison_max_cycles: 5
  edison_n2_wake_volume: 0.8
keyframes: []
# Edison Mode is state-driven, NOT timeline-driven.
# Do not use keyframe interpolation from timeline_runner.py.
```

---

## Agent State Machine

| # | State | Trigger | Action | Transition |
|---|-------|---------|--------|------------|
| 1 | IDLE | User starts Edison Mode | — | PREPARING |
| 2 | PREPARING | Entry | Deliver instructions, set up environment | SEED_DELIVERY |
| 3 | SEED_DELIVERY | Environment ready | Deliver creative seed via TTS | MONITORING |
| 4 | MONITORING | Seed delivered | Watch `eeg_sleep_state` | HOLDING (on N1) |
| 5 | HOLDING | N1 confirmed | N1 timer running, no prompts | WAKING (timer/N2) |
| 6 | WAKING | Timer expires or N2_WARNING | Deliver wake cue, await response | CAPTURING |
| 7 | CAPTURING | User responds | Record report, ask follow-ups | MONITORING (next cycle) or END |
| 8 | END | Max cycles or user exit | Summarize, save logs | — |

### Key Behavioral Rules

| Rule | Specification |
|------|---------------|
| PASSIVITY | **Never deliver prompts during N1 hold phase.** Any auditory stimulus risks premature waking. |
| PATIENCE | Don't rush the descent. Some users take 10+ minutes to reach N1. Agent must not fill silence with prompts. |
| CAPTURE PRIORITY | Hypnagogic content fades within 30–60 seconds. Get the user talking immediately after wake cue. |
| ADAPTATION | If user consistently fails to reach N1, suggest darker/cooler room, later time of night. |

### Example Prompts

| Context | Prompt |
|---------|--------|
| Preparation | "Edison Mode starting. This session will catch creative insights at the edge of sleep. Get comfortable, close your eyes when ready." |
| Seed delivery | "As you drift, think about [topic]. Let it float. Don't hold on to anything." |
| Wake cue (normal) | "Gently come back. What were you just thinking about? What images did you see?" |
| Wake cue (N2 rescue) | "Hey — come back now. Tell me what was just happening." |
| Cycle restart | "Good capture. Close your eyes again when you're ready for another round." |
| Session summary | "You completed [N] capture cycles tonight. Here's what emerged: [summaries]." |

---

## Integration Details

### `live_control.json` Keys for Edison Mode

```json
{
  "edison_active": true,
  "edison_state": "MONITORING",
  "edison_seed_topic": "fractal geometry",
  "edison_cycle_count": 2,
  "edison_n1_hold_seconds": 60,
  "eeg_sleep_state": "N1",
  "eeg_alpha_theta_ratio": 0.62,
  "eeg_n1_entry_timestamp": "2026-04-01T23:14:43"
}
```

### Module Roles

| Module | Role | Key Detail |
|--------|------|------------|
| `eeg_engine.py` | Writes `eeg_sleep_state`, `eeg_alpha_theta_ratio` to `live_control.json` | Via `_patch_live()` |
| `somna_agent.py` | Reads EEG state, manages state machine, delivers TTS prompts | Central orchestrator |
| `tts_engine.py` | Delivers seed prompts and wake cues | `voice_mode: "tts"` — NOT subliminal |
| `visual_display.py` | Dims to near-black during descent, brightness pulse on wake cue | Disable spirals |
| `audio_engine.py` | Optional theta binaural beats at low volume to assist descent | `beat_type`, `beat_hz` |

### Board and Channel Details

| Parameter | Value |
|-----------|-------|
| Board ID | `BoardIds.MUSE_2_BOARD = 38` (native BLE, no dongle — never use 22) |
| Primary detection channels | AF7 (index 1), AF8 (index 2) — frontal, best for alpha dropout |
| Supporting channels | TP9 (index 0), TP10 (index 3) — temporal |
| Sampling rate | 256 Hz (DEFAULT_PRESET) |
| Window read | `get_current_board_data(256)` — non-destructive, 1-second window |
| Dev board | `BoardIds.SYNTHETIC_BOARD = -1` |

---

## Critical Implementation Notes

- Alpha/theta thresholds (0.8 / 1.2) are starting points. **Require empirical calibration on real hardware.**
- N1 hold duration (default 60s) must be configurable. Dormio research used variable durations.
- Edison Mode is **state-driven, NOT timeline-driven**. The `keyframes` array is empty intentionally. Do not use `timeline_runner.py` interpolation.
- The seed prompt is optional — Edison Mode works without TDI, it just becomes a pure Edison ball-drop analog.
- Log alpha/theta ratio at every second during session. All state transitions. All captures. This is the calibration dataset.
- Always use IAF-personalized band boundaries if `iaf_hz` is set in `user_profile.json`.
- All `live_control.json` writes use `_patch_live()` — not `llm_driver.send()`.

---

## References

1. Horowitz AH, Esfahany K, Gálvez TV, Maes P, Stickgold R (2023). Targeted dream incubation at sleep onset increases post-sleep creative performance. *Scientific Reports*, 13, 7319.
2. Lacaux C, Strauss M, Bekinschtein TA, Oudiette D (2024). Embracing sleep-onset complexity. *Trends in Neurosciences*, 47(4), 273–288.
3. Gonzalez CE et al. (2018). Theta Bursts Precede, and Spindles Follow, Cortical and Thalamic Downstates in Human NREM Sleep. *Journal of Neuroscience*, 38(46), 9989–10001.
4. Lacaux C, Andrillon T, Arnulf I, Oudiette D (2022). Memory loss at sleep onset. *Cerebral Cortex Communications*, 3(4), tgac042.
