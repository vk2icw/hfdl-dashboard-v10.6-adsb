# v10.2.1 Installer Fix

- Uses a Windows-compatible numeric version (`10.2.0.1`) for executable metadata.
- Retains `10.2.0-rc1` as the displayed application version.
- Stops the PowerShell build when Inno Setup compilation fails.
- Prevents a false “installer created” message after compiler errors.
