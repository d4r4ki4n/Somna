# Somna — Session Authoring Guide

Sessions live in `sessions/<name>/` and contain:

```
sessions/my_session/
  session.yaml       ← timeline + defaults
  affirmations.txt   ← phrase pool with optional tag groups
  fonts/             ← .ttf / .otf files
  images/            ← .jpg .png .gif .webp .webm (MP4 not supported on Windows)
```

---

## session.yaml

```yaml
name: "My Session"
description: "Example session"

# Session-level defaults (used if a timeline keyframe hasn't set a value yet)
defaults:
  beat_frequency:          10.0    # Hz  — 0.5–40
  carrier_frequency:       200.0   # Hz  — 80–400
  volume:                  75.0    # 0–100

  spiral_style:            "galaxy"
  spiral_count:            4
  spiral_tightness:        6.0
  spiral_thickness:        14
  spiral_speed_multiplier: 1.0
  spiral_chaos:            0.1
  spiral_opacity:          88
  spiral_color_mode:       "rainbow"   # rainbow | solid
  spiral_show_text:        false

  veil_opacity:            40.0
  veil_mode:               null        # null = auto-rotate; or: scroll|rain|drift|converge|tunnel|strobe
  slideshow_interval:      5.0         # seconds between background image switches

  center_flash_sync_to_beat: true
  flash_duty_cycle:          0.38
  flash_variance:            0.15
  center_flash_on_time:      120   # ms (used when sync is OFF)
  center_flash_off_time:     80    # ms (used when sync is OFF)

  shadow_opacity:          30
  shadow_flash_on_time:    40     # ms — keep ≤ 50 ms for subliminal threshold
  shadow_flash_off_time:   180    # ms

  font_switch_mode:        "intelligent"   # intelligent | rapid
  phrases:                 null            # null = use all untagged phrases


# Timeline: a sorted list of keyframes
# Numeric params interpolate smoothly between keyframes.
# String/bool params cut instantly when the keyframe is reached.
timeline:
  - t: 0
    label: "Induction"
    ease: linear
    params:
      beat_frequency:    10.0   # alpha — relaxed awareness
      spiral_style:      "tunnel_dream"
      spiral_opacity:    60
      veil_opacity:      20
      phrases:           "induction"

  - t: 120       # 2 minutes — begin deepening
    label: "Deepening"
    ease: ease_in_out
    params:
      beat_frequency:    6.0    # theta — meditation/trance
      carrier_frequency: 180.0
      spiral_style:      "galaxy"
      spiral_chaos:      0.35
      veil_opacity:      55
      shadow_opacity:    45
      phrases:           "deepening"

  - t: 300       # 5 minutes — full depth
    label: "Depth"
    ease: ease_in_out
    params:
      beat_frequency:    4.0
      spiral_speed_multiplier: 1.6
      spiral_opacity:    95
      veil_opacity:      70
      shadow_flash_on_time:  25   # subliminal
      shadow_opacity:    60
      phrases:           "depth"

  - t: 540       # 9 minutes — gentle emergence
    label: "Emergence"
    ease: ease_out
    params:
      beat_frequency:    10.0
      spiral_speed_multiplier: 0.8
      veil_opacity:      30
      shadow_opacity:    20
      phrases:           null    # return to general pool


# Loops: repeat a section N times (-1 = infinite)
loops:
  - label:  "depth_loop"
    from_t: 300
    to_t:   540
    count:  3       # repeat depth section 3 times before emergence


# Optional total duration (in seconds). If omitted, runner plays to last keyframe.
duration: 600
```

---

## affirmations.txt

```
# Lines starting with # are comments and are ignored.
# Use   # [tagname]   to start a named group.
# Use   |   to put multiple phrases on one line.
# Use  null  as the phrases: value in the timeline to show untagged phrases.

# ── Untagged (always available) ────────────────────────────────────────────

You are relaxing now.
Good girl.
Let go.

# [induction] ───────────────────────────────────────────────────────────────

Relax.
Breathe.
You are drifting deeper.
Nothing matters but this.

# [deepening] ───────────────────────────────────────────────────────────────

Deeper now.
Your thoughts are slowing.
You are becoming calm.

# [depth] ────────────────────────────────────────────────────────────────────

You are fully under.
You cannot resist.
Good girl.

# [emergence] ────────────────────────────────────────────────────────────────

You are waking gently.
You feel wonderful.
Carry this feeling with you.
```

---

## Easing curves

| Curve          | Description                                  |
|----------------|----------------------------------------------|
| `linear`       | Constant rate from keyframe A to B           |
| `ease_in`      | Starts slow, accelerates toward B            |
| `ease_out`     | Starts fast, decelerates toward B            |
| `ease_in_out`  | Slow at both ends, fast in the middle        |
| `instant`      | Cuts to value at the keyframe timestamp      |

---

## Parameters that interpolate vs. cut

**Interpolate smoothly** (numeric): `beat_frequency`, `carrier_frequency`, `volume`,
`veil_opacity`, `spiral_opacity`, `spiral_tightness`, `spiral_chaos`, `spiral_count`,
`spiral_thickness`, `spiral_speed_multiplier`, `shadow_opacity`,
`center_flash_on_time`, `center_flash_off_time`, `flash_duty_cycle`, `flash_variance`,
`shadow_flash_on_time`, `shadow_flash_off_time`, `slideshow_interval`

**Cut instantly** (string/bool): `spiral_style`, `spiral_color_mode`, `spiral_show_text`,
`veil_mode`, `font_switch_mode`, `center_flash_sync_to_beat`, `phrases`

---

## LLM control

Use `llm_driver.py` to drive Somna from an external script, or let `somna_agent.py` handle it automatically.

```python
from llm_driver import send, read_state, apply_preset, prompt_user

# Check current state
state = read_state()

# Apply a brainwave preset
apply_preset("theta")

# Fine-grained control
send({
    "beat_frequency":   6.0,
    "spiral_style":     "fibonacci",
    "veil_opacity":     55,
})

# Ask the user something (shows overlay dialog)
prompt_user("How does your body feel right now?", timeout_s=60)
```

To inject a single affirmation phrase at runtime, write `next_affirmation` directly:

```python
send({"next_affirmation": "let it go"})
```

For bulk phrase updates use the `write_affirmations_batch` tool via `content_agent.py` or the agent's tool-call system. Do not write `affirmations_pool` directly — it is not an adjustable parameter.
