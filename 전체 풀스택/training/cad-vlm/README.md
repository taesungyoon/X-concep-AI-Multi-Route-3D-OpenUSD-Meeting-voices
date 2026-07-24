# Xconcep CAD VLM 학습 패키지

외부 서버 복사, Docker/가상환경 설치, 학습 결과 어댑터만 이동하는 세 가지 절차는
[`docs/MIGRATION_GUIDE_KO.md`](docs/MIGRATION_GUIDE_KO.md)에 정리되어 있다.

다중 시점 설비·모듈·부품 이미지에서 현재 프로젝트의 `DesignSpec JSON`을 생성하도록 Qwen3-VL을 LoRA/QLoRA로 미세조정하는 독립 패키지다. 모델은 임의 Python/CAD 코드를 직접 실행하지 않으며, 추론 결과는 기존 Xconcep 결정론적 `GeometryContract` 생성기로 전달한다.

## 포함 내용

- Qwen3-VL 4B/8B Unsloth QLoRA 학습 코드
- H100급 서버용 8B BF16 LoRA 설정
- 현재 파라메트릭 생성기 기반 부품·모듈·설비 예시 데이터 생성기
- 라이선스·계약·이미지 해시·split 누수·요구사항 커버리지 검증기
- JSON·수량·치수·관계와 Wilson 95% 하한을 계산하는 독립 홀드아웃 평가기
- 체크포인트 자동 재개, TensorBoard·Trackio 기록, 선택적 비공개 Hub 저장
- Ubuntu/Windows 설치 스크립트, Docker Compose, 이식용 ZIP 생성기
- 상세 조정값과 운영 절차: `docs/TRAINING_AND_TUNING_MANUAL_KO.md`

## 가장 짧은 실행 순서

```bash
cd xconcep-cad-vlm
python3 scripts/build_sample_dataset.py
./scripts/install-server.sh
python scripts/train_vlm.py --config configs/qwen3-vl-4b-qlora.json --dry-run
./scripts/train.sh configs/qwen3-vl-4b-qlora.json
```

학습 후 승격 평가:

```bash
python scripts/evaluate_predictions.py \
  --dataset data/production-v1 \
  --predictions outputs/predictions-v1 \
  --split test \
  --output outputs/holdout-report-v1.json
```

평가기 배선만 확인하려면 포함된 골드 예시를 사용한다. 3건의 관측 통과율이 100%여도 표본 수가 부족하므로 95% 목표 달성으로 표시되지 않는 것이 정상이다.

```bash
python scripts/evaluate_predictions.py \
  --dataset data/examples \
  --predictions data/examples/gold_eval_predictions.example.jsonl \
  --split eval \
  --output outputs/evaluation-smoke.json
```

Docker를 사용할 경우:

```bash
cp .env.example .env
docker compose build
docker compose run --rm trainer --config configs/qwen3-vl-4b-qlora.json --dry-run
docker compose run --rm trainer
```

학습 어댑터를 로컬 FLUX 의미 검증 API로 제공:

```bash
cp .env.example .env
docker compose --profile serve up -d --build verifier
curl http://127.0.0.1:8191/health
```

예시 데이터 9건은 경로와 스키마 검증용이다. 실제 학습에는 부품·모듈·설비별 최소 수천 건의 독립 설계와 실제 이미지 홀드아웃이 필요하다.

## 주요 경로

- `configs/`: GPU 등급별 설정
- `data/examples/`: 9개 설계 × 3면 이미지, 정답 JSON, 평가 입력 예시
- `scripts/train_vlm.py`: 학습 진입점
- `scripts/infer_vlm.py`: 어댑터 추론
- `scripts/export_bundle.py`: 서버 이식용 압축 파일 생성
- `schema/license_allowlist.json`: 운영 학습 허용 라이선스

## 외부 원본 데이터 전처리

`scripts/preprocess_dataset.py`는 원본 JSONL과 이미지 폴더를 현재 학습 스키마로 변환한다. 출력 경로는 비어 있어야 하며, 동일 프롬프트 또는 동일 이미지가 서로 다른 train/eval/test split으로 누수되지 않게 그룹 단위로 분할한다.

```bash
python scripts/preprocess_dataset.py \
  --input data/raw/records.jsonl \
  --output data/production-v1 \
  --max-image-side 2048 \
  --min-images 1
```

각 원본 레코드는 `id`, `category`, `prompt`, `images`, `provenance.license`, `provenance.training_allowed=true`을 가져야 한다. `design_spec`과 `geometry_contract`가 없으면 현재 파라메트릭 생성기로 결정론적으로 만든다. 생성 후 `records.jsonl`, PNG 정규화 이미지, 해시, split, 라이선스 사본, `preprocessing_report.json`이 만들어지며 전체 데이터셋 검증을 통과해야 완료된다.

이식 파일 생성:

```bash
python scripts/export_bundle.py
```

생성된 ZIP과 `.sha256` 파일을 대상 서버로 복사한 뒤 체크섬을 확인하고 압축을 해제한다.

## 검증된 호환 기준

- 공식 Qwen3-VL 4B/8B Instruct 모델 ID
- 공식 Unsloth Qwen3-VL 예제 계열과 맞춘 `transformers 4.57.x` / `trl 0.22.2`
- VLM 토큰 절단을 막는 `max_length=None`, 이미지 컬럼 보존, 체크포인트 자동 재개
- Hub 저장을 켤 때만 `HF_TOKEN`을 명시적으로 Trainer에 주입하며 기본은 사내 로컬 저장
