// Style 19 — Lissajous Weave (interlocking parametric curves)
vec4 style_strange_attractor(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float g     = 0.0;
    float hue_acc = 0.0;

    // 5 interlocking Lissajous curves with different frequency ratios
    for (int i = 0; i < 5; i++) {
        float fi = float(i);

        // Frequency ratios produce evolving weave patterns
        float a = 3.0 + fi * 0.7 + u_tightness * 0.3;
        float b = 2.0 + fi * 0.5;
        float phase_shift = fi * PI * 0.4 + u_time * (0.3 + fi * 0.08);

        // Sample points along the curve and measure minimum distance
        float min_dist = 10.0;
        for (int j = 0; j < 16; j++) {
            float t = float(j) / 16.0 * TWO_PI;
            float cx = sin(a * t + phase_shift) * 0.8;
            float cy = sin(b * t) * 0.8;
            float d = length(p - vec2(cx, cy));
            min_dist = min(min_dist, d);
        }

        // Width varies by radius and thickness param
        float w = (0.03 + r * 0.01) * u_thickness * 0.8;
        float line = smoothstep(w, 0.0, min_dist);
        float glow = exp(-min_dist * min_dist * 25.0) * 0.25;

        float layer = (line + glow) * (1.0 - fi * 0.08);
        g = g + layer * (1.0 - g);
        hue_acc += min_dist * 0.5;
    }

    // Chaos adds noise perturbation to the weave
    if (u_chaos > 0.1) {
        g *= 1.0 + snoise(p * 3.0 + u_time * 0.2) * u_chaos * 0.3;
    }

    g *= breath();

    // Center glow
    float core = exp(-r * r * 5.0) * 0.75;
    g += core;

    vec3 col = arm_color(fract(hue_acc * 0.3 + u_time * 0.05), g);
    float alpha = g * u_opacity;
    alpha *= 1.0;

    return vec4(col, alpha) * entrainmentModulation();
}
