// Style 9 — Bloom (Polar Rose)
vec4 style_rose(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float k     = float(u_count);
    float width = (0.020 + r * 0.013) * u_thickness;

    float g       = 0.0;
    float hue_acc = 0.0;

    for (int i = 0; i < 4; i++) {
        float fi = float(i);

        // Speed differential: tightness spreads layers apart so they orbit differently
        float speed  = 0.38 + fi * (0.12 + u_tightness * 0.07);
        // Each layer has a chaos cross-harmonic at 2k (still integer → seamless)
        float raw    = cos(k * angle - u_time * speed)
                     + u_chaos * 0.22 * cos(k * 2.0 * angle - u_time * speed * 1.7 + fi * 1.1);
        float rose_r = max(raw, 0.0) * (1.20 - fi * 0.13) * breath();

        // Solid fill: smooth gradient dark→bright toward the petal edge
        float inside = step(r, rose_r);
        float fill   = inside * smoothstep(0.0, rose_r, r) * 0.58;

        float dist  = abs(r - rose_r);
        float edge  = smoothstep(width * 1.2, 0.0, dist);
        float halo  = smoothstep(width * 4.5, 0.0, dist) * 0.30 * (1.0 - inside);

        float layer = edge + fill * (1.0 - edge) + halo * (1.0 - edge) * (1.0 - inside);
        g       = g + layer * (1.0 - g) * (1.05 - fi * 0.12);
        hue_acc += rose_r * (1.2 - fi * 0.15);
    }

    g += exp(-r * r * 8.0) * 0.85;

    // hue_acc is a weighted sum of all layer radii — seamless and always moving
    vec3 col = arm_color(fract(hue_acc * 0.28 + r * 0.14 - u_time * 0.05), g * breath());
    return vec4(col, g * u_opacity * smoothstep(2.25, 0.03, r));
}
