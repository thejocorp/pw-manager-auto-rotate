"""Read or replace one value inside a config file, by format. Pure string functions.

Formats:
  env   KEY=value lines (a shell/dotenv file); keeps quotes and an `export` prefix.
  line  a "prefix value" line; `key` is the literal prefix including its separator,
        e.g. "registration_shared_secret: ".
  json  a top-level key or a dotted path, e.g. "database.password".
  ini   "section.key" in an INI file.
  raw   the whole file is the value.

get() returns the current value or None. set() returns new file text with the value replaced,
appending the key if it was absent (except ini/json, which require the key to exist).
"""
from __future__ import annotations

import json
import re

FORMATS = ("env", "line", "json", "ini", "raw")


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def get(text: str, fmt: str, key: str) -> str | None:
    if fmt == "raw":
        return text.rstrip("\n")
    if fmt == "env":
        m = re.search(rf"^(?:export\s+)?{re.escape(key)}=(.*)$", text, re.M)
        return _unquote(m.group(1)) if m else None
    if fmt == "line":
        for line in text.splitlines():
            if line.startswith(key):
                return line[len(key):].strip()
        return None
    if fmt == "json":
        node = json.loads(text) if text.strip() else {}
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node if isinstance(node, str) else None
    if fmt == "ini":
        section, _, want = key.partition(".")
        cur = ""
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                cur = s[1:-1].strip()
            elif cur == section and "=" in s and not s.startswith((";", "#")):
                k, _, v = s.partition("=")
                if k.strip() == want:
                    return v.strip()
        return None
    raise ValueError(f"unknown format: {fmt}")


def set(text: str, fmt: str, key: str, value: str) -> str:
    if fmt == "raw":
        return value if value.endswith("\n") else value + "\n"
    if fmt == "env":
        pat = re.compile(rf"^((?:export\s+)?{re.escape(key)}=)(.*)$", re.M)

        def repl(m):
            old = m.group(2)
            if len(old) >= 2 and old[0] == old[-1] and old[0] in ("'", '"'):
                return m.group(1) + old[0] + value + old[0]
            return m.group(1) + value

        new, n = pat.subn(repl, text, count=1)
        if n:
            return new
        sep = "" if text == "" or text.endswith("\n") else "\n"
        return text + sep + f"{key}={value}\n"
    if fmt == "line":
        out, done = [], False
        for line in text.splitlines():
            if not done and line.startswith(key):
                out.append(key + value)
                done = True
            else:
                out.append(line)
        if not done:
            out.append(key + value)
        return "\n".join(out) + ("\n" if text.endswith("\n") or not text else "")
    if fmt == "json":
        node = json.loads(text) if text.strip() else {}
        parts = key.split(".")
        cur = node
        for part in parts[:-1]:
            if not isinstance(cur.get(part), dict):
                raise KeyError(f"json path {key!r} does not exist")
            cur = cur[part]
        if parts[-1] not in cur:
            raise KeyError(f"json key {key!r} does not exist")
        cur[parts[-1]] = value
        return json.dumps(node, indent=2) + "\n"
    if fmt == "ini":
        section, _, want = key.partition(".")
        out, cur, done = [], "", False
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                cur = s[1:-1].strip()
            if not done and cur == section and "=" in s and not s.startswith((";", "#")):
                k, sep, _ = line.partition("=")
                if k.strip() == want:
                    out.append(f"{k}={' ' if line[len(k) + 1:].startswith(' ') else ''}{value}")
                    done = True
                    continue
            out.append(line)
        if not done:
            raise KeyError(f"ini key {key!r} does not exist")
        return "\n".join(out) + ("\n" if text.endswith("\n") else "")
    raise ValueError(f"unknown format: {fmt}")
