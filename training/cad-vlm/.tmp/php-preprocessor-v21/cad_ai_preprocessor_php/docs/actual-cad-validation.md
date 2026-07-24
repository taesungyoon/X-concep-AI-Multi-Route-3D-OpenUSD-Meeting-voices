# 실제 산업 CAD 검증 결과

- 검증 일시: 2026-07-23
- 런타임: PHP 8.4.23
- 입력: 사용자 제공 DXF 5개, STP 2개
- 결과: 7/7 완료, 실패 0, 품질 경고 0
- 파일별 산출물: 10개
- 데이터셋 ZIP: 7/7 정상

| 파일 | SHA-256 | 엔티티 | 주요 관측 | 품질 |
|---|---|---:|---|---:|
| 01- (1).dxf | 66bb5b7c1c17135e65a5e262e3c1f57157ae94abca25c3116761c0b124a51918 | 1,258 | LINE 931, CIRCLE 196, 4 layers | 1.0 |
| 01- (2).dxf | f3ba88b6b042348c18a55166e7c2408bcf38026d30ca09ab81ab8be04a30b2fb | 956 | LINE 663, TEXT 112, SPLINE 89 | 1.0 |
| 01- (3).dxf | 2d8a3a577985d8de65e26d53a54457cb9f501c5a33d9997a224fe1fb9e3d28df | 100 | LINE 44, TEXT 19, DIMENSION 17 | 1.0 |
| 01- (4).dxf | 467e7a4267f75e4b4db0558193b4289725df7561eafcb9e69c82f1be316c9503 | 69 | LINE 35, TEXT 19 | 1.0 |
| 01- (5).dxf | c89fdc7558bcabb84fc63022f79d87aef10b1cf42f07f3475d3d772a4c46c39f | 973 | LINE 668, CIRCLE 154, ARC 88 | 1.0 |
| speed control unit.stp | bcc5f1cf6d6935b491baee1cf04147f4fd228e2e2e23c720e4cdaeefa92cb0b8 | 87,113 | 25,026 points, 6,564 faces, 5 solids | 1.0 |
| speed controller box.stp | 6d727526e1eda66bc8e4849710f53c06d3005d5c7b2828a4c90f7d1518e6dfb4 | 1,384 | 226 points, 129 faces, 2 solids | 1.0 |

## 검증 중 수정

1. DXF 업로드 시 첫 8KB 안에 `ENTITIES`가 있어야 한다는 오탐 규칙을 제거했다.
2. ASCII DXF 시작 그룹 `0 / SECTION / 2 / HEADER`를 검증하도록 변경했다.
3. `$DWGCODEPAGE=ANSI_949`를 감지하여 CP949 한글 값을 UTF-8로 변환한다.
4. 긴 헤더와 CP949 한글 도면 문자에 대한 회귀 테스트를 추가했다.

## 해석 제한

품질 1.0은 시그니처, 파싱, 형상 관측, 경계상자, 라벨, 패키지 계약이 완료됐다는 의미다.
설계 정확성, 공차, 조립 간섭, 제조 가능성 또는 원 CAD 피처 트리의 정확성을 의미하지 않는다.
정밀 STEP B-Rep와 Assembly 검증은 OCP/Open CASCADE 기반 생산 Worker에서 별도로 수행한다.
