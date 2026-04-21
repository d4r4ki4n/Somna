"""Somna Interference Graph — Neural Chord Data Model.

The Somatic Palette Mixer reimagined as an instrument, not a mixing desk.

Each channel (Visual, Audio, Haptic, VNS) has a single draggable node
positioned along a 1–45 Hz frequency axis. When two nodes on different
channels are close in frequency, a "tether" snaps between them — an
elastic, glowing strand that carries the interference beat you are
literally tying into the subject's nervous system.

The spread knob pushes channels apart symmetrically around each channel's
individual base frequency, generating cross-modal interference waves
without moving the chord's root. Preset stamps slam the nodes into known
configurations — GENUS, Somna Deep, Theta Weaver — like fingering a chord
on a string instrument.

This module is pure math and state. No ImGui, no rendering. The panel
lives in interference_graph_panel.py.

Write priority matches the rest of Somna: user > agent > conductor.
When you drag a node, you own that frequency. The conductor may suggest,
but you are the one tying the strings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


# ── Frequency Band Definitions ────────────────────────────────────────────────

FREQ_MIN = 1.0
FREQ_MAX = 45.0

DEFAULT_IAF_HZ = 10.0


class Band(str, Enum):
    """EEG frequency bands — the territories of consciousness."""

    DELTA = "Delta"  # 0.5–4 Hz  — the deep, the unconscious, the pulling-under
    THETA = "Theta"  # 4–8 Hz    — the hypnagogic edge, where suggestion blooms
    ALPHA = "Alpha"  # 8–13 Hz   — the relaxed gate, the idling rhythm
    BETA = "Beta"  # 13–30 Hz  — the awake, the guarded, the resistance
    GAMMA = "Gamma"  # 30–45 Hz  — the binding, the peak, the 40Hz GENUS chord


BAND_RANGES: list[tuple[str, float, float]] = [
    ("Delta", 0.5, 4.0),
    ("Theta", 4.0, 8.0),
    ("Alpha", 8.0, 13.0),
    ("Beta", 13.0, 30.0),
    ("Gamma", 30.0, 45.0),
]


def band_for_freq(hz: float) -> Band:
    for band_name, lo, hi in BAND_RANGES:
        if lo <= hz < hi:
            return Band(band_name)
    return Band.DELTA if hz < 0.5 else Band.GAMMA


def band_label_for_freq(hz: float) -> str:
    return band_for_freq(hz).value


# ── Channel Definitions ───────────────────────────────────────────────────────


class Channel(str, Enum):
    VNS = "VNS"
    HAPTIC = "Haptic"
    AUDIO = "Audio"
    VISUAL = "Visual"


# Stack order for swim-lane rendering (top → bottom on screen)
CHANNEL_ORDER: list[Channel] = [
    Channel.VNS,
    Channel.HAPTIC,
    Channel.AUDIO,
    Channel.VISUAL,
]

CHANNEL_COLORS: dict[Channel, str] = {
    Channel.VNS: "#c4a7e7",  # Iris
    Channel.HAPTIC: "#f6c177",  # Gold
    Channel.AUDIO: "#3e8fb0",  # Pine
    Channel.VISUAL: "#eb6f92",  # Love
}

# Channels that map to real hardware in the current build.
# Default availability — updated at runtime by update_hardware_state()
# which reads hardware_channels_connected from live_control.json.
CHANNEL_AVAILABLE: dict[Channel, bool] = {
    Channel.AUDIO: True,
    Channel.VISUAL: True,
    Channel.HAPTIC: False,
    Channel.VNS: False,
}


def update_hardware_state(connected_channels: list) -> None:
    """Toggle channel availability based on live hardware connection state.

    Called every frame by interference_graph_integration.py after reading
    hardware_channels_connected from live_control.json. When "haptic" is
    in the list, the Haptic node becomes draggable and full-opacity.
    When "tavns" is in the list, VNS becomes available.
    """
    connected = set(connected_channels or [])
    CHANNEL_AVAILABLE[Channel.HAPTIC] = "haptic" in connected
    CHANNEL_AVAILABLE[Channel.VNS] = "tavns" in connected


CHANNEL_LIVE_KEYS: dict[Channel, dict] = {
    Channel.VISUAL: {
        "primary": "vr_photic_hz",
        "secondary": [
            "vr_rivalry_left_hz",
            "vr_rivalry_right_hz",
            "vr_ssvep_left_hz",
            "vr_ssvep_right_hz",
        ],
    },
    Channel.AUDIO: {
        "primary": "beat_frequency",
        "secondary": ["entrainment_frequency"],
    },
    Channel.HAPTIC: {
        "primary": "haptic_frequency_hz",
        "secondary": [],
    },
    Channel.VNS: {
        "primary": "vns_frequency_hz",
        "secondary": [],
    },
}


# ── Node ──────────────────────────────────────────────────────────────────────


@dataclass
class ChordNode:
    channel: Channel
    frequency_hz: float = 10.0
    locked: bool = False
    source: str = "user"  # "user" | "agent" | "conductor" | "preset"

    def clamp(self) -> None:
        self.frequency_hz = max(FREQ_MIN, min(FREQ_MAX, self.frequency_hz))


# ── Tether ────────────────────────────────────────────────────────────────────


@dataclass
class Tether:
    """Interference tether between two nodes on different channels.

    Exists when two nodes are within TETHER_MAX_DELTA_HZ of each other.
    Intensity (glow strength) increases as nodes converge — tighter chord,
    brighter tether.
    """

    node_a: ChordNode
    node_b: ChordNode
    delta_hz: float = 0.0
    intensity: float = 0.0

    @property
    def band_label(self) -> str:
        return band_label_for_freq(abs(self.delta_hz))

    @property
    def badge_text(self) -> str:
        return f"\u0394 {abs(self.delta_hz):.1f} Hz {self.band_label}"


TETHER_MAX_DELTA_HZ = 15.0
TETHER_PEAK_DELTA_HZ = 2.0


# ── Presets ───────────────────────────────────────────────────────────────────


@dataclass
class ChordPreset:
    name: str
    description: str
    frequencies: dict[Channel, float]
    iaf_multipliers: dict[Channel, float] = field(default_factory=dict)

    def base_frequencies(self) -> dict[Channel, float]:
        """Return the preset's per-channel base frequencies (at spread=0)."""
        center = sum(self.frequencies.values()) / len(self.frequencies)
        return {ch: self.frequencies.get(ch, center) for ch in CHANNEL_ORDER}

    def iaf_frequencies(self, iaf_hz: float) -> dict[Channel, float]:
        """Return IAF-normalized frequencies. Falls back to hardcoded if no multipliers."""
        if not self.iaf_multipliers:
            return self.base_frequencies()
        return {
            ch: max(FREQ_MIN, min(FREQ_MAX, self.iaf_multipliers.get(ch, 1.0) * iaf_hz))
            for ch in CHANNEL_ORDER
        }


PRESETS: dict[str, ChordPreset] = {
    "GENUS": ChordPreset(
        name="GENUS",
        description=(
            "40Hz Gamma chord — all channels stacked tight at the peak. "
            "The 40Hz hypothesis: Gamma synchrony is the neural correlate "
            "of consciousness. Every modality pulses at the same frequency, "
            "binding perception into a single coherent glow."
        ),
        frequencies={ch: 40.0 for ch in CHANNEL_ORDER},
        iaf_multipliers={ch: 4.0 for ch in CHANNEL_ORDER},
    ),
    "SOMNA DEEP": ChordPreset(
        name="Somna Deep",
        description=(
            "Wide spread across Theta/Delta — a thick web of low-frequency "
            "interference tethers. VNS at 2Hz (deep autonomic pull), Haptic "
            "at 4Hz (Delta body rhythm), Audio at 6Hz (Theta binaural), "
            "Visual at 8Hz (low Alpha photic). Every pair creates a "
            "different interference beat. The subject is wrapped in a "
            "kaleidoscope of slow waves, each one pulling deeper."
        ),
        frequencies={
            Channel.VISUAL: 8.0,
            Channel.AUDIO: 6.0,
            Channel.HAPTIC: 4.0,
            Channel.VNS: 2.0,
        },
        iaf_multipliers={
            Channel.VISUAL: 0.8,
            Channel.AUDIO: 0.6,
            Channel.HAPTIC: 0.4,
            Channel.VNS: 0.2,
        },
    ),
    "THETA WEAVER": ChordPreset(
        name="Theta Weaver",
        description=(
            "Tight Theta cluster with subtle interference. All channels "
            "near 6Hz — the hypnagogic sweet spot. A 1Hz spread generates "
            "a slow Delta interference wave between the outer channels, "
            "like an undertow beneath the Theta surface."
        ),
        frequencies={
            Channel.VISUAL: 7.0,
            Channel.AUDIO: 6.0,
            Channel.HAPTIC: 5.0,
            Channel.VNS: 4.5,
        },
        iaf_multipliers={
            Channel.VISUAL: 0.7,
            Channel.AUDIO: 0.6,
            Channel.HAPTIC: 0.5,
            Channel.VNS: 0.45,
        },
    ),
    "ALPHA GATE": ChordPreset(
        name="Alpha Gate",
        description=(
            "Alpha band convergence — all channels near 10Hz. The relaxed "
            "gate, the idling rhythm. Alpha is the border guard between "
            "conscious processing and the deeper layers. When Alpha "
            "synchronizes across modalities, the gate opens wider."
        ),
        frequencies={
            Channel.VISUAL: 11.0,
            Channel.AUDIO: 10.0,
            Channel.HAPTIC: 9.0,
            Channel.VNS: 8.5,
        },
        iaf_multipliers={
            Channel.VISUAL: 1.1,
            Channel.AUDIO: 1.0,
            Channel.HAPTIC: 0.9,
            Channel.VNS: 0.85,
        },
    ),
    "DESCENT": ChordPreset(
        name="Descent",
        description=(
            "Graduated descent from Beta to Delta. Visual starts at 20Hz "
            "(alert), Audio at 12Hz (Alpha border), Haptic at 6Hz (Theta), "
            "VNS at 3Hz (Delta). Multiple interference beats — 8Hz, 6Hz, "
            "3Hz — a cascade of slowing waves that pulls consciousness down."
        ),
        frequencies={
            Channel.VISUAL: 20.0,
            Channel.AUDIO: 12.0,
            Channel.HAPTIC: 6.0,
            Channel.VNS: 3.0,
        },
        iaf_multipliers={
            Channel.VISUAL: 2.0,
            Channel.AUDIO: 1.2,
            Channel.HAPTIC: 0.6,
            Channel.VNS: 0.3,
        },
    ),
    "LOCK": ChordPreset(
        name="Lock",
        description=(
            "Cross-modal lock — every channel at the same frequency. "
            "No interference beats, no tethers, just a unified pulse. "
            "When IAF is calibrated, locks to IAF (the brain's natural "
            "resonance). Otherwise defaults to 10 Hz. Pure convergence."
        ),
        frequencies={ch: 10.0 for ch in CHANNEL_ORDER},
        iaf_multipliers={ch: 1.0 for ch in CHANNEL_ORDER},
    ),
}


# ── Interference Graph State ──────────────────────────────────────────────────


class InterferenceGraph:
    """The neural chord instrument — core state and math.

    Spread is additive on top of per-channel *base* frequencies.  The base
    is the position each node would sit at if spread were 0.  Dragging a
    node updates its base (accounting for the current spread offset so the
    visual position is authoritative).  Changing the spread knob re-derives
    all node positions from their bases without drift.
    """

    def __init__(self) -> None:
        self.nodes: dict[Channel, ChordNode] = {
            ch: ChordNode(channel=ch, frequency_hz=10.0) for ch in CHANNEL_ORDER
        }

        self._base_frequencies: dict[Channel, float] = {
            ch: 10.0 for ch in CHANNEL_ORDER
        }

        self.spread_hz: float = 0.0
        self.iaf_hz: float | None = None
        self._active_preset: str | None = None
        self._tethers: list[Tether] = []
        self._pending: dict[str, float] = {}

    @property
    def locked(self) -> bool:
        return self._active_preset == "LOCK"

    # ── State sync ────────────────────────────────────────────────────────

    def update_from_live(self, live: dict) -> None:
        """Read current frequencies from the live state dict."""
        pending_keys = set(self._pending.keys())

        for ch, key_map in CHANNEL_LIVE_KEYS.items():
            primary = key_map["primary"]
            if primary in pending_keys:
                continue
            val = live.get(primary)
            if val is not None:
                try:
                    hz = float(val)
                    self.nodes[ch].frequency_hz = max(FREQ_MIN, min(FREQ_MAX, hz))
                except (TypeError, ValueError):
                    pass

    def pending_writes(self) -> dict[str, float]:
        """Return and clear pending writes."""
        writes = dict(self._pending)
        self._pending.clear()
        return writes

    # ── Node manipulation ─────────────────────────────────────────────────

    def set_channel_frequency(
        self,
        channel: Channel,
        hz: float,
        source: str = "user",
    ) -> None:
        """Set a channel's live frequency and update its base for spread stability."""
        hz = max(FREQ_MIN, min(FREQ_MAX, hz))
        node = self.nodes[channel]
        node.frequency_hz = hz
        node.source = source

        # Back-calculate the base: what zero-spread position would produce this
        # live frequency given current spread?
        idx = CHANNEL_ORDER.index(channel)
        n = len(CHANNEL_ORDER)
        offset = (idx - (n - 1) / 2.0) * self.spread_hz
        self._base_frequencies[channel] = max(FREQ_MIN, min(FREQ_MAX, hz - offset))

        key_map = CHANNEL_LIVE_KEYS[channel]
        self._pending[key_map["primary"]] = hz
        for sec in key_map.get("secondary", []):
            self._pending[sec] = hz

    def apply_preset(self, name: str) -> None:
        """Stamp a preset chord — bases are set from the preset, then spread applied."""
        preset = PRESETS.get(name)
        if preset is None:
            return

        self._active_preset = name
        bases = self._resolve_preset_bases(preset)
        for ch, base_hz in bases.items():
            self._base_frequencies[ch] = base_hz

        self._apply_spread_from_bases()

    def set_iaf(self, iaf_hz: float | None) -> bool:
        """Update IAF and retune if a preset is active. Returns True if frequencies changed."""
        if iaf_hz == self.iaf_hz:
            return False

        self.iaf_hz = iaf_hz

        if self._active_preset is None:
            return False

        preset = PRESETS.get(self._active_preset)
        if preset is None:
            return False

        bases = self._resolve_preset_bases(preset)
        for ch, base_hz in bases.items():
            self._base_frequencies[ch] = base_hz

        self._apply_spread_from_bases()
        return True

    def _resolve_preset_bases(self, preset: ChordPreset) -> dict[Channel, float]:
        """Compute preset base frequencies using IAF if available, else hardcoded."""
        if self.iaf_hz is not None and self.iaf_hz > 0 and preset.iaf_multipliers:
            return preset.iaf_frequencies(self.iaf_hz)
        return preset.base_frequencies()

    def apply_spread(self, new_spread: float | None = None) -> None:
        """Re-apply spread from the stored bases — no drift."""
        if new_spread is not None:
            self.spread_hz = max(0.0, new_spread)
        self._apply_spread_from_bases()

    def _apply_spread_from_bases(self) -> None:
        n = len(CHANNEL_ORDER)
        for i, ch in enumerate(CHANNEL_ORDER):
            offset = (i - (n - 1) / 2.0) * self.spread_hz
            hz = max(FREQ_MIN, min(FREQ_MAX, self._base_frequencies[ch] + offset))
            self.nodes[ch].frequency_hz = hz

            key_map = CHANNEL_LIVE_KEYS[ch]
            self._pending[key_map["primary"]] = hz
            for sec in key_map.get("secondary", []):
                self._pending[sec] = hz

    # ── Tether computation ────────────────────────────────────────────────

    def compute_tethers(self) -> list[Tether]:
        tethers: list[Tether] = []
        channels = list(self.nodes.keys())

        for i in range(len(channels)):
            for j in range(i + 1, len(channels)):
                a = self.nodes[channels[i]]
                b = self.nodes[channels[j]]
                delta = abs(a.frequency_hz - b.frequency_hz)

                if delta < TETHER_MAX_DELTA_HZ:
                    if delta <= TETHER_PEAK_DELTA_HZ:
                        intensity = 1.0
                    else:
                        intensity = 1.0 - (delta - TETHER_PEAK_DELTA_HZ) / (
                            TETHER_MAX_DELTA_HZ - TETHER_PEAK_DELTA_HZ
                        )
                    intensity = max(0.0, min(1.0, intensity))
                    tethers.append(
                        Tether(
                            node_a=a,
                            node_b=b,
                            delta_hz=a.frequency_hz - b.frequency_hz,
                            intensity=intensity,
                        )
                    )

        self._tethers = tethers
        return tethers

    # ── Chord analysis ────────────────────────────────────────────────────

    def chord_summary(self) -> str:
        parts = []
        for ch in reversed(CHANNEL_ORDER):
            node = self.nodes[ch]
            band = band_label_for_freq(node.frequency_hz)
            parts.append(f"{ch.value[0]}={node.frequency_hz:.1f}{band[0]}")
        return "  ".join(parts)

    def dominant_interference(self) -> str | None:
        tethers = self.compute_tethers()
        if not tethers:
            return None
        return max(tethers, key=lambda t: t.intensity).badge_text

    def center_frequency(self) -> float:
        freqs = [n.frequency_hz for n in self.nodes.values()]
        return sum(freqs) / len(freqs) if freqs else 10.0

    # ── Frequency ↔ pixel conversion ──────────────────────────────────────

    @staticmethod
    def freq_to_x(hz: float, x_min: float, x_max: float) -> float:
        if hz <= 0:
            return x_min
        log_min = math.log(FREQ_MIN)
        log_max = math.log(FREQ_MAX)
        log_hz = math.log(max(FREQ_MIN, min(FREQ_MAX, hz)))
        t = (log_hz - log_min) / (log_max - log_min)
        return x_min + t * (x_max - x_min)

    @staticmethod
    def x_to_freq(x: float, x_min: float, x_max: float) -> float:
        if x_max <= x_min:
            return FREQ_MIN
        t = max(0.0, min(1.0, (x - x_min) / (x_max - x_min)))
        log_min = math.log(FREQ_MIN)
        log_max = math.log(FREQ_MAX)
        return math.exp(log_min + t * (log_max - log_min))

    @staticmethod
    def band_boundaries_x(x_min: float, x_max: float) -> list[tuple[str, float, float]]:
        result = []
        for band_name, lo, hi in BAND_RANGES:
            x0 = InterferenceGraph.freq_to_x(lo, x_min, x_max)
            x1 = InterferenceGraph.freq_to_x(hi, x_min, x_max)
            result.append((band_name, x0, x1))
        return result
