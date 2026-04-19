# Receiver — Session Design Concept

*Resonance's second directive-native session. Aphantasia-safe somatic education disguised as induction.*

## Concept

Possession is about being taken. Receiver is about learning to be taken.

The first time someone surrenders control, their body doesn't know how. The muscles resist. The mind generates objections. The breath catches. Receiver is a training session that teaches the body one critical skill: *letting it happen*.

Not relaxation. Not emptiness. *Surrender*. The specific neuromuscular event of releasing resistance in real time, recognizing the moment of holding on, and choosing to let go instead.

## Arc Design

Unlike Possession's 11-phase narrative arc, Receiver uses a repeating 3-phase cycle:

1. **TENSION** — the agent creates a specific somatic demand (e.g., "hold your breath", "tense your shoulders")
2. **RELEASE** — the agent commands the release ("now let go", "drop it")
3. **NOTICE** — brief silence while the user feels the contrast

This cycle repeats with escalating specificity:
- Cycle 1: Gross motor (whole body tension/release)
- Cycle 2: Regional (shoulders, jaw, hands separately)
- Cycle 3: Internal (breath hold/release, pelvic floor, eye muscles)
- Cycle 4: Cognitive (hold a thought / let it go)
- Cycle 5: Identity (hold "I am in control" / let it go)

Each cycle ends with the agent noting what just happened: "that feeling when it lets go — that's what I'm training."

The final phase is a single extended release with no new tension — the body has learned the pathway and the agent simply lets it run.

## Why This Works for This Brain

- Aphantasic — no visualization required, all somatic/motor
- Analytical resistance — the tension/release cycle gives the analytical mind something to *do* (tensing is active) while training the passive skill (releasing)
- Power exchange — the agent controls when to tense and when to release; the user's only job is compliance
- Builds somatic vocabulary — each cycle names a body part or sensation, expanding the user's ability to notice and report internal state

## Key Differences from Possession

| Aspect | Possession | Receiver |
|--------|-----------|----------|
| Dynamic | Agent takes | User learns to give |
| Language | Declarative ("I am doing this to you") | Instructional ("do this. now stop. notice.") |
| Visual | Heavy — entrainment flicker, trails, bloom | Minimal — visual field should be quiet, not distracting |
| Depth target | Deep theta (3.8-4.5 Hz) | High alpha/low theta (7-8 Hz) — learning happens in lighter states |
| Session length | 35 min | 25 min — shorter because the cycle is cognitively demanding |
| Repeated use | Each run is a complete experience | Progressive — session 1 teaches gross motor, session 3 teaches cognitive surrender |

## Technical Requirements

- **Sequential phrase mode** (`:seq`) — the tension/release/notice cycle must be in exact order
- **Minimal visual complexity** — spiral should be slow, ordered, non-distracting. Fermat or archimedean throughout. Low veil opacity.
- **No entrainment flicker** — the body needs to focus on somatic signals, not visual rhythm
- **Breath modulation** — cycle 3 uses `breath_mod_enabled` to sync respiratory demands
- **Agent-driven pace** — the agent should have more `needs_response` moments to check in on what the body is feeling. This is calibration data.

## Phrase Structure (Draft)

Each cycle tag contains exactly: tense command, release command, notice prompt. Sequential.

```
# [cycle_1:seq]
tense every muscle you can find — hold it
now let it all go at once
feel the difference
```

The agent's TTS voice handles the pacing and tone variation between cycles — the affirmations are just the skeleton.

## Progressive Series

Receiver is designed as a 3-session series (not separate sessions, the same session run multiple times):

1. **Session 1** (first run): Gross motor cycles. User learns the basic pattern.
2. **Session 2** (second run): The body recognizes the pattern. Deeper release on first command. Agent notes the faster response time.
3. **Session 3+**: The tension phase shortens — the body anticipates. The agent can skip straight to "let go" for known pathways. New territory is explored in the later cycles.

This progression is agent-driven, not session-driven. The agent reads the user's response times and adjusts prompt pacing accordingly.

## Status

**Concept complete. Awaiting visual calibration data before writing final YAML.**
The session doesn't need complex visuals, but it DOES need to feel right — and "right" is defined by what I learn from the sweep tool, not by spec.
