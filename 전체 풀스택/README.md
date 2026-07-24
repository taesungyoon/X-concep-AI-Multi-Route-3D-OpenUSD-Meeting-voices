# X concep AI Multi-Route 3D · Meeting · OpenUSD Final Full Stack

로컬 ComfyUI/FLUX 2D 생성과 TripoSR 이미지 기반 3D, OpenSCAD 구조 생성, Blender 고품질 자산 처리, 회의 음성 분석, Design State, 자동 Router·Fallback, 검증 등급 및 OpenUSD·Omniverse를 통합한 기준 코드임. OpenAI Image API는 선택 모드이며 기존 `hunyuan3d` 라우트 키는 API 호환 별칭으로만 유지함.

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

- UI: `http://localhost:8080`
- 통합 상태: `http://localhost:8080/api/system-status`
- Smoke Test: `./scripts/smoke-test.sh`

## 사용자 결과 선택

- 자동 추천임
- 빠른 3D임
- 구조 중심 3D임
- 고품질 3D임
- 동작·OpenUSD임

세부 설치·운영·검증 기준은 `docs/MANUAL_MULTIROUTE_FINAL_KO.md`를 확인함.

로컬 우선 구현·실제 연결 상태·자동 테스트 기준은 `docs/LOCAL_FIRST_IMPLEMENTATION_KO.md`를 확인함.

Blender/OpenSCAD 네이티브 설치, strict native 운영, 25건 acceptance 벤치마크, 실제 API 스모크 절차는 `docs/NATIVE_CAD_VALIDATION_KO.md`를 확인함.

외부 사내 MySQL 인증, ComfyUI/OpenAI 이미지 모드, `.env` 입력 항목과 실제 연결 승인 경계는 `docs/EXTERNAL_INTEGRATIONS_KO.md`를 확인함.

현재 기본인 내부 MySQL 인증 테스트와 추후 외부 DB 전환 절차는 `docs/INTERNAL_MYSQL_TEST_KO.md`를 확인함.

## 서버 이식·설치·실행

권장 운영 구조는 다음과 같다.

- 앱 서버: PHP Web, Control Plane, Worker, Celery, MySQL, Redis, Qdrant
- GPU 서비스: ComfyUI/FLUX `8188/tcp`, TripoSR `8081/tcp`
- 선택 학습 서버: CAD VLM 파인튜닝과 검증 API `8191/tcp`
- `8081`, `8188`, `8191`, MySQL 포트는 인터넷에 공개하지 않고 앱 서버만 접근하게 제한함

처음에는 한 NVIDIA 서버에 모두 설치할 수 있다. 운영 부하가 커지면 학습 서버와
추론 서버를 분리한다. 학습과 검증 API를 같은 GPU에서 동시에 실행하지 않는다.

### 1. 현재 PC에서 전달본 만들기

저장소 루트의 Windows PowerShell에서 실행한다.

```powershell
tar -czf xconcep-fullstack.tar.gz `
  --exclude="./.env" `
  --exclude="./storage/*" `
  --exclude="./training/cad-vlm/outputs/*" `
  --exclude="./training/cad-vlm/hf-cache/*" `
  -C ".\전체 풀스택" .

scp .\xconcep-fullstack.tar.gz USER@SERVER_IP:/tmp/
```

`.env`에는 비밀번호와 API Key가 있으므로 일반 배포 압축에 넣지 않는다.
기존 프로젝트 결과까지 이전할 때만 `storage/`를 별도로 `rsync` 또는 `scp`로
전송한다. 기존 MySQL 데이터는 실행 중인 volume을 복사하지 말고 `mysqldump`로
백업·복원한다.

Git 서버를 사용할 수 있으면 압축 대신 private 저장소를 clone해도 된다. 모델
weight, `.env`, `storage/`, 학습 결과는 Git에 넣지 않는다.

### 2. 대상 Ubuntu 서버 준비

권장 기준:

- Ubuntu 22.04 또는 24.04
- Docker Engine과 Docker Compose v2
- NVIDIA Driver와 NVIDIA Container Toolkit
- RAM 64GB 이상, 여유 디스크 150GB 이상
- 4B QLoRA는 VRAM 24GB 이상, 8B는 48GB 이상

설치 상태를 먼저 확인한다.

```bash
nvidia-smi
docker version
docker compose version
```

전달본을 해제한다.

```bash
sudo mkdir -p /srv/xconcep
sudo chown "$USER":"$USER" /srv/xconcep
tar -xzf /tmp/xconcep-fullstack.tar.gz -C /srv/xconcep
cd /srv/xconcep

cp .env.example .env
chmod 600 .env
```

### 3. 운영 `.env` 설정

다음은 내부 MySQL 인증, 로컬 ComfyUI, TripoSR, Faster-Whisper,
OpenSCAD·Blender·OpenUSD를 사용하는 최소 live 설정이다.

```dotenv
WEB_PORT=8080
DJANGO_SECRET_KEY=충분히-긴-랜덤값
DJANGO_DEBUG=false

DB_ENGINE=mysql
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=xconcep
MYSQL_USER=xconcep
MYSQL_PASSWORD=충분히-긴-DB-비밀번호
MYSQL_ROOT_PASSWORD=충분히-긴-root-비밀번호

AUTH_MODE=internal_db
INTERNAL_AUTH_BOOTSTRAP_ENABLED=true
INTERNAL_AUTH_USERNAME=internal_admin
INTERNAL_AUTH_PASSWORD=충분히-긴-로그인-비밀번호

PIPELINE_MODE=live
LLM_MODE=rules

OPENAI_IMAGE_MODE=comfyui
COMFYUI_BASE_URL=http://host.docker.internal:8188
COMFYUI_UNET_MODEL=flux-2-klein-base-4b-fp8.safetensors
COMFYUI_CLIP_MODEL=qwen_3_4b.safetensors
COMFYUI_VAE_MODEL=flux2-vae.safetensors

SHAPE_MODE=triposr
SHAPE_PROVIDER=triposr
SHAPE_API_URL=http://host.docker.internal:8081

INSTALL_SPEECH=true
SPEECH_MODE=faster_whisper
WHISPER_MODEL=small

INSTALL_OPENSCAD=true
OPENSCAD_MODE=auto
INSTALL_BLENDER=true
BLENDER_MODE=auto

OPENUSD_GENERATE_USDC=true
```

비밀값은 다음 명령으로 각각 생성할 수 있다.

```bash
openssl rand -hex 32
```

OpenAI Image는 추가 모드다. 기본 ComfyUI 경로가 검증된 뒤 필요한 환경에서만
아래 값을 설정하고 Worker를 재기동한다.

```dotenv
OPENAI_IMAGE_MODE=openai
OPENAI_API_KEY=서버의-비밀저장소에서-주입
OPENAI_IMAGE_MODEL=gpt-image-2
```

### 4. GPU Provider 준비

메인 Docker stack을 시작하기 전에 GPU 서버에서 다음 endpoint가 응답해야 한다.

```bash
curl -fsS http://127.0.0.1:8188/system_stats
curl -fsS http://127.0.0.1:8081/health
```

필요한 기본 모델:

```text
ComfyUI diffusion model  flux-2-klein-base-4b-fp8.safetensors
ComfyUI text encoder     qwen_3_4b.safetensors
ComfyUI VAE              flux2-vae.safetensors
Image-to-3D              stabilityai/TripoSR
Speech                   faster-whisper small
```

모델 weight는 저장소와 배포 ZIP에 포함하지 않는다. Docker container에서 Linux
호스트의 Provider에 접근할 때는 Compose에 포함된
`host.docker.internal:host-gateway` 경로를 사용한다. Provider가 별도 서버에
있으면 `COMFYUI_BASE_URL`과 `SHAPE_API_URL`을 해당 사내 IP로 변경한다.

### 5. 전체 서비스 빌드와 실행

비동기 Celery Worker까지 포함해 시작한다.

```bash
cd /srv/xconcep
docker compose --profile async up -d --build
docker compose ps
```

로그:

```bash
docker compose logs -f --tail=200
```

재시작:

```bash
docker compose --profile async restart
```

종료:

```bash
docker compose --profile async down
```

MySQL·Redis·Qdrant 데이터를 유지하려면 `docker compose down -v`를 사용하지
않는다.

### 6. 설치 후 검증

```bash
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8080/api/system-status | jq
```

live 준비 완료 기준:

```json
{
  "status": "ok",
  "pipeline_mode": "live",
  "execution_profile": "live",
  "runtime_ready": true
}
```

`runtime_ready=false`이면 `image.connected`, `image_to_3d.connected`,
`speech.connected`, `authentication.database_connected`를 먼저 확인한다.

UI는 `http://SERVER_IP:8080`으로 접속한다. 내부 인증이 활성화된 환경에서는
로그인 후 다음 순서로 한 건을 검증한다.

1. 직접 입력으로 2D 콘셉트 4안 생성
2. 콘셉트 선택 후 TripoSR GLB 생성
3. 구조 중심 경로로 OpenSCAD GLB·STL·SCAD 생성
4. 고품질 경로로 Blender GLB·BLEND·재질 manifest 생성
5. USDA·USDC·layered `root.usda` 다운로드
6. 회의 음성 업로드 후 STT·요구사항·치수·3D 결과 확인

인증을 사용하는 실제 smoke는 Windows/PowerShell 환경에서 다음 스크립트를
사용한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-live.ps1 `
  -BaseUrl http://SERVER_IP:8080

powershell -ExecutionPolicy Bypass -File .\scripts\smoke-meeting-live.ps1 `
  -BaseUrl http://SERVER_IP:8080 `
  -FixtureDir .\storage\e2e-audio\korean-industrial-meeting-edge

powershell -ExecutionPolicy Bypass -File .\scripts\smoke-native-cad.ps1 `
  -BaseUrl http://SERVER_IP:8080
```

`scripts/smoke-test.sh`은 인증을 끈 Mock 환경용이다.

### 7. 기존 데이터 이전

생성 파일:

```bash
rsync -av --checksum OLD_SERVER:/srv/xconcep/storage/ /srv/xconcep/storage/
```

MySQL 백업:

```bash
docker compose exec -T mysql sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  > xconcep.sql
```

복원:

```bash
docker compose exec -T mysql sh -c \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  < xconcep.sql
```

실제 명령에서는 비밀번호를 shell history나 CI 로그에 직접 남기지 말고 Docker
secret 또는 서버 비밀 저장소를 사용한다. 복원 후 프로젝트 수와 결과 파일 수를
비교하고 smoke E2E를 다시 실행한다.

### 8. 업데이트와 롤백

업데이트 전에 `.env`, MySQL dump, `storage/`를 백업한다.

```bash
docker compose --profile async up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8080/api/system-status | jq
```

문제가 생기면 직전 소스 release로 되돌리고 동일한 `.env`와 volume을 사용해
다시 빌드한다. DB migration이 포함된 release는 먼저 staging 복원 시험을 한다.

## CAD VLM 파인튜닝 서버

독립 이식 파일:

```text
training/cad-vlm/dist/xconcep-cad-vlm-portable.zip
training/cad-vlm/dist/xconcep-cad-vlm-portable.zip.sha256
```

현재 ZIP SHA-256:

```text
0bd720e7ca7e676e751c0a86b51b842cd2513ddfeb4a529697a15289282b3b68
```

서버로 복사한다.

```powershell
scp ".\전체 풀스택\training\cad-vlm\dist\xconcep-cad-vlm-portable.zip" `
  USER@GPU_SERVER:/srv/
scp ".\전체 풀스택\training\cad-vlm\dist\xconcep-cad-vlm-portable.zip.sha256" `
  USER@GPU_SERVER:/srv/
```

무결성과 패키지 구조를 확인한다.

```bash
cd /srv
sha256sum -c xconcep-cad-vlm-portable.zip.sha256
unzip xconcep-cad-vlm-portable.zip
cd xconcep-cad-vlm
python3 scripts/verify_install.py
```

`valid: true`가 아니면 설치하거나 학습하지 않는다.

Docker 학습:

```bash
cp .env.example .env
docker compose --profile training build trainer

docker compose run --rm trainer \
  --config configs/qwen3-vl-4b-qlora.json \
  --dry-run

docker compose run --rm trainer \
  --config configs/qwen3-vl-4b-qlora.json
```

Ubuntu 가상환경 학습:

```bash
chmod +x scripts/*.sh
./scripts/install-server.sh
source .venv/bin/activate

python scripts/train_vlm.py \
  --config configs/qwen3-vl-4b-qlora.json \
  --dry-run

./scripts/train.sh configs/qwen3-vl-4b-qlora.json
```

PHP DXF/STEP 전처리 패키지를 반입한다.

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
않는다. 동일 CAD에서 만든 여러 view는 같은 split에 유지한다.

학습 모델 검증 API:

```bash
docker compose --profile serve up -d --build verifier
curl -fsS http://127.0.0.1:8191/health
```

앱 서버 `.env` 연결값:

```dotenv
IMAGE_SEMANTIC_VERIFIER_URL=http://GPU_SERVER_IP:8191
IMAGE_SEMANTIC_VERIFIER_API_KEY=VLM_API_KEY와-동일한-값
IMAGE_SEMANTIC_VERIFIER_TIMEOUT_SECONDS=120
```

학습·조정값 상세 설명은
`training/cad-vlm/docs/TRAINING_AND_TUNING_MANUAL_KO.md`, 독립 ZIP 이식은
`training/cad-vlm/SERVER_INSTALL_QUICKSTART_KO.md`와
`training/cad-vlm/docs/MIGRATION_GUIDE_KO.md`를 확인한다.
