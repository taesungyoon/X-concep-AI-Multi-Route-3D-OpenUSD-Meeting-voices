# Xconcep CAD VLM 외부 GPU 서버 이식 가이드

## 1. 권장 구성

- 학습 서버: Ubuntu 22.04/24.04, NVIDIA GPU, 드라이버와 CUDA 호환 PyTorch
- 디스크: 최소 100GB 여유, 운영 데이터가 크면 300GB 이상
- 네트워크: Hugging Face 모델을 받을 수 있는 outbound HTTPS
- 운영 연결: 학습 서버의 검증 API `8191/tcp`는 Xconcep 워커가 있는 사내망에서만 접근 허용
- 비밀값: `HF_TOKEN`, `VLM_API_KEY`는 ZIP이나 Git에 넣지 않고 대상 서버의 `.env`에만 저장

## 2. 방법 A: 오프라인 ZIP 이식(권장)

Windows 원본 PC에서 다음 두 파일을 대상 서버로 복사한다.

- `xconcep-cad-vlm-portable.zip`
- `xconcep-cad-vlm-portable.zip.sha256`

대상 Linux 서버:

```bash
sha256sum -c xconcep-cad-vlm-portable.zip.sha256
unzip xconcep-cad-vlm-portable.zip
cd xconcep-cad-vlm
python3 scripts/verify_install.py
cp .env.example .env
./scripts/install-server.sh
python scripts/train_vlm.py --config configs/qwen3-vl-4b-qlora.json --dry-run
```

`bundle-manifest.json`은 압축 내부 파일별 크기와 SHA-256을 검증한다. 외부 ZIP 체크섬과 내부 manifest 검사를 모두 통과해야 설치한다.

## 3. 방법 B: Docker Compose 이식

NVIDIA Container Toolkit이 설치된 Linux 서버에서:

```bash
unzip xconcep-cad-vlm-portable.zip
cd xconcep-cad-vlm
cp .env.example .env
docker compose --profile training build trainer
docker compose run --rm trainer --config configs/qwen3-vl-4b-qlora.json --dry-run
docker compose run --rm trainer --config configs/qwen3-vl-8b-h100-lora.json
```

학습된 어댑터를 의미 검증 API로 실행한다.

```bash
docker compose --profile serve up -d --build verifier
curl http://127.0.0.1:8191/health
```

`.env` 예시:

```dotenv
VLM_MODEL=/workspace/outputs/qwen3-vl-8b-designspec
VLM_API_KEY=충분히-긴-사내전용-토큰
VLM_HOST_PORT=8191
VLM_LOAD_IN_4BIT=true
```

## 4. 방법 C: 학습 결과 어댑터만 운영 서버로 이동

학습 서버의 `outputs/<run-name>` 전체를 운영 GPU 서버의 동일 경로로 복사한다. `adapter_config.json`, adapter weight, processor/tokenizer 파일을 빠뜨리지 않는다. 운영 서버에는 이 패키지와 모델 캐시가 있어야 한다.

```bash
rsync -av --checksum outputs/qwen3-vl-8b-designspec/ gpu-runtime:/srv/xconcep-cad-vlm/outputs/qwen3-vl-8b-designspec/
```

복사 후 운영 서버에서 verifier만 기동한다. 모델이 Hugging Face private repo라면 `VLM_MODEL=company/model-repo`와 읽기 권한 `HF_TOKEN`을 설정해도 된다.

## 5. 기존 Xconcep 워커 연결

`전체 풀스택/.env`에 다음을 설정하고 워커를 재기동한다.

```dotenv
IMAGE_SEMANTIC_VERIFIER_URL=http://GPU-SERVER-IP:8191
IMAGE_SEMANTIC_VERIFIER_API_KEY=VLM_API_KEY와-동일한-값
IMAGE_SEMANTIC_VERIFIER_TIMEOUT_SECONDS=120
```

이 연결이 활성화되면 로컬 ComfyUI/FLUX가 만든 정밀 후보를 VLM이 검사한다. 부품 수량·공간 관계가 실패하면 동일 seed의 대안 경로와 비교하고, 검증된 후보를 우선 선택한다.

## 6. 방화벽과 운영 안전

- `8191/tcp`를 인터넷 전체에 공개하지 않는다.
- Xconcep 워커 IP만 allowlist에 등록한다.
- TLS가 필요한 네트워크에서는 Nginx/사내 API Gateway 뒤에 배치한다.
- `VLM_API_KEY`를 로그, manifest, 데이터셋, Docker image에 포함하지 않는다.
- 한 GPU에서 학습과 verifier를 동시에 실행하지 않는다. 학습이 끝난 후 verifier 프로필로 전환한다.

## 7. 승격 순서

1. `scripts/validate_dataset.py` 통과
2. `train_vlm.py --dry-run` 통과
3. 실제 학습과 최적 checkpoint 선택
4. 독립 test split 예측 생성
5. `evaluate_predictions.py`로 범주별 최소 200건과 Wilson 95% 하한 확인
6. `/verify` API 스모크 테스트
7. FLUX→VLM 검증→파라메트릭 3D→Blender→OpenUSD E2E 재실행
8. 이전 운영 모델보다 낮아지면 승격하지 않고 rollback

## 8. 되돌리기

`VLM_MODEL`을 직전 승인 어댑터 경로로 바꾸고 verifier를 재시작한다.

```bash
docker compose --profile serve up -d --force-recreate verifier
```

긴급 시 Xconcep 워커의 `IMAGE_SEMANTIC_VERIFIER_URL`을 비우면 기존 로컬 FLUX 경로로 즉시 복귀한다.
