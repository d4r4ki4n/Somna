// Style 21 — Sacred Geometry
// Centered Seed of Life core with radiating triangular sectors,
// golden-ratio concentric rings, and rotating star geometry.
vec4 style_sacred_geometry(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float n     = float(u_count);
    float tight = u_tightness * 0.5;

    // ── Seed of Life: 7 circles (1 center + 6 petals) ──────────────────
    float scale = 1.2 + tight * 0.15;
    float breathe_s = 1.0 + sin(u_time * 0.3) * 0.06;
    float petal_r = scale * breathe_s;
    float edge_w = (0.03 + u_chaos * 0.015) * u_thickness * 0.4;

    float g = 0.0;

    // Center circle
    float d0 = abs(length(p) - petal_r * 0.5);
    g = max(g, smoothstep(edge_w, 0.0, d0));

    // 6 petal circles evenly spaced
    for (int k = 0; k < 6; k++) {
        float fk = float(k);
        float a = fk * TWO_PI / 6.0 + u_time * 0.1;
        vec2 center = vec2(cos(a), sin(a)) * petal_r * 0.5;
        float d = abs(length(p - center) - petal_r * 0.5);
        g = max(g, smoothstep(edge_w, 0.0, d));
    }

    // Glow around all circle edges
    float seed_glow = 0.0;
    {
        float d0g = abs(length(p) - petal_r * 0.5);
        seed_glow = exp(-d0g * d0g * 40.0) * 0.2;
        for (int k = 0; k < 6; k++) {
            float fk = float(k);
            float a = fk * TWO_PI / 6.0 + u_time * 0.1;
            vec2 center = vec2(cos(a), sin(a)) * petal_r * 0.5;
            float dg = abs(length(p - center) - petal_r * 0.5);
            seed_glow += exp(-dg * dg * 40.0) * 0.15;
        }
    }

    // ── Radiating triangular sectors ────────────────────────────────────
    // count triangular "rays" from center outward
    float sector_angle = TWO_PI / n;
    // Integer coefficient — atan seam absorbed
    float folded_a = mod(angle + sector_angle * 0.5, sector_angle) - sector_angle * 0.5;
    float abs_folded = abs(folded_a);

    // Ray edges — two edges per sector, distance from each edge line
    float ray_w = edge_w * 0.8;
    float ray_d = abs_folded * r;
    float ray_edge = smoothstep(ray_w, 0.0, ray_d);

    // Ray brightness fades with distance from center
    float ray_fade = smoothstep(0.0, 0.1, r) * exp(-r * r * 1.5);
    float rays = ray_edge * ray_fade;

    // Phase wave traveling outward along rays
    float ray_wave = sin(r * tight * 8.0 - u_time * 2.0) * 0.5 + 0.5;
    rays *= 0.5 + ray_wave * 0.5;

    // ── Golden-ratio concentric rings ───────────────────────────────────
    float phi = 1.618033988749895;
    float ring_g = 0.0;
    float ring_pulse = sin(u_time * 1.5) * 0.1;
    for (int i = 0; i < 8; i++) {
        float fi = float(i);
        float ring_r = pow(phi, fi * 0.35 - 1.0) * scale * 1.5 + ring_pulse * fi * 0.03;
        float rd = abs(r - ring_r);
        float rw = edge_w * (0.6 + fi * 0.05);
        ring_g = max(ring_g, smoothstep(rw, 0.0, rd)
                     * exp(-fi * 0.12));
    }

    // ── Rotating inner star ─────────────────────────────────────────────
    float star_rot = u_time * 0.25;
    float star_a = angle - star_rot;
    float star_n = max(n, 2.0);
    // Integer angular coefficient: round(star_n)
    float star_folded = mod(star_a + PI / star_n, TWO_PI / star_n) - PI / star_n;
    float star_arm = cos(star_folded * star_n) * 0.5 + 0.5;
    float star_r = 0.15 + tight * 0.08;
    float star_shape = smoothstep(star_r, star_r * 0.3, r * (1.0 + star_arm * 2.0));
    float star = star_shape * smoothstep(0.0, 0.05, r) * 0.4;

    // ── Luminous nodes at ring-ray intersections ────────────────────────
    float node_g = 0.0;
    for (int i = 1; i <= 5; i++) {
        float fi = float(i);
        float ring_r = pow(phi, fi * 0.35 - 1.0) * scale * 1.5;
        // Distance to this ring along the ray direction
        float dr = abs(r - ring_r);
        // Angular proximity to ray edges
        float da = min(abs_folded, sector_angle - abs_folded);
        float node_d = sqrt(dr * dr + da * da * r * r);
        float pulse = 0.6 + 0.4 * sin(u_time * 2.5 + fi * 1.3);
        node_g = max(node_g, exp(-node_d * node_d * 60.0) * pulse);
    }

    // ── Composite ──────────────────────────────────────────────────────
    float total = g + seed_glow + rays + ring_g * 0.5 + star + node_g * 0.6;
    total *= breath();
    total += exp(-r * r * 6.0) * 0.35;

    // Color — warm gold core transitioning to cool outer hues
    float hue_base = fract(r * 0.15 - u_time * 0.03 + total * 0.2);
    vec3 col = arm_color(hue_base, total);
    col += vec3(1.0, 0.9, 0.6) * node_g * 0.3;
    col += vec3(0.9, 0.8, 1.0) * star * 0.3;

    float alpha = total * u_opacity * smoothstep(0.0, 0.03, r);
    return vec4(col, alpha) * entrainmentModulation();
}
