# HFDL Dashboard v8.3 — Reliable aircraft photo sources

## Changes

- Removes the unsupported automatic Planespotters lookup.
- Stops presenting upstream `403 Forbidden` responses as “no photo found.”
- Retains local JPEG, PNG and WebP uploads.
- Adds manual direct image URL entry on Aircraft Detail.
- Adds photographer/source credit and source-page URL fields.
- Keeps local-first, internet-first, local-only, internet-only and disabled display modes.
- Existing OpenSky metadata, alerts, authentication, analytics and database tools remain unchanged.

## Using an internet photograph

Open:

```text
Aircraft → Details
```

Enter:

```text
Direct image URL
Photographer or source credit
Source webpage URL
```

Then click:

```text
Save internet photo URL
```

The image URL must directly return an image. A normal webpage URL will not render as the photograph.

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
http://localhost:8090/?v=8.3
```

Press `Ctrl+Shift+R`.
