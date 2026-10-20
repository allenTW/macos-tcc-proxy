# macos-tcc-proxy

A tiny permission proxy for automation that runs under Claude Code (or launchd) on macOS.

**Problem.** macOS files a privacy grant (Automation, Screen Recording, Downloads/removable volumes) under the process that asks. A process spawned by Claude Code is attributed to the Claude binary, whose path contains the version number, so the prompts come back after every update. launchd jobs also cannot read some external volumes and fail with "Operation not permitted" or, worse, silently return nothing.

**Approach.** A launchd-run `/usr/bin/osascript` JXA daemon (`daemon.js`) polls a request directory and answers through a response directory. The grant attaches to the stable osascript binary, asked once. `mac_proxy.py` is the client; `vol_io.py` tries direct file access first and falls back through the proxy on "Operation not permitted".

```text
mac_proxy.py run /bin/ls -la ~/Downloads
mac_proxy.py applescript '...'      mac_proxy.py jxa '...'
mac_proxy.py screenshot /abs/path.png
```

From Python: `from mac_proxy import call`.

## Install

```bash
./install.sh     # installs to ~/.mac-proxy and loads a launchd job (label com.example.mac-proxy)
```

macOS asks for each permission the first time it is needed; approve once. Pair with `bash_guard.py` from `claude-code-guardrails` to stop sessions from calling osascript directly.

## Test

```bash
python3 -m pytest -q     # no daemon, network or real home directory needed
```

## Limits

- macOS only. The behaviours described were observed on our own machine; other macOS versions are untested.
- Anything that can write to the request directory can run commands as the proxy user. Keep `~/.mac-proxy` private (mode 700).

## 繁體中文簡介

讓 Claude Code／launchd 的自動化有固定的 macOS 權限主體：授權掛在穩定的 `/usr/bin/osascript` 上，Claude 更新後不必重新授權；`vol_io` 處理 launchd 讀不到外接碟的情況。安裝：`./install.sh`；測試：`python3 -m pytest -q`。

## License

MIT, see `LICENSE`.
