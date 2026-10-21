# Contributing

Issues and pull requests are welcome.

- Python code uses the standard library only (`mac_proxy.py`, `vol_io.py`); keep it that way.
- Run the tests before opening a PR: `python3 -m pytest -q tests`. Tests must not need the daemon, the network or the real home directory (use `tmp_path` / `monkeypatch`).
- Add a test for behaviour you change; do not weaken existing tests.
- `daemon.js` and `chrome.js` are JXA and can only be exercised on macOS under `osascript`; describe how you verified such changes in the PR.
- Never commit secrets, personal paths, logs or screenshots.
- Security-relevant changes (new verbs, anything that widens what a request can do) need an update to `docs/security.md`.
