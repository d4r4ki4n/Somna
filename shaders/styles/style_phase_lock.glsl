// Style 29 — Phase Lock
// Two spiral fields at different frequencies, coupled by Kuramoto dynamics.
// When coupling (tightness) exceeds the frequency gap (chaos), the fields
// snap into synchronization in a single frame. The connector between them
// condenses from noise into a stable luminous channel.
//
// The snap is the visual event: not a gradual merge but a discontinuous
// phase transition, like metronomes on a shared surface finding unison.
// Before lock: two fields drifting through each other, different hues.
// After lock: unified field, same color, bright thread connecting them.
//
// Parameters:
//   u_tightness → coupling strength K
//   u_chaos     → initial frequency offset (how far apart the fields start)
//   u_count     → arms per field
//   u_thickness → arm width

vec4 style_phase_lock(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // ── Kuramoto coupling ────────────────────────────────────────────────
    float freq_A = 1.0;
    float freq_B = 1.0 + 0.6 * u_chaos;
    float delta_omega = abs(freq_B - freq_A);
    float K = u_tightness;

    // Hard step: locked or not. Phase transitions are discontinuous.
    float locked = step(delta_omega + 0.001, K);

    // Drift rate when unlocked: residual frequency difference
    float drift_rate = max(0.0, delta_omega - K);

    // Phase A: evolves at natural frequency
    float phase_A = freq_A * u_time;

    // Phase B: natural frequency when unlocked, matched to A when locked
    float phase_B_free = freq_B * u_time;
    float phase_B_lock = phase_A + 0.4;
    float phase_B = mix(phase_B_free, phase_B_lock, locked);

    // Phase difference (for connector visualization)
    float delta_phase = phase_B - phase_A;

    // ── Field A ──────────────────────────────────────────────────────────
    float arm_per = TWO_PI / float(u_count);

    // Spiral geometry — separate tightness for visual winding vs coupling K
    float spiral_K = 1.0 + K * 0.5;
    float field_phase_A = r * spiral_K - angle - phase_A * 0.5;
    float arm_d_A   = mod(field_phase_A, arm_per) / arm_per;
    float arm_dist_A = min(arm_d_A, 1.0 - arm_d_A);
    float width_A   = (0.05 + r * 0.04) * u_thickness * breath();
    float core_A    = smoothstep(width_A * 1.3, 0.0, arm_dist_A);
    float glow_A    = smoothstep(width_A * 4.0, 0.0, arm_dist_A) * 0.25;
    float spiral_A  = core_A + glow_A * (1.0 - core_A);

    // ── Field B — offset center, drifts when unlocked ────────────────────
    float center_offset = (1.0 - locked) * u_chaos * 0.2;
    vec2  center_B = vec2(cos(u_time * 0.15) * center_offset,
                          sin(u_time * 0.15) * center_offset);
    vec2  pb      = p - center_B;
    float rb      = length(pb);
    float angle_b = atan(pb.y, pb.x);

    float field_phase_B = rb * spiral_K * 0.95 - angle_b - phase_B * 0.5 + 0.8;
    float arm_d_B    = mod(field_phase_B, arm_per) / arm_per;
    float arm_dist_B = min(arm_d_B, 1.0 - arm_d_B);
    float width_B    = (0.045 + rb * 0.04) * u_thickness * breath();
    float core_B     = smoothstep(width_B * 1.3, 0.0, arm_dist_B);
    float glow_B     = smoothstep(width_B * 4.0, 0.0, arm_dist_B) * 0.25;
    float spiral_B   = core_B + glow_B * (1.0 - core_B);

    // ── Connector: phase-difference visualization ────────────────────────
    // Before lock: phase difference grows → connector is noisy and flickers
    // After lock: phase difference is constant → connector stabilizes, glows
    float connector_raw = sin(delta_phase * 3.0) * 0.5 + 0.5;

    // Add spatial noise when drifting — the connector isn't formed yet
    float noise_mod = snoise(vec2(delta_phase * 0.5, r * 4.0 + u_time * 0.3));
    float connector_drift = connector_raw * (0.3 + 0.7 * max(0.0, noise_mod));

    // Locked connector: clean, bright, positionally stable
    float connector_lock = connector_raw * 1.2;

    // The connector only appears where both fields overlap
    float overlap = min(spiral_A, spiral_B);
    float connector = mix(connector_drift, connector_lock, locked) * overlap;

    // ── Composite ────────────────────────────────────────────────────────
    float g = max(spiral_A, spiral_B);

    // When locked, fields merge — B adds to A rather than competing
    float merge_factor = locked * 0.4;
    g = g + spiral_B * merge_factor * (1.0 - g);

    // Connector contributes more when locked
    g += connector * mix(0.15, 0.35, locked);

    g *= breath();

    // Center singularity — brighter when locked (both fields converge)
    float singularity = exp(-r * r * 5.0) * (0.3 + locked * 0.25);
    g += singularity * (1.0 - g * 0.5);

    // ── Color ────────────────────────────────────────────────────────────
    float arm_u_A = fract(field_phase_A / TWO_PI);
    float arm_u_B = fract(field_phase_B / TWO_PI);

    // Hue offset between fields — shrinks to zero at lock
    float hue_offset = (1.0 - locked) * u_chaos * 0.3;

    vec3 col_A = arm_color(arm_u_A + u_time * 0.02 + r * 0.1, spiral_A);
    vec3 col_B = arm_color(arm_u_B + hue_offset + u_time * 0.018 + r * 0.12, spiral_B);

    // Merge colors — at lock they converge to A's hue
    vec3 col = mix(col_B, col_A, 0.5 + locked * 0.45);

    // Connector glow in warm base_color — only prominent when locked
    col += u_base_color * connector * locked * 1.5;

    // Singularity glow
    col += u_base_color * singularity * 0.6;

    // ── Text overlay ─────────────────────────────────────────────────────
    if (u_show_text == 1 && g > 0.2) {
        vec4 txt = sample_text(arm_u_A, arm_dist_A / max(width_A, 0.001));
        col = mix(col, txt.rgb * u_base_color * 1.4, txt.a * g * 0.65);
    }

    float fade = smoothstep(0.0, 0.04, r);
    return vec4(col, g * u_opacity * fade) * entrainmentModulation();
}
