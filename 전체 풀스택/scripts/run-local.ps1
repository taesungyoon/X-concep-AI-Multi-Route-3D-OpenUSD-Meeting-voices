$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
New-Item -ItemType Directory -Force -Path "$Root\storage\projects" | Out-Null
$PublicStorage = "$Root\frontend-php\public\storage"
if (Test-Path $PublicStorage) { Remove-Item -Recurse -Force $PublicStorage }
New-Item -ItemType Junction -Path $PublicStorage -Target "$Root\storage" | Out-Null
$env:STORAGE_PATH = "$Root\storage"
$env:DB_ENGINE = "sqlite"
Push-Location "$Root\control-plane-drf"
python manage.py migrate --noinput
Pop-Location
Write-Host "아래 명령을 각각 별도 PowerShell에서 실행함"
Write-Host "1) cd $Root\knowledge-service; `$env:QDRANT_URL=':memory:'; uvicorn app.main:app --port 8020"
Write-Host "2) cd $Root\python-worker; `$env:PIPELINE_MODE='mock'; `$env:LLM_MODE='mock'; `$env:OPENAI_IMAGE_MODE='mock'; `$env:HUNYUAN_MODE='mock'; `$env:SPEECH_MODE='mock'; `$env:OPENSCAD_MODE='fallback'; `$env:BLENDER_MODE='fallback'; uvicorn app.main:app --port 8001"
Write-Host "3) cd $Root\agent-layer-nat; `$env:PYTHON_WORKER_URL='http://127.0.0.1:8001'; `$env:KNOWLEDGE_SERVICE_URL='http://127.0.0.1:8020'; uvicorn gateway:app --port 8010"
Write-Host "4) cd $Root\control-plane-drf; `$env:AGENT_GATEWAY_URL='http://127.0.0.1:8010'; `$env:KNOWLEDGE_SERVICE_URL='http://127.0.0.1:8020'; python manage.py runserver 127.0.0.1:8000 --noreload"
Write-Host "5) cd $Root; `$env:CONTROL_PLANE_URL='http://127.0.0.1:8000'; php -S 127.0.0.1:8080 -t frontend-php/public frontend-php/public/router.php"
