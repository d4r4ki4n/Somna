# 40 Hz GENUS Protocol Reference for Somna
*Gamma ENtrainment Using Sensory Stimulation*
*v1.0 | 28 March 2026 | Internal Engineering Reference*

---

## 1. What GENUS Is

GENUS stands for **G**amma **EN**trainment **U**sing **S**ensory **S**timulation. Developed by the Tsai Lab at the Picower Institute for Learning and Memory, MIT. Principal investigators: Li-Huei Tsai and Edward S. Boyden.

**Core principle:** Non-invasive sensory stimulation at exactly 40 Hz — via light flicker, sound clicks, or both combined — entrains neural gamma-band oscillations throughout the brain, including deep structures (hippocampus, amygdala, medial temporal lobe). This triggers a cascade of neuroprotective cellular and molecular responses via the glymphatic waste-clearance system.

**Origin:** Developed for Alzheimer's disease (AD) research. In mouse models, 40 Hz stimulation reduces amyloid-beta plaques, reduces phosphorylated tau, prevents neurodegeneration, preserves synaptic density, and sustains cognition. First published in Nature, 2016 (Iaccarino et al.).

**Human translation:** Phase I/II trials demonstrated safety and preliminary efficacy in mild AD patients. A Phase III-scale prevention trial (NCT05776641) is actively recruiting at Massachusetts General Hospital (as of March 2026).

**Somna relevance:**
- `audio_engine.py` — isochronic 40 Hz rectangular click train mode
- `visual_display.py` — 40 Hz stroboscopic flicker mode (ModernGL frame-level modulation)
- `eeg_engine.py` — real-time 40 Hz gamma power monitoring via Muse 2 to verify entrainment
- `somna_agent.py` — cognitive engagement overlay enhances entrainment (Mlinarič 2025 finding)
- Somna's 144 Hz vsync display fully supports 40 Hz visual flicker via frame dithering

---

## 2. Exact Stimulus Parameters

### 2.1 Audio Stimulus

| Parameter | Value | Notes |
|-----------|-------|-------|
| Repetition frequency | **40.0 Hz exactly** | 25.0 ms period |
| Pulse waveform | **Rectangular (square) click** | Sharp onset/offset — NOT a sine wave, NOT raised cosine |
| Pulse width (ON duration) | **1.0 ms (0.001 s)** | Full amplitude for 1 ms |
| Inter-pulse interval (OFF) | **24.0 ms (0.024 s)** | Zero amplitude |
| Duty cycle | **4%** (1 ms / 25 ms) | Very brief pulse, long silence |
| Recommended SPL | 60–78 dB SPL (~65 dB target) | Normal conversation level |
| Pulse edge profile | **No smoothing. No fade.** | Sharp transient onset drives ASSR entrainment |

**CRITICAL:** This is a **monaural isochronic click train**, NOT a binaural beat. The sharp onset transient of each click is what drives auditory steady-state response (ASSR) entrainment. Smooth or sinusoidal waveforms at 40 Hz produce significantly weaker entrainment.

**Somna's current `beat_type: "isochronic"` uses a raised-cosine envelope and is appropriate for general entrainment. For GENUS specifically, a separate rectangular pulse generator is required.** The `genus_active` flag should trigger the rectangular pulse variant.

At 44,100 Hz sample rate:
- ON samples: `ceil(0.001 × 44100) = 45 samples` at full amplitude
- OFF samples: `ceil(0.024 × 44100) = 1059 samples` at zero
- Total per cycle: ~1103 samples ≈ 25.01 ms ≈ 40.0 Hz

```python
# GENUS rectangular pulse generation
import numpy as np, math

sample_rate = 44100
frequency   = 40.0
pulse_width = 0.001   # 1 ms ON
period      = 1.0 / frequency  # 25 ms
off_dur     = period - pulse_width  # 24 ms

on_samples  = int(math.ceil(pulse_width * sample_rate))   # 45
off_samples = int(math.ceil(off_dur    * sample_rate))    # 1059

cycle = np.zeros(on_samples + off_samples, dtype=np.float32)
cycle[:on_samples] = amplitude   # Sharp onset — NO fade-in, NO Hanning window

# Tile to fill buffer
buffer = np.tile(cycle, num_cycles_needed)
```

### 2.2 Visual Stimulus

| Parameter | Value | Notes |
|-----------|-------|-------|
| Flicker frequency | **40.0 Hz exactly** | 25.0 ms period |
| Flicker pattern | **Stroboscopic ON/OFF** | Full white ↔ full black |
| Duty cycle | 50% (12.5 ms ON, 12.5 ms OFF) | Equal ON and OFF |
| Modulation depth | **100%** | Full luminance contrast — max white to full black |
| Color | White / Black | Some replications use specific LED wavelengths |
| **Minimum monitor refresh rate** | **≥ 80 Hz** | **60 Hz displays CANNOT produce true 40 Hz flicker** |

**Somna's 144 Hz vsync display can produce 40 Hz flicker** via frame dithering (see table below).

#### Frame Patterns by Refresh Rate

| Refresh Rate | Frames per 40 Hz Cycle | Frame Pattern | Result |
|-------------|------------------------|---------------|--------|
| 60 Hz | 1.5 (non-integer) | **IMPOSSIBLE.** Closest = 30 Hz or 20 Hz. | **NOT suitable — warn user, fallback to audio-only** |
| 80 Hz | 2.0 (exact) | ON, OFF | 40.00 Hz exact |
| 120 Hz | 3.0 (exact) | ON, ON, ON, OFF, OFF, OFF (6-frame period) | 40.00 Hz exact |
| **144 Hz** | **3.6 (non-integer)** | **Dithered: e.g., ON×2, OFF×2, ON×2, OFF×1, ON×1, OFF×2** | **~40.0 Hz averaged (39.7–40.3 Hz instantaneous)** |
| 240 Hz | 6.0 (exact) | ON×3, OFF×3 | 40.00 Hz exact |

At 144 Hz, dithering alternates between 3- and 4-frame half-cycles to average 40 Hz. The instantaneous frequency varies slightly but the average is correct — this is acceptable per the research literature.

### 2.3 Combined Audio-Visual Stimulus

| Parameter | Value |
|-----------|-------|
| Temporal alignment | **Audio click onset = Visual ON frame onset** — phase-locked |
| Acceptable jitter | < 5 ms |
| Relative efficacy | **AV combined > either alone** (Martorell 2019 — additive/synergistic) |
| Phase alignment | Audio click coincides with visual **ON** transition, not OFF |

**AV sync implementation:** The `beat_phase` key already written by `audio_engine.py` to `live_control.json` provides the synchronization signal. The GENUS visual flicker layer should read this key to lock visual ON frames to audio click phase.

### 2.4 Session Parameters

| Parameter | Value |
|-----------|-------|
| Session duration | **60 minutes (1 hour)** per clinical protocol |
| Session frequency | **Daily** while awake |
| Clinical trial duration | 12 months daily (NCT05776641) |
| Longest published home use | ~30 months (5 patients, 2025 open-label extension) |

---

## 3. Publication History

| Paper | Key Findings |
|-------|-------------|
| Iaccarino et al. (2016, Nature) | **Foundational proof of concept.** 40 Hz visual flicker reduces amyloid-beta in visual cortex. Microglia shift to phagocytic state, cluster around plaques. |
| Long-term GENUS (2019, Neuron) | Chronic 40 Hz light protects against neurodegeneration. Preserves neurons, synapses, and cognitive performance over time. |
| Martorell et al. (2019, Cell) | **Audio 40 Hz click trains also reduce amyloid + tau. Combined AV is additive/synergistic.** Justifies implementing both audio and visual channels in Somna. |
| Chan et al. (2022, PLOS ONE) | **First human data.** n=25 cognitively normal + n=16 mild AD. Intracranial EEG confirmed non-invasive stimulation entrains hippocampus, amygdala, and other deep structures — not just surface cortex. 3-month pilot: lesser brain atrophy, improved functional connectivity, better memory recall. |
| Tactile (2023) | 40 Hz vibrotactile stimulation also reduces AD pathology — confirms modality-independent mechanism. |
| **Murdock et al. (2024, Nature)** | **THE MECHANISM PAPER.** Identified the full glymphatic pathway (see Section 6.1). Validated pharmacologically — blocking glymphatic clearance abolished the effect. |
| Blanpain et al. (2024, Nature Comms) | Human intracranial EEG. Flicker modulates medial temporal lobe and prefrontal cortex via long-range circuit resonance. Also **reduces interictal epileptiform discharges** (pathological biomarker). |
| **Mlinarič et al. (2025, Comms Biology)** | **CRITICAL FOR SOMNA.** Cognitive engagement during stimulation ENHANCES entrainment strength AND spatial extent, including hippocampus. Direction of information flow shifts frontal→hippocampal. |
| Tsai & Park (2025, PLOS Biology) | Decade review. All modalities produce consistent results. Key quote: "The key is delivering stimulation at 40 Hz. They all see beneficial effects." |
| Chan & Tsai (2025, Alz & Dementia) | ~30 months daily use in 5 mild AD patients. Several cognitive measures significantly higher than comparable AD patients in national databases. Plasma phosphorylated tau-217 significantly decreased. |

---

## 4. Active Clinical Trial

- **ID:** NCT05776641
- **Title:** "Gamma Light and Sound Stimulation to Prevent Dementia in Cognitively Normal People At Risk for Alzheimer's Disease"
- **Sponsor:** Massachusetts General Hospital
- **Status (March 2026):** Actively recruiting
- **Population:** 200 participants, aged 55–90, cognitively normal (MMSE ≥ 27), family history of AD
- **Design:** Double-blinded, sham-controlled, 12 months daily home use, 60 min/day
- **Significance:** Largest GENUS trial to date. First prevention trial (treating cognitively normal individuals).

---

## 5. Somna Implementation Specification

### 5.1 `audio_engine.py` — GENUS Mode

Add `genus_active` flag to trigger rectangular pulse generator. When `genus_active: true`:
- Generate 1 ms ON + 24 ms OFF rectangular pulses at `genus_frequency` (default 40.0 Hz)
- **No smoothing, no fade-in, no Hanning windows on individual pulses**
- Monaural output (both channels identical)
- Both channels receive same signal (not binaural separation)
- Phase-lock to `beat_phase` for AV sync

New config keys:
```json
{
    "genus_active": false,
    "genus_frequency": 40.0,
    "genus_audio_pulse_ms": 1.0,
    "genus_audio_enabled": true,
    "genus_visual_enabled": true,
    "genus_visual_duty_cycle": 0.5,
    "genus_modulation_depth": 1.0,
    "genus_session_duration_min": 60,
    "genus_session_start_time": null
}
```

### 5.2 `visual_display.py` — 40 Hz Flicker Layer

1. **Monitor refresh rate detection at startup:**
   ```python
   import pygame
   info = pygame.display.Info()
   refresh_rate = info.current_refresh  # e.g., 144
   if refresh_rate < 80:
       print("[GENUS] Warning: display refresh rate < 80 Hz — visual flicker unavailable, fallback to audio-only")
   ```

2. **Frame pattern generation** (for 144 Hz):
   - Pre-compute a dither sequence that averages 40 Hz over multiple cycles
   - Use frame counter modulo pattern: at 144 Hz, pattern like `[1,1,0,0,1,1,0,1,1,0]` averaged = 40 Hz
   - Apply as a scalar modulation to the full composite frame (OpenGL `glClearColor` or overlay blend factor)

3. **Dedicated GENUS overlay layer** — composited at the final stage. `genus_modulation_depth` controls contrast (1.0 = full black-to-white, 0.5 = dimmer flicker). Can layer over existing spiral/veil content.

4. **AV sync:** Read `beat_phase` from `live_control.json`. Align visual ON frames to when `beat_phase` crosses 0.0. The audio click and visual ON onset phase-lock within the jitter tolerance.

### 5.3 `eeg_engine.py` — GENUS Entrainment Verification

During GENUS sessions, monitor the narrow 38–42 Hz band for entrainment ratio:

```python
# Every 2–5 seconds during GENUS session
g40 = DataFilter.get_custom_band_powers(
    data, [(38.0, 42.0)], eeg_channels, sampling_rate, True
)
gamma_40hz_power = float(g40[0][0])
entrainment_ratio = gamma_40hz_power / baseline_40hz_power  # established in pre-session 60s window

# Values: >2.0 = strong, >1.5 = moderate, <1.2 = weak/absent
_patch_live({"eeg_gamma_40hz": round(gamma_40hz_power, 6), "eeg_genus_ratio": round(entrainment_ratio, 3)})
```

**Artifact note:** Visual flicker produces stimulus-locked EEG artifacts. To distinguish genuine neural entrainment from artifact: compare entrainment ratio during vs. immediately after stimulation offset (genuine entrainment persists briefly; artifact disappears instantly). Alternatively, use audio-only GENUS for cleaner EEG measurement, introduce visual flicker after confirming auditory entrainment.

### 5.4 Cognitive Engagement Enhancement

**Mlinarič et al. (2025) finding:** Cognitive engagement during 40 Hz stimulation enhances both the strength and spatial extent of neural entrainment, including shifting information flow frontal→hippocampal. This is a competitive advantage.

| Somna Feature | Engagement Type | Expected Enhancement |
|--------------|-----------------|---------------------|
| Scrolling veil affirmations | Reading = active cognitive engagement | Frontal lobe recruitment; enhanced hippocampal entrainment |
| Agent prompts and questions | Responding = high active engagement | Maximum frontal-hippocampal coupling |
| Center text affirmations | Attending = mild engagement | Sustained visual attention supports visual cortex entrainment |
| Spiral focus tasks | Attentional engagement | Enhanced visual pathway entrainment |

**GENUS sessions should NOT be passive staring at a flickering screen.** Somna should layer interactive cognitive content over the 40 Hz flicker. This is a research-backed differentiating feature that simple passive 40 Hz devices (Cognito Therapeutics device, etc.) cannot match.

### 5.5 Safety Implementation

| Safety Feature | Requirement |
|---------------|------------|
| Epilepsy warning | Modal dialog before first GENUS session. Explicit acknowledgment. Store state so shown only once (but re-display if `genus_visual_enabled` re-enabled). |
| Audio-only mode | `genus_visual_enabled: false` — safe for photosensitive epilepsy risk. Audio clicks only. |
| Volume limiting | Hard max 78 dB SPL at output |
| Session timer | Auto-stop after `genus_session_duration_min` (default 60). Write `genus_active: false`. Display remaining time. |
| Emergency stop | Escape key → stimulation cessation < 100 ms. Must work reliably from any app state. |
| Session logging | Log start/stop times, modalities, total duration, any user-initiated stops |

---

## 6. Mechanism Summary

### 6.1 Primary Mechanism Chain (Glymphatic Pathway)
*(Murdock et al., 2024, Nature)*

```
40 Hz sensory stimulation (light + sound)
  → Cortical gamma oscillation entrainment (40 Hz neural synchrony across brain)
    → VIP interneuron activation (vasoactive intestinal peptide release)
      → Arterial pulsatility increase (arteriole dilation)
        → Astrocyte AQP4 channel polarization (aquaporin-4 water channels on endfeet)
          → Glymphatic CSF influx (cerebrospinal fluid enters parenchyma)
            → Amyloid-beta washout (cleared from brain tissue)
              → Meningeal lymphatic drainage (waste exits brain)
```

Pharmacological validation: blocking glymphatic clearance abolished the effect. VIP interneuron chemogenetic manipulation confirmed causal role.

### 6.2 Additional Mechanisms
- **Microglial morphology changes:** Microglia shift to more phagocytic state, cluster around amyloid plaques (Iaccarino 2016)
- **Reduced neuroinflammation:** Pro-inflammatory cytokine reduction
- **Synaptic protection:** Preservation of synaptic density (Neuron 2019)
- **Improved functional connectivity:** Default mode network + medial visual network (Chan 2022)
- **Circadian rhythm improvement:** Daily activity rhythmicity (Chan 2022)

### 6.3 Key Insight

The glymphatic system is the same waste-clearance infrastructure most active during deep (NREM) sleep. **40 Hz GENUS essentially amplifies the brain's natural waste-clearance system during wakefulness, providing amyloid clearance that normally requires sleep.** Does not replace sleep but supplements it.

Cognitive engagement enhances the effect (Mlinarič 2025) — the mechanism involves active neural circuit participation, not merely a passive sensory response.

---

## 7. Implementation Checklist

| # | Task | Module | Notes |
|---|------|--------|-------|
| 1 | Add rectangular pulse generator (1 ms ON, 24 ms OFF, configurable Hz) | `audio_engine.py` | No fade, no smoothing on individual pulses |
| 2 | Monitor refresh rate detection at startup | `visual_display.py` | Warn + fallback if < 80 Hz |
| 3 | Add 40 Hz flicker overlay layer (frame pattern per refresh rate) | `visual_display.py` | Depends on #2 |
| 4 | AV phase sync via `beat_phase` key | `audio_engine.py` + `visual_display.py` | Depends on #1 and #3 |
| 5 | Add `genus_*` keys to `live_control.json` schema | `live_control.json` | |
| 6 | Narrow-band 38–42 Hz monitoring + entrainment ratio | `eeg_engine.py` | Requires Muse 2 for live testing |
| 7 | GENUS session YAML template (60 min, with cognitive engagement content) | `sessions/genus/session.yaml` | |
| 8 | Photosensitive epilepsy safety warning dialog | `control_panel_imgui.py` | Must be in place before visual flicker is user-facing |
| 9 | Session timer + emergency stop (Escape) | `control_panel_imgui.py` | |
| 10 | Test: synthetic EEG first, then Muse 2 | `eeg_engine.py` | |

---

## 8. References

1. Iaccarino et al. (2016). Gamma frequency entrainment attenuates amyloid load and modifies microglia. *Nature*, 540, 230–235. doi:10.1038/nature20587
2. Adaikkan et al. (2019). Gamma entrainment binds higher-order brain regions and offers neuroprotection. *Neuron*, 102(5), 929–943.
3. Martorell et al. (2019). Multi-sensory gamma stimulation ameliorates Alzheimer's-associated pathology and improves cognition. *Cell*, 177(2), 256–271.
4. Chan et al. (2022). Gamma frequency sensory stimulation in mild probable Alzheimer's dementia patients. *PLOS ONE*, 17(12), e0278412.
5. Murdock et al. (2024). Multisensory gamma stimulation promotes glymphatic clearance of amyloid. *Nature*, 627, 149–156. doi:10.1038/s41586-024-07132-6
6. Blanpain et al. (2024). Multisensory flicker modulates widespread brain networks and reduces interictal epileptiform discharges. *Nature Communications*, 15, 3156. Trial: NCT04188834.
7. Mlinarič et al. (2025). Visual gamma stimulation induces 40 Hz neural oscillations in the human hippocampus and alters phase synchrony and lag. *Communications Biology*, 8, 1301.
8. Park & Tsai (2025). [Decade review of 40 Hz gamma stimulation]. *PLOS Biology*.
9. Chan & Tsai (2025). [~30-month open-label extension in 5 mild AD patients]. *Alzheimer's & Dementia*.

**Active Trial:** NCT05776641 — "Gamma Light and Sound Stimulation to Prevent Dementia" (MGH, recruiting as of March 2026)

---

## 9. Medical Disclaimer

GENUS is an active research protocol. Not FDA-approved for treatment, prevention, or diagnosis of any disease. Somna's implementation is for personal experimental use only. Not a medical device.

**Stroboscopic visual stimulation at 40 Hz may trigger seizures in individuals with photosensitive epilepsy.** Users with epilepsy, seizure history, or photosensitive conditions must use audio-only mode. Audio-only mode must always be available.

The developers of Somna are not affiliated with MIT, the Tsai Lab, Cognito Therapeutics, or Massachusetts General Hospital.
