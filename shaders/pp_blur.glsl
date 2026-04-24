// pp_blur.glsl — Gaussian blur pass (Doc 47 §3.2)
// Apply horizontally (direction=(1/w,0)) then vertically (direction=(0,1/h))
// for separable 2-pass blur.
#version 330 core

uniform sampler2D u_texture;
uniform vec2 u_direction;    // (1.0/width, 0) or (0, 1.0/height)
uniform float u_blur_radius; // pixels; from pp_blur_radius in live_control
uniform vec2 u_texel_size;   // 1.0 / resolution

in  vec2 uv;
out vec4 frag_color;

void main() {
    float weights[5] = float[](0.227027, 0.194596, 0.121622, 0.054054, 0.016216);
    vec3 result = texture(u_texture, uv).rgb * weights[0];
    for (int i = 1; i < 5; i++) {
        vec2 offset = u_direction * u_blur_radius * float(i) * u_texel_size;
        result += texture(u_texture, uv + offset).rgb * weights[i];
        result += texture(u_texture, uv - offset).rgb * weights[i];
    }
    float a = texture(u_texture, uv).a;
    frag_color = vec4(result, a);
}
