# X concep Omniverse WebRTC Client

NVIDIA OV Web RTC Library `6.6.0`의 공식 `StreamType.DIRECT` 계약을 사용하는 TypeScript Client임.

```bash
npm install
npm run build
npm run dev
```

접속 예시임.

```text
http://localhost:5173/?server=192.168.0.20&signalingPort=49100
```

standalone `ovstream` Direct 연결은 signaling port만 명시하며 media port는 SDP/ICE 협상으로 결정함.


서버와 `npm run dev`를 실행한 뒤 실제 브라우저 디코딩까지 검사함.

```bash
E2E_BASE_URL='http://127.0.0.1:5173/?server=127.0.0.1&signalingPort=49100' npm run test:e2e
```

NVIDIA Web SDK와 Kit Runtime의 호환성 매트릭스를 기준으로 버전을 함께 고정해야 함.
