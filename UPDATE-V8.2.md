# HFDL Dashboard v8.2 — Automatic aircraft photo lookup

## New features

- **Find photo online** button on Aircraft Detail
- Uses the public Planespotters.net photo API
- Searches by aircraft registration first and ICAO address second
- Stores the returned image URL, photographer credit and source link
- Optional automatic lookup for aircraft without a cached photograph
- Automatic failed lookups are not retried for 30 days
- Manual lookup remains available
- Local photo upload still takes priority when `Local first` is selected

## Recommended settings

```text
Aircraft photo source: Local photo first, then internet URL
Online lookup: Automatically look up missing photos
```

## Upgrade

Preserve:

```text
C:\hfdl-dashboard\data
```

Then:

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
http://localhost:8090/?v=8.2
```

Press `Ctrl+Shift+R`.
