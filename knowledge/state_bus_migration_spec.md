# State Bus Migration Spec

## Goal

Add a `read_live()` RPC to the existing StateServer so that all low-frequency readers (1-10 Hz) can get fresh state over TCP instead of reading `live_control.json` directly from disk. This eliminates stale-state bugs where a process crash leaves outdated values in the file that persist after restart.

**Do NOT touch `config.py` or `visual_display.py`** — those are the 60fps hot path and need a subscription model that is out of scope for this task.

## Architecture

```
Current:   Reader process → json.loads(path.read_text()) → stale data risk
After:     Reader process → TCP "read\n" → StateServer → in-memory dict → fresh data
```

The StateServer already holds all state in memory (it reads from file on every patch/write). We add a `READ` op that returns the current state dict synchronously over the same TCP connection.

## Step 1: StateServer — Add in-memory state cache + READ handler

File: `F:\Somna\ipc\state_server.py`

### 1a: Add `_state` dict to `__init__`

After `self._lock = threading.Lock()`, add:

```python
self._state: dict = {}
```

Initialize it from the file if it exists:

```python
try:
    self._state = json.loads(live_path.read_text(encoding="utf-8"))
except Exception:
    self._state = {}
```

### 1b: Update `_apply_patch` to update `_state`

In `_apply_patch`, after the `with self._lock:` line, replace the file-read with `self._state`:

```python
def _apply_patch(self, updates: dict) -> None:
    with self._lock:
        for k, v in updates.items():
            if v is None:
                self._state.pop(k, None)
            else:
                self._state[k] = v
        self._atomic_write(self._state)
```

### 1c: Update `_apply_write` to update `_state`

```python
def _apply_write(self, data: dict) -> None:
    with self._lock:
        self._state = dict(data)
        self._atomic_write(data)
```

### 1d: Add READ handler in `_handle_client`

In the `while b"\n" in buf:` loop inside `_handle_client`, add a handler for `op == "read"`:

```python
if op == "patch":
    self._apply_patch(msg["data"])
elif op == "write":
    self._apply_write(msg["data"])
elif op == "read":
    with self._lock:
        response = json.dumps(self._state, separators=(",", ":")) + "\n"
    conn.sendall(response.encode("utf-8"))
```

The server now responds to read requests with the current in-memory state as a single newline-terminated JSON line.

## Step 2: StateClient — Add `read()` method

File: `F:\Somna\ipc\state_client.py`

### 2a: Add `read()` method to `StateClient` class

This opens a NEW TCP connection (not the fire-and-forget drain connection), sends a read request, and returns the response. This is a synchronous blocking call.

```python
def read(self) -> dict:
    """Read current live state from the StateServer. Blocking."""
    for attempt in range(5):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((self._host, self._port))
            msg = json.dumps({"op": "read"}, separators=(",", ":")).encode("utf-8") + b"\n"
            s.sendall(msg)
            buf = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    break
            s.close()
            line = buf.strip()
            if line:
                return json.loads(line.decode("utf-8"))
        except Exception:
            time.sleep(0.05 * (attempt + 1))
    return {}
```

### 2b: Add module-level `read_live()` function

After the `write_live` function:

```python
def read_live() -> dict:
    """Read current live state from the StateServer via TCP."""
    return _get_client().read()
```

### 2c: Export from `__init__.py`

File: `F:\Somna\ipc\__init__.py`

Add `read_live` to the import and `__all__`:

```python
from ipc.state_client import patch_live, write_live, read_live, set_server_address
from ipc.state_server import StateServer, PORT

__all__ = ["patch_live", "write_live", "read_live", "set_server_address", "StateServer", "PORT"]
```

## Step 3: Migrate readers — replace direct file reads with `read_live()`

For each file below, find the pattern that reads `live_control.json` directly and replace it with `from ipc import read_live` followed by a call to `read_live()`.

### 3a: `F:\Somna\engines\haptic_engine.py`

Find the `_read_live` static method at the bottom of the file:

```python
@staticmethod
def _read_live() -> Optional[dict]:
    try:
        path = Path(__file__).parent.parent / "live_control.json"
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
```

Replace with:

```python
@staticmethod
def _read_live() -> Optional[dict]:
    try:
        from ipc import read_live
        return read_live()
    except Exception:
        return None
```

Remove the `import json` and `from pathlib import Path` at the top of the file ONLY IF they are not used elsewhere in the file. (Check first — `json` is likely used elsewhere.)

### 3b: `F:\Somna\engines\tavns_engine.py`

Find the equivalent `_read_live` static method (same pattern as haptic_engine) and replace identically.

### 3c: `F:\Somna\agent\somna_agent.py`

Find the `_read_live` method on the `SomnaAgent` class. It looks like:

```python
def _read_live(self) -> dict:
    try:
        path = Path(__file__).parent.parent / "live_control.json"
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
```

Replace with:

```python
def _read_live(self) -> dict:
    try:
        from ipc import read_live
        return read_live()
    except Exception:
        return {}
```

### 3d: `F:\Somna\engines\crossmodal_gain.py`

Find any direct read of `live_control.json`. Replace with `from ipc import read_live` and `read_live()`.

### 3e: `F:\Somna\session\conductor.py`

Find any direct read of `live_control.json`. Replace with `from ipc import read_live` and `read_live()`.

### 3f: `F:\Somna\engines\freq_leader.py`

Find any direct read of `live_control.json`. Replace with `from ipc import read_live` and `read_live()`.

### 3g: `F:\Somna\tools\mcp_somna_server.py`

The MCP server tools (`somna_read_live`, etc.) currently read `live_control.json` directly. Replace with `from ipc import read_live` and `read_live()`. Note: the MCP server runs in a different process (Kilo Code's python environment) so it may not be able to import `ipc` — check if the import path works. If `ipc` is not importable from the MCP server's working directory, fall back to the direct file read and leave a comment explaining why.

## Step 4: DO NOT TOUCH

- `config.py` — 60fps display hot path, uses `os.stat()` mtime polling. Out of scope.
- `visual_display.py` — reads via `config.py`, out of scope.
- `control_panel_imgui.py` — already reads through the StateServer via its own direct access.
- `timeline_runner.py` — check if it reads directly; if so, migrate it (it's low frequency).

## Step 5: Test

After all changes, verify:

1. `python -c "from ipc import read_live; print(read_live())"` — should print the current live state dict
2. Start the control panel, verify no crashes
3. Start the agent, verify no crashes
4. Connect the Lovense, verify haptic engine reads state correctly
5. Run `python smoke_test.py` — should pass all checks

## Important Notes

- The `read_live()` TCP call creates a new connection each time. This is intentional — it avoids shared-state bugs between threads. At 1-10 Hz reader frequency, connection overhead is negligible.
- The StateServer's `_state` dict is the single source of truth. The file write is a side effect for crash forensics.
- If the StateServer is not running (e.g., during testing), `read_live()` returns `{}` after 5 retries — same fallback as the current file-read pattern.
- All changes must preserve the existing `patch_live()` and `write_live()` behavior exactly.
