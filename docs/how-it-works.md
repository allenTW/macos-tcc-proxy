# How it works

All statements below refer to `daemon.js`, `mac_proxy.py`, `chrome.js`, `vol_io.py` and `install.sh` in this repo.

## Components

| File | Role |
| --- | --- |
| `daemon.js` | JXA program run by launchd as `/usr/bin/osascript -l JavaScript daemon.js`. Polls `req/`, runs jobs, writes `res/`. |
| `mac_proxy.py` | Client library and CLI (`call(verb, **args)`). |
| `chrome.js` | Chrome tab verbs, run by the daemon as a child `osascript` process. |
| `vol_io.py` | Helpers that read files from drives launchd jobs cannot access directly. |
| `install.sh` | Copies files to `~/.mac-proxy`, writes the launchd plist, bootstraps or kickstarts it. |

## Why the grants stick

macOS files a privacy grant under the responsible process. The daemon is `/usr/bin/osascript`, which is stable across updates of your tools. Each job runs as a child of the daemon, so it inherits the daemon as its responsible process (comment in `daemon.js`). Editing `daemon.js` or `chrome.js` does not change the binary, so no new prompt appears.

## Request / response protocol

Directory layout under `~/.mac-proxy`: `req/`, `res/`, `tmp/` (stdout/stderr capture files).

1. The client writes `{"verb": ..., "args": {...}}` to a hidden temp file `req/.<id>.tmp`, then renames it to `req/<id>.json`, so the daemon never reads a half-written file. `<id>` is milliseconds-since-epoch plus 8 random hex characters.
2. The daemon polls `req/` (every 0.2 s idle, 0.05 s while jobs run), reads and deletes each `*.json`, and starts the job.
3. The daemon writes `res/<id>.json`: `{"ok": true, "result": ...}` or `{"ok": false, "error": ..., ...}`.
4. The client polls `res/<id>.json`, deletes it, and returns the result or raises `ProxyError`. If the request is never picked up before the deadline (timeout + 15 s; default 60 s), the client deletes the request so it cannot fire late.

## Verbs

- `ping`: answered directly by the daemon with `pong`.
- `run`: `argv` list; an absolute first element is executed directly, otherwise via `/usr/bin/env`. Optional `cwd` (defaults to the home directory).
- `applescript` / `jxa`: `script` (required) plus optional extra `argv`, run through `osascript -e`.
- `screenshot`: absolute `path` plus optional `options`, run as `/usr/sbin/screencapture -x`.
- `list_tabs`, `active_tab`, `close_tabs`, `set_url`, `open_url`: handled by `chrome.js`. They never launch Chrome; if it is not running the answer is `null`.

Each job is launched through `/usr/bin/perl` with `alarm`, which enforces the per-request timeout (default 60 s, clamped to 1-600 s) and then `exec`s the real command. A job that does not exit within 20 s after its timeout is force-finished with a "stuck" error. Because jobs are separate processes, one hung script does not block others.

## Daemon lifecycle

The daemon exits when idle for about 3000 poll loops (about 10 minutes) and, between jobs, after one hour of uptime; launchd restarts it (`KeepAlive`, `ThrottleInterval` 2 s). The source comment explains the hour limit: a long-running instance once stopped completing `run` requests and a restart fixed it. Result files older than 300 s are removed.

## vol_io

A launchd job runs as its own responsible process, and macOS may refuse it access to some external volumes with `Operation not permitted`; background jobs cannot show the approval prompt. `vol_io.py` tries the direct operation first and only on a permission error repeats it via the proxy's `run` verb:

- `read_text(path)`: direct read, else `/bin/cat` through the proxy.
- `local_copy(path)`: copy to `~/.cache/vol_io`, else `/bin/cp` through the proxy. Optional `max_age` reuses a fresh copy.
- `sqlite_snapshot(path)`: consistent copy using sqlite's backup API (WAL included), else `sqlite3 .backup` through the proxy.
- `run(argv)`: run directly, retry through the proxy if stderr contains `Operation not permitted`.

The comment in `vol_io.py` notes that the proxy must have received the volume grant once (run one warm-up command through it). Behaviour was observed on the author's machine; other macOS versions are untested.
