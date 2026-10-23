$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtimeDir = Join-Path $projectRoot '.runtime'
$cloudProject = 'D:\desktop\muse2api-mature-cloud'
$cloudflared = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

$out = Join-Path $runtimeDir 'tunnel.stdout.log'
$err = Join-Path $runtimeDir 'tunnel.stderr.log'
$tunnel = Start-Process -FilePath $cloudflared `
    -ArgumentList @('tunnel','--url','http://127.0.0.1:18620','--protocol','http2','--no-autoupdate') `
    -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru

$tunnelUrl = $null
for ($i = 0; $i -lt 120; $i++) {
    if ($tunnel.HasExited) { throw "cloudflared exited. See $err" }
    $log = Get-Content $err -Raw -ErrorAction SilentlyContinue
    if ($log -match 'https://[a-z0-9-]+\.trycloudflare\.com') { $tunnelUrl = $matches[0]; break }
    Start-Sleep -Milliseconds 500
}
if (-not $tunnelUrl) { throw 'Timed out waiting for the Cloudflare Tunnel URL.' }

Push-Location $cloudProject
try {
    & npx.cmd wrangler deploy --var "UPSTREAM_ORIGIN:$tunnelUrl"
    if ($LASTEXITCODE) { throw "wrangler deploy failed: $LASTEXITCODE" }
}
finally { Pop-Location }

$local = Get-Content -Raw (Join-Path $runtimeDir 'local-status.json') | ConvertFrom-Json
@{
    startedAt = [DateTimeOffset]::Now.ToString('o')
    proxyPid = $local.proxyPid
    apiPid = $local.apiPid
    tunnelPid = $tunnel.Id
    proxyUrl = $local.proxyUrl
    localUrl = $local.localUrl
    tunnelUrl = $tunnelUrl
    publicUrl = 'https://muse2api-mature-relay.yeadon8888.workers.dev'
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $runtimeDir 'status.json')

Write-Output 'muse2api cloud relay deployed: https://muse2api-mature-relay.yeadon8888.workers.dev'
