# HFDL Dashboard v8.1 — Native OpenSky compatibility

## Changes

- Imports the original OpenSky `aircraftDatabase.csv` without editing its headings.
- Recognises OpenSky's `icao24` field as the aircraft ICAO address.
- Maps `model` or `typecode` to the dashboard aircraft-type field.
- Maps `operator`, `operatorcallsign`, or `owner` to the operator field.
- Adds a **Use OpenSky URL** button in Settings.
- Raises the internet CSV download limit from 20 MB to 100 MB.
- Keeps existing local CSV, photo, alerts, authentication, analytics and database functions.

## OpenSky URL

```text
https://opensky-network.org/datasets/metadata/aircraftDatabase.csv
```

## Upgrade

Preserve:

```text
C:\hfdl-dashboard\data
```

Then run:

```powershell
cd C:\hfdl-dashboard
docker compose down
docker compose build --no-cache
docker compose up -d --force-recreate
docker compose ps
docker logs --tail 100 hfdl-dashboard
```

Open:

```text
http://localhost:8090/?v=8.1
```

Press `Ctrl+Shift+R`.
