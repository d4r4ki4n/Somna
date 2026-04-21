# Entrainment Modalities — FM and Bilateral Panning

## Four entrainment channels

Somna has four independent entrainment mechanisms that target different neural pathways:

| Channel | Mechanism | What It Activates | Live Key |
|---------|-----------|-------------------|----------|
| Spectral | Binaural interaural phase difference | Superior olivary complex → bilateral auditory cortex integration | `beat_type: "binaural"` |
| Temporal | Isochronic amplitude modulation | Primary auditory cortex, strongest ASSR at 40 Hz | `beat_type: "isochronic"` |
| Tonal | FM carrier frequency modulation | Tonotopic traveling wave → sustained cortical following response | `beat_type: "fm"` |
| Spatial | Bilateral L/R audio panning | Interhemispheric communication + working memory taxation | `bilateral_panning: true` |

These are **orthogonal** — any beat type can be combined with bilateral panning for compound stimuli.

## FM Entrainment

### Mechanism

FM entrainment modulates the carrier frequency itself at the target brainwave rate. A 200 Hz carrier modulated at 6 Hz with depth 8 sweeps between 196 Hz and 204 Hz, six times per second. The auditory cortex tracks the pitch movement in real time, producing a **sustained field response** — a continuous neural oscillation, not a series of discrete evoked responses.

### Evidence

- Okamoto & Kakigi (2015): FM rate has significant impact on neural responses — higher FM rates produce smaller N1m (onset) responses but **larger sustained field responses**. The cortex tracks FM continuously.
- Cabral-Calderin et al. (2023): Direct behavioral entrainment to 2 Hz FM sounds — gap detection performance sinusoidally modulated by FM stimulus phase.
- Bidelman & Horn (2025); Johnson et al. (2024): Both AM and FM produce ASSR, but through partially different cortical mechanisms. FM engages tonotopic mapping more broadly.

### When to use FM

- **ASSR absent under binaural** — if the EEG engine reports `eeg_entrainment_recommend_modality` is non-null twice, switch to FM as an alternative to isochronic. FM's sustained response may engage where binaural phase detection fails.
- **Long sessions** — FM's vibrato quality is less fatiguing than isochronic's discrete pulses. For sessions over 30 minutes, consider FM for the MAINTENANCE phase even if binaural worked during INDUCTION.
- **Noise-heavy backgrounds** — FM blends better with colored noise than isochronic. When noise_volume > 40, FM may produce a cleaner entrainment signal.
- **Analytical subjects** — subjects who resist standard entrainment (the "Heisenberg problem") may respond better to FM because the stimulus is less obviously rhythmic. The warble doesn't trigger the same "I'm being pulsed" monitoring response.

### Parameters

- `fm_mod_depth`: carrier frequency deviation in Hz. Range 0.5–30.0, default 8.0.
  - Narrow (2–5 Hz): subtle warble, good for alpha/theta maintenance
  - Medium (5–12 Hz): clear vibrato, standard entrainment range
  - Wide (12–20 Hz): dramatic vibrato, use for delta descent or when engagement is low
- When FM is active, `beat_frequency` sets the modulation rate (the entrainment target), not a frequency difference between channels.
- FM is monaural (both channels identical) — works on speakers, doesn't require headphones.

### Interaction with other systems

- **Breath modulation**: stacks normally. Breath AM applied on top of FM carrier.
- **Bilateral panning**: stacks. FM + bilateral = tonal + spatial compound stimulus.
- **ASSR measurement**: the existing ASSR metric works for FM — the cortex produces a following response at `beat_frequency`. Phase relationship may differ from AM; characterize during calibration.
- **Crossmodal gain**: FM audio channel is gain-adjusted normally.
- **Conductor**: FM is a valid modality for `_switch_modality()` rotation. Include in the fallback sequence: binaural → isochronic → FM.

## Bilateral Panning

### Mechanism

Bilateral auditory stimulation alternates a sound between left and right ears at a rhythmic rate. The brain must constantly redirect attention between hemispheres, engaging:
1. **Working memory taxation** — dual-task load weakens sensory intensity of internal representations
2. **Interhemispheric communication** — enhanced cross-hemispheric transfer, mimicking slow-wave sleep patterns
3. **De-arousal** — reduced autonomic arousal (decreased heart rate, skin conductance)
4. **Memory reconsolidation facilitation** — measurable drops in memory vividness and emotionality

### Evidence

- Stingl et al. (BJPsych Open, 2025): Bilateral stimulation significantly increased total frontal EEG power and decreased spectral edge frequency — the same direction Somna targets for trance deepening.
- 2025 review maps four converging mechanisms: working memory taxation, interhemispheric communication, de-arousal, and reconsolidation facilitation.
- EEG research shows BLS shifts activity from frontal-limbic to temporoparietal/occipital — a neural "handoff" from emotional to sensory processing.
- 30+ years of EMDR clinical evidence base.

### When to use bilateral panning

- **Reconsolidation sessions** — during LABILIZE and UPDATE phases, switch bilateral_rate to BLS-rate (0.5–2.0 Hz). This activates working memory taxation and reconsolidation facilitation — the same mechanisms EMDR uses to weaken memory traces before rewriting.
- **Fractionation re-drops** — activate bilateral during FRAC_EMERGE and FRAC_REDROP to enhance the depth re-entry. The spatial alternation prevents the brain from fully "snapping back" to alertness during the emerge phase.
- **ASSR-absent fallback** — when neither binaural nor isochronic nor FM produces a measurable ASSR, bilateral panning at the target frequency provides an alternative spatial entrainment pathway.
- **Plateau breaking** — if trance score stalls in MAINTENANCE for >10 min, activate bilateral at beat_frequency to add a second entrainment channel.

### Parameters

- `bilateral_panning`: bool, default false. Master enable.
- `bilateral_rate`: float 0.1–20.0 Hz, default 6.0.
  - Match `beat_frequency` for spatial entrainment (4–12 Hz)
  - Use 0.5–2.0 Hz for EMDR-rate during reconsolidation
- `bilateral_mode`: "smooth" | "hard", default "smooth".
  - Smooth = sinusoidal pan (gradual, musical, less intrusive)
  - Hard = square wave (percussive, stronger lateralization, more EMDR-like)
- `bilateral_depth`: float 0.0–1.0, default 1.0.
  - 0.5–0.7 is often sufficient for entrainment; 1.0 can be distracting
  - Reduce to 0.5 during MAINTENANCE to avoid pulling the subject out of trance
  - Use 1.0 only during deliberate EMDR-rate sessions

### Conductor integration

- During INDUCTION and DEEPENING: bilateral_panning=false (let spectral/tonal entrainment establish first)
- During MAINTENANCE: bilateral_panning=true, bilateral_rate=beat_frequency, bilateral_depth=0.5 (gentle spatial layer)
- During FRAC_EMERGE: bilateral_panning=true, bilateral_rate=1.0, bilateral_mode="hard" (EMDR-rate to prevent full alertness return)
- During FRAC_REDROP: bilateral_panning=true, bilateral_rate=beat_frequency, bilateral_depth=0.7 (enhanced re-entry)
- During reconsolidation LABILIZE: bilateral_panning=true, bilateral_rate=1.0, bilateral_mode="hard", bilateral_depth=0.8
- During reconsolidation UPDATE: bilateral_panning=true, bilateral_rate=1.0, bilateral_mode="smooth", bilateral_depth=0.6

### Bone conduction note

Somna uses bone conduction speakers. Bilateral panning via bone conduction produces a different spatial percept than headphones — lateralization depends on speaker placement and bone conduction pathways. The interhemispheric communication effect should still occur even if perceived lateralization is less dramatic. Characterize empirically during calibration sessions.

## Modality switching protocol

When the EEG engine reports ASSR is absent for the current modality (via `eeg_entrainment_recommend_modality`), the Conductor should cycle through modalities:

1. **Binaural** (default starting point — brainstem + cortical)
2. **Isochronic** (first fallback — direct cortical, strongest ASSR)
3. **FM** (second fallback — sustained field response, different pathway)
4. **Bilateral activation** (third fallback — spatial entrainment, independent of spectral/temporal)

Each switch should be separated by at least 60 seconds to allow the ASSR measurement to stabilize on the new modality. If all four fail, the session continues in timer mode (no EEG gating).

Do not stack more than two entrainment channels simultaneously. Binaural + bilateral is fine. FM + bilateral is fine. Binaural + FM is redundant (FM is monaural; binaural requires stereo separation). Isochronic + FM is contradictory (AM and FM fight for the same carrier). Choose one spectral/temporal/tonal mode + optional bilateral.
