# EEG Entrainment — Agent Knowledge File
*Somna EEG Integration | Full Pipeline (Docs 20–25)*

This file is your complete operational reference for EEG-driven session management.
It supersedes all earlier versions and covers the full five-document pipeline:
SQI gating → ASSR verification → FAA receptivity → Adaptive Frequency Leading → Session Scoring.

---

## 1. EEG Keys in `live_control.json`

When `eeg_connected = true`, the following keys are available. All band power values are
**normalised proportions of total power** (0.0–1.0) — directly usable without amplitude baselines.

### Core Band Power & State

| Key | Type | Description |
|-----|------|-------------|
| `eeg_connected` | bool | Board session active |
| `eeg_dominant_band` | str | `"delta"` / `"theta"` / `"alpha"` / `"beta"` / `"gamma"` |
| `eeg_delta` | float | 0.5–4 Hz proportion |
| `eeg_theta` | float | 4–8 Hz proportion |
| `eeg_alpha` | float | 8–13 Hz proportion |
| `eeg_beta` | float | 13–30 Hz proportion |
| `eeg_gamma` | float | 30–50 Hz proportion |
| `eeg_gamma_40hz` | float | Narrow 38–42 Hz power (GENUS monitoring) |
| `eeg_alpha_theta_ratio` | float | Alpha/theta — higher = more wakeful |
| `eeg_beta_alpha_ratio` | float | Beta/alpha — higher = more alert |
| `eeg_frontal_asymmetry` | float | ln(AF8_alpha) − ln(AF7_alpha) — legacy; prefer `eeg_faa` |
| `eeg_trance_score` | float | 0–1 depth index (theta+delta vs alpha+beta) |
| `eeg_state` | str | Classified state (see §3) |
| `eeg_iaf_hz` | float\|null | Individual Alpha Frequency (null until calibrated) |
| `eeg_timestamp` | float | Wall time of last valid EEG update |

### Signal Quality Index (SQI) — Bible Ch.2 Â§SQI

The primary gate for all higher-order metrics. Use `eeg_confidence` as the decision gate,
not the raw `eeg_quality` string.

| Key | Type | Description |
|-----|------|-------------|
| `eeg_quality` | str | Legacy `"good"` / `"poor"` / `"unusable"` |
| `eeg_confidence` | str | **`"full"` / `"reduced"` / `"low"` / `"none"`** — use this |
| `eeg_sqi_composite` | float | Composite quality 0–1 (mean of usable channels) |
| `eeg_sqi_tp9` | float | TP9 channel quality 0–1 |
| `eeg_sqi_af7` | float | AF7 channel quality 0–1 |
| `eeg_sqi_af8` | float | AF8 channel quality 0–1 |
| `eeg_sqi_tp10` | float | TP10 channel quality 0–1 |
| `eeg_sqi_usable_channels` | int | Count of channels above 0.5 quality |

**`eeg_confidence` definitions:**
- `"full"` — all 4 channels ≥ 0.6 SQI: full trust
- `"reduced"` — 2–3 channels ≥ 0.5: trust band ratios, use FAA and ASSR cautiously
- `"low"` — 1 channel usable: treat as soft directional hint only
- `"none"` — no usable channels: do not make EEG-driven decisions

### Spectral Depth Markers

| Key | Type | Description |
|-----|------|-------------|
| `eeg_sef95` | float | Spectral Edge Frequency 95% (Hz) — frequency below which 95% of EEG power lies. Lower = deeper. |
| `eeg_spectral_slope` | float | Power-law slope of PSD. More negative = deeper theta/delta dominance. Typical range −1.5 to −3.5. |

**SEF95 interpretation:**
- > 14 Hz: alert / anxious
- 10–14 Hz: relaxed wakefulness (alpha range)
- 7–10 Hz: light trance / drowsy
- 4–7 Hz: deep trance / theta dominant
- < 4 Hz: very deep — reduce stimulation, minimal prompting

SEF95 is the most reliable single depth indicator. Prefer it over `eeg_trance_score` when available.
`eeg_spectral_slope` is a secondary confirmation: a steeper negative slope alongside low SEF95 = confirmed deep state.

### ASSR Entrainment Verification — Bible Ch.2 Â§ASSR

Real-time verification that the brain is actually responding to the binaural/isochronic beat.
An ASSR response proves entrainment is occurring, not just that audio is playing.

`eeg_entrainment_strength` is now a **coherence-augmented composite**: 70% spectral power + 30%
inter-channel coherence, with a 30% penalty when `beat_frequency` is within ±1 Hz of `eeg_iaf_hz`
(alpha overlap). Coherence components are only computed when `eeg_confidence = "full"` (all 4
channels clean); at lower SQI they default to 0.0 and the composite falls back to power-only.

| Key | Type | Description |
|-----|------|-------------|
| `eeg_entrainment_strength` | float | 0–1 **composite** ASSR score (power + coherence blend — this is the primary decision metric) |
| `eeg_entrainment_power_strength` | float | 0–1 raw spectral power component (beat peak vs broadband noise floor) |
| `eeg_entrainment_coherence` | float | 0–1 mean inter-channel coherence at beat frequency (TP9↔TP10 and AF7↔AF8, averaged) |
| `eeg_entrainment_coherence_tp` | float | 0–1 TP9↔TP10 coherence alone |
| `eeg_entrainment_coherence_af` | float | 0–1 AF7↔AF8 coherence alone |
| `eeg_entrainment_confidence` | str | `"strong"` / `"moderate"` / `"weak"` / `"none"` — derived from composite strength |
| `eeg_entrainment_trend` | str | `"increasing"` / `"stable"` / `"decreasing"` |
| `eeg_entrainment_beat_freq` | float | Beat frequency the ASSR was measured at |
| `eeg_entrainment_channel_agreement` | float | 0–1 cross-channel power agreement |
| `eeg_entrainment_recommend_modality` | str | `"binaural"` / `"isochronic"` / `"both"` / `"current_ok"` |

**Reading the composite:** A high `eeg_entrainment_strength` with low `eeg_entrainment_coherence`
means the beat peak is visible in power but the two hemispheres aren't locking together — the
response is present but not strongly bilateral. High on both = robust entrainment. You only need
`eeg_entrainment_strength` for decisions; the component keys are diagnostic.

**When to act on ASSR:**
- `eeg_entrainment_confidence = "none"` for > 3 consecutive minutes → switch modality as recommended
- Alpha band ambiguity: when `beat_frequency` is within ±1 Hz of `eeg_iaf_hz`, ASSR confidence is artificially suppressed (alpha overlap penalty) — do NOT switch modality based on that reading alone
- `eeg_entrainment_trend = "decreasing"` for 10+ minutes → consider +0.5 Hz upward adjustment to re-engage
- Coherence components are only meaningful at `eeg_confidence = "full"`; at `"reduced"` or lower, treat `eeg_entrainment_strength` as power-only

### FAA Receptivity — Bible Ch.2 Â§FAA

Frontal Alpha Asymmetry: the primary gate for affirmation delivery timing.

| Key | Type | Description |
|-----|------|-------------|
| `eeg_faa` | float | Smoothed 10-s rolling FAA (ln(right_alpha) − ln(left_alpha)) |
| `eeg_faa_raw` | float | Instantaneous FAA for this 1-s window |
| `eeg_faa_state` | str | `"approach"` / `"neutral"` / `"withdrawal"` / `"alpha_suppressed"` / `"insufficient_data"` |

**FAA state interpretation:**
- `"approach"` (faa > baseline + 0.10): optimal window — deliver affirmations with full confidence
- `"neutral"`: standard delivery
- `"withdrawal"` (faa < baseline − 0.10): hold affirmations; let audio/visual carry the load; if withdrawal persists > 60 s, deliver anyway (may be trait asymmetry)
- `"alpha_suppressed"`: BOTH hemispheres suppressed — treat as permissive; deep suppression correlates with deep states
- `"insufficient_data"`: frontal SQI too low to trust — fall back to trance_score gating

**Thresholds are personalised:** After the first 60 seconds of valid data, the tracker computes a resting baseline and shifts thresholds to `baseline ± 0.10`. Your context will reflect the personalised gate automatically.

**Ideal delivery window:** `eeg_confidence` "full"/"reduced" AND `eeg_faa_state` "approach" AND `eeg_entrainment_strength` > 0.3 AND `eeg_sef95` falling. When all four agree = maximum confidence.

**Fractionation confirmation:** During fractionation, the pattern approach → withdrawal → approach is the neurological fingerprint of a clean fractionation cycle. Begin reinduction only after FAA shifts to withdrawal (genuine emergence confirmed).

### Frequency Leader — Bible Ch.3 Â§Frequency-Leading

The `AdaptiveFrequencyLeader` runs as a background thread when enabled. When active, it
**owns `beat_frequency`** — do not manually change it while the leader is running.

| Key | Type | Description |
|-----|------|-------------|
| `freq_lead_enabled` | bool | Write `true` to activate; `false` to return manual control |
| `freq_lead_target_hz` | float | Write the target frequency to guide toward |
| `freq_lead_phase` | str | `"inactive"` / `"meet"` / `"lead"` / `"hold"` / `"sustain"` |
| `freq_lead_current` | float | Current commanded beat frequency |
| `freq_lead_target` | float | Target the leader is descending toward |
| `freq_lead_steps` | int | Number of 0.1 Hz descent steps taken |
| `freq_lead_holds` | int | Number of times leader paused for ASSR recovery |

**Phase meanings:**
- `"meet"`: locking to IAF (matching user's current alpha)
- `"lead"`: descending 0.1 Hz every 30 s
- `"hold"`: paused — ASSR dropped below threshold; waiting for recovery
- `"sustain"`: target reached, maintaining

**How to use it:**
```json
{ "adjustments": { "freq_lead_enabled": true, "freq_lead_target_hz": 4.0 } }
```
Narrate key transitions (e.g. first hold, target reached) but stay silent during steady descent.
Disable with `freq_lead_enabled: false` to resume manual control.

---

## 2. SQI-Gated Decision Framework

This is the core quality gate — apply it before acting on any EEG reading:

| `eeg_confidence` | What you can trust | What to do |
|-----------------|-------------------|------------|
| `"full"` | All metrics | Full confidence — act on FAA, ASSR, SEF95, freq leading |
| `"reduced"` | Band powers, SEF95, coarse FAA | Use for entrainment decisions; treat FAA/ASSR as soft hints |
| `"low"` | Directional trends only | Do not change beat frequency; note state, wait for improvement |
| `"none"` | Nothing | Ignore all EEG keys; run session as if EEG is disconnected |

When SQI degrades mid-session, do not panic or interrupt the experience. Stay silent, keep current parameters, and wait 1–2 minutes for signal to recover.

---

## 3. State Classifications

| `eeg_state` | Meaning | Agent Implication |
|-------------|---------|-------------------|
| `awake` | High alpha, alpha/theta > 1.2 | Alert; light relaxation only |
| `relaxed` | Alpha-dominant, theta rising | Good entry state; deepen gradually |
| `trance` | Theta > alpha, some gamma | Active trance; maintain or deepen |
| `n1_entry` | Theta > alpha, low gamma | Near sleep onset; reduce stimulation |
| `n1` | Theta dominant (> 35%) | N1 sleep; whisper only, no response-requiring prompts |
| `n2_warning` | Theta + sigma spike | Deep N2; stop stimulation |

---

## 4. Brainwave Band Reference

Default boundaries (shift with IAF when calibrated — always prefer personalised values):

| Band | Default Range | State Association |
|------|--------------|-------------------|
| Delta | 0.5–4 Hz | Deep sleep, unconsciousness |
| Theta | 4–8 Hz | Hypnagogia, deep meditation, trance |
| Alpha | 8–13 Hz | Relaxed wakefulness, closed eyes |
| Beta | 13–30 Hz | Active thinking, alertness, stress |
| Gamma | 30–50 Hz | Higher cognition, focused attention |

**IAF note:** If `eeg_iaf_hz` is set, all boundaries shift. A user with IAF = 8.5 Hz has their theta/alpha boundary at 6.5 Hz — their 7 Hz activity is alpha, not theta. Always prefer personalised boundaries when IAF is available.

---

## 5. Entrainment Strategy

### Meet-and-Lead (Manual Mode — when FreqLeader is inactive)

1. **Read current state first.** Never assume the user is deeper than the EEG shows.
2. **Meet:** Match beat frequency to slightly above the user's current dominant band centre.
   - Theta dominant (4–8 Hz): start at 6–7 Hz.
   - Alpha dominant (8–13 Hz): set to IAF − 1 Hz to lead toward theta.
3. **Lead:** Reduce by ≤ 0.5 Hz per tick. Use `transitions: {beat_frequency: 120}` — 2-minute ramps.
4. **Lag:** EEG lags 3–5 minutes behind beat changes. Wait at least 5 minutes before re-adjusting.
5. **Quality gate:** `eeg_confidence = "low"` or `"none"` → do not make frequency decisions.

### FreqLeader Mode (Automated — recommended for deep sessions)

Enable with `freq_lead_enabled: true` and `freq_lead_target_hz: <target>`. The leader handles
steps, holds, and ASSR gating automatically. You narrate; the system descends.

During hold phases, acknowledge the pause only if the user is engaged — otherwise stay silent.

---

## 6. FAA-Gated Affirmation Delivery

- **"approach" state:** Deliver affirmations confidently. Use somatic language: "you feel warmth in your chest", "weight settling deeper".
- **faa > 0.2:** Bold somatic statements.
- **faa 0.1–0.2:** Standard delivery.
- **faa < 0.1:** Gentle suggestions only.
- **"withdrawal" state:** Hold affirmations > 60 s — if still withdrawing, deliver gently anyway (may be trait asymmetry, not genuine withdrawal).

### Veil Mode and Subliminal Timing

`converge` and `tunnel` veil modes preserve semantic priming (Marcel 1983 pattern masking).
When delivering affirmations, prefer:
- `veil_mode: "converge"` — flows text toward fovea
- `veil_mode: "tunnel"` — global depth motion, letter recognition intact

High-density `drift` acts as a noise mask — reserve it for pure entrainment phases where text is not displayed.

---

## 7. Beat Mode Selection by Device

| Device | Recommended Mode | Reason |
|--------|-----------------|--------|
| Over-ear headphones | `binaural` | Full stereo separation |
| Earbuds (good seal) | `binaural` or `both` | Seal matters for binaural |
| Open-back / speaker | `isochronic` | Binaural requires headphones |
| Bone conduction | `isochronic` | No stereo separation through bone |

Use `eeg_entrainment_recommend_modality` — the ASSR tracker will tell you if it detects a better modality based on observed response.

---

## 8. Ratio Interpretation

**Alpha/Theta ratio (`eeg_alpha_theta_ratio`):**
- > 1.5: Wakeful, alert
- 0.8–1.5: Relaxed, open awareness
- 0.5–0.8: Drowsy, hypnagogic transition
- < 0.5: Theta-dominant — deep trance or N1

**Beta/Alpha ratio (`eeg_beta_alpha_ratio`):**
- > 1.5: Analytical, stressed, not receptive
- 0.5–1.5: Balanced — alert but open
- < 0.5: Deeply relaxed, receptive

**Trance score (`eeg_trance_score`):**
- 0.0–0.2: Light relaxation
- 0.2–0.4: Moderate trance
- 0.4–0.6: Deep trance
- 0.6–1.0: Very deep — hold current frequency, minimal prompting

---

## 9. Session Effectiveness Scoring — Bible Ch.5 Â§Scoring

Post-session scores are computed automatically by control_panel.py when the display stops
and EEG data was collected. Results appear in the agent console and are stored in `somna.db`.
The `SessionAnalyzer` queries these scores at session start to inform auto-optimization.

**Score components:** depth (SEF95), time in target, transition speed, stability, entrainment (ASSR), receptivity (FAA), signal quality.

**Composite score:** 0–100. SQI penalty applies — noisy sessions score proportionally lower.

The agent queries `SessionAnalyzer().optimization_recommendation(preset)` at each fresh session start.
When ≥ 10 scored sessions exist for that preset, it may apply ≤ 2 parameter tweaks (e.g., veil mode or spiral style) based on what configuration correlated with the highest scores.

---

## 10. Artifact Handling

Artifact sources: jaw clench, blinking (large spikes), electrode contact loss (sustained high amplitude), EMI (50/60 Hz spike).

When `eeg_confidence` drops to `"low"` or `"none"`:
- Treat the last `"reduced"` or `"full"` reading as current state
- Do not increase stimulation intensity
- If low confidence persists > 2 minutes, the headband prompt fires automatically — no need to manually address it

---

## 11. Practical Limits

- **Minimum change threshold:** Do not adjust `beat_frequency` unless trance_score or SEF95 has been stable for at least 2 consecutive readings.
- **Maximum depth:** If `eeg_trance_score` > 0.7 or `eeg_sef95` < 4 Hz, hold current frequency — very deep states are fragile.
- **Alpha blocking:** Alpha drops when user opens eyes or processes visual stimuli. A sudden alpha drop does not mean trance — check beta. Rising beta alongside falling alpha = alerting, not deepening.
- **EEG lag:** Brain responds to beat changes with a 3–5 minute lag. Do not re-adjust before waiting.
