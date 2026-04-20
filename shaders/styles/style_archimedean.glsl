// Style 2 — Archimedean
// Classic spiral arms with layered pulse, radial shimmer, and chromatic bloom.
vec4 style_archimedean(vec2 p) {
    vec3  field  = archimedean_field(p, u_time * 2.2);
    float arm_dist = field.x;
    float arm_u    = field.y;
    float width    = field.z;

    float arm_core = smoothstep(width * 1.2, 0.0, arm_dist);
    float arm_glow = smoothstep(width * 4.5, 0.0, arm_dist) * 0.50;
    float arm      = arm_core + arm_glow * (1.0 - arm_core);

    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Multi-frequency pulse — fundamental + two harmonics for depth
    float pulse = 0.55
                + 0.30 * sin(r * 3.0 - u_time * 1.5)
                + 0.15 * sin(r * 7.0 - u_time * 2.8 + angle * 2.0);

    // Radial shimmer — fine concentric ripple traveling outward
    float shimmer = exp(-arm_dist * arm_dist * 800.0)
                  * sin(r * 20.0 - u_time * 4.0) * 0.12;

    // Secondary spiral layer — rotated offset for visual complexity
    vec3  field2  = archimedean_field(p, u_time * 1.4 + 1.5);
    float arm2_dist = field2.x;
    float arm2 = smoothstep(width * 3.0, 0.0, arm2_dist) * 0.20;

    float g = (arm * pulse + arm2 + shimmer) * breath();

    // Convergence core bloom
    float core = exp(-r * r * 5.0) * 1.2;
    g += core;

    vec3 col = arm_color(r * 0.3 + u_time * 0.07, g);
    col += u_base_color * core * 0.7;

    // Text overlay
    if (u_show_text == 1 && arm > 0.15) {
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * 1.8, txt.a * arm * 0.85);
    }

    float fade = smoothstep(0.0, 0.06, r);
    return vec4(col, g * u_opacity * fade) * entrainmentModulation();
}
