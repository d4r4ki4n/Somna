// pp_bloom_threshold.glsl — Bloom brightness extract (Doc 47 §3.4)
#version 330 core

uniform sampler2D u_texture;
uniform float u_bloom_threshold;  // 0.6–0.9; from pp_bloom_threshold in live_control

in  vec2 uv;
out vec4 frag_color;

void main() {
    vec3 color = texture(u_texture, uv).rgb;
    float brightness = dot(color, vec3(0.2126, 0.7152, 0.0722));
    if (brightness > u_bloom_threshold)
        frag_color = vec4(color, 1.0);
    else
        frag_color = vec4(0.0, 0.0, 0.0, 1.0);
}
