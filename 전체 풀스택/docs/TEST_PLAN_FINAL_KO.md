# 최종 시험 계획

## 현재 패키지에서 자동 검증하는 항목

- Python 소스 compileall임
- PHP 문법 검사임
- DRF SQLite 기반 API unit test임
- 기존 Python Worker mock E2E임
- OpenUSD Parser 재개방임
- Docker Compose YAML parsing임
- ZIP 민감정보 제외 여부임

## 실제 인프라에서 추가 검증할 항목

- MySQL 8.4 마이그레이션·동시성임
- Qdrant 영속화·백업·복구임
- NeMo Agent Toolkit 실제 `nat serve` 실행임
- Gemma 64B vLLM Ray TP/PP 안정성임
- TensorRT-LLM 변환 가능성과 정확도 회귀임
- GPT Image API 실호출 및 원가/Rate Limit임
- Hunyuan3D GPU 실추론임
- NeMo ASR 한국어 정확도와 화자분리임
- Omniverse Kit/Nucleus/WebRTC/Isaac Sim임
- DeepStream RTSP 입력 및 이벤트 전송임
