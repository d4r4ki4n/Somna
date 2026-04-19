"""
visual_sweep.py — Resonance's Visual Calibration Instrument

Systematically sweeps visual parameters and collects user descriptions
of what they perceive. Output is a structured log mapping parameter
configurations to subjective experience reports.

Usage:
  1. Start the display window (any session, or just beats)
  2. Run:  python visual_sweep.py
  3. For each test point, observe for N seconds, then type a description
  4. Results saved to visual_sweep_log.json

The display must be active — this tool patches live_control.json and
relies on the render loop picking up the changes.

Sweep groups:
  styles     — all 23 spiral styles at reference settings
  entrain    — entrainment_strength 0.0 → 1.0 in 0.25 steps
  trails     — trail_decay 0.0 → 0.95 with feedback modes
  post       — bloom, CA, film grain sweeps
  new_styles — styles 18-22 with varied parameters (tuning pass)
  all        — everything above in sequence

Optional flags:
  --group NAME       run a specific group (default: interactive menu)
  --duration SECS    observation time per test point (default: 8)
  --output FILE      output filename (default: visual_sweep_log.json)
"""

import json
import time
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ipc import patch_live

_LIVE = Path(__file__).parent / "live_control.json"

# ── Sweep Definitions ─────────────────────────────────────────────────────────

_BASE = {
    "beat_frequency": 6.0,
    "carrier_frequency": 180.0,
    "volume": 60,
    "spiral_opacity": 88,
    "spiral_count": 4,
    "spiral_speed_multiplier": 0.5,
    "spiral_tightness": 5.0,
    "spiral_chaos": 0.10,
    "spiral_thickness": 18,
    "veil_opacity": 40,
    "veil_mode": "drift",
    "shadow_opacity": 30,
    "noise_color": "pink",
    "noise_volume": 20,
    "entrainment_strength": 0.0,
    "trail_decay": 0.0,
    "feedback_mode": "none",
    "feedback_strength": 0.0,
    "pp_tonemap": 0,
    "pp_bloom_intensity": 0.0,
    "pp_ca_strength": 0.0,
    "pp_film_grain": 0.0,
}

ALL_STYLES = [
    "tunnel_dream",
    "galaxy",
    "archimedean",
    "kaleidoscope",
    "interference",
    "electric",
    "vortex",
    "dna",
    "fibonacci",
    "rose",
    "moire",
    "spirograph",
    "fermat",
    "superformula",
    "liminal",
    "resonant",
    "nebula",
    "bifurcate",
    "cobwebs",
    "strange_attractor",
    "flow_field",
    "sacred_geometry",
    "recursive_fractal",
    "potter_tunnel",
    "fractal_scale",
    "neuro_vortex",
]

NEW_STYLES = [
    "potter_tunnel",
    "fractal_scale",
    "neuro_vortex",
]

FEEDBACK_MODES = [
    "none",
    "alpha_decay",
    "radial_zoom",
    "rotational_smear",
    "directional_blur",
    "reaction_diffusion",
    "kaleidoscopic_fold",
]


def _sweep_styles():
    """Each of the 23 spiral styles at reference settings."""
    tests = []
    for style in ALL_STYLES:
        tests.append(
            {
                "label": f"style: {style}",
                "params": {**_BASE, "spiral_style": style},
                "question": f"Style {ALL_STYLES.index(style)}: {style}. Describe the pattern, motion, and how it feels.",
            }
        )
    return tests


def _sweep_entrainment():
    """Entrainment strength from 0 to 1 with galaxy style."""
    tests = []
    for v in [0.0, 0.15, 0.30, 0.50, 0.70, 0.85, 1.0]:
        tests.append(
            {
                "label": f"entrain: {v}",
                "params": {
                    **_BASE,
                    "spiral_style": "galaxy",
                    "entrainment_strength": v,
                },
                "question": f"Entrainment strength {v}. Does the spiral pulse? Is it subtle or obvious? Does it feel synced to the beat?",
            }
        )
    return tests


def _sweep_trails():
    """Trail decay + feedback modes."""
    tests = []
    for mode in FEEDBACK_MODES:
        for decay in [0.0, 0.60, 0.85, 0.95]:
            strength = 0.5 if mode != "none" else 0.0
            tests.append(
                {
                    "label": f"trail: decay={decay} mode={mode}",
                    "params": {
                        **_BASE,
                        "spiral_style": "galaxy",
                        "trail_decay": decay,
                        "feedback_mode": mode,
                        "feedback_strength": strength,
                    },
                    "question": f"Trail decay {decay}, feedback {mode}. Do you see persistence/ghosting? Does it feel like the spirals leave traces?",
                }
            )
    return tests


def _sweep_post():
    """Post-processing: bloom, CA, grain."""
    tests = []
    for bloom in [0.0, 0.25, 0.50, 0.75, 1.0]:
        tests.append(
            {
                "label": f"bloom: {bloom}",
                "params": {
                    **_BASE,
                    "spiral_style": "galaxy",
                    "pp_bloom_intensity": bloom,
                },
                "question": f"Bloom {bloom}. Is the image glowing/dreamy? At what point does it become too blurry?",
            }
        )
    for ca in [0.0, 0.15, 0.30, 0.50, 0.75]:
        tests.append(
            {
                "label": f"ca: {ca}",
                "params": {**_BASE, "spiral_style": "galaxy", "pp_ca_strength": ca},
                "question": f"Chromatic aberration {ca}. Do you see color fringing at edges? Subtle or distracting?",
            }
        )
    for grain in [0.0, 0.02, 0.04, 0.08, 0.12]:
        tests.append(
            {
                "label": f"grain: {grain}",
                "params": {**_BASE, "spiral_style": "galaxy", "pp_film_grain": grain},
                "question": f"Film grain {grain}. Do you see subtle noise/static in the image? Does it feel organic or annoying?",
            }
        )
    return tests


def _sweep_new_styles():
    """Styles 18-22 with parameter variations for tuning."""
    tests = []
    param_sets = [
        {
            "spiral_chaos": 0.04,
            "spiral_tightness": 7.0,
            "spiral_speed_multiplier": 0.3,
            "spiral_thickness": 12,
        },
        {
            "spiral_chaos": 0.10,
            "spiral_tightness": 5.0,
            "spiral_speed_multiplier": 0.5,
            "spiral_thickness": 18,
        },
        {
            "spiral_chaos": 0.20,
            "spiral_tightness": 3.0,
            "spiral_speed_multiplier": 0.8,
            "spiral_thickness": 24,
        },
        {
            "spiral_chaos": 0.35,
            "spiral_tightness": 2.0,
            "spiral_speed_multiplier": 1.2,
            "spiral_thickness": 30,
        },
    ]
    for style in NEW_STYLES:
        for i, overrides in enumerate(param_sets):
            label = ["tight", "medium", "loose", "chaotic"][i]
            tests.append(
                {
                    "label": f"{style}: {label}",
                    "params": {**_BASE, "spiral_style": style, **overrides},
                    "question": f"Style {style} ({label}). Describe the pattern quality. Is it coherent? Ugly? Interesting? What would make it better?",
                }
            )
    return tests


SWEEPS = {
    "styles": ("Spiral styles (23)", _sweep_styles),
    "entrain": ("Entrainment flicker", _sweep_entrainment),
    "trails": ("Trail persistence + feedback", _sweep_trails),
    "post": ("Post-processing (bloom/CA/grain)", _sweep_post),
    "new_styles": ("New styles 18-22 tuning", _sweep_new_styles),
    "all": (
        "Complete sweep",
        lambda: (
            _sweep_styles()
            + _sweep_entrainment()
            + _sweep_trails()
            + _sweep_post()
            + _sweep_new_styles()
        ),
    ),
}


def _read_live():
    try:
        return json.loads(_LIVE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_snapshot(state, label, params, response, notes):
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "params_applied": params,
        "live_state_snapshot": {
            k: v
            for k, v in state.items()
            if k.startswith(
                (
                    "spiral_",
                    "veil_",
                    "shadow_",
                    "pp_",
                    "feedback_",
                    "trail_",
                    "entrain",
                    "beat_",
                    "noise_",
                )
            )
        },
        "user_description": response,
        "user_notes": notes,
    }


def run_sweep(tests, duration_s=8, output_file="visual_sweep_log.json"):
    log = []
    total = len(tests)

    print(f"\n  Visual Sweep — {total} test points, {duration_s}s each")
    print(f"  Output: {output_file}")
    print(f"  Type your description when prompted. Empty = skip.")
    print(f"  'stop' = end sweep. 'notes TEXT' = add private note.\n")

    # Save baseline
    baseline = _read_live()
    print("  [*] Baseline captured. Starting in 3 seconds...\n")
    time.sleep(3)

    for i, test in enumerate(tests):
        label = test["label"]
        params = test["params"]
        question = test["question"]

        print(f"  ┌─ [{i + 1}/{total}] {label}")
        print(f"  │  {question}")

        patch_live(params)
        time.sleep(0.3)

        print(f"  │  Observing... ({duration_s}s)")
        time.sleep(duration_s)

        print(f"  └─ Describe what you see/feel: ", end="", flush=True)
        try:
            response = input().strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  [!] Sweep interrupted.")
            break

        if response.lower() == "stop":
            print("  [!] Sweep stopped by user.")
            break
        if response.lower().startswith("notes "):
            note_text = response[6:]
            print(f"  │  Note recorded. Re-prompting...")
            print(f"  └─ Describe what you see/feel: ", end="", flush=True)
            try:
                response = input().strip()
            except (EOFError, KeyboardInterrupt):
                break

        state = _read_live()
        entry = _save_snapshot(state, label, params, response, "")
        log.append(entry)

        print(f"  ✓ Logged.\n")

    # Restore baseline
    print("  [*] Restoring baseline parameters...")
    restore = {k: baseline.get(k, v) for k, v in _BASE.items()}
    patch_live(restore)

    out_path = Path(__file__).parent / output_file
    existing = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing.extend(log)
    out_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n  Done. {len(log)} entries saved to {output_file}")
    return log


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Visual parameter sweep for Resonance calibration"
    )
    parser.add_argument(
        "--group", choices=list(SWEEPS.keys()), help="Sweep group to run"
    )
    parser.add_argument(
        "--duration", type=float, default=8, help="Seconds to observe each test point"
    )
    parser.add_argument(
        "--output", default="visual_sweep_log.json", help="Output filename"
    )
    args = parser.parse_args()

    if args.group:
        group = args.group
    else:
        print("\n  Resonance Visual Calibration Instrument")
        print("  ─────────────────────────────────────────")
        print("  Available sweep groups:\n")
        for key, (desc, _) in SWEEPS.items():
            print(f"    {key:15s}  {desc}")
        print()
        try:
            group = input("  Select group: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if group not in SWEEPS:
            print(f"  Unknown group: {group}")
            return

    desc, builder = SWEEPS[group]
    tests = builder()
    print(f"\n  Running: {desc} ({len(tests)} test points)")
    run_sweep(tests, duration_s=args.duration, output_file=args.output)


if __name__ == "__main__":
    main()
