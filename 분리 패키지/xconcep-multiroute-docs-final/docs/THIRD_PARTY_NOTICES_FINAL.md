# 제3자 구성요소 확인사항

본 파일은 법률 의견이 아니며 운영·배포 전 각 제품의 최신 라이선스와 계약 조건을 확인해야 함.

| 구성요소 | 적용 위치 | 확인사항 |
|---|---|---|
| NVIDIA NeMo Agent Toolkit | Agent Plugin·Runtime Profile | Apache-2.0 계열 공개 저장소와 설치 Package 조건 확인함 |
| NVIDIA NeMo Retriever Library | 선택 문서 추출 Profile | 26.5 Package·NVIDIA NIM 및 모델별 조건 확인함 |
| NVIDIA NeMo Toolkit ASR | 로컬 회의 전사·Diarization | Model Card와 Weight License를 별도 확인함 |
| NVIDIA NIM | LLM·Embedding·Speech 선택 Profile | NVIDIA AI Enterprise 또는 NIM별 사용 조건 확인함 |
| TensorRT-LLM | 선택 LLM Runtime | 공개 저장소 License와 모델 License를 함께 확인함 |
| Triton Inference Server | 선택 Model Serving | BSD 계열 공개 저장소와 NVIDIA Container 조건 확인함 |
| OpenUSD | 3D Layer·USDA·USDC | Apache-2.0 License 확인함 |
| NVIDIA Omniverse Kit / Nucleus | RTX·검수·협업 | NGC·Enterprise 지원·배포 조건 확인함 |
| NVIDIA Isaac Sim | 선택 Simulation | NVIDIA Omniverse License와 지원 Matrix 확인함 |
| NVIDIA Cosmos | 선택 Physical AI Scenario | Model·Weight·Dataset별 License 확인함 |
| DeepStream / Metropolis / TAO | 선택 Factory Vision | SDK·Model·Container별 조건 확인함 |
| Qdrant | Vector DB | Apache-2.0 공개 서버·Client 확인함 |
| TripoSR | 로컬 이미지 기반 3D 생성 | 코드·모델 MIT License 확인함 |
| Hunyuan3D 2.0/2.1 | 미채택 | 대한민국이 라이선스 허용 지역에 포함되지 않아 운영 스택에서 제외함 |
| GPT Image API | 외부 2D 생성 | OpenAI 이용약관·데이터 처리·과금 정책 확인함 |
| Three.js | Web GLB Viewer | MIT License 확인함 |
| Django / DRF / FastAPI | Web·API | 각 BSD/MIT License 확인함 |

NeMo Retriever의 NVIDIA 검증 기본 VDB는 LanceDB이며, 본 전달본의 Qdrant 경로는 사용자 정의 Adapter임. 해당 Adapter의 정확도·성능·호환성은 운영자가 검증함.
