<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/src/Config.php';
require_once dirname(__DIR__) . '/src/ControlPlaneClient.php';

$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');

try {
    if ($path === '/health') {
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['status' => 'ok', 'service' => 'php-web'], JSON_UNESCAPED_UNICODE);
        exit;
    }
    if (str_starts_with($path, '/api/')) {
        (new ControlPlaneClient(Config::controlPlaneUrl()))->proxy($method, $path);
    }
} catch (Throwable $e) {
    http_response_code(502);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['error' => $e->getMessage()], JSON_UNESCAPED_UNICODE);
    exit;
}
?>

<!doctype html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#07111f">
    <title>X concep AI · Multi-Route 3D Studio</title>
    <link rel="stylesheet" href="/assets/css/app.css">
    <script type="importmap">
    {
      "imports": {
        "three": "/assets/vendor/three/three.module.js",
        "three/addons/": "/assets/vendor/three/addons/"
      }
    }
    </script>
</head>
<body>
<div class="app-shell">
    <header class="topbar">
        <a class="brand" href="/" aria-label="홈">
            <span class="brand-mark">X</span>
            <span><strong>X concep AI</strong><small>Image · Mesh · Structure · OpenUSD</small></span>
        </a>
        <button class="ghost-btn" id="historyButton" type="button">작업 이력</button>
    </header>
    <div class="system-strip" id="systemStrip">
        <span><i></i> GPT Image API</span>
        <span><i></i> Gemma 4 Local · vLLM/Ray</span>
        <span><i></i> Local Speech</span>
        <span><i></i> Hunyuan3D Local</span>
        <span><i></i> OpenSCAD Structure</span>
        <span><i></i> Blender Asset Bridge</span>
        <span><i></i> OpenUSD Layers</span>
        <span><i></i> Omniverse Kit · PhysX · WebRTC</span>
    </div>

    <main class="main-wrap">
        <section class="hero-copy" id="heroCopy">
            <span class="eyebrow">TEXT + IMAGE TO 3D</span>
            <h1>설명하고 이미지를 넣으면<br><em>2D 비교부터 3D까지</em> 생성함</h1>
            <p>복잡한 설계 메뉴 없이 원하는 장비·모듈·부품을 입력하고 결과만 확인하면 됨</p>
        </section>

        <nav class="stepper" aria-label="생성 단계">
            <button class="step active" data-step="1"><span>1</span><b>입력</b><small>프롬프트·이미지</small></button>
            <i></i>
            <button class="step" data-step="2"><span>2</span><b>2D 비교</b><small>원하는 안 선택</small></button>
            <i></i>
            <button class="step" data-step="3"><span>3</span><b>3D 결과</b><small>렌더링·다운로드</small></button>
        </nav>

        <section class="stage active" id="stageInput">
            <div class="mode-switch" role="tablist" aria-label="입력 모드">
                <button class="mode-btn active" id="promptModeButton" type="button" data-input-mode="prompt">직접 입력</button>
                <button class="mode-btn" id="meetingModeButton" type="button" data-input-mode="meeting">회의 음성 분석</button>
            </div>
            <div id="promptModePanel">
            <form class="generate-card" id="generateForm">
                <div class="panel prompt-panel">
                    <div class="panel-heading">
                        <div><span class="number-chip">01</span><h2>만들고 싶은 것을 설명함</h2></div>
                        <span class="optional">필수</span>
                    </div>
                    <textarea id="promptInput" name="prompt" maxlength="1600" required placeholder="예: 스마트폰 디스플레이 FPCB 끝단을 90도로 접는 단일 벤딩 유닛. 서보모터 구동, 투명 안전커버, 작업자가 전면에서 투입하는 구조로 설계함"></textarea>
                    <div class="prompt-footer"><button type="button" class="example-btn" data-example="자동화 설비 프레임 내부에 소형 컨베이어와 비전 카메라가 설치된 검사 장비. 전면 투명 안전 도어와 우측 제어반을 포함함">예시 입력</button><span id="charCount">0 / 1600</span></div>
                </div>

                <div class="panel upload-panel">
                    <div class="panel-heading">
                        <div><span class="number-chip">02</span><h2>참고 이미지를 추가함</h2></div>
                        <span class="optional">선택 · 최대 4장</span>
                    </div>
                    <label class="dropzone" id="dropzone">
                        <input id="imageInput" name="images[]" type="file" accept="image/png,image/jpeg,image/webp" multiple hidden>
                        <span class="upload-icon">＋</span>
                        <strong>이미지를 여기에 놓거나 선택함</strong>
                        <small>JPG · PNG · WEBP / 장당 12MB 이하</small>
                    </label>
                    <div class="upload-preview" id="uploadPreview"></div>
                </div>

                <div class="panel type-panel">
                    <div class="panel-heading compact"><div><span class="number-chip">03</span><h2>생성 유형을 선택함</h2></div></div>
                    <div class="type-grid">
                        <label class="type-card selected"><input type="radio" name="category" value="equipment" checked><span>설비</span><small>자동화 장비·검사기</small></label>
                        <label class="type-card"><input type="radio" name="category" value="module"><span>모듈</span><small>구동부·작업 유닛</small></label>
                        <label class="type-card"><input type="radio" name="category" value="part"><span>부품</span><small>브래킷·지그·커버</small></label>
                    </div>
                </div>

                <div class="panel goal-panel">
                    <div class="panel-heading compact"><div><span class="number-chip">04</span><h2>원하는 결과를 선택함</h2></div><span class="optional">기본값 · 자동 추천</span></div>
                    <div class="goal-grid" id="goalGrid">
                        <label class="goal-card selected"><input type="radio" name="output_goal" value="auto" checked><strong>자동 추천</strong><small>요구사항에 맞는 생성 경로를 자동 조합함</small></label>
                        <label class="goal-card"><input type="radio" name="output_goal" value="fast"><strong>빠른 3D</strong><small>이미지 기반 외형을 빠르게 확인함</small></label>
                        <label class="goal-card"><input type="radio" name="output_goal" value="structural"><strong>구조 중심 3D</strong><small>치수·프레임·브래킷 구조를 우선함</small></label>
                        <label class="goal-card"><input type="radio" name="output_goal" value="high_quality"><strong>고품질 3D</strong><small>Blender 재질·조명·렌더링을 적용함</small></label>
                        <label class="goal-card"><input type="radio" name="output_goal" value="motion_openusd"><strong>동작·OpenUSD</strong><small>Omniverse 검토 가능한 USD 자산을 준비함</small></label>
                    </div>
                    <details class="advanced-settings">
                        <summary>고급 설정</summary>
                        <div class="advanced-grid">
                            <label>품질 프로필<select name="quality_profile" id="qualityProfile"><option value="preview">Preview</option><option value="standard" selected>Standard</option><option value="final">Final</option></select></label>
                            <label>엔진 직접 선택<select name="engine_override" id="engineOverride"><option value="">자동 라우팅</option><option value="hunyuan3d">Hunyuan3D</option><option value="openscad">OpenSCAD</option><option value="blender">Blender</option><option value="hybrid">Hybrid</option></select></label>
                        </div>
                    </details>
                </div>

                <button class="primary-btn generate-btn" type="submit"><span>2D 컨셉 생성</span><b>→</b></button>
            </form>
            </div>

            <section class="meeting-workspace" id="meetingModePanel" hidden>
                <div class="meeting-head">
                    <div><span class="eyebrow">LOCAL MEETING AGENT</span><h2>회의 내용을 듣고 설계 요구사항을 정리함</h2><p>음성은 로컬 STT와 Gemma vLLM/Ray에서 처리하고, 분석 결과만 2D·3D 생성 파이프라인에 연결함</p></div>
                    <span class="meeting-live" id="meetingLiveBadge">대기</span>
                </div>
                <div class="meeting-grid">
                    <div class="panel meeting-record-panel">
                        <div class="panel-heading"><div><span class="number-chip">01</span><h2>회의 음성을 수집함</h2></div><span class="optional">15초 단위 로컬 처리</span></div>
                        <div class="record-controls">
                            <button class="record-btn" id="startMeetingButton" type="button"><i></i> 회의 시작</button>
                            <button class="ghost-btn" id="stopMeetingButton" type="button" disabled>회의 종료</button>
                            <span class="record-time" id="recordTime">00:00</span>
                        </div>
                        <div class="audio-level"><span id="audioLevelBar"></span></div>
                        <label class="field-label" for="meetingCategory">생성 유형</label>
                        <select id="meetingCategory" class="meeting-select"><option value="equipment">설비</option><option value="module">모듈</option><option value="part">부품</option></select>
                        <label class="field-label" for="meetingOutputGoal">원하는 결과</label>
                        <select id="meetingOutputGoal" class="meeting-select"><option value="auto">자동 추천</option><option value="fast">빠른 3D</option><option value="structural">구조 중심 3D</option><option value="high_quality">고품질 3D</option><option value="motion_openusd">동작·OpenUSD</option></select>
                        <div class="meeting-note">브라우저 마이크 권한이 필요하며, 실제 운영에서는 faster-whisper 또는 NVIDIA Speech NIM 로컬 모드로 전환함</div>
                    </div>

                    <div class="panel transcript-panel">
                        <div class="panel-heading"><div><span class="number-chip">02</span><h2>준실시간 전사 내용을 확인함</h2></div><span class="optional" id="transcriptProvider">STT 대기</span></div>
                        <div class="transcript-stream" id="transcriptStream"><div class="empty-transcript">회의를 시작하거나 내용을 직접 입력함</div></div>
                        <textarea id="manualTranscript" class="manual-transcript" maxlength="30000" placeholder="마이크를 사용할 수 없는 경우 회의 내용을 직접 입력할 수 있음"></textarea>
                    </div>

                    <div class="panel meeting-analysis-panel">
                        <div class="panel-heading"><div><span class="number-chip">03</span><h2>Gemma가 요구사항을 구조화함</h2></div><span class="optional">vLLM · Ray</span></div>
                        <div class="analysis-cards" id="meetingAnalysisCards">
                            <div class="analysis-empty">회의 내용을 분석하면 확정 요구사항, 치수, 변경사항, 미확정 항목이 표시됨</div>
                        </div>
                        <div class="meeting-actions">
                            <button class="ghost-btn" id="analyzeMeetingButton" type="button">현재 내용 분석</button>
                            <button class="primary-btn" id="generateMeeting2dButton" type="button" disabled>분석 결과로 2D 생성 →</button>
                        </div>
                    </div>
                </div>
                <div class="omniverse-capability-row">
                    <span>OpenUSD Layers</span><span>Kit SDK</span><span>RTX/WebRTC</span><span>Nucleus</span><span>Live Session</span><span>PhysX</span><span>Asset Validator</span>
                </div>
            </section>
        </section>

        <section class="stage" id="stageCompare">
            <div class="stage-title"><div><span class="eyebrow">STEP 2</span><h2>원하는 2D 컨셉을 선택함</h2><p>선택한 이미지를 기준으로 3D를 생성하므로 외형과 구성을 먼저 비교함</p></div><button class="ghost-btn" id="editPromptButton">입력 수정</button></div>
            <div class="compare-grid" id="compareGrid"></div>
            <div class="sticky-actions"><span id="selectionGuide">한 가지 안을 선택해야 함</span><button class="primary-btn" id="generate3dButton" disabled>선택한 안으로 3D 생성 <b>→</b></button></div>
        </section>

        <section class="stage" id="stageResult">
            <div class="stage-title"><div><span class="eyebrow">STEP 3</span><h2>3D 렌더링 결과임</h2><p>마우스 또는 손가락으로 회전하고 필요한 파일을 내려받을 수 있음</p></div><button class="ghost-btn" id="newProjectButton">새로 만들기</button></div>
            <div class="result-layout">
                <div class="viewer-card">
                    <div class="viewer-toolbar"><span><i class="online-dot"></i> 3D VIEWER</span><div><button data-view="iso">ISO</button><button data-view="front">FRONT</button><button data-view="top">TOP</button><button id="fullscreenButton">전체화면</button></div></div>
                    <div id="viewer3d" class="viewer3d"><div class="viewer-placeholder"><span class="cube-loader"></span><strong>3D 모델 준비 중</strong></div></div>
                    <div class="viewer-help">드래그: 회전 · 휠/핀치: 확대 · 우클릭: 이동</div>
                </div>
                <aside class="result-side">
                    <div class="selected-reference"><span class="section-label">선택한 2D 기준 이미지</span><img id="selectedReference" alt="선택된 2D 이미지"></div>
                    <div class="result-summary"><span class="section-label">생성 내용</span><h3 id="resultTitle">3D 설계 결과</h3><p id="resultPrompt"></p><div class="result-tags" id="resultTags"></div></div>
                    <div class="route-panel">
                        <span class="section-label">생성 결과 선택</span>
                        <div class="route-tabs" id="routeTabs"></div>
                    </div>
                    <div class="validation-panel" id="validationPanel">
                        <div class="validation-head"><span class="section-label">검증 수준</span><strong id="validationGrade">컨셉 검토 가능</strong></div>
                        <div class="validation-score"><span id="validationScoreBar"></span></div>
                        <p id="validationScope">결과 검증 정보를 준비하고 있음</p>
                        <button class="mini-btn" id="validationDetailsButton" type="button">검증 상세 보기</button>
                        <div class="validation-details" id="validationDetails" hidden></div>
                    </div>
                    <div class="regenerate-panel">
                        <span class="section-label">다른 방식으로 재생성</span>
                        <div class="regenerate-actions">
                            <button type="button" data-regenerate-goal="fast">더 빠르게 생성</button>
                            <button type="button" data-regenerate-goal="structural">구조를 정확하게 재생성</button>
                            <button type="button" data-regenerate-goal="high_quality">더 사실적으로 재생성</button>
                            <button type="button" data-regenerate-goal="motion_openusd">동작·OpenUSD로 확장</button>
                        </div>
                    </div>
                    <div class="download-panel"><span class="section-label">파일 다운로드</span><a class="download-btn primary" id="downloadGlb" download>GLB <small>웹 3D 뷰어</small></a><a class="download-btn" id="downloadStl" download>STL <small>메시 출력</small></a><a class="download-btn" id="downloadScad" download hidden>SCAD <small>파라메트릭 구조 코드</small></a><a class="download-btn" id="downloadGeometryJson" download hidden>Geometry JSON <small>공통 구조 데이터</small></a><a class="download-btn" id="downloadBlenderScript" download hidden>Blender Script <small>후처리·재현 코드</small></a><a class="download-btn" id="downloadUsda" download>OpenUSD · USDA <small>Omniverse 연계</small></a><a class="download-btn" id="downloadUsdc" download hidden>OpenUSD · USDC <small>Binary Stage</small></a><a class="download-btn" id="downloadUsdRoot" download hidden>OpenUSD Package <small>Layered root.usda</small></a><a class="download-btn" id="downloadUsdManifest" download hidden>USD Manifest <small>Kit·Nucleus 연동 정보</small></a><a class="download-btn" id="downloadRender" download>PNG <small>렌더링 이미지</small></a><button class="download-btn omniverse-launch" id="openOmniverseButton" type="button">Omniverse RTX <small>Kit WebRTC Viewer</small></button></div>
                </aside>
            </div>
        </section>

        <section class="history-drawer" id="historyDrawer" aria-hidden="true">
            <div class="drawer-backdrop" data-close-history></div>
            <div class="drawer-panel"><div class="drawer-head"><div><span class="eyebrow">MY PROJECTS</span><h2>작업 이력</h2></div><button class="icon-btn" data-close-history>×</button></div><div class="history-list" id="historyList"></div></div>
        </section>
    </main>
</div>

<div class="loading-overlay" id="loadingOverlay" aria-hidden="true"><div class="loading-card"><div class="progress-ring"><span id="loadingPercent">0%</span></div><h2 id="loadingTitle">생성 준비 중</h2><p id="loadingMessage">입력 내용을 분석하고 있음</p><div class="loading-steps"><span class="active">요구사항 분석</span><span>2D 생성</span><span>결과 정리</span></div></div></div>
<div class="toast" id="toast"></div>
<script type="module" src="/assets/js/app.js"></script>
</body>
</html>
