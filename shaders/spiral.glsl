#version 330 core

// ── Uniforms ─────────────────────────────────────────────────────────────────
uniform float u_time;
uniform float u_tightness;
uniform float u_opacity;
uniform vec3  u_base_color;
uniform int   u_count;
uniform float u_chaos;
uniform vec2  u_resolution;
uniform int   u_style;
uniform float u_thickness;    // arm width multiplier (control panel 4–24 → 0.3–1.7)
uniform float u_beat_phase;   // 0.0–1.0, position in current beat cycle (for breathing)
uniform float u_entrainment_phase;
uniform float u_entrainment_strength;
uniform float u_color_cycle;  // 0 = use base_color directly, 1 = full hue cycle
// Doc 44 additions
uniform int   u_golden_spiral;          // 0 = archimedean, 1 = golden (logarithmic)
uniform float u_fractal_edge_amplitude; // 0.0 = off; >0 = fBm edge displacement
uniform float u_hue_shift;             // hue rotation offset (0–1 wrap)
// Looming
uniform float u_loom_scale;            // radial scale oscillator (1.0 = no effect)

// Text-on-spiral
uniform sampler2D u_text_tex;
uniform int       u_show_text;  // 0 = off, 1 = on

in  vec2 uv;
out vec4 fragColor;

#define PI      3.14159265359
#define TWO_PI  6.28318530718
#define PHI     1.61803398875   // golden ratio

// ── Helpers ───────────────────────────────────────────────────────────────────

// Cosine palette (Inigo Quilez)
vec3 palette(float t, vec3 a, vec3 b, vec3 c, vec3 d) {
    return a + b * cos(TWO_PI * (c * t + d));
}

// Aspect-correct centred coords
vec2 centred(vec2 fragUV) {
    vec2 p = fragUV * 2.0 - 1.0;
    p.x *= u_resolution.x / u_resolution.y;
    return p;
}

// Beat breathing envelope — smooth inhale/exhale curve from beat phase
float breath() {
    // Smooth pulse: rises quickly, falls slowly (like a heartbeat)
    float p = u_beat_phase;
    return 0.85 + 0.15 * (sin(p * TWO_PI - PI * 0.5) * 0.5 + 0.5);
}

float sinEnvelope(float phase) {
    return 0.5 + 0.5 * cos(phase * TWO_PI);
}

float entrainmentModulation() {
    float envelope = sinEnvelope(u_entrainment_phase);
    return mix(1.0, envelope, u_entrainment_strength);
}

// Color with direct base_color respect + optional hue shift
vec3 arm_color(float hue_offset, float brightness) {
    float h = hue_offset + u_hue_shift;   // apply compound CS hue shift
    if (u_color_cycle < 0.5) {
        // Direct: base_color with brightness variation only
        return u_base_color * brightness;
    } else {
        // Hue cycle biased toward base_color hue
        return palette(
            h,
            u_base_color * 0.5 + vec3(0.15),
            u_base_color * 0.45 + vec3(0.05),
            vec3(1.0, 1.0, 1.0),
            vec3(0.0, 0.33, 0.67)
        ) * brightness;
    }
}

// Sample text texture along arm UV coordinates
// arm_u: 0-1 position along the arm's length (tiled)
// arm_v: 0-1 cross-arm position (0=center, 1=edge)
vec4 sample_text(float arm_u, float arm_v) {
    if (u_show_text == 0) return vec4(0.0);
    // Center text vertically on arm (v=0.5 is arm center)
    float v = arm_v * 0.5 + 0.25;
    return texture(u_text_tex, vec2(fract(arm_u), clamp(v, 0.0, 1.0)));
}

// ── Noise Helpers ─────────────────────────────────────────────────────────────
// Pure-math noise functions — no texture dependencies.
// General-purpose: usable by any future style, not just Liminal.

vec3 permute_v3(vec3 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }

// 2D simplex noise — returns approximately [-1, 1]
// Based on Ashima Arts / Ian McEwan implementation
float snoise(vec2 v) {
    const vec4 C = vec4( 0.211324865405187,
                         0.366025403784439,
                        -0.577350269189626,
                         0.024390243902439);
    vec2 i  = floor(v + dot(v, C.yy));
    vec2 x0 = v - i + dot(i, C.xx);
    vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;
    i = mod(i, 289.0);
    vec3 p = permute_v3(permute_v3(i.y + vec3(0.0, i1.y, 1.0))
                                       + i.x + vec3(0.0, i1.x, 1.0));
    vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy),
                            dot(x12.zw, x12.zw)), 0.0);
    m = m * m;
    m = m * m;
    vec3 x_ = 2.0 * fract(p * C.www) - 1.0;
    vec3 h   = abs(x_) - 0.5;
    vec3 ox  = floor(x_ + 0.5);
    vec3 a0  = x_ - ox;
    m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
    vec3 g;
    g.x  = a0.x  * x0.x  + h.x  * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;
    return 130.0 * dot(m, g);
}

// Fractal Brownian Motion — 4 octaves with rotation between layers
// Rotation prevents axis-aligned artifacts
float fbm4(vec2 p) {
    float v = 0.0, a = 0.5;
    mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
    for (int i = 0; i < 4; i++) {
        v += a * snoise(p);
        p  = rot * p * 2.0;
        a *= 0.5;
    }
    return v;
}

// Voronoi distance field — returns distance to nearest cell edge
float voronoi_dist(vec2 p) {
    vec2  n  = floor(p);
    vec2  f  = fract(p);
    float md = 8.0;
    for (int j = -1; j <= 1; j++) {
        for (int i = -1; i <= 1; i++) {
            vec2 g = vec2(float(i), float(j));
            vec2 o = vec2(
                fract(sin(dot(n + g, vec2(127.1, 311.7))) * 43758.5453),
                fract(sin(dot(n + g, vec2(269.5, 183.3))) * 43758.5453)
            );
            vec2  r = g + o - f;
            float d = dot(r, r);
            md = min(md, d);
        }
    }
    return sqrt(md);
}

// ── Fractal edge displacement helper (Doc 44 §2.2) ────────────────────────
// Returns fBm edge displacement in [-1, 1]; applied to arm width as additive noise.
// Uses 3-octave fBm (faster than fbm4; arm edges don't need depth beyond octave 3).
float fractal_edge_noise(float arm_u, float r) {
    vec2  p  = vec2(arm_u * 8.0 + u_time * 0.1, r * 5.0);
    float n  = snoise(p) * 0.6 + snoise(p * 2.0 - u_time * 0.05) * 0.3
                                + snoise(p * 4.0 + u_time * 0.07) * 0.1;
    return n;  // approximately [-1, 1]
}

// ── Core arm distance field for Archimedean / Golden spiral ───────────────
// Returns: x = arm_dist (0 on arm), y = arm_u (0-1 along arm), z = arm_width
// When u_golden_spiral == 1, uses golden ratio growth r = r_min * exp(b*theta).
vec3 archimedean_field(vec2 p, float time_phase) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float arm_per   = TWO_PI / float(u_count);
    float phase;
    float arm_u;

    if (u_golden_spiral == 1) {
        // Golden (logarithmic) spiral: r = r_min * exp(b*theta)
        // theta = log(r / r_min) / b,  b = ln(phi) / (pi/2) ≈ 0.30635
        const float b     = 0.30634896;
        const float r_min = 0.02;
        float theta  = (r > r_min) ? log(max(r / r_min, 0.001)) / b : 0.0;
        float wobble = u_chaos * sin(theta * 1.5 + u_time * 0.9);
        phase   = theta - angle - time_phase + wobble;
        arm_u   = fract(theta / (arm_per * float(u_count)));
    } else {
        // Classic Archimedean spiral
        float wobble = u_chaos * sin(angle * 4.0 + r * 6.0 + u_time * 0.9)
                               * cos(r * 2.5 - u_time * 0.4);
        phase = r * u_tightness - angle - time_phase + wobble;
        arm_u = fract(phase / TWO_PI);
    }

    float arm_d_raw = mod(phase, arm_per) / arm_per;
    float arm_dist  = min(arm_d_raw, 1.0 - arm_d_raw);
    // Widened base so max-thickness setting visibly fills the space between arms
    float width     = (0.065 + r * 0.045) * u_thickness * breath();

    // Fractal edge displacement (Doc 44 §2.2)
    if (u_fractal_edge_amplitude > 0.001) {
        float noise  = fractal_edge_noise(arm_u, r);
        // Displace arm width — noise broadens edge at some points, narrows at others
        width = max(width * 0.3, width * (1.0 + u_fractal_edge_amplitude * noise));
    }

    return vec3(arm_dist, arm_u, width);
}

// ── Style 0 — TUNNEL DREAM ────────────────────────────────────────────────────
vec4 style_tunnel(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float depth = log(r + 0.001) * u_tightness * 0.5 - u_time * 1.4;
    // angle*count is seamless: sin(angle*n) has period 2π/n, completing n full
    // cycles per revolution — no atan discontinuity when count is integer.
    float twist = angle * float(u_count) + depth * TWO_PI * 0.6;
    float rings   = sin(depth * TWO_PI) * 0.5 + 0.5;
    float spokes  = sin(twist) * 0.5 + 0.5;
    float pattern = rings * 0.6 + spokes * 0.4;
    pattern += u_chaos * sin(angle * 6.0 + u_time * 2.0 + r * 4.0) * 0.2;
    float core = smoothstep(0.18 * u_thickness, 0.0, abs(pattern - 0.5));
    float halo = smoothstep(0.54 * u_thickness, 0.0, abs(pattern - 0.5)) * 0.4;
    float g    = (core + halo * (1.0 - core)) * breath();
    vec3  col  = arm_color(depth * 0.1 + u_time * 0.05, g * (0.7 + 0.3 * rings));
    return vec4(col, g * u_opacity * smoothstep(2.3, 0.2, r)) * entrainmentModulation();
}

// ── Style 1 — GALAXY ARMS ────────────────────────────────────────────────────
vec4 style_galaxy(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float log_r = log(max(r, 0.01));
    // k must be an integer so the atan seam (phase jump = 2π*k) is an exact
    // multiple of arm_per (= 2π/count), keeping arms continuous at angle=±π.
    float k     = round(float(u_count) * 0.5);
    float phase = log_r * u_tightness - angle * k
                  - u_time * 1.1
                  + u_chaos * sin(r * 5.0 + u_time);
    float arm_per  = TWO_PI / float(u_count);
    float arm_d    = mod(phase, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);
    float arm_u    = fract(phase / TWO_PI);
    float width    = (0.04 + r * 0.06) * u_thickness * breath();
    // Blend core + glow so they share the same pixel budget — no hard inner ring.
    float arm_core = smoothstep(width * 1.2, 0.0, arm_dist);
    float arm_glow = smoothstep(width * 3.5, 0.0, arm_dist) * 0.35;
    float arm      = arm_core + arm_glow * (1.0 - arm_core);
    // Width-proportional haze so it doesn't create a fixed stripe at large arm sizes
    float haze     = smoothstep(width * 5.0, 0.0, arm_dist) * 0.28 * smoothstep(0.05, 0.5, r);
    float core_glow = exp(-r * r * 6.0) * 2.0;
    // arm_u follows the log-spiral arm phase — seamless because phase jumps by
    // 2π*k (k integer) at the seam, which fract(phase/TWO_PI) fully absorbs.
    vec3 col = arm_color(arm_u + u_time * 0.04 + r * 0.2,
                         (arm + haze) * breath());
    col += vec3(0.9, 0.95, 1.0) * core_glow * u_base_color;
    float alpha = min(1.0, arm + haze + core_glow * 0.5) * u_opacity
                * smoothstep(2.1, 0.1, r);
    // Text overlay
    if (u_show_text == 1 && arm > 0.2) {
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * u_base_color * 1.5, txt.a * 0.7);
    }
    return vec4(col, alpha) * entrainmentModulation();
}

// ── Style 2 — ARCHIMEDEAN ────────────────────────────────────────────────────
vec4 style_archimedean(vec2 p) {
    vec3  field  = archimedean_field(p, u_time * 2.2);
    float arm_dist = field.x;
    float arm_u    = field.y;
    float width    = field.z;
    float arm_core = smoothstep(width * 1.2, 0.0, arm_dist);
    float arm_glow = smoothstep(width * 3.8, 0.0, arm_dist) * 0.25;
    float arm      = arm_core + arm_glow * (1.0 - arm_core);
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float pulse = 0.75 + 0.25 * sin(r * 3.0 - u_time * 1.5);
    vec3  col   = arm_color(r * 0.3 + u_time * 0.07, arm * pulse * breath());
    float fade  = smoothstep(2.0, 0.05, r) * smoothstep(0.0, 0.06, r);
    // Text overlay on arms
    if (u_show_text == 1 && arm > 0.15) {
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * 1.8, txt.a * arm * 0.85);
    }
    return vec4(col, arm * u_opacity * fade) * entrainmentModulation();
}

// ── Style 3 — KALEIDOSCOPE ────────────────────────────────────────────────────
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

// ── Style 4 — INTERFERENCE ────────────────────────────────────────────────────
vec4 style_interference(vec2 p) {
    float r1 = length(p);
    float a1 = atan(p.y, p.x);
    vec2  src2 = vec2(cos(u_time * 0.4), sin(u_time * 0.3)) * (0.3 + u_chaos * 0.4);
    float r2   = length(p - src2);
    float a2   = atan(p.y - src2.y, p.x - src2.x);
    float wave1 = sin(r1 * u_tightness * 2.0 - a1 * float(u_count) - u_time * 2.5);
    float wave2 = sin(r2 * u_tightness * 2.0 - a2 * float(u_count) + u_time * 2.0);
    float interference = (wave1 + wave2) * 0.5;
    float g = (smoothstep(-0.1, 0.6, interference)
             + smoothstep(0.7, 1.0, abs(interference)) * 0.4) * breath();
    vec3 col = arm_color(interference * 0.5 + u_time * 0.05, g);
    return vec4(col, g * u_opacity * smoothstep(1.7, 0.2, max(r1, r2)) * 0.85) * entrainmentModulation();
}

// ── Style 5 — ELECTRIC ───────────────────────────────────────────────────────
vec4 style_electric(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float noise = 0.0, freq = 1.0, amp = 1.0;
    for (int i = 0; i < 5; i++) {
        noise += sin(r * freq * 7.0 + angle * freq * 2.0
                     + u_time * (1.5 + freq * 0.3)) * amp;
        freq *= 2.0; amp *= 0.5;  // integer doubling keeps angle*freq*2 seamless
    }
    noise *= u_chaos * 0.5 + 0.1;
    float phase    = r * u_tightness - angle - u_time * 2.5 + noise;
    float arm_per  = TWO_PI / float(u_count);
    float arm_d    = mod(phase, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);
    float width    = (0.025 + abs(noise) * 0.03) * u_thickness * breath();
    float arm   = smoothstep(width * 1.4, 0.0, arm_dist);
    // Spark only fills the gap beyond the core — no double-bright stripe
    float spark = smoothstep(width * 4.5, 0.0, arm_dist) * 0.2 * (1.0 - arm);
    // Electric: always white-blue, base_color tints the core
    vec3 col = mix(u_base_color, vec3(0.8, 0.9, 1.0), arm)
             + vec3(0.9, 0.9, 1.0) * spark;
    col *= 1.0 + arm * 1.5 * breath();
    return vec4(col, (arm + spark) * u_opacity * smoothstep(2.0, 0.04, r)) * entrainmentModulation();
}

// ── Style 6 — VORTEX ─────────────────────────────────────────────────────────
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
    return vec4(col, (g + core * 0.45) * u_opacity * smoothstep(2.35, 0.0, r)) * entrainmentModulation();
}

// ── Style 7 — DNA ─────────────────────────────────────────────────────────────
vec4 style_dna(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float arm_per = TWO_PI / float(u_count);
    float w       = (0.04 + u_chaos * 0.02) * u_thickness * breath();

    float phase_a = r * u_tightness - angle - u_time * 2.0;
    float phase_b = r * u_tightness + angle + u_time * 2.0;
    float d_a = min(mod(phase_a,arm_per)/arm_per, 1.0-mod(phase_a,arm_per)/arm_per);
    float d_b = min(mod(phase_b,arm_per)/arm_per, 1.0-mod(phase_b,arm_per)/arm_per);
    float helix_a = smoothstep(w, 0.0, d_a);
    float helix_b = smoothstep(w, 0.0, d_b);
    float rung_d  = fract(r * u_tightness * 2.0 - u_time * 1.5);
    float rung    = smoothstep(0.15, 0.0, min(rung_d, 1.0-rung_d))
                  * smoothstep(0.0, 0.04, d_a + d_b) * 0.6;

    // phase_a/TWO_PI jumps by ±count (integer) at the seam → fract absorbs it.
    // phase_b/TWO_PI does the same. Both helices seamless with no angle term needed.
    vec3 col_a = arm_color(fract(phase_a / TWO_PI) + u_time*0.05,        helix_a * breath());
    vec3 col_b = arm_color(fract(phase_b / TWO_PI) + 0.5 + u_time*0.05,  helix_b * breath());
    vec3 col   = col_a + col_b + vec3(0.9,0.9,1.0) * rung * u_base_color;

    // Text on helix_a
    if (u_show_text == 1 && helix_a > 0.2) {
        float arm_u = fract(phase_a / TWO_PI);
        vec4  txt   = sample_text(arm_u, d_a / max(w, 0.001));
        col = mix(col, txt.rgb * 1.6, txt.a * helix_a * 0.8);
    }
    float fade = smoothstep(2.0, 0.05, r) * smoothstep(0.0, 0.06, r);
    return vec4(col, (helix_a + helix_b + rung) * u_opacity * fade) * entrainmentModulation();
}

// ── Style 8 — FIBONACCI (golden ratio logarithmic spiral) ─────────────────────
// Distinct from galaxy: uses exact phi growth rate, tighter golden arm spacing,
// and a signature petal/sunflower symmetry based on Fibonacci angles.
vec4 style_fibonacci(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Golden angle ≈ 137.5° — Fibonacci phyllotaxis
    float golden_angle = PI * (3.0 - sqrt(5.0));

    // Logarithmic spiral with phi growth rate
    float log_r  = log(max(r, 0.01));
    float phase  = log_r * u_tightness * PHI - angle - u_time * 0.9
                 + u_chaos * sin(r * 4.0 + u_time * 0.7);

    // arm_per must divide 2π evenly so the atan seam (phase jump = 2π) lands
    // on an exact arm period boundary. golden_angle is irrational w.r.t. 2π,
    // so we use u_count-equal spacing while keeping the phi logarithmic growth.
    float arm_per  = TWO_PI / float(u_count);
    float arm_d    = mod(phase, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);
    // fract(phase/TWO_PI): seam jump is exactly 1 full period → fract absorbs it.
    // (TWO_PI*PHI divisor caused a 0.618 jump in arm_u, visible as color stripe.)
    float arm_u    = fract(phase / TWO_PI);

    // Width narrows in center, blooms at outer edge like a petal
    // Floor at 0.06 prevents invisible sub-pixel arms at center
    float width    = max(0.06, (0.03 + r * 0.08 * PHI)) * u_thickness * breath();
    float arm_core = smoothstep(width * 1.2, 0.0, arm_dist);
    float arm_glow = smoothstep(width * 3.0, 0.0, arm_dist) * 0.4;
    float arm      = arm_core + arm_glow * (1.0 - arm_core);
    // Fade arms inside r=0.15 where packing is too dense to resolve
    arm *= smoothstep(0.08, 0.25, r);

    // Secondary: radial center-glow (replaces phyllotaxis dot — angle/golden_angle
    // is not 2π-periodic so it created a hard seam at the atan branch cut).
    float dot = exp(-r * r * 5.0) * 0.6;

    float brightness = (arm + dot) * breath();

    // Declare warm/cool at function scope — text overlay also uses warm.
    vec3 warm = u_base_color * vec3(1.0, 0.85, 0.5);
    vec3 cool = u_base_color * vec3(0.5, 0.8, 1.0);

    // Respect the color mode toggle — arm_u is seamless (fract(phase/TWO_PI)).
    vec3 col;
    if (u_color_cycle < 0.5) {
        col = u_base_color * brightness;
    } else {
        col = mix(warm, cool, arm_u) * brightness;
    }

    float core_glow = exp(-r * r * 8.0) * 1.5;
    col += u_base_color * core_glow;

    if (u_show_text == 1 && arm > 0.15) {
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * warm * 2.0, txt.a * arm * 0.75);
    }
    float fade = smoothstep(2.1, 0.05, r) * smoothstep(0.0, 0.05, r);
    return vec4(col, (arm + dot * 0.5) * u_opacity * fade) * entrainmentModulation();
}

// ── Style 9 — BLOOM (Polar Rose) ─────────────────────────────────────────────
// Four petal layers rotating at different speeds — as they drift through each
// other they create organic, ever-changing flower patterns.
// u_tightness controls the speed spread between layers (slow ↔ dramatic sweep).
// cos(k*angle) is 2π-periodic for integer k → seamless on all layers.
vec4 style_rose(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float k     = float(u_count);
    float width = (0.020 + r * 0.013) * u_thickness;

    float g       = 0.0;
    float hue_acc = 0.0;

    for (int i = 0; i < 4; i++) {
        float fi = float(i);

        // Speed differential: tightness spreads layers apart so they orbit differently
        float speed  = 0.38 + fi * (0.12 + u_tightness * 0.07);
        // Each layer has a chaos cross-harmonic at 2k (still integer → seamless)
        float raw    = cos(k * angle - u_time * speed)
                     + u_chaos * 0.22 * cos(k * 2.0 * angle - u_time * speed * 1.7 + fi * 1.1);
        float rose_r = max(raw, 0.0) * (1.20 - fi * 0.13) * breath();

        // Solid fill: smooth gradient dark→bright toward the petal edge
        float inside = step(r, rose_r);
        float fill   = inside * smoothstep(0.0, rose_r, r) * 0.58;

        float dist  = abs(r - rose_r);
        float edge  = smoothstep(width * 1.2, 0.0, dist);
        float halo  = smoothstep(width * 4.5, 0.0, dist) * 0.30 * (1.0 - inside);

        float layer = edge + fill * (1.0 - edge) + halo * (1.0 - edge) * (1.0 - inside);
        g       = g + layer * (1.0 - g) * (1.05 - fi * 0.12);
        hue_acc += rose_r * (1.2 - fi * 0.15);
    }

    g += exp(-r * r * 8.0) * 0.85;

    // hue_acc is a weighted sum of all layer radii — seamless and always moving
    vec3 col = arm_color(fract(hue_acc * 0.28 + r * 0.14 - u_time * 0.05), g * breath());
    return vec4(col, g * u_opacity * smoothstep(2.25, 0.03, r)) * entrainmentModulation();
}

// ── Style 10 — MOIRÉ ─────────────────────────────────────────────────────────
// Two counter-rotating spirals with a slight tightness offset.
// The phase difference grows with r → slowly shifting concentric beat rings.
vec4 style_moire(vec2 p) {
    float r      = length(p);
    float angle  = atan(p.y, p.x);
    float ap     = TWO_PI / float(u_count);

    float tight2 = u_tightness * (1.0 + 0.07 + u_chaos * 0.03);

    // CW — angle coef -1, seam jump +2π = count * ap → seamless
    float ph1  = r * u_tightness - angle - u_time * 1.1;
    float d1   = min(mod(ph1, ap) / ap, 1.0 - mod(ph1, ap) / ap);

    // CCW — angle coef +1, seam jump -2π = -count * ap → seamless
    float ph2  = r * tight2 + angle - u_time * 0.85;
    float d2   = min(mod(ph2, ap) / ap, 1.0 - mod(ph2, ap) / ap);

    float width = (0.020 + r * 0.014) * u_thickness * breath();

    float c1 = smoothstep(width * 1.2, 0.0, d1);
    float h1 = smoothstep(width * 3.5, 0.0, d1) * 0.30;
    float arm1 = c1 + h1 * (1.0 - c1);

    float c2 = smoothstep(width * 1.2, 0.0, d2);
    float h2 = smoothstep(width * 3.5, 0.0, d2) * 0.30;
    float arm2 = c2 + h2 * (1.0 - c2);

    // Beat: bright flare where both cores cross
    float beat = c1 * c2 * 2.8;

    float g = arm1 + arm2 * (1.0 - arm1);
    g = (g + beat * (1.0 - g)) * breath();

    // Complementary hues on each spiral — chromatic moiré
    vec3 col1 = arm_color(fract(ph1 / TWO_PI) + u_time * 0.03, arm1 * breath());
    vec3 col2 = arm_color(fract(ph2 / TWO_PI) + 0.5 + u_time * 0.03, arm2 * breath());
    vec3 col_b = arm_color(r * 0.15 + u_time * 0.07, beat);
    vec3 col   = col1 + col2 * (1.0 - arm1) + col_b;

    return vec4(col, g * u_opacity * smoothstep(2.2, 0.1, r)) * entrainmentModulation();
}

// ── Style 11 — SPIROGRAPH ────────────────────────────────────────────────────
// True hypotrochoid: inner gear r_i = R/(n+1), pen at d_pen.
// Integer n ensures cos(n*t) is 2π-periodic → seamless.
// Samples n symmetry branches (same set on both seam sides) for min-dist.
vec4 style_spirograph(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float n     = float(u_count);

    float R_o   = 0.78;
    float r_i   = R_o / (n + 1.0);
    float arm_r = R_o - r_i;                             // n/(n+1)*R_o
    // d_pen scaled to arm_r so it sweeps a large portion of the canvas.
    // u_tightness 1→5 maps pen from ~28% to ~90% of orbit radius.
    float d_pen = arm_r * clamp(0.15 + u_tightness * 0.15, 0.12, 0.92);

    float min_dist = 100.0;
    for (int k = 0; k < 8; k++) {
        float fk    = float(k);
        float valid = step(fk, n - 0.5);
        float t     = angle + fk * TWO_PI / n - u_time * 0.30;
        float phi   = -n * t + u_chaos * sin(t) * 0.35;
        vec2 pt     = vec2(arm_r * cos(t) + d_pen * cos(phi),
                           arm_r * sin(t) + d_pen * sin(phi));
        float dk    = mix(100.0, length(p - pt), valid);
        min_dist    = min(min_dist, dk);
    }

    float width = max(0.028, (0.028 + r * 0.018) * u_thickness) * breath();
    float core  = smoothstep(width * 1.3, 0.0, min_dist);
    float halo  = smoothstep(width * 5.0, 0.0, min_dist) * 0.45;
    float g     = core + halo * (1.0 - core);
    g += exp(-r * r * 8.0) * 0.75;
    g *= breath();

    vec3 col = arm_color(fract(r * 0.30 + u_time * 0.04), g);
    return vec4(col, g * u_opacity * smoothstep(2.25, 0.02, r) * smoothstep(0.0, 0.04, r)) * entrainmentModulation();
}

// ── Style 12 — FERMAT ────────────────────────────────────────────────────────
// Fermat spiral: r ∝ √θ, so phase uses r² instead of r.
// Arms pack densely at the center and open at the edge — opposite density to
// Archimedean. angle coef -1, seam jump +2π = count arm periods → seamless.
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

    float alpha = (arm + core_glow * 0.4) * u_opacity * smoothstep(2.2, 0.02, r);
    return vec4(col, alpha) * entrainmentModulation();
}

// ── Style 13 — SUPERFORMULA ──────────────────────────────────────────────────
// Gielis superformula with angle*0.5 so the shape closes in 2π.
// abs(cos(m*θ/2)) is seamless for integer m (cos(-mπ) = ±1, abs → always =|cos|).
// u_tightness controls pointiness: low = rounded blob, high = sharp star.
vec4 style_superformula(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float m     = float(u_count);

    // Slow rotation: angle offset is continuous, seam analysis unchanged
    // (abs(cos(m*(angle-time*0.5)*0.5)) still seamless for integer m)
    float angle_rot = angle - u_time * 0.18;

    // n slides from blob (n≈0.4) to star (n≈3.5) via tightness
    float n  = clamp(u_tightness * 0.55, 0.30, 3.80);
    float ca = pow(max(abs(cos(m * angle_rot * 0.5)), 0.001), n);
    float sa = pow(max(abs(sin(m * angle_rot * 0.5)), 0.001), n);
    float r_sf = pow(ca + sa, -1.0 / n) * 1.02;

    // Breathe and add chaos wobble (r-based, no seam)
    r_sf *= (0.88 + 0.12 * breath())
          * (1.0 + u_chaos * 0.09 * sin(r * 3.5 + u_time * 0.9));

    float width = (0.022 + r_sf * 0.028) * u_thickness;

    // Three nested copies at decreasing scales for visual mass and depth
    float g = 0.0;
    for (int i = 0; i < 3; i++) {
        float fi  = float(i);
        float sc  = pow(0.58, fi);          // scales: 1.0, 0.58, 0.336
        float r_s = r_sf * sc;
        float w_s = width * pow(0.78, fi);

        // Solid fill — strong gradient from center to boundary
        float ins  = step(r, r_s);
        float fill = ins * pow(max(r / max(r_s, 0.001), 0.0), 0.45) * (0.65 - fi * 0.12);

        float d_s  = abs(r - r_s);
        float edge = smoothstep(w_s * 1.2, 0.0, d_s);
        float halo = smoothstep(w_s * 5.0, 0.0, d_s) * 0.40 * (1.0 - ins);

        float layer = edge + fill * (1.0 - edge) + halo * (1.0 - edge) * (1.0 - ins);
        g = g + layer * (1.0 - g) * (1.0 - fi * 0.15);
    }

    g += exp(-r * r * 10.0) * 0.65;
    g *= breath();

    // r_sf varies with angle (seamless) — gives each lobe a hue offset
    vec3 col = arm_color(fract(r_sf * 0.6 + r * 0.20 - u_time * 0.05), g);
    // Softer outer fade — was eating ~44% alpha at the main body radius
    return vec4(col, g * u_opacity * smoothstep(1.90, 0.70, r)) * entrainmentModulation();
}

// ── Style 14 — LIMINAL ────────────────────────────────────────────────────────
// Logarithmic spiral + simplex noise domain warping + Voronoi lattice emergence.
// Targets Kluver form constants II (spiral) and III (lattice/honeycomb).
// u_chaos morphs from geometric order (0.0) to organic complexity (1.0).
// beat_phase drives structural warp deformation — the visual breathes as a whole.
//
// Designed by Research as a contribution to the Somna codebase.

vec4 style_liminal(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Beat-phase structural breathing — warp deformation coupled to beat cycle
    float warp_breath = 0.7 + 0.3 * breath();

    // ── Layer 1: Domain-warped logarithmic spiral ─────────────────────────
    // Inigo Quilez nested domain warping: fbm(p + fbm(p + offset))
    float time_slow = u_time * 0.15;

    vec2 warp1 = vec2(
        fbm4(p * 2.0 + vec2(time_slow, 0.0)),
        fbm4(p * 2.0 + vec2(0.0, time_slow))
    );
    vec2 warp2 = vec2(
        fbm4(p * 2.0 + warp1 * 2.0 + vec2(1.7, 9.2) + time_slow * 0.8),
        fbm4(p * 2.0 + warp1 * 2.0 + vec2(8.3, 2.8) + time_slow * 0.6)
    );

    vec2 warped_p = p + u_chaos * warp2 * 0.4 * warp_breath;

    float wr     = length(warped_p);
    float wangle = atan(warped_p.y, warped_p.x);

    // Logarithmic spiral field on warped coordinates
    float log_r   = log(max(wr, 0.01));
    float phase   = log_r * u_tightness * 1.5 - wangle - u_time * 0.8;
    float arm_per = TWO_PI / float(u_count);
    float arm_d   = mod(phase, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);
    float arm_u    = fract(phase / TWO_PI);

    float width    = (0.04 + wr * 0.05) * u_thickness * breath();
    float arm_core = smoothstep(width * 1.3, 0.0, arm_dist);
    float arm_glow = smoothstep(width * 4.0, 0.0, arm_dist) * 0.3;
    float spiral   = arm_core + arm_glow * (1.0 - arm_core);

    // ── Layer 2: Voronoi lattice emergence (Kluver Form Constant III) ─────
    // Emerges as chaos increases — uses warped coordinates so it breathes
    // in structural harmony with the spiral.
    float vor_scale = 3.0 + u_tightness * 0.5;
    vec2  vor_p = warped_p * vor_scale + vec2(u_time * 0.1);
    float vor   = voronoi_dist(vor_p);

    float lattice_edge = 1.0 - smoothstep(0.0, 0.25, vor);
    float lattice_fill = smoothstep(0.0, 0.6, vor) * 0.15;
    // Quadratic fade-in: lattice invisible at low chaos, prominent at high
    float lattice = (lattice_edge * 0.7 + lattice_fill) * u_chaos * u_chaos;

    // ── Composite ─────────────────────────────────────────────────────────
    // Low chaos: pure spiral. High chaos: spiral + lattice overlay.
    // (1.0 - spiral * 0.5) prevents oversaturation where both layers meet.
    float g = spiral + lattice * (1.0 - spiral * 0.5);
    g *= breath();

    // Core convergence glow
    float core = exp(-r * r * 5.0) * 1.2;
    g += core * (1.0 - g * 0.5);

    // ── Color ─────────────────────────────────────────────────────────────
    // Warp field drives organic hue variation — visual coherence: the same
    // field that distorts geometry also colors the surface.
    float hue_warp = fbm4(p * 1.5 + vec2(u_time * 0.08)) * u_chaos;
    vec3 col = arm_color(
        arm_u + hue_warp * 0.3 + r * 0.15 + u_time * 0.03,
        g
    );

    // Lattice gets shifted hue — visual separation from spiral arms
    vec3 lattice_col = arm_color(
        vor * 0.5 + u_time * 0.02 + 0.5,
        lattice * breath()
    );
    col = mix(col, lattice_col, u_chaos * u_chaos * 0.4);

    // Core glow in base_color
    col += u_base_color * core * 0.6;

    // ── Text overlay ──────────────────────────────────────────────────────
    if (u_show_text == 1 && spiral > 0.15) {
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * u_base_color * 1.5, txt.a * spiral * 0.75);
    }

    float fade = smoothstep(2.2, 0.05, r) * smoothstep(0.0, 0.05, r);
    return vec4(col, g * u_opacity * fade) * entrainmentModulation();
}

// ── Curl-noise helper (used by style_nebula only) ────────────────────────────
// Divergence-free velocity field derived from finite differences of snoise.
// eps=0.25 gives gradient magnitudes ~O(1) after the 1/(2*eps) normalisation.
vec2 curl_noise(vec2 p, float t) {
    const float eps = 0.25;
    float n1 = snoise(p + vec2( eps, 0.0) + vec2(t * 0.11, 0.0));
    float n2 = snoise(p + vec2(-eps, 0.0) + vec2(t * 0.11, 0.0));
    float n3 = snoise(p + vec2(0.0,  eps) + vec2(0.0, t * 0.09));
    float n4 = snoise(p + vec2(0.0, -eps) + vec2(0.0, t * 0.09));
    // (∂f/∂y, -∂f/∂x) — divide by 2*eps to normalize to gradient scale
    return vec2(n3 - n4, n2 - n1) / (2.0 * eps) * (0.08 + u_chaos * 0.22);
}

// ── Style 15 — RESONANT STANDING-WAVE SPIRAL ─────────────────────────────────
// Phase field is perturbed by a golden-ratio harmonic series, creating
// standing-wave nodes that throb at beat phase.  Arms locally pinch and widen
// at constructive interference points — completely unlike the existing styles.
vec4 style_resonant(vec2 p) {
    float r      = length(p);
    float angle  = atan(p.y, p.x);
    // Standard Archimedean phase, angular coefficient = 1 for correct arm count
    float phase   = r * u_tightness * 1.8 - angle - u_time * 1.1;
    float arm_per = TWO_PI / float(u_count);

    // Golden-ratio harmonic series — irrational frequencies never repeat
    float wave = 0.0;
    for (int i = 1; i <= 5; i++) {
        float k = float(i) * PHI;
        wave += sin(phase * k) * pow(0.7, float(i));
        wave += sin(phase * k * 1.5 + u_beat_phase * TWO_PI) * 0.28 * pow(0.75, float(i));
    }
    // Raw amplitude peaks ~±3.4; normalise to [0, 1]
    wave = clamp(wave * 0.18 + 0.5, 0.0, 1.0);

    // Crystalline nodes at constructive interference — sharpened with pow
    float nodes = pow(abs(sin(phase * 3.0 * PHI)), 4.0);

    // Arm field perturbed by wave — shifts arm positions by up to 1.5 periods
    float arm_d    = mod(phase + wave * arm_per * 1.5, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);

    float width = (0.035 + r * 0.055) * u_thickness * breath();
    // Wave-modulated edges: pinch/widen at node crests
    width = max(width * 0.25, width * (1.0 + 0.55 * sin(wave * TWO_PI * 2.0)));

    float core = smoothstep(width * 1.1, 0.0, arm_dist);
    float glow = smoothstep(width * 4.5, 0.0, arm_dist) * 0.40;
    float arm  = core + glow * (1.0 - core);

    float beat_mod = 1.8 + sin(u_beat_phase * TWO_PI * 3.0) * 0.7;
    float flare    = nodes * core * beat_mod;

    float hue = fract(phase / TWO_PI) + wave * 0.4;
    float bri = clamp((arm + flare * 0.6) * breath(), 0.0, 2.0);
    vec3  col = arm_color(hue, bri);
    col += u_base_color * flare * 1.8;

    float alpha = clamp(arm + flare * 0.5, 0.0, 1.0) * u_opacity
                * smoothstep(2.3, 0.06, r) * smoothstep(0.0, 0.06, r);

    if (u_show_text == 1 && arm > 0.22) {
        float arm_u = fract(phase / TWO_PI);
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * u_base_color * 2.0, txt.a * arm);
    }
    return vec4(col, alpha) * entrainmentModulation();
}

// ── Style 16 — CURL-FLOW NEBULA SPIRAL ───────────────────────────────────────
// Logarithmic spiral advected by a curl-noise flow field.  Arms drift and
// reform like plasma in a magnetic vortex.  Two-layer composite: geometric
// arms + fBm nebula density.  No other style uses incompressible flow.
vec4 style_nebula(vec2 p) {
    float t = u_time * 0.6;

    // Curl advection — displaces the sample point in an incompressible field
    vec2 flow   = curl_noise(p * (1.8 + u_chaos), t) * 0.55;
    vec2 warped = p + flow;

    float r      = length(warped);
    float angle  = atan(warped.y, warped.x);
    float log_r  = log(max(r, 0.02));
    // Standard log-spiral phase (coefficient 1 on angle for correct arm count)
    float phase   = log_r * u_tightness * 1.65 - angle - t * 0.9;
    float arm_per = TWO_PI / float(u_count);

    // Low-frequency organic perturbation following the flow field
    float organic = fbm4(warped * 2.0 + vec2(t * 0.13, 0.0)) * u_chaos;
    // Scale by arm_per so perturbation is count-independent (max ~±1.5 periods)
    float arm_d    = mod(phase + organic * arm_per * 1.5, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);

    float width = (0.028 + r * 0.070) * u_thickness * breath();
    // Organic field melts edges; guard against zero width
    width = max(width * 0.15, width * (1.0 + organic * 0.85));

    float core = smoothstep(width * 1.15, 0.0, arm_dist);
    float glow = smoothstep(width * 5.0, 0.0, arm_dist) * 0.35;
    float arm  = core + glow * (1.0 - core);

    // Nebula density: fBm cloud advected by the same curl field
    float nebula = fbm4(warped * 3.8 + flow * 6.0) * 0.5 + 0.5;
    nebula = pow(clamp(nebula, 0.0, 1.0), 2.0) * (1.0 - smoothstep(0.0, 1.2, r));

    float total = clamp(arm + nebula * (1.0 - arm * 0.55), 0.0, 1.2);

    // Hue follows flow direction — same field that warps geometry colors it
    float hue_flow = fract(angle * 0.8 + length(flow) * 3.0);
    vec3  col = arm_color(hue_flow + t * 0.04, total * breath() * 1.1);
    col += u_base_color * exp(-r * r * 5.5) * 1.8;

    float alpha = clamp(total, 0.0, 1.0) * u_opacity * smoothstep(2.25, 0.05, r);

    if (u_show_text == 1 && arm > 0.18) {
        float arm_u = fract(phase / TWO_PI);
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * 2.2, txt.a * arm * 0.8);
    }
    return vec4(col, alpha) * entrainmentModulation();
}

// ── Style 17 — BIFURCATING GOLDEN FRACTAL SPIRAL ─────────────────────────────
// Each arm spawns self-similar child arms at golden-ratio phase offsets.
// Four levels of fractal detail via a per-level over-composite loop —
// constant GPU cost regardless of zoom.
vec4 style_bifurcate(vec2 p) {
    float r     = length(p);
    float angle = atan(p.y, p.x);

    // Golden logarithmic spiral (equiangular constant matching archimedean_field)
    const float b = 0.30634896;
    float log_r = log(max(r, 0.015));
    float theta = log_r / b;
    float phase = theta - angle - u_time * 0.85 + u_chaos * sin(theta * 2.0);

    float arm_per  = TWO_PI / float(u_count);
    float arm_d    = mod(phase, arm_per) / arm_per;
    float arm_dist = min(arm_d, 1.0 - arm_d);
    float width    = (0.032 + r * 0.036) * u_thickness * breath();
    float main_arm = smoothstep(width * 1.25, 0.0, arm_dist);

    // Bifurcation: 4 self-similar child levels via PHI phase multiplication.
    // Each level contributes independently; blended with Porter-Duff over.
    float child_total = 0.0;
    float cs = 0.60;  // per-level brightness weight; shrinks by golden ratio
    for (int i = 0; i < 4; i++) {
        float child_phase = phase * PHI + float(i) * PHI;
        float cad = mod(child_phase, arm_per) / arm_per;
        float cd  = min(cad, 1.0 - cad);
        // Each level progressively thinner
        float cw  = max(width * (1.6 - float(i) * 0.22), 0.005);
        float c   = smoothstep(cw, 0.0, cd) * cs;
        child_total += c * (1.0 - child_total);
        cs *= 0.618;
    }
    float child_arm = child_total * 0.70;
    float total     = main_arm + child_arm * (1.0 - main_arm * 0.65);

    vec3  col = arm_color(fract(theta * 0.28 + u_time * 0.06), total * breath());
    // Glow at bifurcation intersections — brightest where child meets parent
    float bifur_glow = child_arm * main_arm * 3.5;
    col += u_base_color * bifur_glow;

    float alpha = clamp(total + bifur_glow * 0.3, 0.0, 1.0) * u_opacity
                * smoothstep(2.35, 0.04, r);

    if (u_show_text == 1 && total > 0.22) {
        float arm_u = fract(phase / TWO_PI);
        vec4 txt = sample_text(arm_u, arm_dist / max(width, 0.001));
        col = mix(col, txt.rgb * u_base_color * 2.2, txt.a * total * 0.75);
    }
    return vec4(col, alpha) * entrainmentModulation();
}

// ── Main ──────────────────────────────────────────────────────────────────────
void main() {
    vec2 p = centred(uv);

    // Looming: scale p radially so the pattern rhythmically approaches/recedes.
    // u_loom_scale < 1.0 → spiral appears larger (coming toward viewer)
    // u_loom_scale > 1.0 → spiral appears smaller (receding)
    p *= u_loom_scale;

    vec4 result;
    if      (u_style == 0)  result = style_tunnel(p);
    else if (u_style == 1)  result = style_galaxy(p);
    else if (u_style == 2)  result = style_archimedean(p);
    else if (u_style == 3)  result = style_kaleidoscope(p);
    else if (u_style == 4)  result = style_interference(p);
    else if (u_style == 5)  result = style_electric(p);
    else if (u_style == 6)  result = style_vortex(p);
    else if (u_style == 7)  result = style_dna(p);
    else if (u_style == 8)  result = style_fibonacci(p);
    else if (u_style == 9)  result = style_rose(p);
    else if (u_style == 10) result = style_moire(p);
    else if (u_style == 11) result = style_spirograph(p);
    else if (u_style == 12) result = style_fermat(p);
    else if (u_style == 13) result = style_superformula(p);
    else if (u_style == 15) result = style_resonant(p);
    else if (u_style == 16) result = style_nebula(p);
    else if (u_style == 17) result = style_bifurcate(p);
    else                    result = style_liminal(p);  // u_style == 14 + unknown

    fragColor = result;
}
