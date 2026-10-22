"""How vaultrotate reads and writes a file, and runs a command, on a host.

A place names a host. The host string chooses the transport:
  "local"            the machine vaultrotate runs on
  "ssh:user@host"    over SSH (keys set up already; no password prompts)

Both expose the same three operations, so the engine does not care which is used. Add your own
(for a container runner, a remote agent, ...) by subclassing Transport and registering it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class Transport:
    def read(self, path: str) -> str | None:
        raise NotImplementedError

    def write(self, path: str, content: str, mode: int | None = None) -> None:
        raise NotImplementedError

    def run(self, cmd: str, stdin: str | None = None, timeout: int = 120) -> tuple[int, str]:
        raise NotImplementedError


class LocalTransport(Transport):
    def read(self, path):
        p = Path(path)
        return p.read_text() if p.is_file() else None

    def write(self, path, content, mode=None):
        p = Path(path)
        tmp = p.with_name(p.name + ".vaultrotate.tmp")
        tmp.write_text(content)
        if mode is not None:
            tmp.chmod(mode)
        elif p.exists():
            tmp.chmod(p.stat().st_mode & 0o7777)
        else:
            tmp.chmod(0o600)
        tmp.replace(p)

    def run(self, cmd, stdin=None, timeout=120):
        r = subprocess.run(cmd, shell=True, input=stdin, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)


class SshTransport(Transport):
    def __init__(self, target: str):
        self.target = target  # user@host
        self.base = ["ssh", "-o", "BatchMode=yes", target]

    def read(self, path):
        r = subprocess.run(self.base + ["cat -- " + _shq(path)], capture_output=True, text=True, timeout=60)
        return r.stdout if r.returncode == 0 else None

    def write(self, path, content, mode=None):
        # write to a temp file, set mode, move into place, all on the remote
        tmp = _shq(path + ".vaultrotate.tmp")
        q = _shq(path)
        m = f"chmod {mode:o} {tmp} && " if mode is not None else ""
        r = subprocess.run(self.base + [f"cat > {tmp} && {m}mv {tmp} {q}"],
                           input=content, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise OSError(f"remote write to {path} failed: {(r.stderr or r.stdout).strip()}")

    def run(self, cmd, stdin=None, timeout=120):
        r = subprocess.run(self.base + [cmd], input=stdin, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)


def _shq(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def for_host(host: str) -> Transport:
    if host in ("local", "localhost", ""):
        return LocalTransport()
    if host.startswith("ssh:"):
        return SshTransport(host[4:])
    raise ValueError(f"no transport for host {host!r} (use 'local' or 'ssh:user@host')")
