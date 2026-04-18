// Style 4 — Interference
vec4 style_interference(vec2 p) {
    float r1 = length(p);
    float a1 = atan(p.y, p.x);
    vec2  src2 = vec2(cos(u_time * 0.4), sin(u_time * 0.3)) * (0.3 + u_chaos * 0.4);
    float r2   = length(p - src2);
    float a2   = atan(p.y - src2.y, p.x - src2.x);
    float wave1 = sin(r1 * u_tightness * 2.0 - a1 * float(u_count) - u_time * 2.5);
    float wave2 = sin(r2 * u_tightness * 2.0 - a2 * float(u_count) + u_time * 2.0);
    float interference = (wave1 + wave2) * 0.5;
    float g = (smoothstep(-0.1, 0.6, interference)
             + smoothstep(0.7, 1.0, abs(interference)) * 0.4) * breath();
    vec3 col = arm_color(interference * 0.5 + u_time * 0.05, g);
    return vec4(col, g * u_opacity * smoothstep(1.7, 0.2, max(r1, r2)) * 0.85);
}
