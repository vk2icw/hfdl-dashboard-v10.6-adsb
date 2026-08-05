# v10.4.3 Startup and Browser Cache Fix

## Browser loading

The application does not erase the user's browser cache. Instead, it safely
forces the current dashboard version to load by:

- adding a unique `cb=` query value whenever the dashboard is opened;
- sending `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`;
- sending `Pragma: no-cache`;
- sending an expired `Expires` header.

This avoids stale dashboard pages without deleting cookies, saved sessions,
history, or cached data belonging to other websites.

## Post-install launch

When **Launch HFDL Operations Dashboard after installation** is selected, Setup
now starts the launcher with `--autostart`.

The launcher then starts the server and opens the dashboard automatically once
the health check succeeds.

Starting the application normally from the Start menu still opens the launcher
without starting the server automatically.
