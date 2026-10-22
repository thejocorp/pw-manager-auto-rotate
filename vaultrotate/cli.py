"""Command line.

    vaultrotate status [NAME]            where each copy agrees with the vault (fingerprints only)
    vaultrotate push NAME                write the vault value to every place, restart, check
    vaultrotate rotate NAME              new value -> vault -> every place -> restart -> check
    vaultrotate rotate NAME --stdin      read the new value from standard input (provider keys)
    vaultrotate rotate NAME --dry-run    show what would change, touch nothing

Manifest: --manifest FILE (JSON, or YAML with the [yaml] extra). Vault: the Bitwarden CLI by
default; it must be unlocked (BW_SESSION in the environment). Values are never printed.
"""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .engine import Engine
from .manifest import load
from .vault import BitwardenVault


def _engine(a) -> Engine:
    secrets = load(a.manifest)
    vault = BitwardenVault(bw=os.environ.get("VAULTROTATE_BW", "bw"), session=os.environ.get("BW_SESSION"))
    return Engine(secrets, vault, backup=not a.no_backup)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="vaultrotate", description=__doc__.strip().splitlines()[0])
    ap.add_argument("--manifest", default=os.environ.get("VAULTROTATE_MANIFEST", "secrets.json"))
    ap.add_argument("--no-backup", action="store_true", help="do not keep a .bak copy before writing")
    ap.add_argument("--version", action="version", version=f"vaultrotate {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").add_argument("name", nargs="?")
    p_push = sub.add_parser("push"); p_push.add_argument("name")
    p_rot = sub.add_parser("rotate")
    p_rot.add_argument("name")
    p_rot.add_argument("--stdin", action="store_true", help="read the new value from stdin")
    p_rot.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    try:
        eng = _engine(a)
    except (OSError, ValueError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        if a.cmd == "status":
            names = [a.name] if a.name else list(eng.secrets)
            ok = True
            for n in names:
                res = eng.status(n)
                print("\n".join(res.lines))
                ok = ok and res.ok
            return 0 if ok else 1
        if a.cmd == "push":
            res = eng.push(a.name)
        else:
            new = sys.stdin.read().strip() if a.stdin else None
            res = eng.rotate(a.name, new_value=new, dry=a.dry_run)
        print("\n".join(res.lines))
        return 0 if res.ok else 1
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 2


def _run():
    try:
        return main()
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(_run())
