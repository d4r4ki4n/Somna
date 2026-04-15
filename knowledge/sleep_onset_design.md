# Sleep Onset Session Design Reference
*Doc #15 · Research · 30 March 2026*
*YAML Keyframe Timeline Design for Wakefulness → Hypnagogia → N1 → N2+*
*Target: timeline_runner.py, somna_agent.py, live_control.json*

---

## Critical Context — Extreme Aphantasia

The user has extreme aphantasia. Visualization-based sleep onset is ineffective. The agent facilitates sleep onset via **audio parameter progression** — NOT verbal imagery narration. No guided imagery. No "picture a beach." Audio frequencies and somatic cues only.

---

## Scope

This document covers standard sleep onset. It does **NOT** cover:
- Edison Mode (Doc #8) — inverted goal; targets hypnagogia boundary to cause arousal
- SSILD (Doc #5) — WBTB middle-of-night protocol, not sleep onset

---

## 1. Sleep Architecture

### The 90-Minute Myth

Median sleep cycle duration is **96 minutes**, not 90 (Cajochen et al. 2024, N=369, 6064 cycles). Large interindividual variability. First cycle is consistently shorter.

**Practical implication**: Design around sleep onset (first 20–40 min). Once in N2+, the session's job is done — taper stimulation and let natural architecture take over.

### Normal Sleep Onset Latency

| SOL Range | Interpretation | Somna Implication |
|-----------|---------------|-------------------|
| < 5 min | Sleep deprivation | Quick Sleep template; log warning |
| 10–20 min | Normal | Standard (40 min active + taper) |
| > 30 min | Insomnia tendency | Extended alpha hold before theta ramp |

---

## 2. Sleep Stage EEG Markers

| Stage | EEG | Frequency | Key Markers |
|-------|-----|-----------|-------------|
| Wake (relaxed) | Alpha | 8–12 Hz | Posterior alpha, some beta |
| N1 (drowsiness) | Alpha → theta | 4–7 Hz | Alpha dropout, slow rolling eye movements, vertex waves |
| N2 (light sleep) | Theta + markers | 4–8 Hz | Sleep spindles (12–16 Hz bursts), K-complexes |
| N3 (deep SWS) | Delta | 0.5–2 Hz | >20% delta waves, minimal artifact |
| REM | Low-voltage mixed | ~4–8 Hz | Sawtooth waves, muscle atonia |

---

## 3. Frequency Progression (Step-Ramp > Smooth Slide)

**Critical principle**: Step down ~0.5–1 Hz per minute. Hold each step for 1–2 min before descending. A smooth linear slide outpaces entrainment — the brain never locks on.

| Time | Target | Beat Freq | Carrier | Notes |
|------|--------|-----------|---------|-------|
| 0:00–5:00 | Relaxed wakefulness | 10→8 Hz | 200 Hz | Settling. Agent may deliver 1–2 somatic prompts. |
| 5:00–10:00 | Alpha deepening | 8→6 Hz | 200 Hz | Step ~0.5 Hz/min. Agent goes quiet. |
| 10:00–18:00 | Theta / hypnagogia | 6→4 Hz | 180 Hz | Agent **SILENT**. Volume tapering begins. |
| 18:00–28:00 | Deep theta / N1→N2 | 4→3 Hz | 150 Hz | Very slow. Sleep spindles may appear. |
| 28:00–40:00 | Delta onset (N2→N3) | 3→1 Hz | 120 Hz | Minimal stimulation. Volume 20–30% of initial. |
| 40:00+ | Stimulus withdrawal | Fade to silence | — | Complete taper over 5–10 min. No abrupt cutoff. |

**Critical**: The session must **fade out, never stop abruptly**. Abrupt silence triggers arousal.

---

## 4. Agent Behavior

| Time Window | Agent State | Permitted Actions |
|-------------|-------------|-------------------|
| 0:00–5:00 | Active (brief) | 1–2 somatic orientation prompts max. No visualization. |
| 5:00–10:00 | Transitioning to silent | At most one final prompt ("Nothing to do now"), then silence. |
| 10:00+ | **SILENT** | No TTS. No prompts. Exception: one calming somatic prompt if EEG shows persistent high beta. |

### EEG monitoring (observe mode after minute 10)

| Key | Tracks | Agent response |
|-----|--------|---------------|
| `eeg_alpha` | Alpha power | Watch for dropout (<50% baseline) as N1 marker |
| `eeg_theta` | Theta power | Track theta rise as hypnagogia marker |
| `eeg_delta` | Delta power | Once stable, record "sleep onset achieved", disengage |

### `sleep_onset_detected` flag

Written to `live_control.json` when both hold simultaneously:

| Condition | Threshold | Duration |
|-----------|-----------|---------|
| Alpha below baseline | < 30% of session baseline | 60+ consecutive sec |
| Theta dominance | Theta > 2× alpha power | 30+ consecutive sec |

This signals `timeline_runner.py` to begin final stimulus taper if not already in progress.

---

## 5. Visual Layer

| Element | Behavior | Rationale |
|---------|----------|-----------|
| Spiral opacity | Ramp to 0% by minute 15–20 | Visual stimulation during N1 causes arousals |
| Veil / text overlays | Disable by minute 10 | Cognitive processing interferes with N1 entry |
| Background images | `bg_mode: none` | No light on closed eyelids |
| Display brightness | Ramp to black by minute 20 | Residual luminance suppresses melatonin |

---

## 6. Noise Layer

| Parameter | Value | Notes |
|-----------|-------|-------|
| Noise color | `pink` or `brown` | Both effective for environmental masking |
| Noise volume | 15–25% | Low enough to not be a stimulus |
| Noise taper | **None — persists** | Unlike beats, noise does not interfere with sleep oscillations |
| YAML flag | `noise_persist: true` | Keeps `noise_vol` set even after beats fade to zero |

---

## 7. Relationship to Other Protocols

| Protocol | Relationship |
|----------|-------------|
| Edison Mode | Inverted goal — Edison detects alpha dropout to cause arousal; sleep continues through it |
| SSILD | Different timing — SSILD is a WBTB technique. A sleep session could precede a planned WBTB+SSILD sequence |
| Fractionation | **Must avoid** — fractionation creates deliberate partial emergences; sleep sessions require smooth transitions only |

---

## 8. Session YAML Templates

### Template A: Standard (40 min active + 10 min taper)

```yaml
session:
  name: "Sleep Onset — Standard"
  type: sleep_onset
  total_duration_min: 50
  noise_color: pink
  noise_vol: 20
  noise_persist: true
  bg_mode: none

keyframes:
  - time: "0:00"
    beat_freq: 10
    carrier_freq: 200
    beat_vol: 80
    spiral_opacity: 88
    agent_state: active_brief

  - time: "5:00"
    beat_freq: 8
    beat_vol: 75
    spiral_opacity: 70
    agent_state: transitioning_silent

  - time: "10:00"
    beat_freq: 6
    beat_vol: 65
    spiral_opacity: 45
    agent_state: silent

  - time: "15:00"
    beat_freq: 5
    carrier_freq: 180
    beat_vol: 55
    spiral_opacity: 10

  - time: "20:00"
    beat_freq: 4
    beat_vol: 50
    spiral_opacity: 0
    agent_state: observe

  - time: "25:00"
    beat_freq: 3.5
    carrier_freq: 150
    beat_vol: 40

  - time: "30:00"
    beat_freq: 3
    beat_vol: 35

  - time: "35:00"
    beat_freq: 2
    carrier_freq: 120
    beat_vol: 25

  - time: "40:00"
    beat_freq: 1
    beat_vol: 15

  - time: "45:00"
    beat_vol: 5
    agent_state: disengage

  - time: "50:00"
    beat_freq: 0
    beat_vol: 0
```

### Template B: Quick (25 min active + 5 min taper)

```yaml
session:
  name: "Sleep Onset — Quick"
  type: sleep_onset
  total_duration_min: 30
  noise_color: pink
  noise_vol: 20
  noise_persist: true
  bg_mode: none

keyframes:
  - time: "0:00"
    beat_freq: 10
    carrier_freq: 200
    beat_vol: 75
    spiral_opacity: 60
    agent_state: active_brief

  - time: "3:00"
    beat_freq: 8
    beat_vol: 70
    spiral_opacity: 40
    agent_state: silent

  - time: "6:00"
    beat_freq: 6
    beat_vol: 60
    spiral_opacity: 15

  - time: "9:00"
    beat_freq: 5
    carrier_freq: 180
    beat_vol: 50
    spiral_opacity: 0
    agent_state: observe

  - time: "12:00"
    beat_freq: 4
    beat_vol: 45

  - time: "16:00"
    beat_freq: 3
    carrier_freq: 150
    beat_vol: 35

  - time: "20:00"
    beat_freq: 2
    carrier_freq: 120
    beat_vol: 25

  - time: "25:00"
    beat_freq: 1
    beat_vol: 10
    agent_state: disengage

  - time: "30:00"
    beat_freq: 0
    beat_vol: 0
```

---

## References

| Source | Detail |
|--------|--------|
| Cajochen et al. 2024 | Sleep Health. N=369, 6064 cycles. Median cycle 96 min. |
| Lacaux et al. 2024 | Trends in Neurosciences. Sleep onset non-linear; local neural patterns. |
| Gantt 2023 | Frontiers in Neurology. Theta/delta BBF for full-night enhancement. |
| Ji et al. 2025 | Physical Review E. NREM-REM ultradian rhythm via saddle-node bifurcation. |
