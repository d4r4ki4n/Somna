// Style 30 — Galaxy Morph (Realistic Galaxy Morphology)
// Based on "Galaxy spirals" by guil (Shadertoy llSGR1)
// Key technique: logarithmic spiral arm winding + smooth dust lanes + star field + central bulge
vec4 style_galaxy_morph(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    float windingBase = 0.7;
    float windingNum  = float(u_count);

    // Visible rotation — was 0.02, now actually perceptible
    float rot = -u_time * 0.35;
    float ca = cos(rot), sa = sin(rot);
    vec2 rp = mat2(ca, -sa, sa, ca) * p;
    float angleR = atan(rp.y, rp.x);
    float rR     = length(rp);

    // Spiral arm function — softened power curve for thicker, less vein-like arms
    float theta_r = atan(exp(1.0 / max(rR, 0.01)) / windingBase) * 2.0 * windingNum;
    float armVal = pow(
        1.0 - 0.15 * sin((theta_r - angleR) * windingNum),
        3.0
    ) * exp(-rR * rR * 0.8) * exp(-0.05 / max(rR, 0.001));

    // Secondary arm structure (offset winding)
    float armVal2 = armVal * (
        0.5 + 0.15 * pow(
            1.0 - 0.15 * sin((theta_r - angleR) * (windingNum + 1.0)),
            2.5
        ) * exp(-rR * rR * 0.8) * exp(-0.05 / max(rR, 0.001))
    );

    // Smooth FBM dust lanes — was using ridged 1/abs(n) which created the "vein" look
    float dust = 0.0;
    {
        float f = 1.0;
        float result = 0.0;
        mat2 m2 = mat2(0.8, 0.6, -0.6, 0.8);
        vec2 dp = p * 8.0;
        for (int i = 1; i < 5; i++) {
            float n = snoise(dp * f);
            result += abs(n) / f;
            f += 1.0;
            dp = m2 * dp;
        }
        dust = 1.0 - result * 0.5;
    }

    // Central bulge — reduced intensity to avoid blown-out center
    float bulge = exp(-dot(p, p) * 1.2) * 0.5;
    vec2 bp = p;
    bp.y -= 0.2;
    bulge += 0.25 * exp(-dot(bp, bp) * 12.0);

    // Disk texture — smooth, not ridged
    float disk = 0.0;
    {
        float f = 1.0;
        for (int i = 1; i < 4; i++) {
            float n = snoise(p * f * 6.0);
            disk += abs(n) / f;
            f += 1.0;
        }
        disk = 1.0 / max(disk, 0.001);
    }

    float combined = max(
        armVal2 * (0.2 + 0.5 * dust + 0.3 * disk),
        bulge * (0.5 + 0.2 * dust)
    );

    // Star field — sparse bright points
    float stars = 0.0;
    {
        float sv = pow(max(snoise(p * 200.0), 0.0), 8.0);
        stars = armVal * sv;
    }
    combined = max(combined, stars);

    // Scale brightness
    combined *= (1.5 + u_tightness * 0.5) * (0.3 + 0.7 * u_thickness / 22.0);

    // Chaos modulation
    combined += u_chaos * snoise(p * 5.0 + u_time * 0.3) * 0.15;

    // Fade center singularity
    float fade = smoothstep(0.0, 0.03, r);
    combined *= fade * breath();

    // Color: warm core, cooler arms
    vec3 col;
    if (u_color_cycle < 0.5) {
        vec3 warm = vec3(1.0, 0.85, 0.6);
        float coreMix = exp(-r * r * 4.0);
        col = mix(u_base_color, warm, coreMix) * combined;
    } else {
        col = arm_color(r * 0.3 + u_time * 0.03, combined);
    }

    // Text overlay
    if (u_show_text == 1 && combined > 0.2) {
        float text_u = fract(angle / TWO_PI + u_time * 0.05);
        vec4 txt = sample_text(text_u, r * 0.3);
        col = mix(col, txt.rgb * 1.5, txt.a * combined * 0.7);
    }

    return vec4(col, combined * u_opacity * fade) * entrainmentModulation();
}
