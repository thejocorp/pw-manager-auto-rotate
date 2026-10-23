"""Command line.

    pwrotate doctor                   is Bitwarden reachable, unlocked, and does it hold every secret?
    pwrotate status [NAME]            where each copy agrees with the vault (fingerprints only)
    pwrotate push NAME                write the vault value to every place, restart, check
    pwrotate rotate NAME              new value -> vault -> every place -> restart -> check
    pwrotate rotate NAME --stdin      read the new value from standard input (provider keys)
    pwrotate rotate NAME --dry-run    show what would change, touch nothing

Manifest: --manifest FILE (JSON, or YAML with the [yaml] extra). Vault: Bitwarden or Vaultwarden
through the official `bw` CLI, logged in and unlocked (BW_SESSION in the environment).
Values are never printed.
"""
from __future__ import annotations

import argparse
import calendar
import os
import shutil
import sys
import time

from . import __version__
from .engine import Engine
from .manifest import load, load_settings
from .vault import BitwardenVault


def _vault(a) -> BitwardenVault:
    st = load_settings(a.manifest) if os.path.exists(a.manifest) else {}
    return BitwardenVault(bw=os.environ.get("PWROTATE_BW", "bw"), session=os.environ.get("BW_SESSION"),
                          organization=st.get("organization"), collection=st.get("collection"),
                          sync=not a.no_sync and st.get("sync", True) is not False)


def _ago(iso: str | None) -> str:
    if not iso:
        return "never"
    try:
        t = calendar.timegm(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))  # bw reports UTC
    except ValueError:
        return iso
    m = int((time.time() - t) // 60)
    return "just now" if m < 1 else f"{m} min ago" if m < 120 else f"{m // 60} h ago"


def doctor(a) -> int:
    """Check the whole chain, say what to do about the first thing that is wrong."""
    v = _vault(a)
    row = lambda k, val: print(f"{k:<11} {val}")  # noqa: E731
    path = shutil.which(v.bw)
    if not path:
        row("bw", "NOT FOUND")
        print("\nInstall the Bitwarden CLI: https://bitwarden.com/help/cli/ (npm install -g @bitwarden/cli,\n"
              "or the standalone binary). It works with bitwarden.com and with a self-hosted Vaultwarden.")
        return 2
    row("bw", f"{path} ({v.version()})")
    st = v.status()
    row("server", st.get("serverUrl") or "bitwarden.com (the cloud)")
    row("account", st.get("userEmail") or "-")
    state = st.get("status", "?")
    if state != "unlocked":
        row("vault", state.upper())
        if state == "unauthenticated":
            print("\nLog in once:  bw config server https://your-vault.example   (skip for bitwarden.com)\n"
                  "              bw login")
        print("Then unlock:  export BW_SESSION=$(bw unlock --raw)")
        return 1
    row("vault", f"unlocked, last sync {_ago(st.get('lastSync'))}")
    if not os.path.exists(a.manifest):
        row("manifest", f"{a.manifest}: not found (see examples/ in the repository)")
        return 1
    secrets = load(a.manifest)
    places = sum(len(s.places) for s in secrets.values())
    row("manifest", f"{a.manifest}: {len(secrets)} secret(s), {places} place(s)")
    where = ""
    if v.organization:
        v.org_id()
        where = f' (organization "{v.organization}"' + (f', collection "{v.collection}")' if v.collection else ")")
    missing = [n for n in secrets if not v.exists(n)]
    row("in vault", f"{len(secrets) - len(missing)} of {len(secrets)} found{where}")
    for n in missing:
        print(f"  missing: {n}   (pwrotate rotate {n} creates it)")
    return 1 if missing else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pwrotate", description=__doc__.strip().splitlines()[0])
    ap.add_argument("--manifest", default=os.environ.get("PWROTATE_MANIFEST", "secrets.json"))
    ap.add_argument("--no-backup", action="store_true", help="do not keep a .bak copy before writing")
    ap.add_argument("--no-sync", action="store_true", help="do not run `bw sync` before reading the vault")
    ap.add_argument("--version", action="version", version=f"pwrotate {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="check Bitwarden and the manifest")
    sub.add_parser("status", help="compare every copy with the vault").add_argument("name", nargs="?")
    p_push = sub.add_parser("push", help="write the vault value everywhere"); p_push.add_argument("name")
    p_rot = sub.add_parser("rotate", help="new value everywhere, verified, rolled back on failure")
    p_rot.add_argument("name")
    p_rot.add_argument("--stdin", action="store_true", help="read the new value from stdin")
    p_rot.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    try:
        if a.cmd == "doctor":
            return doctor(a)
        eng = Engine(load(a.manifest), _vault(a), backup=not a.no_backup)
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
    except (OSError, ValueError, RuntimeError, KeyError) as e:
        print(str(e).strip("'\""), file=sys.stderr)
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
