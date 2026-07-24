$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$php = if ($env:PHP_BIN) { $env:PHP_BIN } else { 'php' }
$hostName = if ($env:CAD_AI_HOST) { $env:CAD_AI_HOST } else { '127.0.0.1' }
$port = if ($env:CAD_AI_PORT) { $env:CAD_AI_PORT } else { '8080' }
& $php -S "${hostName}:${port}" -t "$project\public" "$project\router.php"
