"""
content_tools/sessions.py — Session YAML read/write utilities.

Handles session.yaml files and session folder management.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_ROOT     = Path(__file__).parent.parent
_SESSIONS = _ROOT / "sessions"


# ── Path helpers ──────────────────────────────────────────────────────────────

def _session_dir(session_name: str) -> Path:
    return _SESSIONS / session_name


def _yaml_path(session_name: str) -> Path:
    return _session_dir(session_name) / "session.yaml"


# ── Public API ────────────────────────────────────────────────────────────────

def list_sessions() -> list[str]:
    """Return folder names of all sessions that contain a session.yaml."""
    if not _SESSIONS.exists():
        return []
    return sorted(
        d.name for d in _SESSIONS.iterdir()
        if d.is_dir() and (d / "session.yaml").exists()
    )


def read_session(session_name: str) -> dict:
    """Return {'yaml': str, 'affirmations': str} for a session.

    Returns empty strings for missing files.
    """
    from content_tools.affirmations import read_affirmations

    yaml_path = _yaml_path(session_name)
    yaml_text = yaml_path.read_text(encoding="utf-8") if yaml_path.exists() else ""
    aff_text  = read_affirmations(session_name)

    return {
        "session_name":  session_name,
        "yaml":          yaml_text,
        "affirmations":  aff_text,
    }


def write_session_yaml(session_name: str, yaml_content: str) -> dict:
    """Write or overwrite session.yaml for a session folder.

    Validates that yaml_content parses before writing.
    Creates the session folder if it doesn't exist.

    Returns
    -------
    dict with keys: session_name, path, valid, error (if any)
    """
    try:
        import yaml as _yaml  # type: ignore
        parsed = _yaml.safe_load(yaml_content)
        if not isinstance(parsed, dict):
            return {
                "session_name": session_name,
                "valid": False,
                "error": "YAML does not parse to a dict at the top level.",
            }
    except Exception as exc:
        return {
            "session_name": session_name,
            "valid": False,
            "error": f"YAML parse error: {exc}",
        }

    dest = _yaml_path(session_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml_content, encoding="utf-8")

    return {
        "session_name": session_name,
        "path":         str(dest),
        "valid":        True,
        "duration_s":   parsed.get("duration"),
        "keyframes":    len(parsed.get("timeline", [])),
    }


def get_session_metadata(session_name: str) -> dict[str, Any]:
    """Parse and return key metadata from a session.yaml without reading it all.

    Returns name, duration, keyframe count, phase labels, and defaults.
    Side-effect: registers the session in somna.db via upsert_session() so any
    folder dropped into sessions/ is automatically indexed.
    """
    yaml_path = _yaml_path(session_name)
    if not yaml_path.exists():
        return {"error": f"No session.yaml found for {session_name!r}"}

    try:
        import yaml as _yaml
        parsed = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"Parse error: {exc}"}

    timeline = parsed.get("timeline", [])
    labels   = [kf.get("label", "") for kf in timeline if kf.get("label")]
    defaults = parsed.get("defaults", {})

    # Read metadata-only keys from defaults block (never go into live_control.json)
    description = (
        parsed.get("description")
        or defaults.get("description", "")
    )
    category    = defaults.get("category", "general")
    image_tags  = defaults.get("image_tags", [])
    duration_s  = parsed.get("duration") or 0

    # Register / refresh in the DB — idempotent, fast
    try:
        from content_tools.somna_db import upsert_session
        upsert_session(
            name=session_name,
            description=description,
            image_tags=image_tags if isinstance(image_tags, list) else [],
            duration_s=float(duration_s),
            category=category,
        )
    except Exception:
        pass  # DB unavailable — metadata still returned normally

    return {
        "session_name": session_name,
        "name":         parsed.get("name", session_name),
        "description":  description,
        "category":     category,
        "duration_s":   duration_s,
        "keyframes":    len(timeline),
        "labels":       labels,
        "defaults":     defaults,
        "has_timeline": len(timeline) > 0,
    }


def list_sessions_with_meta() -> list[dict]:
    """Return a list of session dicts enriched with DB metadata.

    Each dict: name, description, category, has_timeline, duration_s,
                is_favorite, last_played, play_count.
    Sessions in the folder but missing from the DB return sensible defaults.
    """
    from content_tools.somna_db import get_all_session_meta

    names   = list_sessions()
    db_meta = get_all_session_meta()
    result  = []

    for name in names:
        db  = db_meta.get(name, {})
        # Trigger YAML parse + DB upsert if this session isn't registered yet
        if name not in db_meta:
            meta = get_session_metadata(name)
            db   = db_meta.get(name, {})  # re-fetch after upsert side-effect
            has_timeline = meta.get("has_timeline", False)
            duration_s   = meta.get("duration_s") or 0
            description  = meta.get("description", "")
            category     = meta.get("category", "general")
        else:
            # Lightweight: derive has_timeline from duration_s heuristic or
            # re-parse only if duration unknown
            has_timeline = None   # populated lazily below
            duration_s   = db.get("duration_s", 0)
            description  = db.get("description", "")
            category     = db.get("category", "general")

        if has_timeline is None:
            try:
                import yaml as _yaml
                p = _yaml.safe_load(
                    (_SESSIONS / name / "session.yaml").read_text(encoding="utf-8")
                )
                has_timeline = len(p.get("timeline", [])) > 0
            except Exception:
                has_timeline = False

        result.append({
            "name":         name,
            "description":  description,
            "category":     category,
            "has_timeline": has_timeline,
            "duration_s":   duration_s,
            "is_favorite":  db.get("is_favorite", False),
            "last_played":  db.get("last_played"),
            "play_count":   db.get("play_count", 0),
        })

    return result
