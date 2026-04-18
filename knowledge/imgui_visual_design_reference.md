# Somna ImGui Visual Design Reference

Implementation-Ready UI Specification — Rosé Pine Moon

**Status:** Specification (v2 — palette corrected)

**Author:** Ed / Reese

**Date:** 17 April 2026

**Stack:** Python / pyimgui / ModernGL / Dear ImGui

**Depends on:** Bible Ch.9 §Control-Panel (Control Panel Architecture)

**Implementation Note**

This document contains exact hex values, pixel dimensions, and layout coordinates. Every value is final. If a value is not specified here, consult Bible Ch.9 §Control-Panel or ask Ed. Do not guess.

**Palette Authority**

Rosé Pine Moon is the ONE AND ONLY color palette for Somna. No other palette exists. Any references to a navy/blue palette or pink/magenta palette in other documents are hallucinated and must be ignored. This file is the single source of truth for all UI colors.

---

# 1 Rosé Pine Moon — Color Token Reference

All Somna UI colors derive from these 15 semantic tokens. No color in any UI element should fall outside this set.

| Token | Hex | Role |
|-------|-----|------|
| Base | `#232136` | Deepest background. App bg, recessed frames. |
| Surface | `#2a273f` | Panel backgrounds, sidebars. |
| Overlay | `#393552` | Floating elements, headers, popovers. |
| Muted | `#6e6a86` | Disabled text, inactive elements. |
| Subtle | `#908caa` | Secondary text, labels, muted indicators. |
| Text | `#e0def4` | Primary text, values, headings. |
| Love | `#eb6f92` | Alerts, errors, destructive actions, active accents. |
| Gold | `#f6c177` | Warnings, user locks, amber callouts. |
| Rose | `#ea9a97` | Warm accents, hover states, transitional badges. |
| Pine | `#3e8fb0` | Checkmarks, agent source tags, cool accents. |
| Foam | `#9ccfd8` | Success, positive indicators, stable states. |
| Iris | `#c4a7e7` | Primary interactive accent. Sliders, buttons, progress. |
| Highlight Low | `#2a283e` | Subtle hover backgrounds. |
| Highlight Med | `#44415a` | Scrollbar grabs, separators, moderate highlights. |
| Highlight High | `#56526e` | Active/pressed states, strong highlights. |

---

# 2 Token-to-Widget Mapping

## 2.1 Core Surface Colors

| Token Name | Hex | Alpha | Usage |
|------------|-----|-------|-------|
| app_bg | `#232136` | 1.0 | Main application background behind the panel |
| panel_bg | `#2a273f` | 0.85 | Panel window background (semi-transparent, Ganzfeld shows through) |
| panel_bg_solid | `#2a273f` | 1.0 | Tooltips and popups where transparency is unwanted |
| section_header_bg | `#393552` | 1.0 | CollapsingHeader background |
| section_header_bg_hovered | `#44415a` | 1.0 | CollapsingHeader hovered |
| section_header_bg_active | `#56526e` | 1.0 | CollapsingHeader while held/active |
| widget_frame_bg | `#232136` | 1.0 | Slider track, checkbox frame, combo frame |
| widget_frame_bg_hovered | `#2a283e` | 1.0 | Frame when hovered |
| widget_frame_bg_active | `#393552` | 1.0 | Frame when interacting |
| separator | `#44415a` | 1.0 | Horizontal separators between widgets |
| scrollbar_bg | `#232136` | 1.0 | Scrollbar track |
| scrollbar_grab | `#44415a` | 1.0 | Scrollbar thumb |
| scrollbar_grab_hovered | `#56526e` | 1.0 | Scrollbar thumb hovered |
| scrollbar_grab_active | `#393552` | 1.0 | Scrollbar thumb dragging |
| tooltip_bg | `#232136` | 0.95 | Tooltip background |
| tooltip_border | `#44415a` | 1.0 | Tooltip border |

## 2.2 Text Colors

| Token Name | Hex | Alpha | Usage |
|------------|-----|-------|-------|
| text_primary | `#e0def4` | 1.0 | Primary labels, values, headings |
| text_muted | `#908caa` | 1.0 | Read-only AGENT_TUNABLE indicators at Advanced layer, secondary info |
| text_disabled | `#6e6a86` | 1.0 | Disabled controls (e.g., alpha/theta controls during GENUS) |
| text_label | `#908caa` | 1.0 | Widget labels (slightly dimmer than values) |
| text_value | `#e0def4` | 1.0 | Current numeric values on sliders, counters |
| text_section_summary | `#c4a7e7` | 0.7 | One-line summaries in collapsed Advanced section headers |

## 2.3 Interactive Element Colors

| Token Name | Hex | Alpha | Usage |
|------------|-----|-------|-------|
| slider_grab | `#c4a7e7` | 1.0 | Slider grab handle resting (Iris) |
| slider_grab_hovered | `#ea9a97` | 1.0 | Slider grab hovered (Rose — warm shift) |
| slider_grab_active | `#eb6f92` | 1.0 | Slider grab while dragging (Love — active) |
| checkbox_check | `#3e8fb0` | 1.0 | Checkbox checkmark color (Pine) |
| button_bg | `#393552` | 1.0 | Button background (Overlay) |
| button_bg_hovered | `#44415a` | 1.0 | Button hovered (Highlight Med) |
| button_bg_active | `#56526e` | 1.0 | Button active/pressed (Highlight High) |
| combo_button | `#393552` | 1.0 | Dropdown arrow button (Overlay) |
| progress_bar_fill | `#c4a7e7` | 1.0 | ProgressBar fill color (Iris) |

## 2.4 Status and Alert Colors

| Token Name | Hex | Alpha | Usage |
|------------|-----|-------|-------|
| alert_red | `#eb6f92` | 1.0 | Signal lost, motion contaminated, critical alerts (pulsing) (Love) |
| alert_red_bg | `#352035` | 1.0 | Alert badge background (Love-tinted Base) |
| warning_amber | `#f6c177` | 1.0 | Lock constraint warnings, amber callouts (Gold) |
| warning_amber_bg | `#352d22` | 1.0 | Warning callout background (Gold-tinted Base) |
| success_green | `#9ccfd8` | 1.0 | Gate pass, positive indicators (Foam) |
| debug_banner_bg | `#352035` | 0.9 | Debug mode warning banner background |
| debug_banner_text | `#eb6f92` | 1.0 | Debug mode warning text (Love) |

## 2.5 Source Tag Icon Colors

| Token Name | Hex | Alpha | Usage |
|------------|-----|-------|-------|
| source_agent | `#3e8fb0` | 1.0 | Robot icon (⚙) for agent-written values (Pine) |
| source_director | `#908caa` | 1.0 | Gear icon for director-written values (Subtle) |
| source_user_lock | `#f6c177` | 1.0 | Padlock icon (🔒) for user-locked parameters (Gold) |
| source_config | — | — | No icon displayed |

## 2.6 Gauge Gradient Colors

Arc gauge maps 0.0–1.0 to a three-stop color gradient. Interpolate linearly between stops.

| Token Name | Hex | Range | Meaning |
|------------|-----|-------|---------|
| gauge_low | `#eb6f92` | 0.0–0.3 | Love (poor / low) |
| gauge_mid | `#f6c177` | 0.3–0.6 | Gold (moderate) |
| gauge_high | `#9ccfd8` | 0.6–1.0 | Foam (good / high) |
| gauge_track | `#232136` | — | Unfilled portion of gauge arc (Base) |

## 2.7 Badge Colors by Domain

### 2.7.1 Conductor Phase (14 phases)

| Value | Hex | Token |
|-------|-----|-------|
| CALIBRATION | `#908caa` | Subtle |
| INDUCTION | `#3e8fb0` | Pine |
| DEEPENING | `#c4a7e7` | Iris |
| MAINTENANCE | `#9ccfd8` | Foam |
| FRAC_EMERGE | `#f6c177` | Gold |
| FRAC_EMERGE_HOLD | `#ea9a97` | Rose |
| FRAC_REDROP | `#c4a7e7` | Iris |
| GENUS_BLOCK | `#eb6f92` | Love |
| SLEEP_APPROACH | `#c4a7e7` | Iris |
| SLEEP_ONSET | `#3e8fb0` | Pine |
| SLEEP_MAINTAIN | `#3e8fb0` | Pine |
| SLEEP_TRAINING | `#f6c177` | Gold |
| SLEEP_WAKE | `#ea9a97` | Rose |
| SESSION_END | `#6e6a86` | Muted |

### 2.7.2 Session Phase (YAML arc phases)

| Value | Hex | Token |
|-------|-----|-------|
| ARRIVAL | `#908caa` | Subtle |
| INDUCTION | `#3e8fb0` | Pine |
| DEEPENING | `#c4a7e7` | Iris |
| WORK | `#9ccfd8` | Foam |
| CONSOLIDATION | `#f6c177` | Gold |
| EMERGENCE | `#ea9a97` | Rose |

### 2.7.3 Sleep Stage

| Value | Hex | Token | Text Color Override |
|-------|-----|-------|-------------------|
| WAKE | `#f6c177` | Gold | `#232136` (dark text) |
| N1 | `#9ccfd8` | Foam | `#232136` (dark text) |
| N2 | `#3e8fb0` | Pine | `#e0def4` |
| N3 | `#c4a7e7` | Iris | `#e0def4` |
| REM | `#eb6f92` | Love | `#e0def4` |

### 2.7.4 Sleep Phase

| Value | Hex | Token |
|-------|-----|-------|
| SLEEP_APPROACH | `#c4a7e7` | Iris |
| SLEEP_ONSET | `#3e8fb0` | Pine |
| SLEEP_MAINTAIN | `#3e8fb0` | Pine |
| SLEEP_TRAINING | `#f6c177` | Gold |
| SLEEP_WAKE | `#ea9a97` | Rose |

### 2.7.5 GENUS Phase

| Value | Hex | Token |
|-------|-----|-------|
| RAMP_UP | `#f6c177` | Gold |
| ACTIVE | `#9ccfd8` | Foam |
| WIND_DOWN | `#3e8fb0` | Pine |

### 2.7.6 Conditioning Paradigm

| Value | Hex | Token |
|-------|-----|-------|
| CLASSICAL | `#3e8fb0` | Pine |
| EVALUATIVE | `#9ccfd8` | Foam |
| OPERANT | `#f6c177` | Gold |
| STATE_DEPENDENT | `#c4a7e7` | Iris |
| OCCASION_SETTING | `#ea9a97` | Rose |
| INTEROCEPTIVE | `#3e8fb0` | Pine |

### 2.7.7 VR Schedule

| Value | Hex | Token |
|-------|-----|-------|
| CRF | `#9ccfd8` | Foam |
| VR-2 | `#3e8fb0` | Pine |
| VR-4 | `#f6c177` | Gold |
| VR-6 | `#eb6f92` | Love |

### 2.7.8 Stimulus Lifecycle

| Value | Hex | Token |
|-------|-----|-------|
| NOVEL | `#9ccfd8` | Foam |
| ACTIVE | `#3e8fb0` | Pine |
| COOLING | `#f6c177` | Gold |
| RETIRED | `#908caa` | Subtle |
| ARCHIVED | `#6e6a86` | Muted |

### 2.7.9 Session Intensity Cycle

| Value | Hex | Token |
|-------|-----|-------|
| BUILD_UP | `#f6c177` | Gold |
| PEAK | `#eb6f92` | Love |
| RELAX | `#9ccfd8` | Foam |

### 2.7.10 Content Semantic Density

| Value | Hex | Token |
|-------|-----|-------|
| PRIME | `#9ccfd8` | Foam |
| BRIDGE | `#3e8fb0` | Pine |
| DEEPEN | `#c4a7e7` | Iris |

### 2.7.11 Director Authority Level

| Value | Hex | Token |
|-------|-----|-------|
| MUST_DECIDE | `#eb6f92` | Love |
| SHOULD_DECIDE | `#f6c177` | Gold |
| MAY_DECIDE | `#3e8fb0` | Pine |
| SUGGEST_ONLY | `#908caa` | Subtle |

### 2.7.12 Dropdown-Only Values (No Badge Colors)

The following enumerations appear in dropdown selectors only, not as colored badges:

| Domain | Values |
|--------|--------|
| Session Arc | GENTLE_DESCENT, WAVE_PATTERN, DEEP_PLATEAU, CONDITIONING_FOCUS, SLEEP_BRIDGE |
| Induction Strategy | ENTRAINMENT_HEAVY, SOMATIC_ANCHOR, BREATH_LEAD, PROGRESSIVE_RELAXATION, COGNITIVE_OVERLOAD, FRACTIONATION, FIXATION_FADE, PACE_AND_LEAD |
| GENUS Arc | GENUS_STANDALONE, GENUS_TRANCE_HYBRID, GENUS_NEUROPROTECTION |

---

# 3 ImGui Style Configuration

Call this function once before the first frame. It sets all ImGui style variables and color tokens. Copy-paste directly into your codebase.

```python
def hex_to_rgba(hex_str: str, alpha: float = 1.0) -> tuple:
    """Convert '#RRGGBB' to (r, g, b, a) floats in 0.0-1.0 range."""
    h = hex_str.lstrip('#')
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    return (r, g, b, alpha)


def apply_somna_theme(style=None):
    """Apply the Somna Rosé Pine Moon theme to ImGui.

    Call ONCE before the first frame, after imgui.create_context().

    Args:
        style: imgui style object. If None, uses imgui.get_style().
    """
    import imgui

    if style is None:
        style = imgui.get_style()

    # ── Rounding ──────────────────────────────────────────────
    style.window_rounding = 4.0
    style.frame_rounding = 3.0
    style.scrollbar_rounding = 3.0
    style.grab_rounding = 2.0

    # ── Sizing / Spacing ──────────────────────────────────────
    style.window_padding = (12, 12)
    style.frame_padding = (8, 4)
    style.item_spacing = (8, 6)
    style.item_inner_spacing = (6, 4)
    style.scrollbar_size = 12.0
    style.grab_min_size = 10.0
    style.window_border_size = 1.0
    style.frame_border_size = 0.0

    # ── Rosé Pine Moon Color Map ──────────────────────────────
    c = hex_to_rgba
    colors = style.colors

    # -- Window / Background --
    colors[imgui.COLOR_WINDOW_BACKGROUND]         = c('#2a273f', 0.85)   # Surface (panel_bg)
    colors[imgui.COLOR_CHILD_BACKGROUND]           = c('#2a273f', 0.85)   # Surface
    colors[imgui.COLOR_POPUP_BACKGROUND]           = c('#2a273f', 1.0)    # Surface (solid)
    colors[imgui.COLOR_BORDER]                     = c('#44415a', 1.0)    # Highlight Med
    colors[imgui.COLOR_BORDER_SHADOW]              = c('#000000', 0.0)    # None

    # -- Text --
    colors[imgui.COLOR_TEXT]                        = c('#e0def4', 1.0)    # Text
    colors[imgui.COLOR_TEXT_DISABLED]               = c('#6e6a86', 1.0)    # Muted
    colors[imgui.COLOR_TEXT_SELECTED_BACKGROUND]    = c('#393552', 0.6)    # Overlay

    # -- Frame (sliders, checkboxes, combos) --
    colors[imgui.COLOR_FRAME_BACKGROUND]            = c('#232136', 1.0)    # Base
    colors[imgui.COLOR_FRAME_BACKGROUND_HOVERED]    = c('#2a283e', 1.0)    # Highlight Low
    colors[imgui.COLOR_FRAME_BACKGROUND_ACTIVE]     = c('#393552', 1.0)    # Overlay

    # -- Title bar --
    colors[imgui.COLOR_TITLE_BACKGROUND]            = c('#393552', 1.0)    # Overlay
    colors[imgui.COLOR_TITLE_BACKGROUND_ACTIVE]     = c('#44415a', 1.0)    # Highlight Med
    colors[imgui.COLOR_TITLE_BACKGROUND_COLLAPSED]  = c('#232136', 0.75)   # Base

    # -- Menu bar --
    colors[imgui.COLOR_MENUBAR_BACKGROUND]          = c('#232136', 1.0)    # Base

    # -- Scrollbar --
    colors[imgui.COLOR_SCROLLBAR_BACKGROUND]        = c('#232136', 1.0)    # Base
    colors[imgui.COLOR_SCROLLBAR_GRAB]              = c('#44415a', 1.0)    # Highlight Med
    colors[imgui.COLOR_SCROLLBAR_GRAB_HOVERED]      = c('#56526e', 1.0)    # Highlight High
    colors[imgui.COLOR_SCROLLBAR_GRAB_ACTIVE]       = c('#393552', 1.0)    # Overlay

    # -- Buttons --
    colors[imgui.COLOR_BUTTON]                      = c('#393552', 1.0)    # Overlay
    colors[imgui.COLOR_BUTTON_HOVERED]              = c('#44415a', 1.0)    # Highlight Med
    colors[imgui.COLOR_BUTTON_ACTIVE]               = c('#56526e', 1.0)    # Highlight High

    # -- Headers (CollapsingHeader) --
    colors[imgui.COLOR_HEADER]                      = c('#393552', 1.0)    # Overlay
    colors[imgui.COLOR_HEADER_HOVERED]              = c('#44415a', 1.0)    # Highlight Med
    colors[imgui.COLOR_HEADER_ACTIVE]               = c('#56526e', 1.0)    # Highlight High

    # -- Separator --
    colors[imgui.COLOR_SEPARATOR]                   = c('#44415a', 1.0)    # Highlight Med
    colors[imgui.COLOR_SEPARATOR_HOVERED]           = c('#56526e', 1.0)    # Highlight High
    colors[imgui.COLOR_SEPARATOR_ACTIVE]            = c('#c4a7e7', 1.0)    # Iris

    # -- Slider grab --
    colors[imgui.COLOR_SLIDER_GRAB]                 = c('#c4a7e7', 1.0)    # Iris
    colors[imgui.COLOR_SLIDER_GRAB_ACTIVE]          = c('#eb6f92', 1.0)    # Love

    # -- Check mark --
    colors[imgui.COLOR_CHECK_MARK]                  = c('#3e8fb0', 1.0)    # Pine

    # -- Resize grip --
    colors[imgui.COLOR_RESIZE_GRIP]                 = c('#44415a', 0.5)    # Highlight Med
    colors[imgui.COLOR_RESIZE_GRIP_HOVERED]         = c('#56526e', 0.7)    # Highlight High
    colors[imgui.COLOR_RESIZE_GRIP_ACTIVE]          = c('#c4a7e7', 1.0)    # Iris

    # -- Tab --
    colors[imgui.COLOR_TAB]                         = c('#232136', 1.0)    # Base
    colors[imgui.COLOR_TAB_HOVERED]                 = c('#44415a', 1.0)    # Highlight Med
    colors[imgui.COLOR_TAB_ACTIVE]                  = c('#393552', 1.0)    # Overlay
    colors[imgui.COLOR_TAB_UNFOCUSED]               = c('#232136', 1.0)    # Base
    colors[imgui.COLOR_TAB_UNFOCUSED_ACTIVE]        = c('#2a273f', 1.0)    # Surface

    # -- Plot (sparklines use custom draw, but set for completeness) --
    colors[imgui.COLOR_PLOT_LINES]                  = c('#c4a7e7', 1.0)    # Iris
    colors[imgui.COLOR_PLOT_LINES_HOVERED]          = c('#eb6f92', 1.0)    # Love
    colors[imgui.COLOR_PLOT_HISTOGRAM]              = c('#9ccfd8', 1.0)    # Foam
    colors[imgui.COLOR_PLOT_HISTOGRAM_HOVERED]      = c('#ea9a97', 1.0)    # Rose

    # -- Drag/drop --
    colors[imgui.COLOR_DRAG_DROP_TARGET]            = c('#f6c177', 0.9)    # Gold

    # -- Nav --
    colors[imgui.COLOR_NAV_HIGHLIGHT]               = c('#c4a7e7', 1.0)    # Iris
    colors[imgui.COLOR_NAV_WINDOWING_HIGHLIGHT]     = c('#e0def4', 0.7)    # Text
    colors[imgui.COLOR_NAV_WINDOWING_DIM_BACKGROUND]= c('#232136', 0.2)    # Base


# ── Badge Color Lookup ────────────────────────────────────────
# Use these dicts for runtime badge rendering.

CONDUCTOR_PHASE_COLORS = {
    'CALIBRATION':      '#908caa',  # Subtle
    'INDUCTION':        '#3e8fb0',  # Pine
    'DEEPENING':        '#c4a7e7',  # Iris
    'MAINTENANCE':      '#9ccfd8',  # Foam
    'FRAC_EMERGE':      '#f6c177',  # Gold
    'FRAC_EMERGE_HOLD': '#ea9a97',  # Rose
    'FRAC_REDROP':      '#c4a7e7',  # Iris
    'GENUS_BLOCK':      '#eb6f92',  # Love
    'SLEEP_APPROACH':   '#c4a7e7',  # Iris
    'SLEEP_ONSET':      '#3e8fb0',  # Pine
    'SLEEP_MAINTAIN':   '#3e8fb0',  # Pine
    'SLEEP_TRAINING':   '#f6c177',  # Gold
    'SLEEP_WAKE':       '#ea9a97',  # Rose
    'SESSION_END':      '#6e6a86',  # Muted
}

SLEEP_STAGE_COLORS = {
    'WAKE': ('#f6c177', '#232136'),  # Gold bg, Base text
    'N1':   ('#9ccfd8', '#232136'),  # Foam bg, Base text
    'N2':   ('#3e8fb0', '#e0def4'),  # Pine bg, Text text
    'N3':   ('#c4a7e7', '#e0def4'),  # Iris bg, Text text
    'REM':  ('#eb6f92', '#e0def4'),  # Love bg, Text text
}

ALERT_COLORS = {
    'error':   '#eb6f92',  # Love
    'warning': '#f6c177',  # Gold
    'success': '#9ccfd8',  # Foam
    'info':    '#3e8fb0',  # Pine
}

GAUGE_GRADIENT = [
    (0.0, '#eb6f92'),   # Love  — poor
    (0.3, '#f6c177'),   # Gold  — moderate
    (0.6, '#9ccfd8'),   # Foam  — good
]
```

---

# 4 Layout Specification

## 4.1 Window Dimensions

| Element | Value | Notes |
|---------|-------|-------|
| Panel min width | 480 px | Below this, labels truncate |
| Panel max width | 600 px | Above this, sliders stretch uselessly |
| Panel height | Fill screen | Scrollable content area |
| Section header height | 28 px | CollapsingHeader + summary text |
| Widget row height | 24 px | Standard slider/toggle/indicator row |
| Spacing between sections | 12 px | Via `item_spacing` |
| Indent for sub-widgets | 16 px | `imgui.indent()` |

## 4.2 Disclosure Layers

Three visibility layers, toggled via a button or keyboard shortcut:

| Layer | Visibility | Target User |
|-------|-----------|-------------|
| Essential | Default. ~15 widgets. | New user, casual sessions. |
| Advanced | All USER_CONTROL + AGENT_TUNABLE (read-only). ~50 widgets. | Power user, session tuning. |
| Debug | Everything including INTERNAL. All writable. ~100+ widgets. | Development, diagnostics. |

When in Debug mode, render a persistent banner at the top of the panel:

```
⚠ DEBUG MODE — Agent parameters are writable. Changes may conflict with session orchestration.
```

Banner uses `debug_banner_bg` (`#352035`, 0.9) and `debug_banner_text` (`#eb6f92`).

---

— End of imgui_visual_design_reference.md —
