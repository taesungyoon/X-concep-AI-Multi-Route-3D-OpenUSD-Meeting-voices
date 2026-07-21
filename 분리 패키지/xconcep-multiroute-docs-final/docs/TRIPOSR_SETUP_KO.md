# TripoSR 로컬 설치·연결

## 채택 기준

- 이미지 기반 자유형 메시의 로컬 기본 엔진임.
- VAST-AI-Research/TripoSR 코드와 stabilityai/TripoSR 모델은 MIT 라이선스임.
- 외부 API 키 없이 로컬 NVIDIA CUDA GPU에서 실행함.
- 외부 API의 기존 `hunyuan3d` 라우트 키는 호환 별칭이며 실제 provider는 `triposr`임.

## Windows 설치와 실행

저장소 루트에서 실행함. 설치 스크립트는 Python 3.12 가상환경, CUDA 12.9용 PyTorch, 고정 TripoSR 커밋과 서비스 의존성을 구성함.

```powershell
powershell -ExecutionPolicy Bypass -File ".\전체 풀스택\scripts\setup-triposr.ps1"
powershell -ExecutionPolicy Bypass -File ".\전체 풀스택\scripts\run-triposr.ps1"
```

서비스 상태는 `http://127.0.0.1:8081/health`, 생성 API는 `POST http://127.0.0.1:8081/generate`임.

## Worker 설정

```dotenv
SHAPE_MODE=triposr
SHAPE_PROVIDER=triposr
SHAPE_API_URL=http://127.0.0.1:8081
SHAPE_TIMEOUT_SECONDS=1800
```

Docker의 Worker에서 Windows 호스트 서비스를 호출할 때는 `SHAPE_API_URL=http://host.docker.internal:8081`을 사용함.

## 검증

```powershell
.\.triposr-venv\Scripts\python.exe -m pytest ".\전체 풀스택\triposr-service\test_compat.py" ".\전체 풀스택\triposr-service\test_api.py" -q
.\.triposr-venv\Scripts\python.exe ".\전체 풀스택\triposr-service\smoke_generate.py" --resolution 128 --remove-background
```

2026-07-20 기준 RTX PRO 4000에서 배경 제거 포함 실제 GLB 생성, GLB 재로딩, geometry 존재 여부와 Worker HTTP 연결을 검증함.
