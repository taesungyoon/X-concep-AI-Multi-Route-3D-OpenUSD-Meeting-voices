param(
    [string]$ToolRoot = '',
    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'
$fullStackRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$repoRoot = Split-Path -Parent $fullStackRoot
if (-not $ToolRoot) { $ToolRoot = Join-Path $repoRoot '.native-tools' }
$downloadRoot = Join-Path $ToolRoot 'downloads'

$tools = @(
    [ordered]@{
        Name = 'Blender'
        Version = '5.2.0 LTS'
        Url = 'https://download.blender.org/release/Blender5.2/blender-5.2.0-windows-x64.zip'
        Sha256 = '2d184b626c001692c362291911293b6a297179d618d95e9e9192c3a80318adc4'
        Archive = Join-Path $downloadRoot 'blender-5.2.0-windows-x64.zip'
        Executable = Join-Path $ToolRoot 'blender-5.2.0-windows-x64\blender.exe'
    },
    [ordered]@{
        Name = 'OpenSCAD'
        Version = '2021.01'
        Url = 'https://files.openscad.org/OpenSCAD-2021.01-x86-64.zip'
        Sha256 = 'fb0caabf5bbc89f8f2f80c10b79ae64d697aaff6efd58b2756f5d6270edb7ba7'
        Archive = Join-Path $downloadRoot 'OpenSCAD-2021.01-x86-64.zip'
        Executable = Join-Path $ToolRoot 'openscad-2021.01\openscad.com'
    }
)

function Assert-ArchiveHash([hashtable]$Tool) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Tool.Archive).Hash.ToLowerInvariant()
    if ($actual -ne $Tool.Sha256) {
        throw "$($Tool.Name) SHA-256 mismatch. Expected $($Tool.Sha256), got $actual"
    }
}

if (-not $VerifyOnly) {
    New-Item -ItemType Directory -Force -Path $ToolRoot, $downloadRoot | Out-Null
    foreach ($tool in $tools) {
        if (-not (Test-Path -LiteralPath $tool.Archive)) {
            Write-Host "Downloading $($tool.Name) $($tool.Version) from the official release server"
            & curl.exe -L --fail --output $tool.Archive $tool.Url
            if ($LASTEXITCODE -ne 0) { throw "$($tool.Name) download failed" }
        }
        Assert-ArchiveHash $tool
        if (-not (Test-Path -LiteralPath $tool.Executable)) {
            Write-Host "Extracting $($tool.Name)"
            Expand-Archive -LiteralPath $tool.Archive -DestinationPath $ToolRoot -Force
        }
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $ToolRoot 'blender-5.2.0-windows-x64\portable') | Out-Null
}

foreach ($tool in $tools) {
    if (-not (Test-Path -LiteralPath $tool.Executable)) {
        throw "$($tool.Name) executable is missing: $($tool.Executable)"
    }
    if (Test-Path -LiteralPath $tool.Archive) { Assert-ArchiveHash $tool }
}

$blender = $tools[0].Executable
$openscad = $tools[1].Executable
$blenderVersion = (& $blender --version | Select-Object -First 1)
$openscadVersion = (& $openscad --version 2>&1 | Select-Object -First 1)

[ordered]@{
    status = 'ready'
    blender = [ordered]@{ executable = $blender; version = $blenderVersion }
    openscad = [ordered]@{ executable = $openscad; version = [string]$openscadVersion }
    environment = [ordered]@{
        OPENSCAD_MODE = 'native'
        OPENSCAD_BIN = $openscad
        BLENDER_MODE = 'native'
        BLENDER_BIN = $blender
    }
} | ConvertTo-Json -Depth 5
