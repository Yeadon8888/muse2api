$ErrorActionPreference = 'Stop'

$runtimeDir = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path '.runtime'
$statusPath = Join-Path $runtimeDir 'status.json'
$localStatusPath = Join-Path $runtimeDir 'local-status.json'
$pids = @()
foreach ($path in @($statusPath, $localStatusPath)) {
    if (Test-Path $path) {
        $status = Get-Content -Raw $path | ConvertFrom-Json
        $pids += @($status.apiPid, $status.proxyPid, $status.tunnelPid)
    }
}
$pids | Where-Object { $_ } | Sort-Object -Unique | ForEach-Object {
    Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
}
Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq 'msedge.exe' -and $_.CommandLine -like '*--remote-debugging-port=19220*') -or
    $_.CommandLine -like '*muse2api-mature*proxy-runner.mjs*' -or
    $_.CommandLine -like '*uvicorn*app:app*18620*'
} | Where-Object { $_.ProcessId -ne $PID } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Output 'muse2api local service stopped'
