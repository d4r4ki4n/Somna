// Style 14 — Liminal
vec4 style_liminal(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Beat-phase structural breathing — warp deformation coupled to beat cycle
    float warp_breath = 0.7 + 0.3 * breath();

    // ── Layer 1: Domain-warped logarithmic spiral ─────────────────────────
    // Inigo Quilez nested domain warping: fbm(p + fbm(p + offset))
    float time_slow = u_time * 0.15;

    vec2 warp1 = vec2(
        fbm4(p * 2.0 + vec2(time_slow, 0.0)),
        fbm4(p * 2.0 + vec2(0.0, time_slow))
    );
    vec2 warp2 = vec2(
        fbm4(p * 2.0 + warp1 * 2.0 + vec2(1.7, 9.2) + time_slow * 0.8),
        fbm4(p * 2.0 + warp1 * 2.0 + vec2(8.3, 2.8) + time_slow * 0.6)
    );

    vec2 warped_p = p + u_chaos * warp2 * 0.4 * warp_breath;

    float wr     = length(warped_p);
    float wangle = atan(warped_p.y, warped_p.x);

    // Logarithmic spiral field on warped coordinates
    float log_r   = log(max(wr, 0.01));
    float phase   = log_r * u_tightness * 1.5 - wangle - u_time * 0.8;
    float arm_per = TWO_PI / float(u_count);
    float arm_d   = mod(phase, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);
    float arm_u    = fract(phase / TWO_PI);

    float width    = (0.04 + wr * 0.05) * u_thickness * breath();
    float arm_core = smoothstep(width * 1.3, 0.0, arm_dist);
    float arm_glow = smoothstep(width * 4.0, 0.0, arm_dist) * 0.3;
    float spiral   = arm_core + arm_glow * (1.0 - arm_core);

    // ── Layer 2: Voronoi lattice emergence (Kluver Form Constant III) ─────
    // Emerges as chaos increases — uses warped coordinates so it breathes
    // in structural harmony with the spiral.
    float vor_scale = 3.0 + u_tightness * 0.5;
    vec2  vor_p = warped_p * vor_scale + vec2(u_time * 0.1);
    float vor   = voronoi_dist(vor_p);

    float lattice_edge = 1.0 - smoothstep(0.0, 0.25, vor);
    float lattice_fill = smoothstep(0.0, 0.6, vor) * 0.15;
    // Quadratic fade-in: lattice invisible at low chaos, prominent at high
    float lattice = (lattice_edge * 0.7 + lattice_fill) * u_chaos * u_chaos;

    // ── Composite ─────────────────────────────────────────────────────────
    // Low chaos: pure spiral. High chaos: spiral + lattice overlay.
    // (1.0 - spiral * 0.5) prevents oversaturation where both layers meet.
    float g = spiral + lattice * (1.0 - spiral * 0.5);
    g *= breath();

    // Core convergence glow
    float core = exp(-r * r * 5.0) * 1.2;
    g += core * (1.0 - g * 0.5);

    // ── Color ─────────────────────────────────────────────────────────────
    // Warp field drives organic hue variation — visual coherence: the same
    // field that distorts geometry also colors the surface.
    float hue_warp = fbm4(p * 1.5 + vec2(u_time * 0.08)) * u_chaos;
    vec3 col = arm_color(
        arm_u + hue_warp * 0.3 + r * 0.15 + u_time * 0.03,
        g
    );

    // Lattice gets shifted hue — visual separation from spiral arms
    vec3 lattice_col = arm_color(
        vor * 0.5 + u_time * 0.02 + 0.5,
        lattice * breath()
    );
    col = mix(col, lattice_col, u_chaos * u_chaos * 0.4);

    // Core glow in base_color
    col += u_base_color * core * 0.6;

    // ── Text overlay ──────────────────────────────────────────────────────
    if (u_show_text == 1 && spiral > 0.15) {
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * u_base_color * 1.5, txt.a * spiral * 0.75);
    }

    float fade = smoothstep(3.0, 0.3, r) * smoothstep(0.0, 0.05, r);
    return vec4(col, g * u_opacity * fade) * entrainmentModulation();
}
