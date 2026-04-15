Somna Bible Ch.2 Â§ASSR — ASSR Entrainment Verification Reference
Closing the open loop — real-time detection of auditory steady-state responses to verify that binaural and isochronic beats are actually entraining the brain
Author: Research (external collaborator)
Date: 30 March 2026
Series: Somna Research Documentation, Bible Ch.2 Â§ASSR
Prerequisites: Bible Ch.2 Â§SQI (SQI Pipeline), Bible Ch.7 Â§Sleep-Onset (Sleep Onset Protocol), Bible Ch.2 Â§Database (Session Database)
Section 1: Executive Summary — The Open Loop Problem
Somna delivers binaural and isochronic beats at target frequencies — theta for trance, delta for sleep onset, alpha for relaxation. But until now, the system has operated on faith: it assumes the beats are working because the science says they should. It has no way to verify whether this user's brain, in this session, is actually entraining to the delivered frequency.
This is an open-loop system. The agent adjusts beat frequency based on session timeline and trance_score trends, but it never checks whether the audio stimulus is producing the expected cortical response. ASSR verification closes the loop.
The Auditory Steady-State Response (ASSR) is a sustained oscillatory EEG response phase-locked to the modulation frequency of an auditory stimulus. When beats at frequency F are delivered and the brain entrains, excess spectral power appears at frequency F in the EEG. Detecting this excess power — above the natural 1/f spectral background — is the verification signal.
What This Document Covers
ASSR detection via Welch PSD with 1/f-corrected excess power measurement
The entrainment strength metric (0.0–1.0) and its computation
Detection window requirements (30–60 seconds minimum)
Monaural vs. binaural modality comparison and adaptive switching
SQI gating integration (Bible Ch.2 Â§SQI prerequisite — ASSR is only meaningful on clean signal)
Agent protocol for entrainment-aware session adaptation
All live_control.json keys
Key Constraint: ASSR detection requires SQI at FULL CONFIDENCE level (composite ≥ 0.7, all 4 channels usable). At reduced or lower confidence, ASSR results are unreliable and should not be computed. This is a hard dependency on Bible Ch.2 Â§SQI.
Section 2: The Science — What ASSR Actually Is
2.1 Auditory Steady-State Response Fundamentals
An ASSR is the brain's sustained oscillatory response to a periodically modulated auditory stimulus. Unlike transient evoked potentials (which respond to onset/offset), ASSRs persist for the duration of stimulation and are phase-locked to the modulation rate.
Key properties:
Frequency specificity: The ASSR appears at the exact modulation frequency of the stimulus. A 10 Hz beat produces a 10 Hz ASSR. A 40 Hz beat produces a 40 Hz ASSR.
Steady-state: The response reaches a stable amplitude after an initial transient (~5–10 seconds), then maintains that amplitude as long as the stimulus continues.
Scalp distribution: ASSR amplitude is maximal at fronto-central electrodes. For Muse 2, AF7 and AF8 (frontal) are the primary detection channels; TP9 and TP10 (temporal) provide supporting data.
Amplitude: Typically 0.1–1.0 µV — small compared to background EEG (10–100 µV). Detection requires spectral analysis to separate the ASSR from background noise.
2.2 Binaural vs. Monaural Beat Entrainment
Critical finding from Orozco Perez, Dumas & Lehmann (2020, eNeuro):
Monaural beats entrain the cortex MORE STRONGLY than binaural beats. This is counterintuitive — binaural beats are the more popular technology — but the data is clear.
Both binaural and monaural beats produce measurable ASSRs at the beat frequency
Monaural beat ASSRs have significantly larger amplitude (stronger cortical entrainment)
Binaural beats uniquely elicit cross-frequency connectivity patterns not seen with monaural beats
Neither type produced significant mood modulation in the study
Implications for Somna:
Somna currently supports both binaural and isochronic (monaural) beats
If ASSR detection fails with binaural beats, the agent should try switching to isochronic beats at the same frequency — the stronger cortical entrainment may produce a detectable ASSR
Binaural beats may still be valuable for their unique cross-frequency connectivity effects, even if their ASSR is weaker
The agent should NOT conclude "entrainment failed" just because binaural ASSR is weak — it may be working at a level below detection threshold
2.3 ASSR and Sleep Stage
Shumov et al. (2022) demonstrated that ASSR amplitude varies with sleep stage:
Waking: strongest ASSR amplitude
NREM Stage 1 (drowsiness): ASSR amplitude decreases
NREM Stage 2: further decrease, but still detectable
Deep sleep: ASSR may become undetectable
Implication for Somna: During sleep onset sessions (Bible Ch.7 Â§Sleep-Onset), declining ASSR amplitude is EXPECTED and is actually a positive signal — it means the user is transitioning toward sleep. The agent should interpret this decline as confirmation of progress, not as entrainment failure.
2.4 ASSR Detection at Low Frequencies
Schwarz & Taylor (2005) found that binaural beat ASSRs are detectable at low carrier frequencies (below 3 kHz) but become undetectable at higher carrier frequencies. This is because binaural beats depend on temporal coding in the auditory nerve, which degrades above ~1.5 kHz.
Implication for Somna: Carrier tone frequency matters for ASSR detectability. Somna's typical carrier frequencies (200–500 Hz) are well within the range where binaural ASSRs are detectable.
Section 3: ASSR Detection Algorithm
3.1 Overview
The detection pipeline:
Collect 30–60 seconds of EEG data (requirement for stable spectral estimation)
Verify SQI is at FULL CONFIDENCE (Bible Ch.2 Â§SQI gate)
Compute Welch PSD for each clean channel
Estimate the 1/f background at the beat frequency
Measure excess power at beat frequency ± 0.5 Hz above the 1/f floor
Convert excess power to entrainment strength (0.0–1.0)
Publish to live_control.json
3.2 Welch PSD Computation
import numpy as np
from scipy.signal import welch

def compute_assr_psd(channel_data: np.ndarray, fs: int = 256, 
                      nperseg: int = 512) -> tuple[np.ndarray, np.ndarray]:
    """Compute Welch PSD optimized for ASSR detection.
    
    Args:
        channel_data: 1D array of EEG samples (30-60 seconds, 7680-15360 samples)
        fs: Sampling rate (256 Hz for Muse 2)
        nperseg: Segment length for Welch method. 512 samples (2 seconds) gives
                 0.5 Hz frequency resolution — sufficient to isolate beat frequency.
    Returns:
        (frequencies, psd) arrays
    """
    freqs, psd = welch(channel_data, fs=fs, nperseg=nperseg, 
                        noverlap=nperseg // 2, window='hann')
    return freqs, psd
Design choices:
nperseg = 512 (2 seconds at 256 Hz): gives 0.5 Hz frequency resolution, which is exactly the ± 0.5 Hz window we need around the beat frequency
50% overlap: standard for Welch method, reduces variance
Hann window: good sidelobe suppression, prevents spectral leakage from strong alpha peaks bleeding into nearby beat frequencies
3.3 The 1/f Background Problem
EEG power spectra follow a 1/fβ distribution (pink noise), where β ≈ 1.0–2.0. This means lower frequencies naturally have MORE power than higher frequencies. A naive "is there power at the beat frequency?" check would always say yes — there's always power everywhere.
The solution: estimate the 1/f background and measure EXCESS power above it.
def estimate_1f_background(freqs: np.ndarray, psd: np.ndarray, 
                            beat_freq: float, exclude_width: float = 2.0) -> float:
    """Estimate 1/f background power at the beat frequency.
    
    Fits a linear regression in log-log space to the PSD, excluding a window
    around the beat frequency (and its harmonics) to avoid the ASSR itself
    inflating the background estimate.
    
    Args:
        freqs: Frequency array from Welch PSD
        psd: Power spectral density array
        beat_freq: Current beat frequency in Hz
        exclude_width: Hz to exclude around beat frequency and harmonics
    Returns:
        Estimated 1/f background power at beat_freq (in same units as PSD)
    """
    # Exclude DC, very low frequencies, and windows around beat freq + harmonics
    mask = (freqs >= 1.0) & (freqs <= 45.0)
    
    # Exclude beat frequency and first two harmonics
    for harmonic in [1, 2, 3]:
        f_center = beat_freq * harmonic
        mask &= ~((freqs >= f_center - exclude_width) & 
                   (freqs <= f_center + exclude_width))
    
    # Also exclude alpha band if beat freq isn't in it (alpha is a natural peak)
    if not (8.0 <= beat_freq <= 13.0):
        mask &= ~((freqs >= 8.0) & (freqs <= 13.0))
    
    fit_freqs = freqs[mask]
    fit_psd = psd[mask]
    
    if len(fit_freqs) < 5:
        return np.median(psd[(freqs >= 1.0) & (freqs <= 45.0)])
    
    # Linear regression in log-log space: log(PSD) = -β * log(f) + log(A)
    log_f = np.log10(fit_freqs)
    log_p = np.log10(fit_psd + 1e-20)  # Avoid log(0)
    
    coeffs = np.polyfit(log_f, log_p, 1)
    
    # Predict background at beat frequency
    log_bg = coeffs[0] * np.log10(beat_freq) + coeffs[1]
    return 10 ** log_bg
3.4 Excess Power and Entrainment Strength
def compute_entrainment_strength(freqs: np.ndarray, psd: np.ndarray,
                                   beat_freq: float, 
                                   window: float = 0.5) -> tuple[float, float]:
    """Compute entrainment strength from excess power at beat frequency.
    
    Args:
        freqs: Frequency array from Welch PSD
        psd: Power spectral density array  
        beat_freq: Current beat frequency in Hz
        window: Hz window around beat frequency to measure (± this value)
    Returns:
        (entrainment_strength, excess_ratio)
        - entrainment_strength: 0.0-1.0 normalized metric
        - excess_ratio: raw ratio of measured power to background (for logging)
    """
    # Measure power in beat frequency window
    beat_mask = (freqs >= beat_freq - window) & (freqs <= beat_freq + window)
    if not np.any(beat_mask):
        return 0.0, 0.0
    
    measured_power = np.max(psd[beat_mask])  # Peak power in window
    
    # Estimate 1/f background
    background = estimate_1f_background(freqs, psd, beat_freq)
    
    if background <= 0:
        return 0.0, 0.0
    
    # Excess ratio: how many times above background
    excess_ratio = measured_power / background
    
    # Convert to 0.0-1.0 scale
    # Ratio of 1.0 = no excess (strength 0.0)
    # Ratio of 2.0 = 2x background (moderate entrainment, strength ~0.4)
    # Ratio of 5.0 = 5x background (strong entrainment, strength ~0.8)
    # Ratio of 10.0+ = very strong entrainment (strength ~1.0)
    if excess_ratio <= 1.0:
        strength = 0.0
    else:
        # Logarithmic mapping: strength = log2(ratio) / log2(10)
        # This gives: ratio 2 → 0.30, ratio 4 → 0.60, ratio 8 → 0.90, ratio 10 → 1.0
        strength = min(1.0, np.log2(excess_ratio) / np.log2(10.0))
    
    return round(strength, 3), round(excess_ratio, 2)
3.5 Multi-Channel Fusion
def compute_assr_multichannel(board, n_samples: int, beat_freq: float,
                                sqi: dict) -> dict:
    """Compute ASSR entrainment strength across all clean channels.
    
    Uses frontal channels (AF7, AF8) as primary — they have strongest ASSR.
    Temporal channels (TP9, TP10) provide confirmation.
    
    Args:
        board: BrainFlow board object
        n_samples: Number of samples to analyze (30-60 seconds worth)
        beat_freq: Current beat frequency in Hz
        sqi: Per-channel SQI dict from Bible Ch.2 Â§SQI
    Returns:
        Dict with entrainment metrics
    """
    from brainflow.board_shim import BoardShim, BrainFlowPresets
    
    data = board.get_current_board_data(n_samples, preset=BrainFlowPresets.DEFAULT_PRESET)
    eeg_channels = BoardShim.get_eeg_channels(38)
    channel_names = ["tp9", "af7", "af8", "tp10"]
    
    # Weight frontal channels higher (stronger ASSR expected)
    weights = {"tp9": 0.15, "af7": 0.35, "af8": 0.35, "tp10": 0.15}
    
    channel_strengths = {}
    weighted_sum = 0.0
    weight_total = 0.0
    
    for i, ch_idx in enumerate(eeg_channels[:4]):
        name = channel_names[i]
        
        # Only use channels that pass SQI
        if sqi.get(name, 0.0) < 0.5:
            continue
        
        ch_data = data[ch_idx, :]
        freqs, psd = compute_assr_psd(ch_data)
        strength, ratio = compute_entrainment_strength(freqs, psd, beat_freq)
        
        channel_strengths[name] = {"strength": strength, "excess_ratio": ratio}
        weighted_sum += strength * weights[name]
        weight_total += weights[name]
    
    # Composite entrainment strength
    composite = round(weighted_sum / weight_total, 3) if weight_total > 0 else 0.0
    
    # Detection confidence based on channel agreement
    if len(channel_strengths) >= 3:
        values = [v["strength"] for v in channel_strengths.values()]
        std_dev = np.std(values)
        agreement = "high" if std_dev < 0.15 else "moderate" if std_dev < 0.30 else "low"
    else:
        agreement = "insufficient_channels"
    
    return {
        "entrainment_strength": composite,
        "channel_detail": channel_strengths,
        "channel_agreement": agreement,
        "beat_freq_tested": beat_freq,
    }
Section 4: Detection Window and Timing
4.1 Minimum Window: 30 Seconds
ASSR detection requires spectral estimation with sufficient frequency resolution and enough averaging to reduce noise. The minimum viable window is 30 seconds:
At 256 Hz sampling: 7,680 samples
With nperseg=512 and 50% overlap: ~29 segments averaged
Frequency resolution: 0.5 Hz (sufficient to isolate beat frequencies that differ by at least 1 Hz)
4.2 Optimal Window: 60 Seconds
60 seconds doubles the number of averaged segments, significantly improving SNR:
At 256 Hz: 15,360 samples
~59 segments averaged
More robust against brief artifacts that might slip through SQI gating
4.3 Update Cadence
ASSR should NOT be computed every second like SQI. It is a slow metric:
Compute every 30 seconds using a sliding 60-second window
This means the first ASSR result is available 60 seconds into the session
Each subsequent result uses the most recent 60 seconds of data
The agent should not make modality-switching decisions based on a single ASSR measurement — require 2 consecutive low readings (60 seconds of evidence) before switching
4.4 Session Timeline Integration
class ASSRTracker:
    """Tracks ASSR entrainment strength over session duration."""
    
    def __init__(self, min_window_seconds: int = 60, update_interval: int = 30):
        self._min_window = min_window_seconds
        self._update_interval = update_interval
        self._history = []  # List of (timestamp, strength, beat_freq) tuples
        self._last_update = 0.0
        self._modality_switch_count = 0
        self._max_switches = 3  # Don't oscillate forever
    
    def should_update(self, session_elapsed: float) -> bool:
        """Check if enough time has passed for a new ASSR computation."""
        if session_elapsed < self._min_window:
            return False
        return (session_elapsed - self._last_update) >= self._update_interval
    
    def record(self, timestamp: float, strength: float, beat_freq: float) -> None:
        """Record an ASSR measurement."""
        self._history.append((timestamp, strength, beat_freq))
        self._last_update = timestamp
    
    def get_trend(self, n_recent: int = 4) -> str:
        """Determine entrainment trend from recent measurements.
        
        Returns: "rising", "stable", "declining", "absent", or "insufficient_data"
        """
        if len(self._history) < 2:
            return "insufficient_data"
        
        recent = [h[1] for h in self._history[-n_recent:]]
        
        if all(s < 0.1 for s in recent):
            return "absent"
        
        if len(recent) >= 3:
            slope = (recent[-1] - recent[0]) / len(recent)
            if slope > 0.05:
                return "rising"
            elif slope < -0.05:
                return "declining"
        
        return "stable"
    
    def should_switch_modality(self) -> bool:
        """Recommend modality switch if entrainment is consistently absent.
        
        Requires 2+ consecutive readings below threshold AND
        hasn't exceeded max switch count.
        """
        if self._modality_switch_count >= self._max_switches:
            return False
        
        if len(self._history) < 2:
            return False
        
        recent_two = [h[1] for h in self._history[-2:]]
        return all(s < 0.1 for s in recent_two)
Section 5: Modality Switching Protocol
5.1 When to Switch
If binaural beats produce no detectable ASSR after 2 consecutive measurements (minimum 90 seconds of evidence), the agent should consider switching to isochronic (monaural) beats at the same frequency.
Rationale (Orozco Perez et al. 2020): monaural beats produce stronger cortical entrainment than binaural beats. A user who doesn't entrain to binaural may entrain to isochronic.
5.2 Switching Protocol
def handle_entrainment_check(tracker: ASSRTracker, current_modality: str,
                               current_beat_freq: float) -> dict:
    """Agent decision function for entrainment-based adaptation.
    
    Args:
        tracker: ASSRTracker instance
        current_modality: "binaural" or "isochronic"
        current_beat_freq: Current beat frequency in Hz
    Returns:
        Dict of live_control.json updates (may be empty if no change needed)
    """
    trend = tracker.get_trend()
    updates = {}
    
    if trend == "absent" and tracker.should_switch_modality():
        if current_modality == "binaural":
            # Try isochronic — stronger cortical entrainment expected
            updates = {
                "beat_modality": "isochronic",
                "eeg_entrainment_modality_reason": "binaural_assr_absent_switching_to_isochronic",
            }
            tracker._modality_switch_count += 1
        elif current_modality == "isochronic":
            # Isochronic also failed — this user may not entrain at this frequency
            # Try shifting frequency by 1 Hz (individual variation)
            updates = {
                "beat_freq": current_beat_freq + 1.0,
                "eeg_entrainment_modality_reason": "isochronic_assr_absent_shifting_frequency",
            }
            tracker._modality_switch_count += 1
    
    elif trend == "declining":
        # During sleep onset sessions, declining ASSR is EXPECTED and GOOD
        # Check session type before intervening
        updates = {
            "eeg_entrainment_trend": "declining",
            # Agent should check session_type before acting on this
        }
    
    elif trend == "rising" or trend == "stable":
        # Entrainment is working — no changes needed
        updates = {
            "eeg_entrainment_trend": trend,
        }
    
    return updates
5.3 Switching Limits
Maximum 3 modality/frequency switches per session
After exhausting switches, the agent accepts that ASSR is not detectable for this user/session and operates on session timeline only
This prevents endless oscillation between modalities
Log all switches for post-session analysis
5.4 Sleep Onset Exception
Critical: During sleep onset sessions (Bible Ch.7 Â§Sleep-Onset), declining ASSR is a POSITIVE signal. The agent should NEVER switch modality in response to declining ASSR during a sleep onset session.
As the user transitions from wakefulness toward sleep, cortical responsiveness to external stimuli decreases. ASSR amplitude naturally declines through NREM Stage 1 and Stage 2. Instead of triggering a modality switch, declining ASSR during sleep onset should increase trance_score confidence.
def interpret_assr_decline(session_type: str, trance_score: float, 
                            assr_trend: str) -> str:
    """Interpret declining ASSR based on session context.
    
    Returns interpretation string for agent decision-making.
    """
    if session_type == "sleep_onset" and assr_trend == "declining":
        if trance_score > 0.6:
            return "expected_sleep_transition"  # Don't intervene
        else:
            return "possible_disengagement"  # User may be restless, not sleeping
    
    if session_type in ("trance", "relaxation") and assr_trend == "declining":
        return "possible_entrainment_loss"  # May warrant modality switch
    
    return "nominal"
Section 6: SQI Integration (Bible Ch.2 Â§SQI Dependency)
6.1 Hard Gate
ASSR computation is ONLY valid at FULL CONFIDENCE SQI level:
Composite SQI ≥ 0.7
All 4 channels usable (SQI ≥ 0.5 each)
At any lower confidence level, ASSR results are unreliable because:
Muscle artifact adds broadband power that raises the 1/f background estimate, potentially masking a real ASSR
Eye blink artifacts on frontal channels (the primary ASSR detection channels) corrupt the measurement
A single bad channel breaks the multi-channel fusion weighting
6.2 Graceful Degradation
When SQI drops below FULL CONFIDENCE mid-session:
Freeze the last valid ASSR measurement (don't overwrite with garbage)
Mark eeg_entrainment_confidence as "frozen"
Resume ASSR computation when SQI returns to FULL CONFIDENCE
If SQI doesn't recover within 5 minutes, mark ASSR as "unavailable" for the remainder of the session
def gate_assr_computation(sqi_composite: float, sqi_usable: int,
                            last_valid_assr: float, 
                            frozen_duration: float) -> dict:
    """Gate ASSR computation based on SQI confidence level.
    
    Args:
        sqi_composite: Current composite SQI (0.0-1.0)
        sqi_usable: Number of channels with SQI >= 0.5
        last_valid_assr: Last valid entrainment strength measurement
        frozen_duration: Seconds since ASSR was last validly computed
    Returns:
        Dict with gating decision and live_control.json updates
    """
    if sqi_composite >= 0.7 and sqi_usable == 4:
        return {
            "compute_assr": True,
            "eeg_entrainment_confidence": "active",
        }
    
    if frozen_duration > 300:  # 5 minutes
        return {
            "compute_assr": False,
            "eeg_entrainment_confidence": "unavailable",
            "eeg_entrainment_strength": 0.0,
        }
    
    return {
        "compute_assr": False,
        "eeg_entrainment_confidence": "frozen",
        "eeg_entrainment_strength": last_valid_assr,  # Keep last valid reading
    }
Section 7: live_control.json Keys
All ASSR-related keys written to live_control.json by the ASSR module:
Key
Type
Range
Default
Written By
Description
eeg_entrainment_strength
float
0.0–1.0
0.0
ASSR module
Composite entrainment strength across clean channels. 0.0 = no detectable entrainment, 1.0 = very strong entrainment (10× background power at beat frequency).
eeg_entrainment_confidence
string
"active" / "frozen" / "unavailable"
"unavailable"
ASSR module
Current confidence in the entrainment measurement. "active" = computing normally, "frozen" = SQI too low, holding last valid value, "unavailable" = never computed or SQI low for > 5 minutes.
eeg_entrainment_trend
string
"rising" / "stable" / "declining" / "absent" / "insufficient_data"
"insufficient_data"
ASSR module
Trend direction over the last 2–4 measurements.
eeg_entrainment_beat_freq
float
0.5–45.0
0.0
ASSR module
The beat frequency that was tested (for correlation with delivered frequency).
eeg_entrainment_modality_reason
string
free text
""
ASSR module
Reason for the most recent modality switch recommendation, if any.
eeg_entrainment_channel_agreement
string
"high" / "moderate" / "low" / "insufficient_channels"
"insufficient_channels"
ASSR module
How well the four channels agree on entrainment strength. High agreement = more reliable measurement.
Section 8: Agent Protocol — Full Integration
8.1 Session Initialization
def assr_agent_init(config: dict) -> None:
    """Initialize ASSR tracking at session start.
    
    Called once during session setup.
    """
    _patch_live({
        "eeg_entrainment_strength": 0.0,
        "eeg_entrainment_confidence": "unavailable",
        "eeg_entrainment_trend": "insufficient_data",
        "eeg_entrainment_beat_freq": 0.0,
        "eeg_entrainment_modality_reason": "",
        "eeg_entrainment_channel_agreement": "insufficient_channels",
    })
8.2 Per-Cycle Agent Logic
def assr_agent_cycle(board, tracker: ASSRTracker, session_elapsed: float,
                      beat_freq: float, beat_modality: str, session_type: str,
                      sqi_composite: float, sqi_usable: int, sqi: dict) -> None:
    """Agent ASSR processing cycle — call every 30 seconds after first 60 seconds.
    
    This is the main integration point. The agent calls this as part of its
    regular processing loop.
    """
    # Gate on SQI
    gate = gate_assr_computation(sqi_composite, sqi_usable,
                                  tracker._history[-1][1] if tracker._history else 0.0,
                                  session_elapsed - tracker._last_update)
    
    _patch_live({
        "eeg_entrainment_confidence": gate["eeg_entrainment_confidence"],
    })
    
    if not gate.get("compute_assr", False):
        return
    
    # Check timing
    if not tracker.should_update(session_elapsed):
        return
    
    # Compute ASSR (uses 60-second window = 15360 samples at 256 Hz)
    n_samples = 60 * 256  # 60 seconds
    result = compute_assr_multichannel(board, n_samples, beat_freq, sqi)
    
    # Record and publish
    strength = result["entrainment_strength"]
    tracker.record(session_elapsed, strength, beat_freq)
    
    _patch_live({
        "eeg_entrainment_strength": strength,
        "eeg_entrainment_beat_freq": beat_freq,
        "eeg_entrainment_trend": tracker.get_trend(),
        "eeg_entrainment_channel_agreement": result["channel_agreement"],
    })
    
    # Check for modality switching (but NOT during sleep onset decline)
    if session_type == "sleep_onset":
        interpretation = interpret_assr_decline(session_type, 
                                                  # trance_score would come from live_control
                                                  0.5, tracker.get_trend())
        if interpretation == "expected_sleep_transition":
            return  # Don't switch — declining ASSR is expected
    
    # Consider modality switch
    switch_updates = handle_entrainment_check(tracker, beat_modality, beat_freq)
    if switch_updates:
        _patch_live(switch_updates)
8.3 Post-Session Summary
After each session, the agent should log an ASSR summary for the session database (Bible Ch.2 Â§Database):
def assr_session_summary(tracker: ASSRTracker) -> dict:
    """Generate post-session ASSR summary for database storage.
    
    Returns dict suitable for session_results table.
    """
    if not tracker._history:
        return {"assr_detected": False, "assr_summary": "no_data"}
    
    strengths = [h[1] for h in tracker._history]
    
    return {
        "assr_detected": max(strengths) > 0.15,
        "assr_peak_strength": round(max(strengths), 3),
        "assr_mean_strength": round(np.mean(strengths), 3),
        "assr_trend_final": tracker.get_trend(),
        "assr_measurements_count": len(tracker._history),
        "assr_modality_switches": tracker._modality_switch_count,
    }
Section 9: Interpretation Guide for the Agent
Use this table to determine agent behavior based on the eeg_entrainment_strength value:
Entrainment Strength
Interpretation
Agent Action
0.0 – 0.1
No detectable entrainment
After 2 consecutive readings: consider modality switch. After exhausting switches: operate on timeline only. During sleep onset: check if declining (expected) or never-present (possible non-responder).
0.1 – 0.3
Weak entrainment
Entrainment may be present but marginal. Monitor trend — if rising, current approach is working. If stable at this level, the user may be a weak responder to auditory entrainment.
0.3 – 0.5
Moderate entrainment
Entrainment is clearly present. The current modality and frequency are working. No changes needed unless the trend is declining.
0.5 – 0.7
Strong entrainment
Excellent cortical response to beats. The agent can trust that beat frequency changes will be tracked by the brain. Fine-grained frequency adjustments (±0.5 Hz) are viable.
0.7 – 1.0
Very strong entrainment
Exceptional response. The brain is strongly phase-locked to the stimulus. This level is typically seen with isochronic beats or unusually responsive users. The agent can attempt more ambitious frequency leading (moving the target frequency toward the session goal more quickly).
Section 10: Edge Cases and Failure Modes
10.1 Beat Frequency in Alpha Band
When the target beat frequency is in the alpha band (8–13 Hz), the ASSR overlaps with the user's natural alpha rhythm. This creates an ambiguity: is the power at 10 Hz from entrainment or from endogenous alpha?
Resolution: Compare power at beat frequency to the user's IAF (Individual Alpha Frequency, from calibration). If beat frequency and IAF differ by at least 1 Hz, the ASSR can be distinguished. If they overlap, the agent cannot reliably distinguish entrainment from natural alpha.
10.2 Harmonic Contamination
If the beat frequency is F, harmonics at 2F, 3F may also appear in the PSD. These are confirmation of entrainment (the brain's response is nonlinear), not false positives. The algorithm already excludes harmonics from the 1/f background fit.
10.3 Individual Non-Responders
Some individuals simply do not produce detectable ASSRs to auditory beats. This is not a failure of the system — it's normal variation. After exhausting modality switches, the agent should:
Note the user as a potential non-responder in session history
Continue the session using timeline-based adaptation
Not repeatedly attempt to "fix" entrainment in future sessions if the pattern is consistent
10.4 Very Low Beat Frequencies (< 4 Hz)
Delta-range beat frequencies (0.5–4 Hz) used in sleep onset sessions produce very low-frequency ASSRs that are difficult to distinguish from natural delta activity and movement artifacts. For beats below 4 Hz:
Increase the detection window to 90 seconds for better frequency resolution
Raise the excess ratio threshold for "detected" from 2× to 3× background
Accept that detection may not be possible for sub-2 Hz beats
Section 11: Key Research Citations
Orozco Perez, H. D., Dumas, G., & Lehmann, A. (2020). Binaural beats through the auditory pathway: from brainstem to connectivity patterns. eNeuro, 7(2). ENEURO.0232-19.2020.
Schwarz, D. W., & Taylor, P. (2005). Human auditory steady state responses to binaural and monaural beats. Clinical Neurophysiology, 116(3), 658–668.
Shumov, D. E., et al. (2022). The brain as an adaptive filter: auditory steady state response to sound stimuli containing binaural beats during human daytime nap. Journal of Evolutionary Biochemistry and Physiology, 58, 1193–1203.
Bidelman, G. M., & Horn, C. M. (2025). Objective detection of ASSRs based on mutual information. Audiology Research, 15(3), 60.
Welch, P. D. (1967). The use of fast Fourier transform for the estimation of power spectra. IEEE Transactions on Audio and Electroacoustics, 15(2), 70–73.
