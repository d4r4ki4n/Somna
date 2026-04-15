# BrainFlow Python SDK Reference for Somna
*Internal Technical Reference | 28 March 2026*
*Target: LLM coding agent. Not for end-user consumption.*

---

## 1. Overview

BrainFlow is an open-source (MIT-licensed) biosignal acquisition library providing a uniform API across 60+ EEG/BCI boards. Install: `pip install brainflow`

Three independent modules:

| Module | Class | Purpose |
|--------|-------|---------|
| `board_shim` | `BoardShim` | Data acquisition — connect, stream, read data |
| `data_filter` | `DataFilter` | Signal processing — filtering, FFT, band powers, wavelets, ICA |
| `ml_model` | `MLModel` | ML metrics — mindfulness, restfulness, custom ONNX models |

**Core data model:** All data is a 2D `numpy.ndarray`. Rows = channels/data types. Columns = samples over time. Row indices for each data type via static methods like `BoardShim.get_eeg_channels(board_id)`.

---

## 2. Muse 2 Hardware and Board Configuration

### CRITICAL: Board ID Selection

There are **two** Muse 2 board IDs. This is the single most important detail in this document.

| Constant | Board ID | Transport | Requires Dongle? | Use? |
|----------|----------|-----------|-----------------|------|
| `MUSE_2_BLED_BOARD` | 22 | BLED112 USB dongle | **YES** — $30+ extra hardware, requires `serial_port` | **NO. Do not use unless you have a BLED112 dongle.** |
| `MUSE_2_BOARD` | **38** | Native BLE via SimpleBLE | **NO** | **YES. Always use this.** |

`MUSE_2_BOARD` (38) was added in BrainFlow 4.7.0 (November 2021). Always use 38 for Somna.

### Related Board IDs

| Constant | Board ID | Device | Transport |
|----------|----------|--------|-----------|
| `MUSE_2_BOARD` | 38 | Muse 2 | Native BLE |
| `MUSE_2_BLED_BOARD` | 22 | Muse 2 | BLED112 dongle |
| `MUSE_S_BOARD` | 39 | Muse S | Native BLE |
| `MUSE_S_BLED_BOARD` | 21 | Muse S | BLED112 dongle |
| `MUSE_2016_BOARD` | 41 | Muse 2016 | Native BLE |
| `SYNTHETIC_BOARD` | -1 | No hardware | Generates synthetic data — Phase 0 dev |

### Muse 2 Hardware Specs

| Parameter | Value |
|-----------|-------|
| EEG Channels | 4: TP9, AF7, AF8, TP10 (temporal and frontal positions) |
| EEG Sampling Rate | 256 Hz (DEFAULT_PRESET) |
| Accelerometer + Gyroscope | ~52 Hz (AUXILIARY_PRESET) |
| PPG | 64 Hz (ANCILLARY_PRESET) |
| 5th EEG Channel | Available since BrainFlow 5.1.0, enabled via `board.config_board("p50")` |
| Connection | Bluetooth Low Energy (BLE), no serial port needed |

**WARNING:** `BoardShim.get_eeg_names()` incorrectly returns Fp1/Fp2 instead of AF7/AF8 for Muse 2. Confirmed labeling error. Data is correct — use hardcoded names: `["TP9", "AF7", "AF8", "TP10"]`.

### Platform Requirements for Native BLE (Board ID 38)

| Platform | Minimum Version |
|----------|----------------|
| Windows | 10.0.19041.0+ (Windows 10 May 2020 Update) |
| macOS | 10.15+ (12.3+ for Monterey — 12.0–12.2 have BLE scanning bugs) |
| Linux | Source compilation recommended (`sudo apt-get install libdbus-1-dev`) |

### `BrainFlowInputParams` for Muse 2 (Board ID 38)

All fields optional for native BLE:

| Parameter | Used? | Description |
|-----------|-------|-------------|
| `serial_port` | NO | Not needed for native BLE |
| `mac_address` | Optional | Connect to specific device when multiple present |
| `serial_number` | Optional | Device name printed on Muse |
| `timeout` | Optional | Discovery timeout in seconds (default 15) |

Minimal init:
```python
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds

params = BrainFlowInputParams()
board = BoardShim(BoardIds.MUSE_2_BOARD, params)  # 38, native BLE
```

---

## 3. BoardShim API — Data Acquisition

Import: `from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds, BrainFlowPresets`

### Instance Methods

| Method | Return | Description |
|--------|--------|-------------|
| `__init__(board_id, params)` | `BoardShim` | Constructor |
| `prepare_session()` | None | Initialize + establish BLE connection. Raises `BrainFlowError` on failure. |
| `start_stream(buffer_size=450000, streamer_params="")` | None | Begin data acquisition into ring buffer |
| `stop_stream()` | None | Stop streaming thread. Buffer data preserved. |
| `release_session()` | None | Free resources + close BLE. **Always call in `finally` block.** |
| `get_board_data(num_datapoints=None)` | ndarray | Get data and **FLUSH buffer**. Use only for batch reads, not polling loops. |
| `get_current_board_data(num_samples)` | ndarray | **Non-destructive read** — get latest N samples WITHOUT removing from buffer. **Use this for real-time monitoring.** |
| `get_board_data_count()` | int | Number of samples currently in buffer |
| `is_prepared()` | bool | Whether session is prepared |
| `config_board(config)` | str | Send config string. For Muse 2: `"p50"` reportedly enables 5th EEG channel; `"p61"` may be required for PPG — **verify on real hardware**, documentation was written from a Muse S example and may be wrong for Muse 2. |
| `insert_marker(value)` | None | Insert event marker at current timestamp |

### Static/Class Methods (board metadata, no connection needed)

| Method | Return | Description |
|--------|--------|-------------|
| `get_sampling_rate(board_id)` | int | Sampling rate in Hz |
| `get_eeg_channels(board_id)` | List[int] | Row indices for EEG data |
| `get_eeg_names(board_id)` | List[str] | Channel names — **WRONG for Muse 2** (returns Fp1/Fp2, actual is AF7/AF8) |
| `get_ppg_channels(board_id)` | List[int] | PPG row indices |
| `get_accel_channels(board_id)` | List[int] | Accelerometer row indices |
| `get_timestamp_channel(board_id)` | int | Timestamp row index |
| `get_marker_channel(board_id)` | int | Event marker row index |
| `get_battery_channel(board_id)` | int | Battery level row index |
| `get_num_rows(board_id)` | int | Total rows in data array |
| `get_board_descr(board_id)` | dict | Full board description |
| `get_version()` | str | BrainFlow library version |
| `release_all_sessions()` | None | Release all sessions globally — emergency cleanup |
| `enable_board_logger()` | None | Enable INFO logging |
| `disable_board_logger()` | None | Disable logging |
| `set_log_level(level)` | None | 0=TRACE, 1=DEBUG, 2=INFO, 3=WARN, 4=ERROR, 6=OFF |

---

## 4. DataFilter API — Signal Processing

Import: `from brainflow.data_filter import DataFilter, FilterTypes, NoiseTypes, WindowOperations, DetrendOperations`

**All filtering methods modify arrays in-place. Copy before filtering if you need the original.**

### Filtering

| Method | Description |
|--------|-------------|
| `perform_bandpass(data, sr, start_freq, stop_freq, order, filter_type, ripple)` | Band-pass filter |
| `perform_bandstop(data, sr, start_freq, stop_freq, order, filter_type, ripple)` | Band-stop (notch) |
| `perform_lowpass(data, sr, cutoff, order, filter_type, ripple)` | Low-pass |
| `perform_highpass(data, sr, cutoff, order, filter_type, ripple)` | High-pass |
| `remove_environmental_noise(data, sr, noise_type)` | 50/60 Hz power line notch |
| `detrend(data, detrend_operation)` | Remove DC offset or linear trend |

`FilterTypes`: `BUTTERWORTH=0`, `CHEBYSHEV_TYPE_1=1`, `BESSEL=2`, `BUTTERWORTH_ZERO_PHASE=3`
`NoiseTypes`: `FIFTY=0`, `SIXTY=1`, `FIFTY_AND_SIXTY=2`
`DetrendOperations`: `NO_DETREND=0`, `CONSTANT=1`, `LINEAR=2`

### Frequency Analysis — THE KEY METHODS FOR SOMNA

| Method | Return | Description |
|--------|--------|-------------|
| `get_avg_band_powers(data, channels, sr, apply_filters)` | `(avg[5], std[5])` | **Primary method.** Returns averages for 5 standard bands: `[delta(1–4), theta(4–8), alpha(8–13), beta(13–30), gamma(30–50)]`. `apply_filters=True` applies bandpass + notch internally. |
| `get_custom_band_powers(data, bands, channels, sr, apply_filters)` | `(avg, std)` | Custom frequency band definitions. Use `[(38.0, 42.0)]` for narrow 40 Hz GENUS monitoring. |
| `get_psd_welch(data, nfft, overlap, sr, window)` | `(amplitudes, frequencies)` | Welch's method PSD for manual band extraction |
| `get_band_power(psd_tuple, freq_start, freq_end)` | float | Extract power in range from PSD tuple |

**Band index mapping for `get_avg_band_powers`:**
```
bands[0][0] → eeg_delta   (1–4 Hz)
bands[0][1] → eeg_theta   (4–8 Hz)
bands[0][2] → eeg_alpha   (8–13 Hz)
bands[0][3] → eeg_beta    (13–30 Hz)
bands[0][4] → eeg_gamma   (30–50 Hz)
```

`WindowOperations`: `NO_WINDOW=0`, `HANNING=1`, `HAMMING=2`, `BLACKMAN_HARRIS=3`

### Advanced

| Method | Description |
|--------|-------------|
| `perform_ica(data, num_components, channels)` | Independent Component Analysis |
| `perform_wavelet_denoising(data, wavelet, level, ...)` | Wavelet denoising for artifact removal |
| `detect_peaks_z_score(data, lag, threshold, influence)` | Z-score peak detection |
| `get_railed_percentage(data, gain)` | Signal quality indicator (% of samples at max amplitude) |

---

## 5. MLModel API — ML Metrics

Import: `from brainflow.ml_model import MLModel, BrainFlowMetrics, BrainFlowClassifiers, BrainFlowModelParams`

`BrainFlowMetrics`: `MINDFULNESS=0`, `RESTFULNESS=1`, `USER_DEFINED=2`
`BrainFlowClassifiers`: `DEFAULT_CLASSIFIER=0`, `ONNX_CLASSIFIER=2`

Usage (input is `bands[0]` from `get_avg_band_powers`):
```python
model_params = BrainFlowModelParams()
mindfulness = MLModel(BrainFlowMetrics.MINDFULNESS, BrainFlowClassifiers.DEFAULT_CLASSIFIER, model_params)
mindfulness.prepare()
score = mindfulness.predict(bands[0])   # [0.0–1.0]
mindfulness.release()
```

---

## 6. Synthetic Board for Development (Phase 0)

`SYNTHETIC_BOARD` (board ID -1) generates synthetic EEG-like data with no hardware required. Exposes the exact same API as real boards. Switching to Muse 2 = change one constant.

```python
# Phase 0 (change to MUSE_2_BOARD=38 for Phase 2):
BOARD_ID = BoardIds.SYNTHETIC_BOARD  # -1

params = BrainFlowInputParams()
board = BoardShim(BOARD_ID, params)

try:
    board.prepare_session()
    board.start_stream()
    import time; time.sleep(5)

    data = board.get_board_data()  # Gets ALL data and FLUSHES buffer
    eeg_channels = BoardShim.get_eeg_channels(BOARD_ID)
    sampling_rate = BoardShim.get_sampling_rate(BOARD_ID)

    bands = DataFilter.get_avg_band_powers(data, eeg_channels, sampling_rate, True)
    delta, theta, alpha, beta, gamma = bands[0]
    print(f"delta={delta:.4f} theta={theta:.4f} alpha={alpha:.4f} beta={beta:.4f} gamma={gamma:.4f}")

    board.stop_stream()
finally:
    board.release_session()
```

---

## 7. Complete Real-Time Polling Pipeline (for `eeg_engine.py`)

```python
# Uses get_current_board_data (non-destructive) for continuous monitoring
BOARD_ID = BoardIds.MUSE_2_BOARD   # 38, native BLE
WINDOW_SECONDS = 4
window_samples = 256 * WINDOW_SECONDS  # 1024 samples

params = BrainFlowInputParams()
board = BoardShim(BOARD_ID, params)
eeg_channels = BoardShim.get_eeg_channels(BOARD_ID)
sampling_rate = BoardShim.get_sampling_rate(BOARD_ID)

board.prepare_session()
board.start_stream(buffer_size=450000)
time.sleep(WINDOW_SECONDS + 1)  # Wait for buffer to fill

while running:
    data = board.get_current_board_data(window_samples)  # NON-DESTRUCTIVE
    if data.shape[1] < window_samples:
        time.sleep(1.0)
        continue

    bands = DataFilter.get_avg_band_powers(data, eeg_channels, sampling_rate, True)
    delta, theta, alpha, beta, gamma = bands[0]

    # Narrow-band GENUS monitoring
    g40 = DataFilter.get_custom_band_powers(data, [(38.0, 42.0)], eeg_channels, sampling_rate, True)

    theta_alpha_ratio = theta / alpha if alpha > 1e-10 else 0.0

    time.sleep(1.0)
```

---

## 8. Standard EEG Band Reference

| Index | Band | Frequency | States | Somna Relevance |
|-------|------|-----------|--------|-----------------|
| 0 | Delta | 1–4 Hz | Deep sleep (N3), unconscious processes | Target for deep sleep / TMR. High delta = successful SWS entrainment. |
| 1 | Theta | 4–8 Hz | Drowsiness, light sleep (N1), hypnagogic imagery | **Primary hypnotic entrainment target.** Rising theta = sleep onset. Key SSILD metric. |
| 2 | Alpha | 8–13 Hz | Relaxed wakefulness, eyes-closed, calm awareness | Baseline relaxation. Theta/alpha crossover is sleep-onset marker. |
| 3 | Beta | 13–30 Hz | Active thinking, alertness, anxiety | Should decrease during entrainment. High beta = user not relaxing / resisting. |
| 4 | Gamma | 30–50 Hz | Higher cognition, perception, cross-modal binding | **40 Hz GENUS target.** Use `get_custom_band_powers([(38, 42)])` for precision. |

---

## 9. SSILD-Specific: Theta/Alpha Ratio for Sleep Staging

| Theta/Alpha Ratio | Interpretation | Action |
|-------------------|----------------|--------|
| < 1.0 | Alpha dominant — relaxed wakefulness | Continue relaxation induction |
| ≈ 1.0 | Crossover — sleep onset | Transition to sleep-deepening |
| > 1.0 | Theta dominant — N1 / hypnagogic | Entrainment succeeding; begin SSILD cycling cues |
| >> 1.0 (+ high delta) | Deep sleep (N2/N3) | Reduce stimulation; monitor only |

```python
theta_alpha_ratio = bands[0][1] / bands[0][2] if bands[0][2] > 1e-10 else 0.0
```

---

## 10. Known Issues and Gotchas

| Issue | Severity | Details | Mitigation |
|-------|----------|---------|------------|
| `get_eeg_names()` returns wrong names | Low | Returns Fp1/Fp2 instead of AF7/AF8 for Muse 2 | Cosmetic only. Use hardcoded `["TP9", "AF7", "AF8", "TP10"]`. |
| `get_board_data()` flushes buffer | **High** | Calling it in a loop loses data between calls | **Use `get_current_board_data(num_samples)` for polling loops.** |
| BLE connection flakiness | High | Can drop, especially on first connect | Implement retry with backoff. Set `eeg_connected: false` during reconnect. |
| Windows BLE requires Bluetooth enabled | Medium | `prepare_session()` fails cryptically if BT is off | Check BT adapter state before connecting. Clear error message. |
| macOS 12.0–12.2 BLE scanning bugs | Medium | Device discovery fails on those versions | Require 12.3+ or 10.15–11.x. |
| Board ID confusion 22 vs 38 | **Critical** | Using 22 requires a BLED112 USB dongle and fails without one | **Always use 38.** Never 22 unless dongle explicitly available. |
| `release_session()` must be called | High | Not calling leaves BLE resources locked; subsequent connections fail | Always use `try/finally`. Check `is_prepared()` before calling. |
| Ring buffer overflow | Low | Default 450k samples = ~29 min at 256 Hz. Oldest data overwritten silently | For long sessions, use `get_board_data()` periodically or increase `buffer_size`. |
| Filter in-place modification | Medium | `DataFilter.perform_*` modifies input array in place | Copy before filtering if original needed; or rely on `get_avg_band_powers(apply_filters=True)`. |
| get_psd() needs even-length data | Medium | Raises error if data length is odd | Trim: `data = data[:len(data)-1] if len(data) % 2 else data`. Or use `get_avg_band_powers()`. |

### Error Handling Pattern

```python
def connect_with_retry(board_id, params, max_retries=3):
    board = BoardShim(board_id, params)
    for attempt in range(max_retries):
        try:
            board.prepare_session()
            return board
        except BrainFlowError as e:
            try:
                board.release_session()
            except BrainFlowError:
                pass
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Failed to connect after {max_retries} attempts")

def safe_cleanup(board):
    try:
        if board.is_prepared():
            try:
                board.stop_stream()
            except BrainFlowError:
                pass
            board.release_session()
    except BrainFlowError:
        BoardShim.release_all_sessions()  # Nuclear option
```

---

## Quick Reference Card

| What | Code |
|------|------|
| Install | `pip install brainflow` |
| Muse 2 board ID (native BLE) | `BoardIds.MUSE_2_BOARD = 38` |
| Synthetic board ID | `BoardIds.SYNTHETIC_BOARD = -1` |
| Muse 2 sampling rate | 256 Hz |
| Muse 2 electrodes | TP9, AF7, AF8, TP10 |
| EEG row indices | `BoardShim.get_eeg_channels(board_id)` |
| **Non-destructive read** | `board.get_current_board_data(num_samples)` |
| Destructive read (flushes) | `board.get_board_data()` |
| Standard 5-band powers | `DataFilter.get_avg_band_powers(data, channels, sr, True)` |
| Custom band (40 Hz GENUS) | `DataFilter.get_custom_band_powers(data, [(38,42)], channels, sr, True)` |
| Enable PPG (verify cmd) | `board.config_board("p50")` or `"p61"` — **unverified for Muse 2 specifically** |
| 60 Hz noise removal | `DataFilter.remove_environmental_noise(data, sr, NoiseTypes.SIXTY)` |
| Mindfulness score | `MLModel(BrainFlowMetrics.MINDFULNESS, ...).predict(bands[0])` |
