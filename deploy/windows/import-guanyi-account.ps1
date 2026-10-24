[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{32}$')]
    [string]$AccountId,

    [string]$Label = '',

    [ValidateRange(30, 1800)]
    [int]$TimeoutSeconds = 300,

    [string]$GuanyiClient = 'D:\desktop\rea\guanghe-api-bridge\runtime\Guanyi.Client-win-x64\Guanyi.Client.exe'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtimeFile = Join-Path $env:LOCALAPPDATA "Guanyi\DesktopClient\browser-runtime\$AccountId.json"
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$helper = Join-Path $projectRoot 'tools\get_muse_cookie.py'
$envFile = Join-Path $projectRoot '.env'

if (-not (Test-Path -LiteralPath $GuanyiClient)) {
    throw "找不到贯一指纹客户端：$GuanyiClient"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "找不到项目 Python：$python"
}
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "找不到 $envFile，请先完成 muse2api 本地部署"
}

$settings = @{}
foreach ($line in Get-Content -LiteralPath $envFile -Encoding utf8) {
    $text = $line.Trim()
    if (-not $text -or $text.StartsWith('#') -or -not $text.Contains('=')) { continue }
    $name, $value = $text.Split('=', 2)
    $settings[$name.Trim()] = $value.Trim().Trim('"').Trim("'")
}
if (-not $settings['MUSE2API_KEY']) {
    throw '.env 中缺少 MUSE2API_KEY'
}

$runtime = $null
if (Test-Path -LiteralPath $runtimeFile) {
    try {
        $candidate = Get-Content -LiteralPath $runtimeFile -Raw | ConvertFrom-Json
        if ($candidate.processId -and (Get-Process -Id $candidate.processId -ErrorAction SilentlyContinue)) {
            $runtime = $candidate
        }
    } catch {
        $runtime = $null
    }
}

if (-not $runtime) {
    Start-Process -FilePath $GuanyiClient -ArgumentList @('--open-account', $AccountId)
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 500
        if (Test-Path -LiteralPath $runtimeFile) {
            try {
                $candidate = Get-Content -LiteralPath $runtimeFile -Raw | ConvertFrom-Json
                if ($candidate.processId -and (Get-Process -Id $candidate.processId -ErrorAction SilentlyContinue)) {
                    $runtime = $candidate
                }
            } catch {
                $runtime = $null
            }
        }
    } until ($runtime -or (Get-Date) -ge $deadline)
}

if (-not $runtime -or -not $runtime.cdpEndpoint) {
    throw '指纹窗口已启动，但没有取得有效 CDP 地址'
}
if ($runtime.channel -ne 'muse') {
    throw "账号通道不是 muse：$($runtime.channel)"
}

$oldBase = $env:MUSE2API_BASE
$oldKey = $env:MUSE2API_KEY
try {
    $env:MUSE2API_BASE = 'http://127.0.0.1:18620'
    $env:MUSE2API_KEY = $settings['MUSE2API_KEY']
    $arguments = @(
        $helper,
        '--base', $env:MUSE2API_BASE,
        '--timeout', $TimeoutSeconds,
        '--cdp-endpoint', [string]$runtime.cdpEndpoint,
        '--keep-open'
    )
    if ($Label) { $arguments += @('--label', $Label) }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Cookie 导入未完成（退出码 $LASTEXITCODE）。请在指纹窗口完成登录后重试。"
    }
} finally {
    $env:MUSE2API_BASE = $oldBase
    $env:MUSE2API_KEY = $oldKey
}
