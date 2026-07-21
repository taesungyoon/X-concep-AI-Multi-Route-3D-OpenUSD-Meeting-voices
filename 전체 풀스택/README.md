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
