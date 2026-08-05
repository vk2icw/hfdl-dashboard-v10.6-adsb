# Upgrade to dashboard v2

This update preserves the existing SQLite database and adds parser fields non-destructively.

## Windows upgrade

1. Stop the existing dashboard:

```powershell
cd C:\hfdl-dashboard
docker compose down
```

2. Back up the data folder:

```powershell
Copy-Item C:\hfdl-dashboard\data C:\hfdl-dashboard-data-backup -Recurse -Force
```

3. Extract the v2 ZIP to a temporary folder, then copy these files over the existing project:

- `app.py`
- `Dockerfile`
- `compose.yaml`
- `requirements.txt`
- `README.md`

Do not overwrite or delete `C:\hfdl-dashboard\data`.

4. Rebuild and start:

```powershell
cd C:\hfdl-dashboard
docker compose up -d --build
docker compose ps
docker logs --tail 100 hfdl-dashboard
```

5. Hard-refresh the browser with `Ctrl+F5` and open:

```text
http://localhost:8090
```

## New v2 fields

- LPDU or SPDU frame type
- Actual protocol message type instead of the decoder application name
- Uplink/downlink direction
- Source or destination ground-station ID
- Separate ICAO and callsign columns
- Assigned HFDL aircraft ID
- Signal level and calculated SNR
- Raw JSON viewer for every message

Old stored rows will not acquire fields that were not previously parsed. New rows received after the upgrade will use the revised parser.
