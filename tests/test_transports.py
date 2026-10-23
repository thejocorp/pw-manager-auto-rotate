"""Writing keeps the file's mode and owner (a service reading the file as its own user must
still be able to read it), and new files are private. The SSH transport is exercised by running
its remote command in a local shell."""
import os
import stat

import pytest

from pwrotate.transports import LocalTransport, SshTransport


def local_shell_ssh():
    t = SshTransport("nobody@nowhere")
    t.base = ["sh", "-c"]          # run the "remote" command right here
    return t


@pytest.fixture(params=["local", "ssh"])
def transport(request):
    return LocalTransport() if request.param == "local" else local_shell_ssh()


def mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


def test_mode_is_kept(transport, tmp_path):
    f = tmp_path / "server.conf"; f.write_text("secret = old\n"); f.chmod(0o640)
    transport.write(str(f), "secret = new\n")
    assert f.read_text() == "secret = new\n" and mode(f) == 0o640


def test_new_files_are_private(transport, tmp_path):
    f = tmp_path / "new.env"
    transport.write(str(f), "TOKEN=x\n")
    assert mode(f) == 0o600


def test_explicit_mode_wins(transport, tmp_path):
    f = tmp_path / "app.env"; f.write_text("A=1\n"); f.chmod(0o644)
    transport.write(str(f), "A=2\n", mode=0o600)
    assert mode(f) == 0o600


@pytest.mark.skipif(os.geteuid() != 0, reason="needs root to hand a file to another user")
def test_owner_is_kept_as_root(transport, tmp_path):
    f = tmp_path / "server.conf"; f.write_text("x\n"); f.chmod(0o640)
    os.chown(f, 65534, 65534)
    transport.write(str(f), "y\n")
    st = os.stat(f)
    assert (st.st_uid, st.st_gid) == (65534, 65534) and mode(f) == 0o640


def test_foreign_owner_without_rights_is_refused_locally(tmp_path, monkeypatch):
    f = tmp_path / "x.env"; f.write_text("A=1\n")
    real = os.stat
    monkeypatch.setattr("pwrotate.transports.os.geteuid", lambda: real(f).st_uid + 1)

    def no_chown(*a):
        raise PermissionError("not allowed")
    monkeypatch.setattr("pwrotate.transports.os.chown", no_chown)
    with pytest.raises(OSError, match="belongs to uid"):
        LocalTransport().write(str(f), "A=2\n")
    assert f.read_text() == "A=1\n" and not (tmp_path / "x.env.pwrotate.tmp").exists()
