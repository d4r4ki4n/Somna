// Style 25 — Neuro Vortex
// Based on "Neuro-Adaptive Hypnosis" by TripZilla (Shadertoy wcBGW3)
// Adapted: uses our uniforms, arm_color, breath(), entrainment system
// Key technique: asymmetric time shifts + peripheral desync for entrainment
vec4 style_neuro_vortex(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Breath-synced pulse (our breath() already tracks beat_phase)
    float breathPulse = breath();

    // Peripheral motion desync: outer regions "drag behind" time
    // Creates post-entrainment hallucination effect
    float periphDesync = sin(r * 12.0 - u_time * 0.02 * u_chaos * 50.0) * 0.4;

    // Asymmetric time shifts — different radial zones move at different speeds
    float asyncShift = sin(u_time * 0.45 + r * 6.0) * 1.3;

    // Depth warp with entrainment-scaled distortion
    float distortIntensity = 3.0 + u_tightness;
    float warp = pow(r * distortIntensity + asyncShift, 1.5) * 50.0;

    // Spiral arms — integer angular coefficient for seamless wrap
    float spirals = float(u_count) * 2.0;
    float spiralTwist = mod(
        angle * spirals + warp - u_time * 0.85 * breathPulse,
        TWO_PI
    );

    // Strobe layer — subtle brightness modulation at entrainment frequency
    // Uses beat_phase for synchronization with audio
    float strobe = 0.7 + 0.3 * (sin(u_entrainment_phase * TWO_PI) * 0.5 + 0.5);

    // Main pattern: cosine spiral with less radial interference
    float comp = cos(spiralTwist) * strobe
               - sin(r * 25.0) * 0.15
               + periphDesync;

    // Power curve for contrast — lower sharp = smoother, more vortex-like
    float sharp = 3.0 + u_thickness * 0.3;
    float g = pow((comp + 1.0) / 2.0, sharp) * breath();

    // Fade center to avoid singularity
    float fade = smoothstep(0.0, 0.08, r);

    // Color: slight RGB channel offset for chromatic aberration feel
    // Each channel samples at slightly different radial position
    float r_shift = 0.02;
    float g_r = pow((cos(spiralTwist) * strobe + 1.0) / 2.0, sharp);
    float g_g = pow((cos(spiralTwist * 1.01 + r_shift * 20.0) * strobe + 1.0) / 2.0, sharp);
    float g_b = pow((cos(spiralTwist * 0.99 - r_shift * 20.0) * strobe + 1.0) / 2.0, sharp);

    vec3 col;
    if (u_color_cycle < 0.5) {
        // Solid mode: monochrome with subtle chromatic shift
        col = u_base_color * vec3(g_r, g_g, g_b) * breath();
    } else {
        // Rainbow mode: hue shifts with depth and angle
        float hue = warp * 0.005 + u_time * 0.04 + angle / TWO_PI;
        col = arm_color(hue, (g_r + g_g + g_b) / 3.0);
    }

    // Text overlay
    if (u_show_text == 1 && g > 0.15) {
        float text_u = fract(spiralTwist / TWO_PI);
        vec4 txt = sample_text(text_u, r * 0.3);
        col = mix(col, txt.rgb * 1.5, txt.a * g * 0.8);
    }

    return vec4(col, g * u_opacity * fade) * entrainmentModulation();
}
