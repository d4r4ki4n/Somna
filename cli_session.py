"""
cli_session.py — Headphone-only session mode.

Runs binaural beats + TTS narration without the visual display or control panel.
Usage:
    python cli_session.py [session_name] [--list] [--volume N]

If no session name is given, lists available sessions.
"""

import sys
import time
import argparse
import threading
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from ipc.state_server import StateServer
from ipc import patch_live, read_live
from config import ConfigManager
from session.timeline_runner import make_runner


def list_sessions() -> list[str]:
    sessions_dir = ROOT / "sessions"
    if not sessions_dir.exists():
        return []
    return sorted(
        p.name
        for p in sessions_dir.iterdir()
        if p.is_dir() and (p / "session.yaml").exists()
    )


def print_session_info(name: str) -> None:
    yaml_path = ROOT / "sessions" / name / "session.yaml"
    if not yaml_path.exists():
        print(f"  {name} (no session.yaml)")
        return
    import yaml
    with open(yaml_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    title = cfg.get("title", name)
    duration = cfg.get("duration", "?")
    desc = cfg.get("description", "")
    print(f"  {name}")
    print(f"    {title} ({duration}s)")
    if desc:
        print(f"    {desc}")


def run_session(session_name: str, volume: float) -> None:
    import pygame
    from engines.audio_engine import BinauralAudioEngine
    from engines.tts_engine import TTSEngine

    live_path = ROOT / "live_control.json"

    # Clear stale state from previous runs directly in the file
    import json
    with open(live_path, "r") as f:
        state = json.load(f)
    state["agent_message"] = None
    state["session_time"] = 0
    state["timeline_label"] = ""
    state["_timeline_cmd"] = ""
    with open(live_path, "w") as f:
        json.dump(state, f, indent=2)

    server = StateServer(live_path)
    server.start()
    time.sleep(0.3)

    patch_live({
        "session_folder": session_name,
        "_timeline_cmd": "load",
        "session_time": 0,
        "audio_muted": False,
        "volume": volume,
        "agent_message": None,
    })

    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.mixer.init()
    pygame.mixer.set_num_channels(7)

    cfg = ConfigManager()
    audio = BinauralAudioEngine(cfg)
    tts = TTSEngine(cfg.config)

    runner = make_runner(ROOT, session_name)
    runner.start()
    runner.resume()

    print(f"\n[CLI] Session: {session_name}")
    print(f"[CLI] Binaural beats + TTS active. Headphones required.")
    print(f"[CLI] Press Ctrl+C to stop.\n")

    last_label = None
    last_narration_ts = 0

    try:
        while True:
            cfg.update()

            label = cfg.config.get("timeline_label", "")
            if label != last_label:
                last_label = label
                beat = cfg.config.get("beat_frequency", 0)
                carrier = cfg.config.get("carrier_frequency", 0)
                elapsed = cfg.config.get("session_time", 0)
                print(f"[{elapsed:6.1f}s] {label:12s} | Beat: {beat:.2f} Hz | Carrier: {carrier:.1f} Hz")

            live = read_live()
            msg = live.get("agent_message")
            if isinstance(msg, dict):
                msg_ts = msg.get("ts", 0)
                msg_text = msg.get("text", "")
                if msg_text and msg_ts != last_narration_ts:
                    last_narration_ts = msg_ts
                    print(f"  >> {msg_text}")

            result = tts.poll_ready(session_active=True)
            if result:
                phrase, dur_ms = result
                patch_live({
                    "tts_playing": phrase,
                    "tts_playing_ts": time.time(),
                    "tts_playing_ms": int(dur_ms),
                })

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n[CLI] Stopping...")
    finally:
        runner.stop()
        patch_live({"audio_muted": True, "session_time": 0})
        time.sleep(0.5)
        server.stop()
        print("[CLI] Session ended.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Somna CLI session player")
    parser.add_argument("session", nargs="?", help="Session name to run")
    parser.add_argument("--list", action="store_true", help="List available sessions")
    parser.add_argument("--volume", type=float, default=0.8, help="Volume 0.0-1.0 (default 0.8)")
    args = parser.parse_args()

    if args.list or not args.session:
        sessions = list_sessions()
        if not sessions:
            print("No sessions found.")
            return
        print("Available sessions:\n")
        for s in sessions:
            print_session_info(s)
        print(f"\nRun: python cli_session.py <session_name>")
        return

    session_path = ROOT / "sessions" / args.session
    if not session_path.exists() or not (session_path / "session.yaml").exists():
        print(f"Session '{args.session}' not found. Use --list to see available sessions.")
        return

    run_session(args.session, args.volume)


if __name__ == "__main__":
    main()