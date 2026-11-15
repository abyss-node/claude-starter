#!/usr/bin/env python3
"""CI fixture: an install made by an old release's installer, updated by this tree's.

    python .github/scripts/update_fixture.py --from v0.3.1 --tool junie --work <dir> [--hooked]

Run from the repo root (full history, so the tag exists). Every HOME is under --work. It checks:
  1. the old release installs, with user text already in the rules file;
  2. the update plan (starter.py update --offline) exits 0 and its pinned apply exits 0;
  3. a second update writes nothing;
  4. the updated install equals a fresh install by this tree, file for file (backups and the
     install record aside);
  5. the user's text outside the claude-starter markers is byte-identical;
  6. with --hooked, a repo given to the old installer's --guard-repo still runs the commit guard,
     which flags a commit that adds a secret.
On a CI runner it writes UPDATED_HOME=<the updated HOME> to $GITHUB_ENV for a later load check.
"""
import argparse
import io
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path.cwd()
USER_TEXT = "# My own rules\n\nThis line is the user's and must survive every update.\n"
WRITE_ROW = re.compile(r"  (installed|merged|updated|moved|deleted)$", re.M)
BLOCK = re.compile(r"\n*<!-- BEGIN claude-starter rules.*?<!-- END claude-starter rules[^\n]*-->\n?", re.S)
RELOCATE = ("CODEX_HOME", "COPILOT_HOME", "CURSOR_CONFIG_DIR", "CLAUDE_CONFIG_DIR", "OPENCODE_CONFIG_DIR",
            "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "COMMIT_GUARD_DIR")
FAILS = []


def env_for(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in RELOCATE}
    env.update(HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8",
               XDG_CONFIG_HOME=str(home / ".config"), XDG_DATA_HOME=str(home / ".local" / "share"),
               XDG_CACHE_HOME=str(home / ".cache"), XDG_STATE_HOME=str(home / ".local" / "state"))
    return env


def run(argv: list, home: Path, cwd: Path = REPO) -> subprocess.CompletedProcess:
    r = subprocess.run(argv, cwd=str(cwd), env=env_for(home), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600, stdin=subprocess.DEVNULL)
    print(f"$ {' '.join(map(str, argv))}  -> {r.returncode}\n{r.stdout}{r.stderr}")
    return r


def check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)


def rules_file(tool: str, home: Path) -> Path:
    return {"junie": home / ".junie" / "AGENTS.md",
            "opencode": home / ".config" / "opencode" / "AGENTS.md"}[tool]


def kit_files(home: Path) -> dict:
    """Every file under home except backups, the install record, caches and the commit guard's own copy
    (only a hooked fixture has one), by relative path."""
    out = {}
    for p in sorted(home.rglob("*")):
        rel = p.relative_to(home).as_posix()
        if (not p.is_file() or ".bak-" in p.name or "__pycache__" in rel
                or rel.startswith((".agents/starter/", ".cache/", ".local/", ".claude/commit-guard/"))):
            continue
        out[rel] = p.read_bytes().replace(b"\r\n", b"\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="tag", required=True)
    ap.add_argument("--tool", required=True, choices=("junie", "opencode"))
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--hooked", action="store_true")
    a = ap.parse_args()
    work = a.work.resolve()
    old, home, fresh, repo = work / "old-kit", work / "home", work / "home-fresh", work / "repo"
    for d in (old, home, fresh):
        d.mkdir(parents=True, exist_ok=True)

    archive = subprocess.run(["git", "archive", "--format=tar", a.tag], cwd=str(REPO), capture_output=True,
                             check=True, timeout=120).stdout
    tarfile.open(fileobj=io.BytesIO(archive)).extractall(str(old))

    guard = []
    if a.hooked:
        repo.mkdir(exist_ok=True)
        for argv in (["git", "init", "-q"], ["git", "config", "user.email", "ci@example.invalid"],
                     ["git", "config", "user.name", "ci"], ["git", "commit", "-q", "--allow-empty", "-m",
                     "init\n\nVerified: none -> fixture\nUnverified: none"]):
            subprocess.run(argv, cwd=str(repo), env=env_for(home), check=True, capture_output=True)
        guard = ["--guard-repo", str(repo)]

    for h in (home, fresh):
        rules_file(a.tool, h).parent.mkdir(parents=True, exist_ok=True)
        rules_file(a.tool, h).write_text(USER_TEXT, encoding="utf-8", newline="\n")

    r = run([sys.executable, str(old / "scripts" / "install.py"), "--tool", a.tool, "--tier", "starter",
             "--yes", *guard], home)
    check(r.returncode == 0, f"{a.tag} installs {a.tool}")

    # The plan is made with the commit guard answer: the apply must carry the same one, and the plan id
    # covers it, so planning without it and adding it at apply is refused as a changed plan.
    answer = guard or ["--no-guard"]
    plan = run([sys.executable, "scripts/starter.py", "update", "--offline", *answer], home)
    check(plan.returncode == 0, "the update plan exits 0")
    m = re.search(r"update --yes --to ([0-9a-f]{40}) --plan ([0-9a-f]+)", plan.stdout)
    check(m is not None, "the plan prints an apply command pinned with --to and --plan")
    pins = ["--to", m.group(1), "--plan", m.group(2)] if m else []
    r1 = run([sys.executable, "scripts/starter.py", "update", "--offline", "--yes", *pins, *answer], home)
    check(r1.returncode == 0, "the pinned apply exits 0")
    r2 = run([sys.executable, "scripts/starter.py", "update", "--offline", "--yes", *answer], home)
    check(r2.returncode == 0 and not WRITE_ROW.search(r2.stdout), "a second update writes nothing")

    rf = run([sys.executable, "scripts/install.py", "--tool", a.tool, "--tier", "starter", "--yes",
              "--no-guard"], fresh)
    check(rf.returncode == 0, "a fresh install by this tree exits 0")
    up, fr = kit_files(home), kit_files(fresh)
    only_up, only_fr = sorted(set(up) - set(fr)), sorted(set(fr) - set(up))
    differ = sorted(k for k in set(up) & set(fr) if up[k] != fr[k])
    check(not (only_up or only_fr or differ),
          f"the update equals a fresh install (only after update: {only_up}; only fresh: {only_fr}; "
          f"differ: {differ})")

    text = rules_file(a.tool, home).read_bytes().decode("utf-8").replace("\r\n", "\n")
    check(len(re.findall("BEGIN claude-starter rules", text)) == 1, "one BEGIN marker in the rules file")
    check(BLOCK.sub("", text).rstrip("\n") == USER_TEXT.rstrip("\n"), "the user's text outside the markers "
          "is unchanged")

    if a.hooked:
        (repo / "creds.txt").write_text("aws_key = AKIA" + "ABCDEFGHIJKLMNOP\n", encoding="utf-8")
        subprocess.run(["git", "add", "creds.txt"], cwd=str(repo), env=env_for(home), check=True)
        c = run(["git", "commit", "-m", "add creds\n\nVerified: none -> fixture\nUnverified: none"], home,
                cwd=repo)
        # The fixture repo is not an agent session, so the guard may warn rather than block; either way it
        # must still run from where the hooks point and name the secret. A missing guard.py prints
        # "guard skipped" and finds nothing.
        check("aws-access-key" in c.stdout + c.stderr and "guard skipped" not in c.stdout + c.stderr,
              "the hooked repo's commit guard still runs and flags a secret after the update")

    if os.environ.get("GITHUB_ENV"):
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as f:
            f.write(f"UPDATED_HOME={home}\n")
    print(f"\n{len(FAILS)} failed" + "".join(f"\n  - {x}" for x in FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
