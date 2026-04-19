// Style 0 — Tunnel Dream
vec4 style_tunnel(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float depth = log(r + 0.001) * u_tightness * 0.5 - u_time * 1.4;
    // angle*count is seamless: sin(angle*n) has period 2π/n, completing n full
    // cycles per revolution — no atan discontinuity when count is integer.
    float twist = angle * float(u_count) + depth * TWO_PI * 0.6;
    float rings   = sin(depth * TWO_PI) * 0.5 + 0.5;
    float spokes  = sin(twist) * 0.5 + 0.5;
    float pattern = rings * 0.6 + spokes * 0.4;
    pattern += u_chaos * sin(angle * 6.0 + u_time * 2.0 + r * 4.0) * 0.2;
    float core = smoothstep(0.18 * u_thickness, 0.0, abs(pattern - 0.5));
    float halo = smoothstep(0.54 * u_thickness, 0.0, abs(pattern - 0.5)) * 0.4;
    float g    = (core + halo * (1.0 - core)) * breath();
    vec3  col  = arm_color(depth * 0.1 + u_time * 0.05, g * (0.7 + 0.3 * rings));
    return vec4(col, g * u_opacity * 1.0) * entrainmentModulation();
}
