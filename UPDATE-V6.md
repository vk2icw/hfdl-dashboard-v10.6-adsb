# HFDL Dashboard v6

## Receiver health and analytics

- Message-rate history
- Average SNR history
- Frequency performance table
- Most-heard aircraft
- Reception-gap detection
- Adjustable 6-hour, 24-hour, 3-day and 7-day analytics windows

## Database controls

- Database size, message count and aircraft count
- Downloadable SQLite backup
- Purge only legacy pre-v2 records
- Delete history older than 7, 30, 90 or 365 days
- Confirmation required before deletion

## Upgrade

Preserve:

```text
C:\hfdl-dashboard\data
```

Copy the v6 files over the current application files, then run:

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
http://localhost:8090/?v=6
```

Press `Ctrl+Shift+R`.

The database controls are under **Settings**. The new graphs are under **Analytics**.
