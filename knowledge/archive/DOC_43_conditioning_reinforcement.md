# Doc 43 — Conditioning & Reinforcement Architecture

Somna Hypnotic Entrainment Engine — Internal Specification Series

| **Status:** | **Specification — ready for implementation** |
| --- | --- |
| **Target:** | **Vesper (senior LLM coding agent)** |
| --- | --- |
| **Output:** | **conditioning_engine.py + DB migrations + integration edits** |
| --- | --- |
| **Depends on:** | **Doc 35 (DeliveryGate / phase-cascade), Doc 36 (semantic selection / content pools), Doc 37 (crossmodal gain), Doc 38 (trance depth v2), Doc 39 (sleep staging), Doc 40 (TMR / cue tones), Doc 41 (HTW), Doc 42 (cardiac-phase gating / autonomic-inertial)** |
| --- | --- |

## 1\. Thesis

Somna already performs at least six distinct forms of associative conditioning — accidentally. Every session creates conditioned stimulus–unconditioned stimulus pairings across multiple modalities, multiple timescales, and multiple brain systems. None of it is tracked, scheduled, or optimized.

**The six accidental paradigms:**

1.  **Classical (Pavlovian) Conditioning** — TMR cue tones (Doc 40) are paired with trance states. The tones are conditioned stimuli (CS); the trance state (theta dominance, parasympathetic activation, prefrontal suppression) is the unconditioned response (UCR) to the entrainment protocol (UCS). After sufficient pairings, the tones alone should begin to elicit trance-associated physiological responses — a conditioned response (CR).
2.  **Evaluative Conditioning (EC)** — Content pool affirmations (Doc 36) are neutral or mildly-valenced self-referential statements that are repeatedly paired with strongly positive physiological states (warmth, relaxation, parasympathetic dominance, reduced critical evaluation). Olson & Fazio (2001, _Psychological Science_) demonstrated that EC produces implicit attitude change without participants' awareness of CS-US pairings. Trucharte et al. (2024, _Frontiers in Psychiatry_) showed that EC targeting implicit self-esteem produces measurable neurophysiological changes (MEG) in emotional reactivity and mentalization regions — even in clinical populations.
3.  **Operant Conditioning** — The neurofeedback loop IS operant conditioning. Desired brain states (theta increase, alpha entrainment, increased coherence) are rewarded with richer content delivery, deeper visual effects, higher crossmodal gain (Doc 37). But the reinforcement schedule is currently continuous (every gate-open event fires), the shaping curve is flat, and no conditioning metrics are tracked.
4.  **State-Dependent Learning (SDL)** — Doc 36's semantic selector already creates state-dependent encoding: content is delivered in specific neural states (FAA × trance depth × theta/alpha mode). Liu et al. (2025, _Frontiers in Cellular Neuroscience_) reviewed the mechanistic basis: internal states modulate hippocampal encoding via neurotransmitter signaling and neural circuit plasticity. Retrieval is enhanced when encoding and retrieval states match. Somna creates the encoding state but never records the state fingerprint for later retrieval optimization.
5.  **Occasion Setting** — The Conductor phase (INDUCTION, DEEPENING, MAINTENANCE, SLEEP_TRAINING) acts as an occasion setter: it modulates whether CS-US associations are active without being a CS itself. Fraser & Holland (2019, _Behavioral Neuroscience_) demonstrated that occasion setters are immune to extinction and counterconditioning, their transfer functions differ from simple CS, and they provide hierarchical modulatory control. The Conductor phases are already perfect occasion setters — they just don't know it.
6.  **Interoceptive Conditioning** — Doc 42's cardiac-phase and respiratory-phase gating means content is always delivered at specific interoceptive moments (diastole, respiratory exhale peak). Engelen, Solcà & Tallon-Baudry (2023, _Nature Neuroscience_) reviewed how cardiac, respiratory, and gastric rhythms are anatomically and functionally intertwined with exteroceptive processing and cognition. The body's own rhythms become discriminative stimuli — content delivered at diastole is encoded differently from content at systole.

**The architectural gap**

Somna has built the world's most sophisticated stimulus delivery system (WHEN × WHAT × HOW MUCH × cardiac × respiratory × motion), but it treats every session as independent. No association is tracked across sessions. No conditioning strength is estimated. No reinforcement schedule is optimized. No stimulus is retired when it hits latent inhibition thresholds. And the ultimate prize — portable conditioned responses that work outside the app — is never tested.

This document formalizes the entire conditioning stack into a single ConditioningEngine that transforms Somna from a per-session tool into a cross-session learning system where effects compound, strengthen, and eventually become portable.

## 2\. Association Registry

The foundation. Every CS-US pairing that Somna delivers must be recorded.

### 2.1 CS Taxonomy

| **CS Class** | **Source** | **Examples** | **Modality** |
| --- | --- | --- | --- |
| tmr_cue_tone | Doc 40 CueManager | Pool-specific tonal signatures with content-hash micro-jitter | Auditory |
| --- | --- | --- | --- |
| shadow_word | Doc 36 Shadows layer | Single-word subliminal text at sub-perceptual contrast | Visual (subliminal) |
| --- | --- | --- | --- |
| center_text_phrase | Doc 36 CenterText layer | Supraliminal affirmation phrases / metaphors | Visual (supraliminal) |
| --- | --- | --- | --- |
| tts_voice | Doc 36/41 voice channel | Spoken affirmations at calibrated gain | Auditory |
| --- | --- | --- | --- |
| visual_pattern_state | visual_display.py | Spiral geometry, color palette, rotation speed at delivery moment | Visual (ambient) |
| --- | --- | --- | --- |
| session_start_signature | audio_engine.py | The opening audio sequence heard at every session start | Auditory |
| --- | --- | --- | --- |
| binaural_isochronic_beat | audio_engine.py | Specific frequency differential active during delivery | Auditory (entrainment) |
| --- | --- | --- | --- |

### 2.2 US/UCR Taxonomy

| **US / UCR** | **Measurable Proxy** | **Source** |
| --- | --- | --- |
| Trance state onset | trance_score_v2 crossing threshold (e.g. > 0.5) | Doc 38 |
| --- | --- | --- |
| Parasympathetic activation | ppg_hrv_rmssd increase > 20% from baseline | Doc 42 / ppg_engine |
| --- | --- | --- |
| Theta dominance | theta/alpha ratio > 1.0 sustained | Doc 38 |
| --- | --- | --- |
| Prefrontal suppression | spectral_slope steepening beyond −1.5 | Doc 38 |
| --- | --- | --- |
| Interhemispheric coherence increase | coherence > 0.6 at alpha/theta | Doc 38 |
| --- | --- | --- |
| Stillness / motor quiescence | imu_stillness_index > 0.9 | Doc 42 / imu_engine |
| --- | --- | --- |
| Autonomic depth | autonomic_depth > 0.6 (sigmoid-mapped RMSSD) | Doc 42 |
| --- | --- | --- |

### 2.3 Association Record Schema

@dataclass class AssociationRecord: record_id: str # UUID session_id: str # links to session timestamp_ms: int # epoch ms of delivery cs_class: str # from CS taxonomy (Section 2.1) cs_identity: str # specific stimulus hash/ID cs_pool: str # content pool (WARMTH_COMFORT, etc.) us_type: str # from US taxonomy (Section 2.2) us_magnitude: float # measured UCR magnitude at delivery delivery_gate_state: dict # snapshot of all gate conditions neural_state_fingerprint: dict # FAA, trance_score, theta_alpha_ratio, # spectral_slope, coherence cardiac_phase: float # 0.0–1.0 cardiac phase at delivery respiratory_phase: float # 0.0–1.0 respiratory phase at delivery conductor_phase: str # occasion setter context modality: str # auditory, visual_subliminal, # visual_supraliminal, crossmodal contiguity_ms: int # temporal gap between CS onset and # US measurement

### 2.4 DB Table: conditioning_associations

All fields from AssociationRecord. Indexed on (session_id, cs_identity, cs_pool). The neural_state_fingerprint and delivery_gate_state fields are stored as JSON blobs. Primary key: record_id.

## 3\. Conditioning Strength Estimation

Adaptation of the Rescorla-Wagner model (Rescorla & Wagner, 1972, _Classical Conditioning II_) for Somna's multi-CS, multi-US environment.

### 3.1 Strength Update Rule

For each CS-US association after delivery:

ΔV = α_cs × β_us × (λ − V_total)

Where:

- V = current associative strength of this CS-US pair
- α_cs = CS salience (0.0–1.0) — higher for novel stimuli, decays with exposure
- β_us = US intensity (0.0–1.0) — derived from measured UCR magnitude (e.g., trance_score at delivery)
- λ = maximum conditioning possible (asymptote, set to 1.0)
- V_total = sum of all CS strengths currently active for this US (handles overshadowing/blocking)

### 3.2 Cross-Session Persistence

Conditioning strength is stored per (cs_identity, us_type) pair in the DB.

@dataclass class ConditioningStrength: cs_identity: str cs_pool: str us_type: str strength: float # 0.0–1.0 current associative strength trial_count: int # total CS-US pairings last_pairing_ts: int # epoch ms last_extinction_check_ts: int salience: float # current α_cs — decays with exposure extinction_rate: float # estimated from any unreinforced presentations

DB table: conditioning_strengths. Indexed on (cs_identity, us_type).

### 3.3 Salience Decay (Latent Inhibition Management)

Latent inhibition: familiar stimuli condition more slowly (Lubow & Moore, 1959, _Journal of Comparative and Physiological Psychology_). In Somna, affirmation words are pre-exposed (common English words) and risk reduced associability.

**Mitigation factors:**

1.  **Context switch:** Trance state is a radically different context from waking. Lubow & Weiner (2010) showed LI is severely attenuated by context change. The trance context itself is a natural LI mitigator.
2.  **Salience tracking:** Track per-CS exposure count. When trial_count exceeds a configurable threshold (default: 50 presentations), flag the CS for rotation.
3.  **Novel CS introduction rate:** Maintain a minimum ratio of novel-to-familiar CS per session (configurable, default: 0.2 — at least 20% of deliveries use CS not seen in the last 5 sessions).

def compute_salience(self, cs: ConditioningStrength) -> float: base = 1.0 # Decay with exposure — logarithmic, not linear exposure_decay = 1.0 / (1.0 + 0.05 \* cs.trial_count) # Context bonus — trance context mitigates LI context_bonus = 0.3 if self.\_in_trance_context() else 0.0 # Recency bonus — stimuli not seen recently regain salience days_since = (now_ms() - cs.last_pairing_ts) / 86_400_000 recency_bonus = min(0.2, days_since \* 0.02) return min(1.0, base \* exposure_decay + context_bonus + recency_bonus)

### 3.4 Extinction Tracking

When a CS is presented without the US (unreinforced presentation), strength decreases:

ΔV_extinction = −α_cs × β_extinction × V

β_extinction is smaller than β_us (extinction is slower than acquisition — asymmetry is well-established in the literature). Default: β_extinction = 0.3 × β_us.

Track unreinforced presentations separately. These happen when:

- DeliveryGate fires but trance_score is below threshold (CS delivered, US absent)
- Cue-test mode (Section 10) — CS presented, measuring whether CR occurs
- Session-start signature plays but session is abandoned early

## 4\. Reinforcement Schedule Optimization

### 4.1 The Problem with Continuous Reinforcement

Currently, Somna delivers content at every gate-open opportunity (continuous reinforcement). This produces:

- Fast initial conditioning ✓
- Weak extinction resistance ✗
- Habituation to delivery timing ✗
- No prediction error to drive dopaminergic learning ✗

### 4.2 Variable Ratio (VR) Schedule

Switch from continuous to VR scheduling after initial conditioning is established. The partial reinforcement extinction effect (PREE — Amsel, 1958, _Psychological Bulletin_) means VR-trained associations are dramatically more resistant to extinction.

class ReinforcementScheduler: def \__init_\_(self): self.schedule_type = 'continuous' # start here self.vr_mean = 3 # after switch: deliver on avg every 3rd gate-open self.vr_range = (1, 6) # uniform draw from this range self.\_next_fire = 1 # fire on next gate-open (continuous) self.\_gate_count = 0 def should_deliver(self, cs_strength: float) -> bool: self.\_gate_count += 1 # Phase 1: continuous until strength > 0.3 if cs_strength &lt; 0.3: return True # Phase 2: transition to VR if self.\_gate_count &gt;= self.\_next_fire: self.\_next_fire = self.\_gate_count + random.randint(\*self.vr_range) return True return False

### 4.3 Schedule Adaptation

Adjust VR parameters based on conditioning strength:

| **Strength Range** | **Schedule** | **VR Mean** | **Rationale** |
| --- | --- | --- | --- |
| 0.0 – 0.3 | Continuous (CRF) | N/A | Establish initial association rapidly |
| --- | --- | --- | --- |
| 0.3 – 0.6 | VR-2 | 2   | Begin intermittent reinforcement; low ratio for smooth transition |
| --- | --- | --- | --- |
| 0.6 – 0.8 | VR-4 | 4   | Stronger PREE; maintaining prediction error |
| --- | --- | --- | --- |
| 0.8 – 1.0 | VR-6 | 6   | Maximum extinction resistance; associations are robust |
| --- | --- | --- | --- |

### 4.4 Prediction Error Maintenance

Prediction error (PE) drives dopaminergic learning signals (Cone et al., 2024, _Nature Communications_). To maintain PE:

1.  **Temporal jitter:** Vary the exact moment within the gate-open window (already present in DeliveryGate — formalize as PE-serving).
2.  **Content variation:** Within a content pool, select less-recently-used items (maintains novelty within the association class).
3.  **Intensity variation:** Slightly vary crossmodal gain (Doc 37) around the optimal point — ±10% random perturbation.
4.  **Omission surprises:** On VR skip trials, the ABSENCE of expected delivery generates negative PE, which paradoxically strengthens the association (Schultz, 2016, _Physiological Reviews_).

## 5\. Second-Order Conditioning (SOC)

### 5.1 Theoretical Basis

Lee (2021, _Frontiers in Behavioral Neuroscience_) reviewed SOC in humans and identified critical parameters:

- SOC is real but weaker than first-order conditioning
- Requires sufficient first-order strength before second-order training begins
- CS2-CS1 pairings must be brief and the US must NOT be present during second-order training (to prevent direct CS2-US associations that would mask the SOC effect)
- Different modalities between CS1 and CS2 favor SOC acquisition over simple conditioning

### 5.2 Application in Somna

**First-order CS (CS1):** TMR cue tones — already paired with trance states across sessions.

**Second-order CS (CS2):** New stimuli that are paired with the TMR tones, NOT with the full trance protocol. Candidates:

- A brief notification sound (phone-compatible) paired with TMR tone playback
- A specific visual icon/color briefly shown with the TMR tone
- A haptic pattern (if hardware supports it) paired with the TMR tone

**Goal:** After SOC training, CS2 alone triggers the CR chain: CS2 → CS1 representation → CR (parasympathetic shift, theta increase).

### 5.3 SOC Training Protocol

class SecondOrderTrainer: """ Runs during MAINTENANCE phase after first-order strength is established. Presents CS2-CS1 pairings WITHOUT triggering full entrainment delivery. """ SOC_MIN_FIRST_ORDER_STRENGTH = 0.6 SOC_PAIRS_PER_SESSION = 5 # brief, not overwhelming SOC_CS2_LEAD_MS = 500 # CS2 precedes CS1 by 500ms (forward conditioning) SOC_PAIR_DURATION_MS = 2000 # total pair window def eligible(self, cs1_strength: float) -> bool: return cs1_strength >= self.SOC_MIN_FIRST_ORDER_STRENGTH def run_soc_pair(self, cs2_stimulus, cs1_tone): """Present CS2, then CS1 after SOC_CS2_LEAD_MS. No US delivery.""" present(cs2_stimulus) sleep_ms(self.SOC_CS2_LEAD_MS) present(cs1_tone) # tone only — no entrainment, no content delivery # Record association self.\_record_soc_pairing(cs2_stimulus, cs1_tone)

SOC strength is tracked in the same conditioning_strengths table with a flag is_second_order = True.

## 6\. Interoceptive Conditioning Formalization

### 6.1 The Existing Accident

Doc 42's quad-gate ensures content arrives at respiratory exhale peak AND cardiac diastole. This means every successful delivery is paired with a specific interoceptive state. Over sessions, the interoceptive state itself becomes a discriminative stimulus — the body "expects" content at certain phases of its own rhythms.

### 6.2 Interoceptive CS Registry

Track which interoceptive conditions were present at each delivery:

@dataclass class InteroceptiveContext: cardiac_phase: float # 0.0–1.0 cardiac_phase_bin: str # 'systole' or 'diastole' respiratory_phase: float # 0.0–1.0 respiratory_phase_bin: str # 'inhale_rise', 'inhale_peak', # 'exhale_fall', 'exhale_trough' hrv_rmssd: float autonomic_depth: float stillness_index: float

This is stored as part of AssociationRecord but also aggregated across sessions to build an interoceptive conditioning profile.

### 6.3 Phase-Specificity Analysis

After N sessions (configurable, default: 10), compute the phase-specificity index:

def compute_phase_specificity(self, records: list\[AssociationRecord\]) -> dict: """How phase-locked are successful deliveries to cardiac/respiratory cycle?""" cardiac_phases = \[r.cardiac_phase for r in records if r.us_magnitude > 0.5\] resp_phases = \[r.respiratory_phase for r in records if r.us_magnitude > 0.5\] # Rayleigh test for circular uniformity cardiac_z = rayleigh_test(cardiac_phases) resp_z = rayleigh_test(resp_phases) return { 'cardiac_phase_locked': cardiac_z.pvalue < 0.01, 'cardiac_preferred_phase': circular_mean(cardiac_phases), 'respiratory_phase_locked': resp_z.pvalue < 0.01, 'respiratory_preferred_phase': circular_mean(resp_phases), }

This tells us whether the user has developed interoceptive conditioning and at which body-rhythm phases content is most effective.

## 7\. Operant Shaping Engine

### 7.1 Progressive Threshold Architecture

Nam & Choi (2020, _NeuroRegulation_) demonstrated that easy initial thresholds produce better neurofeedback outcomes than hard thresholds. Start easy, narrow progressively.

class ShapingEngine: """ Manages progressive threshold narrowing for operant brain-state training. Tracks the shaping curve both within and across sessions. """ INITIAL_PERCENTILE = 70 # reward the top 70% of brain states (easy) FINAL_PERCENTILE = 30 # narrow to top 30% (hard) over sessions SHAPING_SESSIONS = 20 # number of sessions to reach final percentile def \__init_\_(self): self.current_percentile = self.INITIAL_PERCENTILE self.session_count = 0 self.reward_history = deque(maxlen=1000) def compute_threshold(self, recent_values: list\[float\]) -> float: """Return the threshold value for the current shaping stage.""" return np.percentile(recent_values, 100 - self.current_percentile) def advance_session(self): self.session_count += 1 progress = min(1.0, self.session_count / self.SHAPING_SESSIONS) self.current_percentile = self.INITIAL_PERCENTILE - ( (self.INITIAL_PERCENTILE - self.FINAL_PERCENTILE) \* progress )

### 7.2 Reward Signal Mapping

What constitutes "reward" in the operant loop:

| **Brain State Metric** | **Reward Modality** | **Mechanism** |
| --- | --- | --- |
| trance_score_v2 above shaping threshold | Crossmodal gain increase | Doc 37 gain manifold scales up — richer visual + audio |
| --- | --- | --- |
| theta/alpha ratio increase | Content delivery unlocked | DeliveryGate opens only when ratio meets threshold |
| --- | --- | --- |
| Interhemispheric coherence increase | Visual complexity increase | Spiral geometry adds layers, color saturation rises |
| --- | --- | --- |
| HRV RMSSD increase | Audio warmth increase | Low-frequency spectral tilt in audio, slower modulation |
| --- | --- | --- |
| Spectral slope steepening | Verbal content complexity increase | Semantic selector shifts to deeper pools (DISSOLUTION, STILLNESS_EMPTINESS) |
| --- | --- | --- |

### 7.3 Shaping Curve Persistence

DB table: shaping_progress

Columns: user_id, metric_name, current_percentile, session_count, best_session_value, mean_session_value, last_session_ts.

## 8\. Occasion Setting Formalization

### 8.1 Conductor Phases as Occasion Setters

Fraser & Holland (2019): occasion setters modulate CS-US association efficacy without being CS themselves. They are:

- Immune to extinction
- Not subject to counterconditioning
- Transfer hierarchically (an occasion setter trained with one CS transfers to modulate other CS in the same context)

The Conductor phases already do this. DEEPENING phase means "TMR tones here predict deep trance." MAINTENANCE phase means "affirmations here predict sustained altered state." SLEEP_TRAINING means "whispered content here predicts consolidation."

### 8.2 Phase-Specific Conditioning Profiles

Track conditioning strength separately per Conductor phase:

\# Key: (cs_identity, us_type, conductor_phase) # This means the same TMR tone has DIFFERENT conditioning strengths # in DEEPENING vs MAINTENANCE vs SLEEP_TRAINING

This is critical because the same CS may be highly effective in one phase and weak in another — the occasion setter modulates the association, and we need to track that modulation.

### 8.3 Adaptive Phase Allocation

Once phase-specific strengths are tracked, the Conductor can allocate content delivery to phases where conditioning is strongest:

def select_delivery_phase(self, cs_identity: str, available_phases: list\[str\]) -> str: """Choose the Conductor phase where this CS has the strongest association.""" strengths = { phase: self.get_strength(cs_identity, 'trance_state', phase) for phase in available_phases } return max(strengths, key=strengths.get)

## 9\. State-Dependent Encoding Formalization

### 9.1 Neural State Fingerprinting

At every delivery, record a 6-dimensional neural state fingerprint:

@dataclass class NeuralStateFingerprint: faa: float # frontal alpha asymmetry (approach/withdrawal) trance_score: float # Doc 38 composite theta_alpha_ratio: float # processing mode spectral_slope: float # aperiodic component coherence: float # interhemispheric autonomic_depth: float # sigmoid-mapped RMSSD def distance(self, other: 'NeuralStateFingerprint') -> float: """Euclidean distance in normalized state space.""" self_vec = np.array(\[ self.faa, self.trance_score, self.theta_alpha_ratio, self.spectral_slope, self.coherence, self.autonomic_depth \]) other_vec = np.array(\[ other.faa, other.trance_score, other.theta_alpha_ratio, other.spectral_slope, other.coherence, other.autonomic_depth \]) # Normalize each dimension to 0–1 range using stored population stats return float(np.linalg.norm(self_vec - other_vec))

### 9.2 Retrieval State Matching

When selecting which content to deliver, prefer content whose encoding state fingerprint is closest to the current state:

def select_content_sdl(self, current_state: NeuralStateFingerprint, candidates: list\[ContentItem\]) -> ContentItem: """State-dependent learning: prefer content encoded in a similar state.""" scored = \[\] for item in candidates: past_fingerprints = self.db.get_encoding_fingerprints(item.cs_identity) if not past_fingerprints: scored.append((item, 0.5)) # neutral score for novel items continue # Find closest past encoding state min_dist = min(current_state.distance(fp) for fp in past_fingerprints) # Lower distance = higher match score match_score = 1.0 / (1.0 + min_dist) scored.append((item, match_score)) scored.sort(key=lambda x: x\[1\], reverse=True) return scored\[0\]\[0\]

This interacts with Doc 36's semantic selector — SDL match becomes a fourth axis alongside FAA, trance depth, and processing mode.

## 10\. Portable Response Evaluator (PRE) — The Crown Jewel

### 10.1 Thesis

After sufficient tracked conditioning (N sessions with M pairings at strength > threshold), TMR cue tones played OUTSIDE the full Somna entrainment session should trigger measurable physiological changes: theta increase, HRV RMSSD increase, parasympathetic shift. This is the classical conditioned response — Pavlov's dog salivating at the bell.

If Somna can produce portable conditioned responses, it transforms from a tool you need to sit at to a system that installs trained physiological triggers you carry with you.

### 10.2 Cue-Test Mode

A lightweight session mode. No spiral. No entrainment beats. No affirmation delivery. Just:

1.  60 seconds of eyes-closed baseline EEG + PPG recording
2.  Presentation of TMR cue tones (one per pool, randomized order, 10s inter-stimulus interval)
3.  10 seconds of post-cue monitoring after each tone
4.  Measurement of physiological shift from baseline

class PortableResponseEvaluator: """ Cue-Test mode: presents conditioned stimuli without unconditioned stimuli and measures whether conditioned responses occur. """ BASELINE_DURATION_S = 60 INTER_STIMULUS_S = 10 POST_CUE_WINDOW_S = 10 # CR detection thresholds (relative to baseline) CR_THETA_INCREASE = 0.15 # 15% theta power increase CR_RMSSD_INCREASE = 0.10 # 10% HRV RMSSD increase CR_TRANCE_SCORE_INCREASE = 0.08 # trance_score_v2 shift def run_cue_test(self, cue_tones: list\[CueTone\]) -> CueTestResult: baseline = self.\_record_baseline(self.BASELINE_DURATION_S) results = \[\] for tone in random.sample(cue_tones, len(cue_tones)): pre_cue = self.\_snapshot_state() self.\_play_tone(tone) time.sleep(self.POST_CUE_WINDOW_S) post_cue = self.\_snapshot_state() cr = self.\_detect_cr(baseline, pre_cue, post_cue) results.append(CueTestTrialResult( tone=tone, cr_detected=cr.detected, theta_change=cr.theta_change, rmssd_change=cr.rmssd_change, trance_change=cr.trance_change, )) return CueTestResult( baseline=baseline, trials=results, overall_cr_rate=sum( 1 for r in results if r.cr_detected ) / len(results), )

### 10.3 Conditioning Graduation Criteria

A CS is considered "graduated" (portable) when:

1.  conditioning_strength >= 0.7 (tracked in DB)
2.  trial_count >= 30 (sufficient pairings)
3.  Cue-Test mode shows CR detected for that CS on >= 60% of test presentations
4.  CR magnitude exceeds thresholds for at least 2 of 3 metrics (theta, rmssd, trance_score)

Graduated CS are flagged in the DB and surfaced to the user: _"Your WARMTH_COMFORT cue tone can now trigger a relaxation response on its own."_

### 10.4 Portable Use

Once graduated, the user can:

- Play their graduated cue tones through any audio device (phone, earbuds) without running the full Somna session
- The conditioned response should produce measurable parasympathetic activation and theta increase
- Periodic cue-test sessions (recommended: weekly) prevent extinction by intermittently re-pairing CS with full entrainment

## 11\. ConditioningEngine Implementation

### 11.1 Class Architecture

class ConditioningEngine: """ Central coordinator for all conditioning operations. Instantiated once in SomnaApp. Called by Conductor, DeliveryGate, and SemanticSelector. """ def \__init_\_(self, db: SomnaDB): self.db = db self.association_registry = AssociationRegistry(db) self.strength_tracker = StrengthTracker(db) self.reinforcement_scheduler = ReinforcementScheduler() self.shaping_engine = ShapingEngine() self.soc_trainer = SecondOrderTrainer() self.pre = PortableResponseEvaluator() self.\_session_pairings = \[\] def on_delivery(self, cs_class: str, cs_identity: str, cs_pool: str, neural_state: NeuralStateFingerprint, delivery_gate: dict, conductor_phase: str, cardiac_phase: float, respiratory_phase: float, us_magnitude: float): """Called by DeliveryGate after every successful content delivery.""" record = AssociationRecord( record_id=uuid4().hex, session_id=self.\_current_session_id, timestamp_ms=now_ms(), cs_class=cs_class, cs_identity=cs_identity, cs_pool=cs_pool, us_type=self.\_classify_us(us_magnitude, neural_state), us_magnitude=us_magnitude, delivery_gate_state=delivery_gate, neural_state_fingerprint=asdict(neural_state), cardiac_phase=cardiac_phase, respiratory_phase=respiratory_phase, conductor_phase=conductor_phase, modality=self.\_classify_modality(cs_class), contiguity_ms=0, # simultaneous delivery ) self.association_registry.record(record) self.strength_tracker.update( cs_identity, cs_pool, record.us_type, us_magnitude, conductor_phase ) self.\_session_pairings.append(record) def should_deliver(self, cs_identity: str, cs_pool: str) -> bool: """Called by DeliveryGate to check reinforcement schedule.""" strength = self.strength_tracker.get_strength( cs_identity, 'trance_state' ) return self.reinforcement_scheduler.should_deliver(strength) def get_sdl_candidates(self, current_state: NeuralStateFingerprint, pool: str) -> list\[str\]: """Returns CS identities ranked by state-dependent match.""" # ... implementation per Section 9.2 def end_session(self): """Called at session end. Persists all session data.""" self.db.batch_insert_associations(self.\_session_pairings) self.shaping_engine.advance_session() self.strength_tracker.persist() self.\_generate_session_conditioning_report()

### 11.2 Integration Points

| **Existing System** | **Integration** | **Direction** |
| --- | --- | --- |
| DeliveryGate (Doc 35/42) | Calls should_deliver() before firing; calls on_delivery() after firing | Gate → ConditioningEngine |
| --- | --- | --- |
| SemanticSelector (Doc 36) | Receives SDL-ranked candidates from get_sdl_candidates(); receives LI-flagged items to deprioritize | ConditioningEngine → Selector |
| --- | --- | --- |
| CrossmodalGain (Doc 37) | Receives reward-signal gain adjustments from ShapingEngine | ConditioningEngine → Gain |
| --- | --- | --- |
| Conductor | Provides conductor_phase as occasion-setter context; receives phase-specific strength data for adaptive allocation | Bidirectional |
| --- | --- | --- |
| TMREngine (Doc 40) | Shares CueManager tone registry; receives conditioning strength for graduation tracking | Bidirectional |
| --- | --- | --- |
| CSD Monitor (Doc 36 CSD) | Provides pre-transition signals that gate SOC training windows | CSD → ConditioningEngine |
| --- | --- | --- |
| SomnaAgent | Receives session conditioning report; can query strength summaries for user feedback | ConditioningEngine → Agent |
| --- | --- | --- |

### 11.3 live_control.json Keys

{ "conditioning_engine_enabled": true, "conditioning_vr_schedule_enabled": true, "conditioning_shaping_enabled": true, "conditioning_soc_enabled": false, "conditioning_cue_test_mode": false, "conditioning_session_pairing_count": 0, "conditioning_strongest_pool": "", "conditioning_weakest_pool": "", "conditioning_graduated_pools": \[\], "conditioning_overall_strength": 0.0, "conditioning_shaping_percentile": 70, "conditioning_current_schedule": "continuous", "conditioning_vr_mean": 3, "conditioning_li_flagged_items": \[\], "conditioning_soc_pairs_this_session": 0, "conditioning_cue_test_last_cr_rate": 0.0 }

Writer priority: User slider > LLM agent > ConditioningEngine > config defaults.

## 12\. DB Schema Summary

Four new tables:

### conditioning_associations

All columns from AssociationRecord (Section 2.3). Primary key: record_id. Indexes: (session_id), (cs_identity, cs_pool), (conductor_phase, timestamp_ms).

### conditioning_strengths

All columns from ConditioningStrength (Section 3.2) plus conductor_phase and is_second_order. Primary key: (cs_identity, us_type, conductor_phase). Index: (cs_pool).

### shaping_progress

Columns per Section 7.3. Primary key: (user_id, metric_name).

### cue_test_results

Stores each Cue-Test session: test_id, session_ts, baseline snapshot, per-trial results as JSON array, overall_cr_rate, graduated_pools list.

## 13\. Safety Constraints

1.  **No aversive conditioning.** Somna NEVER pairs stimuli with negative states. All US are positive (relaxation, warmth, parasympathetic activation). If trance_score drops below 0.2 during a session, all conditioning tracking pauses — we do not record associations formed during distressed or agitated states.
2.  **Extinction is intentional.** If a user wants to de-condition a specific CS (e.g., they find a particular tone unpleasant after conditioning), provide an explicit extinction protocol: present the CS repeatedly without the US until strength drops below 0.1.
3.  **VR schedule never goes below VR-2.** Minimum delivery rate of ~50% ensures the user still receives tangible content during sessions. The reinforcement schedule serves conditioning optimization, not content deprivation.
4.  **Cue-test mode requires user initiation.** Never auto-enter cue-test mode. The user must explicitly request it.
5.  **SOC training is opt-in.** Second-order conditioning is disabled by default (conditioning_soc_enabled: false). Users must enable it because it introduces stimuli that will be paired with their conditioned cues — they should understand what they're opting into.

## 14\. Session Conditioning Report

Generated at session end and stored in DB. Available to SomnaAgent for user-facing summaries.

@dataclass class SessionConditioningReport: session_id: str total_pairings: int pairings_by_pool: dict\[str, int\] pairings_by_modality: dict\[str, int\] strength_changes: dict\[str, float\] # delta per pool strongest_association: str # (cs_identity, us_type) with highest strength weakest_association: str li_flagged_count: int # items approaching LI threshold schedule_type_used: str vr_skip_count: int # gate-opens that were VR-skipped soc_pairs: int shaping_percentile: float new_graduations: list\[str\] # pools that crossed graduation threshold # this session

## 15\. DM for Vesper

New file: conditioning_engine.py.

**Classes to implement:**

1.  AssociationRecord — dataclass
2.  ConditioningStrength — dataclass
3.  NeuralStateFingerprint — dataclass with distance()
4.  InteroceptiveContext — dataclass
5.  AssociationRegistry — handles DB read/write for association records
6.  StrengthTracker — Rescorla-Wagner updates, salience decay, extinction tracking
7.  ReinforcementScheduler — VR schedule with strength-adaptive parameters
8.  ShapingEngine — progressive threshold narrowing across sessions
9.  SecondOrderTrainer — SOC pairing protocol with eligibility checks
10. PortableResponseEvaluator — cue-test mode orchestration
11. ConditioningEngine — top-level coordinator, integration facade

**DB migrations:**

- conditioning_associations table
- conditioning_strengths table
- shaping_progress table
- cue_test_results table

**Integration edits:**

- delivery_gate.py: Add ConditioningEngine.should_deliver() check in gate evaluation; add ConditioningEngine.on_delivery() call after every successful fire.
- semantic_selector.py: Add SDL ranking query from ConditioningEngine; add LI-flagged item deprioritization.
- crossmodal_gain.py: Add ShapingEngine reward signal to gain computation.
- conductor.py: Pass conductor_phase to ConditioningEngine; query phase-specific strengths for adaptive phase allocation.
- tmr_engine.py: Share CueManager registry; read graduation flags.
- somna_agent.py: Receive session conditioning report; expose conditioning summaries and cue-test invocation.

**Architectural Rules (unchanged from prior docs)**

• All IPC via live_control.json using \_patch_live().

• Writer priority: User slider > LLM agent > timeline_runner > ConditioningEngine > config defaults.

• DB access through somna_db.py only.

• Synthetic board (board_id=-1) path: all conditioning tracking runs normally with synthetic data for dev testing.

## References

Amsel, A. (1958). The role of frustrative nonreward in noncontinuous reward situations. _Psychological Bulletin_, 55(2), 102–119.

Cone, I., Clopath, C., & Shouval, H. Z. (2024). Learning to express reward prediction error-like dopaminergic activity requires plastic representations of time. _Nature Communications_, 15, 5856.

Engelen, T., Solcà, M., & Tallon-Baudry, C. (2023). Interoceptive rhythms in the brain. _Nature Neuroscience_, 26, 1670–1684.

Fraser, K. M., & Holland, P. C. (2019). Occasion setting. _Behavioral Neuroscience_, 133(2), 145–175.

Lee, J. C. (2021). Second-order conditioning in humans. _Frontiers in Behavioral Neuroscience_, 15, 672628.

Liu, Y., Zhang, G., Qi, R., Ma, J., & Xu, J. (2025). State-dependent memory mechanisms: insights from neural circuits and clinical implications. _Frontiers in Cellular Neuroscience_, 19, 1629796.

Lubow, R. E., & Moore, A. U. (1959). Latent inhibition: The effect of nonreinforced pre-exposure to the conditional stimulus. _Journal of Comparative and Physiological Psychology_, 52(4), 415–419.

Lubow, R. E., & Weiner, I. (Eds.). (2010). _Latent Inhibition: Cognition, Neuroscience and Applications to Schizophrenia_. Cambridge University Press.

Nam, S., & Choi, S. (2020). Effect of threshold setting on neurofeedback training. _NeuroRegulation_, 7(3), 107.

Olson, M. A., & Fazio, R. H. (2001). Implicit attitude formation through classical conditioning. _Psychological Science_, 12(5), 413–417.

Rescorla, R. A., & Wagner, A. R. (1972). A theory of Pavlovian conditioning: Variations in the effectiveness of reinforcement and nonreinforcement. In A. H. Black & W. F. Prokasy (Eds.), _Classical Conditioning II_ (pp. 64–99). Appleton-Century-Crofts.

Schultz, W. (2016). Dopamine reward prediction error signalling: a two-component response. _Nature Reviews Neuroscience_, 17(3), 183–195.

Trucharte, A., et al. (2024). Could an evaluative conditioning intervention ameliorate paranoid beliefs? Self-reported and neurophysiological evidence. _Frontiers in Psychiatry_, 15, 1472332.

END OF DOCUMENT — Doc 43, Somna Specification Series