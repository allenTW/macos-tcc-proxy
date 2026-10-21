# macos-tcc-proxy

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python 3](https://img.shields.io/badge/python-3-blue.svg)
![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)
![tests: 15 passing](https://img.shields.io/badge/tests-15%20passing-brightgreen.svg)

**Stop macOS from re-asking for privacy permissions every time your automation tool updates: route the privileged work through one tiny launchd-run daemon whose identity never changes.**

## The problem

macOS (TCC, the privacy-permission system) files each grant (Automation, Screen Recording, Downloads, removable/network volumes) under the process that asks. When a tool such as Claude Code spawns your script, macOS attributes the request to that tool's binary. If the binary lives in a versioned path, every update is a "new" app and the prompts come back. launchd jobs have a second problem: they cannot show a prompt at all, so reading an external drive fails with `Operation not permitted` or silently returns nothing.

## The fix

`daemon.js` runs under launchd as `/usr/bin/osascript` (a stable, Apple-signed binary). You approve each permission once for that binary. Clients drop a small JSON request into a directory; the daemon runs it (its children inherit the grants) and writes the answer back.

```text
your script / CLI ──> ~/.mac-proxy/req/<id>.json ──> daemon (osascript, launchd)
        ^                                                   │ runs child with timeout
        └────────── ~/.mac-proxy/res/<id>.json <───────────┘
```

Also included: `vol_io.py`, which tries plain file access first and only falls back through the proxy on `Operation not permitted`.

## Quick start

```bash
git clone https://github.com/allenTW/macos-tcc-proxy.git
cd macos-tcc-proxy
./install.sh                 # copies files to ~/.mac-proxy, loads launchd job com.example.mac-proxy
python3 ~/.mac-proxy/mac_proxy.py ping     # prints "pong" when the daemon is up
```

macOS asks for each permission the first time something needs it; click Allow once. Re-running `install.sh` after edits never re-prompts, because the grants belong to `/usr/bin/osascript`.

## Usage

CLI:

```bash
mac_proxy.py run /bin/ls -la ~/Downloads
mac_proxy.py applescript 'tell application "Finder" to get name of startup disk'
mac_proxy.py jxa 'Application("Finder").name()'
mac_proxy.py screenshot /tmp/shot.png
mac_proxy.py --timeout 120 run /usr/bin/sqlite3 some.db .tables
mac_proxy.py list_tabs        # Chrome tabs (never launches Chrome)
```

Python:

```python
from mac_proxy import call, ProxyError

res = call("run", argv=["/bin/ls", "-la"], cwd="/tmp")   # {"code", "stdout", "stderr"}
try:
    call("applescript", script='tell application "Finder" to get name of startup disk')
except ProxyError as e:
    print(e, e.res)   # failed commands carry code/stdout/stderr in e.res
```

Verbs: `run`, `applescript`, `jxa`, `screenshot`, `ping`, and the Chrome tab verbs `list_tabs`, `active_tab`, `close_tabs`, `set_url`, `open_url`. Default timeout 60 s, maximum 600 s (`daemon.js`). More in [examples/](examples/).

## Security model

Read this before installing. There is **no allowlist**:

- The `run` verb executes any command the requester names, and `applescript`/`jxa` run any script, as your user and with the daemon's privacy grants.
- The only access control is filesystem permissions: `install.sh` makes `~/.mac-proxy` and its `req/`, `res/`, `tmp/` directories mode 700. Anything that can write to `req/` can run commands as you.
- Chrome URL verbs accept only `http(s):`, `about:blank` and the new-tab page.

So the proxy does not reduce what your own account can do; it only changes which process holds the permissions. Details and hardening ideas: [docs/security.md](docs/security.md).

## FAQ

**Does it bypass macOS privacy protection?** No. You still approve every permission yourself, once. It only makes the approval stick to a stable binary.

**Why osascript?** It is a fixed system binary, so its identity does not change across updates of your tools.

**Why does the daemon restart itself?** It exits after about 10 minutes idle or one hour of uptime and launchd restarts it (`KeepAlive`). See [docs/how-it-works.md](docs/how-it-works.md).

**The call times out.** Check `launchctl print gui/$(id -u)/com.example.mac-proxy` and the log at `~/Library/Logs/mac-proxy.log`; a pending permission dialog also blocks the request until clicked.

**Which macOS versions?** Observed on the author's machine only; other versions are untested.

## Docs

- [How it works](docs/how-it-works.md)
- [Security](docs/security.md)
- [Contributing](CONTRIBUTING.md) / [Changelog](CHANGELOG.md)

## Tests

```bash
python3 -m pytest -q tests     # 15 tests; no daemon, network or real home directory needed
```

## 繁體中文簡介

讓自動化工具（Claude Code、launchd）更新後不必重新授權 macOS 隱私權限：授權掛在穩定的 `/usr/bin/osascript` 上，由常駐代理程序代為執行；`vol_io` 處理 launchd 讀不到外接碟的情況。注意：代理沒有白名單，能寫入 `~/.mac-proxy/req` 的人就能以你的身分執行指令，請保持該目錄為 700。安裝：`./install.sh`。

## License

MIT, see [LICENSE](LICENSE).
