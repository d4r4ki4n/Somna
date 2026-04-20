// Style 29 — Vogel Spiral (Spiral of Spirals 2)
// Based on "Spiral of Spirals 2" by KilledByAPixel (Shadertoy lsdBzX)
// Key technique: self-referential polar spiral where angle feeds back into itself,
// producing evolving fractal-like patterns that change character over time.
// The spiral index creates nested spiral-of-spiral structures.
vec4 style_vogel_spiral(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Scale UV for visible structure — original uses 100x but our p is already
    // normalized to ~[-1,1], so we scale by tightness
    float scale = 40.0 + u_tightness * 30.0;
    float d = r * scale;

    // Normalize angle to [0, 1]
    float p_norm = angle / TWO_PI + 0.5;

    // Spiral index: distance minus angular position
    // This creates the self-referential spiral-of-spirals structure
    float idx = d - p_norm;
    angle += TWO_PI * floor(idx);

    // Time evolution — slow enough to watch patterns develop
    // The +20.0 offset skips the boring startup period
    float t = 0.05 * (u_time + 20.0 + u_chaos * 40.0);

    // Hue channel: first harmonic of the spiral angle, shaped by power curve
    float h = 0.5 * angle * t;
    h = 0.5 * (sin(h) + 1.0);
    h = pow(h, 3.0);
    h += 4.222 * t + 0.4;

    // Saturation channel: second harmonic
    float s = 2.0 * angle * t;
    s = 0.5 * (sin(s) + 1.0);
    s = pow(s, 2.0);

    // Value channel: the spiral angle scaled by floor(index)+fractional
    // This produces the nested spiral structure
    float vAngle = angle * (floor(idx) + p_norm);
    float v = vAngle * t;
    v = sin(v);
    v = 0.5 * (v + 1.0);
    v = pow(v, 4.0);

    // Darken ring edges for depth
    v *= pow(sin(fract(idx) * PI), 0.4);

    // Dot in center — avoids singularity
    v *= min(d, 1.0);

    // Thickness controls brightness falloff
    v *= 0.5 + 0.5 * u_thickness / 22.0;

    // Fade at very center and very edges
    float fade = smoothstep(0.0, 0.02, r) * smoothstep(4.0, 2.0, r);

    v *= fade * breath();

    // Convert HSV to RGB using arm_color for palette integration
    vec3 col;
    if (u_color_cycle < 0.5) {
        // Solid mode: use base_color tinted by the value channel
        col = u_base_color * v * (0.5 + 0.5 * s);
    } else {
        // Rainbow mode: use the hue from the spiral math
        col = arm_color(h * 0.15 + u_hue_shift, v * (0.5 + 0.5 * s));
    }

    // Text overlay
    if (u_show_text == 1 && v > 0.15) {
        float text_u = fract(idx / 3.0);
        vec4 txt = sample_text(text_u, r);
        col = mix(col, txt.rgb * 1.5, txt.a * v * 0.8);
    }

    return vec4(col, v * u_opacity * fade) * entrainmentModulation();
}
