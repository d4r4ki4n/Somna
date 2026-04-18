// Style 5 — Electric
vec4 style_electric(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float noise = 0.0, freq = 1.0, amp = 1.0;
    for (int i = 0; i < 5; i++) {
        noise += sin(r * freq * 7.0 + angle * freq * 2.0
                     + u_time * (1.5 + freq * 0.3)) * amp;
        freq *= 2.0; amp *= 0.5;  // integer doubling keeps angle*freq*2 seamless
    }
    noise *= u_chaos * 0.5 + 0.1;
    float phase    = r * u_tightness - angle - u_time * 2.5 + noise;
    float arm_per  = TWO_PI / float(u_count);
    float arm_d    = mod(phase, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);
    float width    = (0.025 + abs(noise) * 0.03) * u_thickness * breath();
    float arm   = smoothstep(width * 1.4, 0.0, arm_dist);
    // Spark only fills the gap beyond the core — no double-bright stripe
    float spark = smoothstep(width * 4.5, 0.0, arm_dist) * 0.2 * (1.0 - arm);
    // Electric: always white-blue, base_color tints the core
    vec3 col = mix(u_base_color, vec3(0.8, 0.9, 1.0), arm)
             + vec3(0.9, 0.9, 1.0) * spark;
    col *= 1.0 + arm * 1.5 * breath();
    return vec4(col, (arm + spark) * u_opacity * smoothstep(2.0, 0.04, r));
}
