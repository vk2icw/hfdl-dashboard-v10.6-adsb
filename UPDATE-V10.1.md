# v10.1 Release Candidate — Reliable shutdown

## Fixed

- The server process is now terminated as a complete Windows process tree.
- Closing the launcher no longer leaves `HFDLDashboardServer.exe` running.
- A PID file records the active server process.
- On startup, the launcher detects and offers to stop a leftover server.
- Duplicate server instances are blocked.
- UDP and web port conflicts are detected before startup.
- Added **Stop and exit**.

## Build

Open PowerShell in the extracted source folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\BUILD-WINDOWS.ps1
```

Run the newly built launcher from:

```text
dist\HFDL-Dashboard-Windows-Preview\HFDLDashboard.exe
```

## Verification

Start the dashboard, then close it using **Stop and exit**.

Run:

```powershell
Get-Process HFDLDashboardServer -ErrorAction SilentlyContinue
```

No process should be returned.
