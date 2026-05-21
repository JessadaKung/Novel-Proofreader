$ErrorActionPreference = "Stop"
$env:PORT = if ($env:PORT) { $env:PORT } else { "8010" }
python "$PSScriptRoot\review_server.py"
