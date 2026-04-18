// Style 6 — Vortex
vec4 style_vortex(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // u_count arms winding inward; u_tightness controls how tightly wound
    float swirl  = u_tightness * 1.1 / (r + 0.22);
    // round() ensures the angular coefficient is an integer so the atan seam
    // (Δangle = 2π) creates a phase jump that is an exact multiple of 2π.
    float warped = angle * round(float(u_count) * 0.5) + swirl - u_time * 1.5;

    // Layered octaves — fundamental + harmonics, alternating rotation direction
    float turb = 0.0;
    for (int i = 1; i <= 4; i++) {
        float f   = float(i);
        float dir = (mod(f, 2.0) < 1.0) ? 1.0 : -1.0;  // ±1 keeps warped*f*dir seamless
        turb += sin(r * u_tightness * f * 0.38 + warped * f * dir
                    + u_time * f * 0.28) / f;
    }
    turb = turb * (0.25 + u_chaos * 0.55) + 0.08;

    // u_thickness widens the bright tendrils (higher = fatter arms)
    float edge = max(0.02, 0.38 / u_thickness);
    float g    = smoothstep(edge * 0.4, edge * 2.2, turb) * breath()
               * smoothstep(2.25, 0.04, r);

    // Singularity core
    float core = exp(-r * r * 3.8) * 1.3;

    // Radial hue only — no angle term, no atan seam possible.
    vec3 col = arm_color(r * 0.2 + u_time * 0.04,
                         g * (1.1 + 0.38 * sin(u_time * 1.4 + turb * TWO_PI)));
    col += u_base_color * core * 0.9;
    return vec4(col, (g + core * 0.45) * u_opacity * smoothstep(2.35, 0.0, r));
}
