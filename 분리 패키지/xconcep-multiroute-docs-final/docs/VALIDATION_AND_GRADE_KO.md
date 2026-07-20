# X concep AI 검증 등급·제조 활용 기준

## 1. 일관성 우선순위

```text
기능 및 동작 원리
> 필수 구성요소
> 주요 치수와 배치
> 전체 비례와 실루엣
> 재질·곡면·세부 외관
```

각 생성 엔진의 결과가 메시 또는 픽셀 단위로 동일하다고 보장하지 않음. 공통 Design State를 통해 핵심 설계 의도와 구조를 일관되게 유지함.

## 2. 등급

| 코드 | 표시 | 부여 주체 |
|---|---|---|
| concept | 컨셉 검토 가능 | 자동 Worker임 |
| structured | 구조 검토 가능 | 자동 Worker임 |
| validated | 자동 검증 완료 | 자동 Worker임 |
| engineer_reviewed | 엔지니어 검토 완료 | 인증된 검토자임 |
| manufacturing_approved | 제조 승인 완료 | 제조 승인 담당자임 |

## 3. 활용 기준

- GPT Image는 시각 컨셉과 외관 방향에 활용함
- Hunyuan3D는 빠른 Mesh와 웹 3D 검토에 활용함
- OpenSCAD는 지원 형상 범위에서 구조·배치·치수 검토에 활용함
- Blender·OpenUSD는 통합 시각화·애니메이션·시뮬레이션 자산에 활용함
- Validated 결과는 후속 CAD 설계 입력으로 활용할 수 있음
- 제조 승인에는 공차·재질·체결·가공·강도·안전·조립 조건 검토가 추가로 필요함

## 4. 자동 검증 항목

- Mesh Load와 유효 Face임
- NaN·Infinity·0 크기 Bounding Box임
- 주요 치수 오차임
- 필수 Component 존재 여부임
- Assembly Manifest 일치 여부임
- 단위와 좌표축임
- GLB·STL·USD 파일 존재와 재개방임
- OpenUSD Default Prim·Layer·Texture 경로임

## 5. 승인 절차

```text
AI 생성
→ 자동 품질 검증
→ 엔지니어 검토
→ 상세 CAD 보완
→ 제조성·안전 검토
→ 제조 승인
```
