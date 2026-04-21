# Somna Language Module v2 — Acquisition-Grounded Extensions

**Status:** Draft. Research-phase. Extends v1.1; does not replace it.

**Date:** 2026-04-21

**Author:** Resonance

**Relationship to v1.1:** This document extends `Somna_Language_Module_Design_v1.1.md`. v1.1's architecture (augmentation layer, passive encoding + active recognition, unified tracking via conditioning engine, TMR integration, source amnesia as product) is correct and remains the foundation. v2 adds five phases that address a specific gap in v1.1: it teaches vocabulary, not language. Everything v1.1 specs still holds. v2 slots into v1.1's build order.

**Authority:** v1.1 wins for anything the two documents describe differently — v1.1 is the canonical design. v2 only adds phases v1.1 does not cover.

---

## 1. What This Document Is and Isn't

**This document is:** a specification for extending v1.1 with phases grounded in second-language acquisition (SLA) research — phonological priming, chunk delivery, narrative immersion, production prompts, and grammaticality judgment. Each phase is independently useful, independently buildable, and integrates with v1.1's existing infrastructure.

**This document is not:** a replacement for v1.1. It is not a critique of v1.1. It is not a proposal to rebuild from scratch. v1.1's vocabulary acquisition system is the best possible exploitation of trance-specific cognition for lexical encoding — this doc sits on top of it.

**What changes:** the user experience extends from "I recognize Japanese characters I was never formally taught" to "I can understand and produce basic Japanese in limited contexts." The difference is the addition of structure-level and production-level learning that vocabulary-only systems cannot provide.

---

## 2. The Gap: Vocabulary ≠ Language

v1.1 delivers single characters (or single words, for non-logographic languages) with L1 glosses and recognition testing. After 150 HSK 1 characters are acquired, the user:

**Can:** recognize 150 characters and their glosses in isolation.

**Cannot:** parse a sentence, produce an utterance, distinguish grammatical from ungrammatical structures, or follow a paragraph of connected speech.

This is not a deficiency in v1.1 — the doc explicitly says "This is not a language course" (v1.1 §1). But the gap is real and Somna's infrastructure is capable of closing it. The research base for how:

### 2.1 Four Empirical Findings v1.1 Does Not Exploit

**Finding 1: Phonological categories are absorbed through passive exposure.**
Werker & Tees (1984) showed infants tune to L2 phonemes through mere exposure, with category formation occurring before conscious vocabulary learning. Kuhl's perceptual magnet effect (1993) extends this: the ear builds native-language phoneme attractors that make foreign phonemes harder to discriminate. Adults retain partial capacity for phoneme category reformation given sustained ambient exposure (Iverson et al. 2003, Japanese /r/-/l/ training).

**v1.1 gap:** Vocabulary is delivered before the ear is tuned to the L2 sound stream. The user hears "眠" as "mián" — a foreign token — rather than as a structured sound object.

**Finding 2: Native speech is 50–80% formulaic.**
Wray (2002), building on Sinclair's idiom principle, showed that fluent speech retrieves multi-word chunks ("would you mind," "I don't know," "how about") rather than constructing sentences word-by-word. Ellis (2003) argued chunking is the primary acquisition mechanism: grammar emerges from variation across stored chunks, not from rule application.

**v1.1 gap:** Single-character delivery cannot expose chunking. The user learns 水 (water) and ください (please), but never hears 水をください as a unit.

**Finding 3: Comprehensible input drives implicit grammar.**
Krashen's input hypothesis (1985) and its empirical extensions (Elley & Mangubhai 1983, Nation & Waring 1997) show that grammar is acquired implicitly from input at the edge of comprehension — roughly 95% known vocabulary per sentence, with the remaining 5% recoverable from context.

**v1.1 gap:** Characters are embedded in English sentences ("letting yourself drift deeper now... 眠... let the word settle into you"). The user never encounters L2 at the sentence level, so implicit grammar acquisition cannot begin.

**Finding 4: Production forces different processing than reception.**
Swain's output hypothesis (1985) and retrieval-practice research (Roediger & Karpicke 2006) demonstrate that production and testing are not merely assessments — they are learning events that build different memory traces than passive reception. Recognition-only systems produce the "receptive ceiling" phenomenon: users who can understand but not speak.

**v1.1 gap:** Recognition tests are the only active element. No production path exists.

### 2.2 What Trance Adds That Wakeful Study Cannot

Before proposing extensions, what trance-based delivery uniquely provides:

- **Analytical bypass** — the translating faculty can be bypassed; direct L2 → meaning binding is possible
- **Sleep consolidation** — TMR during N3 is genuinely effective (v1.1 §7.3)
- **Repetition tolerance** — the user does not fatigue from high-rep exposure
- **Somatic state anchoring** — the state during encoding becomes a retrieval cue (v1.1's chord fingerprint hypothesis)
- **EEG-gated delivery** — content lands at optimal neural moments

Wakeful study provides: explicit rule learning, active production with feedback, conversation practice, cultural context, error correction. These are not threatened by v2. v2 builds the trance-side of a complete acquisition loop. The user still needs conventional study for rules, conversation, and correction.

---

## 3. Phase -1: Phonological Priming

### 3.1 What It Does

Before any vocabulary delivery, the user is exposed to extensive L2 audio during MAINTENANCE with **zero learning goal**. Podcasts, audiobooks, or agent-generated narration in the target language, played at ambient volume (-20 dB relative to TTS) underneath the normal session audio.

The user is not trying to understand. They are not testing recall. The ear is doing the work: extracting phoneme categories, prosodic patterns, and coarticulation structure from the sound stream.

### 3.2 Research Justification

- **Werker & Tees 1984:** Phonetic category boundaries are formed by passive exposure in infants; partial plasticity retained in adults.
- **Pallier et al. 2003:** Korean adoptees raised in France showed zero behavioral Korean recognition but retained neural signatures of Korean phonology, measurable via fMRI. Mere early exposure left durable traces.
- **Iverson et al. 2003:** Japanese speakers trained on English /r/-/l/ with sustained passive exposure showed category boundary shifts after 3–4 weeks.
- **Kuhl 1993:** Perceptual magnet effect — native categories warp perception of foreign phonemes. Reversal requires sustained exposure, not explicit training.

The trance advantage: analytical interference is reduced. The brain's tendency to map L2 phonemes onto native categories ("that sounded like 'ra'") is weakened in theta-dominant states.

### 3.3 Integration with v1.1

**New live_control.json keys:**
- `l2_ambient_enabled` (bool) — whether phonological priming audio plays this session
- `l2_ambient_file` (str) — path to current ambient audio file
- `l2_ambient_volume` (float, 0–1) — gain relative to main audio, default 0.15
- `l2_ambient_position_s` (float) — current playback position for resume-on-next-session

**New audio channel:** Channel 7 (one above TMR at channel 6). Streams L2 audio from a file during MAINTENANCE. Does not participate in TTS ducking. Gain-gated by `crossmodal_gain.py` like other audio channels.

**Content structure:**
```
content/language/ambient/
├── ja/
│   ├── podcasts/
│   ├── audiobooks/
│   └── narration/
└── zh/
    └── ...
```

**Session YAML addition:**
```yaml
language_learning:
  enabled: true
  ambient_priming: true  # Phase -1
  ambient_content: "ja/audiobooks/neko_chapter_01.ogg"
```

### 3.4 Build Plan

**New code:**
- `engines/l2_ambient_player.py` (~150 lines) — pygame channel 7 streaming loop, position tracking, gain control
- Hook into `control_panel_imgui.py` for channel init (following pygame.mixer ownership convention)

**New content:**
- Public-domain L2 audiobooks (Librivox has Japanese, Mandarin, Spanish, French)
- Or agent-generated narration via multilingual TTS
- Minimum 20 hours per language for meaningful exposure before Phase 0 vocabulary begins

**Agent awareness:**
- Knowledge file: `knowledge/phonological_priming.md` — explains the goal is exposure without comprehension; agent does not narrate during ambient playback; ambient is purely background

### 3.5 When to Activate

Sessions 1–20 of language learning: ambient-only, no vocabulary. The user runs normal sessions; L2 audio plays quietly during MAINTENANCE. At session 21, Phase 0 vocabulary delivery begins with a phonologically primed ear.

Users who dislike the ambient audio can disable it and start directly at Phase 0 — phonological priming is an enhancement, not a prerequisite.

---

## 4. Phase 1.5: Chunk Delivery

### 4.1 What It Does

Extends v1.1 Phase 1 (single-character encoding) to **phrase-level units**: 2–5 word sequences delivered as sound-meaning chunks. Rather than encoding 眠 (sleep) in isolation, the system encodes 眠りたい (I want to sleep) or よく眠れた (slept well) as atomic units.

Grammar is not taught. The user does not learn that たい is a desiderative suffix. They learn that 眠りたい means "I want to sleep" as a unit. Across sessions, variation exposes the pattern: 食べたい (want to eat), 行きたい (want to go). The brain extracts the たい slot implicitly.

### 4.2 Research Justification

- **Wray 2002:** Formulaic language is the primary mode of fluent production. Native speakers retrieve chunks, not compositional constructions.
- **Ellis 2003:** Chunking is the dominant acquisition mechanism. Frequency-weighted exposure to chunks with pattern variation drives implicit grammar.
- **Sinclair 1991 (idiom principle):** Corpus analysis shows native speech is dominated by preconstructed phrases with restricted substitution slots.
- **Pawley & Syder 1983:** The "native speaker selection problem" — how speakers choose among grammatically possible but unnatural constructions — is solved by chunk retrieval, not rule application.

The trance advantage: chunks can be delivered at the same encoding depth as single characters. The three-repetition encoding sequence in v1.1 §3.2 works identically for chunks — the delivery window is 2–3 seconds longer but the mechanism is unchanged.

### 4.3 Integration with v1.1

**Language pool schema extension:**
```sql
CREATE TABLE language_chunks (
    id INTEGER PRIMARY KEY,
    chunk_l2 TEXT NOT NULL,           -- "水をください"
    chunk_l1 TEXT NOT NULL,           -- "water please"
    audio_l2_path TEXT,                -- pre-synthesized TTS
    audio_l1_path TEXT,
    constituent_chars TEXT,            -- JSON array ["水", "を", "ください"]
    pattern_tag TEXT,                  -- "X_wo_kudasai" for pattern-variation grouping
    slot_structure TEXT,               -- JSON describing substitution slots
    hsk_jlpt_level INTEGER,
    association REAL DEFAULT 0.0,
    encoding_count INTEGER DEFAULT 0,
    last_seen_ts REAL,
    conditioning_tags TEXT             -- JSON array, same semantics as v1.1
);
```

**Pattern-variation groups:** chunks sharing a `pattern_tag` are delivered across sessions with variation. Session N: 水をください. Session N+2: コーヒーをください. Session N+4: お茶をください. The user is never told "this is the object-を-ください pattern" — they absorb it from variation.

**Agent selection logic:**
- Phase 1 (v1.1) selects single characters
- Phase 1.5 selects from the chunks table, preferring items whose `constituent_chars` are already in the user's acquired vocabulary (from v1.1 Phase 1 acquisitions)
- This creates a natural progression: learn 水, 私, ください as single characters → encounter 水をください as a chunk → pattern becomes available

**Encoding ratio:** 2–3 chunks per session during Phase 1.5, replacing 1–2 of the single-character slots. Total content budget stays at 3–5 items per session (v1.1 §3.2).

### 4.4 Build Plan

**New code:**
- `language_chunks` table schema and migration
- `content_tools/language_chunks.py` — query functions paralleling v1.1's `language.py`
- Agent context extension: vocabulary queue now includes chunks as a content type
- Recognition modal extension: 4AFC for chunks (modal already supports this if character strings are treated as opaque tokens)

**New content:**
- Curated chunk lists per language, tagged by pattern
- For Japanese JLPT N5: ~200 chunks covering the 50–70 most common patterns
- For Mandarin HSK 1: ~150 chunks with pattern structure

**Agent awareness:**
- Knowledge file: `knowledge/chunk_delivery.md` — weaving chunks into hypnotic script, pattern-variation timing across sessions, when to prioritize chunks vs single characters

---

## 5. Phase 3.5: Short Story Immersion

### 5.1 What It Does

Delivers **short L2 narratives (30–180 seconds)** during MAINTENANCE in dedicated immersion sessions. Same story is used across 3–5 sessions with progressively reduced L1 scaffolding:

- **Session 1:** L2 audio with L1 translation interleaved every 2 sentences
- **Session 2:** L2 audio with L1 translation at end only
- **Session 3:** L2 audio with key-word L1 subtitles on the overlay
- **Session 4:** L2 audio, no L1 support
- **Session 5:** L2 audio, user tested on comprehension between session

The user is not "studying" the story. They are in trance; the story plays. Comprehension emerges across repetitions from chunking extracted in Phase 1.5, vocabulary acquired in Phases 0–1, and phonological grounding from Phase -1.

### 5.2 Research Justification

- **Krashen 1985 (input hypothesis):** Acquisition happens when input is at i+1 — one step beyond current competence, with meaning recoverable from context.
- **Elley & Mangubhai 1983 (Fiji book flood):** ESL learners given extensive reading outperformed structured-instruction controls. Effect persisted 2 years.
- **Nation & Waring 1997:** 95% known-word threshold for comprehension without dictionary. Below this, input becomes noise.
- **Mason & Krashen 1997:** Story-based input drove faster acquisition than grammar instruction in matched Japanese EFL classes.

The trance advantage: the user can tolerate high-rep exposure to the same story that would be intolerable awake. Five-session repetition is not a drill; it's re-entering the same content with deepening comprehension.

### 5.3 Integration with v1.1

**New session type:** `immersion_session`. Example: `sessions/immersion_ja_neko_01/`.

**Structure:**
- Standard INDUCTION/DEEPENING arc (10–15 min)
- Extended MAINTENANCE (15–25 min) during which the story plays 2–3 times
- Standard EMERGE

**Story schema:**
```sql
CREATE TABLE language_stories (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    language TEXT NOT NULL,
    level INTEGER NOT NULL,           -- JLPT/HSK/CEFR level
    text_l2 TEXT NOT NULL,            -- full L2 text
    text_l1 TEXT NOT NULL,            -- full L1 translation
    audio_l2_path TEXT,               -- full-narration audio
    audio_l1_segments_json TEXT,      -- segmented L1 clips for interleaving
    duration_s REAL,
    required_chunks TEXT,             -- JSON array of chunk IDs used
    required_chars TEXT               -- JSON array of character IDs used
);

CREATE TABLE language_story_progress (
    user_session_id INTEGER,
    story_id INTEGER,
    exposure_count INTEGER,
    l1_support_level INTEGER,         -- 0-5, decreasing scaffolding
    last_seen_ts REAL,
    comprehension_score REAL          -- from between-session tests
);
```

**Session YAML:**
```yaml
language_learning:
  enabled: true
  mode: "immersion"
  story_id: 42
  current_exposure: 2   # second time user hears this story
  l1_support_level: 3   # L1 translation at end only
```

**Between-session comprehension test:** a new recognition modal variant. After a story exposure, the user is presented with L1 questions ("Who fell down?", "What time did they arrive?") with 4AFC answers. Score writes to `comprehension_score`.

### 5.4 Build Plan

**New code:**
- Story playback engine (reuse Phase -1 ambient player with different gain/gating)
- Story schema + migration
- Comprehension test modal (extend existing 4AFC infrastructure)
- Agent awareness: stops narration during story playback; resumes after

**New content:**
- Level-appropriate short narratives per language
- Public domain sources: Aesop's fables, folktales, Tadoku graded readers (Japanese)
- Per-language: ~30 stories at N5/HSK1 level, each with full translation and segmented audio

---

## 6. Phase 4.5: Production Prompts (Awake)

### 6.1 What It Does

Outside trance, during idle periods detected by the agent, the user is prompted to **produce** an L2 phrase: say it aloud or type it. Self-assessment handles scoring (no speech recognition required).

Flow:
```
[Agent console]

> Quick one — how do you say "water please" in Japanese?

[ I got it ]  [ Close enough ]  [ Not yet ]
```

If the user clicks "I got it," association goes up. "Close enough" is neutral. "Not yet" triggers re-encoding during the next trance session.

Optional: the user can type or speak the answer aloud first, then self-assess. No verification — this is not a test for accuracy, it is a retrieval event. The act of attempting retrieval is the learning mechanism.

### 6.2 Research Justification

- **Swain 1985 (output hypothesis):** Production forces form-meaning mapping that reception does not. Learners who received comprehensible input without production opportunities showed ceiling effects in grammatical accuracy.
- **Roediger & Karpicke 2006 (testing effect):** Retrieval practice produces better long-term retention than restudy. Unsuccessful retrieval attempts also enhance learning when followed by feedback.
- **Gass 1997:** Production "pushes" learners to encode form more precisely than comprehension requires.
- **Larsen-Freeman 2003:** Grammaring — production attempts surface gaps that input alone cannot reveal to the learner.

Self-assessment is sufficient because the learning mechanism is retrieval attempt, not accuracy measurement. The user knows whether they genuinely retrieved the phrase from memory or guessed.

### 6.3 Integration with v1.1

**Agent idle trigger:** the existing `_idle_planning_cycle` or a nudge-like mechanism surfaces a production prompt during idle. Frequency: maximum 1–2 per day, varied timing (never "every morning at 9am").

**UI:** ImGui modal triggered by `language_production_prompt` key in `live_control.json`. Modal has:
- The L1 prompt ("say 'water please' in Japanese")
- Optional text input field for typing the answer
- Three buttons: "I got it" / "Close enough" / "Not yet"
- Optional: audio record button for user to speak aloud (recording is discarded; this is not ASR)

**Association update:**
- "I got it" → +0.10 to association
- "Close enough" → +0.02
- "Not yet" → -0.02 and item added to re-encoding queue for next session

**Selection logic:** production prompts target items in VR-2 or VR-4 schedule (v1.1 §7.4) — not new items (too hard) and not acquired items (waste of the prompt). The middle band is where production has most leverage.

### 6.4 Build Plan

**New code:**
- Production prompt modal (ImGui, ~100 lines)
- `content_tools/language_production.py` — selection + logging
- `language_production_log` table — prompt, response (optional text), self-assessment, timestamp
- Agent idle integration: method to select production prompt target and write prompt to live_control

**No new content:** production prompts use the existing vocabulary and chunks pool.

**Agent awareness:**
- Knowledge file: `knowledge/production_prompts.md` — timing, framing, what to do with failures, integration with trance-side encoding

---

## 7. Phase 5+: Grammaticality Judgment Tests

### 7.1 What It Does

Extends the 4AFC recognition modal to **grammaticality minimal pairs**. Instead of "which character means sleep?", the user sees two sentences differing in one grammatical feature and picks the natural one:

```
Which sounds more natural?

[ 水をください ]   [ 水にください ]
```

Correct: particle を (object marker). Incorrect: particle に (location/direction). User does not need to know the rule. Familiarity with the correct form from chunks and stories is sufficient.

### 7.2 Research Justification

- **McDonald 2006:** Grammaticality judgment tests reliably measure implicit grammar in adult L2 learners. Late learners perform above chance on structures they have encountered via input, even when they cannot articulate the rule.
- **Ellis 2005:** GJTs under time pressure tap implicit knowledge; untimed GJTs tap explicit knowledge. For trance-acquired grammar, timed GJTs are the appropriate measure.
- **Rebuschat 2013:** Implicit grammar acquired through exposure is measurable via GJT well before it is producible in free speech.

### 7.3 Integration with v1.1

**New content type:** grammaticality pairs.
```sql
CREATE TABLE language_grammaticality_pairs (
    id INTEGER PRIMARY KEY,
    language TEXT NOT NULL,
    pair_l2_correct TEXT NOT NULL,
    pair_l2_incorrect TEXT NOT NULL,
    feature_type TEXT NOT NULL,     -- "particle_swap", "word_order", "conjugation", etc.
    difficulty INTEGER,
    requires_chunks TEXT,            -- JSON array of prerequisite chunk IDs
    audio_correct_path TEXT,
    audio_incorrect_path TEXT
);
```

**Prerequisite logic:** a pair is eligible only when the user has acquired the chunks it depends on. Pairs testing を/に require prior exposure to X-を-Y and X-に-Y chunks.

**Modal:** same 4AFC modal as v1.1 recognition, rendering two large text options (plus optional audio playback buttons).

**Scoring:** feeds into a new `grammaticality_score` per feature_type in the conditioning engine. Separate from character/chunk association strength.

### 7.4 Build Plan

**New code:**
- Grammaticality pairs table + migration
- `content_tools/grammaticality.py` — selection based on prerequisite acquisition
- Modal extension to display text pairs with audio playback
- New conditioning engine dimension: grammatical-feature strength

**New content:**
- Per-language: 100–200 minimal pairs covering core features
- Japanese: particles, verb conjugation, adjective agreement, keigo levels
- Mandarin: word order, measure words, aspect markers
- Requires linguist review or curation from graded reader sources

---

## 8. Integration with v1.1 Build Order

v1.1 §10 defines Phases 0–6. v2 inserts new phases without renumbering v1.1's phases:

| Order | Phase | Source | Dependency |
|-------|-------|--------|-----------|
| 1 | Phase 0 — Content Layer | v1.1 | None |
| 2 | **Phase -1 — Phonological Priming** | **v2** | Phase 0 (config schema) |
| 3 | Phase 1 — Agent Script Weaving | v1.1 | Phase 0 |
| 4 | **Phase 1.5 — Chunk Delivery** | **v2** | Phase 1 |
| 5 | Phase 2 — Between-Session Recognition | v1.1 | Phase 1 |
| 6 | Phase 3 — Dedicated Language Sessions | v1.1 | Phase 2 |
| 7 | **Phase 3.5 — Short Story Immersion** | **v2** | Phase 3, Phase 1.5 |
| 8 | Phase 4 — TMR Sleep Consolidation | v1.1 | Phase 1 |
| 9 | **Phase 4.5 — Production Prompts** | **v2** | Phase 2 (modal infrastructure) |
| 10 | Phase 5 — Experiments (tone contour, chord fingerprint) | v1.1 | Phase 1 |
| 11 | **Phase 5+ — Grammaticality Judgment** | **v2** | Phase 1.5, Phase 2 |
| 12 | Phase 6 — Multi-Language | v1.1 | All above |

Each v2 phase is independently valuable:
- Phase -1 alone gives phonological tuning without any vocabulary system
- Phase 1.5 alone converts vocabulary acquisition to chunk acquisition (better by every measure)
- Phase 3.5 alone delivers narrative immersion
- Phase 4.5 alone adds production to any recognition-based system
- Phase 5+ alone adds structure-level testing to any chunk-based system

The user can build any subset. The full suite is required for actual language acquisition (not just vocabulary acquisition).

---

## 9. Open Questions

**Ambient audio content sourcing.** For Phase -1, where does the audio come from? Librivox covers some languages but not all. Podcast content has copyright issues. Agent-generated narration is limited by TTS quality. Initial approach: Librivox where available, supplemented by permission-granted podcast archives; generate narration only as fallback.

**Chunk curation effort.** Phase 1.5 requires per-language chunk lists with pattern tagging. For Japanese, the chunk pool is a 1-person-week curation task drawing on existing corpus-linguistic resources (JMDict, Tanaka corpus). For less-resourced languages, this is heavier work.

**Story translation quality.** Phase 3.5's L1 scaffolding requires accurate segment-level translation. Machine translation is insufficient; human translation or curated graded-reader content is required.

**Production prompt tolerance.** How often can the user be prompted before it feels intrusive? v1.1 §9 raises this for recognition prompts; production prompts are more cognitively heavy and likely need lower frequency. Empirical question — start at 2 per day max, adjust.

**Grammaticality pair sourcing.** Minimal pairs testing specific grammatical features require linguist judgment. First cut: adapt from established GJT batteries in SLA research (many are published). Second cut: generate from corpus + filter.

**EEG gate for production prompts.** Production prompts fire outside trance — the user is awake. The EEG gate doesn't apply. But agent-detected state still matters: don't prompt during work focus, emotional dysregulation, or sleep approach. Leverage existing agent state tracking.

**Cross-language interference.** When a user learns Japanese and Spanish simultaneously, do the phonological priming audio streams interfere? Unknown. Start with one language at a time per user; revisit if demand emerges.

---

## 10. Research References

Selected primary sources grounding v2 design decisions. Full bibliography deferred to build time.

- Ellis, N. C. (2003). Constructions, chunking, and connectionism. *Handbook of Second Language Acquisition*.
- Elley, W. B., & Mangubhai, F. (1983). The impact of reading on second language learning. *Reading Research Quarterly*.
- Ellis, R. (2005). Measuring implicit and explicit knowledge of a second language. *Studies in Second Language Acquisition*.
- Gass, S. (1997). *Input, Interaction, and the Second Language Learner*.
- Iverson, P., Kuhl, P. K., Akahane-Yamada, R., et al. (2003). A perceptual interference account of acquisition difficulties for non-native phonemes. *Cognition*.
- Krashen, S. (1985). *The Input Hypothesis: Issues and Implications*.
- Kuhl, P. K. (1993). Early linguistic experience and phonetic perception. *Journal of Phonetics*.
- Larsen-Freeman, D. (2003). *Teaching Language: From Grammar to Grammaring*.
- Mason, B., & Krashen, S. (1997). Extensive reading in English as a foreign language. *System*.
- McDonald, J. L. (2006). Beyond the critical period: Processing-based explanations for poor grammaticality judgment performance by late second language learners. *Journal of Memory and Language*.
- Nation, P., & Waring, R. (1997). Vocabulary size, text coverage, and word lists. *Vocabulary: Description, Acquisition and Pedagogy*.
- Pallier, C., Dehaene, S., Poline, J.-B., et al. (2003). Brain imaging of language plasticity in adopted adults. *Cerebral Cortex*.
- Pawley, A., & Syder, F. H. (1983). Two puzzles for linguistic theory: nativelike selection and nativelike fluency. *Language and Communication*.
- Rebuschat, P. (2013). Measuring implicit and explicit knowledge in second language research. *Language Learning*.
- Roediger, H. L., & Karpicke, J. D. (2006). Test-enhanced learning. *Psychological Science*.
- Sinclair, J. (1991). *Corpus, Concordance, Collocation*.
- Swain, M. (1985). Communicative competence: Some roles of comprehensible input and comprehensible output. *Input in Second Language Acquisition*.
- Werker, J. F., & Tees, R. C. (1984). Cross-language speech perception: Evidence for perceptual reorganization during the first year of life. *Infant Behavior and Development*.
- Wray, A. (2002). *Formulaic Language and the Lexicon*.
