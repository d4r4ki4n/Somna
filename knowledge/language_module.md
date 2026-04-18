# Language Module — Vocabulary Acquisition During Trance

**Status:** Specification (v1)

**Author:** Ed / Reese

**Date:** 17 April 2026

**Loaded by:** `_load_idle_knowledge()` during idle planning for vocabulary set selection; active session ticks during MAINTENANCE when language delivery is enabled

**Authority:** This file is the operational reference for the LLM agent. The authoritative design specification lives in the Language Module Design v1.1 and the Somna Bible. When this file and either document disagree, the design doc wins.

---

## 1. What the Language Module Does

The Language Module delivers foreign-language vocabulary during trance sessions, exploiting the heightened suggestibility and reduced cognitive interference of theta-dominant states to accelerate acquisition. It is an **augmentation layer** — it rides on any trance session without replacing the session's primary content.

The core insight: trance states reduce the critical faculty that normally interferes with novel phoneme acceptance and semantic binding. Vocabulary delivered during deep theta with spaced repetition and TMR reinforcement during subsequent sleep has a measurably stronger retention curve than wakeful study alone.

**This is not a language course.** It is a vocabulary delivery pipeline that pairs with conventional study. The module handles exposure, repetition scheduling, and sleep-phase consolidation. Grammar, conversation practice, and cultural context happen outside Somna.

---

## 2. Content Format

Language content is stored as JSON files in the content pool:

```json
{
  "language": "ja",
  "items": [
    {
      "id": "ja_tree_001",
      "l2": "木",
      "l2_romanization": "ki",
      "l1": "tree",
      "audio_l2": "tts_ja_ki.wav",
      "audio_l1": "tts_en_tree.wav",
      "category": "nature",
      "jlpt_level": "N5",
      "association_tags": ["grounding", "nature", "calm"]
    }
  ]
}
```

### Required Fields

| Field | Type | Purpose |
|-------|------|---------|
| `id` | string | Unique identifier for tracking across sessions |
| `l2` | string | Target language word/phrase (what the user is learning) |
| `l2_romanization` | string | Romanized pronunciation for non-Latin scripts |
| `l1` | string | Native language translation |
| `audio_l2` | string | Pre-synthesized TTS audio file path for L2 |
| `audio_l1` | string | Pre-synthesized TTS audio file path for L1 |

### Optional Fields

| Field | Type | Purpose |
|-------|------|---------|
| `category` | string | Thematic grouping for session coherence |
| `jlpt_level` | string | Difficulty level (language-specific scale) |
| `association_tags` | array | Tags connecting vocabulary to session themes |
| `mnemonic_hint` | string | Optional memory aid — somatic/auditory only, never visual |

**Aphantasia constraint:** `mnemonic_hint` must never use visualization language. "The word sounds like..." or "Feel the weight of..." — never "Picture a tree."

---

## 3. Three Delivery Modes

Language delivery progresses through three modes as the user's familiarity with each item increases. The agent selects the mode per-item based on that item's current Leitner box.

### 3.1 Paired Mode (Box 0–1: New / First Review)

Full bilingual presentation. The user hears both languages.

**Delivery sequence:**
1. TTS delivers L2 audio (`audio_l2`)
2. 1.5-second pause
3. TTS delivers L1 audio (`audio_l1`)
4. Center flash displays L2 text for 2 seconds
5. Veil displays L1 translation for 1.5 seconds

**Timing:** ~8 seconds per item including pauses.

**Purpose:** Establish the L2→L1 association. The user consciously processes both forms.

### 3.2 Prompted Mode (Box 2–3: Familiar)

L2 only with a brief L1 confirmation. The user is expected to recall the meaning.

**Delivery sequence:**
1. TTS delivers L2 audio
2. 3-second pause (recall window)
3. Center flash displays L2 text for 1.5 seconds
4. TTS delivers L1 audio (confirmation, 30% volume reduction from L2)

**Timing:** ~7 seconds per item.

**Purpose:** Shift from recognition to recall. The recall window forces active retrieval.

### 3.3 Immersive Mode (Box 4+: Well-Known)

L2 only. No L1 confirmation. The item is treated as acquired vocabulary being maintained.

**Delivery sequence:**
1. TTS delivers L2 audio
2. Center flash displays L2 text for 1 second
3. No L1 presentation

**Timing:** ~3 seconds per item.

**Purpose:** Maintenance exposure. Keeps the item active without conscious translation effort.

---

## 4. Spaced Repetition — Leitner Model

The module uses a simplified Leitner box system for scheduling item reviews:

| Box | Review Interval | Promotion Condition | Demotion Condition |
|-----|----------------|--------------------|--------------------|
| 0 | Every session | Successful delivery + no regression signal | N/A (starting box) |
| 1 | Every session | 3 consecutive clean deliveries | Any regression signal |
| 2 | Every 2 sessions | 3 consecutive clean deliveries | Any regression signal → Box 1 |
| 3 | Every 3 sessions | 3 consecutive clean deliveries | Any regression signal → Box 1 |
| 4 | Every 5 sessions | 3 consecutive clean deliveries | Any regression signal → Box 2 |
| 5 | Every 8 sessions | Maintenance only | Any regression signal → Box 3 |

### What Counts as a "Regression Signal"

The module cannot directly test recall (no quiz mechanism during trance). Regression is inferred from:

- **Delivery gate depth drop:** If `trance_score` drops > 0.15 within 10 seconds of L2 delivery, the item may have caused cognitive disruption (confusion, frustration). Flag for review.
- **FAA shift:** If `faa_value` shifts negative (avoidant) within 10 seconds of delivery, the item may be causing negative association. Flag for review.
- **No signal** is the normal case — most deliveries produce no measurable disruption. Absence of regression is promotion evidence.

### Box Assignment During Idle Planning

The agent selects vocabulary items during idle planning based on box state:

1. Query `language_items` table for items due for review (box interval met or exceeded)
2. Prioritize Box 0 items (new) — maximum 5 new items per session
3. Fill remaining slots with due Box 1–3 items (familiar, need reinforcement)
4. Add Box 4–5 items only if session duration > 45 minutes
5. Total language items per session: 8–15 depending on session length

---

## 5. Delivery Timing and Rate Limiting

### Rate Limit

**One language item per 3 minutes minimum.** This is a hard floor, not a guideline.

Language delivery is cognitively heavier than affirmation delivery — novel phonemes require processing bandwidth even in trance. Faster delivery risks:
- Cognitive overload breaking trance depth
- Interference between successive L2 items (retroactive inhibition)
- Delivery gate rejections stacking up and wasting content

### When Language Delivers

Language items enter the content delivery queue alongside affirmations, conditioning content, and reconsolidation phrases. Queue priority determines delivery order:

| Priority | Content Type | Notes |
|----------|-------------|-------|
| 1 (highest) | Reconsolidation (RETRIEVE/UPDATE) | Time-critical protocol — always first |
| 2 | Conditioning-tagged affirmations | Rescorla-Wagner timing matters |
| 3 | Standard affirmations | Core session content |
| 4 | Language items | Augmentation — never displaces core content |

Language items are delivered in the gaps between higher-priority content. If the session has dense affirmation content, language delivery naturally spaces out further than the 3-minute minimum.

### Conductor Phase Restrictions

Language delivery is **only permitted during MAINTENANCE.**

| Conductor Phase | Language Delivery |
|----------------|-------------------|
| CALIBRATION | ❌ Prohibited — establishing baseline |
| INDUCTION | ❌ Prohibited — novel stimuli disrupt entrainment |
| DEEPENING | ❌ Prohibited — cognitive load risks stalling descent |
| MAINTENANCE | ✅ Permitted — stable depth, adequate processing capacity |
| FRAC_EMERGE | ❌ Prohibited — user is surfacing |
| FRAC_EMERGE_HOLD | ❌ Prohibited — user is at surface |
| FRAC_REDROP | ❌ Prohibited — re-entering trance, same risk as INDUCTION |
| GENUS_BLOCK | ❌ Prohibited — 40 Hz gamma focus, wrong cognitive mode |
| SLEEP_* (all 5) | ❌ Prohibited — user is asleep or approaching sleep |
| SESSION_END | ❌ Prohibited — session closing |

**Exception:** TMR replay of previously-delivered language items during SLEEP_MAINTAIN is handled by the TMR cue manager, not the language delivery system. See §8.

### Delivery Gate Interaction

All language deliveries pass through the standard four-gate delivery gate:

- **Respiratory gate:** Deliver on exhale
- **Cardiac gate:** Deliver during diastolic phase
- **SQI gate:** SQI ≥ REDUCED on ≥ 2 channels
- **Depth gate floor:** `trance_score ≥ 0.45` for language content

The 0.45 depth floor is higher than standard affirmations (0.40) because novel phoneme processing requires slightly deeper state to avoid conscious analytical interference.

---

## 6. Association Strength and Decay

Each language item has an `association_strength` value (0.0–1.0) tracking the strength of the L2→L1 binding:

### Initial Values by Delivery Mode

| Delivery Mode | Initial `association_strength` per delivery |
|--------------|---------------------------------------------|
| Paired | +0.15 |
| Prompted | +0.10 |
| Immersive | +0.05 |

### Decay

Association strength decays between sessions:

```
strength_new = strength_old * decay_factor ^ days_since_last_delivery
```

Where `decay_factor = 0.95` (5% decay per day).

An item with `association_strength = 0.80` and 7 days since last delivery:
```
0.80 * 0.95^7 = 0.80 * 0.698 = 0.559
```

### Decay Interaction with Leitner Boxes

If `association_strength` decays below the box's maintenance threshold, the item is demoted:

| Box | Maintenance Threshold |
|-----|-----------------------|
| 2 | 0.30 |
| 3 | 0.40 |
| 4 | 0.50 |
| 5 | 0.60 |

Boxes 0–1 have no decay-based demotion — they're already in the highest-frequency review cycle.

---

## 7. Session Authoring — YAML Integration

Language delivery is enabled per-session in the session.yaml:

```yaml
language:
  enabled: true
  target_language: "ja"
  content_file: "content/language/ja_n5_nature.json"
  max_items_per_session: 12
  new_item_cap: 5
```

### Agent Idle Planning

During idle planning, the agent:

1. Checks if the upcoming session has `language.enabled: true`
2. Queries `language_items` for items due for review in the target language
3. Selects items using box priority (new items first, then due reviews)
4. Pre-synthesizes TTS audio for all selected items via `tts_engine.py`
5. Writes `agent_conductor_hints.language_items_ready = true` when prep is complete

If TTS pre-synthesis fails for any item, that item is excluded from the session set. Never deliver language items without pre-synthesized audio — real-time TTS introduces latency that breaks the delivery timing.

---

## 8. TMR Integration — Sleep-Phase Vocabulary Replay

When a trance session with language delivery is followed by a sleep session (or transitions into sleep via SLEEP_APPROACH), the TMR cue manager can replay delivered vocabulary items during SWS (N3).

### How It Works

1. During the trance session, every successfully delivered language item is logged to `tmr_candidates` with:
   - Item ID
   - Delivery timestamp
   - Delivery mode (paired/prompted/immersive)
   - `trance_score` at delivery time
   - `association_strength` at delivery time

2. When the Conductor enters SLEEP_MAINTAIN and N3 is detected:
   - TMR cue manager selects vocabulary items from `tmr_candidates`
   - Selection priority: items with lowest `association_strength` first (weakest memories benefit most from reactivation)
   - Cue format: L2 audio only, at 30% of trance-session volume
   - Cue timing: phase-locked to slow oscillation up-states (same as affirmation TMR)

3. **Reconsolidation lockout interaction:** If a reconsolidation LOCKOUT is active, TMR replay of ALL content (including language) is governed by the lockout rules. Language items are not recon-tagged and therefore are NOT blocked by trace-specific lockout — they replay normally during SWS even when a recon lockout is active.

### TMR Volume and Timing

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Volume | 30% of trance delivery volume | Below arousal threshold; sufficient for memory reactivation |
| Inter-cue interval | 90 seconds minimum | Matches TMR literature for optimal reactivation without sleep disruption |
| Max cues per N3 cycle | 8 | Conservative — SWS windows are 20–40 min in early cycles |
| Phase lock target | Slow oscillation up-state | Reactivation during up-states produces strongest consolidation |

---

## 9. Subsystem Interaction Table

| Subsystem | Interaction | Details |
|-----------|-------------|---------|
| **Conductor** | Phase gate | Language only during MAINTENANCE. Agent checks `conductor_phase` before queuing. |
| **Delivery Gate** | All 4 gates apply | Depth floor 0.45 (higher than affirmations). Delivery rate ~60%. |
| **Somatic Palette** | No interaction | Language delivery does not affect chord evaluation. Language items are not chord parameters. |
| **Reconsolidation** | Priority yield | Recon content always takes priority. Language pauses during RETRIEVE and UPDATE phases. Resumes during LOCKOUT. |
| **Conditioning Engine** | Tag compatibility | Language items can carry `association_tags` that connect to conditioning paradigms. The conditioning engine tracks these as weak CS if tagged. |
| **Training Mode** | Pause during training | When training mode is active and the agent is in an active reinforcement/deepening cycle, language delivery pauses. Resumes when training mode returns to monitoring state. |
| **TMR Cue Manager** | Sleep replay | Delivered items become TMR candidates. L2-only replay during N3. Not blocked by recon lockout. |
| **Sleep Burst Engine** | No interaction | Sleep bursts are pink noise — they don't interact with language cue replay. The TMR cue manager handles timing coordination. |
| **Calibration** | Reduced rate | During calibration sessions 1–10, language delivery rate is halved (1 item per 6 min) to avoid confounding calibration metrics. |
| **Fractionation** | Pauses during frac | Language delivery pauses when Conductor enters FRAC_EMERGE. Resumes 3 min after MAINTENANCE re-entry (same cooldown as chord evaluation). |
| **Content Queue** | Priority 4 (lowest) | Recon > conditioning > affirmations > language. Language fills gaps between higher-priority content. |
| **Timeline Runner** | Session.yaml config | `language.enabled`, `target_language`, `content_file`, `max_items_per_session`, `new_item_cap` set per session. |

---

## 10. Database Schema — `language_items` Table

```sql
CREATE TABLE language_items (
    id              TEXT PRIMARY KEY,    -- e.g., "ja_tree_001"
    language        TEXT NOT NULL,       -- ISO 639-1 code, e.g., "ja"
    l2              TEXT NOT NULL,       -- target language word
    l2_romanization TEXT,                -- romanized form
    l1              TEXT NOT NULL,       -- native language translation
    leitner_box     INTEGER DEFAULT 0,  -- current box (0-5)
    association_strength REAL DEFAULT 0.0,
    total_deliveries INTEGER DEFAULT 0,
    successful_deliveries INTEGER DEFAULT 0,  -- no regression signal
    last_delivered_at TEXT,              -- ISO 8601 timestamp
    last_session_id  TEXT,              -- FK to sessions table
    promoted_at     TEXT,               -- last box promotion timestamp
    demoted_at      TEXT,               -- last box demotion timestamp
    created_at      TEXT NOT NULL,      -- first introduction timestamp
    category        TEXT,               -- thematic grouping
    difficulty_level TEXT,              -- language-specific scale
    tmr_replay_count INTEGER DEFAULT 0, -- times replayed during SWS
    last_tmr_at     TEXT                -- last TMR replay timestamp
);
```

### Key Queries

```sql
-- Items due for review this session (Box 0-1 every session, Box 2+ by interval)
SELECT * FROM language_items
WHERE language = ?
AND (
    leitner_box <= 1
    OR (leitner_box = 2 AND julianday('now') - julianday(last_delivered_at) >= 2)
    OR (leitner_box = 3 AND julianday('now') - julianday(last_delivered_at) >= 3)
    OR (leitner_box = 4 AND julianday('now') - julianday(last_delivered_at) >= 5)
    OR (leitner_box = 5 AND julianday('now') - julianday(last_delivered_at) >= 8)
)
ORDER BY leitner_box ASC, association_strength ASC;

-- Items needing decay-based demotion check
SELECT * FROM language_items
WHERE leitner_box >= 2
AND association_strength < CASE leitner_box
    WHEN 2 THEN 0.30
    WHEN 3 THEN 0.40
    WHEN 4 THEN 0.50
    WHEN 5 THEN 0.60
END;

-- Session vocabulary set selection (idle planning)
SELECT * FROM language_items
WHERE language = ?
AND (leitner_box <= 1 OR /* interval check */)
ORDER BY leitner_box ASC, association_strength ASC
LIMIT ?;  -- max_items_per_session from session.yaml

-- TMR candidate selection (strongest benefit = weakest items)
SELECT li.* FROM language_items li
JOIN tmr_candidates tc ON li.id = tc.item_id
WHERE tc.session_id = ?
AND tc.content_type = 'language'
ORDER BY li.association_strength ASC
LIMIT 8;  -- max cues per N3 cycle
```

---

## 11. Agent Decision Flowchart

```
Idle Planning:
    Is language.enabled in upcoming session.yaml?
    ├─ No → Skip language prep
    └─ Yes → Query due items → Select set → Pre-synth TTS
              └─ All audio ready?
                 ├─ No → Exclude failed items, reduce set
                 └─ Yes → Set language_items_ready = true

Active Session (MAINTENANCE tick):
    Is language_items_ready?
    ├─ No → Skip
    └─ Yes → Is conductor_phase == MAINTENANCE?
              ├─ No → Skip (wrong phase)
              └─ Yes → Time since last language delivery ≥ 3 min?
                        ├─ No → Skip (rate limit)
                        └─ Yes → Is recon in RETRIEVE or UPDATE?
                                  ├─ Yes → Skip (recon priority)
                                  └─ No → Is training_mode active cycle?
                                            ├─ Yes → Skip (training priority)
                                            └─ No → Select next due item
                                                     → Check delivery gate
                                                     ├─ Gate closed → Return to pool
                                                     └─ Gate open → Deliver
                                                          → Log delivery
                                                          → Update association_strength
                                                          → Monitor for regression (10s)
                                                          → Update Leitner box if needed
```

---

## 12. Do Not

1. **Do not deliver language items outside MAINTENANCE.** No exceptions. Novel phonemes during INDUCTION, DEEPENING, or sleep phases will disrupt state.
2. **Do not exceed 1 item per 3 minutes.** The rate limit is neurologically motivated — retroactive inhibition is real.
3. **Do not deliver more than 5 new items (Box 0) per session.** Cognitive budget for novel material is limited even in deep trance.
4. **Do not deliver language without pre-synthesized audio.** Real-time TTS introduces 200–500ms latency that breaks delivery timing and may produce inconsistent pronunciation.
5. **Do not use visualization-based mnemonics.** The user has aphantasia. "Picture a tree" is useless. Use somatic/auditory associations only.
6. **Do not deliver language during reconsolidation RETRIEVE or UPDATE phases.** These phases require undivided content delivery focus. Language resumes during LOCKOUT.
7. **Do not deliver language during active training mode reinforcement cycles.** Praise timing is operant-conditioning-critical. Language delivery between reinforcement cues breaks the temporal contingency.
8. **Do not treat language items as palette chord parameters.** Language is content, not configuration. It does not affect chord evaluation or the Interference Graph.
9. **Do not skip TTS pre-synthesis for items with non-Latin scripts.** The center flash can display any Unicode, but the user cannot read arbitrary scripts. Audio is the primary delivery channel.
10. **Do not deliver L1-only.** Every delivery includes L2. Immersive mode is L2-only, never L1-only. The goal is target language exposure, not native language reinforcement.
