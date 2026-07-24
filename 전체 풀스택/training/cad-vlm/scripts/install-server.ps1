$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$pythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$torchIndex = if ($env:PYTORCH_INDEX_URL) { $env:PYTORCH_INDEX_URL } else { "https://download.pytorch.org/whl/cu124" }
& $pythonBin -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel
& .\.venv\Scripts\python.exe -m pip install torch torchvision --index-url $torchIndex
& .\.venv\Scripts\python.exe -m pip install -e ".[train,test]"
if (Test-Path .\bundle-manifest.json) {
    & .\.venv\Scripts\python.exe scripts\verify_install.py
}
& .\.venv\Scripts\python.exe scripts\check_server.py
& .\.venv\Scripts\python.exe scripts\validate_dataset.py --dataset data\examples
& .\.venv\Scripts\python.exe -m pip freeze | Set-Content -Encoding UTF8 environment.freeze.txt
Write-Host "Installation complete. Activate with: .\.venv\Scripts\Activate.ps1"
