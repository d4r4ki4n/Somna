"""
semantic_selector.py — Neural-State Semantic Selection Engine (Bible Ch.6 §6.6)

Maps real-time EEG state onto six categorized content pools and pre-loads
the three-layer affirmation cascade (Shadows → CenterText → Voice) so that
when the DeliveryGate (Bible Ch.4 §4.6) fires, the right content is already behind it.

Three orthogonal EEG axes:
  Axis 1 — Motivational valence: FAA → approach / withdrawal / neutral
  Axis 2 — Trance depth: trance_score → shallow / moderate / deep
  Axis 3 — Processing mode: theta/alpha ratio → semantic SRP vs somatic SRP (tiebreaker)

Six content pools:
  WARMTH_COMFORT     (approach, shallow)
  IDENTITY           (approach, moderate)
  DISSOLUTION        (approach, deep)
  GROUNDING_TEXTURE  (withdrawal, shallow)
  SOMATIC_ANCHORING  (withdrawal, moderate)
  STILLNESS_EMPTINESS (withdrawal, deep)

Instantiated by somna_agent.py. Called each agent tick via tick(live_state).
Writes semantic_cascade to live_control.json for display layers to consume.

Scientific basis: Bao & Frewen (2022), Chien et al. (2023), Marcel (1983),
Delavari et al. (2025), Liu et al. (2025). See Bible Ch.6 §6.6 for full citations.
"""

import json
import random
import threading
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from ipc import patch_live

# ── Pool ID constants ──────────────────────────────────────────────────────────
WARMTH_COMFORT      = "warmth_comfort"
IDENTITY            = "identity"
DISSOLUTION         = "dissolution"
GROUNDING_TEXTURE   = "grounding_texture"
SOMATIC_ANCHORING   = "somatic_anchoring"
STILLNESS_EMPTINESS = "stillness_emptiness"

ALL_POOLS = [
    WARMTH_COMFORT, IDENTITY, DISSOLUTION,
    GROUNDING_TEXTURE, SOMATIC_ANCHORING, STILLNESS_EMPTINESS,
]

# ── Conductor phase eligibility (Bible Ch.6 §6.6 §7) ───────────────────────────────────
# None means selector disabled entirely for that phase.
PHASE_ELIGIBLE_POOLS: Dict[str, Optional[List[str]]] = {
    "CALIBRATION":       None,
    "INDUCTION":         [WARMTH_COMFORT, GROUNDING_TEXTURE],
    "DEEPENING":         [WARMTH_COMFORT, IDENTITY, GROUNDING_TEXTURE, SOMATIC_ANCHORING],
    "MAINTENANCE":       ALL_POOLS,
    "FRAC_EMERGE":       [WARMTH_COMFORT, GROUNDING_TEXTURE],
    "FRAC_EMERGE_HOLD":  [WARMTH_COMFORT, IDENTITY, GROUNDING_TEXTURE],
    "FRAC_REDROP":       [SOMATIC_ANCHORING, DISSOLUTION, STILLNESS_EMPTINESS],
    "SLEEP_APPROACH":    [STILLNESS_EMPTINESS, SOMATIC_ANCHORING],
    "SLEEP_ONSET":       None,
    "SESSION_END":       None,
}

# ── Selection thresholds ──────────────────────────────────────────────────────
FAA_DEAD_ZONE                = 0.05   # ±dead zone to avoid chatter
DEPTH_SHALLOW_CEIL           = 0.35
DEPTH_MODERATE_CEIL          = 0.65
THETA_ALPHA_SEMANTIC_THRESH  = 1.2    # above this → semantic SRP mode

# ── Timing ────────────────────────────────────────────────────────────────────
MIN_POOL_DWELL_S    = 15.0   # minimum seconds in a pool before switching
CASCADE_COOLDOWN_S  =  3.0   # minimum seconds between cascade payload updates
SHADOWS_HISTORY_LEN =  3     # deque length for Shadows word deduplication

# ── Default pool content (Bible Ch.6 §6.6 §3) ─────────────────────────────────────────
# Each pool: {"shadows": [single words], "center": [phrases]}
# Shadows sub-pool: direct associates ONLY — subliminal priming constraint
# (Chien et al. 2023 — unconscious priming only works for direct associates).
_DEFAULT_POOLS: Dict[str, Dict[str, List[str]]] = {
    WARMTH_COMFORT: {
        "shadows": ["warm", "soft", "gentle", "ease", "comfort", "held",
                    "safe", "rest", "calm", "tender", "cozy", "still", "hush"],
        "center":  ["warmth spreading through you", "soft and easy",
                    "letting the warmth find you", "comfortable just like this",
                    "the ease of being held", "nothing to do but feel this",
                    "wrapped in something gentle", "warm enough to let go"],
    },
    IDENTITY: {
        "shadows": ["yours", "self", "belong", "true", "real", "own",
                    "core", "kind", "enough", "name", "claim", "whole", "root"],
        "center":  ["you are soft, you are safe", "this is yours",
                    "belonging here completely", "you are exactly this",
                    "already enough", "nothing to prove, nothing to fix",
                    "the softness is who you are", "claimed by your own quiet"],
    },
    DISSOLUTION: {
        "shadows": ["dissolve", "drift", "gone", "melt", "fade", "blur",
                    "vanish", "nothing", "loose", "release", "float", "empty", "open"],
        "center":  ["dissolving into nothing at all", "no edges left to find",
                    "the boundary was never real", "less and less of anything",
                    "already gone before you noticed", "nothing to hold together",
                    "undone completely", "formless and free"],
    },
    GROUNDING_TEXTURE: {
        "shadows": ["weight", "press", "solid", "ground", "floor", "firm",
                    "hold", "stone", "bone", "root", "thick", "anchor", "dense"],
        "center":  ["the weight of your hands", "notice the pressure where you rest",
                    "solid and grounded", "the texture of this moment",
                    "feel where you meet the surface", "anchored by your own weight",
                    "gravity has you", "held by what's underneath"],
    },
    SOMATIC_ANCHORING: {
        "shadows": ["heavy", "sink", "deep", "pull", "drag", "down",
                    "thick", "dense", "slow", "lead", "pour", "crush", "drop"],
        "center":  ["heavier with every breath", "sinking into the weight",
                    "your body knows how to fall", "the heaviness is a gift",
                    "letting the weight carry you down", "dense and still and heavy",
                    "deeper by the weight of it", "gravity pulling you under"],
    },
    STILLNESS_EMPTINESS: {
        "shadows": ["still", "empty", "hollow", "void", "quiet", "hush",
                    "null", "blank", "flat", "dark", "numb", "zero", "end"],
        "center":  ["nothing to hold, nothing to carry",
                    "the stillness has a weight of its own",
                    "empty all the way through", "hollow and quiet and done",
                    "no one home", "just the hum of nothing",
                    "so still it could be forever",
                    "absence is the last thing left"],
    },
}

_ROOT      = Path(__file__).parent.parent
_LIVE_PATH = _ROOT / "live_control.json"


def _read_live() -> dict:
    try:
        return json.loads(_LIVE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_session_pools(session_name: Optional[str]) -> Dict[str, Dict[str, List[str]]]:
    """
    Load pool-tagged content from the session's affirmations.txt.

    Extended tag format (Bible Ch.6 §6.6 §5):
      # [warmth_comfort.shadows]
      warm
      soft
      # [warmth_comfort.center]
      warmth spreading through you
      soft and easy

    Falls back to empty additions if file has no pool tags.
    Returns a dict suitable for merging into _DEFAULT_POOLS.
    """
    candidates = []
    if session_name:
        candidates.append(_ROOT / "sessions" / session_name / "affirmations.txt")
    candidates.append(_ROOT / "affirmations.txt")

    pool_additions: Dict[str, Dict[str, List[str]]] = {}
    current_pool_id: Optional[str] = None
    current_sub: Optional[str] = None   # "shadows" or "center"

    for path in candidates:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                # Detect pool sub-tag: # [pool_id.shadows] or # [pool_id.center]
                if line.startswith("#"):
                    inner = line.lstrip("#").strip()
                    if inner.startswith("[") and inner.endswith("]"):
                        tag = inner[1:-1].strip()
                        if "." in tag:
                            pid, sub = tag.rsplit(".", 1)
                            if pid in ALL_POOLS and sub in ("shadows", "center"):
                                current_pool_id = pid
                                current_sub     = sub
                                pool_additions.setdefault(pid, {"shadows": [], "center": []})
                                continue
                    # Non-pool comment — reset context
                    current_pool_id = None
                    current_sub     = None
                    continue

                if current_pool_id and current_sub and line:
                    pool_additions[current_pool_id][current_sub].append(line)
        break  # use first file found

    return pool_additions


class SemanticSelector:
    """
    Neural-state semantic selection engine (Bible Ch.6 §6.6).

    Instantiated once in somna_agent.py. Called each agent tick via tick().
    Maintains pool selection, builds cascade payloads, and writes to
    live_control.json for display layers to consume.

    Pool selection has 15-second hysteresis to prevent chatter.
    Shadows sub-pool has 3-cycle deduplication (Shadows history deque).
    """

    def __init__(self, session_name: Optional[str] = None,
                 pool_weights: Optional[Dict[str, float]] = None,
                 habituation_engine=None):
        # Merge default pools with any session-tagged content
        self.pools: Dict[str, Dict[str, List[str]]] = {}
        additions = load_session_pools(session_name)
        for pid in ALL_POOLS:
            merged: Dict[str, List[str]] = {
                "shadows": list(_DEFAULT_POOLS[pid]["shadows"]),
                "center":  list(_DEFAULT_POOLS[pid]["center"]),
            }
            if pid in additions:
                merged["shadows"].extend(additions[pid]["shadows"])
                merged["center"].extend(additions[pid]["center"])
            self.pools[pid] = merged

        self.pool_weights: Dict[str, float] = {p: 1.0 for p in ALL_POOLS}
        if pool_weights:
            self.pool_weights.update(pool_weights)

        self.current_pool_id: Optional[str] = None
        self.pool_entered_at:  float         = 0.0
        self.last_cascade_at:  float         = 0.0
        self.shadows_history:  deque         = deque(maxlen=SHADOWS_HISTORY_LEN)
        self.cascade_count:    int           = 0
        self.pool_transition_log: List[Dict] = []

        # Staging buffer for DB write at session end
        self._cascade_log:    List[Dict] = []
        self._transition_log: List[Dict] = []

        # Optional habituation engine — gates novelty-depleted phrases
        self._habituation = habituation_engine

    # ── Pool selection ─────────────────────────────────────────────────────────

    def select_pool(self, faa: float, trance_score: float,
                    theta: float, alpha: float,
                    conductor_phase: str = "MAINTENANCE") -> Optional[str]:
        """
        Map EEG state onto a pool ID, constrained by Conductor phase eligibility.
        Returns None if the selector should be disabled for this phase.
        """
        eligible = PHASE_ELIGIBLE_POOLS.get(conductor_phase, ALL_POOLS)
        if eligible is None:
            return None

        # Axis 1: FAA → valence
        if faa > FAA_DEAD_ZONE:
            valence = "approach"
        elif faa < -FAA_DEAD_ZONE:
            valence = "withdrawal"
        else:
            valence = "neutral"

        # Axis 2: trance_score → depth band
        if trance_score < DEPTH_SHALLOW_CEIL:
            depth = "shallow"
        elif trance_score < DEPTH_MODERATE_CEIL:
            depth = "moderate"
        else:
            depth = "deep"

        # Axis 3: theta/alpha ratio → processing mode (tiebreaker for neutral FAA)
        ta_ratio      = theta / max(alpha, 0.001)
        semantic_mode = ta_ratio > THETA_ALPHA_SEMANTIC_THRESH

        _POOL_MAP = {
            ("approach",    "shallow"):  WARMTH_COMFORT,
            ("approach",    "moderate"): IDENTITY,
            ("approach",    "deep"):     DISSOLUTION,
            ("withdrawal",  "shallow"):  GROUNDING_TEXTURE,
            ("withdrawal",  "moderate"): SOMATIC_ANCHORING,
            ("withdrawal",  "deep"):     STILLNESS_EMPTINESS,
        }

        if valence == "neutral":
            if depth == "shallow":
                target = WARMTH_COMFORT
            elif depth == "moderate":
                target = IDENTITY if semantic_mode else SOMATIC_ANCHORING
            else:
                target = DISSOLUTION if semantic_mode else STILLNESS_EMPTINESS
        else:
            target = _POOL_MAP[(valence, depth)]

        # Conductor phase gate: if target isn't eligible, pick closest in valence
        if target not in eligible:
            # prefer same valence, fall back to any eligible pool
            same_valence = [p for p in eligible
                            if (valence == "approach" and p in
                                [WARMTH_COMFORT, IDENTITY, DISSOLUTION])
                            or (valence == "withdrawal" and p in
                                [GROUNDING_TEXTURE, SOMATIC_ANCHORING, STILLNESS_EMPTINESS])]
            fallback = same_valence[0] if same_valence else (eligible[0] if eligible else None)
            if fallback is None:
                return None
            target = fallback

        return target

    # ── Main tick ──────────────────────────────────────────────────────────────

    def tick(self, live_state: dict) -> Optional[Dict]:
        """
        Called each agent tick. Returns a cascade payload dict or None.
        Also writes the payload to live_control.json.
        """
        # Master switch — disabled when EEG is absent
        if not live_state.get("semantic_selector_enabled", True):
            return None

        # Check for explicit agent override
        override_pool = live_state.get("semantic_pool_override")
        if override_pool and override_pool in ALL_POOLS:
            target_pool = override_pool
        else:
            faa    = float(live_state.get("eeg_faa", 0.0) or 0.0)
            trance = float(live_state.get("eeg_trance_score", 0.0) or 0.0)
            theta  = float(live_state.get("eeg_theta", 0.0) or 0.0)
            alpha  = float(live_state.get("eeg_alpha", 0.0) or 0.0)
            sqi    = live_state.get("eeg_confidence", "none")
            phase  = live_state.get("conductor_phase", "MAINTENANCE")

            if sqi in ("none", "NONE"):
                return None

            target_pool = self.select_pool(faa, trance, theta, alpha, phase)
            if target_pool is None:
                return None

        now = time.time()

        # Pool hysteresis — enforce minimum dwell time before switching
        if target_pool != self.current_pool_id:
            time_in_current = now - self.pool_entered_at if self.current_pool_id else 999.0
            if self.current_pool_id is not None and time_in_current < MIN_POOL_DWELL_S:
                target_pool = self.current_pool_id   # hold current pool
            else:
                old_pool = self.current_pool_id
                self.current_pool_id = target_pool
                self.pool_entered_at = now
                self.shadows_history.clear()
                # Bible Ch.10 §10.2 §4.2 — fire compound CS for the incoming pool
                dispatch_compound_cs(target_pool)
                entry = {
                    "ts":           now,
                    "from_pool":    old_pool,
                    "to_pool":      target_pool,
                    "faa":          round(float(live_state.get("eeg_faa", 0.0) or 0.0), 3),
                    "trance":       round(float(live_state.get("eeg_trance_score", 0.0) or 0.0), 3),
                    "theta_alpha":  round(
                        float(live_state.get("eeg_theta", 0.0) or 0.0) /
                        max(float(live_state.get("eeg_alpha", 0.001) or 0.001), 0.001), 3),
                }
                self.pool_transition_log.append(entry)
                self._transition_log.append(entry)
                print(f"[SemanticSelector] Pool: {old_pool} -> {target_pool}")

        if self.current_pool_id is None:
            return None

        # Cascade cooldown
        if (now - self.last_cascade_at) < CASCADE_COOLDOWN_S:
            # Still update live_control with current pool id
            patch_live({
                "semantic_pool_active":  self.current_pool_id,
                "semantic_pool_dwell_s": round(now - self.pool_entered_at, 1),
            })
            return None

        cascade = self._build_cascade(self.current_pool_id, live_state)
        if cascade:
            self.last_cascade_at = now
            self.cascade_count  += 1
            cascade["cascade_index"] = self.cascade_count
            cascade["conductor_phase"] = live_state.get("conductor_phase", "")
            cascade["faa"]        = float(live_state.get("eeg_faa", 0.0) or 0.0)
            cascade["trance_score"] = float(live_state.get("eeg_trance_score", 0.0) or 0.0)
            cascade["theta_alpha_ratio"] = round(
                float(live_state.get("eeg_theta", 0.0) or 0.0) /
                max(float(live_state.get("eeg_alpha", 0.001) or 0.001), 0.001), 3)
            cascade["sqi"] = live_state.get("eeg_confidence", "")
            self._cascade_log.append(cascade)
            patch_live({
                "semantic_cascade":      cascade,
                "semantic_pool_active":  self.current_pool_id,
                "semantic_pool_dwell_s": round(now - self.pool_entered_at, 1),
                "semantic_cascade_count": self.cascade_count,
            })
        return cascade

    # ── Cascade payload ────────────────────────────────────────────────────────

    def _build_cascade(self, pool_id: str, live_state: dict) -> Optional[Dict]:
        pool = self.pools.get(pool_id)
        if not pool:
            return None

        shadows_words  = pool.get("shadows", [])
        center_phrases = pool.get("center",  [])

        # Shadows word — deduplicate; additionally filter habituated words
        available = [w for w in shadows_words if w not in self.shadows_history]
        if not available:
            available = list(shadows_words)   # exhausted — reset
        if self._habituation is not None:
            fresh = [w for w in available if self._habituation.is_usable(w)]
            if fresh:
                available = fresh   # prefer novel words; fall back to all if empty
        shadow_word = random.choice(available) if available else ""
        if shadow_word:
            self.shadows_history.append(shadow_word)
            if self._habituation is not None:
                self._habituation.on_stimulus_presented(shadow_word, "word", "shadows")

        # Filter habituated center phrases
        c_pool = center_phrases
        if self._habituation is not None and c_pool:
            fresh = [p for p in c_pool if self._habituation.is_usable(p)]
            if fresh:
                c_pool = fresh

        center_phrase = random.choice(c_pool) if c_pool else None
        if center_phrase and self._habituation is not None:
            self._habituation.on_stimulus_presented(center_phrase, "word", "center_text")
        # Voice phrase: draw independently from center pool for variety
        voice_phrase = random.choice(c_pool) if c_pool else None

        # ── Bible Ch.10 §10.2 §4.1 — trace conditioning interval ────────────────────────
        # Compute the Shadows→CenterText gap based on conditioning history depth.
        # The caller is responsible for honoring this delay before displaying CenterText.
        trace_enabled = bool(live_state.get("trace_conditioning_enabled", True))
        if trace_enabled:
            base_s    = float(live_state.get("trace_interval_base_s", 1.5) or 1.5)
            var_frac  = float(live_state.get("trace_interval_variability", 0.3) or 0.3)
            rng       = live_state.get("trace_interval_range_s") or [0.8, 3.5]
            jitter    = base_s * var_frac
            interval  = base_s + random.uniform(-jitter, jitter)
            interval  = float(max(rng[0], min(rng[1], interval)))
        else:
            interval  = 0.0

        return {
            "pool_id":             pool_id,
            "shadow_word":         shadow_word,
            "center_phrase":       center_phrase,
            "voice_phrase":        voice_phrase,
            "ts":                  time.time(),
            "trace_interval_s":    interval,
        }

    # ── State / diagnostics ────────────────────────────────────────────────────

    def get_state_summary(self) -> Dict:
        """Return current selector state for agent context injection."""
        now = time.time()
        return {
            "active_pool":       self.current_pool_id,
            "pool_dwell_s":      round(now - self.pool_entered_at, 1) if self.current_pool_id else 0,
            "cascade_count":     self.cascade_count,
            "recent_transitions": self.pool_transition_log[-5:],
            "shadows_history":   list(self.shadows_history),
        }

    def flush_cascade_log(self) -> List[Dict]:
        """Return and clear the cascade log for DB write at session end."""
        log = list(self._cascade_log)
        self._cascade_log.clear()
        return log

    def flush_transition_log(self) -> List[Dict]:
        """Return and clear the pool transition log for DB write."""
        log = list(self._transition_log)
        self._transition_log.clear()
        return log


# ── Bible Ch.10 §10.2 §4.2 — Compound CS Registry ───────────────────────────────────────
# Per-pool multimodal compound CS parameters. When a pool fires, the caller can
# invoke dispatch_compound_cs() to apply matching visual/audio signatures.

COMPOUND_CS_REGISTRY: Dict[str, Dict] = {
    WARMTH_COMFORT: {
        "tonal_cue":        "pool_0_tone",
        "spiral_hue_shift": +15.0,
        "spiral_speed_mult": 0.85,
        "gain_profile":     "approach_shallow",
        "noise_tilt_offset": +0.05,
    },
    IDENTITY: {
        "tonal_cue":        "pool_1_tone",
        "spiral_hue_shift": +30.0,
        "spiral_speed_mult": 0.90,
        "gain_profile":     "approach_moderate",
        "noise_tilt_offset": +0.1,
    },
    DISSOLUTION: {
        "tonal_cue":        "pool_2_tone",
        "spiral_hue_shift": +45.0,
        "spiral_speed_mult": 0.70,
        "gain_profile":     "approach_deep",
        "noise_tilt_offset": +0.15,
    },
    GROUNDING_TEXTURE: {
        "tonal_cue":        "pool_3_tone",
        "spiral_hue_shift": -10.0,
        "spiral_speed_mult": 1.0,
        "gain_profile":     "withdrawal_shallow",
        "noise_tilt_offset": -0.05,
    },
    SOMATIC_ANCHORING: {
        "tonal_cue":        "pool_4_tone",
        "spiral_hue_shift": -20.0,
        "spiral_speed_mult": 1.05,
        "gain_profile":     "withdrawal_moderate",
        "noise_tilt_offset": -0.1,
    },
    STILLNESS_EMPTINESS: {
        "tonal_cue":        "pool_5_tone",
        "spiral_hue_shift": 0.0,
        "spiral_speed_mult": 0.60,
        "gain_profile":     "withdrawal_deep",
        "noise_tilt_offset": +0.2,
    },
}


def dispatch_compound_cs(pool_name: str) -> None:
    """Fire compound CS elements in temporal binding order (Bible Ch.10 §10.2 §4.2 & §5.1).

    Correct sequence per §5.1:
      t=0             — tonal cue (audio)        → cue_fire patch
      t=audio_lead_ms — visual shift              → spiral_hue_shift, spiral_speed_multiplier
      t=+30 ms more  — gain profile + noise tilt → gain_profile, noise_spectral_tilt

    Total spread ~80 ms; well within the 200 ms temporal binding window.
    Runs in a daemon thread so the calling agent tick is never blocked.
    """
    registry = COMPOUND_CS_REGISTRY.get(pool_name)
    if registry is None:
        return

    def _fire() -> None:
        try:
            live          = json.loads(_live.read_text(encoding="utf-8"))
            if not live.get("compound_cs_enabled", True):
                return
            audio_lead_ms = float(live.get("audio_lead_ms", 50) or 50)

            # Step 1: tonal cue immediately (audio leads)
            patch_live({"cue_fire": pool_name})

            # Step 2: visual shift after audio_lead_ms
            time.sleep(audio_lead_ms / 1000.0)
            patch_live({
                "spiral_hue_shift":       registry["spiral_hue_shift"],
                "spiral_speed_multiplier": registry["spiral_speed_mult"],
            })

            # Step 3: gain profile + noise tilt 30 ms after visual
            time.sleep(0.030)
            live2     = json.loads(_live.read_text(encoding="utf-8"))
            base_tilt = float(live2.get("noise_spectral_tilt", 1.0) or 1.0)
            patch_live({
                "noise_spectral_tilt": round(
                    max(0.8, min(1.5, base_tilt + registry["noise_tilt_offset"])), 3),
                "gain_profile": registry["gain_profile"],
            })
        except Exception:
            pass

    threading.Thread(target=_fire, daemon=True).start()
