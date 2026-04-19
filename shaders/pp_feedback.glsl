#version 330 core
// pp_feedback.glsl — Feedback composite (Reese Phase 3)
// Modes:
//   0 = alpha_decay    — simple fade (current behavior)
//   1 = radial_zoom    — tunnel zoom feedback
//   2 = rotational_smear — angular persistence
//   3 = directional_blur — spiral arm trails (flow field)
//   4 = reaction_diffusion — Gray-Scott organic emergence
//   5 = kaleidoscopic_fold — angular symmetry

in  vec2 uv;
out vec4 fragColor;

uniform sampler2D u_current;
uniform sampler2D u_previous;
uniform float     u_trail_decay;
uniform float     u_feedback_strength;
uniform int       u_feedback_mode;
uniform float     u_zoom_speed;
uniform float     u_rotation_speed;
uniform float     u_flow_speed;
uniform float     u_fold_sectors;
uniform float     u_time;
uniform vec2      u_resolution;

#define PI 3.14159265359

mat2 rot2(float a) {
    float c = cos(a), s = sin(a);
    return mat2(c, -s, s, c);
}

// 3x3 Laplacian for reaction-diffusion
vec3 laplacian3x3(sampler2D tex, vec2 coord) {
    vec2 tx = 1.0 / u_resolution;
    vec3 sum = vec3(0.0);
    sum += texture(tex, coord + vec2(-tx.x, -tx.y)).rgb;
    sum += texture(tex, coord + vec2( 0.0,  -tx.y)).rgb;
    sum += texture(tex, coord + vec2( tx.x, -tx.y)).rgb;
    sum += texture(tex, coord + vec2(-tx.x,  0.0)).rgb;
    sum += texture(tex, coord + vec2( tx.x,  0.0)).rgb;
    sum += texture(tex, coord + vec2(-tx.x,  tx.y)).rgb;
    sum += texture(tex, coord + vec2( 0.0,   tx.y)).rgb;
    sum += texture(tex, coord + vec2( tx.x,  tx.y)).rgb;
    return sum - 8.0 * texture(tex, coord).rgb;
}

// Simple hash for flow field
vec2 flowField(vec2 p, float t) {
    float n1 = fract(sin(dot(p * 1.5 + vec2(0.0, t * 0.11), vec2(127.1, 311.7))) * 43758.5453);
    float n2 = fract(sin(dot(p * 1.5 + vec2(5.2, t * 0.09), vec2(269.5, 183.3))) * 43758.5453);
    return vec2(n2 - 0.5, -(n1 - 0.5));
}

void main() {
    vec4 curr = texture(u_current, uv);

    if (u_trail_decay < 0.001) {
        fragColor = curr;
        return;
    }

    vec2 centered = uv - 0.5;
    vec4 prev;

    if (u_feedback_mode == 1) {
        // Radial zoom — expand previous frame outward
        float z = 1.0 - u_zoom_speed * 0.01;
        vec2 zoom_uv = centered * z + 0.5;
        prev = texture(u_previous, clamp(zoom_uv, 0.0, 1.0));

    } else if (u_feedback_mode == 2) {
        // Rotational smear — angular persistence
        float angle = u_rotation_speed * 0.005;
        vec2 rot_uv = centered * rot2(angle) + 0.5;
        prev = texture(u_previous, clamp(rot_uv, 0.0, 1.0));

    } else if (u_feedback_mode == 3) {
        // Directional flow — spiral arm following
        vec2 flow = flowField(centered * 3.0, u_time);
        vec2 flow_uv = uv - flow * u_flow_speed * 0.01;
        prev = texture(u_previous, clamp(flow_uv, 0.0, 1.0));

    } else if (u_feedback_mode == 4) {
        // Reaction-diffusion (Gray-Scott)
        prev = texture(u_previous, uv);
        vec3 lap = laplacian3x3(u_previous, uv);
        float a = prev.r;
        float b = prev.g;
        float diff_a = 0.8;
        float diff_b = 0.4;
        float feed = 0.055;
        float kill = 0.062;
        float da = diff_a * lap.r - a * b * b + feed * (1.0 - a);
        float db = diff_b * lap.g + a * b * b - (feed + kill) * b;
        float new_a = clamp(a + da * 0.5, 0.0, 1.0);
        float new_b = clamp(b + db * 0.5, 0.0, 1.0);
        prev = vec4(new_a, new_b, prev.b, prev.a);

    } else if (u_feedback_mode == 5) {
        // Kaleidoscopic fold — angular symmetry
        float sectors = max(2.0, u_fold_sectors);
        float angle = atan(centered.y, centered.x);
        float r = length(centered);
        float sector_angle = 2.0 * PI / sectors;
        float folded = mod(angle + PI, sector_angle);
        if (folded > sector_angle * 0.5) folded = sector_angle - folded;
        vec2 fold_uv = vec2(cos(folded), sin(folded)) * r + 0.5;
        prev = texture(u_previous, clamp(fold_uv, 0.0, 1.0));

    } else {
        // Mode 0: simple alpha decay
        prev = texture(u_previous, uv);
    }

    // Composite: additive blend with decay — previous frames accumulate and fade
    float strength = max(0.0, min(1.0, u_feedback_strength));
    float effective_decay = u_trail_decay * (0.3 + 0.7 * strength);
    vec4 trailed = prev * effective_decay;
    // Additive: previous frames build up as glowing trails behind current
    fragColor = vec4(
        min(curr.r + trailed.r, 1.0),
        min(curr.g + trailed.g, 1.0),
        min(curr.b + trailed.b, 1.0),
        min(curr.a + trailed.a, 1.0)
    );
}
