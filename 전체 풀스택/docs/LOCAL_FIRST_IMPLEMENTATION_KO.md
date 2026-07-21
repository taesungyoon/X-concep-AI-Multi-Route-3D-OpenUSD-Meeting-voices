# 로컬 우선 구현·검증 기준

## 현재 실행 수준

- 로컬 Mock E2E는 PHP → DRF → Agent → Worker → OpenUSD 경로까지 동작함.
- Mock은 연결 검증용이며 실제 AI 모델 품질을 의미하지 않음.
- `/api/system-status`의 `execution_profile`과 `runtime_ready`로 실제 연결 상태를 구분함.
- `mock`은 실모델 미연결, `partial`은 일부 Runtime 연결, `live`는 핵심 2D·3D Runtime 준비 상태임.

## 2026-07-20 실제 검증 결과

- Python 자동 테스트: 통합 스택 25 passed, 1 optional skipped이며 TripoSR 서비스 4 passed임.
- Docker Image 6종 Build를 통과함.
- MySQL·Redis·Qdrant·Celery 비동기 2D·3D E2E를 통과함.
- 로컬 Ollama `qwen3:14b` 요구사항 분석을 통과함.
- Ollama + Native OpenSCAD 비동기 E2E를 통과함.
- Native OpenSCAD Provider, SCAD·GLB 출력 및 `validated` 등급을 확인함.
- `faster-whisper small`로 실제 한국어 WAV 전사를 통과함. 최초 다운로드 포함 29.3초, 2개 구간, 한국어 문장 반환을 확인함.
- ComfyUI 0.19.4 + FLUX.2 Klein 4B FP8로 768×768 실제 산업 설비 이미지를 21.2초에 생성·회수함.
- Worker `/v1/generate/2d` E2E에서 768×768 대안 4장을 34.24초에 생성함. HTTP 200, PNG 검증, 외부 서비스 0건을 확인함.
- TripoSR가 로컬 CUDA에서 FLUX 결과 이미지를 128 해상도 메시로 변환함. 배경 제거 포함 GLB 1,157,944 bytes, geometry 1개를 확인함.
- Worker → TripoSR HTTP 실제 연결에서 기본 256 해상도 GLB 4,869,772 bytes, geometry 1개를 확인함.
- 브라우저 UI에서 직접 입력 → 2D 4안 → 선택 → 3D 생성 → Three.js GLB 캔버스 로드와 회의 텍스트 → 요구사항 분석 → 2D 4안 생성을 확인함.
- Omniverse RTX Runtime과 `@nvidia/ov-web-rtc` 클라이언트를 실제 연결함. 640×360 영상 `readyState=4`, 재생 상태, 서버 `client_connected=true`, 518프레임 전송을 확인함.
- Hunyuan3D 2.0/2.1은 라이선스의 허용 지역에서 대한민국이 제외되므로 현재 로컬 기본 엔진으로 도입하지 않음. MIT 라이선스 TripoSR를 대체 엔진으로 채택함.

## Windows 로컬 실행

저장소 루트의 `.venv`에 기본 Requirements를 설치한 뒤 실행함.

```powershell
cd "전체 풀스택"
powershell -ExecutionPolicy Bypass -File .\scripts\run-local.ps1 -Profile mock
```

- UI: `http://127.0.0.1:8080`
- 상태: `http://127.0.0.1:8080/api/system-status`
- 내부 Control Plane은 vLLM 기본 포트와 충돌하지 않도록 `8030`을 사용함.
- `-Profile live`는 현재 Shell에 설정한 실제 LLM·Image·3D·Speech 환경변수를 보존함.
- `-Profile ollama`는 로컬 Ollama `qwen3:14b`를 OpenAI 호환 LLM으로 연결함. `OLLAMA_MODEL`로 모델을 변경할 수 있음.
- 기본 2D Provider는 `OPENAI_IMAGE_MODE=comfyui`이며 ComfyUI는 별도 터미널에서 `scripts/run-comfyui.ps1`로 실행함.
- `-EnableSpeech`를 추가하면 실제 `faster-whisper`를 연결함. 기본 모델은 `large-v3-turbo`이며 `WHISPER_MODEL=small`처럼 바꿀 수 있음.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-comfyui.ps1
```

OpenAI Image API는 추가 모드임. `OPENAI_IMAGE_MODE=openai`, `OPENAI_API_KEY`를 설정하고 `-Profile live`로 실행함.

이미지 기반 3D는 별도 터미널에서 최초 1회 설치 후 실행함. 실제 워커 설정은 `SHAPE_MODE=triposr`, `SHAPE_PROVIDER=triposr`, `SHAPE_API_URL=http://127.0.0.1:8081`임.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-triposr.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-triposr.ps1
```

## 자동 테스트

```powershell
cd "전체 풀스택"
powershell -ExecutionPolicy Bypass -File .\scripts\test-local.ps1
```

현재 기준 결과는 통합 스택 Python 25 passed, 1 optional skipped, TripoSR 4 passed, Omniverse 장면 2 passed이며 PHP·JavaScript·Compose 정적 검증을 통과함. Omniverse WebRTC 클라이언트는 Vite 7.3.6 production build와 `npm audit` 0건을 확인함.

## Docker 운영형 로컬 실행

Compose에서는 `SYNC_PIPELINE=false`가 기본이며 Redis·Celery Worker가 항상 기동함. 브라우저는 `202 Accepted`로 받은 Job을 폴링해 완료 결과를 조회함.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

`.env`에는 최소한 강한 `DJANGO_SECRET_KEY`, MySQL Password와 `INTERNAL_API_TOKEN`을 설정함.

### Ollama + Native OpenSCAD 프로필

로컬 Ollama LLM, 컨테이너 내부 OpenSCAD Binary와 `faster-whisper`를 실제 연결함. 2D 이미지는 기본 ComfyUI/FLUX를 사용하고 OpenAI Images는 선택 모드로 유지함.

```powershell
docker compose -f docker-compose.yml -f docker-compose.local-native.yml up --build
```

기본 Ollama 모델은 `qwen3:14b`이며 `$env:OLLAMA_MODEL='gemma4:31b'`처럼 변경할 수 있음.

## 실제 Runtime 연결 순서

1. `LLM_MODE=vllm`과 `VLLM_BASE_URL`을 설정하고 `/models` 연결을 확인함.
   Ollama는 `LLM_MODE=openai_compatible`, `VLLM_BASE_URL=http://127.0.0.1:11434/v1`을 사용함.
2. 기본 2D는 연결 완료된 `OPENAI_IMAGE_MODE=comfyui`를 사용함. OpenAI Image API는 선택 모드로 유지함.
3. 자유형 이미지 기반 3D는 연결 완료된 TripoSR를 사용하고, 치수 중심 구조물은 OpenSCAD, 고품질 후처리는 Blender 경로를 사용함.
4. 음성은 연결 완료된 `faster_whisper`를 로컬 기준선으로 사용하고, 추후 NeMo/NIM으로 교체 가능함.
5. Omniverse RTX/WebRTC 서버와 브라우저 클라이언트 연결은 검증 완료됨. 대용량 서버 이전 때 사내 Nucleus 주소와 외부망 사용 시 TURN/STUN을 추가 설정함.

사내 사용자 인증과 조직 DB 연동은 사용자 결정에 따라 후속 단계에서 Control Plane 앞단에 추가함. 현재 `INTERNAL_API_TOKEN`은 사용자 인증이 아니라 PHP와 DRF 사이의 서비스 보호용임.
