# 통합 테스트 보고서

## 최종 판정

Mock 통합 경로는 PASS임. 실제 운영 배포는 외부 모델·GPU·NVIDIA Runtime과 인증·Queue 검증이 남아 있어 조건부 승인임.

## 결과 요약

| 항목 | 결과 |
|---|---|
| Python compileall | PASS |
| Python pytest | 7 passed |
| PHP 전체 문법 검사 | PASS · 6 files |
| JavaScript 문법 검사 | PASS · app.js, viewer.js |
| Docker Compose YAML Parsing | PASS · 기본/Omniverse Overlay |
| Omniverse Kit Python 정적 Compile | PASS |
| Python Health API | PASS |
| PHP Health API | PASS |
| 회의 프로젝트 생성 | PASS |
| WAV 음성 Chunk 업로드 | PASS |
| Mock STT·Transcript 누적 | PASS |
| Gemma 요구사항 분석 | PASS · Mock LLM |
| 회의 기준 2D 설계안 생성 | PASS · 4개 |
| 2D 선택 후 3D 생성 | PASS · Mock Hunyuan3D |
| GLB 생성·HTTP 재다운로드 | PASS · 6,384 bytes |
| STL 생성·HTTP 재다운로드 | PASS · 6,084 bytes |
| PNG Preview 생성 | PASS |
| USDA 생성·Parser 개방 | PASS · 13 prims |
| USDC 생성·Parser 개방 | PASS · 13 prims |
| Layered root.usda 개방 | PASS · 13 prims |
| Default Prim·Z-Up·PhysicsScene | PASS |
| VariantSet 문법 | PASS · usd-core parser |
| Storage 경로 이탈 방지 | PASS |
| project.json·analysis.json 직접 접근 | PASS · HTTP 403 |
| 회의 원본 음성 직접 접근 | PASS · HTTP 403 |
| XSS 방지 Escaping·Asset URL 제한 | PASS · Source Review |

## 최종 실제 호출 흐름

```text
PHP 회의 생성
→ WAV Chunk 업로드
→ Python Mock 전사
→ Transcript 누적
→ 회의 요구사항 분석
→ 2D 설계안 4개 생성
→ 2D 선택
→ GLB·STL·PNG 생성
→ USDA·USDC·Layered OpenUSD 생성
→ USD Parser 재개방
→ 민감 파일 HTTP 403 확인
```

## 수정 후 핵심 회귀 테스트

- USDA VariantSet 문법을 실제 OpenUSD Parser로 검증함.
- Python Worker가 `STORAGE_PATH` 외부 파일을 읽지 못하도록 검증함.
- Hunyuan3D 로컬 파일 응답도 Storage Root 내부로 제한함.
- NVIDIA Speech NIM REST 요청 경로와 multipart 필드 계약을 수정함.
- 브라우저 WebM 계열 음성을 FFmpeg로 16kHz Mono WAV로 변환하도록 구성함.
- 임의 교대 방식 화자 표기를 제거함.
- Omniverse Asset Validator의 `Results` 반환 계약에 맞게 수정함.

## 검증하지 못한 항목

- 사용자 보유 Gemma 커스텀 64B 체크포인트 실제 로딩임.
- vLLM·Ray 멀티노드 TP/PP 추론임.
- 실제 GPT Image API 생성·편집 호출임.
- 실제 Hunyuan3D GPU `/generate` 호출임.
- NVIDIA Speech NIM Container 및 Streaming ASR임.
- NVIDIA Kit App 실제 패키징·Extension 로딩임.
- Nucleus 게시·Live Session·PhysX 실제 시뮬레이션임.
- Omniverse WebRTC 브라우저 실제 연결임.
- Docker Engine 기반 이미지 Build와 Container 통합 기동임.

## WebRTC Client Build 제한

NVIDIA 사설 NPM Registry에 대한 DNS·네트워크 응답이 없어 `@nvidia/ov-web-rtc` 설치와 Production Bundle Build는 완료하지 못함. 소스는 공식 6.4.4 API의 `AppStreamer.connect`, `StreamType.DIRECT`, `DirectConfig` 계약으로 수정함. 실제 배포망에서 `npm install && npm run build` 재검증이 필요함.
