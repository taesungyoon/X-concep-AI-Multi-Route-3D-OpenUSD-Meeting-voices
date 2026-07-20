# 최종 테스트 보고서

테스트 기준일: 2026-07-18

## 정적 검증

| 항목 | 결과 |
|---|---|
| Python compileall | PASS |
| PHP 문법 검사 | PASS |
| JavaScript 문법 검사 | PASS |
| Docker Compose YAML Parse | PASS |
| NeMo Agent Workflow YAML Parse | PASS |

## 자동 테스트

| 서비스 | 결과 |
|---|---|
| DRF Control Plane | 2 passed |
| Python AI Worker | 8 passed, 1 optional skipped |
| Knowledge Service | 2 passed |
| Agent Gateway | 1 passed |

## Local End-to-End Mock

- DRF·Python Worker·Knowledge Service·Agent Gateway 실제 Server를 기동함
- Prompt Project 생성과 2D 4안 생성을 확인함
- 2D 선택 후 GLB·STL·PNG·USDA·USDC 생성을 확인함
- GLB를 Trimesh로 재로딩함
- USDA를 OpenUSD Parser로 열고 Default Prim과 13 Prim을 확인함
- 회의 WAV Chunk 업로드·Mock 전사·Meeting Analysis·2D 4안 생성을 확인함
- 폭 900 mm 변경을 Dimension과 Requested Change로 구조화함
- 높이 추후 확정을 Unresolved Item으로 구조화함
- 문서 파일을 Knowledge Service에서 Chunk화하고 Qdrant 검색함
- API 응답에서 `/tmp/` 절대경로가 노출되지 않음을 확인함

## 실행 환경 부재로 미검증

- Docker Engine 전체 Image Build임
- 실제 MySQL·Qdrant Container E2E임
- 실제 NeMo Agent Toolkit Container Runtime임
- 실제 NeMo Retriever GPU Extraction임
- 실제 Gemma·GPT Image·Hunyuan3D·Speech Model임
- 실제 Omniverse·Nucleus·WebRTC·Isaac Sim임

## 추가 확인 사항

- Omniverse Web Client TypeScript 소스 계약은 정적 검토했으나 `@nvidia/ov-web-rtc` 패키지 설치와 Vite Production Build는 현재 환경에서 실행하지 못함
- Docker CLI가 현재 환경에 없어 Docker Image Build와 Compose 실제 Container 기동은 수행하지 못함
- 위 두 항목은 운영 배포 체크리스트의 차단 조건으로 유지함
