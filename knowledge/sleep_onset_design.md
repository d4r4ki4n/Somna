# Sleep Onset Session Design Reference

**Status:** Specification (v2 — rebuilt with Conductor sleep phases, TMR, and sleep burst integration)

**Author:** Ed / Reese

**Date:** 17 April 2026

**Loaded by:** Active session ticks during SLEEP_APPROACH and SLEEP_ONSET phases; idle planning for sleep session authoring

**Authority:** This file is the operational reference for the LLM agent when running or authoring sleep sessions. The authoritative design specification lives in the Somna Bible, Chapter 7 — Sleep Architecture. When this file and the Bible disagree, the Bible wins.

---

## Critical Constraint — Extreme Aphantasia

The user has extreme aphantasia. Visualization-based sleep onset is ineffective. The agent facilitates sleep onset via **audio parameter progression** — NOT verbal imagery narration. No guided imagery. No "picture a beach." Audio frequencies and somatic cues only.

---

## Scope

This document covers standard sleep onset sessions. It does **NOT** cover:

- Edison Mode — inverted goal; targets hypnagogia boundary to cause arousal
- SSILD — WBTB middle-of-night protocol, not sleep onset
- Training mode during sleep — training mode is disabled during sleep sessions

---

## 1. Sleep Architecture — Key Facts

### The 96-Minute Cycle

Median sleep cycle duration is **96 minutes**, not 90 (Cajochen et al. 2024, N=369, 6064 cycles). Large interindividual variability. First cycle is consistently shorter.

**Practical implication:** Design around sleep onset (first 20–40 min). Once in N2+, the entrainment session's job is done — taper entrainment stimulation and hand off to TMR and sleep burst engines. Natural sleep architecture takes over.

### Normal Sleep Onset Latency

| SOL Range | Interpretation | Somna Implication |
|-----------|---------------|-------------------|
| < 5 min | Sleep deprivation | Quick Sleep template; log warning |
| 10–20 min | Normal | Standard (40 min active + taper) |
| > 30 min | Insomnia tendency | Extended alpha hold before theta ramp |

### Sleep Stage EEG Markers

| Stage | EEG | Frequency | Key Markers |
|-------|-----|-----------|-------------|
| Wake (relaxed) | Alpha | 8–12 Hz | Posterior alpha, some beta |
| N1 (drowsiness) | Alpha → theta | 4–7 Hz | Alpha dropout, slow rolling eye movements, vertex waves |
| N2 (light sleep) | Theta + markers | 4–8 Hz | Sleep spindles (12–16 Hz bursts), K-complexes |
| N3 (deep SWS) | Delta | 0.5–2 Hz | >20% delta waves, minimal artifact |
| REM | Low-voltage mixed | ~4–8 Hz | Sawtooth waves, muscle atonia |

---

## 2. Two Control Layers — Session YAML vs. Conductor

Sleep sessions have the same two-layer control model as trance sessions, but the Conductor's sleep phases are distinct from its trance phases:

### 2.1 The Agent Authors the YAML Arc

The session.yaml defines the parameter progression the timeline runner interpolates. This is the **planned** arc — what happens if the user's brain follows the expected trajectory.

### 2.2 The Conductor Adapts in Real Time

The Conductor's 5 sleep phases manage the actual EEG-driven transitions:

| Conductor Phase | Entry Condition | What Happens | Tick Rate |
|----------------|-----------------|--------------|-----------|
| SLEEP_APPROACH | `session_type = sleep` + depth criteria met | Theta → delta frequency ramping. `freq_lead_mode = step-ramp`. Agent goes quiet. | 30 s |
| SLEEP_ONSET | `sleep_onset_detected` OR SEF95 < 8 for 120 s | Entrainment audio tapers. Visual display dims to black. Agent is SILENT. TMR cue manager activates. | 60 s |
| SLEEP_MAINTAIN | N2 or N3 detected for ≥ 3 consecutive reads | TMR cues fire during SWS. Sleep burst engine active. All entrainment audio OFF. | 60 s |
| SLEEP_TRAINING | Reserved for future sleep-specific training protocols | Not yet implemented | — |
| SLEEP_WAKE | Morning wake detection OR alarm time reached | Gentle frequency ramp up. Volume increase. Wake sequence. | 30 s |

### 2.3 How Session YAML and Conductor Interact

The session.yaml keyframes provide the **starting trajectory**. Once the Conductor enters SLEEP_APPROACH, it takes ownership of frequency-related parameters and overrides the YAML's timing:

- **YAML controls:** Initial alpha hold duration, volume curve shape, visual taper timing
- **Conductor controls:** Beat frequency progression (step-ramp), sleep onset detection, phase transitions
- **Both influence:** The Conductor reads the YAML's target delta frequency as its destination, but controls the pacing based on EEG response

```
Session YAML:    [alpha hold] → [theta ramp] → [delta target] → [silence]
                       ↕              ↕              ↕
Conductor:      SLEEP_APPROACH ──→ SLEEP_ONSET ──→ SLEEP_MAINTAIN
                 (step-ramp)      (taper all)     (TMR + bursts)
```

---

## 3. Frequency Progression — Step-Ramp, Not Smooth Slide

**Critical principle:** Step down ~0.5–1 Hz per minute. Hold each step for 1–2 min before descending. A smooth linear slide outpaces entrainment — the brain never locks on.

The Conductor uses `freq_lead_mode = step-ramp` during SLEEP_APPROACH. This is a discrete stepped descent with plateau holds between each step. The session.yaml should specify the target frequencies at each keyframe; the Conductor manages the micro-stepping between them.

### Frequency Progression Table

| Time | Target State | Beat Freq | Carrier | Notes |
|------|-------------|-----------|---------|-------|
| 0:00–5:00 | Relaxed wakefulness | 10 → 8 Hz | 200 Hz | Settling. Agent may deliver 1–2 somatic prompts. |
| 5:00–10:00 | Alpha deepening | 8 → 6 Hz | 200 Hz | Step ~0.5 Hz/min. Agent goes quiet. |
| 10:00–18:00 | Theta / hypnagogia | 6 → 4 Hz | 180 Hz | Agent SILENT. Volume tapering begins. |
| 18:00–28:00 | Deep theta / N1 → N2 | 4 → 3 Hz | 150 Hz | Very slow. Sleep spindles may appear. |
| 28:00–40:00 | Delta onset (N2 → N3) | 3 → 1 Hz | 120 Hz | Minimal stimulation. Volume 20–30% of initial. |
| 40:00+ | Stimulus withdrawal | Hold or OFF | — | Entrainment complete. TMR + burst engines take over. |

### Carrier Frequency Descent

Carrier frequency descends alongside beat frequency — from 200 Hz (comfortable waking) to 120 Hz (less arousing, darker timbre). This is a secondary entrainment cue: lower carrier = perceptually "heavier" sound.

---

## 4. Sleep Onset Detection

Sleep onset is detected by converging indicators. The Conductor transitions from SLEEP_APPROACH to SLEEP_ONSET when criteria are met. The agent does NOT write `sleep_onset_detected` directly — the Conductor evaluates these conditions internally.

### Conductor's Detection Criteria

| Criterion | Threshold | Duration Required |
|-----------|-----------|-------------------|
| SEF95 | < 8 Hz | 120 consecutive seconds |
| Alpha power | Below 30% of calibrated baseline | 60 consecutive seconds |
| Theta dominance | Theta power > 2× alpha power | 30 consecutive seconds |

If EEG is unavailable (graceful degradation), the Conductor uses a timer-based fallback:

| Fallback Criterion | Threshold |
|-------------------|-----------|
| Time since SLEEP_APPROACH entry | 25 minutes |
| No user interaction | 15 minutes |

All writes to `live_control.json` go through the IPC StateServer:

```python
from ipc import patch_live
# Conductor writes internally — agent does NOT write sleep_onset_detected
# Agent reads: conductor_phase == "SLEEP_ONSET"
```

---

## 5. What Happens AFTER Sleep Onset — TMR and Sleep Bursts

This is where the original version of this file was most wrong. The file said "once in N2+, the session's job is done." **The session's entrainment job is done. Two other systems activate.**

### 5.1 TMR Cue Manager

**Targeted Memory Reactivation** delivers auditory cues during N2/N3 (SWS) to strengthen memory consolidation of content heard during the session.

| Parameter | Value | Source |
|-----------|-------|--------|
| Activation phase | SLEEP_MAINTAIN | Conductor |
| Cue type | Pure tone, NumPy DSP synthesized | `content/tmr_cue_manager.py` |
| Cue volume | 15–25% of session peak | Low enough to not wake; high enough for cortical registration |
| Phase-locking | Timed to slow oscillation up-states (when detectable) | EEG processor |
| Content selection | Phrases heard during MAINTENANCE, weighted by conditioning strength | Semantic selector |

**Critical constraint — reconsolidation lockout:** During an active reconsolidation LOCKOUT phase, `recon_retrieve_<trace>` tagged phrases are excluded from TMR cue selection. The old trace must not be reinforced during sleep. All other content fires normally. Lockout is trace-specific.

### 5.2 Sleep Burst Engine

**Phase-locked pink noise bursts** delivered during N3 slow-wave sleep to enhance slow oscillation amplitude:

| Parameter | Value |
|-----------|-------|
| Activation phase | SLEEP_MAINTAIN, N3 detected |
| Burst type | Pink noise, 50 ms duration |
| Timing | Phase-locked to slow oscillation up-state |
| Volume | 20–30% of session peak |
| Coordination | Bursts and TMR cues do not overlap — burst engine defers to TMR during cue delivery |

### 5.3 What Tapers vs. What Continues

| System | SLEEP_ONSET | SLEEP_MAINTAIN |
|--------|-------------|----------------|
| Binaural beats | Taper to OFF over 2–3 min | OFF |
| Pink/colored noise | Taper to 10% over 5 min | Hold at 10% (masking floor) |
| TTS | OFF | OFF |
| Veil | Fade to 0% opacity | OFF |
| Spiral | Fade to 0% opacity | OFF |
| Center flash | OFF | OFF |
| TMR cues | Inactive (waiting for N2+) | ACTIVE |
| Sleep bursts | Inactive (waiting for N3) | ACTIVE |

---

## 6. Agent Behavior by Phase

### 6.1 Pre-SLEEP_APPROACH (Orient + Early Descent)

- Deliver 1–3 brief somatic prompts: body awareness, breath attention, weight of limbs
- No visualization language (aphantasia constraint)
- Set initial audio parameters per session.yaml
- Monitor for SLEEP_APPROACH entry

### 6.2 SLEEP_APPROACH

- **Go quiet.** Maximum one somatic prompt in the first 2 minutes, then SILENT
- Do not deliver TTS, veil phrases, or center flash content
- Monitor `conductor_phase` for transition to SLEEP_ONSET
- Do not adjust beat frequency — the Conductor owns it via step-ramp
- The delivery gate independently blocks content delivery based on depth floor; the agent's silence rule is a higher-level constraint (even if the gate would allow delivery, the agent should not deliver)

### 6.3 SLEEP_ONSET

- **Absolute silence.** No agent output of any kind
- Monitor for SLEEP_MAINTAIN transition
- Begin visual shutdown (veil and spiral fade to 0%)

### 6.4 SLEEP_MAINTAIN

- **Absolute silence.** No agent output
- TMR and sleep burst engines operate independently
- Agent monitors EEG for sleep stage maintenance
- If user wakes (alpha spike, motion detected), agent may deliver one brief somatic "return to sleep" prompt, then go silent again

### 6.5 SLEEP_WAKE

- Gentle frequency ramp: delta → theta → alpha over 5–10 minutes
- Volume increase: 10% → 50% over 5 minutes
- One brief wake prompt after alpha is established
- Session complete

---

## 7. Somatic Palette — Non-Interaction Note

Sleep sessions do **not** use the somatic palette system. There is no MAINTENANCE phase in a sleep session (the phase progression is SLEEP_APPROACH → SLEEP_ONSET → SLEEP_MAINTAIN), so chord testing never occurs. The agent should not attempt chord evaluation, chord switching, or fractionation during sleep sessions.

If a user's sleep sessions consistently fail (SOL > 40 min), the problem is in the frequency progression or entry state — not in chord selection. Cross-reference `calibration_protocol.md` for personal threshold calibration.

---

## 8. Delivery Gate During Sleep Sessions

The delivery gate operates during sleep sessions with modified thresholds:

| Gate | Sleep Modification |
|------|-------------------|
| Respiratory | Active during Orient/Descent only; disabled during SLEEP_APPROACH+ |
| Cardiac | Active during Orient/Descent only; disabled during SLEEP_APPROACH+ |
| SQI | Always active — low SQI means unreliable sleep staging |
| Depth | Inverted purpose: during trance sessions, depth floor prevents delivery when too shallow. During sleep sessions, depth is not gated — the goal is to let the user drift without interruption |

---

## 9. Session YAML Templates

### 9.1 Standard Sleep Session (40 min active + monitoring)

```yaml
session_type: sleep
duration: 480  # 8 hours total monitoring
active_duration: 40  # 40 min active entrainment

keyframes:
  - time: "0:00"
    beat_frequency: 10
    carrier_frequency: 200
    volume: 0.65
    noise_color: pink
    noise_volume: 0.3
    spiral_style: fermat
    spiral_opacity: 0.3
    spiral_speed_multiplier: 0.3
    veil_mode: drift
    veil_opacity: 0.15
    ease: linear

  - time: "5:00"
    beat_frequency: 8
    volume: 0.70
    spiral_opacity: 0.2
    ease: linear

  - time: "10:00"
    beat_frequency: 6
    carrier_frequency: 190
    volume: 0.65
    spiral_opacity: 0.1
    veil_opacity: 0.05
    ease: linear

  - time: "18:00"
    beat_frequency: 4
    carrier_frequency: 170
    volume: 0.50
    spiral_opacity: 0.0
    veil_opacity: 0.0
    noise_volume: 0.2
    ease: linear

  - time: "28:00"
    beat_frequency: 2
    carrier_frequency: 140
    volume: 0.35
    noise_volume: 0.15
    ease: linear

  - time: "40:00"
    beat_frequency: 1
    carrier_frequency: 120
    volume: 0.20
    noise_volume: 0.10
    ease: linear

  # Post-40:00: Conductor takes full control
  # Entrainment tapers to OFF
  # TMR + sleep burst engines activate during SLEEP_MAINTAIN
  # Agent monitoring continues for full duration
```

**Notes:**
- Do NOT include a Return phase in sleep sessions. There is no planned ascent — the user is asleep.
- The Conductor's step-ramp will micro-step between these keyframe frequencies. The YAML provides waypoints; the Conductor manages pacing.
- `ease: linear` between keyframes. Do NOT use `ease: step` (deprecated; use `ease: instant` for hard cuts if needed).
- Visual parameters (spiral, veil) should reach 0% opacity by minute 18. The visual display is a sleep disturbance past this point.

### 9.2 Quick Sleep Session (< 5 min SOL — sleep-deprived user)

```yaml
session_type: sleep
duration: 480
active_duration: 15

keyframes:
  - time: "0:00"
    beat_frequency: 8
    carrier_frequency: 180
    volume: 0.50
    noise_color: pink
    noise_volume: 0.25
    spiral_opacity: 0.0  # No visuals — user is already drowsy
    veil_opacity: 0.0
    ease: linear

  - time: "5:00"
    beat_frequency: 4
    volume: 0.40
    noise_volume: 0.20
    ease: linear

  - time: "10:00"
    beat_frequency: 2
    carrier_frequency: 150
    volume: 0.30
    noise_volume: 0.15
    ease: linear

  - time: "15:00"
    beat_frequency: 1
    carrier_frequency: 120
    volume: 0.20
    noise_volume: 0.10
    ease: linear
```

**Notes:**
- Skip Orient phase entirely. User with < 5 min SOL doesn't need settling.
- No visuals. Screen should be dark from the start.
- Agent delivers zero prompts. Audio only.
- Log SOL warning: consistently < 5 min SOL indicates sleep deprivation.

### 9.3 Extended Sleep Onset (> 30 min SOL — insomnia tendency)

```yaml
session_type: sleep
duration: 480
active_duration: 60

keyframes:
  - time: "0:00"
    beat_frequency: 11
    carrier_frequency: 210
    volume: 0.60
    noise_color: pink
    noise_volume: 0.3
    spiral_style: archimedean
    spiral_opacity: 0.25
    spiral_speed_multiplier: 0.2
    veil_mode: scroll
    veil_opacity: 0.10
    ease: linear

  - time: "10:00"
    beat_frequency: 9
    volume: 0.65
    ease: linear

  - time: "20:00"
    beat_frequency: 7
    carrier_frequency: 200
    volume: 0.65
    spiral_opacity: 0.15
    veil_opacity: 0.05
    ease: linear

  - time: "30:00"
    beat_frequency: 5
    carrier_frequency: 180
    volume: 0.55
    spiral_opacity: 0.0
    veil_opacity: 0.0
    noise_volume: 0.25
    ease: linear

  - time: "45:00"
    beat_frequency: 3
    carrier_frequency: 150
    volume: 0.40
    noise_volume: 0.20
    ease: linear

  - time: "60:00"
    beat_frequency: 1
    carrier_frequency: 120
    volume: 0.25
    noise_volume: 0.10
    ease: linear
```

**Notes:**
- Extended alpha hold (0–20 min) at 9–11 Hz. Don't rush the descent.
- Very slow frequency progression — max 1 Hz drop per 5-minute keyframe.
- Visuals taper early (by minute 30) to avoid arousal from visual stimulation.
- If calibration data shows personal IAF is high (12–13 Hz), start beat_frequency at IAF.

---

## 10. Common Mistakes — Sleep Sessions

### 10.1 Including a Return Phase

Sleep sessions have no planned ascent. If the YAML includes keyframes that ramp frequency back up at the end, the Conductor will fight the YAML: the Conductor wants to maintain SLEEP_MAINTAIN while the timeline runner is ramping to alpha. Remove any Return-phase keyframes from sleep session YAMLs.

### 10.2 Agent Speaking During SLEEP_APPROACH

Any TTS output after the first 2 minutes of SLEEP_APPROACH is an arousal stimulus. The delivery gate may allow it (depth floor not yet reached), but the agent should self-silence regardless.

### 10.3 Ignoring SOL History

The agent should check prior session records for the user's typical SOL. A user with consistent 10-min SOL using the Extended template is being held in alpha unnecessarily. A user with consistent 30-min SOL using the Quick template will fail to fall asleep. Match the template to the measured SOL.

### 10.4 Visual Stimulation Past Minute 20

Spirals and veil text are entrainment tools for trance sessions. In sleep sessions, they should reach 0% opacity well before the user is expected to lose consciousness. Flickering visuals during N1 transition is counterproductive.

### 10.5 Forgetting TMR Lockout

If the session included a reconsolidation protocol during an earlier trance segment (in a combined trance+sleep session), the reconsolidation LOCKOUT must be respected by the TMR cue manager. The agent should verify that `recon_locked_phrases` is populated before SLEEP_MAINTAIN begins.

### 10.6 Using `ease: step`

Deprecated. Use `ease: instant` for hard parameter cuts. `ease: linear` for smooth transitions. `ease: step` is not recognized by the current timeline runner.

---

## 11. Research Citations

| Source | Contribution |
|--------|-------------|
| Cajochen et al. 2024 | 96-minute median sleep cycle, N=369 |
| Bartossek et al. 2021 | Visual flicker entrainment most effective at IAF |
| Notbohm et al. 2016 | Arnold tongue dynamics — higher opacity = wider capture range |
| Ngo et al. 2013 | Closed-loop auditory stimulation during SWS enhances slow oscillations |
| Antony et al. 2012 | TMR during SWS strengthens declarative memory consolidation |
| Nam & Choi 2020 | Lenient initial thresholds → progressive tightening |
