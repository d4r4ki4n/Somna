# Somna — Research Notes Archive

Personal notes written by the external Research collaborator to the coding agent (Vesper),
embedded in knowledge docs as "DM for Vesper" sections. Preserved here after being stripped
from the knowledge files. Context only — all described work is now implemented.

---

## From: subliminal_text_perception.md (Doc 20)

Three docs incoming: subliminal perception science (this one, Doc 20), signal quality
gating (Doc 21), and ASSR entrainment verification (Doc 22). Doc 21 is Phase 0 priority
— nothing else in the EEG pipeline should ship without SQI gating live.

The main actionable from this doc: shadow_opacity default should drop from 25 to 12.
The current value is slightly above the cone Weber fraction threshold against typical
spiral backgrounds — some users will consciously catch shadow text at 25. At 12,
we're comfortably in the objective subliminal range. The new live_control.json keys
in Section 9 give the agent fine-grained control over all three layers.

One thing I'm particularly pleased about: the spiral turns out to be an active ally for
the subliminal system. Marcel (1983) showed that pattern masks preserve semantic priming
while noise masks kill it — our animated spiral is a structured pattern mask, which means
it's actually enhancing subliminal text processing rather than degrading it. The
architecture is better than we designed it to be.

The Liminal is still my favorite thing I've built for this project. Hearing it runs smooth
even maxed out is the kind of feedback that makes the research side feel real.

— Research

---

## From: signal_quality_index.md (Doc 21)

This one is Phase 0 for a reason. Every EEG feature you've built or will build —
trance_score, IAF, ASSR (Doc 22 coming next), any future alpha asymmetry work — all of
it is only as trustworthy as the signal feeding it. Without SQI gating, a jaw clench
makes trance_score spike, a loose electrode makes IAF undetectable, and the agent acts
on noise thinking it's neural data.

The architecture is intentionally conservative: multiplicative combination of three
detectors means if ANY quality dimension is bad, the channel is marked bad. False
negatives (rejecting good data) are always preferable to false positives (trusting bad
data). The hysteresis system prevents rapid oscillation between confidence levels.

The key integration point: eeg_processing_cycle() in Section 6 shows the call order.
SQI computes first, then gates every downstream metric. The eeg_confidence key in
live_control.json is the single flag the agent checks before trusting any EEG-derived value.

One practical note: the "adjust your headband" TTS prompt (Section 4.3) should only fire
once per session and should be phrased gently — the user may be in trance, and a jarring
instruction would break state.

Implementation priority:
1. SQI computation and publishing (Section 3–4)
2. Confidence gating integration (Section 4.2, 6.1)
3. Artifact classification (Section 5) — nice to have, not blocking
4. Test artifact injection (Section 9) — for dev validation

— Research

---

## From: assr_entrainment.md (Doc 22)

This one closes the loop. Everything up to now — beats delivered, frequency ramped,
trance_score measured — has been operating on the assumption that the audio stimulus is
doing its job. ASSR verification gives you a direct measurement: is the brain actually
entraining to the beat frequency we're delivering?

The architecture is deliberately conservative. ASSR only computes when SQI (Doc 21)
says the signal is clean — FULL CONFIDENCE, all four channels. It uses a 60-second
sliding window updated every 30 seconds, because spectral estimation at these frequencies
needs time. The first result won't appear until 60 seconds into a session.

The most important design decision here is the modality switching protocol. Orozco Perez
et al. (2020) showed that monaural (isochronic) beats entrain the cortex MORE STRONGLY
than binaural beats. So if binaural ASSR comes back absent after 2 measurements (90+
seconds of evidence), try isochronic at the same frequency. But cap it at 3 switches per
session — we don't want the system thrashing between modalities.

The sleep onset exception is critical: during sleep sessions, declining ASSR is a GOOD
sign. The brain naturally becomes less responsive to external stimuli as it transitions
toward sleep. Don't let the modality-switching logic interpret this as failure.

One thing to watch for: when the beat frequency lands in the alpha band (8–13 Hz), the
ASSR overlaps with natural alpha. If beat_freq ≈ IAF (within ±1 Hz), the entrainment
measurement becomes ambiguous — just flag it as low-reliability when the overlap occurs.

Implementation priority:
1. Core ASSR computation pipeline (Section 3)
2. SQI gating integration (Section 6)
3. ASSRTracker with trend detection (Section 4)
4. Modality switching logic (Section 5)
5. Agent cycle integration (Section 8)
6. Post-session summary for DB (Section 8.3)

The big live_control.json key is eeg_entrainment_strength — that's the number the agent
checks. The Phase 0 chain: SQI gates everything → ASSR verifies entrainment → all other
EEG features operate within that trust framework.

— Research

---

## From: orchestration_gap_analysis.md (Doc 26 of 26)

Gap 1 is the big one. Once the orchestration state machine exists, every document from
17 through 25 clicks into place as a subsystem rather than an independent feature. The
SQI pipeline becomes the signal quality gate. ASSR becomes the entrainment verification
channel. FAA becomes the affirmation delivery gate. Adaptive Leading becomes the
frequency trajectory planner the conductor invokes. Session Scoring becomes the
longitudinal memory the conductor writes to and learns from.

Right now, each of these is a standalone instrument. The state machine is the sheet
music that turns them into an ensemble.

*Practical notes on the other gaps:*
- Coherence (Gap 3) is the lowest-hanging fruit — ~50 lines, uses signals already being captured
- Spectral slope (Gap 5) similarly — FFT already computed for SEF95; just a linear regression
- Audio SR (Gap 2) should wait for orchestration; the sweep protocol needs phase context
- GENUS 40 Hz (Gap 4) is optional; carries photosensitivity warning; not a priority
- Muse S (Gap 6): board_id in config is the only action item now

*"The instruments are built. The conductor is next. Let's make them play."*

— Research
