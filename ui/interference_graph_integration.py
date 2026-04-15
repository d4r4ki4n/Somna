"""Somna Interference Graph — Control Panel Integration.

Wires the InterferenceGraph data model and InterferenceGraphPanel renderer
into the ControlPanelManager via the existing set_section_extra() hook.

Usage:
    from ui.interference_graph_integration import install_interference_graph

    # After creating the ControlPanelManager:
    _ig, _ig_panel = install_interference_graph(panel_manager)

That's it. The graph appears as the "SomaticPalette" section in the
Advanced layer of the control panel.
"""

from __future__ import annotations

from ui.interference_graph import InterferenceGraph, update_hardware_state
from ui.interference_graph_panel import InterferenceGraphPanel


# ── Widget definitions for panel_config.json ─────────────────────────────────
# Added at runtime so no JSON edits are required.


_LIVE_DEFAULTS = {
    "haptic_frequency_hz": 10.0,
    "vns_frequency_hz": 10.0,
    "somatic_palette_center_hz": 10.0,
    "somatic_palette_spread_hz": 0.0,
    "somatic_palette_active_preset": "Custom",
}


# ── Install function ──────────────────────────────────────────────────────────


def install_interference_graph(
    panel_manager,
) -> tuple[InterferenceGraph, InterferenceGraphPanel]:
    """Hook the Interference Graph into the control panel.

    Call this once after creating the ControlPanelManager, before the
    first render frame.  The graph section appears automatically in the
    Advanced layer under "SomaticPalette".

    Returns:
        (graph, ig_panel) — data model and renderer, for direct access
        if needed (e.g., scripting or testing).
    """
    from ipc import patch_live

    graph = InterferenceGraph()
    ig_panel = InterferenceGraphPanel(graph, patch_fn=patch_live)

    # ── Sync wrapper ─────────────────────────────────────────────────────
    # Reads live state before each render so node positions stay current,
    # and publishes telemetry keys so section indicators are populated.

    def _render(content_width: float) -> None:
        live = dict(getattr(panel_manager, "_live", {}))
        graph.update_from_live(live)

        update_hardware_state(live.get("hardware_channels_connected"))

        iaf_raw = live.get("eeg_iaf_hz")
        iaf_val = None
        if iaf_raw is not None:
            try:
                iaf_val = float(iaf_raw)
                if iaf_val <= 0:
                    iaf_val = None
            except (TypeError, ValueError):
                pass
        graph.set_iaf(iaf_val)

        telemetry = {
            "somatic_palette_center_hz": round(graph.center_frequency(), 2),
            "somatic_palette_spread_hz": round(graph.spread_hz, 2),
        }
        patch_live(telemetry)

        csum = live.get("conductor_summary") or {}
        phase = csum.get("conductor_phase") or live.get("conductor_phase", "")
        palette_active = bool(phase) and live.get("session_time", 0) > 0

        ig_panel.render(content_width, palette_active=palette_active)

    panel_manager.set_section_extra("SomaticPalette", _render)

    # ── Initialize new live_control keys ─────────────────────────────────
    # Use patch_live so the state server owns the write — never touch
    # live_control.json directly.
    try:
        patch_live(_LIVE_DEFAULTS)
    except Exception:
        pass  # State server may not be up at install time; first drag will write them.

    return graph, ig_panel
