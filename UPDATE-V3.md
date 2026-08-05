# HFDL Dashboard v3

New features:
- Filters for ICAO, callsign, direction, frame and message type
- Uplink/downlink colour coding
- Legacy records dimmed
- Ground-station activity panel
- Three-minute feed-silence warning
- CSV and JSON export
- Existing SQLite history retained

Upgrade:
1. Keep `C:\hfdl-dashboard\data`.
2. Copy the v3 application files into `C:\hfdl-dashboard`.
3. Run:

```powershell
cd C:\hfdl-dashboard
docker compose down
docker compose build --no-cache
docker compose up -d --force-recreate
docker compose ps
docker logs --tail 100 hfdl-dashboard
```

Open `http://localhost:8090/?v=3` and press `Ctrl+Shift+R`.
