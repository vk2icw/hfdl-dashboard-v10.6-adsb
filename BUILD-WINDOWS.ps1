$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Creating the Windows build environment..."
if (-not (Test-Path ".venv")) {
    py -3.12 -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements-windows-build.txt

Write-Host "Applying aircraft photo UI build patch..."
& ".\.venv\Scripts\python.exe" ".\build_photo_ui_patch.py"
if ($LASTEXITCODE -ne 0) {
    throw "Aircraft photo UI patch failed with exit code $LASTEXITCODE."
}

Remove-Item -Recurse -Force ".\build", ".\dist" -ErrorAction SilentlyContinue

$legal = @(
    "LICENSE",
    "DISCLAIMER.md",
    "PRIVACY.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "CHANGELOG.md",
    "VERSION",
    "README.md"
)

$serverArgs = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name", "HFDLDashboardServer",
    "--icon", "hfdl-dashboard.ico",
    "--collect-all", "uvicorn",
    "--collect-all", "fastapi"
)

foreach ($file in $legal) {
    $serverArgs += @("--add-data", "$file;.")
}
$serverArgs += "build_app.py"

Write-Host "Building HFDLDashboardServer.exe..."
& ".\.venv\Scripts\pyinstaller.exe" @serverArgs

Write-Host "Building HFDLDashboard.exe..."
& ".\.venv\Scripts\pyinstaller.exe" `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "HFDLDashboard" `
    --icon "hfdl-dashboard.ico" `
    --add-data "hfdl-dashboard.ico;." `
    --add-data "hfdl-dashboard.png;." `
    --hidden-import "pystray._win32" `
    "windows_launcher.py"

$release = ".\dist\HFDL-Dashboard-Windows-v10.6-RC"
Remove-Item -Recurse -Force $release -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $release | Out-Null

Copy-Item ".\dist\HFDLDashboard.exe" $release
Copy-Item ".\dist\HFDLDashboardServer.exe" $release
Copy-Item ".\LICENSE", ".\DISCLAIMER.md", ".\PRIVACY.md", ".\SECURITY.md", `
          ".\THIRD_PARTY_NOTICES.md", ".\CHANGELOG.md", ".\README-WINDOWS.md", `
          ".\VERSION", ".\hfdl-dashboard.ico", ".\hfdl-dashboard.png" $release

Compress-Archive `
    -Path "$release\*" `
    -DestinationPath ".\dist\HFDL-Dashboard-Windows-v10.6-RC.zip" `
    -Force

Write-Host ""
Write-Host "Build complete:"
Write-Host "  $release"
Write-Host "  .\dist\HFDL-Dashboard-Windows-v10.6-RC.zip"


Write-Host ""
Write-Host "Looking for Inno Setup..."
$innoCandidates = @(
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)

$iscc = $innoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($iscc) {
    Write-Host "Building Windows installer with Inno Setup..."
    & $iscc ".\HFDL-Dashboard-Installer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
}
    Write-Host ""
    Write-Host "Installer created successfully under:"
    Write-Host "  .\installer-output"
} else {
    Write-Warning "Inno Setup 6 was not found."
    Write-Host "Install Inno Setup 6, then rerun this script to produce Setup.exe."
    Write-Host "The portable application package was still built successfully."
}
