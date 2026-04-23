import math
import time as _time
import pygame
from pathlib import Path
import random
import threading
from PIL import Image, ImageSequence

from content_tools.somna_db import load_tags as _db_load_tags
from ipc import patch_live


# ── Ganzfeld helpers ─────────────────────────────────────────────────────────


def _cct_to_rgb(cct_k: float) -> tuple:
    """Tanner Helland (2012) CCT → sRGB. Accurate to ~5% for 1000–40 000 K."""
    t = max(1000.0, min(40000.0, float(cct_k))) / 100.0
    r = (
        255
        if t <= 66
        else max(0, min(255, int(329.698727446 * ((t - 60) ** -0.1332047592))))
    )
    if t <= 66:
        g = max(0, min(255, int(99.4708025861 * math.log(t) - 161.1195681661)))
    else:
        g = max(0, min(255, int(288.1221695283 * ((t - 60) ** -0.0755148492))))
    if t >= 66:
        b = 255
    elif t <= 19:
        b = 0
    else:
        b = max(0, min(255, int(138.5177312231 * math.log(t - 10) - 305.0447927307)))
    return (r, g, b)


def _make_vignette_surf(w: int, h: int) -> pygame.Surface:
    """Pre-compute a radial darkening overlay: transparent at center, dark at edges.

    Strategy:
    1. Fill the entire surface with max-alpha darkening (covers corners which
       no inscribed ellipse can reach).
    2. Draw ellipses from full-screen down to tiny centre, each one with
       proportionally lower alpha — later smaller ellipses overwrite interior
       pixels with progressively less opacity, leaving the centre clear.
    """
    MAX_ALPHA = 90
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((0, 0, 0, MAX_ALPHA))
    steps = 64
    for i in range(steps):
        frac = 1.0 - i / steps  # 1.0 = full-screen, 0 = tiny centre
        alpha = int(MAX_ALPHA * (frac**2.2))  # quadratic: max at edge, 0 at centre
        ew = max(1, int(w * frac))
        eh = max(1, int(h * frac))
        x = (w - ew) // 2
        y = (h - eh) // 2
        pygame.draw.ellipse(surf, (0, 0, 0, alpha), (x, y, ew, eh))
    return surf


# Supported format extensions — no mp4 (too heavy; use WebM/VP9 instead).
# avif / apng rely on Pillow 9.1+ (avif) and 8.4+ (apng) — both are common.
_STATIC_EXTS = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.avif", "*.apng")
_ANIMATED_EXTS = ("*.gif", "*.webp", "*.webm", "*.apng")
_ALL_EXTS = (
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.webp",
    "*.webm",
    "*.avif",
    "*.apng",
)

# Hard cap on WebM frames to prevent multi-GB allocations from long videos.
# 120 frames ≈ 4 s at 30 fps — plenty for a looping ambient clip.
_WEBM_MAX_FRAMES = 120

# Maximum surfaces to hold in memory at once.  For large libraries only a
# random sample is loaded; after _RESAMPLE_AFTER switches a fresh random batch
# is drawn from the full directory so variety compounds over a long session.
_MAX_IMAGES = 200
_RESAMPLE_AFTER = 100  # switch calls before drawing a new random sample
# e.g. 100 × 3 s slideshow_interval ≈ 5 min per batch


class BackgroundLayer:
    """Full animated support: GIF + animated WebP/APNG (Pillow) + WebM (OpenCV).

    All heavy image loading runs on background threads so the render loop
    and audio thread are never blocked by file I/O or frame decoding.
    switch() only selects from images that are already fully loaded; if none
    are ready yet it returns silently and keeps showing the previous image.

    Scaling strategy: "contain + tile" — the image is scaled so the entire
    image fits within the display (min scale), then sharp copies tile to
    fill any remaining margins on the shorter axis.

    Session awareness: if session_folder changes while the display is running,
    the layer reloads its image set automatically on the next draw() call.
    If the session folder has no images, the background stays transparent —
    it never falls back to a different session's images.
    """

    def __init__(self, config: dict):
        self.config = config
        self._session_folder = config.get("session_folder", "")
        # Full path list for the session — just Path objects, nothing loaded yet.
        # _scan_image_paths fills this; _resample() draws a new random batch from it.
        self._all_paths = []
        self._switch_count = 0  # increments on every switch(); triggers resample

        # Tag metadata loaded from somna.db (via content_tools.somna_db).
        # _tag_map: filename -> {"tags": [...], "quality": "keep"|"cull", ...}
        # _culled: set of filenames flagged quality="cull" (excluded from pool)
        self._tag_map: dict = {}
        self._culled: set = set()

        # path -> {'frames': [surfs], 'durations': [ms], 'index': int,
        #          'last_frame': int, 'is_animated': bool}
        self.image_cache = {}
        self._cache_lock = threading.Lock()
        self._loading = set()  # paths currently being loaded

        self.current_path = None
        self.current_surf = None
        self.image_width = 0
        self.image_height = 0
        self.last_switch = pygame.time.get_ticks()
        self.interval = int(config.get("slideshow_interval", 0.007) * 1000)

        self._load_tag_metadata(self._session_folder)
        self.images = self._scan_image_paths(self._session_folder)
        self._queue_loads()
        self._pending_switch = True
        # Sync bg_mode only when not in user-selected ganzfeld mode.
        if config.get("bg_mode") != "ganzfeld":
            self._set_bg_mode("slideshow" if self.has_images else "none")
        self._blurred_surf = None

        # Ganzfeld: pre-cached vignette surface (re-built on window resize)
        self._vignette_cache: tuple = (0, 0, None)  # (w, h, Surface)

        # Hot-reload: track images-dir mtime so new files are picked up
        # mid-session without a full reload. Checked every 10 s in tick().
        self._img_dir_mtime: float = self._images_dir_mtime()
        self._img_dir_check_at: float = 0.0

        # Conditioning hook: track last active override tag so a change triggers
        # an immediate _resample() rather than waiting for the next switch cycle.
        self._last_override_tag: str = ""

    # ------------------------------------------------------------------
    def _load_tag_metadata(self, session: str) -> None:
        """Load image metadata from somna.db into _tag_map and _culled."""
        self._tag_map = {}
        self._culled = set()
        try:
            raw = _db_load_tags(session)
            self._tag_map = raw
            self._culled = {
                fname for fname, meta in raw.items() if meta.get("quality") == "cull"
            }
            print(
                f"[Background] Loaded tags for {len(raw)} images "
                f"({len(self._culled)} culled) from '{session}'"
            )
        except Exception as e:
            print(f"[Background] Could not load image metadata: {e}")

    def _filtered_paths(self, all_paths: list, timeline_label: str) -> list:
        """Return the candidate pool filtered by timeline_label and culled set.

        Filtering logic:
        1. Always exclude culled images from the pool.
        2. If agent has set image_filter_override with a valid, unexpired tag,
           restrict the pool to images matching that tag (≥3 required; else fall through).
        3. If a timeline_label is set and at least 5 images match it as a tag,
           restrict the pool to those matching images.
        4. Otherwise fall back to the full unculled set.

        Tag matching is soft: label 'c2_descent' matches tag 'descent' because
        'descent' is a substring of the label (or vice versa).
        """
        import time as _time

        # Step 1: remove culled paths
        unculled = [p for p in all_paths if p.name not in self._culled]

        def _tag_matches(path: Path, needle: str) -> bool:
            meta = self._tag_map.get(path.name)
            if not meta:
                return False
            nl = needle.lower()
            all_tags = meta.get("tags", []) + meta.get("open_tags", [])
            return any(nl in t.lower() or t.lower() in nl for t in all_tags)

        # Step 2: agent conditioning override — takes precedence over timeline label
        override = self.config.get("image_filter_override")
        if override and isinstance(override, dict):
            expires = override.get("expires_at", 0)
            tag = (override.get("tag") or "").strip()
            if tag and expires > _time.time():
                override_pool = [p for p in unculled if _tag_matches(p, tag)]
                if len(override_pool) >= 3:
                    return override_pool
                # Fewer than 3 matches — fall through to normal logic rather than
                # showing an impoverished pool.

        # Step 3: timeline label filter
        label = timeline_label.strip().lower() if timeline_label else ""
        if not label or not self._tag_map:
            return unculled if unculled else all_paths

        matched = [p for p in unculled if _tag_matches(p, label)]
        if len(matched) >= 5:
            return matched

        # Step 4: not enough matched images — fall back to full unculled set
        return unculled if unculled else all_paths

    # ------------------------------------------------------------------
    def _scan_image_paths(self, session: str) -> list:
        """Scan the session images folder, store ALL paths in _all_paths, and
        return a random sample of up to _MAX_IMAGES for the first load batch.

        If the session declares image_tags in live_control, resolve paths
        cross-session from the DB instead of (or in addition to) the local folder.
        Falls back to the local folder if the DB returns fewer than 5 paths.
        """
        root = Path(__file__).parent.parent

        # ── Cross-session image resolution ───────────────────────────────────
        cross_paths = []
        image_tags = self.config.get("image_tags")
        if image_tags and isinstance(image_tags, list):
            try:
                from content_tools.somna_db import get_images_by_tags

                rows = get_images_by_tags(image_tags)
                for row in rows:
                    candidate = (
                        root / "sessions" / row["session"] / "images" / row["filename"]
                    )
                    if candidate.exists():
                        cross_paths.append(candidate)
            except Exception as e:
                print(f"[Background] cross-session image query failed: {e}")

        # ── Local folder scan ─────────────────────────────────────────────────
        local_paths = []
        p = root / "sessions" / session / "images"
        if p.exists():
            for ext in _ALL_EXTS:
                local_paths.extend(p.glob(ext))

        # Use cross-session results if they're rich enough; otherwise local
        if len(cross_paths) >= 5:
            all_imgs = cross_paths
            print(
                f"[Background] cross-session pool: {len(all_imgs)} images "
                f"(tags={image_tags})"
            )
        else:
            all_imgs = local_paths

        self._all_paths = all_imgs
        total = len(all_imgs)

        # Apply tag/cull filtering for the initial batch
        label = self.config.get("timeline_label", "")
        candidate = self._filtered_paths(all_imgs, label)
        batch = (
            candidate
            if len(candidate) <= _MAX_IMAGES
            else random.sample(candidate, _MAX_IMAGES)
        )
        self._switch_count = 0
        print(
            f"[Background] session={session!r}: {total} files found, "
            f"loading first batch of {len(batch)} "
            f"(filtered by label={label!r} → {len(candidate)} candidates)"
        )
        return list(batch)

    def _resample(self) -> None:
        """Draw a fresh random batch from _all_paths and start loading new images.

        Images that are NOT in the new batch are evicted from the cache so
        memory stays bounded.  Images that happen to be in both old and new
        batches keep their cached surfaces (zero reload cost).

        Tag filtering is re-evaluated here so label changes mid-session
        gradually shift the image pool toward the new phase.
        """
        label = self.config.get("timeline_label", "")
        candidate = self._filtered_paths(self._all_paths, label)

        if len(candidate) <= _MAX_IMAGES:
            # Filtered pool fits in memory — still rotate if overall set is large
            if len(self._all_paths) <= _MAX_IMAGES:
                self._switch_count = 0
                return
            new_batch = candidate
        else:
            new_batch = random.sample(candidate, _MAX_IMAGES)

        new_set = set(new_batch)
        old_set = set(self.images)
        to_evict = old_set - new_set

        with self._cache_lock:
            for p in to_evict:
                self.image_cache.pop(p, None)
                self._loading.discard(p)

        self.images = new_batch
        self._switch_count = 0
        kept = len(old_set & new_set)
        evicted = len(to_evict)
        new_in = len(new_set - old_set)
        print(
            f"[Background] Resample: kept {kept}, evicted {evicted}, "
            f"queued {new_in} new images "
            f"(label={label!r} → {len(candidate)} candidates)"
        )
        for p in new_set - old_set:
            self._load_image_async(p)

    def _queue_loads(self) -> None:
        """Kick off async loading for all images in self.images."""
        for img in self.images:
            self._load_image_async(img)

    def _set_bg_mode(self, mode: str) -> None:
        """Write bg_mode to live_control.json so the display reacts immediately."""
        try:
            patch_live({"bg_mode": mode})
        except Exception as e:
            print(f"[Background] Could not update bg_mode: {e}")

    def _reload_session(self, new_session: str) -> None:
        """Switch to a different session's image set without blocking."""
        self._session_folder = new_session
        # Load tag metadata first so _scan_image_paths can use it for filtering
        self._load_tag_metadata(new_session)
        # Clear state — drop references to old surfaces; GC handles memory
        with self._cache_lock:
            self.image_cache.clear()
            self._loading.clear()
        self.images = self._scan_image_paths(new_session)
        self.current_path = None
        self.current_surf = None
        self._pending_switch = True
        self._queue_loads()
        # Mirror bg_mode only if the user hasn't chosen ganzfeld mode
        # (ganzfeld is independent of whether the session has images).
        if self.config.get("bg_mode") != "ganzfeld":
            self._set_bg_mode("slideshow" if self.has_images else "none")

    # ------------------------------------------------------------------
    def _load_image(self, path):
        """Decode a single image/animation into Pygame surfaces.
        Runs on a background thread — never call directly from the render loop.
        """
        ext = str(path).lower()
        frames = []
        durations = []
        is_animated = ext.endswith((".gif", ".webp", ".webm", ".apng"))

        try:
            if ext.endswith(".webm"):
                try:
                    import cv2
                except ImportError:
                    print(
                        f"[Background] OpenCV not installed — skipping WebM '{path.name}'. "
                        f"Install with: pip install opencv-python-headless"
                    )
                    return
                cap = cv2.VideoCapture(str(path))
                if not cap.isOpened():
                    print(
                        f"[Background] OpenCV could not open '{path.name}' — "
                        f"codec may be unsupported. Convert with: "
                        f'ffmpeg -i "{path.name}" -c:v libvpx-vp9 out.webm'
                    )
                    cap.release()
                else:
                    fps = cap.get(cv2.CAP_PROP_FPS) or 30
                    frame_duration = int(1000 / fps)
                    count = 0
                    while count < _WEBM_MAX_FRAMES:
                        ret, frame = cap.read()
                        if not ret:
                            break
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
                        frames.append(surf)
                        durations.append(frame_duration)
                        count += 1
                    cap.release()
                    if count == 0:
                        print(
                            f"[Background] '{path.name}' opened but yielded 0 frames."
                        )
                    elif count == _WEBM_MAX_FRAMES:
                        print(
                            f"[Background] WebM capped at {_WEBM_MAX_FRAMES} frames: {path.name}"
                        )
                    else:
                        print(f"[Background] WebM loaded: {path.name} ({count} frames)")
            else:
                pil_im = Image.open(path)
                for frame in ImageSequence.Iterator(pil_im):
                    if frame.mode != "RGB":
                        frame = frame.convert("RGB")
                    surf = pygame.image.fromstring(
                        frame.tobytes(), frame.size, frame.mode
                    )
                    frames.append(surf)
                    durations.append(pil_im.info.get("duration", 100))
                label = path.suffix.upper().lstrip(".")
                print(
                    f"[Background] {label} loaded: {path.name} ({len(frames)} frames)"
                )
        except Exception as e:
            print(f"[Background] Load failed for {path.name}: {e}")
            is_animated = False

        if not frames:
            try:
                surf = pygame.image.load(str(path))
                frames = [surf]
            except Exception as e:
                print(f"[Background] Static fallback also failed for {path.name}: {e}")
                return
            durations = [999999]
            is_animated = False

        entry = {
            "frames": frames,
            "durations": durations,
            "index": 0,
            "last_frame": pygame.time.get_ticks(),
            "is_animated": is_animated and len(frames) > 1,
        }
        with self._cache_lock:
            self.image_cache[path] = entry

    def _load_image_async(self, path):
        """Start a background thread to load path if not already cached/loading."""
        with self._cache_lock:
            if path in self.image_cache or path in self._loading:
                return
            self._loading.add(path)

        def worker():
            self._load_image(path)
            with self._cache_lock:
                self._loading.discard(path)

        threading.Thread(
            target=worker, daemon=True, name=f"ImgLoad-{path.name}"
        ).start()

    # ------------------------------------------------------------------
    def _cover_scale(self, orig: pygame.Surface) -> pygame.Surface:
        """Scale `orig` to contain the full image within the display.

        Uses min(scale_h, scale_w) so the entire image is always visible.
        Any remaining margins are filled by sharp tiled copies in draw().
        """
        disp = pygame.display.get_surface()
        sw, sh = disp.get_width(), disp.get_height()
        ow, oh = orig.get_width(), orig.get_height()
        if ow == 0 or oh == 0:
            return orig
        scale = min(sh / oh, sw / ow)
        new_w = max(1, int(ow * scale))
        new_h = max(1, int(oh * scale))
        return pygame.transform.smoothscale(orig, (new_w, new_h))

    # ------------------------------------------------------------------
    @property
    def has_images(self) -> bool:
        """True if the current session folder contains any image files.

        When False, visual_display treats the layer as bg_mode='none' so the
        window stays transparent instead of showing opaque black.  The user or
        agent can still opt into a black background by explicitly setting
        bg_mode to a non-none value and providing images.
        """
        return len(self._all_paths) > 0

    # ------------------------------------------------------------------
    def _images_dir_mtime(self) -> float:
        """Return the mtime of the current session's images directory, or 0."""
        root = Path(__file__).parent.parent
        p = root / "sessions" / self._session_folder / "images"
        try:
            return p.stat().st_mtime if p.exists() else 0.0
        except OSError:
            return 0.0

    def _hot_reload_images(self) -> None:
        """Re-scan the images directory and merge any new files into the pool.

        Only appends paths that aren't already known — the cache and current
        image are left untouched, so the session carries on without a flicker.
        """
        new_paths = self._scan_image_paths(self._session_folder)
        existing = set(self._all_paths)
        added = [p for p in new_paths if p not in existing]
        if added:
            self._all_paths.extend(added)
            self.images.extend(added)
            self._queue_loads()
            print(f"[Background] hot-reload: +{len(added)} new image(s)")

    def tick(self, current_config: dict) -> None:
        """Lightweight per-frame update — handles session change and hot-reload.

        Called unconditionally every frame (even when bg_mode='none') so that
        switching to a session with images can flip bg_mode back to 'slideshow'.
        The heavier draw() work only runs when the display actually needs to
        render the background.
        """
        # Keep self.config live so _filtered_paths and _resample see fresh values.
        self.config = current_config

        new_session = current_config.get("session_folder", "")
        if new_session != self._session_folder:
            self._reload_session(new_session)
            return

        # When the agent changes image_filter_override, immediately resample so
        # the pool shifts to the conditioned tag without waiting for a switch cycle.
        override = current_config.get("image_filter_override") or {}
        cur_tag = override.get("tag", "") if isinstance(override, dict) else ""
        if cur_tag != getattr(self, "_last_override_tag", ""):
            self._last_override_tag = cur_tag
            self._resample()

        # Check every 10 s whether new images have been dropped into the folder
        import time as _time

        now = _time.monotonic()
        if now - self._img_dir_check_at >= 10.0:
            self._img_dir_check_at = now
            mtime = self._images_dir_mtime()
            if mtime != self._img_dir_mtime:
                self._img_dir_mtime = mtime
                self._hot_reload_images()

    # ------------------------------------------------------------------
    def switch(self):
        """Switch to a random already-loaded image. No-op if none are ready."""
        with self._cache_lock:
            loaded = [p for p in self.images if p in self.image_cache]
        if not loaded:
            return

        self.current_path = random.choice(loaded)
        with self._cache_lock:
            cache = self.image_cache[self.current_path]

        orig = cache["frames"][cache["index"]]
        scaled = self._cover_scale(orig)
        self.current_surf = scaled
        self.image_width = scaled.get_width()
        self.image_height = scaled.get_height()

        print(
            f"[Background] Switched -> {self.current_path.name} "
            f"({'animated' if cache['is_animated'] else 'static'})"
        )

        # Periodically rotate the sample to keep variety over long sessions
        self._switch_count += 1
        if self._switch_count >= _RESAMPLE_AFTER:
            self._resample()

    # ------------------------------------------------------------------
    def _draw_ganzfeld_bg(self, surface: pygame.Surface, cfg: dict) -> None:
        """Render the Ganzfeld background: solid CCT-tinted field + radial vignette
        + slow looming (breathing luminance oscillation).

        Config keys read:
          bg_ganzfeld_gain      float 0-1    overall brightness (default 0.55)
          bg_ganzfeld_cct_k     float        colour temperature in Kelvin (default 3200)
          bg_ganzfeld_breath_hz float        looming oscillation Hz (default 0.05)
        """
        gain = max(0.0, min(1.0, float(cfg.get("bg_ganzfeld_gain", 0.55) or 0.55)))
        cct_k = float(cfg.get("bg_ganzfeld_cct_k", 3200.0) or 3200.0)
        breath = max(0.005, float(cfg.get("bg_ganzfeld_breath_hz", 0.05) or 0.05))

        # Looming: amplitude is 8 % of gain so the field breathes subtly
        phase = _time.monotonic() * breath * 2.0 * math.pi
        loom_gain = max(0.0, min(1.0, gain + 0.08 * gain * math.sin(phase)))

        base_r, base_g, base_b = _cct_to_rgb(cct_k)
        r = max(0, min(255, int(base_r * loom_gain)))
        g = max(0, min(255, int(base_g * loom_gain)))
        b = max(0, min(255, int(base_b * loom_gain)))

        surface.fill((r, g, b))

        # Vignette: edges darker than centre; cached and regenerated on resize
        w, h = surface.get_size()
        cw, ch, cvs = self._vignette_cache
        if cw != w or ch != h or cvs is None:
            cvs = _make_vignette_surf(w, h)
            self._vignette_cache = (w, h, cvs)
        surface.blit(cvs, (0, 0))

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface, current_config: dict):
        # Session-change detection is handled by tick(), called every frame.
        mode = current_config.get("bg_mode", "slideshow")

        # Ganzfeld: solid CCT field with looming — no images, always opaque.
        if mode == "ganzfeld":
            self._draw_ganzfeld_bg(surface, current_config)
            return

        # Images explicitly disabled — leave the surface transparent.
        if mode == "none":
            surface.fill((0, 0, 0, 0))
            return

        # First draw after init/reload: try to switch once an image has loaded
        if self._pending_switch:
            self.switch()
            if self.current_surf:
                self._pending_switch = False

        if not self.current_surf or not self.current_path:
            surface.fill((0, 0, 0, 0))
            return

        # Advance animation frame for the currently displayed image
        with self._cache_lock:
            cache = self.image_cache.get(self.current_path)
        if cache and cache["is_animated"]:
            now = pygame.time.get_ticks()
            if now - cache["last_frame"] > cache["durations"][cache["index"]]:
                cache["index"] = (cache["index"] + 1) % len(cache["frames"])
                cache["last_frame"] = now
                orig = cache["frames"][cache["index"]]
                scaled = self._cover_scale(orig)
                self.current_surf = scaled
                self.image_width = scaled.get_width()
                self.image_height = scaled.get_height()

        # Centre the scaled image; negative offset = crop, positive = margin
        w, h = surface.get_size()
        x = (w - self.image_width) // 2
        y = (h - self.image_height) // 2

        surface.blit(self.current_surf, (x, y))

        # ── Tile fill: sharp copies fill any side/top margins ─────────────────
        if x > 0 or y > 0:
            iw, ih = self.image_width, self.image_height
            sw, sh = surface.get_size()
            cols_neg = (x + iw - 1) // iw if iw > 0 else 0
            cols_pos = (sw - x + iw - 1) // iw if iw > 0 else 0
            rows_neg = (y + ih - 1) // ih if ih > 0 else 0
            rows_pos = (sh - y + ih - 1) // ih if ih > 0 else 0
            for col in range(-cols_neg, cols_pos):
                for row in range(-rows_neg, rows_pos):
                    if col == 0 and row == 0:
                        continue  # centre tile already drawn above
                    surface.blit(self.current_surf, (x + col * iw, y + row * ih))

        # Slideshow interval
        self.interval = int(current_config.get("slideshow_interval", 0.007) * 1000)
        if pygame.time.get_ticks() - self.last_switch > self.interval:
            self.switch()
            self.last_switch = pygame.time.get_ticks()
