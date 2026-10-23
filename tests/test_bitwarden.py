"""The Bitwarden backend and `pwrotate doctor`, against tests/fakebw.py (a stand-in for `bw`)."""
import json
import sys
from pathlib import Path

import pytest

from pwrotate import Engine
from pwrotate.cli import main
from pwrotate.manifest import Place, Secret
from pwrotate.vault import NOTES_MARK, BitwardenVault, merge_notes

FAKE = str(Path(__file__).with_name("fakebw.py"))


@pytest.fixture
def bw(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"items": [], "orgs": [{"id": "org-1", "name": "Homelab"}],
                                 "collections": [{"id": "col-1", "name": "Servers", "organizationId": "org-1"}]}))
    monkeypatch.setenv("FAKEBW_STATE", str(state))
    wrapper = tmp_path / "bw"
    wrapper.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE} \"$@\"\n")
    wrapper.chmod(0o755)

    def read():
        return json.loads(state.read_text())

    def write(**kw):
        d = read(); d.update(kw); state.write_text(json.dumps(d))
    return type("BW", (), {"path": str(wrapper), "read": staticmethod(read), "write": staticmethod(write)})


def test_rotate_creates_a_missing_item_in_the_org_collection_with_notes(bw, tmp_path):
    env = tmp_path / "app.env"; env.write_text("TOKEN=old\n")
    s = Secret(name="svc/token", places=[Place(host="local", file=str(env), format="env", key="TOKEN")])
    v = BitwardenVault(bw=bw.path, organization="Homelab", collection="Servers")
    res = Engine({"svc/token": s}, v, backup=False).rotate("svc/token")
    assert res.ok
    [item] = bw.read()["items"]
    assert item["name"] == "svc/token" and item["organizationId"] == "org-1" and item["collectionIds"] == ["col-1"]
    assert NOTES_MARK in item["notes"] and str(env) in item["notes"]
    assert env.read_text() == f"TOKEN={item['login']['password']}\n"
    assert ["sync"] in bw.read()["calls"]


def test_set_keeps_the_users_own_notes(bw):
    bw.write(items=[{"id": "i1", "type": 1, "name": "db/pw", "notes": "ask Sam before changing",
                     "login": {"password": "a"}}])
    BitwardenVault(bw=bw.path).set("db/pw", "b", notes="- local:/etc/db.env [env PW]")
    [item] = bw.read()["items"]
    assert item["login"]["password"] == "b"
    assert item["notes"].startswith("ask Sam before changing\n\n" + NOTES_MARK)


def test_merge_notes_replaces_only_our_block():
    once = merge_notes("mine", "- a")
    assert merge_notes(once, "- b") == f"mine\n\n{NOTES_MARK}\n- b"


def test_exact_name_match_only(bw):
    bw.write(items=[{"id": "i1", "type": 1, "name": "svc/token-old", "login": {"password": "x"}}])
    assert BitwardenVault(bw=bw.path).get("svc/token") is None


def _manifest(tmp_path, org=True):
    m = {"secrets": [{"name": "svc/token", "places": [{"host": "local", "file": "/x.env", "format": "env", "key": "T"}]}]}
    if org:
        m["bitwarden"] = {"organization": "Homelab", "collection": "Servers"}
    p = tmp_path / "secrets.json"; p.write_text(json.dumps(m)); return str(p)


def test_doctor_reports_missing_items(bw, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PWROTATE_BW", bw.path)
    rc = main(["--manifest", _manifest(tmp_path), "doctor"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "unlocked" in out and "0 of 1 found" in out and 'organization "Homelab"' in out
    assert "missing: svc/token" in out


def test_doctor_all_good(bw, tmp_path, monkeypatch, capsys):
    bw.write(items=[{"id": "i1", "type": 1, "name": "svc/token", "organizationId": "org-1", "login": {"password": "x"}}])
    monkeypatch.setenv("PWROTATE_BW", bw.path)
    assert main(["--manifest", _manifest(tmp_path), "doctor"]) == 0
    assert "1 of 1 found" in capsys.readouterr().out


def test_doctor_locked_says_how_to_unlock(bw, tmp_path, monkeypatch, capsys):
    bw.write(status="locked")
    monkeypatch.setenv("PWROTATE_BW", bw.path)
    assert main(["--manifest", _manifest(tmp_path, org=False), "doctor"]) == 1
    assert "bw unlock --raw" in capsys.readouterr().out


def test_doctor_without_bw(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PWROTATE_BW", str(tmp_path / "no-such-bw"))
    assert main(["--manifest", _manifest(tmp_path), "doctor"]) == 2
    assert "Install the Bitwarden CLI" in capsys.readouterr().out
