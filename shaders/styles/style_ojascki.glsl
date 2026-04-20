// Style 26 — Ojascki (Calling)
// Based on "Ojascki - Calling" by BigWings/Shadertoy 3sG3zy
// Key technique: spiral rings with fwidth anti-aliasing, self-rotating, evolving scale
vec4 style_ojascki(vec2 p) {
    float r = length(p);
    float angle = atan(p.y, p.x);

    // Time with wobble for organic motion
    float t = u_time;
    t += sin(t * 0.5) * 0.25 * u_chaos;

    // Rotate entire field
    float ca = cos(t * 0.7);
    float sa = sin(t * 0.7);
    p = mat2(ca, -sa, sa, ca) * p;
    r = length(p);
    angle = atan(p.y, p.x);

    // Evolving scale factor — number of visible rings changes over time
    float a = 2.0 + sin(t * 0.4) * (0.5 + u_chaos * 0.5);

    // Spiral ring distance field
    // x = normalised angle, y = ring index from center
    float x = angle / TWO_PI + 0.5;
    float y = 20.0 / (9.0 * r * a * a) - x;

    // Accumulate ring index for pattern
    x += ceil(y);
    y = fract(y) - 0.5;

    // Ring pattern: x²*4 - sqrt(0.25-y²) produces concentric ring shapes
    // that grow larger toward the edge, creating a spiral tunnel effect
    float ring = (x * x * 4.0 - sqrt(max(0.25 - y * y, 0.0))) * (2.0 + u_thickness * 0.2);

    // fwidth anti-aliasing — clean edges at any zoom level
    float w = fwidth(ring);
    float c = smoothstep(w, -w, abs(fract(ring) - 0.5) - 0.25);

    // Smooth out moiré at high frequencies
    float g = (c - 0.5) * max(0.0, 1.0 - w) + 0.5;

    // Fade center to avoid singularity, fade edges for clean border
    float fade = smoothstep(0.0, 0.06, r) * smoothstep(3.5, 1.5, r);

    g *= fade * breath();

    vec3 col = arm_color(ring * 0.08 + u_time * 0.03, g);

    // Text overlay — sample along the spiral rings
    float arm_u = fract(ring / 2.0);
    if (u_show_text == 1 && g > 0.15) {
        vec4 txt = sample_text(arm_u, r * 0.3);
        col = mix(col, txt.rgb * 1.5, txt.a * g * 0.8);
    }

    return vec4(col, g * u_opacity * fade) * entrainmentModulation();
}
