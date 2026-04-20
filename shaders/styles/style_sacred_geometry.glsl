// Style 21 — Sacred Geometry
// Flower of Life + Metatron's Cube lines, pulsing nodes, breathing scale.
vec4 style_sacred_geometry(vec2 p) {
    float r     = length(p);
    float g     = 0.0;

    // Breathing scale — gentle zoom in/out
    float breathe_scale = 1.0 + sin(u_time * 0.3) * 0.08;
    float scale = (1.8 + u_tightness * 0.4) * breathe_scale;

    // Slow rotation
    float rot = u_time * 0.15;
    float cr = cos(rot), sr = sin(rot);
    vec2 sp = vec2(p.x * cr - p.y * sr, p.x * sr + p.y * cr) * scale;

    // Hex grid basis vectors
    const vec2 e1 = vec2(1.0, 0.0);
    const vec2 e2 = vec2(0.5, 0.8660254);

    float edge_w = (0.04 + u_chaos * 0.02) * u_thickness * 0.5;
    float node_g = 0.0;

    // Circle edges + intersection nodes
    for (int j = -4; j <= 4; j++) {
        for (int i = -4; i <= 4; i++) {
            vec2 center = e1 * float(i) + e2 * float(j);
            float d = length(sp - center);

            float edge = smoothstep(edge_w, 0.0, abs(d - 1.0));
            float glow = exp(-pow(d - 1.0, 2.0) * 30.0) * 0.3;
            float wave = sin(d * 4.0 - u_time * 1.2 + float(i + j) * 0.8) * 0.5 + 0.5;
            float brightness = edge * (0.7 + wave * 0.3) + glow;

            g = max(g, brightness);

            // Intersection nodes — bright spots where circles cross
            // Check distance to center — if close to 1.0 from another center, it's an intersection
            for (int j2 = j; j2 <= min(j + 1, 4); j2++) {
                for (int i2 = i + 1; i2 <= min(i + 1, 4); i2++) {
                    vec2 c2 = e1 * float(i2) + e2 * float(j2);
                    float inter_d = length(sp - (center + c2) * 0.5);
                    float inter_glow = exp(-inter_d * inter_d * 20.0)
                                     * smoothstep(1.3, 0.5, length(center - c2));
                    node_g = max(node_g, inter_glow);
                }
            }
        }
    }

    // Metatron's Cube — straight lines connecting nearest-neighbor centers
    float line_g = 0.0;
    for (int j = -3; j <= 3; j++) {
        for (int i = -3; i <= 3; i++) {
            vec2 c = e1 * float(i) + e2 * float(j);
            // Connect to two neighbors: e1 direction and e2 direction
            for (int dir = 0; dir < 2; dir++) {
                vec2 nb = c + (dir == 0 ? e1 : e2);
                vec2 cp = sp - c;
                vec2 seg = nb - c;
                float seg_len = length(seg);
                float t = clamp(dot(cp, seg) / max(seg_len * seg_len, 0.001), 0.0, 1.0);
                float line_d = length(cp - seg * t);
                float lw = edge_w * 0.6;
                line_g = max(line_g, smoothstep(lw, 0.0, line_d)
                             * smoothstep(0.0, lw * 2.0, min(t, 1.0 - t) * seg_len));
            }
        }
    }
    line_g *= 0.35;

    // Pulse wave through nodes
    float node_pulse = 0.7 + 0.3 * sin(u_time * 2.0 + r * scale * 3.0);
    node_g *= node_pulse;

    g = g * breath() + line_g + node_g;

    // Center glow
    g += exp(-r * r * 5.0) * 0.5;

    // Color — radial + time-based, no angle to avoid seam
    vec3 col = arm_color(fract(r * 0.2 - u_time * 0.04 + g * 0.3), g);

    // Node highlights — warm gold
    col += vec3(1.0, 0.85, 0.5) * node_g * 0.4;

    return vec4(col, g * u_opacity) * entrainmentModulation();
}
