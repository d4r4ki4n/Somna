// Style 22 — Morphing Julia (smooth iteration fractal)
vec4 style_recursive_fractal(vec2 p) {
    float r = length(p);

    // Animate c along the Mandelbrot boundary for continuously morphing fractals
    float t = u_time * 0.06 * (0.5 + u_tightness * 0.1);
    vec2 c = vec2(
        0.7885 * cos(t),
        0.7885 * sin(t)
    );

    // Chaos perturbs c for extra variation
    c += vec2(
        u_chaos * 0.05 * sin(u_time * 0.3),
        u_chaos * 0.05 * cos(u_time * 0.4)
    );

    // Julia iteration
    vec2 z = p * (1.5 + u_thickness * 0.05);
    float iter = 0.0;
    const int MAX_ITER = 48;

    for (int i = 0; i < MAX_ITER; i++) {
        z = vec2(z.x * z.x - z.y * z.y, 2.0 * z.x * z.y) + c;
        if (dot(z, z) > 4.0) break;
        iter += 1.0;
    }

    // Smooth iteration count for anti-aliased coloring
    float smooth_iter = iter;
    if (iter < float(MAX_ITER)) {
        smooth_iter = iter - log2(log2(dot(z, z))) + 4.0;
    }

    // Normalize and create intensity
    float normalized = smooth_iter / float(MAX_ITER);
    float g = normalized * breath();

    // Interior (converged) regions: subtle glow based on final |z|
    if (iter >= float(MAX_ITER)) {
        float interior_glow = 1.0 - smoothstep(0.0, 2.0, length(z));
        g = interior_glow * 0.15 * breath();
    }

    // Edge enhancement: fractal boundaries are the brightest
    float edge_boost = smoothstep(0.3, 0.7, normalized) * 0.4;
    g += edge_boost;

    // Center glow
    float core = exp(-r * r * 4.0) * 0.5;
    g += core;

    vec3 col = arm_color(fract(normalized * 2.0 + u_time * 0.03), g);
    float alpha = clamp(g, 0.0, 1.5) * u_opacity;
    alpha *= smoothstep(2.2, 0.05, r);

    return vec4(col, alpha) * entrainmentModulation();
}
