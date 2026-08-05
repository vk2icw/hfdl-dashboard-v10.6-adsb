$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$innoCandidates = @(
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)

$iscc = $innoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    throw "Inno Setup 6 was not found. Install it, then rerun this script."
}

if (-not (Test-Path ".\dist\HFDL-Dashboard-Windows-v10.6-RC\HFDLDashboard.exe")) {
    throw "The Windows executables have not been built. Run BUILD-WINDOWS.ps1 first."
}

& $iscc ".\HFDL-Dashboard-Installer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
}

Write-Host ""
Write-Host "Installer complete:"
Get-ChildItem ".\installer-output\*.exe" | Select-Object FullName, Length, LastWriteTime
