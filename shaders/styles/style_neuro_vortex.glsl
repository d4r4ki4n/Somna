// Style 25 — Neuro Vortex
// Based on "Neuro-Adaptive Hypnosis" by TripZilla (Shadertoy wcBGW3)
// Key technique: internal strobe + breath sync + peripheral desync + asymmetric motion
// The animation comes from internal oscillators creating continuous phase transformations.
// The strobe frequency scales with u_tightness so it can be tuned per-session.
vec4 style_neuro_vortex(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Internal animation oscillators
    float breathPulse = 0.5 + 0.5 * sin(u_time * 0.6);
    float strobeFreq = 6.0 + u_tightness * 0.5;
    float strobe = 0.5 + 0.5 * sin(u_time * strobeFreq);

    // Peripheral motion desync: outer regions drag behind time
    float periphDesync = sin(r * 12.0 - u_time * 0.02) * 0.6;

    // Asymmetric time shifts — different radial zones move at different speeds
    float asyncShift = sin(u_time * 0.45 + r * 6.0) * 1.3;

    // Depth warp
    float distortIntensity = 3.0 + u_tightness * 0.2;
    float warp = pow(r * distortIntensity + asyncShift, 1.5) * 50.0;

    // Spiral arms — high count for fine lenticular structure
    float spirals = float(u_count) * 6.0;
    float spiralTwist = mod(
        angle * spirals + warp - u_time * 0.85 * breathPulse,
        TWO_PI
    );

    // Main pattern
    float comp = cos(spiralTwist) * strobe
               - sin(r * 55.0)
               + periphDesync;

    // High-contrast power curve for sharp lenticular lines
    float sharp = 6.0 + u_thickness * 0.1;
    float g = pow((comp + 1.0) / 2.0, sharp);

    // Chaos adds extra peripheral lag
    g += u_chaos * sin(r * 12.0 - u_time * u_chaos * 50.0) * 0.15;

    // Fade center singularity
    float fade = smoothstep(0.0, 0.08, r);
    g *= fade;

    // RGB channel separation for chromatic depth
    float colorShift = 0.02 + u_chaos * 0.01;
    float g_r = pow((cos(spiralTwist) * strobe - sin(r * 55.0) + periphDesync + 1.0) / 2.0, sharp);
    float g_g = pow((cos(mod(angle * spirals + pow(r * (1.0 + colorShift) * distortIntensity + asyncShift, 1.5) * 50.0 - u_time * 0.85 * breathPulse, TWO_PI)) * strobe - sin(r * (1.0 + colorShift) * 55.0) + periphDesync + 1.0) / 2.0, sharp);
    float g_b = pow((cos(mod(angle * spirals + pow(r * (1.0 - colorShift) * distortIntensity + asyncShift, 1.5) * 50.0 - u_time * 0.85 * breathPulse, TWO_PI)) * strobe - sin(r * (1.0 - colorShift) * 55.0) + periphDesync + 1.0) / 2.0, sharp);

    g_r *= fade;
    g_g *= fade;
    g_b *= fade;

    vec3 col;
    if (u_color_cycle < 0.5) {
        col = u_base_color * vec3(g_r, g_g, g_b);
    } else {
        float hue = warp * 0.005 + u_time * 0.04 + angle / TWO_PI;
        col = arm_color(hue, (g_r + g_g + g_b) / 3.0);
    }

    // Text overlay
    if (u_show_text == 1 && g > 0.15) {
        float text_u = fract(spiralTwist / TWO_PI);
        vec4 txt = sample_text(text_u, r * 0.3);
        col = mix(col, txt.rgb * 1.5, txt.a * g * 0.8);
    }

    return vec4(col, g * u_opacity * fade * breath()) * entrainmentModulation();
}
