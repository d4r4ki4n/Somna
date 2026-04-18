# Reconsolidation Protocol

**Status:** Specification (v2 — rebuilt with full subsystem integration)

**Author:** Ed / Reese

**Date:** 17 April 2026

**Loaded by:** `_load_idle_knowledge()` during idle planning; also referenced during MAINTENANCE when `_recon_tick()` is active

**Authority:** This file is the operational reference for the LLM agent. The authoritative design specification lives in the Somna Bible, Chapter 6 — Conditioning & Content, §Reconsolidation. When this file and the Bible disagree, the Bible wins.

---

## 1. What Is Reconsolidation

Every time a consolidated memory is actively retrieved, it briefly becomes labile — the molecular machinery that stabilised it temporarily dismantles. For roughly 10-60 minutes after retrieval, that specific trace is writable: it can be strengthened (exact repetition), modified (moderate mismatch), or destabilised (large mismatch). After this window it re-stabilises with whatever update was present.

This is distinct from consolidation (encoding new material into long-term memory). Reconsolidation modifies already-stored patterns — habituated negative self-schemas, fear memories, compulsion loops. It is one of the most powerful levers for behavioural change that Somna has access to.

---

## 2. The Five-Phase State Machine

The reconsolidation engine is a six-state FSM: `idle -> retrieve -> labilize -> update -> lockout -> complete`. Four of these states are active in-session phases; `idle` and `complete` are bookend states.

The in-session sequence is managed automatically by the agent's `_recon_tick()` once retrieve/update content is authored and present in the session's `affirmations.txt`. You do not need to pilot it manually — write the content during idle planning and the agent will run it when the Conductor enters MAINTENANCE.

```
IDLE         Agent has recon content authored but protocol not yet started.
             Waiting for MAINTENANCE entry + depth requirements.

RETRIEVE     (~5 min)   Specific retrieval cue; 1-3 phrases via TTS + overlay.
                        Activates the target trace and opens the labilization window.

LABILIZE     (~12 min)  Normal session content continues; no further retrieve phrases.
                        The trace is now labile and waiting for the update.

UPDATE       (~8 min)   Modified association delivered; 3-5 phrases via TTS + overlay,
                        spaced ~90 s apart. This is the actual rewrite.

LOCKOUT      (~45 min)  Session continues normally; recon_retrieve_<trace> phrases are
                        locked out from TMR encoding so the old trace is not reinforced
                        during sleep. Lockout is trace-specific — all other content fires.

COMPLETE     Protocol finished. Results logged to recon_events table.
```

**Total minimum time:** ~70 minutes from RETRIEVE start to LOCKOUT end.

---

## 3. Minimum Requirements to Start RETRIEVE

The agent must verify ALL of the following before transitioning from IDLE to RETRIEVE:

1. **Conductor is in MAINTENANCE.** Reconsolidation does not run in any other phase.

2. **trance_score >= 0.50.** Delivering retrieval cues in shallow maintenance (trance_score 0.3-0.4) risks activating the trace without sufficient depth for the labilization window to actually open. The brain needs to be in a receptive state for trace activation to be meaningful.

3. **Remaining session time >= 80 minutes.** The protocol needs ~70 minutes minimum (5 + 12 + 8 + 45). Adding a 10-minute buffer for transitions, fractionation recovery, and delivery gate delays gives 80 minutes. If the session has less than 80 minutes remaining from the current moment, do NOT start RETRIEVE.

4. **recon_retrieve_<trace> and recon_update_<trace> content exists** in the session's `affirmations.txt`.

If any requirement is not met, stay in IDLE. The protocol can be attempted in a future session — it is better to skip entirely than to start and not complete.

---

## 4. One Trace Per Session

**Rule: Only one reconsolidation trace per session.**

Running two traces simultaneously creates timing conflicts:
- Trace A's LOCKOUT is 45 minutes. If trace B's RETRIEVE starts during trace A's LOCKOUT, the retrieval cues for trace B may inadvertently re-activate trace A (especially if the traces are thematically related — e.g., "perfectionism" and "self_criticism").
- The delivery gate would need to distinguish between two sets of locked phrases, two update schedules, and two lockout windows simultaneously. This complexity is not worth the risk.
- The total time for two sequential protocols would be ~140 minutes — longer than most sessions.

If the user wants to work on multiple traces, rotate them across sessions. Author content for trace A in session N, trace B in session N+1, etc.

---

## 5. Lockout Interrupted by Session End

If the session ends before the 45-minute LOCKOUT completes:

1. **The lockout was partially effective.** Some re-stabilization has occurred, but the trace is not fully re-consolidated.

2. **TMR for the current sleep session:** The `recon_locked_phrases` list PERSISTS for the remainder of the night's sleep. If this is a pre-sleep session that transitions into SLEEP_MAINTAIN, the TMR engine continues to respect the lockout — retrieve-tagged content will not be replayed during N2/N3, even though the LOCKOUT timer didn't complete during the trance portion.

3. **Next session:** The lockout does NOT carry over to the next day's session. Each session starts with a fresh `recon_locked_phrases = []`. The reasoning: if 24+ hours have passed, the trace has re-stabilized regardless of whether the lockout completed.

4. **Planning implication:** The agent should avoid starting RETRIEVE when remaining session time is < 80 minutes (see section 3). But if an unexpected early termination occurs (user stops session manually), log `lockout_completed = false` in `recon_events` and proceed normally in the next session.

---

## 6. Tagging Convention

Recon content lives in the session's `affirmations.txt` under namespaced tags:

```
# [recon_retrieve_perfectionism]
remember when you believed you had to earn your place in every room
recall the weight of never being enough

# [recon_update_perfectionism]
your presence needs no justification
imperfection is the texture of being alive
you have always been enough to be here
what you make does not define what you are
the striving was learned; it can be unlearned
```

Tag naming: `recon_retrieve_<trace>` and `recon_update_<trace>` where `<trace>` is a short slug identifying the target pattern (e.g., `perfectionism`, `unworthiness`, `fear_of_failure`, `self_criticism`).

These tags are NOT activated by the normal phrase pool — they will not appear in random rotation. The agent's recon engine delivers them directly at the right moment.

---

## 7. Authoring the Prediction Error

The update phrases must introduce a **moderate prediction error** — the single most critical authoring constraint.

| Mismatch Level | What Happens | Example |
|---|---|---|
| Too small (repetition) | Trace is reconsolidated as-is. Strengthened, not modified. | Retrieve: "you're not good enough" -> Update: "you ARE good enough" (simple negation — too close to the original frame) |
| Moderate (sweet spot) | Trace is modified. New association overwrites old. | Retrieve: "you had to earn your place" -> Update: "your presence needs no justification" (reframes the underlying schema, not just the surface belief) |
| Too large (extinction) | Trace is destabilised but no coherent replacement forms. May cause confusion or anxiety. | Retrieve: "you're not good enough" -> Update: "think about the color blue" (completely unrelated — no associative bridge) |

**Authoring heuristic:** The update should address the same emotional core as the retrieve, but from a fundamentally different structural position. Not the opposite (that's too small). Not unrelated (that's too large). A genuine reframe that the brain can bridge to.

**Test:** If you can complete the sentence "I used to believe [retrieve], but now I understand [update]" and it feels like a genuine insight rather than a platitude, the prediction error is probably right.

---

## 8. `recon_events` Table Schema (Snapshot)

**Warning:** This schema is a snapshot for agent reference. If queries fail, check `session/session_db.py` for the current schema — it is the single source of truth.

| Column | Type | Description |
|---|---|---|
| id | INTEGER PRIMARY KEY | Auto-increment |
| session_id | TEXT | FK to sessions table |
| trace_slug | TEXT | e.g., "perfectionism" |
| retrieve_started_at | REAL | Timestamp (session-relative seconds) |
| update_started_at | REAL | Timestamp |
| lockout_started_at | REAL | Timestamp |
| lockout_completed | BOOLEAN | True if full 45-min lockout elapsed |
| depth_at_retrieve | REAL | trance_score when RETRIEVE began |
| depth_at_update | REAL | trance_score when UPDATE began |
| avg_depth_during_update | REAL | Mean trance_score across UPDATE phase |
| faa_at_retrieve | REAL | FAA value at RETRIEVE start |
| faa_at_update | REAL | FAA value at UPDATE start |
| reconsolidation_clean | BOOLEAN | 1 = no contamination (no retrieve phrases leaked during lockout) |
| n_retrieve_phrases | INTEGER | How many retrieve phrases were delivered |
| n_update_phrases | INTEGER | How many update phrases were delivered |
| success | BOOLEAN | Agent assessment: did the protocol run cleanly? |
| notes | TEXT | Free-form agent notes |
| created_at | TEXT | ISO 8601 timestamp |

### Key Queries

- **Protocol history for a trace:** `SELECT * FROM recon_events WHERE trace_slug = 'perfectionism' ORDER BY created_at`
- **Clean completion rate:** `SELECT AVG(reconsolidation_clean) FROM recon_events WHERE success = 1`
- **Depth adequacy:** `SELECT AVG(depth_at_retrieve), AVG(avg_depth_during_update) FROM recon_events` — are protocols running at sufficient depth?
- **Contamination check:** `SELECT * FROM recon_events WHERE reconsolidation_clean = 0` — which sessions had retrieve phrases leak during lockout?

---

## 9. Cross-Session Deepening

After 3+ clean events (`reconsolidation_clean = 1, success = 1`) on a single trace, the agent should consider authoring a **new** retrieve/update pair with a deeper framing.

**What "deeper" means operationally:**

The new retrieve should target the schema that *remains after* the prior updates have taken effect. The original surface belief has been reframed, but the underlying emotional architecture may still be intact.

**Example progression for "perfectionism":**

| Cycle | Retrieve Target | Update Frame |
|---|---|---|
| 1-3 | "you had to earn your place in every room" | "your presence needs no justification" |
| 4-6 | "you don't need to be perfect, but you still feel anxious when you're not productive" | "stillness is not laziness; rest is not failure" |
| 7-9 | "the anxiety isn't about productivity anymore — it's about being seen doing nothing" | "being witnessed at rest is safe; you don't owe anyone your motion" |

Each cycle targets a progressively deeper layer of the same schema. The agent identifies the next layer by reviewing:

1. **Session interaction data:** What does the user talk about in pre/post-session conversation?
2. **Emotional markers:** Does FAA still spike on the current retrieve phrases, or has the emotional charge diminished (suggesting the current layer is resolved)?
3. **Palette data:** Do `emotional` family chords still produce emotional_opening state types during sessions with this trace, or has the response flattened?

If the emotional charge on the current retrieve phrases has diminished (FAA response < 0.1 during RETRIEVE across 2+ sessions), it's time to deepen or retire the trace.

---

## 10. Interaction with Other Subsystems

| System | Interaction |
|---|---|
| **Conductor FSM** | Protocol runs entirely within MAINTENANCE. Conductor does not change phase for reconsolidation. If fractionation is requested during an active protocol, the recon timer pauses during FRAC_EMERGE/HOLD/REDROP and resumes on MAINTENANCE re-entry. |
| **TMR Engine** | During LOCKOUT, `recon_locked_phrases` list prevents TMR replay of retrieve-tagged content during N2/N3. Update-tagged content IS eligible for TMR replay during lockout — reinforcing the new association. |
| **Delivery Gate** | Retrieve and update phrases are delivered through the normal TTS + overlay path and are subject to the delivery gate's respiratory, cardiac, SQI, and depth checks. If the gate is throttling (e.g., low SQI), phrase delivery may be delayed — the recon timer accounts for this by tracking phrases-delivered, not wall-clock time. |
| **Somatic Palette** | The `emotional` family of palette chords pairs naturally with reconsolidation work. When a reconsolidation protocol is planned for a session, the agent should prefer `emotional` family chords during chord selection (add a +0.1 bias to emotional family candidates in the selection_score formula). |
| **Language Module** | Language and reconsolidation are independent. Both can run during MAINTENANCE simultaneously — language uses different delivery windows and different content tags. No conflict. |
| **Content Queue Priority** | During UPDATE phase, reconsolidation update phrases take absolute priority over both affirmations and vocabulary items. The ~90 s spacing between update phrases is enforced by the recon engine, not by the content queue. Between update phrases, normal content delivery resumes. |
