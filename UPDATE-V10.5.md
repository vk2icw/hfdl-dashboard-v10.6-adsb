# v10.5 Planespotters Photo Candidate

## Added

- Automatic Planespotters Photo API lookup by six-character ICAO hex
- Authorised thumbnail display in the Aircraft Detail page
- Photographer attribution directly under the image
- Clear “Photo supplied by Planespotters.net” attribution
- Clickable thumbnail linking to the original photograph page
- Manual **Refresh photo** command
- Six-hour server-side cache by default
- One-request-per-second server-wide request spacing
- Manual/local photographs remain higher priority
- No full-resolution photo download or permanent storage

## Configuration

```text
PLANESPOTTERS_PHOTO_ENABLED=yes
PLANESPOTTERS_PHOTO_CACHE_SECONDS=21600
```

## Behaviour

When an aircraft detail page opens:

1. the dashboard loads its normal local aircraft record;
2. a manually uploaded or configured image is displayed first;
3. when no local image is configured, the server requests an authorised
   Planespotters thumbnail by ICAO hex;
4. the photographer and Planespotters attribution are displayed;
5. clicking the image opens the original Planespotters photograph page.

The feature depends on the external Photo API and may return no result for some
aircraft.
