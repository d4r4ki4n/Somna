"""
visual_display_runner.py
Entry point launched as a subprocess by the control panel.
Starts the timeline runner thread, then hands off to the pygame loop.
"""

from pathlib import Path
from visual_display import VisualDisplay
from session.timeline_runner import make_runner
import json
from ipc import patch_live, read_live

if __name__ == "__main__":
    root = Path(__file__).parent

    try:
        live = read_live()
        session_name = live.get("session_folder") or ""
    except Exception:
        session_name = ""
    if not session_name or not (root / "sessions" / session_name).exists():
        # Genuine fallback: find any valid session to avoid a crash, but log it.
        candidates = [p.name for p in (root / "sessions").iterdir() if p.is_dir()]
        session_name = candidates[0] if candidates else "default"
        print(
            f"[Launcher] session_folder missing/invalid — falling back to '{session_name}'"
        )

    runner = make_runner(root, session_name)
    runner.start()
    runner.resume()

    try:
        VisualDisplay().run()
    finally:
        runner.stop()
        # Zero out session_time so the agent detects closure on the very next
        # tick instead of waiting 30 s for the stale-detection timeout.
        try:
            patch_live({"session_time": 0})
        except Exception:
            pass
