# Changelog

## 0.1.0

First release. Reads a manifest of secrets and the places each one lives, and:
`status` compares every copy to the vault by fingerprint, `push` writes the vault value back
out, and `rotate` sets a new value in the vault and every place, restarts, checks, and rolls
everything back if a check fails. Formats: env, line, json, ini, raw. Transports: local, ssh.
Vault backend: Bitwarden / Vaultwarden CLI. Values are never printed.
