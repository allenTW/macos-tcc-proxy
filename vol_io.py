#!/usr/bin/python3
"""Reach the external drive from launchd jobs.

A launchd job runs /usr/bin/python3 (or bash) as its own "responsible process", and macOS refuses it access to
/Volumes/MyDrive (exFAT on FSKit, filed as a network volume) with "Operation not permitted". The job can't ask
for the grant either: background processes never show the prompt. mac-proxy already holds the Volumes grant
(you must run one warm-up command through the proxy once) and its children inherit it, so each helper here tries the direct way first and, only
when macOS says no, does the same thing through mac-proxy. Nothing extra is granted to python.

    import sys, os; sys.path.insert(0, os.path.expanduser("~/.mac-proxy"))
    import vol_io
    vol_io.read_text("/Volumes/MyDrive/data/queue.json")
    vol_io.local_copy("/Volumes/.../big.bin")             # -> path of a fresh copy under ~/.cache/vol_io
    vol_io.sqlite_snapshot("/Volumes/.../data.db")         # -> consistent db copy (WAL included)
    vol_io.run(["/usr/bin/python3", "/Volumes/.../job.py", ...])   # -> (code, stdout, stderr)

Tests: tests/test_vol_io.py (no proxy, no real drive).
"""
import errno
import hashlib
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.expanduser("~/.cache/vol_io")
DENIED = "Operation not permitted"


def _proxy(argv, timeout, cwd=None):
    """(code, stdout, stderr) of argv run by mac-proxy. A failed command comes back as ProxyError with res."""
    sys.path.insert(0, HERE)
    from mac_proxy import call, ProxyError
    try:
        r = call("run", timeout=timeout, argv=[str(a) for a in argv], cwd=cwd or os.path.expanduser("~"))
        return r.get("code", 0), r.get("stdout", ""), r.get("stderr", "")
    except ProxyError as e:
        res = e.res or {}
        if "code" in res:
            return res["code"], res.get("stdout", ""), res.get("stderr", "")
        return 1, "", "mac-proxy: %s" % e


def _denied(exc):
    return isinstance(exc, PermissionError) or getattr(exc, "errno", None) in (errno.EPERM, errno.EACCES)


def read_text(path, timeout=60, proxy=None):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        if not _denied(e):
            raise
    code, out, err = (proxy or _proxy)(["/bin/cat", path], timeout)
    if code != 0:
        raise PermissionError("vol_io: %s: %s" % (path, (err or "exit %d" % code).strip()))
    return out


def local_copy(path, timeout=120, proxy=None, cache=None, max_age=0, now=None):
    """Copy path to the internal disk (for sqlite and other binary files) and return the copy's path.
    max_age > 0 reuses a copy younger than that many seconds (big files read on a schedule)."""
    cache = cache or CACHE
    os.makedirs(cache, exist_ok=True)
    dest = os.path.join(cache, hashlib.sha1(path.encode("utf-8")).hexdigest()[:12] + "_" + os.path.basename(path))
    if max_age and os.path.exists(dest) and (now or time.time()) - os.path.getmtime(dest) < max_age:
        return dest
    try:
        with open(path, "rb") as src, open(dest + ".tmp", "wb") as out:
            out.write(src.read())
    except OSError as e:
        if not _denied(e):
            raise
        code, _, err = (proxy or _proxy)(["/bin/cp", path, dest + ".tmp"], timeout)
        if code != 0:
            raise PermissionError("vol_io: %s: %s" % (path, (err or "exit %d" % code).strip()))
    os.replace(dest + ".tmp", dest)
    return dest


def sqlite_snapshot(path, timeout=300, proxy=None, cache=None, max_age=0, now=None):
    """Consistent copy of a sqlite db (WAL included) on the internal disk; open it with ?mode=ro&immutable=1.
    A plain copy of a WAL database misses everything still in -wal and won't open read-only."""
    import sqlite3
    cache = cache or CACHE
    os.makedirs(cache, exist_ok=True)
    dest = os.path.join(cache, hashlib.sha1(path.encode("utf-8")).hexdigest()[:12] + "_" + os.path.basename(path))
    if max_age and os.path.exists(dest) and (now or time.time()) - os.path.getmtime(dest) < max_age:
        return dest
    tmp = dest + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    try:
        src = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        try:
            out = sqlite3.connect(tmp)
            src.backup(out)
            out.close()
        finally:
            src.close()
    except sqlite3.Error as e:
        if "authorization denied" not in str(e) and "unable to open" not in str(e):
            raise
        if os.path.exists(tmp):
            os.remove(tmp)
        code, _, err = (proxy or _proxy)(["/usr/bin/sqlite3", path, ".backup '%s'" % tmp], timeout)
        if code != 0:
            raise PermissionError("vol_io: %s: %s" % (path, (err or "exit %d" % code).strip()))
    os.replace(tmp, dest)
    return dest


def run(argv, timeout=60, cwd=None, proxy=None):
    """Run argv; if macOS blocks it from the drive, run it again through mac-proxy. -> (code, stdout, stderr)"""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        if r.returncode == 0 or DENIED not in (r.stderr or ""):
            return r.returncode, r.stdout, r.stderr
    except OSError as e:          # e.g. cwd on the drive is itself denied
        if not _denied(e):
            raise
    return (proxy or _proxy)(argv, timeout, cwd)
