from __future__ import annotations

import argparse
import base64
import binascii
import io
import os
import threading
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from PIL import Image

from xconcep_cad_vlm.verification import (
    build_verification_prompt,
    evaluate_verification,
    extract_json_object,
)


class VerifyRequest(BaseModel):
    image_base64: str
    requirements: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class ModelRuntime:
    def __init__(self) -> None:
        self.model_name = os.environ.get("VLM_MODEL", "").strip()
        if not self.model_name:
            raise RuntimeError("VLM_MODEL is required")
        load_in_4bit = os.environ.get("VLM_LOAD_IN_4BIT", "true").lower() in {"1", "true", "yes", "on"}
        from unsloth import FastVisionModel

        self.model, self.processor = FastVisionModel.from_pretrained(
            model_name=self.model_name,
            load_in_4bit=load_in_4bit,
        )
        FastVisionModel.for_inference(self.model)
        self.max_new_tokens = max(128, int(os.environ.get("VLM_MAX_NEW_TOKENS", "1024")))
        self.lock = threading.Lock()

    def verify(self, image: Image.Image, requirements: list[dict[str, Any]]) -> dict[str, Any]:
        content = [
            {"type": "image", "image": image},
            {"type": "text", "text": build_verification_prompt(requirements)},
        ]
        inputs = self.processor.apply_chat_template(
            [{"role": "user", "content": content}],
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.model.device)
        with self.lock:
            generated = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                use_cache=True,
            )
        text = self.processor.batch_decode(
            generated[:, inputs["input_ids"].shape[-1] :],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
        verdict = evaluate_verification(requirements, extract_json_object(text))
        verdict.update({"evaluator": "xconcep-cad-vlm", "model": self.model_name})
        return verdict


def _decode_image(value: str) -> Image.Image:
    payload = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid image_base64") from exc
    limit = max(1024, int(os.environ.get("VLM_MAX_IMAGE_BYTES", "20971520")))
    if len(raw) > limit:
        raise HTTPException(status_code=413, detail="image exceeds VLM_MAX_IMAGE_BYTES")
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid image") from exc


app = FastAPI(title="Xconcep CAD VLM Verifier", version="1.0.0")
runtime: ModelRuntime | None = None


@app.on_event("startup")
def startup() -> None:
    global runtime
    runtime = ModelRuntime()


def _authorize(authorization: str | None) -> None:
    expected = os.environ.get("VLM_API_KEY", "").strip()
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid bearer token")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if runtime is not None else "starting",
        "ready": runtime is not None,
        "model": runtime.model_name if runtime is not None else os.environ.get("VLM_MODEL"),
    }


@app.post("/verify")
def verify(request: VerifyRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(authorization)
    if runtime is None:
        raise HTTPException(status_code=503, detail="model is not ready")
    return runtime.verify(_decode_image(request.image_base64), request.requirements)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the trained Xconcep CAD VLM as a semantic verifier")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8191)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run("serve_vlm:app", host=args.host, port=args.port, workers=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
