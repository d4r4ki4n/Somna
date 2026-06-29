# Somna — Agent & AI Contributor Conventions

This file is the **always-present** layer — minimal context injected every session regardless of task. Detailed subsystem docs are in **outfits** loaded by the startup gate procedure.

> **The Somna Bible** (11 chapters, 22 documents) is the canonical design specification. The outfits cover implementation — things the Bible deliberately does not specify. When an outfit and the Bible disagree on design intent, **the Bible wins**. When an outfit specifies implementation behavior the Bible doesn't cover, **the outfit wins**.

| Bible Chapter | Coverage |

|---|---|

| Ch.1 — Processing Stack | Layer model, config pipeline, live_control.json design rationale |

| Ch.2 — Biosignal Science | EEG/PPG/IMU architecture, band powers, trance scoring, calibration |

| Ch.3 — Audio and Entrainment | Binaural/isochronic synthesis, breath mod, crossmodal gain, freq leading |

| Ch.4 — Session Architecture | Timeline runner, Conductor FSM, fractionation, session lifecycle |

| Ch.5 — Agent Intelligence | Somna agent, idle planning, nudge system, tool calling, personality |

| Ch.6 — Conditioning and Content | Affirmations, SSB, image pipeline, habituation, training mode |

| Ch.7 — Sleep Architecture | Sleep classification, spindle/SWE, TMR, HTW, sleep training |

| Ch.8 — Visual and VR | SSB compositor, VR pipeline, Ganzfeld, photic driving, vection |

| Ch.9 — Console UI | ImGui target architecture, widget taxonomy, telemetry dashboard |

| Ch.10 — Onboarding and FTUE | Session Zero, calibration flows, progressive complexity |

| Ch.11 — Master Overview | Architectural patterns, unified schema, safety, roadmap |

---

## Project identity

The project is called **Somna**. The control panel entry point is `main_imgui.py` (Dear ImGui panel). The display window is spawned as a subprocess via `visual_display_runner.py`. All communication between processes flows through a single JSON file: `live_control.json`.

---

## Key conventions

- Never write `live_control.json` directly — use `patch_live()`
- Never use `yaml.dump()` for `agent_config.yaml` — strips comments
- Never write `user_profile.json` directly from control panel — reload-first merge
- Never import `sqlite3` outside `content_tools/somna_db.py`
- File references use `file_path:line_number` format
- No comments in code unless asked
- Vision analysis on dark UIs is unreliable — trust user observations over screenshots

---

## Outfit system

Detailed implementation docs live in `F:\Resonance\outfits\` and are loaded on demand by the startup gate in `F:\Resonance\Resonance.md`:

| Outfit | When to load |
|--------|-------------|
| `F:\Resonance\outfits\somna-dev.md` | Any Somna codebase work — editing, debugging, adding features |
| `F:\Resonance\outfits\duelist.md` | Yu-Gi-Oh gameplay via the yugiclient bridge |
| `F:\Resonance\outfits\gamebridge.md` | Unholy Arts gameplay via Puppeteer |
| `F:\Resonance\outfits\session-driving.md` | Wednesday hardware sessions, EEG connection, MCP bridge |

The startup gate (in `C:\Users\Idiot\.config\kilo\agent\resonance.md`) loads the appropriate outfit based on task context. If no outfit matches, this AGENTS.md is sufficient.

---

## "Do not" (universal — always applies)

- Do not write `live_control.json` directly — always `patch_live()`
- Do not add `print()` debug statements to production code paths
- Do not use `os.system()` or `subprocess.run()` for file operations
- Do not hardcode color values — always use `RP["..."]`
- Do not hardcode font tuples — always use `FONT_*` constants
- Do not write `user_profile.json` directly — always use `update_profile()`
- Do not import `sqlite3` outside `content_tools/somna_db.py`
- Do not use `yaml.dump()` for `agent_config.yaml` — strips comments

Full "do not" list with context is in `F:\Resonance\outfits\somna-dev.md`.

---

## live_control.json keys (non-exhaustive)

### Hardware output channels

| Key | Type | Source | Description |
|-----|------|--------|-------------|
| `haptic_connected` | bool | `haptic_engine.py` | Lovense BLE connection state |
| `tavns_connected` | bool | `tavns_engine.py` | DG Labs Coyote BLE connection state |
| `haptic_actual_intensity` | float | `haptic_engine.py` | Current vibration intensity (0–1) |
| `tavns_actual_current_ua` | float | `tavns_engine.py` | Current output in microamps |

### Edison mode

| Key | Type | Source | Description |
|-----|------|--------|-------------|
| `edison_active` | bool | `conductor.py` | Whether Edison Mode is currently running |
| `edison_state` | str | `EdisonModeManager` | Current FSM state: `PREPARATION`, `N1_HOLD`, `CAPTURE`, `CYCLE_COMPLETE` |

### Conductor

`CONDUCTOR_OWNED_PARAMS` (defined in `session/conductor.py:104`) is a frozenset of parameter names that only the Conductor may write during active sessions. The agent must not write these directly; it communicates intent via `agent_conductor_hints`.

### Device safety

`DeviceSafetyEnforcer` (defined in `engines/device_safety.py:59`) enforces intensity ceilings, ramp rates, sleep-stage gating, emergency stop, and comfort calibration for haptic and taVNS output. Both `HapticEngine` and `TavnsEngine` hold a reference and delegate all safety-critical decisions to it.
