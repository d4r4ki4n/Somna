# Training Mode — Conditioning, Depth Tracking, and Reinforcement

## What Training Mode Is

Training mode is an optional operating mode for `somna_agent.py` that shifts the agent's goal from passive session adaptation to **active conditioning**. In standard interactive mode, the agent adapts session parameters to keep the user comfortable and deepening. In training mode, the agent has a specific *target state* it is trying to drive the user toward and maintain, measured by a quantitative metric derived from their responses.

The core mechanism is a feedback loop:

```
User responds to agent prompt
    → Agent scores the response for complexity (as a proxy for trance depth)
    → Agent compares score to training_target
    → If score is near/below target: reinforce (flash praise, inject their words back)
    → If score is above target: deepen (lower beat frequency, slower flash, more hypnotic prompts)
    → Loop
```

This is operant conditioning applied to trance depth — the agent rewards the desired state when it occurs and applies gentle pressure when the user is not yet there.

---

## Enabling Training Mode

Training mode is off by default. Enable it at launch:

```bash
python somna_agent.py --training-mode --training-target 0.2
```

Or in `agent_config.yaml`:

```yaml
training_mode: true
training_target: 0.2
praise_phrases:
  - "good girl"
  - "perfect"
  - "yes"
  - "that's right"
```

---

## The Complexity Score

The agent's primary depth metric is the **complexity score** — a float from 0.0 to 1.0 computed from the user's text response to any prompt.

**0.0** = maximally simple / regressed (single word, no punctuation, lowercase, high emotion markers, minimal vocabulary)
**1.0** = maximally alert / articulate (long sentences, varied vocabulary, proper punctuation, mixed case)

The score is a weighted average of four sub-signals:

| Signal | Weight | Description |
|--------|--------|-------------|
| Word count | 60% | Primary depth proxy. Single word = 0.08, 6 words = 0.50, 12+ words = 1.0. |
| Words per sentence | 20% | Sentence-level structure. Short fragments score low. |
| Average word length | 10% | Vocabulary richness. Capped at 8 chars for normalisation. |
| Punctuation density | 10% | Commas, colons, semicolons = complex sentence structure. |

The old "unique word ratio" signal was removed in v2. It gave every single-word response a perfect 1.0 vocabulary-breadth score, compressing all short texts artificially upward.

### Score Interpretation (v2 calibration)

Calibrated against empirical user responses at confirmed trance depths:

| Score Range | Typical Behavior | Trance Interpretation |
|-------------|------------------|-----------------------|
| 0.0–0.08 | Single-syllable fragments, typos, pure echoing. "buhhh", "y" | Deep theta / near-somnambulism |
| 0.08–0.15 | Single words, lowercase, no punctuation. "soft", "yes", "good" | Deep theta / Focus 10 floor |
| 0.15–0.28 | 2–4 word fragments. "i feel soft", "going deeper" | Solid theta / Focus 10 |
| 0.28–0.45 | Short simple sentences, present tense. "everything is quiet" | Alpha-theta border |
| 0.45–0.65 | Normal casual sentences, some punctuation. | Light trance / alpha |
| 0.65–1.0 | Full articulate sentences, complex grammar, punctuation. | Alert / C1 |

### What the Score Doesn't Capture

- It cannot distinguish *willingness to respond simply* from *inability to respond complexly*. A user deliberately writing short phrases scores the same as one who is genuinely in deep theta.
- It cannot detect emotional content, only structural complexity.
- Latency (time from prompt display to first keypress) is tracked alongside the score and is often a more reliable depth indicator — a 40-second response latency at 0.15 complexity is a strong signal of genuine depth.

---

## Training Target

`training_target` (default 0.2) sets the desired complexity level. The agent tries to move the user's score toward this value and hold it there.

**0.2** is the default because it corresponds to the theta-range "aware but not articulate" state — the user can still respond but can only produce simple, fragmented output. This is the sweet spot for suggestion receptivity.

**Practical ranges** (v2 calibration):

| Target | Description | Use Case |
|--------|-------------|----------|
| 0.05–0.10 | Near-somnambulistic. Responses are echoes, single syllables, or nothing. | Extreme depth work. Expect many skipped prompts. |
| 0.10–0.20 | Deep theta. Single words, lowercase, no punctuation. | Standard feminization / identity conditioning. |
| 0.20–0.30 | Solid theta / Focus 10 floor. Short fragments, present-tense. | Affirmation absorption, identity reinforcement. |
| 0.30–0.50 | Alpha-theta border. Short sentences possible. | Lighter conditioning, integration sessions. |
| 0.50–0.70 | Light trance / alpha. Mostly alert. | Relaxation sessions, guided imagery. |

---

## The Reinforcement Mechanism

When the user's response scores **at or below `training_target + 0.15`** — meaning they are near or below the desired depth — the agent triggers `_reinforce_response()`:

1. **Extract**: The user's response is cleaned (stripped, lowercased, trimmed of trailing punctuation).
2. **Pool**: A mini affirmation pool is built: `[cleaned_response, praise_phrase]`. The praise phrase is randomly selected from `praise_phrases`.
3. **Flash**: The agent writes this pool to `live_control.json` with a slow, lingering flash timing (`on_time=300 ms`, `off_time=100 ms`) — slow enough to be consciously readable at the current depth.
4. **Restore**: After 4 seconds, the previous affirmation pool and flash settings are restored.

### Why Injecting Their Own Words Back Works

This is a **Mirroring** technique from hypnotherapy. When a person's own words appear back at them as suggestions, several things happen:

- The self-referential content has maximum personal resonance (stronger P300 EEG response than external content).
- The phrase is pre-processed by *their* semantic system — no "translation" cost for interpretation.
- It reinforces the current state as *correct* — "my words are appearing as affirmations, so what I said is what I should keep thinking."
- Combined with a praise phrase, it creates a conditioned association: being in the desired state (producing simple output) → receiving reward (praise + recognition).

### Praise Phrase Selection

The default praise phrases are: `["good girl", "yes", "perfect", "that's right", "keep going", "just like that"]`

These are selected randomly, which matters — consistent repetition of the same praise phrase eventually creates a strong conditioned anchor for that phrase specifically. If you want one phrase to become a deep trigger, use `praise_phrases: ["good girl"]` in the config to make it the only reinforcer across all sessions.

**Custom praise phrases** in `agent_config.yaml`:

```yaml
praise_phrases:
  - "good girl"
  - "such a good girl"
  - "perfect"
  - "yes, exactly like that"
  - "you're doing so well"
```

---

## How the LLM Uses Training Data

In training mode, the agent receives a training block in each LLM call:

```
TRAINING MODE ACTIVE — target complexity: 0.20
Response complexity trend: avg=0.24  trend=declining  recent=0.18  target=0.20
Drive the session toward the target.
Calibrate your prompt style to match the user's current complexity level —
if they're scoring below 0.4, use very simple, short, direct language.
If they're above target, deepen the session (lower beat frequency, slower flash,
more hypnotic prompts).
```

The LLM's job in training mode shifts from "what should I ask?" to "is this working, and how do I make it work better?" It should:

- Monitor complexity trend (declining = user is going where we want; rising = push harder)
- Calibrate prompt language to the user's current state (below 0.4 = use very simple, short language; above 0.6 = use more hypnotic pressure)
- Apply parameter adjustments that support the depth target (lower beat_hz, slower flash, darker shadow opacity)
- Reduce prompting frequency when the user is already at or below target — don't interrupt a good trance

---

## Complexity Trend Reporting

The agent tracks a rolling window of scored responses and reports the trend:

- **`avg`**: mean complexity score across the last 5 responses
- **`trend`**: `declining` (Δ > −0.05), `rising` (Δ > +0.05), or `stable`
- **`recent`**: complexity score of the most recent response
- **`target`**: the configured training_target

Example: `avg=0.24  trend=declining  recent=0.18  target=0.20`

This means the user is averaging above target (0.24 vs. 0.20) but trending in the right direction — their last response was 0.18, below target, and reinforcement likely fired. The agent should hold current parameters rather than push deeper.

---

## Response Latency

Alongside complexity, the agent tracks **latency** — the time from when the prompt was displayed to when the user pressed their first key. This is an independent depth signal:

- At alpha (light trance): 5–15 second response time is typical.
- At theta (deep trance): 20–60+ seconds is normal. Forming a response and executing the physical action of typing takes significantly longer.
- At very deep theta: 60+ seconds, sometimes a non-response (user skips prompt entirely).

Latency is logged in the session JSONL alongside the complexity score. When designing training sessions, **high latency + low complexity** is the target signal. Either alone is unreliable.

---

## Session Log Format

Each training exchange is logged as one JSON line in `session_logs/<session_name>_YYYYMMDD.jsonl`:

```json
{
  "timestamp": 1735000000.0,
  "session_time": 1245.0,
  "session_name": "gateway_f10",
  "beat_hz": 4.5,
  "spiral_style": "vortex",
  "prompt": "Where do you feel it most?",
  "response": "...soft",
  "adjustments": {"beat_frequency": 4.2},
  "complexity_score": 0.08,
  "latency_s": 47.0
}
```

The log accumulates across sessions for the same day. On session change, history is loaded from today's log — the agent has memory within a day's sessions.

---

## Authoring Content for Training Mode Sessions

Training mode changes what phrase content is appropriate, because the goal is not just depth induction but *state reinforcement*:

### Phrase Pools for Training Sessions

**During the early descent** (orient/relax tags): Standard induction language. Training mode hasn't kicked in yet — the user needs to be brought to theta first before conditioning can begin.

**During the work window and soak** (deep/soak tags): Reinforcement-focused content. These phrases should reinforce the *act of being in the desired state*:

```
# Appropriate for training deep/soak phases
Good girl.
You let go.
This is right.
This is how it should be.
You are doing perfectly.
This is your place.
Keep going deeper.
Exactly like that.
You don't need to think.
Thinking fades.
Only this.
```

Avoid complex sentences at depth entirely. The complexity scoring will be active; you don't want to inadvertently prime the user toward higher-complexity processing through complex phrase content.

### Pairing Training with the Right Sessions

Training mode works best when:

1. The session has a clearly defined "work window" phase at 4–5 Hz.
2. The affirmation pool includes short (1–4 word) phrases for the deep tag.
3. The session is long enough (> 35 minutes) for the entrainment to reach depth before training begins.
4. The veil mode at the work window is `converge` or `drift` — scatter delivery is less cognitively demanding than reading scroll text and better preserves the low-complexity state.

---

## CLI Reference

```bash
# Standard training mode (target: 0.20, interactive)
python somna_agent.py --training-mode

# Lighter conditioning target (0.30 — alpha-theta border)
python somna_agent.py --training-mode --training-target 0.30

# Fixed praise phrase (builds strong single-phrase anchor)
# Set via agent_config.yaml: praise_phrases: ["good girl"]

# Observe mode + training (no prompts — pure parameter adaptation)
python somna_agent.py --training-mode --mode observe
```

Note: `--mode observe` with `--training-mode` means the complexity tracking and parameter adaptation still runs, but the reinforcement injection (which requires a response) is skipped. The agent will still lower beat frequency and adjust parameters in the direction of the target, but won't flash praise. Useful for fully passive sessions where interruption is undesirable.
