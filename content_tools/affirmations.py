"""
content_tools/affirmations.py — Affirmation file read/write utilities.

Handles structured affirmations.txt files with tagged sections.
Tag format:  # [tag_name]  followed by phrases.

Line syntax:
  plain text           → single phrase
  word | word2         → random variants (phrase_pool picks one at random)
  word >> word2 >> …   → sequential chain (phrase_pool advances cursor in order)

_parse_tags stores every content line as a verbatim string so chain syntax
(>>) is preserved on round-trip without any special handling here.
The >> splitting happens at read-time inside phrase_pool.py and timeline_runner.py.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Optional


def _sanitize_phrase(text: str) -> str | None:
    """Clean and validate a single affirmation phrase.

    Rejects or fixes phrases that would cause TTS 503 errors or pollute
    the affirmation pool with noise from harvested captions / LLM output.
    Returns None if the phrase should be discarded.
    """
    if not isinstance(text, str):
        return None
    t = html.unescape(text)  # &amp; → &, &#39; → '
    t = re.sub(r"<[^>]+>", "", t)  # strip HTML/XML tags
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", t)  # drop control chars
    # Normalize smart quotes and dashes to plain ASCII
    t = t.replace("\u2018", "'").replace("\u2019", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.replace("\u2013", "-").replace("\u2014", "-")
    t = t.strip().rstrip(".,!?;:").lower()
    if not t:
        return None
    # Reject URLs and bare filenames
    if re.search(r"https?://|www\.|\.com|\.png|\.jpg|\.gif|\.webp", t, re.I):
        return None
    words = t.split()
    # Too short (single word) or too long (wall of text) — both break TTS
    if len(words) < 2 or len(words) > 50:
        return None
    return t


_ROOT = Path(__file__).parent.parent
_SESSIONS = _ROOT / "sessions"


def _session_dir(session_name: str) -> Path:
    return _SESSIONS / session_name


def _affirmations_path(session_name: str) -> Path:
    return _session_dir(session_name) / "affirmations.txt"


# ── Parsing ───────────────────────────────────────────────────────────────────


def _parse_tags(text: str) -> dict[str, list[str]]:
    """Parse affirmations.txt into {tag: [lines]} dict.

    Lines starting with '#' that match '# [tag]' are section headers.
    Non-comment, non-empty lines are stored verbatim (including any | or >>
    syntax) so that round-trips preserve the original syntax exactly.
    Lines before the first tag header go into the 'general' bucket.
    """
    tags: dict[str, list[str]] = {}
    current_tag: Optional[str] = None

    for line in text.splitlines():
        # Section header
        m = re.match(r"^#\s*\[(\w+)\]", line)
        if m:
            current_tag = m.group(1)
            tags.setdefault(current_tag, [])
            continue
        # Comment or empty — skip
        if line.startswith("#") or not line.strip():
            continue
        if current_tag is not None:
            tags[current_tag].append(line.strip())
        else:
            # Lines before any # [tag] header — always-active pool (see SESSION docs)
            tags.setdefault("general", []).append(line.strip())

    return tags


def _serialise_tags(tags: dict[str, list[str]]) -> str:
    """Serialise {tag: [phrases]} back to affirmations.txt text."""
    blocks = []
    for tag, phrases in tags.items():
        header = f"# {'─' * 77}\n# [{tag}]\n# {'─' * 77}\n"
        body = "\n".join(phrases) + "\n" if phrases else "\n"
        blocks.append(header + "\n" + body)
    return "\n".join(blocks)


# ── Public API ────────────────────────────────────────────────────────────────


def read_affirmations(session_name: str) -> str:
    """Return the raw text of a session's affirmations.txt, or '' if absent."""
    path = _affirmations_path(session_name)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def list_tags(session_name: str) -> list[str]:
    """Return the list of tag names present in a session's affirmations file."""
    text = read_affirmations(session_name)
    return list(_parse_tags(text).keys())


def count_phrases(session_name: str, tag: str) -> int:
    """Return the number of phrase lines under a given tag. 0 if tag absent."""
    text = read_affirmations(session_name)
    return len(_parse_tags(text).get(tag, []))


def write_affirmations(
    session_name: str,
    tag: str,
    phrases: list[str],
    mode: str = "append",
) -> dict:
    """Append or replace a tagged phrase section in affirmations.txt.

    Parameters
    ----------
    session_name : str
        Folder name under sessions/.
    tag : str
        The tag to write (e.g. 'deep', 'relax').
    phrases : list[str]
        Phrases to write.  Pipe variants: "phrase | variant".
        Sequential chains: "word >> word2 >> word3".
    mode : 'append' | 'replace'
        append — add phrases to the existing tag block (creates tag if absent).
        replace — overwrite the tag block entirely.

    Returns
    -------
    dict with keys: session_name, tag, phrases_written, total_in_tag, path
    """
    path = _affirmations_path(session_name)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Sanitize all incoming phrases at write time
    _raw = [_sanitize_phrase(p) for p in phrases]
    phrases = [p for p in _raw if p is not None]

    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    tags = _parse_tags(existing)

    if mode == "replace":
        tags[tag] = list(phrases)
    else:
        existing_phrases = tags.get(tag, [])
        existing_lower = {p.lower() for p in existing_phrases}
        new_phrases = [p for p in phrases if p.lower() not in existing_lower]
        tags[tag] = existing_phrases + new_phrases

    new_text = _serialise_tags(tags)
    path.write_text(new_text, encoding="utf-8")

    return {
        "session_name": session_name,
        "tag": tag,
        "phrases_written": len(phrases),
        "total_in_tag": len(tags[tag]),
        "path": str(path),
    }


def generate_and_append(
    session_name: str,
    tag: str,
    context: str,
    llm_url: str | None = None,
    llm_model: str | None = None,
    count: int = 15,
) -> dict:
    """Generate new affirmation phrases via the local LLM and append them.

    This is the auto-trigger entry point called by somna_agent._check_content_needs().

    Parameters
    ----------
    session_name : str
    tag : str
        Tag to write to (e.g. 'deep').
    context : str
        Free-text context describing what kind of content is needed (e.g.
        "theta-depth feminization subliminals, 1–4 words each").
    llm_url : str, optional
        Overrides SOMNA_LLM_URL env var.
    llm_model : str, optional
        Overrides SOMNA_LLM_MODEL env var.
    count : int
        Number of phrases to request.

    Returns
    -------
    dict from write_affirmations()
    """
    import json
    import os
    import urllib.request

    url = (
        llm_url or os.environ.get("SOMNA_LLM_URL", "http://localhost:11434")
    ) + "/v1/chat/completions"
    model = llm_model or os.environ.get("SOMNA_LLM_MODEL", "llama3.1")

    existing = read_affirmations(session_name)
    existing_snippet = existing[:1500] if existing else "(none)"

    system_msg = (
        "You are an expert hypnosis content writer specialising in subliminal "
        "affirmations for trance sessions. You write short, punchy, deeply "
        "effective phrases. Use minimal punctuation — only for emphasis "
        "(e.g. '...' or '!'). Never end a phrase with a period. "
        "You output ONLY a JSON array of strings — no explanation, no preamble, "
        "no markdown. Just the array."
    )
    user_msg = (
        f"Session: {session_name!r}  Tag: {tag!r}\n"
        f"Context: {context}\n\n"
        f"Existing affirmations (for reference, do not repeat exactly):\n"
        f"{existing_snippet}\n\n"
        f"Generate exactly {count} new affirmation phrases for the [{tag}] section. "
        f"Short, hypnotic, no terminal periods. "
        f"Output ONLY a JSON array of strings."
    )

    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.85,
            "top_p": 0.8,
            # KoboldCpp: disable thinking blocks so the model outputs the array
            # immediately without emitting a reasoning trace first.
            "chat_template_kwargs": {"enable_thinking": False},
            "rep_pen": 1.0,
            "top_k": 20,
        }
    ).encode()

    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        raw = data["choices"][0]["message"]["content"]
        # Strip think-blocks (DeepSeek/Qwen3 reasoning traces)
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        # Strip markdown code fences
        raw = re.sub(r"```[^\n]*", "", raw).strip()
        # Extract the FIRST complete balanced JSON array, ignoring any
        # trailing garbage or duplicate arrays the model emits after it.
        start = raw.find("[")
        if start == -1:
            raise ValueError(f"No JSON array in output: {raw[:300]!r}")
        depth = 0
        end = -1
        for i, ch in enumerate(raw[start:], start):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            raise ValueError(f"Unclosed JSON array in output: {raw[:300]!r}")
        phrases = json.loads(raw[start : end + 1])
        if not isinstance(phrases, list):
            raise ValueError(f"LLM returned non-list: {raw[start : end + 1][:200]}")
        phrases = [str(p).strip().rstrip(".") for p in phrases if str(p).strip()]
    except Exception as exc:
        print(
            f"[Affirmations] generate_and_append error for {session_name}/{tag}: {exc}"
        )
        return {
            "error": str(exc),
            "phrases_written": 0,
            "session_name": session_name,
            "tag": tag,
        }

    return write_affirmations(session_name, tag, phrases, mode="append")


def audit_affirmations(
    session_name: str,
    llm_url: str | None = None,
    llm_model: str | None = None,
) -> dict:
    """Run an LLM-powered quality audit on a session's affirmations.txt.

    The audit does three things in one pass:
    - Culls: removes phrases that are broken, too long, generic, off-theme,
      or redundant.
    - Chains: groups sequential progressions with >> syntax.
    - Variants: groups alt-phrasings of the same idea with | syntax.
    - Tags: organises untagged or miscategorised phrases into the correct
      # [tag] sections matching the session's existing phase labels.

    Phrases that appear in effective_moments in user_profile.json are
    flagged as protected and the LLM is told not to remove them.

    Returns a dict with before/after phrase counts, any error, and the
    written path.
    """
    import json
    import os
    import urllib.request

    path = _affirmations_path(session_name)
    if not path.exists():
        return {
            "error": f"No affirmations.txt found for session {session_name!r}",
            "session_name": session_name,
        }

    original_text = path.read_text(encoding="utf-8")
    original_tags = _parse_tags(original_text)
    original_count = sum(len(v) for v in original_tags.values())

    # ── Collect protected phrases from effective_moments ──────────────────
    protected: list[str] = []
    try:
        profile_path = _ROOT / "user_profile.json"
        if profile_path.exists():
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            for moment in profile.get("effective_moments", []):
                phrase = (moment.get("affirmation") or "").strip().lower()
                if phrase and len(phrase) >= 3:
                    protected.append(phrase)
            protected = list(dict.fromkeys(protected))  # dedup, preserve order
    except Exception:
        pass

    # ── Collect existing tag names as context ─────────────────────────────
    existing_tags = list(original_tags.keys())

    url = (
        llm_url or os.environ.get("SOMNA_LLM_URL", "http://localhost:11434")
    ) + "/v1/chat/completions"
    model = llm_model or os.environ.get("SOMNA_LLM_MODEL", "llama3.1")

    protected_block = (
        f"\nPROTECTED phrases (do NOT remove — these are known effective phrases "
        f"for this user):\n" + "\n".join(f"  - {p}" for p in protected) + "\n"
        if protected
        else ""
    )

    system_msg = (
        "You are an expert editor of hypnotic affirmation pools for trance sessions. "
        "You receive a raw affirmations.txt file and return a clean, reorganised version. "
        "You MUST return ONLY the complete revised file contents — no preamble, "
        "no explanation, no markdown fences. Just the file."
    )

    user_msg = (
        f"Session: {session_name!r}\n"
        f"Existing tag sections: {existing_tags}\n"
        f"{protected_block}\n"
        "── FILE SYNTAX ──────────────────────────────────────────────────────\n"
        "  plain line          → single phrase delivered in rotation\n"
        "  a | b | c           → variants: pool picks ONE at random each time\n"
        "  a >> b >> c         → chain: pool delivers these IN ORDER on successive turns\n"
        "  # [tag_name]        → section header; timeline activates specific tags\n"
        "  # comment           → ignored by the pool\n"
        "Double-headers are normal (each # [tag] appears twice — keep that pattern).\n\n"
        "── AUDIT INSTRUCTIONS ───────────────────────────────────────────────\n"
        "1. CULL any phrase that is: too long (>10 words), grammatically broken, "
        "   generic/flat (could appear in any app), redundant with another phrase, "
        "   or breaks the session's psychological theme/tone. Quality over quantity.\n"
        "2. CHAIN sequential progressions with >>. Only chain phrases that make "
        "   narrative or kinesthetic sense in that exact order. "
        "   Example: 'sinking >> deeper >> nothing left' works. "
        "   Don't force chains — loose phrases are fine unlinked.\n"
        "3. VARIANT group phrases that are alt-phrasings of the same idea with |. "
        "   Example: 'let go | release | surrender' — pool picks one each time. "
        "   Only group if they're truly interchangeable in context.\n"
        "4. TAGS: keep existing # [tag] structure. Move misplaced phrases to the "
        "   correct section. Do NOT create new tags not in the existing list unless "
        "   there are clearly orphaned untagged phrases that need a home.\n"
        "5. Do NOT touch PROTECTED phrases — they must appear verbatim in the output.\n"
        "6. Keep the double-header format for each section (two # [tag] lines).\n"
        "7. All phrases must be lowercase, no terminal punctuation.\n\n"
        "── CURRENT FILE ─────────────────────────────────────────────────────\n"
        f"{original_text}"
    )

    try:
        payload = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.4,
                "max_tokens": 4096,
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            revised = data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        print(f"[Affirmations] audit LLM error for {session_name!r}: {exc}")
        return {
            "error": str(exc),
            "session_name": session_name,
            "original_count": original_count,
        }

    # Strip any accidental markdown fences the model may have added
    if revised.startswith("```"):
        revised = re.sub(r"^```[^\n]*\n?", "", revised)
        revised = re.sub(r"\n?```$", "", revised.rstrip())

    # Validate that we got something sensible back — must have at least one phrase
    revised_tags = _parse_tags(revised)
    revised_count = sum(len(v) for v in revised_tags.values())
    if revised_count == 0:
        return {
            "error": "LLM returned no parseable phrases — original file unchanged.",
            "session_name": session_name,
            "original_count": original_count,
        }

    # Safety: verify all protected phrases survived
    revised_lower = revised.lower()
    missing_protected = [p for p in protected if p not in revised_lower]
    if missing_protected:
        # Re-insert them verbatim into their nearest existing tag
        first_tag = list(revised_tags.keys())[0] if revised_tags else "general"
        for phrase in missing_protected:
            revised_tags[first_tag].insert(0, phrase)
        revised = _serialise_tags(revised_tags)
        revised_count = sum(len(v) for v in revised_tags.values())

    path.write_text(revised, encoding="utf-8")

    return {
        "session_name": session_name,
        "path": str(path),
        "original_count": original_count,
        "revised_count": revised_count,
        "culled": max(0, original_count - revised_count),
        "protected_count": len(protected),
        "missing_protected_restored": len(missing_protected),
        "tags": list(revised_tags.keys()),
    }
