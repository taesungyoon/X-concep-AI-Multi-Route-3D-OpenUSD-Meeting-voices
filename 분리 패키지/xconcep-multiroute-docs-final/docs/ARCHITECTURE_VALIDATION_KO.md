# 업로드 자료 기반 아키텍처 검증 결과

## 자료에서 확인된 제품 범위

- 소개서는 X concep AI를 요구사항 -> 2D/3D/Proposal/Six-View로 연결되는 Pre-CAD 제조 Workflow Agent로 정의함.
- 소개서 자체가 현재 STL을 Mesh 기반 결과로 명시하고 Parametric CAD와 제조 Feature는 향후 확장이라고 구분함.
- NVIDIA 전략 자료는 PHP/DRF/MySQL을 유지하면서 NeMo Agent Toolkit/NIM, Qdrant, OpenUSD/Omniverse를 단계적으로 추가하는 방향을 제시함.

## 기존 전달본과의 차이

기존 전달본은 PHP + Python Worker + Hunyuan3D + OpenUSD/Omniverse + 회의 음성 분석은 구현했으나, DRF/MySQL/Qdrant/NeMo Agent Toolkit/NeMo Retriever 계층이 없어서 제시된 최종 아키텍처와 완전히 일치하지 않았음.

## 수정된 최종 구조

1. PHP는 사용자 UI와 Gateway 역할만 수행함.
2. DRF가 Project/Job/Asset/Meeting API를 소유함.
3. MySQL은 거래·Job·프로젝트 상태를 저장함.
4. Qdrant는 과거 프롬프트, 회의 요구사항, 2D/3D 자산 메타데이터 검색을 담당함.
5. NeMo Agent Toolkit은 도구 호출과 Agent Workflow를 담당하며 DRF를 대체하지 않음.
6. vLLM/Ray는 사용자 보유 Gemma 커스텀 체크포인트의 기본 서빙 경로임.
7. TensorRT-LLM/Triton/NIM은 동일한 병렬 계층이 아니라 최적화 엔진, 모델 서버, 패키지/API 계층으로 구분함.
8. OpenUSD/Omniverse가 3D 자산화의 핵심이며 실제 물리는 Isaac Sim이 담당함.
9. Cosmos는 멀티뷰/비디오/월드 시나리오가 필요한 과제에 한정함.
10. Metropolis/DeepStream/TAO는 공장 영상 입력이 필요한 확장 프로파일임.

## 제품 표현상 수정

현재 Hunyuan3D/STL 출력은 Mesh 기반 Pre-CAD 컨셉임. STEP/B-Rep/공차/제조 Feature가 없는 상태에서 `제작 가능한 상세 설계`로 단정하지 않고 `제조 요구사항을 반영한 Pre-CAD 컨셉 및 후속 CAD 연계 자산`으로 표현해야 함.
