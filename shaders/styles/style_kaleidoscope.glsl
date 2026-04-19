// Style 3 — Kaleidoscope
vec4 style_kaleidoscope(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float sectors      = float(u_count) * 2.0;
    float sector_angle = TWO_PI / sectors;
    float folded       = mod(angle + u_time * 0.3, sector_angle);
    if (folded > sector_angle * 0.5) folded = sector_angle - folded;
    float spiral1 = sin(r * u_tightness - u_time * 2.0 + folded * 3.0);
    float spiral2 = sin(r * u_tightness * 0.6 + u_time * 1.3 - folded * 5.0);
    float chaos_w = u_chaos * sin(r * 8.0 + u_time * 2.5);
    float pattern = (spiral1 + spiral2) * 0.5 + chaos_w;
    float g = (smoothstep(0.0, 0.4, pattern)
             + smoothstep(0.5, 0.9, pattern) * 0.5) * breath();
    vec3 col = arm_color(r * 0.25 - u_time * 0.06 + folded, g);
    return vec4(col, g * u_opacity * smoothstep(2.0, 0.1, r)) * entrainmentModulation();
}
