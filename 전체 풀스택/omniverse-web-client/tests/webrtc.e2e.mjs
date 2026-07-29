import { chromium } from '/home/theengineer/fine-tuning/Xconcep-AI-Multi-Route-3D-OpenUSD-Meeting-voices/전체 풀스택/omniverse-web-client/node_modules/playwright/index.mjs';

const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173/?server=127.0.0.1&signalingPort=49100';
const browser = await chromium.launch({
  executablePath: '/home/theengineer/fine-tuning/.runtime/playwright/chromium-1193/chrome-linux/chrome',
  headless: true,
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--autoplay-policy=no-user-gesture-required',
    '--enable-logging=stderr',
  ],
});
const page = await browser.newPage();
const messages = [];
page.on('console', (message) => messages.push(`[console:${message.type()}] ${message.text()}`));
page.on('pageerror', (error) => messages.push(`[pageerror] ${error.stack || error}`));

let result;
try {
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => {
    const video = document.querySelector('#stream-video');
    return video && video.videoWidth > 0 && video.videoHeight > 0 && video.currentTime > 0;
  }, undefined, { timeout: 45_000 });
  await page.waitForTimeout(2_000);
  result = await page.locator('#stream-video').evaluate((video) => ({
    videoWidth: video.videoWidth,
    videoHeight: video.videoHeight,
    currentTime: video.currentTime,
    readyState: video.readyState,
    paused: video.paused,
    tracks: video.srcObject
      ? video.srcObject.getTracks().map((track) => ({
          kind: track.kind,
          enabled: track.enabled,
          muted: track.muted,
          readyState: track.readyState,
        }))
      : [],
  }));
  await page.screenshot({ path: '.e2e-artifacts/webrtc.png', fullPage: true });
  console.log(JSON.stringify({ ok: true, result, messages }, null, 2));
} catch (error) {
  result = await page.locator('#stream-video').evaluate((video) => ({
    videoWidth: video.videoWidth,
    videoHeight: video.videoHeight,
    currentTime: video.currentTime,
    readyState: video.readyState,
    paused: video.paused,
    tracks: video.srcObject
      ? video.srcObject.getTracks().map((track) => ({
          kind: track.kind,
          enabled: track.enabled,
          muted: track.muted,
          readyState: track.readyState,
        }))
      : [],
  })).catch(() => null);
  await page.screenshot({ path: '.e2e-artifacts/webrtc-failed.png', fullPage: true }).catch(() => undefined);
  console.error(JSON.stringify({ ok: false, error: String(error), result, messages }, null, 2));
  process.exitCode = 1;
} finally {
  await browser.close();
}
