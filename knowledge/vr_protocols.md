# VR Protocols — Agent Reference

This document describes Somna's VR headset system, what it measures,
and how the agent should interpret and respond to its outputs.

---

## What the VR system does

When `vr_headset_active` is True, a separate subprocess (`vr_display_runner.py`)
is rendering per-eye content to an OpenXR-compatible headset. The control panel
"VR Headset" section manages it. Everything communicates through `live_control.json`.

---

## Render modes (`vr_render_mode`)

| Mode | Description |
|------|-------------|
| `ganzfeld` | Uniform featureless grey field per eye. Triggers prediction error collapse and phosphene imagery. A 2-minute onset ramp from black prevents photosensitive alarm. Add `vr_vection_enabled: true` to layer forward optic flow. |
| `photic` | Both eyes flicker at the same frequency (`vr_photic_hz`). The Conductor auto-adjusts this frequency toward the user's IAF if SSVEP SNR is poor after 60 s. Full-field stimulation — strongest photic driving. |
| `rivalry` | Each eye receives an independent flickering grating at `vr_rivalry_left_hz` / `vr_rivalry_right_hz`. The brain cannot fuse incompatible images and alternates dominance — binocular rivalry. This is the visual equivalent of binaural beats. |
| `dichoptic_ssvep` | Same as rivalry but framed as a measurement tool — the tags are calibration-grade SSVEP probes rather than entrainment stimuli. Used for clean trance depth measurements. |

---

## Vection (`vr_vection_enabled`)

Forward optic flow (particle tunnel) layered on top of any render mode.
Causes illusory self-motion (vection) → somatic dissociation.
The user feels the body receding while the mind remains present.
Can be added to any mode. Cybersickness mitigation is built-in: speed is
session-capped (first session max 0.10 units/frame, full speed at session 4).

---

## SSVEP metrics — what they mean

These keys are written by the SSVEP detector (AF7/AF8 channels) once per second
when the headset is running with rivalry or dichoptic_ssvep modes:

| Key | Meaning |
|-----|---------|
| `ssvep_binocular_index` | 0–1. How strongly the two eye-tags are being integrated by the brain. > 0.6 = strong binocular integration. Analogous to entrainment_strength for binaural. |
| `ssvep_switch_rate_hz` | Rate at which perceptual dominance switches between eyes (Hz). Elevated switch rate (> 0.15 Hz) indicates active rivalry and deep engagement. Low switch rate means one eye is suppressing the other — rivalry is shallow. |
| `ssvep_dominance_raw` | Signed value: positive = left eye dominant, negative = right. Useful for detecting persistent one-eye suppression (contact issue, or unusual lateralised state). |
| `ssvep_im_f1_plus_f2` | SNR at f_L + f_R. Positive value = binocular integration confirmed by intermodulation. |
| `ssvep_left_snr` / `ssvep_right_snr` | Per-eye tag detection SNR (dB). Values > 3 dB mean the tag is reliably present. |

### Interpreting binocular_index

- **0.0–0.3**: Rivalry not established. User may be in a light state, one eye suppressing, or VR session very new.
- **0.3–0.6**: Partial rivalry. Entrainment beginning. Continue deepening.
- **0.6–0.8**: Strong rivalry and integration. Equivalent to moderate trance. Conductor may allow phase advance.
- **> 0.8**: Maximal binocular integration. Very deep state. Reduce stimulation, maintain.

### Interpreting switch_rate_hz

- **< 0.05 Hz**: Static dominance — one image completely suppressing the other. May indicate single-eye adaptation. Consider reducing depth or switching to photic mode.
- **0.05–0.15 Hz**: Normal rivalry oscillation. Healthy engagement.
- **> 0.15 Hz**: Elevated switch rate — proxy for deep trance (consistent with Bible Ch.8 Â§VR findings). Use this as a secondary depth signal alongside trance_score.

---

## Depth-plane subliminal delivery

When `vr_headset_active` is True and the session is in `maintenance` or
`frac_emerge` phases, the subliminal renderer delivers affirmation phrases
at three stereoscopic depth planes simultaneously:

- **Far plane** (~4 m virtual): primary delivery, highest throughput
- **Mid plane** (screen depth): secondary stream
- **Near plane** (~0.5 m, foreground): tertiary; time-limited due to VAC rules

Your `next_affirmation` injections are automatically routed across these planes
(4:4:1 far/mid/near ratio). You do not need to do anything differently — just
keep writing `next_affirmation` as normal and the VR renderer picks it up.

The user receives up to 3× the subliminal throughput compared to the flat
2D affirmation layer, because each depth plane has independent masking.

---

## How to act on VR data as an agent

### When to suggest enabling vection
Suggest `vr_vection_enabled: true` (via adjustments) when:
- The user is in `deepening` or `maintenance` phase
- `trance_score` is plateauing (rate of change near zero)
- `ssvep_binocular_index` is moderate (0.4–0.6) but not rising

Vection adds a somatic pathway that complements the binaural/visual entrainment.
Frame it as: the body drifting away while the mind remains.

### When rivalry is shallow (switch_rate < 0.05 Hz)
One eye may be dominating. Options:
1. Reduce `vr_rivalry_depth` to 0.10–0.15 (less aggressive stimulation)
2. Ask the user if their headset feels uncomfortable
3. Switch to `photic` mode for a few minutes then return to rivalry

### When binocular_index suddenly drops during maintenance
This usually means the user has shifted attention — opened eyes, moved,
or disengaged. Treat like a drop in trance_score: send a gentle refocusing
affirmation and reduce beat frequency by 0.5 Hz.

### When photic SNR is poor (ssvep_left_snr < 3 dB in photic mode)
The Conductor handles frequency adjustment automatically. You don't need to
intervene unless this persists > 3 minutes, at which point switching to
rivalry mode may be more effective for this user's neurotype.

---

## Proactive rivalry probe (Phase 3, not yet implemented)

A planned feature: the agent can request a 60-second rivalry measurement
burst at any time by writing `vr_rivalry_probe_requested: true` to
`live_control.json`. The system would switch to dichoptic_ssvep mode,
collect a clean measurement, then return to the previous mode.
This gives the agent an active tool for assessing trance depth independent
of the ongoing session parameters.

---

## Safety constraints (non-overridable)

- Danger zone (10–25 Hz): modulation depth hard-capped at 0.40
- Square wave above 30 Hz: rejected at renderer level
- First session: depth cannot exceed 0.10 regardless of Conductor commands
- Paroxysmal EEG activity: all stimulation zeros immediately (`vr_safety_kill: true`)
- Near-plane subliminal: capped at 25% of total subliminal time (VAC)
- Total subliminal delivery: 20 minutes per session maximum

**Never attempt to adjust `vr_photic_hz` into the 10–25 Hz danger zone at
high depth.** The safety enforcer will clamp depth to 0.40 but the frequency
will still drive the 10–25 Hz band. For trance work, stay at IAF (typically
8–12 Hz) at depth 0.10–0.25.
