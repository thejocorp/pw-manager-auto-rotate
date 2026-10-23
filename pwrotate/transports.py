"""How pwrotate reads and writes a file, and runs a command, on a host.

A place names a host. The host string chooses the transport:
  "local"            the machine pwrotate runs on
  "ssh:user@host"    over SSH (keys set up already; no password prompts)

Both expose the same three operations, so the engine does not care which is used. Add your own
(for a container runner, a remote agent, ...) by subclassing Transport and registering it.
"""
from __future__ import annotations

import os
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
        """Atomic replace that keeps the file's mode and owner: a service that reads the file
        as its own user must still be able to read it afterwards. New files are private (600)."""
        p = Path(path)
        tmp = p.with_name(p.name + ".pwrotate.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(content)
        old = p.stat() if p.exists() else None
        tmp.chmod(mode if mode is not None else (old.st_mode & 0o7777 if old else 0o600))
        if old is not None and (old.st_uid, old.st_gid) != (os.geteuid(), os.getegid()):
            try:
                os.chown(tmp, old.st_uid, old.st_gid)
            except PermissionError:
                tmp.unlink()
                raise OSError(f"{path} belongs to uid {old.st_uid}:{old.st_gid}; writing it as another user "
                              "would change its owner. Run pwrotate as root or as that user.")
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
        # on the remote: private temp file, the old file's mode and owner copied onto it, then an
        # atomic move into place (GNU coreutils --reference; plain chmod for an explicit mode)
        tmp = _shq(path + ".pwrotate.tmp")
        q = _shq(path)
        keep = (f"if [ -e {q} ]; then chmod --reference={q} {tmp} && "
                f"{{ chown --reference={q} {tmp} 2>/dev/null || [ \"$(stat -c %u:%g {q})\" = \"$(id -u):$(id -g)\" ]; }}; fi && ")
        m = f"chmod {mode:o} {tmp} && " if mode is not None else ""
        r = subprocess.run(self.base + [f"umask 077 && cat > {tmp} && {keep}{m}mv {tmp} {q}"],
                           input=content, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            subprocess.run(self.base + [f"rm -f {tmp}"], capture_output=True, timeout=60)
            raise OSError(f"remote write to {path} failed (mode/owner could not be kept, or no access): "
                          f"{(r.stderr or r.stdout).strip()}")

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
