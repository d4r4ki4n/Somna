"""
SSILD Engine -- Senses-Initiated Lucid Dreaming (Bible Ch.7 §§30-31)

TTS-guided sensory cycling protocol for lucid dream induction. Four phases:
  PRE_TECHNIQUE -> QUICK_CYCLES -> SLOW_CYCLES -> POST_TECHNIQUE

During POST_TECHNIQUE, monitors for REM sleep and dispatches TLR
(Targeted Lucidity Reactivation) subliminal cues. On wake detection,
collects dream journal entry via agent prompt.

Ticked by the Conductor when session_type == "ssild".
"""

import json
import time
from enum import Enum


class SSILDPhase(Enum):
    PRE_TECHNIQUE = "PRE_TECHNIQUE"
    QUICK_CYCLES = "QUICK_CYCLES"
    SLOW_CYCLES = "SLOW_CYCLES"
    POST_TECHNIQUE = "POST_TECHNIQUE"
    REM_MONITORING = "REM_MONITORING"
    DREAM_JOURNAL = "DREAM_JOURNAL"
    COMPLETE = "COMPLETE"


_QUICK_PROMPTS = {
    "visual": "Eyes.",
    "auditory": "Listen.",
    "somatic": "Feel.",
}

_SLOW_PROMPTS = {
    "visual": "Now shift your attention to the darkness behind your eyelids. "
    "Don't strain. Don't search. Just observe.",
    "auditory": "Now listen. Notice any sounds -- your heartbeat, the room, "
    "the silence. Just listen.",
    "somatic": "Now feel your body. Notice weight, warmth, tingling, breathing. "
    "Just notice.",
}

_TLR_CUES = [
    "You are dreaming. Check your hands.",
    "This is a dream. Look around.",
    "Are you dreaming right now?",
]

_SENSE_ORDER = ("visual", "auditory", "somatic")


class SSILDEngine:
    def __init__(
        self,
        quick_cycle_count: int = 4,
        quick_sense_duration_s: float = 4.0,
        slow_cycle_count: int = 3,
        slow_sense_duration_s: float = 20.0,
        tlr_max_cues_per_rem: int = 3,
        tlr_inter_cue_s: float = 60.0,
    ):
        self.phase = SSILDPhase.PRE_TECHNIQUE
        self.quick_cycle_count = quick_cycle_count
        self.quick_sense_duration_s = quick_sense_duration_s
        self.slow_cycle_count = slow_cycle_count
        self.slow_sense_duration_s = slow_sense_duration_s
        self.tlr_max_cues_per_rem = tlr_max_cues_per_rem
        self.tlr_inter_cue_s = tlr_inter_cue_s

        self.current_cycle: int = 0
        self.current_sense_index: int = 0
        self.sense_entered_at: float = 0.0
        self.phase_entered_at: float = time.time()
        self.pre_technique_delivered: bool = False

        self.rem_entered_at: float = 0.0
        self.rem_count: int = 0
        self.tlr_cues_delivered: int = 0
        self.tlr_last_cue_ts: float = 0.0
        self.tlr_cue_index: int = 0
        self.lucidity_detected: bool = False

        self.journal_collected: bool = False

    def tick(self, live: dict) -> dict:
        handler = {
            SSILDPhase.PRE_TECHNIQUE: self._tick_pre_technique,
            SSILDPhase.QUICK_CYCLES: self._tick_cycles,
            SSILDPhase.SLOW_CYCLES: self._tick_cycles,
            SSILDPhase.POST_TECHNIQUE: self._tick_post_technique,
            SSILDPhase.REM_MONITORING: self._tick_rem_monitoring,
            SSILDPhase.DREAM_JOURNAL: self._tick_dream_journal,
        }.get(self.phase)
        if handler is None:
            return {}
        updates = handler(live)
        base = self._base_state_dict()
        base.update(updates)
        return base

    def _base_state_dict(self) -> dict:
        return {
            "ssild_active": True,
            "ssild_phase": self.phase.value,
            "ssild_cycle": self.current_cycle,
            "ssild_sense": _SENSE_ORDER[self.current_sense_index]
            if self.current_sense_index < len(_SENSE_ORDER)
            else "",
            "ssild_rem_count": self.rem_count,
            "ssild_tlr_cues_delivered": self.tlr_cues_delivered,
        }

    def _tick_pre_technique(self, live: dict) -> dict:
        if not self.pre_technique_delivered:
            self.pre_technique_delivered = True
            return {
                "agent_message": {
                    "text": (
                        "Get comfortable. We'll cycle through your senses gently. "
                        "Don't try to make anything happen. Just notice whatever is "
                        "there. If there's nothing -- that's perfectly fine. "
                        "Remember: always do a reality check when you wake up. "
                        "Push your finger through your palm. Check if text changes."
                    ),
                    "ts": time.time(),
                    "needs_response": False,
                    "via": ["tts"],
                    "style": {"voice_mode": "tts", "intensity": 0.6},
                    "timeout_s": None,
                },
            }
        elapsed = time.time() - self.phase_entered_at
        if elapsed > 15.0:
            self._enter_phase(SSILDPhase.QUICK_CYCLES)
        return {}

    def _tick_cycles(self, live: dict) -> dict:
        is_quick = self.phase == SSILDPhase.QUICK_CYCLES
        max_cycles = self.quick_cycle_count if is_quick else self.slow_cycle_count
        sense_dur = (
            self.quick_sense_duration_s if is_quick else self.slow_sense_duration_s
        )
        prompts = _QUICK_PROMPTS if is_quick else _SLOW_PROMPTS
        voice_intensity = 0.5 if is_quick else 0.3

        if self.current_cycle >= max_cycles:
            if is_quick:
                self.current_cycle = 0
                self.current_sense_index = 0
                self._enter_phase(SSILDPhase.SLOW_CYCLES)
                return {}
            else:
                self._enter_phase(SSILDPhase.POST_TECHNIQUE)
                return {
                    "agent_message": {
                        "text": "The cycles are complete. Now just let yourself fall "
                        "asleep naturally. I'll be here.",
                        "ts": time.time(),
                        "needs_response": False,
                        "via": ["tts"],
                        "style": {"voice_mode": "tts", "intensity": 0.2},
                        "timeout_s": None,
                    },
                }

        if self.sense_entered_at == 0.0:
            self.sense_entered_at = time.time()
            sense = _SENSE_ORDER[self.current_sense_index]
            return {
                "agent_message": {
                    "text": prompts[sense],
                    "ts": time.time(),
                    "needs_response": False,
                    "via": ["tts"],
                    "style": {"voice_mode": "tts", "intensity": voice_intensity},
                    "timeout_s": None,
                },
            }

        elapsed = time.time() - self.sense_entered_at
        if elapsed >= sense_dur:
            self.current_sense_index += 1
            self.sense_entered_at = 0.0
            if self.current_sense_index >= len(_SENSE_ORDER):
                self.current_sense_index = 0
                self.current_cycle += 1
        return {}

    def _tick_post_technique(self, live: dict) -> dict:
        sleep_stage = str(live.get("eeg_sleep_stage", "WAKE"))
        if sleep_stage == "REM":
            self.rem_entered_at = time.time()
            self.tlr_cue_index = 0
            self.tlr_last_cue_ts = 0.0
            self.rem_count += 1
            self._enter_phase(SSILDPhase.REM_MONITORING)
            print(f"[SSILD] REM detected (#{self.rem_count}), entering TLR monitoring")
        return {}

    def _tick_rem_monitoring(self, live: dict) -> dict:
        sleep_stage = str(live.get("eeg_sleep_stage", "WAKE"))
        if sleep_stage != "REM":
            print(
                f"[SSILD] REM ended (stage={sleep_stage}), returning to post-technique"
            )
            self._enter_phase(SSILDPhase.POST_TECHNIQUE)
            return {}

        now = time.time()
        cues_in_this_rem = self.tlr_cues_delivered
        if cues_in_this_rem >= self.tlr_max_cues_per_rem:
            return {}

        if self.tlr_last_cue_ts == 0.0:
            rem_delay = 30.0
            if now - self.rem_entered_at < rem_delay:
                return {}

        if (
            self.tlr_last_cue_ts > 0.0
            and now - self.tlr_last_cue_ts < self.tlr_inter_cue_s
        ):
            return {}

        cue_text = _TLR_CUES[self.tlr_cue_index % len(_TLR_CUES)]
        self.tlr_cue_index += 1
        self.tlr_cues_delivered += 1
        self.tlr_last_cue_ts = now
        print(f"[SSILD] TLR cue #{self.tlr_cues_delivered}: {cue_text}")

        return {
            "agent_message": {
                "text": cue_text,
                "ts": now,
                "needs_response": False,
                "via": ["tts"],
                "style": {"voice_mode": "subliminal", "intensity": 0.15},
                "timeout_s": None,
            },
        }

    def _tick_dream_journal(self, live: dict) -> dict:
        if not self.journal_collected:
            self.journal_collected = True
            return {
                "agent_message": {
                    "text": (
                        "Good morning. Before you start your day, a few questions "
                        "about last night. Did you dream? Did you become lucid at "
                        "any point? Did you notice any cues or prompts during the "
                        "night? Take your time."
                    ),
                    "ts": time.time(),
                    "needs_response": True,
                    "via": ["tts", "overlay"],
                    "style": {"voice_mode": "tts", "intensity": 0.7},
                    "timeout_s": 300.0,
                },
            }
        return {}

    def _enter_phase(self, phase: SSILDPhase) -> None:
        self.phase = phase
        self.phase_entered_at = time.time()

    def enter_dream_journal(self) -> None:
        self._enter_phase(SSILDPhase.DREAM_JOURNAL)

    def state_dict(self) -> dict:
        return self._base_state_dict()

    def finalize(self) -> dict:
        return {
            "quick_cycles_completed": self.quick_cycle_count,
            "slow_cycles_completed": self.slow_cycle_count,
            "rem_periods_detected": self.rem_count,
            "tlr_cues_delivered": self.tlr_cues_delivered,
            "lucidity_detected": int(self.lucidity_detected),
        }
