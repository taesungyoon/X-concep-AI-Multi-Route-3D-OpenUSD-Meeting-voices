# 운영 배포 체크리스트

## 보안

- [ ] HTTPS·HSTS 적용함
- [ ] SSO 또는 계정 인증 적용함
- [ ] Company Tenant Query Filter 적용함
- [ ] Download Signed URL 적용함
- [ ] OpenAI Key Secret Manager 저장함
- [ ] 내부 GPU·DB Port 비공개 적용함
- [ ] 회의 녹음 동의 UI 적용함
- [ ] 회의 음성·Transcript 보존·파기 정책 적용함

## 데이터

- [ ] MySQL Backup·복구 Drill 수행함
- [ ] Qdrant Snapshot 수행함
- [ ] Storage Virus·MIME Scan 적용함
- [ ] 고객 Prompt 외부 전송 범위 승인함

## GPU

- [ ] vLLM TP·PP와 Ray Resource 일치함
- [ ] LLM TTFT·TPS·OOM 검증함
- [ ] Hunyuan3D VRAM·Queue 검증함
- [ ] Speech ASR 실회의 WER 평가함
- [ ] GPU Job Queue·Timeout·Retry 적용함

## NVIDIA Runtime

- [ ] NAT Plugin 설치·`nat validate` 수행함
- [ ] NeMo Retriever 추출 정확도 평가함
- [ ] Embedding NIM Dimension과 Qdrant Collection 일치함
- [ ] OpenUSD Asset Validator 통과함
- [ ] Nucleus ACL·TLS 확인함
- [ ] WebRTC TURN/STUN 확인함
- [ ] Isaac Sim 대상 Asset만 별도 SimReady 처리함

## 제품 문구

- [ ] Mesh 기반 Pre-CAD 결과로 표시함
- [ ] STEP·정밀 제조 CAD 자동 생성으로 과대 표현하지 않음
- [ ] AI 추정 치수와 사용자 확정 치수를 구분함
