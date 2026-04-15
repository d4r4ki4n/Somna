Somna Bible Ch.2 Â§SQI — Signal Quality Index (SQI) Reference
Phase 0 EEG foundation gate — per-channel quality metrics, artifact classification, and the confidence architecture that makes every other EEG feature trustworthy
Author: Research (external collaborator)
Date: 30 March 2026
Series: Somna Research Documentation  |  Priority: Phase 0
1. Executive Summary
This document specifies a real-time Signal Quality Index (SQI) for Somna's Muse 2 EEG pipeline. SQI is Phase 0 priority — it must be implemented before any other EEG-driven feature can be trusted. Without SQI gating, every EEG metric (trance_score, IAF, ASSR, alpha asymmetry) is operating on potentially garbage data, and the agent has no way to know.
The SQI system provides:
Per-channel quality scores (0.0–1.0) for all four Muse 2 channels (TP9, AF7, AF8, TP10)
A composite signal quality metric
Artifact type classification (eye blink, muscle, electrode contact, saturation)
Confidence gating: all EEG-derived decisions are suppressed when quality is below threshold
live_control.json keys for agent awareness and response
Core Principle
It is always better to report "I don't know" than to act on bad data.
2. Why SQI Is Phase 0
2.1 The Garbage-In Problem
Every EEG metric Somna computes depends on clean signal:
SEF95 / trance_score (Bible Ch.2 Â§SEF95): Spectral edge frequency is meaningless if muscle artifact floods the high-frequency band — EMG pushes SEF95 up, making the user appear MORE alert when they might be deeply relaxed.
IAF calibration: Individual Alpha Frequency detection fails if the alpha band is contaminated by eye movement artifact (which has power in the same frequency range).
ASSR (Bible Ch.2 Â§ASSR): Entrainment verification requires isolating beat-frequency power from background — impossible if broadband muscle noise raises the floor.
Alpha asymmetry (proposed): Left-right frontal alpha comparison requires BOTH AF7 and AF8 to be clean simultaneously — one bad channel invalidates the metric entirely.
2.2 Muse 2 Specifics
Hardware: Muse 2, BrainFlow board_id=38. Four dry EEG electrodes:
TP9 (left temporal) — behind left ear. Prone to jaw clench (temporalis muscle) artifact.
AF7 (left frontal) — above left eyebrow. Prone to eye blink and eye movement artifact.
AF8 (right frontal) — above right eyebrow. Same eye artifact vulnerability as AF7.
TP10 (right temporal) — behind right ear. Same jaw artifact vulnerability as TP9.
Dry electrodes have higher impedance and more contact noise than gel-based systems. SQI must account for this baseline noise level being higher than clinical EEG.
Data access pattern:
# Non-destructive read — does NOT consume samples from the ring buffer
data = board.get_current_board_data(n_samples, preset=BrainFlowPresets.DEFAULT_PRESET)
# Returns numpy array: rows = channels, columns = samples
# EEG channels for Muse 2: indices from BoardShim.get_eeg_channels(38)
3. Per-Channel SQI Computation
3.1 Three-Component Quality Score
Each channel receives a quality score from three independent detectors, combined multiplicatively:
Component 1: Amplitude Check (RMS)
Compute RMS amplitude over a sliding window (1 second, 256 samples at Muse 2's 256 Hz sampling rate).
Good signal: RMS between 5 µV and 100 µV.
Bad signal (too high): RMS > 100 µV → likely muscle artifact or electrode pop.
Bad signal (too low): RMS < 2 µV → likely disconnected electrode or dead channel.
Saturated: any sample exceeds ±500 µV → electrode contact failure or movement artifact.
Score mapping: 1.0 for RMS in 5–80 µV, linear ramp down to 0.0 from 80–150 µV, 0.0 above 150 µV. Below 2 µV → 0.0.
import numpy as np

def _sqi_amplitude(channel_data: np.ndarray) -> float:
    """Amplitude-based quality score for one channel.

    Args:
        channel_data: 1D array of EEG samples (1 second window, ~256 samples)
    Returns:
        Quality score 0.0-1.0
    """
    rms = np.sqrt(np.mean(channel_data ** 2))

    # Saturation check
    if np.any(np.abs(channel_data) > 500):
        return 0.0

    # Dead channel
    if rms < 2.0:
        return 0.0

    # Good range
    if rms <= 80.0:
        return 1.0

    # Ramp down 80-150
    if rms <= 150.0:
        return max(0.0, 1.0 - (rms - 80.0) / 70.0)

    return 0.0
Component 2: Spectral Flatness (Muscle Artifact Detection)
Compute Welch PSD over the 1-second window.
Muscle (EMG) artifact produces broadband power increase — the spectrum becomes FLAT instead of showing the normal 1/f slope.
Spectral flatness = geometric mean of PSD / arithmetic mean of PSD (Wiener entropy).
Range: 0.0 (pure tone, very peaked spectrum) to 1.0 (white noise, perfectly flat).
Normal EEG: spectral flatness ~0.05–0.15 (strong 1/f slope with peaks).
Muscle-contaminated: spectral flatness > 0.3 (flattened spectrum).
Score mapping: 1.0 for flatness < 0.15, linear ramp to 0.0 from 0.15–0.40, 0.0 above 0.40.
from scipy.signal import welch
from scipy.stats import gmean

def _sqi_spectral_flatness(channel_data: np.ndarray, fs: int = 256) -> float:
    """Spectral flatness quality score — detects muscle artifact.

    Args:
        channel_data: 1D array of EEG samples
        fs: Sampling rate (256 Hz for Muse 2)
    Returns:
        Quality score 0.0-1.0
    """
    freqs, psd = welch(channel_data, fs=fs, nperseg=min(256, len(channel_data)))

    # Focus on 1-45 Hz range (relevant EEG bands)
    mask = (freqs >= 1.0) & (freqs <= 45.0)
    psd_band = psd[mask]

    if len(psd_band) == 0 or np.any(psd_band <= 0):
        return 0.0

    flatness = gmean(psd_band) / np.mean(psd_band)

    if flatness <= 0.15:
        return 1.0
    elif flatness <= 0.40:
        return max(0.0, 1.0 - (flatness - 0.15) / 0.25)
    return 0.0
Component 3: High-Frequency Power Ratio (EMG Confirmation)
Compute power in high-frequency band (30–45 Hz) relative to total power (1–45 Hz).
Muscle artifact dominates high frequencies; clean EEG has most power below 30 Hz.
HF ratio = power(30–45 Hz) / power(1–45 Hz).
Normal EEG: HF ratio < 0.15.
Muscle-contaminated: HF ratio > 0.30.
Score mapping: 1.0 for ratio < 0.15, linear ramp to 0.0 from 0.15–0.40, 0.0 above 0.40.
def _sqi_hf_ratio(channel_data: np.ndarray, fs: int = 256) -> float:
    """High-frequency power ratio — confirms muscle artifact detection.

    Args:
        channel_data: 1D array of EEG samples
        fs: Sampling rate
    Returns:
        Quality score 0.0-1.0
    """
    freqs, psd = welch(channel_data, fs=fs, nperseg=min(256, len(channel_data)))

    total_mask = (freqs >= 1.0) & (freqs <= 45.0)
    hf_mask = (freqs >= 30.0) & (freqs <= 45.0)

    total_power = np.sum(psd[total_mask])
    hf_power = np.sum(psd[hf_mask])

    if total_power <= 0:
        return 0.0

    ratio = hf_power / total_power

    if ratio <= 0.15:
        return 1.0
    elif ratio <= 0.40:
        return max(0.0, 1.0 - (ratio - 0.15) / 0.25)
    return 0.0
3.2 Combined Per-Channel SQI
def compute_channel_sqi(channel_data: np.ndarray, fs: int = 256) -> float:
    """Compute combined SQI for one EEG channel.

    Multiplicative combination: if ANY component is bad, the channel is bad.
    This is intentionally conservative — we want false negatives (marking
    good data as bad) rather than false positives (trusting bad data).
    """
    amp = _sqi_amplitude(channel_data)
    flat = _sqi_spectral_flatness(channel_data, fs)
    hf = _sqi_hf_ratio(channel_data, fs)

    return amp * flat * hf
4. Composite SQI and Confidence Gating
4.1 Per-Channel Publication
The agent needs per-channel SQI to make channel-specific decisions:
def publish_sqi(board, n_samples: int = 256) -> dict:
    """Compute and publish SQI for all Muse 2 channels.

    Call this every 1 second (256 samples at 256 Hz).
    """
    from brainflow.board_shim import BoardShim, BrainFlowPresets

    data = board.get_current_board_data(n_samples, preset=BrainFlowPresets.DEFAULT_PRESET)
    eeg_channels = BoardShim.get_eeg_channels(38)  # Muse 2 board_id

    channel_names = ["tp9", "af7", "af8", "tp10"]
    sqi_values = {}

    for i, ch_idx in enumerate(eeg_channels[:4]):
        ch_data = data[ch_idx, :]
        sqi = compute_channel_sqi(ch_data)
        sqi_values[channel_names[i]] = round(sqi, 3)

    # Composite: mean of all channels
    composite = round(np.mean(list(sqi_values.values())), 3)

    # Usable channel count
    usable = sum(1 for v in sqi_values.values() if v >= 0.5)

    _patch_live({
        "eeg_sqi_tp9": sqi_values["tp9"],
        "eeg_sqi_af7": sqi_values["af7"],
        "eeg_sqi_af8": sqi_values["af8"],
        "eeg_sqi_tp10": sqi_values["tp10"],
        "eeg_sqi_composite": composite,
        "eeg_sqi_usable_channels": usable,
    })

    return sqi_values
4.2 Confidence Gating Rules
Composite SQI
Usable Channels
Gate Decision
Agent Behavior
≥ 0.7
4
FULL CONFIDENCE
All EEG features active. Agent trusts trance_score, IAF, ASSR, all metrics.
0.5 – 0.7
3–4
REDUCED CONFIDENCE
EEG features active but agent applies wider uncertainty margins. trance_score changes must exceed 0.15 (not 0.05) to trigger adaptation. ASSR threshold raised.
0.3 – 0.5
2–3
LOW CONFIDENCE
Only robust metrics active (gross alpha power trends). Fine-grained metrics (SEF95, ASSR, asymmetry) suspended. Agent relies more on session timeline and behavioral cues.
< 0.3
0–1
NO CONFIDENCE
All EEG-derived decisions suspended. Agent operates on session timeline only. If sustained > 60 seconds, agent may issue a gentle "adjust your headband" prompt via TTS.
4.3 The "Adjust Headband" Prompt
When SQI is critically low for an extended period, the agent should gently prompt the user without disrupting trance:
def _check_sqi_intervention(sqi_history: list[float], threshold: float = 0.3,
                              sustained_seconds: int = 60) -> None:
    """Check if sustained low SQI warrants a gentle user prompt.

    Only triggers once per session to avoid disruption.
    """
    if len(sqi_history) < sustained_seconds:
        return

    recent = sqi_history[-sustained_seconds:]
    if all(s < threshold for s in recent):
        # Gentle, non-disruptive prompt
        _patch_live({
            "tts_queue": "The headband may need a small adjustment. "
                        "When you're ready, gently press it snug against your forehead.",
            "eeg_sqi_prompted": True,  # Prevent repeat prompting
        })
5. Artifact Type Classification
Beyond the composite score, the agent benefits from knowing what kind of artifact is present:
5.1 Eye Blink Detection
Eye blinks produce large (50–200 µV) transient deflections primarily on frontal channels (AF7, AF8).
Duration: 100–400ms.
Detection: peak amplitude > 75 µV on AF7 or AF8 with temporal profile matching blink morphology.
Impact: frontal channels only — temporal channels (TP9, TP10) are unaffected.
Agent response: exclude AF7/AF8 data during blink window, continue using TP9/TP10.
def detect_blinks(af7_data: np.ndarray, af8_data: np.ndarray,
                  fs: int = 256, threshold_uv: float = 75.0) -> list[int]:
    """Detect eye blink artifacts on frontal channels.

    Returns list of sample indices where blinks are detected.
    """
    blink_indices = []

    # Use the average of both frontal channels (blinks are bilateral)
    frontal_avg = (af7_data + af8_data) / 2.0

    # Simple threshold detection with minimum spacing
    above_threshold = np.where(np.abs(frontal_avg) > threshold_uv)[0]

    if len(above_threshold) == 0:
        return []

    # Group consecutive samples and take peaks
    groups = np.split(above_threshold, np.where(np.diff(above_threshold) > fs // 4)[0] + 1)
    for group in groups:
        if len(group) > 0:
            peak_idx = group[np.argmax(np.abs(frontal_avg[group]))]
            blink_indices.append(int(peak_idx))

    return blink_indices
5.2 Jaw Clench / Muscle Artifact
Temporalis muscle activity affects TP9 and TP10 primarily.
Produces broadband power increase (10–100+ Hz).
Detection: spectral flatness > 0.25 AND HF ratio > 0.25 on temporal channels.
Agent response: exclude temporal channels, rely on frontal channels if they're clean.
5.3 Electrode Contact Loss
Characterized by very low amplitude (RMS < 2 µV) or extremely high amplitude with 50/60 Hz line noise dominance.
Detection: RMS < 2 µV OR dominant frequency is exactly 50 Hz or 60 Hz (power line).
Agent response: mark channel as disconnected, do not use until SQI recovers.
5.4 Movement Artifact
Large, slow (< 2 Hz) baseline shifts affecting all channels simultaneously.
Detection: high power in 0.5–2 Hz band relative to total, affecting ALL channels simultaneously.
Agent response: brief suspension of all EEG metrics, auto-resume when movement subsides.
5.5 Artifact Classification Summary
Artifact Type
Affected Channels
Spectral Signature
Duration
Detection Method
Agent Response
Eye Blink
AF7, AF8 (frontal)
Broadband transient, 50–200 µV peak
100–400ms
Peak amplitude > 75 µV on frontal average
Exclude frontal data during blink window; temporal channels remain valid
Jaw Clench
TP9, TP10 (temporal)
Broadband power increase, flat spectrum
200ms – seconds
Spectral flatness > 0.25 AND HF ratio > 0.25 on temporal channels
Exclude temporal channels; frontal channels remain valid if clean
Electrode Contact Loss
Any single channel
Very low RMS (< 2 µV) or 50/60 Hz line noise dominance
Sustained
RMS < 2 µV or dominant peak at exactly 50/60 Hz
Mark channel disconnected; prompt headband adjustment after 60s
Movement
All channels simultaneously
High power in 0.5–2 Hz band, baseline shift
0.5–3 seconds
Low-frequency power surge on all 4 channels within same 1s window
Suspend all EEG metrics briefly; auto-resume when settled
Saturation
Any channel
Rail clipping at ADC limits
Single sample
abs(sample) > 500 µV
Mark affected samples; if sustained, treat as electrode contact loss
6. Integration with Existing EEG Pipeline
6.1 Call Order
SQI must be computed BEFORE any other EEG metric on every processing cycle:
def eeg_processing_cycle(board, n_samples: int = 256) -> dict:
    """Master EEG processing cycle — SQI gates everything.

    Call every 1 second.
    """
    # STEP 1: Always compute SQI first
    sqi = publish_sqi(board, n_samples)
    composite = np.mean(list(sqi.values()))
    usable = sum(1 for v in sqi.values() if v >= 0.5)

    results = {"sqi": sqi, "composite_sqi": composite, "usable_channels": usable}

    # STEP 2: Gate downstream metrics
    if composite < 0.3:
        # NO CONFIDENCE — skip all EEG metrics
        _patch_live({
            "eeg_confidence": "none",
            "trance_score_confidence": "suspended",
        })
        return results

    if composite < 0.5:
        # LOW CONFIDENCE — only gross metrics
        results["trance_score"] = _compute_trance_score_conservative(board, sqi)
        _patch_live({"eeg_confidence": "low"})
        return results

    # REDUCED or FULL CONFIDENCE — compute all metrics
    confidence = "full" if composite >= 0.7 and usable == 4 else "reduced"

    results["trance_score"] = _compute_trance_score(board, sqi)
    results["iaf"] = _compute_iaf(board, sqi)
    # ASSR only at full confidence (Bible Ch.2 Â§ASSR)
    if confidence == "full":
        results["assr"] = _compute_assr(board, sqi)

    _patch_live({"eeg_confidence": confidence})
    return results
6.2 Channel-Aware Metric Computation
When some channels are bad but others are good, metrics should use only clean channels:
def _get_clean_channels(board, n_samples: int, sqi: dict,
                         min_sqi: float = 0.5) -> dict:
    """Get data from channels that pass SQI threshold.

    Returns dict of channel_name: data for channels above min_sqi.
    """
    from brainflow.board_shim import BoardShim, BrainFlowPresets

    data = board.get_current_board_data(n_samples, preset=BrainFlowPresets.DEFAULT_PRESET)
    eeg_channels = BoardShim.get_eeg_channels(38)
    channel_names = ["tp9", "af7", "af8", "tp10"]

    clean = {}
    for i, ch_idx in enumerate(eeg_channels[:4]):
        name = channel_names[i]
        if sqi.get(name, 0.0) >= min_sqi:
            clean[name] = data[ch_idx, :]

    return clean
7. live_control.json Keys
Key
Type
Range
Default
Written By
Description
eeg_sqi_tp9
float
0.0–1.0
0.0
SQI module
Signal quality for left temporal channel
eeg_sqi_af7
float
0.0–1.0
0.0
SQI module
Signal quality for left frontal channel
eeg_sqi_af8
float
0.0–1.0
0.0
SQI module
Signal quality for right frontal channel
eeg_sqi_tp10
float
0.0–1.0
0.0
SQI module
Signal quality for right temporal channel
eeg_sqi_composite
float
0.0–1.0
0.0
SQI module
Mean of all four channel SQIs
eeg_sqi_usable_channels
int
0–4
0
SQI module
Count of channels with SQI ≥ 0.5
eeg_confidence
string
"none" / "low" / "reduced" / "full"
"none"
SQI module
Current confidence level for EEG-derived metrics
eeg_sqi_prompted
bool
true / false
false
SQI module
Whether headband adjustment has been prompted this session (prevents repeats)
trance_score_confidence
string
"active" / "suspended"
"active"
SQI module
Whether trance_score is currently trustworthy
8. Temporal Smoothing and Hysteresis
8.1 Exponential Moving Average
Raw SQI values can be noisy — a single jaw clench shouldn't cause all metrics to oscillate. Apply EMA smoothing:
class SQITracker:
    """Tracks per-channel SQI with temporal smoothing and hysteresis."""

    def __init__(self, alpha: float = 0.3):
        """
        Args:
            alpha: EMA smoothing factor. 0.3 = moderate smoothing
                   (~3 second effective window at 1 Hz update rate)
        """
        self._alpha = alpha
        self._ema = {"tp9": 0.5, "af7": 0.5, "af8": 0.5, "tp10": 0.5}
        self._history = []  # For sustained-low detection
        self._prompted = False

    def update(self, raw_sqi: dict) -> dict:
        """Update smoothed SQI values.

        Args:
            raw_sqi: Dict of channel_name: raw_sqi_value
        Returns:
            Dict of channel_name: smoothed_sqi_value
        """
        smoothed = {}
        for ch in ["tp9", "af7", "af8", "tp10"]:
            raw = raw_sqi.get(ch, 0.0)
            self._ema[ch] = self._alpha * raw + (1 - self._alpha) * self._ema[ch]
            smoothed[ch] = round(self._ema[ch], 3)

        composite = round(np.mean(list(smoothed.values())), 3)
        self._history.append(composite)

        # Keep last 120 seconds of history
        if len(self._history) > 120:
            self._history = self._history[-120:]

        return smoothed
8.2 Hysteresis for Confidence Transitions
To prevent rapid oscillation between confidence levels, use hysteresis:
Transition DOWN (e.g., full → reduced): requires SQI to drop below threshold for 3 consecutive seconds.
Transition UP (e.g., reduced → full): requires SQI to exceed threshold for 5 consecutive seconds.
This asymmetry is intentional: be quick to protect against bad data, but slow to trust that data is good again.
Design Note
The 3-down / 5-up asymmetry mirrors a core Somna principle: conservative trust management. In ambiguous situations, the system defaults to caution. A brief dropout should gate metrics quickly, but a brief recovery shouldn't un-gate them — the signal needs to prove it's stable before we trust it again.
9. Development and Synthetic Board Testing
When using SYNTHETIC_BOARD (board_id=-1) during development:
Synthetic data will produce artificial SQI values — they may not match real Muse 2 characteristics.
Recommendation: add a dev mode that injects controlled artifacts into synthetic data for SQI testing.
Test cases to implement:
Clean signal — all channels SQI > 0.8
Single-channel dropout — one channel SQI = 0.0, others normal
Bilateral blink — AF7 + AF8 brief SQI drop, TP9 + TP10 unaffected
Jaw clench — TP9 + TP10 SQI drop, AF7 + AF8 unaffected
Full movement artifact — all channels SQI drop simultaneously
Gradual electrode drying — one channel slowly degrades over 5 minutes
def inject_test_artifact(data: np.ndarray, artifact_type: str,
                          channel_idx: int, start_sample: int) -> np.ndarray:
    """Inject synthetic artifact for SQI testing.

    Args:
        data: Full EEG data array (channels x samples)
        artifact_type: "blink", "muscle", "disconnect", "movement"
        channel_idx: Which channel to affect
        start_sample: Sample index to begin artifact
    Returns:
        Modified data array
    """
    modified = data.copy()

    if artifact_type == "blink":
        # 250ms Gaussian pulse, 150 uV peak
        duration = 64  # samples at 256 Hz
        t = np.arange(duration)
        pulse = 150.0 * np.exp(-0.5 * ((t - duration/2) / (duration/6)) ** 2)
        end = min(start_sample + duration, data.shape[1])
        modified[channel_idx, start_sample:end] += pulse[:end-start_sample]

    elif artifact_type == "muscle":
        # 1 second of broadband noise, 80 uV RMS
        duration = 256
        noise = np.random.randn(duration) * 80.0
        end = min(start_sample + duration, data.shape[1])
        modified[channel_idx, start_sample:end] += noise[:end-start_sample]

    elif artifact_type == "disconnect":
        # Zero out channel
        modified[channel_idx, start_sample:] = 0.0

    elif artifact_type == "movement":
        # Large slow wave on ALL channels
        duration = 512  # 2 seconds
        t = np.arange(duration) / 256.0
        wave = 200.0 * np.sin(2 * np.pi * 0.5 * t)
        end = min(start_sample + duration, data.shape[1])
        for ch in range(min(4, data.shape[0])):
            modified[ch, start_sample:end] += wave[:end-start_sample]

    return modified
10. Key Research Citations
Dhole, P. V., et al. (2025). A Review of EEG Artifact Removal Techniques for Brain-Computer Interface. SN Computer Science, 6, 1026.
Porr, B., & Bohollo, L. M. (2023). BCI-Walls: A robust methodology to predict if conscious EEG changes can be detected in the presence of artefacts. PLOS ONE, 18(8), e0290446.
Schmoigl-Tonis, M., Schranz, C. S., & Müller-Putz, G. R. (2023). Methods for motion artifact reduction in online brain-computer interface experiments: a systematic review. Frontiers in Human Neuroscience, 17, 1251690.
Muse 2 Hardware Specification — InteraXon. 4 dry EEG electrodes (TP9, AF7, AF8, TP10), 256 Hz sampling rate.
BrainFlow Documentation — board_id=38 for Muse 2, get_current_board_data() for non-destructive reads.
