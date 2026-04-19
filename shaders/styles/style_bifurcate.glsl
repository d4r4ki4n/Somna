// Style 17 — Bifurcating Golden Fractal Spiral
vec4 style_bifurcate(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Golden logarithmic spiral (equiangular constant matching archimedean_field)
    const float b = 0.30634896;
    float log_r = log(max(r, 0.015));
    float theta = log_r / b;
    float phase = theta - angle - u_time * 0.85 + u_chaos * sin(theta * 2.0);

    float arm_per  = TWO_PI / float(u_count);
    float arm_d    = mod(phase, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);
    float width    = (0.032 + r * 0.036) * u_thickness * breath();
    float main_arm = smoothstep(width * 1.25, 0.0, arm_dist);

    // Bifurcation: 4 self-similar child levels via PHI phase multiplication.
    // Each level contributes independently; blended with Porter-Duff over.
    float child_total = 0.0;
    float cs = 0.60;  // per-level brightness weight; shrinks by golden ratio
    for (int i = 0; i < 4; i++) {
        float child_phase = phase * PHI + float(i) * PHI;
        float cad = mod(child_phase, arm_per) / arm_per;
        float cd  = min(cad, 1.0 - cad);
        // Each level progressively thinner
        float cw  = max(width * (1.6 - float(i) * 0.22), 0.005);
        float c   = smoothstep(cw, 0.0, cd) * cs;
        child_total += c * (1.0 - child_total);
        cs *= 0.618;
    }
    float child_arm = child_total * 0.70;
    float total     = main_arm + child_arm * (1.0 - main_arm * 0.65);

    vec3  col = arm_color(fract(theta * 0.28 + u_time * 0.06), total * breath());
    // Glow at bifurcation intersections — brightest where child meets parent
    float bifur_glow = child_arm * main_arm * 3.5;
    col += u_base_color * bifur_glow;

    float alpha = clamp(total + bifur_glow * 0.3, 0.0, 1.0) * u_opacity
                * 1.0;

    if (u_show_text == 1 && total > 0.22) {
        float arm_u = fract(phase / TWO_PI);
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * u_base_color * 2.2, txt.a * total * 0.75);
    }
    return vec4(col, alpha) * entrainmentModulation();
}
