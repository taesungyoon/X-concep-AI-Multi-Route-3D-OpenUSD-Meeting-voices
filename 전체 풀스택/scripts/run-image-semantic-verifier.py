from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image


STACK_ROOT = Path(__file__).resolve().parents[1]


def _load_scorer():
    path = Path(__file__).with_name("score-geneval-owlvit.py")
    spec = importlib.util.spec_from_file_location("xconcep_semantic_scorer", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load scorer: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GroundingDinoVerifier:
    def __init__(self, model_id: str, revision: str, *, det_threshold: float, text_threshold: float, nms_threshold: float, color_threshold: float):
        scorer = _load_scorer()
        self.scorer = scorer
        self.model_id = model_id
        self.revision = revision
        self.det_threshold = det_threshold
        self.text_threshold = text_threshold
        self.nms_threshold = nms_threshold
        self.color_threshold = color_threshold
        self.device = scorer.torch.device("cuda" if scorer.torch.cuda.is_available() else "cpu")
        self.processor = scorer.AutoProcessor.from_pretrained(model_id, revision=revision)
        self.model = scorer.AutoModelForZeroShotObjectDetection.from_pretrained(
            model_id, revision=revision, use_safetensors=True,
        ).to(self.device)
        self.model.eval()
        self.lock = threading.Lock()

    def verify(self, image_bytes: bytes, requirements: list[dict[str, Any]]) -> dict[str, Any]:
        with Image.open(BytesIO(image_bytes)) as source:
            image = source.convert("RGB")
        classes = list(dict.fromkeys(str(item["class"]).strip() for item in requirements if item.get("class")))
        if not classes:
            raise ValueError("requirements must contain at least one class")
        with self.lock:
            detections = self.scorer._detect_grounding_dino(
                image, classes, self.processor, self.model, self.device,
                self.det_threshold, self.nms_threshold, self.text_threshold,
            )
        passed, reasons, detail = self.scorer._score_case(
            image, {"include": requirements}, detections, self.color_threshold,
        )
        return {
            "passed": passed,
            "reasons": reasons,
            "detail": detail,
            "evaluator": "grounding-dino-local-verifier-v1",
            "model_id": self.model_id,
            "model_revision": self.revision,
            "device": str(self.device),
        }


def make_handler(verifier: GroundingDinoVerifier):
    class Handler(BaseHTTPRequestHandler):
        server_version = "XconcepSemanticVerifier/1.0"

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/health":
                self._json(404, {"error": "not_found"})
                return
            self._json(200, {
                "status": "ready", "evaluator": "grounding-dino-local-verifier-v1",
                "model_id": verifier.model_id, "model_revision": verifier.revision,
                "device": str(verifier.device),
            })

        def do_POST(self):
            if self.path != "/verify":
                self._json(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 32 * 1024 * 1024:
                    raise ValueError("request body must be between 1 byte and 32 MiB")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                requirements = payload.get("requirements")
                if not isinstance(requirements, list):
                    raise ValueError("requirements must be a list")
                image_bytes = base64.b64decode(str(payload.get("image_base64") or ""), validate=True)
                result = verifier.verify(image_bytes, requirements)
                self._json(200, result)
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self._json(400, {"error": type(exc).__name__, "detail": str(exc)})
            except Exception as exc:
                self._json(500, {"error": type(exc).__name__, "detail": str(exc)})

        def log_message(self, format, *args):
            print(f"{self.address_string()} - {format % args}", flush=True)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the pinned local Grounding DINO semantic verifier")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8191)
    parser.add_argument("--model", default="IDEA-Research/grounding-dino-base")
    parser.add_argument("--revision", default="12bdfa3120f3e7ec7b434d90674b3396eccf88eb")
    parser.add_argument("--det-threshold", type=float, default=0.30)
    parser.add_argument("--text-threshold", type=float, default=0.30)
    parser.add_argument("--nms-threshold", type=float, default=0.30)
    parser.add_argument("--color-threshold", type=float, default=0.08)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
    verifier = GroundingDinoVerifier(
        args.model, args.revision, det_threshold=args.det_threshold,
        text_threshold=args.text_threshold, nms_threshold=args.nms_threshold,
        color_threshold=args.color_threshold,
    )
    server = HTTPServer((args.host, args.port), make_handler(verifier))
    print(json.dumps({"status": "ready", "url": f"http://{args.host}:{args.port}", "device": str(verifier.device)}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
