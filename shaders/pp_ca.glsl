// pp_ca.glsl — Chromatic aberration pass (Doc 47 §3.2)
#version 330 core

uniform sampler2D u_texture;
uniform float u_ca_strength;  // 0.0 to 0.01; from pp_ca_strength in live_control
uniform vec2  u_resolution;

in  vec2 uv;
out vec4 frag_color;

void main() {
    vec2 center = vec2(0.5);
    vec2 dir    = uv - center;
    float dist  = length(dir);
    vec2 offset = dir * u_ca_strength * dist;  // radial: stronger at edges
    float r = texture(u_texture, uv + offset).r;
    float g = texture(u_texture, uv).g;
    float b = texture(u_texture, uv - offset).b;
    frag_color = vec4(r, g, b, 1.0);
}
