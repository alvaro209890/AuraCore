param()

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$runDir = Join-Path $root ".local-run"
$frontendNextDir = Join-Path $root "frontend\\.next"

if (!(Test-Path $runDir)) {
  New-Item -ItemType Directory -Path $runDir | Out-Null
}

foreach ($port in @(8000, 10001, 3000)) {
  $lines = netstat -ano | Select-String ":$port\s"
  foreach ($line in $lines) {
    $parts = ($line.ToString() -split "\s+") | Where-Object { $_ }
    $processId = $parts[-1]
    if ($processId -match '^\d+$' -and [int]$processId -gt 0) {
      Stop-Process -Id ([int]$processId) -Force -ErrorAction SilentlyContinue
    }
  }
}

Start-Sleep -Seconds 2

if (Test-Path $frontendNextDir) {
  Remove-Item -LiteralPath $frontendNextDir -Recurse -Force
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backendOut = Join-Path $runDir "backend.$stamp.out.log"
$backendErr = Join-Path $runDir "backend.$stamp.err.log"
$gatewayOut = Join-Path $runDir "gateway.$stamp.out.log"
$gatewayErr = Join-Path $runDir "gateway.$stamp.err.log"
$frontendOut = Join-Path $runDir "frontend.$stamp.out.log"
$frontendErr = Join-Path $runDir "frontend.$stamp.err.log"

$backend = Start-Process `
  -FilePath (Join-Path $root "backend\\.venv\\Scripts\\python.exe") `
  -ArgumentList @("-m", "uvicorn", "local_main:app", "--host", "127.0.0.1", "--port", "8000") `
  -WorkingDirectory (Join-Path $root "backend") `
  -RedirectStandardOutput $backendOut `
  -RedirectStandardError $backendErr `
  -PassThru

$gateway = Start-Process `
  -FilePath $env:ComSpec `
  -ArgumentList @("/c", "npm.cmd run dev") `
  -WorkingDirectory (Join-Path $root "whatsapp-gateway") `
  -RedirectStandardOutput $gatewayOut `
  -RedirectStandardError $gatewayErr `
  -PassThru

$frontend = Start-Process `
  -FilePath $env:ComSpec `
  -ArgumentList @("/c", "npm.cmd run dev") `
  -WorkingDirectory (Join-Path $root "frontend") `
  -RedirectStandardOutput $frontendOut `
  -RedirectStandardError $frontendErr `
  -PassThru

Start-Sleep -Seconds 5

[pscustomobject]@{
  backend_pid = $backend.Id
  gateway_pid = $gateway.Id
  frontend_pid = $frontend.Id
  backend_url = "http://127.0.0.1:8000"
  gateway_url = "http://127.0.0.1:10001"
  frontend_url = "http://localhost:3000"
  backend_log = $backendOut
  gateway_log = $gatewayOut
  frontend_log = $frontendOut
} | Format-List
