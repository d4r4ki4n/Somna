// Style 26 — Descent
// Concentric rings collapsing inward with warm glow.
// Designed for the depth phase — the feeling of being pulled under.
vec4 style_descent(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Radial noise for organic distortion
    float n = snoise(vec2(angle * 2.0 + u_time * 0.15, r * 3.0)) * u_chaos * 0.4;

    // Rings moving inward — negative time direction pulls toward center
    float ring_phase = (r * u_tightness * 2.5 - u_time * 1.8 + n);
    float ring_per   = TWO_PI / float(u_count);
    float ring_d     = mod(ring_phase, ring_per) / ring_per;
    float ring_dist  = min(ring_d, 1.0 - ring_d);

    // Width widens toward center — the pull gets stronger as you go deeper
    float width = clamp((0.08 + (1.0 - smoothstep(0.0, 0.8, r)) * 0.06)
                        * u_thickness * breath(), 0.01, 0.4);

    // Core + glow blend
    float ring_core = smoothstep(width * 1.3, 0.0, ring_dist);
    float ring_glow = smoothstep(width * 4.0, 0.0, ring_dist) * 0.28;
    float ring      = ring_core + ring_glow * (1.0 - ring_core);

    // Angular variation — rings aren't perfect circles, they breathe with angle
    float angular = 0.5 + 0.5 * sin(angle * float(u_count) + u_time * 0.3);
    ring *= mix(0.7, 1.0, angular);

    // Center glow — the place everything falls toward
    float pull = exp(-r * r * 3.5) * 1.8;

    // Radial gradient — darker at edges, warmer toward center
    float depth_fade = smoothstep(1.2, 0.15, r);

    float ring_u = fract(ring_phase / TWO_PI);
    vec3 col = arm_color(ring_u + u_time * 0.03 + r * 0.15,
                         ring * depth_fade * breath());

    // Warm center glow using base color
    col += u_base_color * pull * 0.9;

    // Faint outer haze so the edges don't cut hard
    float haze = smoothstep(1.1, 0.5, r) * 0.12 * (0.5 + 0.5 * sin(r * 8.0 - u_time));
    col += u_base_color * haze;

    float alpha = min(1.0, ring * depth_fade + pull * 0.5 + haze * 0.3) * u_opacity;

    // Text overlay on rings
    if (u_show_text == 1 && ring > 0.25) {
        vec4 txt = sample_text(ring_u, ring_dist / max(width, 0.001));
        col = mix(col, txt.rgb * u_base_color * 1.5, txt.a * 0.6);
    }

    return vec4(col, alpha) * entrainmentModulation();
}
