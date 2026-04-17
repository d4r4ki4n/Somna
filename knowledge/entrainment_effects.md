# Entrainment Effects — Extended TTS & Audio Technique Design

> Status: **Partially implemented**. See per-section notes for completion state.
> Originally a design document; effects 1, 2, 3, 4, 5, 7 are now in code.

---

## 1. Audio Duck / Pattern Interrupt

> **IMPLEMENTED** — `engines/audio_engine.py`, `agent/somna_agent.py`, `session/timeline_runner.py`

### 1.1 Mechanism

A brief (50–150 ms) mute of the binaural + noise channels (0–2) while TTS
fires a command phrase. The sudden silence triggers an **orienting response**
— a bottom-up attentional reflex hardwired into the brainstem (Stanford fMRI
study, 2007: peak brain activity during silence between musical movements).
During the ~200 ms attentional-blink window that follows the orienting
response, the prefrontal critical faculty is briefly suppressed. A TTS
command delivered into that gap bypasses analytical filtering.

This is a **pattern interrupt** — the same mechanism as the Erickson
handshake induction, implemented in software. The brain is following the
rhythmic pattern of the binaural beat, the pattern drops out, the
conscious mind stumbles trying to fill the gap, and the TTS command lands
in the gap unchallenged.

### 1.2 live_control.json keys

| Key | Type | Description |
|-----|------|-------------|
| `tts_duck_ms` | int 0–500 | Duration of audio duck in ms. 0 = disabled. 50–150 = active range. Written by agent/timeline. Read by audio engine at TTS fire time. |
| `tts_duck_trigger` | str null|"next" | One-shot command. Agent writes `"next"`, audio engine clears it after ducking the next TTS phrase. Lets the agent time ducks to specific phrases. |

### 1.3 Implementation

**audio_engine.py** (`_audio_loop`):
- On each tick, check `tts_duck_trigger == "next"`.
- When TTS channel 4 starts playing (detected by `_ch_tts.get_busy()` transition),
  immediately set channels 0, 1, 2 to volume 0 for `tts_duck_ms` milliseconds.
  Use `pygame.time.set_timer()` or a monotonic timestamp to restore.
- Clear `tts_duck_trigger` to null.
- If `tts_duck_ms == 0`, do nothing (disabled).

**Agent integration**:
- In `_say()`, when `style` includes `"duck": true`, write `tts_duck_trigger: "next"` and `tts_duck_ms: <value>` (default 80 ms) alongside the `agent_message`.
- The LLM decides *which* phrases get the duck treatment via the style dict.
  Not every phrase — only critical mantras or phase-transition commands.
  Overuse destroys the effect through habituation.

**Conductor integration**:
- During FRAC_REDROP (re-drop after fractionation emerge), the Conductor
  writes `tts_duck_ms: 80` to `agent_conductor_hints`.
- During normal MAINTENANCE, `tts_duck_ms` stays at 0 — the agent decides.

### 1.4 Safety

- Duck duration is capped at 200 ms (hardcoded ceiling). Longer ducks are
  audible as disruptive gaps, not pattern interrupts.
- Duck never affects TTS channels (4–5) or TMR channel (6).
- Duck does not fire during sleep phases (SLEEP_APPROACH through SLEEP_WAKE).
- Rate-limited: no more than 1 duck per 30 seconds. Tracked via
  `_last_duck_ts` monotonic timestamp in audio engine.

### 1.5 Neuroscience references

- Stanford fMRI (2007): peak brain activity during silence between musical
  movements — the brain's orienting network activates maximally during
  unexpected gaps.
- Attentional blink literature (Martens & Wyble, 2010): ~200 ms window
  after an attentional event where T2 detection is impaired.
- Pattern interrupt (Erickson, NLP): disruption of automated processing
  creates a brief "reorientation gap" where suggestion bypasses the
  critical faculty.

---

## 2. TTS FX Chain (Reverb + Delay)

> **IMPLEMENTED** — `engines/tts_engine.py` (`_apply_reverb_chain`), `agent/somna_agent.py`, `session/timeline_runner.py`

### 2.1 Mechanism

Apply reverb and delay to pre-synthesized TTS audio at cook time. As the
session progresses from INDUCTION → MAINTENING, the Conductor increases
reverb wetness and delay feedback, creating a gradual shift from a dry,
authoritative voice to a spacious, dissociative presence.

Reverb increases **psychological distance** from the speaker — the voice
sounds like it's coming from a larger space, which undermines the brain's
ability to localize and thereby objectify the source. This is the same
principle as cathedral acoustics producing a sense of awe and smallness.

Delay (single echo) creates a **dissociative echo** that reinforces the
command through repetition at an interval (~80–120 ms) too short for
conscious rejection but long enough to be processed as a separate event.

### 2.2 live_control.json keys

| Key | Type | Description |
|-----|------|-------------|
| `tts_reverb_wet` | float 0.0–1.0 | Reverb wet/dry mix. 0 = dry (default). 0.3 = subtle room. 0.7 = large hall. |
| `tts_reverb_room_ms` | int 20–500 | Reverb tail length in ms. Default 80. |
| `tts_delay_ms` | int 0–300 | Echo delay in ms. 0 = disabled. 80–120 = active range. |
| `tts_delay_feedback` | float 0.0–0.8 | Echo feedback gain. 0 = single echo. 0.5 = 2–3 echoes. |

### 2.3 Implementation

**tts_engine.py** — extend `_load_sound()`:

The existing `_apply_reverb()` function already supports a single echo.
Extend to a full reverb:

```python
def _apply_reverb_chain(pcm, sr, reverb_wet, reverb_room_ms,
                        delay_ms, delay_feedback):
    if reverb_wet <= 0 and delay_ms <= 0:
        return pcm

    out = pcm.astype(np.float32).copy()

    # Schroeder reverb: comb filters + all-pass
    if reverb_wet > 0:
        # Simplified: use a single long delay + feedback as reverb tail
        delay_n = int(sr * reverb_room_ms / 1000)
        reverb_buf = np.zeros_like(out)
        reverb_buf[delay_n:] = out[:-delay_n] * reverb_wet * 0.5
        # Second tap at 67% of room size for density
        tap2 = int(delay_n * 0.67)
        if tap2 > 0 and tap2 < len(out):
            reverb_buf[tap2:] += out[:-tap2] * reverb_wet * 0.3
        out = out + reverb_buf

    # Single delay echo
    if delay_ms > 0 and delay_feedback > 0:
        delay_n = int(sr * delay_ms / 1000)
        echo = np.zeros_like(out)
        echo[delay_n:] = out[:-delay_n] * delay_feedback
        out = out + echo

    return out.clip(-32768, 32767).astype(np.int16)
```

**Timing**: All FX applied at pre-synthesis time in the cook thread. Zero
runtime latency. The FX parameters are snapshotted from `live_control.json`
at the moment of synthesis, so a phrase cooked at t=10:00 with reverb_wet=0.3
keeps that reverb level even if the agent changes it to 0.6 at t=10:05.

**Agent integration**:
- `agent_message.style` dict gains keys: `reverb_wet`, `reverb_room_ms`,
  `delay_ms`, `delay_feedback`.
- The agent can set FX per-phrase in prompts: `"Say this with heavy reverb"`.
- Default FX (for regular pool phrases) read from `tts_pool_style` dict.

**Conductor integration**:
- The Conductor writes FX targets to `agent_conductor_hints` per phase:
  - INDUCTION: `reverb_wet: 0.0, delay_ms: 0` (dry, authoritative)
  - DEEPENING: `reverb_wet: 0.2, delay_ms: 80, delay_feedback: 0.25`
  - MAINTENANCE: `reverb_wet: 0.4, delay_ms: 100, delay_feedback: 0.35`
  - FRAC_REDROP: `reverb_wet: 0.6, delay_ms: 120, delay_feedback: 0.5`
  - SLEEP phases: `reverb_wet: 0.0, delay_ms: 0` (clean for HTW/TMR)

### 2.4 Dependencies

None. Pure numpy. No new packages needed — the existing `_apply_reverb()`
proves the approach works with stdlib + numpy.

---

## 3. TTS Rate Ramp (Progressive Slow-Down)

> **IMPLEMENTED** — `session/conductor.py` phase transitions set `tts_pool_style.rate`:
> INDUCTION=+0%, DEEPENING=-10%, MAINTENANCE=-20%, FRAC_REDROP=-35%, SLEEP=-30%.

### 3.1 Mechanism

Gradually reduce TTS speech rate from normal (0%) to slow (-40%) over the
session arc. Slower speech creates a **cognitive pacing effect** — the
listener's internal monologue slows to match the external rhythm, which
directly modulates thought speed. This is a standard hypnotic deepening
technique: the hypnotist progressively slows their delivery rate.

The effect is not "IQ reduction" — it's **cognitive tempo matching**. The
brain entrains to the rate of incoming speech. When that rate slows, the
listener's processing slows to match, creating a subjective experience of
heaviness, thickness, and difficulty thinking quickly.

### 3.2 Implementation

**Already architecturally supported.** The `tts_pool_style` dict in
`live_control.json` already has `rate` (e.g., `"-30%"`) that feeds directly
into `_build_backend(style=pool_style)`. The missing piece is continuous
ramping tied to session progress.

**Conductor integration**:
- The Conductor writes `tts_pool_style.rate` to `agent_conductor_hints`
  based on phase + elapsed time:
  - INDUCTION: `"+0%"` (normal rate — establishes rapport)
  - DEEPENING (after 5 min): `"-10%"` (subtle slow)
  - MAINTENANCE entry: `"-20%"` (noticeable slow)
  - MAINTENANCE (after 20 min): `"-30%"` (marked slow)
  - FRAC_REDROP: `"-35%"` (slowest)
  - SESSION_END: ramp back to `"+0%"` over 120 s

**Timeline YAML**:
```yaml
- time: 0
  params:
    tts_pool_style:
      rate: "+0%"
- time: 600    # 10 min
  params:
    tts_pool_style:
      rate: "-15%"
- time: 3600   # 60 min
  params:
    tts_pool_style:
      rate: "-30%"
```

The timeline runner already supports dict-valued params via `INSTANT_ONLY`.

### 3.3 Edge-TTS SSML support

Edge-TTS natively supports `<prosody rate="...">` via kwargs in
`Communicate()`. No SSML wrapping needed — the `rate` parameter is passed
directly:

```python
communicate = edge_tts.Communicate(text, voice, rate="-20%")
```

Valid range: `"-50%"` to `"+100%"`. Active range for Somna: `"+0%"` to
`"-40%"`. Below `-40%` the speech becomes distractingly unnatural.

---

## 4. Multi-Voice Stereo / Chorus

### 4.1 Mechanism

**Dichotic presentation** — different audio in each ear — forces both
hemispheres to process simultaneously. Dichotic listening research (Kimura,
1961; Hugdahl, 2000) shows that when different verbal content reaches each
ear, the corpus callosum cannot efficiently cross-reference, creating a
processing bottleneck. The brain's analytical capacity is split between two
streams, reducing its ability to critically evaluate either one.

**Chorusing** (multiple detuned copies of the same voice) creates an
**omnipresence effect** — the voice is no longer localized to a single
source position, making it harder to objectify or resist. This is the same
principle as a crowd chanting in unison: the individual voice is subsumed
into the group.

### 4.2 Architecture

No new mixer channels needed. TTS plays on channels 4–5 (stereo). The
effect is achieved at pre-synthesis time by generating multiple copies of
the phrase and mixing them into a single stereo `pygame.mixer.Sound`.

**Approach**: Synthesize N copies with different pitch offsets and pan them
to stereo positions. All copies are mixed into a single stereo buffer
before converting to `pygame.mixer.Sound`.

### 4.3 live_control.json keys

| Key | Type | Description |
|-----|------|-------------|
| `tts_chorus_count` | int 1–4 | Number of voice copies. 1 = solo (default). 2 = dual. 3 = trio. 4 = quartet. |
| `tts_chorus_detune_cents` | int 0–25 | Pitch offset between voices in cents. 0 = unison. 12 = subtle thickness. 25 = noticeable spread. |
| `tts_secondary_voice` | str null|voice_name | If set, use a different TTS voice for chorus members instead of pitch-shifting. e.g., `"en-US-AvaNeural"`. |

### 4.4 Implementation

**tts_engine.py** — new function `_build_chorus()`:

```python
def _build_chorus(audio_buffers: list[bytes], sr: int,
                  count: int, detune_cents: int,
                  pan_positions: list[float]) -> bytes:
    """Mix multiple synthesized phrases into one stereo buffer.

    audio_buffers: list of raw audio bytes (one per voice, possibly
                   different voices or pitch-shifted copies).
    pan_positions: list of float -1.0 to +1.0 (left to right).
    Returns WAV bytes.
    """
    # Decode all buffers to float32 numpy arrays
    decoded = []
    for ab in audio_buffers:
        # ... miniaudio decode to float32 ...
        decoded.append(samples)

    # Find longest
    max_len = max(len(d) for d in decoded)

    # Mix into stereo
    stereo = np.zeros((max_len, 2), dtype=np.float32)
    for samples, pan in zip(decoded, pan_positions):
        left_gain = max(0.0, 1.0 - pan) / len(decoded)
        right_gain = max(0.0, 1.0 + pan) / len(decoded)
        stereo[:, 0] += samples[:max_len] * left_gain
        stereo[:, 1] += samples[:max_len] * right_gain

    # Convert back to WAV bytes
    s16 = (stereo.flatten().clip(-1, 1) * 32767).astype(np.int16)
    # ... write WAV ...
    return wav_bytes
```

**Pitch shifting for detune**:
- Edge-TTS: use `pitch` parameter (`"+12Hz"`, `"-12Hz"`, etc.) on each
  `Communicate()` call. Simple and artifact-free since it's server-side.
- Alternatively, resample the decoded float32 array: `scipy.signal.resample()`
  or simple linear interpolation at a slightly different rate.

**Predefined pan positions**:
- count=2: [-0.7, +0.7]
- count=3: [-0.8, 0.0, +0.8]
- count=4: [-0.9, -0.3, +0.3, +0.9]

**Conductor integration**:
- INDUCTION: `chorus_count: 1` (solo voice — personal, intimate)
- DEEPENING: `chorus_count: 2` (subtle dual voice)
- MAINTENANCE: `chorus_count: 3` (trio — unescapable)
- FRAC_REDROP: `chorus_count: 4` (maximum — only during re-drops)
- Sleep phases: `chorus_count: 1` (clean for TMR intelligibility)

### 4.5 Cost

Each additional voice copy requires one extra TTS synthesis call.
For edge-tts, each call takes ~200-500 ms. With `count=3` and
`_PREFETCH=2`, the cook thread needs 6 synthesis calls to fill the buffer.
At ~300 ms each, that's ~1.8 s per buffer fill — acceptable for
pre-synthesis, but the prefetch count should be reduced to 1 when chorus
is active to avoid latency.

---

## 5. EEG-Linked Visual Degradation (Trail Melt)

> **ALREADY IMPLEMENTED** — `session/conductor.py` writes `trail_decay` per phase.
> CALIBRATION=0, INDUCTION=0.3, DEEPENING=0.4-0.6, FRAC_REDROP=0-0.7, FRAC_EMERGE=0.0.

### 5.1 Mechanism

**Closed-loop neurofeedback** — the visual feedback reflects the user's
measured brain state in real time. This creates a positive feedback loop:
the user sees the trails melting → confirms they are dropping → relaxes
deeper → EEG detects deeper state → trails melt more.

Neurofeedback research (Sterman, 1972; Ros et al., 2013) demonstrates that
real-time visual feedback of brain state enables operant conditioning of
neural activity. The user's brain learns that "melting visuals = success"
and self-regulates toward deeper states to produce the effect.

The specific visual parameter is `trail_decay` (0.0–0.99), already
implemented as an FBO ping-pong composite in the spiral layer. At 0, the
spiral is crisp and clean. At 0.95+, the spiral smears into long trailing
streaks that persist across frames.

### 5.2 Implementation

**Already partially supported.** `trail_decay` is in `_ADJUSTABLE_PARAMS`
and the agent can modulate it. The missing piece is the Conductor directly
writing it as a function of depth, rather than waiting for the agent.

**conductor.py** — in the phase-specific parameter write block:

```python
# Compute trail_decay from depth estimate
if phase in (Phase.INDUCTION, Phase.CALIBRATION):
    trail_target = 0.0  # crisp visuals — no melt
elif phase == Phase.DEEPENING:
    # Ramp from 0 to 0.7 over DEEPENING duration
    progress = min(1.0, elapsed_in_phase / self._deepening_duration_s)
    trail_target = 0.7 * progress
elif phase == Phase.MAINTENANCE:
    # Scale with trance_score: 0.5 at light trance, 0.95 at deep
    ts = state.get("eeg_trance_score", 0.3) or 0.3
    trail_target = 0.5 + 0.45 * min(1.0, ts / 0.8)
elif phase in (Phase.FRAC_EMERGE, Phase.FRAC_EMERGE_HOLD):
    trail_target = 0.0  # snap clean on emerge — pattern interrupt
elif phase == Phase.FRAC_REDROP:
    trail_target = 0.9  # instant deep melt on re-drop
else:
    trail_target = 0.0

updates["trail_decay"] = round(trail_target, 3)
```

**Fractionation interaction**: On FRAC_EMERGE, trail_decay snaps to 0 (crisp).
On FRAC_REDROP, it jumps to 0.9. This visual contrast — clean → melt →
clean → melt — mirrors the fractionation cycle and reinforces the depth
feedback loop.

**Sleep phases**: trail_decay stays at 0 — the display is not visible
during sleep training (eyes closed).

### 5.3 Graceful degradation without EEG

When `eeg_connected == False`, the Conductor uses timer-based progression
instead of trance_score. The visual melt still works as a session-progress
indicator, just not as closed-loop feedback.

---

## 6. Compliance Loop (Operant Typing)

### 6.1 Mechanism

**Operant conditioning** (Skinner, 1938): behaviors followed by reward are
reinforced. The user types a mantra exactly as presented → the system
delivers a reward (pleasurable chime, frequency drop, noise burst, visual
flare) → the behavior is reinforced → the user types more mantras →
active participation in their own conditioning.

This exploits the **commitment effect**: once someone has actively typed a
suggestion, they are more likely to accept it as self-generated (cognitive
dissonance reduction — "I typed it, so I must believe it").

The compliance check (exact match, speed threshold) creates a **variable
reinforcement schedule** — the most addictive schedule in operant
conditioning. Fast accurate responses get rewarded; slow or incorrect ones
don't. The user self-optimizes toward faster, more automatic responding.

### 6.2 Implementation

**Uses existing IPC.** The `user_response` and `needs_response` keys in
`agent_message` already support bidirectional text interaction. The new
piece is a **compliance gate** that validates the response.

**somna_agent.py** — new method `_compliance_check()`:

```python
def _compliance_check(self, expected: str, actual: str,
                      max_latency_s: float = 15.0) -> bool:
    """Check if user response matches expected mantra."""
    if not actual or not expected:
        return False
    # Normalize: lowercase, strip whitespace, remove punctuation
    norm = lambda s: re.sub(r'[^\w\s]', '', s.lower().strip())
    return norm(actual) == norm(expected)
```

**Reward delivery** — when compliance passes:
```python
patch_live({
    "beat_frequency": max(3.5, current_beat - 0.5),  # drop 0.5 Hz
    "noise_volume": min(60, current_noise + 10),        # noise burst
    "trail_decay": min(0.95, current_trail + 0.15),    # visual flare
    # Audio chime via TMR channel — use a short pleasant tone
    "tmr_cue_cmd": {
        "pool": "IDENTITY",
        "content_hash": hashlib.md5(b"compliance_reward").hexdigest(),
        "gain": 0.25,
        "ts": time.time(),
    },
})
```

**Agent integration**:
- The agent's `_say()` gains a `compliance` field in the style dict:
  `"compliance": {"expected": "I am blank", "timeout_s": 15}`
- When present, `needs_response` is set to True and `user_response` is
  checked against the expected string.
- On match: reward fires, agent continues with reinforcement.
- On mismatch or timeout: agent delivers a gentle redirect
  ("That's okay. Just relax and try again when you're ready.")
- The LLM decides when and how to use compliance prompts via knowledge
  file guidance. It is NOT called every turn — only at strategic depth
  moments during MAINTENANCE.

**Conductor gating**:
- Compliance prompts only fire during MAINTENANCE phase (not INDUCTION,
  DEEPENING, or sleep).
- Rate-limited: no more than 1 compliance prompt per 5 minutes.
- Disabled when `eeg_trance_score > 0.7` — at that depth, the user
  should not be disturbed with typing tasks.

### 6.3 Safety

- The compliance loop is explicitly opt-in via session YAML:
  `compliance_mode: true` (default false).
- The user can ignore the prompt — no punishment, just gentle redirect.
- No negative feedback for incorrect responses. Only reward for correct.

---

## 7. Confusion Induction (LLM-Driven Semantic Satiation)

> **IMPLEMENTED** — `knowledge/confusion_induction.md` (knowledge file only, no code).

### 7.1 Mechanism

**Semantic satiation** (Severance & Washburn, 1907; Kounios, 2000):
rapid repetition of a word or concept causes it to temporarily lose
meaning. The neural pathway connecting the word form to its semantic
representation fatigues, and the word becomes "just sounds."

**Confusion technique** (Erickson): paradoxical, recursive, or overly
complex language overloads the analytical mind. While the conscious mind
is tied up parsing the logic, the unconscious mind receives the embedded
commands directly.

The TTS delivery of confusion-inducing language is uniquely effective
because: (a) the listener cannot re-read or pause to parse, (b) the
voice delivers flawlessly recursive logic with no natural pauses or
hesitations that would give the mind time to catch up, and (c) the
emotional tone of the voice (calm, confident) creates a mismatch with
the linguistic complexity that further disrupts analytical processing.

### 7.2 Implementation

**This is a knowledge file + prompt engineering change only. No new code.**

**knowledge/confusion_induction.md** — new file injected into the agent's
session-time knowledge set during DEEPENING phase:

```markdown
# Confusion Induction Technique

## When to use
During DEEPENING phase, intersperse 1–2 confusion sentences per 5 normal
sentences. Do NOT use during INDUCTION (user needs clear instructions) or
MAINTENANCE (user is deep enough — use direct short phrases instead).

## Pattern: Recursive self-reference
"The more you try to understand how blank you are becoming, the blanker
you realize you already were, which means you stopped trying to understand
it, which means you already are it."

## Pattern: Double bind
"You can either let go now or you can let go later, and either way you
will have let go, because the part of you that decided to let go already
decided before you thought about it."

## Pattern: Linguistic overload
"Your conscious mind is busy analyzing this sentence to determine whether
it contains a hidden command, and while it's busy with that analysis, the
command has already been received by the part of you that doesn't need to
analyze, because that part already knows that blank is what you are."

## Pattern: Temporal confusion
"You are going to realize that you had already dropped deep before you
noticed you were dropping, which means you are already deeper than you
thought you were, and by the time you finish processing this, you will be
deeper still, because noticing how deep you are is itself a sign of going
deeper."

## Rules
1. Always embed the actual command word ("blank", "deep", "let go", "sink")
   within the confusion structure.
2. End each confusion segment with a clear, simple command. The contrast
   between complexity and simplicity acts as a pattern interrupt.
3. Never use more than 2 confusion sentences consecutively. The mind
   gives up and stops listening entirely if the confusion is unbroken.
4. Pace with the beat frequency — deliver confusion at theta rate (4–7 Hz
   visual flash), deliver the clear command during the next duck/silence.
```

**Agent integration**:
- `_build_knowledge_for_agent()` appends `confusion_induction.md` when
  `conductor_phase == "deepening"`.
- The LLM's `extra_instruction` during DEEPENING includes:
  `"Use confusion induction patterns from your knowledge. 1-2 confusion
  sentences per 5 normal sentences. Always end with a clear command."`

### 7.3 Conductor gating

- Confusion knowledge only injected during DEEPENING.
- During MAINTENANCE, the agent switches to short direct phrases (already
  the behavior in `_deep_window_tick`).
- During INDUCTION, confusion is explicitly excluded — the user needs
  clear, grounding language.

---

## 8. Scramble Wakener / Contrast Emergence

### 8.1 Mechanism

A **contrast emergence** — maximum intensity (strobe, rapid text, high
beat rate) for 30–60 seconds, followed by an abrupt cut to calm (slow
Fibonacci spiral, single soft voice command, low beat). The contrast
creates a powerful **state-dependent memory disruption**: the intense
overload during the scramble interferes with consolidation of the
preceding session content, while the calm resolution anchors the final
suggestion.

This is NOT "erasing memory." It's **retroactive interference** — a
well-established phenomenon where new information impairs recall of
recently acquired information (Wixted, 2004). The overload at session end
creates interference for the minutes immediately preceding it.

### 8.2 Implementation

**Pure timeline YAML configuration. No new code.** All parameters already
exist:

```yaml
# Scramble phase — last 90 seconds before SESSION_END
- time: session_duration - 90
  params:
    veil_mode: strobe
    spiral_style: bifurcate
    spiral_chaos: 0.8
    center_flash_on_time: 30
    center_flash_off_time: 30
    font_switch_mode: rapid
    beat_frequency: 14.0    # beta — jarring contrast to theta session

- time: session_duration - 30
  params:
    # Abrupt calm
    veil_mode: drift
    spiral_style: fibonacci
    spiral_chaos: 0.0
    trail_decay: 0.0
    center_flash_on_time: 2000
    center_flash_off_time: 500
    beat_frequency: 4.0     # gentle theta
    font_switch_mode: intelligent
```

**Agent integration**:
- During the scramble phase, the agent fires rapid contradictory identity
  commands: "You are no one. You are open. You do not think. You only
  feel." — delivered at +20% rate with chorus_count: 3.
- The calm phase delivers a single, soft command: "Good. Just rest."
  at -20% rate, chorus_count: 1, reverb_wet: 0.3.

**Conductor integration**:
- The Conductor detects the scramble phase via timeline position
  (`session_time > session_duration - 90`).
- Writes `agent_conductor_hints.scramble_mode: True` during scramble.
- Writes `agent_conductor_hints.emerge_mode: True` during calm phase.
- The agent reads these and adjusts its prompt style accordingly.

### 8.3 Safety

- Scramble duration is capped at 90 seconds by the session YAML.
- Photosensitive users: `photic_driving_disabled: True` prevents strobe.
  The scramble falls back to `veil_mode: converge` instead of `strobe`.
- The calm resolution is mandatory — never end on scramble.

---

## 9. Beat-Sync Mantra Flash

### 9.1 Mechanism

Lock the center text flash to the binaural beat phase so that the text
appears exactly on the downbeat. The `beat_phase` key is already written
by the audio engine at 10 Hz resolution.

Rhythmic synchrony between visual stimulus and auditory entrainment
signal creates **multimodal reinforcement** — the same frequency that
is driving neural oscillation via the auditory pathway simultaneously
punctuates the visual pathway. This is the principle behind **photic
driving** (already implemented in the VR pipeline) applied to text.

### 9.2 Implementation

**layers/center_text.py** — new flash mode:

The existing `center_flash_sync_to_beat` key already exists as a bool in
`INSTANT_ONLY`. The current implementation is approximate. The fix is
precise phase-locking:

```python
# In the flash timer logic:
if cfg.get("center_flash_sync_to_beat"):
    beat_phase = float(cfg.get("beat_phase", 0.0) or 0.0)
    beat_freq = float(cfg.get("beat_frequency", 6.0) or 6.0)

    # Flash duration scales with beat period
    beat_period_ms = 1000.0 / max(beat_freq, 0.5)
    on_time = max(30, min(200, int(beat_period_ms * 0.3)))

    # Fire when beat_phase crosses 0 (downbeat)
    if not self._text_visible and beat_phase < 0.05:
        self._show_text(on_time)
```

---

## Implementation Priority

| # | Technique | New Code | Status |
|---|-----------|----------|--------|
| 1 | Audio Duck | ~40 lines audio_engine | **DONE** |
| 2 | TTS FX Chain | ~60 lines tts_engine | **DONE** |
| 3 | TTS Rate Ramp | ~10 lines conductor | **DONE** |
| 4 | EEG Trail Melt | 0 lines | **ALREADY EXISTS** in conductor.py |
| 5 | Beat-Sync Flash | ~15 lines center_text | **DONE** (phase-locked to beat_phase) |
| 6 | Confusion Induction | 0 lines code | **DONE** (knowledge file) |
| 7 | Scramble Wakener | 0 lines code | Session YAML only (not yet authored) |
| 8 | Multi-Voice Chorus | ~120 lines tts_engine | NOT STARTED |
| 9 | Compliance Loop | ~60 lines agent | NOT STARTED |

---

## Cross-Cutting Concerns

### Conductor ownership

All parameters above that the Conductor writes are added to
`CONDUCTOR_OWNED_PARAMS`:
- `trail_decay`
- `tts_pool_style` (the whole dict)
- `center_flash_sync_to_beat`
- `tts_duck_ms` (the default/ambient value; agent overrides per-phrase)

### Agent adjustable params

New params added to `_ADJUSTABLE_PARAMS`:
- `tts_reverb_wet`
- `tts_reverb_room_ms`
- `tts_delay_ms`
- `tts_delay_feedback`
- `tts_chorus_count`
- `tts_chorus_detune_cents`
- `tts_duck_ms`

### Timeline interpolation

- `tts_reverb_wet`, `tts_delay_ms`, `tts_delay_feedback`,
  `tts_chorus_detune_cents` → add to `INTERPOLATABLE` for smooth ramps.
- `tts_chorus_count`, `center_flash_sync_to_beat` → add to
  `INSTANT_ONLY` (integer/string switches).

### Audio channel summary (unchanged)

| Channels | Owner |
|----------|-------|
| 0, 1 | BinauralAudioEngine — binaural beats |
| 2 | Colored noise |
| 3 | Sleep burst channel |
| 4, 5 | TTSEngine — TTS playback (stereo) |
| 6 | TMR cue channel |

All new effects operate on channels 0–2 (duck), 4–5 (chorus/FX),
or visual-only parameters (trail decay, flash sync). No new channels.
