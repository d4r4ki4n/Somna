#version 330 core

// ── Shared uniforms ──────────────────────────────────────────────────────────
uniform float u_time;
uniform float u_tightness;
uniform float u_opacity;
uniform vec3  u_base_color;
uniform int   u_count;
uniform float u_chaos;
uniform vec2  u_resolution;
uniform int   u_style;
uniform float u_thickness;
uniform float u_beat_phase;
uniform float u_color_cycle;
uniform int   u_golden_spiral;
uniform float u_fractal_edge_amplitude;
uniform float u_hue_shift;
uniform float u_loom_scale;

uniform sampler2D u_text_tex;
uniform int       u_show_text;

in  vec2 uv;
out vec4 fragColor;

#define PI      3.14159265359
#define TWO_PI  6.28318530718
#define PHI     1.61803398875

// ── Shared helpers ───────────────────────────────────────────────────────────

vec3 palette(float t, vec3 a, vec3 b, vec3 c, vec3 d) {
    return a + b * cos(TWO_PI * (c * t + d));
}

vec2 centred(vec2 fragUV) {
    vec2 p = fragUV * 2.0 - 1.0;
    p.x *= u_resolution.x / u_resolution.y;
    return p;
}

float breath() {
    float p = u_beat_phase;
    return 0.85 + 0.15 * (sin(p * TWO_PI - PI * 0.5) * 0.5 + 0.5);
}

vec3 arm_color(float hue_offset, float brightness) {
    float h = hue_offset + u_hue_shift;
    if (u_color_cycle < 0.5) {
        return u_base_color * brightness;
    } else {
        return palette(
            h,
            u_base_color * 0.5 + vec3(0.15),
            u_base_color * 0.45 + vec3(0.05),
            vec3(1.0, 1.0, 1.0),
            vec3(0.0, 0.33, 0.67)
        ) * brightness;
    }
}

vec4 sample_text(float arm_u, float arm_v) {
    if (u_show_text == 0) return vec4(0.0);
    float v = arm_v * 0.5 + 0.25;
    return texture(u_text_tex, vec2(fract(arm_u), clamp(v, 0.0, 1.0)));
}

// ── Noise ────────────────────────────────────────────────────────────────────

vec3 permute_v3(vec3 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }

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

// ── Fractal edge displacement ────────────────────────────────────────────────

float fractal_edge_noise(float arm_u, float r) {
    vec2  p  = vec2(arm_u * 8.0 + u_time * 0.1, r * 5.0);
    float n  = snoise(p) * 0.6 + snoise(p * 2.0 - u_time * 0.05) * 0.3
                                + snoise(p * 4.0 + u_time * 0.07) * 0.1;
    return n;
}

// ── Core arm distance field ──────────────────────────────────────────────────

vec3 archimedean_field(vec2 p, float time_phase) {
    float r     = length(p);
    float angle = atan(p.y, p.x);
    float arm_per   = TWO_PI / float(u_count);
    float phase;
    float arm_u;

    if (u_golden_spiral == 1) {
        const float b     = 0.30634896;
        const float r_min = 0.02;
        float theta  = (r > r_min) ? log(max(r / r_min, 0.001)) / b : 0.0;
        float wobble = u_chaos * sin(theta * 1.5 + u_time * 0.9);
        phase   = theta - angle - time_phase + wobble;
        arm_u   = fract(theta / (arm_per * float(u_count)));
    } else {
        float wobble = u_chaos * sin(angle * 4.0 + r * 6.0 + u_time * 0.9)
                               * cos(r * 2.5 - u_time * 0.4);
        phase = r * u_tightness - angle - time_phase + wobble;
        arm_u = fract(phase / TWO_PI);
    }

    float arm_d_raw = mod(phase, arm_per) / arm_per;
    float arm_dist  = min(arm_d_raw, 1.0 - arm_d_raw);
    float width     = (0.065 + r * 0.045) * u_thickness * breath();

    if (u_fractal_edge_amplitude > 0.001) {
        float noise  = fractal_edge_noise(arm_u, r);
        width = max(width * 0.3, width * (1.0 + u_fractal_edge_amplitude * noise));
    }

    return vec3(arm_dist, arm_u, width);
}

// ── Curl noise (nebula) ─────────────────────────────────────────────────────

vec2 curl_noise(vec2 p, float t) {
    const float eps = 0.25;
    float n1 = snoise(p + vec2( eps, 0.0) + vec2(t * 0.11, 0.0));
    float n2 = snoise(p + vec2(-eps, 0.0) + vec2(t * 0.11, 0.0));
    float n3 = snoise(p + vec2(0.0,  eps) + vec2(0.0, t * 0.09));
    float n4 = snoise(p + vec2(0.0, -eps) + vec2(0.0, t * 0.09));
    return vec2(n3 - n4, n2 - n1) / (2.0 * eps) * (0.08 + u_chaos * 0.22);
}

// ── Oklab perceptual color space (Ottosson 2020) ────────────────────────────

vec3 rgbToOklab(vec3 c) {
    float l = 0.4122214708 * c.r + 0.5363325363 * c.g + 0.0514459929 * c.b;
    float m = 0.2119034982 * c.r + 0.6806995451 * c.g + 0.1073969566 * c.b;
    float s = 0.0883024619 * c.r + 0.2220049168 * c.g + 0.6968735794 * c.b;
    l = pow(l, 1.0/3.0); m = pow(m, 1.0/3.0); s = pow(s, 1.0/3.0);
    return vec3(
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    );
}

vec3 oklabToRgb(vec3 lab) {
    float l = lab.x + 0.3963377774 * lab.y + 0.2158037573 * lab.z;
    float m = lab.x - 0.1055613458 * lab.y - 0.0638541728 * lab.z;
    float s = lab.x - 0.0894841775 * lab.y - 1.2914855480 * lab.z;
    l = l*l*l; m = m*m*m; s = s*s*s;
    return vec3(
         4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    );
}

vec3 mixOklab(vec3 a, vec3 b, float t) {
    return oklabToRgb(mix(rgbToOklab(a), rgbToOklab(b), t));
}
