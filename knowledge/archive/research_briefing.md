# Somna — Research Briefing
*State of the project as of March 2026. Read this alongside `somna_research_ref.md`.*
*Prepared for the external Research collaborator returning after the Doc 26 series.*

---

## What Happened Since Doc 26

Your capstone (orchestration_gap_analysis.md) called for a state machine conductor and
said "the instruments are built — the conductor is next." The conductor was built, along
with a substantial amount of additional work. Here is the current state.

---

## The Conductor Is Shipped

`conductor.py` implements the FSM you described. Phase map:

```
CALIBRATION → INDUCTION → DEEPENING → MAINTENANCE (→ fractionation loop)
```

- EEG-driven phase transitions using trance_score, ASSR confidence, and SEF95
- Hold timers with configurable patience (can be scaled by agent hints)
- Fractionation: automatic eligibility detection with a `request_fractionation` override
- `_log_decision()` writes every transition rationale to `somna.db` for longitudinal review
- `assessment()` returns phase arc narrative, phase duration, and trance trend per minute

The agent now reads the conductor's assessment every tick and incorporates it into LLM
context: which phase, how long in it, and the trance trajectory — so the agent's
language can match where the session actually is rather than where the timeline says it is.

---

## Agent → Conductor Communication

A new `agent_conductor_hints` key in `live_control.json` lets the agent write guidance
the conductor reads each tick:

```json
{
  "depth_patience": 1.4,       // multiplier on hold timers (agent can ask for more patience)
  "target_floor_hz": 4.5,      // nudge maintenance beat toward this frequency
  "request_fractionation": true, // agent detected depth signal → trigger frac cycle
  "note": "user showed depth signal in console"
}
```

`request_fractionation` is set automatically when the user types certain keywords
("deep", "gone", "floating", etc.) in the agent console during a session.

---

## Session Scoring Is Live

`somna.db` now has a `session_metrics` table. The `session_scorer.py` module computes
a composite quality score after each session using the EEG metrics you specified in
Doc 25 (`session_effectiveness_scoring.md`):

| Metric | Weight |
|--------|--------|
| Depth (min SEF95) | 0.25 |
| Mean depth (mean SEF95) | 0.15 |
| Entrainment (ASSR strength) | 0.25 |
| Receptivity (time in approach) | 0.20 |
| Signal quality (mean SQI) | 0.15 |

The agent can query this longitudinally via the `query_session_performance` tool, which
returns recent session rows, a trend direction for any metric over the last 20 sessions,
and the best-performing visual/audio config for a given session preset.

---

## New Agent Tools

Three tools added since Doc 26:

| Tool | What it does |
|------|-------------|
| `query_session_performance` | Longitudinal session metrics from DB; trend + best config |
| `find_images_by_theme` | Cross-session image search by tag across all sessions |
| `audit_affirmations` | LLM-powered phrase audit: cull weak, chain with `>>`, group with `\|`, retag |

---

## New Conditioning Mechanism: `image_filter_override`

The agent can now write:
```json
"image_filter_override": {"tag": "surrender", "expires_at": 1712349000.0}
```

`background.py` detects this on each tick and immediately resamples the image pool to
images tagged with that theme. This gives the agent full sensory coherence control —
when the LLM decides to lean into a theme in language, it can simultaneously pull the
visual environment toward matching imagery.

---

## Three-Layer Voice Model (Hypnosis Theory)

A new `knowledge/hypnosis_theory.md` document formalizes the agent's operational model
as three simultaneous layers:

- **Guide** — the conversational/question layer (next_prompt)
- **Fill** — the affirmation injection layer (next_affirmation, image_filter_override)
- **Inscribe** — the subliminal conditioning layer (subliminal TTS + veil text)

This is injected into both active-session and idle-planning agent contexts.

---

## What's Still Open (Gaps from Doc 26)

| Gap | Status | Notes |
|-----|--------|-------|
| Orchestration FSM (Gap 1) | ✅ Shipped | `conductor.py` |
| Audio SR sweep protocol (Gap 2) | Open | `stochastic_resonance.md` exists; no conductor-aware sweep yet |
| Coherence (HRV, Gap 3) | Partial | `hrv_coherence_breathing.md` + `hrv_breath_coupling.md` written; not wired to conductor |
| FAA receptivity gate (from Doc 23) | Partial | `faa_receptivity.md` written; FAA not yet gating affirmation delivery |
| Spectral slope (Gap 5) | Open | FFT is available; linear regression slope not computed |
| Muse S upgrade (Gap 6) | Open | board_id=39 in config is the only change needed |
| Adaptive frequency leading (Doc 24) | Partial | `adaptive_frequency_leading.md` written; conductor has `target_floor_hz` hint; full adaptive trajectory not implemented |

---

## Knowledge Files Added Since Doc 26

All live in `knowledge/`:
- `conductor_fsm.md` — phase definitions, transition triggers, agent context format
- `hypnosis_theory.md` — three-layer voice model
- `fbo_trail_decay.md` — FBO trail persistence; MAE mechanism for this user
- `stochastic_resonance.md` — SR noise on subliminal text
- `sef95_trance_depth.md` — SEF95 as trance depth proxy
- `faa_receptivity.md` — FAA asymmetry; affirmation delivery gating
- `adaptive_frequency_leading.md` — dynamic frequency targeting
- `session_effectiveness_scoring.md` — composite session quality schema
- `assr_entrainment.md`, `signal_quality_index.md` — (your docs; now integrated)

---

## Open Questions Worth Researching

These have come up during implementation but haven't been formally addressed:

1. **FAA integration with conductor** — the `faa_receptivity.md` doc exists but FAA is
   not yet wired into the conductor's phase decisions or affirmation gating. What should
   the thresholds look like? How should the conductor interpret FAA during DEEPENING vs
   MAINTENANCE?

2. **Fractionation timing calibration** — the protocol doc has placeholder thresholds.
   What does the literature say about optimal induction hold time before fractionation
   is effective? Any specific EEG correlates (theta burst? alpha suppression dip) that
   signal fractionation readiness better than a timer?

3. **Adaptive frequency leading implementation** — Doc 24 describes the concept.
   The conductor has a `target_floor_hz` hint but no full trajectory planner. What
   should the ramp profile look like across phases? Should it be IAF-relative?

4. **Spectral slope as a depth metric** — you mentioned this as low-hanging fruit.
   How does spectral slope (1/f exponent) track vs SEF95 for trance depth estimation?
   Any published correlations with hypnotic depth scales?
