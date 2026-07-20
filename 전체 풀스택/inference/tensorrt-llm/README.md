# TensorRT-LLM Migration Path

TensorRT-LLM은 vLLM과 병렬로 무조건 중복 배치하는 계층이 아님. 사용자 보유 Gemma 커스텀 체크포인트가 지원되는지 먼저 확인한 뒤 엔진 빌드·정확도·처리량 검증을 통과할 경우에만 전환함.

권장 순서: vLLM/Ray 기준 성능 확보 -> TensorRT-LLM 엔진 PoC -> Triton 또는 `trtllm-serve` 배포 -> NIM 패키징 검토임.
