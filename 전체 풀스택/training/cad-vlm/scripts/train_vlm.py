"""Fine-tune the CAD vision-language adapter from the unified CAD dataset.

Input records are produced by the PHP DXF/STEP preprocessor importer and must
pass schema/file/hash validation before any GPU model is loaded. Training uses
Qwen3-VL + Unsloth LoRA/QLoRA, saves resumable checkpoints, and exports the
adapter/processor plus a machine-readable run summary for server migration.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from xconcep_cad_vlm.config import load_config
from xconcep_cad_vlm.dataset import to_training_dataset, validate_dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("xconcep.train")


def _last_checkpoint(output_dir: Path) -> str | None:
    checkpoints = []
    for path in output_dir.glob("checkpoint-*"):
        if path.is_dir():
            try:
                checkpoints.append((int(path.name.rsplit("-", 1)[1]), path))
            except ValueError:
                continue
    return str(max(checkpoints)[1]) if checkpoints else None


def _resume_value(value: Any, output_dir: Path) -> str | bool | None:
    if value in (None, False, "", "none"):
        return None
    if value is True:
        return True
    if str(value).lower() == "auto":
        return _last_checkpoint(output_dir)
    return str(Path(str(value)).expanduser().resolve())


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune Qwen3-VL for Xconcep DesignSpec extraction")
    parser.add_argument("--config", default=str(PACKAGE_ROOT / "configs" / "qwen3-vl-4b-qlora.json"))
    parser.add_argument("--dry-run", action="store_true", help="Validate config and data without loading a model")
    args = parser.parse_args()

    config = load_config(args.config)
    # Fail fast on broken manifests, missing views, or stale file hashes.
    validation = validate_dataset(config.dataset_dir)
    LOGGER.info("dataset valid: %s", validation)
    LOGGER.info("effective batch size: %s", config.effective_batch_size)
    if args.dry_run:
        print(json.dumps({
            "status": "dry_run_ok",
            "config": str(config.config_path),
            "dataset": validation,
            "effective_batch_size": config.effective_batch_size,
            "output_dir": str(config.output_dir),
        }, ensure_ascii=False, indent=2))
        return 0

    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required. Run scripts/check_server.py first.")
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    tracking = config.tracking

    from unsloth import FastVisionModel
    from unsloth.trainer import UnslothVisionDataCollator
    from trl import SFTConfig, SFTTrainer

    # Base-model and LoRA knobs are config-driven so smoke and production runs
    # use the same code path and differ only in resource/step settings.
    model_cfg = config.model
    train_cfg = config.training
    lora_cfg = config.lora
    LOGGER.info("loading %s on %s", model_cfg["base_model"], torch.cuda.get_device_name(0))
    model, processor = FastVisionModel.from_pretrained(
        model_name=model_cfg["base_model"],
        load_in_4bit=bool(model_cfg.get("load_in_4bit", True)),
        use_gradient_checkpointing="unsloth",
    )
    max_pixels = model_cfg.get("max_pixels")
    if max_pixels and hasattr(processor, "image_processor"):
        processor.image_processor.max_pixels = int(max_pixels)
    model = FastVisionModel.get_peft_model(
        model,
        finetune_vision_layers=bool(model_cfg.get("finetune_vision_layers", True)),
        finetune_language_layers=bool(model_cfg.get("finetune_language_layers", True)),
        finetune_attention_modules=bool(model_cfg.get("finetune_attention_modules", True)),
        finetune_mlp_modules=bool(model_cfg.get("finetune_mlp_modules", True)),
        r=int(lora_cfg["r"]),
        lora_alpha=int(lora_cfg["alpha"]),
        lora_dropout=float(lora_cfg.get("dropout", 0.0)),
        target_modules="all-linear",
        use_rslora=bool(lora_cfg.get("use_rslora", False)),
        random_state=int(train_cfg.get("seed", 3407)),
    )
    FastVisionModel.for_training(model)
    tokenizer = processor.tokenizer
    eos_token = tokenizer.eos_token
    if not eos_token or tokenizer.convert_tokens_to_ids(eos_token) == tokenizer.unk_token_id:
        raise RuntimeError(f"processor tokenizer has no valid EOS token: {eos_token!r}")

    data_cfg = config.data
    train_data = to_training_dataset(
        config.dataset_dir,
        split=data_cfg.get("train_split", "train"),
        target_type=data_cfg["target_type"],
        max_images=int(data_cfg.get("max_images", 3)),
        limit=data_cfg.get("limit_train"),
    )
    eval_split = data_cfg.get("eval_split")
    eval_data = None
    if eval_split:
        eval_data = to_training_dataset(
            config.dataset_dir,
            split=eval_split,
            target_type=data_cfg["target_type"],
            max_images=int(data_cfg.get("max_images", 3)),
            limit=data_cfg.get("limit_eval"),
        )

    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "resolved_config.json").write_text(
        json.dumps(config.public_snapshot(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_to = list(tracking.get("report_to") or ["tensorboard", "trackio"])
    if "trackio" in report_to and not (os.getenv("HF_TOKEN") or os.getenv("TRACKIO_TOKEN")):
        report_to.remove("trackio")
        LOGGER.warning("Trackio disabled: no Hugging Face/Trackio token is configured; TensorBoard logging remains enabled.")
    if "trackio" in report_to:
        os.environ.setdefault("TRACKIO_PROJECT", str(tracking.get("project", "xconcep-cad-vlm")))
        if os.getenv("TRACKIO_SPACE_ID"):
            LOGGER.info("Trackio: https://huggingface.co/spaces/%s", os.environ["TRACKIO_SPACE_ID"])
    hub = config.hub
    push_to_hub = bool(hub.get("enabled"))
    if push_to_hub and not str(hub.get("repo_id") or "").strip():
        raise ValueError("hub.repo_id is required when hub.enabled=true")
    if push_to_hub and not os.getenv("HF_TOKEN"):
        raise RuntimeError("HF_TOKEN is required when hub.enabled=true")

    sft_args = SFTConfig(
        output_dir=str(output_dir),
        per_device_train_batch_size=int(train_cfg["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(train_cfg.get("per_device_eval_batch_size", 1)),
        gradient_accumulation_steps=int(train_cfg["gradient_accumulation_steps"]),
        num_train_epochs=float(train_cfg.get("num_train_epochs", 1.0)),
        max_steps=int(train_cfg["max_steps"]) if train_cfg.get("max_steps") is not None else -1,
        learning_rate=float(train_cfg["learning_rate"]),
        warmup_ratio=float(train_cfg.get("warmup_ratio", 0.03)),
        weight_decay=float(train_cfg.get("weight_decay", 0.01)),
        max_grad_norm=float(train_cfg.get("max_grad_norm", 1.0)),
        lr_scheduler_type=str(train_cfg.get("lr_scheduler_type", "cosine")),
        optim=str(train_cfg.get("optim", "adamw_8bit")),
        bf16=bool(train_cfg.get("bf16", True)),
        fp16=bool(train_cfg.get("fp16", False)),
        logging_steps=int(train_cfg["logging_steps"]),
        save_steps=int(train_cfg["save_steps"]),
        save_total_limit=int(train_cfg.get("save_total_limit", 3)),
        eval_strategy="steps" if eval_data is not None else "no",
        eval_steps=int(train_cfg.get("eval_steps", train_cfg["save_steps"])),
        save_strategy="steps",
        load_best_model_at_end=eval_data is not None,
        metric_for_best_model="eval_loss" if eval_data is not None else None,
        greater_is_better=False if eval_data is not None else None,
        seed=int(train_cfg.get("seed", 3407)),
        remove_unused_columns=False,
        dataset_text_field="",
        dataset_kwargs={"skip_prepare_dataset": True},
        max_length=None,
        eos_token=eos_token,
        report_to=report_to,
        run_name=str(tracking.get("run_name", "xconcep-cad-vlm")),
        push_to_hub=push_to_hub,
        hub_model_id=hub.get("repo_id") or None,
        hub_token=os.getenv("HF_TOKEN") if push_to_hub else None,
        hub_private_repo=bool(hub.get("private", True)),
        hub_strategy="every_save" if hub.get("push_checkpoints") else "end",
        save_safetensors=True,
        ddp_find_unused_parameters=False,
    )
    trainer = SFTTrainer(
        model=model,
        train_dataset=train_data,
        eval_dataset=eval_data,
        processing_class=processor.tokenizer,
        data_collator=UnslothVisionDataCollator(model, processor),
        args=sft_args,
    )
    resume = _resume_value(train_cfg.get("resume_from_checkpoint"), output_dir)
    LOGGER.info("training records=%d eval=%d resume=%s", len(train_data), len(eval_data or []), resume)
    result = trainer.train(resume_from_checkpoint=resume)
    trainer.save_model(str(output_dir / "adapter"))
    processor.save_pretrained(str(output_dir / "adapter"))
    if push_to_hub:
        trainer.push_to_hub()
        processor.push_to_hub(hub["repo_id"], private=bool(hub.get("private", True)))
    summary = {
        "status": "completed",
        "base_model": model_cfg["base_model"],
        "adapter_dir": str(output_dir / "adapter"),
        "train_records": len(train_data),
        "eval_records": len(eval_data or []),
        "effective_batch_size": config.effective_batch_size,
        "metrics": _json_safe(result.metrics),
        "promotion_note": "Run scripts/evaluate_predictions.py on an independent holdout before promotion.",
    }
    (output_dir / "training_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
