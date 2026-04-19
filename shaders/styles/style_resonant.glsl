// Style 15 — Resonant Standing-Wave Spiral
vec4 style_resonant(vec2 p) {
    float r      = length(p);
    float angle  = atan(p.y, p.x);
    // Standard Archimedean phase, angular coefficient = 1 for correct arm count
    float phase   = r * u_tightness * 1.8 - angle - u_time * 1.1;
    float arm_per = TWO_PI / float(u_count);

    // Golden-ratio harmonic series — irrational frequencies never repeat
    float wave = 0.0;
    for (int i = 1; i <= 5; i++) {
        float k = float(i) * PHI;
        wave += sin(phase * k) * pow(0.7, float(i));
        wave += sin(phase * k * 1.5 + u_beat_phase * TWO_PI) * 0.28 * pow(0.75, float(i));
    }
    // Raw amplitude peaks ~±3.4; normalise to [0, 1]
    wave = clamp(wave * 0.18 + 0.5, 0.0, 1.0);

    // Crystalline nodes at constructive interference — sharpened with pow
    float nodes = pow(abs(sin(phase * 3.0 * PHI)), 4.0);

    // Arm field perturbed by wave — shifts arm positions by up to 1.5 periods
    float arm_d    = mod(phase + wave * arm_per * 1.5, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);

    float width = (0.035 + r * 0.055) * u_thickness * breath();
    // Wave-modulated edges: pinch/widen at node crests
    width = max(width * 0.25, width * (1.0 + 0.55 * sin(wave * TWO_PI * 2.0)));

    float core = smoothstep(width * 1.1, 0.0, arm_dist);
    float glow = smoothstep(width * 4.5, 0.0, arm_dist) * 0.40;
    float arm  = core + glow * (1.0 - core);

    float beat_mod = 1.8 + sin(u_beat_phase * TWO_PI * 3.0) * 0.7;
    float flare    = nodes * core * beat_mod;

    float hue = fract(phase / TWO_PI) + wave * 0.4;
    float bri = clamp((arm + flare * 0.6) * breath(), 0.0, 2.0);
    vec3  col = arm_color(hue, bri);
    col += u_base_color * flare * 1.8;

    float alpha = clamp(arm + flare * 0.5, 0.0, 1.0) * u_opacity
                * smoothstep(3.0, 0.3, r) * smoothstep(0.0, 0.06, r);

    if (u_show_text == 1 && arm > 0.22) {
        float arm_u = fract(phase / TWO_PI);
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * u_base_color * 2.0, txt.a * arm);
    }
    return vec4(col, alpha) * entrainmentModulation();
}
