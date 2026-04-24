"""
External Agent Channel Client — connects to MCP prompt bridge on TCP :6790.

somna_agent.py uses this to push assembled prompts to the MCP server,
which forwards them via sampling/createMessage to the connected LLM client
(e.g. Kilo/Resonance). The response comes back over the same TCP connection.

Usage:
    client = ExternalAgentClient()
    if client.connect():
        result = await client.request(prompt="...", system_prompt="...", tick_id="uuid")
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import uuid
from typing import Any, Optional

PROMPT_HOST = "127.0.0.1"
PROMPT_PORT = 6790
CONNECT_TIMEOUT = 2.0
REQUEST_TIMEOUT = 30.0


class ExternalAgentClient:
    """Sync wrapper around the TCP prompt bridge.

    Runs an async receiver thread internally so the synchronous
    somna_agent.py loop can call request() without dealing with asyncio.
    """

    def __init__(self) -> None:
        self._sock: Optional[socket.socket] = None
        self._connected = False
        self._pending: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def connected(self) -> bool:
        return self._connected and self._sock is not None

    def connect(self) -> bool:
        """Try to connect to the MCP prompt bridge. Returns True on success."""
        self.disconnect()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(CONNECT_TIMEOUT)
            s.connect((PROMPT_HOST, PROMPT_PORT))
            s.settimeout(None)
            self._sock = s
            self._connected = True
            self._reader_thread = threading.Thread(
                target=self._recv_loop, name="ExtAgentClient", daemon=True
            )
            self._reader_thread.start()
            print("[ExtChannel] Connected to MCP prompt bridge :6790")
            return True
        except ConnectionRefusedError:
            print("[ExtChannel] Connection refused on :6790 — bridge not ready")
            self._connected = False
            return False
        except OSError as e:
            print(f"[ExtChannel] Connection error: {e}")
            self._connected = False
            return False
        except TimeoutError:
            print("[ExtChannel] Connection timed out on :6790")
            self._connected = False
            return False

    def disconnect(self) -> None:
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def request(
        self,
        prompt: str,
        system_prompt: str = "",
        tick_id: str = "",
        max_tokens: int = 4096,
        timeout: float = REQUEST_TIMEOUT,
    ) -> Optional[dict]:
        """Send a prompt and wait for the response. Returns None on timeout/error."""
        if not self._connected or not self._sock:
            return None

        if not tick_id:
            tick_id = str(uuid.uuid4())

        msg = {
            "type": "prompt",
            "tick_id": tick_id,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "max_tokens": max_tokens,
        }

        event = threading.Event()
        with self._lock:
            self._pending[tick_id] = {"event": event, "result": None}

        try:
            data = json.dumps(msg, ensure_ascii=False) + "\n"
            print(
                f"[ExtChannel] Sending prompt tick={tick_id[:8]}... {len(data)} bytes"
            )
            self._sock.sendall(data.encode("utf-8"))
        except (ConnectionResetError, BrokenPipeError, OSError):
            self.disconnect()
            with self._lock:
                self._pending.pop(tick_id, None)
            return None

        if not event.wait(timeout):
            with self._lock:
                self._pending.pop(tick_id, None)
            return None

        with self._lock:
            entry = self._pending.pop(tick_id, None)
        return entry.get("result") if entry else None

    def _recv_loop(self) -> None:
        """Background thread that reads responses from the TCP bridge."""
        buf = ""
        while self._connected and self._sock:
            try:
                data = self._sock.recv(65536)
                if not data:
                    break
                buf += data.decode("utf-8")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        resp = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    tick_id = resp.get("tick_id", "")
                    with self._lock:
                        entry = self._pending.get(tick_id)
                        if entry:
                            entry["result"] = resp
                            entry["event"].set()
            except (ConnectionResetError, BrokenPipeError, OSError):
                break
        self._connected = False
