# v10.6 ADSB.lol Correlation Candidate

## Added

- Free ADSB.lol lookup by six-character ICAO hex
- No API key required
- Separate ADSB.lol correlation card
- Position and position age
- Barometric and geometric altitude
- Ground speed
- Track and true/magnetic heading
- Vertical rate
- Squawk and emergency status
- Callsign, registration and aircraft type
- ADS-B integrity values where supplied
- Direct **Open on ADSB.lol** link
- Manual **Refresh ADSB.lol** command
- Sixty-second server-side cache by default
- Conservative one-request-per-second spacing
- Explicit separation from locally decoded HFDL data

## Configuration

```text
ADSB_LOL_ENABLED=yes
ADSB_LOL_CACHE_SECONDS=60
```

## Provider order

The Aircraft Detail page now displays:

1. local HFDL and ADS-C information;
2. ADSB.lol free external correlation;
3. Airplanes.live external correlation;
4. local or authorised aircraft photograph information.

External information never overwrites the locally decoded HFDL record.

## Limitation

ADSB.lol only returns information that its volunteer receiver network currently
has available. Oceanic HFDL aircraft may have no recent external ADS-B or MLAT
record.
