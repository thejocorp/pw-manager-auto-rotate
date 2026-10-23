# Changelog

## 0.2.0

The project is now **pw-manager-auto-rotate**; the command is `pwrotate`.

- Bitwarden comes first: `pwrotate doctor` checks the CLI, server, account, lock state and that
  every secret is in the vault, and says what to do about the first problem.
- Organization collections: a top-level `bitwarden:` block (`organization`, `collection`) looks
  items up there and creates new ones there, so a team shares them.
- A rotation of a secret that is not in the vault yet creates its login item.
- Item notes list every place the secret lives, refreshed on each rotation; your own notes stay.
- `bw sync` once before reading (`--no-sync` to skip).
- Writing keeps the file's mode **and owner**, locally and over SSH (before, SSH writes fell back
  to the remote default mode and both paths could change the owner). New files and backups are 600.
  If the owner cannot be kept, the write is refused.

## 0.1.0

First release. Reads a manifest of secrets and the places each one lives, and:
`status` compares every copy to the vault by fingerprint, `push` writes the vault value back
out, and `rotate` sets a new value in the vault and every place, restarts, checks, and rolls
everything back if a check fails. Formats: env, line, json, ini, raw. Transports: local, ssh.
Vault backend: Bitwarden / Vaultwarden CLI. Values are never printed.
