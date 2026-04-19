// Style 16 — Curl-Flow Nebula Spiral
vec4 style_nebula(vec2 p) {
    float t = u_time * 0.6;

    // Curl advection — displaces the sample point in an incompressible field
    vec2 flow   = curl_noise(p * (1.8 + u_chaos), t) * 0.55;
    vec2 warped = p + flow;

    float r      = length(warped);
    float angle  = atan(warped.y, warped.x);
    float log_r  = log(max(r, 0.02));
    // Standard log-spiral phase (coefficient 1 on angle for correct arm count)
    float phase   = log_r * u_tightness * 1.65 - angle - t * 0.9;
    float arm_per = TWO_PI / float(u_count);

    // Low-frequency organic perturbation following the flow field
    float organic = fbm4(warped * 2.0 + vec2(t * 0.13, 0.0)) * u_chaos;
    // Scale by arm_per so perturbation is count-independent (max ~±1.5 periods)
    float arm_d    = mod(phase + organic * arm_per * 1.5, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);

    float width = (0.028 + r * 0.070) * u_thickness * breath();
    // Organic field melts edges; guard against zero width
    width = max(width * 0.15, width * (1.0 + organic * 0.85));

    float core = smoothstep(width * 1.15, 0.0, arm_dist);
    float glow = smoothstep(width * 5.0, 0.0, arm_dist) * 0.35;
    float arm  = core + glow * (1.0 - core);

    // Nebula density: fBm cloud advected by the same curl field
    float nebula = fbm4(warped * 3.8 + flow * 6.0) * 0.5 + 0.5;
    nebula = pow(clamp(nebula, 0.0, 1.0), 2.0) * (1.0 - smoothstep(0.0, 1.2, r));

    float total = clamp(arm + nebula * (1.0 - arm * 0.55), 0.0, 1.2);

    // Hue follows flow direction — same field that warps geometry colors it
    float hue_flow = fract(angle * 0.8 + length(flow) * 3.0);
    vec3  col = arm_color(hue_flow + t * 0.04, total * breath() * 1.1);
    col += u_base_color * exp(-r * r * 5.5) * 1.8;

    float alpha = clamp(total, 0.0, 1.0) * u_opacity * 1.0;

    if (u_show_text == 1 && arm > 0.18) {
        float arm_u = fract(phase / TWO_PI);
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * 2.2, txt.a * arm * 0.8);
    }
    return vec4(col, alpha) * entrainmentModulation();
}
