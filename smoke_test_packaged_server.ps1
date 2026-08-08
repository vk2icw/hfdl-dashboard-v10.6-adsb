$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot "dist\HFDLDashboardServer.exe"
if (-not (Test-Path $exe)) { throw "Packaged server executable not found: $exe" }

$tempRoot = Join-Path $env:RUNNER_TEMP ("hfdl-packaged-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot | Out-Null
$db = Join-Path $tempRoot "smoke.sqlite3"
$log = Join-Path $tempRoot "server.log"

$old = @{}
foreach ($name in @('DATABASE_PATH','UDP_BIND_IP','UDP_PORT','WEB_BIND_IP','WEB_PORT','DASHBOARD_USERNAME','DASHBOARD_PASSWORD')) {
    $old[$name] = [Environment]::GetEnvironmentVariable($name,'Process')
}

$env:DATABASE_PATH = $db
$env:UDP_BIND_IP = '127.0.0.1'
$env:UDP_PORT = '5569'
$env:WEB_BIND_IP = '127.0.0.1'
$env:WEB_PORT = '8099'
$env:DASHBOARD_USERNAME = ''
$env:DASHBOARD_PASSWORD = ''

$p = $null
try {
    $p = Start-Process -FilePath $exe -RedirectStandardOutput $log -RedirectStandardError $log -PassThru -WindowStyle Hidden
    $health = 'http://127.0.0.1:8099/health'
    $ready = $false
    for ($i=0; $i -lt 40; $i++) {
        if ($p.HasExited) { throw "Packaged server exited early with code $($p.ExitCode). Log:`n$(Get-Content $log -Raw -ErrorAction SilentlyContinue)" }
        try {
            $r = Invoke-WebRequest -UseBasicParsing -Uri $health -TimeoutSec 1
            if ($r.StatusCode -eq 200) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "Packaged server health check timed out. Log:`n$(Get-Content $log -Raw -ErrorAction SilentlyContinue)" }

    $photoUri = 'http://127.0.0.1:8099/api/external/airport-data-photo/7C6B39?refresh=true'
    $photoResponse = Invoke-WebRequest -UseBasicParsing -Uri $photoUri -TimeoutSec 20
    $data = $photoResponse.Content | ConvertFrom-Json
    if (-not $data.ok) { throw "Packaged Airport-Data route returned ok=false: $($photoResponse.Content)" }
    if (-not $data.photo.thumbnail_url) { throw "Packaged Airport-Data route returned no thumbnail_url: $($photoResponse.Content)" }

    $img = Invoke-WebRequest -UseBasicParsing -Uri $data.photo.thumbnail_url -TimeoutSec 20 -MaximumRedirection 5
    $contentType = [string]$img.Headers['Content-Type']
    if (-not $contentType.StartsWith('image/')) { throw "Packaged server returned photo URL but image fetch was not image content: $contentType" }

    Write-Host "Packaged server HTTPS smoke test passed"
    Write-Host "image: $($data.photo.thumbnail_url)"
    Write-Host "content-type: $contentType"
}
finally {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    foreach ($name in $old.Keys) { [Environment]::SetEnvironmentVariable($name,$old[$name],'Process') }
    Remove-Item -Recurse -Force $tempRoot -ErrorAction SilentlyContinue
}
