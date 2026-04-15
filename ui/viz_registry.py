"""
Somna Visualization Registry — Toggle Architecture

Every viz widget registers here with an ID, display name, panel, and render
function.  Users toggle widgets via View menu or per-panel gear icons.
Layouts persist as named JSON presets under presets/viz/.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class WidgetConfig:
    widget_id:       str
    display_name:    str
    panel:           str
    default_visible: bool = True
    visible:         bool = True
    order:           int  = 0

    def to_dict(self) -> dict:
        return {"visible": self.visible, "order": self.order}


class VisualizationRegistry:
    def __init__(self, presets_dir: str = "presets/viz"):
        self._widgets:      dict[str, WidgetConfig]       = {}
        self._render_funcs: dict[str, Callable]           = {}
        self._panels:       dict[str, list[str]]          = {}
        self._presets_dir   = Path(presets_dir)
        self._presets_dir.mkdir(parents=True, exist_ok=True)

    def register(
        self,
        widget_id:       str,
        display_name:    str,
        panel:           str,
        render_func:     Callable,
        default_visible: bool = True,
        order:           int  = 0,
    ) -> None:
        cfg = WidgetConfig(
            widget_id       = widget_id,
            display_name    = display_name,
            panel           = panel,
            default_visible = default_visible,
            visible         = default_visible,
            order           = order,
        )
        self._widgets[widget_id]      = cfg
        self._render_funcs[widget_id] = render_func
        self._panels.setdefault(panel, [])
        if widget_id not in self._panels[panel]:
            self._panels[panel].append(widget_id)

    def is_visible(self, widget_id: str) -> bool:
        w = self._widgets.get(widget_id)
        return w.visible if w else False

    def toggle(self, widget_id: str) -> None:
        if widget_id in self._widgets:
            self._widgets[widget_id].visible = not self._widgets[widget_id].visible

    def set_visible(self, widget_id: str, visible: bool) -> None:
        if widget_id in self._widgets:
            self._widgets[widget_id].visible = visible

    def get_panel_widgets(self, panel: str) -> list[WidgetConfig]:
        return sorted(
            (self._widgets[wid] for wid in self._panels.get(panel, [])
             if wid in self._widgets),
            key=lambda w: w.order,
        )

    def render_panel(self, panel: str) -> None:
        """Render all visible widgets in a panel, sorted by order."""
        for widget in self.get_panel_widgets(panel):
            if widget.visible and widget.widget_id in self._render_funcs:
                self._render_funcs[widget.widget_id]()

    def render_toggle_menu(self) -> None:
        """Call inside a menu-bar frame to render a View → … submenu."""
        from imgui_bundle import imgui
        if imgui.begin_menu("View"):
            for panel_name in sorted(self._panels):
                if imgui.begin_menu(panel_name.title()):
                    for wid in self._panels[panel_name]:
                        w = self._widgets[wid]
                        clicked, new_val = imgui.menu_item(
                            w.display_name, "", w.visible
                        )
                        if clicked:
                            w.visible = new_val
                    imgui.end_menu()
            imgui.separator()
            if imgui.begin_menu("Presets"):
                for name in self.list_presets():
                    if imgui.menu_item_simple(name):
                        self.load_preset(name)
                imgui.separator()
                if imgui.menu_item_simple("Save Current"):
                    self.save_preset("last")
                imgui.end_menu()
            imgui.separator()
            if imgui.menu_item_simple("Reset to Defaults"):
                self.reset_defaults()
            imgui.end_menu()

    def render_panel_gear(self, panel: str) -> None:
        """Small ⚙ popup for toggling one panel's widgets inline."""
        from imgui_bundle import imgui
        popup_id = f"##viz_gear_{panel}"
        imgui.same_line()
        if imgui.small_button(f"\u2699##{panel}"):
            imgui.open_popup(popup_id)
        if imgui.begin_popup(popup_id):
            for wid in self._panels.get(panel, []):
                w = self._widgets[wid]
                changed, val = imgui.checkbox(w.display_name, w.visible)
                if changed:
                    w.visible = val
            imgui.end_popup()

    def reset_defaults(self) -> None:
        for w in self._widgets.values():
            w.visible = w.default_visible

    def save_preset(self, name: str) -> None:
        data = {wid: w.to_dict() for wid, w in self._widgets.items()}
        (self._presets_dir / f"{name}.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def load_preset(self, name: str) -> bool:
        path = self._presets_dir / f"{name}.json"
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        for wid, state in data.items():
            if wid in self._widgets:
                self._widgets[wid].visible = state.get("visible", True)
                self._widgets[wid].order   = state.get("order",
                    self._widgets[wid].order)
        return True

    def list_presets(self) -> list[str]:
        return sorted(p.stem for p in self._presets_dir.glob("*.json"))
