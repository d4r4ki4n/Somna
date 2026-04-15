"""Somna ImGui control panel entry point.

Run with:   python main_imgui.py
Or:         python -m control_panel_imgui    (not available, use this file)

The legacy Tkinter panel is still available via:  python main.py
"""
import sys
from pathlib import Path

# Ensure the project root is on sys.path regardless of how the script is invoked
sys.path.insert(0, str(Path(__file__).parent))

from control_panel_imgui import ControlPanelImGui

if __name__ == "__main__":
    ControlPanelImGui().run()
