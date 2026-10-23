import pytest
from pwrotate import Engine, MemoryVault
from pwrotate.manifest import Place, Secret, Step


class FakeWorld:
    """In-memory hosts: files keyed by (host, path), plus a record of commands run."""
    def __init__(self, files=None, fail_checks=False):
        self.files = dict(files or {})
        self.runs = []
        self.fail_checks = fail_checks

    def transport(self, host):
        world = self

        class T:
            def read(self, path):
                return world.files.get((host, path))

            def write(self, path, content, mode=None):
                world.files[(host, path)] = content

            def run(self, cmd, stdin=None, timeout=120):
                world.runs.append((host, cmd, stdin))
                if cmd == "CHECK" and world.fail_checks:
                    return 1, "health check failed"
                return 0, "ok"

        return T()


def secret(**kw):
    kw.setdefault("places", [Place(host="h1", file="/app.env", format="env", key="TOKEN")])
    return Secret(name="svc/token", **kw)


def test_status_reports_agreement():
    s = secret()
    world = FakeWorld({("h1", "/app.env"): "TOKEN=abc\n"})
    eng = Engine({"svc/token": s}, MemoryVault({"svc/token": "abc"}), transport=world.transport)
    res = eng.status("svc/token")
    assert res.ok and any("same" in line for line in res.lines)


def test_status_detects_drift():
    s = secret()
    world = FakeWorld({("h1", "/app.env"): "TOKEN=stale\n"})
    eng = Engine({"svc/token": s}, MemoryVault({"svc/token": "fresh"}), transport=world.transport)
    res = eng.status("svc/token")
    assert not res.ok and any("DIFFERENT" in line for line in res.lines)


def test_push_writes_vault_value():
    s = secret()
    world = FakeWorld({("h1", "/app.env"): "TOKEN=stale\n"})
    eng = Engine({"svc/token": s}, MemoryVault({"svc/token": "fresh"}), transport=world.transport, backup=False)
    eng.push("svc/token")
    assert world.files[("h1", "/app.env")] == "TOKEN=fresh\n"


def test_rotate_updates_everywhere_and_keeps_backup():
    s = secret(restart=[Step("h1", "RESTART")], check=[Step("h1", "CHECK")])
    world = FakeWorld({("h1", "/app.env"): "TOKEN=old\n"})
    vault = MemoryVault({"svc/token": "old"})
    eng = Engine({"svc/token": s}, vault, transport=world.transport)
    res = eng.rotate("svc/token", new_value="brandnew")
    assert res.ok
    assert vault.get("svc/token") == "brandnew"
    assert world.files[("h1", "/app.env")] == "TOKEN=brandnew\n"
    assert any(path.startswith("/app.env.bak-") for (_, path) in world.files)


def test_rotate_rolls_back_on_failed_check():
    s = secret(restart=[Step("h1", "RESTART")], check=[Step("h1", "CHECK")])
    world = FakeWorld({("h1", "/app.env"): "TOKEN=old\n"}, fail_checks=True)
    vault = MemoryVault({"svc/token": "old"})
    eng = Engine({"svc/token": s}, vault, transport=world.transport)
    res = eng.rotate("svc/token", new_value="brandnew")
    assert not res.ok
    assert vault.get("svc/token") == "old"                      # vault restored
    assert world.files[("h1", "/app.env")] == "TOKEN=old\n"     # file restored


def test_unknown_secret():
    eng = Engine({}, MemoryVault())
    with pytest.raises(KeyError):
        eng.status("nope")
