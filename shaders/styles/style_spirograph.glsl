// Style 11 — Spirograph
// Multi-layer epitrochoid traces with bloom and pulsing cusp nodes.
vec4 style_spirograph(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float n     = float(u_count);

    float R_o   = 0.78;
    float r_i   = R_o / (n + 1.0);
    float arm_r = R_o - r_i;
    float d_pen = arm_r * clamp(0.15 + u_tightness * 0.15, 0.12, 0.92);

    // Primary spirograph trace
    float min_dist = 100.0;
    float cusp_accum = 0.0;
    for (int k = 0; k < 8; k++) {
        float fk    = float(k);
        float valid = step(fk, n - 0.5);
        float t     = angle + fk * TWO_PI / n - u_time * 0.30;
        float phi   = -n * t + u_chaos * sin(t) * 0.35;
        vec2 pt     = vec2(arm_r * cos(t) + d_pen * cos(phi),
                           arm_r * sin(t) + d_pen * sin(phi));
        float dk    = mix(100.0, length(p - pt), valid);
        min_dist    = min(min_dist, dk);

        // Cusp detection — curvature peaks where pen reverses direction
        float speed = length(vec2(-arm_r * sin(t) - d_pen * n * sin(phi) * (-1.0),
                                   arm_r * cos(t) + d_pen * n * cos(phi) * (-1.0)));
        cusp_accum += exp(-dk * dk * 80.0) * (1.0 / max(speed * 0.5, 0.3)) * valid;
    }

    float width = max(0.028, (0.028 + r * 0.022) * u_thickness) * breath();
    float core  = smoothstep(width * 1.3, 0.0, min_dist);
    float halo  = smoothstep(width * 5.0, 0.0, min_dist) * 0.50;
    float g     = core + halo * (1.0 - core);

    // Second layer — different R/r ratio, phase-shifted
    float r_i2 = R_o / (n * 0.5 + 2.0);
    float arm_r2 = R_o - r_i2;
    float d_pen2 = arm_r2 * clamp(0.2 + u_tightness * 0.1, 0.12, 0.85);
    float min_dist2 = 100.0;
    for (int k = 0; k < 6; k++) {
        float fk = float(k);
        float t  = angle + fk * TWO_PI / max(n * 0.5, 1.0) - u_time * 0.18 + 1.0;
        float phi = -(n * 0.5) * t + u_chaos * cos(t * 0.7) * 0.25;
        vec2 pt  = vec2(arm_r2 * cos(t) + d_pen2 * cos(phi),
                        arm_r2 * sin(t) + d_pen2 * sin(phi));
        min_dist2 = min(min_dist2, length(p - pt));
    }
    float width2 = width * 0.6;
    float core2  = smoothstep(width2 * 1.3, 0.0, min_dist2) * 0.35;
    float halo2  = smoothstep(width2 * 4.0, 0.0, min_dist2) * 0.15;
    g += core2 + halo2 * (1.0 - core2);

    // Cusp glow — pulsing bright spots at curve cusps
    float cusp_pulse = 0.6 + 0.4 * sin(u_time * 2.5);
    float cusp_glow  = cusp_accum * cusp_pulse * 0.8;
    g += cusp_glow;

    g += exp(-r * r * 8.0) * 0.25;
    g *= breath();

    // Phase-shifted color per layer
    vec3 col = arm_color(fract(r * 0.30 + u_time * 0.04), g);
    col += arm_color(fract(r * 0.20 + u_time * 0.06 + 0.3), core2 + halo2) * 0.5;
    col += vec3(1.0, 0.9, 0.7) * cusp_glow * 0.4;

    return vec4(col, g * u_opacity * smoothstep(0.0, 0.04, r)) * entrainmentModulation();
}
