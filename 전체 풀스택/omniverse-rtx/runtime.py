from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = REPO_ROOT / ".omniverse-runtime"
CACHE_ROOT = REPO_ROOT / ".cache"
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
(CACHE_ROOT / "warp").mkdir(parents=True, exist_ok=True)
(CACHE_ROOT / "optix").mkdir(parents=True, exist_ok=True)

os.environ.setdefault("OVRTX_SKIP_USD_CHECK", "1")
os.environ.setdefault("OPTIX_CACHE_PATH", str(CACHE_ROOT / "optix"))
os.environ.setdefault("WARP_CACHE_PATH", str(CACHE_ROOT / "warp"))

import numpy as np
import ovrtx
import ovstage

os.environ.setdefault("OVRTX_BIN_PATH", str(Path(ovrtx.__file__).resolve().parent / "bin"))

import ovstream
import warp as wp
from PIL import Image

from scene import RENDER_PRODUCT_PATH, validation_stage_usda


LOGGER = logging.getLogger("xconcep.omniverse")


@wp.kernel
def _rgba_to_bgra(image: wp.array3d(dtype=wp.uint8)):
    row, column = wp.tid()
    red = image[row, column, 0]
    image[row, column, 0] = image[row, column, 2]
    image[row, column, 2] = red


@dataclass(frozen=True)
class RuntimeConfig:
    width: int = 1280
    height: int = 720
    fps: int = 30
    cuda_device: int = 0
    signaling_port: int = 49100
    public_ip: str = "127.0.0.1"
    health_host: str = "127.0.0.1"
    health_port: int = 8011
    warmup_frames: int = 5

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        return cls(
            width=int(os.getenv("OVRTX_WIDTH", "1280")),
            height=int(os.getenv("OVRTX_HEIGHT", "720")),
            fps=int(os.getenv("OVRTX_FPS", "30")),
            cuda_device=int(os.getenv("OVRTX_CUDA_DEVICE", "0")),
            signaling_port=int(os.getenv("OVSTREAM_SIGNALING_PORT", "49100")),
            public_ip=os.getenv("OVSTREAM_PUBLIC_IP", "127.0.0.1"),
            health_host=os.getenv("OVRTX_HEALTH_HOST", "127.0.0.1"),
            health_port=int(os.getenv("OVRTX_HEALTH_PORT", "8011")),
            warmup_frames=int(os.getenv("OVRTX_WARMUP_FRAMES", "5")),
        )


@dataclass
class RuntimeState:
    ready: bool = False
    renderer_ready: bool = False
    stream_ready: bool = False
    client_connected: bool = False
    frames_rendered: int = 0
    frames_streamed: int = 0
    first_frame_path: str = ""
    last_error: str = ""
    ovrtx_version: str = ""
    ovstream_version: str = ""


class OmniverseRuntime:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.state = RuntimeState()
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._renderer: Any = None
        self._stage: Any = None
        self._ordinal = 1
        self._server: Any = None
        self._server_started = False
        self._stream_buffer: Any = None
        self._health_server: ThreadingHTTPServer | None = None
        self._health_thread: threading.Thread | None = None
        self._ovstream_initialized = False

    def snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            return asdict(self.state)

    def request_stop(self) -> None:
        self._stop_event.set()

    def start_health_server(self) -> None:
        runtime = self

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path not in ("/healthz", "/readyz"):
                    self.send_error(404)
                    return
                payload = runtime.snapshot()
                status = 200 if payload["ready"] else 503
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

        self._health_server = ThreadingHTTPServer(
            (self.config.health_host, self.config.health_port), HealthHandler
        )
        self._health_thread = threading.Thread(
            target=self._health_server.serve_forever,
            name="omniverse-health",
            daemon=True,
        )
        self._health_thread.start()
        LOGGER.info(
            "Health endpoint listening at http://%s:%s/healthz",
            self.config.health_host,
            self.config.health_port,
        )

    def _set_error(self, error: BaseException) -> None:
        with self._state_lock:
            self.state.ready = False
            self.state.last_error = f"{type(error).__name__}: {error}"

    def _create_renderer(self) -> None:
        wp.config.kernel_cache_dir = str(CACHE_ROOT / "warp")
        wp.init()
        log_path = RUNTIME_ROOT / "ovrtx.log"
        self._renderer = ovrtx.Renderer(
            config=ovrtx.RendererConfig(
                sync_mode=True,
                active_cuda_gpus=str(self.config.cuda_device),
                keep_system_alive=True,
                log_file_path=str(log_path),
            )
        )
        with self._state_lock:
            self.state.ovrtx_version = ".".join(map(str, self._renderer.version))

    def _open_validation_stage(self) -> None:
        stage = validation_stage_usda(self.config.width, self.config.height)
        stage_copy = RUNTIME_ROOT / "validation-stage.usda"
        stage_copy.write_text(stage, encoding="utf-8")
        validator = Path(__file__).with_name("pxr_validate.py")
        validation = subprocess.run(
            [sys.executable, str(validator), str(stage_copy)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if validation.returncode != 0:
            detail = validation.stderr.strip() or validation.stdout.strip()
            raise RuntimeError(f"OpenUSD validation failed: {detail}")
        self._stage = ovstage.Stage("xconcep.omniverse.runtime")
        self._renderer.attach_ovstage(self._stage)
        ovstage.population.open_usd_from_string(
            self._stage, stage, ordinal=self._ordinal
        )
        self._stage.advance_write_floor(self._ordinal, ovstage.Scope.ALL).wait()

    @staticmethod
    def _managed(value: Any):
        return value if hasattr(value, "__enter__") else nullcontext(value)

    def _render_frame(self, save_evidence: bool = False) -> None:
        products = self._renderer.step(
            render_products={RENDER_PRODUCT_PATH},
            delta_time=1.0 / self.config.fps,
            ordinal=self._ordinal,
        )
        found_frame = False
        with self._managed(products) as product_set:
            if RENDER_PRODUCT_PATH not in product_set:
                raise RuntimeError(f"RenderProduct missing: {RENDER_PRODUCT_PATH}")
            product = product_set[RENDER_PRODUCT_PATH]
            for frame in product.frames:
                if "LdrColor" not in frame.render_vars:
                    continue
                found_frame = True
                if save_evidence:
                    mapped_cpu = frame.render_vars["LdrColor"].map(device=ovrtx.Device.CPU)
                    with self._managed(mapped_cpu) as cpu_view:
                        rgba = np.from_dlpack(cpu_view).copy()
                    if rgba.shape != (self.config.height, self.config.width, 4):
                        raise RuntimeError(f"Unexpected LdrColor shape: {rgba.shape}")
                    if rgba.dtype != np.uint8 or float(rgba[..., :3].std()) < 2.0:
                        raise RuntimeError("First RTX frame is blank or invalid")
                    evidence = RUNTIME_ROOT / "first-frame.png"
                    Image.fromarray(rgba, mode="RGBA").save(evidence)
                    with self._state_lock:
                        self.state.first_frame_path = str(evidence)

                mapped_cuda = frame.render_vars["LdrColor"].map(device=ovrtx.Device.CUDA)
                with self._managed(mapped_cuda) as cuda_view:
                    rgba_cuda = wp.from_dlpack(cuda_view)
                    shape = tuple(int(value) for value in rgba_cuda.shape)
                    if shape != (self.config.height, self.config.width, 4):
                        raise RuntimeError(f"Unexpected CUDA LdrColor shape: {shape}")
                    if self._stream_buffer is None:
                        self._stream_buffer = wp.empty(
                            shape=shape,
                            dtype=wp.uint8,
                            device=f"cuda:{self.config.cuda_device}",
                        )
                    wp.copy(self._stream_buffer, rgba_cuda)
                    wp.launch(
                        _rgba_to_bgra,
                        dim=(self.config.height, self.config.width),
                        inputs=[self._stream_buffer],
                        device=f"cuda:{self.config.cuda_device}",
                    )
                    wp.synchronize_device(f"cuda:{self.config.cuda_device}")

                with self._state_lock:
                    self.state.frames_rendered += 1
                break
        if not found_frame:
            raise RuntimeError("LdrColor frame was not produced")

    def _start_stream_server(self) -> None:
        def stream_log(level: ovstream.LogLevel, channel: str, message: str, _time: float) -> None:
            LOGGER.log(logging.ERROR if level >= ovstream.LogLevel.ERROR else logging.WARNING, "%s: %s", channel, message)

        ovstream.initialize(log_fn=stream_log, log_min_severity=ovstream.LogLevel.WARNING)
        self._ovstream_initialized = True
        self._server = ovstream.Server(ovstream.ServerType.WEBRTC)

        def on_connection(connected: bool) -> None:
            with self._state_lock:
                self.state.client_connected = connected
            LOGGER.info("WebRTC client connected=%s", connected)

        def on_message(raw: str) -> None:
            LOGGER.debug("WebRTC message: %s", raw)

        def on_input(event: ovstream.InputEvent) -> None:
            LOGGER.debug("WebRTC input: %s", event.type)

        self._server.on_connection = on_connection
        self._server.on_message = on_message
        self._server.on_input = on_input
        cuda_context = int(wp.get_device(f"cuda:{self.config.cuda_device}").context)
        self._server.start(
            ovstream.ServerConfig(
                width=self.config.width,
                height=self.config.height,
                target_fps=self.config.fps,
                video_input=ovstream.VideoInput.CUDA,
                cuda_device=self.config.cuda_device,
                cuda_context=cuda_context,
                webrtc_signal_port=self.config.signaling_port,
                webrtc_public_ip=self.config.public_ip,
            )
        )
        self._server_started = True
        with self._state_lock:
            self.state.ovstream_version = ".".join(map(str, ovstream.get_version()))
            self.state.renderer_ready = True
            self.state.stream_ready = True
            self.state.ready = True

    def validate(self) -> dict[str, Any]:
        try:
            self._create_renderer()
            self._open_validation_stage()
            for _ in range(max(0, self.config.warmup_frames)):
                self._render_frame()
            self._render_frame(save_evidence=True)
            with self._state_lock:
                self.state.renderer_ready = True
                self.state.ready = True
            LOGGER.info("First nonblank RTX frame: %s", self.state.first_frame_path)
            return self.snapshot()
        except BaseException as error:
            self._set_error(error)
            raise
        finally:
            self.close()

    def run(self, max_frames: int | None = None) -> None:
        self.start_health_server()
        try:
            self._create_renderer()
            self._open_validation_stage()
            for _ in range(max(0, self.config.warmup_frames)):
                self._render_frame()
            self._render_frame(save_evidence=True)
            self._start_stream_server()
            LOGGER.info(
                "RTX/WebRTC ready: signal=%s health=%s:%s",
                self.config.signaling_port,
                self.config.health_host,
                self.config.health_port,
            )
            frame = ovstream.VideoFrame.from_cuda_array(self._stream_buffer)
            frame_interval = 1.0 / self.config.fps
            loop_frames = 0
            while not self._stop_event.is_set():
                started = time.perf_counter()
                self._render_frame()
                if self._server.is_client_connected:
                    try:
                        self._server.stream_video(frame)
                    except ovstream.OvstreamError:
                        LOGGER.debug("Client disconnected while sending a frame", exc_info=True)
                    else:
                        with self._state_lock:
                            self.state.frames_streamed += 1
                loop_frames += 1
                if max_frames is not None and loop_frames >= max_frames:
                    self.request_stop()
                remaining = frame_interval - (time.perf_counter() - started)
                if remaining > 0:
                    self._stop_event.wait(remaining)
        except BaseException as error:
            self._set_error(error)
            raise
        finally:
            self.close()

    def close(self) -> None:
        if self._health_server is not None:
            self._health_server.shutdown()
            self._health_server.server_close()
            self._health_server = None
        if self._server is not None:
            if self._server_started:
                try:
                    self._server.stop()
                finally:
                    self._server_started = False
            self._server.close()
            self._server = None
        if self._ovstream_initialized:
            ovstream.shutdown()
            self._ovstream_initialized = False
        if self._stage is not None:
            self._renderer.detach_ovstage()
            self._stage.destroy()
            self._stage = None
        if self._renderer is not None:
            self._renderer.destroy()
            self._renderer = None


def main() -> int:
    parser = argparse.ArgumentParser(description="X concep AI ovrtx/ovstream runtime")
    parser.add_argument("--validate-only", action="store_true", help="render one verified frame and exit")
    parser.add_argument("--max-frames", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    runtime = OmniverseRuntime(RuntimeConfig.from_env())
    if args.validate_only:
        print(json.dumps(runtime.validate(), ensure_ascii=False, indent=2))
        return 0

    def stop_handler(_signum: int, _frame: Any) -> None:
        runtime.request_stop()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    runtime.run(max_frames=args.max_frames)
    return 0


if __name__ == "__main__":
    sys.exit(main())
