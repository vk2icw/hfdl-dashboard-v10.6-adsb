# v10.2 Installer Candidate

## Added

- Inno Setup installer script
- Program Files installation
- Start menu shortcut
- Optional desktop shortcut
- Optional start with Windows
- Optional inbound UDP 5557 Private-network firewall rule
- Upgrade-time server shutdown
- Uninstall-time server shutdown
- Firewall-rule cleanup on uninstall
- User-data preservation by default
- Optional `/REMOVEUSERDATA` uninstall flag
- Separate installer build script

## Build

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\BUILD-WINDOWS.ps1
```

The installer is produced under:

```text
installer-output
```
