"""Somna control panel entry point.

Run with:   python main_imgui.py
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path regardless of how the script is invoked
sys.path.insert(0, str(Path(__file__).parent))

from control_panel_imgui import ControlPanelImGui

if __name__ == "__main__":
    ControlPanelImGui().run()
