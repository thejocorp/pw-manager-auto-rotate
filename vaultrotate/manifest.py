"""Load the manifest: which secrets exist and, for each, where its copies live.

JSON is read with the standard library. YAML is read only if PyYAML is installed
(`pip install vaultrotate[yaml]`). No secret values are stored in the manifest, only names and
locations.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Place:
    host: str
    file: str
    format: str
    key: str = ""
    mode: int | None = None


@dataclass
class Step:
    host: str
    cmd: str
    stdin: bool = False


@dataclass
class Secret:
    name: str
    places: list = field(default_factory=list)
    kind: str = "generated"     # generated | provider
    bytes: int = 32
    restart: list = field(default_factory=list)
    check: list = field(default_factory=list)


def _secret(d: dict) -> Secret:
    return Secret(
        name=d["name"],
        kind=d.get("kind", "generated"),
        bytes=int(d.get("bytes", 32)),
        places=[Place(host=p["host"], file=p["file"], format=p["format"], key=p.get("key", ""),
                      mode=(int(str(p["mode"]), 8) if "mode" in p else None)) for p in d.get("places", [])],
        restart=[Step(host=s["host"], cmd=s["cmd"], stdin=s.get("stdin", False)) for s in d.get("restart", [])],
        check=[Step(host=s["host"], cmd=s["cmd"], stdin=s.get("stdin", False)) for s in d.get("check", [])],
    )


def load(path) -> dict:
    text = Path(path).read_text()
    if str(path).endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError as e:
            raise RuntimeError("YAML manifests need PyYAML: pip install vaultrotate[yaml]") from e
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return {s.name: s for s in (_secret(d) for d in data.get("secrets", []))}
