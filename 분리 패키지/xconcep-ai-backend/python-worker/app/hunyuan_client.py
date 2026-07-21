from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from .settings import Settings


class ShapeGenerationClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, image_path: Path, output_path: Path) -> dict[str, Any]:
        if self.settings.hunyuan_mode == "mock":
            raise RuntimeError("mock 3D 생성은 generator.generate_3d_mock 경로를 사용해야 함")
        if self.settings.hunyuan_mode not in {"local_api", "triposr"}:
            raise RuntimeError(f"지원하지 않는 SHAPE_MODE: {self.settings.hunyuan_mode}")
        if not image_path.exists():
            raise FileNotFoundError(f"선택된 2D 이미지가 없음: {image_path}")

        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload = {"image": image_b64, "remove_background": True, "type": "glb"}
        endpoint = f"{self.settings.hunyuan_api_url}/generate"
        timeout = httpx.Timeout(float(self.settings.hunyuan_timeout_seconds), connect=30.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(endpoint, json=payload)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "model/gltf-binary" in content_type or "application/octet-stream" in content_type:
                output_path.write_bytes(response.content)
                return {"mode": self.settings.hunyuan_mode, "engine": self.settings.shape_provider, "source": endpoint}
            data = response.json()
            self._save_json_result(client, data, output_path)
            return {"mode": "json", "source": endpoint, "response": _safe_metadata(data)}

    def _save_json_result(self, client: httpx.Client, data: dict[str, Any], output_path: Path) -> None:
        for key in ("glb_base64", "model_base64", "file_base64"):
            if data.get(key):
                output_path.write_bytes(base64.b64decode(data[key]))
                return
        for key in ("glb_url", "file_url", "url", "download_url"):
            if data.get(key):
                url = str(data[key])
                if url.startswith("/"):
                    url = urljoin(self.settings.hunyuan_api_url + "/", url.lstrip("/"))
                response = client.get(url)
                response.raise_for_status()
                output_path.write_bytes(response.content)
                return
        for key in ("file_path", "path", "output_path"):
            value = data.get(key)
            if value:
                candidate = Path(str(value)).resolve()
                storage_root = self.settings.storage_path.resolve()
                if candidate != storage_root and storage_root not in candidate.parents:
                    raise RuntimeError("이미지-3D 서비스가 허용되지 않은 서버 파일 경로를 반환함")
                if candidate.is_file():
                    shutil.copy2(candidate, output_path)
                    return
        raise RuntimeError("이미지-3D API 응답에서 GLB 파일을 찾을 수 없음")


def _safe_metadata(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key not in {"glb_base64", "model_base64", "file_base64"}}


# Backward-compatible import for existing extensions.
Hunyuan3DClient = ShapeGenerationClient
