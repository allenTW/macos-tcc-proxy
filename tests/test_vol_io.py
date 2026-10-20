import builtins
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import vol_io  # noqa: E402


def test_read_text_direct(tmp_path):
    p = tmp_path / "a.json"
    p.write_text("hi", encoding="utf-8")
    assert vol_io.read_text(str(p), proxy=lambda *a: pytest.fail("must not use the proxy")) == "hi"


def test_read_text_falls_back_on_denied(monkeypatch):
    real_open = builtins.open

    def fake_open(path, *a, **k):
        if str(path).startswith("/Volumes/"):
            raise PermissionError(1, "Operation not permitted")
        return real_open(path, *a, **k)
    monkeypatch.setattr(builtins, "open", fake_open)
    calls = []
    out = vol_io.read_text("/Volumes/X/q.json", proxy=lambda argv, t: calls.append(argv) or (0, "{}", ""))
    assert out == "{}" and calls == [["/bin/cat", "/Volumes/X/q.json"]]


def test_read_text_missing_file_is_not_proxied(tmp_path):
    with pytest.raises(FileNotFoundError):
        vol_io.read_text(str(tmp_path / "nope"), proxy=lambda *a: pytest.fail("must not use the proxy"))


def test_read_text_proxy_failure_raises(monkeypatch):
    monkeypatch.setattr(builtins, "open", lambda *a, **k: (_ for _ in ()).throw(PermissionError(1, "x")))
    with pytest.raises(PermissionError):
        vol_io.read_text("/Volumes/X/q", proxy=lambda argv, t: (1, "", "cat: denied"))


def test_local_copy_direct(tmp_path):
    src = tmp_path / "db.sqlite"
    src.write_bytes(b"\x00\x01data")
    dest = vol_io.local_copy(str(src), cache=str(tmp_path / "c"), proxy=lambda *a: pytest.fail("must not use the proxy"))
    assert open(dest, "rb").read() == b"\x00\x01data"


def test_local_copy_via_proxy(monkeypatch, tmp_path):
    real_open = builtins.open

    def fake_open(path, *a, **k):
        if str(path).startswith("/Volumes/"):
            raise PermissionError(1, "Operation not permitted")
        return real_open(path, *a, **k)
    monkeypatch.setattr(builtins, "open", fake_open)

    def proxy(argv, t):
        assert argv[0] == "/bin/cp" and argv[1] == "/Volumes/X/data.sqlite"
        real_open(argv[2], "wb").write(b"copied")
        return 0, "", ""
    dest = vol_io.local_copy("/Volumes/X/data.sqlite", cache=str(tmp_path), proxy=proxy)
    assert dest.endswith("_data.sqlite") and real_open(dest, "rb").read() == b"copied"


def test_local_copy_reuses_fresh_copy(tmp_path):
    src = tmp_path / "db.sqlite"
    src.write_bytes(b"v1")
    dest = vol_io.local_copy(str(src), cache=str(tmp_path / "c"))
    src.write_bytes(b"v2")
    t = os.path.getmtime(dest)
    assert open(vol_io.local_copy(str(src), cache=str(tmp_path / "c"), max_age=3600, now=t + 60), "rb").read() == b"v1"
    assert open(vol_io.local_copy(str(src), cache=str(tmp_path / "c"), max_age=3600, now=t + 4000), "rb").read() == b"v2"


def test_sqlite_snapshot_includes_wal(tmp_path):
    import sqlite3
    db = str(tmp_path / "live.db")
    c = sqlite3.connect(db)
    c.execute("pragma journal_mode=wal")
    c.execute("create table t(x)")
    c.execute("insert into t values (1), (2)")
    c.commit()                                   # rows sit in -wal while c stays open
    snap = vol_io.sqlite_snapshot(db, cache=str(tmp_path / "c"), proxy=lambda *a: pytest.fail("must not use the proxy"))
    r = sqlite3.connect("file:%s?mode=ro&immutable=1" % snap, uri=True)
    assert r.execute("select count(*) from t").fetchone()[0] == 2
    c.close()


def test_sqlite_snapshot_via_proxy_when_denied(tmp_path, monkeypatch):
    import sqlite3
    real = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda p, **k: (_ for _ in ()).throw(sqlite3.DatabaseError("authorization denied"))
                        if str(p).startswith("file:/Volumes/") else real(p, **k))

    def proxy(argv, t):
        assert argv[:2] == ["/usr/bin/sqlite3", "/Volumes/X/data.db"] and argv[2].startswith(".backup '")
        open(argv[2][9:-1], "wb").write(b"snap")
        return 0, "", ""
    snap = vol_io.sqlite_snapshot("/Volumes/X/data.db", cache=str(tmp_path), proxy=proxy)
    assert open(snap, "rb").read() == b"snap"


def test_run_direct_success():
    assert vol_io.run(["/bin/echo", "ok"], proxy=lambda *a: pytest.fail("must not use the proxy"))[:2] == (0, "ok\n")


def test_run_retries_through_proxy_when_denied():
    argv = ["/bin/sh", "-c", "echo \"python3: can't open file 'x': [Errno 1] Operation not permitted\" >&2; exit 2"]
    calls = []
    got = vol_io.run(argv, proxy=lambda a, t, cwd: calls.append(a) or (0, "via proxy", ""))
    assert got == (0, "via proxy", "") and calls == [argv]


def test_run_other_failures_not_retried():
    got = vol_io.run(["/bin/sh", "-c", "echo boom >&2; exit 3"], proxy=lambda *a: pytest.fail("must not use the proxy"))
    assert got[0] == 3 and "boom" in got[2]
