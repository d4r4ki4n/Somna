// Style 11 — Spirograph
vec4 style_spirograph(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float n     = float(u_count);

    float R_o   = 0.78;
    float r_i   = R_o / (n + 1.0);
    float arm_r = R_o - r_i;                             // n/(n+1)*R_o
    // d_pen scaled to arm_r so it sweeps a large portion of the canvas.
    // u_tightness 1→5 maps pen from ~28% to ~90% of orbit radius.
    float d_pen = arm_r * clamp(0.15 + u_tightness * 0.15, 0.12, 0.92);

    float min_dist = 100.0;
    for (int k = 0; k < 8; k++) {
        float fk    = float(k);
        float valid = step(fk, n - 0.5);
        float t     = angle + fk * TWO_PI / n - u_time * 0.30;
        float phi   = -n * t + u_chaos * sin(t) * 0.35;
        vec2 pt     = vec2(arm_r * cos(t) + d_pen * cos(phi),
                           arm_r * sin(t) + d_pen * sin(phi));
        float dk    = mix(100.0, length(p - pt), valid);
        min_dist    = min(min_dist, dk);
    }

    float width = max(0.028, (0.028 + r * 0.018) * u_thickness) * breath();
    float core  = smoothstep(width * 1.3, 0.0, min_dist);
    float halo  = smoothstep(width * 5.0, 0.0, min_dist) * 0.45;
    float g     = core + halo * (1.0 - core);
    g += exp(-r * r * 8.0) * 0.75;
    g *= breath();

    vec3 col = arm_color(fract(r * 0.30 + u_time * 0.04), g);
    return vec4(col, g * u_opacity * smoothstep(2.25, 0.02, r) * smoothstep(0.0, 0.04, r)) * entrainmentModulation();
}
