"""
tmr_engine.py — Targeted Memory Reactivation Engine  (Bible Ch.7 §7.5)
==============================================================
Manages two TMR phases:

  Encoding (trance)
      Called from Conductor._deliver_affirmation_with_tmr() whenever the FAA
      gate fires.  Records the (pool, content_hash, affirmation_text) triple
      to somna_db and updates the per-session association-strength estimate.

  Replay (NREM sleep)
      tick() is called once per Conductor SLEEP_MAINTAIN tick.  It checks EEG
      stage, replay budget, and TMR lockout, then writes tmr_cue_cmd to
      live_control.json so the audio engine can generate and play the cue.

IPC: all coordination with audio_engine.py goes through live_control.json
(tmr_cue_cmd key).  No direct method calls across process boundaries.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from ipc import patch_live, read_live

# Replay budget
_MAX_CUES_PER_HOUR: int = 20
_MIN_CUE_INTERVAL_S: float = 30.0  # minimum seconds between replay cues
_TMR_LOCKOUT_S: float = 2.5  # tmr_lockout_until after each cue (SWE coord.)

# Only replay during NREM stages
_VALID_REPLAY_STAGES = frozenset({"N2", "N3"})

# Minimum encoding events before a cue enters the replay pool
_MIN_ENCODING_COUNT: int = 2


# ── Scheduling helpers ────────────────────────────────────────────────────────


def _inverted_u_priority(strength: float) -> float:
    """Inverted-U curve: peak = 1.0 at strength = 0.5, tapers to 0 at 0 and 1."""
    return 4.0 * max(0.0, min(1.0, strength)) * (1.0 - max(0.0, min(1.0, strength)))


# ── ConsolidationScheduler ────────────────────────────────────────────────────


class ConsolidationScheduler:
    """Prioritised cue queue for NREM replay.

    Loads the current session's cue registry from somna_db on first use, sorts
    entries by inverted-U strength priority, and provides them round-robin via
    next_cue().  Call invalidate() after any new encoding event so the list
    reflects the updated registry.
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._queue: List[Dict] = []
        self._idx = 0
        self._dirty = True  # force load on first call

    def _load(self) -> None:
        if not self._dirty:
            return
        try:
            from content_tools.somna_db import get_tmr_cue_registry

            rows = get_tmr_cue_registry(self._session_id)
        except Exception:
            rows = []

        # Filter out under-encoded cues; sort by priority descending
        eligible = [
            r for r in rows if r.get("encoding_count", 0) >= _MIN_ENCODING_COUNT
        ]
        eligible.sort(
            key=lambda r: _inverted_u_priority(r.get("strength", 0.5)), reverse=True
        )
        self._queue = eligible
        self._idx = 0
        self._dirty = False

    def next_cue(self) -> Optional[Dict]:
        """Return the next {pool, content_hash, strength} entry, or None."""
        self._load()
        if not self._queue:
            return None
        entry = self._queue[self._idx % len(self._queue)]
        self._idx += 1
        return entry

    def invalidate(self) -> None:
        """Force a reload on the next next_cue() call."""
        self._dirty = True


# ── TMREngine ────────────────────────────────────────────────────────────────

_CARDIAC_GATE_TIMEOUT_S = 10.0  # relax cardiac requirement after this many seconds


class TMREngine:
    """Coordinates TMR cue delivery during both trance (encoding) and sleep (replay).

    One instance is created per session by the Conductor.
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._scheduler = ConsolidationScheduler(session_id)
        self._last_cue_ts: float = 0.0
        self._hour_start: float = time.time()
        self._cues_this_hr: int = 0
        self._cardiac_gate_stall: float = 0.0  # Bible Ch.2 §2.9 §7.1

    # ── IPC helpers ────────────────────────────────────────────────────────

    def _read_live(self) -> Dict[str, Any]:
        try:
            return read_live()
        except Exception:
            return {}

    def on_affirmation_encoded(
        self, pool: str, content_hash: str, affirmation_text: str
    ) -> None:
        """Record a trance encoding event.

        Updates the cue registry (upsert: increment encoding_count, apply EMA
        to association strength) and appends to the encoding log.  Invalidates
        the scheduler so the new entry is included in the next replay pass.
        """
        try:
            from content_tools.somna_db import (
                upsert_tmr_cue_registry,
                log_tmr_encoding,
            )

            upsert_tmr_cue_registry(
                session_id=self._session_id,
                pool=pool,
                content_hash=content_hash,
                affirmation_text=affirmation_text,
            )
            log_tmr_encoding(
                session_id=self._session_id,
                pool=pool,
                content_hash=content_hash,
                affirmation_text=affirmation_text,
                timestamp=time.time(),
            )
        except Exception:
            pass
        self._scheduler.invalidate()

    # ── Sleep replay tick (called from Conductor SLEEP_MAINTAIN) ───────────

    def tick(self) -> None:
        """Check replay conditions and fire one cue if all gates pass."""
        now = time.time()
        live = self._read_live()

        # Stage gate: only replay in N2/N3
        stage = live.get("eeg_sleep_stage", "WAKE")
        if stage not in _VALID_REPLAY_STAGES:
            return

        # EEG loss safety — don't deliver if signal is unreliable
        if live.get("eeg_signal_lost", False):
            return

        # Hourly budget
        if now - self._hour_start >= 3600.0:
            self._cues_this_hr = 0
            self._hour_start = now
        if self._cues_this_hr >= _MAX_CUES_PER_HOUR:
            return

        # Minimum inter-cue interval
        if now - self._last_cue_ts < _MIN_CUE_INTERVAL_S:
            return

        # SWE coordination lockout
        tmr_lockout = float(live.get("tmr_lockout_until", 0.0) or 0.0)
        if now < tmr_lockout:
            return

        # Bible Ch.2 §2.9 §7.1 — cardiac diastole soft gate.
        # SO up-states are already rare; cardiac is a best-effort optimisation.
        # Prefer diastole but relax after _CARDIAC_GATE_TIMEOUT_S so we don't
        # miss too many consolidation windows.
        cardiac_diastole = bool(live.get("ppg_cardiac_diastole", True))
        if not cardiac_diastole:
            self._cardiac_gate_stall += _MIN_CUE_INTERVAL_S
            if self._cardiac_gate_stall <= _CARDIAC_GATE_TIMEOUT_S:
                return  # defer — wait for diastole
        else:
            self._cardiac_gate_stall = 0.0

        cue = self._scheduler.next_cue()
        if cue is None:
            return

        pool = cue["pool"]
        content_hash = cue["content_hash"]

        # Write cue command; set lockout so SlowWaveEnhancer yields for 2.5 s
        cmd = {
            "pool": pool,
            "content_hash": content_hash,
            "gain": 0.12,
            "ts": now,
        }
        patch_dict = {
            "tmr_cue_cmd": cmd,
            "tmr_lockout_until": now + _TMR_LOCKOUT_S,
        }

        # Bible Ch.2 §12 — haptic TMR anchor cue (200 ms pulse at 30% intensity)
        connected = set(live.get("hardware_channels_connected") or [])
        if "haptic" in connected:
            haptic_sleep_n1n2 = bool(live.get("haptic_sleep_enabled_n1n2", False))
            if haptic_sleep_n1n2 and stage in ("N2",):
                patch_dict["tmr_haptic_cue"] = {
                    "intensity": 30.0,
                    "duration_s": 0.2,
                    "ts": now,
                }

        patch_live(patch_dict)

        self._last_cue_ts = now
        self._cues_this_hr += 1

        try:
            from content_tools.somna_db import log_tmr_replay

            log_tmr_replay(
                session_id=self._session_id,
                pool=pool,
                content_hash=content_hash,
                sleep_stage=stage,
                timestamp=now,
            )
        except Exception:
            pass

    # ── EEG-loss safety shutdown ────────────────────────────────────────────

    def eeg_loss_shutdown(self) -> None:
        """Immediately halt all TMR stimulation.

        A 5-minute lockout on tmr_lockout_until is written so that even if the
        signal briefly recovers, no cue fires until the Conductor explicitly
        resumes (or the lockout expires).  Wrong-phase stimulation during an
        uncertain EEG state is actively harmful.
        """
        patch_live(
            {
                "tmr_cue_cmd": None,
                "tmr_lockout_until": time.time() + 300.0,
            }
        )
