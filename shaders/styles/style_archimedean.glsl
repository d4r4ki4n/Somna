// Style 2 — Archimedean
vec4 style_archimedean(vec2 p) {
    vec3  field  = archimedean_field(p, u_time * 2.2);
    float arm_dist = field.x;
    float arm_u    = field.y;
    float width    = field.z;
    float arm_core = smoothstep(width * 1.2, 0.0, arm_dist);
    float arm_glow = smoothstep(width * 3.8, 0.0, arm_dist) * 0.25;
    float arm      = arm_core + arm_glow * (1.0 - arm_core);
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float pulse = 0.75 + 0.25 * sin(r * 3.0 - u_time * 1.5);
    vec3  col   = arm_color(r * 0.3 + u_time * 0.07, arm * pulse * breath());
    float fade  = 1.0 * smoothstep(0.0, 0.06, r);
    // Text overlay on arms
    if (u_show_text == 1 && arm > 0.15) {
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * 1.8, txt.a * arm * 0.85);
    }
    return vec4(col, arm * u_opacity * fade) * entrainmentModulation();
}
