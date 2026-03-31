# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it by opening a GitHub issue or contacting the maintainer directly.

**Please include:**
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond as quickly as possible and work to address the issue.

## Security Considerations

This software runs on Victron Venus OS and controls power equipment. Please ensure:

- Keep your Venus OS updated
- Use HTTPS for web interface access
- Store `secrets.py` securely and never commit real credentials
- Restrict network access to trusted devices only
