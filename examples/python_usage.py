"""Python example. Assumes ./install.sh has been run (client lives in ~/.mac-proxy)."""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/.mac-proxy"))
from mac_proxy import call, ProxyError  # noqa: E402
import vol_io  # noqa: E402

print(call("ping"))                                   # pong

res = call("run", argv=["/bin/ls", "-la"], cwd="/tmp")
print(res["code"], res["stdout"][:200])

try:
    call("run", argv=["/bin/sh", "-c", "exit 3"])
except ProxyError as e:
    print("failed:", e.res.get("code"))               # failed commands carry code/stdout/stderr

# Read a file that a launchd job may not be allowed to open directly:
# direct read first, proxy fallback only on "Operation not permitted".
print(vol_io.read_text("/path/to/external/drive/queue.json"))
