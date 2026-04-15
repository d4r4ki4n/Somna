# SSILD Protocol Reference for Somna
*Senses-Initiated Lucid Dreaming — Technical Integration Guide*
*v1.0 | 28 March 2026 | Internal Engineering Reference*

---

## 1. Overview and Origin

SSILD (Senses-Initiated Lucid Dreaming) is a modern lucid dreaming induction technique created in 2011 by a Chinese practitioner known as "CosmicIron" (cosmiciron). Originally published under the Chinese title "太玄功" ("A Very Mysterious Technique") — a fitting name because at the time, neither the inventor nor the community had a theoretical model for why it worked.

Despite the lack of formal theory, community feedback was overwhelmingly positive. Within a few months, hundreds of success stories were collected. Multiple tutorial revisions followed, each informed by community experimentation. The Chinese forum grew to 80,000+ members. One year after original publication, CosmicIron wrote the first English version for DreamViews and LD4All. Over a hundred additional success stories in nine months.

**Classification:** Hybrid DILD/WILD technique, but requires critical qualification:
- SSILD is **NOT** a WILD technique in practice. No attempt to maintain continuous consciousness through the sleep transition.
- SSILD primes meta-awareness via passive sensory cycling, then the practitioner falls asleep naturally.
- Lucidity occurs later — during a false awakening, mid-dream recognition, or occasionally hypnagogic transition. Not during the cycles themselves.

**Key Properties for Somna:**

| Property | Value |
|----------|-------|
| Difficulty | Low — designed to be "idiot-proof". No visualization or advanced mental skills. |
| Core Mechanism | Passive sensory cycling primes meta-awareness without conscious effort |
| Timing Dependency | Requires WBTB (Wake Back To Bed) after 4–5 hours of initial sleep |
| Long-Term Consistency | Results do NOT degrade with repeated practice — multiple users sustain daily LDs over months |
| Failure Mode | Trying too hard. Passivity is mandatory. |
| Automation Potential | **High** — structured, timed cycles ideal for TTS-guided delivery via `somna_agent.py` |

---

## 2. SSILD vs MILD vs WILD

| Technique | Mechanism | Difficulty | When Lucidity Occurs | Key Requirement |
|-----------|-----------|------------|---------------------|-----------------|
| MILD | Intention-setting + prospective memory. Mnemonic phrase + dream visualization. | Moderate | During dream via recognition trigger | Genuine intention. Cannot be externally supplied — LaBerge (Stanford, 1980s). |
| WILD | Maintain continuous consciousness through entire wake-to-sleep transition | High | Immediate — at dream onset, consciousness never lost | Intense focus + tolerance of sleep paralysis. High failure rate. |
| **SSILD** | **Passive sensory cycling primes meta-awareness. Fall asleep naturally after cycles.** | **Low** | **During false awakening or mid-dream** | **Passivity. Trying too hard is the primary failure mode. Also: WBTB timing.** |

**Key distinction for Somna:** SSILD's low difficulty and structured timing make it ideal for automated guided delivery. Unlike MILD (requires genuine personal intention) or WILD (requires skill most users lack), SSILD's value proposition is: follow these simple timed steps passively, then fall asleep. Maps directly to a TTS-guided session flow.

---

## 3. The SSILD Cycle — Three Sensory Steps

One complete cycle = Visual → Auditory → Somatic. Two speeds: quick (few seconds/step) for warm-up, slow (15–30 seconds/step) for the main technique.

### Step 1: Visual (Sight)
- Close eyes, passively observe the darkness behind eyelids
- Do NOT strain, look for patterns, visualize, or create imagery
- Seeing nothing (just darkness) is completely normal and equally effective
- If hypnagogic imagery appears spontaneously, observe passively without engaging or trying to enhance it
- Duration: 3–5 seconds (quick) or 15–30 seconds (slow)

### Step 2: Auditory (Hearing)
- Relax eyes. Shift attention fully to hearing.
- Listen for internal sounds: heartbeat, tinnitus, blood flow, ringing
- Listen for external sounds: wind, clock, ambient noise, HVAC
- Silence is a valid observation — do not strain to hear things that aren't there
- If unusual sounds appear (hypnagogic audio: voices, music, tones), observe passively
- Duration: same as visual

### Step 3: Somatic (Touch / Body Sensation)
- Shift attention to full-body physical sensations
- Feel for: weight/gravity, tingling, heaviness, warmth, cold, blanket contact, breathing rhythm, pulse
- Note unusual sensations: spinning, floating, vibrating — positive indicators, but do not react
- Do NOT tense muscles or shift body to "check" for sensations
- Duration: same as other steps

### CRITICAL: The Passivity Imperative

> **The single most important instruction — and the single most common failure mode — is the requirement for passive attention.**

- Passive attention is non-negotiable. Observe whatever is present without straining, expecting, or trying to produce experiences.
- Expect nothing from each cycle. Cycles with no experiences are completely normal and effective.
- Do not get excited or analyze experiences during cycles. If phenomena arise, correct response is neutral detached observation.
- Results do not fade with repeated practice.
- The cycles prime the brain for later lucidity — the actual lucid dream occurs after falling asleep. This prevents the mistake of treating cycles as a WILD "stay conscious" attempt.
- Duration precision is not critical. TTS prompts from `somna_agent.py` handle all transitions.

---

## 4. Full Protocol — Step by Step

### Step 1: Sleep Hygiene First
Normal bedtime, standard sleep hygiene. No caffeine, alcohol, or stimulants.

*Somna:* Pre-sleep relaxation deepener and sleep hygiene reminders during the initial bedtime session.

### Step 2: Initial Sleep Period (4–5 Hours)
Sleep normally. WBTB timing targets the transition from SWS-dominant to REM-dominant sleep cycles.

*Somna:* `eeg_engine.py` can identify optimal wake timing — specifically waking during natural N1/N2 rather than deep SWS, which causes grogginess.

### Step 3: WBTB (Wake Back To Bed)
Achieve mild alertness: use bathroom, glass of water, walk 2–5 minutes, optional brief LD reminder.

Avoid: bright screens, email, extended conversations, exercise, full meals.

*Somna TTS:* "Take a moment to become slightly alert. Use the bathroom if you need to. When you're ready, return to bed. I'll guide you through the cycles."

### Step 4: Return to Bed
Normal sleeping position. Comfort is paramount — discomfort creates distractions.

### Step 5: Quick Warm-Up Cycles (4–6 Cycles)
Rapidly cycle Visual → Auditory → Somatic, ~3–5 seconds each. Total: ~1–2 minutes.

Purpose: establish rhythm without overthinking. These are purely preparatory — no experiences expected.

*Somna TTS (fast, brief):* "Eyes… listen… feel…" with brief pauses.

### Step 6: Slow Technique Cycles (3–4 Cycles)
Slow down. ~15–30 seconds per sense, 3–4 full cycles. Total: ~4–6 minutes.

*Somna TTS (slow, gentle):* "Now shift your attention to the darkness behind your eyelids. Don't strain. Don't search. Just observe."

The pauses between prompts are as important as the prompts themselves.

### Step 7: Fall Asleep Naturally

**Do NOT:**
- Try to stay conscious (this is not WILD)
- Continue cycling
- Analyze what happened or evaluate whether the technique "worked"
- Avoid comfortable position changes — movement is acceptable

*Somna TTS:* "The cycles are complete. Now just let yourself fall asleep naturally. I'll be here." → System transitions to silent REM monitoring. All TTS ceases. Visual display goes dark/minimal. `eeg_engine.py` begins active monitoring for REM onset.

### Step 8: Lucidity Onset

Three pathways:

| Pathway | Frequency | Description |
|---------|-----------|-------------|
| False Awakening | Most common | Practitioner "wakes up" but is still dreaming. Primed meta-awareness detects anomalies (wrong room, unstable text). Reality checks critical here. |
| Mid-Dream Recognition | Common | Something in a dream triggers primed meta-awareness. The SSILD cycles lowered the threshold. |
| Hypnagogic Transition | Less common | Practitioner remains semi-conscious during sleep transition (unforced WILD). Bonus outcome, not the intended pathway. |

**Reality Check Imperative:** Always reality-check upon any awakening after SSILD cycles. Recommended: try to push finger through opposite palm, examine text (does it change?), breathe with nose pinched. `somna_agent.py` should reinforce this during pre-technique phase.

---

## 5. Academic Research

### Esfahani et al. (2024) — "Dreamento" Multi-Center Study
- **Publication:** bioRxiv preprint. DOI: 10.1101/2024.06.21.600133
- **Groups:** Donders Institute (Radboud, NL), IMT School (Lucca, IT), Dream Engineering Lab (Montreal)
- **n:** 60 participants across three sites
- **EEG:** 2-channel wearable, open-source "Dreamento" Python toolbox
- **Cognitive training:** SSILD as the pre-sleep method
- **Stimulation:** Targeted Lucidity Reactivation (TLR) — multimodal sensory cues (visual, auditory, tactile) delivered automatically during detected REM sleep

**Results:**

| Metric | Netherlands | Italy |
|--------|------------|-------|
| Signal-Verified Lucid Dreams (overall) | **65%** of participants | 45% of participants |
| SVLD during REM cueing sessions | 45% of sessions | 35% of sessions |
| SVLD during sham sessions (SSILD only) | 35% of sessions | 15% of sessions |
| Average verified lucidity duration | 78.75 ± 54.85 seconds | |

**65% SVLD rate is the highest verified lucid dream induction rate in published literature.** Even the sham condition (SSILD alone, no REM cueing) produced 35% and 15% rates — suggesting SSILD has significant standalone efficacy.

**Somna relevance:** Directly validates the architecture Somna can replicate: EEG REM detection → automated multimodal cue delivery → significantly boosted lucid dream success.

### Konkoly et al. (2024) — TLR via Smartphone App (Northwestern)
- Participants improved from 0.74 to **2.11 lucid dreams/week** (~3× increase)
- No EEG — timing based on sleep duration heuristics
- First study with control group for at-home TLR

**Somna relevance:** Establishes baseline — even without EEG-based REM detection, timer-based cue delivery significantly improves frequency. Adding EEG pushes this further.

### Demirel et al. (2025) — EEG Signatures of Lucid Dreaming (Journal of Neuroscience)
- Multi-lab pooled data, sensor and source level analysis
- **Key EEG markers of lucid dreaming:**

| Marker | Band | Region | Muse 2 Coverage |
|--------|------|--------|-----------------|
| Beta power reduction | 12–30 Hz | Right central/parietal, TPJ | TP9/TP10 (temporal) — partial TPJ coverage |
| Increased alpha connectivity | 8–12 Hz | Posterior, functional connectivity | TP9/TP10 — alpha power; limited connectivity with 4 channels |
| **Increased gamma1 power** | **30–36 Hz** | **Right temporo-occipital, right precuneus** | **TP10 (right temporal) — primary electrode of interest** |
| Frontal alpha/beta shifts | 8–30 Hz | Frontal cortex | AF7/AF8 — direct coverage |

**Primary lucidity marker for Somna:** Gamma1 (30–36 Hz) power increase at TP10 (right temporal). TP10 is the highest-value electrode for this purpose. This is the signal `eeg_engine.py` should monitor after REM onset to detect if TLR cues achieved their goal.

---

## 6. Somna Architecture Mapping

### 6.1 Session Timeline Design

Four phases in YAML session definition:

| Phase | Duration | Components Active |
|-------|----------|-------------------|
| Pre-Technique | 1–3 min | TTS instructions, reality check reminder, relaxation deepener |
| Quick Cycles | 1–2 min | TTS (short prompts, fast), visual minimal |
| Slow Cycles | 4–6 min | TTS (gentle, long pauses), visual dark/off |
| Post-Technique / REM Monitoring | 60–180 min | `eeg_engine.py` (REM + lucidity detection), subliminal TLR cues, visual off/minimal |

### 6.2 TTS Prompts

| Phase | Sense | Prompt | Voice |
|-------|-------|--------|-------|
| Pre-Technique | — | "Get comfortable. We'll cycle through your senses gently. Don't try to make anything happen. Just notice whatever is there. If there's nothing — that's perfectly fine." | Normal rate, soft |
| Quick Cycle | Visual | "Eyes." | Brief, neutral |
| Quick Cycle | Auditory | "Listen." | Brief, neutral |
| Quick Cycle | Somatic | "Feel." | Brief, neutral |
| Slow Cycle | Visual | "Now shift your attention to the darkness behind your eyelids. Don't strain. Don't search. Just observe." | Slow, low pitch, soft |
| Slow Cycle | Auditory | "Now listen. Notice any sounds — your heartbeat, the room, the silence. Just listen." | Slow, low pitch, soft |
| Slow Cycle | Somatic | "Now feel your body. Notice weight, warmth, tingling, breathing. Just notice." | Slow, low pitch, soft |
| Post-Cycles | — | "The cycles are complete. Now just let yourself fall asleep naturally. I'll be here." | Very slow, very soft |

**Voice Mode Selection:**
- Normal TTS mode: Pre-technique and cycle prompts. Audible speech at comfortable volume.
- Subliminal SSB mode (`voice_mode: "subliminal"`): Post-technique TLR cue delivery. Below conscious threshold, designed to penetrate dream awareness without causing full awakening.

### 6.3 Visual Layer Behavior

| Phase | Visual |
|-------|--------|
| Pre-Technique | Gentle ambient. Low brightness. Optional slow-dissolving instructional text. |
| Visual Attention Step | **Dark/black screen. No animation. No patterns.** Light leaking through eyelids creates competing noise. |
| Auditory Step | Remain dark/minimal. |
| Somatic Step | Optional: very subtle visual drift at absolute minimum to enhance body awareness. Experimental — default off. |
| Post-Technique / REM Monitoring | Screen off or absolute minimum brightness. During TLR cue delivery: very dim visual flickers (Esfahani 2024 used visual cues during REM). Must be sub-awakening threshold. |

### 6.4 EEG Integration — REM Detection

`eeg_engine.py` monitors for REM onset using these heuristics:

| EEG Feature | REM Signature | Muse 2 Channel(s) |
|-------------|---------------|-------------------|
| Theta dominance | Elevated theta vs. wake | All channels |
| Low delta | Reduced vs. N3 — absence of slow waves | All channels |
| Reduced alpha | Lower than wake/relaxed state | TP9/TP10, AF7/AF8 |
| Eye movement artifacts | Conjugate deflections (rapid eye movements) | **AF7/AF8 (frontal — closest to eyes)** |
| Increased beta variability | More variable than non-REM; desynchronized | All channels |
| Absent sleep spindles | 12–16 Hz bursts absent (characteristic of N2) | All channels |

### 6.5 TLR Cue Delivery

Upon REM detection, dispatch cues via `content_tools.py`:
1. **Subliminal SSB audio whispers:** "You are dreaming. Check your hands." / "This is a dream. Look around." — same cues associated with lucidity during pre-sleep training.
2. **Subtle audio tones:** Brief, soft tonal cues. Calibrated to penetrate dream awareness without awakening.
3. **Very dim visual flickers:** Brief, low-intensity light pulses through closed eyelids.

**Cue calibration is critical.** Start at lowest possible level. Each morning, `somna_agent.py` asks: "Did anything wake you up during the night?" to calibrate downward if disruption reported.

### 6.6 Lucidity Detection

After TLR cues are being delivered, monitor for Demirel 2025 markers:
1. **Primary:** Gamma1 (30–36 Hz) increase at TP10 (right temporal) above baseline REM levels
2. **Secondary:** Alpha coherence increase (8–12 Hz) between TP9↔TP10
3. **Tertiary:** Beta power reduction (12–30 Hz) at TP9/TP10

**On lucidity detection:** Reduce or stop TLR cue delivery. Goal achieved — further stimulation risks disrupting the lucid dream. Log with timestamp and EEG feature values.

---

## 7. Implementation Checklist

1. Create SSILD session YAML with keyframes for: `pre_technique`, `quick_cycles`, `slow_cycles`, `post_technique_monitoring`
2. Add TTS prompt templates to knowledge file (variants for first-time vs. returning users)
3. Implement REM detection heuristics in `eeg_engine.py` (theta + low delta + eye artifacts in AF7/AF8)
4. Add sleep spindle detector (12–16 Hz burst detection) to distinguish N2 from REM
5. Implement TLR cue delivery (subliminal audio, tonal audio, visual flicker with calibration params)
6. Add Demirel 2025 lucidity marker detection (gamma1 at TP10)
7. Implement per-user baseline storage for non-lucid REM gamma levels
8. Create SSILD-specific agent behavior mode (phase-based state machine)
9. Implement morning wakefulness detection and dream journal prompt
10. Log: session date, REM periods detected, TLR cues delivered, lucidity marker detections, user-reported lucidity, user-reported cue awareness

---

## 8. References

1. Esfahani et al. (2024). bioRxiv. DOI: 10.1101/2024.06.21.600133
2. Esfahani et al. (2023). Dreamento: open-source dream engineering toolbox. SoftwareX, 24, 101595.
3. Konkoly et al. (2024). Targeted lucidity reactivation via smartphone app. Consciousness and Cognition. Northwestern University, Paller Lab.
4. Demirel et al. (2025). Electrophysiological correlates of lucid dreaming. Journal of Neuroscience, 45(20). DOI: 10.1523/JNEUROSCI.2237-24.2025
5. LaBerge, S. (1980). Lucid dreaming as a learnable skill. Perceptual and Motor Skills, 51, 1039–1042. (Origin of MILD technique)
6. CosmicIron (2011). 太玄功 ("A Very Mysterious Technique") — original SSILD protocol. Chinese forum, later English on DreamViews and LD4All.
7. Konkoly et al. (2021). Real-time dialogue between experimenters and dreamers during REM sleep. Current Biology, 31(7), 1417–1427.
