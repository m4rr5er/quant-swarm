# Download nats-server.exe into deploy\bin\ (Windows). Binaries are gitignored.
param([string]$Version = "v2.15.3")

$dest = Join-Path (Split-Path $PSScriptRoot -Parent) "deploy\bin"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$tmp = Join-Path $env:TEMP "nats-fetch"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

$zip = Join-Path $tmp "nats.zip"
$url = "https://github.com/nats-io/nats-server/releases/download/$Version/nats-server-$Version-windows-amd64.zip"
Invoke-WebRequest -Uri $url -OutFile $zip
Expand-Archive -Path $zip -DestinationPath $tmp -Force
Copy-Item (Join-Path $tmp "nats-server-$Version-windows-amd64\nats-server.exe") (Join-Path $dest "nats-server.exe")
Remove-Item -Recurse -Force $tmp
Write-Host "nats-server $Version -> $dest\nats-server.exe"
