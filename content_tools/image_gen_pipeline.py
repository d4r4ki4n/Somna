"""
content_tools/image_gen_pipeline.py — Self-improving idle-time image generation.

One pipeline cycle:
  1. PICK     — choose a random untagged image from sessions/<name>/images/
  2. ANALYSE  — vision model describes and tags it; cull or keep; harvest caption
  3. ENGINEER — text LLM writes a verbose conditioning-tuned prompt inspired by the
                kept image's visual description, informed by the gen_log history
  4. GENERATE — generate one new image to sessions/<name>/images/generated/
  5. REVIEW   — vision model scores the generated image (quality + prompt fidelity)
  6. RETRY    — if failed, feed criticism back and re-engineer (up to max_retries times)
  7. PROMOTE  — if score passes, tag and move to images/; else discard
  8. LOG      — every attempt (pass or fail) written to somna.db for future learning

The LLM writes prompts in natural-language paragraph style — subject first, rich
physical/clothing details, setting, lighting, mood, conditioning hook — rather than
SD1.5 keyword lists.  Verbose specificity is encouraged; FLUX handles it well.

Designed to run one cycle at a time from the agent's idle planning loop.
CLI: python -m content_tools.image_gen_pipeline <session> <theme> <tag> [--cycles N]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import re
import shutil
import time
import urllib.request
from pathlib import Path

from content_tools.somna_db import (
    get_tagged_filenames as _get_tagged_filenames,
    load_gen_log         as _load_gen_log,
    append_gen_log       as _append_gen_log,
    save_image_meta      as _save_image_meta,
    save_tags            as _save_tags,
)

_ROOT     = Path(__file__).parent.parent
_SESSIONS = _ROOT / "sessions"


# ── Shared helpers ────────────────────────────────────────────────────────────

def _llm_base_url() -> str:
    return os.environ.get("SOMNA_LLM_URL", "http://localhost:8000").rstrip("/")


def _llm_model() -> str:
    return os.environ.get("SOMNA_LLM_MODEL", "")


def _affirmations_path(session_name: str) -> Path:
    return _SESSIONS / session_name / "affirmations.txt"


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}


def _images_dir(session_name: str) -> Path:
    return _SESSIONS / session_name / "images"


def _generated_dir(session_name: str) -> Path:
    d = _SESSIONS / session_name / "images" / "generated"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── STEP 1: Pick an untagged image ────────────────────────────────────────────

def _pick_untagged(session_name: str) -> Path | None:
    """Return a random untagged image from the session's images folder."""
    img_dir = _images_dir(session_name)
    if not img_dir.exists():
        return None

    tagged = _get_tagged_filenames(session_name)
    candidates = [
        p for p in img_dir.iterdir()
        if p.suffix.lower() in _IMAGE_EXTS
        and p.name not in tagged
        and p.parent.name != "generated"
    ]
    return random.choice(candidates) if candidates else None


# ── STEP 2: Analyse with vision model ─────────────────────────────────────────

_ANALYSE_SYSTEM = (
    "You are an expert image analyst for a hypnotic conditioning application. "
    "Produce detailed visual descriptions and structured metadata. "
    "Respond ONLY with valid JSON — no prose, no markdown fences."
)

_ANALYSE_PROMPT = """\
Analyse this image and return a JSON object with exactly these fields:

1. "description": Rich 3-5 sentence visual description covering: subject (gender,
   body type, hair color/style, expression, eye contact), clothing details (fabric,
   fit, color, accessories), pose and action, setting and background, lighting quality
   and color temperature, overall mood and aesthetic style. Be specific — this feeds
   a generation prompt so detail matters.

2. "tags": Array of 3-6 lowercase strings:
   Theme (1-3): submission, obedience, bimbo, blank, mindless, arousal, sissy,
                feminization, praise, degradation, playful, commanding, teasing, dreamy
   Explicitness (1): mild, suggestive, explicit, graphic
   Style (1): photo-caption, anime-caption, illustrated, photo-only, anime-only

3. "open_tags": Array of 1-6 free-form lowercase tags for specific details:
   body features, props, clothing items, hair, setting specifics, subculture markers.

4. "caption_text": Any text overlay copied verbatim. "" if none.

5. "quality": "keep" or "cull".
   Cull only if: heavily watermarked over the subject, severely blurry/corrupt,
   or a blank placeholder with no real content. Keep everything else.

6. "style": repeat the style tag from field 2.

7. "conditioning_hook": One honest sentence — what psychological effect is this image
   designed to produce in a viewer undergoing hypnotic conditioning?

Return ONLY valid JSON.
"""


def _analyse_image(image_path: Path) -> dict:
    from content_tools.image_tags import _image_to_jpeg_bytes
    jpeg_bytes = _image_to_jpeg_bytes(image_path)
    b64_img    = base64.b64encode(jpeg_bytes).decode()
    data_url   = f"data:image/jpeg;base64,{b64_img}"

    payload = json.dumps({
        "model": _llm_model(),
        "messages": [
            {"role": "system", "content": _ANALYSE_SYSTEM},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text",      "text": _ANALYSE_PROMPT},
            ]},
        ],
        "max_tokens": 600,
        "temperature": 0.2,
    }).encode()

    url = _llm_base_url() + "/v1/chat/completions"
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())

    raw = data["choices"][0]["message"]["content"]
    return _parse_json_response(raw)


# ── Caption harvesting ────────────────────────────────────────────────────────

# Tags that describe style or explicitness — not useful as affirmation routing keys
_STYLE_TAGS       = {"photo-caption", "anime-caption", "illustrated", "photo-only", "anime-only"}
_EXPLICIT_TAGS    = {"mild", "suggestive", "explicit", "graphic"}
_NON_THEMATIC     = _STYLE_TAGS | _EXPLICIT_TAGS


def _thematic_tags(tags: list[str]) -> list[str]:
    """Return only the thematic/conditioning tags from an analysis tags list.

    Strips out style and explicitness labels so we only route captions to
    semantically meaningful sections (submission, bimbo, obedience, etc.).
    """
    return [t for t in tags if t.lower() not in _NON_THEMATIC]


_GARBAGE_RE = re.compile(
    r"(?i)"
    r"(https?://|www\.)"                     # explicit URLs
    r"|([\w.-]+\.[a-z]{2,10}(/|\s|$))"      # anything.tld — catches .com .vip .xxx .adult etc.
    r"|(@[\w.]+)"                            # social handles
    r"|([/\\])"                              # slashes (patreon/something)
    r"|(©|\(c\)|copyright|all\s+rights\s+reserved)"  # copyright
    r"|(\b(19|20)\d{2}\b)"                  # years
    r"|(#[\w]+)"                             # hashtags
    r"|(^\s*[\d\s\-/:.]+\s*$)"             # numbers/dates only
)


def _is_garbage_caption(text: str) -> bool:
    """Return True if the caption looks like metadata noise, not an affirmation."""
    t = text.strip()
    if len(t) < 4 or len(t) > 100:
        return True
    return bool(_GARBAGE_RE.search(t))


def _harvest_caption(
    session_name: str,
    caption_text: str,
    tags: list[str] | None = None,
) -> bool:
    """Write a caption into every relevant tag section.

    tags — thematic tags to file this caption under.
           For reference captions: pass _thematic_tags(analysis["tags"]).
           For generated captions: pass [pipeline_target_tag].
           If None/empty, falls back to 'general' (the global pool).

    Each tag is created if absent; existing tags are appended to (deduped).
    No mirroring to general when specific tags exist — all tagged phrases are
    already included in the global fallback pool by phrase_pool and
    timeline_runner, so duplicating them under general is just noise.

    Garbage captions (URLs, watermarks, copyright, dates, slashes) are
    silently skipped and logged.

    Returns True if the caption was new to at least one tag, False if skipped.
    """
    from content_tools.affirmations import count_phrases, write_affirmations

    if not caption_text or not caption_text.strip():
        return False
    caption_text = caption_text.strip()
    if _is_garbage_caption(caption_text):
        print(f"[Pipeline] Skipped garbage caption: {caption_text!r}")
        return False

    # Use the supplied thematic tags; fall back to general only when none given
    effective_tags = [t.strip().lower() for t in tags if t.strip()] if tags else ["general"]

    wrote_new = False
    for t in effective_tags:
        n_before = count_phrases(session_name, t)
        write_affirmations(session_name, t, [caption_text], mode="append")
        if count_phrases(session_name, t) > n_before:
            wrote_new = True
    return wrote_new


# ── STEP 3: Engineer a conditioning prompt ────────────────────────────────────

_ENGINEER_SYSTEM = (
    "You are a specialist image generation prompt writer for hypnotic conditioning "
    "imagery using FLUX diffusion models.\n\n"
    "FLUX responds to natural language, not keyword lists. Your prompts are written "
    "like a cinematographer's shot brief: subject first (physical description, expression, "
    "eye contact), then clothing (specific fabrics, colors, fit), then pose and action, "
    "then setting, then lighting (source, quality, color temperature), then mood and "
    "psychological conditioning tone. Be verbose and specific — 80-160 words of "
    "flowing connected prose, not a comma-separated list of buzzwords.\n\n"
    "Never use: 'masterpiece', '8k', 'best quality', 'ultra detailed', 'highly detailed', "
    "'sharp focus', or any other SD1.5-era quality token. They do nothing for FLUX.\n\n"
    "When the conditioning theme references bimbo, doll, barbie, or similar Western "
    "fetish-glam aesthetics, and the reference description does not explicitly specify "
    "ethnicity or regional origin, steer the subject toward that aesthetic (platinum "
    "blonde, dramatic makeup, doll-like glam proportions) rather than an unintended "
    "default. If the reference clearly establishes a different look, follow the reference.\n\n"
    "Respond ONLY with valid JSON."
)


def _build_history_context(session_name: str, theme: str, n: int = 6) -> str:
    """Summarise recent gen_log entries for this theme to give the LLM memory."""
    relevant = _load_gen_log(session_name, theme=theme, limit=n)
    if not relevant:
        return ""

    lines = ["Recent generation attempts for this theme (learn from these):"]
    for e in relevant:
        action = e.get("action", "?")
        scores = e.get("scores", {})
        score_str = (f"vq={scores.get('visual_quality','?')} "
                     f"pf={scores.get('prompt_fidelity','?')} "
                     f"cv={scores.get('conditioning_value','?')}")
        note    = e.get("failure_note", "") or e.get("note", "")
        prompt  = (e.get("prompt") or "")[:120]
        lines.append(
            f"  [{action.upper()}] {score_str}  note: {note or 'none'}\n"
            f"  prompt: {prompt}{'...' if len(e.get('prompt',''))>120 else ''}"
        )
    return "\n".join(lines)


def _build_affirmations_context(session_name: str, n: int = 12) -> str:
    """Return a sample of existing affirmations to inspire caption generation."""
    aff_path = _affirmations_path(session_name)
    if not aff_path.exists():
        return ""
    lines = [
        l.strip() for l in aff_path.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    ]
    if not lines:
        return ""
    sample = random.sample(lines, min(n, len(lines)))
    return "Existing affirmations for caption inspiration:\n" + "\n".join(f"  - {l}" for l in sample)


def _engineer_prompt(
    description: str,
    open_tags: list[str],
    conditioning_hook: str,
    theme: str,
    target_tag: str,
    style: str,
    intensity: str,
    session_name: str,
    ref_caption: str = "",
    failure_note: str = "",
    forced_caption: str = "",
    llm_url: str | None = None,
    llm_model: str | None = None,
) -> tuple[str, str]:
    """Write a verbose generation prompt + an optional caption.

    Returns (prompt_str, caption_str).  caption_str is empty if the style
    does not call for a text overlay.
    """
    style_guidance = {
        "photo-only":    "photorealistic photograph, natural or studio setting",
        "photo-caption": "photorealistic photograph with a bold text caption overlay",
        "anime-only":    "anime illustration, clean cel shading, vibrant palette",
        "anime-caption": "anime illustration with a bold text caption overlay",
        "illustrated":   "digital illustration, painterly style, detailed linework",
    }.get(style, "photorealistic photograph")

    intensity_guidance = {
        "mild":       "tastefully dressed, elegant, fully clothed",
        "suggestive": "revealing or lingerie, alluring but not explicit",
        "explicit":   "topless or partially nude, explicit content",
        "graphic":    "fully nude, graphic content",
    }.get(intensity, "revealing or lingerie, alluring but not explicit")

    history_ctx   = _build_history_context(session_name, theme)
    aff_ctx       = _build_affirmations_context(session_name)
    open_tag_str  = ", ".join(open_tags) if open_tags else "none noted"

    retry_note = ""
    if failure_note:
        retry_note = (
            f"\n⚠ PREVIOUS ATTEMPT FAILED: {failure_note}\n"
            "Adjust your approach to avoid this problem.\n"
        )

    if forced_caption:
        caption_instruction = (
            f'You MUST use this exact caption verbatim: "{forced_caption.upper()}"\n'
            "Bake it into the scene description as visible text (neon, signage, "
            "projected, painted, title-card overlay, etc). The caption field in "
            "your JSON must contain this exact text."
        )
    else:
        caption_instruction = (
            "Also write a short caption (3-8 words, ALL CAPS, commanding or affirming) "
            "for the image. The caption MUST appear somewhere in the final prompt you "
            "write — baked into the scene description as visible text (neon, signage, "
            "projected, painted, title-card overlay, etc).\n"
            "Choose from the affirmation examples above if suitable, or create a new "
            "one fitting the theme."
        )

    user_msg = f"""\
Reference image description:
{description}

Visual details observed: {open_tag_str}
Conditioning hook of reference image: {conditioning_hook}
{"Caption on reference image: " + ref_caption if ref_caption else ""}
{retry_note}
Target conditioning theme: {theme}
Target library tag: {target_tag}
Style: {style_guidance}
Content level: {intensity_guidance}
{history_ctx}
{aff_ctx}

Write a new image generation prompt (80-160 words) inspired by the reference above,
tuned for the '{theme}' conditioning theme. The prompt should be natural flowing prose,
not a list. Weave the conditioning psychology into the visual description naturally.

{caption_instruction}

Return JSON: {{"prompt": "...", "caption": "..."}}
(Both fields required. Caption field must not be empty.)
"""

    payload = json.dumps({
        "model": llm_model or _llm_model(),
        "messages": [
            {"role": "system", "content": _ENGINEER_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        "max_tokens": 500,
        "temperature": 0.88,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }).encode()

    base = (llm_url or _llm_base_url()).rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    url = base + "/chat/completions"
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())

    raw    = data["choices"][0]["message"]["content"]
    parsed = _parse_json_response(raw)
    prompt  = parsed.get("prompt", "").strip()
    caption = parsed.get("caption", "").strip()
    return prompt, caption


def _prepend_caption_to_prompt(prompt: str, caption: str) -> str:
    """Frame the prompt so FLUX sees the caption requirement in its first tokens.

    FLUX is early-token-dominant: instructions buried at the end of a long prose
    block compete against all the rich visual detail and often lose.  Putting the
    caption as the opening frame makes it impossible for the model to ignore.

    The phrasing deliberately allows any text-rendering approach the model finds
    natural (overlay, neon, title card, signage) — the constraint is that the
    wording must appear, not how it appears.
    """
    caption = caption.strip()
    if not caption:
        return prompt
    cap_upper = caption.upper()
    prefix = (
        f'The words "{cap_upper}" appear in large, bold, highly legible text on this image. '
    )
    return prefix + prompt


# ── STEP 4: Generate the image ────────────────────────────────────────────────

def _generate_to_staging(session_name: str, prompt: str) -> Path:
    from content_tools.images import _generate_koboldcpp, _load_imggen_config
    cfg       = _load_imggen_config()
    png_bytes = _generate_koboldcpp(
        prompt    = prompt,
        steps     = cfg.get("steps",     8),
        width     = cfg.get("width",  1024),
        height    = cfg.get("height", 1024),
        cfg_scale = cfg.get("cfg_scale", 1.0),
        sampler   = cfg.get("sampler",   "Euler"),
        scheduler = cfg.get("scheduler", "Beta"),
        shift     = cfg.get("shift",     7.0),
    )
    out_dir  = _generated_dir(session_name)
    filename = f"gen_{int(time.time())}.png"
    out_path = out_dir / filename
    out_path.write_bytes(png_bytes)
    return out_path


# ── STEP 5: Review the generated image ───────────────────────────────────────

_REVIEW_SYSTEM = (
    "You are a strict quality reviewer for AI-generated conditioning imagery. "
    "Be critical and honest — grade inflation wastes generation budget. "
    "A score of 4 means genuinely good. A score of 5 is rare and outstanding. "
    "Score 1-2 for clear failures. Score 3 only for mediocre output that has "
    "real problems but is not a total failure. Return ONLY valid JSON."
)

_REVIEW_PROMPT_TMPL = """\
Review this AI-generated image strictly. Do NOT round up — be harsh.

Intended prompt (first 200 chars): {prompt_summary}
Target theme: {theme}  |  Target tag: {tag}
{caption_block}
Score 1-5 (5=exceptional, 4=good, 3=mediocre/flawed, 2=bad, 1=failure):
1. "visual_quality": Correct anatomy, not blurry, well-composed, aesthetically coherent.
   Score 3 or below if anatomy is wrong, face is broken, or image is blurry.
2. "prompt_fidelity": Does the image match the intended subject, style, and mood?
   Score 3 or below if the subject is wrong or the style misses the brief.
3. "conditioning_value": Effectiveness for '{theme}' hypnotic conditioning.
   Score 3 or below if the image does not communicate the theme clearly.
{text_block}
Also provide:
- "open_tags": array of 1-5 free-form tags for what is actually visible.
- "failure_note": If not kept, one specific sentence on the PRIMARY problem.
  Write "good" if kept.

Do NOT include a "keep" field — that will be calculated from your scores.
Return ONLY JSON with these exact fields: visual_quality, prompt_fidelity,
conditioning_value{text_field_list}, open_tags, failure_note.
"""

_REVIEW_TEXT_BLOCK = """\
4. "text_legibility": Is the caption text "{caption}" readable, correctly spelled,
   and not garbled/mirrored/partial? Score 4+ only if ALL words are legible and
   correctly spelled. Score 1-2 if text is garbled, missing, or badly misspelled.
"""


def _passes_review(review: dict, caption: str = "") -> bool:
    """Enforce pass threshold in code — do not trust the LLM's keep field."""
    vq = int(review.get("visual_quality",     0) or 0)
    pf = int(review.get("prompt_fidelity",    0) or 0)
    cv = int(review.get("conditioning_value", 0) or 0)
    if vq < 4 or pf < 4 or cv < 4:
        return False
    if caption and caption.strip():
        tl = int(review.get("text_legibility", 0) or 0)
        if tl < 4:
            return False
    return True


def _review_generated(
    image_path: Path,
    prompt: str,
    theme: str,
    tag: str,
    caption: str = "",
) -> dict:
    from content_tools.image_tags import _image_to_jpeg_bytes
    jpeg_bytes = _image_to_jpeg_bytes(image_path)
    b64_img    = base64.b64encode(jpeg_bytes).decode()
    data_url   = f"data:image/jpeg;base64,{b64_img}"

    has_caption   = bool(caption and caption.strip())
    caption_block = f'Expected caption text on image: "{caption.strip()}"\n' if has_caption else ""
    text_block    = _REVIEW_TEXT_BLOCK.format(caption=caption.strip()) if has_caption else ""
    text_field_list = ", text_legibility" if has_caption else ""

    review_prompt = _REVIEW_PROMPT_TMPL.format(
        prompt_summary  = (prompt[:200] + "...") if len(prompt) > 200 else prompt,
        theme           = theme,
        tag             = tag,
        caption_block   = caption_block,
        text_block      = text_block,
        text_field_list = text_field_list,
    )
    payload = json.dumps({
        "model": _llm_model(),
        "messages": [
            {"role": "system", "content": _REVIEW_SYSTEM},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text",      "text": review_prompt},
            ]},
        ],
        "max_tokens": 300,
        "temperature": 0.1,
    }).encode()

    url = _llm_base_url() + "/v1/chat/completions"
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())

    raw    = data["choices"][0]["message"]["content"]
    result = _parse_json_response(raw)

    # Calculate keep in code — never trust the LLM to do threshold math
    result["keep"] = _passes_review(result, caption=caption)
    if not result.get("failure_note") or result["failure_note"] == "good":
        if not result["keep"]:
            scores = (f"vq={result.get('visual_quality','?')} "
                      f"pf={result.get('prompt_fidelity','?')} "
                      f"cv={result.get('conditioning_value','?')}")
            if has_caption:
                scores += f" tl={result.get('text_legibility','?')}"
            result["failure_note"] = f"scores below threshold ({scores})"

    return result


# ── STEP 7: Promote or discard ────────────────────────────────────────────────

def _promote(
    session_name: str,
    generated_path: Path,
    tag: str,
    theme: str,
    review: dict,
    ref_tags: list[str],
    ref_open_tags: list[str],
    caption: str = "",
) -> Path:
    dest = _images_dir(session_name) / generated_path.name
    shutil.move(str(generated_path), str(dest))

    _save_image_meta(session_name, generated_path.name, {
        "tags":        list({tag} | set(ref_tags)),
        "open_tags":   list(set(ref_open_tags) | set(review.get("open_tags", []))),
        "caption_text": caption,
        "quality":     "keep",
        "style":       "generated",
        "gen_scores": {
            "visual_quality":     review.get("visual_quality"),
            "prompt_fidelity":    review.get("prompt_fidelity"),
            "conditioning_value": review.get("conditioning_value"),
        },
    })

    # Generated caption was intentionally made for this theme — file under it
    if caption:
        _harvest_caption(session_name, caption, tags=[tag])

    return dest


# ── Full pipeline cycle ────────────────────────────────────────────────────────

def run_pipeline_cycle(
    session_name: str,
    theme: str,
    tag: str,
    intensity: str        = "suggestive",
    max_retries: int      = 2,
    forced_caption: str   = "",
    llm_url: str | None   = None,
    llm_model: str | None = None,
) -> dict:
    """Run one full generate-and-review cycle, with up to max_retries retry passes.

    On failure the review's `failure_note` is fed back to the prompt engineer so
    each retry attempt adapts to what went wrong.  Every attempt (pass or fail) is
    written to gen_log.json for long-term learning.

    Returns a result dict with: status, reference_image, generated_image, prompt,
    caption, review_scores, action, attempts, notes.
    """
    result: dict = {
        "session":          session_name,
        "theme":            theme,
        "tag":              tag,
        "status":           "ok",
        "reference_image":  None,
        "generated_image":  None,
        "prompt":           None,
        "caption":          None,
        "review_scores":    None,
        "action":           None,
        "attempts":         0,
        "notes":            "",
    }

    # ── 1. Pick reference image ───────────────────────────────────────────────
    ref_path = _pick_untagged(session_name)
    if ref_path is None:
        result["status"] = "no_untagged_images"
        result["notes"]  = "All images in this session are already tagged."
        return result
    result["reference_image"] = ref_path.name

    # ── 2. Analyse reference ──────────────────────────────────────────────────
    try:
        analysis = _analyse_image(ref_path)
    except Exception as exc:
        result["status"] = "analyse_error"
        result["notes"]  = str(exc)
        return result

    # Write tags for this reference image (single upsert — no load-all)
    _save_image_meta(session_name, ref_path.name, {
        "tags":              analysis.get("tags", []),
        "open_tags":         analysis.get("open_tags", []),
        "caption_text":      analysis.get("caption_text", ""),
        "quality":           analysis.get("quality", "keep"),
        "style":             analysis.get("style", ""),
        "conditioning_hook": analysis.get("conditioning_hook", ""),
    })

    # Harvest caption from reference — route to what the image actually IS, not the pipeline target
    ref_caption = analysis.get("caption_text", "")
    if ref_caption:
        ref_thematic = _thematic_tags(analysis.get("tags", []))
        harvested = _harvest_caption(session_name, ref_caption, tags=ref_thematic)
        if harvested:
            print(f"[Pipeline] Harvested caption: {ref_caption!r}")

    if analysis.get("quality") == "cull":
        result["action"] = "ref_culled"
        result["notes"]  = f"Reference {ref_path.name} culled — skipping gen."
        return result

    # ── 3-6. Engineer → Generate → Review → Retry loop ───────────────────────
    failure_note  = ""
    last_review   = {}
    gen_path: Path | None = None
    total_attempts = 0

    for attempt in range(1 + max_retries):
        total_attempts += 1
        result["attempts"] = total_attempts

        # Engineer prompt (with feedback from prior failure if retrying)
        try:
            prompt, caption = _engineer_prompt(
                description       = analysis.get("description", ""),
                open_tags         = analysis.get("open_tags", []),
                conditioning_hook = analysis.get("conditioning_hook", ""),
                theme             = theme,
                target_tag        = tag,
                style             = analysis.get("style", "photo-only"),
                intensity         = intensity,
                session_name      = session_name,
                ref_caption       = ref_caption,
                failure_note      = failure_note,
                forced_caption    = forced_caption,
                llm_url           = llm_url,
                llm_model         = llm_model,
            )
        except Exception as exc:
            result["status"] = "engineer_error"
            result["notes"]  = str(exc)
            return result

        if not prompt:
            result["status"] = "empty_prompt"
            result["notes"]  = "LLM returned empty prompt."
            return result

        # Caption is already woven into the prose by the engineer; prepend it as
        # an upfront constraint so FLUX sees it in the first tokens.
        effective_caption = caption or ref_caption.strip()
        final_prompt = _prepend_caption_to_prompt(prompt, effective_caption)

        result["prompt"]  = final_prompt
        result["caption"] = caption
        if attempt > 0:
            print(f"[Pipeline] Retry {attempt}/{max_retries} — {failure_note}")

        # Generate
        try:
            # Clean up previous failed generation before generating again
            if gen_path and gen_path.exists():
                gen_path.unlink(missing_ok=True)
            gen_path = _generate_to_staging(session_name, final_prompt)
        except Exception as exc:
            result["status"] = "generate_error"
            result["notes"]  = str(exc)
            return result

        result["generated_image"] = gen_path.name

        # Review
        try:
            review = _review_generated(
                gen_path, final_prompt, theme, tag,
                caption=effective_caption,
            )
        except Exception as exc:
            # Can't review — keep it anyway, mark as unreviewed
            review = {"keep": True, "failure_note": f"review_error: {exc}"}

        last_review  = review
        failure_note = review.get("failure_note", "") or ""

        # Log this attempt
        _append_gen_log(session_name, {
            "ts":            time.strftime("%Y-%m-%dT%H:%M:%S"),
            "theme":         theme,
            "tag":           tag,
            "attempt":       attempt + 1,
            "prompt":        final_prompt,
            "prompt_base":   prompt,
            "caption":       effective_caption,
            "ref_image":     ref_path.name,
            "action":        "promoted" if review.get("keep") else "discarded",
            "scores": {
                "visual_quality":     review.get("visual_quality"),
                "prompt_fidelity":    review.get("prompt_fidelity"),
                "conditioning_value": review.get("conditioning_value"),
                "text_legibility":    review.get("text_legibility"),
            },
            "failure_note":  failure_note if not review.get("keep") else "",
            "note":          "good" if review.get("keep") else failure_note,
        })

        if review.get("keep", False):
            break   # pass — exit retry loop

        # Fail — iterate if retries remain
        if attempt < max_retries:
            continue
        # Out of retries
        break

    result["review_scores"] = {
        k: last_review.get(k)
        for k in ("visual_quality", "prompt_fidelity", "conditioning_value", "failure_note")
    }

    # ── 7. Promote or discard ─────────────────────────────────────────────────
    if last_review.get("keep", False) and gen_path and gen_path.exists():
        promoted = _promote(
            session_name   = session_name,
            generated_path = gen_path,
            tag            = tag,
            theme          = theme,
            review         = last_review,
            ref_tags       = analysis.get("tags", []),
            ref_open_tags  = analysis.get("open_tags", []),
            caption        = caption,
        )
        result["action"] = "promoted"
        result["notes"]  = (f"Promoted → {promoted.name}  "
                            f"(attempt {total_attempts}/{1+max_retries})")
    else:
        if gen_path and gen_path.exists():
            gen_path.unlink(missing_ok=True)
        result["action"] = "discarded"
        result["notes"]  = (f"Discarded after {total_attempts} attempt(s). "
                            f"Last issue: {failure_note}")

    return result


# ── JSON parsing helper ───────────────────────────────────────────────────────

def _parse_json_response(raw: str) -> dict:
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    pos = 0
    while True:
        start = raw.find("{", pos)
        if start == -1:
            break
        depth, end = 0, -1
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
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass
        pos = start + 1
    return {}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Self-improving image generation pipeline."
    )
    parser.add_argument("session",          help="Session folder name (e.g. 'default')")
    parser.add_argument("theme",            help="Conditioning theme (e.g. 'bimbo submission')")
    parser.add_argument("tag",              help="Library tag for generated images (e.g. 'bimbo')")
    parser.add_argument("--intensity",      default="suggestive",
                        choices=["mild", "suggestive", "explicit", "graphic"])
    parser.add_argument("--cycles",         type=int, default=1,
                        help="Number of pipeline cycles to run (default 1)")
    parser.add_argument("--retries",        type=int, default=2,
                        help="Max retry attempts per cycle on failure (default 2)")
    args = parser.parse_args()

    promoted_total  = 0
    discarded_total = 0

    for cycle in range(1, args.cycles + 1):
        print(f"\n{'─'*60}")
        print(f"[Pipeline] Cycle {cycle}/{args.cycles}  "
              f"session={args.session!r}  theme={args.theme!r}  tag={args.tag!r}")
        print(f"{'─'*60}")

        result = run_pipeline_cycle(
            session_name = args.session,
            theme        = args.theme,
            tag          = args.tag,
            intensity    = args.intensity,
            max_retries  = args.retries,
        )

        print(f"  Status:    {result['status']}")
        print(f"  Reference: {result['reference_image']}")
        print(f"  Action:    {result['action']}  ({result['attempts']} attempt(s))")
        if result.get("prompt"):
            print(f"  Prompt:    {result['prompt'][:120]}...")
        if result.get("caption"):
            print(f"  Caption:   {result['caption']!r}")
        if result.get("review_scores"):
            s = result["review_scores"]
            print(f"  Scores:    vq={s.get('visual_quality')} "
                  f"pf={s.get('prompt_fidelity')} "
                  f"cv={s.get('conditioning_value')}")
        print(f"  Notes:     {result['notes']}")

        if result["action"] == "promoted":
            promoted_total += 1
        elif result["action"] == "discarded":
            discarded_total += 1

    print(f"\n{'═'*60}")
    print(f"[Pipeline] Done — {args.cycles} cycle(s): "
          f"{promoted_total} promoted, {discarded_total} discarded")
    print(f"{'═'*60}")
