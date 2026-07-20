# OpenUSD 연계 매뉴얼

## 출력

- `model.usda`: 항상 생성되는 텍스트 OpenUSD Stage임.
- `model.usdc`: `usd-core` Python Binding 설치 시 생성되는 Binary Stage임.
- `model.glb`: 웹 Three.js Viewer용임.
- `model.stl`: 메시 전달·출력용임.

## Stage 구조

```text
/World
└─ /Asset
   ├─ /Mesh_1
   ├─ /Mesh_2
   └─ ...
```

Stage Metadata임.

```text
defaultPrim = World
metersPerUnit = 1
upAxis = Z
```

Custom Attribute임.

```text
xconcep:projectId
xconcep:category
xconcep:selectedConcept
xconcep:pipeline
```

## Omniverse에서 열기

1. Omniverse USD Composer 또는 Kit 기반 앱을 실행함.
2. `model.usda` 또는 `model.usdc`를 열음.
3. Asset 하위 Mesh Prim을 선택하여 재질·Transform을 편집함.
4. 기업용 확장에서는 Nucleus 저장소로 복사함.

## 제한

- Hunyuan3D가 단일 Mesh를 생성하면 OpenUSD에서도 의미 기반 부품 구조가 자동 복원되지 않음.
- OpenUSD는 STEP B-Rep 또는 CAD Feature Tree를 대체하지 않음.
- 제조용 치수·공차 데이터가 필요한 경우 별도 Geometry JSON·CadQuery 경로를 추가해야 함.
