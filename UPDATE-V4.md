# HFDL Dashboard v4

## Main change

The dashboard is now divided into top-menu views:

- Overview
- Map
- Messages
- Aircraft
- Stations
- Analytics
- Settings

This prevents the full dashboard from being larger than the browser screen.

## Other improvements

- Sticky top navigation
- Collapsible mobile menu
- Full-height map page
- Full-screen map button
- Dedicated message page
- Compact display mode
- Configurable message-row limit
- Configurable silence-warning period
- Hide/show legacy records
- Last-used view remembered by the browser

## Upgrade on Windows

Preserve:

```text
C:\hfdl-dashboard\data
```

Copy the v4 application files into:

```text
C:\hfdl-dashboard
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
http://localhost:8090/?v=4
```

Press `Ctrl+Shift+R`.
