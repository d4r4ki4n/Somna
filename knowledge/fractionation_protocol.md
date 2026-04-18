# Fractionation Protocol Reference for Somna

**Status:** Specification (v2 — rebuilt with Conductor ownership model)

**Author:** Ed / Reese

**Date:** 17 April 2026

**Loaded by:** Active session ticks during MAINTENANCE when fractionation is eligible

**Authority:** This file is the operational reference for the LLM agent. The authoritative design specification lives in the Somna Bible, Chapter 4 — Session Architecture, §Conductor. When this file and the Bible disagree, the Bible wins.

---

## Critical Constraint — Aphantasia

The user has **extreme aphantasia** — zero voluntary visualization. All prompts must be somatic/auditory.

- **NEVER** use visualization language: "imagine a staircase," "picture yourself," "see a light"
- **NEVER** narrate state transitions explicitly
- The user experiences entrainment as "sinking" — an imperceptible gradient where he never catches the transition

---

## 1. Mechanism

**Vogt's core observation (1890s)**: Patients hypnotized, emerged, then immediately re-hypnotized entered trance faster and deeper on each subsequent induction. Interruption does not reset progress — it accelerates it.

The interruption is a **ratchet mechanism**. Subjects carry residual trance into the brief waking state. Re-induction begins from the previous depth floor and descends further.

### Why It Works (Homoaction)

| Factor | Effect |
|--------|--------|
| Confidence | Each successful re-entry confirms ability |
| Familiarity | The route in becomes known; less cognitive work |
| Transition training | The shift mechanism itself is exercised |
| Residual trance | Re-induction starts from an elevated floor, not zero |

### Claire Jack's Critical Insight

> "Deeper is not always the goal." Fractionation trains **transitions**, not depth. For analytical subjects, "try to go deeper" recruits the monitoring that keeps them on the surface. Depth follows as a side effect of practicing the movement.

This is especially relevant for aphantasia — visualization-based deepening scripts are unavailable. Fractionation sidesteps this entirely.

---

## 2. Ownership Model — Who Does What

**The Conductor owns fractionation execution. The agent requests it.**

This is the single most important architectural fact about fractionation in Somna. The agent does NOT run its own fractionation state machine. The agent decides *when* to request fractionation; the Conductor decides *how* to execute it.

### The Request Path

```
Agent decides fractionation is warranted
    → Agent writes: agent_conductor_hints.request_fractionation = true
    → Conductor reads the hint on next tick
    → Conductor transitions: MAINTENANCE → FRAC_EMERGE
    → Conductor manages all phase transitions internally
    → Conductor transitions: FRAC_REDROP → MAINTENANCE
    → Agent receives MAINTENANCE re-entry via conductor_phase
```

All writes use the module-level IPC function:

```python
from ipc import patch_live
patch_live({"agent_conductor_hints": {"request_fractionation": True}})
```

Do NOT use `_patch_live()` (deprecated). Do NOT write `live_control.json` directly. See Bible Ch.1 §IPC-StateServer.

### The Conductor's Three Fractionation Phases

| Phase | Duration | Entry Trigger | Exit Trigger | What Happens |
|-------|----------|---------------|-------------|--------------|
| FRAC_EMERGE | 15–45 s | `request_fractionation` hint while frac-eligible in MAINTENANCE | SEF95 > 15 Hz OR 45 s timeout | Conductor ramps beat frequency back to IAF (alpha). Agent delivers brief emergence prompt (somatic only). Visual parameters shift to orient-level. |
| FRAC_EMERGE_HOLD | 15–45 s | FRAC_EMERGE exit | Hold timer elapsed | User is briefly in lighter state. Conductor holds alpha parameters. Agent is SILENT — no prompts. |
| FRAC_REDROP | Variable | FRAC_EMERGE_HOLD exit | trance_score > 0.65 for 90 s (same as MAINTENANCE entry) | Conductor ramps back to theta. Agent may deliver one somatic re-induction prompt. On MAINTENANCE re-entry, the session continues from a deeper floor. |

### What the Agent Controls

| Agent Responsibility | How |
|---------------------|-----|
| Decide WHEN to request fractionation | Write `request_fractionation = true` to hints |
| Deliver emergence prompt (somatic only) | During FRAC_EMERGE — 1 brief prompt, no visualization |
| Deliver re-induction prompt (optional) | During FRAC_REDROP — 1 somatic prompt, optional |
| Stay SILENT during FRAC_EMERGE_HOLD | No prompts, no TTS, no content delivery |
| Select post-frac chord (if palette active) | On MAINTENANCE re-entry, after 3-min cooldown |
| Track fractionation count | Agent-side counter; cap at 3 per session |

### What the Agent Does NOT Control

| Conductor Responsibility | Why Agent Cannot Do This |
|-------------------------|------------------------|
| Phase transitions | Timing is EEG-gated (SEF95, trance_score). Agent cannot read EEG at tick resolution. |
| Beat frequency ramping | Conductor owns `beat_frequency` during frac phases. |
| Visual parameter shifts | Conductor owns spiral/veil parameters during frac phases. |
| Hold duration | EEG-gated with time fallback. Agent's clock would be less accurate. |

---

## 3. When to Request Fractionation

The agent should request fractionation when ANY of these conditions hold during MAINTENANCE:

### 3.1 Somatic Palette Chord Failure

The primary trigger. When a chord evaluation window fails (see `somatic_palette.md` §2), the agent requests fractionation before switching to the next chord.

```
Chord fails evaluation criteria
    → Agent sets request_fractionation = true
    → Conductor runs FRAC_EMERGE → HOLD → REDROP → MAINTENANCE
    → 3-minute cooldown on MAINTENANCE re-entry
    → Agent selects next chord from palette
    → New evaluation window opens
```

### 3.2 Depth Plateau

When `trance_score` has been flat (variance < 0.05) for > 15 minutes during MAINTENANCE without chord failure. The ratchet effect can break a plateau that gradual parameter adjustment cannot.

### 3.3 Agent Judgment (Rare)

The agent may request fractionation based on session arc design — for example, if the session plan calls for a fractionation cycle at a specific point. This should be rare and deliberate, not routine.

### 3.4 When NOT to Request

- During CALIBRATION, INDUCTION, or DEEPENING — fractionation is not eligible
- During any SLEEP_* phase — fractionation disrupts sleep onset
- During GENUS_BLOCK — gamma entrainment must not be interrupted
- When the 3-frac-per-session cap has been reached
- When reconsolidation is in RETRIEVE or UPDATE phase — trace manipulation must not be interrupted (see §6)
- Within 5 minutes of a previous frac cycle completing — minimum recovery window

---

## 4. EEG Markers

| Marker | Band | Behavior During Fractionation | Measurement |
|--------|------|-------------------------------|-------------|
| Alpha power | 8–12 Hz | Increases during FRAC_EMERGE, decreases during FRAC_REDROP | Muse 2 TP9/TP10 |
| Theta power | 4–8 Hz | Decreases during emerge, increases during redrop — each redrop reaches higher theta than previous | Muse 2 TP9/TP10 |
| Theta/Alpha ratio | Computed | Rising = deepening, falling = emergence. Useful secondary metric. | `eeg_theta / eeg_alpha` |
| SEF95 | Computed | Rises above 15 during emergence (FRAC_EMERGE exit trigger). Falls below 10 during deep redrop. | `eeg_processor.py` |
| trance_score | Composite | MAINTENANCE re-entry requires trance_score > 0.65 for 90 s — same threshold as initial MAINTENANCE entry. | `conductor.py` |

**Not measurable with 4-channel Muse 2**: gamma midline frontal, beta interhemispheric PEC. Do not use as triggers.

---

## 5. The Ratchet Effect — Quantified Expectations

Each fractionation cycle should produce measurably deeper re-entry than the previous MAINTENANCE state:

| Cycle | Expected Behavior | If Not Observed |
|-------|-------------------|-----------------|
| 1st | Baseline. Re-entry trance_score ≈ pre-frac level or slightly higher. | Normal — first cycle establishes the floor. |
| 2nd | Re-entry trance_score > 1st cycle's peak by ≥ 0.05. Faster theta onset. | May indicate poor emergence (user didn't fully surface). Extend HOLD next time. |
| 3rd | Deepest state. Re-entry should exceed all prior peaks. | If still no improvement, the session may have hit a ceiling. Do not request a 4th. |

Log each cycle's pre-frac and post-frac trance_score, SEF95, and theta/alpha ratio to `conductor_decisions` for cross-session analysis.

---

## 6. Subsystem Interactions

### 6.1 Somatic Palette

Fractionation and the somatic palette are tightly coupled. The palette uses fractionation re-entries as chord switch points:

- Chord fails evaluation → agent requests fractionation → FRAC cycle runs → MAINTENANCE re-entry → 3-min cooldown → new chord selected → new evaluation window
- On MAINTENANCE re-entry, the agent should select the next chord BEFORE the cooldown ends, so parameters are stable when the evaluation window opens
- The Conductor retains ownership of `spiral_chaos`, `trail_decay`, `sr_noise_level`, and `shadow_opacity_target` regardless of palette chord state

### 6.2 Reconsolidation

Fractionation and reconsolidation can coexist in the same session, but with constraints:

| Recon Phase | Fractionation Allowed? | Reasoning |
|-------------|----------------------|-----------|
| IDLE | Yes | Protocol not yet started |
| RETRIEVE | **NO** | Trace activation must not be interrupted |
| LABILIZE | Yes, with caution | Trace is labile; emergence won't close the window, but may disrupt processing. Avoid unless chord failure forces it. |
| UPDATE | **NO** | Update delivery must not be interrupted |
| LOCKOUT | Yes | Lockout is passive; fractionation doesn't affect TMR blocking |
| COMPLETE | Yes | Protocol finished |

**Rule:** If reconsolidation is in RETRIEVE or UPDATE, the agent must NOT request fractionation even if a chord failure occurs. Instead: continue with the current chord until the recon phase completes, then evaluate whether fractionation is still warranted.

### 6.3 Delivery Gate

During FRAC_EMERGE and FRAC_EMERGE_HOLD, the delivery gate should block all content delivery (TTS, veil phrases, center flash). The agent's emergence prompt bypasses the delivery gate because it is delivered directly, not through the content queue.

During FRAC_REDROP, the delivery gate resumes normal gating. The agent's optional re-induction prompt should respect delivery gate timing (respiratory phase, cardiac phase).

### 6.4 Training Mode

If training mode is active during a fractionation session, praise delivery pauses during all three frac phases. The operant conditioning loop resumes on MAINTENANCE re-entry. See `training_mode.md` §6.

---

## 7. Agent Prompts — Aphantasia-Safe Examples

### Emergence Prompt (FRAC_EMERGE)

Brief, somatic, one sentence maximum:

- "Let yourself come up just a little."
- "Feel the surface for a moment."
- "Rise just enough to notice the shift."

**Do NOT say**: "Open your eyes," "Come fully awake," "Count up from 1 to 5," or anything that implies full emergence. This is a *partial* surface — the user should stay in a liminal state.

### Re-Induction Prompt (FRAC_REDROP, optional)

- "And back down."
- "Let go again."
- "Sink."

One or two words is often sufficient. The re-induction prompt is optional because the Conductor's frequency ramping does the heavy lifting. The prompt is a nudge, not a driver.

### What NOT to Prompt

- No visualization: "imagine going deeper," "picture a staircase"
- No counting: "I'll count from 5 to 1"
- No narration of state: "you're going deeper now," "notice how much more relaxed you are"
- No meta-commentary: "this is fractionation," "we're doing another cycle"

---

## 8. Session Cap and Exhaustion

**Maximum 3 fractionation cycles per session.** This cap is absolute — the agent must not request a 4th even if conditions warrant it.

After 3 cycles with no measurable deepening:
1. Continue in MAINTENANCE with the current chord (or best available palette chord)
2. Do not suggest emergence unless the user requests it or trance_score < 0.30 for > 10 minutes
3. Log `frac_exhausted = true` in the session record
4. Consider the possibility that the entry state (time of day, fatigue, mood) is the limiting factor, not the technique

---

## 9. Research Citations

| Source | Contribution |
|--------|-------------|
| Vogt (1890s) | Original observation of fractionation deepening |
| Claire Jack | "Deeper is not always the goal" — transition training vs. depth chasing |
| Fehrlin et al. 2023 | Alpha power increases in early trance; useful for tracking emergence |
| Jensen & Barrett 2024 | Theta dominance as primary depth marker |
| Cajochen et al. 2024 | 96-minute median sleep cycle (relevant for sleep session timing, not fractionation directly) |
| Nam & Choi 2020 | Lenient initial thresholds → progressive tightening (calibration relevance) |

---

## 10. Quick Reference — Agent Decision Flowchart

```
Is the Conductor in MAINTENANCE?
    No → Do not request fractionation
    Yes ↓

Is fractionation eligible? (frac count < 3, not within 5 min of last frac)
    No → Do not request fractionation
    Yes ↓

Is reconsolidation in RETRIEVE or UPDATE?
    Yes → Do not request fractionation; wait for phase to complete
    No ↓

Is there a reason to fractionate? (chord failure, depth plateau, planned arc)
    No → Continue MAINTENANCE normally
    Yes ↓

Write: patch_live({"agent_conductor_hints": {"request_fractionation": True}})
    → Conductor handles FRAC_EMERGE → HOLD → REDROP → MAINTENANCE
    → Agent delivers emergence prompt (somatic, 1 sentence) during FRAC_EMERGE
    → Agent is SILENT during FRAC_EMERGE_HOLD
    → Agent delivers optional re-induction prompt during FRAC_REDROP
    → On MAINTENANCE re-entry: 3-min cooldown, then select next chord if palette active
```
