# Hunyuan3D + ComfyUI 영구 배포 및 E2E 결과

- 실행일: 2026-07-28 KST
- 서버: NVIDIA GB10, ARM64, CUDA capability 12.1
- 판정: PASS

## 1–10 완료 감사

1. Hunyuan custom node를 호스트 build context에 영구 저장했다.
   - 저장소: `ComfyUI/custom_nodes/ComfyUI-Hunyuan-3D-2`
   - commit: `657a9c86ae377b6b784bebf2f5be1b9ec8768e18`
   - submodules: Hunyuan3D-2 `dfa8967`, Hunyuan3D-2.1 `52e68bf`
2. `Dockerfile.dgx-spark`에 GL/OpenCV/pymeshlab 런타임과 Hunyuan Python 의존성을 반영했다.
3. `custom_rasterizer`를 `TORCH_CUDA_ARCH_LIST=12.0+PTX`와 현재 Torch/CUDA 환경에서 ARM64 wheel로 빌드했다.
4. `/root/.cache/huggingface`를 호스트 `ComfyUI/cache/huggingface`에 영구 mount했다. 캐시 크기 6.9GB.
5. 재사용 smoke CLI `scripts/hy3d_smoke_test.py`를 저장했다.
6. 새 이미지 `xconcep-comfyui:hunyuan3d-2.1-persistent`를 별도 빌드하고 검증 후 운영에 전환했다.
7. 새 이미지의 node loading, CUDA, OpenCV, rasterizer import, 80-step GLB 생성을 검증했다.
8. Xconcep python-worker가 `shape-adapter`를 통해 ComfyUI Hunyuan workflow를 호출하도록 연결했다.
9. `GET /health`, `POST /generate`, 선택적 Bearer 인증, GLB binary 반환 계약을 구현했다.
10. 운영 worker API에서 이미지 → Hunyuan GLB → Blender → USDA/USDC/layered OpenUSD 전체 E2E를 완료했다.

## 배포 상태

- `xconcep-comfyui-1`: healthy, image `xconcep-comfyui:hunyuan3d-2.1-persistent`
- `xconcep-shape-adapter-1`: healthy, `127.0.0.1:8081`
- `xconcep-python-worker-1`: healthy
- worker `runtime_ready=true`
- GPT-OSS `gpt-oss:120b`: connected
- ComfyUI/FLUX: connected
- Hunyuan3D adapter: connected
- OpenUSD packaging: enabled

## 실제 생성 결과

### Adapter 단독 검증

- 기존 임시 설치: HTTP 200, 133.5초, 15,823,528 bytes, GLB magic `glTF`
- 영구 이미지 재현: HTTP 200, 161.7초, 15,823,528 bytes, GLB magic `glTF`
- 모델: `tencent/Hunyuan3D-2.1/hunyuan3d-dit-v2-1`
- steps 80, paint false, face_reducer false, face_remover true, floater_remover true

### 운영 worker full E2E

- 프로젝트: `PRJ-HY3D-E2E-001`
- API: `POST /v1/generate/3d`
- 결과: HTTP 200, 224.9초
- Blender native return code: 0
- Blender duration: 80.599초
- fast GLB: 10,787,460 bytes
- high-quality GLB: 52,614,764 bytes
- Blender file: 29,532,704 bytes
- preview render: 1,123,138 bytes
- USDA: 124,671,021 bytes
- USDC: 25,242,214 bytes
- layered OpenUSD: root, geometry, looks, meeting, revision 생성
- USDA parser valid: true
- root package parser valid: true
- default prim: `/World`
- mesh count: 1
- physics metadata: enabled
- variant metadata: enabled

독립 GLB 검증:

- mesh count: 1
- vertices: 439,502
- faces: 879,056
- watertight meshes: 1
- finite vertices: true
- positive extents: true

## 테스트 결과

- adapter/client 계약: 2/2 PASS
- python-worker 전체 회귀: 88/88 PASS, 4.59초
- live adapter health: 200
- 잘못된 Bearer: 401
- 올바른 Bearer + invalid base64 image: 400
- ComfyUI 재시작 후 Hunyuan node: 200
- 재시작 후 adapter: 200
- 재시작 후 worker `runtime_ready`: true
- 재시작 후 Hunyuan connection: true
- HF cache mount 유지: PASS

## 발견·수정한 버그

1. rasterizer PEP 517 build isolation에서 `No module named 'torch'` 발생.
   - 수정: `pip install --no-build-isolation`로 현재 Torch/CUDA 환경 사용.
2. python-worker에 `SHAPE_API_KEY`가 전달되지 않아 full E2E가 401.
   - 수정: Compose overlay의 worker environment에 동일 키 전달.
3. worker의 Ollama URL이 `host.docker.internal:11435`를 사용해 proxy listen 주소와 불일치.
   - 수정: `http://172.17.0.1:11435/v1` 사용, proxy Bearer와 worker key를 값 노출 없이 동기화.
4. RGB LoadImage 기본 mask가 64×64라 입력 크기와 불일치.
   - 수정: adapter 경계에서 업로드 이미지를 RGBA PNG로 정규화.
5. 6.9GB HF cache가 Docker build context에 포함될 위험.
   - 수정: `.dockerignore`에 `cache` 추가.

## 남은 경고와 제한

- PyTorch wheel은 CUDA arch 8.0–12.0 지원으로 표시하고 GB10은 12.1이라 경고를 출력한다. 실제 CUDA 사용과 80-step 생성은 두 번 성공했고 rasterizer는 12.0+PTX로 빌드됐다.
- `nvidia-resiliency-ext`는 배포판 메타데이터 이름 `pynvml`을 요구한다. 실제 `pynvml` module은 `nvidia-ml-py`가 제공한다. 중복 패키지는 설치하지 않았다.
- `nvidia-cusparselt-cu13` ARM64 platform 경고는 유지했다. Torch/CUDA/driver는 변경하지 않았다.
- Hunyuan 결과는 생성 mesh라 validation grade가 `concept`이다. OpenUSD 구문·parser·mesh·physics/variant gate는 통과했지만 제조 승인 의미는 아니다.
- NVIDIA Content Agents/Omniverse Nucleus 배포는 이 Hunyuan/ComfyUI 작업 범위 밖이며 별도 상태다.

## 재현 명령

```bash
python3 scripts/hy3d_smoke_test.py \
  ../../ComfyUI/input/hy3d_balloon.webp \
  /tmp/hy3d_smoke.glb \
  --token "$SHAPE_API_KEY"
```

운영 endpoint는 host loopback `http://127.0.0.1:8081`; Compose 내부 endpoint는 `http://shape-adapter:8081`이다.
