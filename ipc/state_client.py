"""
ipc/state_client.py — Per-process client for the StateServer
=============================================================
Each process (control_panel, visual_display, somna_agent, audio_engine, …)
holds exactly one StateClient instance, accessed via the module-level
`patch_live` and `write_live` helpers.

Design goals:
  - Fire-and-forget: callers never block waiting for an ack.
  - Auto-reconnect: if the TCP connection drops (display subprocess restarts,
    etc.), the client queues messages and retries in the background.
  - Thread-safe: `patch_live` may be called from any thread simultaneously.

The send queue drains as fast as the OS loopback allows (~10 µs per message),
so at 100 writes/second the total overhead is < 1 ms/s per process.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
from pathlib import Path
from typing import Optional

from ipc.state_server import PORT

_RECONNECT_DELAY_S = 0.25
_QUEUE_MAXSIZE = 4096  # stop accumulating if the server is gone too long


class StateClient:
    def __init__(self, host: str = "127.0.0.1", port: int = PORT) -> None:
        self._host = host
        self._port = port
        self._q: queue.Queue[bytes] = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self._sock: Optional[socket.socket] = None
        self._thread = threading.Thread(
            target=self._drain_loop, name="StateClient", daemon=True
        )
        self._thread.start()

    # ── Public API ────────────────────────────────────────────────────────────

    def patch(self, updates: dict) -> None:
        """Merge updates into live state.  None values delete the key."""
        self._enqueue({"op": "patch", "data": updates})

    def write(self, data: dict) -> None:
        """Full atomic replace of live state."""
        self._enqueue({"op": "write", "data": data})

    # ── Internal ──────────────────────────────────────────────────────────────

    def _enqueue(self, msg: dict) -> None:
        line = json.dumps(msg, separators=(",", ":")).encode("utf-8") + b"\n"
        try:
            self._q.put_nowait(line)
        except queue.Full:
            pass  # drop oldest item and try again
            try:
                self._q.get_nowait()
                self._q.put_nowait(line)
            except Exception:
                pass

    def _drain_loop(self) -> None:
        while True:
            msg = self._q.get()  # block until there is something to send
            while True:
                try:
                    if self._sock is None:
                        self._connect()
                    self._sock.sendall(msg)
                    break
                except Exception:
                    self._close_sock()
                    time.sleep(_RECONNECT_DELAY_S)

    def _connect(self) -> None:
        while True:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                s.connect((self._host, self._port))
                s.settimeout(None)
                self._sock = s
                return
            except Exception:
                time.sleep(_RECONNECT_DELAY_S)

    def _close_sock(self) -> None:
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None


# ── Module-level singleton ─────────────────────────────────────────────────

_client: Optional[StateClient] = None
_client_lock = threading.Lock()


def _get_client() -> StateClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = StateClient()
    return _client


def patch_live(updates: dict) -> None:
    """Merge *updates* into live_control.json via the StateServer."""
    _get_client().patch(updates)


def write_live(data: dict) -> None:
    """Atomically replace all of live_control.json via the StateServer."""
    _get_client().write(data)


def set_server_address(host: str = "127.0.0.1", port: int = PORT) -> None:
    """Call before first use if the server is on a non-default port."""
    global _client
    with _client_lock:
        _client = StateClient(host=host, port=port)
