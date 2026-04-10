param()

$ErrorActionPreference = "SilentlyContinue"

foreach ($port in @(8000, 10001, 3000)) {
  $lines = netstat -ano | Select-String ":$port\s"
  foreach ($line in $lines) {
    $parts = ($line.ToString() -split "\s+") | Where-Object { $_ }
    $processId = $parts[-1]
    if ($processId -match '^\d+$' -and [int]$processId -gt 0) {
      Stop-Process -Id ([int]$processId) -Force
    }
  }
}
