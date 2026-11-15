#!/usr/bin/env python3
"""SessionStart hook: relay the kit's update notice, if any, to the person and to the model.

It runs `scripts/update_check.py` from the kit clone and does nothing else. The clone is the record's
`kit.kit_root` (~/.agents/starter/installs.json, as install.py writes it), else the documented
~/.claude-starter. update_check.py decides whether notices are on, caches its check for a day and
prints one line or nothing; this hook never fetches and never updates.

Claude Code adds a SessionStart hook's plain stdout to the model's context only, and shows a JSON
`systemMessage` to the user (https://code.claude.com/docs/en/hooks, "JSON output"). So a line is printed
as JSON carrying both. Anything that goes wrong (no clone, no Python script, a timeout, a non-zero exit,
no output) prints nothing and exits 0, so the hook never slows or breaks a session start.
"""
import json
import subprocess
import sys
from pathlib import Path

TIMEOUT_S = 8  # update_check.py bounds its own network call at 3 s


def kit_root() -> Path:
    record = Path.home() / ".agents" / "starter" / "installs.json"
    try:
        root = (json.loads(record.read_text(encoding="utf-8")).get("kit") or {}).get("kit_root")
        if isinstance(root, str) and root:
            return Path(root)
    except (OSError, ValueError, AttributeError):
        pass
    return Path.home() / ".claude-starter"


def notice() -> str:
    script = kit_root() / "scripts" / "update_check.py"
    if not script.is_file():
        return ""
    try:
        r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=TIMEOUT_S, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    return lines[0] if r.returncode == 0 and len(lines) == 1 else ""


def main() -> int:
    line = notice()
    if line:
        print(json.dumps({
            "systemMessage": line,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "claude-starter update notice (already shown to the user): " + line
                                     + " Do not run the update unless the user asks for it.",
            },
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
