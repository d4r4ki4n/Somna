Somna — Session & Timeline Format Specification
Version: 1.1
Date: March 23, 2026
Status: Locked
Supersedes: SESSION_PLAYLIST.md v1.1
Parent Document: DESIGN.md v1.3

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A Somna session is a self-contained folder that describes a complete
hypnotic experience: its audio, visuals, text, and how all parameters
evolve over time. The timeline system is the heart of session authoring
— think of it like keyframes in a video editor. The session creator
places keyframes at specific timestamps, sets target values, chooses
easing curves, and Somna handles all interpolation automatically.

Randomization algorithms (font switching, image cycling, phrase
selection) always continue running independently. The timeline controls
the *envelope* of the experience, not every individual event.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. SESSION FOLDER STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

sessions/
└── my_session/
    ├── session.yaml          ← settings, defaults, timeline, loops
    ├── affirmations.txt      ← phrases with optional tag groups
    ├── images/               ← background images (PNG, JPG, GIF, WebP, WebM)
    └── fonts/                ← optional .ttf files for text layers

All files are optional except session.yaml.
If affirmations.txt is absent, the root-level affirmations.txt is used.
If fonts/ is absent or empty, the system font is used.
If images/ is empty, the background layer renders black.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. SESSION.YAML — FULL FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── Identity ──────────────────────────────────────────
name: "Deep Conditioning"          # display name in UI (required)
description: "60-minute induction → deepening → conditioning arc"
author: "anonymous"
duration: 3600                     # seconds — informational, not enforced
version: "1.0"

# ── Master toggles ────────────────────────────────────
start_fullscreen: true             # override display window behavior
beat_sync_master: true             # global on/off for all beat-sync features

# ── Defaults ─────────────────────────────────────────
# Applied at t=0. Any parameter not set by a timeline keyframe
# retains its default value. This is the session's "resting state".
defaults:
  # Binaural
  beat_frequency: 12.0
  carrier_frequency: 200.0
  volume: 75

  # Veil
  veil_opacity: 25
  veil_scroll_speed_x: 1.2
  veil_scroll_speed_y: 0.8

  # Background
  slideshow_interval: 3.0

  # Spirals
  spiral_style: tunnel_dream
  spiral_count: 4
  spiral_opacity: 60
  spiral_tightness: 6.0
  spiral_chaos: 0.1

  # Affirmation layers
  center_flash_on_time: 120
  center_flash_off_time: 80
  shadow_opacity: 25
  font_switch_mode: intelligent

  # Active phrase group (see affirmations.txt tagging)
  # Omit or set to null to use ALL phrases
  phrases: null


# ── Timeline ──────────────────────────────────────────
# Each entry is a keyframe. Numeric parameters interpolate from the
# previous keyframe's value to this keyframe's value, arriving exactly
# at time t. String/boolean parameters switch instantly at time t.
#
# Keys:
#   t        (required) — timestamp in seconds
#   label    (optional) — shown in the timeline editor UI
#   ease     (optional) — easing curve for interpolatable params
#              values: linear | ease_in | ease_out | ease_in_out | instant
#              default: linear
#              "instant" forces all params in this keyframe to cut hard
#   params   (required) — any subset of the defaults keys above

timeline:
  - t: 0
    label: "Induction"
    ease: linear
    params:
      beat_frequency: 12.0
      veil_opacity: 20
      spiral_opacity: 40
      volume: 60
      phrases: induction         # only draw from [induction] tag group

  - t: 300                       # 5:00 — begin deepening
    label: "Deepening"
    ease: ease_in_out
    params:
      beat_frequency: 8.0        # interpolates 12→8 over the 300s before this
      veil_opacity: 45
      spiral_opacity: 75
      spiral_style: galaxy       # string: cuts instantly at t=300
      phrases: deepening

  - t: 900                       # 15:00 — conditioning begins
    label: "Conditioning"
    ease: ease_in
    params:
      beat_frequency: 6.0
      veil_opacity: 70
      spiral_chaos: 0.3
      center_flash_on_time: 80   # faster flashing
      center_flash_off_time: 50
      phrases: conditioning

  - t: 3300                      # 55:00 — wake
    label: "Wake"
    ease: ease_out
    params:
      beat_frequency: 10.0
      volume: 35
      veil_opacity: 15
      spiral_opacity: 30
      phrases: null              # back to all phrases


# ── Loops ─────────────────────────────────────────────
# A loop repeats the segment between from_t and to_t N times
# before the timeline continues past to_t.
# The loop's internal timeline keyframes run normally each iteration.
# count: -1 means loop forever (session never advances past this point).

loops:
  - label: "Deepening loop"
    from_t: 300
    to_t: 900
    count: 3                     # play deepening segment 3× before conditioning

  - label: "Conditioning hold"
    from_t: 900
    to_t: 3300
    count: 1                     # play once (default — same as no loop)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. AFFIRMATIONS.TXT — TAGGING SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Without tags, affirmations.txt is just a flat list — every phrase is
always in the pool. This is the default and nothing about existing
sessions needs to change.

Tags let you group phrases into named sets. A tag header is a comment
line in the format:

    # [tagname]

Every phrase below that line belongs to that tag group, until the next
tag header or the end of the file. A phrase can only belong to one group.

When a timeline keyframe sets `phrases: tagname`, Somna draws only from
that group. When `phrases: null` (or the key is absent), all phrases from
all groups are in the pool.

EXAMPLE affirmations.txt:
─────────────────────────────────────────────────────────
# [induction]
Just breathe
Let your body relax completely
You are safe here
Each breath takes you deeper

# [deepening]
Deeper and deeper
Your mind is open and receptive
Every word sinks in effortlessly
Relaxing further with every breath

# [conditioning]
You are becoming who you want to be
These words are true
You absorb everything you hear
This is what you want
─────────────────────────────────────────────────────────

RULES:
- Tag names are lowercase, no spaces (use underscores if needed)
- Phrases still support the | chain separator within any group
- Blank lines within a group are ignored
- A phrase above the first tag header belongs to an implicit "untagged"
  pool, active when phrases: null
- Tag names are arbitrary — the session creator defines them, and
  the timeline references them by the same name
- The UI affirmation editor will display groups visually and allow
  adding/removing/reordering within each group


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5. INTERPOLATABLE vs INSTANT-ONLY PARAMETERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INTERPOLATABLE (smooth transition between keyframes):
  beat_frequency, carrier_frequency, volume
  veil_opacity, veil_scroll_speed_x, veil_scroll_speed_y
  spiral_opacity, spiral_tightness, spiral_chaos, spiral_count
  center_flash_on_time, center_flash_off_time
  shadow_opacity, slideshow_interval

INSTANT-ONLY (hard cut at keyframe timestamp):
  spiral_style, font_switch_mode
  start_fullscreen, beat_sync_master
  phrases (phrase group swap)

If an instant-only parameter appears in a keyframe with ease: ease_in_out
(or any non-instant easing), the easing is ignored for that parameter
and it cuts hard. No error is raised.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
6. RUNTIME BEHAVIOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The timeline runner is a background thread that:
1. Tracks elapsed session time
2. Finds the surrounding keyframe pair for the current time
3. Computes interpolated values for all numeric params
4. Writes computed values to live_control.json every 100ms
5. Respects loop boundaries — inside a loop, time wraps back to from_t
   after reaching to_t, decrementing the loop counter each pass

Live overrides: any value written to live_control.json by the user
(via the control panel) or LLM takes effect immediately. The timeline
runner will overwrite it again on the next 100ms tick UNLESS the
parameter has been flagged as "user locked" (future feature).

Session time is wall-clock seconds since the session started, paused
when the user hits Pause in the transport bar.

Scrubbing: the user or LLM can jump to any timestamp. The runner
recalculates from the new position immediately.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
7. PLAYLIST FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Playlists are plain text files at the root level or inside a session
folder. One session folder name per line. Blank lines and # comments
ignored.

EXAMPLE playlist.txt:
─────────────────────────────────────────────────────────
# Morning routine
relaxation_induction
alpha_conditioning
gentle_wake
─────────────────────────────────────────────────────────

Playback modes (set in UI, stored in live_control.json):
  sequential  — play each session in order, stop at end
  loop        — repeat the playlist indefinitely
  loop_one    — loop the current session indefinitely
  shuffle     — randomize order each pass

When a session ends (duration elapsed or timeline exhausted), the
playlist runner automatically loads the next session. The transition
is seamless — the next session's defaults are applied immediately,
no gap in audio or visuals.

The LLM can read and rewrite the active playlist via live_control.json:
  "playlist": ["session_a", "session_b", "session_c"]
  "playlist_mode": "loop"
  "playlist_index": 1


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
8. LLM INTEGRATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

All timeline state is readable from live_control.json:
  "session_name"      — currently loaded session
  "session_time"      — current playback position in seconds
  "session_duration"  — total session length (from session.yaml)
  "timeline_label"    — label of the current keyframe segment
  "loop_count"        — remaining loop iterations for active loop (if any)
  "phrases_active"    — currently active tag group name (or null)

The LLM can:
  - Scrub to a timestamp:  "session_time": 600
  - Force a phrase group:  "phrases_active": "conditioning"
  - Inject phrases:        "llm_generated_affirmations": ["you are...", ...]
  - Override any param:    same as always
  - Load a new session:    "session_name": "other_session"


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
9. APPROVAL CRITERIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- session.yaml fully describes a session with no external dependencies
- Timeline keyframes interpolate numeric params smoothly between t values
- Easing curves (linear, ease_in, ease_out, ease_in_out, instant) work
- Loops repeat a time segment N times before advancing
- affirmations.txt tag groups activate and deactivate on keyframe cue
- Untagged affirmations.txt files work exactly as before (no migration)
- Playlist advances automatically through sessions with no gap
- All timeline state is readable and writable via live_control.json
- Live user overrides take effect immediately, locking that parameter for the remainder of the session

This document is locked.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
9. USER KEYFRAME LOCKS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When a user moves a control panel slider while a session is running,
the timeline runner would normally overwrite their change on the next
100ms tick. Keyframe locks prevent this gracefully.

BEHAVIOR:
- Any parameter touched by the user during playback is immediately
  flagged as user-locked for that parameter only
- The timeline runner skips writing any user-locked parameter on
  every subsequent tick
- Locks are PERMANENT within a session — they do not expire at
  keyframe boundaries
- Locks are cleared only on: session restart, seek command, or
  loading a new session
- This matches user expectation: if you moved a slider, you own it
  for the rest of the session unless you explicitly reset

VISUAL INDICATOR:
- The slider label turns Gold (#f6c177, Rosé Pine) while locked
- Returns to Subtle (#908caa) only after restart / seek / session load
- No per-keyframe unlock mechanism exists or is needed

PRIORITY STACK (highest to lowest):
  1. User keyframe lock       (permanent within session)
  2. Timeline interpolation   (computed from surrounding keyframes)
  3. Session defaults         (from session.yaml defaults block)
  4. Application defaults     (hardcoded fallbacks in config.py)

IMPLEMENTATION NOTE:
  The timeline runner maintains a set of locked parameter names in
  live_control.json["timeline_locked_params"]. On each tick it skips
  any key present in that set. The set is cleared in full on restart,
  seek, and load — never on a per-keyframe basis.
