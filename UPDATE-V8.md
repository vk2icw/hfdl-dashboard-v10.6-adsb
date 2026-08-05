# HFDL Dashboard v8 — Aircraft enrichment sources and photographs

## New features

- Metadata source choices: local CSV, internet CSV, local-first, internet-first, or disabled
- Preserve existing metadata or overwrite it during import
- Local CSV import
- Internet download from a direct HTTP/HTTPS CSV URL
- Optional `photo_url` and `photo_credit` CSV columns
- Photo source choices: local, internet, local-first, internet-first, or disabled
- Local JPEG, PNG or WebP upload from Aircraft Detail
- Local photos are stored in the persistent Docker data volume
- Existing alerts, authentication, analytics and database tools remain available

## CSV format

```csv
icao,registration,aircraft_type,operator,country,photo_url,photo_credit
76CD77,9V-SMQ,Airbus A350-900,Singapore Airlines,Singapore,https://example.org/9V-SMQ.jpg,Photographer name
```

Only `icao` is required.

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
http://localhost:8090/?v=8
```

Press `Ctrl+Shift+R`.
