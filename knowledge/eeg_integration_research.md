# Somna × EEG: A Research-Backed Ideas Report
## 10 High-Impact Features for Neurofeedback-Driven Entrainment
*March 2026 | Prepared for: Somna | Internal Development Reference*

> **Implementation status (as of March 2026):**
> - Idea 1 (Theta-Gated Affirmation Delivery) — **Implemented.** Agent uses `eeg_trance_score`, `eeg_faa_state`, and `eeg_confidence` to gate delivery.
> - Idea 2 (Trance Depth Scoring) — **Implemented.** `eeg_trance_score`, `eeg_sef95`, and `eeg_spectral_slope` are all live. Per-session effectiveness scoring in `session_scorer.py` / `somna.db`.
> - Idea 3 (40 Hz GENUS) — **Partially implemented.** Isochronic mode at 40 Hz works; rectangular pulse variant not yet implemented.
> - Idea 4 (AV Sync) — **Implemented.** `av_sync_enabled` + `beat_phase` key.
> - Idea 5 (αCLAS) — Future (Phase 3–4).
> - Idea 6 (Sleep TMR) — Future.
> - Idea 7 (EEG-Reactive Soundscapes) — Future.
> - Idea 8 (Pink Noise SR) — **Implemented.** `noise_color: "pink"` channel available; user calibrates level.
> - Ideas 9, 10 — Future.
> - **Additional implemented (beyond this list):** ASSR entrainment verification (Bible Ch.2 Â§ASSR), FAA receptivity gating (Bible Ch.2 Â§FAA), Adaptive Frequency Leading / Meet-and-Lead (Bible Ch.3 Â§Frequency-Leading), per-session effectiveness scoring and longitudinal auto-optimization (Bible Ch.5 Â§Scoring).


---

## Executive Summary

- Somna's architecture — real-time audio entrainment + GPU-rendered visuals + LLM agent + SSB subliminal delivery + file-based IPC bus — positions it to implement neurofeedback features that commercial devices sell as locked-down subscription products (Elemind: $349 + $7/month; Muse premium: $13/month; NeurOptimal: $6,000+). Somna can replicate and exceed their core capabilities with a $250 Muse 2 and free, open-source software.
- The `eeg_engine.py` → `live_control.json` pipeline design — 12 read-only EEG keys updated every 1 second — is the foundation. Every idea in this report reads from those keys. No new IPC mechanisms required.
- 10 ideas ranked by impact × feasibility. The top 3 — Theta-Gated Affirmation Delivery, Trance Depth Scoring, and 40 Hz GENUS Mode — are implementable within the existing Phase 0–4 dev plan with zero new hardware beyond the Muse 2 already planned.
- Ideas #1, #3, #4, and #8 require zero new code modules — they are agent logic + session templates + knowledge file updates layered on existing infrastructure.
- The combination of Idea #1 (theta-gated affirmations) + Idea #2 (trance depth scoring) creates a closed-loop hypnotic system that no consumer product offers: detect depth → gate affirmation delivery → verify deepening → adjust strategy → repeat.

---

## 1. The Landscape — Why Somna Is Uniquely Positioned

Most neurofeedback products are one-trick ponies. Muse does meditation scoring. Elemind does phase-locked alpha suppression for sleep. NeurOptimal does passive EEG-triggered audio interrupts. None combine audio entrainment + visual entrainment + subliminal delivery + an LLM agent making real-time decisions + EEG sensing in a single, hackable, extensible system.

Five structural advantages:

1. **`live_control.json` as universal IPC bus.** Any new sensor data — EEG bands, trance depth, heart rate — becomes instantly available to every component by writing a key. The 100ms stat-gated poll means components react within a single tick.
2. **`somna_agent.py` as decision engine.** The LLM agent reads system state every tick and makes decisions. Unlike hardcoded rule systems, the agent can reason about combinations of signals, session context, user history, and strategic goals. Update `knowledge/eeg_entrainment.md` and the agent's behavior changes — no code deployment.
3. **`tts_engine.py` with SSB subliminal delivery.** The per-prompt `voice_mode` control (tts/subliminal/both/silent) means the agent can switch affirmation delivery modality in real time based on EEG state.
4. **GPU-rendered visual display at high FPS.** The ModernGL pipeline already runs with multiple modifiable layers. Adding brightness modulation at a target frequency is a uniform float in a shader.
5. **`knowledge/` directory as strategy layer.** The agent's entrainment strategy, EEG interpretation rules, and session protocols live in Markdown files injected into the system prompt. Change the strategy, change the behavior. No recompilation.

---

## 2. The Ideas — Ranked by Impact × Feasibility

### Idea 1: Theta-Gated Affirmation Delivery
**IMPACT: ★★★★★ / FEASIBILITY: ★★★★★**

When `eeg_engine.py` detects theta dominance — `eeg_theta` crosses threshold, `eeg_alpha_theta_ratio` shifts toward theta — the agent increases subliminal affirmation delivery rate, switches TTS to subliminal SSB mode, and delivers high-priority affirmations during peak suggestibility windows.

**The Science:** Gordon et al. (2026, Nature Scientific Reports) demonstrated that theta-frequency (4 Hz) rhythmic stimulation selectively induces altered states of consciousness in 40 participants. Neural tracking at theta predicted stronger ASC intensity. De Benedittis (2025, Brain Sciences) confirmed: hypnotic states show increased alpha and theta power alongside reduced beta and gamma (critical thinking suppression). Theta state = reduced critical faculty = enhanced suggestibility.

**Somna Integration:**
- `somna_agent.py`: Read `eeg_theta` and `eeg_alpha_theta_ratio`; when theta dominance detected, adjust `voice_mode` to "subliminal" or "both", increase affirmation cadence. **Complexity: Low.**
- `knowledge/eeg_entrainment.md`: Add theta-gating strategy instructions. **Complexity: Low.**
- No changes to `tts_engine.py` or `live_control.json` — already supports per-prompt `voice_mode`.

**Effort:** 1 weekend. Phase 3 alignment. This is Somna's core value proposition made neurologically precise. Implement this first.

---

### Idea 2: Real-Time Trance Depth Scoring
**IMPACT: ★★★★★ / FEASIBILITY: ★★★★☆**

A derived `eeg_trance_depth` key (0.0–1.0) computed from band ratios and written to `live_control.json`. The agent uses it as the primary depth signal for all session decisions. Personalizable calibration baselines stored in `user_profile.json` across sessions — EEG correlates of depth are stable within individuals but vary between them.

**The Science:** Obukhov et al. (2023, BMC Research Notes) built a passive BCI for real-time hypnotic depth estimation using 27 EEG recordings from 8 outpatients. The 4–15 Hz band achieved 82% accuracy for classifying deep hypnosis probability. Critical finding: EEG correlates were stable within each patient but varied between patients — individualized calibration is not optional, it's mandatory. Farahzadi et al. (2024, Nature Scientific Reports) identified that reduced gamma power plus increased beta power envelope correlation between interhemispheric Dorsal Attention Networks predict hypnotic depth. Open-source precedent: "ThetaGate" on GitHub implements EEG-powered hypnosis with trance depth detection using Muse/OpenBCI.

**Somna Integration:**
- `eeg_engine.py`: Compute `eeg_trance_depth` from weighted band ratios (primarily 4–15 Hz power, gamma suppression indicator, frontal asymmetry). **Complexity: Medium.**
- `somna_agent.py`: Read `eeg_trance_depth` as primary depth signal. **Complexity: Low.**
- `user_profile.json`: Store per-user calibration baselines: resting band ratios, personal depth thresholds, session-over-session trends.

**Effort:** 1–2 weekends. Phase 3 alignment. This is the backbone metric that makes every other idea more powerful.

---

### Idea 3: 40 Hz Gamma GENUS Brain Health Mode
**IMPACT: ★★★★★ / FEASIBILITY: ★★★★★**

A dedicated "Brain Health" session mode delivering synchronized 40 Hz audio-visual stimulation — spiral layer pulsing at 40 Hz + isochronic tone at 40 Hz. Based on MIT's decade of GENUS (Gamma ENtrainment Using Sensory Stimuli) research. Protocol: 1 hour/day.

**The Science:** Park & Tsai (2025, PLOS Biology) reviewed a decade of studies demonstrating that 40 Hz stimulation reduces Alzheimer's pathology (amyloid plaques, tau tangles), prevents neuron death, and sustains memory and cognition in mouse models. In humans, Phase II clinical trials showed significant slowing of brain atrophy. The mechanism: 40 Hz AV stimulation induces interneurons to increase VIP peptide release, prompting increased amyloid clearance via the glymphatic system (Bhatt et al., Nature 2024). Mlinarič et al. (2025, Communications Biology) provided first intracranial EEG evidence in humans: 40 Hz visual stimulation entrains neural activity beyond early visual areas into the hippocampus and frontal/temporal lobes. **Critical finding: cognitive engagement during stimulation enhanced both strength and spatial extent of entrainment** — the agent's prompts could boost efficacy.

**Somna Integration:**
- `audio_engine.py`: Isochronic mode at 40 Hz (already being implemented). **Complexity: None (reuses isochronic mode).**
- `visual_display.py`: Spiral layer opacity/brightness modulated at 40 Hz via ModernGL shader uniform. **Complexity: Low.**
- YAML session template `genus_40hz` with 60-minute duration, fixed 40 Hz target. **Complexity: Low.**

**Effort:** 1 weekend. Phase 1 alignment (no EEG needed for basic mode). Transforms Somna from a hypnosis tool into a daily brain health platform.

---

### Idea 4: Cross-Modal Audio-Visual Entrainment Sync
**IMPACT: ★★★★☆ / FEASIBILITY: ★★★★★**

Synchronize visual display layers — spiral brightness, veil opacity, shadow intensity — with the audio entrainment frequency so they pulse together at the target beat frequency. Combined AV stimulation is significantly more powerful than either modality alone.

**The Science:** Blanpain et al. (2024, Nature Communications) demonstrated with intracranial EEG that multisensory (audio-visual) flicker modulates widespread brain networks including the hippocampus, medial temporal lobe, and prefrontal cortex. Frohlich et al. (2024, bioRxiv) demonstrated audiovisual periodic stimulation effects resembling transcranial brain stimulation — non-invasively through eyes and ears. **Implementation note from Oppermann et al. (2024, Clinical Neurophysiology):** photic driving effects appear as continuous oscillations in averaged EEG but are actually transient bursts in single trials. Design the agent's interpretation logic accordingly.

**Somna Integration:** Already being implemented in this session. The `beat_phase` key from `audio_engine.py` enables true phase-locked AV sync. `av_sync_enabled` boolean for agent control.

**Effort:** 1 weekend. Phase 1 alignment. This is the lowest-effort, highest-return enhancement to Somna's entrainment power.

---

### Idea 5: Alpha Phase-Locked Auditory Stimulation (αCLAS)
**IMPACT: ★★★★★ / FEASIBILITY: ★★★☆☆**

The open-science version of what Elemind sells for $349 + $7/month. Real-time phase tracking of the user's individual alpha oscillation (8–12 Hz), then delivering acoustic pulses timed to specific phases: anti-phase to suppress alpha for sleep onset, in-phase to boost alpha for relaxation.

**The Science:** Bressler et al. (2024, Nature Scientific Reports, Elemind Technologies) ran an RCT with 21 insomnia subjects. Acoustic pulses timed anti-phase to alpha oscillations reduced sleep onset latency by 29.3% (10.5 ± 15.9 minutes). Hebron et al. (2024, PLOS Biology) demonstrated that αCLAS alters alpha power, frequency, and connectivity in phase-dependent ways. Harlow et al. (2024, eNeuro) found opposing alpha phase-dependent effects — trough vs. peak produce distinct modulations.

**Somna Integration:** Requires real-time alpha phase tracking in `eeg_engine.py` (BrainFlow bandpass → Hilbert transform → instantaneous phase). Likely requires a direct callback path from `eeg_engine.py` to `audio_engine.py`, bypassing `live_control.json` for latency — a dedicated thread with a shared ring buffer. The IPC bus latency (100ms poll) is too slow for the <25 ms latency budget at 10 Hz alpha.

**Effort:** 3–4 weekends. Phase 3–4 alignment. This replicates $349 + $84/year commercial functionality with $250 hardware and free Python code.

---

### Idea 6: Sleep TMR Affirmation Consolidation
**IMPACT: ★★★★★ / FEASIBILITY: ★★★☆☆**

Targeted Memory Reactivation — replaying key affirmations from the waking session as audio cues during NREM slow-wave sleep to strengthen consolidation into long-term memory.

**The Science:** Carbone & Diekelmann (2024, npj Science of Learning): TMR builds on the brain's natural memory reactivation during sleep. Recher et al. (2024, Translational Psychiatry) demonstrated closed-loop cueing in 80 participants' homes over 2–5 nights using wearable EEG — memories became significantly less vivid and distressing. Shin et al. (2025, npj Science of Learning) showed personalized TMR enhanced slow wave-spindle synchronization and significantly reduced memory decay.

**Somna Integration:** `somna_agent.py` already logs affirmations per session in JSONL logs. Add sleep-stage detection in `eeg_engine.py` (high `eeg_delta`, low `eeg_beta`), a "sleep" session mode in `timeline_runner.py` with indefinite duration and EEG-gated cue delivery.

**Effort:** 3–4 weekends. Phase 3–4 alignment. Extends Somna's affirmation delivery from a single-session event into a two-phase waking+sleep consolidation pipeline.

---

### Idea 7: EEG-Reactive Ambient Soundscapes
**IMPACT: ★★★☆☆ / FEASIBILITY: ★★★★☆**

Map EEG band powers to ambient soundscape parameters — rain intensity, drone pitch, pad filter cutoff, nature sound volume — so the sonic environment evolves in real-time response to brain state. The brain hears its own state reflected back, reinforcing the target pattern.

**Somna Integration:** New "soundscape" layer in `audio_engine.py` alongside binaural/isochronic beats. EEG band powers mapped to soundscape parameters (high alpha → warm pad opens, high theta → rain intensifies, high beta → sharper textures). Open-source precedent: "neuro-music-reactor" on GitHub.

**Effort:** 2–3 weekends. Phase 3–4 alignment. Medium complexity — requires new audio layer architecture and soundscape asset creation.

---

### Idea 8: Pink Noise Stochastic Resonance Layer
**IMPACT: ★★★☆☆ / FEASIBILITY: ★★★★★**

A calibrated low-level pink noise layer leveraging stochastic resonance — adding a small amount of noise to a signal enhances the system's response to that signal. Dual benefit: enhances brain response to entrainment stimuli, and potentially improves EEG signal quality.

**The Science:** Herrmann (2025, eLife) demonstrated stochastic resonance in human neural speech tracking across five EEG experiments. Minimal background noise at ~30 dB SNR enhanced neural tracking. The effect is independent of attention. Chen et al. (2023, Frontiers in Neuroscience) validated the computational application: adding optimal noise levels to EEG signals improved BCI detection accuracy.

**Somna Integration:** Pink noise generation is ~10 lines of numpy (generate white noise, apply cumulative sum, normalize, highpass). Mix at calibrated level relative to entrainment tone (~30 dB below signal). Note: Somna already has a pink noise channel. This is about calibrating it for stochastic resonance specifically.

**Effort:** 1 weekend. Phase 1 alignment (no EEG needed). Minimal effort, dual benefit. "Why not" feature.

---

### Idea 9: Lucid Dream Induction Mode
**IMPACT: ★★★★☆ / FEASIBILITY: ★★☆☆☆**

Two-phase protocol: (1) pre-sleep training with visual + audio cues associated with lucidity awareness ("You are dreaming"), (2) during sleep, `eeg_engine.py` detects REM and replays those same cues to trigger lucid awareness. Based on SSILD + TLR (Targeted Lucidity Reactivation) method.

**The Science:** Esfahani et al. (2024, bioRxiv, multi-center, n=60) combined SSILD with TLR using 2-channel EEG and the open-source "Dreamento" toolbox. Successfully induced signal-verified lucid dreams in 65% (Netherlands) and 45% (Italy) of participants. Average verified lucidity duration: 78.75 ± 54.85 seconds. Demirel et al. (2025, Journal of Neuroscience) characterized lucid dreaming EEG signatures: beta power reductions in right central/parietal areas, increased alpha functional connectivity, and increased gamma1 (30–36 Hz) in right temporo-occipital regions. Konkoly et al. (Northwestern, 2024) validated TLR via smartphone app: participants improved to 2.11 lucid dreams/week from 0.74 baseline.

**Effort:** 4+ weekends. Phase 4+ alignment. Robust REM detection from Muse 2 frontal electrodes is achievable but requires careful validation. A marquee feature that extends Somna from "hypnosis tool" to "consciousness exploration platform."

---

### Idea 10: HRV-EEG Coherence Breathing Guide
**IMPACT: ★★★★☆ / FEASIBILITY: ★★☆☆☆**

Agent-guided resonant breathing (4–7 breaths/min) with real-time HRV monitoring, timed to audio pulsing, while EEG tracks the alpha response to breathing coherence. Requires additional hardware: BLE PPG sensor (Polar H10 ~$90 or fingertip pulse oximeter ~$30–50). Note: Muse 2 does not have PPG (Muse S does).

**The Science:** Balaji et al. (2025, Nature Scientific Reports) published the largest HRV biofeedback study ever — 1.8 million sessions analyzed. Most common coherence frequency: 0.10 Hz (6 breaths/min). Demin & Poskotinova (2025, Life) demonstrated the direct HRV→EEG coupling: during HRV biofeedback, alpha EEG activity significantly increased across all brain regions. Breathing coherence boosts alpha.

**Somna Integration:** New `hrv_engine.py` module (same architecture as `eeg_engine.py`) writing `hrv_bpm`, `hrv_rmssd`, `hrv_coherence`, `hrv_coherence_freq` to `live_control.json`. Agent guides breathing via TTS prompts. Creates triple-feedback loop: breathing → HRV coherence → alpha → agent adjusts.

**Effort:** 3–4 weekends + hardware purchase. Phase 4+ alignment.

---

## 3. Implementation Roadmap

| Phase | Timeline | Ideas That Fit | New Hardware |
|-------|----------|----------------|--------------|
| Phase 0 | Synthetic EEG | Prototype #1 and #2 with synthetic theta/depth signals. Validate agent behavior before hardware. | None |
| Phase 1 | Isochronic/Monaural Audio | #3 (40 Hz GENUS), #4 (AV Sync), #8 (Pink Noise SR) | None |
| Phase 2 | Muse 2 Hardware | Hardware validation, EEG signal quality confirmation, baseline calibration for #2 | Muse 2 ($250) |
| Phase 3 | Agent Tuning | #1 (Theta-Gated Affirmations), #2 (Trance Depth), #7 (Reactive Soundscapes) | None |
| Phase 4 | Advanced | #5 (αCLAS), #6 (Sleep TMR), #9 (Lucid Dreams) | None |
| Phase 5 | Future Sensors | #10 (HRV-EEG Coherence) | PPG sensor ($30–90) |

---

## 4. The Dithering Technique — A Cross-Cutting Optimization

Duchet et al. (2025, bioRxiv/Oxford) described "dithering": slightly jittering stimulation pulse timing to selectively suppress half-harmonic entrainment while preserving target frequency entrainment. When stimulating at 40 Hz, inadvertent 20 Hz entrainment (the half-harmonic) can occur. Adding ±5–10 ms random jitter to each pulse disrupts subharmonic phase consistency without affecting the target frequency.

Relevant to three ideas:
- **#3 (40 Hz GENUS):** Add ±5 ms jitter to isochronic pulse timing to prevent unintended 20 Hz beta entrainment.
- **#4 (AV Sync):** Both audio and visual modulation should use the same dithered timing for cross-modal coherence while suppressing subharmonics.
- **#5 (αCLAS):** Phase-locked pulses should include minimal dithering to avoid ~5 Hz theta artifacts when targeting ~10 Hz alpha.

**Implementation in `audio_engine.py`:** Add optional `dither_ms` parameter to isochronic mode (default 0, typical value 5–10). For each pulse onset, add `random.uniform(-dither_ms, dither_ms)` milliseconds. Expose as a `live_control.json` key. ~5 lines of code.

---

## 5. Key Takeaways

- Somna already has ~80% of the infrastructure needed for every idea in this report.
- Ideas #1, #3, #4, and #8 require zero new code modules.
- Idea #2 (trance depth) is the backbone metric. Prioritize it alongside #1.
- The combination of #1 + #2 creates a closed-loop hypnotic system: detect depth → gate affirmations → verify deepening → adjust strategy → repeat.
- The open-science publication of αCLAS research means Somna can replicate Elemind's core functionality using $250 hardware and free Python code.
- Start with Phase 0 (synthetic data) to validate agent behavior before hardware. The synthetic board toggle in `eeg_engine.py` means every agent-side feature can be developed, tested, and tuned without a Muse 2 on your head.

---

## 6. References

1. Gordon, C.L., et al. "Theta-frequency rhythmic auditory stimulation selectively induces altered states of consciousness." *Nature Scientific Reports*, 16, Article 9682 (2026).
2. De Benedittis, G. "Neural Mechanisms of Hypnosis and Meditation." *Brain Sciences*, 15(1), 65 (2025).
3. De Pascalis, V. "EEG and Hypnosis: A Review of the Literature." *Brain Sciences*, 14(10), 1006 (2024).
4. Obukhov, Y.V., et al. "Passive brain-computer interface for real-time estimation of hypnotic depth." *BMC Research Notes*, 16, Article 303 (2023).
5. Farahzadi, A., et al. "Gamma Power and Beta Envelope Correlation as Neural Predictors of Deep Hypnosis." *Nature Scientific Reports*, 14, Article 15342 (2024).
6. Zech, N., et al. "Anesthesia Depth Monitors BIS and CSI Respond to Hypnotic Trance." *Frontiers in Psychology*, 14, Article 1115829 (2023).
7. Park, H. & Tsai, L.-H. "Non-invasive Gamma Entrainment Using Sensory Stimuli for Alzheimer's Disease: A Decade of Research." *PLOS Biology*, 23(2), e3003055 (2025).
8. Bhatt, D.P., et al. "Gamma sensory stimulation promotes glymphatic clearance of amyloid via VIP-mediated mechanisms." *Nature*, 627, 149–156 (2024).
9. Mlinarič, T., et al. "Visual gamma stimulation induces 40 Hz neural oscillations in the human hippocampus." *Communications Biology*, 8, Article 1301 (2025).
10. Chan, D., et al. "Long-term safety and feasibility of daily 40 Hz GENUS device use in patients with mild Alzheimer's disease." *Alzheimer's & Dementia*, 21(1), e14572 (2025).
11. Blanpain, L.T., et al. "Multisensory flicker modulates widespread brain networks and reduces interictal epileptiform discharges." *Nature Communications*, 15, Article 3156 (2024).
12. Frohlich, F., et al. "Audiovisual periodic stimulation as non-invasive brain stimulation." *bioRxiv* (2024).
13. Rahmani, S., et al. "Audio-Visual Entrainment Neuromodulation: A Comprehensive Review." *Brain Sciences*, 15(2), 173 (2025).
14. Oppermann, H., et al. "Photic Driving in Single-Trial EEG: Transient Bursts vs. Continuous Oscillations." *Clinical Neurophysiology*, 160, 108–119 (2024).
15. Bressler, S., et al. "An EEG-based BCI for real-time acoustic alpha phase-locked stimulation reduces sleep onset latency." *Nature Scientific Reports*, 14, Article 12964 (2024).
16. Hebron, H., et al. "Alpha Closed-Loop Auditory Stimulation (αCLAS) alters alpha oscillation power, frequency, and connectivity." *PLOS Biology*, 22(12), e3002959 (2024).
17. Harlow, T., et al. "Individualized closed-loop acoustic stimulation during wakefulness targets alpha oscillations." *eNeuro*, 11(7), ENEURO.0188-24.2024 (2024).
18. Jaramillo, V., et al. "Closed-loop auditory stimulation targeting alpha and theta oscillations during REM sleep." *SLEEP*, 47(Suppl_1), A10 (2024).
19. Carbone, J. & Diekelmann, S. "An update on recent advances in targeted memory reactivation during sleep." *npj Science of Learning*, 9, Article 31 (2024).
20. Recher, D., et al. "Targeted memory reactivation during sleep using a wearable EEG device at home." *Translational Psychiatry*, 14, Article 412 (2024).
21. Shin, Y.S., et al. "Personalized targeted memory reactivation during sleep." *npj Science of Learning*, 10, Article 8 (2025).
22. Sifuentes Ortega, R. "Targeted Memory Reactivation during SWS and REM Sleep." *SLEEP*, 47(Suppl_1), A205 (2024).
23. Jiang, Z., et al. "EEG-Driven Automatic Music Generation via Transformer." *Frontiers in Neurorobotics*, 18, Article 1381569 (2024).
24. Shukla, A., et al. "A Survey on EEG and Generative AI: EEG-to-Audio." *arXiv*, 2502.12345 (2025).
25. Herrmann, B. "Enhanced neural speech tracking through noise indicates stochastic resonance in humans." *eLife*, 13, RP100830 (2025).
26. Chen, Y., et al. "Stochastic Resonance Applied to SSVEP-EEG Feature Enhancement." *Frontiers in Neuroscience*, 17, Article 1254685 (2023).
27. Esfahani, M.J., et al. "Multi-center Targeted Lucidity Reactivation with wearable EEG." *bioRxiv* (2024).
28. Demirel, Ö., et al. "EEG Correlates of Lucid Dreaming." *Journal of Neuroscience*, 45(5), e0987242024 (2025).
29. Konkoly, K., et al. "Targeted Lucidity Reactivation via Smartphone Application." *Consciousness and Cognition*, 119, Article 103657 (2024).
30. Balaji, A., et al. "Largest HRV Biofeedback Study: Analysis of 1.8 Million Sessions." *Nature Scientific Reports*, 15, Article 4521 (2025).
31. Saito, I., et al. "HRV Biofeedback Training Increases Resting Vagally-Mediated HRV." *Applied Psychophysiology and Biofeedback*, 49, 375–386 (2024).
32. Demin, D.B. & Poskotinova, L.V. "Alpha EEG Activity During HRV Biofeedback." *Life*, 15(2), 234 (2025).
33. Duchet, B., et al. "Dithering: Jittered Stimulation Timing Selectively Suppresses Half-Harmonic Entrainment." *bioRxiv* (2025).

---

*Medical Disclaimer: Somna is a personal wellness tool, not a medical device. The 40 Hz GENUS research involves clinical trials for specific medical conditions; implementing a 40 Hz session does not constitute medical treatment. Visual flicker features may trigger seizures in individuals with photosensitive epilepsy. EEG-based features provide estimates from consumer-grade hardware and should not be used for clinical assessment.*
