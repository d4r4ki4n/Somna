// pp_composite.glsl — Combined bloom+vignette+IAF pass (Doc 47 §11.1 merged)
// Merges bloom additive composite, vignette tunnel, and IAF luminance mod
// into a single pass to reduce FBO overhead.
#version 330 core

uniform sampler2D u_scene;
uniform sampler2D u_bloom;
uniform float u_bloom_intensity;      // 0.0–0.5; pp_bloom_intensity
uniform float u_vignette_sigma;       // 0.25–0.80; pp_vignette_sigma
uniform float u_vignette_intensity;   // 0.0–1.0; pp_vignette_intensity
uniform float u_iaf_mod_amplitude;    // 0.0–0.05; pp_iaf_mod_amplitude
uniform float u_iaf_mod_phase;        // 0.0–2π, per-frame; pp_iaf_mod_phase

in  vec2 uv;
out vec4 frag_color;

void main() {
    vec3 scene = texture(u_scene, uv).rgb;
    vec3 bloom = texture(u_bloom, uv).rgb;
    vec3 combined = scene + bloom * u_bloom_intensity;

    // Vignette
    vec2 center   = vec2(0.5);
    float dist    = length(uv - center);
    float sigma   = max(u_vignette_sigma, 0.01);
    float vignette = exp(-dist * dist / (2.0 * sigma * sigma));
    vignette = mix(1.0, vignette, u_vignette_intensity);
    combined *= vignette;

    // IAF luminance modulation (sub-threshold whole-screen flicker)
    float iaf_mod = 1.0 + u_iaf_mod_amplitude * sin(u_iaf_mod_phase);
    combined *= iaf_mod;

    frag_color = vec4(combined, 1.0);
}
