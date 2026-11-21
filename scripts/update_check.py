#!/usr/bin/env python3
"""Print one line when a newer claude-starter release exists, else nothing. Always exits 0.

Runs at session start, so it never slows one down or updates anything: it reads the install record
(~/.agents/starter/installs.json), stays silent when notices are not on or nothing is recorded, uses a
check cached in the record's folder when it is under 24 hours old, and otherwise asks the remote with
`git ls-remote --tags`, killed with its whole process tree after 3 seconds. A failed check is cached
too, so an offline machine pays those 3 seconds once a day, not at every session. Offline or any
failure prints nothing. The line itself prints at most once a day. It never fetches into the clone.

    python update_check.py            # the notice line, or nothing (the SessionStart hook, lanes)
    python update_check.py --remind   # also REMIND while no answer is recorded (checkpoint)

With --remind and no notice answer in the record (or no record at all, as for an install made before
v0.4.0), it prints REMIND instead and checks nothing. An unreadable record prints nothing, as before.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DAY = 24 * 60 * 60
TIMEOUT = 3
TAG = re.compile(r"refs/tags/v(\d+)\.(\d+)\.(\d+)$")
REMIND = ("claude-starter update notices are not chosen yet: say yes or no to a one-line notice when a new "
          "kit version is out (yes is recommended; it never updates anything).")


def record_dir() -> Path:
    return Path.home() / ".agents" / "starter"  # the same folder as install.record_dir()


def key(v: str) -> tuple:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(x) for x in m.groups()) if m else (-1,)


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill git and its helpers. Killing git.exe alone on Windows leaves git-remote-https running."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=2)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def newest_tag(remote: str) -> str | None:
    """The newest vX.Y.Z tag on the remote, "" when it has none, None when the check failed. Output
    goes to a file, not a pipe: a helper that outlives a killed git holds a pipe open, and reading the
    pipe then waits for that helper (21 s on Windows against an unroutable address)."""
    with tempfile.TemporaryFile() as out:
        proc = subprocess.Popen(["git", "ls-remote", "--tags", remote], stdout=out, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"),
                                **({} if os.name == "nt" else {"start_new_session": True}))
        try:
            rc = proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            return None
        if rc:
            return None
        out.seek(0)
        text = out.read().decode("utf-8", errors="replace")
    found = []
    for ln in text.splitlines():
        m = TAG.search(ln.split("\t")[-1].replace("^{}", ""))
        if m:
            found.append(tuple(int(x) for x in m.groups()))
    return "{}.{}.{}".format(*max(found)) if found else ""


def write_cache(cache: Path, c: dict) -> None:
    tmp = cache.with_name(f".{cache.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(c) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(cache))


def check() -> str | None:
    rec = json.loads((record_dir() / "installs.json").read_text(encoding="utf-8"))
    if (rec.get("notices") or {}).get("update") is not True:
        return None
    kit = rec.get("kit") or {}
    have, remote = kit.get("version"), kit.get("remote")
    if not have or not remote:
        return None
    cache = record_dir() / "update-check.json"
    try:
        c = json.loads(cache.read_text(encoding="utf-8"))
        fresh = c.get("remote") == remote and 0 <= time.time() - float(c["checked_at"]) < DAY
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        c, fresh = {}, False
    if not fresh:
        found = newest_tag(remote)
        # A failure is cached as no news (newest ""), so it is retried a day later, not every session.
        c = {"checked_at": time.time(), "remote": remote, "newest": found or "", "failed": found is None,
             **({"shown_at": c["shown_at"]} if "shown_at" in c else {})}
        write_cache(cache, c)
    newest = c.get("newest") or ""
    if not newest or key(newest) <= key(have):
        return None
    try:
        if 0 <= time.time() - float(c["shown_at"]) < DAY:
            return None  # already shown today
    except (KeyError, ValueError, TypeError):
        pass
    write_cache(cache, dict(c, shown_at=time.time()))
    return (f"claude-starter v{newest} is available (you have v{have}). Ask your agent to run "
            "starter-update to see what changed.")


def unanswered() -> bool:
    """True when the record holds no notice answer, or there is no record. Raises on an unreadable one."""
    path = record_dir() / "installs.json"
    if not path.is_file():
        return True
    return (json.loads(path.read_text(encoding="utf-8")).get("notices") or {}).get("update") is None


def main(argv: list[str]) -> int:
    try:
        line = REMIND if "--remind" in argv and unanswered() else check()
    except Exception:  # noqa: BLE001 - a notice must never break or slow a session
        return 0
    if line:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
