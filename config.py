import yaml
import json
import os
from pathlib import Path
import time
from typing import Dict, Any


class ConfigManager:
    """Live config bridge between live_control.json and the render layers.

    Polls live_control.json every 100 ms, but only parses JSON when the
    file's mtime or size has actually changed.  This drops steady-state
    disk overhead from a full JSON parse at 10 Hz to a single stat() call.
    """

    _POLL_INTERVAL = 0.10   # seconds between stat checks

    def __init__(self):
        self.root      = Path(__file__).parent
        self.live_path = self.root / "live_control.json"
        self.last_poll    = 0.0
        self._last_mtime  = -1.0
        self._last_size   = -1
        # Read session_folder from live_control.json first so we never
        # default-init BackgroundLayer (and other layers) with the wrong session.
        live_init = self._read_live()
        self.session_name = live_init.get("session_folder") or "default"
        self.session_path = self.root / "sessions" / self.session_name
        self.config: Dict[str, Any] = self._load_base()

    # ------------------------------------------------------------------
    def _load_base(self) -> Dict:
        cfg = {}
        yaml_file = self.session_path / "session.yaml"
        if yaml_file.exists():
            with open(yaml_file, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        cfg.update(self._read_live())
        cfg["session_folder"] = self.session_name
        return cfg

    def _read_live(self) -> Dict:
        if not self.live_path.exists():
            return {}
        try:
            with open(self.live_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    # ------------------------------------------------------------------
    def update(self) -> Dict:
        now = time.time()
        if now - self.last_poll < self._POLL_INTERVAL:
            return self.config

        self.last_poll = now

        # Cheap stat check before touching JSON at all
        try:
            st = os.stat(self.live_path)
            mtime, size = st.st_mtime, st.st_size
        except FileNotFoundError:
            return self.config

        if mtime == self._last_mtime and size == self._last_size:
            return self.config   # file unchanged — skip parse entirely

        # File changed: parse and merge
        live = self._read_live()
        for k, v in live.items():
            if self.config.get(k) != v:
                self.config[k] = v
        self._last_mtime = mtime
        self._last_size  = size
        return self.config
