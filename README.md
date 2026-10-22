# vaultrotate

Rotate a secret everywhere it lives, from one vault, with verification and rollback.

A single API key or database password often sits in a dozen places: a `.env` on one server, a
JSON config on another, a YAML file a service reads at boot. Rotating it by hand means editing
each copy, restarting each service, and hoping you did not miss one. `vaultrotate` does it from
one command: it takes the authoritative value from your vault, writes it to every place you
listed, restarts what needs restarting, runs your health checks, and if any check fails it puts
the old value back everywhere. Secret values are never printed; copies are compared by
fingerprint.

```
$ vaultrotate status myapp/api-key
myapp/api-key: vault 3f9c1a2b7d4e
  local:/etc/myapp/app.env [env] same
  ssh:deploy@web2.example:/etc/myapp/app.env [env] DIFFERENT 0a1b2c3d4e5f

$ vaultrotate rotate myapp/api-key
myapp/api-key: 3f9c1a2b7d4e -> 8e2d5f0a9c33
  local:/etc/myapp/app.env: written
  ssh:deploy@web2.example:/etc/myapp/app.env: written
  restart local: ok
  check local: ok
```

## Why

Secret rotation is one of those jobs everyone agrees to do and few actually do, because doing
it safely by hand is fiddly and one missed copy breaks production. `vaultrotate` makes the safe
path the easy path: one source of truth (your vault), one manifest of where each secret lives,
and a rotate that verifies itself and rolls back on failure. It is built for homelabs and small
fleets where a secrets manager with per-service injection would be overkill, but copy-paste
rotation is error-prone.

## How it works

1. A **manifest** lists your secrets and, for each, the **places** a copy lives: a host, a
   file, a format and the key within that file. No values are in the manifest, only locations.
2. The **vault** holds the real value. The default backend is the Bitwarden / Vaultwarden CLI
   (`bw`), reading and writing an item's password field, so every change keeps the item's
   history and can be undone in the app.
3. `rotate` sets a new value in the vault, writes it to every place (backing up each file
   first), runs your restarts and checks, and **rolls every place back** to the old value if a
   check fails.

## Install

```sh
pipx install vaultrotate            # core, no dependencies
pipx install "vaultrotate[yaml]"    # to use YAML manifests
```

Python 3.9+. The core is standard library only. You need the Bitwarden CLI (`bw`) on PATH and
an unlocked session (`export BW_SESSION=$(bw unlock --raw)`); SSH places need key-based SSH
already working.

## The manifest

JSON ([`examples/secrets.example.json`](examples/secrets.example.json)) or YAML
([`examples/secrets.example.yaml`](examples/secrets.example.yaml)):

```yaml
secrets:
  - name: myapp/api-key          # the vault item name
    kind: generated              # generated = random value; provider = you paste one in
    bytes: 32
    places:
      - { host: local, file: /etc/myapp/app.env, format: env, key: API_KEY, mode: "600" }
      - { host: "ssh:deploy@web2.example", file: /etc/myapp/app.env, format: env, key: API_KEY }
    restart:
      - { host: local, cmd: systemctl restart myapp }
    check:
      - { host: local, cmd: "curl -fsS http://127.0.0.1:8080/health" }
```

**Formats** (how the value sits in a file):

| format | the value is | `key` is |
|---|---|---|
| `env` | `KEY=value` in a dotenv/shell file (quotes and `export` kept) | the variable name |
| `line` | the rest of a `prefix value` line | the literal prefix incl. separator, e.g. `"secret: "` |
| `json` | a string at a (possibly dotted) path | e.g. `database.password` |
| `ini` | `key = value` under a section | `section.key` |
| `raw` | the whole file | (unused) |

**Transports** (`host`): `local` for this machine, `ssh:user@host` over SSH. Both read a file,
write a file, and run a command; add your own by subclassing `Transport`.

**Checks** run after a rotation; a non-zero exit triggers rollback. Add `stdin: true` to a step
to receive the new secret value on standard input (handy for a check that must authenticate
with it).

## Commands

```sh
vaultrotate status [NAME]       # where each copy agrees with the vault (fingerprints only)
vaultrotate push NAME           # write the vault value to every place, then restart + check
vaultrotate rotate NAME         # new value -> vault -> every place -> restart -> check -> (rollback)
vaultrotate rotate NAME --stdin # read the new value from stdin (a provider-issued key)
vaultrotate rotate NAME --dry-run
```

Point at a manifest with `--manifest FILE` or `$VAULTROTATE_MANIFEST`. Exit code is `0` on
success, `1` if a place disagrees or a rotation rolled back, `2` on a usage or vault error.

## Safety

- **Values are never printed or logged.** `status` shows a 12-character SHA-256 fingerprint so
  you can see agreement without seeing the secret.
- **Every file is backed up** (`file.bak-<timestamp>`) before it is overwritten, unless you pass
  `--no-backup`.
- **A failed check rolls back** the vault and every place to the previous value.
- The vault item keeps its history, so any change can also be undone in the Bitwarden app.

## Extending

- A new **vault backend**: subclass `Vault` (two methods, `get` and `set`).
- A new **transport** (a container runner, a config-management agent): subclass `Transport`
  (`read`, `write`, `run`).

## What it does not do

- It is not a secret *store* and not an *injector*. It keeps the copies you already have in
  sync with one source of truth; it does not hand secrets to running processes at request time.
- It does not discover where your secrets are; you tell it, in the manifest.

## License

MIT. See [LICENSE](LICENSE).
