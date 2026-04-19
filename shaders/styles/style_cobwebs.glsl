// Style 18 — Gossamer (seamless radial filigree with drifting dewdrop rings)
vec4 style_cobwebs(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Use arm distance field for seamless spokes
    vec3 field = archimedean_field(p, u_time * 0.6);
    float arm_d = field.x;
    float width = field.z;

    // Thin bright spoke lines
    float spoke = smoothstep(width, 0.0, arm_d * width * 2.0);
    // Broader glow around each spoke
    float spoke_glow = exp(-arm_d * arm_d * 80.0) * 0.4;

    // Drifting concentric dewdrop rings — modulate radius with time
    int n_rings = 3 + int(u_chaos * 6.0);
    float rings = 0.0;
    for (int i = 1; i <= 6; i++) {
        float fi = float(i);
        float ring_r = 0.15 * fi + 0.08 * sin(u_time * 0.4 + fi * 1.7) * u_chaos;
        float ring_dist = abs(r - ring_r);
        float ring_width = (0.008 + u_chaos * 0.004) * u_thickness;
        float ring_line = smoothstep(ring_width, 0.0, ring_dist);
        // Each ring pulses at a different phase
        float ring_pulse = 0.5 + 0.5 * sin(u_time * 0.8 + fi * 2.1);
        rings += ring_line * ring_pulse;
    }

    // Combine: spokes + rings + glow
    float g = (spoke + spoke_glow + rings * 0.6) * breath();

    // Center glow
    float core = exp(-r * r * 6.0) * 0.9;
    g += core;

    vec3 col = arm_color(angle / TWO_PI + r * 0.15 - u_time * 0.03, g);
    float alpha = g * u_opacity;
    alpha *= smoothstep(3.0, 0.3, r);

    return vec4(col, alpha) * entrainmentModulation();
}
