$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtimeDir = Join-Path $projectRoot '.runtime'
$accountStore = 'C:\Users\Yeadon\AppData\Local\Guanyi\DesktopClient\accounts.json'
$nodeExe = 'D:\nodejs\node.exe'
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$edgeExe = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$previousStatus = Join-Path $runtimeDir 'local-status.json'
if (Test-Path $previousStatus) {
    $previous = Get-Content -Raw $previousStatus | ConvertFrom-Json
    @($previous.apiPid, $previous.proxyPid) | Where-Object { $_ } | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
}
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like '*muse2api-mature*proxy-runner.mjs*' -or
    $_.CommandLine -like '*uvicorn*app:app*18620*'
} | Where-Object { $_.ProcessId -ne $PID } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$staleBrowsers = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'msedge.exe' -and $_.CommandLine -like '*--remote-debugging-port=19220*'
}
$staleBrowsers | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
$account = Get-Content -Raw -LiteralPath $accountStore | ConvertFrom-Json |
    Where-Object { $_.Channel -eq 'muse' -and $_.Name -eq 'Muse账号 1' } |
    Select-Object -First 1
if (-not $account) { throw 'Muse账号 1 was not found in the desktop account store.' }

$cipher = [Convert]::FromBase64String($account.Proxy.ProtectedPassword)
$entropy = [Text.Encoding]::UTF8.GetBytes('Guanyi.Client.v1')
$plainBytes = [Security.Cryptography.ProtectedData]::Unprotect(
    $cipher, $entropy, [Security.Cryptography.DataProtectionScope]::CurrentUser)
$password = [Text.Encoding]::UTF8.GetString($plainBytes)
$proxyConfig = @{
    host = $account.Proxy.Host
    port = [int]$account.Proxy.Port
    username = $account.Proxy.Username
    password = $password
    timeoutMs = 30000
}
$proxyTarget = [Uri]::new("https://$($account.Proxy.Host):$($account.Proxy.Port)")
$systemProxy = [Net.WebRequest]::DefaultWebProxy.GetProxy($proxyTarget)
if (-not [Net.WebRequest]::DefaultWebProxy.IsBypassed($proxyTarget) -and
    $systemProxy -ne $proxyTarget -and $systemProxy.IsLoopback) {
    $proxyConfig.gatewayHost = $systemProxy.Host
    $proxyConfig.gatewayPort = $systemProxy.Port
}
$proxyConfig = $proxyConfig | ConvertTo-Json -Compress
$password = $null
$env:MUSE2API_SOCKS_CONFIG = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($proxyConfig)).TrimEnd('=').Replace('+','-').Replace('/','_')
$proxyConfig = $null

$proxyOut = Join-Path $runtimeDir 'proxy.stdout.log'
$proxyErr = Join-Path $runtimeDir 'proxy.stderr.log'
$proxyProcess = Start-Process -FilePath $nodeExe -ArgumentList (Join-Path $PSScriptRoot 'proxy-runner.mjs') `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $proxyOut `
    -RedirectStandardError $proxyErr -PassThru
Remove-Item Env:MUSE2API_SOCKS_CONFIG

$proxyUrl = $null
for ($i = 0; $i -lt 100; $i++) {
    if ($proxyProcess.HasExited) { throw "Proxy bridge exited. See $proxyErr" }
    if (Test-Path $proxyOut) {
        $line = Get-Content $proxyOut -First 1
        $proxyUrl = if ($null -ne $line) { $line.Trim() } else { $null }
        if ($proxyUrl -match '^http://127\.0\.0\.1:\d+$') { break }
    }
    Start-Sleep -Milliseconds 100
}
if (-not $proxyUrl) { throw 'Proxy bridge did not publish a local endpoint.' }

$env:MUSE2API_HOME = $projectRoot
$env:MUSE2API_HOST = '127.0.0.1'
$env:MUSE2API_PORT = '18620'
$env:MUSE2API_CDP_PORT = '19220'
$env:MUSE2API_CHROMIUM = $edgeExe
$env:MUSE2API_PROXY_SERVER = $proxyUrl
$env:HTTP_PROXY = $proxyUrl
$env:HTTPS_PROXY = $proxyUrl
$env:NO_PROXY = '127.0.0.1,localhost'
$env:MUSE2API_CONCURRENCY = '1'

$apiOut = Join-Path $runtimeDir 'api.stdout.log'
$apiErr = Join-Path $runtimeDir 'api.stderr.log'
$apiProcess = Start-Process -FilePath $pythonExe `
    -ArgumentList @('-m','uvicorn','app:app','--host','127.0.0.1','--port','18620') `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $apiOut `
    -RedirectStandardError $apiErr -PassThru

@{
    startedAt = [DateTimeOffset]::Now.ToString('o')
    proxyPid = $proxyProcess.Id
    apiPid = $apiProcess.Id
    proxyUrl = $proxyUrl
    localUrl = 'http://127.0.0.1:18620'
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $runtimeDir 'local-status.json')

Write-Output 'muse2api local service started on http://127.0.0.1:18620'
