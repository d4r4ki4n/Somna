"""Somna Biosignal Dashboard — Real-time physiological telemetry.

Four-tab ImPlot dashboard per Bible Ch.9 S19:
  EEG Overview, Alpha Detail, Cardiac, Respiratory.

Renders as a floating ImGui window from the main show_gui callback.
All data read from live_control.json via the live dict passed each frame.
"""

from __future__ import annotations

import math
import time
from collections import deque

import numpy as np
from imgui_bundle import imgui, implot

from ui.panel_theme import hex_to_rgba, hex_to_u32, RP


BAND_COLORS_RGBA = [
    (0.78, 0.55, 0.86, 0.9),
    (0.24, 0.56, 0.69, 0.9),
    (0.92, 0.44, 0.57, 0.9),
    (0.96, 0.76, 0.47, 0.9),
    (0.62, 0.81, 0.64, 0.9),
]

BAND_NAMES = ["Delta", "Theta", "Alpha", "Beta", "Gamma"]
BAND_KEYS = ["eeg_delta", "eeg_theta", "eeg_alpha", "eeg_beta", "eeg_gamma"]

ROLLING_SECONDS = 10.0
SAMPLE_RATE_HZ = 10.0
ROLLING_N = int(ROLLING_SECONDS * SAMPLE_RATE_HZ)


def _band_col_v4(idx: int, alpha: float | None = None) -> imgui.ImVec4:
    r, g, b, a = BAND_COLORS_RGBA[idx]
    return imgui.ImVec4(r, g, b, alpha if alpha is not None else a)


class BiosignalDashboard:
    def __init__(self) -> None:
        self._ctx = implot.create_context()
        self._ts_buf: deque[float] = deque(maxlen=ROLLING_N)
        self._band_bufs: list[deque[float]] = [
            deque(maxlen=ROLLING_N) for _ in range(5)
        ]
        self._hr_buf: deque[float] = deque(maxlen=ROLLING_N)
        self._rmssd_buf: deque[float] = deque(maxlen=ROLLING_N)
        self._breath_buf: deque[float] = deque(maxlen=ROLLING_N)
        self._last_sample_t: float = 0.0
        self._sample_interval: float = 1.0 / SAMPLE_RATE_HZ
        self._alpha_spectrum_mode: bool = False
        self._live: dict = {}
        self._t0: float = 0.0
        self._connected_since: float = 0.0

    def update(self, live: dict) -> None:
        self._live = dict(live)
        now = time.monotonic()
        if now - self._last_sample_t < self._sample_interval:
            return
        connected = bool(live.get("eeg_connected"))
        if not connected:
            return
        self._last_sample_t = now
        if not self._t0:
            self._t0 = now
        self._ts_buf.append(now - self._t0)
        for i, key in enumerate(BAND_KEYS):
            self._band_bufs[i].append(float(live.get(key) or 0.0))
        self._hr_buf.append(float(live.get("ppg_heart_rate") or 0.0))
        self._rmssd_buf.append(float(live.get("ppg_hrv_rmssd") or 0.0))
        self._breath_buf.append(float(live.get("ppg_breath_rate") or 0.0))

    def render(self) -> None:
        self._render_device_strip()
        imgui.spacing()

        if imgui.begin_tab_bar("biosignal_tabs"):
            sel = imgui.begin_tab_item("EEG Overview")
            if sel[0]:
                self._render_eeg_overview()
                imgui.end_tab_item()
            sel2 = imgui.begin_tab_item("Alpha Detail")
            if sel2[0]:
                self._render_alpha_detail()
                imgui.end_tab_item()
            sel3 = imgui.begin_tab_item("Cardiac")
            if sel3[0]:
                self._render_cardiac()
                imgui.end_tab_item()
            sel4 = imgui.begin_tab_item("Respiratory")
            if sel4[0]:
                self._render_respiratory()
                imgui.end_tab_item()
            imgui.end_tab_bar()

    def _render_device_strip(self) -> None:
        live = self._live
        connected = bool(live.get("eeg_connected"))
        eeg_ts = live.get("eeg_timestamp")
        device_name = str(live.get("eeg_device_name") or "Synthetic")

        dl = imgui.get_window_draw_list()
        cp = imgui.get_cursor_screen_pos()
        dot_r = 5.0
        dot_cx = cp.x + dot_r + 2
        dot_cy = cp.y + imgui.get_text_line_height() * 0.5

        if connected:
            pulse = 0.6 + 0.4 * math.sin(time.monotonic() * 2.0 * math.pi / 1.5)
            col_u32 = hex_to_u32(RP["pine"], pulse)
        else:
            col_u32 = hex_to_u32(RP["love"])

        dl.add_circle_filled(imgui.ImVec2(dot_cx, dot_cy), dot_r, col_u32)

        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + dot_r * 2 + 8)
        imgui.text_colored(imgui.ImVec4(*hex_to_rgba(RP["text"])), device_name)
        imgui.same_line(spacing=12)

        if connected:
            if not self._connected_since:
                self._connected_since = time.monotonic()
            dur = int(time.monotonic() - self._connected_since)
            m, s = divmod(dur, 60)
            imgui.text_colored(
                imgui.ImVec4(*hex_to_rgba(RP["muted"])),
                f"{m}:{s:02d}" if m else f"{dur}s",
            )
        else:
            self._connected_since = 0.0
            imgui.text_colored(imgui.ImVec4(*hex_to_rgba(RP["muted"])), "disconnected")

    def _render_eeg_overview(self) -> None:
        if len(self._ts_buf) < 2:
            imgui.text_colored(
                imgui.ImVec4(*hex_to_rgba(RP["muted"])), "Waiting for EEG data..."
            )
            return

        ts = np.array(self._ts_buf, dtype=np.float64)
        avail = imgui.get_content_region_avail()
        plot_h = max(120.0, avail.y - 10)

        if implot.begin_plot("##eeg_overview", imgui.ImVec2(avail.x, plot_h)):
            implot.setup_axes("Time (s)", "Power")
            t_min = float(ts[0])
            t_max = float(ts[-1])
            if t_max - t_min < 0.5:
                t_max = t_min + 1.0
            implot.setup_axis_limits(
                implot.ImAxis_.x1, t_min, t_max, implot.Cond_.always
            )
            implot.setup_axis_limits(implot.ImAxis_.y1, 0.0, 1.0, implot.Cond_.always)
            for i in range(5):
                ys = np.array(self._band_bufs[i], dtype=np.float64)
                if len(ys) != len(ts):
                    continue
                spec = implot.Spec()
                spec.line_color = _band_col_v4(i)
                spec.line_weight = 1.5
                implot.plot_line(BAND_NAMES[i], ts, ys, spec)
            implot.end_plot()

    def _render_alpha_detail(self) -> None:
        if len(self._ts_buf) < 2:
            imgui.text_colored(
                imgui.ImVec4(*hex_to_rgba(RP["muted"])), "Waiting for EEG data..."
            )
            return

        ts = np.array(self._ts_buf, dtype=np.float64)
        alpha = np.array(self._band_bufs[2], dtype=np.float64)
        if len(alpha) != len(ts):
            return

        avail = imgui.get_content_region_avail()
        plot_h = max(120.0, avail.y - 10)

        if implot.begin_plot("##alpha_detail", imgui.ImVec2(avail.x, plot_h)):
            implot.setup_axes("Time (s)", "Alpha Power")
            t_min = float(ts[0])
            t_max = float(ts[-1])
            if t_max - t_min < 0.5:
                t_max = t_min + 1.0
            implot.setup_axis_limits(
                implot.ImAxis_.x1, t_min, t_max, implot.Cond_.always
            )
            implot.setup_axis_limits(implot.ImAxis_.y1, 0.0, 0.2, implot.Cond_.always)

            spec_shade = implot.Spec()
            spec_shade.fill_color = _band_col_v4(2, 0.15)
            implot.plot_shaded("Alpha fill", ts, alpha, 0.0, spec_shade)

            spec_line = implot.Spec()
            spec_line.line_color = _band_col_v4(2, 0.9)
            spec_line.line_weight = 1.5
            implot.plot_line("Alpha", ts, alpha, spec_line)

            gate_threshold = live.get("eeg_alpha_gate_threshold")
            if gate_threshold is not None:
                thresh = np.array([float(gate_threshold)], dtype=np.float64)
                spec_gate = implot.Spec()
                spec_gate.line_color = imgui.ImVec4(*hex_to_rgba(RP["gold"], 0.7))
                implot.plot_inf_lines("Gate", thresh, spec_gate)

            implot.end_plot()

    def _render_cardiac(self) -> None:
        live = self._live
        ppg_avail = bool(live.get("ppg_available"))

        if not ppg_avail and len(self._hr_buf) < 2:
            imgui.text_colored(
                imgui.ImVec4(*hex_to_rgba(RP["muted"])), "No cardiac source configured"
            )
            return

        if len(self._ts_buf) < 2:
            imgui.text_colored(
                imgui.ImVec4(*hex_to_rgba(RP["muted"])), "Waiting for cardiac data..."
            )
            return

        ts = np.array(self._ts_buf, dtype=np.float64)
        hr = np.array(self._hr_buf, dtype=np.float64)
        rmssd = np.array(self._rmssd_buf, dtype=np.float64)
        n = min(len(ts), len(hr), len(rmssd))
        if n < 2:
            return
        ts, hr, rmssd = ts[:n], hr[:n], rmssd[:n]

        avail = imgui.get_content_region_avail()
        plot_h = max(120.0, avail.y - 10)

        if implot.begin_plot("##cardiac", imgui.ImVec2(avail.x, plot_h)):
            implot.setup_axes("Time (s)", "BPM")
            t_min = float(ts[0])
            t_max = float(ts[-1])
            if t_max - t_min < 0.5:
                t_max = t_min + 1.0
            implot.setup_axis_limits(
                implot.ImAxis_.x1, t_min, t_max, implot.Cond_.always
            )
            implot.setup_axis_limits(implot.ImAxis_.y1, 0.0, 160.0, implot.Cond_.always)

            spec_shade = implot.Spec()
            spec_shade.fill_color = imgui.ImVec4(*hex_to_rgba(RP["love"], 0.15))
            implot.plot_shaded("HR fill", ts, hr, 0.0, spec_shade)

            spec_hr = implot.Spec()
            spec_hr.line_color = imgui.ImVec4(*hex_to_rgba(RP["love"], 0.8))
            spec_hr.line_weight = 1.5
            implot.plot_line("Heart Rate", ts, hr, spec_hr)

            spec_rmssd = implot.Spec()
            spec_rmssd.line_color = imgui.ImVec4(*hex_to_rgba(RP["foam"], 0.7))
            implot.plot_line("RMSSD (ms)", ts, rmssd, spec_rmssd)

            implot.end_plot()

        hr_now = float(live.get("ppg_heart_rate") or 0)
        rmssd_now = float(live.get("ppg_hrv_rmssd") or 0)
        if hr_now > 0:
            imgui.text_colored(
                imgui.ImVec4(*hex_to_rgba(RP["text"])), f"HR {hr_now:.0f} BPM"
            )
            imgui.same_line(spacing=12)
            imgui.text_colored(
                imgui.ImVec4(*hex_to_rgba(RP["foam"])), f"RMSSD {rmssd_now:.1f} ms"
            )

    def _render_respiratory(self) -> None:
        live = self._live

        if len(self._ts_buf) < 2:
            imgui.text_colored(
                imgui.ImVec4(*hex_to_rgba(RP["muted"])),
                "Waiting for respiratory data...",
            )
            return

        ts = np.array(self._ts_buf, dtype=np.float64)
        breath = np.array(self._breath_buf, dtype=np.float64)
        n = min(len(ts), len(breath))
        if n < 2:
            return
        ts, breath = ts[:n], breath[:n]

        resp_mode = str(live.get("respiratory_mode") or "synthetic")
        source_label = "PPG-DERIVED" if resp_mode == "ppg" else "SYNTHETIC"

        avail = imgui.get_content_region_avail()
        plot_h = max(120.0, avail.y - 10)

        if implot.begin_plot("##respiratory", imgui.ImVec2(avail.x, plot_h)):
            implot.setup_axes("Time (s)", "Rate (Hz)")
            t_min = float(ts[0])
            t_max = float(ts[-1])
            if t_max - t_min < 0.5:
                t_max = t_min + 1.0
            implot.setup_axis_limits(
                implot.ImAxis_.x1, t_min, t_max, implot.Cond_.always
            )

            spec_shade = implot.Spec()
            spec_shade.fill_color = imgui.ImVec4(*hex_to_rgba(RP["foam"], 0.15))
            implot.plot_shaded("Breath fill", ts, breath, 0.0, spec_shade)

            spec_line = implot.Spec()
            spec_line.line_color = imgui.ImVec4(*hex_to_rgba(RP["foam"], 0.7))
            spec_line.line_weight = 1.5
            implot.plot_line("Breath Rate", ts, breath, spec_line)

            implot.end_plot()

        bpm_display = float(
            live.get("ppg_breath_rate") or live.get("breath_rate_bpm") or 0
        )
        bpm_converted = bpm_display * 60.0 if bpm_display < 1.0 else bpm_display
        imgui.text_colored(
            imgui.ImVec4(*hex_to_rgba(RP["text"])), f"{bpm_converted:.1f} BPM"
        )
        imgui.same_line(spacing=12)

        dl = imgui.get_window_draw_list()
        cp = imgui.get_cursor_screen_pos()
        tw = imgui.calc_text_size(source_label).x
        pad = 6.0
        h = imgui.get_text_line_height() + 4.0
        dl.add_rect_filled(
            imgui.ImVec2(cp.x, cp.y),
            imgui.ImVec2(cp.x + tw + pad * 2, cp.y + h),
            hex_to_u32(RP["overlay"]),
            3.0,
        )
        dl.add_text(
            imgui.ImVec2(cp.x + pad, cp.y + 2.0), hex_to_u32(RP["subtle"]), source_label
        )
        imgui.dummy(imgui.ImVec2(tw + pad * 2 + 4, h))
