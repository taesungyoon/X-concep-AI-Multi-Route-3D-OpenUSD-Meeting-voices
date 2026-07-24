# Xconcep CAD VLM 서버 설치·파인튜닝 빠른 시작

이 ZIP은 외부 NVIDIA GPU 서버에서 Xconcep `DesignSpec JSON` 추출 모델을
LoRA/QLoRA로 학습하기 위한 독립 패키지다. 모델 weight, 실제 학습 데이터,
`.env`, Hugging Face cache, 학습 결과는 포함하지 않는다.

## 1. 권장 서버

- Ubuntu 22.04 또는 24.04
- NVIDIA Driver와 `nvidia-smi`
- Docker 방식은 NVIDIA Container Toolkit과 Docker Compose v2
- 4B QLoRA: VRAM 24GB 이상, RAM 64GB, 여유 디스크 150GB
- 8B QLoRA: VRAM 48GB 이상, RAM 128GB, 여유 디스크 250GB
- H100/A100 80GB: `configs/qwen3-vl-8b-h100-lora.json`

## 2. 전달 파일 검증

```bash
sha256sum -c xconcep-cad-vlm-portable.zip.sha256
unzip xconcep-cad-vlm-portable.zip
cd xconcep-cad-vlm
python3 scripts/verify_install.py
```

`valid: true`가 아니면 설치하지 않는다.

## 3. Docker 설치와 학습

```bash
cp .env.example .env
# private Hugging Face 모델을 쓸 때만 .env의 HF_TOKEN 입력
docker compose --profile training build trainer
docker compose run --rm trainer \
  --config configs/qwen3-vl-4b-qlora.json --dry-run
docker compose run --rm trainer \
  --config configs/qwen3-vl-4b-qlora.json
```

`data/`는 읽기 전용, `outputs/`와 `hf-cache/`는 호스트에 남는다.

## 4. Ubuntu 가상환경 설치와 학습

```bash
chmod +x scripts/*.sh
./scripts/install-server.sh
source .venv/bin/activate
python scripts/train_vlm.py \
  --config configs/qwen3-vl-4b-qlora.json --dry-run
./scripts/train.sh configs/qwen3-vl-4b-qlora.json
```

기본 PyTorch index는 CUDA 12.8이다. 서버 조건이 다르면 설치 전에 바꾼다.

```bash
export PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu126
./scripts/install-server.sh
```

## 5. PHP DXF/STEP 전처리 데이터 반입

PHP 전처리 프로그램이 만든 패키지 ZIP 또는 패키지 폴더를 입력한다.

```bash
python scripts/import_php_cad_dataset.py \
  --input /data/incoming/cad-packages.zip \
  --output data/raw/company-cad-v1 \
  --license LicenseRef-Company-Approved \
  --training-allowed \
  --minimum-quality 0.90

python scripts/preprocess_dataset.py \
  --input data/raw/company-cad-v1/records.jsonl \
  --output data/production-v1 \
  --max-image-side 2048 \
  --min-images 1 \
  --split 0.8,0.1,0.1

python scripts/validate_dataset.py --dataset data/production-v1
```

출처와 학습 권한을 확인하지 않은 데이터에는 `--training-allowed`를 사용하지
않는다. 동일 CAD에서 만든 여러 view는 같은 split에 있어야 한다.

원본 레코드에 사람이 검토한 `design_spec`과 `geometry_contract`가 있으면 이를
그대로 사용한다. 둘이 없으면 portable bootstrap label을 만들지만, 이는 설치와
초기 데이터 구축용이다. 생산 학습에 넣기 전 설비/CAD 엔지니어가 구성요소,
치수, 관계를 검토해야 한다.

## 6. 실제 데이터로 설정 변경

사용할 config를 복사한 뒤 `data.dataset_dir`만 실제 데이터 경로로 바꾼다.

```bash
cp configs/qwen3-vl-4b-qlora.json configs/company-4b-v1.json
```

초기 학습은 4B QLoRA 기준선을 먼저 고정한다. OOM이면 다음 순서로 줄인다.

1. `model.max_pixels`
2. `per_device_train_batch_size`
3. `data.max_images`
4. LoRA `r`

학습률, LoRA rank, image 수를 한 번에 모두 바꾸지 않는다.

## 7. 다중 GPU

```bash
GPU_COUNT=4 ./scripts/train.sh configs/company-8b-v1.json
```

서로 다른 VRAM GPU를 같은 DDP 작업에 섞지 않는 것을 권장한다.

## 8. 체크포인트와 재개

결과는 `outputs/<run>/`에 저장된다. config의
`resume_from_checkpoint: "auto"`가 최신 checkpoint를 자동 선택한다.

```bash
tensorboard --logdir outputs --host 0.0.0.0 --port 6006
```

## 9. 학습 후 평가

```bash
python scripts/evaluate_predictions.py \
  --dataset data/production-v1 \
  --predictions outputs/predictions-v1 \
  --split test \
  --dimension-tolerance-pct 5 \
  --target 0.95 \
  --min-cases-per-category 200 \
  --output outputs/holdout-report-v1.json
```

샘플 데이터의 높은 점수는 설치 확인일 뿐 95% 달성 증거가 아니다.
부품·모듈·설비별 독립 test 200건 이상과 Wilson 95% 하한을 사용한다.

## 10. 학습 모델 API 실행

```bash
docker compose --profile serve up -d --build verifier
curl http://127.0.0.1:8191/health
```

운영 서버에서는 `8191/tcp`를 인터넷에 공개하지 않고 Xconcep Worker IP만
허용한다. `.env`의 `VLM_API_KEY`는 충분히 긴 사내 전용 값으로 교체한다.

## 11. 보안·백업

- `.env`, `HF_TOKEN`, `VLM_API_KEY`를 Git/ZIP/Docker image에 넣지 않는다.
- `outputs/`, config, base model revision, dataset manifest를 한 release로 백업한다.
- 학습 GPU와 verifier를 동시에 실행하지 않는다.
- 모델이 출력한 Python/OpenSCAD 코드를 직접 실행하지 않는다.
- JSON schema 검증 후 기존 `build_geometry_contract()` 경로만 사용한다.

상세 조정값은 `docs/TRAINING_AND_TUNING_MANUAL_KO.md`, 전체 이식 절차는
`docs/MIGRATION_GUIDE_KO.md`를 참고한다.
