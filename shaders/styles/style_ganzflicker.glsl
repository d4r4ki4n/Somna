// Style 28 — Ganzflicker (Jager-Ganzflicker)
// Based on "Jager-Ganzflicker" by TripZilla (Shadertoy tcB3W3)
// Key technique: fullscreen flicker tuned for alpha/theta entrainment,
// peripheral distortion, RGB chromatic separation
// Purpose: dedicated entrainment style — pure flicker + peripheral warping
vec4 style_ganzflicker(vec2 p) {
    float r = length(p);

    // Core flicker: entrainment phase drives the primary oscillation
    // entrainment_phase is already locked to beat_frequency by the audio engine
    // so this flickers at exactly the binaural beat frequency
    float flicker = 0.5 + 0.5 * sin(u_entrainment_phase * TWO_PI);

    // Peripheral distortion — radial pattern that creates visual instability
    // Stronger at edges (larger r) for peripheral vision effect
    float periphDistort = sin(r * 12.0 + u_time * 0.03 * (1.0 + u_chaos * 50.0));

    // Combined pattern: flicker dominates, peripheral adds depth
    float intensity = 0.9;
    float comp = pow(abs(flicker + periphDistort * intensity), 6.0);

    // Add subtle spiral twist for visual interest
    float angle = atan(p.y, p.x);
    float twist = sin(angle * float(u_count) + r * u_tightness * 10.0 - u_time * 2.0);
    comp += twist * u_chaos * 0.15;
    comp = clamp(comp, 0.0, 1.0);

    // Thickness controls how sharp the flicker edges are
    // Higher thickness = harder transition, lower = softer pulse
    float softness = mix(1.0, 6.0, 1.0 - u_thickness / 40.0);
    comp = pow(comp, softness);

    // Fade center to avoid singularity
    float fade = smoothstep(0.0, 0.04, r);

    comp *= fade * breath();

    // RGB channel separation for chromatic entrainment
    // Each channel flickers at slightly offset phase
    float colorShift = 0.02 + u_chaos * 0.02;
    float comp_r = pow(abs(
        0.5 + 0.5 * sin(u_entrainment_phase * TWO_PI)
        + sin(r * 12.0 + u_time * 0.03) * intensity
    ), 6.0);
    float comp_g = pow(abs(
        0.5 + 0.5 * sin(u_entrainment_phase * TWO_PI + colorShift * 10.0)
        + sin(r * (12.0 + colorShift * 100.0) + u_time * 0.03) * intensity
    ), 6.0);
    float comp_b = pow(abs(
        0.5 + 0.5 * sin(u_entrainment_phase * TWO_PI - colorShift * 10.0)
        + sin(r * (12.0 - colorShift * 100.0) + u_time * 0.03) * intensity
    ), 6.0);

    vec3 col;
    if (u_color_cycle < 0.5) {
        col = u_base_color * vec3(
            pow(comp_r, softness),
            pow(comp_g, softness),
            pow(comp_b, softness)
        ) * breath();
    } else {
        float hue = r * 0.5 + u_time * 0.06;
        col = arm_color(hue, (comp_r + comp_g + comp_b) / 3.0);
    }

    // Text overlay — limited utility in a flicker style but supported
    if (u_show_text == 1 && comp > 0.2) {
        float text_u = fract(angle / TWO_PI + u_time * 0.1);
        vec4 txt = sample_text(text_u, r * 0.3);
        col = mix(col, txt.rgb * 1.5, txt.a * comp * 0.7);
    }

    return vec4(col, comp * u_opacity * fade) * entrainmentModulation();
}
