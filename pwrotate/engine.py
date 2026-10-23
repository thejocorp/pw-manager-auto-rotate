"""The engine: check where a secret's copies disagree, push the vault value out, or rotate.

Rotate is the careful one: new value -> vault -> every place (each backed up first) -> restart
-> check. If any check fails, every place and the vault are put back to the old value. A secret
value is never printed; places are compared by fingerprint.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import formats
from .manifest import describe
from .transports import for_host
from .util import backup_suffix, fingerprint, random_value, same


@dataclass
class Result:
    name: str
    ok: bool = True
    lines: list = field(default_factory=list)

    def add(self, line, ok=True):
        self.lines.append(line)
        if not ok:
            self.ok = False
        return self


class Engine:
    def __init__(self, secrets: dict, vault, transport=for_host, backup: bool = True):
        self.secrets = secrets
        self.vault = vault
        self.transport = transport
        self.backup = backup

    def _secret(self, name):
        if name not in self.secrets:
            raise KeyError(f"no secret named {name!r} in the manifest")
        return self.secrets[name]

    def _read(self, place):
        tx = self.transport(place.host)
        text = tx.read(place.file)
        if text is None:
            return None
        return formats.get(text, place.format, place.key)

    def _write(self, place, value):
        tx = self.transport(place.host)
        text = tx.read(place.file)
        if text is None:
            text = ""
        if self.backup and text:
            tx.write(place.file + backup_suffix(), text)
        tx.write(place.file, formats.set(text, place.format, place.key, value), mode=place.mode)

    def _steps(self, steps, value, result, kind):
        for st in steps:
            rc, out = self.transport(st.host).run(st.cmd, stdin=(value if st.stdin else None))
            result.add(f"  {kind} {st.host}: {'ok' if rc == 0 else 'FAILED ' + out.strip()[-160:]}", rc == 0)
            if rc != 0:
                return False
        return True

    def status(self, name) -> Result:
        s = self._secret(name)
        want = self.vault.get(name)
        r = Result(name).add(f"{name}: vault {fingerprint(want)}")
        for p in s.places:
            got = self._read(p)
            state = "missing" if got is None else ("same" if same(got, want) else f"DIFFERENT {fingerprint(got)}")
            r.add(f"  {p.host}:{p.file} [{p.format}] {state}", got is not None and (want is None or same(got, want)))
        return r

    def push(self, name, dry=False) -> Result:
        s = self._secret(name)
        want = self.vault.get(name)
        r = Result(name)
        if want is None:
            return r.add(f"{name}: not in the vault, nothing to push", False)
        r.add(f"{name}: pushing {fingerprint(want)}" + (" (dry run)" if dry else ""))
        for p in s.places:
            if same(self._read(p), want):
                r.add(f"  {p.host}:{p.file}: already same")
                continue
            if not dry:
                self._write(p, want)
            r.add(f"  {p.host}:{p.file}: {'would write' if dry else 'written'}")
        if not dry:
            self._steps(s.restart, want, r, "restart")
            self._steps(s.check, want, r, "check")
        return r

    def rotate(self, name, new_value=None, dry=False) -> Result:
        s = self._secret(name)
        old = self.vault.get(name)
        new = new_value if new_value is not None else random_value(s.bytes)
        r = Result(name).add(f"{name}: {fingerprint(old)} -> {fingerprint(new)}" + (" (dry run)" if dry else ""))
        if dry:
            for p in s.places:
                r.add(f"  {p.host}:{p.file}: would write")
            return r
        self.vault.set(name, new, notes=describe(s))
        for p in s.places:
            self._write(p, new)
            r.add(f"  {p.host}:{p.file}: written")
        if self._steps(s.restart, new, r, "restart") and self._steps(s.check, new, r, "check"):
            return r
        # a check failed: put the old value back everywhere
        r.add(f"{name}: a check failed, rolling back to {fingerprint(old)}", False)
        if old is not None:
            self.vault.set(name, old)
            for p in s.places:
                self._write(p, old)
            self._steps(s.restart, old, r, "rollback restart")
        return r
