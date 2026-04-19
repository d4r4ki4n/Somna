// Style 8 — Fibonacci (golden ratio logarithmic spiral)
vec4 style_fibonacci(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Golden angle ≈ 137.5° — Fibonacci phyllotaxis
    float golden_angle = PI * (3.0 - sqrt(5.0));

    // Logarithmic spiral with phi growth rate
    float log_r  = log(max(r, 0.01));
    float phase  = log_r * u_tightness * PHI - angle - u_time * 0.9
                 + u_chaos * sin(r * 4.0 + u_time * 0.7);

    // arm_per must divide 2π evenly so the atan seam (phase jump = 2π) lands
    // on an exact arm period boundary. golden_angle is irrational w.r.t. 2π,
    // so we use u_count-equal spacing while keeping the phi logarithmic growth.
    float arm_per  = TWO_PI / float(u_count);
    float arm_d    = mod(phase, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);
    // fract(phase/TWO_PI): seam jump is exactly 1 full period → fract absorbs it.
    // (TWO_PI*PHI divisor caused a 0.618 jump in arm_u, visible as color stripe.)
    float arm_u    = fract(phase / TWO_PI);

    // Width narrows in center, blooms at outer edge like a petal
    // Floor at 0.06 prevents invisible sub-pixel arms at center
    float width    = max(0.06, (0.03 + r * 0.08 * PHI)) * u_thickness * breath();
    float arm_core = smoothstep(width * 1.2, 0.0, arm_dist);
    float arm_glow = smoothstep(width * 3.0, 0.0, arm_dist) * 0.4;
    float arm      = arm_core + arm_glow * (1.0 - arm_core);
    // Fade arms inside r=0.15 where packing is too dense to resolve
    arm *= smoothstep(0.08, 0.25, r);

    // Secondary: radial center-glow (replaces phyllotaxis dot — angle/golden_angle
    // is not 2π-periodic so it created a hard seam at the atan branch cut).
    float dot = exp(-r * r * 5.0) * 0.6;

    float brightness = (arm + dot) * breath();

    // Declare warm/cool at function scope — text overlay also uses warm.
    vec3 warm = u_base_color * vec3(1.0, 0.85, 0.5);
    vec3 cool = u_base_color * vec3(0.5, 0.8, 1.0);

    // Respect the color mode toggle — arm_u is seamless (fract(phase/TWO_PI)).
    vec3 col;
    if (u_color_cycle < 0.5) {
        col = u_base_color * brightness;
    } else {
        col = mix(warm, cool, arm_u) * brightness;
    }

    float core_glow = exp(-r * r * 8.0) * 1.5;
    col += u_base_color * core_glow;

    if (u_show_text == 1 && arm > 0.15) {
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * warm * 2.0, txt.a * arm * 0.75);
    }
    float fade = smoothstep(3.0, 0.3, r) * smoothstep(0.0, 0.05, r);
    return vec4(col, (arm + dot * 0.5) * u_opacity * fade) * entrainmentModulation();
}
