// Style 4 — Interference
// Two coherent wave sources produce constructive/destructive beating patterns.
// Chromatic fringe via frequency offset per channel — no spatial shift, no seam.
vec4 style_interference(vec2 p) {
    float r1 = length(p);
    float a1 = atan(p.y, p.x);

    // Orbiting second source
    float src_angle = u_time * 0.35;
    float src_r = 0.3 + u_chaos * 0.5;
    vec2  src2 = vec2(cos(src_angle), sin(src_angle)) * src_r;
    float r2   = length(p - src2);
    float a2   = atan(p.y - src2.y, p.x - src2.x);

    float count = float(u_count);
    float tight = u_tightness * 2.0;

    // Primary waves
    float wave1 = sin(r1 * tight - a1 * count - u_time * 2.5);
    float wave2 = sin(r2 * tight - a2 * count + u_time * 2.0);

    // Third harmonic — offset orbit
    vec2  src3 = vec2(cos(src_angle * 0.7 + 2.0), sin(src_angle * 0.6 + 1.0)) * src_r * 0.6;
    float r3   = length(p - src3);
    float a3   = atan(p.y - src3.y, p.x - src3.x);
    float wave3 = sin(r3 * tight * 0.7 - a3 * count * 0.5 - u_time * 1.8) * 0.4;

    float interference = wave1 + wave2 + wave3;

    // Chromatic fringe via frequency offset — same position, different tightness.
    // No spatial shift so no atan seam.
    float chroma = 0.08 + u_chaos * 0.04;
    float wave_r = sin(r1 * tight * (1.0 + chroma) - a1 * count - u_time * 2.5)
                 + sin(r2 * tight * (1.0 + chroma) - a2 * count + u_time * 2.0) + wave3;
    float wave_b = sin(r1 * tight * (1.0 - chroma) - a1 * count - u_time * 2.5)
                 + sin(r2 * tight * (1.0 - chroma) - a2 * count + u_time * 2.0) + wave3;

    // Constructive peaks, destructive troughs, beat nodes
    float peak   = smoothstep(0.2, 1.0, interference);
    float trough = smoothstep(-0.1, -0.8, -interference) * 0.25;
    float node   = exp(-interference * interference * 8.0) * 0.4;

    float g = (peak + trough + node) * breath();

    // Core glow at source positions
    float glow1 = exp(-r1 * r1 * 6.0) * 0.5;
    float glow2 = exp(-dot(p - src2, p - src2) * 6.0) * 0.3;
    g += glow1 + glow2;

    vec3 col;
    if (u_color_cycle > 0.5) {
        float g_r = (smoothstep(0.2, 1.0, wave_r) + node) * breath();
        float g_g = (peak + node) * breath();
        float g_b = (smoothstep(0.2, 1.0, wave_b) + node) * breath();
        float base_hue = r1 * 0.15 + u_time * 0.04;
        vec3 col_r = arm_color(base_hue, g_r);
        vec3 col_g = arm_color(base_hue + 0.33, g_g);
        vec3 col_b = arm_color(base_hue + 0.66, g_b);
        col = vec3(col_r.r, col_g.g, col_b.b) * 1.3;
    } else {
        col = arm_color(interference * 0.3 + r1 * 0.15 + u_time * 0.05, g);
        col += u_base_color * (glow1 + glow2) * 0.5;
    }

    return vec4(col, g * u_opacity * 0.9) * entrainmentModulation();
}
