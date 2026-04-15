# Somna EEG Integration — Pipeline Design Specification
*March 28, 2026 | Internal Engineering Spec | Phase 0–4 Roadmap*

> **STATUS: SUPERSEDED.** This document describes the Phase 0 initial design.
> The implemented pipeline (Docs 20–25) is documented in `eeg_entrainment.md` (agent-facing)
> and the actual source files (`eeg_engine.py`, `freq_leader.py`, `session_scorer.py`).
> The correction notes in §Implementor Notes below remain accurate and should be consulted
> if re-reading historical context.

---

## Implementor Notes

Three corrections to the original spec that the writing agent got wrong:

- **Board ID**: The spec says Muse 2 = board ID 22. **This is wrong.** Board ID 22 is `MUSE_2_BLED_BOARD` which requires a $30 BLED112 USB dongle. The correct ID for native BLE (no dongle) is **38 = `MUSE_2_BOARD`**. See `brainflow_reference.md` for full detail.
- **IPC write pattern**: The spec references `llm_driver.send()` for writing to `live_control.json`. **Do not use this.** Use the `_patch_live()` helper (same pattern as `audio_engine.py` and `visual_display.py`) — a direct JSON read-modify-write.
- **`beat_type` vs `beat_mode`**: The spec uses `beat_mode` as the config key name. Somna's implementation uses `beat_type`. These are the same concept — `beat_type` is the canonical key in `live_control.json`.

---

## 1. Executive Summary

One new module (`eeg_engine.py`), one new knowledge file (`knowledge/eeg_entrainment.md`), minor additions to `control_panel.py`, `somna_agent.py`, and `agent_config.yaml`. Everything else stays the same.

Integration pattern: EEG data flows through `live_control.json` as read-only keys — exactly like `session_time`, `session_duration`, and `display_active` already do. The agent reads these keys from state and factors them into its existing decision loop. No new threads inside `somna_agent.py`. No new IPC mechanisms.

Hardware: Muse 2 (~$250), `pip install brainflow`.

---

## 2. What Already Exists

~80% of the standalone pipeline concept already exists in Somna:

| Pipeline Component | Somna Already Has |
|---|---|
| LLM Decision Engine | `somna_agent.py` — always-on agent, reads state every tick, outputs adjustments + transitions |
| Binaural Beat Generator | `audio_engine.py` — phase-tracked, dual-channel crossfade, isochronic, monaural modes |
| IPC Bus | `live_control.json` — 100ms poll, stat-gated, battle-tested |
| Smooth Transitions | `RampEngine` — agent declares `transitions: {param: seconds}`, 1 Hz interpolation |
| TTS / Subliminals | `tts_engine.py` — Edge/OpenAI/local, SSB subliminals, beat-frequency AM |
| Session Management | Full YAML timelines, playlist, seek, transport, keyframe interpolation |
| Agent Knowledge | `knowledge/` directory — Markdown files injected into system prompt |
| Tool Calling | `content_tools/` registry — `dispatch()`, one tool per tick |
| User Profile / Memory | `user_profile.json` — cross-session memory, responsive themes |
| Visual Feedback | Full GPU-rendered display — spirals, veil, shadows, agent overlay, VR support |

The only genuinely new components are EEG acquisition/processing and GENUS-specific audio modes.

---

## 3. New Module — `eeg_engine.py`

**Purpose:** Acquire raw EEG from Muse 2 via BrainFlow, process into band power metrics, write results to `live_control.json` as read-only keys.

**Pattern:** Same as `timeline_runner.py` — a background thread started from `control_panel.py`, writing to `live_control.json` via `_patch_live()`.

### Thread Lifecycle
- Started by "Start EEG" button in control panel (or auto-start if `eeg_auto_connect: true`)
- Runs until "Stop EEG" button or shutdown
- Reconnects on BLE dropout (exponential backoff, max 3 attempts)

### Processing Pipeline (runs every 1 second)
1. `board.get_current_board_data(256)` — 1 second at 256 Hz (non-destructive read)
2. Artifact rejection — threshold ±100 μV, discard window if >50% contaminated
3. `DataFilter.detrend()` — LINEAR
4. `DataFilter.perform_bandpass()` — 1–50 Hz
5. `DataFilter.get_avg_band_powers()` — or `get_psd_welch()` + `get_band_power()` for custom bands
6. Compute derived metrics: alpha/theta ratio, beta/alpha ratio, frontal asymmetry
7. Determine dominant band and signal quality
8. Write to `live_control.json` via `_patch_live()`

### New `live_control.json` Keys (read-only, written by `eeg_engine.py`)

All normalized to 0.0–1.0 (proportions of total power, not raw μV²). Makes them immediately interpretable by the LLM without needing absolute amplitude knowledge.

| Key | Type | Description |
|-----|------|-------------|
| `eeg_connected` | bool | Muse 2 BLE connection active |
| `eeg_quality` | str | `"good"`, `"poor"`, `"unusable"` — based on artifact ratio |
| `eeg_dominant_band` | str | `"delta"`, `"theta"`, `"alpha"`, `"beta"`, `"gamma"` |
| `eeg_delta` | float | Delta band power (0.5–4 Hz), 0.0–1.0 |
| `eeg_theta` | float | Theta band power (4–8 Hz), 0.0–1.0 |
| `eeg_alpha` | float | Alpha band power (8–13 Hz), 0.0–1.0 |
| `eeg_beta` | float | Beta band power (13–30 Hz), 0.0–1.0 |
| `eeg_gamma` | float | Gamma band power (30–50 Hz), 0.0–1.0 |
| `eeg_gamma_40hz` | float | Narrow 38–42 Hz power (GENUS monitoring), 0.0–1.0 |
| `eeg_alpha_theta_ratio` | float | Alpha/theta — meditation depth indicator |
| `eeg_beta_alpha_ratio` | float | Beta/alpha — alertness indicator |
| `eeg_frontal_asymmetry` | float | ln(AF8_alpha) − ln(AF7_alpha) — approach/withdrawal motivation |
| `eeg_timestamp` | float | Wall time of last valid EEG update |

### Code Skeleton

```python
import json
import threading
import time
from pathlib import Path
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds, BrainFlowError
from brainflow.data_filter import DataFilter, FilterTypes, DetrendOperations

_LIVE_PATH = Path(__file__).parent / "live_control.json"

def _patch_live(updates: dict) -> None:
    try:
        data = json.loads(_LIVE_PATH.read_text(encoding="utf-8")) if _LIVE_PATH.exists() else {}
        data.update(updates)
        _LIVE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


class EEGEngine:
    def __init__(self, config):
        # config.get("eeg_synthetic") -> use SYNTHETIC_BOARD (-1) for Phase 0
        # config.get("eeg_board_id", 38) -> default 38 = MUSE_2_BOARD (native BLE, no dongle)
        # NEVER use board ID 22 (MUSE_2_BLED_BOARD) unless a BLED112 USB dongle is present
        synthetic = bool(config.get("eeg_synthetic", True))
        self.board_id = BoardIds.SYNTHETIC_BOARD if synthetic else int(config.get("eeg_board_id", 38))
        self.params = BrainFlowInputParams()
        self.board = None
        self._stop = threading.Event()
        self._thread = None
        self._history = []  # deque for read_eeg_history tool (max 300 entries = 5 min)

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="EEGEngine")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self.board and self.board.is_prepared():
            try:
                self.board.stop_stream()
                self.board.release_session()
            except BrainFlowError:
                BoardShim.release_all_sessions()
        _patch_live({"eeg_connected": False})

    def _run(self):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.board = BoardShim(self.board_id, self.params)
                self.board.prepare_session()
                break
            except BrainFlowError as e:
                print(f"[EEG] Connection attempt {attempt+1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
        else:
            print("[EEG] Could not connect — giving up.")
            _patch_live({"eeg_connected": False, "eeg_quality": "unusable"})
            return

        self.board.start_stream(buffer_size=450000)
        _patch_live({"eeg_connected": True})

        eeg_channels = BoardShim.get_eeg_channels(self.board_id)
        sampling_rate = BoardShim.get_sampling_rate(self.board_id)
        window_samples = sampling_rate  # 1 second

        while not self._stop.is_set():
            try:
                # Non-destructive read — does NOT flush the buffer
                data = self.board.get_current_board_data(window_samples)
                if data.shape[1] < window_samples:
                    time.sleep(0.5)
                    continue
                state = self._process(data, eeg_channels, sampling_rate)
                _patch_live(state)
                self._history.append(state)
                if len(self._history) > 300:
                    self._history.pop(0)
                time.sleep(1.0)
            except BrainFlowError as e:
                print(f"[EEG] Stream error: {e} — reconnecting")
                _patch_live({"eeg_connected": False})
                break  # outer reconnect logic would go here

    def _process(self, data, eeg_channels, sampling_rate) -> dict:
        # get_avg_band_powers returns ([delta, theta, alpha, beta, gamma], [stddevs])
        # apply_filters=True applies internal bandpass + notch
        try:
            bands = DataFilter.get_avg_band_powers(data, eeg_channels, sampling_rate, True)
            delta, theta, alpha, beta, gamma = [float(x) for x in bands[0]]
        except Exception:
            return {"eeg_quality": "unusable", "eeg_timestamp": time.time()}

        total = delta + theta + alpha + beta + gamma + 1e-12
        alpha_n = alpha / total
        theta_n = theta / total
        beta_n  = beta  / total
        gamma_n = gamma / total
        delta_n = delta / total

        # Narrow-band 40 Hz for GENUS monitoring
        try:
            g40 = DataFilter.get_custom_band_powers(data, [(38.0, 42.0)], eeg_channels, sampling_rate, True)
            gamma_40hz = float(g40[0][0])
        except Exception:
            gamma_40hz = 0.0

        # Frontal asymmetry: uses first two EEG channels (AF7=idx0, AF8=idx1 for Muse 2)
        frontal_asym = 0.0
        if len(eeg_channels) >= 2:
            try:
                import numpy as np
                af7_power = float(np.mean(data[eeg_channels[0]] ** 2))
                af8_power = float(np.mean(data[eeg_channels[1]] ** 2))
                if af7_power > 0 and af8_power > 0:
                    frontal_asym = float(np.log(af8_power) - np.log(af7_power))
            except Exception:
                pass

        bands_sorted = [("delta", delta_n), ("theta", theta_n), ("alpha", alpha_n),
                        ("beta", beta_n), ("gamma", gamma_n)]
        dominant = max(bands_sorted, key=lambda x: x[1])[0]

        return {
            "eeg_connected":       True,
            "eeg_quality":         "good",  # TODO: artifact ratio gating
            "eeg_dominant_band":   dominant,
            "eeg_delta":           round(delta_n, 4),
            "eeg_theta":           round(theta_n, 4),
            "eeg_alpha":           round(alpha_n, 4),
            "eeg_beta":            round(beta_n, 4),
            "eeg_gamma":           round(gamma_n, 4),
            "eeg_gamma_40hz":      round(gamma_40hz, 6),
            "eeg_alpha_theta_ratio": round(alpha_n / (theta_n + 1e-12), 3),
            "eeg_beta_alpha_ratio":  round(beta_n  / (alpha_n + 1e-12), 3),
            "eeg_frontal_asymmetry": round(frontal_asym, 4),
            "eeg_timestamp":       time.time(),
        }
```

---

## 4. Audio Engine Extension — `beat_type` Key

Already implemented. Somna uses `beat_type` (not `beat_mode` as this doc originally proposed — `beat_type` is the canonical key). Values: `"binaural"` | `"isochronic"` | `"both"`.

For GENUS specifically, the isochronic mode needs to support a **sharp rectangular pulse** at 40 Hz (1 ms ON, 24 ms OFF, 4% duty cycle). The current raised-cosine implementation is appropriate for general entrainment but NOT for the GENUS protocol. GENUS requires hard-edge rectangular pulses — the sharp transient onset is what drives the ASSR response. A dedicated `genus_mode` or `genus_active` key should trigger the rectangular pulse variant.

See `genus_protocol.md` for exact GENUS pulse parameters.

---

## 5. Agent Integration

The agent doesn't need code changes to read EEG data — it already reads all of `live_control.json` into its state context every tick. The `eeg_*` keys appear automatically.

What does change in `somna_agent.py`:
- State context enrichment: when building LLM context, if `eeg_connected` is true, include the EEG state block. If false or missing, omit it (backward compatible — sessions work fine without EEG).
- Nothing else. The real work is the knowledge file.

---

## 6. Knowledge File — `knowledge/eeg_entrainment.md`

Content sections needed:
1. EEG keys table (what they mean, normalization scheme)
2. Brainwave band reference table
3. Key ratio interpretation rules
4. Entrainment strategy ("meet and lead" principle, 5-minute lag, ≤0.5 Hz per adjustment)
5. Beat mode selection by output device
6. Artifact handling (when to ignore data)

Add to `knowledge_files` list in `agent_config.yaml` when the file is created.

---

## 7. `agent_config.yaml` Additions

```yaml
# EEG Integration
eeg_enabled: false          # Master enable
eeg_synthetic: true         # Use BrainFlow synthetic board (Phase 0 — no hardware)
eeg_board_id: 38            # 38 = MUSE_2_BOARD (native BLE); -1 = synthetic
eeg_auto_connect: false     # Auto-start EEG engine on app launch
output_device: headphones   # "headphones" or "bone_conduction" (affects beat_type default)
```

---

## 8. Control Panel EEG Section

New "EEG" section in the left column, below Binaural Beats:

```
┌─ EEG ──────────────────────────────────────────┐
│  [Connect]  [Disconnect]   ● Connected (good)  │
│                                                 │
│  Delta ████░░░░░░  0.12                         │
│  Theta ██████░░░░  0.28                         │
│  Alpha ████████░░  0.35  ◀ dominant             │
│  Beta  ███░░░░░░░  0.18                         │
│  Gamma █░░░░░░░░░  0.07                         │
│                                                 │
│  Quality: good    Frontal: +0.15                │
│  [Synthetic Mode ☑]                             │
└─────────────────────────────────────────────────┘
```

Implementation: read `eeg_*` keys from `live_control.json` on the existing 100ms poll cycle. Tkinter canvas for the bar chart.

---

## 9. New Agent Tool — `read_eeg_history`

Give the agent access to EEG trend data beyond the current snapshot. Stored as a `collections.deque` in `eeg_engine.py` (max 300 entries = 5 minutes at 1 Hz).

```json
{
  "samples": 60,
  "period_minutes": 5,
  "trend": {"alpha": "falling", "theta": "rising", "beta": "stable"},
  "avg_alpha_theta_ratio": 0.95,
  "avg_beta_alpha_ratio": 1.1,
  "dominant_band_history": ["alpha", "alpha", "theta", "theta", "theta"],
  "quality_good_pct": 0.85
}
```

Register in `content_tools/__init__.py`. Called as a tool by the agent when it needs temporal context.

---

## 10. Development Phases

| Phase | What | Estimated Effort |
|-------|------|-----------------|
| Phase 0 | `eeg_engine.py` with `SYNTHETIC_BOARD`, EEG section in control panel, `knowledge/eeg_entrainment.md`, agent verification | 1 weekend |
| Phase 1 | GENUS rectangular pulse mode, monitor refresh rate detection, 40 Hz visual flicker overlay | 1 weekend |
| Phase 2 | Swap to `MUSE_2_BOARD` (ID 38), BLE connection testing, artifact calibration, 30+ min stability | 1 weekend |
| Phase 3 | Agent tuning, `read_eeg_history` tool, EEG data in JSONL session logs | 1–2 weekends |
| Phase 4 (stretch) | EEG visualization layer in display | 1 weekend if desired |

---

## 11. New Dependencies

```
brainflow>=5.20.0
```

Add to `requirements.txt`. BrainFlow handles all Muse 2 communication, signal processing, band power extraction, and filtering.

---

## 12. Known Risks

| Risk | Severity | Notes |
|------|----------|-------|
| Muse 2 BLE stability in long sessions | Medium | BrainFlow handles BLE internally. Add reconnection logic with backoff. |
| Agent overreacting to EEG noise | High | Knowledge file must emphasize patience. Rate-limit beat_frequency changes to ≤0.5 Hz per tick. Use `transitions: 60–120`. |
| Binaural beats through bone conduction | Medium | Solved by isochronic mode. Agent knowledge file covers modality selection. |
| 40 Hz visual flicker on sub-80Hz displays | Medium | Must detect refresh rate and warn/fallback. 144Hz display enables proper 40 Hz (see `genus_protocol.md`). |
| LLM context window growth | Low | EEG adds ~15 keys to state. Negligible. |

---

## 13. File Changes Summary

| File | Change | What |
|------|--------|------|
| `eeg_engine.py` | NEW | BrainFlow acquisition + processing thread |
| `knowledge/eeg_entrainment.md` | NEW | Agent knowledge file for EEG interpretation |
| `control_panel.py` | MODIFY | Add EEG section (connect buttons, band power bars, quality badge) |
| `somna_agent.py` | MODIFY | Include EEG state block in LLM context when `eeg_connected` is true |
| `agent_config.yaml` | MODIFY | Add `eeg_enabled`, `eeg_synthetic`, `eeg_board_id`, `eeg_auto_connect`, `output_device` |
| `content_tools/__init__.py` | MODIFY | Register `read_eeg_history` tool |
| `requirements.txt` | MODIFY | Add `brainflow>=5.20.0` |
