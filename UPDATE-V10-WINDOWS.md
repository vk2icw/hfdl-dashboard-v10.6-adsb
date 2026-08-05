# v10 Windows Preview

This release begins the transition from Docker to a native Windows application.

It includes:

- a Tkinter Windows launcher;
- configurable UDP bind IP and port;
- configurable web bind IP and port;
- configurable database file;
- optional authentication;
- background server start/stop;
- browser launching;
- persistent launcher settings;
- server log access;
- a PowerShell PyInstaller build script.

The archive contains build source rather than precompiled Windows executables. Windows executables must be built on Windows so that PyInstaller includes the correct Windows bootloader and native modules.
