# HFDL Dashboard v9 — Publication Edition

## Upgrade

Preserve:

```text
C:\hfdl-dashboard\data
```

Copy the v9 files into the application directory, then run:

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
http://localhost:8090/?v=9
```

Press `Ctrl+Shift+R`.

Open the new **About** page and verify every legal-document button.
