import json
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import mac_proxy  # noqa: E402


@pytest.fixture
def fake_daemon(tmp_path, monkeypatch):
    req, res = tmp_path / "req", tmp_path / "res"
    req.mkdir()
    res.mkdir()
    monkeypatch.setattr(mac_proxy, "REQ", req)
    monkeypatch.setattr(mac_proxy, "RES", res)

    def serve(answer):
        def loop():
            for _ in range(200):
                for f in req.glob("*.json"):
                    body = json.loads(f.read_text())
                    f.unlink()
                    (res / f.name).write_text(json.dumps(answer(body)))
                    return
                time.sleep(0.02)
        t = threading.Thread(target=loop, daemon=True)
        t.start()
        return t
    return serve


def test_call_round_trip(fake_daemon):
    fake_daemon(lambda body: {"ok": True, "result": {"verb": body["verb"], "args": body["args"]}})
    out = mac_proxy.call("run", argv=["/bin/echo", "hi"])
    assert out["verb"] == "run" and out["args"]["argv"] == ["/bin/echo", "hi"]


def test_call_error_carries_result(fake_daemon):
    fake_daemon(lambda body: {"ok": False, "error": "exit 3", "code": 3, "stdout": "", "stderr": "boom"})
    with pytest.raises(mac_proxy.ProxyError) as e:
        mac_proxy.call("run", argv=["/bin/false"])
    assert e.value.res["code"] == 3 and "exit 3" in str(e.value)


def test_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(mac_proxy, "REQ", tmp_path / "missing")
    with pytest.raises(mac_proxy.ProxyError):
        mac_proxy.call("ping")
