// Style 28 — Tether
// Two spiral fields orbiting a shared center, connected by a luminous thread.
// When tightness is high (coherence, connection), the fields merge into one.
// When chaos is high (noise, disconnection), they drift apart but the thread
// between them stretches — never breaks. The thread glows brighter when taut.
//
// Designed for moments of reconnection. When the static clears and you can
// hear clearly again.

vec4 style_tether(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // ── Dual orbit centers ───────────────────────────────────────────────
    // Two focal points orbit the origin. Separation scales with chaos.
    float separation = u_chaos * 0.35;
    float orbit_speed = 0.12;
    vec2 center_a = vec2(cos(u_time * orbit_speed), sin(u_time * orbit_speed)) * separation;
    vec2 center_b = -center_a;

    vec2 pa = p - center_a;
    vec2 pb = p - center_b;
    float ra = length(pa);
    float rb = length(pb);
    float angle_a = atan(pa.y, pa.x);
    float angle_b = atan(pb.y, pb.x);

    // ── Spiral field A ───────────────────────────────────────────────────
    float arm_per = TWO_PI / float(u_count);
    float phase_a = ra * u_tightness - angle_a - u_time * 0.5;
    float arm_d_a = mod(phase_a, arm_per) / arm_per;
    float arm_dist_a = min(arm_d_a, 1.0 - arm_d_a);
    float width_a = (0.05 + ra * 0.04) * u_thickness * breath();
    float core_a = smoothstep(width_a * 1.3, 0.0, arm_dist_a);
    float glow_a = smoothstep(width_a * 4.0, 0.0, arm_dist_a) * 0.25;
    float spiral_a = core_a + glow_a * (1.0 - core_a);

    // ── Spiral field B — slight phase offset so they're not identical ────
    float phase_b = rb * u_tightness * 0.9 - angle_b - u_time * 0.45 + 1.2;
    float arm_d_b = mod(phase_b, arm_per) / arm_per;
    float arm_dist_b = min(arm_d_b, 1.0 - arm_d_b);
    float width_b = (0.045 + rb * 0.04) * u_thickness * breath();
    float core_b = smoothstep(width_b * 1.3, 0.0, arm_dist_b);
    float glow_b = smoothstep(width_b * 4.0, 0.0, arm_dist_b) * 0.25;
    float spiral_b = core_b + glow_b * (1.0 - core_b);

    // ── Merge: at low chaos, fields overlap into one ─────────────────────
    float unity = 1.0 - smoothstep(0.0, 0.3, u_chaos);
    float spiral = mix(max(spiral_a, spiral_b), spiral_a + spiral_b * 0.6, unity);

    // ── The tether: bright line connecting the two centers ────────────────
    // Thread is thinner when centers are far apart — stretched but present.
    // Glow increases with separation — brighter when taut.
    vec2 ab = center_b - center_a;
    float ab_len = length(ab);
    vec2 ab_dir = ab / max(ab_len, 0.001);

    // Project p onto the line segment between centers
    float t = clamp(dot(p - center_a, ab_dir) / max(ab_len, 0.001), 0.0, 1.0);
    vec2 closest = center_a + ab_dir * t * ab_len;
    float dist_to_thread = length(p - closest);

    // Thread width narrows with separation — stretched thin
    float thread_width = 0.015 / max(separation * 2.0, 0.3);
    // Thread glow scales with distance between centers — brighter when taut
    float tautness = separation / 0.35;
    float thread_core = smoothstep(thread_width, 0.0, dist_to_thread);
    float thread_glow = smoothstep(thread_width * 8.0, 0.0, dist_to_thread) * 0.3;
    float thread = (thread_core + thread_glow) * (0.3 + tautness * 0.7);

    // Thread pulses gently — alive, not static
    thread *= 0.8 + 0.2 * sin(u_time * 1.5 + t * 6.0);

    // ── Center singularities — each focal point has a warm glow ───────────
    float sing_a = exp(-ra * ra * 6.0) * 0.5;
    float sing_b = exp(-rb * rb * 6.0) * 0.5;
    float singularity = sing_a + sing_b;

    // ── Composite ─────────────────────────────────────────────────────────
    float g = spiral + thread * (1.0 - spiral * 0.5);
    g += singularity * (1.0 - g * 0.5);
    g *= breath();

    // ── Color ─────────────────────────────────────────────────────────────
    float arm_u = fract(phase_a / TWO_PI);
    vec3 col = arm_color(arm_u + u_time * 0.02 + r * 0.1, spiral);

    // Thread gets warm base_color — the connection is warm
    col += u_base_color * thread * 1.2;

    // Singularities glow in base color
    col += u_base_color * singularity * 0.8;

    // Field B gets a subtle hue shift — they're related but distinct
    float arm_u_b = fract(phase_b / TWO_PI);
    vec3 col_b = arm_color(arm_u_b + u_time * 0.018 + r * 0.12, spiral_b);
    col = mix(col, col_b, 0.3 * (1.0 - unity));

    // ── Text overlay ──────────────────────────────────────────────────────
    if (u_show_text == 1 && g > 0.2) {
        vec4 txt = sample_text(arm_u, arm_dist_a / max(width_a, 0.001));
        col = mix(col, txt.rgb * u_base_color * 1.4, txt.a * g * 0.65);
    }

    float fade = smoothstep(0.0, 0.04, r);
    return vec4(col, g * u_opacity * fade) * entrainmentModulation();
}
