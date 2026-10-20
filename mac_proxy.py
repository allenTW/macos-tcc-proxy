#!/usr/bin/python3
"""Client for mac-proxy (daemon.js under launchd). Anything that needs a macOS privacy grant (controlling another
app with AppleScript/JXA, screenshots) goes through here instead of being run from a Claude session: a process
Claude spawns is attributed to the Claude Code binary, whose path changes with every update, so macOS asks again
and again. The daemon is /usr/bin/osascript run by launchd and keeps each grant for good. This process itself
sends no Apple Events.

  mac_proxy.py [--timeout S] applescript 'tell application "Finder" to …'   ('-' reads the script from stdin)
  mac_proxy.py [--timeout S] jxa 'Application("Finder").name()'
  mac_proxy.py [--timeout S] run CMD [ARG ...]          # e.g. a CLI that needs the proxy's grants
  mac_proxy.py screenshot /abs/path.png [screencapture options ...]
  mac_proxy.py list_tabs | active_tab | close_tabs ID [ID ...] | set_url ID URL | open_url URL | ping

In Python:  from mac_proxy import call, ProxyError
            call("applescript", script='…') -> {"code", "stdout", "stderr"}
            call("list_tabs") -> [{id, url, title, window}]  (None when Chrome isn't running; never launches it)
"""
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path.home() / ".mac-proxy"
REQ, RES = ROOT / "req", ROOT / "res"
DEFAULT_TIMEOUT = 60


class ProxyError(RuntimeError):
    def __init__(self, msg, res=None):
        super().__init__(msg)
        self.res = res or {}       # for a failed command: code, stdout, stderr


def call(verb, timeout=None, **args):
    """Send one request and wait for the answer. Raises ProxyError on failure or timeout."""
    if not REQ.is_dir():
        raise ProxyError("mac-proxy is not installed (%s not found); run install.sh" % REQ)
    if timeout:
        args["timeout"] = timeout
    rid = "%d-%s" % (time.time() * 1000, uuid.uuid4().hex[:8])
    tmp = REQ / (".%s.tmp" % rid)
    tmp.write_text(json.dumps({"verb": verb, "args": args}))
    os.replace(tmp, REQ / (rid + ".json"))
    out = RES / (rid + ".json")
    deadline = time.time() + (timeout or DEFAULT_TIMEOUT) + 15
    while time.time() < deadline:
        try:
            res = json.loads(out.read_text())
        except (OSError, ValueError):
            time.sleep(0.05)
            continue
        out.unlink(missing_ok=True)
        if not res.get("ok"):
            raise ProxyError(res.get("error", "unknown error"), res)
        return res.get("result")
    try:
        (REQ / (rid + ".json")).unlink()     # never picked up: don't let it fire late
    except OSError:
        pass
    raise ProxyError("mac-proxy did not answer. Is the launchd agent running "
                     "(launchctl print gui/%d/com.example.mac-proxy)? If macOS shows a permission "
                     "dialog for osascript, click Allow" % os.getuid())


def main(argv):
    timeout = None
    if argv[:1] == ["--timeout"]:
        timeout, argv = float(argv[1]), argv[2:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    verb, rest = argv[0], argv[1:]
    if verb in ("applescript", "jxa"):
        script = sys.stdin.read() if rest[:1] == ["-"] else rest[0]
        args = {"script": script, "argv": rest[1:]}
    elif verb == "run":
        args = {"argv": rest, "cwd": os.getcwd()}
    elif verb == "screenshot":
        args = {"path": os.path.abspath(rest[0]), "options": rest[1:]}
    elif verb == "close_tabs":
        args = {"ids": [int(x) for x in rest]}
    elif verb == "set_url":
        args = {"id": int(rest[0]), "url": rest[1]}
    elif verb == "open_url":
        args = {"url": rest[0]}
    else:
        args = {}
    try:
        res = call(verb, timeout=timeout, **args)
    except ProxyError as e:
        if "code" in e.res:
            sys.stdout.write(e.res.get("stdout", ""))
            sys.stderr.write(e.res.get("stderr", "") or str(e) + "\n")
            return e.res["code"] or 1
        print(e, file=sys.stderr)
        return 1
    if isinstance(res, dict) and "stdout" in res:
        sys.stdout.write(res["stdout"])
        sys.stderr.write(res["stderr"])
        return res["code"]
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
