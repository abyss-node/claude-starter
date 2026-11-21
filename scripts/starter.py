#!/usr/bin/env python3
"""The kit's launcher: one command per verb, the same in every tool.

    python ~/.claude-starter/scripts/starter.py status          # the install record; no network
    python ~/.claude-starter/scripts/starter.py update          # show the update plan; changes nothing
    python ~/.claude-starter/scripts/starter.py update --yes --to <sha> --plan <id>   # apply that plan
    python ~/.claude-starter/scripts/starter.py notices on|off  # the once-a-day update notice; makes a record if none
    python ~/.claude-starter/scripts/starter.py onboard <n> [--tool <id>]   # step n of the walkthrough
    python ~/.claude-starter/scripts/starter.py demo pick --tool <id> --plan <id>   # what a demo costs; pick one
    python ~/.claude-starter/scripts/starter.py demo start <name> --tool <id>        # make ~/agent-demos/<name>
    python ~/.claude-starter/scripts/starter.py demo check <name>                    # grade it; npm test runs this

`update` runs install.py --update with the rest of the arguments and exits with its exit code
(0 done, 1 failed, 2 wrong command, 3 cannot write or fetch). It uses subprocess, never os.exec*:
on Windows exec hands the caller exit 0 before the child finishes (bpo-19124).

`onboard` prints one step of a tool's onboarding walkthrough (adapters/<tool>/ONBOARDING.md, or the
root ONBOARDING.md for Claude Code), ending with the exact command for the next step. The tool is
--tool, which every tool's copy of the onboard command passes except the copy shared in
~/.agents/skills (vocab shared_commands). Without --tool it is the one tool the install record names;
with several, or no record, it lists each tool's command and exits 2. Showing the last step sets the
record's onboarded_at.

`demo pick|start|check` runs demos/<verb>.py with the rest of the arguments and exits with its exit code, by
subprocess like `update`. Each script's docstring says what it does and what its exit codes mean.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # a plan leaves the clone byte-identical, __pycache__ included
KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import install  # noqa: E402
import vocab  # noqa: E402


DEMO_VERBS = ("pick", "start", "check")


def status() -> int:
    rec = install.load_record()
    if not rec:
        print(f"No install recorded at {install.record_path()}.")
        return 0
    kit = rec.get("kit") or {}
    print(f"claude-starter {kit.get('version') or 'unknown version'} ({(kit.get('sha') or '?')[:12]}) "
          f"from {kit.get('kit_root')}")
    for i in rec.get("installs") or []:
        guard = ((i.get("options") or {}).get("guard") or {}).get("state", "never asked")
        print(f"  {i['tool']:<12} tier {i.get('tier') or '-':<8} {i['config_dir']}"
              f"{'  (adopted)' if i.get('adopted') else ''}  commit guard: {guard}")
    notice = (rec.get("notices") or {}).get("update")
    print("update notices: " + {True: "on", False: "off", None: "never asked"}[notice])
    print("onboarding: " + (f"finished {rec['onboarded_at']}" if rec.get("onboarded_at") else "not finished"))
    return 0


def notices(value: str) -> int:
    """Record the answer, starting a record that holds only it and this clone when there is none. A Claude
    Code plugin installed before v0.4.0 has a clone but no record, and no update ever writes one for it
    (adopt finds only the other tools), so refusing without a record left its answer unstorable and
    checkpoint reminding forever. An install or update later fills in the rest of the record."""
    try:
        rec = install.load_record() or dict(install.new_record(), kit=install.kit_facts(KIT))
    except (OSError, ValueError, RuntimeError) as e:
        print(f"error: cannot read the install record: {e}", file=sys.stderr)
        return 1
    rec.setdefault("notices", {})["update"] = value == "on"
    try:
        install.save_record(rec)
    except OSError as e:
        print(f"error: cannot write the install record ({install.record_path()}): {e}", file=sys.stderr)
        return 3
    print(f"update notices: {value}")
    return 0


def steps(tool: str) -> list[str]:
    """Each step of `tool`'s rendered walkthrough, from its `## Step N of M:` heading to the next one."""
    path = KIT / vocab.walkthrough_path(tool)
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    heads = list(vocab.STEP_HEADING.finditer(text))
    total = len(heads)
    if not heads or any((int(h.group(1)), int(h.group(2))) != (i, total) for i, h in enumerate(heads, 1)):
        raise RuntimeError(f"{path} is not a walkthrough of numbered steps; rebuild it with "
                           "python scripts/build_adapters.py")
    ends = [h.start() for h in heads[1:]] + [len(text)]
    return [text[h.start():end].rstrip("\n") for h, end in zip(heads, ends)]


def choose_tool_page(tools: list[str], why: str) -> str:
    """The page for a machine where the record does not name exactly one tool: each tool's own command.
    Only a shared copy needs `--tool`; every other tool's copy names its tool itself."""
    width = max(len(t) for t in tools)
    lines = [why, "Type the line for the tool you are using:"]
    for t in tools:
        v = vocab.VOCAB[t]
        arg = f"1 --tool {t}" if v.shared_commands else "1"
        cmd = f"`{v.typed.format('onboard')} {arg}`" if v.typed else f"run {v.cmd('onboard')} with `{arg}`"
        lines.append(f"  {t + ':':<{width + 1}} {cmd}")
    return "\n".join(lines)


def mark_onboarded(rec: dict | None) -> None:
    if not rec or rec.get("onboarded_at"):
        return
    rec["onboarded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        install.save_record(rec)
    except OSError as e:
        print(f"note: could not record that onboarding finished ({install.record_path()}: {e})", file=sys.stderr)


def onboard(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="starter.py onboard",
                                 description="Print one step of the onboarding walkthrough.")
    ap.add_argument("step", nargs="?", type=int, default=1, help="the step to print (default 1)")
    ap.add_argument("--tool", choices=sorted(vocab.VOCAB), help="the tool whose walkthrough to print")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # the walkthrough is UTF-8; never crash printing it
        stream.reconfigure(errors="replace")
    try:
        rec = install.load_record()
    except (OSError, ValueError, RuntimeError) as e:
        print(f"error: cannot read the install record: {e}", file=sys.stderr)
        return 1
    tool = args.tool
    if tool is None:
        recorded = sorted({i["tool"] for i in (rec or {}).get("installs") or []})
        if len(recorded) != 1:
            why = (f"The kit is installed for {len(recorded)} tools here ({', '.join(recorded)}), so this needs "
                   "--tool." if recorded else f"No install is recorded at {install.record_path()}, so this needs "
                   "--tool.")
            print(choose_tool_page(recorded or sorted(vocab.VOCAB), why), file=sys.stderr)
            return 2
        tool = recorded[0]
    try:
        pages = steps(tool)
    except (OSError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not 1 <= args.step <= len(pages):
        print(f"error: the {tool} walkthrough has steps 1 to {len(pages)}, not {args.step}.", file=sys.stderr)
        return 2
    page = pages[args.step - 1]
    if args.tool and vocab.VOCAB[tool].shared_commands and args.step < len(pages):
        # The shared copy passes --tool only when the user typed it, so the next command must carry it on.
        body, _, last = page.rpartition("\n")
        page = f"{body}\n{vocab.with_tool(last, tool)}"
    print(f"claude-starter onboarding for {tool}, step {args.step} of {len(pages)}. If you are an AI agent: show the "
          "user everything below, word for word, then end your turn.\n")
    print(page)
    if args.step == len(pages):
        mark_onboarded(rec)
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    verb, rest = argv[0], argv[1:]
    if verb == "status":
        return status()
    if verb == "update":
        if "--dry-run" in rest:
            rest = [a for a in rest if a not in ("--dry-run", "--yes")]
        return subprocess.run([sys.executable, str(KIT / "scripts" / "install.py"), "--update", *rest]).returncode
    if verb == "notices" and rest in (["on"], ["off"]):
        return notices(rest[0])
    if verb == "onboard":
        return onboard(rest)
    if verb == "demo" and rest and rest[0] in DEMO_VERBS:
        return subprocess.run([sys.executable, str(KIT / "demos" / f"{rest[0]}.py"), *rest[1:]]).returncode
    verbs = ["status", "update", "notices on|off", "onboard <n>"] + [f"demo {v}" for v in DEMO_VERBS]
    print(f"unknown command: {' '.join(argv)}\n{json.dumps(verbs)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
