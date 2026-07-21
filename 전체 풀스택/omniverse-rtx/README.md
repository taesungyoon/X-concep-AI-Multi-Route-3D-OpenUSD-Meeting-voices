# X concep AI Omniverse RTX Runtime

Windows 네이티브 `ovrtx` 렌더러와 `ovstream` WebRTC 서버임. 브라우저는 영상과 입력만 담당하며 USD를 Three.js/WebGL로 렌더링하지 않음.

## 실행

저장소 경로에 한글이 포함되어 있으므로 NVIDIA 네이티브 런타임과 캐시는 저장소 루트의 ASCII 이름 디렉터리를 사용함.

```powershell
.\전체 풀스택\scripts\setup-omniverse-rtx.ps1
.\전체 풀스택\scripts\run-omniverse-rtx.ps1 -ValidateOnly -Width 640 -Height 360
.\전체 풀스택\scripts\run-omniverse-rtx.ps1
```

서버 준비 확인은 `http://127.0.0.1:8011/healthz`, WebRTC 시그널링은 `127.0.0.1:49100`임. `/healthz`는 실제 `LdrColor` 프레임을 RGBA에서 BGRA CUDA 버퍼로 변환하고 WebRTC 서버를 시작한 뒤에만 200을 반환함.

생성한 USDA는 별도 `pxr` subprocess에서 먼저 파싱한 뒤 ovrtx 프로세스가 로드함. 검증 프레임은 `.omniverse-runtime/first-frame.png`, RTX 로그는 `.omniverse-runtime/ovrtx.log`에 저장함. 렌더러는 한 스레드의 단일 루프만 `renderer.step()`을 호출하고 종료 시 `server.stop()`, `ovstream.shutdown()`, `renderer.destroy()`를 순서대로 실행함.
