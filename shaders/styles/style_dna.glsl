// Style 7 — DNA
vec4 style_dna(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float arm_per = TWO_PI / float(u_count);
    float w       = (0.04 + u_chaos * 0.02) * u_thickness * breath();

    float phase_a = r * u_tightness - angle - u_time * 2.0;
    float phase_b = r * u_tightness + angle + u_time * 2.0;
    float d_a = min(mod(phase_a,arm_per)/arm_per, 1.0-mod(phase_a,arm_per)/arm_per);
    float d_b = min(mod(phase_b,arm_per)/arm_per, 1.0-mod(phase_b,arm_per)/arm_per);
    float helix_a = smoothstep(w, 0.0, d_a);
    float helix_b = smoothstep(w, 0.0, d_b);
    float rung_d  = fract(r * u_tightness * 2.0 - u_time * 1.5);
    float rung    = smoothstep(0.15, 0.0, min(rung_d, 1.0-rung_d))
                  * smoothstep(0.0, 0.04, d_a + d_b) * 0.6;

    // phase_a/TWO_PI jumps by ±count (integer) at the seam → fract absorbs it.
    // phase_b/TWO_PI does the same. Both helices seamless with no angle term needed.
    vec3 col_a = arm_color(fract(phase_a / TWO_PI) + u_time*0.05,        helix_a * breath());
    vec3 col_b = arm_color(fract(phase_b / TWO_PI) + 0.5 + u_time*0.05,  helix_b * breath());
    vec3 col   = col_a + col_b + vec3(0.9,0.9,1.0) * rung * u_base_color;

    // Text on helix_a
    if (u_show_text == 1 && helix_a > 0.2) {
        float arm_u = fract(phase_a / TWO_PI);
        vec4  txt   = sample_text(arm_u, d_a / max(w, 0.001));
        col = mix(col, txt.rgb * 1.6, txt.a * helix_a * 0.8);
    }
    float fade = smoothstep(2.0, 0.05, r) * smoothstep(0.0, 0.06, r);
    return vec4(col, (helix_a + helix_b + rung) * u_opacity * fade);
}
