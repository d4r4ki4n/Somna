# HRV-Breath-Beat Coupling Reference for Somna
*Passive Respiratory Entrainment via Carrier Amplitude Modulation at 0.1 Hz*
*Doc #14 · Research · 30 March 2026*
*Extends: hrv_coherence_breathing.md · Targets: audio_engine.py, somna_agent.py*

---

## 1. Resonance Frequency Fundamentals

The adult cardiorespiratory system resonates near **0.1 Hz** (6 breaths/min). Stimulation at this frequency produces large-amplitude BP oscillations and increases baroreflex sensitivity.

| Mechanism | Description |
|-----------|-------------|
| Baroreflex resonance | Slow breathing at ~0.1 Hz resonates the baroreflex loop |
| SAR recruitment | Prolonged inhalation recruits slowly-adapting pulmonary afferents |
| Baroreceptor activation | Deep exhalations raise arterial BP, stimulating parasympathetic outflow |
| Pronounced RSA | Reciprocal SAR/baroreceptor actions produce large-amplitude RSA |

*Noble & Hochman 2019 (Frontiers in Physiology)*

---

## 2. Evidence: 0.1 Hz Is the Population Default

**Balaji et al. 2025 (Scientific Reports, N=1.8M sessions)**
- Population mode coherence frequency: **0.10 Hz**
- High-coherence users often fell in 0.04–0.10 Hz band
- Session-to-session frequency SD < 0.012 Hz — resonance is stable per user
- Users naturally converge on resonance when instructed to breathe slowly

**Implication**: Start at 0.1 Hz (`breath_rate: 0.1`). It covers the population mode. No calibration required for Tier 1.

---

## 3. Passive Audio Modulation Entrains Breathing — Evidence Chain

**Goheen et al. 2024 (Nature Communications Biology)** — strongest evidence:
- Brain and breathing activities attune their temporal power spectra to periodic auditory inputs
- "Dynamic attunement" coordinates brain activity, breathing, and auditory input across minutes
- This is exactly the mechanism Somna exploits via carrier AM at 0.1 Hz

**Other modalities confirming 0.1 Hz passive entrainment:**
- Visual (pulsing light): Grote et al. 2013 — 0.1 Hz light increased vagal HRV
- Muscle tension: Vaschillo et al. 2011 — cyclic contraction at 0.1 Hz evoked HR/BP oscillations; off-resonance (0.05 / 0.2 Hz) significantly smaller
- Auditory-motor: Pranjić et al. 2024 — audio guidance reduces cognitive load vs. self-paced breathing

---

## 4. Implementation: `breath_mod` in audio_engine.py

### Modulation formula

```
modulated_amplitude = base_amplitude × (1 + breath_depth × sin(2π × breath_rate × t))
```

Where `t` is continuous sample time in seconds. Produces a gentle volume swell/fade at the breathing rate.

### New `live_control.json` keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `breath_mod` | bool | false | Enable carrier AM at breath rate |
| `breath_rate` | float | 0.1 | Breath modulation frequency in Hz (0.04–0.2) |
| `breath_depth` | float | 0.20 | Modulation depth as fraction of carrier amplitude (0.0–0.5) |
| `breath_phase` | string | `"swell_inhale"` | Whether volume peak aligns with inhale or exhale |

### Interaction with existing systems

- **`beat_mod`** (existing): modulates voice amplitude at entrainment frequency (Hz-range)
- **`breath_mod`** (new): modulates carrier amplitude at breathing rate (ultra-slow, 0.04–0.2 Hz)
- Both applied multiplicatively — no conflict, different timescales
- `breath_rate` can be a RampEngine target (e.g., 0.12 → 0.08 Hz over 15 min)

---

## 5. Three-Tier Protocol Design

### Tier 1: Preset-Pace (No hardware) — **NO BLOCKERS, implement now**
- `breath_rate: 0.1`, `breath_depth: 0.15–0.20`
- Balaji et al.: users naturally converge on resonance at 0.1 Hz

### Tier 2: Agent-Guided RF Discovery (No hardware) — nice-to-have
- 5 trials from 6.5 to 4.5 bpm in 0.5-bpm decrements, 2 min each
- User self-reports most comfortable rate; agent stores in `user_profile.json`

### Tier 3: Closed-Loop PPG Feedback — **BLOCKED**
- Requires PPG config_board verification on real Muse 2 hardware
- Update interval: coherence score every 30 s, ±0.005 Hz adjustment step

---

## 6. Session YAML Example (Tier 1, 20 min)

```yaml
session:
  name: "HRV Coherence — Passive Breath Entrainment"
  duration_min: 20

timeline:
  - time: "0:00"
    beat_freq: 10.0
    carrier_freq: 200
    beat_mod: true
    breath_mod: false      # no breath mod yet

  - time: "2:00"
    breath_mod: true
    breath_rate: 0.12      # start at 7.2 bpm
    breath_depth: 0.15

  - time: "5:00"           # ramp to 6 bpm over 2 min
    breath_rate: {ramp_to: 0.10, ramp_duration: 120}
    breath_depth: {ramp_to: 0.25, ramp_duration: 180}

  - time: "15:00"
    beat_freq: {ramp_to: 6.0, ramp_duration: 60}
    breath_rate: 0.10

  - time: "18:00"
    beat_freq: {ramp_to: 10.0, ramp_duration: 90}
    breath_depth: {ramp_to: 0.0, ramp_duration: 90}
```

---

## 7. Agent Behavior

- **Without PPG (Tiers 1–2)**: Monitor `eeg_alpha` and `eeg_beta` as proxy — increased alpha / reduced beta during breath-entrained segments indicates relaxation response
- **With PPG (Tier 3)**: Monitor coherence score directly; adjust `breath_rate` toward resonance peak
- `breath_rate` and `breath_depth` are valid RampEngine targets — use `transitions` dict

---

## References

| Citation | Detail |
|----------|--------|
| Balaji et al. 2025 | Scientific Reports. N=1.8M HRV biofeedback sessions. |
| Goheen et al. 2024 | Nature Communications Biology. Tripartite brain-breathing-auditory attunement. |
| Noble & Hochman 2019 | Frontiers in Physiology. SAR/baroreceptor resonance at 0.1 Hz. |
| Pranjić et al. 2024 | Brain Sciences. Auditory-motor synchronization; audio reduces cognitive load. |
| Vaschillo et al. 2011 | Cyclic muscle tension at 0.1 Hz evokes HR/BP oscillations. |
| Lalanza et al. 2023 | Systematic review, N=143 HRVB studies. Three protocol types. |
