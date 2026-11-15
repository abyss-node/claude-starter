"""A stand-in for the `opencode` binary, 1.x or 2.x, for testing the installer's load check without one.

It answers from the config folder it finds in its environment, the way OpenCode does (OPENCODE_CONFIG_DIR,
else $XDG_CONFIG_HOME/opencode, else ~/.config/opencode), and reproduces what makes a 2.x check lie or
hang, each observed on 2.3.0:
  - `serve` keeps the config it started with, and always has a password (OPENCODE_PASSWORD, else
    OPENCODE_SERVER_PASSWORD, else a random one) that `api --server` must send;
  - `api` without `--server` is the background service, answering for `service_config_dir`;
  - a server's first `partial_reads` answers to each operation carry only the built-in entries;
  - a server also lists `.opencode/commands` and `.claude/skills` in every folder above its working
    directory, unless OPENCODE_DISABLE_PROJECT_CONFIG is 1;
  - 2.x refuses `agent list` with "Unexpected positional argument".
Behaviour comes from $FAKE_OC_DIR/fake.json; every call is appended to $FAKE_OC_DIR/calls.jsonl.
  version             what `--version` prints ("opencode v2.3.0" or "1.19.5")
  partial_reads       per operation and server (default 1)
  hang                any of "version", "serve", "api:<operation>": sleep hang_seconds instead
  hang_seconds        default 20; bounded, so a check that fails to time out still finishes
  leak                `api` leaves a child holding its stdout and stderr for hang_seconds
  extra_rules         {agent: [rules appended after the agent's own]}
  late_rules          the same, but only from the second complete answer on (an answer that changes)
  prompt              `api` first reads a line from stdin, as a password prompt would
  extra_skills        [{"name", "path"}], listed after the config's; one per name, the config's first
  service_config_dir  the folder the background service answers for
"""
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

STATE = Path(os.environ["FAKE_OC_DIR"])
FAKE = json.loads((STATE / "fake.json").read_text(encoding="utf-8")) if (STATE / "fake.json").is_file() else {}
V2_ACTION = {"bash": "shell", "task": "subagent"}
BUILTIN_AGENTS = [("build", "primary"), ("general", "subagent")]


def say(obj) -> None:
    sys.stdout.write(obj if isinstance(obj, str) else json.dumps(obj))
    sys.stdout.write("\n")
    sys.stdout.flush()


def hang(what: str) -> None:
    if what in FAKE.get("hang", []):
        time.sleep(FAKE.get("hang_seconds", 20))
        sys.exit(9)


def config_dir(env) -> Path:
    if env.get("OPENCODE_CONFIG_DIR"):
        return Path(env["OPENCODE_CONFIG_DIR"])
    return Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "opencode"


def frontmatter(path: Path) -> list:
    text = path.read_text(encoding="utf-8")
    return text.split("\n---", 1)[0].splitlines() if text.startswith("---") else []


def agents(cfg: Path, late: bool = False) -> list:
    out = [{"id": a, "mode": m, "permissions": [{"action": "*", "resource": "*", "effect": "allow"}]}
           for a, m in BUILTIN_AGENTS]
    for f in sorted((cfg / "agents").glob("*.md")):
        fm = frontmatter(f)
        mode = next((ln.split(":", 1)[1].strip() for ln in fm if ln.startswith("mode:")), "all")
        rules = [{"action": "*", "resource": "*", "effect": "allow"}]
        for key, effect in re.findall(r"^  (\w+): (\w+)$", "\n".join(fm), re.M):
            rules.append({"action": V2_ACTION.get(key, key), "resource": "*", "effect": effect})
        rules += FAKE.get("extra_rules", {}).get(f.stem, [])
        rules += FAKE.get("late_rules", {}).get(f.stem, []) if late else []
        out.append({"id": f.stem, "mode": mode, "permissions": rules})
    return out


def skills(cfg: Path) -> list:
    out = [{"name": "OpenCode", "path": "skill://opencode/SKILL.md"}]
    for f in sorted((cfg / "skills").glob("*/SKILL.md")):
        out.append({"name": f.parent.name, "path": str(f)})
    names = {s["name"] for s in out}
    return out + [s for s in FAKE.get("extra_skills", []) if s["name"] not in names]


def commands(cfg: Path) -> list:
    return [{"name": "init"}] + [{"name": f.stem} for f in sorted((cfg / "commands").glob("*.md"))]


def project(op: str, cwd: Path) -> list:
    """What a 2.x server adds from the folders above its working directory."""
    out = []
    for d in [cwd, *cwd.parents]:
        if op == "command.list":
            out += [{"name": f.stem} for f in sorted((d / ".opencode" / "commands").glob("*.md"))]
        elif op == "skill.list":
            out += [{"name": f.parent.name, "path": str(f)} for f in sorted((d / ".claude" / "skills").glob("*/SKILL.md"))]
    return out


LISTS = {"agent.list": agents, "skill.list": skills, "command.list": commands}
BUILTIN = {"agent.list": 2, "skill.list": 1, "command.list": 1}  # what a read before discovery shows


def serve(env) -> None:
    hang("serve")
    servers = STATE / "servers"
    servers.mkdir(exist_ok=True)
    port = random.randint(20000, 60000)
    password = env.get("OPENCODE_PASSWORD") or env.get("OPENCODE_SERVER_PASSWORD") or "%032x" % random.getrandbits(128)
    (servers / f"{port}.json").write_text(json.dumps(
        {"password": password, "config_dir": str(config_dir(env)), "pid": os.getpid(), "cwd": os.getcwd(),
         "project": env.get("OPENCODE_DISABLE_PROJECT_CONFIG") != "1"}), encoding="utf-8")
    say(f"server listening on http://127.0.0.1:{port}")
    time.sleep(600)  # until the check kills it; bounded so a check that never does cannot strand it


def api(argv: list, env) -> int:
    op = argv[-1]
    hang(f"api:{op}")
    if FAKE.get("prompt") and not sys.stdin.readline():
        print("Error: no password entered", file=sys.stderr)
        return 1
    if FAKE.get("leak"):  # handed over explicitly: on Windows a child inherits no handle it is not given
        subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({FAKE.get('hang_seconds', 20)})"],
                         stdout=sys.stdout, stderr=sys.stderr)
    if "--server" not in argv:  # the background service, with whatever config it started with
        cfg = Path(FAKE.get("service_config_dir") or STATE / "service-config")
        say({"location": {"directory": os.getcwd()}, "data": LISTS[op](cfg)})
        return 0
    url = argv[argv.index("--server") + 1]
    port = url.rsplit(":", 1)[-1]
    info = STATE / "servers" / f"{port}.json"
    if not info.is_file():
        print(f"Error: Could not reach server at {url}", file=sys.stderr)
        return 1
    server = json.loads(info.read_text(encoding="utf-8"))
    sent = env.get("OPENCODE_PASSWORD")
    if sent != server["password"]:
        print(f"Error: Server at {url} " + ("rejected the password" if sent else
                                            "requires a password; set OPENCODE_PASSWORD"), file=sys.stderr)
        return 1
    count = STATE / "servers" / f"{port}.{op}.count"
    n = int(count.read_text(encoding="utf-8")) + 1 if count.is_file() else 1
    count.write_text(str(n), encoding="utf-8")
    full = n - FAKE.get("partial_reads", 1)  # how many complete answers, this one included
    data = agents(Path(server["config_dir"]), full > 1) if op == "agent.list" else LISTS[op](Path(server["config_dir"]))
    if server["project"]:
        names = {x.get("name") for x in data}
        data += [x for x in project(op, Path(server["cwd"])) if x["name"] not in names]
    if n <= FAKE.get("partial_reads", 1):
        data = data[:BUILTIN[op]]
    say({"location": {"directory": os.getcwd()}, "data": data})
    return 0


def v1(argv: list, env) -> int:
    cfg = config_dir(env)
    if argv[:2] == ["agent", "list"]:
        say("\n".join(f"{a['id']} ({a['mode']})" for a in agents(cfg)))
    elif argv[:2] == ["debug", "agent"]:
        f = cfg / "agents" / f"{argv[2]}.md"
        tools = dict.fromkeys(["bash", "edit", "write", "read", "task", "webfetch", "websearch"], True)
        for key in re.findall(r"^  (\w+): deny$", "\n".join(frontmatter(f)) if f.is_file() else "", re.M):
            tools.update({"edit": False, "write": False} if key == "edit" else {key: False})
        say({"name": argv[2], "tools": tools})
    elif argv[:2] == ["debug", "skill"]:
        say([{"name": s["name"], "location": s["path"]} for s in skills(cfg)])
    elif argv[:2] == ["debug", "config"]:
        say({"command": {c["name"]: {} for c in commands(cfg)}})
    else:
        print(f"unknown command: {' '.join(argv)}", file=sys.stderr)
        return 1
    return 0


def main(argv: list) -> int:
    env = os.environ
    with open(STATE / "calls.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps({"argv": argv, "password": env.get("OPENCODE_PASSWORD")}) + "\n")
    version = FAKE.get("version", "opencode v2.3.0")
    if argv[:1] in (["--version"], ["-v"]):
        hang("version")
        say(version)
        return 0
    major = re.search(r"(\d+)\.\d+\.\d+", version)
    if major and major.group(1) == "1":
        return v1(argv, env)
    if argv[:1] == ["serve"]:
        serve(env)
        return 0
    if argv[:1] == ["api"]:
        return api(argv, env)
    print(f"Error: Unexpected positional argument: {argv[0] if argv else ''}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
