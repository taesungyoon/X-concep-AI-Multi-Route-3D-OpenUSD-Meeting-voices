from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model output does not contain a JSON object")
    value = json.loads(text[start : end + 1])
    if value.get("units") != "mm" or value.get("category") not in {"part", "module", "equipment"}:
        raise ValueError("output is not a valid Xconcep DesignSpec")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an Xconcep CAD VLM adapter")
    parser.add_argument("--model", required=True, help="Adapter directory or Hub repo")
    parser.add_argument("--image", action="append", required=True, help="Repeat for each view")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", default="prediction.json")
    parser.add_argument("--max-new-tokens", type=int, default=2048)
    parser.add_argument("--load-in-4bit", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    from unsloth import FastVisionModel
    model, processor = FastVisionModel.from_pretrained(model_name=args.model, load_in_4bit=args.load_in_4bit)
    FastVisionModel.for_inference(model)
    opened = [Image.open(path).convert("RGB") for path in args.image]
    content = [{"type": "image", "image": image} for image in opened]
    content.append({"type": "text", "text": (
        "동일 대상의 다중 시점 이미지에서 Xconcep DesignSpec JSON만 생성하세요. "
        "단위는 mm, 좌표계는 Z-up/right-handed입니다. 보이지 않는 부품은 추가하지 마세요.\n"
        f"요구사항: {args.prompt}"
    )})
    inputs = processor.apply_chat_template(
        [{"role": "user", "content": content}], add_generation_prompt=True,
        tokenize=True, return_dict=True, return_tensors="pt",
    ).to(model.device)
    generated = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False, use_cache=True)
    text = processor.batch_decode(
        generated[:, inputs["input_ids"].shape[-1] :], skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0]
    prediction = _extract_json(text)
    Path(args.output).write_text(json.dumps(prediction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(prediction, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
