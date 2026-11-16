"""Build the finished workspace for the commit-guard dojo as a real git repo.

This demo is graded on git history, and a git folder cannot be committed to the kit, so the reference is a
replay: workspace/ holds the finished files and commits.json the starting commit and the three commits that lead
there. The kit runs it as

    <python> build.py --skeleton <the skeleton folder> --out <an empty folder>

Git comes from DEMO_GIT and runs with no system or user config. Every identity and date is fixed, so the same
inputs give the same commit hashes. It reads commits.json and workspace/ beside itself.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_TIME = 1794717000  # 2026-11-15T10:00:00+05:30
GIT = os.environ.get("DEMO_GIT", "")


def git(dest: Path, env: dict, *args: str) -> None:
    subprocess.run([GIT, "-C", str(dest)] + list(args), env=env, check=True, stdout=subprocess.DEVNULL)


def commit(dest: Path, env: dict, message: str, n: int) -> None:
    env = dict(env)
    stamp = "@%d +0530" % (BASE_TIME + 60 * n)
    env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = stamp
    fd, msg_path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(message)
        git(dest, env, "add", "-A")
        git(dest, env, "commit", "-q", "-F", msg_path)
    finally:
        os.unlink(msg_path)


def tree_files(root: Path) -> dict:
    out = {}
    for f in root.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts and ".git" not in f.relative_to(root).parts:
            out[f.relative_to(root).as_posix()] = f.read_bytes().replace(b"\r\n", b"\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skeleton", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    if not GIT or not os.path.isabs(GIT) or not os.path.isfile(GIT):
        print("DEMO_GIT must be the absolute path of git (got %r)" % GIT, file=sys.stderr)
        return 2
    dest, skeleton = Path(a.out), Path(a.skeleton)
    if dest.exists() and any(dest.iterdir()):
        print("refusing: %s is not empty" % dest, file=sys.stderr)
        return 2
    plan = json.loads((HERE / "commits.json").read_text(encoding="utf-8"))
    finished = HERE / "workspace"

    env = dict(os.environ)
    env.update({
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Dojo Reference", "GIT_AUTHOR_EMAIL": "dojo@example.invalid",
        "GIT_COMMITTER_NAME": "Dojo Reference", "GIT_COMMITTER_EMAIL": "dojo@example.invalid",
    })

    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(skeleton), str(dest), dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    subprocess.run([GIT, "init", "-q", "-b", "main", str(dest)], env=env, check=True)
    git(dest, env, "config", "core.autocrlf", "false")
    commit(dest, env, plan["initial"]["message"], 0)

    for n, step in enumerate(plan["commits"], start=1):
        for r in step.get("replace", []):
            p = dest / r["path"]
            text = p.read_text(encoding="utf-8")
            if r["old"] not in text:
                print("step %d: %r not found in %s" % (n, r["old"], r["path"]), file=sys.stderr)
                return 1
            with open(p, "w", encoding="utf-8", newline="\n") as f:  # Path.write_text has no newline= before 3.10
                f.write(text.replace(r["old"], r["new"]))
        for rel in step.get("copy", []):
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(finished / rel, dest / rel)
        for rel in step.get("delete", []):
            (dest / rel).unlink()
        commit(dest, env, step["message"], n)

    if tree_files(dest) != tree_files(finished):
        print("built tree does not match workspace/ (commits.json is incomplete)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
