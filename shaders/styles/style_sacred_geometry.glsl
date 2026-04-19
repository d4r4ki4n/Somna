// Style 21 — Sacred Geometry (hexagonal tiling, GENUS-compatible)
vec4 style_sacred_geometry(vec2 p) {
    // Scale to tile space
    vec2 tp = p * 3.0;

    // Hex grid — two interleaved offsets
    const vec2 s = vec2(1.0, 1.7320508); // 1, sqrt(3)
    vec2 p1 = mod(tp, s) - s * 0.5;
    vec2 p2 = mod(tp + s * 0.5, s) - s * 0.5;
    vec2 hex_p = (dot(p1, p1) < dot(p2, p2)) ? p1 : p2;

    // Distance to hex edge
    float hex_d = max(
        abs(hex_p.x),
        dot(abs(hex_p), vec2(0.5, 0.8660254))
    );

    // Cell identity for per-cell animation
    vec2 cell_id = floor(tp / s);
    float cell_hash = fract(sin(dot(cell_id, vec2(127.1, 311.7))) * 43758.5453);

    // Phase-animated fill: cells light up in waves
    float wave = sin(cell_hash * TWO_PI + u_time * 0.8);
    float fill = smoothstep(0.0, 0.3, wave);

    // Edge glow
    float edge = 1.0 - smoothstep(0.35, 0.5, hex_d);
    float edge_glow = exp(-(hex_d - 0.45) * 20.0) * 0.3;

    // Chaos: domain-warp the fill
    if (u_chaos > 0.1) {
        fill *= 1.0 + snoise(tp * 2.0 + u_time * 0.1) * u_chaos * 0.5;
    }

    float g = (fill * 0.7 + edge * 0.2 + edge_glow) * breath();
    float phase = fract(cell_hash + u_time * 0.1);
    vec3 col = arm_color(phase, g);

    float r = length(p);
    float alpha = g * u_opacity;
    alpha *= smoothstep(2.2, 0.2, r);

    return vec4(col, alpha) * entrainmentModulation();
}
