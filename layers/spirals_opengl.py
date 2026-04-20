"""
spirals_opengl.py
Somna — GPU spiral layer

Passes all uniforms including:
  u_thickness   — arm width multiplier from control panel slider
  u_beat_phase  — 0-1 position in beat cycle for breathing effect
  u_color_cycle — 0=use base_color directly, 1=full hue cycling
  u_text_tex    — current phrase rendered as a GL texture (text-on-spiral)
  u_show_text   — whether to overlay text on arms
"""

import math
import pygame
import moderngl
import numpy as np
from layers.font_manager import discover_fonts, make_font


STYLE_MAP = {
    "tunnel_dream": 0,
    "galaxy": 1,
    "archimedean": 2,
    "kaleidoscope": 3,
    "interference": 4,
    "vortex": 6,
    "dna": 7,
    "rose": 9,
    "moire": 10,
    "spirograph": 11,
    "fermat": 12,
    "superformula": 13,
    "liminal": 14,
    "nebula": 16,
    "cobwebs": 18,
    "strange_attractor": 19,
    "flow_field": 20,
    "sacred_geometry": 21,
    "recursive_fractal": 22,
    "potter_tunnel": 23,
    "fractal_scale": 24,
    "neuro_vortex": 25,
    "ojascki": 26,
    "tunnel_warp": 27,
    "ganzflicker": 28,
    "galaxy_morph": 29,
    # authoring guide aliases (Reese spiral_authoring_guide.md)
    "galaxy_arms": 1,
    "bloom": 9,
    # legacy names
    "zyntaks_hybrid": 2,
    "fan_blade": 2,
    "star_polygon": 3,
    "dense_web": 4,
    "wide_vortex": 6,
    "interlocked": 7,
    "radiating_pulse": 0,
}

# Normalize control panel thickness range (4–40) to shader multiplier (0.3–6.0)
_THICK_MIN, _THICK_MAX = 4, 40
_MULT_MIN, _MULT_MAX = 0.3, 6.0

# Text texture dimensions
_TEXT_W, _TEXT_H = 512, 64
_TEXT_FONT_SIZE = 42


class SpiralsLayer:
    """ModernGL GPU spiral shader — 27 styles, beat breathing, text-on-spiral,
    IAF rotation lock (Bible Ch.10 §10.2 §2.3), motion aftereffect cycle (Bible Ch.10 §10.2 §2.4)."""

    def __init__(self, config: dict, ctx: moderngl.Context):
        self.config = config
        self.ctx = ctx
        self.program = self._load_shader()
        self.vao = self._create_vao()
        self.time = 0.0
        self._beat_accum = 0.0
        self._last_phrase = None
        self._text_tex = self._make_blank_text_texture()
        self._spiral_font_paths = discover_fonts(config.get("session_folder"))

        # ── IAF rotation lock (Bible Ch.10 §10.2 §2.3) ──────────────────────────────────
        self._iaf_rot_hz: float = 0.0  # current effective rotation rate
        self._iaf_rot_target_hz: float = 0.0  # target (updated every 30 s)
        self._iaf_rot_interp: float = 0.0  # 0.0 → 1.0 smooth transition
        self._iaf_last_update_t: float = 0.0  # monotonic, seconds

        # ── Aftereffect cycle (Bible Ch.10 §10.2 §2.4) ──────────────────────────────────
        # Direction: +1.0 = CW, 0.0 = paused, -1.0 = CCW
        self._ae_direction: float = 1.0
        self._ae_phase_t: float = 0.0  # time spent in current phase
        self._ae_ramp_factor: float = 1.0  # 1.0 = full speed, 0.0 = stopped

        # ── Loom oscillator ──────────────────────────────────────────────────────────────
        self._loom_accum: float = 0.0  # phase accumulator in cycles

    def _load_shader(self):
        from pathlib import Path

        shader_dir = Path(__file__).parent.parent / "shaders"
        styles_dir = shader_dir / "styles"
        common_path = shader_dir / "common.glsl"

        frag_src = self._assemble_shader(common_path, styles_dir)

        return self.ctx.program(
            vertex_shader="""
                #version 330 core
                in  vec2 in_vert;
                out vec2 uv;
                void main() {
                    gl_Position = vec4(in_vert, 0.0, 1.0);
                    uv = in_vert * 0.5 + 0.5;
                }
            """,
            fragment_shader=frag_src,
        )

    @staticmethod
    def _assemble_shader(common_path, styles_dir):
        with open(common_path, "r", encoding="utf-8") as f:
            src = f.read()

        style_names = [
            "tunnel",
            "galaxy",
            "archimedean",
            "kaleidoscope",
            "interference",
            "vortex",
            "dna",
            "rose",
            "moire",
            "spirograph",
            "fermat",
            "superformula",
            "liminal",
            "nebula",
            "cobwebs",
            "strange_attractor",
            "flow_field",
            "sacred_geometry",
            "recursive_fractal",
            "potter_tunnel",
            "fractal_scale",
            "neuro_vortex",
            "ojascki",
            "tunnel_warp",
            "ganzflicker",
            "galaxy_morph",
        ]

        for name in style_names:
            style_path = styles_dir / f"style_{name}.glsl"
            if style_path.exists():
                with open(style_path, "r", encoding="utf-8") as f:
                    src += "\n" + f.read()

        dispatch_lines = [
            "\n// ── Main dispatch ──────────────────────────────────────────────────────────",
            "void main() {",
            "    vec2 p = centred(uv);",
            "    p *= u_loom_scale;",
            "    vec4 result;",
            "    if      (u_style == 0)  result = style_tunnel(p);",
            "    else if (u_style == 1)  result = style_galaxy(p);",
            "    else if (u_style == 2)  result = style_archimedean(p);",
            "    else if (u_style == 3)  result = style_kaleidoscope(p);",
            "    else if (u_style == 4)  result = style_interference(p);",
            "    else if (u_style == 6)  result = style_vortex(p);",
            "    else if (u_style == 7)  result = style_dna(p);",
            "    else if (u_style == 9)  result = style_rose(p);",
            "    else if (u_style == 10) result = style_moire(p);",
            "    else if (u_style == 11) result = style_spirograph(p);",
            "    else if (u_style == 12) result = style_fermat(p);",
            "    else if (u_style == 13) result = style_superformula(p);",
            "    else if (u_style == 14) result = style_liminal(p);",
            "    else if (u_style == 16) result = style_nebula(p);",
            "    else if (u_style == 18) result = style_cobwebs(p);",
            "    else if (u_style == 19) result = style_strange_attractor(p);",
            "    else if (u_style == 20) result = style_flow_field(p);",
            "    else if (u_style == 21) result = style_sacred_geometry(p);",
            "    else if (u_style == 22) result = style_recursive_fractal(p);",
            "    else if (u_style == 23) result = style_potter_tunnel(p);",
            "    else if (u_style == 24) result = style_fractal_scale(p);",
            "    else if (u_style == 25) result = style_neuro_vortex(p);",
            "    else if (u_style == 26) result = style_ojascki(p);",
            "    else if (u_style == 27) result = style_tunnel_warp(p);",
            "    else if (u_style == 28) result = style_ganzflicker(p);",
            "    else if (u_style == 29) result = style_galaxy_morph(p);",
            "    else                    result = style_tunnel(p);",
            "    fragColor = result;",
            "}",
        ]
        src += "\n".join(dispatch_lines)
        return src

    def _create_vao(self):
        vertices = np.array(
            [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0],
            dtype="f4",
        )
        vbo = self.ctx.buffer(vertices)
        return self.ctx.vertex_array(self.program, [(vbo, "2f", "in_vert")])

    # ── Text texture ──────────────────────────────────────────────────────────

    def _make_blank_text_texture(self) -> moderngl.Texture:
        tex = self.ctx.texture((_TEXT_W, _TEXT_H), 4)
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        tex.repeat_x = True
        tex.repeat_y = False
        blank = np.zeros((_TEXT_H, _TEXT_W, 4), dtype=np.uint8)
        tex.write(blank.tobytes())
        return tex

    def _update_text_texture(self, phrase: str):
        """Render phrase to a pygame surface and upload to GL texture."""
        surf = pygame.Surface((_TEXT_W, _TEXT_H), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))

        chosen = self._spiral_font_paths[0] if self._spiral_font_paths else None
        font = make_font(chosen, _TEXT_FONT_SIZE)

        # Render with explicit black background then set colorkey so the
        # background becomes transparent when blitted onto the SRCALPHA surface.
        # This avoids the solid-white-rectangle problem from the (r,g,b,a)
        # colour tuple path in older pygame builds.
        text_surf = font.render(phrase.upper(), True, (255, 255, 255), (0, 0, 0))
        text_surf.set_colorkey((0, 0, 0))

        y = (_TEXT_H - text_surf.get_height()) // 2
        x = 0
        while x < _TEXT_W:
            surf.blit(text_surf, (x, y))
            x += text_surf.get_width() + 24

        data = pygame.image.tobytes(surf, "RGBA", False)
        self._text_tex.write(data)

    # ── IAF rotation helpers ──────────────────────────────────────────────────

    def _update_iaf_rotation(self, dt: float, cfg: dict) -> float:
        """
        Return a speed_mult modifier based on Bible Ch.10 §10.2 §2.3 IAF-locked rotation.

        Returns 1.0 when rotation_iaf_lock is disabled (no-op).
        When enabled: rotation_rate_Hz = iaf / num_arms, recomputed every 30 s
        with 2 s interpolation.
        """
        if not cfg.get("rotation_iaf_lock", False):
            return 1.0

        iaf = float(cfg.get("eeg_iaf_hz") or 0.0) or 10.0
        num_arms = max(1, min(8, int(cfg.get("spiral_count", 4))))
        divisor = int(cfg.get("rotation_iaf_divisor", 0))
        mult = float(cfg.get("rotation_iaf_multiplier", 1.0))

        self._iaf_last_update_t += dt
        if self._iaf_last_update_t >= 30.0:
            target_hz = (iaf / (divisor if divisor > 0 else num_arms)) * mult
            self._iaf_rot_target_hz = target_hz
            self._iaf_last_update_t = 0.0
            self._iaf_rot_interp = 0.0

        # 2-second smooth interpolation to new target
        if self._iaf_rot_interp < 1.0:
            self._iaf_rot_interp = min(1.0, self._iaf_rot_interp + dt / 2.0)
            self._iaf_rot_hz = (
                self._iaf_rot_hz * (1.0 - self._iaf_rot_interp)
                + self._iaf_rot_target_hz * self._iaf_rot_interp
            )
        else:
            self._iaf_rot_hz = self._iaf_rot_target_hz

        # On first activation, seed immediately
        if self._iaf_rot_hz == 0.0:
            self._iaf_rot_hz = (iaf / (divisor if divisor > 0 else num_arms)) * mult
            self._iaf_rot_target_hz = self._iaf_rot_hz

        # Convert from rotation_rate_Hz to the speed_mult expected by the
        # time integrator. The baseline speed when beat_sync is off uses
        # dt * speed_mult directly; scale so 10 Hz IAF at 4 arms = 2.5 Hz = 1.0.
        # (baseline reference: 10 Hz / 4 arms = 2.5 Hz → speed_mult = 1.0)
        return self._iaf_rot_hz / 2.5

    def _update_aftereffect(self, dt: float, cfg: dict) -> float:
        """
        Manage the CW/pause/CCW rotation cycle per Bible Ch.10 §10.2 §2.4.

        Returns a direction multiplier: +1.0 = CW, 0.0 = stopped, -1.0 = CCW.
        """
        if not cfg.get("aftereffect_enabled", False):
            return self._ae_direction

        cycle_s = float(cfg.get("aftereffect_cycle_s", 35.0))
        pause_s = float(cfg.get("aftereffect_pause_s", 2.0))
        ramp_s = float(cfg.get("aftereffect_ramp_s", 1.5))

        self._ae_phase_t += dt

        if self._ae_ramp_factor == 1.0:
            # Running phase
            if self._ae_phase_t >= cycle_s:
                # Enter ramp-down
                self._ae_phase_t = 0.0
                self._ae_ramp_factor = 1.0  # will decline below
                # Actually transition: ramp speed to 0 over 0.5 s
                self._ae_ramp_factor = 0.0
                return 0.0
        elif self._ae_ramp_factor == 0.0:
            # Pause phase
            if self._ae_phase_t >= pause_s:
                # Flip direction and start ramp-up
                self._ae_direction = -self._ae_direction
                self._ae_phase_t = 0.0
                self._ae_ramp_factor = -1.0  # ramping up
        elif self._ae_ramp_factor < 0.0:
            # Ramp-up phase
            progress = min(1.0, self._ae_phase_t / max(ramp_s, 0.01))
            if progress >= 1.0:
                self._ae_ramp_factor = 1.0
                self._ae_phase_t = 0.0
            return self._ae_direction * progress

        return self._ae_direction if self._ae_ramp_factor == 1.0 else 0.0

    # ── Update / Draw ─────────────────────────────────────────────────────────

    def update(self, dt: float, beat_freq: float, cfg: dict):
        sync = bool(cfg.get("spiral_sync_to_beat", True))
        speed_mult = float(cfg.get("spiral_speed_multiplier", 1.0))

        # ── Phase-cascade convergence pulse (Bible Ch.4 §4.6 §9.2) ────────────────────
        # CenterTextLayer sets _spiral_pulse_pending=True on each gated fire.
        # We consume it here, start a timed pulse, and boost speed_mult for
        # pulse_duration_ms milliseconds — creating audiovisual coherence between
        # the visual disruption and the subliminal text flash.
        if cfg.get("_spiral_pulse_pending") and cfg.get("spiral_phase_pulse", False):
            cfg["_spiral_pulse_pending"] = False
            self._pulse_remaining_s = (
                float(cfg.get("spiral_pulse_duration_ms", 50)) / 1000.0
            )

        if getattr(self, "_pulse_remaining_s", 0.0) > 0:
            intensity = float(cfg.get("spiral_pulse_intensity", 1.3))
            speed_mult *= intensity
            self._pulse_remaining_s = max(0.0, self._pulse_remaining_s - dt)

        # ── IAF rotation lock and aftereffect direction modifiers ────────────
        iaf_speed_mod = self._update_iaf_rotation(dt, cfg)
        ae_direction = self._update_aftereffect(dt, cfg)
        # When IAF lock is active, replace speed_mult; otherwise keep panel value
        if cfg.get("rotation_iaf_lock", False):
            effective_speed = iaf_speed_mod
        else:
            effective_speed = speed_mult
        effective_speed *= ae_direction  # +1 CW, 0 pause, -1 CCW

        if sync and beat_freq > 0.5:
            self.time += dt * (beat_freq / 10.0) * effective_speed
            # Advance our own integrator each frame for smooth per-frame animation
            self._beat_accum = (self._beat_accum + dt * beat_freq) % 1.0
            # When the audio engine writes a new authoritative phase value, snap to it.
            # ConfigManager delivers new values at ~100ms intervals; the snap corrects
            # any accumulated drift between the visual integrator and the audio waveform.
            audio_phase = cfg.get("beat_phase")
            if audio_phase is not None and audio_phase != getattr(
                self, "_last_audio_phase", None
            ):
                self._last_audio_phase = audio_phase
                self._beat_accum = float(audio_phase)
        else:
            self.time += dt * effective_speed
            self._beat_accum = (self._beat_accum + dt * 1.0) % 1.0

        # ── Loom phase accumulation ───────────────────────────────────────────
        if cfg.get("spiral_loom_enabled", False):
            loom_sync = cfg.get("spiral_loom_sync", "manual")
            if loom_sync == "breath":
                # respiratory_rate_hz published by the respiratory tracker (~0.2–0.4 Hz)
                loom_rate = float(cfg.get("respiratory_rate_hz", 0.25) or 0.25)
            elif loom_sync == "beat_div4":
                # Loom at 1/4 of binaural beat frequency (4 Hz beat → 1 Hz loom)
                loom_rate = float(cfg.get("beat_frequency", 10.0) or 10.0) / 4.0
            else:
                loom_rate = float(cfg.get("spiral_loom_rate", 0.08))
            self._loom_accum = (self._loom_accum + dt * loom_rate) % 1.0

        # Only update the text texture when show_text is enabled AND the pool
        # has actually changed. Picking a random phrase every frame caused a
        # 144Hz texture upload that made wide arms flicker badly.
        if cfg.get("spiral_show_text", False):
            pool = cfg.get("affirmations_pool")
            phrase = cfg.get("current_phrase", "")
            if isinstance(pool, list) and pool:
                # Use the pool's identity as a stable key; only re-pick when
                # the pool itself changes (timeline switched tag groups, etc.)
                pool_id = id(pool)
                if pool_id != getattr(self, "_last_pool_id", None):
                    import random

                    phrase = random.choice(pool)
                    self._last_pool_id = pool_id
                    if phrase != self._last_phrase:
                        self._update_text_texture(phrase)
                        self._last_phrase = phrase
            elif phrase and phrase != self._last_phrase:
                self._update_text_texture(phrase)
                self._last_phrase = phrase

    def draw(self, cfg: dict):
        surface = pygame.display.get_surface()
        w, h = surface.get_size()

        style_name = cfg.get("spiral_style", "tunnel_dream")
        style_int = STYLE_MAP.get(style_name, 0)
        base = cfg.get("spiral_base_color", [255, 20, 147])

        # Normalize thickness slider value → shader multiplier
        thick_raw = float(cfg.get("spiral_thickness", 14))
        thick_norm = _MULT_MIN + (thick_raw - _THICK_MIN) / (
            _THICK_MAX - _THICK_MIN
        ) * (_MULT_MAX - _MULT_MIN)

        # color_cycle: "solid"/"bw" → 0 (use base directly), "rainbow"/"cycle" → 1
        color_mode = cfg.get("spiral_color_mode", "rainbow")
        color_cycle = 0.0 if color_mode in ("bw", "solid") else 1.0

        show_text = 1 if cfg.get("spiral_show_text", False) else 0

        # Bind text texture to unit 1
        self._text_tex.use(1)

        # Bible Ch.10 §10.2 §2.1 — spiral geometry (golden vs archimedean)
        geom_key = cfg.get("spiral_geometry", "archimedean")
        golden_spiral = 1 if geom_key == "golden" else 0

        # Bible Ch.10 §10.2 §2.2 & §3.4 — fractal edge amplitude, driven by SR noise floor.
        # When fractal_edge_enabled, derive amplitude from sr_noise_level (0–1)
        # unless an explicit override value is present in config.
        if cfg.get("fractal_edge_enabled", False):
            explicit_amp = cfg.get("fractal_edge_amplitude")
            if explicit_amp is not None:
                fractal_amp = float(explicit_amp)
            else:
                # SR visual floor: map sr_noise_level 0→0, 1→0.4 (empirical max)
                sr_level = max(
                    0.0, min(1.0, float(cfg.get("sr_noise_level", 0.0) or 0.0))
                )
                fractal_amp = round(sr_level * 0.4, 4)
        else:
            fractal_amp = 0.0

        # Bible Ch.10 §10.2 §4.2 — compound CS hue shift
        hue_shift = float(cfg.get("spiral_hue_shift", 0.0))

        self.program["u_time"].value = self.time
        self.program["u_tightness"].value = float(cfg.get("spiral_tightness", 6.0))
        self.program["u_opacity"].value = float(cfg.get("spiral_opacity", 88)) / 100.0
        self.program["u_count"].value = min(8, max(1, int(cfg.get("spiral_count", 4))))
        self.program["u_chaos"].value = float(cfg.get("spiral_chaos", 0.12))
        self.program["u_style"].value = style_int
        self.program["u_thickness"].value = float(thick_norm)
        self.program["u_beat_phase"].value = float(self._beat_accum)
        if "u_entrainment_phase" in self.program:
            self.program["u_entrainment_phase"].value = float(self._beat_accum)
        if "u_entrainment_strength" in self.program:
            self.program["u_entrainment_strength"].value = max(
                0.0,
                min(1.0, float(cfg.get("entrainment_strength", 0.0) or 0.0)),
            )
        self.program["u_color_cycle"].value = float(color_cycle)
        self.program["u_show_text"].value = show_text
        self.program["u_text_tex"].value = 1
        self.program["u_resolution"].value = (float(w), float(h))
        self.program["u_base_color"].value = (
            base[0] / 255.0,
            base[1] / 255.0,
            base[2] / 255.0,
        )
        self.program["u_golden_spiral"].value = golden_spiral
        self.program["u_fractal_edge_amplitude"].value = fractal_amp
        self.program["u_hue_shift"].value = hue_shift / 360.0

        # Loom: oscillate the radial scale around 1.0 using a sine wave.
        # depth=1.0 → ±25% zoom swing (0.75–1.25); depth=0.0 → no effect.
        if cfg.get("spiral_loom_enabled", False):
            loom_depth = float(cfg.get("spiral_loom_depth", 0.25))
            loom_scale = 1.0 + loom_depth * 0.25 * math.sin(math.tau * self._loom_accum)
        else:
            loom_scale = 1.0
        self.program["u_loom_scale"].value = loom_scale

        self.vao.render(moderngl.TRIANGLE_STRIP)
