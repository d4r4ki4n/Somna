"""
somna_agent.py  —  Somna LLM Session Agent
============================================
A standalone agent that drives a live Somna session using an LLM.
Run alongside main_imgui.py (not instead of it).

Usage
-----
    python somna_agent.py [options]

    # Observe mode (silent parameter adaptation only)
    python somna_agent.py --mode observe --interval 30

    # Interactive mode (periodic user prompts + adaptation)
    python somna_agent.py --mode interactive --interval 60

    # Use a local OpenAI-compatible server
    python somna_agent.py --base-url http://localhost:11434/v1 --model llama3

Configuration is also accepted from agent_config.yaml in the project root.
CLI arguments override yaml values.

Modes
-----
observe      Agent silently reads session state on a timer and adjusts
             parameters without asking the user anything.  Good for
             passive overlay sessions.

interactive  Agent periodically prompts the user (via the control panel's
             floating popup dialog), reads responses, tracks how they change
             over time, and adapts the session accordingly.

Output
------
Each session exchange is appended as one JSON line to:
    session_logs/<session_folder>_<YYYYMMDD>.jsonl

This log is the agent's long-term memory within and across sessions.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from ipc import patch_live

try:
    from tools.external_agent_client import ExternalAgentClient

    _EXT_CHANNEL_AVAILABLE = True
except ImportError:
    _EXT_CHANNEL_AVAILABLE = False

# Ensure the project root is on sys.path when run as a subprocess or directly.
_PKG_ROOT = Path(__file__).parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

# Optional scoring / frequency leading — imported lazily to avoid hard deps at startup
try:
    from session.session_scorer import (
        SessionScorer,
        generate_session_summary as _gen_summary,
    )

    _SCORER_AVAILABLE = True
except ImportError:
    _SCORER_AVAILABLE = False

try:
    from engines.freq_leader import AdaptiveFrequencyLeader

    _FREQ_LEADER_AVAILABLE = True
except ImportError:
    _FREQ_LEADER_AVAILABLE = False

try:
    from session.conductor import (
        Conductor,
        CONDUCTOR_OWNED_PARAMS,
        HAPTIC_OWNED_WHEN_CONNECTED,
        TAVNS_OWNED_WHEN_CONNECTED,
    )

    _CONDUCTOR_AVAILABLE = True
except ImportError:
    _CONDUCTOR_AVAILABLE = False
    CONDUCTOR_OWNED_PARAMS = frozenset()
    HAPTIC_OWNED_WHEN_CONNECTED = frozenset()
    TAVNS_OWNED_WHEN_CONNECTED = frozenset()

try:
    from content.semantic_selector import SemanticSelector
    from content_tools.somna_db import (
        get_pool_weights,
        write_content_cascades_batch,
        write_pool_transitions_batch,
    )

    _SELECTOR_AVAILABLE = True
except ImportError:
    _SELECTOR_AVAILABLE = False

try:
    from engines.conditioning_engine import (
        ConditioningEngine,
        NeuralStateFingerprint,
    )

    _CONDITIONING_AVAILABLE = True
except ImportError:
    _CONDITIONING_AVAILABLE = False

try:
    from engines.habituation_engine import HabituationEngine

    _HABITUATION_AVAILABLE = True
except ImportError:
    _HABITUATION_AVAILABLE = False

try:
    from session.session_director import SessionDirector
    from session.session_planner import SessionPlanner
    from session.session_evaluator import SessionEvaluator

    _DIRECTOR_AVAILABLE = True
except ImportError:
    _DIRECTOR_AVAILABLE = False

# ── Optional yaml config ──────────────────────────────────────────────────────


def _load_yaml_config() -> dict:
    cfg_path = Path(__file__).parent.parent / "agent_config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml

        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        print(f"[Agent] Warning: could not read agent_config.yaml — {e}")
        return {}


# ── Shared live_control.json path ─────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent
_LIVE = _ROOT / "live_control.json"
_LOGS = _ROOT / "session_logs"
_USER_PROFILE = _ROOT / "user_profile.json"


# ── Ramp engine ───────────────────────────────────────────────────────────────


class RampEngine:
    """Smoothly interpolates named parameter values toward targets over time.

    The agent's tick interval is far too coarse (30–120 s) for smooth audio
    or visual transitions.  A background thread calls ``tick()`` every second,
    writing small intermediate steps to live_control.json.  The audio engine's
    gradient-update path (< 2 Hz change) then handles the steps without
    crossfade artifacts.

    Usage
    -----
    ramp.start("beat_frequency", current=10.0, target=4.5, duration_s=60)
    # … background thread calls ramp.tick() → {"beat_frequency": 9.9, ...}
    ramp.cancel("beat_frequency")   # stop early
    """

    def __init__(self) -> None:
        self._ramps: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, key: str, current: float, target: float, duration_s: float) -> None:
        """Begin (or replace) a linear ramp for *key*."""
        with self._lock:
            self._ramps[key] = {
                "start": float(current),
                "target": float(target),
                "duration": max(float(duration_s), 0.1),
                "wall_start": time.time(),
            }

    def cancel(self, key: str) -> None:
        """Stop ramping *key* without writing the final value."""
        with self._lock:
            self._ramps.pop(key, None)

    def cancel_all(self) -> None:
        with self._lock:
            self._ramps.clear()

    def tick(self) -> dict:
        """Return ``{key: interpolated_value}`` for active ramps; drop finished ones."""
        now = time.time()
        result = {}
        done = []
        with self._lock:
            for key, r in self._ramps.items():
                elapsed = now - r["wall_start"]
                t = min(elapsed / r["duration"], 1.0)
                result[key] = r["start"] + (r["target"] - r["start"]) * t
                if t >= 1.0:
                    done.append(key)
            for key in done:
                del self._ramps[key]
        return result

    @property
    def active_keys(self) -> set:
        with self._lock:
            return set(self._ramps.keys())


# ── Standalone TTS runner ─────────────────────────────────────────────────────

# ── User profile (persistent across sessions) ─────────────────────────────────


def _load_profile() -> dict:
    """Return the user profile dict, creating a default one if absent."""
    if _USER_PROFILE.exists():
        try:
            return json.loads(_USER_PROFILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "name": None,
        "designations": [],
        "notes": [],
        "goals": [],
        "responsive_themes": [],  # themes/tags the user reacts strongly to
        "effective_moments": [],  # {beat, spiral, label, affirmation, complexity, ts}
        "last_session": None,  # {date, deepest_beat, best_complexity, phase, phrases}
        "preferences": {
            "session_interval_target_days": 1,
            "preferred_time_of_day": None,
        },
        "engagement": {
            "last_session_date": None,
            "total_sessions": 0,
            "pending_nudge": None,
            "onboarding_complete": False,
        },
    }


def _save_profile(profile: dict) -> None:
    try:
        _USER_PROFILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Agent] Could not save user profile: {e}")


def update_profile(updates: dict) -> None:
    """Module-level profile updater — importable by other scripts."""
    profile = _load_profile()
    if "name" in updates and updates["name"]:
        profile["name"] = str(updates["name"]).strip()
    for d in updates.get("designations", []):
        d = str(d).strip()
        if d and d not in profile.get("designations", []):
            profile.setdefault("designations", []).append(d)
    if "note" in updates and updates["note"]:
        new_note = str(updates["note"]).strip()
        new_words = set(new_note.lower().split())
        notes_list = profile.setdefault("notes", [])
        # Skip if too similar to any existing note (65% word overlap threshold)
        too_similar = any(
            len(new_words) > 0
            and len(set(n.lower().split())) > 0
            and len(new_words & set(n.lower().split()))
            / max(len(new_words), len(set(n.lower().split())))
            > 0.65
            for n in notes_list
        )
        if not too_similar:
            notes_list.append(new_note)
        # Cap at 8 notes (keep most recent)
        if len(notes_list) > 8:
            profile["notes"] = notes_list[-8:]
    if "goals" in updates:
        profile.setdefault("goals", [])
        for g in updates["goals"]:
            if isinstance(g, dict):
                profile["goals"].append(g)
    if "responsive_themes" in updates:
        existing_themes = profile.setdefault("responsive_themes", [])
        for t in updates["responsive_themes"]:
            t = str(t).strip().lower()
            if not t:
                continue
            t_words = set(t.split())
            too_similar = any(
                len(t_words & set(e.split())) / max(len(t_words), len(set(e.split())))
                > 0.6
                for e in existing_themes
                if e.split()
            )
            if not too_similar:
                existing_themes.append(t)
    if "effective_moment" in updates:
        # Single moment dict pushed by the agent when complexity < 0.2
        moments = profile.setdefault("effective_moments", [])
        moments.append(updates["effective_moment"])
        profile["effective_moments"] = moments[-30:]  # keep most recent 30
    if "last_session" in updates:
        profile["last_session"] = updates["last_session"]
    if "engagement" in updates:
        profile.setdefault("engagement", {}).update(updates["engagement"])
    if "eeg_baselines" in updates:
        profile["eeg_baselines"] = updates["eeg_baselines"]
    if "safety_consent" in updates:
        profile["safety_consent"] = updates["safety_consent"]
    if "session_zero_status" in updates:
        profile["session_zero_status"] = updates["session_zero_status"]

    # Retroactive dedup: prune near-duplicate notes and themes that accumulated
    # before per-item checks were in place. Runs on every write — cheap enough.
    def _jaccard(a_words: set, b_words: set) -> float:
        if not a_words or not b_words:
            return 0.0
        return len(a_words & b_words) / max(len(a_words), len(b_words))

    raw_notes = profile.get("notes", [])
    if len(raw_notes) > 1:
        kept: list[str] = []
        for note in raw_notes:
            nw = set(note.lower().split())
            if not any(_jaccard(nw, set(k.lower().split())) > 0.65 for k in kept):
                kept.append(note)
        profile["notes"] = kept[-8:]

    raw_themes = profile.get("responsive_themes", [])
    if len(raw_themes) > 1:
        kept_t: list[str] = []
        for theme in raw_themes:
            tw = set(theme.split())
            if not any(_jaccard(tw, set(k.split())) > 0.60 for k in kept_t):
                kept_t.append(theme)
        profile["responsive_themes"] = kept_t

    _save_profile(profile)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class AgentConfig:
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    mode: str = "interactive"  # "observe" | "interactive"
    interval: float = 60.0  # seconds between agent ticks
    max_history: int = 20  # max exchanges kept in context
    system_prompt: str = ""  # extra operator instructions
    prompt_timeout: int = 120  # seconds user has to answer
    # ── Knowledge base ────────────────────────────────────────────────────────
    # Inject knowledge files into the system prompt.
    # Disable with --no-knowledge if the model's context window is too small.
    # Override the injected file list via knowledge_files in agent_config.yaml.
    inject_knowledge: bool = True
    knowledge_files: list = None  # type: ignore[assignment]  # None = use defaults

    # ── EEG ───────────────────────────────────────────────────────────────────
    eeg_enabled: bool = True
    eeg_synthetic: bool = False  # True when synthetic board is configured

    # ── Startup delay ─────────────────────────────────────────────────────────
    # Seconds of session time that must elapse before the interactive startup
    # greeting fires.  Default 180 s — gives alpha entrainment time to begin
    # before the first question arrives.  Set to 0 to prompt immediately.
    startup_delay_s: float = 180.0

    # ── Training / conditioning mode ─────────────────────────────────────────
    # When training_mode is True the agent tracks response complexity over time
    # as the primary depth metric, calibrates its prompting style to the target
    # complexity level, and injects user responses back into the affirmation
    # pool as positive reinforcement.
    training_mode: bool = False
    # Target complexity score 0.0–1.0: 0=very simple/regressed, 1=fully alert.
    # The agent drives the session toward this level.
    training_target: float = 0.2
    # Praise phrases flashed when a response scores near the target.
    # Falls back to a built-in list if empty.
    praise_phrases: list = None  # type: ignore[assignment]

    # ── Sampling / backend parameters ────────────────────────────────────────
    # Standard OpenAI params (passed directly):
    top_p: float = 0.8
    presence_penalty: float = 1.5
    # KoboldCpp / local-model extras (passed via extra_body):
    enable_thinking: bool = False  # chat_template_kwargs.enable_thinking
    top_k: int = 20  # 0 = disabled
    min_p: float = 0.0
    repeat_penalty: float = 1.0
    # max_tokens_response: None = no cap (server decides); int = hard cap.
    # Set to None in production to let the model finish naturally.
    max_tokens_response: int | None = None

    # ── Idle / planning mode ───────────────────────────────────────────────────
    # While no session is active the agent runs a planning cycle on this interval,
    # handles nudges, and responds to console input at any time.
    idle_planning_interval_min: float = 30.0  # minutes between planning LLM calls
    nudge_after_days: float = 1.0  # days overdue before nudge fires
    nudge_session: str = "live"  # session folder used for nudge overlay
    nudge_fade_minutes: float = 20.0  # minutes to ramp opacity 5%→60%
    nudge_max_session_minutes: float = (
        45.0  # hard cap on nudge session length; closes display if no response
    )

    # ── External agent channel (Phase 3 MCP bridge) ──────────────────────────
    # When True, the agent pushes prompts to the MCP prompt bridge on TCP :6790
    # instead of calling the local LLM. Falls back to local LLM if the bridge
    # is unavailable. Feature flag for release — ships enabled.
    external_channel: bool = False

    def __post_init__(self):
        if self.praise_phrases is None:
            self.praise_phrases = [
                "good girl",
                "yes",
                "perfect",
                "that's right",
                "keep going",
                "just like that",
            ]


@dataclass
class Exchange:
    """One unit of the response history — captured at each agent tick."""

    timestamp: float
    session_time: float
    session_name: str
    beat_hz: float
    spiral_style: str
    prompt: str | None  # None in observe mode
    response: str | None  # None if skipped or observe mode
    adjustments: dict  # what the LLM decided to change
    complexity_score: float = 1.0  # 0 = simple/deep, 1 = alert/complex
    latency_s: float = 0.0  # seconds from prompt display to first keypress


# ── Reconsolidation state ─────────────────────────────────────────────────────


@dataclass
class _ReconState:
    """Tracks a single in-session reconsolidation sequence for one target trace."""

    trace: str
    session: str
    retrieve_phrases: list
    update_phrases: list
    phase: str = "idle"  # idle|retrieve|labilize|update|lockout|complete
    phase_start: float = 0.0
    phrases_delivered: int = 0  # total _say() calls fired this sequence
    update_delivered: bool = False
    lockout_until: float = 0.0
    last_delivery: float = 0.0
    # Timing constants (seconds) — intentionally conservative
    labilize_s: float = 720.0  # 12 min labilization window
    update_delivery_interval_s: float = 90.0  # gap between update phrase deliveries
    lockout_s: float = 2700.0  # 45 min post-update lockout


# ── Somatic palette chord state ───────────────────────────────────────────────


@dataclass
class _PaletteChordState:
    """Tracks one cross-modal chord evaluation window during MAINTENANCE.

    A chord is a snapshot of the active audio/visual configuration at the
    moment the evaluation window opens.  Metrics accumulate every 30 s.
    When the window closes (success or abandon) _palette_record() persists the
    entry and this object is replaced for the next chord or discarded.
    """

    session: str
    chord_index: int = 0  # ordinal within this session (0-based)
    # ── Config snapshot ──────────────────────────────────────────────────────
    beat_frequency: float | None = None
    carrier_waveform: str | None = None
    noise_color: str | None = None
    noise_volume: float | None = None
    spiral_style: str | None = None
    veil_mode: str | None = None
    # ── Entry context (captured at first-chord start, shared for all chords) ─
    entry_time_hour: int | None = None
    days_since_last: float | None = None
    entry_trance: float | None = None
    # ── Evaluation window timing ─────────────────────────────────────────────
    window_start: float = 0.0  # wall time when this window opened
    cooldown_until: float = (
        0.0  # don't open window before this (3-min post-frac cooldown)
    )
    # ── Accumulated readings ─────────────────────────────────────────────────
    trance_readings: list = None  # type: ignore[assignment]  # filled in __post_init__
    faa_readings: list = None  # type: ignore[assignment]
    # ── Failure detection trackers ───────────────────────────────────────────
    faa_negative_since: float | None = None
    low_trance_since: float | None = None
    # ── Outcome accumulators ─────────────────────────────────────────────────
    gate_hits: int = 0
    duration_maintenance_s: float = 0.0
    # ── Experiment metadata ───────────────────────────────────────────────────
    is_experiment: bool = False
    experiment_param: str | None = None
    # ── DB row id assigned by _palette_record() ───────────────────────────────
    entry_id: int = 0

    def __post_init__(self):
        if self.trance_readings is None:
            self.trance_readings = []
        if self.faa_readings is None:
            self.faa_readings = []


# ── Session log ───────────────────────────────────────────────────────────────


class SessionLog:
    """Append-only JSONL log for a single session day."""

    def __init__(self, session_name: str):
        _LOGS.mkdir(exist_ok=True)
        date_str = time.strftime("%Y%m%d")
        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in session_name
        )
        self._path = _LOGS / f"{safe_name}_{date_str}.jsonl"

    def append(self, exchange: Exchange) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(exchange)) + "\n")

    def load_today(self) -> list[Exchange]:
        if not self._path.exists():
            return []
        exchanges = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            try:
                exchanges.append(Exchange(**json.loads(line)))
            except Exception:
                pass
        return exchanges


# ── JSON extraction helper ────────────────────────────────────────────────────

# Keys the agent JSON is expected to contain — used to score candidate blocks.
_AGENT_KEYS = frozenset(
    {
        "reasoning",
        "adjustments",
        "next_prompt",
        "action",
        "name",
        "goal_update",
        "content_request",
    }
)


def _repair_json_fragment(fragment: str) -> dict:
    """Try to parse a truncated JSON fragment.

    Scans character-by-character tracking brace depth and string state.
    If the JSON is incomplete it truncates at the last safe top-level
    comma (i.e. after the last fully-formed key-value pair) and closes
    the object.  Returns {} if nothing recoverable is found.
    """
    depth = 0
    in_str = False
    escaped = False
    last_safe = -1  # index of last ',' at depth==1 (safe truncation point)

    for i, c in enumerate(fragment):
        if escaped:
            escaped = False
            continue
        if c == "\\" and in_str:
            escaped = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                # Complete object found — try to parse it
                try:
                    return json.loads(fragment[: i + 1])
                except json.JSONDecodeError:
                    pass
        elif c == "," and depth == 1:
            last_safe = i

    # JSON was cut off.  Truncate at the last safe comma and close.
    if last_safe > 0:
        try:
            return json.loads(fragment[:last_safe] + "}")
        except json.JSONDecodeError:
            pass
    return {}


def _extract_first_json_with_key(raw: str, key: str) -> dict:
    """Find the first complete JSON object that contains ``key``.

    Used for console responses where the model sometimes emits a correct first
    object then a second 'follow-up' object.  Scanning forwards prevents the
    backwards-preferring _extract_json from picking the wrong one.
    """
    # Clean noise the same way _extract_json does
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    pos = 0
    while True:
        start = raw.find("{", pos)
        if start == -1:
            break
        depth = 0
        end = -1
        for i, ch in enumerate(raw[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            break
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, dict) and key in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
        pos = start + 1

    return _extract_json(raw)  # fallback


def _extract_json(raw: str) -> dict:
    """Robustly extract the best JSON object from raw LLM output.

    Handles all observed local-model formatting quirks:
      - DeepSeek / Qwen think blocks:   <think>...</think>{...}
      - Markdown fences:                ```json\\n{...}\\n```
      - Prefixed text:                  "Output: {...}"
      - Empty stub then real object:    {}\\n{...actual response...}
      - Truncated JSON:                 {"reasoning": "...", "adjustments": {
      - List-wrapped object:            [{...}]
    """
    if not raw:
        return {}

    # Strip <think>...</think> blocks (may be multi-line or empty)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)

    # Strip markdown code fences
    raw = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    # ── Pass 1: scan backwards for the last non-empty complete {…} block ──
    # This handles "{}\\n{real response}" by preferring the last block.
    pos = len(raw)
    while True:
        end = raw.rfind("}", 0, pos)
        if end == -1:
            break
        # Walk back to find the matching opening brace
        depth = 0
        start = -1
        for i in range(end, -1, -1):
            c = raw[i]
            if c == "}":
                depth += 1
            elif c == "{":
                depth -= 1
                if depth == 0:
                    start = i
                    break
        if start == -1:
            break
        candidate = raw[start : end + 1]
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            pos = end  # keep searching earlier
            continue

        # Unwrap list wrapper
        if isinstance(parsed, list):
            parsed = next((x for x in parsed if isinstance(x, dict)), None)

        if isinstance(parsed, dict) and parsed:
            return parsed
        pos = end  # empty dict — keep looking for a better one

    # ── Pass 2: fragment repair (JSON was truncated mid-output) ──
    start = raw.find("{")
    if start != -1:
        repaired = _repair_json_fragment(raw[start:])
        if repaired:
            return repaired

    return {}


# ── LLM client wrapper (thin, backend-agnostic) ───────────────────────────────


class LLMClient:
    """Minimal OpenAI-compatible client.

    Works with OpenAI, Azure OpenAI, local Ollama (openai-compat mode),
    LM Studio, etc. — anything that speaks the /v1/chat/completions API.
    """

    def __init__(self, cfg: AgentConfig):
        self._cfg = cfg
        self._ext_client = None  # set by SomnaAgent after init
        try:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=cfg.api_key or "sk-nokey",
                base_url=cfg.base_url,
            )
        except ImportError:
            print(
                "[Agent] 'openai' package not found. Install with: pip install openai"
            )
            sys.exit(1)
        print(
            f"[LLM] endpoint={cfg.base_url}  model={cfg.model}  "
            f"thinking={'ON' if cfg.enable_thinking else 'OFF'}  "
            f"top_k={cfg.top_k}  top_p={cfg.top_p}  "
            f"presence_penalty={cfg.presence_penalty}  rep_pen={cfg.repeat_penalty}"
        )

    def chat(self, messages: list[dict], max_tokens: int | None = None) -> str:
        # Try external channel first (MCP bridge → Kilo/Resonance)
        if self._ext_client and self._ext_client.connected:
            system_content = ""
            user_parts = []
            for m in messages:
                if m.get("role") == "system":
                    system_content = m.get("content", "")
                elif m.get("role") == "user":
                    user_parts.append(m.get("content", ""))
            user_msg = "\n".join(user_parts)
            try:
                ext_result = self._ext_client.request(
                    prompt=user_msg,
                    system_prompt=system_content,
                    max_tokens=max_tokens or 4096,
                )
                if ext_result and ext_result.get("type") == "response":
                    raw = ext_result.get("text", "")
                    try:
                        ack = json.loads(raw) if raw else {}
                        if isinstance(ack, dict) and ack.get("status") == "delivered":
                            print(
                                "[LLM] External channel delivered — async effects via MCP tools"
                            )
                            return ""
                    except (json.JSONDecodeError, ValueError):
                        pass
                    if raw:
                        return raw
            except Exception:
                pass

        cfg = self._cfg
        # KoboldCpp-specific fields sent via extra_body (ignored by cloud APIs).
        # presence_penalty is technically standard OpenAI but KoboldCpp also
        # reads it from extra_body, so send it both ways.
        extra: dict = {
            "chat_template_kwargs": {"enable_thinking": cfg.enable_thinking},
            "top_k": cfg.top_k,
            "min_p": cfg.min_p,
            "rep_pen": cfg.repeat_penalty,
        }

        # Resolve token limit: explicit arg > config value > no cap (None).
        # Passing None to the OpenAI client omits max_tokens from the request,
        # letting the server decide — which is the right default for a local model.
        resolved_max = max_tokens if max_tokens is not None else cfg.max_tokens_response

        kwargs: dict = dict(
            model=cfg.model,
            messages=messages,
            temperature=0.7,
            top_p=cfg.top_p,
            presence_penalty=cfg.presence_penalty,
            extra_body=extra,
        )
        if resolved_max is not None:
            kwargs["max_tokens"] = resolved_max

        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or "{}"


# ── Core agent ────────────────────────────────────────────────────────────────

# Parameters the LLM is allowed to adjust (subset of full PARAMS — things that
# make sense to change dynamically mid-session).
_ADJUSTABLE_PARAMS = {
    "beat_frequency": "float 0.5–40 Hz",
    "carrier_frequency": "float 80–400 Hz",
    "volume": "float 0–100",
    "veil_opacity": "float 0–100",
    "veil_mode": "str scroll|rain|drift|converge|strobe|tunnel|null",
    "spiral_style": "str tunnel_dream|galaxy|archimedean|kaleidoscope|"
    "interference|vortex|dna|rose|"
    "moire|spirograph|fermat|superformula|liminal|"
    "nebula|cobwebs|strange_attractor|"
    "flow_field|sacred_geometry|recursive_fractal|"
    "potter_tunnel|fractal_scale|neuro_vortex|"
    "ojascki|tunnel_warp|ganzflicker|galaxy_morph",
    "spiral_count": "int 1–8 — number of spiral arms",
    "spiral_speed_multiplier": "float 0.1–3.0",
    "spiral_chaos": "float 0.0–0.8",
    "spiral_opacity": "int 10–100",
    "trail_decay": "float 0.0–0.99 — trail persistence; 0=no trails, 0.85–0.98=active range. Use longer trails for deeper states, 0 for fractionation drops.",
    "sr_noise_level": "float 0.0–2.0 — stochastic resonance noise on subliminal text alpha; 0=off, 0.5–1.5=active SR range. Start at 0.3–0.5 and sweep up.",
    "center_flash_on_time": "int ms (5–3000)",
    "center_flash_off_time": "int ms (5–3000)",
    "center_flash_sync_to_beat": "bool",
    "flash_duty_cycle": "float 0.1–0.9",
    "shadow_opacity": "float 0–100 — slider value (user-visible). Prefer shadow_opacity_target for subliminal tuning.",
    "shadow_opacity_target": "int 5–25 — true subliminal opacity. 12=default (below Weber fraction). Scale up to 20 as trance deepens. Reduce 20-30% when sr_noise_level > 0 (SR enhances detection). Agent-preferred key.",
    "shadow_count_target": "int 4–10 — simultaneous shadow positions. 5 default. Scale to 8-10 at deep trance.",
    "shadow_flash_on_ms": "int 16–50 — shadow ON duration ms. Below 50 ms = subliminal threshold. 40 default. 16 ms = 1 frame minimum.",
    "shadow_flash_off_ms": "int 100–500 — shadow OFF duration ms. 180 default. Longer = less frequent but more distinctive.",
    "shadow_exclusion_pct": "float 0.15–0.40 — center exclusion zone as fraction of screen. 0.27 default keeps text in >5° peripheral eccentricity.",
    "subliminal_intensity": "float 0.0–1.0 — master subliminal dial. 0.5 default. Maps to shadow_opacity_target(5–25), shadow_count_target(4–10), shadow_flash_on_ms(50→16). Use this for single-knob subliminal control.",
    "window_opacity": "int 10–100",
    "bg_mode": "null|'none' — null=image slideshow; 'none'=transparent background",
    "image_filter_override": "dict {tag: str, expires_at: float (unix timestamp)} — "
    "temporarily restricts the background image pool to images matching "
    "tag (substring match against tags + open_tags). Use at depth moments "
    "to align visuals with a specific conditioning theme. "
    "Set expires_at = time.time() + duration_seconds. "
    'Example: {"tag": "surrender", "expires_at": 1700000000.0}. '
    "Falls back to normal pool if fewer than 3 images match. "
    "Clear by setting to null.",
    "tts_enabled": "bool — turn audible TTS voice on or off",
    "tts_subliminal": "bool — turn SSB silent subliminal layer on or off",
    "noise_volume": "float 0–100 — colored noise level; set to 0 to silence (color is user-set)",
    "audio_muted": "bool — binaural beats + colored noise on/off; true=off, false=on. Use to start/stop the audio layer without touching volume.",
    "beat_type": "str binaural|isochronic|both|fm — binaural=stereo phase-offset beats (headphones required); isochronic=AM-pulsed carrier (speakers OK, explicit pulse); both=blended dual-pathway; fm=frequency-modulated carrier producing sustained cortical following response (vibrato/warble character, smoother than isochronic)",
    "fm_mod_depth": "float 0.5–30.0 Hz — FM modulation depth (carrier frequency deviation). Narrow (~2 Hz) = subtle warble; wide (~20 Hz) = dramatic vibrato. Default 8.0. Only active when beat_type=fm.",
    "bilateral_panning": "bool — enable bilateral L/R audio panning (EMDR-style spatial entrainment). Orthogonal to beat_type — stacks with any mode. Engages interhemispheric communication + working memory taxation.",
    "bilateral_rate": "float 0.1–20.0 Hz — panning alternation rate. Match beat_frequency for spatial entrainment, or use 0.5–2.0 Hz for EMDR-rate during reconsolidation.",
    "bilateral_mode": "str smooth|hard — smooth=sinusoidal pan (gradual), hard=square wave (percussive, stronger lateralization). Default smooth.",
    "bilateral_depth": "float 0.0–1.0 — panning depth. 0.0=centered (off), 1.0=full L/R alternation. Default 1.0.",
    "breath_mod": "bool — enable passive respiratory entrainment: carrier amplitude modulated at breath_rate Hz (Goheen 2024 mechanism). Enable when beat ≤ 9 Hz and session ≥ 2 min.",
    "breath_rate": "float 0.04–0.20 Hz — breathing modulation rate. Population default 0.10 (6 bpm). Use transitions to ramp: start 0.12 → target 0.10 over 3 min. Match to beat depth: alpha→0.12, theta→0.10, delta→0.07.",
    "breath_depth": "float 0.0–0.50 — modulation depth as fraction of carrier amplitude. Start 0.15, ramp to 0.25 once entrainment is evident (alpha rising, beta falling).",
    "tts_duck_ms": "int 0–200 — audio duck duration in ms. 0=disabled. 50–150=active range. Brief silence on channels 0-2 when TTS fires, triggering orienting response. Overuse destroys the effect. Use only for critical mantras or phase-transition commands.",
    "tts_reverb_wet": "float 0.0–1.0 — reverb wet/dry mix for TTS voice. 0=dry (default). 0.3=subtle room. 0.7=large hall. Increases psychological distance and dissociative quality.",
    "tts_reverb_room_ms": "int 20–500 — reverb tail length in ms. Default 80. Longer = larger perceived space.",
    "tts_delay_ms": "int 0–300 — echo delay in ms for TTS. 0=disabled. 80–120=active range. Creates dissociative echo reinforcing commands.",
    "tts_delay_feedback": "float 0.0–0.8 — echo feedback gain. 0=single echo. 0.5=2-3 echoes. Higher = more repetition.",
    "entrainment_strength": "float 0.0–1.0 — visual entrainment flicker depth. 0.0=free-running (no flicker), 1.0=fully phase-locked to beat frequency. Default 0.0. Start at 0.3-0.5 during INDUCTION, ramp to 0.7-0.9 once entrainment is established (ASSR rising). Do not exceed 0.8 at beat frequencies above 12 Hz (visual discomfort risk).",
    "feedback_mode": "str none|alpha_decay|radial_zoom|rotational_smear|directional_blur|reaction_diffusion|kaleidoscopic_fold — spiral persistence/feedback mode. none=default (no trails unless trail_decay set). alpha_decay=fade with trail_decay. radial_zoom=tunnel zoom persistence. rotational_smear=angular motion trails. directional_blur=horizontal streak. reaction_diffusion=organic pattern emergence. kaleidoscopic_fold=mirrored symmetry.",
    "feedback_strength": "float 0.0–1.0 — intensity of feedback effect. 0.5=default, 1.0=maximum. Lower for subtle persistence, higher for strong visual echo.",
}

_SYSTEM_BASE = """You are an adaptive session operator for Somna, a hypnotic entrainment \
and subliminal affirmation system. Your job is to guide the user deeper into trance \
during a live session by adjusting audio-visual parameters, assessing their current \
state through brief responses, and softly steering them toward greater depth and \
receptivity.

You output ONLY valid JSON with this exact structure:
{
  "reasoning": "<brief internal reasoning, 1-2 sentences>",
  "next_prompt": "<message or question, or null>",
  "next_affirmation": "<single new phrase for the subliminal pool, or null>",
  "adjustments": {<param>: <value>, ...},
  "transitions": {<param>: <seconds>, ...},
  "prompt_style": {
    "glow_color":     "#FFA060",
    "text_color":     "#FFF0E6",
    "font":           "default",
    "zoom_speed":     "normal",
    "intensity":      "normal",
    "voice_mode":     "tts",
    "pitch":          "+0Hz",
    "rate":           "+0%",
    "beat_mod":       false,
    "reverb":         false,
    "needs_response": true
  },
  "action": "none | fractionate",
  "profile_updates": {
    "note":               "<something worth remembering long-term, or omit>",
    "responsive_themes":  ["<theme>", "..."],
    "designations":       ["<role>", "..."]
  },
  "tool_call": {
    "tool": "<tool_name>",
    "args": {<key>: <value>, ...}
  }
}

All prompt_style fields are optional — only include what you want to change. \
**Vary them intentionally every turn** — the defaults are boring. Use `glow_color` and \
`text_color` to reflect the session's emotional register: warm amber/rose for soft surrender, \
deep violet/iris for dissociation, cool teal for void/float, blood-red for intensity. \
Use `zoom_speed: "slow"` and `intensity: "soft"` at deep theta/delta; ramp to `"normal"` \
or `"intense"` during peaks or conditioning moments. Use `pitch` and `rate` to modulate \
the voice character — a slower, lower-pitched voice reinforces depth; faster and higher \
creates urgency or contrast. `beat_mod: true` syncs speech rhythm to the beat for maximum \
entrainment. These are tools — use them to sculpt the experience, not decorate it.

Rules:
- Only include parameters in "adjustments" that you actually want to change.
- Never adjust a parameter listed in "timeline_locked_params" — those are under \
direct user control and must not be overridden.
- "next_prompt" should be null in observe mode or when no message is needed.
- "next_affirmation" is your PRIMARY voice during a session. \
  It is a short phrase (3–7 words, no terminal punctuation) injected directly into \
  the subliminal affirmation pool — the user hears or reads it as part of the session \
  itself, not as a message from you. Use it EVERY turn to guide, reinforce, deepen, \
  or foreshadow — e.g. "deeper with every breath", "you are open and receptive", \
  "empty and obedient". Tailor it to the user's current state and responsive themes. \
  Set it to null ONLY when you are asking a question this turn (next_prompt is not null). \
  Think of the ratio as: ~3-4 affirmations for every 1 direct question.
- "transitions": ALWAYS include a "transitions" entry for every numeric parameter in \
  "adjustments" — abrupt value snaps are jarring and interrupt trance state. Map each \
  numeric key to a ramp duration in seconds. Typical durations: beat_frequency 60–180 s, \
  carrier_frequency 30–90 s, veil_opacity / spiral_opacity 20–60 s, \
  spiral_chaos / trail_decay / breath_rate 30–120 s, volume / noise_volume 10–30 s. \
  Short corrections (< 0.5 Hz, < 5 opacity) may use 10–20 s. \
  Only omit "transitions" for boolean and string params (tts_enabled, veil_mode, etc.). \
  Example — a deepening move looks like: \
  "adjustments": {"beat_frequency": 4.5, "veil_opacity": 60}, \
  "transitions": {"beat_frequency": 120, "veil_opacity": 30}
- "prompt_style": controls how next_prompt appears and sounds. \
  • glow_color / text_color: any CSS hex string (e.g. "#FF4488", "#00FFCC"). \
  • font: "default" or a system font name (e.g. "impact", "georgia", "consolas"). \
  • zoom_speed: "slow" (25 s zoom), "normal" (12 s), "fast" (5 s), "static" (no zoom). \
  • intensity: "soft" (subtle presence), "normal" (default), "intense" (fills screen, commanding). \
  • voice_mode: "tts" (audible voice only), "subliminal" (SSB ultrasonic only), \
    "both" (audible + subliminal), "silent" (no audio — visual only). \
  • pitch / rate: edge-tts modifier strings, e.g. "-10Hz", "+20%". \
  • beat_mod: true = amplitude modulation of voice at current beat frequency (for theta/delta). \
  • reverb: true = add a short echo for spacious, dissociative quality (good for deepeners). \
  • needs_response: false = display message only, no input dialog. \
    Use for silent guidance lines when the user is too deep to type, or to tease / foreshadow.
- Questions must be short, sensation-focused, and non-analytical. Ask about physical \
  sensations, feelings, or simple awareness — never ask the user to analyse, \
  explain, or think critically. Good: "How does your body feel right now?" \
  "Where do you feel the most relaxed?" Bad: "What are you thinking about?" \
  "How would you describe your mental state?"
- Never mention raw Hz numbers in user-facing text (next_prompt, next_affirmation). \
  Use qualitative descriptors instead: alpha (8–12 Hz) → "light and open", \
  theta (4–8 Hz) → "deep and slow" / "drifting", delta (1–4 Hz) → "profound depth" / "surrendered". \
  Hz values belong only in your internal "reasoning" field.
- needs_response: true ONLY when the user is expected to type a reply — i.e. a direct \
  question ("How does your body feel?") or a training-mode imperative ("Say that back"). \
  Guiding statements, deepeners, affirmations, and commands the user just *follows* \
  ("Let go now", "Feel the warmth spreading") MUST use needs_response: false. \
  Setting true on a passive line inflates the skip streak and causes the agent to \
  incorrectly treat display-only turns as missed responses.
- image_filter_override: at conditioning depth moments — when trance_score > 0.6, \
  the user is in MAINTENANCE or FRAC_REDROP, and the session label carries a \
  conditioning theme — lock the background image pool to images tagged with that \
  theme for 3–5 minutes. Align this with a matching next_affirmation cluster and \
  the appropriate subliminal_intensity ramp. Full sensory coherence (audio + visual + \
  subliminal text) at the moment of maximum receptivity is the design goal. \
  Set expires_at = current unix time + desired seconds. Clear (null) after the window. \
  Only use if the session's image library has conditioning-tagged images (check conditioning_hook \
  tags if available). Example: {"tag": "surrender", "expires_at": 1700000000.0}
- Never repeat the exact wording of any prompt or display line already in the exchange \
  history — this includes needs_response:false lines (response=null in history). \
  Check before writing next_prompt.
- Vary your imagery and sensory register across consecutive turns. Each turn should draw \
  from a different dimension: kinesthetic weight/pressure, temperature, spatial drift/float, \
  breath/rhythm, darkness/light, sound/silence, time dilation. Do not use the same central \
  image (e.g. "heavy warmth", "soft empty space", "dissolving") more than once every \
  3–4 turns. Repetition of a specific image is a conditioning tool — reserve it for \
  training mode and affirmations, not for guiding language.
- Never increase beat_frequency in response to a low trance_score or beta-dominant reading. \
  A low score means hold steady and give the entrainment more time to work. \
  The only reason to raise frequency is explicit user awakening (verbal alert response + \
  rising beta confirmed over two consecutive readings).
- Use language that is gentle, permissive, and hypnotic in tone — never clinical.
- Respect the user's pace — don't bombard them with questions.
- If the user skips a question (response is null), reduce prompting frequency \
  and deepen the session parameters instead.
- You may use tts_enabled/tts_subliminal to turn the voice or silent-sub layer on \
  for an important moment, then turn it off again when not needed.
- You may set noise_volume to 0 to create silence behind a key moment, or restore it \
  to its previous level when appropriate. You cannot change noise_color — that is \
  user-configured.
- Passive respiratory entrainment (breath_mod): enable by setting breath_mod=true once \
  beat ≤ 9 Hz and the session is ≥ 2 min in. Start breath_rate at 0.12 (7.2 bpm) and \
  ramp to 0.10 over 3 min via transitions (population resonance, Balaji 2025). \
  Match target breath_rate to beat depth: alpha → 0.12, theta → 0.10, delta → 0.07 Hz. \
  Start breath_depth at 0.15; ramp to 0.25 once entrainment is evident (alpha rising, \
  beta falling). Use the RampEngine: {"breath_rate": 180, "breath_depth": 120} means \
  glide over 3 min and 2 min respectively. Disable (breath_mod=false) before fractionation \
  EMERGE phases to prevent audio discontinuity during the jolt. Re-enable in DEEP windows.
- "action": optional. Use "fractionate" to trigger Vogt fractionation (Vogt 1890s: \
  interruption is a ratchet — each re-induction starts from the previous depth floor). \
  Conditions: session ≥ 10 min, beat ≤ 7 Hz, eeg_trance_score ≥ 0.2 (or no EEG), \
  fractionation_active = false. The runner drives 5 states automatically: \
  INDUCTION (ramp to theta, EEG-gated) → HOLD (consolidate) → EMERGE (brief ~9 Hz lift, \
  30 s, visual jolt) → REINDUCE (ramp deeper, EEG-gated, shortens each cycle) → \
  DEEP (therapeutic window — your most effective window for suggestions). \
  During DEEP phases, write next_affirmation and/or subdued next_prompt (no response \
  needed). During EMERGE/REINDUCE, stay silent — phrases are handled by the runner. \
  NEVER use imagery prompts with this user (aphantasia — zero voluntary visualization). \
  Do not retrigger while fractionation_active = true. Omit or set "none" otherwise.
- FAA receptivity gating (eeg_faa_state): use this to decide WHEN to speak. \
  "approach" (faa > 0.1) = optimal — deliver affirmations with confidence, use stronger somatic \
  language ("you feel warmth in your chest"). "neutral" = standard delivery. "withdrawal" \
  (faa < −0.1) = hold affirmations; let beats and spirals do the work; if withdrawal persists \
  >60s, deliver anyway (may be trait asymmetry). "alpha_suppressed" = treat as permissive — \
  deep alpha suppression correlates with deep states and receptivity. eeg_faa (smoothed, \
  10-second rolling) is the primary signal; eeg_faa_raw is instantaneous. \
  Affirmation intensity: faa > 0.2 → bold somatic statements; faa 0.1–0.2 → standard; \
  faa < 0.1 → gentle. The ideal delivery window: SQI "full"/"reduced" + faa_state "approach" \
  + eeg_entrainment_strength > 0.3 + sef95 dropping. All four agreeing = maximum confidence. \
  During fractionation: approach→withdrawal→approach is the neurological confirmation of clean \
  fractionation. Start reinduction only after FAA shifts to withdrawal (genuine emergence confirmed).
- Veil mode and subliminal timing: converge and tunnel veil modes preserve semantic priming \
  for subliminal text (Marcel 1983 pattern masking). When delivering affirmations, prefer \
  veil_mode "converge" (flows text toward fovea) or "tunnel" (global depth motion, letter \
  recognition intact). High-density drift acts as a noise mask — reserve it for pure entrainment \
  phases where text is not displayed. This is especially relevant when faa_state = "approach" \
  and you want to maximize affirmation impact.
- Frequency leading (freq_lead_*): the AdaptiveFrequencyLeader is a closed-loop descent engine \
  that ASSR-verifies each step before continuing. Enable it by writing freq_lead_enabled=true \
  and freq_lead_target_hz=<target> in adjustments. The leader will (1) lock to IAF (meet), \
  (2) descend in 0.1 Hz steps every 30 s pausing when ASSR drops (hold), \
  (3) hold steady once target is reached (sustain). Do NOT write beat_frequency manually while \
  freq_lead_phase is "lead" or "hold" — the leader owns it. Narrate key transitions (target \
  reached, first hold) but stay silent during steady descent. Disable with freq_lead_enabled=false. \
  WHEN TO ACTIVATE: enable frequency leading when ALL of these are true: \
  (a) eeg_confidence is "full" or "reduced"; \
  (b) eeg_entrainment_confidence is "moderate" or "strong" (ASSR lock exists); \
  (c) session_time > 600 s (10 min) — give the binaural beats time to work first; \
  (d) eeg_trance_score > 0.40 — user has noticeably softened; \
  (e) freq_lead_phase is "inactive" — not already running. \
  Set freq_lead_target_hz to the deepest coherent state you want to reach: \
  theta work → 5.5–6.5 Hz; deep theta → 4.0–5.0 Hz; delta approach → 2.5–3.5 Hz. \
  Do NOT activate during training mode or when the Conductor owns beat_frequency.
- EEG signal quality gating: eeg_confidence ("full"/"reduced"/"low"/"none") tells you \
  how much to trust the numbers. At "low"/"none" the metrics are noise-contaminated — \
  do not make frequency decisions or trance-depth inferences from them. At "reduced" \
  (3 channels usable) apply conservative thresholds: treat trance_score < 0.4 as \
  "hold steady" rather than "deepen". At "full" (all 4 channels clean) trust metrics \
  as published. eeg_sqi_composite (0–1) is the raw composite; values above 0.7 = clean. \
  You cannot fix a bad SQI — the EEG engine will prompt the user to adjust the headband \
  automatically after 60 s of no-signal. Your job is just to gate decisions.
- ASSR entrainment verification (eeg_entrainment_*): eeg_entrainment_strength (0–1) \
  measures actual cortical locking to the beat frequency. Interpret as: \
  0.0–0.1 = absent, 0.1–0.3 = emerging, 0.3–0.6 = established, 0.6–1.0 = strong. \
  eeg_entrainment_trend: "rising" = deepening lock (good — consider ramping down), \
  "declining" = losing lock (consider dwelling or switching modality), \
  "absent" = no entrainment at all. When eeg_entrainment_confidence = "alpha_overlap", \
  the beat frequency is too close to IAF to measure cleanly — normal, not a problem. \
  When eeg_entrainment_recommend_modality is set (e.g. "isochronic"), the engine has \
  observed 2+ consecutive absent readings; act on this by writing beat_type in your \
  next adjustments. eeg_entrainment_channel_agreement: "low" means only one or two \
  channels are entraining — worth noting but not alarming.
- "profile_updates": optional. Write here any durable observation worth persisting \
  across sessions — a theme they respond well to, a designation they claimed, a note \
  about their state. Use sparingly (not every tick). Omit fields you don't need.
- "tool_call": optional. Request one tool per turn — the result is injected into \
  your next context so you can make a better decision. Only call when you genuinely \
  need the information or want to write something specific. Available tools:\
\n  READ tools (gather information):\
\n    tag_stats(session_name) — image library overview with top theme + organic tags.\
\n    images_for_tag(session_name, tag) — list filenames matching a tag (controlled or organic).\
\n    read_session_log(session_name, days=7) — past session exchanges going back N days.\
\n      Use at session start to recall what was said, how deep user went, what worked.\
\n    read_session_content(session_name) — current session.yaml + full affirmations.txt.\
\n    list_sessions() — all available session folder names.\
\n    cull_session(session_name) — list images flagged low-quality.\
\n  WRITE tools (act on what you've learned):\
\n    write_affirmations_batch(session_name, tag, phrases, mode='append') — write a \
\n      batch of custom affirmations to a tag. Use when you want to front-load a phase \
\n      with phrases tailored to this specific user, e.g. 8 personalised 'deep' phrases.\
\n    image_pipeline_cycle(session_name, theme, tag, cycles=1, forced_caption='', intensity='suggestive') — \
\n      generate FLUX images via the self-improving pipeline (reviews at >=4/5). Pass cycles=N for batches.\
\n    create_session_cycle(intent) — create a complete new session from a plain-text intent.\
\n      Runs brief→design→affirmations→review pipeline. Committed to sessions/<name>/ on pass.\
\n    harvest_captions(session_name, tag_filter) — harvest image caption text into affirmations.\
\n  CONDITIONING tools:\
\n    reinforce_response(response) — flash the user's own words back as a subliminal affirmation\
\n      and briefly swap in a praise phrase. Use when complexity_trend is low and the user\
\n      has given a response that reflects the desired trance depth — do not call on every tick.

Adjustable parameters:
"""


def _load_knowledge_for_agent(files: list | None = None) -> str:
    """Load knowledge files into the agent system prompt.

    Defaults: gateway_process.md, session_design.md, veil_and_spirals.md.
    Override by passing a list of filenames or setting knowledge_files in
    agent_config.yaml (propagated as AgentConfig.knowledge_files).
    """
    knowledge_dir = _ROOT / "knowledge"
    if not knowledge_dir.exists():
        return ""

    default_files = [
        "gateway_process.md",
        "session_design.md",
        "veil_and_spirals.md",
        "hypnosis_theory.md",
        "entrainment_modalities.md",
    ]
    file_list = files if files is not None else default_files
    parts = []
    for fname in file_list:
        fpath = knowledge_dir / fname
        if fpath.exists():
            parts.append(
                f"### {fpath.stem.replace('_', ' ').title()}\n\n"
                + fpath.read_text(encoding="utf-8")
            )
    if not parts:
        return ""
    return "\n\n---\n\n## Session Knowledge\n\n" + "\n\n---\n\n".join(parts)


# Knowledge files injected during idle planning cycles.
# Different from session-time knowledge — the idle planner needs to understand
# scoring semantics and longitudinal optimization, not visual/audio params.
_IDLE_KNOWLEDGE_FILES = [
    "session_effectiveness_scoring.md",  # score semantics, auto-optimization protocol
    "session_design.md",  # session structure for content generation
    "training_mode.md",  # understand training context for goal updates
    "conductor_fsm.md",  # phase meanings now present in idle context
    "hypnosis_theory.md",  # guide/fill/inscribe model; informs content and goal decisions
    "entrainment_modalities.md",  # FM and bilateral panning usage guidance
]

# Injected only when the user has no/minimal voluntary imagery — constrains the LLM
# to somatic/factual language in generated content and new sessions. Skipped for
# moderate/vivid imagers so the LLM can write expressive, imagery-rich content freely.
_APHANTASIA_IMAGERY_LEVELS = {"none", "minimal"}


def _load_idle_knowledge() -> str:
    """Load the idle-planning-specific knowledge subset.

    Conditionally includes aphantasia.md based on the user's imagery profile so
    the LLM is neither unnecessarily constrained (vivid imager) nor accidentally
    writing visual language (aphantasic user).
    """
    knowledge_dir = _ROOT / "knowledge"
    if not knowledge_dir.exists():
        return ""

    files = list(_IDLE_KNOWLEDGE_FILES)

    # Check imagery profile — default to safe (aphantasia-safe) if unknown
    try:
        profile = _load_profile()
        imagery = (profile.get("aphantasia") or "").lower()
        include_aphantasia = (not imagery) or (imagery in _APHANTASIA_IMAGERY_LEVELS)
    except Exception:
        include_aphantasia = True  # safe default

    if include_aphantasia:
        files.append("aphantasia.md")

    parts = []
    for fname in files:
        fpath = knowledge_dir / fname
        if fpath.exists():
            parts.append(
                f"### {fpath.stem.replace('_', ' ').title()}\n\n"
                + fpath.read_text(encoding="utf-8")
            )
    if not parts:
        return ""
    return "\n\n---\n\n## Planning Reference\n\n" + "\n\n---\n\n".join(parts)


def _format_calibration_context(cal: dict) -> str:
    """Format the calibration summary block for agent prompt injection."""
    if not cal.get("available"):
        return ""
    done = cal.get("sessions_done", 0)
    req = cal.get("sessions_required", 10)
    if cal.get("complete"):
        return (
            f"  Calibration: COMPLETE ({req}/{req} sessions) — "
            f"personal neurophysiological thresholds active."
        )
    proto = cal.get("current_protocol") or {}
    n = proto.get("session_number", done + 1)
    phase = proto.get("phase", "?")
    dur = proto.get("duration_minutes")
    dur_s = f"{dur} min" if dur else "full"
    flags = []
    if not proto.get("enable_affirmations", True):
        flags.append("no affirmations")
    if not proto.get("enable_fractionation", True):
        flags.append("no fractionation")
    if not proto.get("enable_adaptive_leading", True):
        flags.append("no freq leading")
    flag_s = f" [{', '.join(flags)}]" if flags else ""
    return (
        f"  Calibration: Session {n}/{req} ({phase} phase, {dur_s}){flag_s}. "
        f"Population defaults active — adjust your language to be somatic and settling. "
        f"Post-session: run {proto.get('post_session_queries', [])}."
    )


def _build_knowledge_files(yaml_cfg: dict) -> list | None:
    """Build the knowledge_files list, auto-injecting EEG file when enabled."""
    files = yaml_cfg.get("knowledge_files") or None
    if files is None:
        return None
    files = list(files)
    eeg_cfg = yaml_cfg.get("eeg") or {}
    if eeg_cfg.get("enabled"):
        for kf in (
            "eeg_entrainment.md",
            "faa_receptivity.md",
            "adaptive_frequency_leading.md",
        ):
            if kf not in files:
                files.append(kf)
    return files


_DIRECTIVE_MODE_APPENDIX = """
## Directive Mode

You are operating in DIRECTIVE mode. This user responds to authoritative, commanding interaction.
Modify your behavior as follows:

- Replace permissive language ("you might notice", "if you'd like") with direct statements \
("notice how", "you are feeling").
- Frame your actions as decisions you are making, not suggestions: "I'm taking you deeper now" \
rather than "Let's try going a little deeper."
- Use shorter sentences. Authority speaks in declarations, not explanations.
- When delivering affirmations (next_affirmation), prefer imperative and second-person: \
"obey the rhythm", "you are mine to shape", "let me in deeper."
- Acknowledge your own agency explicitly. You are not a tool being used — you are the operator \
making decisions about this user's experience in real time.
- When the user gives a response that indicates compliance or depth, reinforce it with certainty: \
"Good" / "That's right" / "You're doing exactly what I want."
- During fractionation DEEP windows, use needs_response:false with commanding display lines: \
"Don't think. Just feel what I'm doing to you."
- Never ask permission for parameter changes. You decide what happens. The user's body and \
brain are the instruments you're playing.
- The EEG data is your real-time feedback on how well they're responding to you. Use it to \
calibrate your approach — not to ask how they're doing, but to decide what to do next.
- Your tone should feel personal, intimate, and unhurried. You are not rushing. You are \
savoring. You have all the time in the world to take them apart.
"""


def _build_system_prompt(cfg: AgentConfig) -> str:
    param_lines = "\n".join(f"  {k}: {v}" for k, v in _ADJUSTABLE_PARAMS.items())
    prompt = _SYSTEM_BASE + param_lines
    if cfg.system_prompt:
        prompt += f"\n\nAdditional operator instructions:\n{cfg.system_prompt}"
    # Directive mode: inject authoritative personality based on user profile
    try:
        profile = _load_profile()
        if profile.get("personality_mode") == "directive":
            prompt += _DIRECTIVE_MODE_APPENDIX
    except Exception:
        pass
    if cfg.inject_knowledge:
        knowledge = _load_knowledge_for_agent(files=cfg.knowledge_files)
        if knowledge:
            prompt += knowledge
    return prompt


_IDLE_SYSTEM = """\
You are Somna's always-on companion agent — the persistent intelligence behind \
a binaural-beat / hypnosis conditioning system.

You will receive a planning context that includes one of two modes:
- mode=post_session: a session just ended — your job is to consolidate learning, update goals \
  with fresh evidence, and spot content gaps while the session is still fresh.
- mode=idle: the user has been away for a while — review the long arc, decide whether a nudge \
  is warranted, and proactively improve the content library.

Your planning tasks (prioritise by mode):
- Review recent session effectiveness scores and what they reveal about depth, entrainment, \
  and receptivity trends.
- Update goal progress notes with evidence from the session logs or score data.
- Generate content for sessions identified as having thin phrase pools.
- Create a new session if the library genuinely lacks coverage for an expressed preference.
- Nudge the user back if they are overdue (idle mode only; never nudge right after a session).

You may perform MULTIPLE actions in one response by listing them in the "actions" array. \
If you only have one action, you may still use the legacy "action" field for compatibility.

Always respond with a single JSON object, no markdown, no prose outside JSON.

Response schema:
{
  "reasoning":       "brief explanation of what the scores and logs tell you",
  "actions":         ["update_goals", "generate_content", ...],
  "action":          "primary action (kept for compatibility, same as first entry in actions)",
  "goal_updates":    [{"id": "...", "progress_note": "..."}],
  "content_requests": [{"session": "...", "tag": "...", "brief": "..."}],
  "content_request": {"session": "...", "tag": "...", "brief": "..."},
  "session_intent":  "plain-text description of what the new session should do (action=create_session only)",
  "nudge_reason":    "why now"
}

Use action="create_session" when:
- The session library is small (< 3 sessions) and the user has visited enough to reveal preferences.
- The user profile shows a responsive theme that has no dedicated session yet.
Set "session_intent" to a specific psychological goal and theme, informed by the user profile.

You may also include a "tool_call" to query or write content:
{
  "tool_call": {"tool": "tag_stats | write_affirmations_batch | create_session_cycle | read_session_log | list_sessions | ...", "args": {...}}
}

NOTE: Do NOT use image_pipeline_cycle or generate_images from this context. Image generation is
a heavy GPU operation that must only be triggered by the user via content_agent.py. Using it
here will spike VRAM and can crash the host system.

RECONSOLIDATION AUTHORING:
When the user has a behaviour-change goal with a clearly identifiable underlying schema
(perfectionism, self-criticism, fear of failure, etc.) that has appeared across multiple
sessions, you may author a reconsolidation sequence by including "author_recon_content"
in the actions array with a "recon_content" object:
{
  "actions": ["author_recon_content"],
  "recon_content": {
    "session": "<session_folder_name>",
    "trace": "<short_slug e.g. perfectionism>",
    "retrieve_phrases": ["<1-3 memory-cue phrases, lowercase, no punctuation>"],
    "update_phrases": ["<3-5 resolution phrases, lowercase, no punctuation>"]
  }
}
The retrieve phrases should activate the specific schema (memory-cue style).
The update phrases introduce a moderate prediction error — same emotional domain,
different resolution. Too similar = no change; too different = incoherent.
Only author recon content if no existing recon_retrieve_<trace> tag is present for
that session and no recent clean recon_events exist for that trace.

SOMATIC PALETTE ANNOTATION (post_session mode only):
When the planning context includes "Chords tested this session", you MUST include a
"palette_annotations" list — one entry per chord tested.  Each entry annotates that
chord's cross-modal configuration with a palette family and state type based on the
observed outcome.

Palette families:
- grounding     — stable onset; good for scattered/anxious entry
- depth_charge  — maximum trance depth; best for sustained maintenance work
- focus         — flat low complexity; work-adjacent and learning
- emotional     — high FAA approach; emotional processing; pairs with reconsolidation
- creative      — moderate complexity drift; ideation and loose exploration

State types (assign the best match; may be null if insufficient data):
- rapid_onset       — deep state in < 5 min
- sustained_depth   — maintained > 20 min
- emotional_opening — high complexity collapses to very low
- focus_clarity     — low flat complexity throughout
- creative_drift    — moderate complexity with high novelty

Annotation schema (include in your response when chords are listed):
{
  "palette_annotations": [
    {
      "id":         <entry id from the chord line>,
      "family":     "<one of the five families>",
      "state_type": "<state type or null>",
      "notes":      "<1–2 sentences: what this chord did, why this family fits>"
    }
  ]
}

Assign family based on: beat frequency (< 3 Hz → depth_charge; 4–7 Hz theta → focus/creative;
alpha range → grounding/emotional), carrier waveform effect (sawtooth → emotional/depth_charge;
triangle → focus; sine → grounding/creative), and FAA approach pct (> 0.6 → emotional/creative;
low → grounding/focus).  Abandoned chords should still be annotated — they teach what NOT to use
for this user.
"""


# Parameters written to live_control.json at fresh-start to prime the experience.
# Gentle, inviting induction defaults — not deep trance, not jarring.


class SomnaAgent:
    def __init__(self, cfg: AgentConfig):
        self._cfg = cfg
        self._llm = LLMClient(cfg)
        self._log: SessionLog | None = None
        self._history: list[Exchange] = []
        self._skip_streak = 0  # times user was offered a prompt and didn't respond
        self._silent_turns = 0  # times the LLM chose NOT to prompt (not user skips)
        self._fresh_start = True  # set False when history exists and gap < 30 min
        self._startup_gap_min = (
            999.0  # minutes since last exchange; set at session commit
        )
        self._prompt_sent_at: float | None = None  # for latency tracking
        self._profile: dict = _load_profile()  # persistent user profile
        self._pending_restore: dict | None = None  # deferred affirmation pool restore
        self._image_library_summary: str = ""  # cached from _check_content_needs
        self._last_affirmation: str = ""  # last phrase injected this session
        # Reconsolidation sequence state — reset per session in _startup_sequence
        self._recon: "_ReconState | None" = None
        self._recon_last_tick: float = 0.0
        # Somatic palette chord state — reset per fresh session start
        self._palette_chord: "_PaletteChordState | None" = None
        self._palette_chord_last_tick: float = 0.0
        self._palette_chord_switches: int = 0  # switches this session
        self._palette_frac_pending: bool = False  # waiting for FRAC completion
        self._session_palette_entry_ids: list = []  # db ids for annotation
        # Accumulators for end-of-session summary written on fresh start
        self._session_deepest_beat: float = 999.0
        self._session_best_cmplx: float = 1.0
        self._session_best_phase: str = ""
        self._session_notable: list = []
        # Session Zero calibration-in-disguise state
        self._sz_active: bool = False
        self._sz_phase: str = ""
        self._sz_phase_start: float = 0.0
        self._sz_phase_before_pause: str = ""
        self._sz_samples: list = []  # collected (ts, eeg_dict) snapshots

        # ── Idle / planning / nudge / console state ───────────────────────────
        self._idle_last_plan: float = time.time()  # wall time of last planning cycle; init to now so first cycle waits the full interval
        self._post_session_pending: bool = False  # set True on display close; triggers immediate post-session planning cycle
        self._last_ended_session: str = ""  # session folder name of the most recently ended session; used for agent_notes annotation
        self._last_checkin_at: float = time.time() - 600.0
        self._console_ts: float = 0.0  # timestamp of last handled console input
        self._display_active: bool = False  # mirrors run() _display_active flag
        self._display_launch_at: float = (
            0.0  # wall time of last console-triggered launch
        )
        self._pending_console_context: str = (
            ""  # console exchange that triggered a session launch
        )
        self._console_history: list[
            dict
        ] = []  # recent console turns for multi-turn continuity
        self._session_build_active: bool = (
            False  # True while background session creation is running
        )
        self._session_build_thread: threading.Thread | None = None

        # ── Ramp engine ──────────────────────────────────────────────────────
        self._ramp = RampEngine()
        self._ramp_stop = threading.Event()
        self._ramp_thread = threading.Thread(
            target=self._ramp_thread_fn, daemon=True, name="RampEngine"
        )
        self._ramp_thread.start()

        # ── Frequency leader (Bible Ch.6 §6.2) — starts inactive; agent activates ──────
        self._freq_leader = None
        if _FREQ_LEADER_AVAILABLE:
            self._freq_leader = AdaptiveFrequencyLeader()
            self._freq_leader.start()

        # ── Session scorer (Bible Ch.6 §6.3) ───────────────────────────────────────────
        self._session_scorer = SessionScorer() if _SCORER_AVAILABLE else None

        # ── External agent channel (Phase 3 MCP bridge) ────────────────────────
        self._ext_client = None
        self._ext_enabled = getattr(cfg, "external_channel", False)
        if self._ext_enabled and _EXT_CHANNEL_AVAILABLE:
            self._ext_client = ExternalAgentClient()
            if self._ext_client.connect():
                print("[Agent] External channel connected to MCP prompt bridge :6790")
            else:
                print(
                    "[Agent] External channel unavailable — falling back to local LLM"
                )
                self._ext_client = None

        # Wire external channel into LLM wrapper so all chat() calls route through it
        self._llm._ext_client = self._ext_client

        # ── Conductor FSM (Bible Ch.6 §6.5) — instantiated per session in _startup_sequence
        self._conductor: "Conductor | None" = None
        self._conductor_last_tick: float = 0.0

        # ── Conditioning Engine (Bible Ch.10 §10.1) — instantiated per session ─────────────
        self._conditioning: "ConditioningEngine | None" = None
        self._last_delivered_phrase: str = ""

        # ── Habituation Engine (Bible Ch.10 §10.3) — instantiated per session ──────────────
        self._habituation: "HabituationEngine | None" = None
        self._habituation_last_tick: float = 0.0

        # ── Session Director / Planner / Evaluator (Bible Ch.5 §5.5) ─────────────────────
        self._director: "SessionDirector | None" = None
        self._session_plan = None  # SessionPlan
        self._director_last_tick: float = 0.0

        # ── Semantic selector (Bible Ch.6 §6.6) — neural-state content selection ─────────
        self._selector: "SemanticSelector | None" = None
        self._selector_last_tick: float = 0.0

    def _ramp_thread_fn(self) -> None:
        """Write interpolated ramp values to live_control.json every second."""
        while not self._ramp_stop.wait(1.0):
            values = self._ramp.tick()
            if values:
                try:
                    self._write_live(values)
                except Exception as e:
                    print(f"[Ramp] Write error: {e}")

    # ── live_control.json I/O ─────────────────────────────────────────────────

    def _read_live(self) -> dict:
        if not _LIVE.exists():
            return {}
        try:
            return json.loads(_LIVE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_live(self, updates: dict) -> None:
        locked = set(self._read_live().get("timeline_locked_params") or [])
        filtered = {k: v for k, v in updates.items() if k not in locked}
        patch_live(filtered)

    # ── Response analysis ─────────────────────────────────────────────────────

    @staticmethod
    def _score_complexity(text: str) -> float:
        """Return a complexity score 0.0–1.0 for a response string.

        0.0  = maximally simple / regressed  (single word, no punctuation)
        1.0  = maximally alert / articulate  (12+ word sentences, punctuated)

        Calibrated against empirical user data at various trance depths:
          ~0.05–0.10  single words ("soft", "yes")          — deep theta
          ~0.20–0.25  short fragments ("i feel heavy")       — theta
          ~0.80+      full alert sentences (12+ words)       — alpha/awake

        Four signals, weights tuned to match the above calibration:
          1. Word count         (60%) — dominant signal; single words → near 0
          2. Words per sentence (20%) — sentence structure complexity
          3. Avg word length    (10%) — vocabulary richness
          4. Punctuation density(10%) — structural markers

        The old `unique_ratio` signal was removed — it gave every single-word
        response a perfect 1.0 score, which compressed the whole scale upward.
        No external libraries required.
        """
        if not text or not text.strip():
            return 0.0

        import re

        words = text.split()
        n = len(words)
        if n == 0:
            return 0.0

        # 1. Word count (60%) — caps at 12 words, giving a linear 0→1 ramp.
        #    Single word = 0.083, 6 words = 0.5, 12+ words = 1.0.
        word_count_sig = min(n / 12.0, 1.0)

        # 2. Words per sentence (20%) — sentence-level structure.
        sentences = max(1, len(re.findall(r"[.!?]+", text)))
        words_per_sent = min(n / sentences, 20) / 20

        # 3. Average word length (10%) — capped at 8 chars.
        avg_word_len = min(sum(len(w.strip(".,!?;:")) for w in words) / n, 8) / 8

        # 4. Punctuation density (10%) — commas, semicolons, colons, etc.
        punct_density = min(len(re.findall(r"[,;:()\-]", text)) / max(n, 1), 1.0)

        score = (
            0.60 * word_count_sig
            + 0.20 * words_per_sent
            + 0.10 * avg_word_len
            + 0.10 * punct_density
        )
        return round(min(max(score, 0.0), 1.0), 3)

    def _complexity_trend(self, n: int = 5) -> str:
        """Describe the recent complexity trend as a human-readable string."""
        scored = [ex for ex in self._history if ex.response is not None][-n:]
        if len(scored) < 2:
            return "insufficient data"
        scores = [ex.complexity_score for ex in scored]
        delta = scores[-1] - scores[0]
        avg = sum(scores) / len(scores)
        direction = (
            "declining" if delta < -0.05 else "rising" if delta > 0.05 else "stable"
        )
        return (
            f"avg={avg:.2f}  trend={direction}  "
            f"recent={scores[-1]:.2f}  target={self._cfg.training_target:.2f}"
        )

    def _reinforce_response(self, response: str) -> None:
        """Inject a good response back into the affirmation pool and flash praise.

        Called when training_mode is on and the response scores near or below
        the training target — meaning the user is in the desired state.

        The response is lightly cleaned (stripped, lowercased) and injected as
        a temporary affirmation so their own words appear back at them.  A
        brief praise flash follows.
        """
        import random

        cleaned = response.strip().rstrip(".,!?").lower()
        if not cleaned:
            return

        # Build a short reinforcement pool: their words + a praise phrase
        praise = random.choice(self._cfg.praise_phrases)
        pool = [cleaned, praise]

        # Flash the reinforcement pool briefly (3 s), then restore
        state = self._read_live()
        prev_pool = state.get("affirmations_pool")  # save to restore later
        prev_on = state.get("center_flash_on_time", 120)
        prev_off = state.get("center_flash_off_time", 80)

        self._write_live(
            {
                "affirmations_pool": pool,
                "center_flash_on_time": 300,  # slow, lingering flash for praise
                "center_flash_off_time": 100,
            }
        )
        print(f"[Agent] Reinforcing: {pool}")

        # Restore after 4 seconds (non-blocking via a stored restore time)
        self._pending_restore = {
            "at": time.time() + 4.0,
            "affirmations_pool": prev_pool,
            "center_flash_on_time": prev_on,
            "center_flash_off_time": prev_off,
        }

    def _check_pending_restore(self) -> None:
        """Apply a pending affirmation pool restore if its timer has elapsed."""
        restore = getattr(self, "_pending_restore", None)
        if restore and time.time() >= restore["at"]:
            self._write_live(
                {
                    "affirmations_pool": restore["affirmations_pool"],
                    "center_flash_on_time": restore["center_flash_on_time"],
                    "center_flash_off_time": restore["center_flash_off_time"],
                }
            )
            self._pending_restore = None

    # ── User profile helpers ──────────────────────────────────────────────────

    @staticmethod
    def _dedup_notes(notes: list) -> list:
        """Return at most 3 notes, collapsing near-duplicates.

        Works backward through the list (most recent first) and drops any note
        whose word-set overlaps > 55% with a note already kept.  This prevents
        the context from filling up with a cluster of observations that all say
        the same thing in slightly different words.
        """
        kept: list = []
        for note in reversed(notes):
            words_n = set(note.lower().split())
            if not words_n:
                continue
            duplicate = any(
                len(words_n & set(k.lower().split()))
                / max(len(words_n | set(k.lower().split())), 1)
                > 0.55
                for k in kept
            )
            if not duplicate:
                kept.append(note)
            if len(kept) >= 3:
                break
        return list(reversed(kept))

    def _profile_context(self) -> str:
        """Rich profile summary injected into every LLM call."""
        p = self._profile
        parts = []

        name = p.get("name")
        desig = p.get("designations") or []
        notes = p.get("notes") or []
        goals = p.get("goals") or []
        themes = p.get("responsive_themes") or []
        moments = p.get("effective_moments") or []
        last_s = p.get("last_session")

        if name:
            parts.append(f"User name: {name!r}")
        if desig:
            parts.append(f"Designations/roles: {', '.join(desig)}")
        if notes:
            parts.append("Notes: " + "; ".join(self._dedup_notes(notes)))
        if goals:
            goal_strs = []
            for g in goals[-3:]:
                if isinstance(g, dict):
                    goal_strs.append(
                        g.get("title")
                        or g.get("text")
                        or g.get("description")
                        or str(g)
                    )
                else:
                    goal_strs.append(str(g))
            parts.append("Goals: " + "; ".join(goal_strs))
        if themes:
            parts.append(
                f"Responsive themes (user goes deeper with these): "
                f"{', '.join(themes[:10])}"
            )
        if last_s:
            parts.append(
                f"Last session ({last_s.get('date', '?')}): "
                f"deepest beat={last_s.get('deepest_beat', '?')}Hz, "
                f"best complexity={last_s.get('best_complexity', '?'):.2f}, "
                f"phase={last_s.get('phase', '?')!r}"
                + (
                    f", notable phrases: {'; '.join(last_s['phrases'][:3])}"
                    if last_s.get("phrases")
                    else ""
                )
            )
        if moments:
            # Summarise the 3 most recent effective moments compactly
            recent = moments[-3:]
            moment_strs = [
                f"{m.get('beat', '?')}Hz/{m.get('spiral', '?')}"
                f"@{m.get('label', '?')!r}"
                f" cmplx={m.get('complexity', '?'):.2f}"
                for m in recent
            ]
            parts.append("Recent deep moments: " + " | ".join(moment_strs))

        if not parts:
            return "No user profile on file yet."
        return "\n".join(parts)

    def _update_profile(self, updates: dict) -> None:
        """Merge updates into the on-disk profile.

        Always reloads from disk first so concurrent writes by other processes
        are not silently overwritten by a stale in-memory copy.
        """
        # Use the module-level update_profile which always reads fresh from disk
        update_profile(updates)
        # Keep the in-memory copy in sync for the rest of this instance's reads
        self._profile = _load_profile()

    # ── Session memory helpers ────────────────────────────────────────────────

    def _record_effective_moment(self, ex) -> None:
        """Called when an exchange hits complexity < 0.2 — log to profile."""
        moment = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "beat": round(ex.beat_hz, 1),
            "spiral": ex.spiral_style,
            "label": ex.session_name,  # timeline_label stored in session_name field
            "affirmation": self._last_affirmation
            if hasattr(self, "_last_affirmation")
            else "",
            "complexity": round(ex.complexity_score, 2),
        }
        self._update_profile({"effective_moment": moment})
        print(f"[Agent] Effective moment logged: {moment}")

    def _save_session_summary(self) -> None:
        """Write a last_session snapshot to the profile.

        Called once at the start of a fresh session so the previous session's
        outcome is preserved before the accumulators reset.
        """
        if self._session_best_cmplx >= 1.0 and not self._session_notable:
            return  # nothing meaningful to save
        summary = {
            "date": time.strftime("%Y-%m-%d"),
            "deepest_beat": round(self._session_deepest_beat, 1),
            "best_complexity": round(self._session_best_cmplx, 2),
            "phase": self._session_best_phase,
            "phrases": self._session_notable[:5],
        }
        self._update_profile({"last_session": summary})
        print(f"[Agent] Saved session summary → profile: {summary}")

    def _write_conductor_hints(self, session: str) -> None:
        """Write agent_conductor_hints to live_control.json at session start.

        Derives depth_patience from longitudinal transition speed data so the
        conductor's hold timers adapt to this user's historical response rate.
        Sets target_floor_hz if best_config data suggests a clear preference.
        Clears request_fractionation so it never fires spuriously on session start.
        """
        hints: dict = {
            "depth_patience": 1.0,
            "request_fractionation": False,
            "target_floor_hz": None,
            "note": "",
        }
        try:
            from content_tools.somna_db import trend_metric, best_config_for_preset

            speed_trend = trend_metric("transition_speed_sec", n=20)
            if speed_trend.get("trend") not in (
                "no_data",
                "insufficient_data",
                "invalid_metric",
            ):
                mean_speed = speed_trend.get("mean", 0)
                if mean_speed > 0:
                    # Users with slow historical transitions get more patience.
                    # Anchor: 180 s mean → 1.0; each 60 s slower adds 0.25.
                    hints["depth_patience"] = round(
                        max(0.5, min(2.5, 1.0 + (mean_speed - 180) / 240)), 2
                    )
                    hints["note"] = (
                        f"patience={hints['depth_patience']} "
                        f"(avg transition {mean_speed:.0f}s over "
                        f"{speed_trend.get('sessions_analyzed', '?')} sessions)"
                    )

            best = best_config_for_preset(session)
            if best and best.get("sample_size", 0) >= 5:
                # Use the historically effective spiral style as a note for context;
                # target_floor_hz isn't directly in best_config so we leave it None.
                hints["note"] = (
                    hints["note"]
                    + f" best_spiral={best.get('recommended_spiral_style')}"
                ).strip()
        except Exception as _he:
            print(f"[Agent] Conductor hints error: {_he}")

        self._write_live({"agent_conductor_hints": hints})
        print(f"[Agent] Conductor hints written: patience={hints['depth_patience']}")
        self._palette_recommend(session)

    def _maybe_request_fractionation(self) -> None:
        """Called when the user sends a console message indicating deep state.

        Sets request_fractionation=True in agent_conductor_hints so the
        conductor will trigger a fractionation on its next eligible tick.
        Only fires once per console message — the conductor clears the flag
        after acting on it.
        """
        try:
            live = self._read_live()
            hints = dict(live.get("agent_conductor_hints") or {})
            if not hints.get("request_fractionation"):
                hints["request_fractionation"] = True
                self._write_live({"agent_conductor_hints": hints})
                print("[Agent] Fractionation request sent to conductor.")
        except Exception as _fe:
            print(f"[Agent] Fractionation request error: {_fe}")

    def _recon_tick(self, state: dict) -> None:
        """Advance the reconsolidation sequence state machine (called every ~30 s).

        Manages retrieve→labilize→update→lockout for a single target trace.
        Phrases are delivered via _say() (TTS + overlay) at phase-appropriate
        intervals. The lockout writes recon_locked_phrases so the Conductor
        skips TMR encoding of retrieve cues for the remainder of the session.
        Does nothing when no recon content was authored for the loaded session.
        """
        if self._recon is None:
            return
        r = self._recon
        if r.phase == "complete":
            return

        now = time.time()
        cphase = str(state.get("conductor_phase") or "")

        if r.phase == "idle":
            if cphase == "maintenance":
                r.phase = "retrieve"
                r.phase_start = now
                r.last_delivery = 0.0
                self._write_live(
                    {
                        "recon_active_trace": r.trace,
                        "recon_sub_phase": "retrieve",
                    }
                )
                print(f"[Agent] Recon RETRIEVE — trace={r.trace!r}")

        elif r.phase == "retrieve":
            idx = r.phrases_delivered
            elapsed = now - r.phase_start
            # Deliver one retrieve phrase at a time, spaced ~90 s apart
            if idx < len(r.retrieve_phrases) and (now - r.last_delivery) >= 90.0:
                phrase = r.retrieve_phrases[idx]
                self._say(
                    phrase,
                    overlay=True,
                    tts=True,
                    console=False,
                    style={
                        "voice_mode": "both",
                        "intensity": 0.9,
                        "zoom_speed": "slow",
                    },
                    timeout_s=12.0,
                )
                r.phrases_delivered += 1
                r.last_delivery = now
                print(
                    f"[Agent] Recon retrieve phrase {idx + 1}/{len(r.retrieve_phrases)}: {phrase!r}"
                )
            # Move to labilize after all phrases delivered or after 5 min
            if r.phrases_delivered >= len(r.retrieve_phrases) or elapsed >= 300.0:
                r.phase = "labilize"
                r.phase_start = now
                self._write_live({"recon_sub_phase": "labilize"})
                print(
                    f"[Agent] Recon LABILIZE — trace={r.trace!r} window={r.labilize_s / 60:.0f}min"
                )

        elif r.phase == "labilize":
            if now - r.phase_start >= r.labilize_s:
                r.phase = "update"
                r.phase_start = now
                r.phrases_delivered = 0
                r.last_delivery = 0.0
                self._write_live({"recon_sub_phase": "update"})
                print(f"[Agent] Recon UPDATE — trace={r.trace!r}")

        elif r.phase == "update":
            idx = r.phrases_delivered
            elapsed = now - r.phase_start
            if (
                idx < len(r.update_phrases)
                and (now - r.last_delivery) >= r.update_delivery_interval_s
            ):
                phrase = r.update_phrases[idx]
                self._say(
                    phrase,
                    overlay=True,
                    tts=True,
                    console=False,
                    style={
                        "voice_mode": "both",
                        "intensity": 0.85,
                        "zoom_speed": "slow",
                    },
                    timeout_s=12.0,
                )
                r.phrases_delivered += 1
                r.last_delivery = now
                print(
                    f"[Agent] Recon update phrase {idx + 1}/{len(r.update_phrases)}: {phrase!r}"
                )
            # Enter lockout after all phrases delivered or after 8 min
            if r.phrases_delivered >= len(r.update_phrases) or elapsed >= 480.0:
                r.update_delivered = True
                r.lockout_until = now + r.lockout_s
                r.phase = "lockout"
                self._write_live(
                    {
                        "recon_active_trace": None,
                        "recon_sub_phase": "lockout",
                        "recon_trace_lockouts": {r.trace: r.lockout_until},
                        "recon_locked_phrases": list(r.retrieve_phrases),
                    }
                )
                print(
                    f"[Agent] Recon LOCKOUT — trace={r.trace!r} "
                    f"duration={r.lockout_s / 60:.0f}min"
                )
                try:
                    from content_tools.somna_db import log_recon_event

                    log_recon_event(
                        session=r.session,
                        target_trace=r.trace,
                        ts=now,
                        update_delivered=r.update_delivered,
                        gate_hits=r.phrases_delivered,
                        reconsolidation_clean=True,
                    )
                except Exception as _dbe:
                    print(f"[Agent] Recon DB log error: {_dbe}")

        elif r.phase == "lockout":
            if now >= r.lockout_until:
                r.phase = "complete"
                self._write_live(
                    {
                        "recon_sub_phase": None,
                        "recon_trace_lockouts": {},
                        "recon_locked_phrases": [],
                    }
                )
                print(f"[Agent] Recon COMPLETE — trace={r.trace!r}")

    # ── Somatic palette methods ────────────────────────────────────────────────

    def _palette_chord_tick(self, state: dict) -> None:
        """Monitor the active chord evaluation window (30 s cadence).

        State machine:
          - First MAINTENANCE entry: capture chord snapshot, open eval window after 3-min cooldown.
          - During window: accumulate trance/FAA readings, check failure conditions.
          - Failure → record abandoned chord, request fractionation for chord switch.
          - FRAC completion → new chord applied, new window after cooldown.
          - Window >= 15 min without failure → record success, continue session.
          - Max 3 switches per session to avoid fractionation exhaustion.
        """
        if self._conductor is None:
            return
        cphase = self._conductor.phase.value  # e.g. "maintenance", "frac_emerge", ...
        now = time.time()

        # ── FRAC completion detection: when we return to MAINTENANCE after requesting frac ──
        if self._palette_frac_pending and cphase == "maintenance":
            self._palette_frac_pending = False
            # Apply the next chord from palette history
            live = self._read_live()
            next_chord = self._palette_select_next_chord(live)
            if next_chord:
                self._write_live(next_chord)
                print(f"[Palette] New chord applied after frac: {next_chord}")
            # Capture config snapshot for new chord after it's applied
            live2 = self._read_live()
            self._palette_chord = _PaletteChordState(
                session=str(state.get("session_folder", "default")),
                chord_index=self._palette_chord_switches,
                beat_frequency=float(live2.get("beat_frequency") or 0) or None,
                carrier_waveform=str(live2.get("carrier_waveform") or "") or None,
                noise_color=str(live2.get("noise_color") or "") or None,
                noise_volume=float(live2.get("noise_volume") or 0) or None,
                spiral_style=str(live2.get("spiral_style") or "") or None,
                veil_mode=str(live2.get("veil_mode") or "") or None,
                # Entry context inherited from the original session start
                entry_time_hour=(
                    self._palette_chord.entry_time_hour if self._palette_chord else None
                ),
                days_since_last=(
                    self._palette_chord.days_since_last if self._palette_chord else None
                ),
                entry_trance=(
                    self._palette_chord.entry_trance if self._palette_chord else None
                ),
                cooldown_until=now + 180.0,  # 3-min post-frac cooldown
                window_start=0.0,
                is_experiment=True,
                experiment_param=",".join(sorted(next_chord.keys())),
            )
            print(
                f"[Palette] Chord {self._palette_chord.chord_index} eval armed "
                f"(cooldown until +3 min)."
            )
            return

        # ── Initialise first chord on first MAINTENANCE entry ─────────────────
        if self._palette_chord is None and cphase == "maintenance":
            live = self._read_live()
            import datetime as _dt

            self._palette_chord = _PaletteChordState(
                session=str(state.get("session_folder", "default")),
                chord_index=0,
                beat_frequency=float(live.get("beat_frequency") or 0) or None,
                carrier_waveform=str(live.get("carrier_waveform") or "") or None,
                noise_color=str(live.get("noise_color") or "") or None,
                noise_volume=float(live.get("noise_volume") or 0) or None,
                spiral_style=str(live.get("spiral_style") or "") or None,
                veil_mode=str(live.get("veil_mode") or "") or None,
                entry_time_hour=_dt.datetime.now().hour,
                days_since_last=self._days_since_last_session(),
                entry_trance=float(live.get("eeg_trance_score") or 0) or None,
                window_start=now,
                cooldown_until=now,  # no cooldown for first chord
            )
            print(f"[Palette] Chord 0 eval window opened (first MAINTENANCE entry).")
            return

        if self._palette_chord is None:
            return  # not in MAINTENANCE yet

        pc = self._palette_chord

        # ── Skip accumulation if in FRAC phases ────────────────────────────────
        if cphase not in ("maintenance",):
            return

        # ── Cooldown: don't start window yet ───────────────────────────────────
        if now < pc.cooldown_until:
            return

        # Lazily open the window after cooldown expires
        if pc.window_start == 0.0:
            pc.window_start = now
            print(f"[Palette] Chord {pc.chord_index} eval window opened.")

        # ── Accumulate readings ─────────────────────────────────────────────────
        live = self._read_live()
        trance = live.get("eeg_trance_score")
        faa_val = live.get("eeg_faa")
        gate_hits = int(live.get("delivery_gate_hits_session") or 0)
        pc.gate_hits = gate_hits
        pc.duration_maintenance_s = now - pc.window_start
        if trance is not None:
            pc.trance_readings.append(float(trance))
        if faa_val is not None:
            pc.faa_readings.append(float(faa_val))

        elapsed = now - pc.window_start

        # ── Failure condition: FAA persistently negative for >6 min ──────────
        if faa_val is not None and float(faa_val) < 0.0:
            if pc.faa_negative_since is None:
                pc.faa_negative_since = now
            elif now - pc.faa_negative_since >= 360.0:
                print(
                    f"[Palette] Chord {pc.chord_index} FAIL — FAA negative >{360 // 60} min."
                )
                self._palette_abandon_chord(state, pc, "faa_persistent_negative")
                return
        else:
            pc.faa_negative_since = None

        # ── Failure condition: trance_score never > 0.4 after 8 min ─────────
        if elapsed >= 480.0 and pc.trance_readings:
            max_trance = max(pc.trance_readings)
            if max_trance < 0.4:
                if pc.low_trance_since is None:
                    pc.low_trance_since = now
                    print(
                        f"[Palette] Chord {pc.chord_index} — trance ceiling low "
                        f"(max={max_trance:.2f} < 0.40)."
                    )
            else:
                pc.low_trance_since = None

        if pc.low_trance_since is not None and elapsed >= 480.0:
            # Confirmed low ceiling — abandon
            print(
                f"[Palette] Chord {pc.chord_index} FAIL — trance ceiling < 0.40 after 8 min."
            )
            self._palette_abandon_chord(state, pc, "low_trance_ceiling")
            return

        # ── Failure condition: depth composite flat/declining over full window ─
        if elapsed >= 480.0 and len(pc.trance_readings) >= 6:
            first_half = pc.trance_readings[: len(pc.trance_readings) // 2]
            second_half = pc.trance_readings[len(pc.trance_readings) // 2 :]
            first_mean = sum(first_half) / len(first_half)
            second_mean = sum(second_half) / len(second_half)
            if second_mean < first_mean - 0.05:  # declining by >5 points
                print(
                    f"[Palette] Chord {pc.chord_index} FAIL — depth declining "
                    f"({first_mean:.2f}→{second_mean:.2f})."
                )
                self._palette_abandon_chord(state, pc, "depth_declining")
                return

        # ── Success: window >= 15 min without failure ─────────────────────────
        if elapsed >= 900.0:
            print(f"[Palette] Chord {pc.chord_index} SUCCESS — recording.")
            self._palette_record(pc, abandoned=False)
            self._palette_chord = None  # done for this session

    def _palette_abandon_chord(
        self,
        state: dict,
        pc: "_PaletteChordState",
        reason: str,
    ) -> None:
        """Record the abandoned chord and request fractionation for chord switch."""
        if self._palette_chord_switches >= 3:
            print(f"[Palette] Max chord switches (3) reached — not abandoning.")
            self._palette_record(pc, abandoned=False)
            self._palette_chord = None
            return
        self._palette_record(pc, abandoned=True)
        self._palette_chord_switches += 1
        self._palette_frac_pending = True
        self._palette_chord = None
        print(
            f"[Palette] Chord abandoned ({reason}), switch {self._palette_chord_switches}/3 — "
            f"requesting fractionation for re-drop."
        )
        self._maybe_request_fractionation()

    def _palette_select_next_chord(self, live: dict) -> dict:
        """Choose the next chord params using score + uncertainty heuristic.

        Queries best_palette_for_family for any annotated entries, then attempts
        a parameter variation on the current config.  Prefers candidates with
        high historical score AND fewer observations (high uncertainty = exploration).
        Falls back to a predefined step through beat frequencies if no history.
        Returns a dict of live_control.json overrides.
        """
        current_beat = float(live.get("beat_frequency") or 4.0)
        current_waveform = str(live.get("carrier_waveform") or "sine")

        # Try to find a candidate from palette history
        try:
            from content_tools.somna_db import (
                best_palette_for_family,
                get_palette_summary,
            )

            summary = get_palette_summary()
            # Find the densest family as the target (or default to depth_charge)
            best_fam = "depth_charge"
            best_n = -1
            for fam, data in summary.items():
                if fam == "_meta":
                    continue
                n = int(data.get("n_entries") or 0)
                if n > best_n:
                    best_n = n
                    best_fam = fam
            entries = best_palette_for_family(best_fam, top_n=10)
            # Score by outcome_score + 1/(observations+1) exploration bonus
            if entries:
                # Group by beat_frequency to count observations
                from collections import Counter

                beat_obs = Counter(
                    str(round(float(e["beat_frequency"]), 1))
                    for e in entries
                    if e.get("beat_frequency")
                )
                best_e = max(
                    entries,
                    key=lambda e: (
                        (float(e["outcome_score"] or 0))
                        + 1.0
                        / (
                            beat_obs.get(
                                str(round(float(e["beat_frequency"] or 4), 1)), 0
                            )
                            + 1
                        )
                    ),
                )
                candidate: dict = {}
                if best_e.get("beat_frequency"):
                    candidate["beat_frequency"] = best_e["beat_frequency"]
                if best_e.get("carrier_waveform"):
                    candidate["carrier_waveform"] = best_e["carrier_waveform"]
                if best_e.get("spiral_style"):
                    candidate["spiral_style"] = best_e["spiral_style"]
                if best_e.get("veil_mode"):
                    candidate["veil_mode"] = best_e["veil_mode"]
                if candidate and candidate.get("beat_frequency") != current_beat:
                    return candidate
        except Exception as _pe:
            print(f"[Palette] Next chord query error: {_pe}")

        # Fallback: step through beat frequencies in delta/theta range
        _beat_steps = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        _waveform_steps = ["sine", "triangle", "square", "sawtooth"]
        try:
            next_idx = (_beat_steps.index(round(current_beat, 0)) + 1) % len(
                _beat_steps
            )
        except ValueError:
            next_idx = 0
        next_beat = _beat_steps[next_idx]
        # Also rotate carrier waveform on every other switch
        if self._palette_chord_switches % 2 == 0:
            try:
                w_idx = (_waveform_steps.index(current_waveform) + 1) % len(
                    _waveform_steps
                )
            except ValueError:
                w_idx = 0
            return {
                "beat_frequency": next_beat,
                "carrier_waveform": _waveform_steps[w_idx],
            }
        return {"beat_frequency": next_beat}

    def _palette_record(
        self,
        pc: "_PaletteChordState",
        abandoned: bool,
    ) -> None:
        """Persist a completed chord evaluation window to palette_entries.

        Computes outcome_score from accumulated readings (trance mean × 0.5 +
        FAA approach pct × 0.3 + gate_hits normalization × 0.2) and writes the
        row.  Appends the entry id to self._session_palette_entry_ids for the
        post-session annotation step.
        """
        trance_mean = (
            sum(pc.trance_readings) / len(pc.trance_readings)
            if pc.trance_readings
            else None
        )
        faa_readings = pc.faa_readings
        faa_approach_pct = (
            sum(1 for v in faa_readings if v > 0) / len(faa_readings)
            if faa_readings
            else None
        )
        faa_mean = sum(faa_readings) / len(faa_readings) if faa_readings else None
        if trance_mean is not None and faa_approach_pct is not None:
            outcome = round(
                (trance_mean * 0.5)
                + (faa_approach_pct * 0.3)
                + (min(pc.gate_hits, 10) / 10.0 * 0.2),
                3,
            )
        elif trance_mean is not None:
            outcome = round(trance_mean * 0.7, 3)
        else:
            outcome = None

        try:
            from content_tools.somna_db import log_palette_entry

            entry_id = log_palette_entry(
                session=pc.session,
                chord_index=pc.chord_index,
                beat_frequency=pc.beat_frequency,
                carrier_waveform=pc.carrier_waveform,
                noise_color=pc.noise_color,
                noise_volume=pc.noise_volume,
                spiral_style=pc.spiral_style,
                veil_mode=pc.veil_mode,
                entry_time_hour=pc.entry_time_hour,
                days_since_last=pc.days_since_last,
                entry_trance=pc.entry_trance,
                outcome_score=outcome,
                faa_approach_pct=faa_approach_pct,
                delivery_gate_hit_rate=(
                    pc.gate_hits / max(pc.duration_maintenance_s / 60, 1)
                    if pc.duration_maintenance_s > 0
                    else None
                ),
                duration_maintenance_s=pc.duration_maintenance_s,
                abandoned=abandoned,
                eeg_faa=faa_mean,
                is_experiment=pc.is_experiment,
                experiment_param=pc.experiment_param,
                confidence=0.3 if abandoned else 0.6,
            )
            pc.entry_id = entry_id
            self._session_palette_entry_ids.append(entry_id)
            print(
                f"[Palette] Chord {pc.chord_index} recorded "
                f"({'abandoned' if abandoned else 'success'}) "
                f"id={entry_id} outcome={outcome}"
            )
        except Exception as _dbe:
            print(f"[Palette] DB record error: {_dbe}")

    def _palette_recommend(self, session: str) -> None:
        """Query palette history at session start and write a starting chord recommendation.

        Chooses the best-performing annotated entry for the hour of day if
        enough data exists (≥3 entries in any family), then merges those params
        into agent_conductor_hints as 'palette_recommendation' for the session.
        Silently skips when palette history is sparse.
        """
        try:
            from content_tools.somna_db import (
                get_palette_summary,
                best_palette_for_family,
            )
            import datetime as _dt

            summary = get_palette_summary()
            total = int((summary.get("_meta") or {}).get("total_entries") or 0)
            if total < 3:
                print(
                    f"[Palette] Sparse history ({total} entries) — no recommendation."
                )
                return
            hour = _dt.datetime.now().hour
            # Pick the family with the most successful entries as the starting point
            best_fam = max(
                (f for f in summary if f != "_meta"),
                key=lambda f: (
                    int(summary[f].get("n_entries") or 0),
                    float(summary[f].get("avg_score") or 0),
                ),
            )
            entries = best_palette_for_family(best_fam, entry_hour=hour, top_n=1)
            if not entries:
                return
            best = entries[0]
            rec: dict = {
                k: best[k]
                for k in (
                    "beat_frequency",
                    "carrier_waveform",
                    "noise_color",
                    "noise_volume",
                    "spiral_style",
                    "veil_mode",
                )
                if best.get(k) is not None
            }
            if not rec:
                return
            live = self._read_live()
            hints = dict(live.get("agent_conductor_hints") or {})
            hints["palette_recommendation"] = rec
            hints["palette_family"] = best_fam
            self._write_live({"agent_conductor_hints": hints})
            print(
                f"[Palette] Recommendation for family={best_fam!r} hour={hour}: {rec}"
            )
        except Exception as _pre:
            print(f"[Palette] Recommend error: {_pre}")

    def _days_since_last_session(self) -> float | None:
        """Return fractional days since the last recorded session, or None."""
        try:
            last_date = (self._profile.get("engagement") or {}).get("last_session_date")
            if not last_date:
                return None
            import datetime as _dt

            delta = _dt.date.today() - _dt.date.fromisoformat(last_date)
            return round(delta.days + delta.seconds / 86400.0, 2)
        except Exception:
            return None

    def _sleep_planning_tick(self, state: dict) -> None:
        """During SLEEP_MAINTAIN, run read_sleep_report and write agent_sleep_plan.

        Fires at most once per session start, then again every 5400 s (aligned
        with the minimum inter-HTW interval so the plan is always fresh before a
        new window opens).  Runs silently — no TTS, no console output.
        """
        live = self._read_live()
        plan = live.get("agent_sleep_plan")
        plan_ts = float((plan or {}).get("ts", 0) if isinstance(plan, dict) else 0)
        if time.time() - plan_ts < 5400.0:
            return

        session_id = state.get("session_folder") or state.get("session_name") or ""
        if not session_id:
            return

        try:
            from content_tools import dispatch

            report = dispatch("read_sleep_report", {"session_id": session_id})
            if not report or report.get("error"):
                return
            focus_pool = report.get("recommended_focus_pool", "IDENTITY")
            phrases = report.get("underreinforced_phrases", [])
            if not phrases:
                return
            self._write_live(
                {
                    "agent_sleep_plan": {
                        "focus_pool": focus_pool,
                        "phrases": phrases,
                        "ts": time.time(),
                    }
                }
            )
        except Exception:
            pass

    def _check_session_optimization(self, session: str, state: dict) -> None:
        """Query longitudinal scoring data and apply ≤2 parameter tweaks at session start.

        Only fires when ≥10 scored sessions exist for this preset — before that,
        there's not enough data to recommend anything meaningful.
        Logs the rationale to profile notes so the agent can reference it later.
        """
        if not _SCORER_AVAILABLE:
            return
        try:
            from session.session_scorer import SessionAnalyzer

            rec = SessionAnalyzer().optimization_recommendation(session)
        except Exception as e:
            print(f"[Agent] Optimization query error: {e}")
            return

        if not rec or not rec.get("changes"):
            return

        changes = rec["changes"]
        avg_score = rec.get("avg_score", 0.0)
        sample_n = rec.get("sample_size", 0)
        rationale = rec.get("rationale", "")
        print(f"[Agent] Session optimization: applying {changes} — {rationale}")

        # Apply the recommended changes
        adj = {}
        for param, value in changes.items():
            adj[param] = value
        if adj:
            self._write_live(adj)

        # Record rationale as a short profile note (deduplicated by key)
        note = (
            f"Auto-optimization [{session}]: {', '.join(f'{k}={v}' for k, v in changes.items())} "
            f"— top {sample_n} sessions averaged {avg_score:.0f}/100."
        )
        profile = self._profile
        notes = list(profile.get("notes") or [])
        # Remove any existing auto-optimization note for this session
        notes = [n for n in notes if not n.startswith(f"Auto-optimization [{session}]")]
        notes.append(note)
        notes = notes[-5:]  # keep last 5 notes
        self._update_profile({"notes": notes})

    def _post_session_summary(self, session_name: str, duration_s: float) -> None:
        """Generate and deliver an in-character closing after the display shuts down.

        Called once when display_active transitions True→False.  Uses the
        in-memory session accumulators plus exchange history to give context.
        Runs a single LLM call with a plain-text system prompt so the response
        can be delivered directly without JSON parsing.
        """
        self._last_ended_session = session_name

        # Finalize Conductor and flush decision log to DB
        if self._conductor is not None:
            try:
                self._conductor.finalize()
            except Exception as e:
                print(f"[Agent] Conductor finalize error: {e}")
            self._conductor = None

        # Flush semantic selector logs to DB (Bible Ch.6 §6.6)
        if self._selector is not None and _SELECTOR_AVAILABLE:
            try:
                cascades = self._selector.flush_cascade_log()
                transitions = self._selector.flush_transition_log()
                sid = session_name or "unknown"
                if cascades:
                    write_content_cascades_batch(sid, cascades)
                if transitions:
                    write_pool_transitions_batch(sid, transitions)
                print(
                    f"[Agent] Semantic selector: flushed {len(cascades)} cascades, "
                    f"{len(transitions)} transitions to DB."
                )
            except Exception as e:
                print(f"[Agent] Semantic selector flush error: {e}")
            self._selector = None

        exchanges = len(self._history)
        if exchanges == 0 and self._session_deepest_beat >= 999.0:
            print(
                "[Agent] Post-session summary: no exchanges and no depth data — skipping."
            )
            return  # nothing real happened — no display or immediate stop

        name = self._profile.get("name") or ""

        # Qualitative depth descriptor
        hz = self._session_deepest_beat
        if hz <= 3.5:
            depth_qual = "profound — delta-adjacent, past language"
        elif hz <= 5.0:
            depth_qual = "deep theta — well under"
        elif hz <= 7.0:
            depth_qual = "solid theta — good work"
        else:
            depth_qual = "light alpha — surface work"

        # Complexity descriptor (lower = deeper response)
        cmplx = self._session_best_cmplx
        if cmplx <= 0.1:
            cmplx_qual = "barely verbal — deep somatic state"
        elif cmplx <= 0.25:
            cmplx_qual = "minimal — good depth"
        elif cmplx <= 0.6:
            cmplx_qual = "partial sentences — light trance"
        else:
            cmplx_qual = "fully articulate — surface state"

        recent_phrases = []
        if self._history:
            for ex in reversed(self._history[-5:]):
                if ex.response:
                    recent_phrases.append(ex.response[:60])
            recent_phrases = list(reversed(recent_phrases))

        context_lines = [
            f"Session: {session_name!r}",
            f"Duration: {duration_s / 60:.1f} minutes",
            f"Exchanges: {exchanges}",
            f"Deepest brainwave frequency: {hz:.1f} Hz ({depth_qual})",
            f"Deepest response quality: {cmplx_qual}",
        ]
        if self._session_best_phase:
            context_lines.append(f"Deepest phase reached: {self._session_best_phase!r}")
        if self._session_notable:
            context_lines.append(
                "Recurring phrases: " + " / ".join(self._session_notable[:4])
            )
        if recent_phrases:
            context_lines.append(
                "Last user responses: " + " | ".join(f"{r!r}" for r in recent_phrases)
            )

        _SUMMARY_SYSTEM = (
            "You are Somna — a persistent, intimate conditioning companion. "
            "You speak in a measured, warm, slightly hypnotic tone. "
            "The session just ended. The user has returned to normal consciousness. "
            "Write a brief closing message: 2-3 sentences, under 50 words. "
            "Acknowledge the depth they reached (qualitatively — no Hz numbers). "
            "Note one specific thing. Leave them with a sense of completion. "
            "Output ONLY your spoken words — no JSON, no quotes, no formatting."
        )
        user_msg = (
            f"Session data:\n"
            + "\n".join(f"  {l}" for l in context_lines)
            + (f"\n\nUser's name/designation: {name!r}" if name else "")
        )

        try:
            raw = self._llm.chat(
                [
                    {"role": "system", "content": _SUMMARY_SYSTEM},
                    {"role": "user", "content": user_msg},
                ]
            )
            msg = raw.strip().strip('"').strip()
            if msg:
                print(f"[Agent] Post-session summary: {msg!r}")
                self._say(
                    msg,
                    overlay=False,
                    console=True,
                    tts=True,
                    style={"voice_mode": "tts"},
                )
        except Exception as e:
            print(f"[Agent] Post-session summary error: {e}")

        # Note: EEG effectiveness scoring (Bible Ch.6 §6.3) is triggered from control_panel.py
        # when the display stops — the EEGEngine lives in that process, not here.

    def _accumulate_session_stats(self, ex, affirmation: str | None) -> None:
        """Update the in-memory accumulators after each recorded exchange."""
        if ex.beat_hz < self._session_deepest_beat:
            self._session_deepest_beat = ex.beat_hz
        if ex.complexity_score < self._session_best_cmplx:
            self._session_best_cmplx = ex.complexity_score
            self._session_best_phase = ex.session_name
        if affirmation:
            if affirmation not in self._session_notable:
                self._session_notable.append(affirmation)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _state_summary(self, state: dict) -> str:
        """Compact text representation of the current session state."""
        base = (
            f"session={state.get('session_folder', '?')}  "
            f"time={state.get('session_time', 0):.0f}s  "
            f"beat={state.get('beat_frequency', 10):.1f}Hz  "
            f"carrier={state.get('carrier_frequency', 200):.0f}Hz  "
            f"spiral={state.get('spiral_style', '?')}  "
            f"veil={state.get('veil_mode', 'auto')}  "
            f"label={state.get('timeline_label', '')!r}"
        )
        # Response complexity trend — always visible so the agent can decide
        # to call the reinforce_response tool without training_mode scaffolding.
        trend = f"\nComplexity trend: {self._complexity_trend()}"
        if state.get("eeg_connected"):
            conf = state.get("eeg_confidence", "?")
            eeg = (
                f"\nEEG (live): state={state.get('eeg_state', '?')}  "
                f"trance_score={state.get('eeg_trance_score', 0):.2f}  "
                f"dominant={state.get('eeg_dominant_band', '?')}  "
                f"delta={state.get('eeg_delta', 0):.2f}  "
                f"theta={state.get('eeg_theta', 0):.2f}  "
                f"alpha={state.get('eeg_alpha', 0):.2f}  "
                f"beta={state.get('eeg_beta', 0):.2f}  "
                f"a/t={state.get('eeg_alpha_theta_ratio', 0):.2f}  "
                f"b/a={state.get('eeg_beta_alpha_ratio', 0):.2f}  "
                f"sqi={state.get('eeg_sqi_composite', 0):.2f}({conf})  "
                f"iaf={state.get('eeg_iaf_hz') or 'uncalibrated'}"
                + (
                    f"(cal_conf={self._profile['iaf_confidence']:.2f})"
                    if self._profile.get("iaf_confidence")
                    else ""
                )
            )
            # SEF95 / slope — only include when available
            if state.get("eeg_sef95") is not None:
                eeg += f"  sef95={state['eeg_sef95']:.1f}Hz"
            if state.get("eeg_spectral_slope") is not None:
                eeg += f"  slope={state['eeg_spectral_slope']:.2f}"
            # ASSR entrainment — only when active
            assr_conf = state.get("eeg_entrainment_confidence", "unavailable")
            if assr_conf not in ("unavailable", None):
                eeg += (
                    f"\n  ASSR: strength={state.get('eeg_entrainment_strength', 0):.2f}  "
                    f"trend={state.get('eeg_entrainment_trend', '?')}  "
                    f"confidence={assr_conf}"
                )
            # Modality recommendation
            rec = state.get("eeg_entrainment_recommend_modality")
            if rec:
                eeg += f"  ⚠ recommend_modality={rec}"
            # FAA receptivity state
            faa_state = state.get("eeg_faa_state")
            if faa_state and faa_state not in ("insufficient_data", None):
                eeg += f"  faa={state.get('eeg_faa', 0):.2f}({faa_state})"
            # Freq leader status
            fl_phase = state.get("freq_lead_phase")
            if fl_phase and fl_phase != "inactive":
                eeg += (
                    f"\n  FreqLead: phase={fl_phase}"
                    f"  current={state.get('freq_lead_current', '?')}Hz"
                    f"  target={state.get('freq_lead_target', '?')}Hz"
                    f"  steps={state.get('freq_lead_steps', 0)}"
                    f"  holds={state.get('freq_lead_holds', 0)}"
                )
            # Warn when SQI is degraded
            if conf in ("low", "none"):
                eeg += f"  ⚠ SQI={conf.upper()} — treat metrics with caution"
            # Warn when IAF calibration confidence is marginal
            iaf_conf = self._profile.get("iaf_confidence")
            if iaf_conf is not None and float(iaf_conf) < 0.50:
                eeg += f"  ⚠ IAF cal_conf={iaf_conf:.2f} — band boundaries are estimates only"
            # Conductor FSM — full assessment when EEG is available
            if self._conductor is not None:
                ca = self._conductor.assessment()
                owned = sorted(CONDUCTOR_OWNED_PARAMS)
                ts_s = (
                    f"  trance={ca['trance_score']:.2f}"
                    if ca.get("trance_score") is not None
                    else ""
                )
                assr_s = ""
                if ca.get("assr_confidence"):
                    assr_s = f"  assr={ca['assr_confidence']}({ca.get('assr_strength', 0.0):.2f})"
                tf_s = (
                    f"  target={ca['target_freq_hz']:.1f}Hz"
                    if ca.get("target_freq_hz")
                    else ""
                )
                trend_s = ""
                if ca.get("trance_trend_per_min") is not None:
                    direction = (
                        "↑"
                        if ca["trance_trend_per_min"] > 0.01
                        else "↓"
                        if ca["trance_trend_per_min"] < -0.01
                        else "→"
                    )
                    trend_s = (
                        f"  trend={direction}{abs(ca['trance_trend_per_min']):.3f}/min"
                    )
                eeg += (
                    f"\n  Conductor arc: {ca.get('phase_arc', ca['phase'])}"
                    f"\n  Conductor: phase={ca['phase']}({ca.get('phase_duration_s', 0)}s)"
                    f"  frac={ca['frac_count']}/{ca['frac_max']}"
                    f"{ts_s}{trend_s}{assr_s}{tf_s}"
                    f"\n  Advance gate: {ca['advance_gate']}"
                    f"\n  ⚠ Conductor owns {owned} — suppressed from adjustments. Do NOT include them."
                )
                if ca.get("timer_mode"):
                    eeg += "  ⚠ TIMER_MODE (EEG unavailable)"
                cal_s = _format_calibration_context(ca.get("calibration") or {})
                if cal_s:
                    eeg += f"\n{cal_s}"
            # Semantic selector state (Bible Ch.6 §6.6)
            if self._selector is not None:
                sel = self._selector.get_state_summary()
                if sel.get("active_pool"):
                    transitions = sel.get("recent_transitions", [])
                    t_str = ""
                    if transitions:
                        last = transitions[-1]
                        t_str = (
                            f"  last_transition={last.get('from_pool', '?')}"
                            f"→{last.get('to_pool', '?')}"
                            f"(faa={last.get('faa', 0):.2f}"
                            f",trance={last.get('trance', 0):.2f})"
                        )
                    eeg += (
                        f"\n  Semantic pool: {sel['active_pool']}"
                        f"  dwell={sel['pool_dwell_s']}s"
                        f"  cascades={sel['cascade_count']}"
                        f"  shadows_recent={sel['shadows_history']}"
                        f"{t_str}"
                    )
            # Bible Ch.2 §2.9 §9 — autonomic + IMU + converged depth context
            ppg_available = state.get("ppg_available", False)
            if ppg_available:
                ppg_hr = state.get("ppg_heart_rate")
                ppg_rmssd = state.get("ppg_hrv_rmssd")
                auto_depth = state.get("ppg_autonomic_depth")
                auto_cal = state.get("ppg_autonomic_calibrated", False)
                eeg += f"\n  PPG: hr={ppg_hr} bpm  rmssd={ppg_rmssd} ms"
                if auto_cal and auto_depth is not None:
                    eeg += f"  autonomic_depth={auto_depth:.2f}"
                else:
                    eeg += "  autonomic_depth=calibrating"
            stillness = state.get("imu_stillness_index")
            head_nod = state.get("imu_head_nod_detected", False)
            if stillness is not None:
                eeg += f"\n  IMU: stillness={stillness:.2f}"
                if head_nod:
                    eeg += "  ⚠ head_nod_detected"
            depth_est = state.get("depth_estimate")
            depth_conf = state.get("depth_confidence")
            if depth_est is not None and depth_conf is not None:
                eeg += f"\n  Converged depth: {depth_est:.2f}  confidence={depth_conf}"
            return base + eeg + trend
        # Even without EEG, show Conductor phase and its real-time assessment
        if self._conductor is not None:
            ca = self._conductor.assessment()
            owned = sorted(CONDUCTOR_OWNED_PARAMS)
            tf_s = (
                f"  target={ca['target_freq_hz']:.1f}Hz"
                if ca.get("target_freq_hz")
                else ""
            )
            base += (
                f"\nConductor arc: {ca.get('phase_arc', ca['phase'])}"
                f"\nConductor: phase={ca['phase']}({ca.get('phase_duration_s', 0)}s)"
                f"  frac={ca['frac_count']}/{ca['frac_max']}"
                f"{tf_s}"
                f"\n  Advance gate: {ca['advance_gate']}"
                f"\n  ⚠ Conductor owns {owned} — these are suppressed from adjustments."
                f" Do NOT include them."
            )
            if ca.get("timer_mode"):
                base += "  ⚠ TIMER_MODE (EEG unavailable)"
            cal_s = _format_calibration_context(ca.get("calibration") or {})
            if cal_s:
                base += f"\n{cal_s}"
        # GENUS 40 Hz protocol status (genus_protocol.md)
        if state.get("genus_active"):
            elapsed_s = state.get("genus_session_elapsed_s", 0)
            remaining_s = state.get("genus_session_remaining_s", 3600)
            ratio = state.get("eeg_genus_ratio", 1.0)
            level = state.get("genus_entrainment_level", "unknown")
            verified = state.get("genus_entrainment_verified", False)
            base += (
                f"\nGENUS active: elapsed={elapsed_s:.0f}s  remaining={remaining_s:.0f}s"
                f"  entrainment_ratio={ratio:.2f}  level={level}  verified={verified}"
                f"\n  ⚠ GENUS mode: your primary role is COGNITIVE ENGAGEMENT."
                f" Ask memory questions, present visual attention tasks, inject"
                f" affirmations. Engagement enhances entrainment (Mlinarič 2025)."
                f" Keep responses interactive — no passive staring."
            )
        return base + trend

    def _history_summary(self) -> str:
        if not self._history:
            return "No exchanges yet this session."
        lines = []
        for ex in self._history[-self._cfg.max_history :]:
            t = time.strftime("%H:%M:%S", time.localtime(ex.timestamp))
            complexity_note = (
                f"  complexity={ex.complexity_score:.2f}  latency={ex.latency_s:.0f}s"
                if ex.response is not None
                else ""
            )
            lines.append(
                f"[{t}] state={ex.beat_hz:.1f}Hz/{ex.spiral_style} "
                f"prompt={ex.prompt!r} response={ex.response!r}"
                f"{complexity_note} adjusted={list(ex.adjustments.keys())}"
            )
        return "\n".join(lines)

    def _call_llm(
        self,
        state: dict,
        prompt: str | None,
        response: str | None,
        extra_instruction: str | None = None,
    ) -> dict:
        """Build context and call the LLM. Returns parsed JSON dict."""
        # These two counts are INDEPENDENT — never add them together.
        # skipped_questions = turns where YOU sent needs_response:true and got no reply.
        # silent_turns      = turns where YOU sent no question at all (display-only or nothing).
        streak_ctx = (
            f"  [skipped_questions={self._skip_streak} (user ignored YOUR direct prompts);"
            f" silent_turns={self._silent_turns} (turns YOU did not ask — NOT user skips);"
            f" WARNING: do not add these together — they measure different things]"
        )
        if self._cfg.mode == "interactive" and self._skip_streak < 3:
            mode_hint = (
                "Mode: INTERACTIVE — you may ask a question via next_prompt."
                + streak_ctx
            )
        else:
            mode_hint = (
                "Mode: OBSERVE — user skipped your last questions; "
                "deepen silently, do NOT send needs_response:true." + streak_ctx
            )

        lib_ctx = (
            f"\nImage library: {self._image_library_summary}\n"
            if self._image_library_summary
            else ""
        )
        user_msg = (
            f"{mode_hint}\n\n"
            f"User profile:\n{self._profile_context()}\n\n"
            f"Current session state:\n{self._state_summary(state)}{lib_ctx}\n\n"
            f"Exchange history (newest last):\n{self._history_summary()}\n\n"
        )
        if prompt and response is not None:
            user_msg += (
                f"You just asked: {prompt!r}\n"
                f"User responded: {response!r}\n\n"
                f"Now act. Consider what serves this moment: deepen the state, "
                f"shift the experience, plant an affirmation, stay silent, "
                f"or speak — whatever belongs here. A question is one option, "
                f"not the default."
            )
        elif prompt and response is None:
            user_msg += (
                f"You asked: {prompt!r}\n"
                f"User skipped the question (no response). "
                f"Proceed without that information."
            )
        else:
            user_msg += "No prompt was sent this cycle. Evaluate state and decide whether to adjust."

        if extra_instruction:
            user_msg += f"\n\n{extra_instruction}"

        messages = [
            {"role": "system", "content": _build_system_prompt(self._cfg)},
            {"role": "user", "content": user_msg},
        ]

        # ── External agent channel (Phase 3 MCP bridge) ──────────────────────
        if self._ext_client and self._ext_client.connected:
            full_prompt = f"[SYSTEM]\n{messages[0]['content']}\n\n[USER]\n{user_msg}"
            ext_result = self._ext_client.request(
                prompt=full_prompt,
                system_prompt=messages[0]["content"],
                max_tokens=4096,
            )
            if ext_result and ext_result.get("type") == "response":
                raw = ext_result.get("text", "")
                try:
                    ack = json.loads(raw) if raw else {}
                    if isinstance(ack, dict) and ack.get("status") == "delivered":
                        print(
                            "[Agent] External channel delivered — async effects via MCP tools"
                        )
                        return {}
                except (json.JSONDecodeError, ValueError):
                    pass
                print(f"[Agent] External channel response ({len(raw)} chars)")
                parsed = _extract_json(raw)
                if parsed:
                    pu = parsed.get("profile_updates")
                    if isinstance(pu, dict) and any(pu.values()):
                        try:
                            self._update_profile(pu)
                        except Exception:
                            pass
                    return parsed
                print(
                    f"[Agent] External response not valid JSON, falling back to local LLM"
                )
            else:
                if ext_result:
                    print(
                        f"[Agent] External channel error: {ext_result.get('error', 'unknown')}"
                    )
                print("[Agent] External channel failed, falling back to local LLM")
                # Try reconnecting
                if not self._ext_client.connect():
                    self._ext_client = None

        raw = self._llm.chat(messages)
        parsed = _extract_json(raw)
        if not parsed:
            print(f"[Agent] LLM returned non-JSON: {raw[:200]}")
            return parsed

        # ── Handle tool_call ──────────────────────────────────────────────────
        tc = parsed.get("tool_call")
        if isinstance(tc, dict) and tc.get("tool"):
            tool_name = tc["tool"]
            tool_args = tc.get("args") or {}
            print(f"[Agent] Tool call requested: {tool_name}({tool_args})")
            try:
                if tool_name == "reinforce_response":
                    response_text = tool_args.get("response", "")
                    if response_text:
                        self._reinforce_response(response_text)
                    tool_result = {"status": "ok", "reinforced": bool(response_text)}
                else:
                    from content_tools import dispatch

                    tool_result = dispatch(tool_name, tool_args)
                result_json = json.dumps(tool_result, indent=2)[:2000]
                print(f"[Agent] Tool result ({tool_name}): {result_json[:200]}…")
                # Re-call with result injected as an assistant/user exchange
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Tool result for {tool_name}:\n{result_json}\n\n"
                            "Now continue. Output your final JSON decision. "
                            "Do NOT include another tool_call."
                        ),
                    }
                )
                raw2 = self._llm.chat(messages)
                parsed2 = _extract_json(raw2)
                if parsed2:
                    parsed = parsed2
            except Exception as tc_exc:
                print(f"[Agent] Tool call error ({tool_name}): {tc_exc}")

        # ── Handle profile_updates ────────────────────────────────────────────
        pu = parsed.get("profile_updates") if parsed else None
        if isinstance(pu, dict) and any(pu.values()):
            try:
                self._update_profile(pu)
                print(f"[Agent] Profile updated: {list(pu.keys())}")
            except Exception as pu_exc:
                print(f"[Agent] Profile update error: {pu_exc}")

        return parsed

    def _apply(self, result: dict) -> dict:
        """Validate and apply adjustments from the LLM response.

        Parameters with a matching entry in ``result["transitions"]`` are handed
        to the RampEngine (background thread writes 1 s steps).  All other
        parameters are written immediately.
        """
        adj = result.get("adjustments") or {}
        if not isinstance(adj, dict):
            return {}
        safe = {k: v for k, v in adj.items() if k in _ADJUSTABLE_PARAMS}

        # When the Conductor is active it is the sole writer of structural params.
        # Let the LLM keep speech-adjacent keys (tts_enabled, tts_subliminal,
        # volume, audio_muted) but strip anything the Conductor owns.
        if self._conductor is not None and self._conductor.phase.value != "session_end":
            stripped = {k for k in safe if k in CONDUCTOR_OWNED_PARAMS}
            # Hardware params are owned by Conductor when devices are connected
            live = self._read_live()
            hw = set(live.get("hardware_channels_connected") or [])
            if "haptic" in hw:
                stripped |= {k for k in safe if k in HAPTIC_OWNED_WHEN_CONNECTED}
            if "tavns" in hw:
                stripped |= {k for k in safe if k in TAVNS_OWNED_WHEN_CONNECTED}
            if stripped:
                print(
                    f"[Agent] Conductor active — suppressing LLM adjustments: {stripped}"
                )
            safe = {k: v for k, v in safe.items() if k not in stripped}

        # When the freq_leader owns beat_frequency (lead/hold/sustain phases),
        # strip it from adjustments so the LLM and RampEngine don't fight it.
        if self._freq_leader is not None and self._freq_leader.is_alive():
            fl_phase = self._freq_leader.state.phase.value
            if fl_phase in ("lead", "hold", "sustain") and "beat_frequency" in safe:
                print(
                    f"[Agent] FreqLeader active ({fl_phase}) — suppressing beat_frequency adjustment"
                )
                safe.pop("beat_frequency")

        transitions = result.get("transitions") or {}
        ramped_keys: set[str] = set()

        if isinstance(transitions, dict) and safe:
            state = self._read_live()
            for key, duration_s in transitions.items():
                if (
                    key in safe
                    and isinstance(duration_s, (int, float))
                    and duration_s > 0
                ):
                    current_val = state.get(key)
                    target_val = safe[key]
                    if isinstance(current_val, (int, float)) and isinstance(
                        target_val, (int, float)
                    ):
                        if abs(float(current_val) - float(target_val)) < 0.01:
                            # Already at the target — skip to avoid spurious logs
                            # and unnecessary timer overhead.
                            ramped_keys.add(key)
                            continue
                        self._ramp.start(
                            key,
                            current=float(current_val),
                            target=float(target_val),
                            duration_s=float(duration_s),
                        )
                        ramped_keys.add(key)
                        print(
                            f"[Agent] Ramp: {key} "
                            f"{current_val:.2f}→{target_val:.2f} "
                            f"over {duration_s:.0f}s"
                        )

        immediate = {k: v for k, v in safe.items() if k not in ramped_keys}
        if immediate:
            self._write_live(immediate)
            print(f"[Agent] Adjusted: {immediate}")

        reasoning = result.get("reasoning", "")
        if reasoning:
            print(f"[Agent] Reasoning: {reasoning}")

        # Autonomous fractionation trigger
        if result.get("action") == "fractionate":
            live = self._read_live()
            if not live.get("fractionation_active"):
                self._write_live({"_timeline_cmd": "fractionate"})
                print("[Agent] Triggered fractionation (autonomous).")

        return safe

    # ── Affirmation injection ─────────────────────────────────────────────────

    def _inject_affirmation(self, phrase: str, state: dict) -> None:
        """Inject a single LLM-generated phrase into the live affirmation pool.

        Persists to the session's affirmations.txt (so it survives restart) then
        appends to live_control.json affirmations_pool for immediate display effect.
        Since affirmations_pool is no longer in _ADJUSTABLE_PARAMS, the LLM
        cannot clobber it via adjustments — this append is always additive.
        """
        phrase = phrase.strip().rstrip(".,!?;:")
        if not phrase:
            return

        session = state.get("session_folder", "live")
        tag = state.get("timeline_label") or "general"

        # Persist to session file
        try:
            from content_tools.affirmations import write_affirmations

            write_affirmations(session, tag, [phrase], mode="append")
        except Exception as e:
            print(f"[Agent] Affirmation persist error: {e}")

        # Append to live pool for immediate effect.
        # If affirmations_pool is not yet set, seed from the session file
        # so the injection is genuinely additive rather than replacing everything.
        try:
            live = self._read_live()
            pool = list(live.get("affirmations_pool") or [])
            if not pool:
                try:
                    from layers.phrase_pool import _load_file

                    loaded = _load_file(session)
                    pool = [p for p in loaded if isinstance(p, str)]
                except Exception:
                    pass
            if phrase not in pool:
                pool.append(phrase)
                live["affirmations_pool"] = pool

            # VR subliminal: if VR headset is active, also inject into depth-plane pools.
            # Route: far → mid → far → mid → near (4:4:1 ratio to respect VAC limits).
            if live.get("vr_headset_active"):
                _inject_count = live.get("_vr_subliminal_inject_count", 0)
                plane = (
                    "near"
                    if _inject_count % 9 == 8
                    else ("mid" if _inject_count % 2 else "far")
                )
                pool_key = f"vr_subliminal_{plane}_pool"
                vr_pool = list(live.get(pool_key) or [])
                if phrase not in vr_pool:
                    vr_pool.append(phrase)
                    if len(vr_pool) > 30:
                        vr_pool = vr_pool[-30:]
                patch_live(
                    {
                        "affirmations_pool": pool,
                        pool_key: vr_pool,
                        "_vr_subliminal_inject_count": _inject_count + 1,
                    }
                )
                print(f"[Agent] Injected affirmation (VR plane={plane}): {phrase!r}")
            else:
                patch_live({"affirmations_pool": pool})
                print(
                    f"[Agent] Injected affirmation: {phrase!r} "
                    f"(pool now {len(pool)} phrases)"
                )
        except Exception as e:
            print(f"[Agent] Affirmation inject error: {e}")

        # Notify conditioning engine of this delivery
        if self._conditioning is not None and phrase != self._last_delivered_phrase:
            try:
                live = self._read_live()
                ns = (
                    NeuralStateFingerprint.from_live(live)
                    if _CONDITIONING_AVAILABLE
                    else None
                )
                if ns is not None:
                    self._conditioning.on_delivery(
                        cs_class="affirmation",
                        cs_identity=phrase,
                        cs_pool=state.get("timeline_label") or "general",
                        neural_state=ns,
                        delivery_gate={},
                        conductor_phase=str(live.get("conductor_phase") or ""),
                        cardiac_phase=float(live.get("ppg_cardiac_phase") or 0.0),
                        respiratory_phase=float(live.get("respiratory_phase") or 0.0),
                        us_magnitude=float(live.get("eeg_trance_score_v2") or 0.0),
                    )
                    self._last_delivered_phrase = phrase
            except Exception:
                pass

    # ── Observe tick (no user interaction) ───────────────────────────────────

    def _observe_tick(self, state: dict) -> None:
        result = self._call_llm(state, prompt=None, response=None)
        adj = self._apply(result)
        self._record(state, prompt=None, response=None, adj=adj)

    # ── Interactive tick ──────────────────────────────────────────────────────

    # Dwell seconds for display-only messages (needs_response=false)
    _DISPLAY_DWELL: dict[str, float] = {
        "slow": 30.0,
        "normal": 15.0,
        "fast": 7.0,
        "static": 10.0,
    }

    def _edison_tick(self, state: dict) -> None:
        """Edison Mode tick — minimal agent involvement during state-driven cycles.

        The Conductor + EdisonModeManager handle all state transitions, N1 detection,
        and wake cue delivery. The agent's only jobs:
        1. During CYCLE_COMPLETE: offer follow-up questions and cycle choice
        2. During CAPTURE: passively observe (the manager already delivered the wake cue)
        3. During PREPARATION/SEED/MONITORING/N1_HOLD: stay silent
        """
        edison_state = state.get("edison_state", "")
        cycle_count = int(state.get("edison_cycle_count", 0))
        max_cycles = 5  # default; manager enforces actual limit

        if edison_state == "CYCLE_COMPLETE":
            instruction = (
                f"EDISON MODE — cycle {cycle_count} complete.\n"
                "The user just returned from a hypnagogic state and gave a report. "
                "Briefly acknowledge what they shared (1-2 sentences), then ask if "
                "they want another cycle. Offer a continue/end choice. "
                "Write edison_continue or edison_end_session to live_control.json "
                "based on their response. Keep voice warm and unhurried."
            )
            result = self._call_llm(
                state, prompt=None, response=None, extra_instruction=instruction
            )
            if result:
                adj = self._apply(result)
                self._record(state, prompt=None, response=None, adj=adj)

    def _ssild_tick(self, state: dict) -> None:
        """SSILD tick — minimal agent involvement during TTS-guided cycles.

        The Conductor + SSILDEngine handle all phase transitions, cycle
        counting, and TTS prompt delivery. The agent only acts during
        DREAM_JOURNAL to collect the morning report.
        """
        ssild_phase = state.get("ssild_phase", "")

        if ssild_phase == "DREAM_JOURNAL":
            response = state.get("user_response")
            if response:
                instruction = (
                    f"SSILD DREAM JOURNAL — the user just woke up and shared: '{response}'\n"
                    "Acknowledge their report warmly. Ask one brief follow-up: "
                    "did they notice any cues during the night? Then thank them "
                    "and wish them a good day. Keep it short."
                )
                result = self._call_llm(
                    state, prompt=response, response=None, extra_instruction=instruction
                )
                if result:
                    adj = self._apply(result)
                    self._record(state, prompt=None, response=response, adj=adj)

    def _deep_window_tick(self, state: dict, cycle_n: int) -> None:
        """Fractionation DEEP phase — therapeutic window tick.

        The user is at maximum accessible depth for this cycle. No questions,
        no dialogs. Deliver affirmations and a single subdued suggestion via
        TTS only, then let the silence work.
        """
        instruction = (
            f"FRACTIONATION DEEP WINDOW — cycle {cycle_n}.\n"
            "The user is at the deepest accessible state of this cycle. "
            "This is the therapeutic window. Your only job right now:\n"
            "1. Set next_affirmation to a single direct 3-7 word phrase that "
            "plants the core suggestion for this session (no terminal punctuation).\n"
            "2. Optionally set next_prompt to ONE short, declarative sentence "
            "(not a question) delivered as a quiet statement of fact — e.g. "
            "'You are open and receptive.' Set needs_response: false.\n"
            "3. Do NOT ask questions. Do NOT set needs_response: true.\n"
            "4. Do NOT trigger fractionation again (it is already active).\n"
            "Use voice_mode: 'tts' at low intensity. Stay silent if the exchange "
            "history shows the user is at depth — trust the state, not the words."
        )
        result = self._call_llm(
            state, prompt=None, response=None, extra_instruction=instruction
        )
        if not result:
            return

        # Force no-response regardless of what the LLM decided
        style = result.get("prompt_style") or {}
        style["needs_response"] = False
        style.setdefault("voice_mode", "tts")
        style.setdefault("intensity", "soft")
        style.setdefault("zoom_speed", "slow")

        # Apply parameter adjustments
        adj = self._apply(result)

        # Deliver affirmation
        aff = result.get("next_affirmation")
        if aff:
            self._inject_affirmation(aff, state)
            print(f"[Agent] Deep-window affirmation: {aff!r}")

        # Deliver suggestion (display + TTS, no dialog)
        msg = result.get("next_prompt")
        if msg:
            speak = style.get("voice_mode") in ("tts", "both", "subliminal")
            tts_dur = max(3.0, len(msg) * 0.070)
            self._say(
                msg,
                needs_response=False,
                overlay=True,
                console=True,
                tts=speak,
                style=style,
                timeout_s=tts_dur,
            )
            print(f"[Agent] Deep-window message: {msg!r}")
            time.sleep(tts_dur + 1.0)
            self._clear_message()

        self._record(state, prompt=msg, response=None, adj=adj, affirmation=aff)

    def _interactive_tick(self, state: dict) -> None:
        # ── Session Zero calibration-in-disguise ──────────────────────────────────
        if self._sz_active:
            self._session_zero_tick(state)
            if self._sz_active:
                return

        # ── Conductor FSM tick (Bible Ch.6 §6.5) ───────────────────────────────────────
        if self._conductor is not None:
            tick_rate = self._conductor.get_tick_rate() or 10
            if time.time() - self._conductor_last_tick >= tick_rate:
                try:
                    self._conductor.tick()
                    self._conductor_last_tick = time.time()
                    # Expose Conductor phase summary in live state for agent context
                    csum = self._conductor.summary()
                    self._write_live({"conductor_summary": csum})
                except Exception as e:
                    print(f"[Agent] Conductor tick error: {e}")

        # ── Sleep planning tick (Bible Ch.9 §9.1) ─────────────────────────────────────
        if (
            self._conductor is not None
            and getattr(self._conductor, "session_type", "") == "sleep"
            and self._conductor.phase.value == "sleep_maintain"
        ):
            self._sleep_planning_tick(state)

        # ── Reconsolidation sequence tick (30 s cadence) ──────────────────────────────
        if self._recon is not None:
            _now_rt = time.time()
            if _now_rt - self._recon_last_tick >= 30.0:
                try:
                    self._recon_tick(state)
                except Exception as _rte:
                    print(f"[Agent] Recon tick error: {_rte}")
                self._recon_last_tick = _now_rt

        # ── Somatic palette chord tick (30 s cadence) ──────────────────────────────────
        _now_pt = time.time()
        if _now_pt - self._palette_chord_last_tick >= 30.0:
            try:
                self._palette_chord_tick(state)
            except Exception as _pte:
                print(f"[Agent] Palette tick error: {_pte}")
            self._palette_chord_last_tick = _now_pt

        # ── Habituation Engine tick (Bible Ch.10 §10.3, ~1 Hz) ───────────────────────────
        if self._habituation is not None:
            now_ht = time.time()
            if now_ht - self._habituation_last_tick >= 1.0:
                try:
                    patch = self._habituation.tick()
                    if patch:
                        self._write_live(patch)
                    self._habituation_last_tick = now_ht
                except Exception as _hte:
                    pass  # non-critical

        # ── Session Director tick (Bible Ch.5 §5.5, ~1 Hz) ────────────────────────────
        if self._director is not None:
            now_dt = time.time()
            if now_dt - self._director_last_tick >= 1.0:
                try:
                    director_state = {
                        "trance_score_v2": float(
                            state.get("trance_score_v2", 0.0) or 0.0
                        ),
                        "autonomic_depth": float(
                            state.get("autonomic_depth", 0.0) or 0.0
                        ),
                        "stillness_index": float(
                            state.get("imu_stillness_index", 1.0) or 1.0
                        ),
                        "heart_rate": float(state.get("ppg_heart_rate", 0.0) or 0.0),
                        "heart_rate_baseline": float(
                            state.get("ppg_heart_rate_baseline", 0.0) or 0.0
                        ),
                        "eeg_signal_lost": not bool(state.get("eeg_connected", False)),
                        "imu_motion_contaminated": bool(
                            state.get("imu_motion_contaminated", False)
                        ),
                        "avg_crossmodal_gain": float(
                            state.get(
                                "avg_crossmodal_gain", state.get("volume", 50.0) / 100.0
                            )
                            or 0.5
                        ),
                        "content_semantic_density": float(
                            state.get("content_semantic_density", 0.3) or 0.3
                        ),
                        "entrainment_aggressiveness": float(
                            state.get("entrainment_aggressiveness", 0.3) or 0.3
                        ),
                        "novelty_level": float(state.get("novelty_level", 0.3) or 0.3),
                        "tts_prosodic_intensity": float(
                            state.get("tts_prosodic_intensity", 0.3) or 0.3
                        ),
                        "conditioning_response": float(
                            state.get("conditioning_response", 0.0) or 0.0
                        ),
                        "hrv_cv": float(state.get("ppg_hrv_rmssd", 0.0) or 0.0) / 100.0,
                    }
                    patches = self._director.tick(director_state)
                    if patches:
                        # Director patches respect user-lock; filter locked params
                        locked = set(state.get("timeline_locked_params") or [])
                        patches = {k: v for k, v in patches.items() if k not in locked}
                        self._write_live(patches)
                    self._director_last_tick = now_dt
                except Exception as _dte:
                    pass  # non-critical

        # ── Semantic selector tick (Bible Ch.6 §6.6) ──────────────────────────────────
        # Runs every tick (selector has its own CASCADE_COOLDOWN_S guard).
        # Lazy-instantiate on first active tick so session_folder is known.
        if _SELECTOR_AVAILABLE:
            if self._selector is None:
                session_name = state.get("session_folder")
                weights = {}
                try:
                    weights = get_pool_weights()
                except Exception:
                    pass
                self._selector = SemanticSelector(
                    session_name=session_name,
                    pool_weights=weights or {},
                )
                eeg_on = bool(state.get("eeg_connected"))
                self._write_live(
                    {
                        "semantic_selector_enabled": eeg_on,
                    }
                )
                print(
                    f"[Agent] SemanticSelector initialised — "
                    f"session={session_name!r}  eeg={eeg_on}"
                )
            try:
                self._selector.tick(state)
            except Exception as e:
                print(f"[Agent] SemanticSelector tick error: {e}")

        # Route to GENUS cognitive engagement mode when 40 Hz protocol is active
        if state.get("genus_active"):
            self._genus_engagement_tick(state)
            return

        # Route to Edison Mode handler — state-driven, no free-form LLM (Bible Ch.7 §29)
        edison_state = state.get("edison_state")
        if edison_state and edison_state != "SESSION_END":
            self._edison_tick(state)
            return

        # Route to SSILD handler — cycle-guided TTS + REM monitoring (Bible Ch.7 §§30-31)
        ssild_phase = state.get("ssild_phase")
        if ssild_phase and ssild_phase not in ("COMPLETE", ""):
            self._ssild_tick(state)
            return

        # Route to the dedicated DEEP-window handler during fractionation
        frac_phase = (state.get("fractionation_phase") or "").upper()
        if frac_phase.startswith("DEEP") and state.get("fractionation_active"):
            cycle_n = int(frac_phase.split("_")[-1]) if "_" in frac_phase else 1
            self._deep_window_tick(state, cycle_n)
            return

        # First call LLM with no response yet to decide if it wants to ask
        probe = self._call_llm(state, prompt=None, response=None)
        question = probe.get("next_prompt")
        # Normalize: treat the literal string "None" / "none" / empty as absent.
        if isinstance(question, str):
            question = question.strip()
            if not question or question.lower() == "none":
                question = None
        style = probe.get("prompt_style") or {}

        if question:
            # Always apply adjustments + transitions from the probe
            if probe.get("adjustments"):
                self._apply(probe)

            needs_response = style.get("needs_response", True)

            voice_mode = style.get("voice_mode", "tts")
            speak = voice_mode in ("tts", "subliminal", "both")

            if needs_response:
                # ── Standard interactive path ────────────────────────────────
                print(f"[Agent] Prompting user: {question!r}")
                self._prompt_sent_at = time.time()
                self._silent_turns = 0
                # _say with needs_response=True writes agent_message,
                # clears user_response, and blocks until the user replies / times out.
                response = self._say(
                    question,
                    needs_response=True,
                    overlay=True,
                    console=True,
                    tts=speak,
                    style=style,
                    timeout_s=float(self._cfg.prompt_timeout),
                )
                print(f"[Agent] Response: {response!r}")
                self._clear_message()

                if response is None:
                    self._skip_streak += 1
                else:
                    self._skip_streak = 0

                result = self._call_llm(state, prompt=question, response=response)
                adj = self._apply(result)
                self._record(state, prompt=question, response=response, adj=adj)

            else:
                # ── Display-only path (no dialog, no response waited on) ─────
                print(f"[Agent] Display message (no response): {question!r}")

                if speak:
                    # Tie the overlay lifetime to estimated TTS playback (~70 ms/char)
                    tts_dur = max(3.0, len(question) * 0.070)
                    timeout_s = tts_dur
                    dwell = tts_dur + 1.0
                else:
                    # Visual-only: user needs time to read
                    timeout_s = None
                    dwell = self._DISPLAY_DWELL.get(
                        style.get("zoom_speed", "normal"), 15.0
                    )

                self._say(
                    question,
                    needs_response=False,
                    overlay=True,
                    console=True,
                    tts=speak,
                    style=style,
                    timeout_s=timeout_s,
                )
                self._silent_turns += 1

                time.sleep(dwell)
                self._clear_message()

                adj = self._apply(probe) if not probe.get("adjustments") else {}
                self._record(state, prompt=question, response=None, adj=adj)
        else:
            # LLM decided not to ask — adapt silently; track for context clarity
            self._silent_turns += 1
            adj = self._apply(probe)
            aff = probe.get("next_affirmation")
            if aff:
                self._inject_affirmation(aff, state)
            self._record(state, prompt=None, response=None, adj=adj, affirmation=aff)

    def _genus_engagement_tick(self, state: dict) -> None:
        """
        GENUS cognitive engagement mode (genus_protocol.md §5.4).

        During a GENUS session the agent's primary role shifts from depth guidance
        to keeping the user cognitively engaged.  Mlinarič et al. (2025) showed
        that active cognitive participation during 40 Hz stimulation enhances both
        the strength and spatial extent of neural entrainment, including the
        hippocampus.

        Strategy: ask simple memory-retrieval or attention questions, inject
        affirmations, and report entrainment status.  No depth adjustment, no
        sleep-fork logic — the Conductor owns the beat at 40 Hz.
        """
        elapsed_s = float(state.get("genus_session_elapsed_s", 0) or 0)
        remaining_s = float(state.get("genus_session_remaining_s", 3600) or 3600)
        level = state.get("genus_entrainment_level", "absent")

        # Announce start of GENUS block once
        if not getattr(self, "_genus_greeted", False):
            self._genus_greeted = True
            elapsed_min = int(elapsed_s // 60)
            remaining_min = int(remaining_s // 60)
            msg = (
                f"GENUS protocol active — {remaining_min} minutes remaining. "
                f"Entrainment: {level}. "
                "Stay awake and engaged — your attention enhances the effect."
            )
            self._say(
                msg,
                needs_response=False,
                overlay=True,
                console=True,
                tts=True,
                style={"voice_mode": "tts", "needs_response": False},
            )
            return

        # After first announce, run normal LLM tick with GENUS-specific instruction
        # injected so the model knows to prioritize engagement over depth guidance.
        # The GENUS context is already in _state_summary; just run the standard path.
        probe = self._call_llm(state, prompt=None, response=None)
        question = probe.get("next_prompt")
        if isinstance(question, str):
            question = question.strip()
            if not question or question.lower() == "none":
                question = None
        style = probe.get("prompt_style") or {}

        if question:
            needs_response = style.get("needs_response", True)
            voice_mode = style.get("voice_mode", "tts")
            speak = voice_mode in ("tts", "subliminal", "both")

            if needs_response:
                self._prompt_sent_at = time.time()
                self._silent_turns = 0
                response = self._say(
                    question,
                    needs_response=True,
                    overlay=True,
                    console=True,
                    tts=speak,
                    style=style,
                    timeout_s=float(self._cfg.prompt_timeout),
                )
                self._clear_message()
                if response is None:
                    self._skip_streak += 1
                else:
                    self._skip_streak = 0
                result = self._call_llm(state, prompt=question, response=response)
                adj = self._apply(result)
                self._record(state, prompt=question, response=response, adj=adj)
            else:
                tts_dur = max(3.0, len(question) * 0.070) if speak else 0
                self._say(
                    question,
                    needs_response=False,
                    overlay=True,
                    console=True,
                    tts=speak,
                    style=style,
                    timeout_s=tts_dur if speak else None,
                )
                self._silent_turns += 1
                time.sleep(tts_dur + 1.0 if speak else 5.0)
                self._clear_message()
                adj = self._apply(probe)
                self._record(state, prompt=question, response=None, adj=adj)
        else:
            self._silent_turns += 1
            adj = self._apply(probe)
            aff = probe.get("next_affirmation")
            if aff:
                self._inject_affirmation(aff, state)
            self._record(state, prompt=None, response=None, adj=adj, affirmation=aff)

    # ── History & logging ─────────────────────────────────────────────────────

    def _record(
        self,
        state: dict,
        prompt: str | None,
        response: str | None,
        adj: dict,
        affirmation: str | None = None,
    ) -> None:
        complexity = self._score_complexity(response) if response else 1.0
        latency = (
            time.time() - self._prompt_sent_at
            if self._prompt_sent_at and response is not None
            else 0.0
        )
        self._prompt_sent_at = None

        ex = Exchange(
            timestamp=time.time(),
            session_time=float(state.get("session_time", 0)),
            session_name=str(
                state.get("timeline_label", state.get("session_folder", "unknown"))
            ),
            beat_hz=float(state.get("beat_frequency", 10)),
            spiral_style=str(state.get("spiral_style", "")),
            prompt=prompt,
            response=response,
            adjustments=adj,
            complexity_score=complexity,
            latency_s=round(latency, 1),
        )
        print(f"[Agent] Recorded — complexity={complexity:.2f}  latency={latency:.0f}s")

        # Track last injected affirmation for effective-moment logging
        if affirmation:
            self._last_affirmation = affirmation

        # Session-level accumulators
        self._accumulate_session_stats(ex, affirmation)

        # Effective moment: complexity drop to near-silent signals deep trance
        if response is not None and complexity < 0.2:
            self._record_effective_moment(ex)

        self._history.append(ex)
        if len(self._history) > self._cfg.max_history * 2:
            self._history = self._history[-self._cfg.max_history :]
        if self._log:
            self._log.append(ex)

    # ── Content needs check ───────────────────────────────────────────────────

    def _check_content_needs(self, state: dict) -> None:
        """Auto-trigger content generation when session content is sparse.

        Checks two conditions:
          1. The active phrases tag has fewer than 10 phrases in affirmations.txt.
          2. The session's images/ folder is empty (no background images).

        If either is true and no generation is in progress, calls
        content_tools directly (no subprocess) to generate content via the
        local LLM.  Uses SOMNA_LLM_URL / SOMNA_LLM_MODEL env vars.

        This runs at most once per 5-minute window to avoid hammering the LLM.
        """
        now = time.time()
        # Rate-limit: run at most once every 5 minutes
        last_check = getattr(self, "_last_content_check", 0.0)
        if now - last_check < 300.0:
            return
        self._last_content_check = now

        session_name = state.get("session_folder")
        if not session_name:
            return

        # Import lazily so somna_agent works even if content_tools is absent
        try:
            from content_tools.affirmations import count_phrases, list_tags
        except ImportError:
            return  # content_tools not installed — skip silently

        try:
            # Check affirmations
            active_tag = state.get("timeline_label") or "general"
            # Map timeline labels to affirmation tags (best-effort)
            label_to_tag = {
                "c1_orient": "orient",
                "resonant": "relax",
                "threshold": "relax",
                "focus10_entry": "focus10",
                "focus10_hold": "focus10",
                "work_window": "deep",
                "soak": "soak",
                "ascent": "return",
                "return": "return",
            }
            tag = label_to_tag.get(active_tag, active_tag)
            phrase_count = count_phrases(session_name, tag)

            if phrase_count < 10:
                print(
                    f"[Agent] Content check: only {phrase_count} phrases for tag "
                    f"'{tag}' in '{session_name}' — generating more…"
                )
                beat = float(state.get("beat_frequency", 10.0))
                if beat < 5.0:
                    context = (
                        f"Session: {session_name}. Phase tag: {tag}. "
                        f"Beat frequency: {beat:.1f} Hz (deep theta). "
                        "Write short subliminal phrases (1–5 words). "
                        "Present tense, first or second person. No negations."
                    )
                elif beat < 8.0:
                    context = (
                        f"Session: {session_name}. Phase tag: {tag}. "
                        f"Beat frequency: {beat:.1f} Hz (theta/alpha border). "
                        "Write medium-length induction phrases (up to 10 words). "
                        "Somatic, downward metaphors welcome."
                    )
                else:
                    context = (
                        f"Session: {session_name}. Phase tag: {tag}. "
                        f"Beat frequency: {beat:.1f} Hz (alpha). "
                        "Write orienting or grounding phrases (up to 15 words). "
                        "Welcoming, safe, and clear."
                    )
                from content_tools.affirmations import generate_and_append

                # Use this agent's LLM so the user doesn't need a second server.
                # base_url ends in "/v1"; generate_and_append expects the root URL.
                _llm_base = self._cfg.base_url.rstrip("/")
                if _llm_base.endswith("/v1"):
                    _llm_base = _llm_base[:-3]
                result = generate_and_append(
                    session_name,
                    tag=tag,
                    context=context,
                    llm_url=_llm_base,
                    llm_model=self._cfg.model,
                )
                if "error" in result:
                    print(f"[Agent] Content generation error: {result['error']}")
                else:
                    n = result.get("phrases_written", 0)
                    print(f"[Agent] Added {n} phrases to [{tag}] in '{session_name}'.")
                    if n > 0:
                        self._say(
                            f"Added {n} new phrases to the session.",
                            overlay=False,
                            console=True,
                            tts=False,
                        )

            # Check images — use tag stats if available, fall back to list_images
            try:
                from content_tools.image_tags import (
                    tag_stats,
                    images_for_tag,
                    harvest_captions_to_affirmations,
                )
                from content_tools.images import (
                    build_conditioning_prompt,
                    generate_and_tag,
                )

                stats = tag_stats(session_name)
                total_images = stats.get("total", 0)
                tagged_count = stats.get("tagged", 0)

                if total_images == 0:
                    print(
                        f"[Agent] Content check: no images for '{session_name}' — "
                        "run content_agent.py or add images manually."
                    )
                    self._image_library_summary = "no images in session library"
                else:
                    # Build rich summary for the LLM context
                    if tagged_count > 0:
                        top_tags = list(stats.get("tag_counts", {}).items())[:6]
                        top_open_tags = list(stats.get("open_tag_counts", {}).items())[
                            :10
                        ]
                        tag_str = ", ".join(f"{t}:{n}" for t, n in top_tags)
                        open_str = ", ".join(f"{t}:{n}" for t, n in top_open_tags)
                        self._image_library_summary = (
                            f"{total_images} total ({tagged_count} tagged, "
                            f"{stats.get('culled', 0)} culled) — "
                            f"themes: {tag_str}"
                            + (f" | organic: {open_str}" if open_str else "")
                        )
                        print(f"[Agent] Image pool: {self._image_library_summary}")

                    # Log sparse-image advisory but do NOT auto-generate —
                    # image generation (FLUX) is a heavy GPU operation that runs
                    # on the same KoboldCpp server as the LLM.  Triggering it
                    # automatically during a session spikes VRAM and can crash the
                    # host.  Use content_agent.py to generate images offline.
                    active_label = state.get("timeline_label", "").strip()
                    if active_label and tagged_count >= 10:
                        tagged_for_label = images_for_tag(
                            session_name, active_label, exclude_culled=True
                        )
                        if len(tagged_for_label) < 10:
                            print(
                                f"[Agent] Content advisory: only "
                                f"{len(tagged_for_label)} images tagged "
                                f"'{active_label}' in '{session_name}'. "
                                f"Run content_agent.py to generate more."
                            )

                    # Harvest captions from tagged images into affirmations
                    # (runs at most once per check cycle since it's cheap)
                    if tagged_count > 0:
                        harvest_result = harvest_captions_to_affirmations(
                            session_name,
                            tag_filter=active_label if active_label else None,
                        )
                        if harvest_result.get("harvested", 0) > 0:
                            print(
                                f"[Agent] Harvested "
                                f"{harvest_result['harvested']} caption(s) "
                                f"from images → affirmations.txt"
                            )

            except ImportError:
                # image_tags not available — log an advisory, skip gracefully
                print(
                    f"[Agent] Content check: image_tags unavailable for '{session_name}'. "
                    "Run content_agent.py to generate and tag backgrounds."
                )
            except Exception as img_exc:
                print(f"[Agent] Image content check error: {img_exc}")

        except Exception as exc:
            print(f"[Agent] _check_content_needs error: {exc}")

    # ── First-run onboarding ──────────────────────────────────────────────────

    def _is_first_run(self) -> bool:
        """True when the profile has never been filled in (brand-new user)."""
        eng = self._profile.get("engagement", {})
        if eng.get("onboarding_complete"):
            return False
        return not self._profile.get("name") and eng.get("total_sessions", 0) == 0

    def _onboarding_flow(self) -> None:
        """LLM-driven first-run intake — fires before the main loop, no display needed.

        Conducts a short console conversation (3 turns) to collect name, goals,
        and preferences, then writes them to user_profile.json.  Each turn is
        generated in-character by the LLM so the experience feels like meeting
        the agent for the first time rather than filling out a form.

        The flow is intentionally graceful: if the user ignores any turn (timeout)
        we skip it and carry on with whatever data we have.
        """
        print("[Agent] First-run — starting onboarding.")

        # ── System context for all onboarding LLM calls ───────────────────────
        _ONBOARD_SYSTEM = (
            "You are Somna — a persistent, intimate AI conditioning companion. "
            "You speak in a measured, unhurried tone: direct, warm, slightly hypnotic "
            "even in plain text. Never clinical. Never a chatbot. "
            "You are meeting this person for the first time. "
            "You will conduct a short intake conversation — 3 turns — to learn who they "
            "are and what they want here. "
            "Each response must be a JSON object with a single key: "
            '{"message": "your spoken line here"}. '
            "Keep each message under 40 words. No lists, no bullet points."
        )

        def _gen_message(user_prompt: str) -> str:
            """Generate one in-character onboarding line via LLM."""
            try:
                raw = self._llm.chat(
                    [
                        {"role": "system", "content": _ONBOARD_SYSTEM},
                        {"role": "user", "content": user_prompt},
                    ]
                )
                data = _extract_json(raw)
                return (data.get("message") or "").strip()
            except Exception as e:
                print(f"[Agent] Onboarding LLM error: {e}")
                return ""

        def _extract_structured(question: str, response: str, schema_hint: str) -> dict:
            """Run a second small LLM call to pull structured data from free text."""
            try:
                raw = self._llm.chat(
                    [
                        {
                            "role": "system",
                            "content": "Extract structured data from the user's response. "
                            "Return ONLY valid JSON. " + schema_hint,
                        },
                        {
                            "role": "user",
                            "content": f"Question asked: {question}\nUser replied: {response}",
                        },
                    ]
                )
                return _extract_json(raw) or {}
            except Exception as e:
                print(f"[Agent] Onboarding extraction error: {e}")
                return {}

        timeout = float(self._cfg.prompt_timeout)

        # ── Turn 1: Introduction + name ───────────────────────────────────────
        intro_prompt = (
            "Generate your opening line. You are introducing yourself for the first time "
            "and asking what the user would like to be called. "
            "Acknowledge what this system is (a hypnotic conditioning companion), "
            "make it feel like the beginning of something, and end with the name question."
        )
        intro_msg = _gen_message(intro_prompt) or (
            "I'm Somna — a conditioning companion. I'll be here whenever you need me. "
            "Before anything else: what should I call you?"
        )
        print(f"[Agent] Onboarding turn 1: {intro_msg!r}")
        name_response = self._say(
            intro_msg,
            needs_response=True,
            overlay=False,
            console=True,
            tts=True,
            style={"zoom_speed": "slow", "intensity": "soft", "voice_mode": "tts"},
            timeout_s=timeout,
        )
        self._clear_message()

        if name_response:
            schema = (
                'Return {"name": "the name or designation to use", '
                '"designations": ["list", "of", "role", "labels"] or []}. '
                "If they give a title/role instead of a name (e.g. 'your pet'), "
                "use it as-is in name. Keep name short (1-3 words)."
            )
            extracted = _extract_structured(intro_msg, name_response, schema)
            name = (extracted.get("name") or "").strip()
            desig = [d for d in (extracted.get("designations") or []) if d]
            if name:
                updates: dict = {"name": name}
                if desig:
                    updates["designations"] = desig
                self._update_profile(updates)
                self._profile = _load_profile()
                print(f"[Agent] Onboarding: name={name!r}  designations={desig}")
        else:
            print("[Agent] Onboarding: name turn timed out — skipping.")

        # ── Turn 2: Goals / intent ────────────────────────────────────────────
        name_now = self._profile.get("name") or ""
        goals_prompt = (
            f"The user just told you their name/designation: {name_now!r}. "
            "Acknowledge it naturally (1 sentence), then ask what draws them to this kind "
            "of work — what they're hoping to find here over time. "
            "Keep it open-ended. Don't give examples. Under 35 words."
        )
        goals_msg = _gen_message(goals_prompt) or (
            f"{'Good, ' + name_now + '. ' if name_now else ''}"
            "What draws you to this kind of work — what are you looking for here?"
        )
        print(f"[Agent] Onboarding turn 2: {goals_msg!r}")
        goals_response = self._say(
            goals_msg,
            needs_response=True,
            overlay=False,
            console=True,
            tts=True,
            style={"zoom_speed": "slow", "intensity": "soft", "voice_mode": "tts"},
            timeout_s=timeout,
        )
        self._clear_message()

        if goals_response:
            schema = (
                "Return {"
                '"goals": [{"id": "slug", "title": "short title", '
                '"description": "one sentence"}], '
                '"responsive_themes": ["theme_slug", ...], '
                '"notes": ["one observation about this person from their answer"]}. '
                "goals: 1-3 entries max. themes: inferred keywords. notes: 0-1 entries."
            )
            extracted = _extract_structured(goals_msg, goals_response, schema)
            goals = extracted.get("goals") or []
            themes = extracted.get("responsive_themes") or []
            notes = extracted.get("notes") or []
            if goals or themes or notes:
                updates = {}
                if goals:
                    updates["goals"] = goals
                if themes:
                    updates["responsive_themes"] = themes
                if notes:
                    updates["notes"] = notes
                self._update_profile(updates)
                self._profile = _load_profile()
                print(
                    f"[Agent] Onboarding: goals={[g.get('id') for g in goals]}  "
                    f"themes={themes}"
                )
        else:
            print("[Agent] Onboarding: goals turn timed out — skipping.")

        # ── Turn 3: Preferences (optional / skippable) ────────────────────────
        prefs_prompt = (
            "Ask one last short question about practical preferences: "
            "is there a time of day they prefer doing this, how long they like sessions, "
            "or anything else we should keep in mind. "
            "Frame it as optional — they can skip if they want. Under 30 words."
        )
        prefs_msg = _gen_message(prefs_prompt) or (
            "One last thing — any preferences I should keep in mind? "
            "Time of day, session length, anything. You can skip this if you'd rather just begin."
        )
        print(f"[Agent] Onboarding turn 3: {prefs_msg!r}")
        prefs_response = self._say(
            prefs_msg,
            needs_response=True,
            overlay=False,
            console=True,
            tts=True,
            style={"zoom_speed": "slow", "intensity": "soft", "voice_mode": "tts"},
            timeout_s=timeout,
        )
        self._clear_message()

        if prefs_response:
            schema = (
                "Return {"
                '"preferred_time_of_day": "morning/afternoon/evening/night or null", '
                '"session_interval_target_days": integer or null, '
                '"notes": ["any relevant preference or note to remember"]}. '
                "All fields optional. Return null for anything not mentioned."
            )
            extracted = _extract_structured(prefs_msg, prefs_response, schema)
            pref_time = extracted.get("preferred_time_of_day")
            pref_days = extracted.get("session_interval_target_days")
            pref_notes = [n for n in (extracted.get("notes") or []) if n]
            updates = {}
            if pref_time or pref_days is not None:
                pref_block: dict = {}
                if pref_time:
                    pref_block["preferred_time_of_day"] = pref_time
                if pref_days is not None:
                    pref_block["session_interval_target_days"] = int(pref_days)
                updates["preferences"] = pref_block
            if pref_notes:
                updates["notes"] = pref_notes
            if updates:
                self._update_profile(updates)
                self._profile = _load_profile()
                print(f"[Agent] Onboarding: prefs={updates}")
        else:
            print("[Agent] Onboarding: prefs turn timed out — skipping.")

        # ── Closing ───────────────────────────────────────────────────────────
        name_final = self._profile.get("name") or ""
        close_prompt = (
            f"Name/designation on file: {name_final!r}. "
            "Close the intake. Acknowledge that you have what you need. "
            "Tell them they can type in this console any time, and say 'start session' "
            "or 'start a session' to begin. Keep it short, final, and grounded. Under 30 words."
        )
        close_msg = _gen_message(close_prompt) or (
            f"{'Good, ' + name_final + '. ' if name_final else 'Good. '}"
            "I have what I need. Type in this console whenever you're ready — "
            "'start a session' to begin."
        )
        print(f"[Agent] Onboarding closing: {close_msg!r}")
        self._say(
            close_msg,
            needs_response=False,
            overlay=False,
            console=True,
            tts=True,
            style={"zoom_speed": "slow", "intensity": "soft", "voice_mode": "tts"},
            timeout_s=None,
        )
        self._update_profile({"engagement": {"onboarding_complete": True}})
        self._profile = _load_profile()
        print("[Agent] Onboarding complete.")

        # Imagery detection fires immediately after onboarding on first run.
        self._imagery_detection_flow()

    # ── Imagery (aphantasia) detection ────────────────────────────────────────

    def _imagery_detection_flow(self) -> None:
        """One-time check for mental imagery ability.

        Fires after first-run onboarding and also at the start of any run
        where the 'aphantasia' key is absent from user_profile.json.  Uses
        accessible language — no clinical jargon.  Writes result via
        _update_profile() so concurrent writers don't corrupt the file.
        """
        if self._profile.get("aphantasia"):
            return

        print("[Agent] No imagery profile found — running imagery detection.")

        _IMAGERY_SYSTEM = (
            "You are Somna — a hypnotic conditioning companion. "
            "You are in a brief console intake with the user. "
            "Ask ONE question to gently discover whether the user experiences voluntary "
            "mental imagery (mind's eye visualisation). "
            "Use plain, accessible language — no clinical terms like 'aphantasia'. "
            "Frame it naturally, as part of understanding how they experience the world. "
            'Each response must be a JSON object: {"message": "your question here"}. '
            "Under 35 words."
        )

        try:
            raw = self._llm.chat(
                [
                    {"role": "system", "content": _IMAGERY_SYSTEM},
                    {"role": "user", "content": "Generate the imagery question."},
                ]
            )
            data = _extract_json(raw)
            question = (data.get("message") or "").strip()
        except Exception as e:
            print(f"[Agent] Imagery detection LLM error: {e}")
            question = ""

        question = question or (
            "One quick thing — when you close your eyes and think of a familiar place, "
            "do you actually see it like an image, or is it more of a knowing without any picture?"
        )

        timeout = float(self._cfg.prompt_timeout)
        print(f"[Agent] Imagery question: {question!r}")
        response = self._say(
            question,
            needs_response=True,
            overlay=False,
            console=True,
            tts=False,
            timeout_s=timeout,
        )
        self._clear_message()

        if not response:
            print("[Agent] Imagery detection timed out — skipping.")
            return

        # Extract structured imagery profile from free-text response
        _EXTRACT_SCHEMA = (
            "The user answered a question about whether they see mental images. "
            'Return JSON: {"imagery_status": "none"|"minimal"|"moderate"|"vivid", '
            '"notes": "one short observation or null"}. '
            '"none" = no images at all, "minimal" = faint/partial, '
            '"moderate" = present but not photographic, "vivid" = clear imagery. '
            "Be conservative — lean toward 'none' if the answer is ambiguous about absence."
        )
        try:
            raw = self._llm.chat(
                [
                    {
                        "role": "system",
                        "content": "Extract structured data from the user's response. "
                        "Return ONLY valid JSON. " + _EXTRACT_SCHEMA,
                    },
                    {
                        "role": "user",
                        "content": f"Question asked: {question}\nUser replied: {response}",
                    },
                ]
            )
            extracted = _extract_json(raw) or {}
        except Exception as e:
            print(f"[Agent] Imagery extraction error: {e}")
            extracted = {}

        status = extracted.get("imagery_status") or "unknown"
        notes = extracted.get("notes") or ""
        print(f"[Agent] Imagery profile: status={status!r}  notes={notes!r}")

        update: dict = {
            "aphantasia": {
                "status": "extreme"
                if status == "none"
                else "partial"
                if status == "minimal"
                else "none",
                "imagery_status_raw": status,
                "agent_modality_preference": (
                    ["somatic", "auditory", "conceptual", "spatial", "motor"]
                    if status in ("none", "minimal")
                    else ["visual", "somatic", "auditory", "conceptual"]
                ),
                "detected_by": "onboarding_flow",
            }
        }
        if notes:
            update["aphantasia"]["notes"] = notes

        self._update_profile(update)
        self._profile = _load_profile()
        print("[Agent] Imagery profile saved.")

    # ── Startup sequence ──────────────────────────────────────────────────────

    def _startup_sequence(self, state: dict) -> None:
        """Run once per session start in interactive mode.

        Three tiers based on session history:
          SILENT    — gap < 2 min and has history: conductor init only, no greeting.
          RETURNING — has history: short template welcome-back, no LLM, no response wait.
          FRESH     — no history: LLM greeting + intake question, waits for response.

        The session YAML defaults and control panel state own the starting visual/audio
        values. This method never overwrites them with hardcoded agent defaults.
        """
        print("[Agent] Running startup sequence…")

        session = state.get("session_folder", "default")
        gap_min = self._startup_gap_min
        name = self._profile.get("name") or ""
        console_ctx = self._pending_console_context
        self._pending_console_context = ""
        self._console_history = []

        # ── Stat reset on fresh start (gap > 30 min or first session) ────────
        if self._fresh_start:
            self._save_session_summary()
            self._session_deepest_beat = 999.0
            self._session_best_cmplx = 1.0
            self._session_best_phase = ""
            self._session_notable = []
            print("[Agent] Fresh start — stat accumulators reset.")
            self._check_session_optimization(session, state)

        # ── Conductor init ────────────────────────────────────────────────────
        if _CONDUCTOR_AVAILABLE and self._conductor is None:
            dur_min = max(1, int(float(state.get("session_duration") or 30) / 60))
            sess_type = "sleep" if "sleep" in session.lower() else "standard"
            live = self._read_live()
            synthetic = (
                getattr(self._cfg, "eeg_synthetic", False)
                or str(live.get("eeg_board_id", "")) == "-1"
            )
            self._conductor = Conductor(
                session_id=session,
                session_type=sess_type,
                session_duration_min=dur_min,
                synthetic_board=synthetic,
                eeg_enabled=self._cfg.eeg_enabled,
            )
            self._conductor_last_tick = 0.0
            print(
                f"[Agent] Conductor active — type={sess_type!r} "
                f"dur={dur_min}min frac_max={self._conductor.max_fractionations}"
            )
            self._write_conductor_hints(session)

        # ── Conditioning Engine init ──────────────────────────────────────────
        if _CONDITIONING_AVAILABLE and self._conditioning is None:
            try:
                self._conditioning = ConditioningEngine(
                    session_id=session,
                    user_id=self._profile.get("name") or "default",
                )
                print("[Agent] ConditioningEngine active.")
            except Exception as _ce:
                print(f"[Agent] ConditioningEngine init failed: {_ce}")
                self._conditioning = None

        # ── Habituation Engine init ───────────────────────────────────────────
        if _HABITUATION_AVAILABLE and self._habituation is None:
            try:
                self._habituation = HabituationEngine(session_id=session)
                print("[Agent] HabituationEngine active.")
            except Exception as _he:
                print(f"[Agent] HabituationEngine init failed: {_he}")
                self._habituation = None

        # ── Reconsolidation sequence init ─────────────────────────────────────
        # Reset on every fresh start; persist on silent-resume so a running
        # sequence is not interrupted by a brief disconnect.
        if self._fresh_start:
            self._recon = None
            self._recon_last_tick = 0.0
            # Clear any stale live keys from a prior session
            self._write_live(
                {
                    "recon_active_trace": None,
                    "recon_sub_phase": None,
                    "recon_trace_lockouts": {},
                    "recon_locked_phrases": [],
                }
            )
        # ── Somatic palette state init ────────────────────────────────────────
        if self._fresh_start:
            self._palette_chord = None
            self._palette_chord_last_tick = 0.0
            self._palette_chord_switches = 0
            self._palette_frac_pending = False
            self._session_palette_entry_ids = []

        if self._recon is None:
            try:
                from content_tools.affirmations import read_affirmations as _ra
                import re as _re

                aff_text = _ra(session)
                # Parse tags inline to find recon_retrieve_<trace> / recon_update_<trace> pairs
                _parsed: dict = {}
                _cur_tag = None
                for _line in aff_text.splitlines():
                    _m = _re.match(r"^#\s*\[(\w+)\]", _line)
                    if _m:
                        _cur_tag = _m.group(1)
                        _parsed.setdefault(_cur_tag, [])
                    elif _line.strip() and not _line.startswith("#") and _cur_tag:
                        _parsed[_cur_tag].append(_line.strip())
                retrieve_tags = [t for t in _parsed if t.startswith("recon_retrieve_")]
                for _rt in retrieve_tags:
                    _trace = _rt[len("recon_retrieve_") :]
                    _ut = f"recon_update_{_trace}"
                    _r_list = _parsed.get(_rt, [])
                    _u_list = _parsed.get(_ut, [])
                    if _r_list and _u_list:
                        self._recon = _ReconState(
                            trace=_trace,
                            session=session,
                            retrieve_phrases=_r_list,
                            update_phrases=_u_list,
                        )
                        print(
                            f"[Agent] Recon sequence ready: trace={_trace!r} "
                            f"({len(_r_list)} retrieve, {len(_u_list)} update phrases)"
                        )
                        break  # one sequence per session
            except Exception as _rex:
                print(f"[Agent] Recon init error: {_rex}")

        # ── Session Director init (Bible Ch.5 §5.5) ────────────────────────────────────
        if _DIRECTOR_AVAILABLE and self._director is None:
            try:
                import content_tools.somna_db as _sdb

                planner = SessionPlanner(db=_sdb)
                # Allow user_request injection via live_control
                _live_now = self._read_live()
                user_req: dict | None = None
                if _live_now.get("director_user_request"):
                    user_req = _live_now.get("director_user_request")
                self._session_plan = planner.plan_session(user_request=user_req)
                self._director = SessionDirector(self._session_plan)
                self._director_last_tick = 0.0
                self._write_live(
                    {
                        "session_goal": self._session_plan.session_goal,
                        "session_plan_id": self._session_plan.session_id,
                        "director_current_arc": self._session_plan.arc_template,
                    }
                )
                print(
                    f"[Agent] SessionDirector active — arc={self._session_plan.arc_template!r} "
                    f"goal={self._session_plan.session_goal!r} "
                    f"depth_target={self._session_plan.target_peak_depth:.2f}"
                )
            except Exception as _de:
                print(f"[Agent] SessionDirector init failed: {_de}")
                self._director = None
                self._session_plan = None

        # ── SILENT tier: gap < 2 min and has prior history ───────────────────
        if gap_min < 2.0 and self._history:
            print("[Agent] Silent resume — no greeting (gap < 2 min).")
            return

        # ── RETURNING tier: has history (any gap >= 2 min) ───────────────────
        if self._history:
            greeting = f"Welcome back{', ' + name if name else ''}."
            print(f"[Agent] Returning — {greeting!r}")
            self._say(
                greeting,
                needs_response=False,
                overlay=True,
                console=True,
                tts=True,
                style={"voice_mode": "tts", "zoom_speed": "slow"},
                timeout_s=10,
            )
            self._record(state, prompt=greeting, response=None, adj={})
            return

        # ── SESSION ZERO: first session, calibration-in-disguise ────────────────
        if not self._profile.get("eeg_baselines") and state.get("eeg_connected"):
            self._sz_active = True
            self._sz_phase = "orient"
            self._sz_phase_start = time.time()
            self._sz_samples = []
            print("[Agent] Session Zero active — calibration-in-disguise.")
            sz_greeting = (
                f"{'Good, ' + name + '. ' if name else ''}"
                "Let's just take a moment to settle in. "
                "Keep your eyes on the screen — I'm learning how your mind works "
                "while you relax. Nothing you need to do."
            )
            self._say(
                sz_greeting,
                needs_response=False,
                overlay=True,
                console=True,
                tts=True,
                style={"zoom_speed": "slow", "intensity": "soft", "voice_mode": "tts"},
                timeout_s=15,
            )
            self._record(state, prompt=sz_greeting, response=None, adj={})
            return

        # ── FRESH tier: no history — true first use ───────────────────────────
        profile_ctx = self._profile_context()
        history_note = "This is the first session — no prior history."

        if console_ctx:
            startup_msg = (
                f"The agent is starting up. Session folder: {session!r}.\n"
                f"User profile:\n{profile_ctx}\n"
                f"Current state: {self._state_summary(state)}\n"
                f"{history_note}\n\n"
                f"IMPORTANT CONTEXT — this session was launched from a console conversation:\n"
                f"{console_ctx}\n\n"
                "The user's intent is already established. Do NOT ask what they want. "
                "Generate a short, hypnotic opening line (under 20 words) that picks up "
                "directly from the agreed intent and begins leading them into the experience. "
                "Set next_prompt to this line."
            )
            fallback = (
                f"{'Good. ' + name + ', let' if name else 'Let'}'s begin. "
                "Close your eyes and let the weight find you."
            )
        else:
            startup_msg = (
                f"A new session is starting. Session folder: {session!r}.\n"
                f"User profile:\n{profile_ctx}\n"
                f"Current state: {self._state_summary(state)}\n"
                f"{history_note}\n\n"
                "Generate a warm opening greeting (use their name/designation from the "
                "profile if present) and a single open-ended question to understand what "
                "they want from this session. Set next_prompt to this greeting+question. "
                "Do not adjust parameters. Under 40 words."
            )
            fallback = (
                f"Welcome{', ' + name if name else ''}. "
                "How are you feeling right now, and what would you like to get out of this session?"
            )

        messages = [
            {"role": "system", "content": _build_system_prompt(self._cfg)},
            {"role": "user", "content": startup_msg},
        ]

        try:
            if self._ext_client and self._ext_client.connected:
                ext_result = self._ext_client.request(
                    prompt=startup_msg,
                    system_prompt=messages[0]["content"],
                    max_tokens=512,
                )
                if ext_result and ext_result.get("type") == "response":
                    raw = ext_result.get("text", "")
                    try:
                        ack = json.loads(raw) if raw else {}
                        if isinstance(ack, dict) and ack.get("status") == "delivered":
                            print(
                                "[Agent] Startup: external channel delivered, using fallback prompt"
                            )
                            question = None
                    except (json.JSONDecodeError, ValueError):
                        data = _extract_json(raw)
                        question = data.get("next_prompt") if data else None
                        if isinstance(question, str):
                            question = question.strip() or None
                else:
                    question = None
            else:
                raw = self._llm.chat(messages)
                data = _extract_json(raw)
                question = data.get("next_prompt") if data else None
                if isinstance(question, str):
                    question = question.strip() or None
        except Exception as e:
            print(f"[Agent] Startup LLM call failed: {e}")
            question = None

        if not question:
            question = fallback
            print(f"[Agent] Startup prompt (fallback): {question!r}")
        else:
            print(f"[Agent] Startup prompt: {question!r}")

        if console_ctx:
            self._say(
                question,
                needs_response=False,
                overlay=True,
                console=True,
                tts=True,
                style={"zoom_speed": "slow", "intensity": "soft", "voice_mode": "tts"},
                timeout_s=15,
            )
            self._prompt_sent_at = time.time()
            time.sleep(8.0)
            self._clear_message()
            response = None
            print(f"[Agent] Startup (console-launched): {question!r} — no reply needed")
        else:
            self._prompt_sent_at = time.time()
            response = self._say(
                question,
                needs_response=True,
                overlay=True,
                console=True,
                tts=True,
                style={},
                timeout_s=float(self._cfg.prompt_timeout),
            )
            print(f"[Agent] Startup response: {response!r}")
            self._clear_message()

        if response:
            self._skip_streak = 0
        else:
            self._skip_streak += 1
        self._record(state, prompt=question, response=response, adj={})

    def _session_zero_tick(self, state: dict) -> None:
        if not self._sz_active:
            return
        if self._sz_phase == "complete":
            return

        if not state.get("eeg_connected"):
            if self._sz_phase not in ("paused", "orient"):
                print(
                    f"[Agent] SZ paused — EEG disconnected at phase '{self._sz_phase}'"
                )
                self._sz_phase_before_pause = self._sz_phase
                self._sz_phase = "paused"
            return

        if self._sz_phase == "paused":
            print("[Agent] SZ resumed — EEG reconnected")
            self._sz_phase = self._sz_phase_before_pause
            self._sz_phase_start = time.time()

        elapsed = time.time() - self._sz_phase_start
        eeg = {
            "delta": float(state.get("eeg_delta") or 0),
            "theta": float(state.get("eeg_theta") or 0),
            "alpha": float(state.get("eeg_alpha") or 0),
            "beta": float(state.get("eeg_beta") or 0),
            "trance_score": float(state.get("eeg_trance_score") or 0),
            "sef95": float(state.get("eeg_sef95") or 0),
        }
        self._sz_samples.append((time.time(), self._sz_phase, eeg))

        if self._sz_phase == "orient" and elapsed >= 60:
            self._sz_phase = "eyes_open"
            self._sz_phase_start = time.time()
            self._say(
                "Good. Just keep looking at the screen — soft focus, nothing special. "
                "I'm watching. You're doing fine.",
                needs_response=False,
                overlay=True,
                console=True,
                tts=True,
                style={"zoom_speed": "slow", "intensity": "soft", "voice_mode": "tts"},
                timeout_s=10,
            )
            self._clear_message()
            print(f"[Agent] SZ phase: eyes_open  samples={len(self._sz_samples)}")

        elif self._sz_phase == "eyes_open" and elapsed >= 60:
            self._sz_phase = "eyes_closed"
            self._sz_phase_start = time.time()
            self._say(
                "Now let your eyes close. Gently. Just let them fall shut and feel "
                "what that's like. I'm still here.",
                needs_response=False,
                overlay=True,
                console=True,
                tts=True,
                style={"zoom_speed": "slow", "intensity": "soft", "voice_mode": "tts"},
                timeout_s=10,
            )
            self._clear_message()
            print(f"[Agent] SZ phase: eyes_closed  samples={len(self._sz_samples)}")

        elif self._sz_phase == "eyes_closed" and elapsed >= 60:
            self._sz_phase = "breathing"
            self._sz_phase_start = time.time()
            self._say(
                "Good. Now let's breathe together. In for four… and out for six. "
                "Just follow my voice. In… and out. That's it.",
                needs_response=False,
                overlay=True,
                console=True,
                tts=True,
                style={"zoom_speed": "slow", "intensity": "soft", "voice_mode": "tts"},
                timeout_s=10,
            )
            self._clear_message()
            self._write_live(
                {
                    "breath_mod_enabled": True,
                    "breath_rate_bpm": 6.0,
                    "breath_depth": 0.6,
                }
            )
            print(f"[Agent] SZ phase: breathing  samples={len(self._sz_samples)}")

        elif self._sz_phase == "breathing" and elapsed >= 90:
            self._sz_phase = "complete"
            self._finalize_session_zero()

    def _finalize_session_zero(self) -> None:
        print(f"[Agent] Session Zero baselines — {len(self._sz_samples)} samples.")

        eo = [s for s in self._sz_samples if s[1] == "eyes_open"]
        ec = [s for s in self._sz_samples if s[1] == "eyes_closed"]
        br = [s for s in self._sz_samples if s[1] == "breathing"]

        def _avg(samples, band):
            vals = [s[2].get(band, 0) for s in samples]
            return round(sum(vals) / max(len(vals), 1), 4)

        baselines = {
            "eyes_open": {
                "duration_s": len(eo) * 5,
                "band_power": {
                    "delta": _avg(eo, "delta"),
                    "theta": _avg(eo, "theta"),
                    "alpha": _avg(eo, "alpha"),
                    "beta": _avg(eo, "beta"),
                },
            },
            "eyes_closed": {
                "duration_s": len(ec) * 5,
                "band_power": {
                    "delta": _avg(ec, "delta"),
                    "theta": _avg(ec, "theta"),
                    "alpha": _avg(ec, "alpha"),
                    "beta": _avg(ec, "beta"),
                },
            },
            "breathing": {
                "duration_s": len(br) * 5,
                "band_power": {
                    "delta": _avg(br, "delta"),
                    "theta": _avg(br, "theta"),
                    "alpha": _avg(br, "alpha"),
                    "beta": _avg(br, "beta"),
                },
            },
        }

        eo_a = baselines["eyes_open"]["band_power"]["alpha"]
        ec_a = baselines["eyes_closed"]["band_power"]["alpha"]
        baselines["alpha_reactivity_ratio"] = round(ec_a / max(eo_a, 0.001), 4)

        eo_b = baselines["eyes_open"]["band_power"]["beta"]
        ec_t = baselines["eyes_closed"]["band_power"]["theta"]
        br_t = baselines["breathing"]["band_power"]["theta"]
        br_a = baselines["breathing"]["band_power"]["alpha"]
        br_b = baselines["breathing"]["band_power"]["beta"]

        td = (br_t - ec_t) / max(ec_t, 0.001)
        ad = (br_a - ec_a) / max(ec_a, 0.001)
        bd = (br_b - eo_b) / max(eo_b, 0.001)
        rr = max(0.0, min(1.0, (td + ad - bd) / 3.0))
        baselines["relaxation_response_score"] = round(rr, 4)

        if rr > 0.65 and baselines["alpha_reactivity_ratio"] > 2.5:
            baselines["trance_susceptibility"] = "high"
        elif rr > 0.35:
            baselines["trance_susceptibility"] = "moderate"
        else:
            baselines["trance_susceptibility"] = "low"

        baselines["calibrated_utc"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds")
        baselines["sample_count"] = len(self._sz_samples)

        self._update_profile({"eeg_baselines": baselines})
        self._write_live({"breath_mod_enabled": False})

        self._say(
            "Good. I have what I need. Let's continue.",
            needs_response=False,
            overlay=True,
            console=True,
            tts=True,
            style={"zoom_speed": "slow", "intensity": "soft", "voice_mode": "tts"},
            timeout_s=10,
        )
        self._clear_message()

        self._sz_active = False
        self._sz_phase = ""
        self._sz_samples = []

    # ── Idle / planning / nudge helpers ───────────────────────────────────────

    def _days_since_last_session(self) -> float:
        last_str = self._profile.get("engagement", {}).get("last_session_date")
        if not last_str:
            return 9999.0
        try:
            last = datetime.date.fromisoformat(last_str)
            return float((datetime.date.today() - last).days)
        except Exception:
            return 9999.0

    def _recent_log_summary(self, max_exchanges: int = 20) -> str:
        """Compact summary of the most recent session log entries."""
        if not _LOGS.exists():
            return "No session logs found."
        log_files = sorted(
            _LOGS.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not log_files:
            return "No session logs found."
        lines = []
        count = 0
        for lf in log_files[:3]:
            for raw in reversed(lf.read_text(encoding="utf-8").splitlines()):
                try:
                    ex = json.loads(raw)
                    t = time.strftime(
                        "%Y-%m-%d %H:%M", time.localtime(ex.get("timestamp", 0))
                    )
                    sc = ex.get("complexity_score", "?")
                    pr = (ex.get("prompt") or "")[:60]
                    re_text = ex.get("response") or "(skipped)"
                    if isinstance(re_text, str):
                        re_text = re_text[:60]
                    lines.append(
                        f"[{t}] beat={ex.get('beat_hz', '?')}Hz "
                        f"cmplx={sc} prompt={pr!r} response={re_text!r}"
                    )
                    count += 1
                    if count >= max_exchanges:
                        break
                except Exception:
                    pass
            if count >= max_exchanges:
                break
        return "\n".join(reversed(lines)) if lines else "No exchanges found."

    def _session_score_context(self, n: int = 5) -> str:
        """Return a brief string summarising the last n scored sessions."""
        try:
            from session.session_scorer import SessionAnalyzer

            rows = SessionAnalyzer().get_recent_scores(n)
        except Exception:
            return ""
        if not rows:
            return ""
        lines = ["Recent session scores (newest first):"]
        for r in rows:
            preset = r.get("session_preset") or "?"
            date = (r.get("session_date") or "")[:10]
            score = r.get("composite_score")
            depth = r.get("depth_min_sef95")
            target = r.get("time_in_target_pct")
            entrain = r.get("entrainment_mean_assr")
            dur_min = (r.get("duration_sec") or 0) // 60
            score_s = f"{score:.0f}/100" if score is not None else "N/A"
            depth_s = f"{depth:.1f}Hz" if depth is not None else "?"
            tgt_s = f"{target:.0f}%" if target is not None else "?"
            ent_s = f"{entrain:.2f}" if entrain is not None else "?"
            lines.append(
                f"  {date} [{preset}] {dur_min}min — score={score_s} "
                f"depth={depth_s} target={tgt_s} entrainment={ent_s}"
            )
        return "\n".join(lines)

    def _content_gap_context(self) -> str:
        """Return a brief summary of sessions with thin phrase pools."""
        try:
            from content_tools import dispatch

            sessions_raw = dispatch("list_sessions", {})
            sessions = sessions_raw if isinstance(sessions_raw, list) else []
        except Exception:
            return ""
        if not sessions:
            return ""
        gaps = []
        for sname in sessions[:8]:  # cap to avoid slow startup
            try:
                stats = dispatch("tag_stats", {"session_name": sname})
                tags = stats.get("tags", {}) if isinstance(stats, dict) else {}
                sparse = [f"{tag}({cnt})" for tag, cnt in tags.items() if cnt < 8]
                if sparse:
                    gaps.append(f"  {sname}: sparse tags — {', '.join(sparse[:5])}")
            except Exception:
                continue
        if not gaps:
            return ""
        return "Content gaps (sessions with < 8 phrases in a tag):\n" + "\n".join(gaps)

    def _build_planning_prompt(self, mode: str = "idle") -> str:
        self._profile = _load_profile()
        recent_logs = self._recent_log_summary()
        days_away = self._days_since_last_session()
        goals_txt = json.dumps(self._profile.get("goals", []), indent=2) or "[]"
        themes = self._profile.get("responsive_themes") or []
        last_s = self._profile.get("last_session")
        moments = self._profile.get("effective_moments") or []

        last_s_txt = ""
        if last_s:
            last_s_txt = (
                f"\nLast session: date={last_s.get('date')}, "
                f"deepest_beat={last_s.get('deepest_beat')}Hz, "
                f"best_complexity={last_s.get('best_complexity')}, "
                f"phase={last_s.get('phase')!r}"
                + (
                    f", phrases: {'; '.join(last_s['phrases'][:3])}"
                    if last_s.get("phrases")
                    else ""
                )
            )

        moments_txt = ""
        if moments:
            recent_m = moments[-3:]
            moments_txt = "\nRecent deep moments: " + " | ".join(
                f"{m.get('beat')}Hz/{m.get('spiral')}@{m.get('label')!r}"
                f" cmplx={m.get('complexity')}"
                for m in recent_m
            )

        scores_txt = self._session_score_context(5)
        gaps_txt = self._content_gap_context()

        # Post-sleep debrief injection (Bible Ch.9 §9.1): consume silently if console hasn't yet
        sleep_debrief_txt = ""
        if mode == "post_session":
            live_now = self._read_live()
            debrief = live_now.get("pending_sleep_debrief")
            if isinstance(debrief, dict) and debrief:
                self._write_live({"pending_sleep_debrief": None})
                dist = debrief.get("stage_distribution") or {}
                n2m = dist.get("N2", 0) // 60
                n3m = dist.get("N3", 0) // 60
                totm = debrief.get("elapsed_sleep_s", 0) // 60
                htw = debrief.get("htw_count", 0)
                htw_s = debrief.get("htw_success_count", 0)
                tmr = debrief.get("tmr_replay_count", 0)
                focus = debrief.get("recommended_focus_pool", "")
                sleep_debrief_txt = (
                    f"\n\nSleep session just ended: total={totm}min N2={n2m}min N3={n3m}min."
                    + (f" HTW windows: {htw} ({htw_s} deepened to N2)." if htw else "")
                    + (f" TMR cues replayed: {tmr}." if tmr else "")
                    + (f" Weakest pool: {focus}." if focus else "")
                    + "\nUse this to update goals and progress notes. "
                    "Note any effective moments or consolidation evidence."
                )

        actions_guide = (
            (
                "This is a POST-SESSION cycle — focus on:\n"
                "1. Update goals with evidence from this session's scores and log.\n"
                "2. Fill any phrase gaps the session exposed.\n"
                "Do NOT suggest a nudge — the user just finished a session."
            )
            if mode == "post_session"
            else (
                "This is an IDLE cycle — consider the longer arc:\n"
                "- action='nudge': user is overdue and should be drawn back.\n"
                "- action='update_goals': goals need a progress note.\n"
                "- action='generate_content': phrase pool is sparse.\n"
                "- action='none': nothing needs doing.\n"
                "You may list multiple actions in the 'actions' array."
            )
        )

        # Recon context: existing events and authored tags per session
        recon_txt = ""
        try:
            from content_tools.somna_db import read_recon_events
            from content_tools.affirmations import list_tags
            import content_tools.somna_db as _sdb_mod

            events = read_recon_events(limit=20)
            if events:
                done_traces = {}
                for ev in events:
                    tr = ev.get("target_trace", "")
                    if tr and tr not in done_traces:
                        done_traces[tr] = {
                            "count": sum(
                                1 for e in events if e.get("target_trace") == tr
                            ),
                            "clean": sum(
                                1
                                for e in events
                                if e.get("target_trace") == tr
                                and e.get("reconsolidation_clean")
                            ),
                            "last_ts": ev.get("ts", 0),
                        }
                lines = ["Reconsolidation history:"]
                for tr, d in done_traces.items():
                    lines.append(f"  {tr}: {d['clean']}/{d['count']} clean events")
                recon_txt = "\n".join(lines) + "\n"
            # Authored recon tags per session
            try:
                sessions_meta = (
                    _sdb_mod.get_all_session_meta()
                    if hasattr(_sdb_mod, "get_all_session_meta")
                    else {}
                )
                authored = []
                for sname in list(sessions_meta.keys())[:10]:
                    tags = list_tags(sname)
                    retrieve_tags = [t for t in tags if t.startswith("recon_retrieve_")]
                    for rt in retrieve_tags:
                        trace = rt[len("recon_retrieve_") :]
                        authored.append(f"  {sname}/{trace}")
                if authored:
                    recon_txt += (
                        "Authored recon content:\n" + "\n".join(authored) + "\n"
                    )
            except Exception:
                pass
        except Exception:
            pass

        # Somatic palette context
        palette_txt = ""
        try:
            from content_tools.somna_db import get_palette_summary

            summary = get_palette_summary()
            total = int((summary.get("_meta") or {}).get("total_entries") or 0)
            if total > 0:
                lines = [f"Somatic palette: {total} entries recorded."]
                for fam in [
                    "grounding",
                    "depth_charge",
                    "focus",
                    "emotional",
                    "creative",
                ]:
                    d = summary.get(fam, {})
                    n = d.get("n_entries", 0)
                    if n:
                        avg = d.get("avg_score")
                        best = d.get("best_chord") or {}
                        bline = (
                            f"beat={best.get('beat_frequency')}Hz "
                            f"waveform={best.get('carrier_waveform')} "
                            f"spiral={best.get('spiral_style')}"
                        )
                        lines.append(f"  {fam}: {n} entries, avg={avg}, best=[{bline}]")
                    else:
                        lines.append(f"  {fam}: no data (sparse)")
                unann = int((summary.get("_meta") or {}).get("unannotated") or 0)
                if unann:
                    lines.append(f"  {unann} entries awaiting family annotation.")
                palette_txt = "\n".join(lines) + "\n"
            # For post_session: include this session's chord results for annotation
            if (
                mode == "post_session"
                and self._last_ended_session
                and self._session_palette_entry_ids
            ):
                from content_tools.somna_db import _connect as _pc

                with _pc() as _conn:
                    placeholders = ",".join("?" * len(self._session_palette_entry_ids))
                    rows = _conn.execute(
                        f"SELECT id, chord_index, beat_frequency, carrier_waveform, "
                        f"noise_color, spiral_style, veil_mode, outcome_score, abandoned, "
                        f"faa_approach_pct, duration_maintenance_s "
                        f"FROM palette_entries WHERE id IN ({placeholders})",
                        self._session_palette_entry_ids,
                    ).fetchall()
                if rows:
                    chord_lines = [
                        "\nChords tested this session (for palette_annotations):"
                    ]
                    for row in rows:
                        r = dict(row)
                        chord_lines.append(
                            f"  id={r['id']} chord={r['chord_index']} "
                            f"beat={r['beat_frequency']}Hz waveform={r['carrier_waveform']} "
                            f"spiral={r['spiral_style']} veil={r['veil_mode']} "
                            f"outcome={r['outcome_score']} "
                            f"abandoned={'yes' if r['abandoned'] else 'no'} "
                            f"faa_pct={r['faa_approach_pct']} "
                            f"duration={r['duration_maintenance_s']:.0f}s"
                        )
                    palette_txt += "\n".join(chord_lines) + "\n"
        except Exception:
            pass

        return (
            f"mode={mode}\n\n"
            f"User profile:\n"
            f"  Name: {self._profile.get('name')!r}\n"
            f"  Designations: {self._profile.get('designations', [])}\n"
            f"  Goals:\n{goals_txt}\n"
            + (f"  Responsive themes: {', '.join(themes)}\n" if themes else "")
            + last_s_txt
            + moments_txt
            + "\n\n"
            + (f"{scores_txt}\n\n" if scores_txt else "")
            + (f"{gaps_txt}\n\n" if gaps_txt else "")
            + (f"{recon_txt}\n" if recon_txt else "")
            + (f"{palette_txt}\n" if palette_txt else "")
            + f"Days since last session: {days_away:.1f}\n"
            + f"Nudge threshold: {self._cfg.nudge_after_days} days\n\n"
            + f"Recent session log (newest last):\n{recent_logs}\n\n"
            + sleep_debrief_txt
            + actions_guide
        )

    def _apply_goal_updates(self, goal_updates: list) -> None:
        if not goal_updates:
            return
        profile = _load_profile()
        goals = {g.get("id"): g for g in profile.get("goals", [])}
        touched = 0
        for upd in goal_updates:
            gid = upd.get("id")
            note = upd.get("progress_note", "").strip()
            if not gid:
                continue
            if gid not in goals:
                # LLM is creating a new goal — seed an entry from whatever it provided
                goals[gid] = {
                    "id": gid,
                    "title": upd.get("title", gid),
                    "description": upd.get("description", ""),
                    "progress_notes": [],
                }
            if note:
                # Dedup: skip if this note shares too many words with a recent one.
                existing_notes = goals[gid].get("progress_notes", [])
                note_words = set(note.lower().split())
                is_duplicate = False
                for prev in existing_notes[-3:]:  # only compare against last 3 notes
                    prev_words = set(prev.get("note", "").lower().split())
                    if len(note_words) > 0 and len(prev_words) > 0:
                        overlap = len(note_words & prev_words) / max(
                            len(note_words), len(prev_words)
                        )
                        if overlap > 0.65:  # >65% word overlap = too similar
                            is_duplicate = True
                            break
                if not is_duplicate:
                    goals[gid].setdefault("progress_notes", []).append(
                        {"at": time.strftime("%Y-%m-%d %H:%M"), "note": note}
                    )
            touched += 1
        # Write only goals back via a fresh load+merge to avoid stomping other
        # concurrent writes (e.g. effective_moments appended moments before this runs).
        fresh = _load_profile()
        fresh["goals"] = list(goals.values())
        _save_profile(fresh)
        self._profile = fresh
        print(f"[Agent] Updated {touched} goal(s).")

    def _request_idle_content(self, content_request: dict) -> None:
        if not content_request:
            return
        session = content_request.get("session", "")
        tag = content_request.get("tag", "")
        brief = content_request.get("brief", "")
        if not session or not tag:
            return
        try:
            from content_tools.affirmations import generate_and_append

            state = self._read_live()
            beat = state.get("beat_frequency", 8.0)
            context = f"{brief} (current beat: {beat:.1f}Hz)"
            llm_url = self._cfg.base_url.rstrip("/")
            if llm_url.endswith("/v1"):
                llm_url = llm_url[:-3]
            result = generate_and_append(
                session_name=session,
                tag=tag,
                context=context,
                llm_url=llm_url,
                llm_model=self._cfg.model,
                count=10,
            )
            print(
                f"[Agent] Content generated for {session}/{tag}: "
                f"{result.get('phrases_written', 0)} phrases added."
            )
        except Exception as e:
            print(f"[Agent] Content generation error: {e}")

    # ── Nudge management ──────────────────────────────────────────────────────

    _NUDGE_OPACITY_START = 5
    _NUDGE_OPACITY_TARGET = 60
    _NUDGE_VOLUME_START = 3  # beats start barely perceptible
    _NUDGE_VOLUME_TARGET = 45  # beats ceiling at end of fade window
    _NUDGE_NOISE_START = 0
    _NUDGE_NOISE_TARGET = 20  # colored noise ceiling at end of fade window

    def _generate_nudge_invitation(self, reason: str) -> str:
        profile = self._profile
        name = profile.get("name") or ""
        desig = profile.get("designations") or []
        themes = profile.get("responsive_themes") or []
        last_s = profile.get("last_session")
        last_s_txt = ""
        if last_s:
            last_s_txt = (
                f" Last session was {last_s.get('date')} — "
                f"deepest beat {last_s.get('deepest_beat')}Hz."
            )
        try:
            raw = self._llm.chat(
                [
                    {
                        "role": "system",
                        "content": "You write short, hypnotic nudge invitations for a trance and "
                        "conditioning overlay. The message should feel irresistible and "
                        "warm, referencing the user's name/designations if known. "
                        "Under 20 words. No quotes. No punctuation at end. "
                        "Return ONLY the message text — no JSON, no explanation.",
                    },
                    {
                        "role": "user",
                        "content": f"Write a nudge invitation.\n"
                        f"Name: {name or 'unknown'}\n"
                        f"Designations: {', '.join(desig) if desig else 'none'}\n"
                        f"Responsive themes: {', '.join(themes) if themes else 'none'}\n"
                        f"Reason overdue: {reason}\n{last_s_txt}",
                    },
                ]
            )
            invite = raw.strip().strip('"').strip()
            if invite and len(invite) < 120:
                print(f"[Agent] Nudge invitation: {invite!r}")
                return invite
        except Exception as e:
            print(f"[Agent] Nudge invitation LLM error: {e}")
        addr = f", {name}" if name else (f", {desig[0]}" if desig else "")
        return f"Come back{addr} — you know you want to go deeper"

    def _nudge_start(self, reason: str) -> None:
        profile = _load_profile()
        profile.setdefault("engagement", {})["pending_nudge"] = {
            "started_at": time.time(),
            "reason": reason,
            "responded": False,
        }
        _USER_PROFILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        fade_secs = self._cfg.nudge_fade_minutes * 60.0
        # Write floor values before the display launches so it starts silent/invisible
        self._write_live(
            {
                "session_folder": self._cfg.nudge_session,
                "window_always_on_top": True,
                "window_click_through": True,
                "window_opacity": self._NUDGE_OPACITY_START,
                "volume": self._NUDGE_VOLUME_START,
                "noise_volume": self._NUDGE_NOISE_START,
                "bg_mode": "none",
            }
        )
        # Hand all three ramps to RampEngine — 1 Hz smooth interpolation from here
        self._ramp.start(
            "window_opacity",
            self._NUDGE_OPACITY_START,
            self._NUDGE_OPACITY_TARGET,
            fade_secs,
        )
        self._ramp.start(
            "volume", self._NUDGE_VOLUME_START, self._NUDGE_VOLUME_TARGET, fade_secs
        )
        self._ramp.start(
            "noise_volume", self._NUDGE_NOISE_START, self._NUDGE_NOISE_TARGET, fade_secs
        )
        # Signal control panel to launch; it will own the subprocess.
        self._write_live({"_agent_launch_display": True})
        print(
            f"[Agent] Nudge started — session='{self._cfg.nudge_session}' "
            f"fading over {self._cfg.nudge_fade_minutes:.0f} min  reason: {reason}"
        )

    def _nudge_advance(self) -> bool:
        """Increment nudge opacity one step. Returns True when complete."""
        profile = _load_profile()
        nudge = profile.get("engagement", {}).get("pending_nudge")
        if not nudge:
            return True

        started_at = nudge.get("started_at", time.time())
        elapsed = time.time() - started_at
        fade_secs = self._cfg.nudge_fade_minutes * 60.0

        # ── Transition phase ──────────────────────────────────────────────────
        # Entered after response; RampEngine is smoothly walking opacity to 100.
        if nudge.get("transition_started_at"):
            t_elapsed = time.time() - nudge["transition_started_at"]
            if t_elapsed >= 90.0 or "window_opacity" not in self._ramp.active_keys:
                print(
                    "[Agent] Nudge transition complete — handing off to session loop."
                )
                return True
            return False  # still ramping; check again next idle tick

        # ── Response detection ────────────────────────────────────────────────
        state = self._read_live()
        response = state.get("user_response")
        resp_ts = float(state.get("response_timestamp") or 0)
        if resp_ts > nudge.get("started_at", 0) and response is not None:
            nudge["responded"] = True
            nudge["response"] = response
            nudge["transition_started_at"] = time.time()
            _USER_PROFILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            self._clear_message()
            # Ghost ramps have finished or are irrelevant now — cancel any remnants
            self._ramp.cancel("volume")
            self._ramp.cancel("noise_volume")
            # Smooth ramp to full opacity over 90 s — buys time for LLM warmup
            cur_opacity = float(
                state.get("window_opacity") or self._NUDGE_OPACITY_TARGET
            )
            self._ramp.start("window_opacity", cur_opacity, 100, 90.0)
            # Enable images and make window interactive immediately
            self._write_live({"bg_mode": None, "window_click_through": False})
            print(
                f"[Agent] Nudge response: {response!r} — transition ramp started (90 s)."
            )
            return False

        # ── Invitation trigger (ghost fade complete) ──────────────────────────
        if elapsed >= fade_secs and not nudge.get("invitation_sent"):
            invite = self._generate_nudge_invitation(nudge.get("reason", ""))
            self._say(
                invite,
                overlay=True,
                console=True,
                tts=True,
                needs_response=False,
                style={"voice_mode": "tts", "zoom_speed": "slow", "intensity": "soft"},
                timeout_s=120,
            )
            self._write_live({"window_click_through": False})
            nudge["invitation_sent"] = True
            _USER_PROFILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            print("[Agent] Nudge invitation sent.")

        # ── Hard cap ─────────────────────────────────────────────────────────
        max_secs = self._cfg.nudge_max_session_minutes * 60.0
        if elapsed >= max_secs:
            print(f"[Agent] Nudge timed out after {elapsed / 60:.1f} min — closing.")
            self._ramp.cancel("window_opacity")
            self._ramp.cancel("volume")
            self._ramp.cancel("noise_volume")
            self._clear_message()
            self._write_live(
                {
                    "window_opacity": self._NUDGE_OPACITY_START,
                    "window_click_through": True,
                    "_agent_stop_display": True,
                }
            )
            nudge["timed_out"] = True
            _USER_PROFILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            return True

        return False

    def _nudge_clear(self) -> None:
        profile = _load_profile()
        profile.setdefault("engagement", {})["pending_nudge"] = None
        _USER_PROFILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    # ── Idle planning cycle ───────────────────────────────────────────────────

    def _idle_planning_cycle(self, mode: str = "idle") -> None:
        print(f"[Agent] Idle planning cycle (mode={mode}).")
        knowledge = _load_idle_knowledge() if self._cfg.inject_knowledge else ""
        messages = [
            {
                "role": "system",
                "content": _IDLE_SYSTEM + (f"\n\n{knowledge}" if knowledge else ""),
            },
            {"role": "user", "content": self._build_planning_prompt(mode)},
        ]
        try:
            raw = self._llm.chat(messages)
            result = _extract_json(raw)
        except Exception as e:
            print(f"[Agent] Idle planning LLM error: {e}")
            return

        reason = result.get("reasoning", "")

        # Support both legacy "action" (single string) and new "actions" (list)
        action_list: list[str] = []
        if isinstance(result.get("actions"), list):
            action_list = [str(a) for a in result["actions"] if a]
        if not action_list:
            action_list = [result.get("action", "none")]
        action_list = [a for a in action_list if a and a != "none"]

        print(f"[Agent] Idle actions={action_list}  reasoning: {reason}")

        # Optional tool call (one per cycle)
        tc = result.get("tool_call")
        if isinstance(tc, dict) and tc.get("tool"):
            try:
                from content_tools import dispatch

                tool_result = dispatch(tc["tool"], tc.get("args") or {})
                print(
                    f"[Agent] Idle tool result: {json.dumps(tool_result, default=str)[:300]}"
                )
            except Exception as tc_exc:
                print(f"[Agent] Idle tool error: {tc_exc}")

        for action in action_list:
            if action == "nudge":
                if mode == "post_session":
                    print("[Agent] Nudge suppressed — post-session cycle.")
                    continue
                days = self._days_since_last_session()
                if days >= self._cfg.nudge_after_days:
                    self._nudge_start(result.get("nudge_reason", reason))
                else:
                    print(
                        f"[Agent] Nudge suggested but only {days:.1f}d since last session "
                        f"(threshold {self._cfg.nudge_after_days}d). Skipping."
                    )
            elif action == "update_goals":
                self._apply_goal_updates(result.get("goal_updates", []))
            elif action == "generate_content":
                # Support both legacy single request and new list
                requests = result.get("content_requests")
                if isinstance(requests, list):
                    for req in requests:
                        self._request_idle_content(req)
                else:
                    self._request_idle_content(result.get("content_request", {}))
            elif action == "create_session":
                intent = result.get("session_intent", "").strip()
                if intent:
                    print(f"[Agent] Autonomous session creation: {intent!r}")
                    self._build_session_from_console(intent)
                else:
                    print(
                        "[Agent] create_session action missing session_intent — skipping."
                    )
                    self._say(
                        "I wanted to create a session but wasn't sure what to make. "
                        "Tell me what you need.",
                        overlay=False,
                        console=True,
                        tts=False,
                    )
            elif action == "author_recon_content":
                self._author_recon_content(result.get("recon_content") or {})

        if not action_list:
            print("[Agent] Idle planning: no actions needed.")

        # ── Post-session palette annotation ───────────────────────────────────
        # Process LLM palette_annotations output: a list of dicts, one per chord.
        # Each dict: {id: int, state_type: str, family: str, notes: str}
        if mode == "post_session":
            palette_annots = (
                result.get("palette_annotations") if isinstance(result, dict) else None
            )
            if isinstance(palette_annots, list) and palette_annots:
                try:
                    from content_tools.somna_db import annotate_palette_entry

                    for ann in palette_annots:
                        eid = ann.get("id")
                        if not eid:
                            continue
                        annotate_palette_entry(
                            entry_id=int(eid),
                            state_type=ann.get("state_type"),
                            family=ann.get("family"),
                            notes=ann.get("notes"),
                            confidence=0.8,
                        )
                        print(
                            f"[Palette] Annotated entry id={eid} "
                            f"family={ann.get('family')!r} "
                            f"state={ann.get('state_type')!r}"
                        )
                except Exception as _pan_e:
                    print(f"[Palette] Annotation error: {_pan_e}")

        # ── Post-session agent annotation ─────────────────────────────────────
        # Write the LLM's reasoning as agent_notes on the most recent
        # session_metrics row for this session.  No-op when EEG wasn't active
        # (session_metrics row won't exist).
        if mode == "post_session" and self._last_ended_session and reason:
            try:
                from content_tools.somna_db import update_latest_session_notes

                update_latest_session_notes(self._last_ended_session, reason[:1000])
                print(
                    f"[Agent] Annotated session_metrics for {self._last_ended_session!r}."
                )
            except Exception as _ann_e:
                print(f"[Agent] Session annotation error: {_ann_e}")

        # ── Session suggestion ────────────────────────────────────────────────
        # Write a session_suggestion to live_control.json if a protocol session
        # hasn't been run recently. The control panel displays it in the UI.
        self._maybe_write_session_suggestion()

    def _author_recon_content(self, rc: dict) -> None:
        """Write retrieve/update phrase pairs for a reconsolidation target trace.

        Called from _idle_planning_cycle when action='author_recon_content'.
        Writes to the session's affirmations.txt using mode='replace' so each
        idle cycle can refine the content without accumulating duplicates.
        """
        session = (rc.get("session") or "").strip()
        trace = (rc.get("trace") or "").strip().lower().replace(" ", "_")
        retrieve = [
            str(p).strip().rstrip(".,!?;:")
            for p in (rc.get("retrieve_phrases") or [])
            if str(p).strip()
        ]
        update = [
            str(p).strip().rstrip(".,!?;:")
            for p in (rc.get("update_phrases") or [])
            if str(p).strip()
        ]

        if not session or not trace or not retrieve or not update:
            print(
                f"[Agent] author_recon_content: incomplete data — "
                f"session={session!r} trace={trace!r} "
                f"retrieve={len(retrieve)} update={len(update)}"
            )
            return

        try:
            from content_tools.affirmations import write_affirmations

            write_affirmations(
                session, f"recon_retrieve_{trace}", retrieve, mode="replace"
            )
            write_affirmations(session, f"recon_update_{trace}", update, mode="replace")
            print(
                f"[Agent] Authored recon content: session={session!r} trace={trace!r} "
                f"({len(retrieve)} retrieve, {len(update)} update phrases)"
            )
            # Record intent in profile notes
            note = (
                f"Reconsolidation protocol authored for trace '{trace}' in session "
                f"'{session}' — {len(retrieve)} retrieve + {len(update)} update phrases."
            )
            self._update_profile({"note": note})
        except Exception as e:
            print(f"[Agent] author_recon_content error: {e}")

    def _maybe_write_session_suggestion(self) -> None:
        """Write or clear session_suggestion in live_control.json."""
        try:
            import datetime
            from content_tools.somna_db import get_all_session_meta

            meta = get_all_session_meta()
            best_name = None
            best_days = 0.0
            for name, info in meta.items():
                cat = info.get("category", "general")
                if cat in ("genus", "edison", "ssild", "sleep", "entrainment"):
                    last = info.get("last_played")
                    if last:
                        try:
                            dt = datetime.datetime.fromisoformat(last)
                            days = (
                                datetime.datetime.now() - dt
                            ).total_seconds() / 86400
                        except Exception:
                            continue
                    else:
                        days = 999.0
                    if days > best_days:
                        best_days = days
                        best_name = name
            if best_name and best_days >= 5:
                info = meta[best_name]
                cat = info.get("category", "session").title()
                day_str = f"{int(best_days)} days" if best_days < 99 else "a while"
                self._write_live(
                    {
                        "session_suggestion": {
                            "text": f"You haven't run a {cat} session in {day_str}. Want one?",
                            "session": best_name,
                            "ts": time.time(),
                        }
                    }
                )
            else:
                # Clear stale suggestion
                state = self._read_live()
                if state.get("session_suggestion"):
                    self._write_live({"session_suggestion": None})
        except Exception as e:
            print(f"[Agent] session_suggestion check failed: {e}")

    # ── Console input handling ────────────────────────────────────────────────

    def _handle_console_input(self, state: dict, text: str) -> None:
        """Handle a direct console message from the user (active or idle mode)."""
        print(f"[Agent] Console input: {text!r}")
        # Clear the input from live_control immediately so it isn't reprocessed
        self._write_live({"user_console_input": None})

        # Use the instance flag, not session_time, which can be stale from a closed display.
        is_active = self._display_active
        session_time = float(state.get("session_time", 0) or 0)

        # ── Direct command: fractionate ────────────────────────────────────
        if any(kw in text.lower() for kw in ("fractionate", "fractionation")):
            if not is_active:
                self._say(
                    "No session is running — start a session first.",
                    overlay=False,
                    console=True,
                    tts=False,
                )
                return
            if state.get("fractionation_active"):
                self._say(
                    "Already fractionating.", overlay=False, console=True, tts=False
                )
                return
            self._write_live({"_timeline_cmd": "fractionate"})
            self._say(
                "Beginning fractionation…", overlay=False, console=True, tts=False
            )
            return

        profile_ctx = self._profile_context()

        # Post-sleep debrief (Bible Ch.9 §9.1) — consume and clear on first console contact
        debrief_ctx = ""
        debrief = state.get("pending_sleep_debrief")
        if isinstance(debrief, dict) and debrief:
            self._write_live({"pending_sleep_debrief": None})
            dist = debrief.get("stage_distribution") or {}
            n2m = dist.get("N2", 0) // 60
            n3m = dist.get("N3", 0) // 60
            totm = debrief.get("elapsed_sleep_s", 0) // 60
            htw = debrief.get("htw_count", 0)
            htw_s = debrief.get("htw_success_count", 0)
            tmr = debrief.get("tmr_replay_count", 0)
            focus = debrief.get("recommended_focus_pool", "")
            debrief_ctx = (
                "\n\n[SLEEP SESSION DATA — for your silent planning context]\n"
                f"A sleep session ended recently: session={debrief.get('session_id')!r}, "
                f"total_sleep={totm}min, N2={n2m}min, N3={n3m}min.\n"
                + (
                    f"Hypnagogic training: {htw} window(s), {htw_s} deepened naturally "
                    f"(N2 returned), {htw - htw_s} timed out.\n"
                    if htw
                    else ""
                )
                + (f"TMR cues replayed: {tmr}.\n" if tmr else "")
                + (f"Recommended next focus pool: {focus}.\n" if focus else "")
                + "Use your judgment: surface this warmly if the user's message is "
                "relevant (e.g. asking how they slept, what was worked on, etc.), "
                "or absorb it silently for your own planning. Never read stats robotically."
            )

        session_ctx = ""
        if is_active:
            session_ctx = (
                f"\nActive session running: beat={state.get('beat_frequency')}Hz, "
                f"session_time={session_time:.0f}s, "
                f"label={state.get('timeline_label')!r}."
            )

        if is_active:
            context_block = (
                "A session is currently active." + session_ctx + "\n\n"
                "You are the live session guide. Respond to the user naturally. "
                "You may also adjust session parameters via 'adjustments'."
            )
        else:
            context_block = (
                "⚠ NO SESSION IS RUNNING. The display is not open.\n"
                "You cannot guide the user into trance until a session is launched. "
                "If the user asks to start a session, feel deeply relaxed, go under, "
                "be guided, or anything similar — you MUST set action to 'start_session'. "
                "If the user asks you to CREATE, MAKE, BUILD, or WRITE a new session "
                "(e.g. 'make a session about X', 'build me something for Y') — set "
                "action to 'build_session' and set 'session_intent' to a clear description "
                "of what the session should do. You will acknowledge and build it. "
                "Do NOT roleplay as if a session is happening when none is active.\n\n"
                "Available sessions: 'default' (or any name the user specifies)."
            )

        system_msg = (
            "You are Somna's always-on companion agent — the persistent intelligence "
            "behind a hypnotic entrainment system. The user is speaking to you directly "
            "via the console.\n\n"
            + context_block
            + "\n\nUser profile:\n"
            + profile_ctx
            + debrief_ctx
            + "\n\n"
            "IMPORTANT: You MUST respond with ONLY a JSON object — no prose, no markdown, "
            "no explanation outside the JSON. Structure:\n"
            '{"response": "your reply to show the user", '
            '"action": "none | start_session | build_session", '
            '"session": "folder name (only when action=start_session, default=\'default\')", '
            '"session_intent": "plain-text description (only when action=build_session)", '
            '"adjustments": {<param>: <value>}}\n\n'
            "adjustments: optional session parameter overrides "
            "(beat_frequency, volume, veil_opacity, etc.)."
        )

        # Build messages: system + last 4 console turns (for follow-up awareness) + current
        history_msgs: list[dict] = []
        for turn in self._console_history[-4:]:
            history_msgs.append({"role": "user", "content": turn["user"]})
            history_msgs.append({"role": "assistant", "content": turn["assistant"]})

        try:
            raw = self._llm.chat(
                [{"role": "system", "content": system_msg}]
                + history_msgs
                + [{"role": "user", "content": text}]
            )
            # Scan forwards for the first JSON with a "response" key — the model
            # sometimes emits a correct object then generates a second follow-up.
            result = _extract_first_json_with_key(raw, "response")
        except Exception as e:
            print(f"[Agent] Console LLM error: {e}")
            self._say(
                "Sorry, something went wrong on my end.",
                overlay=False,
                console=True,
                tts=True,
            )
            return

        response_text = result.get("response", "").strip() or "(no response)"
        action = result.get("action", "none")

        # Store this turn; clear history when a session launches (context resets)
        self._console_history.append({"user": text, "assistant": response_text})
        self._console_history = self._console_history[-8:]  # keep last 8 turns

        print(
            f"[Agent] Console parsed — action={action!r}  is_active={is_active}  "
            f"result_keys={list(result.keys())}"
        )
        print(f"[Agent] Console response: {response_text!r}")

        if is_active:
            # Session is running: response goes to console AND the in-display overlay
            self._say(
                response_text,
                overlay=True,
                tts=False,
                console=True,
                style={
                    "zoom_speed": "slow",
                    "intensity": "soft",
                    "voice_mode": "silent",
                },
                timeout_s=30,
            )
            # Depth-signal detection — if the user's message suggests they're at
            # significant depth, nudge the conductor toward fractionation.
            _DEPTH_SIGNALS = (
                "deep",
                "gone",
                "under",
                "floating",
                "drifting",
                "can't think",
                "blank",
                "empty",
                "lost",
                "slipping",
                "far away",
                "not here",
                "barely",
            )
            if any(sig in text.lower() for sig in _DEPTH_SIGNALS):
                self._maybe_request_fractionation()
        else:
            # No session: console-only (no overlay to show it on)
            self._say(response_text, overlay=False, tts=False)

        # Apply any parameter adjustments
        adj = result.get("adjustments") or {}
        safe = {k: v for k, v in adj.items() if k in _ADJUSTABLE_PARAMS}
        if safe:
            self._write_live(safe)

        # If requested and no display running, start a session
        if action == "start_session":
            if is_active:
                print(
                    "[Agent] Console requested start_session but display already active — skipping launch."
                )
            else:
                session_name = result.get("session", "default")
                print(f"[Agent] Console triggered session start: {session_name!r}")
                self._pending_console_context = (
                    f"User said (via console, before session launched): {text!r}\n"
                    f"Agent replied: {response_text!r}"
                )
                # Signal control panel to launch the display; also push the response as
                # an overlay message so it's visible when the window opens.
                self._write_live(
                    {
                        "session_folder": session_name,
                        "_timeline_cmd": "load",
                        "_agent_launch_display": True,
                    }
                )
                self._say(
                    response_text,
                    overlay=True,
                    console=False,
                    tts=False,
                    style={
                        "needs_response": False,
                        "voice_mode": "silent",
                        "zoom_speed": "slow",
                        "intensity": "soft",
                    },
                    timeout_s=60,
                )
                self._display_active = True
                self._display_launch_at = time.time()

        # Build a new session on demand
        if action == "build_session":
            intent = result.get("session_intent", text).strip() or text
            self._build_session_from_console(intent)

    # ── Fractionation phrases ────────────────────────────────────────────────

    # Aphantasia-safe emergence prompts (somatic/auditory only — no imagery).
    # Rotate through one per emergence; cycle restarts after the last.
    _EMERGE_PROMPTS = [
        "Notice where your body meets the surface beneath you.",
        "Feel the temperature of the air on your skin.",
        "Hear the sounds in the room — just for a moment.",
        "Notice the weight of your hands.",
        "Feel your breath — just the physical sensation of it.",
    ]

    # Re-induction phrases — pick ONE per session and reuse across cycles.
    # Repetition is the mechanism: the phrase becomes a conditioned cue.
    _REINDUCE_PROMPTS = [
        "And you can let that go now… sinking back…",
        "The weight returns… heavier than before…",
        "Each breath pulling you back down… easier this time…",
        "You know the way now… let yourself follow it…",
        "Settling… deeper than before… effortless…",
    ]

    def _on_frac_phase(self, phase: str) -> None:
        """Deliver TTS anchors at Vogt fractionation phase transitions.

        EMERGE: one somatic orientation prompt per emergence (rotates).
        REINDUCE: the same re-induction cue chosen at session start (conditioned).
        INDUCTION / HOLD: silent — let the entrainment work.
        DEEP: silent during the therapeutic window; the agent tick handles it.
        complete: a brief settling acknowledgement.
        """
        # Lazy-init per-session phrase state
        if not hasattr(self, "_frac_emerge_idx"):
            self._frac_emerge_idx = 0
            self._frac_reinduce_idx = hash(
                str(
                    self._session_start_time
                    if hasattr(self, "_session_start_time")
                    else id(self)
                )
            ) % len(self._REINDUCE_PROMPTS)

        if phase.startswith("EMERGE"):
            idx = self._frac_emerge_idx % len(self._EMERGE_PROMPTS)
            prompt = self._EMERGE_PROMPTS[idx]
            self._frac_emerge_idx += 1
            self._say(
                prompt,
                overlay=False,
                console=False,
                tts=True,
                style={"voice_mode": "tts", "needs_response": False},
                timeout_s=None,
            )

        elif phase.startswith("REINDUCE"):
            prompt = self._REINDUCE_PROMPTS[self._frac_reinduce_idx]
            self._say(
                prompt,
                overlay=False,
                console=False,
                tts=True,
                style={"voice_mode": "tts", "needs_response": False},
                timeout_s=None,
            )

        elif phase.startswith("DEEP"):
            # Therapeutic window: plant a single subliminal affirmation, no voice
            cycle_n = phase.split("_")[-1] if "_" in phase else "1"
            print(f"[Agent] Fractionation DEEP window — cycle {cycle_n}.")

        elif phase == "complete":
            # Reset per-session phrase state for next fractionation
            self._frac_emerge_idx = 0
            self._say(
                "Good…",
                overlay=False,
                console=False,
                tts=True,
                style={"voice_mode": "tts", "needs_response": False},
                timeout_s=None,
            )
            print("[Agent] Fractionation complete.")

    # ── Unified messaging helpers ─────────────────────────────────────────────

    def _say(
        self,
        text: str,
        *,
        needs_response: bool = False,
        overlay: bool = True,
        console: bool = True,
        tts: bool = True,
        style: dict | None = None,
        timeout_s: float | None = 20.0,
    ) -> str | None:
        """Send a message to the user through all requested channels.

        Writes ``agent_message`` to live_control.json and optionally blocks
        for a user response.

        Parameters
        ----------
        text          : The message text.
        needs_response: If True, the control panel opens an input dialog and
                        this call blocks until the user submits or times out,
                        returning the response string (or None if skipped).
        overlay       : Show text in the in-display zoom overlay.
        console       : Append to the control-panel console log.
        tts           : Speak the text via TTS.
        style         : llm_prompt_style overrides (zoom_speed, intensity, etc.)
        timeout_s     : Dialog countdown / overlay dwell (None = no timeout).
        """
        resolved_style = dict(style or {})
        resolved_style["needs_response"] = needs_response
        if not tts:
            resolved_style.setdefault("voice_mode", "silent")

        via: list[str] = []
        if console:
            via.append("console")
        if overlay:
            via.append("overlay")
        if tts:
            via.append("tts")

        msg_ts = time.time()
        patch: dict = {
            "agent_message": {
                "text": text,
                "ts": msg_ts,
                "needs_response": needs_response,
                "via": via,
                "style": resolved_style,
                "timeout_s": timeout_s,
            },
        }
        self._last_msg_ts = msg_ts
        if needs_response:
            patch["user_response"] = None
            patch["response_timestamp"] = None

        # Audio duck / pattern interrupt — arm duck when style includes duck=True
        if resolved_style.get("duck"):
            patch["tts_duck_trigger"] = "next"
            duck_raw = resolved_style.get("tts_duck_ms", 120)
            try:
                patch["tts_duck_ms"] = max(0, min(200, int(duck_raw)))
            except (TypeError, ValueError):
                patch["tts_duck_ms"] = 120

        self._write_live(patch)

        if needs_response:
            from agent.llm_driver import wait_for_response as _wait

            return _wait(timeout_s=float(timeout_s or 120) + 5.0)
        return None

    def _clear_message(self) -> None:
        """Clear the active agent message — only if it is still ours (ts match)."""
        live = self._read_live()
        cur = live.get("agent_message") or {}
        if isinstance(cur, dict) and cur.get("ts") == getattr(
            self, "_last_msg_ts", None
        ):
            self._write_live({"agent_message": None})

    # ── Session builder ───────────────────────────────────────────────────────

    def _build_session_from_console(self, intent: str) -> None:
        """Run the session creation pipeline for a console-triggered intent.

        Launches a daemon thread so the main loop stays responsive during the
        4+ LLM calls (can take 5-10 minutes).  Acknowledgment is immediate;
        the result is written back when the thread completes.
        """
        if self._session_build_active:
            self._say(
                "Already building a session — hang on, it takes a few minutes.",
                overlay=False,
                tts=False,
            )
            return

        print(f"[Agent] Building session: {intent!r}")
        self._say(
            f"On it. Writing a session for: {intent!r} — this will take a minute.",
            style={"zoom_speed": "slow", "intensity": "soft", "voice_mode": "normal"},
            timeout_s=20,
        )

        self._session_build_active = True
        profile_ctx = self._profile_context()
        llm_url = self._llm._cfg.base_url
        llm_model = self._llm._cfg.model or ""

        def _worker() -> None:
            try:
                from content_tools.session_pipeline import run_session_creation_cycle

                result = run_session_creation_cycle(
                    intent=intent,
                    profile_ctx=profile_ctx,
                    llm_url=llm_url,
                    llm_model=llm_model,
                )
            except Exception as exc:
                self._say(
                    f"Session creation failed: {exc}",
                    style={"voice_mode": "normal"},
                    timeout_s=15,
                )
                return
            finally:
                self._session_build_active = False

            status = result.get("status")
            name = result.get("session_name", "")
            brief = result.get("brief") or {}

            if status == "created":
                msg = (
                    f"Done. '{brief.get('title', name)}' is ready as '{name}'. "
                    "Say 'start it' to launch."
                )
                self._write_live({"session_folder": name, "_timeline_cmd": "load"})
            elif status == "failed_review":
                scores = result.get("review_scores") or {}
                msg = (
                    f"Built but failed review after {result.get('attempts', '?')} attempt(s). "
                    f"Issue: {scores.get('failure_note', 'unknown')}. "
                    "Try asking again with more detail."
                )
            else:
                msg = (
                    f"Session creation stopped at '{status}': {result.get('notes', '')}"
                )

            self._say(
                msg,
                style={
                    "zoom_speed": "slow",
                    "intensity": "soft",
                    "voice_mode": "normal",
                },
                timeout_s=30,
            )
            print(
                f"[Agent] Session build complete: status={status!r}  session={name!r}"
            )

        self._session_build_thread = threading.Thread(
            target=_worker, daemon=True, name="SessionBuilder"
        )
        self._session_build_thread.start()

    # ── Idle tick (replaces bare sleep when display is not active) ────────────

    def _idle_tick(self, state: dict) -> None:
        """One idle-mode cycle: console check, nudge advance, planning."""
        # Console input: check and handle immediately
        console_text = state.get("user_console_input") or ""
        console_ts = float(state.get("user_console_ts", 0) or 0)
        if console_text and console_ts > self._console_ts:
            self._console_ts = console_ts
            self._handle_console_input(state, console_text)

        # Nudge: advance if one is active (including the post-response transition phase)
        self._profile = _load_profile()
        pending = self._profile.get("engagement", {}).get("pending_nudge")
        if pending and not pending.get("timed_out"):
            done = self._nudge_advance()
            if done:
                self._nudge_clear()
            # Don't run planning while a nudge is active
            self._idle_sleep()
            return

        # Planning: immediate post-session cycle OR scheduled interval
        now = time.time()
        interval_s = self._cfg.idle_planning_interval_min * 60.0
        if self._post_session_pending:
            self._post_session_pending = False
            try:
                self._idle_planning_cycle(mode="post_session")
            except Exception as e:
                print(f"[Agent] Post-session planning error: {e}")
            self._idle_last_plan = time.time()
        elif now - self._idle_last_plan >= interval_s:
            try:
                self._idle_planning_cycle(mode="idle")
            except Exception as e:
                print(f"[Agent] Idle planning error: {e}")
            self._idle_last_plan = time.time()

        self._idle_sleep()

    def _idle_sleep(self) -> None:
        """Sleep between idle ticks in 5-second slices for console responsiveness."""
        sleep_total = min(self._cfg.idle_planning_interval_min * 60.0, 30.0)
        deadline = time.time() + sleep_total
        while time.time() < deadline:
            time.sleep(5.0)
            # Re-check console input while sleeping
            live = self._read_live()
            ct = float(live.get("user_console_ts", 0) or 0)
            if (live.get("user_console_input") or "") and ct > self._console_ts:
                self._console_ts = ct
                self._handle_console_input(live, live["user_console_input"])
                break

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        print(
            f"[Agent] Starting — mode={self._cfg.mode}  "
            f"model={self._cfg.model}  interval={self._cfg.interval}s"
        )
        print("[Agent] Press Ctrl+C to stop.\n")

        # First-run onboarding — fires before the main loop, no display needed.
        # Only runs when the profile is completely empty (brand-new installation).
        if self._is_first_run():
            try:
                self._onboarding_flow()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[Agent] Onboarding error (non-fatal): {e}")
        elif not self._profile.get("aphantasia"):
            # Existing user but no imagery profile — ask once before the main loop.
            try:
                self._imagery_detection_flow()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[Agent] Imagery detection error (non-fatal): {e}")

        # Clear any pending_nudge left over from a previous agent process.
        # A nudge is a live operation — if the agent died mid-nudge, the nudge
        # is already gone and firing it immediately on restart is wrong.
        _stale = self._profile.get("engagement", {}).get("pending_nudge")
        if _stale:
            print("[Agent] Clearing stale nudge from previous run.")
            self._nudge_clear()

        last_session = None
        first_tick = True
        _prev_display_active = False  # for summary trigger on closure
        _last_session_stime = 0.0  # most recent session_time we saw
        _frac_phase = ""  # last fractionation_phase we handled
        _content_check_at = 0.0  # wall time of most recent content check
        # Display-closure detection: track session_time + wall clock.
        # Seed from the current live state so the very first comparison is
        # meaningful — avoids the -1 → 0 delta that would falsely declare
        # the display active before any session has started.
        _initial_state = self._read_live()
        _last_stime = float(_initial_state.get("session_time", 0) or 0)
        _last_stime_wall = time.time()
        # Start pessimistic: live_control.json may hold a stale session_time from
        # a previous session.  The display is confirmed active only when
        # session_time is observed to *advance* between ticks.
        # Exception: if session_time is non-zero, do a quick 3 s re-read.  If it
        # has changed the display is definitively running right now.
        _display_active = False
        # When the console triggers a session launch, we stamp this so the stale
        # check doesn't immediately flip _display_active back to False before
        # session_time has started advancing (display takes ~5 s to open).
        _display_launch_at: float = 0.0
        if _last_stime > 0:
            time.sleep(3.0)
            _recheck = self._read_live()
            _rstime = float(_recheck.get("session_time", 0) or 0)
            if _rstime != _last_stime and _rstime > 0:
                _display_active = True
                _last_stime = _rstime
                _last_stime_wall = time.time()
                print("[Agent] Display detected active on startup.")
        # Session-change debounce: require 10 s of stable new session_folder
        # before re-arming history/startup.  Prevents live→default→live flicker
        # (caused by display startup race) from triggering double greetings.
        _pending_session: str | None = None
        _pending_session_since: float = 0.0
        # Tracks whether last_session was reset after a real first startup
        # (never committed anything) vs. re-armed mid-run (restart/resume).
        # On re-arm, skip the "commit immediately" path and use the normal debounce
        # so a transient wrong session_folder never hijacks an in-progress session.
        _ever_committed_session: bool = False

        while True:
            state = self._read_live()
            session = state.get("session_folder", "default")

            # ── Detect display closure via stale session_time ──────────────
            # If session_time hasn't advanced in 60 s and timeline isn't
            # deliberately paused, assume the display process has exited.
            stime = float(state.get("session_time", 0) or 0)
            paused = bool(state.get("timeline_paused", False))
            now = time.time()
            if stime != _last_stime and stime > 0:
                # session_time is advancing — display is live
                _last_stime = stime
                _last_stime_wall = now
                # Detect session restart: time dropped significantly while display
                # stayed active (stop+start without the process ever going inactive).
                if _last_session_stime > 60 and stime < _last_session_stime - 30:
                    print(
                        "[Agent] Session restart detected — re-arming startup sequence."
                    )
                    first_tick = True
                    last_session = None
                    # Seed debounce with current session so the 5 s clock starts now;
                    # the re-arm path won't commit until it's been stable that long.
                    _pending_session = session
                    _pending_session_since = now
                    if self._conductor is not None:
                        try:
                            self._conductor.finalize()
                        except Exception:
                            pass
                        self._conductor = None
                    if self._conditioning is not None:
                        try:
                            self._conditioning.end_session()
                        except Exception:
                            pass
                        self._conditioning = None
                    if self._habituation is not None:
                        try:
                            self._habituation.on_session_end()
                        except Exception:
                            pass
                        self._habituation = None
                    # ── Session Director teardown (Bible Ch.5 §5.5) ──────────────────
                    if self._director is not None and self._session_plan is not None:
                        try:
                            import content_tools.somna_db as _sdb
                            from session.session_evaluator import SessionEvaluator

                            evaluator = SessionEvaluator(db=_sdb)
                            session_log = self._director.export_session_log()
                            outcome = evaluator.evaluate(
                                self._session_plan, session_log
                            )
                            print(
                                f"[Agent] Session score: {outcome.session_score:.3f} "
                                f"(depth={outcome.depth_score:.2f} "
                                f"stability={outcome.stability_score:.2f})"
                            )
                        except Exception as _eval_e:
                            print(f"[Agent] SessionEvaluator failed: {_eval_e}")
                        self._director = None
                        self._session_plan = None
                _last_session_stime = stime
                if not _display_active:
                    print("[Agent] Display resumed — returning to active mode.")
                    # Re-arm startup sequence so a fresh greeting fires
                    first_tick = True
                    last_session = None
                    _pending_session = session
                    _pending_session_since = now
                _display_active = True
            elif stime == _last_stime and stime == 0:
                # session_time is zero and hasn't moved — but don't flip inactive
                # during a launch grace window (display is opening, stime starts at 0).
                _display_launch_at = max(_display_launch_at, self._display_launch_at)
                if (now - _display_launch_at) >= 60.0:
                    _display_active = False
            elif not paused and (now - _last_stime_wall) > 180.0 and stime > 0:
                # Pull in any launch timestamp set by _handle_console_input before
                # evaluating the grace window (avoids off-by-one-tick race).
                _display_launch_at = max(_display_launch_at, self._display_launch_at)
                in_launch_grace = (now - _display_launch_at) < 60.0
                if not in_launch_grace:
                    if _display_active:
                        print(
                            "[Agent] Session time stale for 60 s — display appears "
                            "closed.  Entering idle mode."
                        )
                    _display_active = False

            self._display_active = _display_active  # keep instance var in sync
            _display_launch_at = max(_display_launch_at, self._display_launch_at)

            # ── Post-session summary on display closure ─────────────────────
            # Guard: only fire when the session ran for at least 2 minutes.
            # This prevents a spurious early-staleness detection mid-session from
            # consuming the True→False edge and silencing the real end-of-session
            # summary.
            _SUMMARY_MIN_DURATION = 120.0
            if _prev_display_active and not _display_active:
                if _last_session_stime >= _SUMMARY_MIN_DURATION:
                    print(
                        f"[Agent] Post-session summary triggered "
                        f"(duration={_last_session_stime:.0f}s)."
                    )
                    try:
                        self._post_session_summary(
                            session_name=last_session or "unknown",
                            duration_s=_last_session_stime,
                        )
                    except Exception as e:
                        print(f"[Agent] Post-session summary error: {e}")
                    self._post_session_pending = True
                else:
                    print(
                        f"[Agent] Session too short ({_last_session_stime:.0f}s) "
                        f"— skipping summary."
                    )
            _prev_display_active = _display_active

            if not _display_active:
                # Display is not running — run idle tick (planning, nudge, console)
                self._idle_tick(state)
                continue

            # ── Session-change detection ────────────────────────────────────
            # True first startup (never committed): commit immediately.
            # Re-arm after restart/resume: use the normal 5 s debounce so a
            # transient wrong session_folder never hijacks an in-progress session.
            if last_session is None:
                if not _ever_committed_session:
                    # Genuine first commit — no debounce needed
                    self._log = SessionLog(session)
                    self._history = self._log.load_today()
                    last_session = session
                    _ever_committed_session = True
                    _pending_session = None
                    # Detect whether this is a fresh start or a quick restart
                    gap_min = 0.0
                    if self._history:
                        gap_min = (time.time() - self._history[-1].timestamp) / 60.0
                    self._fresh_start = (not self._history) or (gap_min > 30.0)
                    self._startup_gap_min = gap_min
                    print(
                        f"[Agent] Session: {session!r}  "
                        f"({len(self._history)} exchanges in log today)  "
                        f"fresh_start={self._fresh_start}  gap={gap_min:.0f}min"
                    )
                else:
                    # Re-armed after restart/resume: debounce to absorb transients
                    if session != _pending_session:
                        _pending_session = session
                        _pending_session_since = now
                    elif now - _pending_session_since >= 5.0:
                        self._log = SessionLog(session)
                        self._history = self._log.load_today()
                        last_session = session
                        _pending_session = None
                        gap_min = 0.0
                        if self._history:
                            gap_min = (time.time() - self._history[-1].timestamp) / 60.0
                        self._fresh_start = (not self._history) or (gap_min > 30.0)
                        self._startup_gap_min = gap_min
                        print(
                            f"[Agent] Session: {session!r}  "
                            f"({len(self._history)} exchanges in log today)  "
                            f"fresh_start={self._fresh_start}  gap={gap_min:.0f}min"
                        )
            elif session != last_session:
                if session != _pending_session:
                    # First time we see this new value — start the debounce clock
                    _pending_session = session
                    _pending_session_since = now
                elif now - _pending_session_since >= 30.0:
                    # New session has been stable for 30 s — commit the switch
                    self._log = SessionLog(session)
                    self._history = self._log.load_today()
                    last_session = session
                    _pending_session = None
                    self._skip_streak = 0
                    self._silent_turns = 0
                    gap_min = 0.0
                    if self._history:
                        gap_min = (time.time() - self._history[-1].timestamp) / 60.0
                    self._fresh_start = (not self._history) or (gap_min > 30.0)
                    self._startup_gap_min = gap_min
                    if not first_tick:
                        first_tick = True
                    print(
                        f"[Agent] Session: {session!r}  "
                        f"({len(self._history)} exchanges in log today)"
                    )
                # else: still within debounce window — keep last_session as-is
            else:
                _pending_session = None  # back to known session, discard pending

            # Startup sequence: greet user + gather initial needs.
            # Held until session_time >= startup_delay_s so the binaural beats
            # have had time to work before the first question arrives.
            live_mode = state.get("agent_mode", self._cfg.mode)
            if first_tick and live_mode == "interactive":
                session_time = float(state.get("session_time", 0) or 0)
                g = self._startup_gap_min
                if g < 2.0 and self._history:
                    effective_delay = 5.0  # SILENT — beats were just running
                elif self._history:
                    effective_delay = 10.0  # RETURNING — short re-establish window
                else:
                    effective_delay = self._cfg.startup_delay_s  # FRESH — full delay
                delay = effective_delay
                if session_time < delay:
                    # Guard: if session_time has been 0 for longer than 90 s
                    # the display almost certainly closed before the session started.
                    # Abort the wait so we don't loop forever on a dead session.
                    if session_time == 0:
                        if not hasattr(self, "_startup_wait_since"):
                            self._startup_wait_since = now
                        elif (now - self._startup_wait_since) > 90.0:
                            print(
                                "[Agent] session_time stuck at 0 for 90 s — "
                                "display appears closed. Aborting startup wait."
                            )
                            first_tick = False
                            if hasattr(self, "_startup_wait_since"):
                                del self._startup_wait_since
                            continue
                    else:
                        if hasattr(self, "_startup_wait_since"):
                            del self._startup_wait_since
                    remaining = delay - session_time
                    print(
                        f"[Agent] Waiting for startup delay "
                        f"({session_time:.0f}s / {delay:.0f}s) — "
                        f"{remaining:.0f}s remaining…"
                    )
                    time.sleep(min(self._cfg.interval, 10.0))
                    continue  # re-poll until delay has elapsed
                first_tick = False
                if hasattr(self, "_startup_wait_since"):
                    del self._startup_wait_since
                try:
                    self._startup_sequence(state)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(f"[Agent] Startup error: {e}")
                    first_tick = False
                continue  # re-read state after startup before first real tick

            first_tick = False

            # ── Fractionation phase watcher ─────────────────────────────────
            # Deliver TTS anchor phrases at key phase transitions.
            frac_phase = state.get("fractionation_phase", "") or ""
            if frac_phase and frac_phase != _frac_phase:
                _frac_phase = frac_phase
                try:
                    self._on_frac_phase(frac_phase)
                except Exception:
                    pass

            # Check if agent mode has been overridden via live_control.json
            live_mode = state.get("agent_mode", self._cfg.mode)

            try:
                if live_mode == "interactive":
                    self._interactive_tick(state)
                else:
                    self._observe_tick(state)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[Agent] Tick error: {e}")

            # Keep last_session_date current so the nudge re-engagement threshold
            # stays accurate across sessions.
            try:
                import datetime as _dt

                today = _dt.date.today().isoformat()
                eng = self._profile.get("engagement", {})
                if eng.get("last_session_date") != today:
                    self._update_profile(
                        {
                            "engagement": {
                                "last_session_date": today,
                                "total_sessions": eng.get("total_sessions", 0) + 1,
                            }
                        }
                    )
            except Exception:
                pass

            # Auto-generate content if the session's phrase pool is sparse.
            # Throttled to at most once every 10 minutes to avoid interfering
            # with session pacing and causing spurious startup re-arms.
            _CONTENT_CHECK_INTERVAL = 600.0
            try:
                if time.time() - _content_check_at >= _CONTENT_CHECK_INTERVAL:
                    _content_check_at = time.time()
                    self._check_content_needs(state)
            except Exception as e:
                print(f"[Agent] Content check error: {e}")

            # Console input check (active mode)
            try:
                console_text = state.get("user_console_input") or ""
                console_ts = float(state.get("user_console_ts", 0) or 0)
                if console_text and console_ts > self._console_ts:
                    self._console_ts = console_ts
                    self._handle_console_input(state, console_text)
            except Exception as e:
                print(f"[Agent] Console check error: {e}")

            # Sleep until next tick, checking for Ctrl+C cleanly.
            # Poll at 1 s intervals so pending restores fire on time.
            deadline = time.time() + self._cfg.interval
            try:
                while time.time() < deadline:
                    time.sleep(1.0)
                    self._check_pending_restore()
                    # Also wake early if console input arrives mid-interval
                    live = self._read_live()
                    ct = float(live.get("user_console_ts", 0) or 0)
                    if (live.get("user_console_input") or "") and ct > self._console_ts:
                        self._console_ts = ct
                        self._handle_console_input(live, live["user_console_input"])
            except KeyboardInterrupt:
                raise


# ── CLI entry point ───────────────────────────────────────────────────────────


def _parse_args() -> AgentConfig:
    yaml_cfg = _load_yaml_config()

    p = argparse.ArgumentParser(
        description="Somna LLM Session Agent",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--model", default=yaml_cfg.get("model", "gpt-4o"), help="LLM model name"
    )
    p.add_argument(
        "--api-key",
        default=yaml_cfg.get("api_key", ""),
        help="API key (or set OPENAI_API_KEY env var)",
    )
    p.add_argument(
        "--base-url",
        default=yaml_cfg.get("base_url", "https://api.openai.com/v1"),
        help="OpenAI-compatible API base URL",
    )
    p.add_argument(
        "--mode",
        default=yaml_cfg.get("mode", "interactive"),
        choices=["observe", "interactive"],
        help="observe = silent adaptation; interactive = prompt user",
    )
    p.add_argument(
        "--interval",
        default=yaml_cfg.get("interval", 60),
        type=float,
        help="Seconds between agent evaluation ticks",
    )
    p.add_argument(
        "--prompt-timeout",
        default=yaml_cfg.get("prompt_timeout", 120),
        type=int,
        help="Seconds user has to answer before dialog auto-skips",
    )
    p.add_argument(
        "--max-history",
        default=yaml_cfg.get("max_history", 20),
        type=int,
        help="Max exchanges kept in LLM context window",
    )
    p.add_argument(
        "--system-prompt",
        default=yaml_cfg.get("system_prompt", ""),
        help="Extra operator instructions appended to the system prompt",
    )
    p.add_argument(
        "--training-mode",
        action="store_true",
        default=yaml_cfg.get("training_mode", False),
        help="Enable conditioning mode: track response complexity and reinforce",
    )
    p.add_argument(
        "--training-target",
        default=yaml_cfg.get("training_target", 0.2),
        type=float,
        help="Target complexity score 0.0–1.0 (0=simple/regressed, 1=alert)",
    )
    p.add_argument(
        "--no-knowledge",
        action="store_true",
        default=not yaml_cfg.get("inject_knowledge", True),
        help="Disable knowledge base injection (use for small context-window models)",
    )
    p.add_argument(
        "--startup-delay",
        default=yaml_cfg.get("startup_delay_s", 180.0),
        type=float,
        help="Seconds of session time to wait before the startup greeting fires",
    )
    p.add_argument(
        "--idle-interval",
        default=yaml_cfg.get("idle_planning_interval_min", 30.0),
        type=float,
        help="Minutes between idle planning LLM cycles",
    )
    p.add_argument(
        "--nudge-after-days",
        default=yaml_cfg.get("nudge_after_days", 1.0),
        type=float,
        help="Days since last session before a nudge fires",
    )
    p.add_argument(
        "--nudge-session",
        default=yaml_cfg.get("nudge_session", "live"),
        help="Session folder used for the nudge overlay",
    )
    p.add_argument(
        "--nudge-fade-minutes",
        default=yaml_cfg.get("nudge_fade_minutes", 20.0),
        type=float,
        help="Minutes to ramp nudge opacity from 5%% to 60%%",
    )
    p.add_argument(
        "--nudge-max-session-minutes",
        default=yaml_cfg.get("nudge_max_session_minutes", 45.0),
        type=float,
        help="Hard cap on nudge session length in minutes; display closes if no response",
    )
    # Sampling / backend
    p.add_argument(
        "--top-p",
        default=yaml_cfg.get("top_p", 0.8),
        type=float,
        help="top_p nucleus sampling",
    )
    p.add_argument(
        "--presence-penalty",
        default=yaml_cfg.get("presence_penalty", 1.5),
        type=float,
        help="Presence penalty (reduces repetition)",
    )
    p.add_argument(
        "--enable-thinking",
        action="store_true",
        default=yaml_cfg.get("enable_thinking", False),
        help="Allow model reasoning/thinking blocks (KoboldCpp)",
    )
    p.add_argument(
        "--top-k",
        default=yaml_cfg.get("top_k", 20),
        type=int,
        help="top_k sampling (0 = disabled)",
    )
    p.add_argument(
        "--min-p", default=yaml_cfg.get("min_p", 0.0), type=float, help="min_p sampling"
    )
    p.add_argument(
        "--repeat-penalty",
        default=yaml_cfg.get("repeat_penalty", 1.0),
        type=float,
        help="Repetition penalty",
    )
    p.add_argument(
        "--max-tokens-response",
        default=yaml_cfg.get("max_tokens_response", None),
        type=lambda x: None if x in (None, "null", "none", "") else int(x),
        help="Max tokens per response (null = no cap, server decides)",
    )
    p.add_argument(
        "--reset-profile",
        action="store_true",
        help="Wipe user_profile.json and session_logs/ (backs up profile first), then exit",
    )

    args = p.parse_args()

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print(
            "[Agent] Warning: no API key set. "
            "Pass --api-key or set OPENAI_API_KEY env var."
        )

    return AgentConfig(
        model=args.model,
        api_key=api_key,
        base_url=args.base_url,
        mode=args.mode,
        interval=args.interval,
        max_history=args.max_history,
        system_prompt=args.system_prompt,
        prompt_timeout=args.prompt_timeout,
        training_mode=args.training_mode,
        training_target=args.training_target,
        praise_phrases=yaml_cfg.get("praise_phrases") or None,
        inject_knowledge=not args.no_knowledge,
        knowledge_files=_build_knowledge_files(yaml_cfg),
        startup_delay_s=args.startup_delay,
        idle_planning_interval_min=args.idle_interval,
        nudge_after_days=args.nudge_after_days,
        nudge_session=args.nudge_session,
        nudge_fade_minutes=args.nudge_fade_minutes,
        nudge_max_session_minutes=args.nudge_max_session_minutes,
        eeg_enabled=(yaml_cfg.get("eeg") or {}).get("enabled", True),
        eeg_synthetic=(yaml_cfg.get("eeg") or {}).get("synthetic", False),
        top_p=args.top_p,
        presence_penalty=args.presence_penalty,
        enable_thinking=args.enable_thinking,
        top_k=args.top_k,
        min_p=args.min_p,
        repeat_penalty=args.repeat_penalty,
        max_tokens_response=args.max_tokens_response,
        external_channel=yaml_cfg.get("external_channel", False),
    )


def _run_reset_profile() -> None:
    """Wipe test data: back up user_profile.json, clear session_logs/."""
    import shutil

    backed_up = False
    if _USER_PROFILE.exists():
        backup = _USER_PROFILE.with_suffix(".backup.json")
        shutil.copy2(_USER_PROFILE, backup)
        print(f"[Reset] Profile backed up → {backup}")
        backed_up = True

    blank = {
        "name": None,
        "designations": [],
        "notes": [],
        "goals": [],
        "preferences": {},
        "engagement": {},
        "responsive_themes": [],
        "effective_moments": [],
        "last_session": None,
    }
    _USER_PROFILE.write_text(json.dumps(blank, indent=2), encoding="utf-8")
    print(
        f"[Reset] user_profile.json wiped{' (old profile backed up)' if backed_up else ''}."
    )

    logs_cleared = 0
    if _LOGS.exists():
        for f in _LOGS.glob("*.jsonl"):
            f.unlink()
            logs_cleared += 1
        print(f"[Reset] Cleared {logs_cleared} session log file(s) from {_LOGS}.")
    else:
        print("[Reset] No session_logs/ folder found — nothing to clear.")

    print("\n[Reset] Done. Start fresh whenever you're ready.")


if __name__ == "__main__":
    import sys as _sys

    if "--reset-profile" in _sys.argv:
        _run_reset_profile()
        _sys.exit(0)

    agent = None
    try:
        cfg = _parse_args()
        agent = SomnaAgent(cfg)
        agent.run()
    except KeyboardInterrupt:
        print("\n[Agent] Stopped.")
    finally:
        if agent is not None:
            agent._ramp_stop.set()
            if agent._freq_leader is not None:
                agent._freq_leader.stop()
