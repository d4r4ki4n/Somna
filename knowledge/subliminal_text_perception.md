Somna Bible Ch.8 Â§Visual-Layers — Subliminal Text and Image Perception Reference
Perception thresholds, masking dynamics, contrast science, and per-layer optimization for Somna's affirmation system
Author: Research (external collaborator)   |   Date: 30 March 2026   |   Series: Somna Research Documentation
1   Executive Summary
This document audits Somna's three text affirmation layers — CenterText, Shadows, and Veil — against the subliminal perception literature. It provides evidence-based recommendations for flash duration, opacity/contrast, and spatial placement; covers subliminal image perception science; and specifies new live_control.json keys for agent-driven adaptive subliminal tuning.
Key Finding: Somna's layer architecture maps cleanly onto a three-tier perceptual model — supraliminal (CenterText), subliminal (Shadows), and liminal (Veil). The current defaults are well-chosen, but specific adjustments to shadow opacity and the addition of agent-controllable parameters will tighten the subliminal layer's operation against the science.
2   Perceptual Threshold Science
2.1   The Conscious Access Threshold (~50 ms SOA)
Based on Del Cul, Baillet & Dehaene (2007, PLOS Biology): When a flashed stimulus is followed by a backward mask, subjects fail to perceive it unless the target-mask stimulus onset asynchrony (SOA) exceeds approximately 50 ms. This threshold corresponds to the time needed to establish sustained activity in recurrent cortical loops.
Key findings:
Below 50 ms SOA: considerable subliminal processing occurs in the feedforward sweep through the occipito-temporal pathway (<250 ms post-stimulus)
Above 50 ms SOA: late (>270 ms) fronto-parieto-temporal activation enables conscious reportability
The threshold is nonlinear — not a gradual fade but a sharp transition (sigmoid-shaped psychometric function)
This 50 ms boundary is the single most important number for Somna's subliminal layer design
2.2   Objective vs. Subjective Threshold
Based on Cheesman & Merikle (1984/1986):
Objective threshold: forced-choice detection at chance level (true subliminal — the stimulus literally cannot be detected even when trying)
Subjective threshold: observer reports "no stimulus" but forced-choice performance is above chance (stimulus influences behavior but is not consciously reported)
Somna's Shadows layer should operate at or near the objective threshold for maximum subliminal effect
The Veil layer operates between subjective threshold and full awareness — the "liminal" zone
2.3   Individual Variation
The Subliminal Threshold Estimation Procedure (STEP) by Elbaz, Yaron & Mudrik (2025, Behavior Research Methods) demonstrates that subliminal thresholds vary significantly between individuals. Implication for Somna: fixed parameters will be subliminal for some users and supraliminal for others. Agent-adaptive calibration is the correct long-term architecture.
2.4   Temporal Perception is Rhythmic
Johannknecht, Schnitzler & Lange (2025, Nature Scientific Reports): Subliminal visual stimulation produces behavioral oscillations at theta, alpha, and beta frequencies. Alpha oscillations (~10 Hz) are a functional rhythm for visual perception. Perception fluctuates as a function of delay between subliminal stimulus and target. Implication: timing subliminal flashes relative to beat phase and EEG alpha phase could optimize subliminal absorption. The beat_pulse modulation already present in VeilLayer partially captures this.
3   Masking Dynamics — The Spiral as Ally
3.1   Pattern Masking vs. Noise Masking
Based on Marcel (1983):
Pattern masking (structured visual content surrounding the target): full semantic priming PRESERVED — 62 ms to 56 ms facilitation, even when the stimulus is subliminal
Noise masking (random noise surrounding the target): semantic priming ELIMINATED (+4 ms, not significant)
Critical implication: Somna's animated spiral overlay functions as a structured pattern mask, NOT a noise mask. This means the spiral actively ENHANCES semantic processing of subliminal text rather than degrading it.
3.2   Forward vs. Backward Masking
Based on Scharf & Lefton (1970) and the visual masking literature:
Forward masking (mask precedes target): degrades the visual input signal
Backward masking (mask follows target): degrades visual input AND disrupts poststimulatory processing — more effective at suppressing conscious access
Backward masking effect ceases when the inter-stimulus interval exceeds ~80 ms
In Somna's context: the spiral is a continuous simultaneous mask — it both forward-masks and backward-masks each text flash. The continuous nature means there is no ISI, maximizing masking effectiveness for the subliminal layer.
3.3   The Masking Advantage for Somna
The spiral overlay creates ideal conditions for subliminal text delivery:
Structured pattern masking preserves semantic processing (Marcel 1983)
Continuous simultaneous masking suppresses conscious detection
The spiral's luminance modulation (beat_phase breathing) creates rhythmic windows where masking strength varies — potentially allowing brief moments of stronger subliminal penetration at specific beat phases
FBO trail decay (Bible Ch.8 Â§Subliminal) adds temporal persistence that further enriches the masking texture
4   Contrast and Opacity Science
4.1   Detection Thresholds
Weber fraction for cones: ~0.14 (14% luminance contrast change needed for 50% detection probability under optimal conditions)
Weber fraction for rods: ~0.015–0.03 (1.5–3% — far more sensitive, relevant for dark-adapted viewing)
Human contrast sensitivity peaks at ~4 cycles per degree spatial frequency, dropping at both higher and lower frequencies (Campbell & Robson 1968)
For subliminal text: the goal is to be ABOVE neural registration threshold but BELOW conscious detection threshold
4.2   Somna Shadow Layer: Current State
Current defaults:
shadow_opacity = 25
Converted: int(25 × 2.55) = 64 → alpha 64/255 ≈ 25.1% of maximum
Against a dark spiral background (typical luminance ~10–30 cd/m²), this produces a Weber contrast of roughly 0.25 — above the cone Weber fraction of 0.14
Assessment: The current shadow opacity is slightly above the optimal subliminal range. Users with good contrast sensitivity may consciously detect shadow text, especially during moments of low spiral complexity.
4.3   Recommended Opacity Ranges
Layer
Current Opacity
Current Alpha
Recommended Range
Rationale
Shadows
25
64/255 (25%)
8–18
Below cone Weber fraction against typical spiral backgrounds. 12 recommended as default.
Veil
45
115/255 (45%)
30–55
Liminal zone — should be noticeable as texture but individual phrases not readable. Current 45 is well-placed.
CenterText
N/A (color-driven)
Full (via text_color alpha)
No change
Supraliminal by design — must be consciously readable.
4.4   Dynamic Contrast Adaptation
The agent should modulate shadow opacity based on:
Spiral style complexity: dense styles → lower opacity still registers; sparse styles → opacity may need to increase slightly to maintain neural registration
Beat frequency: higher frequencies → shorter flash cycles → lower opacity compensated by repetition rate
Time in session: as trance deepens and critical faculty reduces, opacity can be gently lowered
SQI data (Bible Ch.2 Â§SQI): if available, correlate EEG alpha power changes with opacity adjustments
5   Spatial Placement — Peripheral vs. Central
5.1   Foveal vs. Peripheral Processing
Based on Zhang, Zhou & Wang (2024, Nature Communications Biology):
Foveal and peripheral vision engage distinct neural mechanisms and circuits
Foveal units show more extensively modulated spike-LFP coherence
Peripheral receptive fields are larger (Gattass et al. 2005)
Cortical magnification: far more cortex devoted to fovea than periphery
5.2   Parafoveal Processing
Based on Pan, Frisson & Jensen (2021, Nature Communications):
Parafoveal region: 2–5° from fixation point
Words are processed at the lexical level in the parafovea during reading
60 Hz subliminal tagging showed stronger responses for low-frequency (less common) words — the brain works harder on unfamiliar content
Parafoveal preview primes subsequent foveal processing (Schotter, Angele & Rayner 2012)
5.3   Implications for Somna's Layers
Layer
Spatial Strategy
Perceptual Basis
Assessment
CenterText
Center of screen (foveal)
Supraliminal text requires foveal acuity for reading
CORRECT — foveal placement for conscious reading
Shadows
Grid-spread avoiding center (22% exclusion zone), peripheral
Peripheral vision has lower spatial resolution → text harder to consciously read but semantic content still processed via ventral pathway
CORRECT — peripheral placement is the optimal subliminal strategy
Veil (scroll / rain / drift / tunnel)
Full-screen coverage, including foveal
Creates texture that is noticed but individual phrases are not tracked — the motion and density prevent reading
CORRECT — overwhelming density replaces spatial hiding with attentional hiding
Veil (converge)
Edges-to-center flow
Phrases enter periphery (subliminal) and approach center (increasingly liminal) — natural subliminal-to-liminal gradient
CORRECT and particularly well-designed for subliminal absorption
Veil (strobe)
Center, large font
Supraliminal (uses center_flash timing) — functions like a second CenterText channel
CORRECT for its purpose
5.4   Shadow Placement Refinement
The current 22% center exclusion zone is good but could be refined:
Optimal subliminal eccentricity: 5–15° from fixation (well into peripheral vision)
On a 1080p display at typical viewing distance (~60 cm), 5° ≈ 290 px from center
Current exclusion zone at 22% of screen dimensions ≈ 237 px — slightly tight
Recommendation: increase exclusion zone to 27% for more consistent peripheral placement
The drift velocity (±0.35 horizontal, ±0.25 vertical) should remain within the peripheral zone — current edge-wrapping at ±300 px horizontal ensures this
6   Per-Layer Audit and Recommendations
6.1   CenterText Layer — Supraliminal Affirmation
Current Parameters
Flash ON: 120 ms default (beat-synced: cycle_ms × duty × (1±jitter))
Flash OFF: 80 ms default
Duty cycle: 0.38, variance: 0.22
Font: 140 px, 30% switch probability per cycle
Perceptual Assessment
120 ms is well above the 50 ms conscious access threshold — correctly supraliminal
At theta beat frequency (4 Hz): cycle_ms = 250 ms → ON ≈ 95 ms — still supraliminal
At alpha frequency (10 Hz): cycle_ms = 100 ms → ON ≈ 38 ms — approaches subliminal threshold
The TTS voice-lock mode (holding phrase visible during audio) is pure supraliminal delivery
Recommendations
Add a floor clamp: if beat-synced ON time drops below 60 ms, clamp to 60 ms to maintain supraliminal character
The current system is well-designed; no major changes needed
Consider adding a config key for the agent to temporarily boost ON time during key affirmation moments
6.2   Shadows Layer — True Subliminal
Current Parameters
Flash ON: 40 ms default
Flash OFF: 180 ms default
Opacity: 25 (→ alpha 64/255)
Count: 6 positions
Font: 88 px base at 1080p, scaling linearly
Placement: grid-spread with 22% center exclusion
Perceptual Assessment
40 ms ON is below the 50 ms conscious access threshold — correctly subliminal
180 ms OFF provides sufficient temporal separation to prevent temporal integration with subsequent flashes
Duty cycle: 40/(40+180) = 18.2% — low duty is correct for subliminal (brief exposure, long recovery)
At 25% alpha, the text is likely above the objective threshold for some users — needs reduction
Peripheral placement with center exclusion is scientifically supported
Per-position independent phrases maximize semantic coverage — correct
The ON→OFF transition creates a backward-masking effect as the spiral reasserts — beneficial
Recommendations
Lower default opacity to 12 (alpha ≈ 31/255 ≈ 12.2%) — comfortably below cone Weber fraction
Add agent-controllable opacity range: 5–25 (mapping to alpha 13–64)
Consider adding a shadow_flash_phase_offset parameter: offset shadow flashes relative to beat phase. Research (Johannknecht 2025) suggests specific beat phases may have higher subliminal penetration
Keep 40 ms ON as default but allow agent range: 16–50 ms
Lower bound 16 ms ≈ 1 frame at 60 fps — minimum renderable duration
Increase center exclusion from 22% to 27%
Add live_control.json key for agent to control shadow count (4–10 range)
6.3   Veil Layer — Liminal Field
Current Parameters
Opacity: 45 (base)
Density: 1.3
Mode rotation: 30–90 seconds, random selection from scroll / rain / drift / converge / tunnel
Beat pulse modulation on all modes
Strobe / mirror only on explicit request
Perceptual Assessment
At opacity 45 (alpha ≈ 115/255 ≈ 45%), text is clearly above the conscious detection threshold
However, the MOTION and DENSITY prevent conscious reading of individual phrases — this is "attentional masking" rather than sensory-level subliminal
Each mode creates a different perceptual experience:
Scroll: wall of text — overwhelming density, no single phrase trackable
Rain: vertical motion draws eye tracking, phrases at periphery of tracking are subliminal
Drift: floating phrases fade in/out — the fade cycle creates brief subliminal moments at low alpha
Converge: edge-to-center flow — natural subliminal (edge) to liminal (mid) gradient
Tunnel: center-to-edge expansion — brief subliminal moment at birth (tiny size), grows to liminal
Strobe: supraliminal — intentional readable flash
The beat_pulse modulation creates rhythmic salience oscillation — aligns with Johannknecht finding
Recommendations
Current design is strong — veil operates correctly in the liminal zone
Add agent-controllable mode forcing (already partially supported via config["veil_mode"])
Consider a "veil_reading_difficulty" metric: density × speed / font_size — agent can target specific difficulty zones
Drift mode's fade cycle should have configurable min alpha: if fade_min_alpha is set very low (e.g., 5), phrases spend more time in the truly subliminal zone during fade-in
7   Subliminal Image Perception
7.1   Can Images Be Processed Subliminally?
Yes — robust evidence:
Affective priming with pictures (Hermans, Spruyt, De Houwer & Eelen, 2003): Subliminal picture primes (sandwich-masked, below conscious detection) significantly affected evaluative categorization of subsequent targets. Works with both picture-to-picture and picture-to-word priming.
Emotional valence transfer (Huang, Rana & Vaina, Boston University): Subliminally presented images with emotional content (aggressive, pleasant, neutral) impacted conscious perception of subsequent face expressions. Images containing faces were more effective than images without faces.
Amygdala involvement (Sato et al. 2024, Nature Scientific Reports): Patients with unilateral medial temporal lobe resection (including amygdala) showed impaired subliminal affective priming. The amygdala is causally involved in unconscious emotional processing. Fearful and happy dynamic facial expressions presented for 30 ms served as effective subliminal primes.
Visual (not semantic) priming (Bar & Biederman): Subliminal picture priming is entirely visual — same-name but different-shape objects showed NO priming. The locus is at an intermediate stage in the ventral cortical pathway. Priming persisted for at least 15 minutes.
Mere exposure effect (Zajonc & Kunst-Wilson): 1 ms exposure to stimuli → preference increase without recognition. Subliminal familiarity breeds liking.
7.2   Implications for Somna
Somna currently uses TEXT-only subliminal delivery. The research supports potential future expansion to:
Subliminal symbolic images: Simple shapes, sigils, or icons flashed at shadow-layer timing could prime emotional states or identity associations
Affirmation-congruent imagery: Brief flashes of imagery matching the affirmation theme (warmth, strength, calm) could reinforce the text pathway through a parallel visual channel
Face priming: Brief subliminal presentation of positive facial expressions could prime emotional state — the amygdala pathway processes these below conscious awareness
Architecture note: Image subliminal delivery would require a new layer or an extension to ShadowsLayer — the current text rendering pipeline (PhrasePool → FontManager → surface cache) does not handle image assets. This is a future feature, not a current recommendation.
8   The Three-Tier Perception Model
Somna's text layer architecture maps onto a clean perceptual hierarchy:
Tier
Layer
Duration
Opacity
Placement
Perceptual Mode
Processing Pathway
Supraliminal
CenterText
120 ms (beat-synced)
Full
Foveal (center)
Conscious reading, deliberate cognitive engagement
Feedforward + recurrent loops → conscious reportability
Liminal
Veil
Continuous (mode-dependent)
45 (30–55 range)
Full-screen
Noticed as texture, individual phrases not consciously tracked
Partial recurrent activation, attentional masking prevents full conscious access
Subliminal
Shadows
40 ms
12 (recommended; was 25)
Peripheral (>27% exclusion)
Below conscious detection, semantic content processed via feedforward sweep
Feedforward only → subliminal priming, affect modulation, mere exposure
This three-tier model is not just a design convenience — it maps directly onto the neuroscience of conscious access:
Feedforward sweep (0–150 ms): All three layers reach this stage. Subliminal processing occurs here.
Recurrent processing (150–300 ms): Only stimuli above the ~50 ms SOA threshold establish recurrent loops. CenterText always reaches this; Veil partially reaches it; Shadows should NOT reach it.
Global workspace (>300 ms): Full conscious access. Only CenterText consistently reaches this stage. Veil intermittently approaches it. Shadows never.
9   New live_control.json Keys
Key
Type
Range
Default
Description
shadow_opacity_target
int
5–25
12
Agent-controlled shadow opacity (replaces static config default of 25)
shadow_flash_on_ms
int
16–50
40
Shadow flash ON duration in milliseconds
shadow_flash_off_ms
int
100–500
180
Shadow flash OFF duration in milliseconds
shadow_count_target
int
4–10
6
Number of simultaneous shadow positions
shadow_phase_offset
float
0.0–1.0
0.0
Offset shadow flash timing relative to beat phase (0.0 = flash at beat onset, 0.5 = flash at beat midpoint)
shadow_exclusion_pct
float
0.15–0.40
0.27
Center exclusion zone as fraction of screen dimensions
veil_opacity_target
int
20–70
45
Agent-controlled veil base opacity
veil_mode_force
string
null or mode name
null
Force specific veil mode (null = random rotation)
veil_density_target
float
0.5–3.0
1.3
Agent-controlled veil density multiplier
center_flash_on_floor_ms
int
40–120
60
Minimum ON time for center text when beat-synced (prevents accidental subliminal operation)
subliminal_intensity
float
0.0–1.0
0.5
Master subliminal intensity dial — agent uses this as a single control to coordinate shadow opacity, count, and timing. 0.0 = minimal subliminal presence, 1.0 = maximum within safe subliminal range.
10   Agent Protocol — Adaptive Subliminal Tuning
10.1   Session Start Protocol
# Agent initialization — set subliminal parameters for session
def _init_subliminal_layer(session_config: dict) -> None:
    """Set initial subliminal parameters based on session intent."""
    intensity = session_config.get("subliminal_intensity", 0.5)

    # Map intensity to parameter space
    opacity = int(5 + intensity * 20)      # 5-25 range
    count = int(4 + intensity * 6)          # 4-10 range
    on_ms = int(50 - intensity * 34)        # 50-16 range (higher intensity = shorter flash)

    _patch_live({
        "shadow_opacity_target": opacity,
        "shadow_count_target": count,
        "shadow_flash_on_ms": on_ms,
        "shadow_flash_off_ms": 180,
        "shadow_exclusion_pct": 0.27,
        "center_flash_on_floor_ms": 60,
    })
10.2   Mid-Session Adaptation
def _adapt_subliminal(trance_score: float, sqi_mean: float) -> None:
    """Adjust subliminal parameters based on trance depth and signal quality.

    As trance deepens (trance_score rises), the critical faculty reduces,
    allowing slightly bolder subliminal delivery without breaking threshold.
    If EEG signal quality is poor (sqi_mean < 0.5), hold parameters steady.
    """
    if sqi_mean < 0.3:
        return  # Unreliable EEG — don't adapt

    # Trance-scaled opacity: deeper trance → can push opacity slightly higher
    # while remaining subliminal (reduced conscious monitoring)
    base_opacity = 12
    trance_bonus = int(trance_score * 8)  # 0-8 additional opacity points
    target_opacity = min(25, base_opacity + trance_bonus)

    # Trance-scaled count: more shadow positions as depth increases
    base_count = 5
    count_bonus = int(trance_score * 3)  # 0-3 additional positions
    target_count = min(10, base_count + count_bonus)

    _patch_live({
        "shadow_opacity_target": target_opacity,
        "shadow_count_target": target_count,
    })
10.3   Beat Phase Synchronization
def _sync_shadow_to_alpha(iaf: float, beat_freq: float) -> None:
    """Align shadow flash timing with individual alpha frequency (IAF).

    Research (Johannknecht 2025) shows subliminal perception oscillates
    with alpha rhythm. Timing shadow flashes to coincide with alpha
    troughs (low alertness moments) may enhance subliminal penetration.

    The phase_offset parameter shifts shadow flashes relative to beat phase.
    Optimal offset depends on the ratio of beat frequency to IAF.
    """
    if iaf <= 0 or beat_freq <= 0:
        return

    # Target the alpha trough — approximately 180° offset from alpha peak
    # In beat-phase terms: offset by half an alpha cycle relative to beat
    alpha_period_ms = 1000.0 / iaf
    beat_period_ms = 1000.0 / beat_freq

    # Phase offset as fraction of beat cycle
    offset = (alpha_period_ms / 2.0) / beat_period_ms
    offset = offset % 1.0  # Wrap to 0-1

    _patch_live({
        "shadow_phase_offset": round(offset, 3),
    })
10.4   Veil Mode Selection Strategy
The agent should select veil modes based on session phase:
Induction phase: converge or tunnel (center-directed flow enhances absorption focus)
Deepening phase: drift or rain (gentle, dissociative motion)
Maintenance phase: scroll (dense, steady, low-engagement background)
Emergence / fractionation: strobe (supraliminal flash to briefly sharpen awareness before re-deepening)
def _select_veil_mode(session_phase: str) -> None:
    """Force veil mode appropriate to session phase."""
    mode_map = {
        "induction": "converge",
        "deepening": "drift",
        "maintenance": "scroll",
        "fractionation_up": "strobe",
        "fractionation_down": "tunnel",
        "sleep_onset": "rain",
    }
    mode = mode_map.get(session_phase)
    if mode:
        _patch_live({"veil_mode_force": mode})
    else:
        _patch_live({"veil_mode_force": None})  # Resume random rotation
11   Stochastic Resonance Integration (Cross-Reference: Bible Ch.8 Â§Stochastic-Resonance)
Bible Ch.8 Â§Stochastic-Resonance covered stochastic resonance noise injection into the visual display via GLSL. The subliminal perception research strengthens that design:
Van der Groen & Wenderoth (2016): Adding optimal noise to subthreshold visual stimuli in V1 enhances detection — the inverted-U stochastic resonance curve
For Somna's shadows layer: the GLSL noise injection from Bible Ch.8 Â§Stochastic-Resonance acts as a detection-enhancing mechanism — but only if shadow opacity is BELOW the detection threshold. If opacity is too high (above threshold), noise makes the text MORE detectable (undesirable for subliminal layer).
Recommendation: when stochastic resonance is active (Bible Ch.8 Â§Stochastic-Resonance), REDUCE shadow opacity by 20–30% to compensate for the noise-enhanced detection. The agent should coordinate these two systems.
def _coordinate_sr_and_subliminal(sr_active: bool, sr_amplitude: float) -> None:
    """Reduce shadow opacity when stochastic resonance is enhancing detection."""
    if sr_active and sr_amplitude > 0.0:
        # SR enhances detection — compensate by lowering opacity
        compensation = 1.0 - (sr_amplitude * 0.3)  # 0-30% reduction
        base_opacity = 12
        adjusted = max(5, int(base_opacity * compensation))
        _patch_live({"shadow_opacity_target": adjusted})
12   Key Research Citations
Del Cul, A., Baillet, S., & Dehaene, S. (2007). Brain dynamics underlying the nonlinear threshold for access to consciousness. PLOS Biology, 5(10), e260.
Cheesman, J., & Merikle, P. M. (1984). Priming with and without awareness. Perception & Psychophysics, 36(4), 387–395.
Marcel, A. J. (1983). Conscious and unconscious perception: Experiments on visual masking and word recognition. Cognitive Psychology, 15(2), 197–237.
Johannknecht, M., Schnitzler, A., & Lange, J. (2025). Subliminal visual stimulation produces behavioral oscillations. Nature Scientific Reports.
Elbaz, E., Yaron, I., & Mudrik, L. (2025). The Subliminal Threshold Estimation Procedure (STEP). Behavior Research Methods, 58, 13.
Pan, Y., Frisson, S., & Jensen, O. (2021). Neural evidence for lexical parafoveal processing. Nature Communications, 12, 5234.
Zhang, Zhou & Wang (2024). Distinct foveal vs peripheral visual processing networks. Nature Communications Biology.
Hermans, D., Spruyt, A., De Houwer, J., & Eelen, P. (2003). Affective priming with subliminally presented pictures. Canadian Journal of Experimental Psychology, 57(2), 97–114.
Sato, W., et al. (2024). Impairment of unconscious emotional processing after unilateral medial temporal structure resection. Scientific Reports, 14, 4269.
Bar, M., & Biederman, I. (1998). Subliminal visual priming. Psychological Science.
Jacobs, C., & Sack, A. T. (2012). The neurobiology of subliminal priming. Brain Sciences, MDPI.
Zajonc, R. B. (1980). Feeling and thinking: Preferences need no inferences. American Psychologist, 35(2), 151–175.
Scharf, B., & Lefton, L. A. (1970). Backward and forward masking as a function of stimulus and task parameters. Journal of Experimental Psychology, 84(2), 331–338.
Campbell, F. W., & Robson, J. G. (1968). Application of Fourier analysis to the visibility of gratings. Journal of Physiology, 197(3), 551–566.
Schotter, E. R., Angele, B., & Rayner, K. (2012). Parafoveal processing in reading. Attention, Perception, & Psychophysics, 74, 5–35.
