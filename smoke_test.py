#!/usr/bin/env python
"""
Somna Smoke Test — automated import and structural checks.

Run from project root:  python smoke_test.py

Exercises every major module, class, function, and data structure
against Bible Ch.1–Ch.11 spec.  Exits 0 on success, 1 on any failure.
"""

import sys
import os
import importlib
import traceback
from pathlib import Path

os.environ["SDL_AUDIODRIVER"] = "dummy"

PASS = 0
FAIL = 0
ERRORS = []


def _result(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
        ERRORS.append(f"  FAIL: {name} — {detail}")


def _import(mod_path):
    try:
        return importlib.import_module(mod_path), None
    except Exception as e:
        return None, e


def _has(obj, name):
    return hasattr(obj, name), getattr(obj, name, None)


# ═══════════════════════════════════════════════════════════════════════════════
#  Ch.1 — Processing Stack / IPC
# ═══════════════════════════════════════════════════════════════════════════════


def test_ipc():
    m, e = _import("ipc")
    _result("ipc imports", m is not None, e)
    if m is None:
        return
    _result("ipc.patch_live", *_has(m, "patch_live"))
    _result("ipc.write_live", *_has(m, "write_live"))
    _result("ipc.StateServer", *_has(m, "StateServer"))
    _result("ipc.PORT", *_has(m, "PORT"))
    _result("ipc.PORT == 6789", m.PORT == 6789)

    sc, e = _import("ipc.state_client")
    _result(
        "ipc.state_client.StateClient", sc is not None and hasattr(sc, "StateClient"), e
    )

    ss, e = _import("ipc.state_server")
    _result(
        "ipc.state_server.StateServer class",
        ss is not None and hasattr(ss, "StateServer"),
        e,
    )


def test_config():
    m, e = _import("config")
    _result("config module", m is not None, e)


# ═══════════════════════════════════════════════════════════════════════════════
#  Ch.2 — Biosignal Science (EEG, PPG, IMU)
# ═══════════════════════════════════════════════════════════════════════════════


def test_eeg_engine():
    m, e = _import("eeg.eeg_engine")
    _result("eeg.eeg_engine imports", m is not None, e)
    if m is None:
        return
    for cls in ("EEGEngine", "SQITracker", "ASSRTracker", "FAATracker"):
        _result(f"eeg.{cls}", *_has(m, cls))
    for fn in (
        "compute_channel_sqi",
        "detect_iaf",
        "detect_iaf_with_confidence",
        "composite_assr",
        "band_coherence",
    ):
        _result(f"eeg.{fn}()", *_has(m, fn))


def test_phase_tracker():
    m, e = _import("eeg.phase_tracker")
    _result(
        "eeg.phase_tracker.PhaseTracker",
        m is not None and hasattr(m, "PhaseTracker"),
        e,
    )


def test_respiratory_tracker():
    m, e = _import("eeg.respiratory_tracker")
    _result(
        "eeg.respiratory_tracker.RespiratoryTracker",
        m is not None and hasattr(m, "RespiratoryTracker"),
        e,
    )
    if m:
        _result("eeg.CONDUCTOR_HOT_WINDOWS", *_has(m, "CONDUCTOR_HOT_WINDOWS"))


def test_pac_estimator():
    m, e = _import("eeg.pac_estimator")
    _result(
        "eeg.pac_estimator.PACEstimator",
        m is not None and hasattr(m, "PACEstimator"),
        e,
    )


def test_delivery_gate():
    m, e = _import("eeg.delivery_gate")
    _result(
        "eeg.delivery_gate.DeliveryGate",
        m is not None and hasattr(m, "DeliveryGate"),
        e,
    )


def test_calibration_manager():
    m, e = _import("eeg.calibration_manager")
    _result(
        "eeg.calibration_manager.CalibrationManager",
        m is not None and hasattr(m, "CalibrationManager"),
        e,
    )


def test_depth_features():
    m, e = _import("eeg.depth_features")
    _result("eeg.depth_features imports", m is not None, e)
    if m is None:
        return
    for fn in (
        "compute_spectral_slope",
        "frontal_spectral_slope",
        "compute_beta_envelope_correlation",
        "enhanced_trance_score",
        "convergent_check",
    ):
        _result(f"eeg.{fn}()", *_has(m, fn))


def test_sleep_classifier():
    m, e = _import("eeg.sleep_classifier")
    _result(
        "eeg.sleep_classifier.SleepStageClassifier",
        m is not None and hasattr(m, "SleepStageClassifier"),
        e,
    )


def test_spindle_detector():
    m, e = _import("eeg.spindle_detector")
    _result(
        "eeg.spindle_detector.SpindleDetector",
        m is not None and hasattr(m, "SpindleDetector"),
        e,
    )


def test_slow_wave_enhancer():
    m, e = _import("eeg.slow_wave_enhancer")
    _result(
        "eeg.slow_wave_enhancer.SlowWaveEnhancer",
        m is not None and hasattr(m, "SlowWaveEnhancer"),
        e,
    )


def test_ppg_engine():
    m, e = _import("eeg.ppg_engine")
    _result("eeg.ppg_engine.PPGEngine", m is not None and hasattr(m, "PPGEngine"), e)


def test_imu_engine():
    m, e = _import("eeg.imu_engine")
    _result("eeg.imu_engine.IMUEngine", m is not None and hasattr(m, "IMUEngine"), e)


def test_gamma_verification_gate():
    m, e = _import("eeg.gamma_verification_gate")
    _result(
        "eeg.gamma_verification_gate.GammaVerificationGate",
        m is not None and hasattr(m, "GammaVerificationGate"),
        e,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Ch.3 — Audio and Entrainment
# ═══════════════════════════════════════════════════════════════════════════════


def test_audio_engine():
    m, e = _import("engines.audio_engine")
    _result("engines.audio_engine imports", m is not None, e)
    if m is None:
        return
    _result("engines.BinauralAudioEngine", *_has(m, "BinauralAudioEngine"))
    _result("engines.NOISE_COLORS", *_has(m, "NOISE_COLORS"))
    nc = getattr(m, "NOISE_COLORS", {})
    _result("NOISE_COLORS has 6+ entries", len(nc) >= 6)


def test_tts_engine():
    m, e = _import("engines.tts_engine")
    _result(
        "engines.tts_engine.TTSEngine", m is not None and hasattr(m, "TTSEngine"), e
    )


def test_crossmodal_gain():
    m, e = _import("engines.crossmodal_gain")
    _result("engines.crossmodal_gain imports", m is not None, e)
    if m is None:
        return
    _result("engines.CrossmodalGainEngine", *_has(m, "CrossmodalGainEngine"))
    _result("engines.SRCalibrationSweep", *_has(m, "SRCalibrationSweep"))
    _result("engines.SLEEP_GAIN_PROFILES", *_has(m, "SLEEP_GAIN_PROFILES"))
    sgp = getattr(m, "SLEEP_GAIN_PROFILES", {})
    expected = ("sleep_approach", "sleep_onset", "sleep_maintain", "sleep_training")
    for k in expected:
        _result(f"SLEEP_GAIN_PROFILES['{k}']", k in sgp)


def test_freq_leader():
    m, e = _import("engines.freq_leader")
    _result("engines.freq_leader imports", m is not None, e)
    if m is None:
        return
    _result("engines.AdaptiveFrequencyLeader", *_has(m, "AdaptiveFrequencyLeader"))
    _result("engines.LeadPhase", *_has(m, "LeadPhase"))
    _result("engines.LeadState", *_has(m, "LeadState"))


def test_spatial_audio():
    m, e = _import("engines.spatial_audio")
    _result(
        "engines.spatial_audio.SpatialAudioEngine",
        m is not None and hasattr(m, "SpatialAudioEngine"),
        e,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Ch.4 — Session Architecture (Conductor, Timeline)
# ═══════════════════════════════════════════════════════════════════════════════


def test_conductor():
    m, e = _import("session.conductor")
    _result("session.conductor imports", m is not None, e)
    if m is None:
        return
    _result("session.Conductor", *_has(m, "Conductor"))
    _result("session.Phase", *_has(m, "Phase"))
    Phase = getattr(m, "Phase", None)
    if Phase:
        expected_phases = [
            "CALIBRATION",
            "INDUCTION",
            "DEEPENING",
            "MAINTENANCE",
            "FRAC_EMERGE",
            "FRAC_EMERGE_HOLD",
            "FRAC_REDROP",
            "SLEEP_APPROACH",
            "SLEEP_ONSET",
            "SLEEP_MAINTAIN",
            "SLEEP_TRAINING",
            "SLEEP_WAKE",
            "EDISON_PREPARATION",
            "EDISON_SEED",
            "EDISON_MONITORING",
            "EDISON_N1_HOLD",
            "EDISON_CAPTURE",
            "EDISON_CYCLE_END",
            "SESSION_END",
            "GENUS_BLOCK",
        ]
        for p in expected_phases:
            _result(f"Phase.{p}", hasattr(Phase, p), f"missing from enum")
    _result("session.CONDUCTOR_OWNED_PARAMS", *_has(m, "CONDUCTOR_OWNED_PARAMS"))
    _result(
        "session.HAPTIC_OWNED_WHEN_CONNECTED", *_has(m, "HAPTIC_OWNED_WHEN_CONNECTED")
    )
    _result(
        "session.TAVNS_OWNED_WHEN_CONNECTED", *_has(m, "TAVNS_OWNED_WHEN_CONNECTED")
    )


def test_edison_mode():
    m, e = _import("session.edison_mode")
    _result("session.edison_mode imports", m is not None, e)
    if m is None:
        return
    _result("session.EdisonModeManager", *_has(m, "EdisonModeManager"))
    _result("session.EdisonState", *_has(m, "EdisonState"))
    EdisonState = getattr(m, "EdisonState", None)
    if EdisonState:
        for s in (
            "PREPARATION",
            "SEED_DELIVERY",
            "MONITORING",
            "N1_HOLD",
            "CAPTURE",
            "CYCLE_COMPLETE",
            "SESSION_END",
        ):
            _result(f"EdisonState.{s}", hasattr(EdisonState, s))


def test_timeline_runner():
    m, e = _import("session.timeline_runner")
    _result("session.timeline_runner imports", m is not None, e)
    if m is None:
        return
    _result("session.TimelineRunner", *_has(m, "TimelineRunner"))
    _result("session.Session", *_has(m, "Session"))


def test_tmr_cue_manager():
    m, e = _import("session.tmr_cue_manager")
    _result("session.tmr_cue_manager imports", m is not None, e)
    if m is None:
        return
    _result("session.CueManager", *_has(m, "CueManager"))
    _result("session.POOL_SIGNATURES", *_has(m, "POOL_SIGNATURES"))
    pools = getattr(m, "POOL_SIGNATURES", {})
    for p in ("IDENTITY", "RELEASE", "POTENTIAL", "SOMATIC", "PURPOSE", "TRANSITION"):
        _result(f"POOL_SIGNATURES['{p}']", p in pools)
    _result("session.pool_for_label()", *_has(m, "pool_for_label"))


def test_tmr_engine():
    m, e = _import("session.tmr_engine")
    _result("session.tmr_engine imports", m is not None, e)
    if m is None:
        return
    _result("session.TMREngine", *_has(m, "TMREngine"))
    _result("session.ConsolidationScheduler", *_has(m, "ConsolidationScheduler"))


def test_session_scorer():
    m, e = _import("session.session_scorer")
    _result("session.session_scorer imports", m is not None, e)
    if m is None:
        return
    _result("session.SessionScorer", *_has(m, "SessionScorer"))
    _result("session.SessionAnalyzer", *_has(m, "SessionAnalyzer"))


def test_session_director():
    m, e = _import("session.session_director")
    _result(
        "session.session_director.SessionDirector",
        m is not None and hasattr(m, "SessionDirector"),
        e,
    )


def test_session_planner():
    m, e = _import("session.session_planner")
    _result(
        "session.session_planner.SessionPlanner",
        m is not None and hasattr(m, "SessionPlanner"),
        e,
    )


def test_session_evaluator():
    m, e = _import("session.session_evaluator")
    _result(
        "session.session_evaluator.SessionEvaluator",
        m is not None and hasattr(m, "SessionEvaluator"),
        e,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Ch.5 — Agent Intelligence
# ═══════════════════════════════════════════════════════════════════════════════


def test_somna_agent():
    m, e = _import("agent.somna_agent")
    _result("agent.somna_agent imports", m is not None, e)
    if m is None:
        return
    _result("agent.SomnaAgent", *_has(m, "SomnaAgent"))


def test_content_agent():
    m, e = _import("agent.content_agent")
    _result("agent.content_agent imports", m is not None, e)


def test_llm_driver():
    m, e = _import("agent.llm_driver")
    _result("agent.llm_driver imports", m is not None, e)
    if m is None:
        return
    _result("agent.send()", *_has(m, "send"))
    _result("agent.read_state()", *_has(m, "read_state"))


# ═══════════════════════════════════════════════════════════════════════════════
#  Ch.6 — Conditioning and Content
# ═══════════════════════════════════════════════════════════════════════════════


def test_conditioning_engine():
    m, e = _import("engines.conditioning_engine")
    _result("engines.conditioning_engine imports", m is not None, e)
    if m is None:
        return
    for cls in (
        "ConditioningEngine",
        "StrengthTracker",
        "ReinforcementScheduler",
        "ShapingEngine",
        "SecondOrderTrainer",
        "AssociationRegistry",
        "NeuralStateFingerprint",
        "PortableResponseEvaluator",
    ):
        _result(f"engines.{cls}", *_has(m, cls))


def test_habituation_engine():
    m, e = _import("engines.habituation_engine")
    _result("engines.habituation_engine imports", m is not None, e)
    if m is None:
        return
    for cls in ("HabituationEngine", "NoveltyBudget", "DishabituationScheduler"):
        _result(f"engines.{cls}", *_has(m, cls))


def test_content_manager():
    m, e = _import("content.content_manager")
    _result(
        "content.content_manager.ContentManager",
        m is not None and hasattr(m, "ContentManager"),
        e,
    )


def test_semantic_selector():
    m, e = _import("content.semantic_selector")
    _result(
        "content.semantic_selector.SemanticSelector",
        m is not None and hasattr(m, "SemanticSelector"),
        e,
    )
    if m:
        for pool in ("ALL_POOLS",):
            _result(f"content.{pool}", *_has(m, pool))


def test_content_tools():
    m, e = _import("content_tools")
    _result("content_tools imports", m is not None, e)
    if m is None:
        return
    _result("content_tools.TOOLS", *_has(m, "TOOLS"))
    _result("content_tools.dispatch", *_has(m, "dispatch"))
    tools = getattr(m, "TOOLS", [])
    tool_names = [t.get("function", {}).get("name", "") for t in tools] if tools else []
    expected_tools = (
        "tag_stats",
        "read_session_log",
        "read_session_content",
        "list_sessions",
        "cull_session",
        "write_affirmations_batch",
        "harvest_captions",
        "auto_tag_session",
        "write_affirmations",
        "write_session_yaml",
        "image_pipeline_cycle",
        "query_session_performance",
        "find_images_by_theme",
        "audit_affirmations",
    )
    for t in expected_tools:
        _result(f"tool '{t}'", t in tool_names, "not in TOOLS list")


def test_somna_db():
    m, e = _import("content_tools.somna_db")
    _result("content_tools.somna_db imports", m is not None, e)
    if m is None:
        return
    for fn in (
        "log_edison_capture",
        "get_edison_captures",
        "upsert_session",
        "record_session_played",
        "write_session_metrics",
        "write_conductor_decisions_batch",
        "log_recon_event",
        "read_recon_events",
        "log_palette_entry",
        "best_palette_for_family",
        "save_tags",
        "load_tags",
    ):
        _result(f"somna_db.{fn}()", *_has(m, fn))


# ═══════════════════════════════════════════════════════════════════════════════
#  Ch.7 — Sleep Architecture
# ═══════════════════════════════════════════════════════════════════════════════


def test_sleep_classifier():
    pass  # already tested in Ch.2 section


def test_sleep_reports():
    m, e = _import("content_tools.sleep_report")
    _result(
        "content_tools.sleep_report.read_sleep_report",
        m is not None and hasattr(m, "read_sleep_report"),
        e,
    )


# (sleep classifier tested in Ch.2 section above)


# ═══════════════════════════════════════════════════════════════════════════════
#  Ch.8 — Visual and VR
# ═══════════════════════════════════════════════════════════════════════════════


def test_visual_layers():
    for mod, cls in [
        ("layers.background", "BackgroundLayer"),
        ("layers.center_text", "CenterTextLayer"),
        ("layers.veil", "VeilLayer"),
        ("layers.spirals_opengl", "SpiralsLayer"),
        ("layers.shadows", "ShadowsLayer"),
        ("layers.phrase_pool", "PhrasePool"),
        ("layers.agent_prompt", "AgentPromptLayer"),
        ("layers.font_manager", "FontManager"),
    ]:
        m, e = _import(mod)
        _result(f"{mod}.{cls}", m is not None and hasattr(m, cls), e)


def test_veil_modes():
    m, e = _import("layers.veil")
    _result("layers.veil imports", m is not None, e)
    if m is None:
        return
    vl = m.VeilLayer
    modes = getattr(vl, "_MODES", None)
    if modes:
        _result("veil has _MODES", True)
        for mode in ("scroll", "rain", "drift", "converge", "strobe", "tunnel", "null"):
            _result(f"veil mode '{mode}'", mode in modes, "missing from _MODES")
        _result("veil mode 'mirror' removed", "mirror" not in modes, "still present!")


def test_vr_modules():
    for mod, name in [
        ("vr.vr_safety", "SafetyEnforcer"),
        ("vr.vr_flicker_engine", "DichopticFlickerEngine"),
        ("vr.vr_ssvep_detector", "SSVEPDetector"),
        ("vr.vr_freq_table", "FrequencyAllocationTable"),
        ("vr.vr_ganzfeld", "GanzfeldProtocol"),
        ("vr.vr_vection", "VectionRenderer"),
        ("vr.vr_subliminal", "SubLiminalRenderer"),
        ("vr.vr_overlay", "VROverlayManager"),
    ]:
        m, e = _import(mod)
        _result(f"{mod}.{name}", m is not None and hasattr(m, name), e)


# ═══════════════════════════════════════════════════════════════════════════════
#  Ch.1 §8 — Hardware Output Channels
# ═══════════════════════════════════════════════════════════════════════════════


def test_device_safety():
    m, e = _import("engines.device_safety")
    _result("engines.device_safety imports", m is not None, e)
    if m is None:
        return
    _result("engines.DeviceSafetyEnforcer", *_has(m, "DeviceSafetyEnforcer"))
    _result("engines.UnlockTier", *_has(m, "UnlockTier"))
    _result("engines.UNLOCK_GATES", *_has(m, "UNLOCK_GATES"))
    gates = getattr(m, "UNLOCK_GATES", {})
    _result("UNLOCK_GATES has entries", len(gates) >= 2)


def test_haptic_engine():
    m, e = _import("engines.haptic_engine")
    _result(
        "engines.haptic_engine.HapticEngine",
        m is not None and hasattr(m, "HapticEngine"),
        e,
    )


def test_tavns_engine():
    m, e = _import("engines.tavns_engine")
    _result(
        "engines.tavns_engine.TavnsEngine",
        m is not None and hasattr(m, "TavnsEngine"),
        e,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Ch.9 — Console UI (ImGui)
# ═══════════════════════════════════════════════════════════════════════════════


def test_ui_modules():
    for mod, name in [
        ("ui.panel_theme", "apply_somna_theme"),
        ("ui.panel_theme", "COLOR_TOKENS"),
        ("ui.panel_theme", "RP"),
        ("ui.panel_widgets", "draw_badge"),
        ("ui.panel_widgets", "draw_gauge"),
        ("ui.panel_widgets", "draw_sparkline"),
        ("ui.panel_widgets", "draw_phase_ring"),
        ("ui.panel_widgets", "draw_alert_badge"),
        ("ui.control_panel_manager", "ControlPanelManager"),
        ("ui.interference_graph", "InterferenceGraph"),
        ("ui.interference_graph_panel", "InterferenceGraphPanel"),
        ("ui.interference_graph_integration", "install_interference_graph"),
        ("ui.console", "SpectrogramConsole"),
        ("ui.session_player", "SessionPlayer"),
        ("ui.viz_registry", "VisualizationRegistry"),
    ]:
        m, e = _import(mod)
        _result(f"{mod}.{name}", m is not None and hasattr(m, name), e)


def test_interference_graph_channels():
    m, e = _import("ui.interference_graph")
    _result("ui.interference_graph imports", m is not None, e)
    if m is None:
        return
    for name in ("Band", "Channel", "ChordNode", "Tether", "update_hardware_state"):
        _result(f"interference_graph.{name}", *_has(m, name))


# ═══════════════════════════════════════════════════════════════════════════════
#  Session YAML validation
# ═══════════════════════════════════════════════════════════════════════════════


def test_session_yamls():
    try:
        import yaml
    except ImportError:
        _result("yaml available", False, "PyYAML not installed")
        return
    sessions_dir = Path("sessions")
    if not sessions_dir.exists():
        _result("sessions/ directory", False, "not found")
        return
    for sd in sorted(sessions_dir.iterdir()):
        if not sd.is_dir():
            continue
        yf = sd / "session.yaml"
        if not yf.exists():
            continue
        try:
            d = yaml.safe_load(yf.read_text(encoding="utf-8"))
            _result(f"sessions/{sd.name}/session.yaml parses", True)
            _result(f"sessions/{sd.name} has 'name'", "name" in d if d else False)
            _result(
                f"sessions/{sd.name} has 'defaults'", "defaults" in d if d else False
            )
        except Exception as ex:
            _result(f"sessions/{sd.name}/session.yaml parses", False, str(ex))

    edison = sessions_dir / "edison_default" / "session.yaml"
    if edison.exists():
        d = yaml.safe_load(edison.read_text(encoding="utf-8"))
        _result("edison_default type=edison", d.get("type") == "edison")
        _result("edison_default keyframes=[]", d.get("keyframes") == [])
        _result(
            "edison_default edison_mode=true",
            d.get("defaults", {}).get("edison_mode") is True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Knowledge base integrity
# ═══════════════════════════════════════════════════════════════════════════════


def test_knowledge_files():
    kb = Path("knowledge")
    if not kb.exists():
        _result("knowledge/ directory", False, "not found")
        return
    bible_files = list(kb.glob("bible_ch*.md"))
    _result(
        "Bible chapters present",
        len(bible_files) >= 11,
        f"found {len(bible_files)}, need >= 11",
    )
    required = [
        "bible_ch1_processing_stack.md",
        "bible_ch2_biosignal_science.md",
        "bible_ch3_audio_entrainment.md",
        "bible_ch4_session_architecture.md",
        "bible_ch5_agent_intelligence.md",
    ]
    for f in required:
        _result(f"knowledge/{f}", (kb / f).exists(), "missing")


# ═══════════════════════════════════════════════════════════════════════════════
#  Structural checks
# ═══════════════════════════════════════════════════════════════════════════════


def test_requirements():
    req = Path("requirements.txt")
    _result("requirements.txt exists", req.exists())
    if req.exists():
        content = req.read_text(encoding="utf-8")
        for pkg in (
            "buttplug-py",
            "pydglab-v3",
            "brainflow",
            "pygame",
            "moderngl",
            "edge-tts",
            "pyyaml",
        ):
            _result(f"requirements: {pkg}", pkg in content.lower(), "missing")


def test_agents_md():
    ag = Path("AGENTS.md")
    _result("AGENTS.md exists", ag.exists())
    if ag.exists():
        content = ag.read_text(encoding="utf-8")
        for kw in (
            "edison_active",
            "edison_state",
            "EdisonModeManager",
            "haptic_connected",
            "tavns_connected",
            "DeviceSafetyEnforcer",
            "CONDUCTOR_OWNED_PARAMS",
            "patch_live",
        ):
            _result(f"AGENTS.md documents '{kw}'", kw in content, "not found")


def test_shaders():
    sh = Path("shaders")
    _result("shaders/ directory", sh.exists())
    if sh.exists():
        _result("shaders/spiral.glsl", (sh / "spiral.glsl").exists())


def test_gitignore():
    gi = Path(".gitignore")
    _result(".gitignore exists", gi.exists())
    if gi.exists():
        content = gi.read_text(encoding="utf-8")
        for pattern in (
            "*.db",
            "user_profile.json",
            "live_control.json",
            "__pycache__/",
            "session_logs/*.jsonl",
        ):
            _result(f".gitignore has '{pattern}'", pattern in content, "missing")


# ═══════════════════════════════════════════════════════════════════════════════
#  Runner
# ═══════════════════════════════════════════════════════════════════════════════

TESTS = [
    ("Ch.1 — Processing Stack", [test_ipc, test_config]),
    (
        "Ch.2 — Biosignal Science",
        [
            test_eeg_engine,
            test_phase_tracker,
            test_respiratory_tracker,
            test_pac_estimator,
            test_delivery_gate,
            test_calibration_manager,
            test_depth_features,
            test_sleep_classifier,
            test_spindle_detector,
            test_slow_wave_enhancer,
            test_ppg_engine,
            test_imu_engine,
            test_gamma_verification_gate,
        ],
    ),
    (
        "Ch.3 — Audio and Entrainment",
        [
            test_audio_engine,
            test_tts_engine,
            test_crossmodal_gain,
            test_freq_leader,
            test_spatial_audio,
        ],
    ),
    (
        "Ch.4 — Session Architecture",
        [
            test_conductor,
            test_edison_mode,
            test_timeline_runner,
            test_tmr_cue_manager,
            test_tmr_engine,
            test_session_scorer,
            test_session_director,
            test_session_planner,
            test_session_evaluator,
        ],
    ),
    (
        "Ch.5 — Agent Intelligence",
        [
            test_somna_agent,
            test_content_agent,
            test_llm_driver,
        ],
    ),
    (
        "Ch.6 — Conditioning and Content",
        [
            test_conditioning_engine,
            test_habituation_engine,
            test_content_manager,
            test_semantic_selector,
            test_content_tools,
            test_somna_db,
        ],
    ),
    ("Ch.7 — Sleep Architecture", [test_sleep_reports]),
    ("Ch.8 — Visual and VR", [test_visual_layers, test_veil_modes, test_vr_modules]),
    (
        "Hardware Output Channels",
        [test_device_safety, test_haptic_engine, test_tavns_engine],
    ),
    ("Ch.9 — Console UI", [test_ui_modules, test_interference_graph_channels]),
    ("Session YAMLs", [test_session_yamls]),
    ("Knowledge Base", [test_knowledge_files]),
    ("Structure", [test_requirements, test_agents_md, test_shaders, test_gitignore]),
]


def main():
    print("=" * 60)
    print("  Somna Smoke Test")
    print("=" * 60)

    for section, tests in TESTS:
        print(f"\n-- {section} {'-' * (55 - len(section))}")
        for t in tests:
            try:
                t()
            except Exception as ex:
                ERRORS.append(f"  CRASH: {t.__name__} — {ex}")
                global FAIL
                FAIL += 1

    print(f"\n{'=' * 60}")
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}")

    if ERRORS:
        print("\nFailures:")
        for e in ERRORS:
            print(e)
        print()
        sys.exit(1)
    else:
        print("\nAll checks passed.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
