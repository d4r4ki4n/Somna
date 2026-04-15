# Somna Doc 44 — Stimulus Techniques & Optimization

**Concrete Entrainment Methods, Geometry Specifications, and Conditioning Delivery Patterns**

**Status:** Specification — ready for implementation

**Author:** Ed

**Date:** 5 April 2026

**Depends on:** Doc 35 (Phase-Cascade), Doc 36 (Semantic Selection), Doc 37 (Crossmodal Gain), Doc 38 (Trance Depth v2), Doc 42 (Cardiac-Phase Gating), Doc 43 (Conditioning Architecture)

**Implements in:** visual_display.py, audio_engine.py, semantic_selector.py, delivery_gate.py, crossmodal_gain.py, conductor.py

# 1\. Overview

This document specifies concrete, evidence-based stimulus techniques that optimize Somna's entrainment and conditioning effectiveness. It does **not** introduce new architectural subsystems — it specifies new parameters, functions, and modes for existing modules. Every technique maps to a specific .py file and integrates with the existing phase-cascade, gain manifold, and conditioning framework.

The techniques are organized into five domains:

- **§2 Visual Geometry** — golden spiral, fractal edges, IAF-matched rotation, motion aftereffect
- **§3 Audio Structure** — dual-mode entrainment, IAF personalization, AM depth profiling, spectral shaping
- **§4 Conditioning Delivery** — trace intervals, compound stimuli, spaced repetition, VR optimization
- **§5 Crossmodal Timing** — temporal binding window, stochastic resonance tuning
- **§6 Subliminal Presentation** — Shadows timing, masking parameters

# 2\. Visual Geometry Optimization (visual_display.py)

## 2.1 Golden Spiral Mode

**Scientific basis:** Golden (Fibonacci) spirals follow r = a·e^(b·θ) where b = ln(φ)/(π/2) ≈ 0.3063 and φ = 1.618034. Salera et al. (2024, _Symmetry_/MDPI) demonstrated that golden-ratio stimuli produce faster response times and higher accuracy when paired with positive categories in implicit association tasks. Explicit preference varies individually (Hübner & Goodarzi, 2025, _Scientific Reports_), but implicit preference — the kind that matters for subconscious processing — favors the golden ratio.

**Implementation:** Add a spiral_geometry parameter to the spiral renderer config.

spiral_geometry: str = "archimedean" # Options: "archimedean", "golden", "logarithmic"

When spiral_geometry == "golden":

- Growth factor b = ln(1.618034) / (π/2) ≈ 0.30634896...
- Arm separation angle = 2π / num_arms (unchanged)
- Each arm follows r(θ) = r_min · e^(b · θ) from θ_start to θ_max
- r_min = 0.02 (normalized to viewport), θ_max = 6π (3 full turns)
- Arm width tapers: width(θ) = base_width · e^(b · θ · 0.5) — grows with radius but at half-rate, so arms get proportionally thinner
- The existing color palette, opacity, and trail_decay parameters apply unchanged

When spiral_geometry == "archimedean" (current default, unchanged):

- r(θ) = a + b_arch·θ with constant spacing

When spiral_geometry == "logarithmic":

- r(θ) = a · e^(b_log · θ) with user-configurable b_log (default 0.2)

**Config key in live_control.json:** "spiral_geometry" (string). Patchable at runtime.

## 2.2 Fractal Edge Modulation

**Scientific basis:** Hagerhall's EEG study found fractal images with dimension D ≈ 1.3 produce the largest frontal alpha power changes. D between 1.3–1.5 produces maximal alpha response. This is the fractal dimension found in natural landscapes, clouds, and coastlines — the human visual system is tuned to it.

**Implementation:** Add fractal noise displacement to spiral arm edges.

New parameters:

fractal_edge_enabled: bool = True fractal_edge_d: float = 1.3 # Target fractal dimension fractal_edge_amplitude: float = 0.15 # Max displacement as fraction of arm width fractal_edge_octaves: int = 5 # Noise octaves for self-similarity fractal_edge_seed: int = 0 # Random seed (0 = use session timestamp) fractal_edge_drift_rate: float = 0.02 # How fast the noise pattern crawls along edges (units/s)

The fractal dimension D maps to the Hurst exponent H via D = 2 - H (for 1D edge profiles). So D = 1.3 → H = 0.7. Generate fractional Brownian motion (fBm) with H = 0.7 using spectral synthesis:

1.  Generate white noise spectrum in frequency domain
2.  Scale amplitude of frequency k by k^(-(H + 0.5)) = k^(-1.2)
3.  Inverse FFT to get displacement profile
4.  Normalize to \[-1, 1\] range, multiply by fractal_edge_amplitude × arm_width
5.  Apply as perpendicular displacement to each arm edge vertex

The noise pattern drifts along the edge at fractal_edge_drift_rate to prevent static appearance while maintaining structural self-similarity. This drift is **not** random jitter — it is a smooth translation of the noise seed coordinate along the arm parameterization.

#### Anti-Habituation Cycle

Every 120 seconds, smoothly interpolate fractal_edge_d between 1.2 and 1.4 over 10 seconds, then return to 1.3. This creates subtle organic variation while keeping the alpha-optimal center. The interpolation changes H from 0.8 to 0.6 and back:

if (time_in_cycle % 120) < 10: t = (time_in_cycle % 120) / 10.0 current_H = 0.7 + 0.1 \* sin(t \* π) # Smooth there-and-back else: current_H = 0.7

**Config keys:** "fractal_edge_enabled", "fractal_edge_d", "fractal_edge_amplitude" — all patchable.

## 2.3 IAF-Matched Rotation Rate

**Scientific basis:** Gulbinaite et al. (2017, _Journal of Neuroscience_) demonstrated that individual alpha peak frequency (IAF) predicts 10 Hz flicker entrainment effectiveness — flicker at the person's IAF produces maximum entrainment. Somna's eeg_engine.py already computes IAF during calibration.

**Implementation:** The perceived flicker frequency of a rotating multi-arm spiral equals:

perceived_flicker_Hz = num_arms × rotation_rate_Hz

To match IAF:

rotation_rate_Hz = IAF / num_arms

New parameters:

rotation_iaf_lock: bool = True # When True, rotation speed auto-derived from IAF rotation_iaf_divisor: int = 0 # Override: if > 0, rotation = IAF / divisor (ignores num_arms)

When rotation_iaf_lock == True and rotation_iaf_divisor == 0:

- rotation_rate_Hz = eeg_iaf / num_arms
- Example: IAF = 10.2, 4 arms → rotation = 2.55 Hz → perceived flicker = 10.2 Hz ✓

When rotation_iaf_divisor > 0:

- rotation_rate_Hz = eeg_iaf / rotation_iaf_divisor
- This allows subharmonic entrainment: divisor=8 with 4 arms → flicker = IAF/2 (theta-range)

**Fallback:** If IAF is not yet calibrated (eeg_iaf == 0 or None), use 10.0 Hz as default IAF.

The rotation rate updates every 30 seconds from the latest IAF measurement, smoothly interpolating over 2 seconds to prevent jarring speed changes.

#### Phase-Dependent Override

The Conductor can shift the target frequency based on phase:

| **Phase** | **Target** | **Effect** |
| --- | --- | --- |
| INDUCTION | IAF × 1.0 | Alpha entrainment |
| --- | --- | --- |
| DEEPENING | IAF × 0.75 | Pulling toward theta |
| --- | --- | --- |
| MAINTENANCE | IAF × 0.6 | Deep theta |
| --- | --- | --- |
| SLEEP_APPROACH | IAF × 0.4 | Delta approach |
| --- | --- | --- |

This multiplier is applied before the num_arms division. It is written to live_control.json as "rotation_iaf_multiplier" (float, default 1.0).

**Config keys:** "rotation_iaf_lock", "rotation_iaf_divisor", "rotation_iaf_multiplier" — all patchable.

## 2.4 Motion Aftereffect Exploitation

**Scientific basis:** Viewing a rotating spiral for ~30 seconds produces neural adaptation in direction-selective neurons (primarily pretectal circuit — Wu et al., 2020, _Neuron_). When the spiral stops or reverses, the user experiences a compelling somatic sensation of expansion or contraction that persists for several seconds. This is a **felt** experience — it works regardless of visualization ability and is ideal for an aphantasic user.

**Implementation:** Periodic spiral direction reversals to exploit the motion aftereffect.

New parameters:

aftereffect_enabled: bool = True aftereffect_cycle_s: float = 35.0 # Seconds per rotation direction (>30 for adaptation saturation) aftereffect_pause_s: float = 2.0 # Seconds of zero rotation at reversal (maximizes aftereffect) aftereffect_ramp_s: float = 1.5 # Seconds to ramp back to full speed after pause aftereffect_gate: bool = True # When True, reversals only fire through DeliveryGate

Cycle structure:

1.  Rotate clockwise for aftereffect_cycle_s seconds (adaptation builds)
2.  Ramp rotation speed to zero over 0.5 seconds
3.  Hold at zero for aftereffect_pause_s seconds (aftereffect peaks — user feels expansion/contraction)
4.  Ramp to counter-clockwise over aftereffect_ramp_s seconds
5.  Rotate counter-clockwise for aftereffect_cycle_s seconds
6.  Repeat

When aftereffect_gate == True: the reversal only triggers when the DeliveryGate AND-logic returns True (respiratory trough + alpha trough + cardiac diastole + stillness). This synchronizes the peak somatic sensation with optimal stimulus delivery windows. If the gate doesn't open within 10 seconds of the scheduled reversal, fire anyway to prevent drift.

**CenterText Interaction**

During the aftereffect_pause_s zero-rotation window, if a CenterText phrase is queued, display it. The combination of somatic aftereffect sensation + text creates a powerful associative pairing — the felt sensation becomes a somatic anchor for the phrase content.

**Config keys:** "aftereffect_enabled", "aftereffect_cycle_s", "aftereffect_pause_s", "aftereffect_gate" — all patchable.

# 3\. Audio Structure Optimization (audio_engine.py)

## 3.1 Dual-Mode Entrainment: Isochronic-Primary + Binaural-Secondary

**Scientific basis:** Isochronic tones produce stronger cortical entrainment than binaural beats (Manns, 1981; multiple replications). They create a more distinctive beat producing a stronger EEG frequency-following response. However, binaural beats uniquely engage subcortical structures (superior olivary complex) via the phantom beat percept. Running both simultaneously provides cortical + subcortical entrainment.

**Implementation:** New entrainment mode that layers isochronic and binaural.

New parameter:

entrainment_mode: str = "dual" # Options: "binaural", "isochronic", "dual"

When entrainment_mode == "dual":

isochronic_duty_cycle: float = 0.5 # Fraction of period at full amplitude (0.3-0.7 valid range)

binaural_blend: float = 0.3 # 0.0 = isochronic only, 1.0 = equal, range 0.0-1.0

When entrainment_mode == "binaural": current behavior, unchanged.

When entrainment_mode == "isochronic": isochronic only, no binaural.

**Config keys:** "entrainment_mode", "isochronic_duty_cycle", "binaural_blend" — all patchable.

## 3.2 IAF-Personalized Beat Frequency

**Scientific basis:** Battù et al. (2025, _Bioengineering_/MDPI) — personalized alpha-range binaural beats based on individual IAF produced classification accuracy >81% (baseline vs stimulation) and >89% (baseline vs post-stimulation) with persistent frontal EEG effects after 10-day training. Fixed-frequency protocols show weaker effects.

**Implementation:** The beat frequency for both isochronic and binaural channels is derived from IAF.

beat_freq_source: str = "iaf" # Options: "iaf", "fixed", "conductor" beat_freq_fixed: float = 10.0 # Used when beat_freq_source == "fixed"

When beat_freq_source == "iaf":

- beat_freq = eeg_iaf (from eeg_engine calibration, typically 8–12 Hz)
- Updates every 30 seconds with 2-second smooth interpolation (same cadence as visual)
- Fallback: 10.0 Hz if IAF not yet available

When beat_freq_source == "conductor":

| **Phase** | **Multiplier** |
| --- | --- |
| INDUCTION | IAF × 1.0 |
| --- | --- |
| DEEPENING | IAF × 0.75 |
| --- | --- |
| MAINTENANCE | IAF × 0.6 |
| --- | --- |
| SLEEP_APPROACH | IAF × 0.4 |
| --- | --- |

**Critical Design Constraint**

Audio and visual entrainment frequencies are always locked together — they both derive from IAF and both use the same Conductor multiplier. This crossmodal frequency coherence is critical for binding.

**Config keys:** "beat_freq_source", "beat_freq_fixed", "beat_freq_target" — all patchable.

## 3.3 Amplitude Modulation Depth Profiling

**Scientific basis:** The brainwave entrainment integrative review (Cidral-Filho et al., 2024, _Applied Psychophysiology and Biofeedback_) establishes that AM depth is a key parameter for entrainment effectiveness. Too much depth is jarring and prevents deepening; too little fails to entrain. The optimal depth varies with trance state.

**Implementation:** Phase-dependent AM depth for all amplitude-modulated audio.

New parameters:

am_depth: float = 0.8 # Current AM depth, 0.0 (no modulation) to 1.0 (full on/off), patchable

AM depth profile by Conductor phase:

| **Phase** | **AM Depth** | **Rationale** |
| --- | --- | --- |
| CALIBRATION | 0.0 | No modulation during baseline measurement |
| --- | --- | --- |
| INDUCTION | 0.9 | Strong beat for initial entrainment capture |
| --- | --- | --- |
| DEEPENING | 0.7 | Moderate — maintain entrainment, reduce harshness |
| --- | --- | --- |
| MAINTENANCE | 0.5 | Gentle — brain is entrained, less drive needed |
| --- | --- | --- |
| FRACTIONATION_LIFT | 0.8 | Re-engage for deliberate lift |
| --- | --- | --- |
| FRACTIONATION_DROP | 0.6 | Moderate for re-deepening |
| --- | --- | --- |
| SLEEP_APPROACH | 0.3 | Minimal — approaching sleep, avoid arousal |
| --- | --- | --- |
| SLEEP_ONSET | 0.2 | Near-subliminal modulation |
| --- | --- | --- |
| SLEEP_MAINTAIN | 0.15 | Barely perceptible |
| --- | --- | --- |
| SLEEP_TRAINING | 0.25 | Slight increase for conditioning delivery |
| --- | --- | --- |

The Conductor writes "am_depth" to live_control.json on every phase transition. audio_engine reads it each tick and interpolates toward the target over 5 seconds.

AM depth applies to:

- Isochronic envelope depth (at depth 0.5, amplitude cycles between 0.5 and 1.0 instead of 0.0 and 1.0)
- Binaural volume modulation envelope
- Breath-synchronized AM on pink/brown noise (existing feature — now depth-controlled)

**Config keys:** "am_depth" (float, patchable), "am_depth_profile" (dict, config-only).

## 3.4 Dynamic Spectral Tilt

**Scientific basis:** Pink noise has a 1/f^1.0 power spectrum. The human brain's aperiodic neural activity steepens (higher exponent) during relaxation and sleep. Doc 38 tracks this as spectral_slope. Matching the audio spectral slope to the brain's current aperiodic slope creates congruence.

**Implementation:** Dynamically tilt the noise spectrum to track neural state.

New parameters:

noise_spectral_tilt: float = 1.0 # Exponent α in 1/f^α, range 0.8-1.5 noise_tilt_track_brain: bool = False # When True, tilt tracks eeg spectral_slope

When noise_tilt_track_brain == True:

- Read eeg_spectral_slope from eeg_engine output (typically -1.0 to -2.0 for 1/f^1 to 1/f^2)
- Set noise_spectral_tilt = abs(eeg_spectral_slope), clamped to \[0.8, 1.5\]
- Update every 10 seconds with 5-second interpolation
- As the brain deepens (slope steepens toward -1.5 to -2.0), the audio shifts toward brown noise (1/f^1.5) — more low-frequency emphasis, more "depth"

When noise_tilt_track_brain == False:

- Use fixed noise_spectral_tilt value
- Default 1.0 = standard pink noise

**Implementation approach:** Apply a frequency-domain filter to the existing pink noise generator. For each FFT frame, multiply bin amplitudes by (f_bin / f_ref)^(1.0 - α) where α is the target tilt. When α = 1.0, this is identity (pink). When α = 1.5, low frequencies are boosted by ~4 dB per octave relative to pink.

**Config keys:** "noise_spectral_tilt", "noise_tilt_track_brain" — all patchable.

# 4\. Conditioning Delivery Optimization

## 4.1 Trace Conditioning Intervals (semantic_selector.py, delivery_gate.py)

**Scientific basis:** Finke et al. (2025, _Scientific Reports_) — within-subject comparison showed trace conditioning (CS–US gap of 1–4 seconds) produced conditioned responses that showed significantly diminished extinction compared to delay conditioning (CS–US overlap). Knight et al. (2004, _Journal of Neuroscience_) showed trace conditioning additionally recruits hippocampus, SMA, frontal operculum, middle frontal gyrus, and inferior parietal lobule — more brain regions engaged = deeper, more distributed encoding.

**In Somna's architecture:** The Shadows word is the CS (conditioned stimulus). The CenterText phrase is the US (unconditioned stimulus — the full meaning payload). Currently these can fire independently or simultaneously. Trace conditioning means deliberately inserting a gap between Shadows prime and CenterText delivery.

**Implementation:** New trace interval logic in semantic_selector.py.

trace_conditioning_enabled: bool = True trace_interval_base_s: float = 1.5 # Base trace interval in seconds trace_interval_range_s: list = \[0.8, 3.5\] # \[min, max\] for variable intervals trace_interval_variability: float = 0.3 # Fraction of base to vary (uniform random)

Delivery sequence when trace_conditioning_enabled:

jitter = trace_interval_base_s \* trace_interval_variability trace_interval = trace_interval_base_s + uniform(-jitter, +jitter) trace_interval = clip(trace_interval, trace_interval_range_s\[0\], trace_interval_range_s\[1\])

The variability prevents the user from unconsciously predicting the exact timing, which would reduce the associative impact. However, the range is constrained enough that the brain still learns "Shadows → pause → CenterText" as a reliable sequence.

#### Acquisition vs Maintenance Phase Adaptation

| **Session Range** | **trace_interval_base_s** | **Rationale** |
| --- | --- | --- |
| Sessions 1–5 | 1.0 | Shorter gap = easier acquisition |
| --- | --- | --- |
| Sessions 6–15 | 1.5 | Standard trace interval |
| --- | --- | --- |
| Sessions 16+ | 2.5 | Longer gap = stronger trace, extinction-resistant |
| --- | --- | --- |

The session count is per content pool, stored in the conditioning_history table from Doc 43.

**Config keys:** "trace_conditioning_enabled", "trace_interval_base_s", "trace_interval_range_s" — all patchable.

## 4.2 Compound Stimulus Design (crossmodal_gain.py, cue_manager.py)

**Scientific basis:** Configural conditioning (Pearce, 1987) — when multiple CS elements are presented simultaneously, the organism encodes the configuration as a unique compound rather than a sum of elements. This produces distinctive, hard-to-generalize associations. The compound CS is more robust because extinguishing any single element does not extinguish the compound.

**In Somna:** Combine tonal cue (cue_manager) + spiral color/speed shift (visual_display) + gain profile change (crossmodal_gain) as a unified compound CS for each content pool.

**Implementation:** Each content pool (6 pools from Doc 36) gets a compound stimulus signature:

COMPOUND_CS_REGISTRY = { "WARMTH_COMFORT": { "tonal_cue": "pool_0_tone", "spiral_hue_shift": +15.0, # Degrees on color wheel, warm direction "spiral_speed_mult": 0.85, # Slight slowdown (approach, shallow) "gain_profile": "approach_shallow", "noise_tilt_offset": +0.05, # Slightly warmer noise (toward brown) }, "IDENTITY": { "tonal_cue": "pool_1_tone", "spiral_hue_shift": +30.0, "spiral_speed_mult": 0.90, "gain_profile": "approach_moderate", "noise_tilt_offset": +0.1, }, "DISSOLUTION": { "tonal_cue": "pool_2_tone", "spiral_hue_shift": +45.0, # Strong warm shift "spiral_speed_mult": 0.70, # Significant slowdown (deep state) "gain_profile": "approach_deep", "noise_tilt_offset": +0.15, }, "GROUNDING_TEXTURE": { "tonal_cue": "pool_3_tone", "spiral_hue_shift": -10.0, # Slight cool shift "spiral_speed_mult": 1.0, # Steady (grounding) "gain_profile": "withdrawal_shallow", "noise_tilt_offset": -0.05, }, "SOMATIC_ANCHORING": { "tonal_cue": "pool_4_tone", "spiral_hue_shift": -20.0, # Cool shift "spiral_speed_mult": 1.05, # Slight speedup (alerting withdrawal) "gain_profile": "withdrawal_moderate", "noise_tilt_offset": -0.1, }, "STILLNESS_EMPTINESS": { "tonal_cue": "pool_5_tone", "spiral_hue_shift": 0.0, # No shift (emptiness = neutral) "spiral_speed_mult": 0.60, # Significant slowdown "gain_profile": "withdrawal_deep", "noise_tilt_offset": +0.2, # Deep brown noise (stillness) }, }

When semantic_selector activates a pool:

1.  Write the compound CS parameters to live_control.json via \_patch_live()
2.  visual_display reads spiral_hue_shift and spiral_speed_mult → smoothly interpolates over 2 seconds
3.  audio_engine reads noise_tilt_offset → adjusts spectral tilt
4.  cue_manager fires the tonal cue
5.  crossmodal_gain applies the gain_profile preset
6.  **All** of these happen within the 200ms temporal binding window (see §5.1) — the tonal cue leads, visual and gain follow within 100–200ms

The compound CS fires **before** the Shadows word (it sets the context), then the trace interval (§4.1) runs, then the CenterText phrase delivers. The full sequence is:

Compound CS (tone + visual + gain shift) → Shadows word → \[trace interval\] → CenterText phrase

**Conditioning Mechanism**

The compound CS is a Pavlovian predictor of the content delivery. Over sessions, the compound CS alone begins to evoke the state associated with that pool — before any words appear.

**Config key:** "compound_cs_enabled" (bool, default True, patchable).

## 4.3 Spaced Repetition Within and Across Sessions (semantic_selector.py)

**Scientific basis:** The spacing effect (Ebbinghaus, 1885; meta-analysis _d_ = 0.69 across 586 studies, 167,763 participants) — distributed practice produces 10–30% better retention than massed practice. Optimal inter-study interval ≈ 10–30% of desired retention interval.

**Implementation:** Controls how frequently the same content pool is re-activated within a session and across sessions.

#### Within-Session Spacing

pool_spacing_min_s: float = 360.0 # Minimum seconds before same pool re-activates (6 minutes) pool_spacing_max_s: float = 900.0 # Maximum seconds before same pool is prioritized (15 minutes)

When selecting the next pool:

urgency = (time_since - pool_spacing_min_s) / (pool_spacing_max_s - pool_spacing_min_s) urgency = clip(urgency, 0.0, 1.0) weight = base_weight_from_state_space \* (0.5 + 0.5 \* urgency)

#### Cross-Session Spacing

- The conditioning_history table (Doc 43) stores last_activation_timestamp per pool
- Pools that haven't been activated in >3 sessions get a 1.5× weight boost
- Pools activated in the immediately previous session get a 0.7× weight reduction
- This ensures all 6 pools receive periodic reinforcement even if the user's EEG state space tends to favor certain pools

**Config keys:** "pool_spacing_min_s", "pool_spacing_max_s" — patchable.

## 4.4 Variable Ratio Schedule Optimization (delivery_gate.py)

**Scientific basis:** VR schedules produce the highest, steadiest response rates and strongest resistance to extinction. The post-reinforcement pause disappears. Behavior persists even after rewards stop because the organism is accustomed to variable dry spells.

**Implementation:** Refines Doc 43's VR scheduling with specific ratio progressions.

vr_ratio_acquisition: int = 3 # VR-3: reinforce after average 3 gate-openings (range 1-5) vr_ratio_maintenance: int = 5 # VR-5: reinforce after average 5 gate-openings (range 2-8) vr_transition_session: int = 10 # Session count at which VR transitions from acquisition to maintenance

**VR-3 during acquisition (sessions 1–10):** On average, every 3rd time the DeliveryGate opens for a given pool, the full conditioning sequence fires. The other 2 are "dry" — the gate opens, but only the compound CS fires without content. This teaches the brain that the compound CS _sometimes_ predicts content, creating anticipatory engagement.

**VR-5 during maintenance (sessions 11+):** More variable, wider range. The user experiences longer stretches without content for a given pool, making each delivery more impactful and the association more extinction-resistant.

The VR counter is per-pool, tracked in the conditioning_history table. The actual count for each reinforcement is drawn from a geometric distribution:

import random def next_vr_count(ratio): """Returns number of gate-openings until next reinforcement.""" p = 1.0 / ratio return max(1, int(random.expovariate(p))) # Geometric distribution, minimum 1

**Config keys:** "vr_ratio_acquisition", "vr_ratio_maintenance", "vr_transition_session" — config-only (not runtime-patchable; these are session-level parameters).

# 5\. Crossmodal Timing Optimization

## 5.1 Temporal Binding Window (crossmodal_gain.py)

**Scientific basis:** Multisensory integration occurs within a temporal binding window (TBW) of approximately 200–300ms. Stimuli from different modalities arriving within this window are automatically bound into a unified percept by the brain's causal inference machinery (Günaydın et al., 2026, _Scientific Reports_; Tong et al., 2020, _Attention, Perception & Psychophysics_). Audio-leading is slightly more effective than visual-leading for binding, due to auditory dominance in temporal processing.

**Implementation:** When compound CS or any crossmodal stimulus fires, enforce temporal ordering:

binding_window_ms: int = 200 # Maximum spread between first and last modality onset audio_lead_ms: int = 50 # Audio fires this many ms before visual onset

Crossmodal firing sequence:

| **Time Offset** | **Action** | **Module** |
| --- | --- | --- |
| t = 0 | Tonal cue onset | audio_engine |
| --- | --- | --- |
| t = audio_lead_ms (50ms) | Visual changes applied (spiral hue/speed shift, Shadows word if present) | visual_display |
| --- | --- | --- |
| t = audio_lead_ms + 30ms (80ms) | Gain profile change applied | crossmodal_gain |
| --- | --- | --- |

Total spread: ~80ms, well within the 200ms binding window.

This sequence is managed by a CrossmodalDispatcher function added to crossmodal_gain.py:

def dispatch_compound_cs(pool_name: str, live_control: dict): """Fire compound CS elements in temporal binding order.""" # 1. Audio cue immediately \_patch_live({"cue_fire": pool_name}) # 2. Visual after audio_lead_ms time.sleep(audio_lead_ms / 1000.0) \_patch_live({ "spiral_hue_shift": COMPOUND_CS_REGISTRY\[pool_name\]\["spiral_hue_shift"\], "spiral_speed_mult": COMPOUND_CS_REGISTRY\[pool_name\]\["spiral_speed_mult"\], }) # 3. Gain after 30ms more time.sleep(0.030) \_patch_live({ "gain_profile": COMPOUND_CS_REGISTRY\[pool_name\]\["gain_profile"\], "noise_tilt_offset": COMPOUND_CS_REGISTRY\[pool_name\]\["noise_tilt_offset"\], })

**Threading Note**

The sleep calls are acceptable because this runs in semantic_selector's own thread, not the render loop. visual_display and audio_engine read their values from live_control.json on their next tick.

**Config keys:** "binding_window_ms", "audio_lead_ms" — config-only.

## 5.2 Stochastic Resonance Visual Floor (visual_display.py, crossmodal_gain.py)

**Scientific basis:** Stochastic resonance (SR) occurs when a subthreshold signal becomes detectable by adding an optimal level of noise. Doc 37 already implements SR coupling in the crossmodal gain manifold. The fractal edges from §2.2 serve as the visual SR noise floor — they are structured noise at the edge of perception.

**Implementation:** The fractal_edge_amplitude parameter from §2.2 is now coupled to the SR gain channel from Doc 37.

\# In crossmodal_gain.py SR coupling update: sr_optimal_noise = compute_sr_optimal(current_signal_strength, noise_floor) fractal_edge_amplitude_sr = base_fractal_amplitude \* (0.5 + 0.5 \* sr_optimal_noise) \_patch_live({"fractal_edge_amplitude": fractal_edge_amplitude_sr})

When signal strength is low (shallow trance, weak alpha), fractal edge amplitude increases — more visual noise pushes subthreshold entrainment signals past the detection threshold. When signal strength is high (deep trance, strong alpha), fractal edges decrease — the brain is already entrained and excess noise would degrade the signal.

The existing SR coupling math from Doc 37 handles the optimization. This specification only routes the SR output to a new visual parameter.

# 6\. Subliminal Presentation Optimization (Shadows Layer)

## 6.1 Display Duration and Masking (visual_display.py, semantic_selector.py)

**Scientific basis:** Subliminal visual stimuli below ~50ms with backward masking are below conscious perception threshold while still activating amygdala and semantic processing networks (confirmed via fMRI). The ISI law (Francis et al., 2004, _Spatial Vision_) establishes that the critical masking parameter is the interstimulus interval — the time gap between stimulus offset and mask onset.

**Important Limitation**

Subliminal stimuli can facilitate or speed up existing behavioral tendencies but generally lack power to create entirely new behaviors. This aligns with Somna's design — the affirmations reinforce what the user already wants.

**Implementation:** Precise timing for Shadows word display.

shadows_display_ms: int = 33 # Display duration in ms (2 frames at 60Hz, 1 frame at 30Hz) shadows_mask_isi_ms: int = 17 # ISI between word offset and spiral mask (1 frame at 60Hz) shadows_display_mode: str = "masked" # Options: "masked", "brief", "supraliminal"

#### Mode: "masked" (default, fully subliminal)

1.  Word rendered at configured opacity for shadows_display_ms milliseconds
2.  Word removed
3.  After shadows_mask_isi_ms, the spiral rendering resumes at full opacity (acts as backward mask)
4.  The spiral's arm passage across the word's screen position provides continuous masking

Implementation note: At 60 FPS, 1 frame = 16.67ms. Display timing is best handled at the frame level:

- Frame 0: Render word
- Frame 1: Render word (if shadows_display_ms > 16.67)
- Frame 2: Word removed, spiral at full opacity (mask onset)

#### Mode: "brief" (conscious but brief)

- shadows_display_ms = 200 (brief flash, consciously perceived)
- No masking needed
- For users who prefer to see the words

#### Mode: "supraliminal" (fully visible)

- shadows_display_ms = 2000 (held for 2 seconds)
- Standard fade-in/fade-out
- For users who want to read and consciously engage with affirmations

## 6.2 Shadows–Spiral Phase Alignment

The spiral's rotating arms create natural periodic masking. Optimal Shadows timing synchronizes word display with the arm **gap** (the space between arms where the word is most visible) for maximum subliminal impact:

def get_next_shadows_window(rotation_angle, num_arms, arm_width_angle): """Returns True when the word position is in a gap between arms.""" arm_period = 2 \* π / num_arms angle_in_period = rotation_angle % arm_period gap_start = arm_width_angle / 2 gap_end = arm_period - arm_width_angle / 2 return gap_start < angle_in_period < gap_end

When semantic_selector requests a Shadows display:

1.  Wait for get_next_shadows_window() == True
2.  Display word for shadows_display_ms
3.  The next arm passage acts as the backward mask
4.  The arm's sweep across the word position creates a natural, smooth mask that is less disruptive than an artificial rectangular mask

**Config keys:** "shadows_display_ms", "shadows_mask_isi_ms", "shadows_display_mode" — all patchable.

# 7\. Integration Matrix

Summary showing which existing module each technique modifies, what new config keys are added, and what dependencies exist:

| **Technique** | **Module** | **New Config Keys** | **Depends On** |
| --- | --- | --- | --- |
| Golden spiral geometry | visual_display.py | spiral_geometry | —   |
| --- | --- | --- | --- |
| Fractal edge modulation | visual_display.py | fractal_edge_enabled, fractal_edge_d, fractal_edge_amplitude, fractal_edge_octaves, fractal_edge_seed, fractal_edge_drift_rate | —   |
| --- | --- | --- | --- |
| IAF-matched rotation | visual_display.py | rotation_iaf_lock, rotation_iaf_divisor, rotation_iaf_multiplier | eeg_engine (IAF) |
| --- | --- | --- | --- |
| Motion aftereffect | visual_display.py | aftereffect_enabled, aftereffect_cycle_s, aftereffect_pause_s, aftereffect_ramp_s, aftereffect_gate | delivery_gate |
| --- | --- | --- | --- |
| Dual entrainment mode | audio_engine.py | entrainment_mode, isochronic_duty_cycle, binaural_blend | —   |
| --- | --- | --- | --- |
| IAF-personalized beats | audio_engine.py | beat_freq_source, beat_freq_fixed, beat_freq_target | eeg_engine (IAF) |
| --- | --- | --- | --- |
| AM depth profiling | audio_engine.py | am_depth, am_depth_profile | conductor (phase) |
| --- | --- | --- | --- |
| Dynamic spectral tilt | audio_engine.py | noise_spectral_tilt, noise_tilt_track_brain | eeg_engine (spectral_slope) |
| --- | --- | --- | --- |
| Trace conditioning | semantic_selector.py, delivery_gate.py | trace_conditioning_enabled, trace_interval_base_s, trace_interval_range_s, trace_interval_variability | Doc 43 conditioning_history |
| --- | --- | --- | --- |
| Compound CS | crossmodal_gain.py, cue_manager.py, visual_display.py, audio_engine.py | compound_cs_enabled, COMPOUND_CS_REGISTRY | Doc 36 pools, Doc 43 |
| --- | --- | --- | --- |
| Spaced repetition | semantic_selector.py | pool_spacing_min_s, pool_spacing_max_s | Doc 36, Doc 43 |
| --- | --- | --- | --- |
| VR optimization | delivery_gate.py | vr_ratio_acquisition, vr_ratio_maintenance, vr_transition_session | Doc 43 |
| --- | --- | --- | --- |
| Temporal binding | crossmodal_gain.py | binding_window_ms, audio_lead_ms | —   |
| --- | --- | --- | --- |
| SR visual floor | visual_display.py, crossmodal_gain.py | (routes existing SR to fractal_edge_amplitude) | Doc 37 |
| --- | --- | --- | --- |
| Subliminal timing | visual_display.py | shadows_display_ms, shadows_mask_isi_ms, shadows_display_mode | —   |
| --- | --- | --- | --- |
| Spiral-phase alignment | visual_display.py | (internal timing logic, no new keys) | —   |
| --- | --- | --- | --- |

# 8\. Default Configuration Block

Complete default configuration for all new parameters, ready to merge into config.yaml:

\# ============================================================ # Doc 44 — Stimulus Techniques & Optimization # ============================================================ # §2 Visual Geometry spiral_geometry: "golden" fractal_edge_enabled: true fractal_edge_d: 1.3 fractal_edge_amplitude: 0.15 fractal_edge_octaves: 5 fractal_edge_seed: 0 fractal_edge_drift_rate: 0.02 rotation_iaf_lock: true rotation_iaf_divisor: 0 rotation_iaf_multiplier: 1.0 aftereffect_enabled: true aftereffect_cycle_s: 35.0 aftereffect_pause_s: 2.0 aftereffect_ramp_s: 1.5 aftereffect_gate: true # §3 Audio Structure entrainment_mode: "dual" isochronic_duty_cycle: 0.5 binaural_blend: 0.3 beat_freq_source: "conductor" beat_freq_fixed: 10.0 beat_freq_target: 10.0 am_depth: 0.8 am_depth_profile: CALIBRATION: 0.0 INDUCTION: 0.9 DEEPENING: 0.7 MAINTENANCE: 0.5 FRACTIONATION_LIFT: 0.8 FRACTIONATION_DROP: 0.6 SLEEP_APPROACH: 0.3 SLEEP_ONSET: 0.2 SLEEP_MAINTAIN: 0.15 SLEEP_TRAINING: 0.25 noise_spectral_tilt: 1.0 noise_tilt_track_brain: false # §4 Conditioning Delivery trace_conditioning_enabled: true trace_interval_base_s: 1.5 trace_interval_range_s: \[0.8, 3.5\] trace_interval_variability: 0.3 compound_cs_enabled: true pool_spacing_min_s: 360.0 pool_spacing_max_s: 900.0 vr_ratio_acquisition: 3 vr_ratio_maintenance: 5 vr_transition_session: 10 # §5 Crossmodal Timing binding_window_ms: 200 audio_lead_ms: 50 # §6 Subliminal Presentation shadows_display_ms: 33 shadows_mask_isi_ms: 17 shadows_display_mode: "masked"

# 9\. Implementation Priority

Vesper should implement these techniques in the following order, as each layer builds on the previous:

| **Priority** | **Technique** | **Section** | **Rationale** |
| --- | --- | --- | --- |
| 1   | Visual geometry (golden spiral + fractal edges) | §2.1–2.2 | Self-contained visual_display changes, no dependencies |
| --- | --- | --- | --- |
| 2   | IAF coupling (rotation rate + beat frequency) | §2.3 + §3.2 | Establishes personalization backbone via eeg_engine |
| --- | --- | --- | --- |
| 3   | Dual entrainment mode | §3.1 | Self-contained audio_engine change |
| --- | --- | --- | --- |
| 4   | AM depth profiling | §3.3 | Requires conductor integration |
| --- | --- | --- | --- |
| 5   | Subliminal timing | §6  | Self-contained visual_display change |
| --- | --- | --- | --- |
| 6   | Trace conditioning | §4.1 | Requires semantic_selector and delivery_gate changes |
| --- | --- | --- | --- |
| 7   | Compound CS + temporal binding | §4.2 + §5.1 | Most complex integration: crossmodal_gain, cue_manager, binding |
| --- | --- | --- | --- |
| 8   | Motion aftereffect | §2.4 | Requires DeliveryGate integration |
| --- | --- | --- | --- |
| 9   | Spaced repetition | §4.3 | Requires conditioning_history from Doc 43 |
| --- | --- | --- | --- |
| 10  | VR optimization | §4.4 | Requires conditioning_history from Doc 43 |
| --- | --- | --- | --- |
| 11  | Dynamic spectral tilt | §3.4 | Requires eeg_engine spectral_slope output |
| --- | --- | --- | --- |
| 12  | SR visual floor | §5.2 | Routes existing Doc 37 SR output to fractal edges |
| --- | --- | --- | --- |

# 10\. Research Citations

| **Citation** | **Relevance** |
| --- | --- |
| Hagerhall et al. — Fractal dimension D≈1.3 and frontal alpha EEG (referenced in Myndlift review) | §2.2 Fractal edge target dimension |
| --- | --- |
| Hübner & Goodarzi, 2025 (_Scientific Reports_) — Individual spiral type preferences | §2.1 Golden spiral mode justification |
| --- | --- |
| Salera et al., 2024 (_Symmetry_/MDPI) — Implicit association: golden ratio + positive categories | §2.1 Golden spiral implicit preference |
| --- | --- |
| Gulbinaite et al., 2017 (_Journal of Neuroscience_) — IAF predicts 10 Hz flicker entrainment | §2.3 IAF-matched rotation |
| --- | --- |
| Wu et al., 2020 (_Neuron_) — Pretectal circuit in motion aftereffect | §2.4 Motion aftereffect mechanism |
| --- | --- |
| Battù et al., 2025 (_Bioengineering_/MDPI) — Personalized IAF binaural beats, >81% accuracy | §3.2 IAF-personalized beat frequency |
| --- | --- |
| Cidral-Filho et al., 2024 (_Applied Psychophysiology and Biofeedback_) — Brainwave entrainment review | §3.3 AM depth as key entrainment parameter |
| --- | --- |
| Finke et al., 2025 (_Scientific Reports_) — Trace vs delay conditioning extinction | §4.1 Trace conditioning intervals |
| --- | --- |
| Knight et al., 2004 (_Journal of Neuroscience_) — Trace conditioning recruits hippocampus + cortex | §4.1 Neural basis of trace conditioning |
| --- | --- |
| Pearce, 1987 — Configural theory of conditioning | §4.2 Compound CS design |
| --- | --- |
| Ebbinghaus, 1885 — Spacing effect (_d_ = 0.69, 586 studies, 167,763 participants) | §4.3 Spaced repetition scheduling |
| --- | --- |
| Francis et al., 2004 (_Spatial Vision_) — ISI law for backward masking | §6.1 Subliminal display timing |
| --- | --- |
| Günaydın et al., 2026 (_Scientific Reports_) — Crossmodal postdiction, 200–300ms TBW | §5.1 Temporal binding window |
| --- | --- |
| Tong et al., 2020 (_Attention, Perception & Psychophysics_) — Audiovisual spatial integration | §5.1 Audio-leading binding advantage |
| --- | --- |
| Herbert et al., 2003 (_Behavioral Neuroscience_) — Optimal ISI for eyeblink conditioning | §4.1 Trace interval calibration reference |
| --- | --- |

_End of Document — Somna Doc 44 — Stimulus Techniques & Optimization_