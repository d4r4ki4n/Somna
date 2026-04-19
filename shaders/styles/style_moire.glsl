// Style 10 — Moiré
vec4 style_moire(vec2 p) {
    float r      = length(p);
    float angle  = atan(p.y, p.x);
    float ap     = TWO_PI / float(u_count);

    float tight2 = u_tightness * (1.0 + 0.07 + u_chaos * 0.03);

    // CW — angle coef -1, seam jump +2π = count * ap → seamless
    float ph1  = r * u_tightness - angle - u_time * 1.1;
    float d1   = min(mod(ph1, ap) / ap, 1.0 - mod(ph1, ap) / ap);

    // CCW — angle coef +1, seam jump -2π = -count * ap → seamless
    float ph2  = r * tight2 + angle - u_time * 0.85;
    float d2   = min(mod(ph2, ap) / ap, 1.0 - mod(ph2, ap) / ap);

    float width = (0.035 + r * 0.016) * u_thickness * breath();

    float c1 = smoothstep(width * 1.2, 0.0, d1);
    float h1 = smoothstep(width * 4.0, 0.0, d1) * 0.50;
    float arm1 = c1 + h1 * (1.0 - c1);

    float c2 = smoothstep(width * 1.2, 0.0, d2);
    float h2 = smoothstep(width * 4.0, 0.0, d2) * 0.50;
    float arm2 = c2 + h2 * (1.0 - c2);

    // Beat: bright flare where both cores cross
    float beat = c1 * c2 * 3.5;

    float g = arm1 + arm2 * (1.0 - arm1);
    g = (g + beat * (1.0 - g)) * breath();

    // Complementary hues on each spiral — chromatic moiré
    vec3 col1 = arm_color(fract(ph1 / TWO_PI) + u_time * 0.03, arm1 * breath());
    vec3 col2 = arm_color(fract(ph2 / TWO_PI) + 0.5 + u_time * 0.03, arm2 * breath());
    vec3 col_b = arm_color(r * 0.15 + u_time * 0.07, beat);
    vec3 col   = col1 + col2 * (1.0 - arm1) + col_b;

    return vec4(col, g * u_opacity * 1.0) * entrainmentModulation();
}
