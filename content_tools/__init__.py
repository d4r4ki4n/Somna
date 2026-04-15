"""
content_tools — Somna Content Generation Tool Library

Provides the tool functions available to content_agent.py and to
somna_agent.py's auto-generation extension.

Quick import reference
----------------------
    from content_tools.affirmations import write_affirmations, read_affirmations
    from content_tools.sessions      import list_sessions, read_session, write_session_yaml
    from content_tools.images        import generate_image, list_images, generate_and_tag
    from content_tools.image_tags    import auto_tag_session, tag_stats, cull_session
    from content_tools.image_tags    import harvest_captions_to_affirmations

Tool function registry (used by content_agent.py for dispatch)
--------------------------------------------------------------
    TOOLS      — list of OpenAI-compatible tool schema dicts
    dispatch() — call a tool by name with a dict of arguments
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# ── Tool schemas (OpenAI function-calling format) ─────────────────────────────

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "write_affirmations",
            "description": (
                "Append or replace a tagged phrase section in a session's "
                "affirmations.txt file. Use this to add new subliminal phrases, "
                "induction language, or identity content to a session."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Folder name of the session (e.g. 'default', 'gateway_f10').",
                    },
                    "tag": {
                        "type": "string",
                        "description": (
                            "Tag name to write into (e.g. 'deep', 'relax', 'return'). "
                            "Must match the tag referenced by a keyframe's 'phrases' parameter."
                        ),
                    },
                    "phrases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of phrase strings. Use 'phrase | variant' pipe syntax "
                            "to provide alternate wordings for the same concept."
                        ),
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["append", "replace"],
                        "description": (
                            "append: add phrases to existing tag (default). "
                            "replace: overwrite the tag block entirely."
                        ),
                    },
                },
                "required": ["session_name", "tag", "phrases"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_session_content",
            "description": (
                "Read the session.yaml and affirmations.txt for a given session. "
                "Use this before writing to understand the existing content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Folder name of the session.",
                    },
                },
                "required": ["session_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_session_yaml",
            "description": (
                "Write or overwrite the session.yaml for a session folder. "
                "Creates the folder if needed. Validates YAML before writing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Folder name for the session.",
                    },
                    "yaml_content": {
                        "type": "string",
                        "description": (
                            "Complete valid session.yaml text. Must include at minimum: "
                            "name, duration (int seconds), and a timeline list."
                        ),
                    },
                },
                "required": ["session_name", "yaml_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "auto_tag_session",
            "description": (
                "Use the vision model (KoboldCpp mmproj) to automatically tag images "
                "in a session folder. Reads caption text overlays, assigns conditioning "
                "theme tags, and flags low-quality images for culling. "
                "Results saved incrementally to somna.db. "
                "Run in batches (default 20 at a time) to avoid overloading the server."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Session folder name.",
                    },
                    "batch_size": {
                        "type": "integer",
                        "description": "Number of images to process in this call (default 20). Use 0 for all.",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Re-tag already-tagged images. Default false (skip existing).",
                    },
                },
                "required": ["session_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tag_stats",
            "description": (
                "Show a summary of tag frequencies, image counts, and cull status "
                "for a session's image library. Useful to understand what content "
                "is available and which themes are under-represented."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Session folder name.",
                    },
                },
                "required": ["session_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cull_session",
            "description": (
                "List image filenames flagged as low-quality (blurry, watermarked, "
                "or near-duplicate) by the auto-tagger. Does NOT delete files — "
                "returns the list for review. Delete manually if desired."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Session folder name.",
                    },
                },
                "required": ["session_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "harvest_captions",
            "description": (
                "Extract caption text from tagged images and append them as new phrases "
                "to a session's affirmations.txt. Captions are human-curated conditioning "
                "phrases — this recycles them as subliminal affirmations. Deduplicates "
                "against existing phrases automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Session whose tags.json to harvest captions from.",
                    },
                    "target_session": {
                        "type": "string",
                        "description": "Session to write affirmations to. Defaults to session_name.",
                    },
                    "tag_filter": {
                        "type": "string",
                        "description": "Only harvest captions from images matching this tag (optional).",
                    },
                },
                "required": ["session_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_sessions",
            "description": "List all available session folder names.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_affirmations_batch",
            "description": (
                "Write a batch of subliminal phrases to a session's affirmations.txt "
                "under a specific tag. Use this when you want to front-load a phase "
                "with custom affirmations tailored to the user — e.g. inject 8–12 "
                "personalised phrases for the 'deep' tag based on what you've learned. "
                "Phrases are deduplicated automatically. Use mode='append' to add to "
                "existing content, mode='replace' to overwrite the whole tag block."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Session folder name.",
                    },
                    "tag": {
                        "type": "string",
                        "description": (
                            "Tag to write under (e.g. 'deep', 'focus10', 'return', "
                            "'general'). Must match a keyframe phrases parameter or "
                            "use 'general' for always-on phrases."
                        ),
                    },
                    "phrases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of phrase strings, each 2–12 words. Present tense, "
                            "first or second person, no negations, no punctuation. "
                            "Use 'phrase | variant' pipe syntax for alternates."
                        ),
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["append", "replace"],
                        "description": "append (default) or replace the tag block.",
                    },
                },
                "required": ["session_name", "tag", "phrases"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_pipeline_cycle",
            "description": (
                "Run one or more self-improving image generation cycles. "
                "Each cycle: picks a random untagged reference image, analyses and tags it, "
                "engineers a verbose conditioning prompt, generates a new image, reviews it "
                "strictly (scores must be >= 4/5), retries on failure, and promotes or "
                "discards the result. Use this for ALL image generation — it is the only "
                "image generation tool. Pass cycles > 1 to batch (e.g. cycles=10 to "
                "generate up to 10 images). Use forced_caption to embed a specific phrase "
                "in every generated image (e.g. user asks for 'GOOD GIRL' caption)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Session folder name (e.g. 'default').",
                    },
                    "theme": {
                        "type": "string",
                        "description": (
                            "Conditioning theme to generate toward — e.g. "
                            "'bimbo submission', 'blank obedience', 'somatic heaviness'. "
                            "Be specific; this drives the prompt engineering."
                        ),
                    },
                    "tag": {
                        "type": "string",
                        "description": (
                            "Tag to assign to promoted images. Should match an existing "
                            "tag from the session library or a new meaningful one."
                        ),
                    },
                    "intensity": {
                        "type": "string",
                        "enum": ["mild", "suggestive", "explicit", "graphic"],
                        "description": "Content intensity for the generated image.",
                    },
                    "cycles": {
                        "type": "integer",
                        "description": (
                            "Number of pipeline cycles to run in this call (default 1, max 10). "
                            "Use when the user requests multiple images — e.g. cycles=10."
                        ),
                    },
                    "forced_caption": {
                        "type": "string",
                        "description": (
                            "Optional: a specific caption phrase (3-8 words) to embed in "
                            "every generated image in this batch. ALL CAPS. "
                            "Use when the user requests a specific caption text "
                            "(e.g. 'GOOD GIRL', 'COCK GOES IN MIND GOES OUT'). "
                            "Leave empty to let the pipeline engineer captions automatically."
                        ),
                    },
                },
                "required": ["session_name", "theme", "tag"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_session_log",
            "description": (
                "Read structured summaries from past session exchange logs. "
                "Returns a list of past exchanges (prompt, response, beat_hz, "
                "complexity_score, spiral_style, timestamp) going back N days. "
                "Use this to understand long-term patterns — what the user has "
                "said in previous sessions, how deep they've gone, which phases "
                "they've experienced. Invaluable at session start."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Session folder name.",
                    },
                    "days": {
                        "type": "integer",
                        "description": (
                            "How many past days of logs to include (default 7, max 30). "
                            "Logs are returned newest-first, truncated to 50 exchanges "
                            "per day to avoid flooding context."
                        ),
                    },
                },
                "required": ["session_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_session_cycle",
            "description": (
                "Create a complete, self-reviewed hypnotic session from a plain-text intent. "
                "Runs a 4-step pipeline: (1) writes an internal creative brief, "
                "(2) designs a session.yaml, (3) writes affirmations per phase, "
                "(4) reviews the session on arc coherence, phrase quality, technical "
                "validity, and conditioning effectiveness — retries if any score < 4. "
                "Use this for ALL session creation — user-requested ('make me a session "
                "about X') or autonomous ('I'll generate a bimbo submission session for "
                "the library'). The session is committed to sessions/<name>/ on success."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": (
                            "Plain-text description of what the session should do or feel like. "
                            "Can be as brief as 'bimbo transformation' or as detailed as a paragraph. "
                            "The pipeline derives everything else from this."
                        ),
                    },
                    "session_name": {
                        "type": "string",
                        "description": (
                            "Optional: override the generated session folder name. "
                            "Leave empty to let the pipeline derive a name from the brief."
                        ),
                    },
                },
                "required": ["intent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "audit_affirmations",
            "description": (
                "Run a quality audit on a session's affirmations.txt. "
                "In a single LLM pass: culls weak/broken/redundant/off-theme phrases, "
                "chains sequential progressions with >> syntax, groups alt-phrasings "
                "as | variants, and reorganises phrases into the correct # [tag] sections. "
                "Phrases that appear in the user's effective_moments profile are protected "
                "and will never be removed. "
                "Use during idle planning when a session's phrase pool has grown large, "
                "disorganised, or after a round of bulk generation that may have introduced "
                "low-quality content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "Session folder name to audit (e.g. 'undone', 'hollow').",
                    },
                },
                "required": ["session_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_session_performance",
            "description": (
                "Query longitudinal session effectiveness data from the database. "
                "Returns recent session metrics, trend direction for a key metric, "
                "and the best-performing visual/audio config for a given session preset. "
                "Use during idle planning to understand whether sessions are improving, "
                "which configurations work best for this user, and what to prioritise next."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_preset": {
                        "type": "string",
                        "description": (
                            "Session folder name to analyse (e.g. 'hollow', 'default'). "
                            "Used for best_config lookup. Leave empty to skip best_config."
                        ),
                    },
                    "trend_metric": {
                        "type": "string",
                        "enum": [
                            "composite_score", "depth_min_sef95", "depth_mean_sef95",
                            "entrainment_mean_assr", "receptivity_approach_pct",
                            "signal_quality_mean", "transition_speed_sec",
                        ],
                        "description": (
                            "Which metric to compute a trend for over the last 20 sessions. "
                            "composite_score is usually the most informative starting point."
                        ),
                    },
                    "recent_n": {
                        "type": "integer",
                        "description": "How many recent session rows to return (default 10, max 20).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_images_by_theme",
            "description": (
                "Search the image database across ALL sessions for images matching "
                "a list of theme tags. Returns session + filename pairs. "
                "Use this to find aesthetically consistent images from other sessions "
                "that could be imported into a new session, or to understand what visual "
                "content already exists for a given theme before generating new images."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of tag strings to search for (e.g. ['ethereal', 'surrender', "
                            "'dark']). Matches against both controlled tags and open_tags. "
                            "Tag matching is case-insensitive substring."
                        ),
                    },
                },
                "required": ["tags"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_sleep_report",
            "description": (
                "Return an aggregated sleep session report: stage distribution, "
                "TMR replay counts, HTW windows used, under-reinforced phrases, "
                "and the recommended focus pool for the next HTW window. "
                "Call this during a sleep session (SLEEP_MAINTAIN phase) to plan "
                "the content for the next Hypnagogic Training Window. "
                "Also useful as a morning debrief after a sleep session ends."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": (
                            "The session folder name (e.g. 'default', 'gateway_f10'). "
                            "Use the current session_folder from live state."
                        ),
                    },
                },
                "required": ["session_id"],
            },
        },
    },
]


# ── Tool dispatch ─────────────────────────────────────────────────────────────

def dispatch(name: str, arguments: dict[str, Any]) -> Any:
    """Call a content tool by name with a dict of arguments.

    Returns the tool's return value (always a dict or list).
    Raises ValueError for unknown tool names.
    """
    if name == "write_affirmations":
        from content_tools.affirmations import write_affirmations
        return write_affirmations(
            session_name = arguments["session_name"],
            tag          = arguments["tag"],
            phrases      = arguments["phrases"],
            mode         = arguments.get("mode", "append"),
        )

    if name == "read_session_content":
        from content_tools.sessions import read_session
        return read_session(arguments["session_name"])

    if name == "write_session_yaml":
        from content_tools.sessions import write_session_yaml
        return write_session_yaml(
            session_name = arguments["session_name"],
            yaml_content = arguments["yaml_content"],
        )


    if name == "auto_tag_session":
        from content_tools.image_tags import auto_tag_session
        batch = arguments.get("batch_size", 20)
        batch = None if batch == 0 else int(batch)
        return auto_tag_session(
            session_name = arguments["session_name"],
            batch_size   = batch,
            force        = bool(arguments.get("force", False)),
        )

    if name == "tag_stats":
        from content_tools.image_tags import tag_stats
        return tag_stats(arguments["session_name"])

    if name == "cull_session":
        from content_tools.image_tags import cull_session
        return cull_session(arguments["session_name"])

    if name == "harvest_captions":
        from content_tools.image_tags import harvest_captions_to_affirmations
        return harvest_captions_to_affirmations(
            session_name   = arguments["session_name"],
            target_session = arguments.get("target_session"),
            tag_filter     = arguments.get("tag_filter"),
        )

    if name == "list_sessions":
        from content_tools.sessions import list_sessions
        return list_sessions()

    if name == "write_affirmations_batch":
        from content_tools.affirmations import write_affirmations
        return write_affirmations(
            session_name = arguments["session_name"],
            tag          = arguments["tag"],
            phrases      = arguments["phrases"],
            mode         = arguments.get("mode", "append"),
        )


    if name == "image_pipeline_cycle":
        from content_tools.image_gen_pipeline import run_pipeline_cycle
        cfg_path = Path(__file__).parent.parent / "agent_config.yaml"
        img_cfg: dict = {}
        try:
            import yaml
            with open(cfg_path, encoding="utf-8") as f:
                img_cfg = (yaml.safe_load(f) or {}).get("image_gen", {})
        except Exception:
            pass

        cycles         = max(1, min(10, int(arguments.get("cycles", 1))))
        forced_caption = arguments.get("forced_caption", "")
        intensity      = arguments.get("intensity",
                         img_cfg.get("default_intensity", "suggestive"))
        llm_url        = os.environ.get("SOMNA_LLM_URL", "http://localhost:8000")
        llm_model      = os.environ.get("SOMNA_LLM_MODEL", "")

        if cycles == 1:
            return run_pipeline_cycle(
                session_name   = arguments["session_name"],
                theme          = arguments["theme"],
                tag            = arguments["tag"],
                intensity      = intensity,
                forced_caption = forced_caption,
                llm_url        = llm_url,
                llm_model      = llm_model,
            )

        # Multi-cycle batch — run sequentially, collect compact summary
        results      = []
        promoted     = 0
        discarded    = 0
        errors       = 0
        for i in range(cycles):
            r = run_pipeline_cycle(
                session_name   = arguments["session_name"],
                theme          = arguments["theme"],
                tag            = arguments["tag"],
                intensity      = intensity,
                forced_caption = forced_caption,
                llm_url        = llm_url,
                llm_model      = llm_model,
            )
            action = r.get("action", "")
            if action == "promoted":
                promoted += 1
            elif action in ("discarded", "ref_culled"):
                discarded += 1
            elif r.get("status") not in ("ok",):
                errors += 1
            results.append({
                "cycle":   i + 1,
                "action":  action,
                "status":  r.get("status"),
                "ref":     r.get("reference_image"),
                "gen":     r.get("generated_image"),
                "caption": r.get("caption"),
                "scores":  r.get("review_scores"),
                "note":    r.get("notes", ""),
            })
        return {
            "cycles_run": cycles,
            "promoted":   promoted,
            "discarded":  discarded,
            "errors":     errors,
            "results":    results,
        }

    if name == "read_session_log":
        return _read_session_log(
            session_name = arguments["session_name"],
            days         = min(int(arguments.get("days", 7)), 30),
        )

    if name == "create_session_cycle":
        from content_tools.session_pipeline import run_session_creation_cycle
        return run_session_creation_cycle(
            intent       = arguments["intent"],
            session_name = arguments.get("session_name") or None,
            llm_url      = os.environ.get("SOMNA_LLM_URL", "http://localhost:8000"),
            llm_model    = os.environ.get("SOMNA_LLM_MODEL", ""),
        )

    if name == "audit_affirmations":
        from content_tools.affirmations import audit_affirmations
        return audit_affirmations(
            session_name = arguments["session_name"],
            llm_url      = os.environ.get("SOMNA_LLM_URL", "http://localhost:8000"),
            llm_model    = os.environ.get("SOMNA_LLM_MODEL", ""),
        )

    if name == "query_session_performance":
        from content_tools.somna_db import (
            get_session_metrics, trend_metric, best_config_for_preset,
        )
        n       = min(int(arguments.get("recent_n", 10)), 20)
        preset  = (arguments.get("session_preset") or "").strip()
        metric  = arguments.get("trend_metric", "composite_score")
        recent  = get_session_metrics(n)
        trend   = trend_metric(metric, n=20)
        best    = best_config_for_preset(preset) if preset else {}
        # Compact the recent rows so they don't flood context
        compact = [
            {k: v for k, v in row.items()
             if k in ("session_id", "session_date", "composite_score",
                      "depth_mean_sef95", "entrainment_mean_assr",
                      "signal_quality_mean", "agent_notes")}
            for row in recent
        ]
        return {
            "recent_sessions":  compact,
            "trend":            {metric: trend},
            "best_config":      best,
            "total_sessions":   len(recent),
        }

    if name == "find_images_by_theme":
        from content_tools.somna_db import get_images_by_tags
        tags    = [str(t) for t in (arguments.get("tags") or []) if t]
        results = get_images_by_tags(tags)
        by_session: dict = {}
        for r in results:
            by_session.setdefault(r["session"], []).append(r["filename"])
        return {
            "tags_searched": tags,
            "matches_total": len(results),
            "by_session":    by_session,
        }

    if name == "read_sleep_report":
        from content_tools.sleep_report import read_sleep_report
        return read_sleep_report(arguments["session_id"])

    raise ValueError(f"Unknown tool: {name!r}")


# ── Session log reader ────────────────────────────────────────────────────────

def _read_session_log(session_name: str, days: int = 7) -> dict:
    """Return structured summaries of past session exchanges.

    Reads .jsonl files from session_logs/ going back `days` days.
    Each file is named <session>_<YYYYMMDD>.jsonl.
    Returns a compact summary to avoid flooding the LLM context:
    per-day stats + up to 20 most interesting exchanges (deepest
    complexity scores + any with actual user responses).
    """
    import time as _time
    root     = Path(__file__).parent.parent
    logs_dir = root / "session_logs"
    if not logs_dir.exists():
        return {"error": "No session_logs directory found.", "days": []}

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_"
                        for c in session_name)

    cutoff_ts = _time.time() - days * 86400
    day_summaries = []

    # Collect matching log files sorted newest-first
    log_files = sorted(
        [p for p in logs_dir.glob(f"{safe_name}_*.jsonl")],
        reverse=True,
    )

    for log_path in log_files:
        # Parse date from filename suffix
        stem = log_path.stem  # e.g. "default_20260324"
        date_str = stem.rsplit("_", 1)[-1]
        try:
            day_ts = _time.mktime(_time.strptime(date_str, "%Y%m%d"))
        except ValueError:
            continue
        if day_ts < cutoff_ts:
            break   # files are sorted newest-first; older than window — stop

        exchanges = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                exchanges.append(json.loads(line))
            except Exception:
                pass

        if not exchanges:
            continue

        # Per-day stats
        complexities = [e.get("complexity_score", 1.0) for e in exchanges
                        if e.get("response") is not None]
        beats        = [e.get("beat_hz", 10.0) for e in exchanges]
        best_cmplx   = min(complexities) if complexities else None
        deepest_beat = min(beats) if beats else None

        # Curated sample: all exchanges with real responses + the deepest ones
        with_response = [e for e in exchanges if e.get("response")]
        deep_ones     = sorted(
            [e for e in exchanges if e.get("complexity_score", 1.0) < 0.3],
            key=lambda e: e.get("complexity_score", 1.0),
        )[:5]
        sample = {e.get("timestamp", 0): e
                  for e in (with_response[-15:] + deep_ones)}
        sample_list = sorted(sample.values(),
                             key=lambda e: e.get("session_time", 0))

        day_summaries.append({
            "date":          date_str,
            "exchange_count": len(exchanges),
            "best_complexity": round(best_cmplx, 2) if best_cmplx is not None else None,
            "deepest_beat_hz": round(deepest_beat, 1) if deepest_beat is not None else None,
            "exchanges": [
                {
                    "t":          f"{e.get('session_time', 0):.0f}s",
                    "beat":       e.get("beat_hz"),
                    "spiral":     e.get("spiral_style"),
                    "prompt":     e.get("prompt"),
                    "response":   e.get("response"),
                    "complexity": e.get("complexity_score"),
                }
                for e in sample_list
            ],
        })

        if len(day_summaries) >= days:
            break

    return {
        "session":       session_name,
        "days_requested": days,
        "days_found":    len(day_summaries),
        "history":       day_summaries,
    }
