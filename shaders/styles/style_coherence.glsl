// Style 27 — Coherence Mirror
// Visualizes the EEG state directly: fragments when frontal coherence drops
// (executive decoupling), binds when temporal theta coherence rises.
// The shader doesn't receive live EEG — it reads u_chaos as a proxy for
// fragmentation and u_tightness as a proxy for binding/depth.
// When chaos is low: unified spiral field, coherent motion.
// When chaos is high: the field fractures into independent shards that
// drift apart, each with its own phase, reassembling only at the core.
//
// Intended for deep trance phases where the visual should reflect the
// brain's own state back to it — a mirror, not a stimulus.

vec4 style_coherence(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // ── Fragmentation field ──────────────────────────────────────────────
    // Chaos drives how many fragments exist and how far they drift.
    // At chaos=0: one unified field. At chaos=1: up to 6 independent shards.
    float frag_count = 3.0 + u_chaos * 3.0;
    float frag_id    = floor(mod(angle / TWO_PI * frag_count + u_chaos * 2.0, frag_count));

    // Each fragment gets its own time offset and angular drift
    float frag_time  = u_time * (0.5 + frag_id * 0.12) + frag_id * 1.7;
    float frag_drift = u_chaos * sin(frag_id * 2.3 + u_time * 0.2) * 0.4;

    // ── Core spiral (unified, always present at center) ─────────────────
    float arm_per   = TWO_PI / float(u_count);
    float phase     = r * u_tightness - angle - frag_time * 0.6 + frag_drift;
    float arm_d     = mod(phase, arm_per) / arm_per;
    float arm_dist  = min(arm_d, 1.0 - arm_d);
    float width     = (0.055 + r * 0.04) * u_thickness * breath();

    float core = smoothstep(width * 1.3, 0.0, arm_dist);
    float glow = smoothstep(width * 4.0, 0.0, arm_dist) * 0.25;
    float spiral = core + glow * (1.0 - core);

    // ── Shard displacement ──────────────────────────────────────────────
    // At high chaos, each fragment shifts its coordinates independently.
    // The displacement is radial — shards slide outward from center.
    vec2 shard_offset = vec2(
        cos(frag_id * 1.3 + u_time * 0.15) * u_chaos * 0.12,
        sin(frag_id * 1.7 + u_time * 0.12) * u_chaos * 0.12
    );
    vec2 shard_p = p - shard_offset;
    float shard_r     = length(shard_p);
    float shard_angle = atan(shard_p.y, shard_p.x);

    // Shard has its own spiral phase — desynchronized from the core
    float shard_phase    = shard_r * u_tightness * 0.8 - shard_angle
                           - frag_time * 0.4 + frag_drift * 1.5;
    float shard_arm_d    = mod(shard_phase, arm_per) / arm_per;
    float shard_arm_dist = min(shard_arm_d, 1.0 - shard_arm_d);

    float shard_core = smoothstep(width * 1.1, 0.0, shard_arm_dist);
    float shard_glow = smoothstep(width * 3.5, 0.0, shard_arm_dist) * 0.2;
    float shard      = shard_core + shard_glow * (1.0 - shard_core);

    // ── Blend: unified at center, fragmented at edges ───────────────────
    // The coherence radius shrinks as chaos rises — the center stays whole
    // longer but the edges break apart first.
    float coherence_radius = max(0.15, 0.6 - u_chaos * 0.45);
    float unity = smoothstep(coherence_radius, coherence_radius * 0.3, r);

    // At center (unity=1): use core spiral. At edges (unity=0): use shards.
    float g = mix(shard, spiral, unity);

    // ── Binding layer (temporal theta analog) ────────────────────────────
    // Tightness controls a secondary voronoi lattice that emerges at depth.
    // More tightness = more binding = lattice connects the fragments.
    float vor_scale = 2.5 + u_tightness * 0.3;
    vec2  vor_p = p * vor_scale + vec2(u_time * 0.08);
    float vor   = voronoi_dist(vor_p);
    float lattice_edge = 1.0 - smoothstep(0.0, 0.2, vor);
    float lattice = lattice_edge * u_tightness * 0.008;

    g += lattice * (1.0 - g * 0.5);

    // ── Center singularity — the place where everything converges ────────
    float singularity = exp(-r * r * 4.0) * (0.4 + 0.3 * (1.0 - u_chaos));
    g += singularity * (1.0 - g * 0.5);

    // Fragment edge glow — visible seams where shards separate
    float frag_edge = abs(fract(angle / TWO_PI * frag_count + u_chaos) - 0.5) * 2.0;
    frag_edge = 1.0 - smoothstep(0.0, 0.15 * u_chaos, frag_edge);
    g += frag_edge * u_chaos * 0.15 * (1.0 - unity);

    g *= breath();

    // ── Color ────────────────────────────────────────────────────────────
    float arm_u = fract(phase / TWO_PI);
    vec3 col = arm_color(
        arm_u + u_time * 0.025 + r * 0.12,
        g
    );

    // Shard regions get hue-shifted — visual distinction between fragments
    float shard_hue = frag_id * 0.15;
    vec3 shard_col = arm_color(
        arm_u + shard_hue + u_time * 0.02,
        shard
    );
    col = mix(shard_col, col, unity);

    // Lattice gets warmer color — the binding is warm
    vec3 lattice_col = arm_color(vor * 0.5 + 0.3, lattice);
    col = mix(col, lattice_col, u_tightness * 0.002);

    // Singularity glow in base color — everything returns here
    col += u_base_color * singularity * 0.7;

    // ── Text overlay ────────────────────────────────────────────────────
    if (u_show_text == 1 && g > 0.2) {
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * u_base_color * 1.4, txt.a * g * 0.65);
    }

    float fade = smoothstep(0.0, 0.04, r);
    return vec4(col, g * u_opacity * fade) * entrainmentModulation();
}
