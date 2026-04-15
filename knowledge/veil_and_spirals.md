# Veil Modes and Spiral Styles — Experiential Reference

## Veil Modes

The veil layer delivers affirmation phrases as floating text over the spiral background. Each mode controls how phrases enter, move through, and exit the visual field. Choosing the right mode for the session phase is as important as choosing the right phrase content.

---

### `scroll`

**Visual description**: Phrases move steadily across the screen in a single direction (typically horizontal). Clean, predictable, readable.

**Experiential quality**: Calm. The eye can track individual phrases easily. There is no surprise. Best suited for alpha-range phases where readability is the goal.

**When to use**:
- Orient phase (t=0 to ~15%)
- Return phase
- Anytime you want the user to *consciously read* the phrases

**Avoid during**: Deep work phases. The predictable motion is too easily tracked and read, which maintains analytical engagement.

**Parameter sensitivity**:
- `veil_density`: directly controls how many phrases are visible. 1.0 is a reasonable default; >2.0 becomes cluttered at readable opacity.
- `veil_opacity`: 20–50% is the readable range.

---

### `rain`

**Visual description**: Phrases fall vertically from top to bottom, like rainfall. Multiple phrases fall simultaneously at different horizontal positions.

**Experiential quality**: Immersive, slightly overwhelming if density is high. Triggers a "shower of input" sensation that can support the idea of being saturated with suggestions.

**When to use**:
- Mid-descent phase
- Focus 10 entry, where slight overload of the analytical mind supports entrainment

**Avoid during**: Soak phase. Too stimulating. Use drift instead.

**Parameter sensitivity**:
- High `veil_density` (2.0–3.0) with `rain` creates a phrase waterfall — powerful visual but requires low opacity (< 40%) to avoid becoming illegible noise.
- Low `veil_density` (0.5–1.0) makes individual phrases visible and readable.

---

### `drift`

**Visual description**: Phrases float independently across the screen in random directions, each at a slightly different speed. No predictable trajectory. Phrases enter from any edge and drift to the opposite side.

**Experiential quality**: Dreamlike, organic, disorienting in a pleasant way. The user cannot predict where the next phrase will appear. This unpredictability is mildly hypnotic — it keeps the peripheral visual cortex engaged without the analytical mind's ability to track.

**When to use**:
- Descent phase
- Focus 10 hold
- Work window (at low-medium opacity)

**Parameter sensitivity**:
- Speed variance between individual messages is the key quality of `drift`. Each phrase should have a slightly different velocity — this avoids the regular-grid feeling of rain.
- `veil_density` 1.0–2.0 is the sweet spot.
- `veil_opacity` 30–60%: enough to register, not enough to dominate.

**Design note**: Do not set all drift phrases to the same speed — that degenerates into a more predictable scroll effect. The value of drift is the randomness.

---

### `converge`

**Visual description**: Phrases start scattered across the screen and move toward a central point, shrinking as they approach the center until they disappear at the vanishing point. Multiple phrases simultaneously converge from different directions.

**Experiential quality**: Hypnotically compelling. Creates a strong "being drawn toward center" sensation that reinforces the depth metaphor. The shrinking size as phrases approach center gives a tunnel-vision quality.

**When to use**:
- Focus 10 hold
- Work window
- Any keyframe where the intent is to create inward focus and absorption

**Avoid during**:
- Orient phase — the intensity is too high for a user who is still at alpha.
- Soak phase — still too intense; use drift instead.

**Parameter sensitivity**:
- Initialization: phrases should NOT all appear simultaneously — stagger their start times to avoid a visual pulse wave at initialization.
- Density: 1.0–2.0. Above 2.0 the screen becomes an incomprehensible stream of incoming text.
- `veil_opacity` 30–55%. Higher than this and the converging phrases become visually dominating.
- `size_shrink`: phrases should visibly shrink as they approach center. This is the core visual hook of the mode.
- Center fade: phrases should fade to alpha=0 at the vanishing point, not hard-disappear.

**Common mistake**: Setting converge at high density and high opacity simultaneously — it creates a visual wall rather than a depth cue.

---

### `tunnel`

**Visual description**: Phrases appear in a ring around the center of the screen and move outward toward the edges, growing larger as they move. The opposite motion to converge.

**Experiential quality**: Expanding, opening. Suggests the user is moving outward into a larger space. Useful for ascent phases or for creating a sense of space expanding around the listener.

**When to use**:
- Return phase
- Transitions between descent phases where you want a visual "breath" between descents
- Focus 15 / expansion-themed sessions

**Parameter sensitivity**:
- Similar to converge, stagger initialization.
- Phrases growing rather than shrinking creates a different psychological valence — outward, expansive, rather than inward, focused.

---

### `strobe`

**Visual description**: Full-field or center-field phrase bursts at a set rate. High-intensity, attention-demanding.

**Experiential quality**: Commanding. Impossible to ignore. Analogous to a direct verbal command rather than a whisper.

**When to use**:
- Very sparingly. Mostly inappropriate for trance-deepening contexts.
- Can be used briefly at the transition between orient and descent to "stamp" a single key phrase before shifting to drift.

**Avoid during**: Deep phases. Strobe is physiologically arousing and will work against entrainment.

---

## Spiral Styles — Experiential Reference

The spiral layer is the primary visual background. While the visual_display.py code renders each style mathematically, the *experiential* quality is what matters for session design.

---

### `tunnel_dream`

**Visual**: A receding tunnel with soft, dream-like geometry. The walls curve inward. Strong depth cue.

**Experience**: Most directly hypnotic of all styles. The tunnel illusion creates a powerful depth metaphor — the user feels they are *moving into* the screen. Strong proprioceptive disruption.

**Best for**: Focus 10 entry and hold. The middle phases of the descent.

---

### `galaxy`

**Visual**: Spiral arms radiating from a bright center, with particle scattering. Resembles a galaxy or whirlpool.

**Experience**: Expansive but centered. Creates a "looking into vastness" sensation without losing the center anchor.

**Best for**: Descent phase. Works well with drift veil.

---

### `archimedean`

**Visual**: Classic Archimedean spiral — uniform-spacing, clean lines rotating from center.

**Experience**: Mathematical, clean. The most "neutral" spiral — not particularly arousing, not particularly immersive. Works as a background that doesn't demand attention.

**Best for**: Orient phase. Does not compete with phrases the user should be reading.

---

### `kaleidoscope`

**Visual**: Symmetric repeating patterns radiating from center with color variation. Fractal-adjacent.

**Experience**: Mandala quality. The symmetry is meditative. At moderate speed it creates an almost breathing quality.

**Best for**: Work window. Matches Level 4 phosphene patterns (radial mandalas).

---

### `interference`

**Visual**: Overlapping wave patterns creating moiré-like interference geometries.

**Experience**: Dynamic, organic. The pattern seems to shift and breathe even at constant speed. Creates a sense that the visual field is alive.

**Best for**: Work window, focus 10 hold. Strong at medium opacity.

---

### `electric`

**Visual**: Branching lightning-like tendrils from center. High contrast, high energy.

**Experience**: High-energy. Stimulating rather than calming. More appropriate for attention/alertness work than trance deepening.

**Best for**: Alert sessions. Or contrast effect — brief electric burst before dropping back to a calm style.

---

### `vortex`

**Visual**: Tight spiral vortex with strong center pull. Fast and intense at high speed multipliers; hypnotic and slow at low speeds.

**Experience**: At low speed (0.3–0.6): profoundly hypnotic. The vortex creates an extremely strong center-pull sensation. At high speed: arousing, even disorienting.

**Best for**: Focus 10 hold, work window. At low speed. One of the strongest trance-induction styles.

**Warning**: At speed > 1.0, vortex induces nausea or dizziness in some users. Use speed ≤ 0.8 for extended use.

---

### `dna`

**Visual**: Intertwined double helix rotating around a central axis.

**Experience**: Regular, rhythmic, almost biological. The rotation creates a predictable pulse that can sync with the binaural beat at the right speed multiplier.

**Best for**: Descent phase when combined with a descending beat frequency. The biological metaphor ("something changing inside you") can reinforce identity content.

---

### `fibonacci`

**Visual**: Fibonacci sequence spiral — the "golden ratio" spiral seen in shells and sunflowers.

**Experience**: Natural, mathematically satisfying. The eye follows the spiral inward automatically. One of the most naturally hypnotic geometries.

**Best for**: Orient or early descent. Beautiful and non-threatening. Users frequently report they "could stare at it."

---

### `rose`

**Visual**: Rhodonea curve ("rose curve") — petal-shaped loops radiating from center.

**Experience**: Organic, floral. At slow speed it feels like a flower opening and closing. Calming.

**Best for**: Orient phase, return phase. Softer than most other styles.

---

### `moire`

**Visual**: Overlapping concentric circle sets creating moiré patterns.

**Experience**: Strong mandala quality. Very regular. Can feel slightly geometric compared to the organic styles. The pattern seems to pulsate at slower speeds.

**Best for**: Work window, soak. The regularity supports the quiet, repetitive quality of these phases.

---

### `spirograph`

**Visual**: Hypotrochoid / epicycloid patterns — the "Spirograph toy" geometry.

**Experience**: Playful, intricate. More complex than simple spirals. Keeps the eye moving along the curve.

**Best for**: Descent phase. Provides visual complexity that occupies the analytical mind without being overwhelming.

---

### `fermat`

**Visual**: Fermat spiral — parabolic spiral where spacing between arms increases with radius.

**Experience**: Open, expanding. The wider spacing at the periphery creates a sense of the spiral breathing outward.

**Best for**: Orient phase. Non-threatening. Mathematically interesting without being intense.

---

### `superformula`

**Visual**: Johan Gielis' superformula — a generalized shape formula that can produce an enormous variety of forms depending on parameters. In Somna, these are typically petal/symmetry forms.

**Experience**: Depends on the active parameterization. Can range from organic and soft to geometric and complex.

**Best for**: Varied phases. Watch the chaos parameter — low chaos (0.0–0.1) produces clean, predictable forms; high chaos (0.3+) creates organic distortion.

---

## Speed Multiplier Reference

Across all spiral styles, speed has consistent experiential effects:

| Speed Range | Experiential Quality | Session Phase |
|-------------|----------------------|---------------|
| 0.1–0.3 | Near-static. Barely moving. Meditative. | Soak |
| 0.3–0.6 | Slow, hypnotic. Clear motion but not intrusive. | Work window, Focus 10 hold |
| 0.6–1.0 | Moderate. Engaging without demanding attention. | Descent |
| 1.0–1.5 | Active. Attention-demanding. Slightly arousing. | Orient, or brief transitions |
| 1.5–3.0 | Fast. Exciting. Potentially arousing or disorienting. | Not recommended for trance use |

**Rule**: speed should descend as the session descends, and rise as the session returns. This creates a coherent multi-sensory metaphor for depth.
