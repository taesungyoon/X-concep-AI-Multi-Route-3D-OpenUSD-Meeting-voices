# Omniverse Kit 배포 매뉴얼

## 1. 전제

본 저장소에는 NVIDIA Omniverse Kit SDK Runtime·NGC Container 자체를 포함하지 않음. 운영자가 NVIDIA 계정·NGC 접근권한·GPU Driver에 맞는 Kit App Base Image를 준비해야 함.

## 2. Kit App Template 적용

1. Kit App Template 프로젝트를 생성함
2. 아래 파일을 Template 프로젝트에 복사함

```text
omniverse-kit/apps/xconcep.meeting_review.kit
omniverse-kit/source/extensions/xconcep.meeting.review/
```

3. Extension Folder가 `.kit` 파일의 `settings.app.exts.folders`에 포함됐는지 확인함
4. Kit App을 빌드·실행함

## 3. Docker Compose 선택 서비스

`.env`에 운영자가 빌드한 Kit App Image를 지정함.

```env
OMNIVERSE_KIT_IMAGE=registry.local/xconcep-meeting-review:1.0.0
```

```bash
docker compose -f docker-compose.yml -f docker-compose.omniverse.yml up -d
```

## 4. Stage 열기

생성 결과의 `result/openusd/manifest.json` 경로를 Extension UI에서 지정함. Extension이 Manifest의 `root` 경로를 읽어 Stage를 오픈함.

## 5. Nucleus 게시

Kit Python 환경에서 실행함.

```bash
python omniverse-kit/scripts/publish_nucleus.py \
  --local_folder storage/projects/PRJ-ID/result/openusd \
  --nucleus_folder omniverse://SERVER/Projects/Xconcep/PRJ-ID
```

## 6. WebRTC

- Kit App에 Livestream Extension이 활성화되어야 함
- UDP/TCP Port, NAT, TURN/STUN을 운영망에 맞게 구성해야 함
- 브라우저 Client는 `omniverse-web-client`를 빌드하여 사용함
- 사용자별 동시 Session은 GPU Memory·Encoder Session을 기준으로 Capacity Test가 필요함

## 7. 검증 항목

- Stage Default Prim 존재함
- Z-Up·metersPerUnit 확인함
- 모든 Sublayer 경로가 해석됨
- Mesh Bounding Box가 정상임
- Material·Texture 경로가 존재함
- PhysicsScene·Collision API가 열림
- Nucleus URI 권한이 정상임
- WebRTC ICE 연결과 입력 이벤트가 정상임
