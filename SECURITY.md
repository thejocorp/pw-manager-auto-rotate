# Security

pw-manager-auto-rotate handles secrets, so security reports are welcome and taken seriously.

Please report a vulnerability privately through GitHub: **Security → Report a vulnerability** on
this repository. Do not open a public issue for it. Expect an answer within a few days.

Design choices worth knowing when you review it:

- Values never reach stdout, stderr or logs; only 12-character SHA-256 fingerprints do.
- Files are replaced atomically from a private (600) temp file that takes the old file's mode
  and owner; backups are 600.
- The vault is reached only through the official Bitwarden CLI; no credentials are stored by
  pwrotate itself.
