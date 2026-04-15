# Reconsolidation Protocol

## What is reconsolidation

Every time a consolidated memory is actively retrieved, it briefly becomes labile — the molecular machinery that stabilised it temporarily dismantles. For roughly 10–60 minutes after retrieval, that specific trace is writable: it can be strengthened (exact repetition), modified (moderate mismatch), or destabilised (large mismatch). After this window it re-stabilises with whatever update was present.

This is distinct from consolidation (encoding new material into long-term memory). Reconsolidation modifies already-stored patterns — habituated negative self-schemas, fear memories, compulsion loops. It is one of the most powerful levers for behavioural change that Somna has access to.

## The four-phase sequence

The in-session sequence is managed automatically by the agent's `_recon_tick()` once retrieve/update content is authored and present in the session's `affirmations.txt`. You do not need to pilot it manually — write the content during idle planning and the agent will run it when the conductor enters MAINTENANCE.

```
RETRIEVE  (~5 min)   Specific retrieval cue; 1–3 phrases via TTS + overlay.
                     Activates the target trace and opens the labilization window.

LABILIZE  (~12 min)  Normal session content continues; no further retrieve phrases.
                     The trace is now labile and waiting for the update.

UPDATE    (~8 min)   Modified association delivered; 3–5 phrases via TTS + overlay,
                     spaced ~90 s apart. This is the actual rewrite.

LOCKOUT   (~45 min)  Session continues normally; recon_retrieve_<trace> phrases are
                     locked out from TMR encoding so the old trace is not reinforced
                     during sleep. Lockout is trace-specific — all other content fires.
```

## Tagging convention

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

Tag naming: `recon_retrieve_<trace>` and `recon_update_<trace>` where `<trace>` is a
short slug identifying the target pattern (e.g. `perfectionism`, `unworthiness`,
`fear_of_failure`, `self_criticism`).

These tags are NOT activated by the normal phrase pool — they will not appear in random
rotation. The agent's recon engine delivers them directly at the right moment.

## Authoring the prediction error

The update phrases must introduce a **moderate prediction error** — the single most
critical authoring constraint. Too small a mismatch (just repeating a positive version
of the same belief) produces reconsolidation without modification: the old trace
re-stabilises unchanged. Too large a mismatch causes destabilisation without
integration.

The sweet spot: same protagonist, same emotional domain, different resolution. The
update should feel like a natural next step in a story the user already knows — not a
contradiction, not a mere restatement.

**Good prediction error distance:**
- Retrieve: "remember when you believed you had to earn your place"
- Update: "your presence needs no justification" ← same space, different framing
  of the self-in-world relationship

**Too small (just positive spin):**
- Retrieve: "remember feeling not good enough"
- Update: "you ARE good enough" ← direct negation, no update, just resistance

**Too large (breaks the frame):**
- Retrieve: "remember the perfectionism that drove you"
- Update: "nothing matters, surrender all effort" ← incoherent mismatch

## When to author recon content

Author recon content during idle planning when:

1. The user has a behaviour-change goal with a clearly identifiable underlying schema
   (perfectionism, self-criticism, imposter syndrome, approval-seeking, fear of failure).
2. The goal has been mentioned or noted across multiple sessions — evidence it's a real
   pattern, not a passing thought.
3. There is no existing recon content for this trace yet (check `recon_events` DB and
   the session's existing affirmation tags).

Do not author recon content for vague goals, one-time mentions, or goals that are
about adding new capabilities (skills, knowledge) rather than changing existing
patterns. TMR consolidation handles the former; reconsolidation handles the latter.

## How to author recon content (idle planning action)

When you identify a target trace, include `"author_recon_content"` in your `actions`
array and provide a `recon_content` object:

```json
{
  "actions": ["author_recon_content"],
  "reasoning": "User has mentioned perfectionism-driven anxiety in 3 session logs...",
  "recon_content": {
    "session": "default",
    "trace": "perfectionism",
    "retrieve_phrases": [
      "remember when you believed you had to earn your place in every room",
      "recall the weight of never being enough"
    ],
    "update_phrases": [
      "your presence needs no justification",
      "imperfection is the texture of being alive",
      "you have always been enough to be here",
      "what you make does not define what you are",
      "the striving was learned; it can be unlearned"
    ]
  }
}
```

Guidelines:
- 1–3 retrieve phrases (precise, activating the specific schema)
- 3–5 update phrases (each a distinct angle on the resolution, not repetitions)
- All phrases lowercase, no terminal punctuation, 5–12 words
- Retrieve phrases should feel like memory cues, not statements about the present
- Update phrases should feel like insights arriving, not commands or affirmations

## What the agent sees during a recon sequence

The agent's `recon_sub_phase` key in live state will be `"retrieve"`, `"labilize"`,
`"update"`, `"lockout"`, or null. During `labilize` and `lockout`, the agent should
continue normal session behaviour — do not reference the recon sequence in prompts or
console messages. The sequence is invisible to the user by design.

During `update` phase specifically, if the agent is composing a `next_affirmation`
injection via the LLM, avoid injecting retrieve-tagged content. The engine handles
update delivery directly.

## Checking what has been done

Read recon history using the `read_recon_events` tool (available as DB query):
```python
from content_tools.somna_db import read_recon_events
events = read_recon_events(target_trace="perfectionism")
```

A `reconsolidation_clean=1` row means the window closed without contamination.
Multiple clean events on the same trace indicate repeated reinforcement of the update —
this is beneficial, not redundant.

## Cross-session notes

- Recon content for a trace can be run in multiple sessions. The update accumulates.
- After 3+ clean events on a trace, consider authoring a new retrieve/update pair with
  a deeper framing — the original schema may have been modified enough that the old
  retrieve cue no longer precisely targets the residual pattern.
- TMR consolidation and reconsolidation are complementary: TMR reinforces new material
  written by the update; reconsolidation rewrites the old material that needed updating.
