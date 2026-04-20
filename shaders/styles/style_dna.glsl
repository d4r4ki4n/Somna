// Style 7 — DNA
// Dual helix with luminous rungs, backbone glow, and pulsing nodes.
vec4 style_dna(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float arm_per = TWO_PI / float(u_count);
    float w       = (0.04 + u_chaos * 0.02) * u_thickness * breath();
    float n       = float(u_count);

    float phase_a = r * u_tightness - angle - u_time * 2.0;
    float phase_b = r * u_tightness + angle + u_time * 2.0;
    float d_a = min(mod(phase_a,arm_per)/arm_per, 1.0-mod(phase_a,arm_per)/arm_per);
    float d_b = min(mod(phase_b,arm_per)/arm_per, 1.0-mod(phase_b,arm_per)/arm_per);
    float helix_a = smoothstep(w, 0.0, d_a);
    float helix_b = smoothstep(w, 0.0, d_b);

    // Luminous rungs between helices
    float rung_d  = fract(r * u_tightness * 2.0 - u_time * 1.5);
    float rung_sharp = smoothstep(0.12, 0.0, min(rung_d, 1.0-rung_d));
    float rung    = rung_sharp * smoothstep(0.0, 0.04, d_a + d_b) * 0.7;

    // Pulsing nodes at rung-helix intersections
    float node_pulse = 0.6 + 0.4 * sin(u_time * 3.0 + r * 5.0);
    float node_a = rung_sharp * helix_a * node_pulse;
    float node_b = rung_sharp * helix_b * node_pulse;

    // Backbone glow — broad luminous envelope following each helix
    float glow_w = w * 4.0;
    float glow_a = smoothstep(glow_w, 0.0, d_a) * 0.25;
    float glow_b = smoothstep(glow_w, 0.0, d_b) * 0.25;

    // Secondary thinner helix at offset phase — depth layer
    float phase_c = r * u_tightness * 1.5 - angle * 1.5 - u_time * 1.6;
    float arm_per_c = TWO_PI / max(round(n * 1.5), 1.0);
    float d_c = min(mod(phase_c, arm_per_c) / arm_per_c,
                    1.0 - mod(phase_c, arm_per_c) / arm_per_c);
    float helix_c = smoothstep(w * 0.4, 0.0, d_c) * 0.3;

    vec3 col_a = arm_color(fract(phase_a / TWO_PI) + u_time * 0.05, helix_a * breath());
    vec3 col_b = arm_color(fract(phase_b / TWO_PI) + 0.5 + u_time * 0.05, helix_b * breath());
    vec3 col   = col_a + col_b;

    // Rung color — bright neutral
    col += vec3(0.9, 0.9, 1.0) * rung * u_base_color;

    // Node highlights
    col += vec3(1.0, 0.95, 0.8) * (node_a + node_b) * 0.5;

    // Backbone glow tinted by base color
    col += u_base_color * (glow_a + glow_b) * 0.4;

    // Secondary helix — subtle depth layer
    col += arm_color(fract(phase_c / TWO_PI) + u_time * 0.03, helix_c * breath()) * 0.4;

    // Text on helix_a
    if (u_show_text == 1 && helix_a > 0.2) {
        float arm_u = fract(phase_a / TWO_PI);
        vec4  txt   = sample_text(arm_u, d_a / max(w, 0.001));
        col = mix(col, txt.rgb * 1.6, txt.a * helix_a * 0.8);
    }

    float fade = smoothstep(0.0, 0.06, r);
    float alpha = (helix_a + helix_b + rung + node_a * 0.3 + node_b * 0.3
                 + glow_a + glow_b + helix_c) * u_opacity * fade;
    return vec4(col, alpha) * entrainmentModulation();
}
