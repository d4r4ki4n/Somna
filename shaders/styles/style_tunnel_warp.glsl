// Style 27 — Tunnel Warp (Deep Tunnel Time Warper)
// Based on "Deep Tunnel Time Warper" by TripZilla (Shadertoy tfBGD3)
// Key technique: phase-shifted radial movement, depth warping, time-bend illusion
// Purpose-built for alpha/theta entrainment with asymmetric motion
vec4 style_tunnel_warp(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Depth warp — stronger distortion toward edges for tunnel depth
    float depthWarp = 3.0 + u_tightness * 0.5;

    // Spiral arm count (integer for seamless angular wrap)
    float spirals = float(u_count) * 2.0;

    // Phase-shifted depth: creates diverging/converging motion cycles
    // This is the "time bending" effect — rings appear to accelerate and decelerate
    float warp = pow(r * depthWarp, 1.5) * 40.0;

    // Main spiral equation — modulated by time for constant rotation
    float spiralPhase = mod(
        angle * spirals + warp - u_time * 1.2,
        TWO_PI
    );

    // Radial frequency interference — creates secondary ring pattern
    float radialWave = sin(r * 60.0) * sin(u_time * 0.5 + u_chaos * 2.0);

    // Combined pattern
    float comp = cos(spiralPhase) - radialWave * 0.15;

    // Sharp power curve for high-contrast rings
    float sharp = 9.0 - u_thickness * 0.3;
    float g = pow((comp + 1.0) / 2.0, max(sharp, 2.0));

    // Chaos: add radial wobble
    g += u_chaos * sin(angle * 6.0 + r * 20.0 - u_time * 4.0) * 0.1;

    // Fade center singularity
    float fade = smoothstep(0.0, 0.06, r);

    g *= fade * breath();

    // RGB channel separation for chromatic depth
    // Each channel samples at slightly offset radius — creates prismatic tunnel walls
    float colorShift = 0.03 + u_chaos * 0.02;
    float g_r = pow((cos(spiralPhase) + 1.0) / 2.0, max(sharp, 2.0));
    float g_g = pow((cos(mod(angle * spirals + pow(r * (1.0 + colorShift) * depthWarp, 1.5) * 40.0 - u_time * 1.2, TWO_PI)) + 1.0) / 2.0, max(sharp, 2.0));
    float g_b = pow((cos(mod(angle * spirals + pow(r * (1.0 - colorShift) * depthWarp, 1.5) * 40.0 - u_time * 1.2, TWO_PI)) + 1.0) / 2.0, max(sharp, 2.0));

    vec3 col;
    if (u_color_cycle < 0.5) {
        col = u_base_color * vec3(g_r, g_g, g_b) * breath();
    } else {
        float hue = warp * 0.003 + u_time * 0.04 + angle / TWO_PI;
        col = arm_color(hue, (g_r + g_g + g_b) / 3.0);
    }

    // Text overlay
    if (u_show_text == 1 && g > 0.15) {
        float text_u = fract(spiralPhase / TWO_PI);
        vec4 txt = sample_text(text_u, r * 0.3);
        col = mix(col, txt.rgb * 1.5, txt.a * g * 0.8);
    }

    return vec4(col, g * u_opacity * fade) * entrainmentModulation();
}
