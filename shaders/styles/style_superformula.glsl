// Style 13 — Superformula
vec4 style_superformula(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float m     = float(u_count);

    // Slow rotation: angle offset is continuous, seam analysis unchanged
    // (abs(cos(m*(angle-time*0.5)*0.5)) still seamless for integer m)
    float angle_rot = angle - u_time * 0.18;

    // n slides from blob (n≈0.4) to star (n≈3.5) via tightness
    float n  = clamp(u_tightness * 0.55, 0.30, 3.80);
    float ca = pow(max(abs(cos(m * angle_rot * 0.5)), 0.001), n);
    float sa = pow(max(abs(sin(m * angle_rot * 0.5)), 0.001), n);
    float r_sf = pow(ca + sa, -1.0 / n) * 1.02;

    // Breathe and add chaos wobble (r-based, no seam)
    r_sf *= (0.88 + 0.12 * breath())
          * (1.0 + u_chaos * 0.09 * sin(r * 3.5 + u_time * 0.9));

    float width = (0.022 + r_sf * 0.028) * u_thickness;

    // Three nested copies at decreasing scales for visual mass and depth
    float g = 0.0;
    for (int i = 0; i < 3; i++) {
        float fi  = float(i);
        float sc  = pow(0.58, fi);          // scales: 1.0, 0.58, 0.336
        float r_s = r_sf * sc;
        float w_s = width * pow(0.78, fi);

        // Solid fill — strong gradient from center to boundary
        float ins  = step(r, r_s);
        float fill = ins * pow(max(r / max(r_s, 0.001), 0.0), 0.45) * (0.65 - fi * 0.12);

        float d_s  = abs(r - r_s);
        float edge = smoothstep(w_s * 1.2, 0.0, d_s);
        float halo = smoothstep(w_s * 5.0, 0.0, d_s) * 0.40 * (1.0 - ins);

        float layer = edge + fill * (1.0 - edge) + halo * (1.0 - edge) * (1.0 - ins);
        g = g + layer * (1.0 - g) * (1.0 - fi * 0.15);
    }

    g += exp(-r * r * 10.0) * 0.65;
    g *= breath();

    // r_sf varies with angle (seamless) — gives each lobe a hue offset
    vec3 col = arm_color(fract(r_sf * 0.6 + r * 0.20 - u_time * 0.05), g);
    // Softer outer fade — was eating ~44% alpha at the main body radius
    return vec4(col, g * u_opacity * smoothstep(3.0, 0.3, r)) * entrainmentModulation();
}
