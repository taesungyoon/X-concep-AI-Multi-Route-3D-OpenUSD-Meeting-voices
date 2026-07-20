# NVIDIA 기술 계층 최종 매핑

| 제안 기술 | 최종 위치 | 적용 판단 |
|---|---|---|
| NeMo Agent Toolkit | Agent Layer | 핵심 도입함. DRF 위에서 도구·워크플로를 오케스트레이션함 |
| NIM | Inference API package | 선택 도입함. 모든 로컬 모델을 NIM으로 강제하지 않음 |
| TensorRT-LLM | LLM optimization/runtime | Gemma 체크포인트 지원 검증 후 전환함 |
| Triton | Multi-model serving | ASR/embedding/reranker/vision 통합 시 적용함 |
| NeMo Retriever | RAG ingestion/extraction | Qdrant 앞의 인제스트 계층으로 적용함 |
| Qdrant | Vector storage/search | 현재 구조에 핵심 적용함 |
| OpenUSD | 3D canonical asset | 핵심 적용함 |
| Omniverse | Review/collaboration/rendering | 핵심 후처리 및 Enterprise 검수에 적용함 |
| Isaac Sim | Physics/robot simulation | OpenUSD 자산이 SimReady 수준일 때 적용함 |
| Cosmos | World/video scenario generation | 선택 확장함 |
| TAO | Vision model training | 공장 카메라 과제에 한정함 |
| DeepStream | Video inference pipeline | 공장 카메라 과제에 한정함 |
| Metropolis | Factory vision architecture | 공장 비전 서비스 확장에 한정함 |
