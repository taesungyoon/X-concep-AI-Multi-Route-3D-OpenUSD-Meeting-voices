# Metropolis / DeepStream / TAO Optional Layer

이 계층은 Prompt-to-3D 핵심 경로가 아니라 실제 공장 카메라 입력, 안전 이벤트, 설비 상태 인식이 필요한 확장 프로파일임.

- TAO: 현장 데이터로 비전 모델 파인튜닝/최적화함
- DeepStream: RTSP 영상 추론 파이프라인과 이벤트 전송을 담당함
- Metropolis: 비전 AI 애플리케이션·분석 아키텍처를 구성함
- DRF `/api/vision/events`: 이벤트 수신 경계임
