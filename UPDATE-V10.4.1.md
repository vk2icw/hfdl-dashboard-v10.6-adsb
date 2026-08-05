# v10.4.1 Airplanes.live Diagnostics Fix

## Corrected

- Dashboard header now shows `v10.4.1 Airplanes.live`.
- Removed the obsolete `v10 Windows Preview` label.
- Airplanes.live lookup failures now distinguish:
  - no current record;
  - invalid ICAO address;
  - integration disabled;
  - API rate limit;
  - API timeout;
  - external service unavailable;
  - other HTTP/API failures.
- The correlation badge now shows the actual lookup state.
- A contextual explanation is displayed without affecting local HFDL data.
- API endpoints now return appropriate HTTP status codes.
