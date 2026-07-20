# X concep AI Multi-Route 최종 테스트 보고서

## 1. 정적 검증

- Python Worker·DRF·Agent·Knowledge Compile을 통과함
- PHP 전체 문법 검사를 통과함
- JavaScript 문법 검사를 통과함
- Docker Compose와 Agent YAML Parsing을 통과함

## 2. 자동 테스트

| 영역 | 결과 |
|---|---|
| Python Worker | 11 passed, 1 optional skipped임 |
| Django REST Framework | 2 passed임 |
| Agent Gateway | 1 passed임 |
| Knowledge Service | 2 passed임 |

Optional Skip은 실제 NeMo Diarization Runtime이 없는 환경의 선택 테스트임.

## 3. Mock End-to-End

실제 Uvicorn·Django·PHP 서버를 로컬에서 기동하여 검증함.

- PHP Web Health 통과함
- DRF·Agent·Worker·Knowledge Health 통과함
- 프롬프트 프로젝트 생성 통과함
- 2D 설계안 4개 생성 통과함
- 자동 Route로 Fast·Structural·High Quality 3개 자산 생성 통과함
- Active Asset이 High Quality로 선택됨을 확인함
- Validation Grade가 Validated로 생성됨을 확인함
- 검증 점수 0.821을 확인함
- GLB를 Trimesh로 재개방하고 19개 Geometry를 확인함
- OpenUSD Root Stage를 재개방하고 22개 Prim과 6개 Layer Stack을 확인함
- 회의 WAV Chunk 업로드와 Transcript 누적을 확인함
- 회의 분석에서 폭 900 mm를 구조화함
- 높이 미확정 항목을 별도로 분리함
- 회의 내용 기반 2D 4안 생성을 확인함

## 4. 미검증 항목

- 실제 GPT Image API 호출은 API Key가 없어 미검증임
- 실제 Gemma GPU Checkpoint·vLLM·Ray Multi-Node는 미검증임
- 실제 Hunyuan3D GPU 생성 품질·동시 처리량은 미검증임
- Native OpenSCAD와 Blender Binary 실행은 전달 환경에서 미검증임
- NeMo ASR·Speech NIM·NeMo Diarization 실제 Model은 미검증임
- Omniverse Kit·Nucleus·WebRTC·PhysX 실제 Runtime은 미검증임
- Docker Image Build 자체는 현재 환경의 Docker Engine 부재로 미검증임

## 5. 판정

PoC·사내 통합 개발·고객 시연 기준 코드로 승인함. 인터넷 공개 운영은 인증·Tenant·비동기 GPU Queue·실모델 부하 시험·라이선스 검토 완료 후 승인하는 조건임.
