# X concep AI 회의·Omniverse 풀스택 최종 점검 보고서

## 1. 판정

**조건부 승인**임.

Mock 기반 PHP→Python→회의 전사→Gemma 분석→GPT Image Mock→Hunyuan3D Mock→GLB/STL/PNG→OpenUSD 전체 연동은 정상임. 실제 상용 운영 승인은 실모델·GPU 클러스터·NVIDIA Runtime 검증과 인증·비동기 Queue 적용 후 가능함.

## 2. 점검 범위

- PHP 반응형 UI·API Gateway임.
- 회의 음성 Chunk 업로드와 준실시간 전사 흐름임.
- Gemma 계열 커스텀 64B의 vLLM OpenAI 호환 Client임.
- Ray 멀티노드 실행 스크립트임.
- GPT Image API Client임.
- Hunyuan3D 로컬 API Client임.
- GLB·STL·PNG 생성 및 다운로드임.
- OpenUSD USDA·USDC·Layer Package임.
- Omniverse Kit Extension·Asset Validator·Nucleus·WebRTC Client임.
- 경로 보안·민감 파일 공개·XSS·산출물 무결성임.

## 3. 수정 완료 항목

### OpenUSD

- 잘못 작성된 VariantSet USDA 문법을 수정함.
- 문자열 검색식 검증을 실제 `Usd.Stage.Open()` Parser 검증으로 교체함.
- `usd-core`를 기본 의존성에 포함하여 USDC 생성을 보장함.
- root.usda·model.usda·model.usdc를 모두 재개방하여 13개 Prim을 확인함.

### 경로·정보보호

- Python Worker의 입력 경로를 `STORAGE_PATH` 내부로 제한함.
- `..` 및 절대경로를 이용한 Path Traversal을 차단함.
- Hunyuan3D가 반환한 로컬 파일 경로도 Storage Root 내부인지 검증함.
- `project.json`, `analysis.json`, 원본 업로드, 회의 음성을 PHP 정적 경로에서 HTTP 403 처리함.
- LLM·생성 결과 문자열을 HTML에 출력할 때 Escape 처리함.
- 3D Asset URL은 생성 결과 경로만 허용함.

### 회의 음성

- NVIDIA Speech NIM REST Endpoint를 `/v1/audio/transcriptions`로 수정함.
- multipart 필드명을 `file`로 수정함.
- WebM·M4A·OGG 입력을 FFmpeg로 16kHz Mono WAV로 변환함.
- 근거 없는 교대 방식 화자 분리를 제거함.
- HTTP REST 전사는 준실시간 Chunk 처리로 표시하고, 지속 Streaming·화자 분리는 별도 WebSocket/gRPC 경로로 구분함.

### Hunyuan3D

- 요청에 `type=glb`와 `remove_background=true`를 명시함.
- GLB Binary·JSON Base64·URL·공유 파일 응답 경로를 분리함.

### NVIDIA Omniverse

- Asset Validator의 `ValidationEngine.validate()` 결과를 단일 `Results` 객체로 처리함.
- Kit Extension의 Variant 선택 UI를 단순 버튼 방식으로 안정화함.
- WebRTC Client를 `@nvidia/ov-web-rtc` 6.4.4의 정적 `AppStreamer.connect()` 구조로 수정함.
- Nucleus 게시 스크립트는 `omni.client.copy_file()`과 덮어쓰기 동작을 사용함.

## 4. 최종 테스트 결과

- Python pytest 7개 모두 통과함.
- Python 및 Omniverse Kit Python 정적 Compile을 통과함.
- PHP 6개 파일 문법 검사를 통과함.
- JavaScript 2개 파일 문법 검사를 통과함.
- Docker Compose 기본·Omniverse Overlay YAML Parsing을 통과함.
- 실제 PHP·Uvicorn Mock 서버를 기동하여 End-to-End API를 통과함.
- GLB 6,384 bytes, STL 6,084 bytes, PNG Preview, USDA, USDC를 생성하고 HTTP 다운로드를 확인함.
- root.usda·model.usda·model.usdc를 OpenUSD Parser로 재개방함.
- 프로젝트 내부 JSON과 회의 원본 음성에 대한 HTTP 403을 확인함.

상세 표는 `docs/TEST_REPORT.md`에 기록함.

## 5. 운영 배포 전 차단 조건

1. 인증·권한·Tenant 분리가 없음. 외부 공개 전 반드시 적용해야 함.
2. PHP가 AI 요청을 동기 호출함. 장시간 생성과 동시접속을 위해 Queue가 필요함.
3. 사용자 지정 Gemma 64B는 공식 모델명이 아닌 커스텀 체크포인트임. 실제 아키텍처·Tokenizer·Chat Template·멀티모달 지원 검증이 필요함.
4. 실 GPT Image API, Hunyuan3D, vLLM·Ray, Speech NIM을 현재 환경에서 호출하지 못함.
5. NVIDIA Kit/Nucleus/WebRTC Runtime을 현재 환경에서 기동하지 못함.
6. 회의 음성·전사 데이터의 동의·보존·삭제 정책이 필요함.
7. Hunyuan3D 단일 Mesh는 모터·프레임·센서의 의미 기반 Assembly 구조를 자동 복원하지 않음.
8. OpenUSD는 STEP·B-Rep 제조 CAD를 대체하지 않음.

## 6. 차선 시나리오

1차 운영은 GLB Three.js Viewer와 OpenUSD 다운로드까지만 배포함. Omniverse WebRTC·Nucleus·Live Session은 Enterprise On-Premise 환경 검증 후 활성화함. 실시간 화자 분리는 제외하고 15초 Chunk 전사와 사용자 수동 보정을 유지함.

## 7. 최종 결론

현재 전달본은 **PoC·사내 검증·GPU 서비스 연동 개발의 기준 코드로 사용 가능함**. 인증·Queue·실 GPU·NVIDIA Runtime 검증 없이 인터넷에 직접 공개하는 것은 승인하지 않음.
