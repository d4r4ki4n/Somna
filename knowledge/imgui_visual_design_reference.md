# Somna ImGui Visual Design Reference

Implementation-Ready UI Specification

**Status:** Specification

**Author:** Ed

**Date:** 6 April 2026

**Stack:** Python / pyimgui / ModernGL / Dear ImGui

**Depends on:** Bible Ch.9 Â§Control-Panel (Control Panel Architecture)

**Implementation Note**

This document contains exact hex values, pixel dimensions, and layout coordinates. Every value is final. If a value is not specified here, consult Bible Ch.9 Â§Control-Panel or ask Ed. Do not guess.

# 1 Dark Theme Color Palette

All colors are specified as hex. Alpha is a float from 0.0 to 1.0. Use imgui.push_style_color() with RGBA tuples derived from these values.

## 1.1 Core Surface Colors


| **Token Name**            | **Hex Value** | **Alpha** | **Usage**                                                          |
| ------------------------- | ------------- | --------- | ------------------------------------------------------------------ |
| app_bg                    | #1a1a2e       | 1.0       | Main application background behind the panel                       |
| ---                       | ---           | ---       | ---                                                                |
| panel_bg                  | #16213e       | 0.85      | Panel window background (semi-transparent, Ganzfeld shows through) |
| ---                       | ---           | ---       | ---                                                                |
| panel_bg_solid            | #16213e       | 1.0       | Tooltips and popups where transparency is unwanted                 |
| ---                       | ---           | ---       | ---                                                                |
| section_header_bg         | #0f3460       | 1.0       | CollapsingHeader background                                        |
| ---                       | ---           | ---       | ---                                                                |
| section_header_bg_hovered | #144080       | 1.0       | CollapsingHeader hovered                                           |
| ---                       | ---           | ---       | ---                                                                |
| section_header_bg_active  | #1a4fa0       | 1.0       | CollapsingHeader while held/active                                 |
| ---                       | ---           | ---       | ---                                                                |
| widget_frame_bg           | #0d1b2a       | 1.0       | Slider track, checkbox frame, combo frame                          |
| ---                       | ---           | ---       | ---                                                                |
| widget_frame_bg_hovered   | #1b2d45       | 1.0       | Frame when hovered                                                 |
| ---                       | ---           | ---       | ---                                                                |
| widget_frame_bg_active    | #0f3460       | 1.0       | Frame when interacting                                             |
| ---                       | ---           | ---       | ---                                                                |
| separator                 | #2a3a5c       | 1.0       | Horizontal separators between widgets                              |
| ---                       | ---           | ---       | ---                                                                |
| scrollbar_bg              | #0d1b2a       | 1.0       | Scrollbar track                                                    |
| ---                       | ---           | ---       | ---                                                                |
| scrollbar_grab            | #2a3a5c       | 1.0       | Scrollbar thumb                                                    |
| ---                       | ---           | ---       | ---                                                                |
| scrollbar_grab_hovered    | #3a4a6c       | 1.0       | Scrollbar thumb hovered                                            |
| ---                       | ---           | ---       | ---                                                                |
| scrollbar_grab_active     | #0f3460       | 1.0       | Scrollbar thumb dragging                                           |
| ---                       | ---           | ---       | ---                                                                |
| tooltip_bg                | #0d1b2a       | 0.95      | Tooltip background                                                 |
| ---                       | ---           | ---       | ---                                                                |
| tooltip_border            | #2a3a5c       | 1.0       | Tooltip border                                                     |
| ---                       | ---           | ---       | ---                                                                |


## 1.2 Text Colors


| **Token Name**       | **Hex Value** | **Alpha** | **Usage**                                                            |
| -------------------- | ------------- | --------- | -------------------------------------------------------------------- |
| text_primary         | #e0e0e0       | 1.0       | Primary labels, values, headings                                     |
| ---                  | ---           | ---       | ---                                                                  |
| text_muted           | #aaaaaa       | 1.0       | Read-only AGENT_TUNABLE indicators at Advanced layer, secondary info |
| ---                  | ---           | ---       | ---                                                                  |
| text_disabled        | #666666       | 1.0       | Disabled controls (e.g., alpha/theta controls during GENUS)          |
| ---                  | ---           | ---       | ---                                                                  |
| text_label           | #c0c0c0       | 1.0       | Widget labels (slightly dimmer than values)                          |
| ---                  | ---           | ---       | ---                                                                  |
| text_value           | #e0e0e0       | 1.0       | Current numeric values on sliders, counters                          |
| ---                  | ---           | ---       | ---                                                                  |
| text_section_summary | #8899bb       | 1.0       | One-line summaries in collapsed Advanced section headers             |
| ---                  | ---           | ---       | ---                                                                  |


## 1.3 Interactive Element Colors


| **Token Name**      | **Hex Value** | **Alpha** | **Usage**                  |
| ------------------- | ------------- | --------- | -------------------------- |
| slider_grab         | #0f3460       | 1.0       | Slider grab handle resting |
| ---                 | ---           | ---       | ---                        |
| slider_grab_hovered | #1a5a90       | 1.0       | Slider grab hovered        |
| ---                 | ---           | ---       | ---                        |
| slider_grab_active  | #2070b0       | 1.0       | Slider grab while dragging |
| ---                 | ---           | ---       | ---                        |
| checkbox_check      | #4a9eff       | 1.0       | Checkbox checkmark color   |
| ---                 | ---           | ---       | ---                        |
| button_bg           | #0f3460       | 1.0       | Button background          |
| ---                 | ---           | ---       | ---                        |
| button_bg_hovered   | #144080       | 1.0       | Button hovered             |
| ---                 | ---           | ---       | ---                        |
| button_bg_active    | #1a4fa0       | 1.0       | Button active/pressed      |
| ---                 | ---           | ---       | ---                        |
| combo_button        | #0f3460       | 1.0       | Dropdown arrow button      |
| ---                 | ---           | ---       | ---                        |
| progress_bar_fill   | #0f3460       | 1.0       | ProgressBar fill color     |
| ---                 | ---           | ---       | ---                        |


## 1.4 Status and Alert Colors


| **Token Name**    | **Hex Value** | **Alpha** | **Usage**                                                   |
| ----------------- | ------------- | --------- | ----------------------------------------------------------- |
| alert_red         | #e94560       | 1.0       | Signal lost, motion contaminated, critical alerts (pulsing) |
| ---               | ---           | ---       | ---                                                         |
| alert_red_bg      | #3d1a25       | 1.0       | Alert badge background                                      |
| ---               | ---           | ---       | ---                                                         |
| warning_amber     | #ffaa33       | 1.0       | Lock constraint warnings, amber callouts                    |
| ---               | ---           | ---       | ---                                                         |
| warning_amber_bg  | #3d2d1a       | 1.0       | Warning callout background                                  |
| ---               | ---           | ---       | ---                                                         |
| success_green     | #44cc66       | 1.0       | Gate pass, positive indicators                              |
| ---               | ---           | ---       | ---                                                         |
| debug_banner_bg   | #3d1a25       | 0.9       | Debug mode warning banner background                        |
| ---               | ---           | ---       | ---                                                         |
| debug_banner_text | #e94560       | 1.0       | Debug mode warning text                                     |
| ---               | ---           | ---       | ---                                                         |


## 1.5 Source Tag Icon Colors


| **Token Name**   | **Hex Value** | **Alpha** | **Usage**                                    |
| ---------------- | ------------- | --------- | -------------------------------------------- |
| source_agent     | #6688cc       | 1.0       | Robot icon (⚙) for agent-written values      |
| ---              | ---           | ---       | ---                                          |
| source_director  | #888888       | 1.0       | Gear icon for director-written values        |
| ---              | ---           | ---       | ---                                          |
| source_user_lock | #ffcc44       | 1.0       | Padlock icon (🔒) for user-locked parameters |
| ---              | ---           | ---       | ---                                          |
| source_config    | —             | —         | No icon displayed                            |
| ---              | ---           | ---       | ---                                          |


## 1.6 Gauge Gradient Colors

Arc gauge maps 0.0–1.0 to a three-stop color gradient. Interpolate linearly between stops.


| **Token Name** | **Hex Value** | **Range** | **Meaning**                   |
| -------------- | ------------- | --------- | ----------------------------- |
| gauge_low      | #e94560       | 0.0–0.3   | Red (poor / low)              |
| ---            | ---           | ---       | ---                           |
| gauge_mid      | #ffaa33       | 0.3–0.6   | Amber / yellow (moderate)     |
| ---            | ---           | ---       | ---                           |
| gauge_high     | #44cc66       | 0.6–1.0   | Green (good / high)           |
| ---            | ---           | ---       | ---                           |
| gauge_track    | #0d1b2a       | —         | Unfilled portion of gauge arc |
| ---            | ---           | ---       | ---                           |


## 1.7 Badge Colors by Domain

### 1.7.1 Conductor Phase


| **Value**      | **Hex** | **Color Name** |
| -------------- | ------- | -------------- |
| IDLE           | #888888 | Gray           |
| ---            | ---     | ---            |
| ACTIVE         | #4a9eff | Blue           |
| ---            | ---     | ---            |
| DEEPENING      | #0f3460 | Deep blue      |
| ---            | ---     | ---            |
| SLEEP_APPROACH | #6644aa | Purple         |
| ---            | ---     | ---            |
| SLEEP_ONSET    | #553399 | Dark purple    |
| ---            | ---     | ---            |
| SLEEP_MAINTAIN | #442288 | Deeper purple  |
| ---            | ---     | ---            |
| SLEEP_TRAINING | #9966cc | Light purple   |
| ---            | ---     | ---            |
| SLEEP_WAKE     | #ffcc44 | Amber          |
| ---            | ---     | ---            |


### 1.7.2 Session Phase


| **Value**     | **Hex** | **Color Name** |
| ------------- | ------- | -------------- |
| ARRIVAL       | #888888 | Gray           |
| ---           | ---     | ---            |
| INDUCTION     | #4a9eff | Blue           |
| ---           | ---     | ---            |
| DEEPENING     | #0f3460 | Deep blue      |
| ---           | ---     | ---            |
| WORK          | #44cc66 | Green          |
| ---           | ---     | ---            |
| CONSOLIDATION | #ffaa33 | Amber          |
| ---           | ---     | ---            |
| EMERGENCE     | #cc8844 | Warm           |
| ---           | ---     | ---            |


### 1.7.3 Sleep Stage


| **Value** | **Hex** | **RGB Tuple**   | **Color Name** | **Text Color Override** |
| --------- | ------- | --------------- | -------------- | ----------------------- |
| WAKE      | #ffd23f | (255, 210, 63)  | Yellow         | #1a1a2e (dark text)     |
| ---       | ---     | ---             | ---            | ---                     |
| N1        | #87cefa | (135, 206, 250) | Light blue     | #1a1a2e (dark text)     |
| ---       | ---     | ---             | ---            | ---                     |
| N2        | #4682c8 | (70, 130, 200)  | Blue           | #e0e0e0                 |
| ---       | ---     | ---             | ---            | ---                     |
| N3        | #19328c | (25, 50, 140)   | Deep blue      | #e0e0e0                 |
| ---       | ---     | ---             | ---            | ---                     |
| REM       | #9467bd | (148, 103, 189) | Purple         | #e0e0e0                 |
| ---       | ---     | ---             | ---            | ---                     |


### 1.7.4 Sleep Phase


| **Value**      | **Hex** | **Color Name** |
| -------------- | ------- | -------------- |
| SLEEP_APPROACH | #6644aa | Purple         |
| ---            | ---     | ---            |
| SLEEP_ONSET    | #553399 | Dark purple    |
| ---            | ---     | ---            |
| SLEEP_MAINTAIN | #442288 | Deeper purple  |
| ---            | ---     | ---            |
| SLEEP_TRAINING | #9966cc | Light purple   |
| ---            | ---     | ---            |
| SLEEP_WAKE     | #ffcc44 | Amber          |
| ---            | ---     | ---            |


### 1.7.5 GENUS Phase


| **Value** | **Hex** | **Color Name** |
| --------- | ------- | -------------- |
| RAMP_UP   | #ffaa33 | Amber          |
| ---       | ---     | ---            |
| ACTIVE    | #44cc66 | Green          |
| ---       | ---     | ---            |
| WIND_DOWN | #4a9eff | Blue           |
| ---       | ---     | ---            |


### 1.7.6 Conditioning Paradigm


| **Value**        | **Hex** | **Color Name** |
| ---------------- | ------- | -------------- |
| CLASSICAL        | #4a9eff | Blue           |
| ---              | ---     | ---            |
| EVALUATIVE       | #44cc66 | Green          |
| ---              | ---     | ---            |
| OPERANT          | #ffaa33 | Amber          |
| ---              | ---     | ---            |
| STATE_DEPENDENT  | #9467bd | Purple         |
| ---              | ---     | ---            |
| OCCASION_SETTING | #cc8844 | Warm           |
| ---              | ---     | ---            |
| INTEROCEPTIVE    | #6688cc | Teal-blue      |
| ---              | ---     | ---            |


### 1.7.7 VR Schedule


| **Value** | **Hex** | **Color Name** |
| --------- | ------- | -------------- |
| CRF       | #44cc66 | Green          |
| ---       | ---     | ---            |
| VR-2      | #4a9eff | Blue           |
| ---       | ---     | ---            |
| VR-4      | #ffaa33 | Amber          |
| ---       | ---     | ---            |
| VR-6      | #e94560 | Red            |
| ---       | ---     | ---            |


### 1.7.8 Stimulus Lifecycle


| **Value** | **Hex** | **Color Name** |
| --------- | ------- | -------------- |
| NOVEL     | #44cc66 | Green          |
| ---       | ---     | ---            |
| ACTIVE    | #4a9eff | Blue           |
| ---       | ---     | ---            |
| COOLING   | #ffaa33 | Amber          |
| ---       | ---     | ---            |
| RETIRED   | #888888 | Gray           |
| ---       | ---     | ---            |
| ARCHIVED  | #666666 | Dim gray       |
| ---       | ---     | ---            |


### 1.7.9 Session Intensity Cycle


| **Value** | **Hex** | **Color Name** |
| --------- | ------- | -------------- |
| BUILD_UP  | #ffaa33 | Amber          |
| ---       | ---     | ---            |
| PEAK      | #e94560 | Red            |
| ---       | ---     | ---            |
| RELAX     | #44cc66 | Green          |
| ---       | ---     | ---            |


### 1.7.10 Content Semantic Density


| **Value** | **Hex** | **Color Name** |
| --------- | ------- | -------------- |
| PRIME     | #44cc66 | Green          |
| ---       | ---     | ---            |
| BRIDGE    | #4a9eff | Blue           |
| ---       | ---     | ---            |
| DEEPEN    | #0f3460 | Deep blue      |
| ---       | ---     | ---            |


### 1.7.11 Director Authority Level


| **Value**     | **Hex** | **Color Name** |
| ------------- | ------- | -------------- |
| MUST_DECIDE   | #e94560 | Red            |
| ---           | ---     | ---            |
| SHOULD_DECIDE | #ffaa33 | Amber          |
| ---           | ---     | ---            |
| MAY_DECIDE    | #4a9eff | Blue           |
| ---           | ---     | ---            |
| SUGGEST_ONLY  | #888888 | Gray           |
| ---           | ---     | ---            |


### 1.7.12 Dropdown-Only Values (No Badge Colors)

The following enumerations appear in dropdown selectors only, not as colored badges:


| **Domain**         | **Values**                                                                                                                              |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| Session Arc        | GENTLE_DESCENT, WAVE_PATTERN, DEEP_PLATEAU, CONDITIONING_FOCUS, SLEEP_BRIDGE                                                            |
| ---                | ---                                                                                                                                     |
| Induction Strategy | ENTRAINMENT_HEAVY, SOMATIC_ANCHOR, BREATH_LEAD, PROGRESSIVE_RELAXATION, COGNITIVE_OVERLOAD, FRACTIONATION, FIXATION_FADE, PACE_AND_LEAD |
| ---                | ---                                                                                                                                     |
| GENUS Arc          | GENUS_STANDALONE, GENUS_TRANCE_HYBRID, GENUS_NEUROPROTECTION                                                                            |
| ---                | ---                                                                                                                                     |


# 2 ImGui Style Configuration

Call this function once before the first frame. It sets all ImGui style variables and color tokens. Copy-paste directly into your codebase.

def hex_to_rgba(hex_str: str, alpha: float = 1.0) -> tuple: """Convert '#RRGGBB' to (r, g, b, a) floats in 0.0-1.0 range.""" h = hex_str.lstrip('#') r, g, b = int(h0:2, 16) / 255.0, int(h2:4, 16) / 255.0, int(h4:6, 16) / 255.0 return (r, g, b, alpha) def apply_somna_theme(style=None): """Apply the Somna dark theme to ImGui. Call ONCE before the first frame, after imgui.create_context(). Args: style: imgui style object. If None, uses imgui.get_style(). """ import imgui if style is None: style = imgui.get_style() # ── Rounding ────────────────────────────────────────────── style.window_rounding = 4.0 style.frame_rounding = 3.0 style.scrollbar_rounding = 3.0 style.grab_rounding = 2.0 # ── Sizing / Spacing ────────────────────────────────────── style.window_padding = (12, 12) style.frame_padding = (8, 4) style.item_spacing = (8, 6) style.item_inner_spacing = (6, 4) style.scrollbar_size = 12.0 style.grab_min_size = 10.0 style.window_border_size = 1.0 style.frame_border_size = 0.0 # ── Color Map ───────────────────────────────────────────── # Helper c = hex_to_rgba colors = style.colors # Window / Background colorsimgui.COLOR_WINDOW_BACKGROUND = c('#16213e', 0.85) # panel_bg colorsimgui.COLOR_CHILD_BACKGROUND = c('#16213e', 0.85) colorsimgui.COLOR_POPUP_BACKGROUND = c('#16213e', 1.0) # panel_bg_solid colorsimgui.COLOR_BORDER = c('#2a3a5c', 1.0) # separator colorsimgui.COLOR_BORDER_SHADOW = c('#000000', 0.0) # Text colorsimgui.COLOR_TEXT = c('#e0e0e0', 1.0) # text_primary colorsimgui.COLOR_TEXT_DISABLED = c('#666666', 1.0) # text_disabled colorsimgui.COLOR_TEXT_SELECTED_BACKGROUND= c('#0f3460', 0.6) # Frame (sliders, checkboxes, combos) colorsimgui.COLOR_FRAME_BACKGROUND = c('#0d1b2a', 1.0) # widget_frame_bg colorsimgui.COLOR_FRAME_BACKGROUND_HOVERED= c('#1b2d45', 1.0) # widget_frame_bg_hovered colorsimgui.COLOR_FRAME_BACKGROUND_ACTIVE = c('#0f3460', 1.0) # widget_frame_bg_active # Title bar (unused — we draw custom header, but set anyway) colorsimgui.COLOR_TITLE_BACKGROUND = c('#0f3460', 1.0) colorsimgui.COLOR_TITLE_BACKGROUND_ACTIVE = c('#144080', 1.0) colorsimgui.COLOR_TITLE_BACKGROUND_COLLAPSED = c('#0d1b2a', 0.75) # Menu bar colorsimgui.COLOR_MENUBAR_BACKGROUND = c('#0d1b2a', 1.0) # Scrollbar colorsimgui.COLOR_SCROLLBAR_BACKGROUND = c('#0d1b2a', 1.0) # scrollbar_bg colorsimgui.COLOR_SCROLLBAR_GRAB = c('#2a3a5c', 1.0) # scrollbar_grab colorsimgui.COLOR_SCROLLBAR_GRAB_HOVERED = c('#3a4a6c', 1.0) colorsimgui.COLOR_SCROLLBAR_GRAB_ACTIVE = c('#0f3460', 1.0) # Buttons colorsimgui.COLOR_BUTTON = c('#0f3460', 1.0) # button_bg colorsimgui.COLOR_BUTTON_HOVERED = c('#144080', 1.0) colorsimgui.COLOR_BUTTON_ACTIVE = c('#1a4fa0', 1.0) # Headers (CollapsingHeader) colorsimgui.COLOR_HEADER = c('#0f3460', 1.0) # section_header_bg colorsimgui.COLOR_HEADER_HOVERED = c('#144080', 1.0) colorsimgui.COLOR_HEADER_ACTIVE = c('#1a4fa0', 1.0) # Separator colorsimgui.COLOR_SEPARATOR = c('#2a3a5c', 1.0) colorsimgui.COLOR_SEPARATOR_HOVERED = c('#3a4a6c', 1.0) colorsimgui.COLOR_SEPARATOR_ACTIVE = c('#0f3460', 1.0) # Slider grab colorsimgui.COLOR_SLIDER_GRAB = c('#0f3460', 1.0) # slider_grab colorsimgui.COLOR_SLIDER_GRAB_ACTIVE = c('#2070b0', 1.0) # slider_grab_active # Check mark colorsimgui.COLOR_CHECK_MARK = c('#4a9eff', 1.0) # checkbox_check # Resize grip colorsimgui.COLOR_RESIZE_GRIP = c('#2a3a5c', 0.5) colorsimgui.COLOR_RESIZE_GRIP_HOVERED = c('#3a4a6c', 0.7) colorsimgui.COLOR_RESIZE_GRIP_ACTIVE = c('#0f3460', 1.0) # Tab (not used currently, set for completeness) colorsimgui.COLOR_TAB = c('#0d1b2a', 1.0) colorsimgui.COLOR_TAB_HOVERED = c('#144080', 1.0) colorsimgui.COLOR_TAB_ACTIVE = c('#0f3460', 1.0) colorsimgui.COLOR_TAB_UNFOCUSED = c('#0d1b2a', 1.0) colorsimgui.COLOR_TAB_UNFOCUSED_ACTIVE = c('#16213e', 1.0) # Plot (sparklines use custom draw, but set anyway) colorsimgui.COLOR_PLOT_LINES = c('#4a9eff', 1.0) colorsimgui.COLOR_PLOT_LINES_HOVERED = c('#6ab4ff', 1.0) colorsimgui.COLOR_PLOT_HISTOGRAM = c('#0f3460', 1.0) colorsimgui.COLOR_PLOT_HISTOGRAM_HOVERED = c('#144080', 1.0) # Modal dimming colorsimgui.COLOR_MODAL_WINDOW_DIM_BACKGROUND = c('#000000', 0.35)

**Note**

pyimgui uses imgui.COLOR_ constants to index into style.colors. The exact constant names may vary between pyimgui versions (e.g., COLOR_WINDOW_BACKGROUND vs Col_WindowBg). Verify against your installed pyimgui version.

# 3 Font Specification

Font family: system monospace stack. Primary: "JetBrains Mono" (if available on system), fallback: "Consolas", fallback: default ImGui font (ProggyClean).

## 3.1 Font Size Table


| **Context**     | **Size (px)** | **Weight** | **Usage**                                   |
| --------------- | ------------- | ---------- | ------------------------------------------- |
| Panel title     | 18            | Bold       | "Somna Control" header text                 |
| ---             | ---           | ---        | ---                                         |
| Section header  | 14            | Bold       | CollapsingHeader text for Advanced sections |
| ---             | ---           | ---        | ---                                         |
| Widget label    | 13            | Regular    | "Master Volume", "Heart Rate", etc.         |
| ---             | ---           | ---        | ---                                         |
| Widget value    | 13            | Regular    | "0.75", "72 BPM", "04:32"                   |
| ---             | ---           | ---        | ---                                         |
| Badge text      | 11            | Bold       | "DEEPENING", "N2", "VR-4"                   |
| ---             | ---           | ---        | ---                                         |
| Tooltip text    | 12            | Regular    | Hover tooltip content                       |
| ---             | ---           | ---        | ---                                         |
| Debug text      | 11            | Regular    | Raw JSON viewer, decision log               |
| ---             | ---           | ---        | ---                                         |
| Section summary | 12            | Regular    | Collapsed header one-line summaries         |
| ---             | ---           | ---        | ---                                         |
| Alert text      | 13            | Bold       | "SIGNAL LOST", "MOTION"                     |
| ---             | ---           | ---        | ---                                         |
| Source icon     | 11            | Regular    | ⚙ robot icon, gear icon, padlock icon       |
| ---             | ---           | ---        | ---                                         |


## 3.2 Font Loading Code

def load_somna_fonts(font_path: str = None): """Load all required font sizes from a single TTF file. Call BEFORE the first frame, after imgui.create_context(). Must be called before any imgui rendering occurs. Args: font_path: Path to .ttf file (JetBrains Mono or Consolas). If None, falls back to default ImGui font. Returns: dict mapping context name to imgui font object. """ import imgui io = imgui.get_io() fonts = {} sizes = { 'panel_title': 18.0, 'section_header': 14.0, 'widget_label': 13.0, 'widget_value': 13.0, 'tooltip': 12.0, 'section_summary':12.0, 'badge': 11.0, 'debug': 11.0, 'source_icon': 11.0, 'alert': 13.0, } if font_path is None: # Use default font at all sizes for name, size in sizes.items(): fontsname = io.fonts.add_font_default(size) return fonts for name, size in sizes.items(): fontsname = io.fonts.add_font_from_file_ttf(font_path, size) # Rebuild font atlas after loading # (The renderer must call io.fonts.get_tex_data_as_rgba32() # and upload to GPU after this function returns.) return fonts

**Warning**

ImGui requires ALL fonts to be loaded before the first imgui.new_frame() call. Loading fonts mid-session requires rebuilding the font atlas and re-uploading the texture to the GPU. Avoid this.

# 4 Widget Sizing Specifications

Panel width: **320px** (minus 24px window padding = **296px** usable content width).

Cue-Test mode panel width: **240px** (minus 24px window padding = **216px** usable content width).


| **Widget Type**      | **Width**                          | **Height**                              | **Padding**                   | **Additional Specs**                                                                                                                                                                                                 |
| -------------------- | ---------------------------------- | --------------------------------------- | ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Slider               | 296px full width                   | 20px frame height (incl. frame padding) | 8px H / 4px V (frame_padding) | Grab width 10px. Value label right-aligned inside frame. Label ABOVE slider in text_label color.                                                                                                                     |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Toggle (Checkbox)    | 16x16px checkbox frame             | 16px                                    | —                             | Label to the right with 6px spacing. Checkmark in checkbox_check.                                                                                                                                                    |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Dropdown (Combo)     | 296px full width                   | 24px                                    | 8px H / 4px V                 | Arrow button 24x24px on right side.                                                                                                                                                                                  |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Badge                | Auto-width (text + 12px H padding) | ~22px (text + 4px V padding)            | 12px H / 4px V                | Corner radius 3px. Background from badge_colors map. Text #e0e0e0 except on light backgrounds (WAKE, N1) where text becomes #1a1a2e.                                                                                 |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Gauge                | —                                  | —                                       | —                             | Essential view: 40px radius. Advanced/standalone: 60px radius. 8px stroke width. 180° arc (bottom semicircle, speedometer style). Gradient: gauge_low → gauge_mid → gauge_high. Value text centered below arc, 13px. |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Sparkline            | 80px                               | 20px                                    | —                             | Line color #4a9eff. No fill. Line width 1px. Positioned right of value display. Background transparent.                                                                                                              |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Indicator            | 296px                              | ~20px                                   | —                             | Label in text_label left-aligned. Value in text_primary or text_muted right-aligned. Same line.                                                                                                                      |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Counter              | 296px                              | ~20px                                   | —                             | Same as Indicator. Value is integer.                                                                                                                                                                                 |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Timer                | 296px                              | ~20px                                   | —                             | Same as Indicator. Value formatted MM:SS (or HH:MM:SS if > 1 hour).                                                                                                                                                  |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Progress Bar         | 296px                              | 16px                                    | —                             | Fill: progress_bar_fill. Background: widget_frame_bg. Percentage text centered inside bar.                                                                                                                           |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Phase Ring           | 24px                               | 24px                                    | —                             | Circle, 24px diameter. Arc from 12 o'clock clockwise to current phase position. Fill #4a9eff. Background circle: widget_frame_bg. Positioned inline, right of breath phase value.                                    |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Gate Indicator       | ~64px (4 × 10px + 3 × 6px gaps)    | 10px circles + 11px labels below        | —                             | 4 circles, 10px diameter each, 6px spacing. Green (#44cc66) = pass, Red (#e94560) = fail. Labels below: "R A C S" (Respiratory, Alpha, Cardiac, SQI).                                                                |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Alert Badge          | Auto-width                         | ~22px                                   | 12px H / 4px V                | Same as Badge but with pulsing animation. Alpha oscillates 0.6–1.0 over 1.0s (sinusoidal). Background: alert_red_bg. Text: alert_red.                                                                                |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Text (multi-line)    | 296px                              | Variable (scrollable via BeginChild)    | —                             | Font size 11px (debug text). Line height 1.4x.                                                                                                                                                                       |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |
| Composite Gate Badge | Auto-width                         | ~22px                                   | 12px H / 4px V                | Green bg + "ALL CLEAR" when all 4 gates pass. Red bg + "BLOCKED" when any gate fails. Same sizing as Badge.                                                                                                          |
| ---                  | ---                                | ---                                     | ---                           | ---                                                                                                                                                                                                                  |


**Cue-Test Mode Adjustment**

In Cue-Test mode (240px panel), replace all "296px" widths above with **216px**. Gauge radius shrinks to **30px**. Sparkline width remains 80px.

# 5 Essential Layer Layout — Trance Mode (Default)

This is the default view. Panel: 320px wide, full screen height, anchored to right edge. Background: panel_bg (#16213e at alpha 0.85).

## 5.1 Panel Header (All Modes)

The header is always visible at the top of the panel, regardless of session mode.


| **Element**         | **Position** | **Spec**                                                                                                                                         |
| ------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| "SOMNA"             | Left         | 18px bold, text_primary (#e0e0e0)                                                                                                                |
| ---                 | ---          | ---                                                                                                                                              |
| Layer toggle: E A D | Center       | Three buttons, 24x24px each. Active button: button_bg (#0f3460). Inactive: widget_frame_bg (#0d1b2a). E = Essential, A = Advanced, D = Debug.    |
| ---                 | ---          | ---                                                                                                                                              |
| Lock count badge    | Right        | "🔒 3" — only visible when locked param count > 0. source_user_lock (#ffcc44) text. "Reset All" text-only button appears on hover of lock count. |
| ---                 | ---          | ---                                                                                                                                              |
| Separator           | Below header | 1px line in separator (#2a3a5c)                                                                                                                  |
| ---                 | ---          | ---                                                                                                                                              |


Total header height: ~40px including padding.

## 5.2 Essential Widgets — Trance Mode

Vertical stack, 6px spacing between rows (from item_spacing.y).


| **Row** | **Key**                                                  | **Widget**           | **Layout**                                                                                                  | **Height**   |
| ------- | -------------------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------- | ------------ |
| 1       | session_elapsed                                          | Timer                | Right-aligned value "04:32:15" in text_primary 13px                                                         | ~20px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 2       | conductor_phase                                          | Badge                | Left-aligned colored pill showing current conductor phase                                                   | ~28px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 3       | session_phase + session_intensity                        | Badge + Gauge        | Session phase badge on left (auto-width). Session intensity gauge on right (40px radius for Essential view) | ~90px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 4       | session_arc                                              | Dropdown             | Full width (296px). Values: GENTLE_DESCENT, WAVE_PATTERN, DEEP_PLATEAU, CONDITIONING_FOCUS, SLEEP_BRIDGE    | ~30px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| —       | —                                                        | SEPARATOR            | Thin line, separator color                                                                                  | 1px + 6px    |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 5       | trance_score                                             | Gauge + Sparkline    | Gauge (40px radius) on left. Sparkline (80×20px) on right. Value "0.72" below gauge.                        | ~90px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 6       | ppg_heart_rate                                           | Value + Sparkline    | Value "68 BPM" left in text_primary. Sparkline (80×20px) right.                                             | ~26px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 7       | eeg_signal_quality                                       | Indicator            | Value "0.85" color-coded: green if >0.7, amber if 0.4–0.7, red if <0.4                                      | ~20px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 8       | eeg_signal_lost                                          | Alert Badge          | Only visible when true. "⚠ SIGNAL LOST" pulsing red. Hidden when false.                                     | 0px or ~28px |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 9       | imu_motion_contaminated                                  | Alert Badge          | Only visible when true. "⚠ MOTION" pulsing red. Hidden when false.                                          | 0px or ~28px |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 10      | ppg_available                                            | Dot Indicator        | Green dot (8px) + "PPG" when true. Red dot + "PPG" when false.                                              | ~20px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 11      | gate_all_clear                                           | Composite Gate Badge | "ALL CLEAR" green or "BLOCKED" red.                                                                         | ~28px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| —       | —                                                        | SEPARATOR            | Thin line                                                                                                   | 1px + 6px    |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 12      | **Audio Group** — mini-header "Audio" in 11px text_muted |                      |                                                                                                             |              |
| ---     | ---                                                      |                      |                                                                                                             |              |
| 12a     | gain_master                                              | Slider               | Label "Master", full width                                                                                  | ~40px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 12b     | gain_tts                                                 | Slider               | Label "TTS", full width                                                                                     | ~40px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 12c     | gain_music                                               | Slider               | Label "Music", full width                                                                                   | ~40px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |
| 12d     | gain_nature                                              | Slider               | Label "Nature", full width                                                                                  | ~40px        |
| ---     | ---                                                      | ---                  | ---                                                                                                         | ---          |


**Total Essential content height (Trance):** approximately 580–620px. Fits on a 1080p display with room below for Advanced sections.

# 6 Essential Layer Layout — Sleep Mode

Same panel header as Section 5.1. All widgets below the header, 6px vertical spacing.


| **Row** | **Key**                       | **Widget**        | **Layout**                                                                               | **Height**   |
| ------- | ----------------------------- | ----------------- | ---------------------------------------------------------------------------------------- | ------------ |
| 1       | session_elapsed               | Timer             | Right-aligned value                                                                      | ~20px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 2       | sleep_stage                   | Badge             | Color-coded badge per sleep stage (see Section 1.7.3). Dark text on WAKE/N1 backgrounds. | ~28px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 3       | sleep_phase                   | Badge             | Color-coded badge per sleep phase (see Section 1.7.4)                                    | ~28px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 4       | sleep_time_n2_n3              | Timer             | Cumulative N2+N3 time as MM:SS                                                           | ~20px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 5       | sleep_cycle_count             | Counter           | "Cycle 3"                                                                                | ~20px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| —       | —                             | SEPARATOR         | —                                                                                        | 1px + 6px    |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 6       | tmr_enabled                   | Toggle            | Checkbox, label "TMR"                                                                    | ~22px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 7       | tmr_active                    | Badge             | Green "ACTIVE" or gray "IDLE"                                                            | ~28px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 8       | htw_active                    | Badge             | Purple (#9966cc) "TRAINING" or gray "IDLE"                                               | ~28px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| —       | —                             | SEPARATOR         | —                                                                                        | 1px + 6px    |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 9       | ppg_heart_rate                | Value + Sparkline | Value left, sparkline right                                                              | ~26px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 10      | eeg_signal_quality            | Indicator         | Color-coded value                                                                        | ~20px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 11      | eeg_signal_lost               | Alert Badge       | Conditional "⚠ SIGNAL LOST"                                                              | 0px or ~28px |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| —       | —                             | SEPARATOR         | —                                                                                        | 1px + 6px    |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 12      | **Audio Group** (reduced set) |                   |                                                                                          |              |
| ---     | ---                           |                   |                                                                                          |              |
| 12a     | gain_master                   | Slider            | Label "Master"                                                                           | ~40px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |
| 12b     | gain_nature                   | Slider            | Label "Nature"                                                                           | ~40px        |
| ---     | ---                           | ---               | ---                                                                                      | ---          |


**Warning — Sleep Mode Audio**

TTS and Music sliders are **HIDDEN** in Sleep mode Essential layer to prevent accidental audio spikes that could wake the subject. They remain accessible in Advanced layer if needed.

# 7 Essential Layer Layout — GENUS Mode

Same panel header. All widgets below the header, 6px vertical spacing.


| **Row** | **Key**                                                              | **Widget**        | **Layout**                                                                       | **Height**   |
| ------- | -------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------- | ------------ |
| 1       | session_elapsed                                                      | Timer             | Right-aligned value                                                              | ~20px        |
| ---     | ---                                                                  | ---               | ---                                                                              | ---          |
| 2       | genus_enabled                                                        | Toggle            | Checkbox, label "GENUS"                                                          | ~22px        |
| ---     | ---                                                                  | ---               | ---                                                                              | ---          |
| 3       | genus_arc                                                            | Dropdown          | Full width. Values: GENUS_STANDALONE, GENUS_TRANCE_HYBRID, GENUS_NEUROPROTECTION | ~30px        |
| ---     | ---                                                                  | ---               | ---                                                                              | ---          |
| 4       | genus_phase                                                          | Badge             | RAMP_UP (#ffaa33), ACTIVE (#44cc66), WIND_DOWN (#4a9eff)                         | ~28px        |
| ---     | ---                                                                  | ---               | ---                                                                              | ---          |
| 5       | genus_gamma_verified                                                 | Indicator         | Green ✓ when true, red ✗ when false. Label "Gamma Verified"                      | ~20px        |
| ---     | ---                                                                  | ---               | ---                                                                              | ---          |
| 6       | genus_session_minutes                                                | Timer             | GENUS session elapsed time                                                       | ~20px        |
| ---     | ---                                                                  | ---               | ---                                                                              | ---          |
| —       | —                                                                    | SEPARATOR         | —                                                                                | 1px + 6px    |
| ---     | ---                                                                  | ---               | ---                                                                              | ---          |
| 7       | ppg_heart_rate                                                       | Value + Sparkline | Value left, sparkline right                                                      | ~26px        |
| ---     | ---                                                                  | ---               | ---                                                                              | ---          |
| 8       | eeg_signal_quality                                                   | Indicator         | Color-coded value                                                                | ~20px        |
| ---     | ---                                                                  | ---               | ---                                                                              | ---          |
| 9       | eeg_signal_lost                                                      | Alert Badge       | Conditional "⚠ SIGNAL LOST"                                                      | 0px or ~28px |
| ---     | ---                                                                  | ---               | ---                                                                              | ---          |
| —       | —                                                                    | SEPARATOR         | —                                                                                | 1px + 6px    |
| ---     | ---                                                                  | ---               | ---                                                                              | ---          |
| 10      | **Audio Group** — all four gain sliders (master, TTS, music, nature) |                   |                                                                                  |              |
| ---     | ---                                                                  |                   |                                                                                  |              |


**Frequency Exclusivity — GENUS Mode**

Alpha/theta entrainment controls (entrainment_frequency, beat_frequency, gain_isochronic, gain_binaural) are rendered at **50% opacity** when GENUS is active.

Tooltip on hover: *"Disabled during GENUS — 40 Hz gamma entrainment is mutually exclusive with alpha/theta entrainment."*

# 8 Essential Layer Layout — Cue-Test Mode

Panel narrows to **240px** (216px usable content width). Same header but compressed.


| **Row** | **Key**                      | **Widget**        | **Layout**                                               | **Height** |
| ------- | ---------------------------- | ----------------- | -------------------------------------------------------- | ---------- |
| 1       | eeg_signal_quality           | Indicator         | Color-coded value                                        | ~20px      |
| ---     | ---                          | ---               | ---                                                      | ---        |
| 2       | ppg_heart_rate               | Value + Sparkline | Value left, sparkline (80×20px) right                    | ~26px      |
| ---     | ---                          | ---               | ---                                                      | ---        |
| 3       | ppg_hrv_rmssd                | Value + Sparkline | HRV RMSSD value left, sparkline right                    | ~26px      |
| ---     | ---                          | ---               | ---                                                      | ---        |
| 4       | trance_score                 | Gauge + Value     | Gauge at 30px radius + value below                       | ~70px      |
| ---     | ---                          | ---               | ---                                                      | ---        |
| —       | —                            | SEPARATOR         | —                                                        | 1px + 6px  |
| ---     | ---                          | ---               | ---                                                      | ---        |
| 5       | association_strength_current | Gauge             | 30px radius arc gauge                                    | ~70px      |
| ---     | ---                          | ---               | ---                                                      | ---        |
| 6       | conditioning_trial_count     | Counter           | Integer count                                            | ~20px      |
| ---     | ---                          | ---               | ---                                                      | ---        |
| 7       | conditioning_active_pool     | Dropdown          | Full width (216px). Treated as USER_CONTROL in Cue-Test. | ~30px      |
| ---     | ---                          | ---               | ---                                                      | ---        |


**No gain controls.** No audio during cue-test.

# 9 Advanced Section Styling

Each Advanced section is rendered as an imgui.collapsing_header(). Below is the complete rendering specification.

## 9.1 Section Header Appearance


| **Property**       | **Value**                                                        |
| ------------------ | ---------------------------------------------------------------- |
| Height             | 28px                                                             |
| ---                | ---                                                              |
| Background         | section_header_bg (#0f3460)                                      |
| ---                | ---                                                              |
| Text               | text_primary (#e0e0e0), 14px bold                                |
| ---                | ---                                                              |
| Left icon          | 16px triangle arrow (ImGui default CollapsingHeader arrow)       |
| ---                | ---                                                              |
| Right-aligned text | One-line section summary in text_section_summary (#8899bb), 12px |
| ---                | ---                                                              |


## 9.2 Collapsed Summary Examples


| **Section**    | **Summary Format**                  |
| -------------- | ----------------------------------- |
| Conditioning   | VR-4 · Classical · Pool: confidence |
| ---            | ---                                 |
| Habituation    | novelty 0.72 · ACTIVE               |
| ---            | ---                                 |
| Induction      | BREATH_LEAD · 45% · eff 0.68        |
| ---            | ---                                 |
| DeliveryGate   | 3/4 gates · relax L1                |
| ---            | ---                                 |
| TMR            | enabled · 3 cues · spindle-gated    |
| ---            | ---                                 |
| HTW            | eligible · count 1/3                |
| ---            | ---                                 |
| Visual / Audio | temp 2200K · panning ON             |
| ---            | ---                                 |
| GENUS          | 40Hz · verified · 12:30             |
| ---            | ---                                 |


## 9.3 Auto-Expand Behavior

A section auto-expands when its subsystem becomes actively operating. Implementation: call imgui.set_next_item_open(True) on the frame when the subsystem state changes to active. This does **not** force-collapse other sections.

## 9.4 Expanded Section Layout


| **Property**          | **Value**                                                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Left indent           | 8px from section header left edge                                                                                                          |
| ---                   | ---                                                                                                                                        |
| Widget order          | Key order from panel_config.json                                                                                                           |
| ---                   | ---                                                                                                                                        |
| USER_CONTROL widgets  | Full interactive (slider / toggle / dropdown). Labels in text_label.                                                                       |
| ---                   | ---                                                                                                                                        |
| AGENT_TUNABLE widgets | Read-only Indicator. Values in text_muted (#aaaaaa). Source icon (⚙ in #6688cc or gear in #888888) displayed 4px to the left of the value. |
| ---                   | ---                                                                                                                                        |
| TELEMETRY widgets     | Read-only. Values in text_primary.                                                                                                         |
| ---                   | ---                                                                                                                                        |
| Locked parameters     | Padlock icon (🔒) in source_user_lock (#ffcc44) to the LEFT of the label.                                                                  |
| ---                   | ---                                                                                                                                        |


# 10 Debug Mode Overlay

## 10.1 Warning Banner


| **Property** | **Value**                                                                             |
| ------------ | ------------------------------------------------------------------------------------- |
| Position     | Top of panel, full width, above all other content                                     |
| ---          | ---                                                                                   |
| Height       | 32px                                                                                  |
| ---          | ---                                                                                   |
| Background   | debug_banner_bg (#3d1a25, alpha 0.9)                                                  |
| ---          | ---                                                                                   |
| Text         | debug_banner_text (#e94560), 13px bold                                                |
| ---          | ---                                                                                   |
| Content      | "⚠ Debug mode active — manual parameter changes may conflict with automated systems." |
| ---          | ---                                                                                   |


## 10.2 Behavioral Changes

- All AGENT_TUNABLE become **editable** (sliders/dropdowns instead of read-only indicators). Values shown in text_primary instead of text_muted. Still trigger lock protocol when touched.
- INTERNAL keys become **visible** as read-only indicators.

## 10.3 Debug Panel 1 — Raw JSON Viewer


| **Property**     | **Value**                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------ |
| Container        | imgui.begin_child() with scrollbar                                                               |
| ---              | ---                                                                                              |
| Width            | 296px                                                                                            |
| ---              | ---                                                                                              |
| Height           | 200px                                                                                            |
| ---              | ---                                                                                              |
| Font             | Monospaced 11px                                                                                  |
| ---              | ---                                                                                              |
| Key sort         | Alphabetical                                                                                     |
| ---              | ---                                                                                              |
| Key names        | text_muted (#aaaaaa)                                                                             |
| ---              | ---                                                                                              |
| Values           | text_primary (#e0e0e0)                                                                           |
| ---              | ---                                                                                              |
| Separator        | Colon between key:value                                                                          |
| ---              | ---                                                                                              |
| Change highlight | Recently changed keys: background flashes #2a3a5c then fades back to transparent over 1.0 second |
| ---              | ---                                                                                              |


## 10.4 Debug Panel 2 — Decision Log


| **Property**    | **Value**                                              |
| --------------- | ------------------------------------------------------ |
| Container       | imgui.begin_child() with scrollbar                     |
| ---             | ---                                                    |
| Width           | 296px                                                  |
| ---             | ---                                                    |
| Height          | 150px                                                  |
| ---             | ---                                                    |
| Capacity        | Last 50 Director decisions                             |
| ---             | ---                                                    |
| Entry format    | Timestamp in text_muted, decision text in text_primary |
| ---             | ---                                                    |
| Entry separator | 1px line in separator color                            |
| ---             | ---                                                    |
| Font            | 11px throughout                                        |
| ---             | ---                                                    |


## 10.5 Debug Panel 3 — Gate Timing Visualization


| **Property** | **Value**                                                          |
| ------------ | ------------------------------------------------------------------ |
| Width        | 296px                                                              |
| ---          | ---                                                                |
| Height       | 40px                                                               |
| ---          | ---                                                                |
| Time range   | Last 30 seconds. Current time at right edge, 30s ago at left edge. |
| ---          | ---                                                                |
| Rows         | Four rows (one per gate: R, A, C, S)                               |
| ---          | ---                                                                |
| Fire events  | Green (#44cc66) tick marks                                         |
| ---          | ---                                                                |
| Miss events  | Red (#e94560) tick marks                                           |
| ---          | ---                                                                |
| Row labels   | Left side, 11px text_muted                                         |
| ---          | ---                                                                |


# 11 Mode Transition Animation

When the session mode changes (Trance → Sleep, Trance → GENUS, etc.), the panel transitions over a 2.0-second animation cycle driven by mode_transition_alpha.

## 11.1 Transition Timeline


| **Time**    | **Phase** | **Outgoing Widgets**                                   | **Incoming Widgets**           |
| ----------- | --------- | ------------------------------------------------------ | ------------------------------ |
| 0.0s – 1.0s | Fade out  | Alpha fades from 1.0 to 0.0, then collapse height to 0 | Not yet visible                |
| ---         | ---       | ---                                                    | ---                            |
| 1.0s – 1.5s | Expand    | Gone (height 0, alpha 0)                               | Expand height from 0 to target |
| ---         | ---       | ---                                                    | ---                            |
| 1.5s – 2.0s | Fade in   | Gone                                                   | Alpha fades from 0.0 to 1.0    |
| ---         | ---       | ---                                                    | ---                            |


**Net effect:** Old controls fade and shrink → brief gap → new controls grow and fade in.

## 11.2 Locked Parameter Pinning

User-locked parameters that would be hidden by the new mode are **pinned** to a "Locked Parameters" section immediately below Essential, above Advanced sections.


| **Property**   | **Value**                                                          |
| -------------- | ------------------------------------------------------------------ |
| Section border | warning_amber (#ffaa33) left accent border                         |
| ---            | ---                                                                |
| Padlock icon   | Visible next to each pinned parameter label                        |
| ---            | ---                                                                |
| User action    | User can unlock parameters from this section to allow them to hide |
| ---            | ---                                                                |


# 12 Icon Reference

All icons rendered as Unicode glyphs in the loaded font, or as simple ImGui draw primitives via GetWindowDrawList().


| **Icon**         | **Glyph / Method**                     | **Color**          | **Size**     | **Usage**                             |
| ---------------- | -------------------------------------- | ------------------ | ------------ | ------------------------------------- |
| Padlock (locked) | "🔒" Unicode or draw (rectangle + arc) | #ffcc44            | 11px         | User-locked parameter indicator       |
| ---              | ---                                    | ---                | ---          | ---                                   |
| Robot (agent)    | "⚙" Unicode                            | #6688cc            | 11px         | Agent-written parameter source tag    |
| ---              | ---                                    | ---                | ---          | ---                                   |
| Gear (director)  | Custom draw (circle + 6 teeth)         | #888888            | 11px         | Director-written parameter source tag |
| ---              | ---                                    | ---                | ---          | ---                                   |
| Triangle arrow   | ImGui default CollapsingHeader arrow   | text_muted         | 10px         | Section expand/collapse               |
| ---              | ---                                    | ---                | ---          | ---                                   |
| Warning          | "⚠" Unicode                            | #e94560 or #ffaa33 | 13px         | Alert badges and warning banners      |
| ---              | ---                                    | ---                | ---          | ---                                   |
| Checkmark        | Custom draw (two lines forming ✓)      | #44cc66            | 12px         | Gamma verified indicator              |
| ---              | ---                                    | ---                | ---          | ---                                   |
| X mark           | Custom draw (two crossing lines)       | #e94560            | 12px         | Gamma not verified                    |
| ---              | ---                                    | ---                | ---          | ---                                   |
| Green dot        | AddCircleFilled()                      | #44cc66            | 8px diameter | PPG available indicator               |
| ---              | ---                                    | ---                | ---          | ---                                   |
| Red dot          | AddCircleFilled()                      | #e94560            | 8px diameter | PPG unavailable indicator             |
| ---              | ---                                    | ---                | ---          | ---                                   |


# 13 Panel Collapse Behavior


| **State**            | **Spec**                                                                                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Default              | Panel visible, 320px wide                                                                                                                                     |
| ---                  | ---                                                                                                                                                           |
| Toggle key           | Tab keypress toggles panel visibility                                                                                                                         |
| ---                  | ---                                                                                                                                                           |
| Collapsed appearance | 40px-wide vertical tab on right screen edge. Vertical text "SOMNA" in text_muted (#aaaaaa), rotated 90° counter-clockwise. Background: panel_bg at alpha 0.6. |
| ---                  | ---                                                                                                                                                           |
| Expand trigger       | Click on collapsed tab OR Tab keypress                                                                                                                        |
| ---                  | ---                                                                                                                                                           |
| Animation            | 200ms ease-in-out width transition (40px ↔ 320px)                                                                                                             |
| ---                  | ---                                                                                                                                                           |
| Visualization impact | Main Ganzfeld visualization expands to fill freed horizontal space during collapse                                                                            |
| ---                  | ---                                                                                                                                                           |


# 14 Disabled State Rendering

Applied when controls are disabled (e.g., alpha/theta controls during GENUS due to 40 Hz frequency exclusivity).


| **Property** | **Behavior**                                                                                |
| ------------ | ------------------------------------------------------------------------------------------- |
| Color alpha  | All colors rendered at **50% alpha** (multiply existing alpha by 0.5)                       |
| ---          | ---                                                                                         |
| Input        | Slider grab does not respond to mouse. Use imgui.push_item_flag(imgui.ITEM_DISABLED, True). |
| ---          | ---                                                                                         |
| Tooltip      | On hover, display tooltip explaining **why** the control is disabled                        |
| ---          | ---                                                                                         |
| Text color   | text_disabled (#666666) instead of text_primary                                             |
| ---          | ---                                                                                         |
| Lock icon    | **No lock icon.** Disabled ≠ locked. These are distinct states.                             |
| ---          | ---                                                                                         |


**Disabled vs. Locked**

**Disabled:** System-enforced constraint (e.g., frequency exclusivity). Gray at 50% alpha. No padlock icon. Cannot be overridden by user. **Locked:** User-chosen freeze. Full opacity. Padlock icon in #ffcc44. Can be unlocked by user.

# 15 Implementation Checklist

Vesper — work through these in order. Each step builds on the previous. Do not skip ahead.

1. **Load fonts.** Call load_somna_fonts() (Section 3.2) with path to JetBrains Mono or Consolas TTF. Load at all required sizes via imgui.get_io().fonts.add_font_from_file_ttf(). Must complete before first imgui.new_frame().
2. **Apply theme.** Call apply_somna_theme() (Section 2) once before the first frame. This sets all ImGui color tokens and style variables.
3. **Create ControlPanelManager.** Instantiate with panel_config.json path. This is defined in Bible Ch.9 Â§Control-Panel.
4. **Wire render loop.** In the main loop: imgui.new_frame() → panel_manager.render(live_data) → imgui.render() → pass draw data to ModernGL renderer.
5. **Implement widget dispatch dict.** Map widget type strings ("slider", "toggle", "badge", "gauge", etc.) to render functions. Each function takes the widget config and current value.
6. **Implement sparkline ring buffer.** Use collections.deque(maxlen=60) updated at 1 Hz. Each sparkline widget maintains its own buffer instance.
7. **Implement gauge arc draw.** Use draw_list.path_arc_to() + draw_list.path_stroke() from imgui.get_window_draw_list(). Refer to Section 4 for radius and stroke specs.
8. **Implement badge draw.** Use draw_list.add_rect_filled() with rounded corners + imgui.text_colored() overlay. Badge color lookup from Section 1.7 tables.
9. **Implement gate indicator.** Use draw_list.add_circle_filled() for four circles. Colors per Section 4 Gate Indicator spec.
10. **Implement phase ring.** Use draw_list.path_arc_to() + draw_list.path_stroke(). Arc from 12 o'clock clockwise to current phase position.
11. **Implement mode transition.** Alpha interpolation on a per-widget basis using mode_transition_alpha. Follow timeline in Section 11.1.
12. **Implement lock icon rendering.** Draw padlock (🔒) in #ffcc44 to the left of locked widget labels. See Section 12.
13. **Implement source icon rendering.** Draw ⚙ in #6688cc (agent) or gear in #888888 (director) 4px to the left of the value for AGENT_TUNABLE widgets. See Section 9.4.
14. **Test all four session modes.** Trance, GENUS, Sleep, Cue-Test. Verify correct widget set appears for each mode per Sections 5–8.
15. **Verify frequency exclusivity.** Confirm alpha/theta controls render at 50% opacity with correct tooltip during GENUS mode. See Section 14.