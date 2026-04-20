// Style 3 — Kaleidoscope
// Sector-folded interference with three wave layers, depth shimmer, and chromatic beat.
vec4 style_kaleidoscope(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float sectors      = float(u_count) * 2.0;
    float sector_angle = TWO_PI / sectors;
    float folded       = mod(angle + u_time * 0.3, sector_angle);
    if (folded > sector_angle * 0.5) folded = sector_angle - folded;

    // Three interleaved wave layers with different spatial frequencies
    float spiral1 = sin(r * u_tightness - u_time * 2.0 + folded * 3.0);
    float spiral2 = sin(r * u_tightness * 0.6 + u_time * 1.3 - folded * 5.0);
    float spiral3 = sin(r * u_tightness * 1.4 - u_time * 0.9 + folded * 7.0) * 0.35;
    float chaos_w = u_chaos * sin(r * 8.0 + u_time * 2.5) * 0.2;
    float pattern = (spiral1 + spiral2) * 0.5 + spiral3 + chaos_w;

    // Primary pattern — layered thresholds for depth
    float g = smoothstep(0.0, 0.4, pattern)
            + smoothstep(0.5, 0.9, pattern) * 0.5;

    // Fine concentric ring overlay — traveling outward through the kaleidoscope
    float rings = smoothstep(0.4, 0.0, abs(sin(r * 12.0 - u_time * 3.0))) * 0.15;

    // Radial spoke accent — highlights the fold lines
    float spoke = smoothstep(sector_angle * 0.02, 0.0, folded) * 0.12
                + smoothstep(sector_angle * 0.02, 0.0, sector_angle * 0.5 - folded) * 0.06;

    g = (g + rings + spoke) * breath();

    // Core convergence glow
    float core = exp(-r * r * 6.0) * 0.7;
    g += core;

    // Chromatic kaleidoscope — each sector gets a shifted hue
    float hue = r * 0.25 - u_time * 0.06 + folded * 2.0 + floor(angle / sector_angle) * 0.1;
    vec3 col = arm_color(hue, g);
    col += u_base_color * core * 0.5;

    return vec4(col, g * u_opacity * 1.0) * entrainmentModulation();
}
