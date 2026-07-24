from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when a training configuration is unsafe or incomplete."""


@dataclass(frozen=True)
class TrainingConfig:
    raw: dict[str, Any]
    config_path: Path
    package_root: Path

    @property
    def model(self) -> dict[str, Any]:
        return self.raw["model"]

    @property
    def data(self) -> dict[str, Any]:
        return self.raw["data"]

    @property
    def training(self) -> dict[str, Any]:
        return self.raw["training"]

    @property
    def lora(self) -> dict[str, Any]:
        return self.raw["lora"]

    @property
    def tracking(self) -> dict[str, Any]:
        return self.raw.get("tracking", {})

    @property
    def hub(self) -> dict[str, Any]:
        return self.raw.get("hub", {})

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (self.package_root / path).resolve()

    @property
    def dataset_dir(self) -> Path:
        return self.resolve_path(self.data["dataset_dir"])

    @property
    def output_dir(self) -> Path:
        return self.resolve_path(self.training["output_dir"])

    @property
    def effective_batch_size(self) -> int:
        return (
            int(self.training["per_device_train_batch_size"])
            * int(self.training["gradient_accumulation_steps"])
            * int(os.getenv("WORLD_SIZE", self.training.get("world_size", 1)))
        )

    def public_snapshot(self) -> dict[str, Any]:
        snapshot = json.loads(json.dumps(self.raw))
        snapshot.get("hub", {}).pop("token", None)
        return snapshot


def _positive_int(section: dict[str, Any], key: str) -> int:
    try:
        value = int(section[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"{key} must be a positive integer") from exc
    if value < 1:
        raise ConfigError(f"{key} must be a positive integer")
    return value


def _validate(raw: dict[str, Any]) -> None:
    required = {"model", "data", "training", "lora"}
    missing = sorted(required - raw.keys())
    if missing:
        raise ConfigError(f"missing config sections: {', '.join(missing)}")
    model, data, training, lora = (raw[key] for key in ("model", "data", "training", "lora"))
    if not str(model.get("base_model") or "").strip():
        raise ConfigError("model.base_model is required")
    if data.get("target_type") not in {"design_spec", "geometry_contract"}:
        raise ConfigError("data.target_type must be design_spec or geometry_contract")
    if not str(data.get("dataset_dir") or "").strip():
        raise ConfigError("data.dataset_dir is required")
    if not str(training.get("output_dir") or "").strip():
        raise ConfigError("training.output_dir is required")
    for key in ("per_device_train_batch_size", "gradient_accumulation_steps", "save_steps", "logging_steps"):
        _positive_int(training, key)
    for key in ("r", "alpha"):
        _positive_int(lora, key)
    learning_rate = float(training.get("learning_rate", 0))
    if not 0 < learning_rate <= 0.01:
        raise ConfigError("training.learning_rate must be in (0, 0.01]")
    warmup_ratio = float(training.get("warmup_ratio", 0))
    if not 0 <= warmup_ratio < 1:
        raise ConfigError("training.warmup_ratio must be in [0, 1)")
    if bool(training.get("bf16")) and bool(training.get("fp16")):
        raise ConfigError("bf16 and fp16 cannot both be enabled")
    if training.get("max_steps") is None and float(training.get("num_train_epochs", 0)) <= 0:
        raise ConfigError("set positive num_train_epochs or max_steps")
    if int(data.get("max_images", 3)) < 1:
        raise ConfigError("data.max_images must be positive")


def load_config(path: str | Path) -> TrainingConfig:
    config_path = Path(path).expanduser().resolve()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("configuration root must be an object")
    _validate(raw)
    package_root = config_path.parent.parent if config_path.parent.name == "configs" else config_path.parent
    return TrainingConfig(raw=raw, config_path=config_path, package_root=package_root.resolve())
