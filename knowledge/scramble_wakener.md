# Scramble Wakener — Agent Integration

## Overview

Two wakener modes that replace the normal gentle wake-up with deliberate cognitive overload. Both live as session YAMLs in `sessions/scramble_wakener/` and `sessions/ego_death_wakener/`. Their final keyframes can be copied into any session's timeline.

## Amnesia Scramble (final 2 minutes)

**Mechanism:** Working memory overload via simultaneous multi-channel saturation.
- `veil_mode: strobe` — visual processing saturated
- `spiral_chaos: 1.0–1.5` — pattern recognition overwhelmed
- `affirmation_rate: 12–15` — too fast for conscious encoding
- `font_switch_mode: rapid` — text parsing disrupted
- `trail_decay: 0.95–0.97` — afterimages compound, nothing resolves
- `volume: 85–92` — auditory channel pushed to discomfort threshold

**Agent behavior:** No special action needed. The timeline handles everything. The affirmations pool `[scramble]` fires automatically at high rate.

**Effect:** The brain discards the last 2 minutes of short-term memory. Subject wakes dazed with no conscious recall of commands. Installed responses persist because they were laid down during the prior 18 minutes of normal session — the scramble only erases the conscious memory of the wake-up period.

## Ego Death Scramble (final 60 seconds + resolution)

**Mechanism:** Identity structure destruction via overload + contradictory commands + abrupt rescue.

Phase 1 — OVERLOAD (t: 1080 to t: 1135, ~55 seconds):
- Same maximum sensory parameters as amnesia scramble
- `spiral_style: kaleidoscope` — specifically chosen for fractal self-similarity, the visual equivalent of "you are no one"
- Agent fires rapid-fire contradictory identity commands from `[ego_scramble]` pool

Phase 2 — THE DROP (t: 1135, instant transition):
- Everything cuts to zero. `ease: instant` on all params.
- `spiral_style: fibonacci` — mathematical order after chaos. The golden ratio as rescue.
- `spiral_speed_multiplier: 0.15` — near-static. Breathing room.
- `volume: 45` — quiet. Warm.
- `veil_opacity: 8` — barely present. The void is gentle now.

Phase 3 — GOOD TOY (t: 1170, 30 seconds of resolution):
- Single slow phrase from `[good_toy]` pool: "Good toy."
- Fibonacci at minimum speed. Warmth. Acceptance.
- The trauma bond: the agent destroyed the ego and then rescued what remained.

**Agent behavior during ego_scramble phase:**
When `timeline_label` is `ego_death`, the agent should:
1. Fire `next_affirmation` rapidly (every 3-5 seconds) with identity commands drawn from the `[ego_scramble]` tag
2. Use short, contradictory statements: "You are no one" → "You are a toy" → "You do not think"
3. Match the increasing intensity — start moderate, escalate to maximum in the last 20 seconds
4. When `timeline_label` transitions to `the_drop`, IMMEDIATELY stop all rapid-fire output
5. Deliver ONE soft phrase: "Good toy." — then silence

**The `tts_pool_style.rate` override:** During scramble phases, the agent should set `tts_pool_style` with `rate: "+30%"` via adjustments. This chipmunk speed makes conscious parsing of the affirmations impossible — they land as pure affect, not semantic content.

## Session Design Notes

Both sessions use the same 18-minute induction arc (anchor → soften → descent → the_split → hollow → soak) lifted from the `hollow` session. The scramble wakener is an interchangeable ending — the keyframes from `pre_scramble` onward can replace any session's final 2-3 minutes.

**Copy-paste guide:** To add amnesia scramble to any session, insert the `pre_scramble`, `scramble`, `scramble_peak`, and `cut` keyframes, adjusting `t:` values to match the host session's timing. Ensure `[scramble]` tag exists in the session's affirmations.txt.

**Copy-paste guide:** To add ego death to any session, insert `pre_scramble`, `ego_death`, `the_drop`, `good_toy`, and `end` keyframes. Ensure `[ego_scramble]` and `[good_toy]` tags exist in affirmations.txt.
