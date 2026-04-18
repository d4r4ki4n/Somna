# Somna Language Module — Design Document

Status: Draft. Research-phase. No code yet.

Date: 2026-04-17
Author: Resonance
Revised by: Resonance + Reese (audit integration)

---

## 1. Design Philosophy

Four principles, derived from research gaps and UX requirements:

**Language is an augmentation layer, not a session type.** Vocabulary delivery is a toggle that augments any session the user is already running. A "language session" is just a session designed with vocabulary encoding in mind — but vocabulary can also surface during a sleep session, a conditioning session, or any other session type. This makes language acquisition ambient, continuous, and decoupled from session selection.

**Passive encoding, active recognition.** The user never "studies" during a session. Vocabulary is woven into the hypnotic flow the same way affirmations are — the user experiences a normal Somna session where Chinese words happen to surface. All testing is deferred to between sessions and uses recognition (choosing from options) rather than recall (producing from memory). This is grounded in the finding that explicit recall is impaired during trance but recognition and implicit memory survive intact (Kihlstrom, 1997; Barnier et al., 2001).

**Source amnesia is the product.** Hypnosis research consistently shows that information learned under trance is retained but the source is forgotten. The user knows what 眠 means without remembering being taught. This is not a bug — it is the desired user experience. Vocabulary appears in the user's mind as if they always knew it. The system should not fight this; it should optimize for it.

**Experimental features are flags, not foundations.** The tone-contour hypothesis (binaural FM maps to tonal categories) and the chord-fingerprint hypothesis (state-dependent recall via specific interference patterns) are both theoretically coherent but empirically untested. Neither should be load-bearing in the architecture. Both should be toggleable, measurable, and removable without breaking the core loop.

---

## 2. Architecture: Language as Augmentation

### 2.1 The Language Toggle

A single boolean in `user_settings.json` (or per-session in `session.yaml`):

```yaml
language_learning:
  enabled: true
  target_language: "mandarin"
  level: 1           # HSK level
  items_per_session: 3
  include_review: true
```

When `enabled: true`, the language module injects vocabulary into whatever session is running. The session itself doesn't change — the conductor runs its normal phase arc, the agent speaks its normal script, the visuals render normally. The language module just adds vocabulary items to the content queue alongside affirmations.

This means:
- A "First Light" induction session with language enabled still feels like First Light — gentle, gradual. Three characters surface during deepening. The user doesn't perceive a mode change.
- A "Somna Deep" session with language enabled uses the same theta-heavy chord that's already optimal for hippocampal encoding. The vocabulary fits naturally.
- A sleep session with language enabled delivers TMR vocabulary cues during SWS alongside conditioning cues.
- A dedicated "HSK 1 — Theta Encoding" session is just a session YAML tuned for vocabulary (long deepening phase, theta-dominant beats, language-optimized timing). It's not a different system — it's a session that happens to be well-suited for language.

The toggle also means language can be turned off instantly. If the user wants a pure trance session with no vocabulary, they turn it off. The session is unchanged.

### 2.2 What Flows Through Existing Pipes

Language content uses the same delivery mechanisms as affirmations. **Content queue priority:** when a delivery window opens and both affirmation and vocabulary items are queued, priority depends on phase. During DEEPENING, vocabulary takes priority (encoding is time-sensitive; affirmations can wait). During MAINTENANCE, affirmations take priority (reinforcement vocabulary is single-rep and can interleave). The `semantic_selector.py` already handles pool-weighted selection — extend it with a `language_priority` weight that the conductor phase sets.

Delivery channels:

| Delivery Channel | Affirmation Path | Language Path |
|-----------------|------------------|---------------|
| Agent voice (TTS) | `next_affirmation` | `next_language_item` (same queue, different source) |
| Overlay text | `agent_message` with text | Character + pinyin rendered as overlay |
| Subliminal whisper | SSB channel | English meaning via SSB |
| VR depth plane | Existing subliminal renderer | Character on depth plane |
| Sleep TMR | `tmr_cue_registry` | Same table, `source='language'` |
| Reinforcement schedule | Conditioning engine VR schedules | Same schedules, association strength |

No new IPC channels. No new delivery mechanisms. Language content flows through the same pipes as everything else. The only new code is the content selection logic: which characters to deliver, when, and how often.

### 2.3 Multi-Language Path

The augmentation architecture makes multi-language support trivial. The schema is language-agnostic:

```yaml
language_learning:
  enabled: true
  target_language: "japanese"  # or "spanish", "french", etc.
  level: 5                      # JLPT N5, CEFR A1, etc.
```

Each language has its own pool table (`language_pool_mandarin`, `language_pool_japanese`) and its own content files. The delivery mechanism, reinforcement schedules, TMR integration, and recognition testing are identical. Adding a new language means:
1. Create the pool table
2. Import the word list
3. Write a language-specific knowledge file for the agent (pronunciation notes, script-weaving guidance)
4. Verify TTS pronunciation for the target language

The core module doesn't change. This is why language-as-augmentation matters — it's a platform feature, not a module.

---

## 3. The Session Experience

What the user actually experiences, minute by minute.

### 3.1 The Session Is Unchanged

With language enabled, the session should not feel different from any other Somna session. There is no "study mode." There is no quiz during the session. The user lies down, puts on headphones, and goes under. The language content is woven into the existing hypnotic flow.

### 3.2 Minute-by-Minute Walkthrough

**Minutes 0–5: Induction (unchanged)**
Standard Somna induction. Spirals, binaural beats, breath entrainment. The agent's voice guides the user deeper. No language content yet — the user needs to reach trance before encoding begins.

**Minutes 5–15: Deepening (language encoding begins)**
The conductor transitions to DEEPENING. Trance depth exceeds 0.5 (the hippocampal encoding threshold). The agent begins weaving vocabulary into the hypnotic script:

> *"...letting yourself drift deeper now... 眠... let the word settle into you... sleep... 眠... you don't need to remember it... just let it find its place..."*

The experience for the user:
- The agent says the Chinese word aloud (TTS, clear pronunciation)
- The character appears on screen (overlay or VR depth plane)
- The English meaning is delivered as a subliminal whisper (SSB channel)
- The binaural beat continues at the encoding frequency (theta range)
- The agent's script flows naturally — no pause, no "now we will learn a word"

**TTS pre-synthesis:** Mandarin pronunciation cannot be generated on-the-fly by switching the TTS voice mid-stream — the latency would break delivery timing. All session vocabulary pronunciations are pre-synthesized into a language-specific audio buffer during CALIBRATION or early INDUCTION, then served from that buffer during DEEPENING. This follows the same pattern as the HTW whisper system, which pre-synthesizes into a `_presynth_ready` buffer with a separate voice profile.

This is delivered for 3–5 items per session. Each item gets three repetitions with decreasing intervals (8s → 4s → 2s), queued as a burst sequence. The first repetition is fully gate-checked (respiratory phase, cardiac phase, SQI, trance depth). Once the first gate opens, repetitions 2 and 3 fire on their own ISI schedule without individual gate checks — the gate validated the window, the ISI owns the burst timing. This follows the same pattern as `center_text.py`'s flash sequences, where the first flash is gate-triggered and subsequent flashes follow their own duty cycle. All repetitions are breath-gated to exhalation. The character is visible during repetitions and fades between them.

The key: **the user does nothing.** They lie there. The words come in. The experience is indistinguishable from a normal session where the agent happens to be speaking Chinese sometimes.

**Minutes 15–25: Maintenance (brief reinforcement)**
Previously encoded characters from earlier sessions surface briefly — one repetition each, woven into the maintenance script. The agent might say:

> *"...drifting in this deep place where 眠 feels as natural as breathing..."*

No testing. No questions. Just one more exposure to strengthen the trace.

**Minutes 25–30: Emergence (unchanged)**
Standard emergence. The user returns to normal awareness. The session ends.

**Between sessions: Recognition prompt (see §4)**

### 3.3 What VR Changes

In VR, the character can be rendered:
- On the bubble membrane (expanding/contracting with breath)
- At a specific depth plane (near/mid/far) using the existing subliminal depth system
- With gaze tracking: the system can detect when the user's eyes fixate on the character, measuring dwell time as an implicit engagement signal

On desktop, the character appears as overlay text in the center of the display, same as affirmation text. Less immersive but fully functional.

---

## 4. Testing — Between Sessions

### 4.1 The Recognition Prompt

Testing happens between sessions, not during. When the user launches Somna (or after a session ends), the agent delivers a recognition prompt in the console:

> *Agent: "Hey — quick one. Which of these means 'sleep'?"*
>
> `[ 眠 ]  [ 醒 ]  [ 梦 ]  [ 走 ]`

The user clicks one. Takes 2 seconds. This is a four-alternative forced-choice (4AFC) recognition test, but it feels like a casual conversation with the agent, not a quiz.

Correct → association strength += 0.15
Incorrect → association strength -= 0.05

The distractors are chosen intelligently: other characters the user has seen, or characters with similar pinyin/tones that test discrimination. Never random characters from later HSK levels.

### 4.2 Why Recognition, Not Recall

Recall ("what does 眠 mean?") requires:
- Active verbalization or typing
- Conscious retrieval of information encoded in an altered state
- Breaking whatever state the user is in

Recognition ("which of these means 'sleep'?") requires:
- A single click
- Familiarity judgment, which is preserved during and after trance
- No state disruption

The research is clear: explicit recall is impaired by hypnosis and state mismatch. Recognition is robust. The module optimizes for what works.

### 4.3 The Casual Framing

The recognition prompt should never feel like homework. Variations:

- *"Quick — do any of these look familiar?"* (first exposure to a character)
- *"Last session you heard this one. Still got it?"* (reinforcement check)
- *"I said this word last night while you were sleeping. Wild, right?"* (post-TMR check)
- *No prompt at all* (the agent skips testing some days to maintain natural feel)

The agent handles the framing through its existing conversational personality. No separate "quiz mode."

### 4.4 Progress Visibility

The user needs to see progress without a dashboard. Options:

- The agent mentions it naturally: *"You've been recognizing 眠 consistently — it's settling in."*
- A lightweight console status line: `HSK 1: 12/150 · 8 strong · 4 learning`
- The Interference Graph shows encoded characters as markers (see §6.2)

No formal progress dashboard. No gamification badges. The information is ambient.

---

## 5. Day-by-Day Learning Arc

### 5.1 Week 1

| Day | Session | New Items | Reinforcement | Night TMR |
|-----|---------|-----------|---------------|-----------|
| 1 | Any session (language on) | 3 new characters | None | All 3 characters during SWS |
| 2 | Any session (language on) | 3 new characters | Day 1 characters (1 rep each) | Day 1 + Day 2 (6 total) |
| 3 | Recognition prompt only | 0 new | Recognition test for days 1–2 | Failed items replayed |
| 4 | Any session (language on) | 3 new characters | Days 1–2 (brief) | Cumulative |
| 5 | Any session (language on) | 3 new characters | Days 1–3 (brief) | Cumulative |
| 6 | Recognition prompt only | 0 new | Recognition test for all | Failed items |
| 7 | Rest day — no session | 0 | TMR only if sleep monitoring active | Failed items |

End of week 1: ~15 characters exposed, ~8–10 with association > 0.3 (partially learned), ~3–5 with association > 0.6 (solid).

Note: "Any session" means whatever session the user chooses to run. The language toggle is on, so vocabulary surfaces during deepening and maintenance regardless of session type. A dedicated language session (Phase 3 of the build) would be optimized for vocabulary encoding, but it's not required.

### 5.2 The Conditioning Schedule

Vocabulary reinforcement follows the existing conditioning engine schedules:

| Association Strength | Schedule | Frequency |
|---------------------|----------|-----------|
| 0.0–0.3 (new) | CRF (every session) | Every session |
| 0.3–0.6 (learning) | VR-2 | Every other session |
| 0.6–0.8 (solid) | VR-4 | Every 4th session |
| 0.8+ (acquired) | VR-6 | Every 6th session |

Items that drop below 0.3 (three consecutive recognition failures) are re-encoded: a full 3-repetition encoding sequence in the next session, as if the character were new.

### 5.3 HSK 1 Timeline

HSK 1 = 150 characters. At 3 new per session, 3 sessions per week = ~9/week. ~17 weeks to first exposure of all 150. But with reinforcement and sleep consolidation, early characters should be acquired (association > 0.8) by week 4–5.

Realistic timeline: **4–5 months to solid HSK 1 recognition.** This is comparable to Duolingo's pace for HSK 1, but the user is lying down with their eyes closed instead of tapping a phone screen.

---

## 6. Content Model

### 6.1 Language Pool Schema

```json
{
  "char": "眠",
  "pinyin": "mián",
  "tone": 2,
  "meaning": "sleep",
  "freq_tag": "theta",
  "hsk_level": 1,
  "association": 0.45,
  "chord_fingerprint": {
    "audio_hz": 6.0,
    "visual_hz": 5.0,
    "spread": 0.0
  },
  "encoding_count": 2,
  "last_recognition_correct": true,
  "last_seen_ts": 1713169200.0,
  "tmr_eligible": true
}
```

Fields:
- `char`, `pinyin`, `tone`, `meaning`, `hsk_level` — static, set at import
- `freq_tag` — optimal entrainment band for encoding. Theta for most vocabulary. Delta for deep encoding of difficult items. Alpha for review/reinforcement (lighter state, easier retrieval)
- `association` — 0.0–1.0, cached from the conditioning engine (see §7.4). The primary metric of acquisition
- `chord_fingerprint` — recorded at first encoding. Used by the chord-fingerprint experiment (§6.2). Optional; system works fine without it
- `encoding_count` — how many full encoding sequences this item has received
- `last_recognition_correct` — most recent test result. Used to detect declining items
- `last_seen_ts` — timestamp of most recent exposure (encoding or reinforcement)
- `tmr_eligible` — whether this item should be queued for sleep TMR delivery

### 6.2 Word Lists

HSK 1 (150 characters) as the inaugural set. Organized by thematic clusters that map to Somna's existing content themes:

| Cluster | Example Characters | Semantic Link |
|---------|-------------------|---------------|
| Sleep & consciousness | 眠 梦 醒 觉 | Core Somna vocabulary. Learned first. |
| Body & sensation | 气 息 温 柔 | Somatic focus vocabulary. |
| Depth & descent | 深 下 落 沉 | Matches induction language. |
| Time & flow | 时 流 过 化 | Matches timeline/session concepts. |
| Elements | 水 火 风 光 | Matches visual layer themes. |

Thematic clustering is not just pedagogically sound — it means the vocabulary the user is learning aligns with what they're experiencing in the session. The agent says "deeper" while the character for "deep" is on screen. The encoding is cross-modal by nature.

### 6.3 Conditioning-Theme Vocabulary Selection

The vocabulary queue is driven by the session's conditioning theme, not the session type. **Themed vocabulary is not gated by HSK level.** A surrender-themed session may draw characters from HSK 3–5 if the thematic match is strong (e.g., 降 yield, 从 obey). The HSK level setting controls the *session-agnostic* pool and the pace of systematic curriculum progression. Themed vocabulary operates outside that gate — the user encounters thematically resonant characters regardless of their curriculum position, because the conditioning context provides the encoding scaffold that compensates for the character being "above level."

Somna sessions carry conditioning themes — the narrative and emotional content the session delivers. A bimbofication session conditions toward vanity and airheadedness. A surrender session conditions toward letting go. A focus session conditions toward attention. The language module matches vocabulary to the conditioning theme so that the words reinforce the conditioning and the conditioning reinforces the words.

| Conditioning Theme | Vocabulary Cluster | Example Characters |
|-------------------|-------------------|-------------------|
| Bimbofication | Vanity, beauty, emptiness | 美 (beautiful), 空 (empty), 柔 (soft), 甜 (sweet) |
| Surrender / submission | Letting go, yielding, depth | 沉 (sink), 下 (down), 落 (fall), 去 (go/away) |
| Focus / concentration | Attention, clarity, sharpness | 明 (bright), 看 (look), 大 (big), 中 (center) |
| Sleep / drift | Sleep, dreams, fade | 眠 (sleep), 梦 (dream), 暗 (dark), 静 (still) |
| Pleasure / sensation | Body, warmth, feeling | 热 (hot), 好 (good), 多 (much/many), 小 (small) |
| Identity / self | I, you, become, change | 我 (I), 你 (you), 变 (become), 化 (transform) |

This does double duty:
- **Conditioning reinforces vocabulary.** The word for "sink" is encoded while the user is experiencing the sensation of sinking. The somatic state is the mnemonic.
- **Vocabulary reinforces conditioning.** Hearing "沉" (sink) in Chinese while being guided to sink deeper adds a second semantic channel to the conditioning. **Hypothesis (untested):** the foreign word may bypass the critical faculty more easily than the native word — the user's analytical mind doesn't have a cached response to "沉" the way it does to "sink," so the conditioning may land cleaner. This is plausible (unfamiliar stimuli receive less analytical processing) but unverified. The conditioning-theme vocabulary concept stands on its own merit — cross-modal reinforcement and somatic state as mnemonic — without requiring this claim to be true.

For **live sessions** (agent-directed, no preset session), the agent selects vocabulary based on its current plan. The agent's `_interactive_tick` already produces a state summary and intention. The language module provides an API: `items_for_theme(agent_intent, n, hsk_level)`. The agent passes its current intent ("deepening toward surrender") and receives vocabulary that matches. The agent then weaves these characters into its live script.

This means even a freeform live session teaches thematic vocabulary without the user ever configuring it. The agent reads the moment, picks the words, delivers them.

Implementation:
- Each HSK 1 character gains a `conditioning_tags` field (list of strings, like the existing image tag system)
- Tags overlap with session themes: `["vanity", "emptiness", "softness"]`, `["surrender", "depth", "yielding"]`, etc.
- `items_for_encoding(n, hsk_level, conditioning_tags)` prioritizes items whose tags overlap with the session's theme
- Fallback: when thematic items are exhausted, draw from session-agnostic pool (weakest association first)
- The agent's live intent maps to the same tag vocabulary, so live sessions use the same selection path

### 6.4 Session-Agnostic Pool

Not all vocabulary maps to a conditioning theme. Numbers, pronouns, common verbs, abstract nouns — these form a session-agnostic pool that the agent draws from when the thematic queue is exhausted or when no theme is active. This pool also serves as the source for between-session recognition tests, which shouldn't be biased toward any particular theme.

Both pools share the same `language_pool` table. The `conditioning_tags` field distinguishes them: `NULL` or empty for agnostic items, populated for themed items.

### 6.5 Storage

Language pool stored in `somna.db` as a `language_pool` table, not in flat files. This allows:
- Efficient querying by association strength, HSK level, last-seen timestamp
- Integration with existing TMR and conditioning tables
- Cross-session persistence without file I/O races

Schema:
```sql
CREATE TABLE language_pool (
    char TEXT PRIMARY KEY,
    pinyin TEXT NOT NULL,
    tone INTEGER NOT NULL CHECK (tone BETWEEN 0 AND 4),  -- 0 = neutral tone (e.g., 的 de, 了 le, 吗 ma, 子 zi)
    meaning TEXT NOT NULL,
    freq_tag TEXT NOT NULL DEFAULT 'theta',
    hsk_level INTEGER NOT NULL DEFAULT 1,
    association REAL NOT NULL DEFAULT 0.0,
    chord_fingerprint TEXT,  -- JSON blob
    encoding_count INTEGER NOT NULL DEFAULT 0,
    last_recognition_correct INTEGER,  -- NULL = never tested
    last_seen_ts REAL,
    tmr_eligible INTEGER NOT NULL DEFAULT 1,
    cluster TEXT  -- thematic cluster name
);

CREATE TABLE language_recognition_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    char TEXT NOT NULL,
    presented_meaning TEXT NOT NULL,  -- what was shown as the prompt
    distractors TEXT NOT NULL,  -- JSON array of distractor characters
    correct INTEGER NOT NULL,  -- 1 = correct, 0 = incorrect
    response_time_ms INTEGER,  -- time from prompt to click
    session_context TEXT,  -- 'between_session', 'console', 'vr_gaze'
    ts REAL NOT NULL
);
```

---

## 7. System Integration

### 7.1 Agent Integration

The agent is the delivery mechanism. It already:
- Speaks to the user via TTS
- Writes overlay text via `agent_message`
- Injects single affirmations via `next_affirmation`
- Reads the conductor's phase state to decide content

Language items are injected into the existing affirmation flow. The agent receives:
- The current vocabulary queue (items to encode this session)
- The reinforcement queue (items to briefly repeat)
- The user's progress summary (for contextual conversation)

When language is enabled, the agent's content selection logic gains a second source alongside affirmations. During DEEPENING, the agent interleaves vocabulary with its normal script. During MAINTENANCE, it weaves in brief reinforcement repetitions. The agent never enters a "language mode" — it just has more content to draw from.

A knowledge file (`knowledge/language_delivery.md`) provides the agent with:
- Delivery pacing (3 reps, decreasing ISI, breath-gated)
- Script weaving guidance (how to embed characters in hypnotic flow)
- Tone pronunciation reminders (TTS needs to produce clear tonal output)
- When to use Chinese vs. L1 (Chinese first, then meaning, never the reverse)

The agent does not need to "understand" Chinese. It needs to deliver the character's pronunciation via TTS and weave it into the script. The TTS engine handles pronunciation.

### 7.2 Conductor Integration

No new conductor phases. Vocabulary delivery rides inside existing phases.

The conductor already manages phase transitions (CALIBRATION → INDUCTION → DEEPENING → MAINTENANCE) and controls delivery timing through the delivery gate (respiratory, alpha phase, cardiac, stillness). The language module uses these same windows:

**During DEEPENING** — the agent queues new vocabulary items for delivery. Trance depth gate: `trance_score > 0.5` (the hippocampal encoding threshold). The conductor doesn't know or care that the content is vocabulary rather than affirmations — it just opens delivery windows based on depth and phase.

**During MAINTENANCE** — the agent queues reinforcement items (single repetitions of previously encoded characters). Priority: items with lowest association strength first. Same delivery windows.

**No LANGUAGE_ENCODING or LANGUAGE_REINFORCE phases.** These were in the initial draft and removed. The augmentation model means the conductor's phase arc is unchanged — vocabulary is just content that flows through the existing delivery pipes during existing phases.

The conductor does gain one new `agent_conductor_hints` field:
- `language_items_ready: int` — count of vocabulary items the agent has queued for this session. The conductor can use this to extend DEEPENING or MAINTENANCE by a few minutes if items are queued but not yet delivered. Optional — if the conductor ignores it, items simply carry over to the next session.

Chord fingerprint recording happens transparently: when a vocabulary item is first encoded, the current chord state from the Interference Graph (or the current beat frequency if the graph isn't active) is written to the item's `chord_fingerprint` field. No conductor involvement required.

### 7.3 TMR Integration

Existing TMR engine + language pool items = sleep consolidation.

Each language item's audio (TTS-generated pronunciation of the character) is stored as a TMR cue. When the sleep classifier detects N2/N3 and a slow-oscillation up-state:
- Play the character pronunciation at whisper volume (lower than conditioning cues)
- Limit to 6 language cues per night (budget within the existing 20 cues/hr limit)
- Priority: items with lowest association strength that were encoded that day
- No meaning is played during sleep — only the character pronunciation

This is a minimal extension of the existing TMR engine. The `tmr_cue_registry` table gains a `source` column: `'conditioning'` or `'language'`. The engine filters by source when enforcing nightly budgets.

**Playback path distinction:** The existing TMR cue system (`tmr_cue_manager.py`) generates all conditioning audio deterministically via NumPy DSP — sine waves with MD5 hash jitter, raised-cosine envelopes, zero audio files. Language TMR cues are fundamentally different: they are pre-rendered TTS audio, not synthesized tones. The TMR engine's `play_cue()` path needs a branch: `if source == 'language': play_prerendered(audio_path)` vs the current `synthesize_and_play()` for conditioning cues. The `tmr_cue_registry` already distinguishes via `source`; the playback dispatcher consumes it.

### 7.4 Conditioning Engine Integration — Unified Tracking

Language items register as CS entries in the conditioning engine's `conditioning_associations` table with `cs_class = 'language_char'`. The existing Rescorla-Wagner machinery handles strength updates from both session encoding (US = trance state) and recognition testing (explicit reinforcement signal). The `language_pool.association` field is a cached read from the conditioning engine, not an independently maintained value.

This unified approach provides salience decay, extinction tracking, and reinforcement schedule optimization for free — all already implemented in `conditioning_engine.py` (Bible Ch.6). Language items follow the same VR schedules as conditioning content:

- `association 0.0–0.3` → CRF: item appears in every session's reinforcement queue
- `association 0.3–0.6` → VR-2: item appears every other session
- `association 0.6–0.8` → VR-4: item appears every 4th session
- `association 0.8+` → VR-6: maintenance, appears every 6th session

No separate association tracking system. One Rescorla-Wagner update rule for everything — conditioning content, language vocabulary, and any future content types all share the same strength model.

---

## 8. Experimental Features

These are hypotheses worth testing. None are load-bearing.

### 8.1 Tone Contour Modulation

**Hypothesis:** Modulating the binaural beat frequency to follow a Mandarin tone contour (e.g., rising for Tone 2) enhances tonal category acquisition compared to steady-state delivery.

**Implementation:** A `ToneContourGenerator` produces a frequency trajectory array for each tone. During character encoding, the binaural beat frequency follows this trajectory instead of holding steady. The visual channel can optionally modulate photic brightness along the same contour.

**Why it might not work:** No study has tested passive frequency modulation transferring to linguistic tone categories. The musician studies show auditory training helps, but that's active training. The Baills et al. (2016) gesture study involves motor production, not passive listening.

**Experiment design:** A/B test across sessions. Group A receives characters with tone contours. Group B receives characters with steady-state theta. After 10 sessions, test tonal discrimination using minimal pairs (e.g., má vs. mǎ). Both groups get the same character exposure; only the binaural modulation differs.

**Architecture implication:** The tone contour system is a standalone module that hooks into the audio engine's frequency control. If the experiment fails, it's removed with zero impact on the core loop.

### 8.2 Chord-Fingerprint State-Dependent Recall

**Hypothesis:** Vocabulary encoded under a specific interference chord (e.g., Audio 6Hz + Visual 5Hz) is more accessible when that chord is re-induced.

**Implementation:** At encoding, the full chord state is **always recorded** as `chord_fingerprint` — this is default behavior, not an experimental toggle. Recording the chord at encoding costs nothing and the data is valuable regardless of whether the recall hypothesis holds. The *experiment* is whether to actively re-induce that chord during testing. For recognition tests in the "chord-reactivated" condition, the conductor re-enters that chord state before the test. Compare recognition accuracy and response time between chord-reactivated and neutral-state tests.

**Why it might not work:** State-dependent memory is well-established for drug states and emotional states. It has not been tested for specific oscillatory frequency patterns. The Clouter et al. (2017) finding (theta-synced audio/visual improves associative recall) was not successfully replicated (2025 Frontiers study). The effect may be too subtle, or it may not exist for frequency-based states.

**Experiment design:** Within-subject. For each user, 50% of recognition tests happen in the encoding chord state, 50% in a neutral state. Compare accuracy and response time over 20 sessions.

**Architecture implication:** The chord fingerprint is always recorded (default behavior). The experimental toggle controls only whether the chord is re-induced during testing. If the experiment fails, the re-induction is disabled but the recorded fingerprints remain as valuable data for future analysis.

### 8.3 Implicit Physiological Recognition

**Hypothesis:** A correctly recognized character produces a measurable physiological response (HRV micro-dip, EEG familiarity response, IMU stillness change) that can serve as an implicit recognition signal, eliminating the need for explicit user input.

**Implementation:** During maintenance, previously encoded characters flash briefly (subliminal speed, ~100ms). The system records physiological signals in a ±2s window around the flash. Compare responses to known characters vs. novel characters. If a reliable signal exists, use it as a passive recognition metric.

**Why it might not work:** Subliminal familiarity responses are documented in the literature, but extracting them from noisy consumer-grade biosensors (Muse 2/S, PPG) in real-time is unproven. The signal-to-noise ratio may be too low.

**Architecture implication:** Purely additive. If it works, recognition testing becomes invisible. If it doesn't, the explicit between-session recognition prompt remains the default.

---

## 9. Open Questions

**Encoding load.** 3–5 items per session is a guess. Too many items produces interference (proactive and retroactive inhibition during encoding). Too few makes progress glacial. The optimal number depends on the user's trance depth, the encoding duration, and individual differences in theta-mediated memory capacity. Start at 3, measure association strength after 5 sessions, adjust.

**TTS tonal accuracy.** Edge-TTS's Mandarin voices produce acceptable tones, but tonal accuracy is critical for this application. Need to verify that the TTS output for each character is phonetically correct. If the tone is wrong in the audio, the user encodes the wrong tonal category. Audit HSK 1 vocabulary against a native speaker's judgment before deployment.

**Recognition prompt fatigue.** If the user is asked to click a character every time they launch Somna, it becomes annoying. Mitigation: the agent varies the framing, skips days, and never frames it as a quiz. But this needs testing. The user's tolerance for between-session interaction is unknown.

**Non-aphantasic users.** The research doc emphasizes the aphantasia advantage, but most users will have typical imagery. The module should work for both populations. For non-aphantasic users, visual mnemonics could supplement the encoding (character paired with an evocative image from the session's image pool). This is a later enhancement.

**Sleep consolidation without EEG.** Many users won't have EEG hardware. The TMR sleep consolidation path requires sleep stage detection, which currently needs EEG. The IMU-based sleep classifier (head-nod + stillness) provides rough sleep onset detection but not reliable N2/N3 staging. For EEG-free users, sleep TMR is limited to "probably asleep" windows detected by IMU. This may be sufficient — the Salfi et al. (2025) study showed home-environment TMR works with imprecise staging.

---

## 10. Build Order

What to build first, in order, with dependencies. Each phase is independently useful.

### Phase 0: Content Layer
- `language_pool` table in `somna.db`
- HSK 1 word list import (CSV/JSON → DB)
- `content_tools/language.py` — query functions: `items_for_encoding(n, hsk_level)`, `items_for_reinforcement(schedule)`, `record_recognition(char, correct)`, `update_association(char, delta)`
- `language_learning` config block in `user_settings.json` and `agent_config.yaml`
- No runtime behavior yet. Just the data layer.

### Phase 1: Agent Script Weaving (Encoding)
- Knowledge file for language delivery (`knowledge/language_delivery.md`)
- Agent prompt context extended with vocabulary queue (alongside affirmation queue)
- `next_affirmation` mechanism extended to support language items — the agent can emit a language item instead of an affirmation during its delivery windows
- TTS Mandarin pronunciation verification for HSK 1 characters
- Pre-synthesis buffer for Mandarin TTS audio (following HTW `_presynth_ready` pattern)
- CJK font support in `font_manager.py` — verify current font includes CJK glyphs; add CJK-capable font if not; adjust text sizing for character readability
- **This makes encoding possible during any session.** The agent weaves vocabulary into whatever session is running. Encoding must exist before recognition testing is meaningful.

### Phase 2: Between-Session Recognition
- Recognition prompt in the agent console flow
- 4AFC display via new ImGui modal popup (4 large character buttons, triggered by `language_recognition_prompt` key in `live_control.json`; UI renders modal, captures click, writes result back)
- Association strength update on response (writes to conditioning engine via unified tracking, §7.4)
- Recognition log table
- **This is where the loop closes.** The user has been exposed to characters in Phase 1 sessions; now they can demonstrate recognition between sessions.

### Phase 3: Dedicated Language Sessions
- Session YAMLs designed for vocabulary encoding (extended deepening, theta-dominant beats, language-optimized timing)
- `sessions/hsk1_theta/` — first dedicated language session
- These are just session files — no new code. The infrastructure from Phase 2 does all the work.
- **This proves the concept end-to-end.** A user runs the dedicated session, vocabulary gets encoded, recognition testing happens between sessions, the full loop works.

### Phase 4: TMR Sleep Consolidation
- Language cues in the TMR engine
- `tmr_cue_registry` gains `source` column (`'conditioning'` or `'language'`)
- Sleep-stage-gated delivery with language-specific nightly budget (6 cues/night)
- Priority: lowest association items encoded that day
- **This adds the sleep consolidation loop.** Works during any sleep session with language enabled.

### Phase 5: Experiments
- Tone contour generator (§7.1)
- Chord-reactivated recognition (§7.2)
- Implicit physiological recognition (§7.3)
- A/B test infrastructure
- **Each experiment is independently toggleable.** None affect the core loop.

### Phase 6: Multi-Language
- Language-agnostic pool table schema (already designed, §5.1)
- Second language support (e.g., Japanese JLPT N5)
- Language-specific knowledge files for the agent
- TTS verification for each new language
- **This proves the platform is general.** Adding a language is content work, not engineering.
