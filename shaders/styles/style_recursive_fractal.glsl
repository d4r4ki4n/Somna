// Style 22 — Recursive Fractal Zoom (infinite self-similar depth)
vec4 style_recursive_fractal(vec2 p) {
    float intensity = 0.0;

    // Layered zoom: each layer is a scaled copy with rotation
    for (int i = 0; i < 6; i++) {
        float layer_time = u_time * 0.8 + float(i) * 1.5;
        float zoom = exp(mod(layer_time * 0.3, 3.0) - 1.5);
        float rotation = layer_time * 0.05 * (1.0 + u_chaos);

        // Rotate and scale
        float cr = cos(rotation), sr = sin(rotation);
        vec2 zp = vec2(p.x * cr - p.y * sr, p.x * sr + p.y * cr) * zoom;

        // Pattern at this zoom level
        float r = length(zp);
        float theta = atan(zp.y, zp.x);
        float pattern = sin(theta * (3.0 + u_chaos * 5.0) + r * 8.0) * 0.5 + 0.5;

        // Fade by depth
        float depth_fade = exp(-abs(mod(layer_time * 0.3, 3.0) - 1.5) * 2.0);
        intensity += pattern * depth_fade * 0.25;
    }

    intensity = clamp(intensity, 0.0, 1.0) * breath();

    float phase = fract(u_time * 0.15);
    vec3 col = arm_color(phase, intensity);
    float r_outer = length(p);
    float alpha = intensity * u_opacity;
    alpha *= smoothstep(2.2, 0.2, r_outer);

    return vec4(col, alpha);
}
