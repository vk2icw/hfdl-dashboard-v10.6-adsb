# HFDL Operations Dashboard v10.2 — Windows Installer Candidate

## What the installer provides

- Installs the application under `C:\Program Files\HFDL Operations Dashboard`
- Adds Start menu shortcuts
- Optional desktop shortcut
- Optional start-with-Windows shortcut
- Optional Windows Firewall rule for inbound UDP 5557 on Private networks
- Launch-after-install option
- Clean upgrade handling
- Stops an old HFDL server before upgrading
- Stops the server during uninstall
- Removes the installer-created firewall rule during uninstall
- Preserves `%LOCALAPPDATA%\HFDLDashboard` by default

## Step 1 — Build the application and installer

Install:

- 64-bit Python 3.12
- Inno Setup 6

Open PowerShell in this folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\BUILD-WINDOWS.ps1
```

When Inno Setup is installed, the Setup executable is created under:

```text
installer-output
```

## Step 2 — Install

Run the generated Setup executable.

Recommended choices:

- Desktop shortcut: optional
- Start with Windows: leave off during testing
- Firewall UDP 5557: enable only when dumphfdl runs on another computer
- Launch after installation: enable

## User data

The installer does not place the database under Program Files.

User data remains under:

```text
%LOCALAPPDATA%\HFDLDashboard
```

This includes:

- SQLite database
- OpenSky metadata
- settings
- logs
- PID file

Normal uninstall preserves this data.

To remove application data as well, run the uninstaller from an elevated command prompt with:

```text
unins000.exe /REMOVEUSERDATA
```

Only use that command when the user intentionally wants to delete the database, metadata, settings and logs.

## Firewall

The optional installer task creates this rule:

```text
HFDL Dashboard UDP 5557
```

It is limited to Private network profiles and the server executable.

If the user selects another UDP port later, the firewall rule must also be changed manually or through a future launcher feature.

## Release-candidate limitations

- The installer is not digitally signed.
- Windows SmartScreen may warn about an unknown publisher.
- The firewall task currently targets UDP 5557 only.
- Start-with-Windows launches the full launcher, not a background tray-only mode.
- The application still opens the dashboard in the default browser.
