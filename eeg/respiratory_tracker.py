"""
respiratory_tracker.py — Respiratory phase tracking for the phase-cascade delivery gate (Bible Ch.4 §4.6 §4.2, §6)

Mode 1 (synthetic): phase derived from breath_rate clock — mathematically coherent
with the audio AM modulation Somna already produces, so what the user hears and when text fires
are the same signal.

Mode 2 (ppg): actual respiratory phase from PPG-RSA on Muse 2 (Bible Ch.2 §2.9).
PPGEngine writes ppg_breath_phase + ppg_breath_rate to live_control.json every second.
EEGEngine calls update_ppg_phase() which switches mode and stores the external phase.
All consumers of get_phase() / is_hot() automatically use the real signal with no other
changes — the RespiratoryTracker interface is mode-transparent.

The adaptive hot window shifts per Conductor phase (Sánchez Corzo 2025).
"""

import time


# Per-Conductor-phase hot window defaults — Sánchez Corzo 2025 + Tort 2025.
# Format: (start, end) as fraction of 0.0–1.0 breath cycle.
# CALIBRATION and FRAC_EMERGE entries are None → gate disabled.
CONDUCTOR_HOT_WINDOWS: dict[str, tuple[float, float] | None] = {
    "CALIBRATION":       None,           # measuring baseline — no gating
    "INDUCTION":         (0.6, 0.9),     # late expiration — parasympathetic deepening
    "DEEPENING":         (0.5, 0.8),     # mid-late expiration — coupling shifts earlier
    "MAINTENANCE":       (0.4, 0.7),     # mid expiration — deep state midpoint
    "FRAC_EMERGE":       None,           # fractionation — fire freely to anchor
    "FRAC_EMERGE_HOLD":  None,
    "FRAC_REDROP":       (0.6, 0.9),     # re-induction — same as initial
    "SLEEP_APPROACH":    (0.3, 0.6),     # early-mid expiration — sleep onset shift
    "SLEEP_ONSET":       (0.2, 0.5),     # minimal intervention
}

_DEFAULT_HOT_WINDOW = (0.6, 0.9)


class RespiratoryTracker:
    """
    Tracks respiratory phase for the phase-cascade delivery gate.

    update_breath_rate() must be called whenever breath_rate changes in live_control.json.
    update_hot_window() is called by the Conductor when FSM state transitions occur.
    """

    def __init__(self, breath_rate: float = 0.10):
        self.breath_rate  = max(0.01, breath_rate)
        self._start_time  = time.monotonic()
        self._hot_window  = _DEFAULT_HOT_WINDOW
        self._window_override: tuple[float, float] | None = None
        self.mode = "synthetic"
        self._ppg_phase: float = 0.0   # updated by EEGEngine when PPG is live

    # ── Phase retrieval ───────────────────────────────────────────────────────

    def get_phase(self) -> float:
        """Returns current respiratory phase 0.0–1.0."""
        if self.mode == "ppg":
            return self._ppg_phase
        # synthetic mode: advance a monotonic clock
        elapsed = time.monotonic() - self._start_time
        return (elapsed * self.breath_rate) % 1.0

    def is_hot(self) -> bool:
        """Returns True if the current respiratory phase is inside the active hot window."""
        window = self._window_override or self._hot_window
        if window is None:
            return False
        phase = self.get_phase()
        lo, hi = window
        if lo <= hi:
            return lo <= phase <= hi
        else:  # wraps around 1.0
            return phase >= lo or phase <= hi

    # ── Configuration ─────────────────────────────────────────────────────────

    def update_ppg_phase(self, phase: float, breath_rate: float) -> None:
        """Switch to PPG mode and update phase from PPGEngine output (Bible Ch.2 §2.9).

        Called by EEGEngine once per second when ppg_available is True.
        Switches mode from 'synthetic' to 'ppg' on first call and logs the
        transition.  All subsequent get_phase() calls return the PPG-derived
        phase directly.
        """
        if self.mode != "ppg":
            self.mode = "ppg"
            print("[RespiratoryTracker] Switched to PPG mode — real respiratory data.")
        self._ppg_phase  = float(phase)
        # Keep breath_rate in sync so state_dict() reports a meaningful value
        if breath_rate > 0:
            self.breath_rate = breath_rate

    def update_breath_rate(self, new_rate: float):
        """
        Called when breath_rate changes in live_control.json.
        Re-anchors the synthetic clock so phase continuity is preserved across
        the rate change — the current phase stays the same, only future rate differs.
        """
        if new_rate == self.breath_rate or new_rate <= 0:
            return
        # Preserve current phase across the rate change
        current_phase = self.get_phase()
        self.breath_rate = new_rate
        # Recompute start_time so current_phase = (elapsed_new * new_rate) % 1.0
        elapsed_equiv   = current_phase / new_rate
        self._start_time = time.monotonic() - elapsed_equiv

    def update_hot_window(self, window: tuple[float, float] | None):
        """
        Called by the Conductor when FSM phase transitions occur.
        Clears any agent override — the override is per-phase and resets on transition.
        """
        self._hot_window      = window
        self._window_override = None

    def set_conductor_phase(self, phase_name: str):
        """Convenience: look up the default hot window for a Conductor FSM phase."""
        window = CONDUCTOR_HOT_WINDOWS.get(phase_name, _DEFAULT_HOT_WINDOW)
        self.update_hot_window(window)

    def apply_agent_override(self, window: tuple[float, float], note: str = ""):
        """
        Agent can nudge the hot window via agent_conductor_hints.resp_hot_window_override.
        Override persists until the next Conductor phase transition.
        """
        self._window_override = window
        if note:
            print(f"[RespiratoryTracker] Agent override applied: {window} — {note}")

    # ── State readout ─────────────────────────────────────────────────────────

    def state_dict(self) -> dict:
        """Current state for writing to live_control.json."""
        window = self._window_override or self._hot_window
        return {
            "respiratory_phase":     round(self.get_phase(), 4),
            "respiratory_hot":       self.is_hot(),
            "resp_hot_window_start": window[0] if window else 0.0,
            "resp_hot_window_end":   window[1] if window else 1.0,
            "respiratory_mode":      self.mode,   # "synthetic" or "ppg"
        }
