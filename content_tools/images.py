"""
content_tools/images.py — Background image generation via KoboldCpp.

Generates images using the KoboldCpp A1111-compatible /sdapi/v1/txt2img
endpoint (FLUX model). The server URL is shared with the LLM (SOMNA_LLM_URL).
Saves generated PNGs to sessions/<name>/images/ with a timestamped filename.
"""

from __future__ import annotations

import base64
import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

_ROOT     = Path(__file__).parent.parent
_SESSIONS = _ROOT / "sessions"

# ── Endpoint helpers ──────────────────────────────────────────────────────────

def _llm_base_url() -> str:
    """Base URL for the KoboldCpp server (shared LLM + image gen instance)."""
    return os.environ.get("SOMNA_LLM_URL", "http://localhost:8000").rstrip("/")


def _images_dir(session_name: str) -> Path:
    d = _SESSIONS / session_name / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Prompt builder ────────────────────────────────────────────────────────────

# Each template is a (setting, lighting, composition, mood) tuple.
# The LLM or caller selects caption/subject; the template handles visual style.
# Using natural language avoids the "JSON key leakage" problem with FLUX on
# A1111-compatible endpoints, which render the entire prompt string literally.

_VISUAL_TEMPLATES = [
    # Studio portrait
    {
        "setting":     "clean studio backdrop, seamless white or soft gradient",
        "lighting":    "professional studio lighting, soft box, catchlight in eyes",
        "composition": "centered portrait, shoulder to waist framing",
        "mood":        "confident, direct gaze, commanding presence",
    },
    # Dreamy boudoir
    {
        "setting":     "soft bedroom, silk sheets, gauzy curtains diffusing warm light",
        "lighting":    "golden hour, backlit, hazy warm glow",
        "composition": "three-quarter angle, intimate close-up",
        "mood":        "soft, hazy, dreamy, vulnerable",
    },
    # Neon cyberpunk
    {
        "setting":     "dark urban environment, neon signs, rain-slicked streets",
        "lighting":    "neon pink and blue rim lighting, high contrast shadows",
        "composition": "dramatic low angle, full figure, environmental portrait",
        "mood":        "hypnotic, electric, otherworldly",
    },
    # Minimal abstract
    {
        "setting":     "pure white void, no background details, isolated subject",
        "lighting":    "flat even lighting, no shadows, graphic quality",
        "composition": "dead center framing, symmetrical, magazine editorial",
        "mood":        "blank, empty, drone-like obedience, no personality",
    },
    # Vintage glamour
    {
        "setting":     "art deco interior, velvet curtains, ornate decor",
        "lighting":    "cinematic chiaroscuro, old Hollywood glamour lighting",
        "composition": "classic glamour portrait, three-quarter body, dramatic pose",
        "mood":        "theatrical, commanding, femme fatale energy",
    },
    # Anime flat
    {
        "setting":     "simple solid color background, anime style environment",
        "lighting":    "flat cel shading, clean anime lighting",
        "composition": "full body or bust shot, dynamic pose, anime proportions",
        "mood":        "cute, expressive, suggestive, playful",
    },
    # Garden / outdoor
    {
        "setting":     "lush garden, soft bokeh foliage, dappled sunlight",
        "lighting":    "natural dappled light, soft outdoor, golden hour",
        "composition": "candid lifestyle portrait, relaxed pose",
        "mood":        "soft, approachable, sensual innocence",
    },
    # Dark ritual
    {
        "setting":     "dimly lit altar, candles, dark stone walls, mystical setting",
        "lighting":    "candlelight only, deep shadows, flickering warmth",
        "composition": "full figure, ritual pose, symmetrical framing",
        "mood":        "occult, submission ritual, reverent, trance-like",
    },
]

_INTENSITY_CLOTHING = {
    "mild":       "elegantly dressed, tasteful, fully clothed",
    "suggestive": "revealing outfit, lingerie or low-cut, alluring",
    "explicit":   "topless or nude, explicit content",
    "graphic":    "fully nude, graphic explicit content",
}

_STYLE_MEDIUM = {
    "photo": "photorealistic photograph, 85mm lens, professional photography, ultra detailed",
    "anime": "anime illustration, cel shaded, clean crisp lineart, vibrant colors, manga style",
}

_NEGATIVE = (
    "deformed anatomy, extra limbs, missing limbs, fused fingers, "
    "blurry, low resolution, jpeg artifacts, watermark, signature, "
    "text watermark, logo, cropped head, out of frame"
)


def build_conditioning_prompt(
    theme: str,
    tags: list[str] | None = None,
    intensity: str = "suggestive",
    style: str = "photo",
    color_hint: str = "",
    caption_text: str = "",
    template_index: int | None = None,
) -> str:
    """Build a FLUX-native natural-language prompt for conditioning images.

    Writes a prose paragraph — subject, clothing/appearance, pose, setting,
    lighting, mood — as FLUX expects. Does NOT emit SD1.5-era keyword lists
    or quality tokens ('masterpiece', '8k', etc.) that FLUX ignores or misreads.

    caption_text is prepended as a hard constraint so FLUX sees it in its
    first tokens (early-token dominance); it is also woven into the scene.
    Template selection is random or pinned for reproducibility.

    Parameters
    ----------
    theme : str
        Conditioning theme, e.g. "blank obedience" or "soft surrender".
    tags : list[str], optional
        Additional visual/thematic descriptors folded into the prose.
    intensity : str
        "mild" | "suggestive" | "explicit" | "graphic"
    style : str
        "photo" | "anime"
    color_hint : str
        Optional palette hint, e.g. "pink and white".
    caption_text : str
        Caption text to bake into the image as a legible text overlay.
    template_index : int | None
        Pin a specific visual setting (0-7). Random if None.
    """
    idx      = (template_index if template_index is not None
                else random.randrange(len(_VISUAL_TEMPLATES)))
    template = _VISUAL_TEMPLATES[idx % len(_VISUAL_TEMPLATES)]

    style_word = "an anime illustration with clean cel shading" if style == "anime" else "a photorealistic photograph"
    color_str  = color_hint if color_hint else "soft pink and white tones"

    clothing_map = {
        "mild":       "elegantly dressed",
        "suggestive": "wearing lingerie or a revealing outfit",
        "explicit":   "topless",
        "graphic":    "nude",
    }
    clothing = clothing_map.get(intensity, "wearing lingerie")

    tag_detail = ""
    unique_tags = [t for t in (tags or []) if t.replace("_", " ").lower() not in theme.lower()]
    if unique_tags:
        tag_detail = " ".join(unique_tags[:4])

    prose = (
        f"{style_word} of a beautiful woman who is {theme}. "
        f"She is {clothing}, {tag_detail + ', ' if tag_detail else ''}"
        f"with {color_str} coloring throughout. "
        f"She is in a {template['setting']}, lit by {template['lighting']}. "
        f"The composition is {template['composition']}. "
        f"Mood: {template['mood']}. "
        f"No watermarks or logos."
    )

    if caption_text:
        cap_upper = caption_text.strip().upper()
        prefix    = f'The words "{cap_upper}" appear in large, bold, legible text on this image. '
        return prefix + prose
    return prose


# ── KoboldCpp backend ─────────────────────────────────────────────────────────

def _generate_koboldcpp(
    prompt: str,
    steps: int = 8,
    width: int = 1024,
    height: int = 1024,
    cfg_scale: float = 1.0,
    sampler: str = "Euler",
    scheduler: str = "Beta",
    shift: float = 7.0,
) -> bytes:
    """POST to KoboldCpp's A1111-compatible /sdapi/v1/txt2img and return PNG bytes.

    KoboldCpp exposes the same A1111 image generation API, so the endpoint and
    response format are identical to A1111.  FLUX-specific parameters (scheduler,
    shift) are passed via override_settings which KoboldCpp forwards to sd.cpp.
    """
    url = _llm_base_url() + "/sdapi/v1/txt2img"
    payload = json.dumps({
        "prompt":       prompt,
        "steps":        steps,
        "width":        width,
        "height":       height,
        "cfg_scale":    cfg_scale,
        "sampler_name": sampler,
        "override_settings": {
            "sd_scheduler": scheduler,
            "s_noise":      shift,      # shift/noise parameter for FLUX
        },
    }).encode()

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw_body = resp.read()
    except urllib.error.HTTPError as exc:
        err_body = exc.read() or b""
        snippet = err_body[:500].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"KoboldCpp txt2img HTTP {exc.code} {exc.reason}: {snippet!r}"
        ) from exc
    if not raw_body.strip():
        raise RuntimeError(
            "KoboldCpp /sdapi/v1/txt2img returned an empty body — "
            "is image gen enabled and the server reachable?"
        )
    try:
        data = json.loads(raw_body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        snippet = raw_body[:400].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"KoboldCpp txt2img response is not JSON ({exc}). "
            f"First bytes: {snippet!r}"
        ) from exc

    images = data.get("images")
    if not images:
        raise RuntimeError(
            f"KoboldCpp returned no images. Response: {str(data)[:300]}"
        )

    return base64.b64decode(images[0])


# ── Public API ────────────────────────────────────────────────────────────────

def _load_imggen_config() -> dict:
    """Load image_gen defaults from agent_config.yaml if available."""
    cfg_path = _ROOT / "agent_config.yaml"
    try:
        import yaml
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("image_gen", {})
    except Exception:
        return {}


def generate_image(
    session_name: str,
    prompt: str,
    steps: int | None = None,
    width: int | None = None,
    height: int | None = None,
    cfg_scale: float | None = None,
    sampler: str | None = None,
    scheduler: str | None = None,
    shift: float | None = None,
    # Legacy positional args kept for backwards compat (ignored)
    negative_prompt: str = "",
) -> dict:
    """Generate an image and save it to sessions/<name>/images/.

    FLUX parameters default to agent_config.yaml image_gen section values,
    falling back to the hardcoded FLUX defaults.

    Returns
    -------
    dict with keys: session_name, filename, path, width, height, prompt,
                    size_kb, error (only present on failure)
    """
    cfg = _load_imggen_config()

    steps     = steps     if steps     is not None else cfg.get("steps",     8)
    width     = width     if width     is not None else cfg.get("width",     1024)
    height    = height    if height    is not None else cfg.get("height",    1024)
    cfg_scale = cfg_scale if cfg_scale is not None else cfg.get("cfg_scale", 1.0)
    sampler   = sampler   if sampler   is not None else cfg.get("sampler",   "Euler")
    scheduler = scheduler if scheduler is not None else cfg.get("scheduler", "Beta")
    shift     = shift     if shift     is not None else cfg.get("shift",     7.0)

    try:
        png_bytes = _generate_koboldcpp(
            prompt=prompt,
            steps=steps,
            width=width,
            height=height,
            cfg_scale=cfg_scale,
            sampler=sampler,
            scheduler=scheduler,
            shift=shift,
        )
    except Exception as exc:
        return {
            "session_name": session_name,
            "error":        str(exc),
            "prompt":       prompt,
        }

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename  = f"gen_{timestamp}.png"
    dest_dir  = _images_dir(session_name)
    dest_path = dest_dir / filename
    dest_path.write_bytes(png_bytes)

    return {
        "session_name": session_name,
        "filename":     filename,
        "path":         str(dest_path),
        "width":        width,
        "height":       height,
        "prompt":       prompt,
        "size_kb":      round(len(png_bytes) / 1024, 1),
    }


def generate_and_tag(
    session_name: str,
    tag: str,
    prompt: str,
    n: int = 4,
    **kwargs,
) -> dict:
    """Generate n images and register each one in tags.json under the given tag.

    Parameters
    ----------
    session_name : str
        Session folder name.
    tag : str
        Tag string to apply to all generated images (e.g. "blank", "descent").
    prompt : str
        Positive prompt for image generation.
    n : int
        Number of images to generate (default 4).
    **kwargs
        Forwarded to generate_image() (steps, width, height, etc.).

    Returns
    -------
    dict with keys: generated (list of filenames), errors (list of error strings)
    """
    try:
        from content_tools.image_tags import tag_image
    except ImportError:
        return {"generated": [], "errors": ["image_tags module not available"]}

    generated = []
    errors    = []

    for i in range(n):
        result = generate_image(session_name, prompt, **kwargs)
        if "error" in result:
            errors.append(result["error"])
            print(f"[ImageGen] Generation {i+1}/{n} failed: {result['error']}")
        else:
            filename = result["filename"]
            tag_image(
                session_name, filename,
                tags=[tag, "generated"],
                quality="keep",
                style="photo",
            )
            generated.append(filename)
            print(f"[ImageGen] Generated and tagged '{filename}' → [{tag}]")

    return {"generated": generated, "errors": errors}


def list_images(session_name: str) -> list[str]:
    """Return filenames of all images in a session's images/ folder."""
    img_dir = _SESSIONS / session_name / "images"
    if not img_dir.exists():
        return []
    return sorted(
        f.name for f in img_dir.iterdir()
        if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    )
