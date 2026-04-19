// Style 18 — Cobwebs (Klüver FC-IV: radial branching filigrees)
vec4 style_cobwebs(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Radial spoke structure
    int n_spokes = 8 + int(u_chaos * 8.0);
    float spoke_angle = TWO_PI / float(n_spokes);
    float nearest_spoke = abs(mod(angle + PI, spoke_angle) - spoke_angle * 0.5);
    float spoke_dist = nearest_spoke * r;

    // Branching: secondary filigrees emerge at intervals
    float branch_interval = 0.15 + u_chaos * 0.1;
    float branch_r = mod(r, branch_interval);
    float branch_angle = spoke_angle * 0.5;
    float branch_theta = abs(mod(angle + branch_angle + PI, spoke_angle) - spoke_angle * 0.5);
    float branch_dist = branch_theta * r;
    float branch_mask = smoothstep(branch_interval * 0.4, branch_interval * 0.5, branch_r);

    // Combine spokes + branches
    float d = min(spoke_dist, branch_dist * branch_mask);

    // FBM perturbation for organic wobble
    d += snoise(vec2(angle * 2.0 + u_time * 0.1, r * 5.0)) * u_chaos * 0.02;

    // Sharpness scales inversely with chaos
    float sharpness = 40.0 - u_chaos * 20.0;
    float g = exp(-d * sharpness) * breath();

    // Concentric ring accents at branch points
    float ring = abs(sin(r * 40.0 - u_time * 2.0));
    ring = smoothstep(0.95, 1.0, ring) * 0.15 * g;

    vec3 col = arm_color(angle / TWO_PI + u_time * 0.02, g * 0.8 + ring);
    float alpha = (g + ring) * u_opacity;
    alpha *= smoothstep(2.0, 0.3, r);
    alpha *= smoothstep(0.02, 0.1, r);

    return vec4(col, alpha);
}
