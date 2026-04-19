// pp_composite.glsl — Combined bloom+vignette+IAF+ACES+grain pass
// Merges bloom additive composite, vignette tunnel, IAF luminance mod,
// ACES filmic tonemapping, and film grain into a single pass.
#version 330 core

uniform sampler2D u_scene;
uniform sampler2D u_bloom;
uniform float u_bloom_intensity;      // 0.0–0.5; pp_bloom_intensity
uniform float u_vignette_sigma;       // 0.25–0.80; pp_vignette_sigma
uniform float u_vignette_intensity;   // 0.0–1.0; pp_vignette_intensity
uniform float u_iaf_mod_amplitude;    // 0.0–0.05; pp_iaf_mod_amplitude
uniform float u_iaf_mod_phase;        // 0.0–2π, per-frame; pp_iaf_mod_phase
uniform float u_film_grain;           // 0.0–0.15; pp_film_grain
uniform float u_time;                 // seconds, for grain animation
uniform int   u_tonemap;              // 0=off, 1=ACES

in  vec2 uv;
out vec4 frag_color;

vec3 acesTonemap(vec3 x) {
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

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

    // ACES filmic tonemapping
    if (u_tonemap == 1) {
        combined = acesTonemap(combined);
    }

    // Film grain — per-frame luminance noise
    if (u_film_grain > 0.001) {
        float grain = fract(sin(dot(uv * vec2(u_time * 1000.0), vec2(12.9898, 78.233))) * 43758.5453);
        combined += (grain - 0.5) * u_film_grain;
    }

    float scene_a = texture(u_scene, uv).a;
    frag_color = vec4(max(combined, vec3(0.0)), scene_a);
}
