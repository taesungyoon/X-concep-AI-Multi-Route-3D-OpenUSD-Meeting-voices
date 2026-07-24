# Xconcep CAD VLM 학습·조정·서버 이식 매뉴얼

실제 서버 복사와 verifier 연결 명령은 `MIGRATION_GUIDE_KO.md`를 함께 참조한다.

## 1. 목표와 책임 경계

이 패키지의 1차 목표는 다중 시점 이미지와 사용자 요구문을 입력받아 현재 Xconcep 스키마의 `DesignSpec JSON`을 재현하는 것이다. 모델이 STEP이나 OpenSCAD/Python 코드를 바로 생성하고 실행하는 구조가 아니다.

운영 흐름은 다음과 같다.

```text
정면·상면·우측면 이미지 + 요구문
  → Qwen3-VL LoRA/QLoRA
  → DesignSpec JSON
  → JSON 스키마·허용값 검증
  → 기존 build_geometry_contract()
  → OpenSCAD/CadQuery/Blender/OpenUSD
  → 제조성·외관 독립 평가기
```

이 경계를 지키면 생성 모델이 잘못된 코드를 출력해도 운영 서버에서 임의 코드가 실행되지 않는다. `geometry_contract` 직접 학습도 설정상 가능하지만 기본 운영 모드는 `design_spec`이다.

## 2. 서버 권장 사양

| 목적 | GPU | 시스템 RAM | 여유 디스크 | 설정 |
|---|---:|---:|---:|---|
| 코드·데이터 확인 | CUDA GPU 불필요 | 16GB | 10GB | `--dry-run` |
| 4B QLoRA 개발 | VRAM 24GB 이상 | 64GB | 150GB | `qwen3-vl-4b-qlora.json` |
| 8B QLoRA 운영 실험 | VRAM 48GB 이상 | 128GB | 250GB | `qwen3-vl-8b-qlora.json` |
| 8B BF16 LoRA | H100/A100 80GB급 | 128GB 이상 | 300GB | `qwen3-vl-8b-h100-lora.json` |
| 2~4 GPU | 동일 GPU 권장 | 256GB | 500GB 이상 | `accelerate launch` |

서로 다른 VRAM의 GPU를 하나의 DDP 작업에 섞으면 가장 작은 GPU가 병목이 된다. 데이터 렌더링 GPU와 학습 GPU를 분리하는 편이 안정적이다.

## 3. 서버 이식

원본 PC에서 다음을 실행한다.

```bash
python scripts/export_bundle.py
```

`dist/xconcep-cad-vlm-portable.zip`과 SHA-256 파일을 대상 서버에 복사한다. Linux에서 확인한다.

```bash
sha256sum -c xconcep-cad-vlm-portable.zip.sha256
unzip xconcep-cad-vlm-portable.zip
cd xconcep-cad-vlm
```

모델 가중치와 `.env`, 학습 결과, Hub 캐시는 ZIP에 포함되지 않는다.

## 4. 설치 방법

### 4.1 Ubuntu 직접 설치

NVIDIA 드라이버와 `nvidia-smi`가 먼저 작동해야 한다.

```bash
chmod +x scripts/*.sh
./scripts/install-server.sh
source .venv/bin/activate
```

서버 CUDA에 맞는 PyTorch 인덱스가 다르면 설치 전 지정한다.

```bash
export PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu128
./scripts/install-server.sh
```

설치 후 `environment.freeze.txt`를 보관한다. 재현 실패 시 이 파일과 GPU 드라이버 버전을 함께 비교한다.

### 4.2 Docker

```bash
cp .env.example .env
docker compose build
docker compose run --rm trainer --config configs/qwen3-vl-4b-qlora.json --dry-run
```

Docker에서 GPU가 보이지 않으면 NVIDIA Container Toolkit 설치와 `docker run --gpus all` 동작을 먼저 확인한다.

### 4.3 Windows

CUDA 학습 라이브러리는 Linux가 더 안정적이다. Windows가 필수라면 WSL2 Ubuntu를 권장한다. 네이티브 Windows는 다음 스크립트를 제공하지만, Unsloth/CUDA 조합에 따라 WSL2가 필요할 수 있다.

```powershell
.\scripts\install-server.ps1
```

## 5. 데이터 레코드 구조

`data/<name>/records.jsonl`의 한 줄이 하나의 독립 설계다.

```json
{
  "schema_version": "xconcep.cad-vlm-sample/1.0",
  "id": "equipment_conveyor_inspection_001",
  "category": "equipment",
  "split": "train",
  "prompt": "폭 1600mm ...",
  "images": ["images/..._front.png", "images/..._top.png", "images/..._right.png"],
  "design_spec": {},
  "geometry_contract": {},
  "provenance": {
    "license": "LicenseRef-Xconcep-Internal-Generated",
    "training_allowed": true
  }
}
```

동일 CAD에서 렌더한 다른 뷰나 재질 변형은 반드시 같은 split에 있어야 한다. 이미지 단위 랜덤 분할은 평가 누수를 만든다. 설계 ID 또는 생성기 계보 단위로 `train/eval/test`를 분리한다.

검증 명령:

```bash
python scripts/validate_dataset.py --dataset data/examples
```

검증기는 이미지 존재·디코딩, 상대 경로 탈출, 중복 ID, 계약 해시, 카테고리/모드 일치, 학습 허용 라이선스, 프롬프트 해시의 split 중복을 검사한다.

## 6. 현재 샘플 생성

전체 저장소 안에서 실행하면 현재 `python-worker`의 실제 생성기를 호출한다.

```bash
python scripts/build_sample_dataset.py --output data/examples
```

생성 결과는 9개 설계, 27개 PNG다. 이 데이터는 배선·학습 형식 검증용이며 성능 학습용이 아니다. 생산 데이터는 다음 순서로 확장한다.

1. 부품·모듈·설비별 사람이 검토한 파라메트릭 템플릿을 늘린다.
2. 한 템플릿의 치수·수량·배치 범위를 공학적 허용 범위 안에서 샘플링한다.
3. Blender에서 카메라·조명·재질·배경을 변화시키되 치수 정답은 고정한다.
4. 각 설계의 정면·상면·우측면과 실제 촬영에 가까운 사시도를 함께 만든다.
5. 생성 실패, 비수밀, 치수 위반 데이터는 학습 전에 제거한다.
6. 실제 사진·도면은 권리와 출처를 확인하고 별도 홀드아웃으로 우선 사용한다.

초기 권장량은 카테고리별 3천~1만 설계다. 각 설계의 단순 렌더 변형 수를 늘리는 것보다 독립된 구조와 파라미터 조합을 늘리는 것이 중요하다.

## 7. 학습 방법

### 7.1 1단계: 출력 형식 적응

비전 인코더를 고정하고 언어·attention·MLP LoRA만 학습하는 빠른 실험이다. JSON 유효율과 필드 재현성을 먼저 확인한다.

```json
"finetune_vision_layers": false
```

### 7.2 2단계: 산업 형상 적응

비전 레이어도 학습한다. 합성 CAD 이미지와 실제 사진의 외관 차이를 줄이는 단계다. 기본 프로파일은 이 모드다. VRAM 사용량과 과적합 위험이 증가한다.

### 7.3 3단계: 사내 도메인 보정

사내 권리 보유 이미지와 엔지니어 수정 이력만 사용한다. 실패한 예측을 정답으로 다시 학습하지 말고, 사람이 승인한 수정본 또는 결정론적 검증을 통과한 레코드만 추가한다.

### 7.4 실행

GPU를 쓰기 전:

```bash
python scripts/train_vlm.py --config configs/qwen3-vl-4b-qlora.json --dry-run
```

단일 GPU:

```bash
./scripts/train.sh configs/qwen3-vl-4b-qlora.json
```

4 GPU:

```bash
GPU_COUNT=4 ./scripts/train.sh configs/qwen3-vl-8b-qlora.json
```

## 8. 조정값 상세 설명

### 모델·이미지

| 값 | 기본 | 의미와 조정 기준 |
|---|---:|---|
| `base_model` | Qwen3-VL 4B | 4B로 파이프라인을 확정한 뒤 8B와 동일 홀드아웃 비교 |
| `load_in_4bit` | `true` | QLoRA. VRAM을 크게 줄인다. H100 80GB에서는 `false` LoRA 비교 가능 |
| `finetune_vision_layers` | `true` | 실제 설비 외관 적응에 유리. OOM/과적합 시 먼저 `false` 비교 |
| `finetune_language_layers` | `true` | JSON과 설비 용어 학습에 필요 |
| `finetune_attention_modules` | `true` | 이미지-필드 대응 학습. 끄면 메모리는 줄지만 위치·수량 인식 저하 가능 |
| `finetune_mlp_modules` | `true` | 도메인 표현력 증가. 작은 데이터에서는 과적합 감시 |
| `max_pixels` | `null` | processor 기본값. OOM이면 이미지 수를 줄인 다음 해상도를 단계적으로 제한 |

### 데이터

| 값 | 기본 | 설명 |
|---|---:|---|
| `target_type` | `design_spec` | 운영 기본. `geometry_contract`는 연구 비교용 |
| `max_images` | 3 | 정면·상면·우측면. OOM이면 2로 낮출 수 있으나 깊이 모호성 증가 |
| `limit_train/eval` | `null` | 20~100건 smoke test에서만 제한. 본 학습에서는 해제 |

### 최적화

| 값 | 기본 | 권장 조정 |
|---|---:|---|
| `per_device_train_batch_size` | 1 | OOM 시 항상 1 유지. VRAM이 충분할 때만 2 이상 |
| `gradient_accumulation_steps` | 32 | 유효 배치 = GPU당 배치 × 누적 × GPU 수. 보통 16~64 목표 |
| `learning_rate` | 4B `8e-5`, 8B `5e-5` | loss 진동·JSON 붕괴 시 절반. 학습 정체 시 데이터 확인 후 20~30% 증가 |
| `num_train_epochs` | 2 | 작은 데이터는 1~3. 평가 손실이 악화되면 즉시 줄임 |
| `max_steps` | `null` | 빠른 배선 시험은 10~100으로 설정. 값이 있으면 epoch보다 우선 |
| `warmup_ratio` | 0.03 | 초기 발산 시 0.05~0.1. 큰 데이터에서는 0.01~0.03 |
| `weight_decay` | 0.01 | 과적합 완화. LoRA에서는 0~0.05 범위 |
| `max_grad_norm` | 1.0 | gradient 폭주 방지. 불안정하면 0.5, 지나치게 느리면 원인 확인 후 1.0 유지 |
| `lr_scheduler_type` | cosine | 긴 학습에 안정적. 매우 짧은 smoke는 linear도 가능 |
| `optim` | adamw_8bit | QLoRA 메모리 절약. H100 BF16은 `adamw_torch_fused` |
| `bf16` | `true` | Ampere 이후 권장. 미지원 GPU는 `false`, `fp16=true` |

### LoRA

| 값 | 기본 | 설명 |
|---|---:|---|
| `r` | 32 | 16은 가볍고 32는 기본, 64는 복잡한 설비/대형 데이터. 높을수록 VRAM·과적합 증가 |
| `alpha` | 64 | 보통 `r` 또는 `2r`. 너무 크면 업데이트가 불안정해질 수 있음 |
| `dropout` | 0 | Unsloth 최적화 경로. 과적합은 먼저 데이터·epoch·rank로 해결 |
| `use_rslora` | `false` | r=64 이상에서 안정화 비교. 작은 rank에는 필수 아님 |

### 저장·평가

| 값 | 기본 | 설명 |
|---|---:|---|
| `logging_steps` | 10 | loss와 처리량 기록 간격 |
| `eval_steps` | 100 | 평가가 너무 비싸면 200~500. 초기 시험은 20~50 |
| `save_steps` | 100 | 서버 선점/중단 가능성이 높으면 더 짧게 |
| `save_total_limit` | 3 | 최근 체크포인트 수. 최종 adapter는 별도 저장 |
| `resume_from_checkpoint` | `auto` | 출력 폴더의 가장 최신 `checkpoint-*` 자동 재개 |

## 9. 증상별 조정 순서

| 증상 | 먼저 할 일 | 다음 조정 | 피해야 할 것 |
|---|---|---|---|
| CUDA OOM | 배치 1 확인, `max_images` 3→2 | `finetune_vision_layers=false`, 4bit 사용 | 무조건 gradient accumulation 감소 |
| loss가 NaN/급등 | 학습률 50% 감소 | warmup 0.05, grad norm 0.5 | 불량 JSON 데이터를 둔 채 epoch 증가 |
| JSON 문법 실패 | 정답 JSON 정규화·중복 제거 | 형식 전용 1단계 SFT, 학습률 감소 | 후처리 정규식만으로 성공 처리 |
| 부품을 임의 추가 | “없는 부품” 음성 예시 추가 | 요구사항 grounding 샘플 확대 | 모델 출력 코드를 바로 실행 |
| 치수 단위 오류 | 모든 정답 mm 확인 | cm/m 입력 예시와 mm 정답 추가 | 단위가 다른 데이터를 혼합 |
| 수량이 자주 틀림 | 동일 부품 1~8개 균형 데이터 | attention/vision layer 학습 | 렌더 복제만 늘리기 |
| train은 좋고 eval 악화 | 계보 단위 split 재검사 | epoch/rank 감소, 독립 설계 추가 | 같은 CAD 다른 뷰를 eval에 배치 |
| 양쪽 모두 정체 | 정답 스키마와 프롬프트 확인 | rank 32→64 또는 8B 비교 | 검증 없이 모델 크기만 확대 |
| 합성은 좋고 실사진 낮음 | 배경·조명·재질 domain randomization | 권리 보유 실사진 소량 SFT | 인터넷 이미지 무단 수집 |
| 학습이 너무 느림 | BF16·Flash Attention·GPU 사용률 확인 | 이미지 해상도/평가 주기 조절 | 체크포인트를 완전히 끄기 |

한 번에 하나의 변수만 바꾸고 `run_name`을 다르게 기록한다. 모델 크기, 데이터 버전, seed, GPU 수, 유효 배치, commit hash를 결과에 같이 남긴다.

## 10. 체크포인트와 외부 저장

기본은 로컬 저장이다. `outputs/<run>/checkpoint-*`와 `adapter/`가 생성된다. `resume_from_checkpoint=auto`이면 최신 체크포인트를 사용한다.

Hub를 사용할 때만 다음을 변경한다.

```json
"hub": {
  "enabled": true,
  "repo_id": "company/xconcep-cad-vlm-private",
  "private": true,
  "push_checkpoints": true
}
```

그리고 환경 변수 `HF_TOKEN`을 설정한다. 토큰을 JSON, Git, Docker 이미지에 넣지 않는다. 사내 정책상 외부 업로드가 금지되면 `enabled=false`를 유지하고 NAS/object storage로 `outputs`를 백업한다.

## 11. 모니터링

TensorBoard는 항상 로컬 기록으로 사용할 수 있다.

```bash
tensorboard --logdir outputs --host 0.0.0.0 --port 6006
```

Trackio는 `report_to`에 포함되어 있다. 원격 Space를 쓸 때만 `TRACKIO_SPACE_ID=조직/space`를 설정한다. 외부 전송이 허용되지 않으면 config의 `report_to`를 `["tensorboard"]`로 바꾼다.

관찰할 값은 train/eval loss, learning rate, gradient norm, tokens/sec, GPU 사용률이다. loss 하나만으로 제조 적중률을 판단하지 않는다.

## 12. 추론과 기존 파이프라인 연결

```bash
python scripts/infer_vlm.py \
  --model outputs/qwen3-vl-4b-designspec/adapter \
  --image front.png --image top.png --image right.png \
  --prompt "폭 1600mm ..." \
  --output prediction.json
```

추론 결과는 다음 순서로 처리한다.

1. JSON 파싱과 필수 필드 검증
2. 허용된 category, component kind, feature kind만 통과
3. 치수 범위·단위·수량 상한 검증
4. 기존 `build_geometry_contract()` 호출
5. 네이티브 CAD 생성과 독립 평가
6. 실패 시 사람이 확인하거나 제한된 재생성만 수행

## 13. 95% 목표 검증

95%는 학습 loss나 평균 유사도가 아니다. 부품·모듈·설비 각각 최소 200개의 완전 독립 홀드아웃에서 아래 조건을 모두 통과한 비율로 정의한다.

- 출력 JSON 유효성
- 필수 구성요소 recall과 수량 일치
- 치수 허용오차 이내
- 관계·배치 계약 통과
- GeometryContract/네이티브 생성 성공
- 수밀·양의 체적·비퇴화 면
- 독립 외관 평가 목표 통과

기존 `score_holdout()`의 Wilson 95% 하한이 카테고리별 0.95 이상일 때만 목표 달성으로 표시한다. 자동 평가는 제조 승인 자체가 아니며, 안전 설비와 실제 가공은 엔지니어 승인이 필요하다.

VLM 자체의 홀드아웃 평가는 다음 명령으로 실행한다. `predictions`는 `<설계 ID>.json` 파일이 들어 있는 폴더 또는 `id`와 `prediction`을 가진 JSONL이다.

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

평가기의 `passed`는 다음 조건의 논리곱이다.

| 검사 | 통과 기준 |
|---|---|
| JSON·스키마 | JSON object, category 일치, 단위 `mm` |
| 구성요소 | 필수 kind recall 100%, 요구 수량 일치 |
| 가공 특징 | 필수 hole/rib/slot recall 100%, 수량 일치 |
| 치수 | 정답에 존재하는 모든 치수가 설정 허용오차 이내 |
| 관계 | 필수 subject-relation-object recall 100% |

`observed_rate`가 1.0이어도 사례 수가 작으면 `target_achieved=false`가 정상이다. 예를 들어 포함된 eval 3건은 코드 배선 확인용일 뿐, 통계적 95% 증거가 아니다. 각 카테고리 200건에서 200건을 전부 성공해도 Wilson 95% 하한은 약 98% 수준이며, 실패가 누적되면 하한이 빠르게 낮아진다.

모델 평가가 끝난 뒤에는 예측 DesignSpec을 기존 `build_geometry_contract()`에 넣어 OpenSCAD/Blender/OpenUSD E2E와 제조성 평가까지 다시 통과시킨다. VLM 평가만 통과한 체크포인트를 운영으로 승격하지 않는다.

## 14. 데이터 권리와 보안

- `schema/license_allowlist.json`에 없는 데이터는 학습 금지다.
- Fusion 360 Gallery와 CC BY-NC 자료는 운영 모델 학습에 넣지 않는다.
- CADEvolve를 쓸 경우 우선 `CADEvolve-*-core`의 출처와 실제 파일별 라이선스를 다시 기록한다.
- ABC/ShapeNet 파생 폴더는 별도 권리 승인 전 제외한다.
- 모든 외부 데이터에는 URL, 버전/commit, 다운로드 날짜, 파일 해시, 라이선스 원문, 수정 내역을 남긴다.
- 생성 모델 출력은 샌드박스 없는 Python에서 실행하지 않는다.

## 15. 최종 운영 체크리스트

1. `scripts/check_server.py`에서 CUDA/BF16/디스크 확인
2. `validate_dataset.py` 통과
3. 10~50 step smoke run과 checkpoint 재개 확인
4. 작은 4B 기준선 고정
5. 한 변수씩 조정하고 Trackio/TensorBoard 기록
6. 독립 홀드아웃 평가
7. 8B가 비용 대비 실제 지표를 개선할 때만 승격
8. adapter·base model revision·config·환경 freeze·데이터 manifest를 한 릴리스로 보관
9. 기존 자가평가기와 E2E를 통과한 모델만 staging 배포
10. 엔지니어 승인 없이 제조 가능 등급을 부여하지 않음
