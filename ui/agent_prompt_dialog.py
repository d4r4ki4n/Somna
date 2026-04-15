"""Standalone agent-prompt dialog.

Launched as a subprocess by control_panel_imgui.py when the agent sends a
needs_response message.  Creates a borderless, always-on-top Tk window that
fights the display window's own TOPMOST via a 150 ms SetWindowPos loop —
the same mechanism used by the legacy Tkinter control panel.

Usage:
    python -m ui.agent_prompt_dialog <prompt_text> [timeout_s]

Writes on submit/skip:
    user_response, response_timestamp, agent_message=None  →  ipc.patch_live
Sets llm_dialog_active=True on open, False on close so the display yields TOPMOST.
"""
from __future__ import annotations

import argparse
import io
import sys
import threading
import time
import tkinter as tk
import wave
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from ipc import patch_live  # noqa: E402

# ── Minimal Rosé Pine Moon palette ────────────────────────────────────────────
RP = {
    "base":    "#232136",
    "overlay": "#393552",
    "hl_med":  "#44415a",
    "hl_high": "#56526e",
    "subtle":  "#908caa",
    "muted":   "#6e6a86",
    "text":    "#e0def4",
    "iris":    "#c4a7e7",
    "foam":    "#9ccfd8",
    "love":    "#eb6f92",
}
_FONT_SMALL = ("Segoe UI", 8)


# ── Voice helpers (self-contained; avoids importing control_panel.py) ──────────

def _load_whisper_cfg() -> dict:
    try:
        import yaml
        with open(ROOT / "agent_config.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        w = data.get("whisper") or {}
        return {
            "enabled":  bool(w.get("enabled", True)),
            "model":    str(w.get("model", "whisper-1")),
            "language": str(w.get("language", "en")),
            "base_url": str(data.get("base_url", "http://localhost:5001")),
        }
    except Exception:
        return {"enabled": False, "model": "whisper-1",
                "language": "en", "base_url": "http://localhost:5001"}


def _transcribe_wav(wav_bytes: bytes, base_url: str,
                    model: str = "whisper-1", language: str = "en") -> str:
    import json as _json
    import urllib.request
    boundary = b"somna_whisper_boundary"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n"
        + wav_bytes + b"\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="model"\r\n\r\n'
        + model.encode() + b"\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="language"\r\n\r\n'
        + language.encode() + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url = url.rstrip("/") + "/v1"
    url += "/audio/transcriptions"
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return _json.loads(resp.read()).get("text", "").strip()


class _VoiceRecorder:
    """VAD-aware mic capture; calls on_done(wav_bytes) from a daemon thread."""
    _SILENCE_THRESHOLD = 400
    _SILENCE_SECONDS   = 2.5
    _MIN_SPEECH_CHUNKS = 5
    _MAX_SECONDS       = 30.0

    def __init__(self, on_done):
        self._on_done    = on_done
        self._stopped    = threading.Event()
        self._samplerate = 44100
        self._thread     = threading.Thread(target=self._capture, daemon=True)
        self._thread.start()

    def _capture(self):
        import numpy as np
        import sounddevice as sd

        frames: list = []
        silence_chunks = speech_chunks = 0
        block = 512
        max_blocks = int(self._MAX_SECONDS * self._samplerate / block)
        sil_limit  = int(self._SILENCE_SECONDS * self._samplerate / block)

        with sd.InputStream(samplerate=self._samplerate, channels=1,
                            dtype="int16", blocksize=block) as stream:
            for _ in range(max_blocks):
                if self._stopped.is_set():
                    break
                chunk, _ = stream.read(block)
                frames.append(chunk.copy())
                rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                if rms < self._SILENCE_THRESHOLD:
                    silence_chunks += 1
                else:
                    silence_chunks = 0
                    speech_chunks  += 1
                if speech_chunks >= self._MIN_SPEECH_CHUNKS and silence_chunks >= sil_limit:
                    break

        raw = np.concatenate(frames, axis=0) if frames else np.zeros((block, 1), dtype="int16")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._samplerate)
            wf.writeframes(raw.tobytes())
        self._on_done(buf.getvalue())

    def stop(self):
        self._stopped.set()


# ── Dialog ─────────────────────────────────────────────────────────────────────

def show_dialog(prompt_text: str, timeout_s: float | None) -> None:
    root = tk.Tk()
    root.withdraw()

    dlg = tk.Toplevel(root)
    dlg.overrideredirect(True)
    dlg.configure(bg=RP["overlay"])
    dlg.attributes("-topmost", True)

    patch_live({"llm_dialog_active": True})

    _topmost_id  = [None]
    _timer_id    = [None]
    _countdown_v = tk.StringVar(value="")

    def _destroy():
        for slot, cancel in ((_topmost_id, dlg.after_cancel),
                             (_timer_id,   dlg.after_cancel)):
            if slot[0] is not None:
                try:
                    cancel(slot[0])
                except Exception:
                    pass
                slot[0] = None
        patch_live({"llm_dialog_active": False})
        try:
            dlg.destroy()
        except Exception:
            pass
        root.quit()

    def _submit(skip: bool = False):
        response = None if skip else (entry.get("1.0", "end-1c").strip() or None)
        patch_live({
            "user_response":      response,
            "response_timestamp": time.time(),
            "agent_message":      None,
        })
        _destroy()

    # ── Iris accent bar ─────────────────────────────────────────────────────
    tk.Frame(dlg, bg=RP["iris"], height=2).pack(fill="x")

    # ── Prompt text ─────────────────────────────────────────────────────────
    tk.Label(
        dlg, text=prompt_text,
        bg=RP["overlay"], fg=RP["subtle"],
        font=("Segoe UI", 10, "italic"),
        wraplength=680, justify="left", anchor="w",
        padx=14, pady=6,
    ).pack(fill="x")

    # ── Input row ───────────────────────────────────────────────────────────
    row = tk.Frame(dlg, bg=RP["hl_med"], padx=10, pady=8)
    row.pack(fill="x")

    entry = tk.Text(
        row, height=2, width=60,
        bg=RP["base"], fg=RP["text"],
        insertbackground=RP["iris"],
        font=("Segoe UI", 11), relief="flat", wrap="word",
        padx=10, pady=6,
    )
    entry.pack(side="left", fill="x", expand=True)
    entry.focus_set()
    entry.bind("<Return>",         lambda _e: _submit())
    entry.bind("<Control-Return>", lambda _e: _submit())
    entry.bind("<Escape>",         lambda _e: _submit(skip=True))

    btn_col = tk.Frame(row, bg=RP["hl_med"])
    btn_col.pack(side="left", padx=(8, 0))

    tk.Label(btn_col, textvariable=_countdown_v,
             bg=RP["hl_med"], fg=RP["muted"],
             font=_FONT_SMALL).pack()

    tk.Button(
        btn_col, text="↵ Send", font=_FONT_SMALL,
        bg=RP["iris"], fg=RP["base"],
        activebackground=RP["foam"], activeforeground=RP["base"],
        relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
        command=lambda: _submit(skip=False),
    ).pack(fill="x")

    tk.Button(
        btn_col, text="Skip", font=_FONT_SMALL,
        bg=RP["overlay"], fg=RP["muted"],
        activebackground=RP["hl_high"], activeforeground=RP["text"],
        relief="flat", bd=0, padx=10, pady=2, cursor="hand2",
        command=lambda: _submit(skip=True),
    ).pack(fill="x", pady=(4, 0))

    # ── Voice input ─────────────────────────────────────────────────────────
    wcfg = _load_whisper_cfg()
    if wcfg["enabled"]:
        _rec     = [None]
        _mactive = [False]
        _mbtn    = [None]

        def _fill(text: str):
            entry.delete("1.0", "end")
            entry.insert("1.0", text)
            entry.focus_set()

        def _on_audio(wav: bytes):
            _mactive[0] = False
            _rec[0]     = None
            dlg.after(0, lambda: _mbtn[0].config(
                text="…", bg=RP["muted"], fg=RP["base"]))
            try:
                tx = _transcribe_wav(wav, wcfg["base_url"],
                                     wcfg["model"], wcfg["language"])
                if tx:
                    dlg.after(0, lambda: _fill(tx))
            except Exception:
                pass
            finally:
                dlg.after(0, lambda: _mbtn[0].config(
                    text="🎤 Voice", bg=RP["overlay"], fg=RP["muted"]))

        def _toggle_mic():
            if not _mactive[0]:
                try:
                    _rec[0]     = _VoiceRecorder(on_done=_on_audio)
                    _mactive[0] = True
                    _mbtn[0].config(text="● Listening…",
                                    bg=RP["love"], fg=RP["base"])
                except Exception:
                    pass
            else:
                _mbtn[0].config(text="…", bg=RP["muted"], fg=RP["base"])
                _mactive[0] = False
                if _rec[0]:
                    _rec[0].stop()
                    _rec[0] = None

        _mbtn[0] = tk.Button(
            btn_col, text="🎤 Voice", font=_FONT_SMALL,
            bg=RP["overlay"], fg=RP["muted"],
            activebackground=RP["hl_high"], activeforeground=RP["text"],
            relief="flat", bd=0, padx=10, pady=2, cursor="hand2",
            command=_toggle_mic,
        )
        _mbtn[0].pack(fill="x", pady=(4, 0))

    # ── Position: bottom-centre, 80 px above taskbar ───────────────────────
    dlg.update_idletasks()
    dw = dlg.winfo_reqwidth()
    dh = dlg.winfo_reqheight()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    dlg.geometry(f"{dw}x{dh}+{(sw - dw) // 2}+{sh - dh - 80}")

    # ── Re-assert HWND_TOPMOST every 150 ms to win the z-order race ────────
    def _keep_topmost():
        try:
            import ctypes
            if not dlg.winfo_exists():
                return
            ctypes.windll.user32.SetWindowPos(
                dlg.winfo_id(), -1, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0010)  # NOSIZE | NOMOVE | NOACTIVATE
            _topmost_id[0] = dlg.after(150, _keep_topmost)
        except Exception:
            pass

    try:
        import ctypes
        ctypes.windll.user32.SetWindowPos(
            dlg.winfo_id(), -1, 0, 0, 0, 0,
            0x0001 | 0x0002 | 0x0010)
        ctypes.windll.user32.SetForegroundWindow(dlg.winfo_id())
        _topmost_id[0] = dlg.after(150, _keep_topmost)
    except Exception:
        pass

    # ── Optional countdown ──────────────────────────────────────────────────
    if timeout_s:
        remaining = [int(timeout_s)]

        def _tick():
            remaining[0] -= 1
            if remaining[0] <= 0:
                _submit(skip=True)
                return
            _countdown_v.set(f"{remaining[0]}s")
            _timer_id[0] = dlg.after(1000, _tick)

        _countdown_v.set(f"{remaining[0]}s")
        _timer_id[0] = dlg.after(1000, _tick)

    root.mainloop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Somna agent-prompt dialog")
    parser.add_argument("prompt_text", help="Agent prompt text to display")
    parser.add_argument("timeout_s",   nargs="?", type=float, default=None,
                        help="Auto-skip timeout in seconds (optional)")
    args = parser.parse_args()
    show_dialog(args.prompt_text, args.timeout_s)
