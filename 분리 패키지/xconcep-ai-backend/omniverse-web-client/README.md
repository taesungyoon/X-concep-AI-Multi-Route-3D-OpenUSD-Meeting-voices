# X concep Omniverse WebRTC Client

NVIDIA OV Web RTC Library `6.4.4`의 공식 `StreamType.DIRECT` 계약을 사용하는 TypeScript Client임.

```bash
npm install
npm run build
npm run dev
```

접속 예시임.

```text
http://localhost:5173/?server=192.168.0.20&signalingPort=49100&mediaPort=47998
```

Reverse Proxy에서 JWT 인증을 적용한 경우 `accessToken` Query 값을 전달할 수 있으나, 운영 환경에서는 URL Query에 장기 토큰을 직접 노출하지 않고 단기 세션 토큰 발급 API를 적용해야 함.

NVIDIA Web SDK와 Kit Runtime의 호환성 매트릭스를 기준으로 버전을 함께 고정해야 함.
