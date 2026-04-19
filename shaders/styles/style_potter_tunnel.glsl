// Style 23 — Potter's Tunnel
// Based on "Breath Potter's Tunnel" by s23b (Shadertoy 4st3WX)
// Adapted: uses our uniforms, arm_color, breath(), entrainment, text overlay
vec4 style_potter_tunnel(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Inverse-radius depth (flythrough feel)
    float depth = u_tightness * 0.5 / max(r, 0.01);

    // Spiral arms from angle
    float twist = angle * float(u_count) / 2.0;

    // Combine depth + twist, animate with time
    float f = depth + twist / PI - u_time * 1.2;

    // Anti-aliased striping (Shane's AA trick from the original)
    // dot(p,p) gives distance² for natural AA; multiplied by resolution scale
    float stripe = 1.0 - clamp(
        sin(f * PI * 2.0) * dot(p, p) * 400.0 * u_thickness / 14.0 + 0.5,
        0.0, 1.0
    );

    // Chaos: wobble the tunnel walls
    stripe += u_chaos * sin(angle * 8.0 + r * 12.0 - u_time * 3.0) * 0.15;

    // Darken tunnel far end (center) and near edges
    float falloff = smoothstep(0.0, 0.08, r);
    float end_dark = smoothstep(0.0, 0.4, r) * 0.7 + 0.3;

    float g = stripe * falloff * end_dark * breath();

    vec3 col = arm_color(depth * 0.15 + u_time * 0.05, g);

    // Text overlay — sample along the spiral arms
    float arm_u = fract(f / TWO_PI);
    if (u_show_text == 1 && g > 0.15) {
        vec4 txt = sample_text(arm_u, r);
        col = mix(col, txt.rgb * 1.8, txt.a * g * 0.85);
    }

    return vec4(col, g * u_opacity * falloff) * entrainmentModulation();
}
