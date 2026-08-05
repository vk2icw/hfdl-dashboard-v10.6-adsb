# HFDL Operations Dashboard — Windows v10.4.1 Airplanes.live

This package converts the Docker-based dashboard into a normal Windows launcher and local server.

## What the launcher provides

- Configurable UDP listener IP
- Configurable UDP listener port
- Configurable web listener IP
- Configurable dashboard port
- User-selectable SQLite database path
- Optional username and password
- Start, Stop, Open Dashboard and Open Logs controls
- Settings stored under `%LOCALAPPDATA%\HFDLDashboard`
- No Docker required after the executables are built

## Recommended settings

For dumphfdl running on another computer:

```text
UDP listen address: 0.0.0.0
UDP port:           5557
Web listen address: 127.0.0.1
Web port:           8090
```

Configure dumphfdl to send JSON to the Windows computer's LAN address and UDP port 5557.

`127.0.0.1` keeps the web dashboard available only on the Windows computer. Change it to `0.0.0.0` only when other trusted devices need browser access.

## Build the executables

Requirements:

- Windows 10 or Windows 11
- 64-bit Python 3.12
- Internet access for the first dependency installation

Open PowerShell in this folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\BUILD-WINDOWS.ps1
```

The completed package will be created under:

```text
dist\HFDL-Dashboard-Windows-Preview
```

Run:

```text
HFDLDashboard.exe
```

Do not launch `HFDLDashboardServer.exe` directly unless troubleshooting.

## First test before building

The launcher source can also be tested with Python:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = $PWD
.\.venv\Scripts\python.exe .\windows_launcher.py
```

In source mode, the launcher starts `app.py` through the active Python interpreter.

## Data location

The default database is:

```text
%LOCALAPPDATA%\HFDLDashboard\data\hfdl.sqlite3
```

Logs are written to:

```text
%LOCALAPPDATA%\HFDLDashboard\logs\server.log
```

Launcher settings are written to:

```text
%LOCALAPPDATA%\HFDLDashboard\launcher-settings.json
```

## Firewall

Windows may ask whether the server may receive network traffic. Permit UDP access only on trusted/private networks when dumphfdl runs on another computer.

The web listener defaults to `127.0.0.1`, so it does not need to be exposed to the LAN.

## Status

This is a Windows packaging preview. Test it before treating it as the final public installer. The later publication build should add:

- system-tray operation;
- optional start with Windows;
- signed installer;
- guided firewall rule;
- update checking;
- installer uninstall and upgrade handling.


## v10.1 shutdown and conflict protection

This release candidate adds:

- process ID tracking under `%LOCALAPPDATA%\HFDLDashboard\server.pid`;
- cleanup of a leftover server at launcher startup;
- full Windows process-tree shutdown using `taskkill /T /F`;
- prevention of duplicate server instances;
- UDP port conflict detection;
- web/TCP port conflict detection;
- a dedicated **Stop and exit** command;
- PID-file cleanup after normal or abnormal shutdown.

After closing the launcher, verify:

```powershell
Get-Process HFDLDashboardServer -ErrorAction SilentlyContinue
```

It should return no process.


See `README-INSTALLER.md` for installer build and uninstall instructions.


## v10.3 tray operation

When reception is active, closing the launcher can hide it in the Windows
notification area. The tray menu can reopen the launcher, open the dashboard,
stop the server, or exit completely.

## v10.3 firewall management

The launcher can keep the `HFDL Dashboard UDP` Private-network firewall rule
aligned with the configured UDP port. Windows requests administrator approval
only when a rule change is required.


## v10.4 Airplanes.live correlation

Opening an aircraft detail page requests the latest available external record
for that aircraft's ICAO hex address. The result is displayed in a separate
Airplanes.live correlation card and never overwrites the locally decoded HFDL
position or altitude.

The integration is deliberately conservative:

- one external request per second maximum;
- sixty-second cache by default;
- manual refresh available;
- no continuous fleet-wide polling;
- external source and data age shown;
- no guarantee that every HFDL aircraft has a current external record.


## v10.4.1 lookup diagnostics

The Airplanes.live panel now distinguishes a genuine absence of a current
aircraft record from an API outage, timeout, rate limit, disabled integration,
or invalid ICAO address. Local HFDL reception and stored data continue to work
when the external service is unavailable.


## v10.4.3 cache handling

The launcher adds a unique cache-busting value each time it opens the browser,
and the server sends no-cache headers for the dashboard HTML. This prevents an
old interface from remaining visible after an upgrade without clearing the
user's entire browser cache.

## v10.4.3 launch after installation

Selecting **Launch HFDL Operations Dashboard after installation** now starts the
server automatically and opens the dashboard after it becomes ready.


## v10.5 Planespotters photographs

The Aircraft Detail page can automatically request a thumbnail from the
Planespotters Photo API using the selected aircraft's ICAO hex address.

The dashboard preserves attribution and links the thumbnail to the original
Planespotters photograph page. It does not copy or permanently store the
full-resolution photograph. Manually configured photographs continue to take
priority.


## v10.6 ADSB.lol

The selected HFDL aircraft can be correlated with the free ADSB.lol API by ICAO
hex. The dashboard shows the external result in a separate card, including the
data source and age. No API key is required.

The integration queries only the selected aircraft, uses a short cache and does
not continuously poll every aircraft in the database.
