from __future__ import annotations

import base64
import hashlib
import json
import secrets
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageOps

from .generator import generate_2d
from .image_quality import validate_generated_image
from .image_usage import OpenAIImageUsageLedger
from .settings import Settings


class GPTImageClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.usage = OpenAIImageUsageLedger(
            settings.openai_image_usage_db,
            max_requests_per_day=settings.openai_image_max_requests_per_day,
            estimated_cost_usd=settings.openai_image_estimated_cost_usd,
            max_estimated_cost_usd_per_day=settings.openai_image_max_estimated_cost_usd_per_day,
        )

    def generate_concepts(
        self,
        project_id: str,
        prompt: str,
        category: str,
        image_paths: list[str],
        analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self.settings.openai_image_mode == "mock":
            return generate_2d(project_id, prompt, category, image_paths)
        if self.settings.openai_image_mode not in {"comfyui", "openai"}:
            raise RuntimeError(f"지원하지 않는 OPENAI_IMAGE_MODE: {self.settings.openai_image_mode}")
        if self.settings.openai_image_mode == "openai" and not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY 환경변수가 없음")

        project = self.settings.storage_path / "projects" / project_id
        output_dir = project / "concepts"
        output_dir.mkdir(parents=True, exist_ok=True)
        contact_sheet = _make_contact_sheet(image_paths, project / "reference-contact-sheet.png")
        results: list[dict[str, Any]] = []
        variants = list(analysis.get("concept_variants") or [])
        while len(variants) < self.settings.image_concept_count:
            number = len(variants) + 1
            variants.append({
                "name": f"Option {number}",
                "design_direction": "engineering alternative",
                "image_prompt": f"{prompt}\nIndustrial engineering concept alternative {number}.",
            })
        manifest: dict[str, Any] = {
            "provider": self.settings.openai_image_mode,
            "model": (
                self.settings.openai_image_model
                if self.settings.openai_image_mode == "openai"
                else self.settings.comfyui_unet_model
            ),
            "concepts": [],
        }
        for index, variant in enumerate(variants[: self.settings.image_concept_count], start=1):
            output_path = output_dir / f"concept-{index}.png"
            image_prompt = str(variant.get("image_prompt") or prompt)
            image_prompt += "\nPreserve the functional mechanism and engineering constraints from the reference. Generate one product only."
            started = time.monotonic()
            if self.settings.openai_image_mode == "comfyui":
                quality = None
                for attempt in range(1, self.settings.comfyui_max_attempts + 1):
                    image_bytes = self._call_comfyui(image_prompt, contact_sheet, project_id, index)
                    quality = validate_generated_image(
                        image_bytes,
                        self.settings,
                        expected_size=(self.settings.comfyui_width, self.settings.comfyui_height),
                    )
                    if quality["passed"]:
                        break
                assert quality is not None
            else:
                image_bytes = self._call_api(image_prompt, contact_sheet, project_id, index)
                quality = validate_generated_image(
                    image_bytes,
                    self.settings,
                    expected_size=_parse_size(self.settings.openai_image_size),
                )
            if not quality["passed"]:
                failed = [item["id"] for item in quality["checks"] if not item["passed"]]
                raise RuntimeError(f"생성 이미지 품질 검증 실패: {', '.join(failed)}")
            output_path.write_bytes(image_bytes)
            with Image.open(output_path) as generated:
                generated.verify()
            item = {
                "id": f"CONCEPT-{index}",
                "title": str(variant.get("name") or f"Option {index}"),
                "description": str(variant.get("design_direction") or "산업 설계 대안"),
                "url": f"{self.settings.public_storage_prefix}/projects/{project_id}/concepts/{output_path.name}",
                "absolute_path": str(output_path),
                "provider": self.settings.openai_image_mode,
                "quality": quality,
            }
            results.append(item)
            manifest["concepts"].append({
                "id": item["id"],
                "file": output_path.name,
                "prompt_sha256": hashlib.sha256(image_prompt.encode("utf-8")).hexdigest(),
                "duration_seconds": round(time.monotonic() - started, 3),
                "quality": quality,
            })
        (project / "concept_generation_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return results

    def _call_comfyui(
        self,
        prompt: str,
        reference_image: Path | None,
        project_id: str,
        variant_index: int,
    ) -> bytes:
        base_url = self.settings.comfyui_base_url
        timeout = httpx.Timeout(float(self.settings.comfyui_timeout_seconds), connect=15.0)
        client_id = str(uuid.uuid4())
        headers = {"Authorization": f"Bearer {self.settings.comfyui_api_key}"} if self.settings.comfyui_api_key else {}
        with httpx.Client(timeout=timeout, headers=headers) as client:
            uploaded_name = None
            if reference_image is not None:
                with reference_image.open("rb") as stream:
                    upload = client.post(
                        f"{base_url}/upload/image",
                        data={"overwrite": "true", "type": "input"},
                        files={"image": (reference_image.name, stream, "image/png")},
                    )
                upload.raise_for_status()
                upload_data = upload.json()
                uploaded_name = "/".join(
                    part for part in [str(upload_data.get("subfolder") or ""), str(upload_data["name"])] if part
                )

            workflow = self._comfyui_flux_workflow(
                prompt,
                uploaded_name,
                f"xconcep/{project_id}/concept-{variant_index}",
            )
            response = client.post(f"{base_url}/prompt", json={"prompt": workflow, "client_id": client_id})
            response.raise_for_status()
            payload = response.json()
            prompt_id = payload.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI 작업 ID가 없음: {payload}")

            deadline = time.monotonic() + self.settings.comfyui_timeout_seconds
            while time.monotonic() < deadline:
                history_response = client.get(f"{base_url}/history/{prompt_id}")
                history_response.raise_for_status()
                history = history_response.json().get(prompt_id)
                if history:
                    status = history.get("status") or {}
                    if status.get("status_str") == "error":
                        raise RuntimeError(f"ComfyUI 생성 실패: {status.get('messages') or status}")
                    images = (history.get("outputs") or {}).get("13", {}).get("images") or []
                    if images:
                        item = images[0]
                        result = client.get(
                            f"{base_url}/view",
                            params={
                                "filename": item["filename"],
                                "subfolder": item.get("subfolder", ""),
                                "type": item.get("type", "output"),
                            },
                        )
                        result.raise_for_status()
                        return result.content
                time.sleep(1.0)
        raise TimeoutError(f"ComfyUI 생성 시간 초과: {self.settings.comfyui_timeout_seconds}초")

    def _comfyui_flux_workflow(
        self, prompt: str, reference_name: str | None, filename_prefix: str
    ) -> dict[str, Any]:
        positive: list[Any] = ["3", 0]
        negative: list[Any] = ["4", 0]
        workflow: dict[str, Any] = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": self.settings.comfyui_unet_model, "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": self.settings.comfyui_clip_model, "type": "flux2", "device": "default"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
            "5": {"class_type": "VAELoader", "inputs": {"vae_name": self.settings.comfyui_vae_model}},
            "6": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": self.settings.comfyui_width, "height": self.settings.comfyui_height, "batch_size": 1}},
            "7": {"class_type": "RandomNoise", "inputs": {"noise_seed": secrets.randbits(63)}},
            "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "9": {"class_type": "Flux2Scheduler", "inputs": {"steps": self.settings.comfyui_steps, "width": self.settings.comfyui_width, "height": self.settings.comfyui_height}},
            "11": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["7", 0], "guider": ["10", 0], "sampler": ["8", 0], "sigmas": ["9", 0], "latent_image": ["6", 0]}},
            "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["5", 0]}},
            "13": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": filename_prefix}},
        }
        if reference_name:
            workflow.update({
                "14": {"class_type": "LoadImage", "inputs": {"image": reference_name}},
                "15": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["14", 0], "upscale_method": "nearest-exact", "megapixels": 1.0, "resolution": 1}},
                "16": {"class_type": "VAEEncode", "inputs": {"pixels": ["15", 0], "vae": ["5", 0]}},
                "17": {"class_type": "ReferenceLatent", "inputs": {"conditioning": positive, "latent": ["16", 0]}},
                "18": {"class_type": "ReferenceLatent", "inputs": {"conditioning": negative, "latent": ["16", 0]}},
            })
            positive, negative = ["17", 0], ["18", 0]
        workflow["10"] = {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": positive, "negative": negative, "cfg": self.settings.comfyui_cfg}}
        return workflow

    def _call_api(
        self,
        prompt: str,
        reference_image: Path | None,
        project_id: str,
        variant_index: int,
    ) -> bytes:
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        if self.settings.openai_organization:
            headers["OpenAI-Organization"] = self.settings.openai_organization
        if self.settings.openai_project:
            headers["OpenAI-Project"] = self.settings.openai_project
        reservation = self.usage.reserve(
            project_id=project_id,
            variant_index=variant_index,
            model=self.settings.openai_image_model,
            size=self.settings.openai_image_size,
            quality=self.settings.openai_image_quality,
            prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        )
        timeout = httpx.Timeout(float(self.settings.openai_image_timeout_seconds), connect=30.0)
        started = time.monotonic()
        response: httpx.Response | None = None
        try:
            with httpx.Client(timeout=timeout) as client:
                if reference_image is None:
                    response = client.post(
                        f"{self.settings.openai_base_url}/images/generations",
                        headers={**headers, "Content-Type": "application/json"},
                        json={
                            "model": self.settings.openai_image_model,
                            "prompt": prompt,
                            "size": self.settings.openai_image_size,
                            "quality": self.settings.openai_image_quality,
                            "output_format": self.settings.openai_image_output_format,
                        },
                    )
                else:
                    with reference_image.open("rb") as image_file:
                        response = client.post(
                            f"{self.settings.openai_base_url}/images/edits",
                            headers=headers,
                            data={
                                "model": self.settings.openai_image_model,
                                "prompt": prompt,
                                "size": self.settings.openai_image_size,
                                "quality": self.settings.openai_image_quality,
                                "output_format": self.settings.openai_image_output_format,
                            },
                            files={"image": (reference_image.name, image_file, "image/png")},
                        )
                response.raise_for_status()
                payload = response.json()
            self.usage.finish(
                reservation.request_id,
                status="success",
                http_status=response.status_code,
                duration_seconds=round(time.monotonic() - started, 3),
                provider_request_id=response.headers.get("x-request-id", ""),
            )
        except Exception as exc:
            self.usage.finish(
                reservation.request_id,
                status="failed",
                http_status=response.status_code if response is not None else None,
                duration_seconds=round(time.monotonic() - started, 3),
                provider_request_id=response.headers.get("x-request-id", "") if response is not None else "",
                error_type=type(exc).__name__,
            )
            raise
        item = payload["data"][0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            with httpx.Client(timeout=120.0) as client:
                download = client.get(item["url"])
                download.raise_for_status()
                return download.content
        raise RuntimeError("GPT Image API 응답에 이미지 데이터가 없음")


def _parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        return int(width), int(height)
    except (TypeError, ValueError):
        raise ValueError(f"잘못된 이미지 크기: {value}") from None


def _make_contact_sheet(image_paths: list[str], output_path: Path) -> Path | None:
    paths = [Path(path) for path in image_paths if Path(path).exists()]
    if not paths:
        return None
    cells: list[Image.Image] = []
    for path in paths[:4]:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((768, 768))
            canvas = Image.new("RGB", (768, 768), "white")
            x = (768 - image.width) // 2
            y = (768 - image.height) // 2
            canvas.paste(image, (x, y))
            cells.append(canvas)
    if len(cells) == 1:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cells[0].save(output_path, "PNG")
        return output_path
    sheet = Image.new("RGB", (1536, 1536), "white")
    positions = [(0, 0), (768, 0), (0, 768), (768, 768)]
    for cell, pos in zip(cells, positions):
        sheet.paste(cell, pos)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, "PNG")
    return output_path
