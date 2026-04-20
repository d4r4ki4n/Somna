// Style 27 — Tunnel Warp (Deep Tunnel Time Warper)
// Based on "Deep Tunnel Time Warper" by TripZilla (Shadertoy tfBGD3)
// Key technique: high spiral count + depth warp + time-bent radial interference
// Animation comes from continuous rotation + sin(time) modulating the radial wave.
vec4 style_tunnel_warp(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Depth warp
    float depthWarp = 2.5 + u_tightness * 0.15;

    // High spiral count for fine lenticular tunnel structure
    float spirals = float(u_count) * 5.0;

    // Phase-shifted depth
    float warp = pow(r * depthWarp, 1.5) * 40.0;

    // Main spiral rotation — continuous, driven by time
    float spiralPhase = mod(
        angle * spirals + warp - u_time * 1.2,
        TWO_PI
    );

    // Radial interference modulated by time — THIS is the animation the original has
    float timeBend = sin(u_time * 0.5 + u_chaos * 2.0);

    float comp = cos(spiralPhase) - sin(r * 60.0) * timeBend;

    // High-contrast power curve for sharp lenticular lines
    float sharp = 7.0 + u_thickness * 0.15;
    float g = pow((comp + 1.0) / 2.0, sharp);

    // Fade center singularity
    float fade = smoothstep(0.0, 0.06, r);
    g *= fade;

    // RGB channel separation for chromatic depth
    float colorShift = 0.03 + u_chaos * 0.02;
    float g_r = pow((cos(spiralPhase) - sin(r * 60.0) * timeBend + 1.0) / 2.0, sharp);
    float g_g = pow((cos(mod(angle * spirals + pow(r * (1.0 + colorShift) * depthWarp, 1.5) * 40.0 - u_time * 1.2, TWO_PI)) - sin(r * (1.0 + colorShift) * 60.0) * timeBend + 1.0) / 2.0, sharp);
    float g_b = pow((cos(mod(angle * spirals + pow(r * (1.0 - colorShift) * depthWarp, 1.5) * 40.0 - u_time * 1.2, TWO_PI)) - sin(r * (1.0 - colorShift) * 60.0) * timeBend + 1.0) / 2.0, sharp);

    g_r *= fade;
    g_g *= fade;
    g_b *= fade;

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

    return vec4(col, g * u_opacity * fade * breath()) * entrainmentModulation();
}
