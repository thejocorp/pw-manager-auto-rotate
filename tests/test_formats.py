import pytest
from vaultrotate import formats


def test_env_get_set_roundtrip():
    text = "# config\nexport API_KEY=\"old-value\"\nOTHER=keep\n"
    assert formats.get(text, "env", "API_KEY") == "old-value"
    new = formats.set(text, "env", "API_KEY", "new-value")
    assert formats.get(new, "env", "API_KEY") == "new-value"
    assert "OTHER=keep" in new and 'export API_KEY="new-value"' in new


def test_env_append_when_absent():
    new = formats.set("A=1\n", "env", "TOKEN", "xyz")
    assert formats.get(new, "env", "TOKEN") == "xyz"
    assert "A=1" in new


def test_line():
    text = "listen: 0.0.0.0\nregistration_shared_secret: OLD\nx: y\n"
    key = "registration_shared_secret: "
    assert formats.get(text, "line", key) == "OLD"
    new = formats.set(text, "line", key, "NEW")
    assert formats.get(new, "line", key) == "NEW"
    assert "x: y" in new


def test_json_nested():
    text = '{"database": {"password": "old"}, "keep": 1}\n'
    assert formats.get(text, "json", "database.password") == "old"
    new = formats.set(text, "json", "database.password", "new")
    assert formats.get(new, "json", "database.password") == "new"
    assert '"keep"' in new


def test_json_missing_key_raises():
    with pytest.raises(KeyError):
        formats.set('{"a": 1}', "json", "b", "x")


def test_ini():
    text = "[server]\nsecret = old\nname = keep\n"
    assert formats.get(text, "ini", "server.secret") == "old"
    new = formats.set(text, "ini", "server.secret", "new")
    assert formats.get(new, "ini", "server.secret") == "new"
    assert "name = keep" in new


def test_raw():
    assert formats.get("a-token\n", "raw", "") == "a-token"
    assert formats.set("a-token", "raw", "", "b-token") == "b-token\n"
