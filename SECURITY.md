# Security

## Supported use

HFDL Operations Dashboard is intended for use on a trusted computer or trusted local network.

## Important limitations

Built-in password protection restricts casual access. It is not a replacement for:

- a properly configured host firewall;
- secure operating-system accounts;
- HTTPS termination through a trusted reverse proxy;
- network segmentation;
- timely software and dependency updates;
- secure backup handling.

Do not expose the dashboard directly to the public internet.

## Recommended deployment

- Bind the web interface to localhost unless remote access is required.
- Permit UDP input only from the expected decoder host or trusted subnet.
- Use a strong unique password.
- Keep Docker, Python packages, the operating system and browser updated.
- Back up the SQLite database before upgrades.
- Preserve the `data` directory when replacing application files.
- Review logs after each upgrade.
- Do not store secrets in publicly shared screenshots or release archives.

## Reporting a security issue

Do not publish credentials, private logs, received-message databases or exploitable details in a public issue. Contact the project maintainer privately through the release channel used to distribute the software.
