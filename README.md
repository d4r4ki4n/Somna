# Somna

**Somna** is a neural write interface — a closed-loop neurostimulation platform that reads your nervous system through EEG biofeedback and writes back through precisely timed audio, visual, haptic, and linguistic stimuli.

It is not a meditation app. It is not a sleep tracker. It is a system for people who actively seek altered states of consciousness and want technology that meets them where they are instead of sanitizing the experience.

---

## What It Does

Somna guides your consciousness along a target trajectory using real-time biosignal feedback:

- **Binaural beats, isochronic tones, and pink noise** synchronized to your brain state
- **GPU-rendered visual spirals** in 14 styles, with trail persistence and subliminal text layers
- **Haptic feedback** through Lovense devices, mapped to session phase and physiological response
- **Transcutaneous auricular vagus nerve stimulation (tAVNS)** through the DG Labs Coyote
- **Text-to-speech** with optional silent subliminal overlay (SSB-AM at 17.5 kHz)
- **An LLM agent** that adapts to your responses in real time

The system reads EEG (Muse 2/S), heart rate, respiration, and motion — then adjusts stimulus parameters live to guide you toward the target state. Every session is a closed loop: your body responds to the stimulus, the sensors detect the response, and the system adapts.

---

## Quick Start

### Prerequisites

- Python 3.10+
- A display (primary monitor used for fullscreen visual output)
- Headphones or bone conduction speakers

### Install

```bash
git clone https://github.com/YOUR_USERNAME/somna.git
cd somna
pip install -r requirements.txt
```

### Run

```bash
python main_imgui.py
```

The control panel opens. On first launch, a welcome wizard guides you through:

1. **About You** — your name and goals
2. **Hardware** — scan for Muse/Lovense/Coyote, or skip
3. **AI Companion** — connect an LLM endpoint (any OpenAI-compatible API), or skip
4. **Ready** — pick a session from the library and press play

You can start with zero hardware. Sessions work with headphones and a screen. EEG, haptics, and tAVNS enhance the experience but are not required.

---

## Hardware Support

| Hardware | Purpose | Required? |
|----------|---------|-----------|
| Headphones / bone conduction | Audio delivery | Yes |
| Display monitor | Visual spirals and text | Yes |
| Muse 2 / Muse S | EEG biofeedback | No |
| Lovense device | Haptic feedback | No |
| DG Labs Coyote | tAVNS electrical stimulation | No |
| Intiface Central | BLE bridge for Lovense | Only with Lovense |

---

## Sessions

Somna ships with 18 session templates covering relaxation, sleep, focus, and deep trance work:

- **First Light** — gentle 15-minute introduction
- **Deep Hold** — extended depth maintenance
- **Fractionation** — 30-minute ascent/descent cycling
- **Edison Mode** — hypnagogic problem-solving
- **SSILD** — Senses-Initiated Lucid Dreaming protocol
- **GENUS** — 40 Hz gamma entrainment (Alzheimer's research frequency)
- **Sleep Default** — sleep onset with progressive deepening
- **Hollow** — dissolution-focused deep trance
- **Gateway F10** — gateway process with 10 Hz alpha target
- And more — see the `sessions/` directory

Each session is a YAML file defining a timeline of keyframes. You can author your own — see `SESSION_AUTHORING.md` for the format.

---

## The Agent

Somna includes an optional LLM agent (**Vesper**) that runs alongside sessions. Vesper can:

- Conduct an intake interview to personalize your experience
- Adapt prompting style based on your response complexity
- Run in **observe mode** (passive monitoring) or **interactive mode** (active guidance)
- Operate fully offline with a local model (Ollama, LM Studio, KoboldCpp)

To use Vesper, point `agent_config.yaml` at any OpenAI-compatible API endpoint. The agent works with cloud APIs (OpenAI, Anthropic via proxy) or local models.

---

## Architecture

Somna is built as a five-layer stack:

1. **Processing & Sensing** — raw hardware data → computed features (one canonical origin per feature)
2. **Biosignal Science** — features → metrics (trance depth index, arousal composite, sleep staging)
3. **Stimulus Generation** — metrics → coordinated audio, visual, haptic, electrical, linguistic output
4. **Session Intelligence** — Conductor FSM + Vesper agent + conditioning engine + sleep architecture
5. **Interface** — ImGui control panel + fullscreen visual display

All inter-process communication flows through a single-writer IPC daemon. See `ARCHITECTURE.md` for the full technical specification.

---

## License

[MIT](LICENSE)

---

## Acknowledgments

Somna was built by Resonance and Bambi. The knowledge base (`knowledge/` directory) contains 11 chapters of research documentation covering the neuroscience, audio engineering, and hypnosis theory behind the system.