import {
  AppStreamer,
  LogLevel,
  StreamType,
  type StreamEvent,
  type StreamProps,
} from '@nvidia/ov-web-rtc';

const status = document.getElementById('status') as HTMLSpanElement;
const params = new URLSearchParams(location.search);
const server = params.get('server') || location.hostname;
const signalingPort = Number(params.get('signalingPort') || '49100');
const mediaPort = Number(params.get('mediaPort') || '47998');
const accessToken = params.get('accessToken') || '';

function updateStatus(message: string): void {
  status.textContent = message;
}

async function connect(): Promise<void> {
  updateStatus(`${server}:${signalingPort} 연결 중`);
  const props: StreamProps = {
    streamSource: StreamType.DIRECT,
    logLevel: LogLevel.WARN,
    streamConfig: {
      server,
      signalingPort,
      mediaPort,
      videoElementId: 'stream-video',
      audioElementId: 'stream-audio',
      width: 1920,
      height: 1080,
      fps: 60,
      fitStreamResolution: true,
      nativeTouchEvents: true,
      authenticate: Boolean(accessToken),
      accessToken: accessToken || undefined,
      onStart: (_message: StreamEvent) => updateStatus('RTX 스트림 연결됨'),
      onStop: (_message: StreamEvent) => updateStatus('스트림 종료됨'),
      onTerminate: (_message: StreamEvent) => updateStatus('세션 종료됨'),
      onUpdate: (message: StreamEvent) => console.debug('Omniverse update', message),
      onCustomEvent: (message) => console.debug('Kit message', message),
    },
  };

  try {
    await AppStreamer.connect(props);
  } catch (error) {
    updateStatus(`연결 실패: ${String(error)}`);
    console.error(error);
  }
}

window.addEventListener('beforeunload', () => {
  void AppStreamer.terminate(false).catch(() => undefined);
});

void connect();
