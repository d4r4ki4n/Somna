"""
content_tools/image_tags.py — Vision-based image tagging for session libraries.

Uses KoboldCpp's vision endpoint (mmproj) to analyse captioned conditioning
images and produce structured tag metadata.  Metadata is stored in somna.db
(via content_tools.somna_db) — no per-session tags.json files.

Image metadata schema (per entry):
    {
      "tags":         ["bimbo", "blank", "photo-caption", "explicit"],
      "open_tags":    ["blonde", "kneeling", "latex"],
      "caption_text": "COCK GOES IN MIND GOES OUT",
      "quality":      "keep",   // "keep" | "cull"
      "style":        "photo-caption"
    }

The vision model reads the text overlay in the image (critical for this
content type — the caption IS the payload) and assigns thematic tags.
Quality culling flags blurry, watermarked, or aesthetically redundant images
for optional removal without deleting anything automatically.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

from content_tools.somna_db import (
    load_tags,
    save_tags,
    save_image_meta,
    get_tagged_filenames,
)

_ROOT     = Path(__file__).parent.parent
_SESSIONS = _ROOT / "sessions"

# ── Supported image extensions ────────────────────────────────────────────────
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".apng"}

# ── Vision prompt ─────────────────────────────────────────────────────────────
# Written for the actual image library: captioned conditioning photos and anime.
# The LLM is asked to read text overlays literally — this is the key signal for
# classifying these images since the caption IS the content.
_VISION_SYSTEM = (
    "You are a tagging assistant for a hypnosis and conditioning slideshow application. "
    "You analyse images and return structured metadata as JSON only — no prose, no markdown."
)

_VISION_PROMPT = """\
Analyse this image and return a JSON object with exactly these fields:

1. "caption_text": Copy any text overlay in the image verbatim. If no text, use "".

2. "tags": A JSON array of 3-6 lowercase tag strings chosen ONLY from these lists:

   Conditioning theme (pick 1-3):
     submission, obedience, bimbo, blank, mindless, arousal, sissy,
     feminization, praise, degradation, playful, commanding, teasing, dreamy

   Explicitness (pick exactly 1):
     mild, suggestive, explicit, graphic

   Style (pick exactly 1):
     photo-caption, anime-caption, illustrated, photo-only, anime-only

3. "open_tags": A JSON array of 1-5 completely FREE-FORM lowercase tags describing
   anything specific you observe that the fixed list above cannot capture.
   Examples: "feet", "latex", "stoner", "maid", "redhead", "outdoors", "crying",
   "hypno-eyes", "collar", "lingerie", "blonde", "makeup-heavy", "fantasy", "toys"
   These can be anything — body parts, props, aesthetics, subcultures, settings,
   clothing items, hair color, emotional state. Be specific and descriptive.
   Do NOT repeat tags already covered by the fixed "tags" list.

4. "quality": "keep" or "cull".
   Set "cull" if: heavily watermarked obscuring the subject, severely blurry or
   low resolution (< 300px), or a blank meme template with no real content.
   Otherwise "keep".

5. "style": repeat the style tag you chose from list 2.

Respond ONLY with valid JSON. Example:
{"tags": ["bimbo", "arousal", "suggestive", "photo-caption"], "open_tags": ["feet", "pink-hair", "latex-gloves"], "caption_text": "GET HORNY GET STUPID", "quality": "keep", "style": "photo-caption"}
"""


# ── LLM endpoint helper ───────────────────────────────────────────────────────

def _llm_base_url() -> str:
    return os.environ.get("SOMNA_LLM_URL", "http://localhost:8000").rstrip("/")


def _image_to_jpeg_bytes(image_path: Path) -> bytes:
    """Return JPEG bytes for any supported image format.

    For animated formats (GIF, WebP, APNG) we extract a single representative
    frame (middle frame) so the base64 payload stays small and the vision model
    gets a useful still image rather than a raw animation byte stream.
    For static images we re-encode as JPEG at 85% quality to keep payload size
    reasonable without noticeable quality loss for a classification task.
    """
    from PIL import Image, ImageSequence
    import io

    pil_im = Image.open(image_path)
    # Seek to middle frame for animated images
    frames = list(ImageSequence.Iterator(pil_im))
    frame  = frames[len(frames) // 2] if frames else pil_im
    if frame.mode not in ("RGB", "RGBA"):
        frame = frame.convert("RGB")
    if frame.mode == "RGBA":
        # Composite onto white background for JPEG
        bg = Image.new("RGB", frame.size, (255, 255, 255))
        bg.paste(frame, mask=frame.split()[3])
        frame = bg
    else:
        frame = frame.convert("RGB")

    # Resize if very large to keep payload under ~500 KB
    max_side = 768
    w, h = frame.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        frame = frame.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    frame.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _chat_with_vision(image_path: Path) -> dict:
    """Send an image to the KoboldCpp vision endpoint and parse the response.

    Uses the standard OpenAI /v1/chat/completions format with an image_url
    content block, which KoboldCpp mmproj supports.

    All image formats are normalised to JPEG before encoding so that:
    - Animated GIFs/WebPs send a single representative frame (not the raw bytes)
    - Payload sizes stay reasonable for the context window
    - JPEG is universally supported by vision backends

    Returns the raw parsed dict from the model, or raises on failure.
    """
    jpeg_bytes = _image_to_jpeg_bytes(image_path)
    b64_img    = base64.b64encode(jpeg_bytes).decode()
    data_url   = f"data:image/jpeg;base64,{b64_img}"

    payload = json.dumps({
        "model": os.environ.get("SOMNA_LLM_MODEL", ""),
        "messages": [
            {"role": "system", "content": _VISION_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text",      "text": _VISION_PROMPT},
                ],
            },
        ],
        "max_tokens": 256,
        "temperature": 0.1,
    }).encode()

    import urllib.request
    url = _llm_base_url() + "/v1/chat/completions"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())

    raw = data["choices"][0]["message"]["content"]
    return _parse_vision_response(raw)


def _repair_json_fragment(fragment: str) -> dict:
    """Try to parse a truncated JSON fragment.

    Identical to the repair logic in somna_agent.py — tracks brace depth and
    string state character-by-character.  Returns {} if nothing recoverable.
    """
    depth     = 0
    in_str    = False
    escaped   = False
    last_safe = -1

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
                try:
                    return json.loads(fragment[: i + 1])
                except json.JSONDecodeError:
                    pass
        elif c == "," and depth == 1:
            last_safe = i

    if last_safe > 0:
        try:
            return json.loads(fragment[: last_safe] + "}")
        except json.JSONDecodeError:
            pass
    return {}


def _extract_vision_json(raw: str) -> dict:
    """Robustly extract a JSON object from raw vision-model output.

    Handles all local-model formatting quirks observed in production:
      - <think>...</think> reasoning blocks (Qwen/DeepSeek)
      - Markdown code fences  ```json ... ```
      - Prefixed prose / trailing reasoning text
      - Truncated JSON output
      - Empty stub {} followed by the real object
    """
    if not raw:
        return {}

    # Strip <think>...</think> blocks (may be multi-line)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)

    # Strip markdown code fences
    raw = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    # Pass 1: scan backwards for the last non-empty complete {...} block.
    # Going backwards handles "{}\\n{real response}" by preferring the last.
    pos = len(raw)
    while True:
        end = raw.rfind("}", 0, pos)
        if end == -1:
            break
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
            pos = end
            continue

        if isinstance(parsed, list):
            parsed = next((x for x in parsed if isinstance(x, dict)), None)

        if isinstance(parsed, dict) and parsed:
            return parsed
        pos = end

    # Pass 2: fragment repair (JSON was truncated mid-output)
    start = raw.find("{")
    if start != -1:
        repaired = _repair_json_fragment(raw[start:])
        if repaired:
            return repaired

    return {}


def _parse_vision_response(raw: str) -> dict:
    """Extract and validate the JSON object from the vision model's response.

    Uses the same multi-pass robust extractor as somna_agent.py so that
    <think> blocks, markdown fences, and trailing reasoning text are all
    handled correctly.
    """
    data = _extract_vision_json(raw)
    if not data:
        return {"tags": [], "caption_text": "", "quality": "keep", "style": ""}

    # Sanitise fields
    tags      = [str(t).lower().strip() for t in data.get("tags",      []) if t]
    open_tags = [str(t).lower().strip() for t in data.get("open_tags", []) if t]
    caption   = str(data.get("caption_text", "")).strip()
    quality   = "cull" if str(data.get("quality", "keep")).lower() == "cull" else "keep"
    style     = str(data.get("style", "")).lower().strip()

    return {
        "tags":         tags,
        "open_tags":    open_tags,
        "caption_text": caption,
        "quality":      quality,
        "style":        style,
    }


# ── Storage helpers ───────────────────────────────────────────────────────────
# read_tags / save_tags / save_image_meta / get_tagged_filenames are imported
# from content_tools.somna_db.  Public aliases kept for external callers.
read_tags  = load_tags   # backward-compat alias
write_tags = save_tags   # backward-compat alias


def tag_image(
    session_name: str,
    filename: str,
    tags: list[str],
    open_tags: list[str] | None = None,
    caption_text: str = "",
    quality: str = "keep",
    style: str = "",
) -> None:
    """Upsert a single image's tag entry, merging with any existing tags."""
    existing        = load_tags(session_name).get(filename, {})
    merged_tags     = list(dict.fromkeys(existing.get("tags",      []) + tags))
    merged_open_tags = list(dict.fromkeys(existing.get("open_tags", []) + (open_tags or [])))
    save_image_meta(session_name, filename, {
        "tags":         merged_tags,
        "open_tags":    merged_open_tags,
        "caption_text": caption_text or existing.get("caption_text", ""),
        "quality":      quality,
        "style":        style or existing.get("style", ""),
    })


def images_for_tag(
    session_name: str,
    tag: str,
    exclude_culled: bool = True,
) -> list[str]:
    """Return filenames whose tags OR open_tags include the given tag.

    Searches both the controlled vocabulary (tags) and the free-form
    folksonomy (open_tags) so a query like "feet" or "latex" works even
    though it's not in the predefined tag list.

    Parameters
    ----------
    session_name : str
    tag : str
        Exact tag string or substring (e.g. "descent" matches "c2_descent").
    exclude_culled : bool
        If True (default), images flagged quality='cull' are excluded.
    """
    tag_map   = load_tags(session_name)
    results   = []
    tag_lower = tag.lower()
    for filename, meta in tag_map.items():
        if exclude_culled and meta.get("quality") == "cull":
            continue
        all_tags = [t.lower() for t in
                    meta.get("tags", []) + meta.get("open_tags", [])]
        if any(tag_lower in t or t in tag_lower for t in all_tags):
            results.append(filename)
    return results


# ── Auto-tagging ──────────────────────────────────────────────────────────────

def auto_tag_session(
    session_name: str,
    batch_size: int = 20,
    force: bool = False,
    progress_cb=None,
) -> dict:
    """Run vision-based tagging over all images in a session folder.

    Sends each image to the KoboldCpp vision endpoint, reads caption text,
    assigns thematic tags, and flags low-quality images for culling.
    Results are written to somna.db incrementally (crash-safe).

    Parameters
    ----------
    session_name : str
    batch_size : int
        Images to process per call (default 20). Use for rate-limiting.
        Pass None to process all images.
    force : bool
        Re-tag already-tagged images. Default False (skip existing entries).
    progress_cb : callable(done, total), optional
        Called after each image is processed.

    Returns
    -------
    dict: {tagged: int, skipped: int, errors: int, culled: int}
    """
    img_dir = _SESSIONS / session_name / "images"
    if not img_dir.exists():
        return {"error": f"No images folder for session '{session_name}'"}

    all_images = [
        p for p in img_dir.iterdir()
        if p.suffix.lower() in _IMAGE_EXTS
    ]
    if not all_images:
        return {"tagged": 0, "skipped": 0, "errors": 0, "culled": 0}

    tagged_set = get_tagged_filenames(session_name)
    to_process = (
        all_images if force
        else [p for p in all_images if p.name not in tagged_set]
    )
    if batch_size is not None:
        to_process = to_process[:batch_size]

    total   = len(to_process)
    tagged  = 0
    errors  = 0
    culled  = 0

    print(f"[ImageTags] Auto-tagging {total} images in '{session_name}' "
          f"({'force' if force else 'incremental'}) …")

    for i, img_path in enumerate(to_process):
        try:
            result = _chat_with_vision(img_path)
            save_image_meta(session_name, img_path.name, {
                "tags":         result["tags"],
                "open_tags":    result.get("open_tags", []),
                "caption_text": result["caption_text"],
                "quality":      result["quality"],
                "style":        result["style"],
            })
            tagged += 1
            if result["quality"] == "cull":
                culled += 1
            print(f"[ImageTags] [{i+1}/{total}] {img_path.name}: "
                  f"tags={result['tags']} open={result.get('open_tags',[])} "
                  f"quality={result['quality']}")
        except Exception as exc:
            errors += 1
            print(f"[ImageTags] [{i+1}/{total}] Error tagging {img_path.name}: {exc}")

        if progress_cb:
            progress_cb(i + 1, total)

    skipped = len(all_images) - len(to_process)
    print(f"[ImageTags] Done: {tagged} tagged, {skipped} skipped, "
          f"{errors} errors, {culled} flagged for culling.")
    return {"tagged": tagged, "skipped": skipped, "errors": errors, "culled": culled}


# ── Quality culling ───────────────────────────────────────────────────────────

def cull_session(session_name: str) -> list[str]:
    """Return filenames flagged quality='cull'. Does NOT delete anything.

    Review the list and delete manually, or pass to a separate cleanup script.
    """
    tag_map = load_tags(session_name)
    return [
        filename for filename, meta in tag_map.items()
        if meta.get("quality") == "cull"
    ]


# ── Stats ─────────────────────────────────────────────────────────────────────

def tag_stats(session_name: str) -> dict:
    """Return a summary of tag frequencies and quality counts for a session.

    Useful for the agent to understand what's in the image pool:
        {
          "total": 7000,
          "tagged": 150,
          "untagged": 6850,
          "culled": 12,
          "tag_counts": {"bimbo": 80, "explicit": 60, "blank": 30, ...},
          "captions_extracted": 140
        }
    """
    img_dir = _SESSIONS / session_name / "images"
    if not img_dir.exists():
        return {"total": 0, "tagged": 0, "untagged": 0, "culled": 0,
                "tag_counts": {}, "captions_extracted": 0}

    all_files = [
        p for p in img_dir.iterdir()
        if p.suffix.lower() in _IMAGE_EXTS
    ]
    tag_map   = load_tags(session_name)
    culled    = sum(1 for m in tag_map.values() if m.get("quality") == "cull")
    captions  = sum(1 for m in tag_map.values() if m.get("caption_text"))

    all_tags:      list[str] = []
    all_open_tags: list[str] = []
    for meta in tag_map.values():
        all_tags.extend(meta.get("tags",      []))
        all_open_tags.extend(meta.get("open_tags", []))

    tag_counts      = dict(Counter(all_tags).most_common())
    open_tag_counts = dict(Counter(all_open_tags).most_common())

    return {
        "total":               len(all_files),
        "tagged":              len(tag_map),
        "untagged":            len(all_files) - len(tag_map),
        "culled":              culled,
        "tag_counts":          tag_counts,
        "open_tag_counts":     open_tag_counts,
        "captions_extracted":  captions,
    }


# ── Affirmation harvest ───────────────────────────────────────────────────────

def _clean_caption(text: str) -> str | None:
    """Return a cleaned affirmation string, or None if the text is junk.

    Filters out:
    - Copyright notices and watermarks  (©, (c), "all rights reserved")
    - URLs and domain names             (.com/.net/.org, http, www.)
    - Social media handles              (@username, patreon.com/...)
    - Artist attributions               ("by X", "art by", "photo by")
    - Digits-heavy strings              (phone numbers, dates, serial numbers)
    - Strings that are mostly symbols   (little alphabetic content)
    - Strings that are ALL CAPS single words (usually watermarks like "WATERMARK")

    Returns the cleaned string (trailing/leading punct stripped, whitespace
    normalised) or None if the string failed the noise checks.
    """
    import re

    t = " ".join(text.split())  # normalise whitespace

    tl = t.lower()

    # ── Hard-reject patterns ──────────────────────────────────────────────────
    _NOISE_PATTERNS = [
        r"©",                          # copyright symbol
        r"\(c\)\s",                    # (c) attribution
        r"all rights reserved",
        r"https?://",                  # URLs
        r"www\.",
        r"\b\w+\.(com|net|org|io|co|tv|me|cc|xxx)\b",  # domain names
        r"@\w+",                       # social handles
        r"\bpatreon\b",
        r"\bonly\s*fans\b",
        r"\bsubscribe\b",
        r"\bfollow\s+(me|us)\b",
        r"\bdeviantart\b",
        r"\btumblr\b",
        r"\bpixiv\b",
        r"\bfanbox\b",
        r"\bbooru\b",
        r"\bgelbooru\b",
        r"\bsankaku\b",
        r"\btwitter\b",
        r"\binstagram\b",
        r"\bart\s+by\b",
        r"\bphoto\s+by\b",
        r"\bdrawing\s+by\b",
        r"\bdrawn\s+by\b",
        r"\billustration\s+by\b",
        r"\boriginal\s+by\b",
        r"\bcredit\s*:",
        r"\bsource\s*:",
    ]
    for pat in _NOISE_PATTERNS:
        if re.search(pat, tl):
            return None

    # ── Digit density: reject if > 30% of chars are digits ───────────────────
    digits = sum(c.isdigit() for c in t)
    if len(t) > 0 and digits / len(t) > 0.30:
        return None

    # ── Symbol density: reject if < 50% of chars are letters/spaces ──────────
    alpha_space = sum(c.isalpha() or c == " " for c in t)
    if len(t) > 0 and alpha_space / len(t) < 0.50:
        return None

    # ── All-caps single token (watermark style: "SHINYBOUND", "CAPTIONED") ────
    tokens = t.split()
    if len(tokens) == 1 and t.isupper() and len(t) > 4:
        return None

    # ── Clean trailing/leading punctuation ───────────────────────────────────
    t = t.strip(".,!?;:\"'()[]{}—-")
    t = t.strip()

    return t if t else None


def harvest_captions_to_affirmations(
    session_name: str,
    target_session: str | None = None,
    tag_filter: str | None = None,
    min_length: int = 3,
    max_length: int = 80,
) -> dict:
    """Extract caption_text from the DB and append to a session's affirmations.txt.

    Caption texts from existing images are human-curated conditioning phrases.
    This harvests them into the affirmation pool (deduplicated, cleaned).

    Parameters
    ----------
    session_name : str
        Session whose image metadata to read captions from.
    target_session : str, optional
        Session to write affirmations to. Defaults to session_name.
    tag_filter : str, optional
        Only harvest captions from images matching this tag.
    min_length : int
        Minimum character count for a phrase to be included (default 3).
    max_length : int
        Maximum character count (default 80 — avoids entire paragraphs).

    Returns
    -------
    dict: {harvested: int, duplicates_skipped: int, written_to: str}
    """
    try:
        from content_tools.affirmations import _affirmations_path
    except ImportError:
        return {"error": "content_tools.affirmations not available"}

    target = target_session or session_name
    tag_map = load_tags(session_name)

    # Collect and clean captions
    captions: list[str] = []
    for filename, meta in tag_map.items():
        if tag_filter:
            all_tags  = (meta.get("tags", []) + meta.get("open_tags", []))
            tag_lower = tag_filter.lower()
            if not any(tag_lower in t.lower() or t.lower() in tag_lower
                       for t in all_tags):
                continue
        caption = meta.get("caption_text", "").strip()
        if not caption:
            continue
        cleaned = _clean_caption(caption)
        if cleaned and min_length <= len(cleaned) <= max_length:
            captions.append(cleaned)

    if not captions:
        return {"harvested": 0, "duplicates_skipped": 0, "written_to": ""}

    # Read existing affirmations to deduplicate
    aff_path = _SESSIONS / target / "affirmations.txt"
    existing: set[str] = set()
    if aff_path.exists():
        for line in aff_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().lower()
            if stripped and not stripped.startswith("#"):
                existing.add(stripped)

    try:
        from content_tools.affirmations import _sanitize_phrase as _san
    except ImportError:
        _san = None  # type: ignore

    new_phrases  = []
    skipped      = 0
    for caption in captions:
        if _san is not None:
            caption = _san(caption)
            if caption is None:
                skipped += 1
                continue
        if caption.lower() in existing:
            skipped += 1
        else:
            new_phrases.append(caption)
            existing.add(caption.lower())

    if not new_phrases:
        return {"harvested": 0, "duplicates_skipped": skipped,
                "written_to": str(aff_path)}

    aff_path.parent.mkdir(parents=True, exist_ok=True)
    with open(aff_path, "a", encoding="utf-8") as f:
        f.write(f"\n# Harvested from image captions — {time.strftime('%Y-%m-%d')}\n")
        for phrase in new_phrases:
            f.write(phrase + "\n")

    print(f"[ImageTags] Harvested {len(new_phrases)} captions → {aff_path} "
          f"({skipped} duplicates skipped)")
    return {
        "harvested":          len(new_phrases),
        "duplicates_skipped": skipped,
        "written_to":         str(aff_path),
    }


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Vision-based image tagger for Somna session libraries."
    )
    sub = parser.add_subparsers(dest="cmd")

    p_tag = sub.add_parser("tag", help="Auto-tag images in a session")
    p_tag.add_argument("session")
    p_tag.add_argument("--batch",   type=int, default=20,
                       help="Images to tag per run (default 20; use 0 for all)")
    p_tag.add_argument("--force",   action="store_true",
                       help="Re-tag already-tagged images")
    p_tag.add_argument("--harvest", action="store_true",
                       help="Also harvest caption text into affirmations.txt after tagging")

    p_cull = sub.add_parser("cull", help="List images flagged for culling")
    p_cull.add_argument("session")

    p_stats = sub.add_parser("stats", help="Show tag statistics")
    p_stats.add_argument("session")

    p_harvest = sub.add_parser("harvest", help="Harvest captions to affirmations.txt")
    p_harvest.add_argument("session")
    p_harvest.add_argument("--target",     default=None,
                           help="Target session for affirmations (default: same session)")
    p_harvest.add_argument("--tag-filter", default=None,
                           help="Only harvest images matching this tag")

    args = parser.parse_args()

    if args.cmd == "tag":
        batch = args.batch if args.batch > 0 else None
        result = auto_tag_session(args.session, batch_size=batch, force=args.force)
        print(json.dumps(result, indent=2))
        if args.harvest and result.get("tagged", 0) > 0:
            print("\n── Harvesting captions → affirmations.txt …")
            h = harvest_captions_to_affirmations(args.session)
            print(json.dumps(h, indent=2))

    elif args.cmd == "cull":
        culled = cull_session(args.session)
        print(f"{len(culled)} images flagged for culling:")
        for f in culled:
            print(f"  {f}")

    elif args.cmd == "stats":
        stats = tag_stats(args.session)
        print(json.dumps(stats, indent=2))

    elif args.cmd == "harvest":
        result = harvest_captions_to_affirmations(
            args.session,
            target_session=args.target,
            tag_filter=args.tag_filter,
        )
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()
