# HFDL Dashboard v7

## Aircraft enrichment

Import a local CSV from Settings. Supported columns:

```text
icao,registration,aircraft_type,operator,country
76CD77,9V-SMQ,Airbus A350-900,Singapore Airlines,Singapore
```

Metadata is stored locally and displayed in Aircraft and Aircraft Detail views.

## Alerts

The Alerts menu can watch:

- ICAO addresses
- Callsigns
- Any message
- Logon
- Logoff
- Position reports

Browser notifications are optional and require permission.

## Password protection

Edit `compose.yaml` before rebuilding:

```yaml
DASHBOARD_USERNAME: "admin"
DASHBOARD_PASSWORD: "choose-a-strong-password"
```

Leave both blank to disable authentication. Authentication applies to the dashboard, APIs and WebSocket feed.

## Upgrade

Keep `C:\hfdl-dashboard\data`, copy the v7 files into `C:\hfdl-dashboard`, then run:

```powershell
cd C:\hfdl-dashboard
docker compose down
docker compose build --no-cache
docker compose up -d --force-recreate
docker compose ps
docker logs --tail 100 hfdl-dashboard
```

Open `http://localhost:8090/?v=7` and press `Ctrl+Shift+R`.
