"""
Spiral shader assembly regression test.

Verifies that the modular shader (common.glsl + per-style files) compiles
and renders for all 26 implemented styles.

Run:  python -m tests.test_spiral_shader_assembly
      pytest tests/test_spiral_shader_assembly.py -v
"""

import os

os.environ["PYOPENGL_PLATFORM"] = "osmesa"

import moderngl
import numpy as np
import unittest
from pathlib import Path

SHADER_DIR = Path(__file__).parent.parent / "shaders"
STYLES_DIR = SHADER_DIR / "styles"
COMMON_PATH = SHADER_DIR / "common.glsl"

VERT = """
#version 330 core
in  vec2 in_vert;
out vec2 uv;
void main() {
    gl_Position = vec4(in_vert, 0.0, 1.0);
    uv = in_vert * 0.5 + 0.5;
}
"""

STYLE_NAMES = [
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

STYLE_IDS = list(range(26))

TEST_W, TEST_H = 320, 240

UNIFORM_DEFAULTS = dict(
    u_time=1.0,
    u_tightness=6.0,
    u_opacity=0.8,
    u_base_color=(0.7, 0.4, 0.8),
    u_count=5,
    u_chaos=0.3,
    u_resolution=(TEST_W, TEST_H),
    u_thickness=1.0,
    u_beat_phase=0.25,
    u_entrainment_phase=0.0,
    u_entrainment_strength=0.0,
    u_color_cycle=1.0,
    u_style=0,
    u_golden_spiral=0,
    u_fractal_edge_amplitude=0.0,
    u_hue_shift=0.0,
    u_loom_scale=1.0,
    u_show_text=0,
)


def _assemble_shader() -> str:
    src = COMMON_PATH.read_text(encoding="utf-8")
    for name in STYLE_NAMES:
        p = STYLES_DIR / f"style_{name}.glsl"
        if p.exists():
            src += "\n" + p.read_text(encoding="utf-8")
    dispatch = [
        "",
        "void main() {",
        "    vec2 p = centred(uv);",
        "    p *= u_loom_scale;",
        "    vec4 result;",
    ]
    for i, name in enumerate(STYLE_NAMES):
        idx = STYLE_IDS[i]
        connector = "" if i == 0 else "else "
        dispatch.append(
            f"    {connector}if (u_style == {idx}) result = style_{name}(p);"
        )
    dispatch.append("    fragColor = result;")
    dispatch.append("}")
    src += "\n".join(dispatch)
    return src


class TestShaderAssembly(unittest.TestCase):
    ctx = None
    fbo = None
    vbo = None

    @classmethod
    def setUpClass(cls):
        cls.ctx = moderngl.create_standalone_context()
        cls.fbo = cls.ctx.framebuffer(
            color_attachments=[cls.ctx.texture((TEST_W, TEST_H), 4)]
        )
        cls.fbo.use()
        quad = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4")
        cls.vbo = cls.ctx.buffer(quad)

    def _render(self, prog, style_idx):
        self.fbo.clear()
        vao = self.ctx.vertex_array(prog, [(self.vbo, "2f", "in_vert")])
        for name, val in UNIFORM_DEFAULTS.items():
            prog[name].value = val
        prog["u_style"].value = style_idx
        vao.render(moderngl.TRIANGLE_STRIP)
        return (
            np.frombuffer(self.fbo.read(components=4), dtype=np.uint8)
            .reshape(TEST_H, TEST_W, 4)
            .copy()
        )

    def test_assembled_compiles(self):
        src = _assemble_shader()
        prog = self.ctx.program(vertex_shader=VERT, fragment_shader=src)
        self.assertIsNotNone(prog)

    def test_assembled_uniforms_match(self):
        src = _assemble_shader()
        prog = self.ctx.program(vertex_shader=VERT, fragment_shader=src)
        for name in UNIFORM_DEFAULTS:
            self.assertIn(name, prog, f"Missing uniform: {name}")

    def test_all_styles_render(self):
        """All styles must compile and render non-black output."""
        assembled_src = _assemble_shader()
        prog = self.ctx.program(vertex_shader=VERT, fragment_shader=assembled_src)
        for name, idx in zip(STYLE_NAMES, STYLE_IDS):
            with self.subTest(style=name, idx=idx):
                img = self._render(prog, idx)
                self.assertEqual(img.shape, (TEST_H, TEST_W, 4))
                self.assertFalse(
                    np.all(img == 0), f"Style {idx} ({name}) rendered all-black"
                )

    def test_all_style_files_exist(self):
        for name in STYLE_NAMES:
            p = STYLES_DIR / f"style_{name}.glsl"
            self.assertTrue(p.exists(), f"Missing style file: {p}")

    def test_common_glsl_exists(self):
        self.assertTrue(COMMON_PATH.exists())


if __name__ == "__main__":
    unittest.main()
