// Style 24 — Fractal Scale Spiral
// Based on "This will give you eye pain fs!" by DizNuts (Shadertoy 3fsSzj)
// Adapted: fixed atan seam, arm_color palette, entrainment, text overlay
vec4 style_fractal_scale(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float t     = u_time * 1.5;

    // Recursive scale bands via exp2(floor(log2(r)))
    // Each octave doubles in spatial frequency — creates fractal self-similarity
    float scale = exp2(floor(log2(max(r, 0.001))) + 0.10);

    // Position in current scale band
    vec2 pos = fract(p / scale) + scale + 11.5;

    // Spiral phase — use atan with seamless integer coefficient
    // Fix: angle*count/TWO_PI gives integer period at 2π boundary → no seam
    float spiral_phase = angle * float(u_count) / TWO_PI + r * 0.5;

    // Smooth blend from fractal-scaled pattern (center) to spiral (outer)
    float blend = smoothstep(0.3, 0.7, r);
    vec2 uv2 = mix(pos, vec2(spiral_phase, r), blend);

    // Animate with time
    uv2 += vec2(t * 0.08, t * 0.12);

    // Chaos: perturb the pattern
    uv2 += u_chaos * vec2(sin(r * 6.0 + t), cos(angle * 4.0 + t)) * 0.3;

    // Pattern: cosine color bands — u_thickness controls band sharpness
    float sharp = 1.0 + u_thickness * 0.3;
    float pattern = 0.5 + 0.5 * cos(dot(uv2, vec2(12.0, 9.0)) + t * 2.0);
    pattern = pow(pattern, sharp);

    // Secondary: concentric ring modulation for depth
    float rings = 0.5 + 0.5 * sin(r * 15.0 - t * 3.0);
    float g = pattern * mix(rings, 1.0, 0.4) * breath();

    // Boost overall brightness — was too transparent
    g = g * 1.6;

    // Fade center to avoid singularity artifacts
    float fade = smoothstep(0.0, 0.1, r);

    vec3 col = arm_color(uv2.x * 0.1 + u_time * 0.06, g);

    // Text overlay
    if (u_show_text == 1 && g > 0.15) {
        float text_u = fract(spiral_phase + t * 0.02);
        vec4 txt = sample_text(text_u, r * 0.5);
        col = mix(col, txt.rgb * 1.8, txt.a * g * 0.75);
    }

    return vec4(col, g * u_opacity * fade) * entrainmentModulation();
}
