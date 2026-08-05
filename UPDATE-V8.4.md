# HFDL Dashboard v8.4 — External aircraft lookup buttons

## New features

- Adds **Open on Planespotters** to Aircraft Detail.
- Generates the browser URL directly from the selected ICAO hex address:

```text
https://www.planespotters.net/hex/ICAO
```

Example:

```text
A67811 → https://www.planespotters.net/hex/A67811
```

- Opens the page in a new browser tab so the website handles its own cookies, bot checks, photographs and access rules.
- Adds **Search Google** as a fallback using registration and ICAO when available.
- Keeps local image upload and manually entered direct image URLs.
- Makes no server-side request to Planespotters, avoiding the previous `403 Forbidden` problem.

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
http://localhost:8090/?v=8.4
```

Press:

```text
Ctrl+Shift+R
```

## Use

Open:

```text
Aircraft → Details
```

Then click:

```text
Open on Planespotters
```

The matching aircraft page opens in a new browser tab.
