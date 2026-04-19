// Style 1 — Galaxy Arms
vec4 style_galaxy(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float log_r = log(max(r, 0.01));
    // k must be an integer so the atan seam (phase jump = 2π*k) is an exact
    // multiple of arm_per (= 2π/count), keeping arms continuous at angle=±π.
    float k     = round(float(u_count) * 0.5);
    float phase = log_r * u_tightness - angle * k
                  - u_time * 1.1
                  + u_chaos * sin(r * 5.0 + u_time);
    float arm_per  = TWO_PI / float(u_count);
    float arm_d    = mod(phase, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);
    float arm_u    = fract(phase / TWO_PI);
    float width    = (0.04 + r * 0.06) * u_thickness * breath();
    // Blend core + glow so they share the same pixel budget — no hard inner ring.
    float arm_core = smoothstep(width * 1.2, 0.0, arm_dist);
    float arm_glow = smoothstep(width * 3.5, 0.0, arm_dist) * 0.35;
    float arm      = arm_core + arm_glow * (1.0 - arm_core);
    // Width-proportional haze so it doesn't create a fixed stripe at large arm sizes
    float haze     = smoothstep(width * 5.0, 0.0, arm_dist) * 0.28 * smoothstep(0.05, 0.5, r);
    float core_glow = exp(-r * r * 6.0) * 2.0;
    // arm_u follows the log-spiral arm phase — seamless because phase jumps by
    // 2π*k (k integer) at the seam, which fract(phase/TWO_PI) fully absorbs.
    vec3 col = arm_color(arm_u + u_time * 0.04 + r * 0.2,
                         (arm + haze) * breath());
    col += vec3(0.9, 0.95, 1.0) * core_glow * u_base_color;
    float alpha = min(1.0, arm + haze + core_glow * 0.5) * u_opacity
                * 1.0;
    // Text overlay
    if (u_show_text == 1 && arm > 0.2) {
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * u_base_color * 1.5, txt.a * 0.7);
    }
    return vec4(col, alpha) * entrainmentModulation();
}
