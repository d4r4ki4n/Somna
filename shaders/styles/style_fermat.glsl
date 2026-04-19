// Style 12 — Fermat
vec4 style_fermat(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Quadratic radial phase — defines the Fermat winding
    float phase   = r * r * u_tightness * 1.8 - angle - u_time * 0.65
                  + u_chaos * sin(float(u_count) * angle + u_time) * 0.25;
    float arm_per = TWO_PI / float(u_count);
    float arm_d   = mod(phase, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);

    // Width narrows outward (arms spread apart at edge, pack at center)
    // Floor at 0.015 prevents vanishing arms at edge; cap stays 0.35
    float width = clamp((0.055 / max(r, 0.12) + 0.018) * u_thickness * breath(),
                        0.015, 0.35);
    // Fade arms inside r=0.2 where Fermat packing is sub-pixel dense
    float inner_mask = smoothstep(0.1, 0.3, r);

    float arm_core = smoothstep(width * 1.2, 0.0, arm_dist);
    float arm_glow = smoothstep(width * 3.5, 0.0, arm_dist) * 0.30;
    float arm      = (arm_core + arm_glow * (1.0 - arm_core)) * inner_mask;

    // Convergence glow at center — reduced intensity so it doesn't drown arms
    float core_glow = exp(-r * r * 4.5) * 1.0;

    vec3 col = arm_color(fract(phase / TWO_PI) + u_time * 0.04, arm * breath());
    col += u_base_color * core_glow;

    float alpha = (arm + core_glow * 0.4) * u_opacity * smoothstep(3.0, 0.3, r);
    return vec4(col, alpha) * entrainmentModulation();
}
