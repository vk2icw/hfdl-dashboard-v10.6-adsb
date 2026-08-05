# v10.4 Airplanes.live Candidate

## Added

- On-demand Airplanes.live lookup for the selected HFDL aircraft
- Lookup by six-character ICAO hex address
- Short server-side cache, default 60 seconds
- Server-wide one-request-per-second throttling
- Position and position age
- Barometric and geometric altitude
- Ground speed, track and heading
- Squawk and ADS-B emergency status
- Callsign, registration and aircraft type
- External source classification, including ADS-B, MLAT, Mode S and ADS-C
- Direct “Open on Airplanes.live” globe link
- Explicit separation between locally decoded HFDL data and external network data
- External emergency/squawk warning banner

## Configuration

Environment variables:

```text
AIRPLANES_LIVE_ENABLED=yes
AIRPLANES_LIVE_CACHE_SECONDS=60
```

## Operational limitation

Airplanes.live is an external non-commercial service with no uptime guarantee.
The correlation card is informational only and must not be used for navigation,
air-traffic control or emergency-response decisions.
