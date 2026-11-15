#!/usr/bin/env python3
"""The kit's launcher: one command per verb, the same in every tool.

    python ~/.claude-starter/scripts/starter.py status          # the install record; no network
    python ~/.claude-starter/scripts/starter.py update          # show the update plan; changes nothing
    python ~/.claude-starter/scripts/starter.py update --yes --to <sha> --plan <id>   # apply that plan
    python ~/.claude-starter/scripts/starter.py notices on|off  # the once-a-day update notice

`update` runs install.py --update with the rest of the arguments and exits with its exit code
(0 done, 1 failed, 2 wrong command, 3 cannot write or fetch). It uses subprocess, never os.exec*:
on Windows exec hands the caller exit 0 before the child finishes (bpo-19124).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # a plan leaves the clone byte-identical, __pycache__ included
KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import install  # noqa: E402


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
    return 0


def notices(value: str) -> int:
    rec = install.load_record()
    if not rec:
        print(f"No install recorded at {install.record_path()} yet. Install first; for an install made before "
              "v0.4.0, run `update` and apply its plan, which records it. Then run this again.", file=sys.stderr)
        return 2
    rec.setdefault("notices", {})["update"] = value == "on"
    install.save_record(rec)
    print(f"update notices: {value}")
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
    print(f"unknown command: {' '.join(argv)}\n{json.dumps(['status', 'update', 'notices on|off'])}",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
