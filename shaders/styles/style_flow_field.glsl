// Style 20 — Flow Field (curl noise advection)
vec4 style_flow_field(vec2 p) {
    float intensity = 0.0;
    vec2 pos = p;

    // Advect through curl noise flow field
    for (int i = 0; i < 8; i++) {
        vec2 c = curl_noise(pos * 1.5, u_time * 0.8);
        pos += c * 0.15;

        // Accumulate streamline density
        float line_dist = length(fract(pos * 3.0) - 0.5);
        intensity += smoothstep(0.3, 0.0, line_dist) * 0.15;
    }

    // Underlying spiral structure fades as chaos rises
    float r = length(p);
    float angle = atan(p.y, p.x);
    float spiral = sin(angle * 3.0 - r * 5.0 + u_time * 0.8) * 0.5 + 0.5;
    intensity += spiral * 0.2 * (1.0 - u_chaos);

    intensity = clamp(intensity, 0.0, 1.0) * breath();

    float phase = fract(u_time * 0.2 + length(pos) * 0.5);
    vec3 col = arm_color(phase, intensity);
    float alpha = intensity * u_opacity;
    alpha *= smoothstep(2.0, 0.2, r);

    return vec4(col, alpha);
}
