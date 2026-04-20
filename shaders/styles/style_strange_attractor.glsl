// Style 19 — Lissajous Weave (interlocking parametric curves)
vec4 style_strange_attractor(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float g     = 0.0;
    float hue_acc = 0.0;

    // 5 interlocking Lissajous curves with different frequency ratios
    for (int i = 0; i < 5; i++) {
        float fi = float(i);

        float a = 3.0 + fi * 0.7 + u_tightness * 0.3;
        float b = 2.0 + fi * 0.5;
        float phase_shift = fi * PI * 0.4 + u_time * (0.3 + fi * 0.08);

        // Radius scales with count so more arms fill more of the screen
        float curve_r = 1.2 + u_count * 0.15;

        float min_dist = 10.0;
        for (int j = 0; j < 48; j++) {
            float t = float(j) / 48.0 * TWO_PI;
            float cx = sin(a * t + phase_shift) * curve_r;
            float cy = sin(b * t) * curve_r;
            float d = length(p - vec2(cx, cy));
            min_dist = min(min_dist, d);
        }

        float w = (0.025 + r * 0.008) * u_thickness * 0.9;
        float line = smoothstep(w, 0.0, min_dist);
        float glow = exp(-min_dist * min_dist * 18.0) * 0.30;

        float layer = (line + glow) * (1.0 - fi * 0.07);
        g = g + layer * (1.0 - g);
        hue_acc += min_dist * 0.4;
    }

    if (u_chaos > 0.1) {
        g *= 1.0 + snoise(p * 3.0 + u_time * 0.2) * u_chaos * 0.3;
    }

    g *= breath();

    float core = exp(-r * r * 5.0) * 0.75;
    g += core;

    vec3 col = arm_color(fract(hue_acc * 0.3 + u_time * 0.05), g);
    float alpha = g * u_opacity;

    return vec4(col, alpha) * entrainmentModulation();
}
