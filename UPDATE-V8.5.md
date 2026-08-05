# HFDL Dashboard v8.5 — External aircraft record card

The Aircraft Detail page now fills the empty area beneath the photograph controls with an aircraft lookup card showing:

- Registration
- ICAO hex address
- Aircraft type
- Operator
- A large **Open complete record and photographs** button
- Google search fallback

The Planespotters page opens in a separate browser tab using the selected ICAO address. No server-side request is made.

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
http://localhost:8090/?v=8.5
```

Press `Ctrl+Shift+R`.
