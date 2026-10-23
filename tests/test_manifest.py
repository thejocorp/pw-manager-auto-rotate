import json
from pwrotate.manifest import load


def test_load_json(tmp_path):
    m = {
        "secrets": [
            {"name": "svc/token", "kind": "generated", "bytes": 24,
             "places": [{"host": "local", "file": "/app.env", "format": "env", "key": "TOKEN", "mode": "600"}],
             "restart": [{"host": "local", "cmd": "systemctl restart svc"}],
             "check": [{"host": "local", "cmd": "curl -fsS localhost/health"}]}
        ]
    }
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps(m))
    secrets = load(str(p))
    assert "svc/token" in secrets
    s = secrets["svc/token"]
    assert s.places[0].mode == 0o600 and s.places[0].key == "TOKEN"
    assert s.restart[0].cmd.startswith("systemctl")
