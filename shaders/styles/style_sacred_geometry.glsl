// Style 21 — Flower of Life (overlapping circle geometry, luminous edges only)
vec4 style_sacred_geometry(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float g     = 0.0;

    // Flower of Life: hexagonal grid of circle centers
    // Each circle has radius = grid spacing, so neighbors overlap
    float scale = 1.8 + u_tightness * 0.4;

    // Slow rotation for hypnotic spin
    float rot = u_time * 0.15;
    float cr = cos(rot), sr = sin(rot);
    vec2 sp = vec2(p.x * cr - p.y * sr, p.x * sr + p.y * cr) * scale;

    // Hex grid basis vectors
    const vec2 e1 = vec2(1.0, 0.0);
    const vec2 e2 = vec2(0.5, 0.8660254);  // 60 degrees

    // Check nearest few cells for circle edges
    for (int j = -2; j <= 2; j++) {
        for (int i = -2; i <= 2; i++) {
            vec2 center = e1 * float(i) + e2 * float(j);
            float d = length(sp - center);

            // Circle edge — narrow bright ring
            float edge_width = (0.02 + u_chaos * 0.01) * u_thickness * 0.3;
            float edge = smoothstep(edge_width, 0.0, abs(d - 1.0));

            // Soft outer glow
            float glow = exp(-pow(d - 1.0, 2.0) * 80.0) * 0.15;

            // Phase wave traveling along the pattern
            float wave = sin(d * 4.0 - u_time * 1.2 + float(i + j) * 0.8) * 0.5 + 0.5;
            float brightness = edge * (0.6 + wave * 0.4) + glow;

            g = max(g, brightness);
        }
    }

    // Add subtle spoke structure for visual interest
    float spoke_angle = TWO_PI / float(u_count * 2);
    float nearest = abs(mod(angle + PI, spoke_angle) - spoke_angle * 0.5);
    float spoke = exp(-nearest * nearest * 150.0 / (r + 0.3)) * 0.2;
    g += spoke * breath();

    // Central seed circle — brighter
    float center_circle = smoothstep(0.025, 0.0, abs(r * scale - 1.0)) * 0.8;
    g = max(g, center_circle);

    g *= breath();

    // Center glow
    float core = exp(-r * r * 5.0) * 0.6;
    g += core;

    vec3 col = arm_color(fract(r * 0.2 - u_time * 0.04 + angle / TWO_PI * 0.5), g);
    float alpha = g * u_opacity;
    alpha *= smoothstep(2.0, 0.1, r);

    return vec4(col, alpha) * entrainmentModulation();
}
