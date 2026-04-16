"""
ipc/state_server.py — Single-writer daemon for live_control.json
================================================================
Serialises ALL writes to live_control.json through one thread so that
concurrent patches from the EEG engine, timeline runner, agent, audio
engine, and display process can never interleave or corrupt the file.

Protocol: newline-delimited JSON over loopback TCP (port 6789).
  {"op": "patch", "data": {…}}   — merge updates; None values delete the key
  {"op": "write", "data": {…}}   — full atomic replace

The server responds with nothing (fire-and-forget from the client side).
Every write uses temp-file + os.replace() for atomic NTFS visibility.

Usage (started automatically by control_panel_imgui.py):
    from ipc.state_server import StateServer
    srv = StateServer(Path("live_control.json"))
    srv.start()   # non-blocking; runs as a daemon thread
    …
    srv.stop()
"""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

PORT = 6789
_BACKLOG = 64


class StateServer:
    def __init__(self, live_path: Path) -> None:
        self._live = live_path
        self._lock = threading.Lock()  # serialises every write
        self._sock: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> "StateServer":
        """Bind, listen, and spin up the accept loop. Non-blocking."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", PORT))
        self._sock.listen(_BACKLOG)
        self._running = True
        self._thread = threading.Thread(
            target=self._accept_loop, name="StateServer", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._running = False
        try:
            self._sock.close()
        except Exception:
            pass

    # ── Network ───────────────────────────────────────────────────────────────

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, _ = self._sock.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(conn,),
                    daemon=True,
                    name="StateClient-handler",
                ).start()
            except Exception:
                break

    def _handle_client(self, conn: socket.socket) -> None:
        buf = b""
        try:
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                        op = msg.get("op")
                        if op == "patch":
                            self._apply_patch(msg["data"])
                        elif op == "write":
                            self._apply_write(msg["data"])
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ── Write operations ──────────────────────────────────────────────────────

    def _apply_patch(self, updates: dict) -> None:
        with self._lock:
            try:
                data = (
                    json.loads(self._live.read_text(encoding="utf-8"))
                    if self._live.exists()
                    else {}
                )
            except Exception:
                data = {}
            for k, v in updates.items():
                if v is None:
                    data.pop(k, None)  # None = delete the key
                else:
                    data[k] = v
            self._atomic_write(data)

    def _apply_write(self, data: dict) -> None:
        with self._lock:
            self._atomic_write(data)

    def _atomic_write(self, data: dict) -> None:
        """Write directly to the live file. The lock in _apply_patch / _apply_write
        already serialises all writes, so no temp-file rename is needed.
        os.replace() is unreliable on Windows (file-in-use errors) and was the
        root cause of writes silently failing and checkboxes appearing to skip."""
        try:
            self._live.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass


# ── Standalone entry point (for debugging) ───────────────────────────────────

if __name__ == "__main__":
    import sys

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent
    live = root / "live_control.json"
    print(f"[StateServer] Starting on port {PORT}  live={live}")
    srv = StateServer(live).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.stop()
