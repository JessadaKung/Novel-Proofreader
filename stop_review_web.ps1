$ErrorActionPreference = "Stop"

$port = if ($env:PORT) { [int]$env:PORT } else { 8010 }
$connections = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen -ErrorAction SilentlyContinue

if (-not $connections) {
    Write-Host "No review server is listening on http://127.0.0.1:$port/"
    exit 0
}

$processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique

foreach ($processId in $processIds) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $processId -Force
        Write-Host "Stopped review server PID=$processId on http://127.0.0.1:$port/"
    }
}
