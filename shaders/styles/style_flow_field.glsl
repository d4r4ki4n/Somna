// Style 20 — Silk Streams (voronoi cell boundaries warped by curl noise)
vec4 style_flow_field(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    float t = u_time;
    float g = 0.0;

    // Layer 1: large-scale flow structure
    float scale1 = 2.0 + u_tightness * 0.5;
    vec2 drift1 = vec2(t * 0.12, t * 0.08) + curl_noise(p * 1.5, t * 0.4) * 1.2;
    vec2 warped1 = p * scale1 + drift1;
    float v1 = voronoi_dist(warped1);
    float stream1 = smoothstep(0.12, 0.0, v1) * 0.8;
    float glow1 = exp(-v1 * v1 * 20.0) * 0.35;

    // Layer 2: finer detail — faster perpendicular drift
    float scale2 = 4.0 + u_chaos * 3.0;
    vec2 drift2 = vec2(-t * 0.06, t * 0.14) + curl_noise(p * 3.0, t * 0.6) * 0.8;
    vec2 warped2 = p * scale2 + drift2;
    float v2 = voronoi_dist(warped2);
    float stream2 = smoothstep(0.06, 0.0, v2) * 0.5;
    float glow2 = exp(-v2 * v2 * 40.0) * 0.2;

    // Layer 3: fine shimmer — fastest, most delicate
    float scale3 = 8.0 + u_chaos * 4.0;
    vec2 drift3 = vec2(t * 0.10, -t * 0.05) + curl_noise(p * 5.0, t * 0.8) * 0.5;
    vec2 warped3 = p * scale3 + drift3;
    float v3 = voronoi_dist(warped3);
    float stream3 = smoothstep(0.04, 0.0, v3) * 0.3;

    g = (stream1 + glow1 + stream2 + glow2 + stream3) * breath();

    // Underlying radial spiral structure for cohesion — rotates slowly
    float radial = sin(angle * float(u_count) - r * u_tightness + t * 0.5) * 0.5 + 0.5;
    g += radial * 0.15 * (1.0 - u_chaos * 0.5);

    // Center glow
    float core = exp(-r * r * 4.0) * 1.0;
    g += core;

    g = clamp(g, 0.0, 1.5);

    float phase = fract(r * 0.3 + angle / TWO_PI + t * 0.08);
    vec3 col = arm_color(phase, g);
    float alpha = g * u_opacity;

    return vec4(col, alpha) * entrainmentModulation();
}
