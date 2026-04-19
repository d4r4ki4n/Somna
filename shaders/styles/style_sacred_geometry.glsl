// Style 21 — Flower of Life (overlapping circle geometry, luminous edges only)
vec4 style_sacred_geometry(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float g     = 0.0;

    // Flower of Life: hexagonal grid of circle centers
    float scale = 1.8 + u_tightness * 0.4;

    // Slow rotation for hypnotic spin
    float rot = u_time * 0.15;
    float cr = cos(rot), sr = sin(rot);
    vec2 sp = vec2(p.x * cr - p.y * sr, p.x * sr + p.y * cr) * scale;

    // Hex grid basis vectors
    const vec2 e1 = vec2(1.0, 0.0);
    const vec2 e2 = vec2(0.5, 0.8660254);

    // Check nearby cells — expanded range to fill screen
    for (int j = -4; j <= 4; j++) {
        for (int i = -4; i <= 4; i++) {
            vec2 center = e1 * float(i) + e2 * float(j);
            float d = length(sp - center);

            // Circle edge — thick enough to see clearly
            float edge_width = (0.04 + u_chaos * 0.02) * u_thickness * 0.5;
            float edge = smoothstep(edge_width, 0.0, abs(d - 1.0));

            // Broader glow around each edge
            float glow = exp(-pow(d - 1.0, 2.0) * 30.0) * 0.3;

            // Phase wave traveling along the pattern
            float wave = sin(d * 4.0 - u_time * 1.2 + float(i + j) * 0.8) * 0.5 + 0.5;
            float brightness = edge * (0.7 + wave * 0.3) + glow;

            g = max(g, brightness);
        }
    }

    g *= breath();

    // Center glow
    float core = exp(-r * r * 5.0) * 0.5;
    g += core;

    // Color: radial + time-based, no angle component to avoid seam
    vec3 col = arm_color(fract(r * 0.2 - u_time * 0.04 + g * 0.3), g);
    float alpha = g * u_opacity;
    alpha *= smoothstep(3.0, 0.3, r);

    return vec4(col, alpha) * entrainmentModulation();
}
