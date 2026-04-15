"""
content_tools/session_pipeline.py — Self-reviewing session creation pipeline.

One creation cycle:
  1. BRIEF    — LLM writes a structured creative brief from the intent text.
                This is always internal; the agent never needs to ask the user
                for a brief — it writes its own.
  2. DESIGN   — LLM writes a complete session.yaml from the brief.
  3. POPULATE — LLM writes affirmations.txt (all phase tags) from the brief.
  4. REVIEW   — Reviewer scores the session on 4 dimensions (≥ 4/5 to pass).
                On fail, the criticism is fed back to the designer for a retry.
  5. COMMIT   — Write session.yaml + affirmations.txt to disk.

Can be triggered:
  - On demand from the console (user asks to make a session)
  - Autonomously during idle planning (agent decides to expand the library)

Session naming: slug derived from the brief title + MMDD timestamp so autonomous
sessions never collide and are easy to recognise in the sessions/ list.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

_ROOT     = Path(__file__).parent.parent
_SESSIONS = _ROOT / "sessions"

# ── Session format reference ──────────────────────────────────────────────────
# Injected into every DESIGN call so the LLM writes valid YAML.

_FORMAT_REFERENCE = """\
SESSION FORMAT REFERENCE
========================

session.yaml — flat structure (params sit directly on each keyframe, NOT under a "params:" sub-key):

  name: "Session Title"
  description: "One sentence."
  duration: 600        # seconds; must match or slightly exceed last keyframe t

  defaults:            # optional session-level defaults
    beat_frequency: 10.0
    carrier_frequency: 200.0
    volume: 75.0
    spiral_style: "galaxy"
    veil_opacity: 40.0
    center_flash_sync_to_beat: true
    flash_duty_cycle: 0.38
    phrases: null

  timeline:
    - t: 0
      label: induction
      ease: linear
      beat_frequency: 10.0
      spiral_style: "tunnel_dream"
      spiral_opacity: 60
      veil_opacity: 20
      shadow_opacity: 0
      phrases: "induction"

    - t: 120
      label: deepening
      ease: ease_in_out
      beat_frequency: 6.0
      spiral_chaos: 0.3
      veil_opacity: 55
      phrases: "deepening"

    - t: 300
      label: depth
      ease: ease_in_out
      beat_frequency: 4.0
      spiral_speed_multiplier: 1.6
      spiral_opacity: 95
      veil_opacity: 70
      phrases: "depth"

    - t: 480
      label: emergence
      ease: ease_out
      beat_frequency: 10.0
      spiral_speed_multiplier: 0.8
      veil_opacity: 30
      phrases: null

PARAMETER RANGES:
  beat_frequency: 0.5–40 Hz   (delta 0.5–4, theta 4–8, alpha 8–13, beta 13–30, gamma 30–40)
  carrier_frequency: 80–400 Hz
  volume: 0–100
  spiral_opacity: 0–100
  veil_opacity: 0–100
  shadow_opacity: 0–100
  spiral_tightness: 1–20
  spiral_thickness: 2–40
  spiral_speed_multiplier: 0.1–5.0
  spiral_chaos: 0.0–1.0
  slideshow_interval: 1–30 (seconds)
  flash_duty_cycle: 0.1–0.9
  center_flash_on_time: 20–500 (ms)
  center_flash_off_time: 20–500 (ms)
  shadow_flash_on_time: 10–100 (ms) — keep ≤ 50 for subliminal threshold

SPIRAL STYLES (valid values only):
  tunnel_dream, galaxy, archimedean, kaleidoscope, interference,
  electric, vortex, dna, fibonacci, rose, moire, spirograph, fermat, superformula

  (Legacy aliases still accepted by the renderer but do not use in new sessions:
   zyntaks_hybrid/fan_blade → archimedean, star_polygon → kaleidoscope,
   fractal_arms → electric, dense_web → interference, wide_vortex → vortex,
   interlocked → dna, radiating_pulse → tunnel_dream)

VEIL MODES: scroll, rain, drift, converge, strobe, tunnel, null (auto-rotate)

EASING: linear, ease_in, ease_out, ease_in_out, instant

AFFIRMATIONS FORMAT (affirmations.txt):
  # Untagged lines (always available — appear when phrases: null)
  You are relaxing.
  Good girl.

  # [induction]
  Breathe.
  Let go.
  You are drifting deeper.

  # [deepening]
  Deeper now.
  Your thoughts are slowing.

  # [depth]
  You are fully under.
  Empty and open.

  # [emergence]
  Waking gently.
  Carry this feeling.

  Rules:
  - Tag names in timeline phrases: field must exactly match # [tagname] headers
  - 4–8 phrases per phase, 3–10 words each
  - Chains: word1 >> word2 >> word3 (flash in sequence)
  - Variants: phrase A | phrase B (random pick)
"""

# ── LLM helpers ───────────────────────────────────────────────────────────────

def _llm_base_url() -> str:
    return os.environ.get("SOMNA_LLM_URL", "http://localhost:8000").rstrip("/")


def _llm_model() -> str:
    return os.environ.get("SOMNA_LLM_MODEL", "")


def _chat(
    messages: list[dict],
    max_tokens: int | None = None,
    temperature: float = 0.7,
    llm_url: str | None = None,
    llm_model: str | None = None,
) -> str:
    body: dict = {
        "model":       llm_model or _llm_model(),
        "messages":    messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    payload = json.dumps(body).encode()
    # Strip trailing /v1 before appending so base_url works with or without it.
    base = (llm_url or _llm_base_url()).rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = base + "/v1/chat/completions"
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _parse_json(raw: str) -> dict:
    """Extract first JSON object from a string, tolerating markdown fences."""
    raw = raw.strip()
    # Strip markdown code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()
    # Find first { ... }
    start = raw.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in: {raw[:200]!r}")
    depth, end = 0, -1
    for i, ch in enumerate(raw[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError("Unclosed JSON object")
    return json.loads(raw[start:end])


# ── STEP 1: Write a creative brief ────────────────────────────────────────────

_BRIEF_SYSTEM = (
    "You are a hypnotic session designer for Somna. "
    "You deeply understand binaural brainwave entrainment, Ericksonian hypnosis, "
    "and psychological conditioning. Return ONLY valid JSON."
)

_BRIEF_PROMPT = """\
Intent / theme: {intent}

User profile context:
{profile_ctx}

Existing sessions in library: {existing_sessions}

Write a detailed creative brief for a new hypnotic session. Return JSON with these fields:

{{
  "title": "Short descriptive title (3-6 words)",
  "slug":  "lowercase_underscore_slug_max_4_words",
  "description": "One sentence describing the session goal",
  "psychological_goal": "What psychological state or transformation is intended?",
  "brainwave_arc": "Describe the Hz journey: e.g. alpha 10→theta 6→delta 3→alpha 10",
  "duration_minutes": integer between 6 and 20,
  "phases": [
    {{
      "label": "phase_slug",
      "name": "Human-readable name",
      "start_minute": 0,
      "purpose": "What happens psychologically in this phase",
      "phrase_vocabulary": ["3-6 example affirmation phrases fitting this phase"],
      "visual_mood": "Describe spiral style, veil, color, speed intent"
    }}
  ],
  "conditioning_hook": "Core psychological mechanism being activated",
  "contraindications": "Any notes about intensity or suitability",
  "imagery_tags": ["1-3 image library tags that would complement this session"]
}}

Produce 4-6 phases. The first phase is always induction (slow, gentle, welcoming).
The last phase is always emergence (gentle return). Middle phases carry the content.
Be specific and psychologically grounded.
"""


def _write_brief(
    intent: str,
    profile_ctx: str = "",
    existing_sessions: list[str] | None = None,
    llm_url: str | None = None,
    llm_model: str | None = None,
) -> dict:
    prompt = _BRIEF_PROMPT.format(
        intent            = intent,
        profile_ctx       = profile_ctx or "(none)",
        existing_sessions = ", ".join(existing_sessions or []) or "none yet",
    )
    raw    = _chat(
        [{"role": "system", "content": _BRIEF_SYSTEM},
         {"role": "user",   "content": prompt}],
        temperature = 0.75,
        llm_url     = llm_url,
        llm_model   = llm_model,
    )
    return _parse_json(raw)


# ── STEP 2: Design the session.yaml ───────────────────────────────────────────

_DESIGN_SYSTEM = (
    "You are a technical hypnotic session designer for Somna. "
    "You write complete, valid session.yaml files that follow the exact format spec. "
    "Return ONLY raw YAML text — no markdown, no code fences, no explanation."
)

_DESIGN_PROMPT = """\
{format_reference}

BRIEF:
{brief_json}
{failure_block}
Write a complete session.yaml for this brief. Use the format reference exactly.
Timeline keyframe params are FLAT (not nested under a "params:" key).
The duration field must be >= the last keyframe's t value.
Every "phrases:" value must exactly match a # [tagname] header you plan to use in affirmations.
Return ONLY raw YAML. No markdown fences. No explanation.
"""


def _design_session(
    brief: dict,
    failure_note: str = "",
    llm_url: str | None = None,
    llm_model: str | None = None,
) -> str:
    failure_block = ""
    if failure_note:
        failure_block = f"\n⚠ PREVIOUS VERSION FAILED REVIEW: {failure_note}\nFix these issues.\n"

    prompt = _DESIGN_PROMPT.format(
        format_reference = _FORMAT_REFERENCE,
        brief_json       = json.dumps(brief, indent=2),
        failure_block    = failure_block,
    )
    return _chat(
        [{"role": "system", "content": _DESIGN_SYSTEM},
         {"role": "user",   "content": prompt}],
        temperature = 0.4,
        llm_url     = llm_url,
        llm_model   = llm_model,
    ).strip()


# ── STEP 3: Populate affirmations ─────────────────────────────────────────────

_AFFIRMATIONS_SYSTEM = (
    "You are a hypnotic copywriter. You write affirmations for subliminal conditioning. "
    "Return ONLY the raw affirmations.txt content — no explanation, no fences."
)

_AFFIRMATIONS_PROMPT = """\
Session brief:
{brief_json}

Phase labels in this session (from the session.yaml): {phase_labels}

Write a complete affirmations.txt for this session.
Include:
- 4-6 untagged general phrases (before any # [tag] header) — short, positive, inviting
- One # [tagname] section for every phase label listed above
- 4-8 phrases per section, each 3-10 words
- Use >> for sequential chains (e.g. "empty >> open >> ready") where appropriate
- Use | for variants on a single line where appropriate
- Tailor each phase's phrases tightly to its purpose described in the brief
- Conditioning language should be direct, present-tense, specific to the session theme

Return ONLY raw affirmations.txt text. No explanation. No fences.
"""


def _populate_affirmations(
    brief: dict,
    phase_labels: list[str],
    llm_url: str | None = None,
    llm_model: str | None = None,
) -> str:
    prompt = _AFFIRMATIONS_PROMPT.format(
        brief_json   = json.dumps(brief, indent=2),
        phase_labels = ", ".join(phase_labels),
    )
    return _chat(
        [{"role": "system", "content": _AFFIRMATIONS_SYSTEM},
         {"role": "user",   "content": prompt}],
        temperature = 0.6,
        llm_url     = llm_url,
        llm_model   = llm_model,
    ).strip()


# ── STEP 4: Review the session ────────────────────────────────────────────────

_REVIEW_SYSTEM = (
    "You are a hypnotic session quality reviewer for an adult conditioning / entrainment system. "
    "Be honest and critical. Grade inflation wastes effort. "
    "A score of 4 means genuinely good. Score 3 only for real flaws. "
    "IMPORTANT CONTEXT: This system is designed for explicit psychological conditioning. "
    "Direct command phrasing, repetition, sensory anchoring, and overt conditioning language "
    "are intentional and VALID stylistic choices — do NOT penalise them. "
    "Only penalise phrase_quality for: wrong tag assignments, formatting errors, "
    "phrases that are off-theme for their phase, or generic filler unrelated to the session intent. "
    "Return ONLY valid JSON."
)

_REVIEW_PROMPT = """\
Review this hypnotic session. The brief describes the intended outcome.

BRIEF:
{brief_json}

SESSION YAML:
{yaml_text}

AFFIRMATIONS:
{aff_text}

Score 1-5 (5=exceptional, 4=good, 3=mediocre/flawed, 2=bad, 1=failure):

1. "arc_coherence": Does the binaural Hz arc tell a coherent psychological story?
   Does induction → depth → emergence structure make sense for the theme?
   Score 3 or below ONLY IF the Hz arc is flat, abrupt, or structurally wrong.

2. "phrase_quality": Are phrases correctly tagged to their phase, thematically on-point,
   and free of formatting errors?
   Score 3 or below ONLY IF phrases are in the wrong section, completely off-theme,
   or have format errors (broken >> chains, malformed | variants).
   Do NOT penalise direct/explicit/repetitive conditioning language — that is intentional.

3. "technical_validity": Is the YAML structurally correct — flat keyframe params (not nested
   under "params:"), valid parameter values in range, duration >= last keyframe t, every
   phrases: tag present in affirmations.txt? Score 3 or below for any structural error.

4. "conditioning_effectiveness": Will this session build the psychological state described
   in the brief? Is the conditioning hook woven through the content?
   Score 3 or below ONLY IF the session is so generic it could belong to any other brief,
   or the stated hook is absent from the content.

Also provide:
- "failure_note": If any STRUCTURAL score (arc_coherence, technical_validity) is below 4,
  one specific sentence on the PRIMARY structural problem. "good" if structure passes.
- "suggested_fixes": Concrete structural fixes only (not style critiques).

Do NOT include a "keep" field — it will be calculated from scores.
Return ONLY JSON: arc_coherence, phrase_quality, technical_validity, conditioning_effectiveness,
failure_note, suggested_fixes.
"""


# Structural dimensions require ≥ 4 (objective: arc Hz sense, valid YAML).
# Content dimensions require ≥ 3 (subjective: phrase style and conditioning tone vary by intent).
_STRUCTURAL_PASS = 4
_CONTENT_PASS    = 3

def _passes_review(review: dict) -> bool:
    structural = all(
        int(review.get(k, 0) or 0) >= _STRUCTURAL_PASS
        for k in ("arc_coherence", "technical_validity")
    )
    content = all(
        int(review.get(k, 0) or 0) >= _CONTENT_PASS
        for k in ("phrase_quality", "conditioning_effectiveness")
    )
    return structural and content


def _review_session(
    brief: dict,
    yaml_text: str,
    aff_text: str,
    llm_url: str | None = None,
    llm_model: str | None = None,
) -> dict:
    prompt = _REVIEW_PROMPT.format(
        brief_json = json.dumps(brief, indent=2),
        yaml_text  = yaml_text[:6000],
        aff_text   = aff_text[:3000],
    )
    raw    = _chat(
        [{"role": "system", "content": _REVIEW_SYSTEM},
         {"role": "user",   "content": prompt}],
        max_tokens  = 400,
        temperature = 0.1,
        llm_url     = llm_url,
        llm_model   = llm_model,
    )
    result = _parse_json(raw)
    result["keep"] = _passes_review(result)
    if not result.get("failure_note") or result["failure_note"] == "good":
        if not result["keep"]:
            scores = " ".join(
                f"{k[:3]}={result.get(k,'?')}"
                for k in ("arc_coherence", "phrase_quality",
                          "technical_validity", "conditioning_effectiveness")
            )
            result["failure_note"] = f"scores below threshold ({scores})"
    return result


# ── STEP 5: Commit to disk ────────────────────────────────────────────────────

def _commit_session(
    session_name: str,
    yaml_text: str,
    aff_text: str,
) -> dict:
    """Validate YAML and write both files. Returns write result dict."""
    from content_tools.sessions import write_session_yaml
    from content_tools.affirmations import _affirmations_path

    write_result = write_session_yaml(session_name, yaml_text)
    if not write_result.get("valid"):
        return write_result

    aff_path = _affirmations_path(session_name)
    aff_path.parent.mkdir(parents=True, exist_ok=True)
    aff_path.write_text(aff_text, encoding="utf-8")

    write_result["affirmations_written"] = True
    return write_result


# ── Session name helper ───────────────────────────────────────────────────────

def _make_session_name(brief: dict) -> str:
    slug = brief.get("slug", "")
    if not slug:
        title = brief.get("title", "session")
        slug  = re.sub(r"[^a-z0-9\s]", "", title.lower())
        slug  = "_".join(slug.split()[:4])
    slug = re.sub(r"[^a-z0-9_]", "", slug) or "custom_session"
    ts   = time.strftime("%m%d")
    return f"{slug}_{ts}"


def _extract_phase_labels(yaml_text: str) -> list[str]:
    """Pull phrase tag names referenced in timeline from raw yaml text."""
    labels = []
    for m in re.finditer(r'phrases:\s*["\']?(\w+)["\']?', yaml_text):
        label = m.group(1)
        if label not in ("null", "true", "false") and label not in labels:
            labels.append(label)
    return labels


# ── Full pipeline ─────────────────────────────────────────────────────────────

def run_session_creation_cycle(
    intent: str,
    session_name: str | None = None,
    profile_ctx:  str = "",
    max_retries:  int = 2,
    llm_url:      str | None = None,
    llm_model:    str | None = None,
) -> dict:
    """Run a full session creation cycle from an intent string.

    Returns a result dict:
        status           — "created" | "failed_review" | "commit_error" |
                           "brief_error" | "design_error" | "affirmations_error"
        session_name     — folder name if committed
        brief            — the creative brief dict
        attempts         — how many design passes were made
        review_scores    — final review score dict
        notes            — human-readable summary
    """
    from content_tools.sessions import list_sessions

    result: dict = {
        "intent":       intent,
        "session_name": None,
        "brief":        None,
        "status":       "ok",
        "attempts":     0,
        "review_scores": None,
        "notes":        "",
    }

    # ── 1. Brief ──────────────────────────────────────────────────────────────
    print(f"[SessionPipeline] Writing brief for: {intent!r}")
    try:
        brief = _write_brief(
            intent            = intent,
            profile_ctx       = profile_ctx,
            existing_sessions = list_sessions(),
            llm_url           = llm_url,
            llm_model         = llm_model,
        )
    except Exception as exc:
        result["status"] = "brief_error"
        result["notes"]  = str(exc)
        return result

    result["brief"] = brief
    final_name = session_name or _make_session_name(brief)
    result["session_name"] = final_name
    print(f"[SessionPipeline] Brief: {brief.get('title')!r} → session: {final_name!r}")

    # ── 2-4. Design → Populate → Review loop ─────────────────────────────────
    failure_note = ""
    last_review  = {}
    yaml_text    = ""
    aff_text     = ""

    for attempt in range(1 + max_retries):
        result["attempts"] = attempt + 1

        if attempt > 0:
            print(f"[SessionPipeline] Retry {attempt}/{max_retries} — {failure_note}")

        # Design
        try:
            yaml_text = _design_session(
                brief        = brief,
                failure_note = failure_note,
                llm_url      = llm_url,
                llm_model    = llm_model,
            )
        except Exception as exc:
            result["status"] = "design_error"
            result["notes"]  = str(exc)
            return result

        # Quick structural pre-check before paying for affirmations + review
        try:
            import yaml as _yaml
            parsed = _yaml.safe_load(yaml_text)
            assert isinstance(parsed, dict), "Top-level must be a dict"
            assert "timeline" in parsed, "Missing timeline"
            assert len(parsed.get("timeline", [])) >= 3, "Need at least 3 keyframes"
        except Exception as exc:
            failure_note = f"YAML structural error: {exc}"
            continue

        # Populate affirmations
        phase_labels = _extract_phase_labels(yaml_text)
        try:
            aff_text = _populate_affirmations(
                brief        = brief,
                phase_labels = phase_labels,
                llm_url      = llm_url,
                llm_model    = llm_model,
            )
        except Exception as exc:
            result["status"] = "affirmations_error"
            result["notes"]  = str(exc)
            return result

        # Review
        try:
            review = _review_session(
                brief     = brief,
                yaml_text = yaml_text,
                aff_text  = aff_text,
                llm_url   = llm_url,
                llm_model = llm_model,
            )
        except Exception as exc:
            # Can't review — commit anyway, mark as unreviewed
            review = {
                "keep":         True,
                "failure_note": f"review_error: {exc}",
            }

        last_review  = review
        failure_note = review.get("failure_note", "") or ""

        scores_str = " ".join(
            f"{k[:3]}={review.get(k,'?')}"
            for k in ("arc_coherence", "phrase_quality",
                      "technical_validity", "conditioning_effectiveness")
        )
        print(f"[SessionPipeline] Review attempt {attempt+1}: {scores_str} — keep={review.get('keep')}")

        if review.get("keep", False):
            break

    result["review_scores"] = {
        k: last_review.get(k)
        for k in ("arc_coherence", "phrase_quality", "technical_validity",
                  "conditioning_effectiveness", "failure_note", "suggested_fixes")
    }

    if not last_review.get("keep", False):
        result["status"] = "failed_review"
        result["notes"]  = (f"Session did not pass review after {result['attempts']} attempts. "
                            f"Last note: {failure_note}")
        _persist_quality(final_name, result)
        return result

    # ── 5. Commit ─────────────────────────────────────────────────────────────
    commit = _commit_session(final_name, yaml_text, aff_text)
    if not commit.get("valid"):
        result["status"] = "commit_error"
        result["notes"]  = commit.get("error", "Unknown write error")
        _persist_quality(final_name, result)
        return result

    result["status"] = "created"
    result["notes"]  = (f"Session '{brief.get('title')}' created as {final_name!r}. "
                        f"{commit.get('keyframes', '?')} keyframes, "
                        f"{commit.get('duration_s', '?')}s duration.")

    print(f"[SessionPipeline] Committed: {final_name!r} — {result['notes']}")
    _persist_quality(final_name, result)
    return result


def _persist_quality(session_name: str, result: dict) -> None:
    """Write pipeline review scores to somna.db — fire-and-forget, never raises."""
    try:
        from content_tools.somna_db import save_session_quality
        save_session_quality(session_name, result)
    except Exception as exc:
        print(f"[SessionPipeline] Quality log error (non-fatal): {exc}")
