# X concep AI 회의·Omniverse 최종 설치 및 운영 매뉴얼

## 1. 제공 기능

- 프롬프트·참고 이미지 입력함
- 회의 음성 녹음·Chunk 업로드·전사함
- Gemma가 제조 요구사항을 구조화함
- GPT Image API로 2D 설계안 4개를 생성함
- 사용자가 2D 결과를 비교·선택함
- Hunyuan3D 로컬에서 GLB·STL을 생성함
- OpenUSD Layer Package와 선택적 USDC를 생성함
- Omniverse Kit에서 RTX·PhysX·Validator·Nucleus·WebRTC 검토 경로를 제공함

## 2. 기본 요구사항

### Web·Orchestrator

- Docker Engine 또는 PHP 8.2+와 Python 3.11+ 필요함
- 파일 저장공간 필요함
- HTTPS 적용을 권장함

### Gemma vLLM·Ray

- 사용자 보유 Gemma 계열 64B 체크포인트 필요함
- vLLM이 해당 아키텍처·Tokenizer·멀티모달 입력을 지원하는지 별도 확인해야 함
- GPU 수에 맞는 Tensor Parallel·Pipeline Parallel 값을 정해야 함

### Hunyuan3D

- Hunyuan3D 지원 CUDA·PyTorch 환경 필요함
- 모델 가중치와 라이선스 확인이 필요함

### Omniverse

- NVIDIA GPU Driver와 Kit SDK 또는 운영자가 패키징한 Kit App Image 필요함
- Nucleus·Kit App Streaming은 NVIDIA 제품·계정·라이선스 조건을 확인해야 함

## 3. Mock 실행

```bash
unzip xconcep-meeting-omniverse-fullstack-final-checked.zip
cd xconcep-omniverse-meeting-final-checked
cp .env.example .env
docker compose up --build
```

```text
http://localhost:8080
```

## 4. 실제 AI 연결

```env
PIPELINE_MODE=production
LLM_MODE=vllm
VLLM_BASE_URL=http://RAY_HEAD:8000/v1
VLLM_API_KEY=local-not-required
GEMMA_MODEL_NAME=gemma-4-64b-local

OPENAI_IMAGE_MODE=openai
OPENAI_API_KEY=sk-...
OPENAI_IMAGE_MODEL=gpt-image-2

HUNYUAN_MODE=local_api
HUNYUAN_API_URL=http://HUNYUAN3D:8081
```

## 5. 회의 음성 연결

### faster-whisper

```env
SPEECH_MODE=faster_whisper
INSTALL_SPEECH=true
WHISPER_MODEL=large-v3-turbo
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
```

이미지를 다시 빌드함.

```bash
docker compose build --no-cache python-worker
docker compose up -d
```

### NVIDIA Speech NIM

```env
SPEECH_MODE=nvidia_nim
NVIDIA_ASR_URL=http://ASR_NIM:9000
NVIDIA_ASR_TRANSCRIBE_PATH=/v1/audio/transcriptions
DIARIZATION_MODE=none
```

HTTP REST 전사는 multipart `file` 필드를 사용함. 지속 스트리밍과 화자 분리가 필요할 경우 NIM WebSocket 또는 gRPC Streaming Client를 별도 적용함.

## 6. 사용자 사용법

### 직접 입력

1. 직접 입력 모드를 선택함
2. 프롬프트와 참고 이미지를 입력함
3. 2D 설계안 생성함
4. 4개 중 하나를 선택함
5. 3D 생성함
6. GLB·STL·PNG·OpenUSD 파일을 다운로드함

### 회의 음성

1. 회의 음성 분석 모드를 선택함
2. 녹음 시작함
3. Transcript를 확인·수정함
4. 회의 내용 분석함
5. 확정·변경·미확정·안전 항목을 검토함
6. 현재 내용으로 2D 생성함
7. 2D를 선택하고 3D 생성함
8. Omniverse RTX 또는 다운로드 파일로 검토함

## 7. Omniverse 적용

```env
OMNIVERSE_ENABLED=true
OMNIVERSE_GENERATE_LAYERS=true
OMNIVERSE_ENABLE_PHYSICS=true
OMNIVERSE_ENABLE_VARIANTS=true
OMNIVERSE_NUCLEUS_URL=omniverse://SERVER/Projects/Xconcep
OMNIVERSE_STREAM_URL=http://WEBRTC_CLIENT
OMNIVERSE_KIT_IMAGE=registry/xconcep-kit:1.0
```

```bash
docker compose -f docker-compose.yml -f docker-compose.omniverse.yml up -d
```

## 8. 저장 구조

```text
storage/projects/PRJ-ID/
├─ project.json
├─ uploads/
├─ meeting/
│  ├─ audio/
│  ├─ analysis.json
│  └─ revision-XXX.json
├─ 2d/
└─ result/
   ├─ model.glb
   ├─ model.stl
   ├─ render.png
   ├─ model.usda
   ├─ model.usdc
   └─ openusd/
```

## 9. 운영 점검

```bash
curl http://localhost:8080/health
curl http://localhost:8080/api/system-status
curl http://localhost:8001/health
```

확인 항목임.

- PHP와 Python Health가 정상임
- vLLM Model Name이 일치함
- OpenAI Key가 Web 응답·Log에 노출되지 않음
- Hunyuan3D 응답이 GLB임
- Speech Chunk가 처리됨
- USD Default Prim·Layer 경로가 유효함
- Nucleus 권한과 WebRTC ICE 연결이 정상임

## 10. 장애 대응

### 마이크가 동작하지 않음

- HTTPS 또는 localhost에서 실행해야 함
- 브라우저 마이크 권한 확인함
- WebM Codec 지원 확인함
- PHP 업로드 한도 확인함

### 전사가 느림

- Whisper Model 크기를 줄임
- Chunk 길이를 조정함
- GPU Device와 Compute Type 확인함
- Speech NIM Streaming으로 전환 검토함

### Gemma JSON 오류

- Temperature 0.1 이하 유지함
- `response_format=json_object` 지원 여부 확인함
- Model Server Log에서 Token Truncation 확인함

### 3D 생성 실패

- Hunyuan3D URL과 Timeout 확인함
- 선택한 2D 이미지 파일 경로 확인함
- VRAM·CUDA OOM 확인함

### OpenUSD가 Omniverse에서 열리지 않음

- Root Sublayer 상대경로 확인함
- Texture·Mesh Asset 경로 확인함
- Kit와 OpenUSD ABI 호환성 확인함
- Asset Validator 실행함
