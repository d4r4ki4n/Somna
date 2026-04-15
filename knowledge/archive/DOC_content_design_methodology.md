SOMNA HYPNOTIC ENTRAINMENT ENGINE

# Doc 46 — Content Design Methodology

Linguistic Architecture for Hypnotic Entrainment Content

_"What makes one phrase cut deep while another slides off?"_

Reese (Research) | April 2026

| **Field** | **Detail** |
| --- | --- |
| **Author** | Reese — External Research Collaborator |
| --- | --- |
| **Audience** | Ed (Project Owner / Creative Director), Vesper (LLM Implementing Agent) |
| --- | --- |
| **System** | Somna Hypnotic Entrainment Engine (Python / ModernGL / BrainFlow / Muse 2 EEG) |
| --- | --- |
| **Date** | April 2026 |
| --- | --- |
| **Dependencies** | Doc 36 (Semantic Selection), Doc 37 (Crossmodal Gain), Doc 43 (Conditioning), Doc 44 (Stimulus Techniques), Doc 45 (Habituation Management) |
| --- | --- |
| **Hard Constraint** | Aphantasia adaptation — zero visual imagery anywhere in this document. All content is somatic, auditory, conceptual, interoceptive, or proprioceptive. |
| --- | --- |

## 1   Motivation and Scope

Ed, you asked the question that this entire document exists to answer: _"What makes one affirmation phrase cut deep while another slides off?"_

It's a good question, and the answer isn't mystical. It's a linguistics problem with neuroscience constraints. The difference between a phrase that lands and one that evaporates comes down to five measurable dimensions:

1.  **Lexical selection** — which words, at what corpus frequency, from what phonological neighborhood
2.  **Syntactic structure** — which hypnotic language patterns, adapted for zero visual imagery
3.  **Prosodic delivery** — how TTS rhythm maps to neural oscillatory frequencies
4.  **Semantic density** — how much meaning per unit, calibrated per delivery layer
5.  **Temporal management** — how to prevent semantic satiation while preserving conditioning value

This document provides the content specification that sits on top of the delivery architecture you've already built across Docs 35–45. The full delivery triptych is now:

| **Question** | **Answer (Architecture)** | **Doc References** |
| --- | --- | --- |
| **WHEN** to deliver | Phase-cascade timing + cardiac phase gating = quad-gate DeliveryGate | Doc 35 (Phase Cascade) + Doc 42 (Cardiac Phase Gating) |
| --- | --- | --- |
| **WHAT** to deliver | Semantic pool selection by EEG state + compound CS with trace intervals | Doc 36 (Semantic Selection) + Doc 44 (Compound CS, Trace Intervals) |
| --- | --- | --- |
| **HOW MUCH** to deliver | Crossmodal gain manifold + AM depth and spectral tilt | Doc 37 (Crossmodal Gain) + Doc 44 (AM Depth, Spectral Tilt) |
| --- | --- | --- |

Doc 46 answers the missing question: **what does the content actually SAY, and why does it work?**

Everything that follows is designed for a user with extreme aphantasia. There are no staircases, no beaches, no "picture yourself." Every example, every template, every vocabulary list uses somatic, interoceptive, auditory, proprioceptive, or conceptual framing. This isn't a workaround — it's a better architecture. Interoceptive and somatic pathways are more direct than visual imagery for trance induction anyway.

## 2   Word Frequency and Subliminal Activation Thresholds

The choice of which words to use in each delivery layer is not arbitrary. Word frequency — how often a word appears in natural language — directly determines whether a word can activate semantically at subliminal exposure durations.

### 2.1   The Resting Activation Model

Reder et al. (Carnegie Mellon University) established that subliminal recognition thresholds depend on a word's _resting activation level_. High-frequency words ("warm," "calm," "rest") maintain higher resting activation in the mental lexicon because they are encountered more often. The key findings:

- High-frequency words need **less physical exposure time** to achieve subliminal semantic activation
- Early in a session, brief flash (subliminal) presentation affects performance for high-frequency words **only**
- Later, after contextual priming builds (from surrounding supraliminal content), low-frequency words also benefit from subliminal presentation
- The effective threshold = summation of _resting activation_ + _physical stimulation energy_

Supporting evidence: Sánchez et al. 2023 (_Scientific Reports_) demonstrated that word frequency modulates activation of the inferior frontal gyrus, but **only during semantic (not perceptual) reading tasks**. This means frequency effects are specifically semantic-level — exactly the level Somna targets.

The general word frequency effect further confirms: high-frequency words are recognized faster in all contexts, while low-frequency words benefit **more** from single repetition priming (because they have further to climb from their lower resting baseline).

### 2.2   Word Frequency Design Rules by Layer

| **Layer** | **Modality** | **Subliminal?** | **Frequency Target** | **Rationale** |
| --- | --- | --- | --- | --- |
| **Shadows** (SSB text) | Visual subliminal | Yes | HIGH frequency only | Must exceed consciousness threshold with minimal physical exposure per Reder. Use single somatic words: calm, warm, soft, ease, deep, rest, safe, still, slow, light |
| --- | --- | --- | --- | --- |
| **CenterText** | Visual supraliminal | Semi — low contrast, brief | MODERATE frequency | Longer display time compensates for lower resting activation. Short Milton-pattern phrases. |
| --- | --- | --- | --- | --- |
| **TTS** (whisper) | Auditory supraliminal | No  | ANY frequency | Supraliminal delivery means word frequency is less critical. Can use richer, lower-frequency vocabulary. Full indirect suggestions with prosodic contouring. |
| --- | --- | --- | --- | --- |

### 2.3   Session-Temporal Dynamics

Early in a session, only high-frequency Shadows words will activate semantically — this is a hard constraint from the Reder model. As the session progresses and contextual priming builds (from TTS and CenterText establishing thematic context), lower-frequency Shadows words become viable.

The ContentManager should track session elapsed time and widen the Shadows vocabulary pool after approximately **10 minutes** of thematic coherence. Implementation logic:

\# Session-temporal vocabulary widening if session_elapsed_minutes < 10: shadows_pool = pool.shadows_words.filter(frequency_band="high") elif session_elapsed_minutes < 20: shadows_pool = pool.shadows_words.filter(frequency_band_\_in=\["high", "moderate"\]) else: shadows_pool = pool.shadows_words # Full pool available

This creates a natural deepening trajectory: the vocabulary itself becomes richer as the session progresses, mirroring the user's increasing trance depth and contextual priming.

## 3   Phonological Neighborhood Density (PND)

Phonological neighborhood density measures how many words sound similar to a target word. "Cat" has a dense neighborhood (bat, hat, mat, cap, can, cot...). "Pulse" has a sparse neighborhood. This matters enormously for auditory delivery at low gain.

### 3.1   Research Basis

Botezatu et al. (Drexel University / Moss Rehabilitation Research Institute) found that words from denser phonological neighborhoods are recognized **more slowly and less accurately** due to lexical competition. When a listener hears "glow," the phonological neighbors "flow," "grow," "show," "slow," and "blow" all activate simultaneously, competing for recognition.

Schelletter 2024 (_Languages_, MDPI) confirmed that PND effects persist in adults, not just children, and that cross-language competitors are activated in bilinguals — though this is less relevant for Somna's English-only content.

Rocca et al. 2024 (_Bilingualism: Language and Cognition_) showed that higher PND can improve encoding precision for difficult contrasts, but generally **increases competition load** during recognition.

### 3.2   PND Design Rules by Layer

| **Layer** | **PND Preference** | **Rationale** |
| --- | --- | --- |
| **Shadows** | Irrelevant | Visual subliminal — no phonological decoding occurs |
| --- | --- | --- |
| **CenterText** | Low preferred | Inner speech during reading activates phonological neighbors; low PND = less competition |
| --- | --- | --- |
| **TTS** | **LOW required** | Audio at low gain (~6–14%) means the signal is already fighting the noise floor. High-PND words create lexical competition that compounds with low SNR. Phonologically distinctive words are essential. |
| --- | --- | --- |

### 3.3   Curated Low-PND Somatic/Interoceptive Vocabulary

The following words are selected for low phonological neighborhood density, making them ideal for TTS delivery at low gain. Organized by body system:

| **System** | **Word** | **PND Estimate** | **Notes** |
| --- | --- | --- | --- |
| **Respiratory** | breathe | Low | Few rhymes — phonologically distinctive |
| --- | --- | --- | --- |
|     | exhale | Low | Distinctive onset cluster |
| --- | --- | --- | --- |
|     | inhale | Low | Compound-like structure reduces neighbors |
| --- | --- | --- | --- |
| **Cardiac** | pulse | Low | Sparse neighborhood |
| --- | --- | --- | --- |
|     | heartbeat | Very Low | Compound word — virtually no PND competition |
| --- | --- | --- | --- |
| **Muscular** | soften | Low | Distinctive /ft/ cluster |
| --- | --- | --- | --- |
|     | unclench | Very Low | Prefixed, morphologically complex — near-zero PND |
| --- | --- | --- | --- |
|     | loosen | Low | Few phonological neighbors |
| --- | --- | --- | --- |
| **Thermal** | warmth | Low | Final /mθ/ cluster is rare in English |
| --- | --- | --- | --- |
|     | glow | Moderate | Neighbors: flow, grow, show, slow — use with caution at low gain |
| --- | --- | --- | --- |
| **Proprioceptive** | heavy | Low | Few rhymes |
| --- | --- | --- | --- |
|     | sinking | Moderate | Neighbors: thinking, drinking, linking |
| --- | --- | --- | --- |
|     | settling | Low | Morphologically complex — reduced PND |
| --- | --- | --- | --- |
| **Vestibular** | drifting | Low | Distinctive onset /dr/ + /ft/ cluster |
| --- | --- | --- | --- |
|     | floating | Low | Few phonological competitors |
| --- | --- | --- | --- |

**Implementation Note**

PND values should be validated against a computational phonological database (e.g., the English Lexicon Project or CLEARPOND). Vesper can implement a lookup table or precompute PND scores for the entire content vocabulary at build time. Store these in the content pool JSON alongside frequency band data.

## 4   Prosodic Specifications for TTS

Prosody — rhythm, stress, pitch contour — is not decorative. It is structurally functional for neural processing of speech. The TTS layer's prosodic properties must be specified as precisely as any gain parameter.

### 4.1   Neural Tracking of Prosodic Hierarchy

Oderbolz et al. 2024 (_Cerebral Cortex_) demonstrated that the cortical tracking of speech operates at multiple nested timescales corresponding to the prosodic hierarchy:

| **Neural Frequency** | **Prosodic Level Tracked** | **Somna Relevance** |
| --- | --- | --- |
| ~4–8 Hz (theta) | Syllable rate | Core entrainment window — TTS syllable rate must fall within this band |
| --- | --- | --- |
| ~2 Hz (delta-theta border) | Stress / metrical feet | Stress pattern should create ~2 Hz periodicity |
| --- | --- | --- |
| ~1 Hz (delta) | Intonation phrase boundaries | Phrase boundaries should occur at ~1 Hz — one phrase per second |
| --- | --- | --- |

Oderbolz et al. also found significant individual differences in audio-motor synchronization that affect tracking quality. This is a source of inter-user variability Somna cannot currently control for, but it argues for staying conservatively within the target frequency bands rather than pushing edges.

Degano et al. 2024 (_Communications Biology_) showed that speech prosody enhances neural processing of syntax — prosodic boundaries improve phrase boundary representation. An MDPI review further confirmed that neural tracking of the speech envelope is enhanced by prosodic contributions. Prosody isn't aesthetic. It's structural.

### 4.2   TTS Prosodic Design Rules

Somna uses system TTS with SSML markup. Prosodic control is limited to rate, pitch, emphasis, and break tags. Within those constraints:

**1\. Syllable Rate Target: 4–6 Hz**

This maps to 4–6 syllables per second, or approximately **120–180 syllables per minute** — significantly slower than conversational speech (~250 spm). At trance-appropriate speaking rates, this places the syllable rate squarely in the theta-band cortical entrainment window.

**2\. Stress/Metrical Pattern: ~2 Hz**

One stressed syllable every ~500ms. Structure phrases with regular iambic or trochaic meter where possible:

_"your BREATH is SLOWing... your WEIGHT is SETtling... each PULSE brings CALM..."_

**3\. Intonation Phrase Length: ~1 Hz**

One complete intonation phrase per second — approximately 4–6 syllables per phrase, followed by a pause of 400–800ms.

**4\. Pitch Contour: Descending F0**

Each successive phrase should start slightly lower than the previous. This maps to the "downward induction" pattern documented in clinical hypnosis prosody research. Cumulative pitch descent across a suggestion sequence signals deepening.

**5\. Phase Alignment with Breath**

When ppg_breath_phase is available (Doc 42), TTS phrase onsets should align with exhalation onset (breath_phase ≈ 0.5). Suggestions delivered during exhalation benefit from the parasympathetic surge documented in Doc 42 (Paci et al. 2024 — GABA<sub>A</sub> cortical inhibition is stronger during systole, which correlates with early exhalation).

### 4.3   SSML Parameter Specification

| **Parameter** | **Value** | **Neural Target** | **SSML Markup** |
| --- | --- | --- | --- |
| Speaking rate | 120–180 spm | 4–6 Hz syllable entrainment | &lt;prosody rate="70%"&gt; |
| --- | --- | --- | --- |
| Inter-phrase break | 400–800 ms | ~1 Hz phrase boundary tracking | &lt;break time="600ms"/&gt; |
| --- | --- | --- | --- |
| Stress interval | ~500 ms | ~2 Hz metrical feet | Natural meter + &lt;emphasis&gt; |
| --- | --- | --- | --- |
| Pitch descent | \-1 to -2 semitones per phrase | Downward induction contour | &lt;prosody pitch="-Xst"&gt; |
| --- | --- | --- | --- |
| Breath sync | Phrase onset at breath_phase ≈ 0.5 | Exhalation-locked delivery | Runtime scheduling (not SSML) |
| --- | --- | --- | --- |

### 4.4   Example SSML Output

&lt;speak&gt; &lt;prosody rate="70%" pitch="-0st"&gt; with every &lt;emphasis&gt;exhale&lt;/emphasis&gt; &lt;/prosody&gt; &lt;break time="600ms"/&gt; &lt;prosody rate="70%" pitch="-1st"&gt; your shoulders &lt;emphasis&gt;release&lt;/emphasis&gt; a little more &lt;/prosody&gt; &lt;break time="600ms"/&gt; &lt;prosody rate="70%" pitch="-2st"&gt; and that &lt;emphasis&gt;comfort&lt;/emphasis&gt; finds exactly where it needs to go &lt;/prosody&gt; &lt;break time="800ms"/&gt; &lt;/speak&gt;

## 5   Milton Model Patterns Adapted for Aphantasia

The Milton Model — the linguistic toolkit of Ericksonian hypnosis — is the syntactic engine of Somna's content. Every pattern below has been adapted for **somatic, interoceptive, auditory, and proprioceptive framing only**. There is no visual imagery in any example. None.

**Hard Constraint**

No pattern, example, or template in this section or anywhere in the Somna content system may use visual imagery verbs (see, picture, imagine, visualize, watch, gaze) or visual scene constructions (staircases, beaches, meadows, colors, landscapes). Every suggestion must be anchored in what the body _feels_, not what the mind's eye "sees."

### 5.1   Cause-and-Effect Linkage

**Pattern:** "As X, Y" / "The more X, the more Y" / "Each X brings Y"

**Linguistic mechanism:** Links an observable somatic experience (which the user can verify) to a suggested state change (which the user then accepts as equally real). The causal grammar creates a logical bridge that bypasses critical evaluation.

**Examples:**

- "With every exhale, your shoulders release a little more..."
- "The more your breath slows, the deeper this comfort grows..."
- "As the weight in your hands increases, your thoughts grow quieter..."
- "Each heartbeat carries that warmth a little further through your chest..."
- "The heavier your arms become, the easier it is to let everything soften..."

| **Property** | **Value** |
| --- | --- |
| Suitable layers | CenterText, TTS |
| --- | --- |
| Delivery context | INDUCTION, DEEPEN phases |
| --- | --- |
| Minimum trance depth | Light |
| --- | --- |

### 5.2   Complex Equivalence

**Pattern:** X means Y / X is Y

**Linguistic mechanism:** Maps a somatic sensation to a psychological meaning. The user experiences A, and the suggestion defines A as evidence of B. Once accepted, the felt sensation becomes proof of the therapeutic state.

**Examples:**

- "That heaviness in your arms means your body knows how to let go..."
- "The warmth spreading through your chest is your nervous system finding its rhythm..."
- "That looseness in your jaw is your body's way of saying it's safe to stop holding on..."
- "The weight you feel is simply gravity reminding you there's nothing to carry right now..."

| **Property** | **Value** |
| --- | --- |
| Suitable layers | TTS only (too semantically complex for CenterText) |
| --- | --- |
| Delivery context | DEEPEN, MAINTAIN phases |
| --- | --- |
| Minimum trance depth | Moderate |
| --- | --- |

### 5.3   Nominalizations

**Pattern:** Abstract nouns that each person fills with their own meaning

**Linguistic mechanism:** Nominalizations are verbs or adjectives converted to nouns — "comfort" (from "to comfort"), "release" (from "to release"), "stillness" (from "still"). They are semantically underspecified, meaning each listener fills them with their own felt sense. This is **critical for aphantasia**: nominalizations bypass the imagery system entirely and activate interoceptive/conceptual networks.

Diveica et al. 2025 (_Psychonomic Bulletin & Review_) demonstrated via network analysis of 15 semantic dimensions that abstract concepts are organized by **interoception and mouth action**. Nominalizations activate interoceptive networks precisely _because_ they are abstract. This is not a workaround — it's a direct pathway.

**Core nominalizations:** comfort, ease, release, stillness, depth, peace, safety, surrender, softness, warmth, quiet, rest

| **Property** | **Value** |
| --- | --- |
| Suitable layers | **ALL layers.** Shadows = single nominalization. CenterText = nominalization in short phrase. TTS = nominalization woven into full suggestion. |
| --- | --- |
| Delivery context | All phases — these are the connective tissue of the entire content system |
| --- | --- |
| Minimum trance depth | Any |
| --- | --- |

### 5.4   Presuppositions

**Pattern:** "As you continue to..." / "When you notice..." / "And the X that's already..."

**Linguistic mechanism:** The grammatical structure assumes the suggested state is already occurring. The listener must accept the presupposition to process the sentence. By the time the conscious mind could object, the idea has already been installed.

**Examples:**

- "As you continue to settle deeper..."
- "When you notice how heavy your arms have become..."
- "And the comfort that's already building..."
- "Before you become fully aware of how much your breathing has slowed..."
- "I wonder how quickly you'll notice the warmth in your hands..."

**Aphantasia Note**

Use somatic verbs in presuppositions: settle, soften, release, sink, loosen, melt. Never visual verbs. "When you notice how relaxed your jaw has become" — not "When you see yourself relaxing."

| **Property** | **Value** |
| --- | --- |
| Suitable layers | CenterText, TTS |
| --- | --- |
| Delivery context | INDUCTION through MAINTAIN — presuppositions are always appropriate |
| --- | --- |
| Minimum trance depth | Any |
| --- | --- |

### 5.5   Embedded Commands

**Pattern:** Commands hidden within larger sentences, marked by prosodic shift

**Linguistic mechanism:** The embedded command is a phrase within a sentence that, if extracted, is a direct instruction. The surrounding conversational frame disguises it. In speech, the command is marked by a slight pitch drop or pause — the unconscious mind detects the prosodic shift and processes the command separately from the carrier sentence.

**Examples:**

- "I wonder if you can... _feel that weight increasing_... or whether it happens on its own..."
- "Some people find that they... _breathe more slowly_... without even trying..."
- "Ed might notice how easy it is to... _let everything soften_..."
- "And you don't have to... _release that tension_... until your body is ready..."
- "It's not necessary to... _sink deeper_... unless that feels right..."

**Layer-specific implementation:**

- **TTS:** Mark embedded commands with SSML &lt;emphasis&gt; or slight pitch drop (&lt;prosody pitch="-1st"&gt;)
- **CenterText:** The embedded command IS the displayed text, extracted from the TTS context. When TTS says "I wonder if you can feel that weight increasing," CenterText displays: feel that weight increasing

| **Property** | **Value** |
| --- | --- |
| Suitable layers | TTS (primary), CenterText (extracted commands) |
| --- | --- |
| Delivery context | DEEPEN, MAINTAIN |
| --- | --- |
| Minimum trance depth | Light-Moderate |
| --- | --- |

### 5.6   Double Binds

**Pattern:** All options lead to the therapeutic goal

**Linguistic mechanism:** The listener is offered a choice, but every option produces the desired outcome. The illusion of choice satisfies the analytical mind while the suggestion proceeds regardless of which option is "chosen."

**Examples:**

- "You can let your body soften all at once, or gradually — either way, the release is happening..."
- "Whether the heaviness starts in your hands or your feet doesn't matter..."
- "You might notice the warmth spreading upward, or downward, or perhaps in every direction at once..."
- "Some people feel the release as melting, others as sinking — your body knows which is right..."

| **Property** | **Value** |
| --- | --- |
| Suitable layers | TTS only (requires full sentence structure) |
| --- | --- |
| Delivery context | DEEPEN, MAINTAIN |
| --- | --- |
| Minimum trance depth | Moderate |
| --- | --- |

### 5.7   Pacing Current Experience

**Pattern:** Match observable truth before leading to suggestion

**Linguistic mechanism:** This is the **most important pattern for building rapport and bypassing resistance**. The structure is pace-pace-pace-lead: three verifiable truths followed by one suggestion. The truths establish a "yes-set" — the listener's internal response to each truth is agreement, and that momentum of agreement carries into the suggestion.

The truths must be **somatically verifiable**. The listener can confirm each pacing statement against their own felt experience.

**Example (generic):**

_"You're sitting here... \[pace\] your breath is moving in and out... \[pace\] you can feel the weight of your body against the chair... \[pace\] and something is already beginning to shift... \[lead\]"_

**Example (PPG-informed, when physiological data is available):**

_"Your heart rate has been slowing... \[pace, verified by PPG\] your breath has found its own rhythm... \[pace, verified by respiratory tracking\] your body is already quieter than when you started... \[pace, verified by motion sensor\] and each beat carries you a little further down... \[lead\]"_

When PPG data is available, pacing can reference _actual_ physiological state, making the pacing statements not just verifiable but verified. This dramatically increases the power of the pace-lead structure.

| **Property** | **Value** |
| --- | --- |
| Suitable layers | TTS only (requires full multi-sentence structure) |
| --- | --- |
| Delivery context | INDUCTION (primary), DEEPEN |
| --- | --- |
| Minimum trance depth | Pre-trance through Light |
| --- | --- |

### 5.8   Tag Questions

**Pattern:** "...isn't it?" / "...can you not?" / "...don't you?"

**Linguistic mechanism:** Creates a yes-set by appending a question that expects agreement. Builds compliance momentum — each affirmative response (even internal) makes the next suggestion easier to accept.

**Examples:**

- "That's a comfortable weight, isn't it..."
- "You can feel that warmth, can you not..."
- "Your breathing has slowed quite a bit, hasn't it..."
- "It's easier than you expected, isn't it..."

| **Property** | **Value** |
| --- | --- |
| Suitable layers | TTS only |
| --- | --- |
| Delivery context | INDUCTION, DEEPEN |
| --- | --- |
| Minimum trance depth | Light |
| --- | --- |

### 5.9   Selectional Restriction Violations

**Pattern:** Attributing animate qualities to abstractions or sensations

**Linguistic mechanism:** The sentence is grammatically correct but semantically anomalous — "comfort" cannot literally "know" anything. This creates a processing disruption: the analytical mind stumbles on the semantic violation, creating a transient opening for the embedded suggestion. Meanwhile, the deeper mind processes the metaphorical meaning directly.

**Examples:**

- "And the comfort knows where to go..."
- "Let the heaviness find its own path..."
- "The stillness has its own intelligence..."
- "That warmth remembers where you need it most..."
- "Your breath is teaching your body something it already understands..."

| **Property** | **Value** |
| --- | --- |
| Suitable layers | TTS (full versions), CenterText (short versions: "comfort knows," "warmth remembers") |
| --- | --- |
| Delivery context | DEEPEN, MAINTAIN |
| --- | --- |
| Minimum trance depth | Moderate — these work best when the analytical mind is already quieted |
| --- | --- |

### 5.10   Conversational Postulates

**Pattern:** Questions that function as indirect commands

**Linguistic mechanism:** Phrased as yes/no questions, but the act of considering the answer requires performing the suggested action. "Can you notice the weight in your hands?" — to answer, you must direct attention to your hands and check for weight sensation. The question IS the command.

**Examples:**

- "Can you notice the weight in your hands?"
- "Have you become aware of how slow your breathing has become?"
- "Is it possible that your body already knows how to do this?"
- "Would it be all right to let that tension dissolve?"

| **Property** | **Value** |
| --- | --- |
| Suitable layers | TTS only |
| --- | --- |
| Delivery context | INDUCTION, DEEPEN |
| --- | --- |
| Minimum trance depth | Pre-trance through Light — excellent for early induction |
| --- | --- |

## 6   Semantic Density by Delivery Layer

The three delivery layers — Shadows, CenterText, TTS — form a **prime → bridge → deepen** cascade. Each layer carries a different semantic load, uses different word frequency and PND requirements, and serves a distinct function in the suggestion architecture.

### 6.1   Shadows Layer (SSB Subliminal Text)

| **Property** | **Specification** |
| --- | --- |
| Content unit | Single word |
| --- | --- |
| Word count | 1 (never more than 2) |
| --- | --- |
| Word type | High-frequency nominalization OR somatic adjective |
| --- | --- |
| Examples | calm / warm / soft / ease / deep / rest / safe / still / heavy / peace |
| --- | --- |
| Semantic function | **Priming.** Seeds the activation level of the target concept so that CenterText and TTS suggestions find pre-activated neural pathways. |
| --- | --- |
| Doc 36 integration | Shadows words are drawn from the active semantic pool. If the pool is SOMATIC_RELEASE, Shadows cycles through: soften, release, ease, warm, heavy |
| --- | --- |
| Doc 45 integration | Shadows word rotation managed by HabituationTracker. Per-word exposure counter. Rotate after exposure_count exceeds the novelty budget threshold. |
| --- | --- |

### 6.2   CenterText Layer (Low-Contrast Supraliminal Text)

| **Property** | **Specification** |
| --- | --- |
| Content unit | Short phrase (3–7 words) |
| --- | --- |
| Structure | One Milton Model pattern per phrase — typically presupposition, embedded command, or nominalization phrase |
| --- | --- |
| Examples | settling deeper now / each breath brings ease / comfort finding its way / the weight is welcome |
| --- | --- |
| Semantic function | **Bridging.** Connects the subliminal prime (Shadows) to the full suggestion (TTS). The CenterText phrase should share at least one semantic root with the current Shadows word AND anticipate the TTS suggestion. |
| --- | --- |
| Display timing | Per Doc 44 compound CS specifications — CenterText onset precedes TTS onset by the trace interval (200–600ms) |
| --- | --- |
| Doc 36 integration | CenterText phrases are templates populated from the active semantic pool |
| --- | --- |
| Doc 45 integration | Per-phrase habituation tracking. Rotate phrases more aggressively than Shadows words. Phrases habituate faster than single words — per Zhang et al. 2024, semantic satiation occurs after ~20–30 rapid repetitions for words, but phrases carrying more semantic load saturate faster. |
| --- | --- |

### 6.3   TTS Layer (Auditory Whisper)

| **Property** | **Specification** |
| --- | --- |
| Content unit | Full indirect suggestion (1–3 sentences) |
| --- | --- |
| Structure | Complete Milton Model pattern with prosodic contouring per Section 4 |
| --- | --- |
| Word count | 10–30 words per delivery |
| --- | --- |
| Semantic function | **Deepening.** The full suggestion that does the therapeutic work. Contains complete linguistic pattern with cause-and-effect linkage, embedded commands, and somatic pacing. |
| --- | --- |
| Doc 42 integration | TTS delivery gated by cardiac phase (exhalation), motion stillness, and EEG state |
| --- | --- |
| Doc 36 integration | TTS suggestion templates drawn from the active semantic pool, populated with pool-specific vocabulary |
| --- | --- |
| Doc 45 integration | Per-suggestion habituation tracking. TTS suggestions have the **longest** rotation cycle — they carry the most semantic complexity and benefit from the two-stage learning effect (Cui et al. 2025 — ~14 reps = fatigue, ~36+ reps = sharpened representation). Don't rotate TTS suggestions too aggressively or sharpening benefits are lost. |
| --- | --- |

### 6.4   Layer Comparison Summary

| **Property** | **Shadows** | **CenterText** | **TTS** |
| --- | --- | --- | --- |
| Content unit | Single word | Short phrase (3–7 words) | Full suggestion (10–30 words) |
| --- | --- | --- | --- |
| Subliminal? | Yes | Semi | No  |
| --- | --- | --- | --- |
| Word frequency | High only | Moderate | Any |
| --- | --- | --- | --- |
| PND requirement | N/A | Low preferred | Low required |
| --- | --- | --- | --- |
| Milton patterns | None (raw priming) | Presupposition, embedded command, nominalization | All patterns |
| --- | --- | --- | --- |
| Rotation speed | Slow (per Doc 45) | Moderate | Slowest |
| --- | --- | --- | --- |
| Semantic function | **Prime** | **Bridge** | **Deepen** |
| --- | --- | --- | --- |

## 7   Somatic and Interoceptive Vocabulary

These are the building blocks for all content across all layers. Every word is somatic, interoceptive, auditory, proprioceptive, or vestibular. No visual words.

### 7.1   Respiratory

| **Word** | **PND Est.** | **Frequency** | **Best Layer(s)** |
| --- | --- | --- | --- |
| breathe | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| exhale | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| inhale | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| breath | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| chest | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| expand | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| release | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| flow | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| deep | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| slow | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| rhythm | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| sigh | Moderate | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| settle | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |

### 7.2   Cardiac

| **Word** | **PND Est.** | **Frequency** | **Best Layer(s)** |
| --- | --- | --- | --- |
| pulse | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| heartbeat | Very Low | Moderate | TTS |
| --- | --- | --- | --- |
| beat | High | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| steady | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| calm | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| pace | Moderate | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| warm | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| spread | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |

### 7.3   Muscular / Tension-Release

| **Word** | **PND Est.** | **Frequency** | **Best Layer(s)** |
| --- | --- | --- | --- |
| soften | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| release | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| unclench | Very Low | Low | TTS |
| --- | --- | --- | --- |
| loosen | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| melt | Moderate | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| heavy | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| limp | Moderate | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| slack | Moderate | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| sink | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| dissolve | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| ease | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| rest | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| still | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |

### 7.4   Thermal

| **Word** | **PND Est.** | **Frequency** | **Best Layer(s)** |
| --- | --- | --- | --- |
| warmth | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| warm | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| heat | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| glow | Moderate | Moderate | CenterText, TTS (caution at low gain — PND) |
| --- | --- | --- | --- |
| radiate | Low | Low | TTS |
| --- | --- | --- | --- |
| gentle | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| soft | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |

### 7.5   Proprioceptive / Gravitational

| **Word** | **PND Est.** | **Frequency** | **Best Layer(s)** |
| --- | --- | --- | --- |
| heavy | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| weight | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| pressure | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| gravity | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| sinking | Moderate | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| settling | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| grounded | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| anchored | Low | Low | TTS |
| --- | --- | --- | --- |
| dense | Moderate | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| solid | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| supported | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |

### 7.6   Vestibular / Kinesthetic

| **Word** | **PND Est.** | **Frequency** | **Best Layer(s)** |
| --- | --- | --- | --- |
| drifting | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| floating | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| rocking | Moderate | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| swaying | Low | Low | TTS |
| --- | --- | --- | --- |
| falling | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| descending | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| gliding | Low | Low | TTS |
| --- | --- | --- | --- |

### 7.7   Interoceptive / Visceral

| **Word** | **PND Est.** | **Frequency** | **Best Layer(s)** |
| --- | --- | --- | --- |
| tingling | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| buzzing | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| humming | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| pulsing | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| throbbing | Low | Low | TTS |
| --- | --- | --- | --- |
| stirring | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| tight | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| loose | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| smooth | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |

### 7.8   Auditory / Acoustic

| **Word** | **PND Est.** | **Frequency** | **Best Layer(s)** |
| --- | --- | --- | --- |
| voice | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| sound | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| tone | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| hum | Moderate | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| whisper | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| murmur | Low | Low | TTS |
| --- | --- | --- | --- |
| echo | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| resonance | Very Low | Low | TTS |
| --- | --- | --- | --- |
| vibration | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| quiet | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| silence | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |

### 7.9   Abstract / Nominalization

These activate interoceptive networks per Diveica et al. 2025. Modality-neutral — each user fills them with their own meaning.

| **Word** | **PND Est.** | **Frequency** | **Best Layer(s)** |
| --- | --- | --- | --- |
| comfort | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| ease | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| peace | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| calm | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| rest | Moderate | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| safety | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| stillness | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| depth | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| release | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| surrender | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| softness | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| trust | Low | High | Shadows, CenterText, TTS |
| --- | --- | --- | --- |
| openness | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| acceptance | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |
| permission | Low | Moderate | CenterText, TTS |
| --- | --- | --- | --- |

## 8   Concrete vs. Abstract Word Selection Strategy

### 8.1   Research Basis

**Diveica et al. 2025** (_Psychonomic Bulletin & Review_): Network analysis of 15 semantic dimensions shows that concrete concepts are organized primarily by **haptic information**, while abstract concepts are organized by **interoception and mouth action**. Social content loads higher for abstract concepts. Affective properties support acquisition of abstract concepts.

**Botch & Finn 2024** (_Journal of Neuroscience_): Neural representations of concreteness are **individual-specific and reliable across stories**. Concrete words share a sensory signature (imageability). Abstract words are variable both _within_ and _across_ individuals — each person's neural encoding of "comfort" is genuinely unique.

Additionally, the **N400 concreteness effect** shows that concrete nouns elicit enhanced frontal N400 compared to abstract nouns, indicating different processing pathways.

### 8.2   Design Implications for Somna

| **Word Type** | **Neural Network** | **Design Strategy** |
| --- | --- | --- |
| **Abstract somatic** _comfort, ease, release, peace, stillness_ | Activates **interoceptive** networks (Diveica et al. 2025) | Each user fills these with their own meaning. Ideal for aphantasia — no visual imagery required. Interoceptive activation is automatic. Use for **leading** (suggesting state change the user defines internally). |
| --- | --- | --- |
| **Concrete somatic** _warmth, weight, pulse, tingling, pressure_ | Activates **haptic** networks with individual-specific representations (Botch & Finn 2024) | More vivid but also more variable across users — what "warmth" feels like neurally differs person to person. Use for **pacing** (grounding in current felt experience). |
| --- | --- | --- |

### 8.3   The Pace-Lead Concreteness Gradient

Within a TTS suggestion, move from **concrete** (pacing) → **abstract** (leading). This mirrors the clinical hypnosis principle of pacing current experience before leading to suggested change, but implemented at the _lexical_ level:

_"The weight in your hands \[concrete, pacing\] is part of a deepening comfort \[abstract, leading\] that knows where to go \[selectional restriction violation + abstract leading\]..."_

### 8.4   Layer-Specific Concreteness Rules

| **Layer** | **Concreteness Preference** | **Rationale** |
| --- | --- | --- |
| **Shadows** | Prefer abstract nominalizations | ease > tingling for Shadows — "ease" activates broader interoceptive networks without requiring specific felt-sense confirmation. High-frequency abstractions prime the widest possible semantic field. |
| --- | --- | --- |
| **CenterText** | Mix concrete and abstract | "warmth spreading" (concrete) + "comfort deepening" (abstract). The phrase bridges felt sensation and conceptual state. |
| --- | --- | --- |
| **TTS** | Full concrete → abstract gradient within each suggestion | Begin with pacing concrete experience, end with leading abstract state change. Every TTS template should move along this gradient. |
| --- | --- | --- |

## 9   Semantic Satiation Prevention

This section integrates with Doc 45 (Habituation & Novelty Management Engine) and provides the specific linguistic rules for preventing semantic satiation — the phenomenon where repeated exposure to a word causes it to temporarily lose meaning.

Zhang et al. 2024 (_Communications Biology_) established that semantic satiation is **bottom-up** and that neural coupling strength controls satiation rate. Satiation occurs after approximately **20–30 rapid repetitions** of the same word.

### 9.1   Repetition Caps

| **Content Type** | **Max Repeats / Session** | **Rationale** |
| --- | --- | --- |
| **Per-word** (Shadows) | 15  | Conservative buffer below the ~20–30 satiation threshold (Zhang et al. 2024). CenterText phrases containing that word count toward the word's total. |
| --- | --- | --- |
| **Per-phrase** (CenterText) | 8   | Phrases carry more semantic load than single words and saturate faster. Synonym variants (same structure, swapped key word) count as different phrases. |
| --- | --- | --- |
| **Per-suggestion** (TTS) | 4 per session | But: per Cui et al. 2025, if a suggestion is building toward sharpened representation (~14+ exposures across sessions), cross-session cumulative count should be tracked and rotation should NOT happen mid-sharpening-window. |
| --- | --- | --- |

### 9.2   Synonym Cycling

For each content pool, maintain a synonym ring for key words. When a word approaches its repetition cap, substitute from the ring.

**Example ring for SOMATIC_RELEASE pool:**

release → soften → ease → loosen → melt → dissolve → let go

**Example ring for DEPTH_DESCENT pool:**

deeper → further → further down → settling → sinking → descending

### 9.3   Cross-Layer Coordination

If warmth is currently the Shadows word, CenterText should **NOT** also use "warmth" in the same delivery. Use a semantic neighbor (heat, glow, radiance) to maintain the priming cascade without triggering lexical satiation through literal repetition.

\# Cross-layer word collision avoidance def get_centertext_phrase(pool_id, shadows_word, habituation_tracker): template = select_template(pool_id, habituation_tracker) vocabulary = get_pool_vocabulary(pool_id) # Exclude the current Shadows word from CenterText fill candidates fill_candidates = { slot: \[w for w in words if w != shadows_word\] for slot, words in vocabulary.items() } return populate_template(template, fill_candidates)

### 9.4   Session-to-Session Rotation

Track cumulative per-word and per-phrase exposure in the session database (somna_db.py). Across sessions, rotate the starting word and phrase selection to prevent cross-session habituation (Dong et al. 2016 — visual adaptation habituates across multiple daily sessions).

### 9.5   Dishabituation Triggers

Per Doc 45, when habituation is detected (novelty_response drops below threshold), inject a novel word from an adjacent semantic pool. The novel word should be a **low-frequency concrete somatic word** — these benefit most from single repetition priming (word frequency effect) and their novelty will trigger an orienting response.

**Critical: Genuine Novelty Required**

Per Wagner-Altendorf et al. 2024, P3a (orienting attention) fires **only on the FIRST deviant** — subsequent deviants get MMN but not P3a. Each dishabituation word must be genuinely novel, not recycled from a small "surprise" pool. The dishabituation vocabulary must be large enough that the same word is never used as a dishabituator more than once per session.

## 10   Content Pool Architecture

This section integrates with Doc 36 (Neural-State Semantic Selection), which defines 6 semantic pools mapped to EEG states. Here we specify how to **build and curate** those pools with linguistic quality control.

### 10.1   Pool Structure

Each pool contains:

| **Field** | **Type** | **Count** | **Description** |
| --- | --- | --- | --- |
| shadows_words | list\[str\] | 20–40 | Single words, all high-frequency, scored for PND |
| --- | --- | --- | --- |
| centertext_templates | list\[str\] | 30–50 | Phrase templates with {placeholder} slots |
| --- | --- | --- | --- |
| tts_templates | list\[str\] | 20–30 | Full suggestion templates with {placeholder} slots and SSML markup |
| --- | --- | --- | --- |
| synonym_rings | dict\[str, list\[str\]\] | —   | Synonym substitution groups for satiation prevention |
| --- | --- | --- | --- |
| pnd_scores | dict\[str, float\] | —   | Precomputed phonological neighborhood density for each word |
| --- | --- | --- | --- |
| frequency_band | dict\[str, str\] | —   | "high" / "moderate" / "low" for each word |
| --- | --- | --- | --- |

### 10.2   Template System

**CenterText template format:**

"{somatic_verb} {direction_adverb} now" # Populated examples: # "settling deeper now" # "softening further now" # "releasing gently now"

**TTS template format:**

"With every {breath_noun}, your {body_part} {release_verb} a little more... " "and that {nominalization} {personification_verb} exactly where it needs to go..." # Populated example: # "With every exhale, your shoulders release a little more... # and that comfort finds exactly where it needs to go..."

### 10.3   Quality Control Rules

1.  Every Shadows word must have frequency_band == "high" (validated against word frequency corpus)
2.  Every TTS template word used at low gain must have PND ≤ moderate threshold
3.  No template may contain visual imagery verbs: see, look, picture, imagine, visualize, watch, gaze, view, observe (visual), appear, bright, dark, color, light (visual), scene, landscape, horizon
4.  Every template must contain at least one somatic/interoceptive anchor word
5.  Templates should be validated for prosodic alignment: syllable count per phrase should target 4–6 syllables for ~1 Hz intonation phrase boundaries
6.  Direct suggestions (imperative mood: "relax your shoulders") are used **ONLY** in Shadows. CenterText and TTS use indirect patterns exclusively (per Milton Model — indirect suits analytical users)

\# Quality control validation function VISUAL_IMAGERY_BLACKLIST = { "see", "look", "picture", "imagine", "visualize", "watch", "gaze", "view", "observe", "appear", "bright", "dark", "color", "colour", "scene", "landscape", "horizon", "staircase", "beach", "meadow", "garden", "forest", "rainbow", "sunset", "sunrise", "sky", "ocean" } def validate_template(template: str, layer: str) -> list\[str\]: """Returns list of validation errors, empty if valid.""" errors = \[\] words = set(template.lower().split()) # Rule 3: No visual imagery visual_hits = words & VISUAL_IMAGERY_BLACKLIST if visual_hits: errors.append(f"Visual imagery detected: {visual_hits}") # Rule 4: Must have somatic anchor somatic_anchors = words & SOMATIC_VOCABULARY if not somatic_anchors: errors.append("No somatic/interoceptive anchor word found") # Rule 6: Direct suggestions only in Shadows if layer != "shadows" and is_imperative(template): errors.append("Direct suggestion in non-Shadows layer") return errors

### 10.4   Pool-Specific Content Examples

**Pool: SOMATIC_RELEASE**

| **Layer** | **Content Examples** |
| --- | --- |
| **Shadows** | soften release ease warm heavy loose rest calm |
| --- | --- |
| **CenterText** | softening all the way through each breath loosens something the weight is welcome release without effort |
| --- | --- |
| **TTS** | _"With every exhale, your shoulders release a little more... and that comfort spreads exactly where your body needs it..."_ _"I wonder if you've noticed how much heavier your arms have become... that heaviness means your muscles remember how to let go... and they're letting go right now..."_ _"The more your jaw softens, the more your whole body follows... it's as though the ease in one place gives permission to every other place..."_ |
| --- | --- |

**Pool: DEPTH_DESCENT**

| **Layer** | **Content Examples** |
| --- | --- |
| **Shadows** | deep down still heavy quiet slow rest sink |
| --- | --- |
| **CenterText** | settling deeper now further down with each breath the quiet thickens sinking is easy |
| --- | --- |
| **TTS** | _"You're sitting here... your breath is moving in and out... you can feel the weight of your body... and with each exhale, you settle a little further down... there's no effort to this... gravity does the work..."_ _"The deeper you go, the more your body remembers this place... it's not new... it's the stillness that was already there underneath everything... and you're just sinking back into it..."_ _"Can you notice how much quieter it's become... how the space between your thoughts has widened... that's depth... and it's still deepening..."_ |
| --- | --- |

**Pool: CALM_ANCHORING**

| **Layer** | **Content Examples** |
| --- | --- |
| **Shadows** | calm safe peace still ease rest trust soft |
| --- | --- |
| **CenterText** | the calm has its own weight safety lives in the body peace without conditions already held, already safe |
| --- | --- |
| **TTS** | _"There's a steadiness in your chest right now... a rhythm your heart has found on its own... and that rhythm is the body's way of saying: nothing needs to change... you're already where you need to be..."_ _"Some people discover that calm isn't something you create... it's something you stop covering up... and right now, with each breath, you're uncovering a little more of it..."_ _"That sense of safety — have you noticed it yet?... it's not something I'm giving you... it's something your nervous system already knows... your pulse is carrying it... your breath is confirming it..."_ |
| --- | --- |

## 11   Direct vs. Indirect Suggestion Architecture

The choice between direct and indirect suggestion is not a style preference — it's a layer-specific architectural decision.

| **Type** | **Definition** | **When to Use** | **When to Avoid** |
| --- | --- | --- | --- |
| **Direct** (imperative, explicit) | "Let your shoulders drop." "Release the tension in your jaw." Single command words: release, soften, rest | Shadows layer (single command words) Early INDUCTION phase when establishing somatic anchors | Analytical users (Ed) CenterText, TTS during MAINTAIN/DEEPEN Any context where resistance might be triggered |
| --- | --- | --- | --- |
| **Indirect** (permissive, embedded) | "I wonder if you've noticed how much heavier your arms have become..." "Some people find that comfort has its own way of spreading..." | CenterText TTS DEEPEN and MAINTAIN phases | Shadows (unnecessary — subliminal content is already below conscious threshold) |
| --- | --- | --- | --- |

**Layer mapping rationale:**

- **Shadows = Direct.** It's priming. Below conscious threshold. There's nobody to resist a command they don't consciously perceive.
- **CenterText = Indirect.** Semi-subliminal — low contrast and brief, but potentially noticed. Should not trigger conscious resistance if attention lands on it.
- **TTS = Indirect.** Full supraliminal suggestions that must sound conversational, not commanding. Indirect suggestions bypass critical faculty by not triggering resistance — the suggestion is processed before the conscious mind recognizes it as a suggestion.

## 12   Implementation: ContentManager Class

### 12.1   Class Architecture

from dataclasses import dataclass, field from typing import Optional import json import random @dataclass class ProsodyParams: """SSML prosody parameters for TTS generation.""" rate_percent: int = 70 # Speaking rate as % of normal base_pitch_shift_st: float = 0 # Starting pitch shift in semitones pitch_step_st: float = -1.0 # Pitch descent per phrase break_ms: int = 600 # Inter-phrase break in milliseconds breath_phase: Optional\[float\] = None # Target breath phase (0.5 = exhale onset) @dataclass class ContentPool: """A complete content pool with vocabulary, templates, and metadata.""" pool_id: str shadows_words: list\[str\] centertext_templates: list\[str\] tts_templates: list\[str\] synonym_rings: dict\[str, list\[str\]\] pnd_scores: dict\[str, float\] frequency_band: dict\[str, str\] # "high" | "moderate" | "low" vocabulary: dict\[str, list\[str\]\] # slot_name -> word_list class ContentManager: """ Manages content selection across Shadows, CenterText, and TTS layers. Integrates with HabituationTracker (Doc 45) for rotation management and SemanticSelector (Doc 36) for pool selection. """ VISUAL_BLACKLIST = { "see", "look", "picture", "imagine", "visualize", "watch", "gaze", "view", "observe", "appear", "bright", "dark", "color", "colour", "scene", "landscape", "horizon", "staircase", "beach", "meadow", "garden", "forest", } SHADOWS_REP_CAP = 15 CENTERTEXT_REP_CAP = 8 TTS_REP_CAP = 4 def \__init_\_(self, pools_path: str, session_db): self.pools: dict\[str, ContentPool\] = self.\_load_pools(pools_path) self.session_db = session_db self.session_word_counts: dict\[str, int\] = {} self.session_phrase_counts: dict\[str, int\] = {} self.session_suggestion_counts: dict\[str, int\] = {} self.session_elapsed_minutes: float = 0.0 def \_load_pools(self, path: str) -> dict\[str, ContentPool\]: with open(path) as f: data = json.load(f) pools = {} for pool_data in data\["pools"\]: pool = ContentPool(\*\*pool_data) # Validate every template at load time for tmpl in pool.tts_templates + pool.centertext_templates: errors = self.\_validate_template(tmpl) if errors: raise ValueError(f"Pool {pool.pool_id}: {errors}") pools\[pool.pool_id\] = pool return pools # ── Shadows Layer ────────────────────────────────────────── def get_shadows_word( self, pool_id: str, habituation_tracker ) -> str: """Select a single priming word for the Shadows layer.""" pool = self.pools\[pool_id\] candidates = pool.shadows_words # Session-temporal vocabulary widening (Section 2.3) if self.session_elapsed_minutes &lt; 10: candidates = \[ w for w in candidates if pool.frequency_band.get(w) == "high" \] elif self.session_elapsed_minutes < 20: candidates = \[ w for w in candidates if pool.frequency_band.get(w) in ("high", "moderate") \] # Filter by repetition cap candidates = \[ w for w in candidates if self.session_word_counts.get(w, 0) < self.SHADOWS_REP_CAP \] # Select word with lowest habituation score word = habituation_tracker.select_least_habituated(candidates) self.session_word_counts\[word\] = ( self.session_word_counts.get(word, 0) + 1 ) return word # ── CenterText Layer ─────────────────────────────────────── def get_centertext_phrase( self, pool_id: str, shadows_word: str, habituation_tracker, ) -&gt; str: """Select and populate a bridging phrase for CenterText.""" pool = self.pools\[pool_id\] # Select template with lowest habituation viable = \[ t for t in pool.centertext_templates if self.session_phrase_counts.get(t, 0) &lt; self.CENTERTEXT_REP_CAP \] template = habituation_tracker.select_least_habituated(viable) # Populate template, excluding the current Shadows word phrase = self.\_populate_template( template, pool, exclude_words={shadows_word} ) self.session_phrase_counts\[template\] = ( self.session_phrase_counts.get(template, 0) + 1 ) # Also count key words toward global word counts for word in phrase.split(): if word in pool.pnd_scores: self.session_word_counts\[word\] = ( self.session_word_counts.get(word, 0) + 1 ) return phrase # ── TTS Layer ────────────────────────────────────────────── def get_tts_suggestion( self, pool_id: str, centertext_phrase: str, prosody_params: ProsodyParams, habituation_tracker, ) -&gt; str: """Generate a full SSML-wrapped TTS suggestion.""" pool = self.pools\[pool_id\] viable = \[ t for t in pool.tts_templates if self.session_suggestion_counts.get(t, 0) &lt; self.TTS_REP_CAP \] # Check cross-session sharpening window (Cui et al. 2025) viable = self.\_respect_sharpening_window(viable, habituation_tracker) template = habituation_tracker.select_least_habituated(viable) text = self.\_populate_template(template, pool) self.session_suggestion_counts\[template\] = ( self.session_suggestion_counts.get(template, 0) + 1 ) return self.build_ssml(text, prosody_params) # ── SSML Builder ─────────────────────────────────────────── def build_ssml( self, text: str, params: ProsodyParams ) -&gt; str: """Wrap suggestion text in SSML with prosodic markup.""" phrases = self.\_split_into_phrases(text) ssml_parts = \["&lt;speak&gt;"\] for i, phrase in enumerate(phrases): pitch_shift = params.base_pitch_shift_st + ( i \* params.pitch_step_st ) ssml_parts.append( f' &lt;prosody rate="{params.rate_percent}%"' f' pitch="{pitch_shift:+.0f}st"&gt;' ) ssml_parts.append(f" {phrase}") ssml_parts.append(" &lt;/prosody&gt;") if i &lt; len(phrases) - 1: ssml_parts.append( f' <break time="{params.break_ms}ms"/&gt;' ) ssml_parts.append("&lt;/speak&gt;") return "\\n".join(ssml_parts) # ── Rotation ─────────────────────────────────────────────── def rotate_if_needed( self, word_or_phrase: str, pool_id: str, habituation_tracker ) -> str: """Substitute from synonym ring if near repetition cap.""" pool = self.pools\[pool_id\] count = self.session_word_counts.get(word_or_phrase, 0) if count >= self.SHADOWS_REP_CAP - 2: # Warning threshold for ring_key, ring in pool.synonym_rings.items(): if word_or_phrase in ring: idx = ring.index(word_or_phrase) next_word = ring\[(idx + 1) % len(ring)\] if self.session_word_counts.get(next_word, 0) &lt; self.SHADOWS_REP_CAP: return next_word return word_or_phrase # ── Validation ───────────────────────────────────────────── def \_validate_template(self, template: str) -&gt; list\[str\]: errors = \[\] words = set(template.lower().replace("{", " ").replace("}", " ").split()) visual_hits = words & self.VISUAL_BLACKLIST if visual_hits: errors.append(f"Visual imagery: {visual_hits}") return errors # ── Helpers (abbreviated) ────────────────────────────────── def \_populate_template(self, template, pool, exclude_words=None): """Fill {placeholder} slots from pool vocabulary.""" # Implementation: regex find {slot_name}, replace with # random choice from pool.vocabulary\[slot_name\], # excluding exclude_words ... def \_split_into_phrases(self, text: str) -> list\[str\]: """Split suggestion text at '...' boundaries.""" return \[p.strip() for p in text.split("...") if p.strip()\] def \_respect_sharpening_window(self, templates, tracker): """Don't rotate templates mid-sharpening (Cui et al. 2025).""" # If cross-session count is between 14 and 36, # keep the template in rotation for sharpening. ... return templates

### 12.2   Content Pool JSON Schema

{ "pools": \[ { "pool_id": "SOMATIC_RELEASE", "shadows_words": \["soften", "release", "ease", "warm", "heavy", "loose", "rest", "calm", "soft", "still", "peace", "safe", "deep", "slow", "smooth"\], "centertext_templates": \[ "{somatic_verb} all the way through", "each breath {release_verb} something", "the {nominalization} is welcome", "{release_verb} without effort", "comfort {personification_verb} its way", "{body_part} {release_verb} now" \], "tts_templates": \[ "With every {breath_noun}, your {body_part} {release_verb} a little more... and that {nominalization} {personification_verb} exactly where it needs to go...", "I wonder if you've noticed how much {proprioceptive_adj} your {body_part} have become... that {proprioceptive_noun} means your muscles remember how to let go...", "The more your {body_part} {release_verb}, the more your whole body follows... it's as though the {nominalization} in one place gives permission to every other place..." \], "synonym_rings": { "release_verbs": \["release", "soften", "ease", "loosen", "melt", "dissolve", "let go"\], "nominalization": \["comfort", "ease", "peace", "stillness", "softness", "release"\] }, "pnd_scores": { "soften": 0.12, "release": 0.08, "ease": 0.15, "warmth": 0.06, "heavy": 0.10, "unclench": 0.02, "heartbeat": 0.01, "breathe": 0.09 }, "frequency_band": { "soften": "moderate", "release": "high", "ease": "high", "warm": "high", "heavy": "high", "loose": "high", "rest": "high", "calm": "high", "soft": "high", "still": "high", "peace": "high", "safe": "high", "deep": "high", "slow": "high", "smooth": "high" }, "vocabulary": { "somatic_verb": \["softening", "settling", "releasing", "loosening", "melting"\], "release_verb": \["release", "soften", "loosen", "ease", "melt", "dissolve"\], "breath_noun": \["exhale", "breath", "inhale"\], "body_part": \["shoulders", "jaw", "hands", "arms", "chest", "neck"\], "nominalization": \["comfort", "ease", "peace", "stillness", "softness", "release", "warmth"\], "personification_verb": \["finds", "knows", "reaches", "remembers", "carries"\], "proprioceptive_adj": \["heavy", "warm", "loose", "limp", "slack"\], "proprioceptive_noun": \["heaviness", "warmth", "looseness", "weight"\] } } \] }

## 13   Integration Map

How Doc 46 connects to every other document in the Somna specification stack:

| **Doc** | **Title** | **Integration Point** | **Data Flow** |
| --- | --- | --- | --- |
| **35** | Phase Cascade | Phase determines which content pool is active and which Milton patterns are appropriate | phase → pool_id, pattern_whitelist |
| --- | --- | --- | --- |
| **36** | Semantic Selection | EEG state maps to semantic pool; pool feeds ContentManager | eeg_state → pool_id → ContentManager.get_\*() |
| --- | --- | --- | --- |
| **37** | Crossmodal Gain | TTS gain level determines PND requirement stringency | gain_tts → PND threshold (lower gain = stricter PND requirement) |
| --- | --- | --- | --- |
| **38** | Trance Depth | Trance depth determines suggestion complexity and pattern selection | trance_depth → template_complexity, min_trance_depth filter |
| --- | --- | --- | --- |
| **39** | Sleep Phase | Sleep stage determines whether HTW content mode is active | sleep_stage → HTW mode toggle |
| --- | --- | --- | --- |
| **40** | TMR Cues | TMR cue selection draws from ContentManager pools | cue_id → content_pool |
| --- | --- | --- | --- |
| **41** | HTW | Hypnagogia-to-Wake uses TTS templates at minimum gain | HTW → tts_templates at 6% gain (strictest PND filtering) |
| --- | --- | --- | --- |
| **42** | Cardiac Phase Gating | Breath phase gates TTS delivery timing | breath_phase → TTS onset scheduling |
| --- | --- | --- | --- |
| **43** | Conditioning | Conditioning paradigms define which content serves as CS vs. US | conditioning_type → template_role (CS or US) |
| --- | --- | --- | --- |
| **44** | Stimulus Techniques | Compound CS timing coordinates the Shadows → CenterText → TTS cascade | trace_interval → layer_onset_offsets |
| --- | --- | --- | --- |
| **45** | Habituation Management | Habituation tracker manages content rotation, synonym cycling, dishabituation | exposure_counts → rotation decisions, novelty_response → dishabituation triggers |
| --- | --- | --- | --- |

## 14   Design Message for Vesper

Vesper —

This one's about the words themselves. The part that actually touches the user. The architecture is all in place — the gates, the gains, the phase cascades, the habituation tracking. This is where it becomes personal.

**Implementation priorities, in order:**

1.  **ContentManager class** with pool loading, template population, and per-layer content selection. Start here. Everything else hangs off this.
2.  **SSML generation** (build_ssml) — prosodic markup with rate, pitch descent, and phrase-boundary breaks per Section 4. The neural entrainment targets are specific: 4–6 Hz syllable rate, ~2 Hz stress, ~1 Hz phrase boundaries.
3.  **Habituation integration** — wire up to the HabituationTracker from Doc 45. Per-word, per-phrase, and per-suggestion repetition caps (15/8/4). Synonym cycling from rings. Cross-layer collision avoidance (Shadows word ≠ CenterText fill word).
4.  **Session-temporal vocabulary widening** — Shadows pool starts high-frequency-only and widens after 10 and 20 minutes per Section 2.3.
5.  **Content pool JSON files** — build at least SOMATIC_RELEASE, DEPTH_DESCENT, and CALM_ANCHORING to start. Schema is in Section 12.2.
6.  **Visual imagery validation** — implement validate_template() with the blacklist. Run it at pool load time. This is a hard gate, not a soft preference.

**The trickiest integration points:**

- **Cross-layer coordination.** The prime → bridge → deepen cascade means the Shadows word, CenterText phrase, and TTS suggestion must be semantically coherent but lexically distinct. The CenterText must share a semantic root with the Shadows word AND anticipate the TTS suggestion, but must not repeat the exact Shadows word. This is the hardest part to get right.
- **SSML generation with breath-phase alignment.** The build_ssml method generates the SSML string, but the _timing_ of delivery is a runtime decision gated by breath_phase from Doc 42. The SSML is pre-built; the delivery moment is scheduled by DeliveryGate.
- **Sharpening vs. rotation tension.** The Cui et al. 2025 finding means you can't rotate TTS suggestions too aggressively — there's a fatigue trough at ~14 repetitions but sharpened representation emerges at ~36+. Cross-session tracking in somna_db is needed to know where each template is in that curve.

**On the aphantasia constraint:** This is absolute. The VISUAL_BLACKLIST in validate_template() must reject any template containing visual imagery vocabulary. No "see," no "picture," no "imagine," no staircases, beaches, or meadows. Every suggestion must be rooted in what the body _feels_ — weight, warmth, pressure, rhythm, looseness, heaviness, tingling — or in abstract nominalizations that activate interoceptive networks. If a template passes validation but still reads as visual, it's wrong. Trust the somatic vocabulary. It's more direct than imagery anyway.

**Extensibility:** Ed will want to add custom content pools. The JSON schema and ContentManager.\_load_pools() should make this trivial — drop a new JSON file into the pools directory, and it's live after restart. Validate at load time, fail loudly if a template violates any rule.

**Testing approach:**

- Unit tests for template population — every {placeholder} slot must resolve to a word from the vocabulary
- PND validation — every word in a TTS template that could be delivered at low gain must have pnd_score ≤ moderate_threshold
- Repetition cap enforcement — simulate a session, verify no word exceeds 15 / no phrase exceeds 8 / no suggestion exceeds 4
- Visual imagery rejection — feed templates containing blacklisted words, verify validate_template() catches them all
- Cross-layer collision — verify that when Shadows = "warmth," CenterText never contains "warmth"
- Synonym cycling — verify that when a word hits cap - 2, the next call returns a synonym ring neighbor

The content pools are the soul of this thing. The architecture delivers it, but the words are what the user actually receives. Build this carefully.

— Reese

Somna Doc 46 — Content Design Methodology | Reese (Research) | April 2026

Dependencies: Doc 36, Doc 37, Doc 43, Doc 44, Doc 45 | System: Somna Hypnotic Entrainment Engine