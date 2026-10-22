"""Where the authoritative copy of each secret lives.

The default backend is the Bitwarden / Vaultwarden CLI (`bw`): vaultrotate reads a secret's
value from an item's password field and writes a new value back, keeping the item's history.
A Vault is small on purpose, so other backends (or a test double) are easy to add.
"""
from __future__ import annotations

import json
import subprocess


class Vault:
    def get(self, name: str) -> str | None:
        raise NotImplementedError

    def set(self, name: str, value: str) -> None:
        raise NotImplementedError


class MemoryVault(Vault):
    """An in-memory vault, for tests and dry runs."""
    def __init__(self, initial: dict | None = None):
        self._d = dict(initial or {})

    def get(self, name):
        return self._d.get(name)

    def set(self, name, value):
        self._d[name] = value


class BitwardenVault(Vault):
    """Reads/writes item passwords through the `bw` CLI. Expects an unlocked session in the
    environment (BW_SESSION), as set up by `bw unlock --raw`."""
    def __init__(self, bw: str = "bw", session: str | None = None):
        self.bw = bw
        self.session = session

    def _run(self, args, stdin=None):
        env_args = (["--session", self.session] if self.session else [])
        r = subprocess.run([self.bw, *args, *env_args], input=stdin, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"bw {args[0]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
        return r.stdout

    def _item(self, name):
        out = self._run(["list", "items", "--search", name])
        for it in json.loads(out):
            if it.get("name") == name:
                return it
        return None

    def get(self, name):
        it = self._item(name)
        return (it.get("login") or {}).get("password") if it else None

    def set(self, name, value):
        it = self._item(name)
        if not it:
            raise KeyError(f"vault item {name!r} not found")
        it.setdefault("login", {})["password"] = value
        enc = self._run(["encode"], stdin=json.dumps(it))
        self._run(["edit", "item", it["id"]], stdin=enc)
