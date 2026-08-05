# Privacy

HFDL Operations Dashboard is designed primarily for local operation.

## Local data

The application stores received HFDL messages, aircraft history, alert rules, settings and imported metadata in the local SQLite database selected by the user.

The application does not intentionally transmit the received-message database or aircraft history to the developer.

## External connections

Internet connections may occur when the user or application:

- loads OpenStreetMap tiles;
- loads Leaflet or Chart.js from their configured content-delivery networks;
- downloads aircraft metadata from OpenSky Network or another user-supplied URL;
- displays a user-supplied external image URL;
- opens an external aircraft website such as Planespotters.net or a Google search.

Those external services may receive the user's IP address, browser information and other ordinary request data under their own privacy policies.

## Credentials

Dashboard usernames and passwords are configured by the operator. Users are responsible for choosing strong credentials, protecting configuration files and limiting access to the host computer and network.

## Backups

Database backups may contain received messages, aircraft history, alert rules and other locally stored information. Store backups securely and delete them when no longer required.
