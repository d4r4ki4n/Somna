"""
vr_freq_table.py — Frequency Allocation Table (Bible Ch.8 §8.1 §3.2, Bible Ch.8 §8.2 §3.2)
=========================================================================
Tracks every driving frequency used across Somna's VR entrainment stack and
detects collisions between any two frequencies or their harmonics.

A collision is defined as: |freq_A_harm_i − freq_B_harm_j| < GUARD_BAND_HZ
for any (A, B) frequency pair and harmonic indices up to MAX_HARMONICS.

This MUST be checked at VR session start before any stimulation begins.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

GUARD_BAND_HZ = 2.0    # minimum separation between any two driving frequencies/harmonics
MAX_HARMONICS = 3      # check fundamental + 2 harmonics (2f, 3f)


@dataclass
class FreqEntry:
    label:      str
    freq:       float
    subsystem:  str          # e.g. "binaural", "photic", "rivalry_left", "assr"
    active:     bool = True
    notes:      str  = ""


class FrequencyAllocationTable:
    """Registry of all active driving frequencies in the VR session.

    Usage:
        table = FrequencyAllocationTable()
        table.add("binaural_beat",   freq=6.0,  subsystem="binaural")
        table.add("photic_driving",  freq=10.0, subsystem="photic")
        table.add("rivalry_left",    freq=7.5,  subsystem="rivalry")
        table.add("rivalry_right",   freq=12.0, subsystem="rivalry")
        collisions = table.check_collisions()
        if collisions:
            raise ValueError(collisions)
    """

    def __init__(self, guard_band: float = GUARD_BAND_HZ):
        self._entries: list[FreqEntry] = []
        self.guard_band = guard_band

    def add(
        self,
        label: str,
        freq: float,
        subsystem: str = "",
        notes: str = "",
    ) -> None:
        """Register a driving frequency.  Overwrites previous entry with same label."""
        self._entries = [e for e in self._entries if e.label != label]
        self._entries.append(FreqEntry(label=label, freq=freq,
                                       subsystem=subsystem, notes=notes))

    def remove(self, label: str) -> None:
        self._entries = [e for e in self._entries if e.label != label]

    def deactivate(self, label: str) -> None:
        for e in self._entries:
            if e.label == label:
                e.active = False

    def activate(self, label: str) -> None:
        for e in self._entries:
            if e.label == label:
                e.active = True

    def check_collisions(self) -> list[str]:
        """Return list of human-readable collision descriptions.  Empty = safe."""
        active = [e for e in self._entries if e.active and e.freq > 0]
        collisions: list[str] = []

        for i, a in enumerate(active):
            for b in active[i + 1:]:
                for ha in range(1, MAX_HARMONICS + 1):
                    fa = a.freq * ha
                    for hb in range(1, MAX_HARMONICS + 1):
                        fb = b.freq * hb
                        if abs(fa - fb) < self.guard_band:
                            tag_a = f"{a.label}@{ha}x{a.freq:.2f}Hz={fa:.2f}Hz"
                            tag_b = f"{b.label}@{hb}x{b.freq:.2f}Hz={fb:.2f}Hz"
                            gap   = abs(fa - fb)
                            collisions.append(
                                f"COLLISION: {tag_a} vs {tag_b} "
                                f"gap={gap:.2f}Hz (guard={self.guard_band:.1f}Hz)"
                            )
        return collisions

    def validate(self) -> None:
        """Raise ValueError if any collisions exist."""
        problems = self.check_collisions()
        if problems:
            raise ValueError(
                "Frequency allocation conflicts detected — resolve before VR session:\n"
                + "\n".join(f"  {p}" for p in problems)
            )

    def suggest_safe_pair(
        self,
        base_freq: float,
        min_separation: float = 3.0,
        search_range: tuple[float, float] = (5.0, 20.0),
    ) -> Optional[tuple[float, float]]:
        """Given a base frequency, suggest the closest safe second frequency.

        Returns (base_freq, candidate) or None if no safe candidate found.
        """
        existing = [e.freq for e in self._entries if e.active]
        step = 0.5
        f = base_freq + min_separation
        while f <= search_range[1]:
            # Check that this candidate doesn't collide with anything currently registered
            candidate_entry = FreqEntry(label="_test", freq=f, subsystem="test")
            test_table = FrequencyAllocationTable(self.guard_band)
            for e in self._entries:
                test_table._entries.append(e)
            test_table._entries.append(candidate_entry)
            if not test_table.check_collisions():
                return (base_freq, round(f, 1))
            f += step
        return None

    def table_string(self) -> str:
        """Human-readable table for logging."""
        lines = ["Frequency Allocation Table:"]
        lines.append(f"  {'Label':<24} {'Freq':>7}  {'Subsystem':<16} {'Status'}")
        lines.append("  " + "-" * 60)
        for e in sorted(self._entries, key=lambda x: x.freq):
            status = "active" if e.active else "inactive"
            lines.append(f"  {e.label:<24} {e.freq:>6.2f}Hz  {e.subsystem:<16} {status}")
        problems = self.check_collisions()
        if problems:
            lines.append(f"\n  [!] {len(problems)} collision(s) detected:")
            for p in problems:
                lines.append(f"    {p}")
        else:
            lines.append(f"\n  [OK] No collisions (guard band +-{self.guard_band:.1f} Hz)")
        return "\n".join(lines)


def build_session_table(
    binaural_beat_hz: float,
    iaf_hz: float,
    photic_enabled: bool = False,
    photic_hz: float | None = None,
    rivalry_enabled: bool = False,
    rivalry_left_hz: float = 7.5,
    rivalry_right_hz: float = 12.0,
    assr_hz: float | None = None,
) -> FrequencyAllocationTable:
    """Build and validate the full frequency allocation table for a VR session.

    Call at session start before enabling any VR stimulation.
    Raises ValueError on collision.
    """
    t = FrequencyAllocationTable()
    t.add("binaural_beat",  binaural_beat_hz, subsystem="binaural")
    t.add("iaf_reference",  iaf_hz,           subsystem="calibration",
          notes="individual alpha frequency — reference only, not a driver")

    if photic_enabled:
        hz = photic_hz if photic_hz is not None else iaf_hz
        t.add("photic_driving", hz, subsystem="photic")

    if rivalry_enabled:
        if abs(rivalry_left_hz - rivalry_right_hz) < 3.0:
            raise ValueError(
                f"Rivalry tag separation {abs(rivalry_left_hz - rivalry_right_hz):.1f} Hz "
                f"< 3 Hz minimum. Suggest {rivalry_left_hz}/{rivalry_left_hz + 3.5:.1f} Hz."
            )
        t.add("rivalry_left",   rivalry_left_hz,  subsystem="rivalry")
        t.add("rivalry_right",  rivalry_right_hz, subsystem="rivalry")

    if assr_hz is not None:
        t.add("assr_target", assr_hz, subsystem="assr")

    t.validate()
    return t
