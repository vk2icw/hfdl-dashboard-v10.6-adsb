# HFDL Operations Dashboard v10.6

Local HFDL monitoring, aircraft history, and receiver-analysis software with optional ADS-B correlation and aircraft-enrichment tools.

Developed by Louis LeMerle, VK2ICW. Concept, design, and project direction by Louis LeMerle, VK2ICW.

This project is experimental hobby, educational, and research software. It is not for navigation, air traffic control, flight safety, emergency operations, legal evidence, or other safety-critical use.

## Project Purpose

HFDL Operations Dashboard receives decoded HFDL JSON datagrams, stores them in a local SQLite database, and presents recent messages, aircraft history, receiver statistics, ground-station information, alerts, and aircraft detail views in a browser.

The dashboard is intended for local radio-monitoring workflows where decoding and display are separated:

- a receiver/decoder host runs SDR and HFDL decoding software;
- the dashboard host receives JSON over UDP;
- the browser displays current and historical aircraft activity;
- optional enrichment can link HFDL aircraft records with public aircraft metadata, ADS-B correlation, and authorised aircraft photographs.

## Actual Project Structure

The current repository is a compact single-service application:

- `app.py` - FastAPI application, UDP listener, SQLite storage, dashboard HTML/CSS/JavaScript, HFDL parsing, ADS-B.lol lookup, Airplanes.live lookup, PlaneSpotters photo lookup, metadata import, alerts, analytics, and database tools.
- `compose.yaml` - Docker Compose service definition.
- `Dockerfile` - Linux container build for the FastAPI dashboard.
- `requirements.txt` - Python runtime dependencies for Docker.
- `windows_launcher.py` - Windows desktop launcher for local/non-Docker operation.
- `BUILD-WINDOWS.ps1`, `BUILD-INSTALLER.ps1`, `HFDL-Dashboard-Installer.iss`, `*.spec` - Windows build and installer tooling.
- `LICENSE`, `DISCLAIMER.md`, `PRIVACY.md`, `SECURITY.md`, `THIRD_PARTY_NOTICES.md` - legal, safety, privacy, and third-party notices.
- `UPDATE-*.md`, `CHANGELOG.md`, `README-WINDOWS.md`, `README-INSTALLER.md` - release and platform documentation.

Generated and local-only folders such as `.venv/`, `build/`, `dist/`, `installer-output/`, and `data/` are intentionally excluded from Git.

## Architecture and Data Flow

```text
HF antenna / SDR
      |
      v
dumphfdl or compatible HFDL decoder
      |
      | decoded JSON over UDP, default port 5557
      v
HFDL Operations Dashboard
      |
      | SQLite database under /data in Docker
      v
Browser dashboard on TCP port 8090
      |
      +--> optional OpenSky metadata CSV import
      +--> optional ADS-B.lol aircraft correlation
      +--> optional Airplanes.live aircraft correlation
      +--> optional PlaneSpotters thumbnail lookup with attribution
```

The dashboard does not decode RF by itself. It expects decoded HFDL JSON from `dumphfdl` or a compatible sender.

## Ports

Default Docker ports:

- `8090/tcp` - web dashboard
- `5557/udp` - decoded HFDL JSON input

The project deliberately uses `5557/udp` for the dashboard so it can run alongside an existing ACARS Hub listener on `5556/udp`. It also uses `8090/tcp` so it can avoid services already bound to `8080/tcp`.

## Docker Installation

Prerequisites:

- Docker Desktop on Windows with Linux containers, or Docker Engine on Linux.
- A decoder host capable of sending decoded HFDL JSON over UDP.

Build and start:

```powershell
cd C:\hfdl-dashboard
docker compose config
docker compose up -d --build
docker compose ps
```

Open:

```text
http://localhost:8090
```

Health endpoint:

```text
http://localhost:8090/health
```

View logs:

```powershell
cd C:\hfdl-dashboard
docker compose logs --tail 150
```

Stop the dashboard:

```powershell
cd C:\hfdl-dashboard
docker compose down
```

`docker compose down` stops this Compose project. It does not delete the SQLite database stored in the `data` bind mount.

## Receiver and Decoder Setup

On the receiver/decoder system, configure `dumphfdl` to send decoded JSON to the dashboard host and UDP port `5557`.

Example output argument:

```bash
--output decoded:json:udp:address=WINDOWS_DASHBOARD_IP,port=5557
```

If the decoder and dashboard run on the same host, use the local host address. If the decoder runs on a Raspberry Pi, Linux machine, or SDR workstation, use the Windows dashboard computer's LAN IP address.

Keep existing outputs for other services, such as ACARS Hub on UDP `5556`, unchanged unless you intentionally want to alter those systems.

## Windows and Linux Roles

Common Windows role:

- runs Docker Desktop or the Windows launcher;
- hosts the browser dashboard;
- receives UDP `5557` from the decoder;
- stores persistent dashboard data locally.

Common Linux/Raspberry Pi role:

- runs SDR hardware and decoder software;
- sends decoded HFDL JSON to the Windows dashboard;
- may continue to send other outputs to Virtual Radar Server, ACARS Hub, or other tools.

These roles are conventional, not mandatory. The Docker service can run on any host that can receive UDP datagrams and expose the web dashboard.

## Configuration

The Docker service reads these environment variables from `compose.yaml`:

- `DATABASE_PATH` - SQLite database path inside the container, default `/data/hfdl.sqlite3`.
- `UDP_PORT` - UDP input port, default `5557`.
- `WEB_PORT` - dashboard HTTP port, default `8090`.
- `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD` - optional HTTP Basic authentication. Leave both blank to disable authentication.
- `ADSB_LOL_ENABLED` and `ADSB_LOL_CACHE_SECONDS` - optional ADS-B.lol lookup control.
- `AIRPLANES_LIVE_ENABLED` and `AIRPLANES_LIVE_CACHE_SECONDS` - optional Airplanes.live lookup control.
- `PLANESPOTTERS_PHOTO_ENABLED` and `PLANESPOTTERS_PHOTO_CACHE_SECONDS` - optional PlaneSpotters thumbnail lookup control.

Do not commit real usernames, passwords, API keys, tokens, private keys, or other secrets.

## Troubleshooting

Validate Compose syntax:

```powershell
docker compose config
```

Rebuild and start:

```powershell
docker compose up -d --build
```

Check container status:

```powershell
docker compose ps
```

Check recent logs:

```powershell
docker compose logs --tail 150
```

Check published ports on Windows:

```powershell
netstat -ano -p TCP | Select-String ':8090'
netstat -ano -p UDP | Select-String ':5557'
```

Check the health endpoint:

```powershell
Invoke-WebRequest -Uri http://localhost:8090/health -UseBasicParsing
```

If no messages arrive:

- confirm `dumphfdl` is running and receiving HFDL traffic;
- confirm the decoder sends JSON to the dashboard host IP and UDP `5557`;
- check Windows Firewall allows UDP `5557` on trusted/private networks;
- check Docker Desktop is running Linux containers;
- check the dashboard logs for JSON parse errors or database errors.

## Security and Privacy

Assume the dashboard is a local-network tool. If exposed beyond a trusted LAN, use proper network controls and authentication.

The application can store received HFDL messages, aircraft history, settings, alerts, imported metadata, and local aircraft photos in SQLite-backed runtime data. Do not publish the `data/` directory, logs, backups, or private receiver data.

External services may receive normal request metadata when optional enrichment features are used. Review `PRIVACY.md`, `SECURITY.md`, and `THIRD_PARTY_NOTICES.md` before enabling internet-based enrichment.

## Licence

Copyright 2026 Louis LeMerle.

Licensed under the MIT License. See `LICENSE`.

Additional notices are provided in `DISCLAIMER.md`, `PRIVACY.md`, `SECURITY.md`, and `THIRD_PARTY_NOTICES.md`.
