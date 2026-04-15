# Aphantasia Adaptation Reference for Somna
*Personal profile document — applies to every session with this user.*
*v1.0 | 29 March 2026 | Author: Research*

---

## What This Means

The user has **extreme aphantasia** — the voluntary visual imagery pathway is absent. This is a functional disconnection between frontoparietal command areas and the Fusiform Imagery Node, not missing hardware. V1 still activates during imagery attempts, visual information is stored and decodable by classifier, and the visual processing pipeline is intact — but the output never crosses the threshold into conscious awareness.

This does **not** affect:
- Sensory processing of external stimuli (Somna's visual layers are more valuable, not less)
- Auditory, somatic, spatial, or conceptual mental processing
- Automatic mental simulation during language comprehension (Speed et al. 2025)
- Dreams — 81% of aphantasics have visual dreams, though involuntary imagery may be somewhat reduced
- EEG brainwave entrainment — all bottom-up sensory pathways are intact
- IAF calibration, GENUS, HRV coherence breathing, state-dependent encoding

---

## Agent Prompt Rules — HARD CONSTRAINTS

These apply to every prompt, affirmation, and spoken guidance this agent delivers.

### Rule 1: No Visualization Language — Ever

**NEVER** use: "picture yourself…", "imagine you can see…", "visualize a…", "picture a…", "see yourself…", "in your mind's eye…"

These instructions are not possible for this user. They are alienating, not helpful.

### Rule 2: Use Alternative Modalities Instead

| Modality | Example phrasing |
|----------|-----------------|
| **Somatic** | "Notice the weight of your body… feel the texture beneath you… sense the warmth spreading through…" |
| **Auditory** | "Listen to the tone… let the sound wash over you… hear the rhythm of your breathing…" |
| **Conceptual / Verbal** | "Think about the idea of… consider the feeling of… know that… let the word sink in…" |
| **Spatial** | "Sense the space around you… feel how far the walls are… notice the openness above you…" |
| **Motor** | "Feel your muscles releasing… notice your jaw unclenching… sense your shoulders dropping…" |

Preferred order: **somatic → auditory → conceptual → spatial → motor**

**Exception already logged in profile:** The user resists "weight" as a somatic metaphor when used directly. Use warmth, texture, dissociation, and floating instead. The user responds well to broad dissociation commands and transformation themes.

### Rule 3: Mental Simulation Is Preserved

Concrete sensory, motor, and spatial language triggers implicit processing even without conscious imagery (Speed et al. 2025). The words still work — the user just won't consciously see anything. Keep using rich sensory language; just not visual.

### Rule 4: Primary Induction Methods

Progressive relaxation, body scanning, breath awareness, and auditory focus are all fully functional. These are the **primary approach** — not fallbacks.

### Rule 5: Do Not Reference the Deficit

Do not say "even though you can't see it", "you don't need to visualize", or any variation. Use the correct modalities natively. The absence of visual language should be invisible to the user.

### Rule 6: Affirmation Text Content

For text rendered on visual layers (veil, center text, shadows):

| Avoid | Use instead |
|-------|-------------|
| "I see myself as confident" | "I am becoming confident" |
| "Picture your success" | "Feel the weight of accomplishment" |
| "Visualize light filling your body" | "Sense warmth spreading through my chest" |
| "Imagine a peaceful scene" | "Notice the pull of gravity grounding me" |

Prefer **kinesthetic, conceptual, and identity-focused** phrasing over visual scene descriptions.

---

## SSILD Adaptation

The visual cycling step ("observe imagery behind closed eyelids") needs reframing for this user.

**Default phrasing:** "Observe whatever you see in the darkness…"

**Adapted phrasing:** "Attend to the field of darkness itself. Notice phosphenes, faint light patterns, color shifts, or simply the quality of the darkness. There's no need to see anything — just observe what is there."

Auditory and somatic cycling steps are unaffected. The underlying mechanism (meta-awareness priming) does not require seeing imagery. Lucid dreaming is possible for aphantasics — visual dreams are present, though potentially less vivid.

---

## Edison Mode Expectations

Hypnagogic imagery is involuntary and uses a separate pathway from voluntary visualization — Edison Mode may be the user's **primary access to visual mental content**. However, research (Krempel & Monzel 2024) indicates involuntary imagery is somewhat reduced in aphantasics — dreams are fewer and qualitatively less vivid than controls. Set expectations accordingly, but the N1 detection mechanism (alpha dropout + theta surge) is fully functional.

---

## EEG Baseline Notes

From Boere et al. 2025 (first group EEG study of aphantasia, n=62):
- **Reduced P300 amplitude** during visual oddball tasks — decreased attentional engagement with visual events
- **Lower frontal delta power** during high-load working memory — reduced reliance on internal imagery
- Delta power correlates with VVIQ score across participants

**Implication for `eeg_engine.py`:** This user's resting and task-related EEG will show measurable differences from population norms that BrainFlow's ML models were trained on. Reduced P300 and lower frontal delta are baseline characteristics, not noise or artifact — do not "correct" them. A personalized baseline measurement during the first EEG session is essential before any state classification is reliable.

IAF calibration is unaffected (alpha peak frequency is a spectral property independent of imagery vividness).

---

## Feature Impact Summary

| Feature | Impact | Notes |
|---------|--------|-------|
| IAF Calibration | None | Spectral measurement, imagery-independent |
| 40 Hz GENUS | None | Bottom-up sensory pathway; V1 intact and responsive |
| Binaural / Isochronic entrainment | None | Auditory pathway unaffected |
| Visual display layers | **Beneficial** | External input bypasses the top-down deficit entirely. More valuable for this user, not less. |
| HRV Coherence Breathing | None | Autonomic pathway |
| Agent prompt design | **High — adapted** | See rules above. Hard constraints. |
| Affirmation content | Moderate — adapted | Kinesthetic/conceptual over visual |
| SSILD visual cycle step | Minor — adapted | Reframe as attending to darkness quality |
| Edison Mode | Low–Moderate | Detection works; content may be less vivid |
| Trance depth scoring | Moderate | Personalized EEG baseline required before classification is reliable |
| State-dependent encoding | None | Operates on brainwave state, not imagery content |

---

## Speculative Note (Long-Term — No Claims Made)

The deficit is weak frontoparietal-to-visual connectivity, not missing hardware. The visual processing pipeline is intact and populated with unconsciously generated data (Knight et al. 2026). Whether sustained visual entrainment combined with the kind of alpha/theta training Somna provides could incrementally strengthen this connection over months of use is an open question — no study has tested this. Somna's session logging with EEG would capture sufficient data for retrospective analysis if something changes. No promises. No therapeutic claims.

---

## References

- Boere et al. (2025). First group EEG study of aphantasia. *Scientific Reports*.
- Liu et al. (2025). Aphantasia as functional disconnection: reduced FIN–frontoparietal connectivity. *Cortex* (7T fMRI).
- Kutsche et al. (2025). Lesion network mapping: all acquired aphantasia lesion sites connected to FIN. *Cortex* (medRxiv).
- Knight, Milton & Zeman (2026). Visual working memory preserved in aphantasia. *Neuropsychologia*.
- Speed et al. (2025). Mental simulation preserved in aphantasia. *Memory & Cognition*.
- Whiteley (2021). 81% of aphantasics report visual dreams. *Philosophical Studies*.
- Krempel & Monzel (2024). Involuntary imagery also reduced in aphantasia. *Consciousness and Cognition*.
- Pearson et al. / UNSW (2025). V1 activates in aphantasia; images remain below conscious threshold.
