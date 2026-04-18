# Training Mode — Conditioning, Depth Tracking, and Reinforcement

**Status:** Specification (v2 — rebuilt with Conductor, palette, reconsolidation, and delivery gate integration)

**Author:** Ed / Reese

**Date:** 17 April 2026

**Loaded by:** `_load_idle_knowledge()` during idle planning when training mode is enabled; active session ticks when `training_mode = true`

**Authority:** This file is the operational reference for the LLM agent. The authoritative design specification lives in the Somna Bible. When this file and the Bible disagree, the Bible wins.

**Visibility:** Training mode is a **hidden feature**. It is not exposed in default UI documentation, onboarding flows, or public-facing design documents. It is a personal, opt-in operating mode.

---

## 1. What Training Mode Is

Training mode is an optional operating mode for `somna_agent.py` that shifts the agent's goal from passive session adaptation to **active conditioning**. In standard interactive mode, the agent adapts session parameters to keep the user comfortable and deepening. In training mode, the agent has a specific *target state* it is trying to drive the user toward and maintain, measured by a quantitative metric derived from their responses.

The core mechanism is operant conditioning applied to trance depth:

```
User responds to agent prompt
    → Agent scores the response for complexity (proxy for trance depth)
    → Agent compares score to training_target
    → If score ≤ target: reinforce (praise phrase via TTS, inject their words back)
    → If score > target: deepen (adjust parameters toward deeper state)
    → Loop
```

The agent rewards the desired state when it occurs and applies gentle parameter pressure when the user is not yet there.

---

## 2. Enabling Training Mode

Training mode is off by default. Enable via `agent_config.yaml`:

```yaml
training_mode: true
training_target: 0.2
praise_phrases:
  - "good girl"
  - "perfect"
  - "yes"
  - "that's right"
```

Or at launch:

```bash
python main_imgui.py --training-mode --training-target 0.2
```

All runtime parameter changes go through the IPC StateServer:

```python
from ipc import patch_live
patch_live({"training_mode": True, "training_target": 0.2})
```

Do NOT use `_patch_live()` (deprecated). Do NOT write `live_control.json` directly.

---

## 3. The Complexity Score

The agent's text-based depth metric is the **complexity score** — a float from 0.0 to 1.0 computed from the user's text response to any prompt.

**0.0** = maximally simple / regressed (single word, no punctuation, lowercase, high emotion markers, minimal vocabulary)
**1.0** = maximally alert / articulate (long sentences, varied vocabulary, proper punctuation, mixed case)

### 3.1 Sub-Signals

| Signal | Weight | Description |
|--------|--------|-------------|
| Word count | 60% | Primary depth proxy. Single word = 0.08, 6 words = 0.50, 12+ words = 1.0. |
| Words per sentence | 20% | Sentence-level structure. Short fragments score low. |
| Average word length | 10% | Vocabulary richness. Capped at 8 chars for normalisation. |
| Punctuation density | 10% | Commas, colons, semicolons = complex sentence structure. |

The old "unique word ratio" signal was removed in v2. It gave every single-word response a perfect 1.0 vocabulary-breadth score, compressing all short texts artificially upward.

### 3.2 Score Interpretation (v2 Calibration)

Calibrated against empirical user responses at confirmed trance depths:

| Score Range | Typical Behavior | Trance Interpretation |
|-------------|------------------|-----------------------|
| 0.0–0.08 | Single-syllable fragments, typos, pure echoing. "buhhh", "y" | Deep theta / near-somnambulism |
| 0.08–0.15 | Single words, lowercase, no punctuation. "soft", "yes", "good" | Deep theta |
| 0.15–0.25 | Short phrases, minimal structure. "feels nice", "so warm" | Moderate theta |
| 0.25–0.40 | Simple sentences, some awareness. "I feel really relaxed right now" | Light theta / deep alpha |
| 0.40–0.60 | Conversational but slowed. Slightly reduced vocabulary. | Alpha |
| 0.60–1.0 | Full articulation, complex sentences, meta-awareness | Alert / light alpha |

### 3.3 Relationship to EEG trance_score

The complexity score and the Conductor's `trance_score` measure the same underlying state (trance depth) through different channels:

| Metric | Source | Latency | Reliability |
|--------|--------|---------|-------------|
| Complexity score | Text response analysis | Requires user prompt → response cycle (30–120 s) | High when user responds; unavailable when silent |
| trance_score | EEG composite (SEF95, theta/alpha, ASSR) | Real-time (every tick) | Dependent on SQI; unavailable without EEG |

**When both are available:** Use `trance_score` for Conductor phase decisions (it's real-time and doesn't require interaction). Use complexity score for training mode reinforcement decisions (it measures behavioral output, which is what operant conditioning targets).

**When EEG is unavailable:** Complexity score becomes the primary depth metric. Training mode can operate in EEG-free sessions using complexity score alone — this was its original design context before EEG integration.

**Conflict resolution:** If complexity score suggests deep state (< 0.15) but trance_score suggests light state (> 0.50), trust trance_score for parameter decisions and investigate: the user may be giving terse responses for reasons unrelated to depth (distraction, disinterest, fatigue).

---

## 4. The Training Loop

### 4.1 Prompt → Score → Reinforce/Deepen Cycle

```
Agent delivers a prompt (somatic/auditory only — aphantasia constraint)
    ↓
User responds (text input)
    ↓
Agent computes complexity_score from response
    ↓
┌─ If complexity_score ≤ training_target:
│     REINFORCE
│     → Select praise phrase from praise_phrases list
│     → Deliver via TTS (subject to delivery gate — see §5)
│     → Optionally echo user's own words back via center flash
│     → Log: training_event(score, "reinforce", phrase)
│     → Hold current parameters (don't change what's working)
│
└─ If complexity_score > training_target:
      DEEPEN
      → Adjust parameters toward deeper state:
         beat_frequency: decrease by 0.5–1.0 Hz (subject to Conductor ownership — see §5.2)
         spiral_speed_multiplier: decrease by 0.1
         veil_opacity: increase by 5–10%
         center_flash_on_time: decrease toward subliminal range
      → Deliver next somatic prompt (gentler, simpler language)
      → Log: training_event(score, "deepen", params_changed)
      → Wait for next response
```

### 4.2 Prompt Design

Training mode prompts are short, somatic, and designed to elicit a response that reveals depth:

**Good prompts (reveal depth through response complexity):**
- "How does that feel?"
- "What do you notice?"
- "Tell me what's happening."
- "Where are you?"

**Bad prompts (binary answers, no depth signal):**
- "Are you comfortable?" → "yes" (no depth info)
- "Should I continue?" → "yes" (no depth info)
- "Do you want to go deeper?" → recruits analytical monitoring

### 4.3 Prompt Frequency

| Depth Zone | Prompt Interval | Reasoning |
|------------|----------------|-----------|
| Alert (score > 0.40) | Every 2–3 min | User is responsive; frequent check-ins accelerate descent |
| Moderate (0.15–0.40) | Every 4–5 min | User is descending; reduce interruption |
| Deep (< 0.15) | Every 6–8 min | User is in target zone; minimize disruption. Reinforce only. |
| Very deep (< 0.08) | Stop prompting | User may be near somnambulism. Prompting risks either waking them or getting no response. Continue session silently. |

---

## 5. Subsystem Interactions

### 5.1 Delivery Gate

Training mode's praise delivery is subject to the delivery gate. This is critical — operant conditioning timing matters, and the delivery gate may delay or block praise delivery:

| Gate | Training Mode Behavior |
|------|----------------------|
| Respiratory | Praise TTS waits for exhalation phase. Acceptable — 2–4 s delay doesn't break reinforcement timing. |
| Cardiac | Praise TTS waits for diastolic window. Acceptable — sub-second delay. |
| SQI | If SQI is low, EEG data is unreliable. Training mode continues using complexity score alone. |
| Depth | Depth floor does not apply to praise delivery — praise is the reward signal and must fire regardless of depth. The delivery gate should exempt `training_praise` tagged content from depth gating. |

**Implementation note:** If the delivery gate blocks praise for > 10 seconds, the agent should deliver via center flash text instead (not gated by respiratory/cardiac). Late reinforcement is worse than no reinforcement — the association between response and reward degrades rapidly after 5 seconds.

### 5.2 Conductor Ownership

When the Conductor is active, it owns `CONDUCTOR_OWNED_PARAMS`. Training mode's DEEPEN adjustments must respect this boundary:

| Parameter | Owned By | Training Mode Can Adjust? |
|-----------|----------|--------------------------|
| beat_frequency | Conductor (during active FSM) | **NO** — request via `agent_conductor_hints.depth_target` instead |
| spiral_style | Conductor / Palette | **NO** during active palette chord; **YES** otherwise |
| spiral_speed_multiplier | Agent | YES |
| spiral_opacity | Agent | YES |
| veil_opacity | Agent | YES |
| veil_mode | Conductor / Palette | **NO** during active palette chord; **YES** otherwise |
| center_flash_on_time | Agent | YES |
| noise_volume | Agent | YES |

When the Conductor is inactive (no EEG, timer-based fallback), training mode has full parameter authority.

### 5.3 Somatic Palette

Training mode and the somatic palette system interact during MAINTENANCE:

- **Palette chord takes priority** for chord parameters (`beat_frequency`, `spiral_style`, `noise_color`, `veil_mode`). Training mode adjusts non-chord parameters only.
- **Chord evaluation is independent of training mode.** The palette evaluates chord effectiveness via trance_score and FAA, not via complexity score. Training mode and palette can run simultaneously without conflict as long as training mode doesn't overwrite chord parameters.
- **Chord failure + training mode:** If a palette chord fails evaluation, fractionation is requested per normal protocol. Training mode pauses during fractionation phases (see §5.5) and resumes on MAINTENANCE re-entry with the new chord.

### 5.4 Fractionation

Training mode pauses during all three Conductor fractionation phases:

| Frac Phase | Training Mode Behavior |
|------------|----------------------|
| FRAC_EMERGE | PAUSE — no prompts, no scoring, no reinforcement. Agent delivers somatic emergence prompt only. |
| FRAC_EMERGE_HOLD | PAUSE — agent is SILENT per fractionation protocol. |
| FRAC_REDROP | PAUSE — agent may deliver optional re-induction prompt. Training loop does not resume until MAINTENANCE re-entry + 3-min cooldown. |

The training loop resumes on MAINTENANCE re-entry. The agent should deliver a fresh prompt after the 3-minute cooldown to re-establish the operant cycle.

---

## 6. Reconsolidation — The Natural Pairing

Training mode and reconsolidation are complementary systems. Training mode conditions new behavioral patterns through operant reinforcement. Reconsolidation destabilizes old patterns by modifying stored memory traces. Together, they form a two-pronged approach: **reconsolidation clears the old; training mode installs the new.**

### 6.1 How They Pair

The reconsolidation protocol has a five-phase state machine: idle → retrieve → labilize → update → lockout → complete. Training mode can integrate with each phase:

| Recon Phase | Training Mode Behavior | Why |
|-------------|----------------------|-----|
| IDLE | Normal training loop | Protocol hasn't started yet |
| RETRIEVE | **PAUSE training loop** | Retrieval cues activate the target trace. Training prompts would contaminate the retrieval. Agent delivers ONLY recon retrieve phrases during this phase. |
| LABILIZE | **Modified training loop** | The trace is labile. Normal session content continues. Training mode can operate, but prompts should NOT reference the target trace's theme. Keep prompts generic and somatic. |
| UPDATE | **TRAINING REINFORCES THE UPDATE** | This is the key integration point. See §6.2. |
| LOCKOUT | Normal training loop | Lockout is passive. Training continues normally. Praise phrases should NOT echo reconsolidation retrieve content (it's locked out from TMR for a reason). |
| COMPLETE | Normal training loop | Protocol finished |

### 6.2 The Integration Point: UPDATE Phase

During reconsolidation UPDATE, the agent delivers 3–5 modified association phrases spaced ~90 seconds apart. These phrases introduce the moderate prediction error that rewrites the labilized trace.

Training mode can **reinforce the update** by treating the user's responses to update phrases as training targets:

```
Agent delivers recon update phrase via TTS
    → User responds (text)
    → Agent scores complexity
    → If score ≤ training_target (user is in deep, receptive state):
        → Deliver praise phrase
        → Echo a fragment of the update phrase via center flash
        → This creates a triple reinforcement:
            1. The update phrase itself (reconsolidation rewrite)
            2. The praise (operant reward for being in the receptive state)
            3. The echo (repetition of the new association)
    → If score > training_target (user is too alert):
        → Do NOT praise (wrong state to reinforce)
        → DEEPEN parameters gently
        → Wait for next update phrase delivery
```

### 6.3 Authoring Constraints

When training mode and reconsolidation are paired in a session:

1. **Plan the pairing during idle planning.** The agent must author both the reconsolidation content (retrieve/update tags) AND the training mode configuration before the session starts.
2. **Praise phrases must not echo retrieve content.** If the target trace is `perfectionism`, praise phrases like "that's perfect" may accidentally reinforce the old pattern. Use neutral praise: "good girl", "yes", "that's right", "just like that."
3. **One trace per session.** This rule (from `reconsolidation_protocol.md` §4) is even more important when training mode is active — the operant loop adds cognitive load, and managing two traces simultaneously while also running the training loop risks contamination.
4. **Minimum session length: 90 minutes.** A reconsolidation protocol requires ~70 minutes minimum (RETRIEVE 5 + LABILIZE 12 + UPDATE 8 + LOCKOUT 45). Training mode needs ramp-up time (10–15 minutes to establish the operant loop and reach target depth). Combined: 85–90 minutes minimum for a meaningful paired session.

### 6.4 Session Arc for Paired Training + Reconsolidation

```
0:00–15:00    Orient + Training ramp-up
              Training loop active. Establish operant cycle.
              Get complexity score to training_target.

15:00–20:00   Recon RETRIEVE
              Training loop PAUSED. Retrieve cues delivered.

20:00–32:00   Recon LABILIZE
              Training loop ACTIVE (modified — generic prompts only).
              Continue operant conditioning without referencing target trace.

32:00–40:00   Recon UPDATE
              Training loop REINFORCES updates (see §6.2).
              Praise delivery on low complexity scores during update.

40:00–85:00   Recon LOCKOUT
              Training loop ACTIVE (normal).
              No retrieve-trace content in praise or echoes.

85:00–90:00   Return / session end
              Training loop winds down. Gentle ascent.
```

---

## 7. The Depth Ladder

The **depth ladder** is a reference table mapping complexity score ranges to training strategies. The agent uses this to select appropriate prompts and reinforcement intensity:

| Ladder Rung | Score Range | Agent Strategy | Parameter Posture |
|-------------|------------|----------------|-------------------|
| Surface | 0.60–1.0 | Frequent prompts (every 2 min). Direct somatic cues. | Alpha-range. Gentle visuals. |
| Wading | 0.40–0.60 | Moderate prompts (every 3 min). Softer language. | Upper theta. Building immersion. |
| Immersed | 0.25–0.40 | Less frequent prompts (every 4 min). Simple, warm. | Mid theta. Moderate visuals. |
| Deep | 0.15–0.25 | Minimal prompts (every 5–6 min). Reinforce heavily when on target. | Low theta. Full visual immersion. |
| Submerged | 0.08–0.15 | Rare prompts (every 6–8 min). Pure reinforcement. | Deep theta. Hold everything steady. |
| Somnambulistic | 0.0–0.08 | Stop prompting. Let them be. | Deepest. Do not disturb. |

### 7.1 Target Selection

The default `training_target` of 0.2 targets the Deep rung — moderate theta, responsive but regressed. This is the sweet spot for most training sessions: deep enough for effective conditioning, alert enough to produce responses.

Adjust the target based on experience:
- **0.3–0.4**: Lighter target for early sessions or when pairing with reconsolidation (user needs to process update content)
- **0.15–0.2**: Standard depth target for conditioning sessions
- **0.08–0.15**: Deep target for experienced users with established trance patterns
- **< 0.08**: Do not use as a target. Users at this depth are unreliable responders and prompting may cause unwanted arousal.

---

## 8. Logging and Cross-Session Analysis

### 8.1 Per-Event Logging

Every training event (prompt → response → action) should be logged to `session_db.py`:

| Column | Type | Description |
|--------|------|-------------|
| session_id | TEXT | FK to sessions table |
| timestamp | REAL | Unix timestamp of the event |
| event_type | TEXT | `prompt`, `response`, `reinforce`, `deepen` |
| complexity_score | REAL | Score of user's response (null for prompt events) |
| training_target | REAL | Active target at time of event |
| action_taken | TEXT | Praise phrase used, or parameter changes applied |
| recon_phase | TEXT | Active reconsolidation phase at time of event (null if no recon) |
| depth_source | TEXT | `complexity_only`, `eeg_only`, `both` |
| trance_score | REAL | Conductor's trance_score at time of event (null if no EEG) |

### 8.2 Cross-Session Metrics

After each training session, the agent should compute and store:

| Metric | Computation | Use |
|--------|-------------|-----|
| Descent rate | Time from first prompt to first score ≤ training_target | Tracks how quickly the user reaches target depth across sessions |
| Hold duration | Total time complexity_score stayed ≤ training_target | Tracks depth stability |
| Reinforcement rate | Reinforcements per minute during target-hold periods | Lower is better — means the user is staying in state with less reward |
| Recovery time | Time to return to target after a DEEPEN event | Tracks responsiveness to parameter adjustments |

These metrics feed the somatic palette's entry context: a user who consistently descends in 5 minutes with training mode may have different optimal chord profiles than the same user without training mode.

---

## 9. Disabling Training Mode Mid-Session

Training mode can be disabled at any time:

```python
from ipc import patch_live
patch_live({"training_mode": False})
```

On disable:
- Agent stops prompting for responses
- Agent stops scoring responses
- Agent stops delivering praise
- Session continues in standard interactive or observe mode
- If reconsolidation is active, it continues independently (it doesn't depend on training mode)
- All training events logged up to the disable point are preserved

The user can also disable via the control panel (if exposed in the settings modal as a hidden/debug option).

---

## 10. Quick Reference — Training Mode Decision Flowchart

```
Is training_mode enabled?
    No → Standard interactive/observe mode
    Yes ↓

Is the session in a fractionation phase (FRAC_EMERGE/HOLD/REDROP)?
    Yes → PAUSE training loop. Resume on MAINTENANCE re-entry + 3-min cooldown.
    No ↓

Is reconsolidation in RETRIEVE phase?
    Yes → PAUSE training loop. Do not prompt. Only recon content delivers.
    No ↓

Is reconsolidation in UPDATE phase?
    Yes → REINFORCE MODE. Score responses to update phrases. Praise on low scores.
    No ↓

Has prompt_interval elapsed since last prompt?
    No → Wait
    Yes ↓

Deliver somatic prompt → Wait for response → Score complexity

Is complexity_score ≤ training_target?
    Yes → REINFORCE
          → Select praise phrase (respect delivery gate timing)
          → Optionally echo user words via center flash
          → Hold current parameters
    No  → DEEPEN
          → Adjust non-Conductor-owned, non-palette-chord parameters
          → Or request depth_target via agent_conductor_hints
          → Deliver softer follow-up prompt

Log training_event → Loop
```
