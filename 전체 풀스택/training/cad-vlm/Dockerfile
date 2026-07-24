ARG PYTORCH_IMAGE=pytorch/pytorch:2.7.1-cuda12.8-cudnn9-devel
FROM ${PYTORCH_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /workspace
RUN apt-get update && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip wheel && python -m pip install -e ".[train,serve]"
COPY . .
ENTRYPOINT ["python", "scripts/train_vlm.py"]
CMD ["--config", "configs/qwen3-vl-4b-qlora.json"]
