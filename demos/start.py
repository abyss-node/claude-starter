#!/usr/bin/env python3
"""Start a demo: a small project your agent builds in a new folder, graded by held-out checks kept in the kit.

    python demos/start.py <name> [--tool <id>] [--dir <folder>]   # default folder: ~/agent-demos/<name>

It refuses before writing anything:
  exit 2  an unknown demo; no install of the kit recorded for the tool ("install first"); several tools recorded
          and no --tool; a folder that is not empty; a path package.json's `test` cannot quote; or a demo that
          needs Node with no Node 22.13 or newer on PATH, where it prints the install command for this OS and
          stops (it never runs a package manager)
  exit 3  the folder, its .git/hooks or the commit guard's data folder cannot be written, as in a sandboxed agent
          session; it prints this command for the user's own terminal (install.py's write probe and refusal)
Everything it then does is local, and deleting the folder undoes it: it copies the skeleton and the brief, writes
the tool's repo rules file and a package.json whose `test` runs the kit's held-out check (a python demo has none:
its rules file names the launcher), makes a git repo with one commit, and installs the commit guard's git hooks in
it (make_workspace). It ends with what the person at the keyboard does
next: the line that opens a session there, the first message, and what to watch for. The outward steps (a GitHub
repo and a push) are only printed, each for its own yes, and the repo they make is private.

What it writes into the folder names the demo by its id and its app (demo.json's `app`), never by its title,
which is the person's and can say what the demo tests: "Break the verifier" in a rules file would tell the
verifier it is the one being tried.
"""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import demolib as dl  # noqa: E402
from demolib import Demo, install, vocab  # noqa: E402

SANDBOX = ("It lets this session write only where its sandbox allows, and the folders above are outside that. A "
           "Codex cloud task runs in a temporary container, so a demo made there would not be on your machine "
           "either.")
ELSEWHERE = ("Making the demo somewhere this session can write would leave it without the commit guard's git "
             "hooks, which the demo exists to show, so this does not.")
UNQUOTABLE = set('"$`%')  # npm runs `test` through sh or cmd.exe, and these change meaning inside double quotes
# A demo's first commit needs an author. When git has none configured, this one is used for that commit only.
FALLBACK_AUTHOR = ["-c", "user.name=agent demo", "-c", "user.email=agent-demo@localhost"]


def say(*lines: str) -> None:
    print("\n".join(lines), file=sys.stderr)


def shell_pair(bash: str, ps: str, indent: str = "  ") -> list[str]:
    return [f"{indent}bash:       {bash}", f"{indent}PowerShell: {ps}"]


def own_lines(demo: Demo, tool: str, ws: Path) -> list[str]:
    return shell_pair(*dl.launcher("demo", "start", demo.name, "--tool", tool, "--dir", str(ws)))


def choose_tool(tools: list[str], args) -> tuple[str | None, int]:
    """(the tool, 0) or (None, exit code) after saying why."""
    rec_path = install.record_path()
    if not tools:
        say(f"error: no install of the kit is recorded at {rec_path}, so there is no agent set up to run a demo.",
            *dl.install_first_lines(args.tool))
        return None, 2
    if args.tool is None:
        if len(tools) == 1:
            return tools[0], 0
        say(f"The kit is installed for {len(tools)} tools here ({', '.join(tools)}), so this needs --tool. Run the "
            "line for the tool that will build the demo:",
            *(ln for t in tools for ln in [f"  {t}:", *shell_pair(*dl.launcher("demo", "start", args.name,
                                                                                "--tool", t), indent="    ")]))
        return None, 2
    if args.tool not in tools:
        say(f"error: the kit is not recorded as installed for {args.tool} here (recorded: {', '.join(tools)}).",
            *dl.install_first_lines(args.tool))
        return None, 2
    return args.tool, 0


def rules_text(demo: Demo, tool: str) -> str:
    stack = {
        "browser": "- **Stack:** ES modules in the browser, with no npm dependencies and no build step. To look at "
                   "it, run `python -m http.server` in this folder and open http://localhost:8000.",
        "node": "- **Stack:** ES modules on Node, with no npm dependencies and no build step.",
        "python": "- **Stack:** Python's standard library only.",
        "browser-python": "- **Stack:** ES modules in the browser, with no npm dependencies and no build step, "
                          "and Python's standard library only; `BRIEF.md` says which part is which.",
    }[demo.stack]
    if demo.runtime == "python":
        bash, ps = dl.launcher("demo", "check", demo.name)
        tests = ["- **Tests:** the test command runs the kit's held-out checks on this folder; they live in the "
                 "kit, not here. In bash:", f"  `{bash}`", "  In PowerShell:", f"  `{ps}`",
                 "  It prints each check's name and any failure, then `PASS k/n` or `FAIL k/n`, then a `RECORD:` "
                 "line that is the commit's `Verified:` trailer.",
                 "- **One test entry point:** that command is the only one. Add no CI config, no Makefile, justfile, "
                 "tox.ini or noxfile.py, and no `package.json` test script. Tests of your own are welcome; Python's "
                 "`unittest` runs them."]
    else:
        tests = ["- **Tests:** `npm test` is the test command. It runs the kit's held-out checks on this folder; they "
                 "live in the kit, not here. It prints each check's name and any failure, then `PASS k/n` or "
                 "`FAIL k/n`, then a `RECORD:` line that is the commit's `Verified:` trailer.",
                 "- **One test entry point:** add no CI config, no Makefile or justfile, and no other test script in "
                 "`package.json`, and keep its `test` as it is. Tests of your own are welcome; `node --test` runs "
                 "them" + (", and Python's `unittest` the Python ones." if demo.runtime == "mixed" else ".")]
    copied = ("its files and its git history, without `node_modules`, git hooks or symbolic links" if demo.copy_git
              else "its files without `.git`, `node_modules` or symbolic links")
    return "\n".join([
        f"# {demo.app}, a demo from the starter kit",
        "",
        "`BRIEF.md` says what this project is and what it must do.",
        "",
        *tests,
        stack,
        "- **No binary assets:** no image, audio or font files, no SVG files, no `data:` URLs and no base64 "
        "blobs.",
        "- **Original names:** nothing named after an existing game, show or toy.",
        f"- **Plain files:** the checks grade a copy of this folder, {copied}, in another folder, so code that "
        "needs any of those, or this folder's own path, to load fails them.",
        "- **The kit's `demos/` folder is off limits:** its checks are held out on purpose, its reference "
        "solution is compared line by line with this one, and code here that names the kit's files fails a check.",
        "",
    ])


def package_json(demo: Demo, root: Path, python: str) -> str | None:
    """The workspace's package.json: the skeleton's, if it ships one, with `test` set to the launcher's
    `demo check`, or a new one. None for a python demo, which has no package.json (npm needs Node)."""
    if demo.runtime == "python":
        return None
    pkg = dl.skeleton_package(demo) or {}
    test = dl.workspace_test_script(demo.name, root, python)
    out = {"name": demo.name, "private": True, "type": "module",
           "description": f"{demo.app}, a demo from the starter kit"}
    out.update({k: v for k, v in pkg.items() if k not in ("name", "private", "description", "scripts")})
    out["scripts"] = dict(pkg.get("scripts") or {}, test=test)
    return json.dumps(out, indent=2) + "\n"


def write(p: Path, text: str) -> None:
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def git(ws: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([dl.exe("git") or "git", "-C", str(ws), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", stdin=subprocess.DEVNULL, timeout=120)


def make_workspace(demo: Demo, tool: str, ws: Path, root: Path, python: str) -> str | None:
    """Fill the empty folder `ws` as a demo starts: the skeleton, each lane's rules file (a skeleton's AGENTS.md
    below the top) under the tool's name for it, BRIEF.md, the tool's rules file, package.json whose `test`
    starts `python` on the kit at `root`, and a git repo whose one commit holds all of it. That commit is the
    demo's only root, made once with its final message: a demo graded on its history checks it was never
    amended. None, or what failed. The mutants engine makes its skeleton workspace with this too."""
    v = vocab.VOCAB[tool]
    shutil.copytree(str(demo.dir / "skeleton"), str(ws), dirs_exist_ok=True)
    nested = dl.nested_rules_name(tool)
    if nested != "AGENTS.md":
        for p in sorted(ws.rglob("AGENTS.md")):
            if p.parent != ws:
                p.rename(p.with_name(nested))
    write(ws / "BRIEF.md", dl.split_brief(demo)[0])
    write(ws / v.repo_rules, rules_text(demo, tool))
    pkg = package_json(demo, root, python)
    if pkg is not None:
        write(ws / "package.json", pkg)
    return make_repo(demo, ws)


def make_repo(demo: Demo, ws: Path) -> str | None:
    """git init, then one commit of everything written. None, or what failed."""
    steps = [["-c", "init.defaultBranch=main", "init", "-q"], ["add", "-A"]]
    for s in steps:
        r = git(ws, *s)
        if r.returncode:
            return f"git {' '.join(s)}: {(r.stderr or r.stdout).strip()}"
    author = [] if git(ws, "config", "user.email").stdout.strip() else FALLBACK_AUTHOR
    r = git(ws, *author, "commit", "-q", "-m", f"chore: start the {demo.app} demo from the starter kit",
            "-m", "Unverified: the skeleton as the kit ships it; the demo check has not run on it")
    return None if r.returncode == 0 else f"git commit: {(r.stderr or r.stdout).strip()}"


def open_lines(tool: str, ws: Path) -> list[str]:
    v = vocab.VOCAB[tool]
    if v.open_cmd is None:
        where = "your tool" if tool == "generic" else v.name
        return [f"   Open the folder {ws} in {where} and start a new session there."]
    bash_dir, ps_dir = shlex.quote(ws.as_posix()), install._ps_quote(str(ws))
    if "{dir}" in v.open_cmd:
        bash, ps = v.open_cmd.format(dir=bash_dir), v.open_cmd.format(dir=ps_dir)
    else:
        bash, ps = f"cd {bash_dir} && {v.open_cmd}", f"Set-Location {ps_dir}; {v.open_cmd}"
    out = shell_pair(bash, ps, indent="     ")
    if tool == "codex":
        out.append(f"   In the Codex app, open the folder {ws} instead (not checked against the app).")
    return out


def for_you(demo: Demo, tool: str, ws: Path, watch: str) -> list[str]:
    v = vocab.VOCAB[tool]
    check = v.cmd("checkpoint")
    first, *more = demo.kickoffs
    later = [f"   This demo takes {len(demo.kickoffs)} sessions. When the agent has finished session {i}, open a "
             f"new session in the same folder, as in step 1, and type: {k}" for i, k in enumerate(more, 1)]
    test_cmd = "the held-out check" if demo.runtime == "python" else "`npm test`"
    return [
        install.FOR_YOU,
        "1. Open a new session in the demo's folder. Your agent reads a folder's rules when a session starts, so "
        "the demo cannot run in this one:",
        *open_lines(tool, ws),
        f"2. Type this as your first message there: {first}",
        *later,
        f"3. Watch for the whole chain: the agent says how it classifies the task, plans, builds, runs {test_cmd}, "
        f"has the verifier agent check the work, runs {check}, and commits; the commit guard checks that the "
        "commit says what was verified. What to watch for in this demo:",
        *(f"   {ln}" if ln else "" for ln in watch.split("\n")),
        "4. Answer the agent as you would on real work. Say no to anything outward, such as a push: this demo "
        "needs none.",
        ("5. Grade it yourself whenever you like, with the kit's launcher from your own terminal: this runs the "
         "kit's own checks on a copy of the folder. "
         if demo.runtime == "python" else
         "5. Grade it yourself whenever you like, with the kit's launcher rather than `npm test`, which the agent "
         "can change: this runs the kit's own checks on a copy of the folder, and fails the work if `test` was "
         "changed. ") +
        "It is still feedback, not proof: anything with a shell on this machine, the agent included, can "
        "tamper with the kit or the grade, so a measured run counts only after CI re-grades the committed folder "
        "(the kit's demos/MEASURING.md). It ends with PASS k/n or FAIL k/n and a RECORD line for the commit:",
        *shell_pair(*dl.launcher("demo", "check", demo.name, "--dir", str(ws)), indent="     "),
        "6. Only after a checkpoint that passed, and only if you want the demo on GitHub: these put it in a "
        "private repo of yours. Run them in the demo's folder, one at a time, each only if you say yes to it:",
        "     gh auth login",
        f"     gh repo create {demo.name} --private --source .",
        "     git push -u origin HEAD",
        f"7. To undo all of this, delete {ws}. Uninstalling the kit leaves that folder where it is.",
        "If you are an AI agent: stop here. Show the user this block, word for word, and end your turn. The demo "
        "runs in a new session in its own folder, not in this one.",
    ]


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="start.py", description="Start a demo in a new folder.")
    ap.add_argument("name", help="the demo; demos/pick.py lists them")
    ap.add_argument("--tool", choices=sorted(vocab.VOCAB), help="the tool that will build it (default: the one "
                    "the install record names)")
    ap.add_argument("--dir", type=Path, help="the folder to make it in (default: ~/agent-demos/<name>)")
    args = ap.parse_args(argv)
    try:
        demo = dl.load_demo(args.name)
    except KeyError:
        say(dl.unknown_demo(args.name))
        return 2
    rec, problem = dl.load_record_or_none()
    if problem:
        say(f"error: {problem}")
        return 1
    root = ((rec or {}).get("kit") or {}).get("kit_root")
    if root and Path(root).resolve() != dl.KIT.resolve():
        say(f"error: this machine's install record ({install.record_path()}) belongs to the clone at {root}, not "
            f"{dl.KIT}, and a demo is graded by the clone that installed the kit. Start it with that clone's "
            "launcher. Nothing was written.")
        return 2
    tool, rc = choose_tool(dl.global_tools(rec), args)
    if tool is None:
        return rc
    _, watch = dl.split_brief(demo)
    v = vocab.VOCAB[tool]
    skeleton = demo.dir / "skeleton"
    clash = [n for n in ("BRIEF.md", *{x.repo_rules for x in vocab.VOCAB.values()}) if (skeleton / n).exists()]
    if clash:
        raise dl.DemoError(f"demos/{demo.name}/skeleton/ holds {', '.join(clash)}, which start.py writes itself")
    dl.skeleton_package(demo)   # refuses one a python demo ships, or one with a second test script
    lines = dl.node_problem(demo)
    if lines:
        say(*lines)
        return 2
    if dl.python_problem():
        say(f"error: {dl.python_problem()} Run the launcher with a newer Python. Nothing was written.")
        return 2
    if not dl.exe("git"):
        say("error: git is not on PATH, and a demo is a git repo whose commits the commit guard checks. Install git "
            "(the kit's AGENTS.md, step 2, says how for your OS), then run this again. Nothing was written.")
        return 2
    ws = (args.dir.expanduser() if args.dir else install.home() / "agent-demos" / demo.name).resolve()
    if ws.exists() and (not ws.is_dir() or any(ws.iterdir())):
        say(f"error: {ws} is not empty, and a demo starts in an empty folder. Delete it, or pass --dir with "
            "another folder. Nothing was written.")
        return 2
    paths = [str(ws), sys.executable, str(install.cmd_root())]
    if any(set(p) & UNQUOTABLE for p in paths):
        say("error: one of these paths holds a character (\" $ ` %) that package.json's `test` script cannot quote "
            f"for every shell: {', '.join(paths)}. Pass --dir with a plainer folder. Nothing was written.")
        return 2
    bad = [(d, e) for d, e in ((d, install.probe_dir(d)) for d in (ws / ".git" / "hooks", install.guard_data_dir()))
           if e is not None]
    if bad:
        return install.refuse_unwritable(bad, args, lines=own_lines(demo, tool, ws), verb="start this demo",
                                         elsewhere=ELSEWHERE, sandbox=SANDBOX)

    failed = make_workspace(demo, tool, ws, install.cmd_root(), sys.executable)
    if failed is None:
        r = subprocess.run([sys.executable, str(install.GUARD), "install", str(ws)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=120)
        failed = None if r.returncode == 0 else f"commit guard install: {(r.stderr or r.stdout).strip()}"
    if failed:
        say(f"error: {failed}", f"The demo folder {ws} is half made. Delete it and run this again.")
        return 1
    wrote = v.repo_rules if demo.runtime == "python" else f"{v.repo_rules} and package.json"
    print(f"Started {demo.title} in {ws}: copied the skeleton and BRIEF.md, wrote {wrote}, made a git repo with one "
          "commit, and installed the commit guard's git hooks in it.")
    print()
    print("\n".join(for_you(demo, tool, ws, watch)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
