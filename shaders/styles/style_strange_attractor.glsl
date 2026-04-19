// Style 19 — Strange Attractor (Rössler density projection)
vec4 style_strange_attractor(vec2 p) {
    float intensity = 0.0;

    float a_param = 0.2 + u_chaos * 0.1;
    float b_param = 0.2;
    float c_param = 5.7 + u_chaos * 3.0;
    float dt = 0.01;

    // Integrate Rössler attractor, accumulate density
    vec3 pos = vec3(1.0, 1.0, 1.0);
    float speed = 0.8 + u_thickness * 0.2;

    // 512 iterations — balance quality vs performance
    for (int i = 0; i < 512; i++) {
        vec3 dp = vec3(
            -pos.y - pos.z,
            pos.x + a_param * pos.y,
            b_param + pos.z * (pos.x - c_param)
        );
        pos += dp * dt;

        // Rotate projection over time
        float ct = cos(u_time * speed * 0.05);
        float st = sin(u_time * speed * 0.05);
        vec2 projected = vec2(
            pos.x * ct - pos.z * st,
            pos.y
        ) * 0.12;

        float dist = length(p - projected);
        intensity += exp(-dist * dist * 150.0) * 0.04;
    }

    intensity = clamp(intensity, 0.0, 1.0) * breath();

    float phase = fract(u_time * speed * 0.1 + intensity);
    vec3 col = arm_color(phase, intensity);
    float r = length(p);
    float alpha = intensity * u_opacity;
    alpha *= smoothstep(2.0, 0.3, r);

    return vec4(col, alpha) * entrainmentModulation();
}
