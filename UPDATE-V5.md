# HFDL Dashboard v5

## Aircraft intelligence

- Click any aircraft row to open its detail page
- Callsign history
- Assigned HFDL aircraft-ID history
- Associated ground stations
- Message and position counts
- Average SNR and strongest received signal
- Last known position, altitude and frequency
- Selectable 6-hour, 24-hour, 3-day or 7-day history
- Track line from stored HFDL position reports
- Operational timeline for logon, logoff, position and squitter messages
- Complete message history for the aircraft
- Aircraft-detail JSON export

## Upgrade

Keep:

```text
C:\hfdl-dashboard\data
```

Copy the v5 files into `C:\hfdl-dashboard`, then run:

```powershell
cd C:\hfdl-dashboard
docker compose down
docker compose build --no-cache
docker compose up -d --force-recreate
docker compose ps
docker logs --tail 100 hfdl-dashboard
```

Open `http://localhost:8090/?v=5` and press `Ctrl+Shift+R`.
