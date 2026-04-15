"""Somna Control Panel — Theme and Color Tokens.

All color constants, badge color maps, font loading, and ImGui style
application per the ImGui Visual Design Reference (Bible Ch.9 §9.2).

API uses imgui_bundle (not legacy pyimgui).
Adapted from Reese's design: uses style.set_color_() instead of
style.colors[] indexing (not available in imgui-bundle nanobind bindings).
"""
from __future__ import annotations

from pathlib import Path

from imgui_bundle import imgui


# ── Hex Conversion Helpers ────────────────────────────────────────────────────

def hex_to_rgba(
    hex_color: str, alpha: float = 1.0,
) -> tuple[float, float, float, float]:
    """Convert '#RRGGBB' → (r, g, b, a) floats in [0, 1]."""
    h = hex_color.lstrip("#")
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
        alpha,
    )


def hex_to_u32(hex_color: str, alpha: float = 1.0) -> int:
    """Convert '#RRGGBB' → ImGui packed u32 (ABGR byte order)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(min(max(alpha, 0.0), 1.0) * 255)
    return (a << 24) | (b << 16) | (g << 8) | r


def token_u32(name: str, alpha_override: float | None = None) -> int:
    """Named color token → u32."""
    hex_val, default_a = COLOR_TOKENS[name]
    return hex_to_u32(hex_val, alpha_override if alpha_override is not None else default_a)


def token_rgba(
    name: str, alpha_override: float | None = None,
) -> tuple[float, float, float, float]:
    """Named color token → (r, g, b, a)."""
    hex_val, default_a = COLOR_TOKENS[name]
    return hex_to_rgba(hex_val, alpha_override if alpha_override is not None else default_a)


def _v4(name: str, alpha_override: float | None = None) -> imgui.ImVec4:
    """Shorthand: token → ImVec4. Internal use in apply_somna_theme."""
    return imgui.ImVec4(*token_rgba(name, alpha_override))


# ── Rosé Pine Moon palette ───────────────────────────────────────────────────
# https://rosepinetheme.com/palette/ingredients/
#
# Base:          #232136   Surface:   #2a273f   Overlay:  #393552
# Muted:         #6e6a86   Subtle:    #908caa   Text:     #e0def4
# Love:          #eb6f92   Gold:      #f6c177   Rose:     #ea9a97
# Pine:          #3e8fb0   Foam:      #9ccfd8   Iris:     #c4a7e7
# Highlight Low: #2a283e   Hl Med:    #44415a   Hl High:  #56526e

RP = {
    "base":    "#232136", "surface": "#2a273f", "overlay": "#393552",
    "muted":   "#6e6a86", "subtle":  "#908caa", "text":    "#e0def4",
    "love":    "#eb6f92", "gold":    "#f6c177", "rose":    "#ea9a97",
    "pine":    "#3e8fb0", "foam":    "#9ccfd8", "iris":    "#c4a7e7",
    "hl_low":  "#2a283e", "hl_med":  "#44415a", "hl_high": "#56526e",
}


# ── Color Tokens (§1) ────────────────────────────────────────────────────────
# token_name → (hex, default_alpha)

COLOR_TOKENS: dict[str, tuple[str, float]] = {
    # Backgrounds — mapped to RP Moon roles
    "app_bg":                    (RP["base"],    1.0),
    "panel_bg":                  (RP["surface"], 0.97),
    "panel_bg_solid":            (RP["surface"], 1.0),
    "section_header_bg":         (RP["overlay"], 1.0),
    "section_header_bg_hovered": (RP["hl_med"],  1.0),
    "section_header_bg_active":  (RP["hl_high"], 1.0),
    "widget_frame_bg":           (RP["overlay"], 1.0),
    "widget_frame_bg_hovered":   (RP["hl_med"],  1.0),
    "widget_frame_bg_active":    (RP["hl_high"], 1.0),
    "separator":                 (RP["overlay"], 1.0),
    "scrollbar_bg":              (RP["hl_low"],  1.0),
    "scrollbar_grab":            (RP["overlay"], 1.0),
    "scrollbar_grab_hovered":    (RP["hl_med"],  1.0),
    "scrollbar_grab_active":     (RP["iris"],    1.0),
    "tooltip_bg":                (RP["base"],    0.97),
    "tooltip_border":            (RP["overlay"], 1.0),
    # Text
    "text_primary":              (RP["text"],    1.0),
    "text_muted":                (RP["muted"],   1.0),
    "text_disabled":             (RP["muted"],   0.7),
    "text_label":                (RP["subtle"],  1.0),
    "text_value":                (RP["text"],    1.0),
    "text_section_summary":      (RP["subtle"],  1.0),
    # Interactive
    "slider_grab":               (RP["iris"],    1.0),
    "slider_grab_hovered":       (RP["rose"],    1.0),
    "slider_grab_active":        (RP["love"],    1.0),
    "checkbox_check":            (RP["love"],    1.0),
    "button_bg":                 (RP["overlay"], 1.0),
    "button_bg_hovered":         (RP["hl_med"],  1.0),
    "button_bg_active":          (RP["hl_high"], 1.0),
    "progress_bar_fill":         (RP["love"],    1.0),
    # Alerts / status
    "alert_red":                 (RP["love"],    1.0),
    "alert_red_bg":              (RP["hl_low"],  1.0),
    "warning_amber":             (RP["gold"],    1.0),
    "warning_amber_bg":          (RP["hl_low"],  1.0),
    "success_green":             (RP["foam"],    1.0),
    # Status strip
    "status_strip_bg":           (RP["overlay"], 0.55),
    # Debug
    "debug_banner_bg":           (RP["hl_low"],  0.95),
    "debug_banner_text":         (RP["love"],    1.0),
    # Source / authority
    "source_agent":              (RP["iris"],    1.0),
    "source_director":           (RP["muted"],   1.0),
    "source_user_lock":          (RP["gold"],    1.0),
    # Gauge gradient
    "gauge_low":                 (RP["love"],    1.0),
    "gauge_mid":                 (RP["gold"],    1.0),
    "gauge_high":                (RP["foam"],    1.0),
    "gauge_track":               (RP["hl_low"],  1.0),
}


# ── Badge Color Maps (§1.7) ──────────────────────────────────────────────────

BADGE_CONDUCTOR_PHASE: dict[str, str] = {
    "IDLE":          RP["muted"],
    "ACTIVE":        RP["love"],
    "DEEPENING":     RP["iris"],
    "SLEEP_APPROACH":RP["pine"],
    "SLEEP_ONSET":   RP["foam"],
    "SLEEP_MAINTAIN":RP["foam"],
    "SLEEP_TRAINING":RP["rose"],
    "SLEEP_WAKE":    RP["gold"],
}

BADGE_SESSION_PHASE: dict[str, str] = {
    "ARRIVAL":       RP["muted"],
    "INDUCTION":     RP["love"],
    "DEEPENING":     RP["iris"],
    "WORK":          RP["foam"],
    "CONSOLIDATION": RP["gold"],
    "EMERGENCE":     RP["rose"],
}

# Sleep stages use (bg_color, text_color) because some need dark text
BADGE_SLEEP_STAGE: dict[str, tuple[str, str]] = {
    "WAKE": (RP["gold"],    RP["base"]),
    "N1":   (RP["foam"],    RP["base"]),
    "N2":   (RP["pine"],    RP["text"]),
    "N3":   (RP["overlay"], RP["text"]),
    "REM":  (RP["iris"],    RP["base"]),
}

BADGE_SLEEP_PHASE: dict[str, str] = {
    "DEEPENING":     RP["iris"],
    "SLEEP_APPROACH":RP["pine"],
    "SLEEP_ONSET":   RP["foam"],
    "SLEEP_MAINTAIN":RP["foam"],
    "SLEEP_TRAINING":RP["rose"],
    "SLEEP_WAKE":    RP["gold"],
}

BADGE_GENUS_PHASE: dict[str, str] = {
    "RAMP_UP":   RP["gold"],
    "ACTIVE":    RP["foam"],
    "WIND_DOWN": RP["iris"],
}

BADGE_CONDITIONING_PARADIGM: dict[str, str] = {
    "CLASSICAL":        RP["love"],
    "EVALUATIVE":       RP["foam"],
    "OPERANT":          RP["gold"],
    "STATE_DEPENDENT":  RP["iris"],
    "OCCASION_SETTING": RP["rose"],
    "INTEROCEPTIVE":    RP["pine"],
}

BADGE_VR_SCHEDULE: dict[str, str] = {
    "CRF":  RP["foam"],
    "VR-2": RP["love"],
    "VR-4": RP["gold"],
    "VR-6": RP["rose"],
}

BADGE_STIMULUS_LIFECYCLE: dict[str, str] = {
    "NOVEL":    RP["foam"],
    "ACTIVE":   RP["love"],
    "COOLING":  RP["gold"],
    "RETIRED":  RP["muted"],
    "ARCHIVED": RP["hl_med"],
}

BADGE_SESSION_INTENSITY: dict[str, str] = {
    "BUILD_UP": RP["gold"],
    "PEAK":     RP["love"],
    "RELAX":    RP["foam"],
}

BADGE_CONTENT_DENSITY: dict[str, str] = {
    "PRIME":  RP["foam"],
    "BRIDGE": RP["love"],
    "DEEPEN": RP["iris"],
}

BADGE_DIRECTOR_AUTHORITY: dict[str, str] = {
    "MUST_DECIDE":   RP["love"],
    "SHOULD_DECIDE": RP["gold"],
    "MAY_DECIDE":    RP["iris"],
    "SUGGEST_ONLY":  RP["muted"],
}

# Lookup: config badge_colors key prefix → map
BADGE_MAPS: dict[str, dict] = {
    "conductor_phase":       BADGE_CONDUCTOR_PHASE,
    "session_phase":         BADGE_SESSION_PHASE,
    "sleep_stage":           BADGE_SLEEP_STAGE,
    "sleep_phase":           BADGE_SLEEP_PHASE,
    "genus_phase":           BADGE_GENUS_PHASE,
    "conditioning_paradigm": BADGE_CONDITIONING_PARADIGM,
    "vr_schedule":           BADGE_VR_SCHEDULE,
    "stimulus_lifecycle":    BADGE_STIMULUS_LIFECYCLE,
    "session_intensity":     BADGE_SESSION_INTENSITY,
    "content_density":       BADGE_CONTENT_DENSITY,
    "director_authority":    BADGE_DIRECTOR_AUTHORITY,
}


# ── Font Spec (§3) ───────────────────────────────────────────────────────────

FONT_SIZES: dict[str, float] = {
    "panel_title":    18.0,
    "section_header": 14.0,
    "widget_label":   13.0,
    "widget_value":   13.0,
    "badge":          11.0,
    "tooltip":        12.0,
    "debug":          11.0,
    "section_summary":12.0,
    "alert":          13.0,
    "source_icon":    11.0,
}

# Populated by load_somna_fonts(); key = role name
FONTS: dict[str, imgui.ImFont] = {}

_FONT_SEARCH_DIRS = [
    Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts",
    Path("C:/Windows/Fonts"),
    Path.home() / ".local" / "share" / "fonts",
    Path("/usr/share/fonts/truetype"),
]

_REGULAR_NAMES = ["calibri.ttf",  "Calibri.ttf",  "JetBrainsMono-Regular.ttf", "consola.ttf"]
_BOLD_NAMES    = ["calibrib.ttf", "CalibriBold.ttf", "JetBrainsMono-Bold.ttf", "consolab.ttf"]
_CJK_NAMES     = ["msyh.ttc", "msyh.ttf", "NotoSansCJK-Regular.ttc", "NotoSansCJK-Regular.ttf"]
_SYMBOL_NAMES  = ["seguisym.ttf", "DejaVuSans.ttf", "Symbola.ttf"]


def _find_font(candidates: list[str]) -> Path | None:
    for d in _FONT_SEARCH_DIRS:
        for name in candidates:
            p = d / name
            if p.exists():
                return p
    return None


def load_somna_fonts() -> None:
    """Load fonts into the ImGui atlas with CJK and symbol merge. Call once before the first frame."""
    io      = imgui.get_io()
    regular = _find_font(_REGULAR_NAMES)
    bold    = _find_font(_BOLD_NAMES)
    cjk     = _find_font(_CJK_NAMES)
    symbols = _find_font(_SYMBOL_NAMES)

    def _merge(path: "Path", size: float) -> None:
        try:
            cfg = imgui.ImFontConfig()
            cfg.merge_mode = True
            io.fonts.add_font_from_file_ttf(str(path), size, cfg)
        except Exception:
            pass

    def _add_with_cjk(src: "Path | None", size: float) -> "imgui.ImFont":
        try:
            font = (io.fonts.add_font_from_file_ttf(str(src), size)
                    if src else io.fonts.add_font_default())
        except Exception:
            font = io.fonts.add_font_default()
        if cjk:
            _merge(cjk, size)
        if symbols:
            _merge(symbols, size)
        return font

    for role, size in FONT_SIZES.items():
        FONTS[role] = _add_with_cjk(regular, size)

    for role in ("panel_title_bold", "section_header_bold", "alert_bold", "badge_bold"):
        base_role = role.removesuffix("_bold")
        size = FONT_SIZES.get(base_role, 13.0)
        FONTS[role] = _add_with_cjk(bold or regular, size)


# ── Apply Theme ──────────────────────────────────────────────────────────────

def apply_somna_theme() -> None:
    """Apply the full Somna color scheme and style vars to the active context.

    Adapted for imgui-bundle: uses style.set_color_() instead of
    style.colors[] indexing (not available in nanobind bindings).
    """
    s  = imgui.get_style()
    sc = s.set_color_
    C  = imgui.Col_

    # Style vars
    s.window_padding     = imgui.ImVec2(8, 4)
    s.frame_padding      = imgui.ImVec2(4, 2)
    s.item_spacing       = imgui.ImVec2(6, 2)
    s.item_inner_spacing = imgui.ImVec2(4, 2)
    s.cell_padding       = imgui.ImVec2(4, 1)
    s.window_rounding    = 0.0
    s.frame_rounding     = 3.0
    s.scrollbar_rounding = 3.0
    s.grab_rounding      = 2.0
    s.scrollbar_size     = 10.0
    s.grab_min_size      = 10.0

    # Colors
    sc(C.window_bg,               _v4("panel_bg"))
    sc(C.child_bg,                imgui.ImVec4(0, 0, 0, 0))
    sc(C.popup_bg,                _v4("panel_bg_solid"))
    sc(C.border,                  _v4("separator"))
    sc(C.border_shadow,           imgui.ImVec4(0, 0, 0, 0))
    sc(C.text,                    _v4("text_primary"))
    sc(C.text_disabled,           _v4("text_disabled"))
    sc(C.frame_bg,                _v4("widget_frame_bg"))
    sc(C.frame_bg_hovered,        _v4("widget_frame_bg_hovered"))
    sc(C.frame_bg_active,         _v4("widget_frame_bg_active"))
    sc(C.slider_grab,             _v4("slider_grab"))
    sc(C.slider_grab_active,      _v4("slider_grab_active"))
    sc(C.check_mark,              _v4("checkbox_check"))
    sc(C.button,                  _v4("button_bg"))
    sc(C.button_hovered,          _v4("button_bg_hovered"))
    sc(C.button_active,           _v4("button_bg_active"))
    sc(C.header,                  _v4("section_header_bg"))
    sc(C.header_hovered,          _v4("section_header_bg_hovered"))
    sc(C.header_active,           _v4("section_header_bg_active"))
    sc(C.separator,               _v4("separator"))
    sc(C.separator_hovered,       imgui.ImVec4(*hex_to_rgba(RP["hl_med"])))
    sc(C.separator_active,        _v4("widget_frame_bg_active"))
    sc(C.scrollbar_bg,            _v4("scrollbar_bg"))
    sc(C.scrollbar_grab,          _v4("scrollbar_grab"))
    sc(C.scrollbar_grab_hovered,  _v4("scrollbar_grab_hovered"))
    sc(C.scrollbar_grab_active,   _v4("scrollbar_grab_active"))
    sc(C.plot_lines,              imgui.ImVec4(*hex_to_rgba(RP["love"])))
    sc(C.plot_lines_hovered,      imgui.ImVec4(*hex_to_rgba(RP["rose"])))
    sc(C.tab,                     _v4("section_header_bg"))
    sc(C.tab_hovered,             _v4("section_header_bg_hovered"))
    sc(C.tab_selected,            _v4("section_header_bg_active"))
    sc(C.tab_dimmed,              _v4("widget_frame_bg"))
    sc(C.tab_dimmed_selected,     _v4("section_header_bg"))
    sc(C.title_bg,                _v4("section_header_bg"))
    sc(C.title_bg_active,         _v4("section_header_bg_hovered"))
    sc(C.menu_bar_bg,             _v4("widget_frame_bg"))
    sc(C.modal_window_dim_bg,     imgui.ImVec4(0, 0, 0, 0.35))
    # Tooltip uses popup_bg; set to solid for readability
    sc(C.popup_bg,                _v4("tooltip_bg"))
