"""Where the authoritative copy of each secret lives: your Bitwarden or Vaultwarden vault.

pwrotate keeps each secret as a Login item whose name is the secret's name and whose password
field is the value. Writing a new value keeps the item's password history, so every change can
be undone in any Bitwarden app. The item's notes list every place the secret is used.

A Vault is small on purpose (get, set), so other backends or a test double are easy to add.
"""
from __future__ import annotations

import json
import subprocess

NOTES_MARK = "-- pw-manager-auto-rotate: where this secret lives --"


class Vault:
    def get(self, name: str) -> str | None:
        raise NotImplementedError

    def set(self, name: str, value: str, notes: str | None = None) -> None:
        raise NotImplementedError

    def exists(self, name: str) -> bool:
        return self.get(name) is not None


class MemoryVault(Vault):
    """An in-memory vault, for tests and dry runs."""
    def __init__(self, initial: dict | None = None):
        self._d = dict(initial or {})
        self.notes = {}

    def get(self, name):
        return self._d.get(name)

    def set(self, name, value, notes=None):
        self._d[name] = value
        if notes is not None:
            self.notes[name] = notes


def merge_notes(existing: str | None, block: str) -> str:
    """Your own notes stay; only the part below NOTES_MARK is ours and gets replaced."""
    mine = (existing or "").split(NOTES_MARK)[0].rstrip()
    ours = f"{NOTES_MARK}\n{block}".rstrip()
    return f"{mine}\n\n{ours}" if mine else ours


class BitwardenVault(Vault):
    """Talks to Bitwarden or a self-hosted Vaultwarden through the official `bw` CLI.

    The CLI must be logged in and unlocked (`export BW_SESSION=$(bw unlock --raw)`); point it at
    a self-hosted server first with `bw config server https://vault.example.com`. With
    `organization` (and `collection`), items are looked up in and created in that organization,
    so a team shares them; names or ids both work.
    """
    def __init__(self, bw: str = "bw", session: str | None = None, organization: str | None = None,
                 collection: str | None = None, sync: bool = True):
        self.bw = bw
        self.session = session
        self.organization = organization
        self.collection = collection
        self._want_sync = sync
        self._synced = False
        self._org_id = None
        self._col_id = None

    # -- plumbing ---------------------------------------------------------------------------
    def _run(self, args, stdin=None):
        extra = ["--session", self.session] if self.session else []
        try:
            r = subprocess.run([self.bw, *args, *extra], input=stdin, capture_output=True, text=True, timeout=120)
        except FileNotFoundError as e:
            raise RuntimeError(f"the Bitwarden CLI ({self.bw}) is not installed; see `pwrotate doctor`") from e
        if r.returncode != 0:
            raise RuntimeError(f"bw {args[0]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
        return r.stdout

    def _sync(self):
        if self._want_sync and not self._synced:
            self._run(["sync"])
            self._synced = True

    def status(self) -> dict:
        """`bw status`: serverUrl, userEmail, lastSync and status (unauthenticated, locked, unlocked)."""
        return json.loads(self._run(["status"]) or "{}")

    def version(self) -> str:
        return self._run(["--version"]).strip()

    def org_id(self):
        if self.organization and self._org_id is None:
            orgs = json.loads(self._run(["list", "organizations"]))
            hit = [o for o in orgs if self.organization in (o.get("id"), o.get("name"))]
            if not hit:
                raise RuntimeError(f"Bitwarden organization {self.organization!r} not found for this account")
            self._org_id = hit[0]["id"]
        return self._org_id

    def collection_id(self):
        if self.collection and self._col_id is None:
            org = self.org_id()
            if not org:
                raise RuntimeError("a Bitwarden collection needs an organization (bitwarden.organization)")
            cols = json.loads(self._run(["list", "org-collections", "--organizationid", org]))
            hit = [c for c in cols if self.collection in (c.get("id"), c.get("name"))]
            if not hit:
                raise RuntimeError(f"collection {self.collection!r} not found in organization {self.organization!r}")
            self._col_id = hit[0]["id"]
        return self._col_id

    def _item(self, name):
        self._sync()
        args = ["list", "items", "--search", name]
        if self.org_id():
            args += ["--organizationid", self.org_id()]
        for it in json.loads(self._run(args)):
            if it.get("name") == name:
                return it
        return None

    # -- the Vault interface -----------------------------------------------------------------
    def get(self, name):
        it = self._item(name)
        return (it.get("login") or {}).get("password") if it else None

    def exists(self, name):
        return self._item(name) is not None

    def set(self, name, value, notes=None):
        it = self._item(name)
        if it is None:
            it = {"type": 1, "name": name, "notes": None, "favorite": False, "fields": [], "reprompt": 0,
                  "login": {"uris": [], "username": None, "password": value, "totp": None},
                  "folderId": None, "organizationId": self.org_id(),
                  "collectionIds": [self.collection_id()] if self.collection else None}
            if notes is not None:
                it["notes"] = merge_notes(None, notes)
            self._run(["create", "item"], stdin=self._run(["encode"], stdin=json.dumps(it)))
            return
        it.setdefault("login", {})["password"] = value
        if notes is not None:
            it["notes"] = merge_notes(it.get("notes"), notes)
        self._run(["edit", "item", it["id"]], stdin=self._run(["encode"], stdin=json.dumps(it)))
