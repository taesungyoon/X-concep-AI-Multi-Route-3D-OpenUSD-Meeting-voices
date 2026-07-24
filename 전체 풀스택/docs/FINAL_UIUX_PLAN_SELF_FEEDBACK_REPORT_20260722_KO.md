# UI·UX, 계획 기능, 95% 목표 자가피드백 최종 검증 보고서

- 검증일: 2026-07-22 (KST)
- 대상 스택: `xconcep-e2e-r2`
- 웹: `http://127.0.0.1:18080`
- 내부 MySQL: `127.0.0.1:13307`
- 판정 원칙: 계약 수용률과 실제 외관·제조 적중률을 분리하며, 독립 증거 없이는 95% 달성을 선언하지 않는다.

## 최종 결론

계획서 1~8단계의 구현·실행 경로는 현재 코드와 E2E 스택에서 작동한다. 9단계는 독립 자가피드백 평가기와 제한 루프까지 구현·배포했으나, 현재 측정치는 95% 미달이다. 10단계 외부 사내 MySQL/인증은 사용자 결정대로 보류다. 11단계 OpenAI Image API는 실제 1회 성공했지만 해당 2D를 구형 3D 경로가 재현하지 못해 실패 표본으로 등록했다.

현재 95% 목표 달성 여부: **미달성**

- 기존 OpenAI 2D → 구형 3D: 외관 37.54%, 제조 80.00%, 게이트 37.54%
- 전문 부품 3D: 외관 50.57%, 제조 100.00%, 게이트 50.57%
- 자동 계약 수용률 100%는 실제 외관 적중률이 아니며 독립 평가로 사용하지 않는다.

## 실행 환경

| 항목 | 결과 | 증거 |
|---|---:|---|
| Docker 서비스 | 9개 실행, 핵심 서비스 healthy | `docker compose -p xconcep-e2e-r2 ps` |
| 웹 | HTTP 200 | `http://127.0.0.1:18080/` |
| 내부 MySQL | healthy, 프로젝트 4건·작업 이력 보존 | 읽기 전용 SQL |
| OpenSCAD | 2021.01 네이티브 실행 | 네이티브 검증 보고서 |
| Blender | 5.2.0 LTS 네이티브 실행 | 네이티브 검증 보고서 |
| 기본 2D 설정 | ComfyUI/FLUX 계열 | 현재 로컬 8188 미가동 |
| 추가 2D 설정 | OpenAI Image API | gpt-image-2 실제 HTTP 200 1회 |
| 현재 E2E 워커 | 2D/3D/LLM Mock | UI·큐·저장·다운로드 검증용 |

## UI·UX E2E 결과

| 기능 | 결과 | 비고 |
|---|---:|---|
| 사내 테스트 로그인/로그아웃 | PASS | 내부 DB 인증, 관리자 표시 확인 |
| 직접 입력/회의 음성 분석 전환 | PASS | 패널·버튼 상태 전환 확인 |
| 프롬프트·카테고리·목표·품질·엔진 | PASS | part/structural/standard/openscad_part |
| 참고 이미지 업로드 | BLOCKED | 자동화 파일 선택 이벤트가 반환되지 않아 수동 브라우저 확인 필요 |
| 2D 4안 생성 | PASS | 2.227초, 이미지 4개 |
| 2D 안 선택/3D 버튼 활성화 | PASS | 단일 선택 및 버튼 활성화 |
| 전문 부품 3D 생성 | PASS | 2.717초, canvas 1개 |
| ISO/FRONT/TOP 동작 | PASS | 카메라 동작; 활성 상태 피드백을 추가 구현·배포 |
| 검증 상세/3면 이미지 | PASS | 960×720 이미지 3개, 계약 체크 PASS |
| 결과 간 전환 | PASS | OpenSCAD ↔ Blender |
| Blender 재생성 | PASS | 2.066초 |
| 작업 이력 | PASS | 데스크톱 drawer 3건 확인 |
| 다운로드 | PASS | GLB/STL/SCAD/Geometry JSON/USDA/USDC/root/manifest 모두 HTTP 200 |
| 모바일 390×844 | BLOCKED | 브라우저 자동화 커널 장애로 최종 캡처 미완료; CSS 반응형 규칙은 존재 |
| 전체화면/Omniverse 실제 앱 | NOT RUN | 현재 Omniverse 스트림 URL 미설정 |

## 계획서 기능 매트릭스

| 계획 단계 | 판정 | 검증 |
|---:|---:|---|
| 1 운영 차단요인 감사 | PASS | 내부 인증, 저장 URL, MySQL 마이그레이션/실행 확인 |
| 2 범용 OpenSCAD 유지 + 선택/fallback | PASS | 단위 테스트 및 레거시 템플릿 유지 |
| 3 DesignSpec·GeometryContract·seed/hash | PASS | 70개 워커 테스트 |
| 4 부품 생성기 | PASS | 네이티브 OpenSCAD/GLB/STL/SCAD/3면 |
| 5 모듈 생성기 | PASS | 네이티브 OpenSCAD/GLB/STL/SCAD/3면 |
| 6 설비 생성기·OpenUSD 계층 | PASS | 네이티브 OpenUSD hierarchy |
| 7 3면·좌표 관계·부분 재생성 | PASS | part/module/equipment 1.0, vision_camera 실패 주입 후 부분 재생성 |
| 8 UI/API/Celery/MySQL/Mock E2E | PASS WITH BLOCKS | 핵심 E2E PASS, 업로드·모바일 수동 확인 잔여 |
| 9 독립 홀드아웃 95% | IN PROGRESS | 평가기·3회 제한 루프·Wilson 하한 판정 구현, 실제 점수 미달 |
| 10 외부 사내 MySQL/인증 | DEFERRED | 사용자 결정 |
| 11 OpenAI Image 재현율 비교 | FAIL SAMPLE | 2D 생성 성공, 구형 3D 외관 불일치 |

## 자동 회귀와 네이티브 검증

- Python worker: **70 passed**
- Django control plane: **12 passed**
- 합계: **82 passed**
- 네이티브 부품·모듈·설비: **3/3 PASS**
- 다중뷰 계약: part/module/equipment **각 1.0**
- 실패 주입 후 부분 재생성: **PASS**
- 전문 부품 다운로드 8종: **8/8 HTTP 200**
- PHP lint: PASS
- JavaScript syntax: PASS

## 자가피드백 고도화 구현

새 평가기는 다음을 분리한다.

1. 2D 기준 이미지와 실제 렌더의 배경 정규화 실루엣 IoU, 투영 프로필, 종횡비, 윤곽 IoU
2. GLB의 유한 좌표, 퇴화면, watertight body, 양의 부피, 실제 bounding box
3. 계약 기반 요구 커버리지는 비독립 항목으로 명시
4. 최종 게이트는 외관과 제조 점수 중 낮은 값을 사용
5. 최대 3회 제한, 최고 후보 보존, 목표 미달 시 실패 유지
6. 부품·모듈·설비 각각 최소 200건과 Wilson 95% 신뢰구간 하한 95%를 만족해야만 목표 달성

자동 등급 상한은 `validated`이며, `manufacturing_approval=false`를 강제한다. 제조 승인에는 공차, 재료 강도, 체결 토크, 공정, 조립성, 안전 검토가 별도로 필요하다.

## 95%까지 남은 작업

1. 고정 홀드아웃 600건(부품·모듈·설비 각 200건)과 사람 정답 라벨 구축
2. 2D 실루엣을 실제 파라메트릭 특징으로 역추정하는 비전 파서 추가
3. L 브래킷, 베이스/가이드/모터, 설비 프레임/도어/비전/제어반 템플릿 세분화
4. 렌더와 기준 이미지의 카메라 자세 자동 정합
5. 최소 두께, 홀 가장자리 거리, 공구 접근성, 체결/간섭 DFM 규칙 추가
6. 실패 유형별 파라미터 수정 정책을 후보 생성기에 연결
7. 홀드아웃 결과를 관측률과 Wilson 하한으로 릴리스 게이트 처리

## 증거 파일

- UI 스크린샷: `storage/e2e-evidence/20260722-uiux-full-openai/`
- 네이티브 보고서: `storage/e2e-evidence/20260722-final-native/native_validation_report.json`
- 다중뷰 보고서: `storage/e2e-evidence/20260722-final-multiview/`
- 기존 OpenAI 실패 기준선: `storage/e2e-evidence/20260722-self-feedback/openai-baseline.json`
- 전문 부품 기준선: `storage/e2e-evidence/20260722-self-feedback/specialized-part-baseline.json`
- 배포된 프로젝트 리포트: `storage/projects/PRJ-FF00B9726F/result/self_feedback_report.json`
- 원시 QA CSV: `storage/e2e-evidence/20260722-uiux-full-openai/qa_raw_results.csv`

## 2026-07-23 로컬 네이티브 추가 검증

이 섹션은 위 2026-07-22 시점 정보를 갱신한다.

- 현재 로컬 ComfyUI/FLUX는 연결됐고 실제 1024×1024 콘셉트 4안을 76.212초에 생성했다.
- OpenAI Image API는 이번 검증에서 호출하지 않았다.
- 실제 한국어 WAV를 로컬 Faster-Whisper로 인식했고, 설비 회의 문장에서 5개 부품군과 치수·안전 요구사항을 추출했다.
- `openscad_equipment` 1.2.0에 기존 범용 셀을 보존하면서 비전 검사 셀 외관 레이아웃을 추가했다.
- Blender 가져오기와 최종 GLB 내보내기의 Y/Z 축 교환을 모두 탐지·보정했다.
- 최종 revision 8은 55 meshes, 외곽 1.6×1.0×1.8m, 제조 구조 1.0, OpenUSD 55/55 valid다.
- 최종 외관 독립 점수는 0.5883으로 0.95 목표 미달이며, 자동 제조 승인은 계속 금지한다.
- Python worker 전체 회귀는 84/84 PASS다.

최신 상세 기록과 증거 경로는 `docs/PARAMETRIC_GENERATOR_ROADMAP_KO.md`의 `2026-07-23 로컬 독립 외관 고도화와 전체 파이프라인 회귀` 섹션을 기준으로 한다.
